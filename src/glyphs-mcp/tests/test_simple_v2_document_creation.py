"""Font creation identity, uncertain-response recovery and native adapter contracts."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import uuid4
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
for component in ("protocol", "bridge", "sidecar"):
    sys.path.insert(0, str(ROOT / "src" / component))

from glyphs_mcp_protocol import document_creation as contract, ProtocolError
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_sidecar.bridge_client import BridgeClientError
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.service import SidecarService, ServiceError


@pytest.fixture
def host(monkeypatch):
    glyphs = NS(fonts=[])

    class Font:
        def __init__(self):
            self.familyName = "Untitled"
            self.upm = 1000
            self.filepath = None
            self.parent = None
            # Deliberate existing constructor defaults must not be duplicated.
            self.masters = [NS(id="default-master", axes=[100], name="Default")]
            self.instances = [NS(id="default-instance", axes=[100], name="Default")]

        def show(self):
            self.parent = NS(isDocumentEdited=True, changeCount=1)
            glyphs.fonts.append(self)

    def master():
        return NS(id=str(uuid4()), name="", axes=[100])

    def instance():
        return NS(id=str(uuid4()), name="", axes=[])

    monkeypatch.setitem(sys.modules, "GlyphsApp", NS(GSFont=Font, GSFontMaster=master, GSInstance=instance))
    return glyphs, Font


class Bridge:
    def __init__(self, core):
        self.core, self.calls, self.lose_response = core, 0, False

    def status(self):
        return self.core.status()

    def create_document(self, request):
        self.calls += 1
        try:
            result = self.core.create_document(request)
        except BridgeError as exc:
            raise BridgeClientError(exc.code, exc.message, exc.details) from exc
        if self.lose_response:
            self.lose_response = False
            raise BridgeClientError("bridge_unavailable", "lost response", {"execution": "uncertain", "creationId": request["creationId"]})
        return result


def setup(host, tmp_path):
    glyphs, _ = host
    core = BridgeCore(GlyphsAdapter(glyphs), lambda callback: callback())
    bridge = Bridge(core)
    service = SidecarService(bridge, jobs=JobStore(tmp_path), worker=NS(status=lambda: {}))
    return glyphs, core, bridge, service


@pytest.mark.parametrize("family,key,upm", [(None, "key", 1000), ("", "key", 1000), ("a\nb", "key", 1000),
    ("A", "", 1000), ("A", "x" * 256, 1000), ("A", "key", True), ("A", "key", 1000.0),
    ("A", "key", 15), ("A", "key", 16385)])
def test_invalid_input_never_creates(host, tmp_path, family, key, upm):
    glyphs, _, bridge, service = setup(host, tmp_path)
    with pytest.raises(ServiceError) as error:
        service.create_document(family, key, upm)
    assert error.value.code == "invalid_request"
    assert bridge.calls == 0 and glyphs.fonts == []


def test_create_normalizes_defaults_and_returns_live_ids(host, tmp_path):
    glyphs, core, _, service = setup(host, tmp_path)
    original = NS(filepath="/tmp/existing.glyphs", parent=NS(isDocumentEdited=True, changeCount=17))
    glyphs.fonts.append(original)
    before = core.adapter.document_state(core.adapter._id(original))
    result = service.create_document("  Test Family  ", "one", 2048)
    font = core.adapter._font(result["id"])
    assert font.familyName == "Test Family" and font.upm == 2048
    assert len(font.masters) == len(font.instances) == 1
    assert font.masters[0].name == font.instances[0].name == "Regular"
    assert font.instances[0].axes == font.masters[0].axes
    assert result["masterIds"] == [font.masters[0].id]
    assert result["instanceIds"] == [font.instances[0].id]
    assert result["path"] is None and result["dirty"] is True
    assert core.adapter.document_state(before["id"]) == before
    assert "document.create.v1" in service.get_status()["writeCapabilities"]


def test_lost_response_and_sidecar_restart_reuse_original_font(host, tmp_path):
    glyphs, _, bridge, service = setup(host, tmp_path)
    bridge.lose_response = True
    with pytest.raises(ServiceError) as error:
        service.create_document("Recover", "one")
    assert error.value.details["execution"] == "uncertain"
    restarted = SidecarService(bridge, jobs=JobStore(tmp_path))
    result = restarted.create_document("Recover", "one")
    assert len(glyphs.fonts) == 1
    assert result == service.create_document("Recover", "one")


def test_concurrent_services_share_creation_key(host, tmp_path):
    glyphs, _, bridge, first = setup(host, tmp_path)
    second = SidecarService(bridge, jobs=JobStore(tmp_path))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.create_document, "Concurrent", "one") for service in (first, second)]
        results = [future.result() for future in futures]
    assert results[0]["id"] == results[1]["id"] and len(glyphs.fonts) == 1


def test_key_conflicts_and_closed_fonts_never_recreate(host, tmp_path):
    glyphs, core, _, service = setup(host, tmp_path)
    result = service.create_document("Original", "one")
    for kwargs in ({"family_name": "Other"}, {"family_name": "Original", "units_per_em": 2048}):
        with pytest.raises(ServiceError) as error:
            service.create_document(idempotency_key="one", **kwargs)
        assert error.value.code == "creation_conflict"
    direct = {**contract.options("Other", "one"), "bridgeSessionId": core.bridge_session_id}
    with pytest.raises(BridgeError) as error:
        core.create_document(direct)
    assert error.value.code == "creation_conflict"
    glyphs.fonts.clear()
    with pytest.raises(ServiceError) as error:
        service.create_document("Original", "one")
    assert error.value.code == "document_not_found" and glyphs.fonts == []
    assert result["id"]


def test_bridge_restart_and_corrupt_journal_fail_closed(host, tmp_path):
    glyphs, core, bridge, service = setup(host, tmp_path)
    service.create_document("Original", "one")
    bridge.core = BridgeCore(core.adapter, lambda callback: callback())
    with pytest.raises(ServiceError) as error:
        service.create_document("Original", "one")
    assert error.value.code == "creation_outcome_unknown" and len(glyphs.fonts) == 1
    record = next((tmp_path / "document-creations").glob("*.json"))
    record.write_text("broken")
    with pytest.raises(ServiceError) as error:
        service.create_document("Original", "one")
    assert error.value.code == "creation_outcome_unknown" and len(glyphs.fonts) == 1


def test_native_partial_failure_is_retained_and_reports_owned_document(host, tmp_path, monkeypatch):
    glyphs, Font = host
    original_show = Font.show
    def broken_show(self):
        original_show(self)
        raise RuntimeError("window failed after attachment")
    monkeypatch.setattr(Font, "show", broken_show)
    _, _, _, service = setup(host, tmp_path)
    for _ in range(2):
        with pytest.raises(ServiceError) as error:
            service.create_document("Partial", "one")
        assert error.value.code == "creation_failed"
        assert error.value.details["documentId"].startswith("doc_")
    assert len(glyphs.fonts) == 1


def test_missing_capability_and_reservation_refuse_creation(host, tmp_path, monkeypatch):
    glyphs, _, bridge, service = setup(host, tmp_path)
    monkeypatch.setattr(bridge, "status", lambda: {"writeCapabilities": []})
    with pytest.raises(ServiceError) as error:
        service.create_document("A", "one")
    assert error.value.code == "unsupported_capability"
    service.lifecycle.reservation = {"id": "reserved", "deadline": float("inf")}
    with pytest.raises(ServiceError) as error:
        service.create_document("A", "two")
    assert error.value.code == "service_reserved" and glyphs.fonts == []


def test_creation_limit_never_evicts_completed_keys(host, tmp_path, monkeypatch):
    from glyphs_mcp_bridge import document_creation
    glyphs, _, _, service = setup(host, tmp_path)
    monkeypatch.setattr(document_creation, "MAX_CREATIONS", 1)
    original = service.create_document("A", "one")
    with pytest.raises(ServiceError) as error:
        service.create_document("B", "two")
    assert error.value.code == "creation_limit_reached"
    assert service.create_document("A", "one")["id"] == original["id"] and len(glyphs.fonts) == 1


def test_bridge_rejects_unknown_fields_and_stale_session(host, tmp_path):
    _, core, _, _ = setup(host, tmp_path)
    request = {**contract.options("A", "one"), "bridgeSessionId": core.bridge_session_id}
    with pytest.raises(BridgeError) as error:
        core.create_document({**request, "destination": "/tmp/a.glyphs"})
    assert error.value.code == "invalid_request"
    with pytest.raises(BridgeError) as error:
        core.create_document({**request, "bridgeSessionId": "old"})
    assert error.value.code == "creation_outcome_unknown"


def test_mcp_client_exposes_creation_without_document_id(host, tmp_path):
    import asyncio
    from fastmcp import Client
    from glyphs_mcp_sidecar.server import create_server
    glyphs, _, _, service = setup(host, tmp_path)
    async def exercise():
        async with Client(create_server(service)) as client:
            catalog = {tool.name: tool for tool in await client.list_tools()}
            assert len(catalog) == 18
            assert set(catalog["create_document"].inputSchema["required"]) == {"family_name", "idempotency_key"}
            first = await client.call_tool("create_document", {"family_name": "Client", "idempotency_key": "client"})
            second = await client.call_tool("create_document", {"family_name": "Client", "idempotency_key": "client"})
            assert first.data["ok"] and first.data["data"]["id"] == second.data["data"]["id"]
    asyncio.run(exercise())
    assert len(glyphs.fonts) == 1


@pytest.mark.parametrize("suffix", [".glyphs", ".glyphspackage"])
def test_created_pathless_font_uses_existing_verified_save_as(host, tmp_path, suffix, monkeypatch):
    from glyphs_mcp_sidecar.saving import prepare_save, verify_save
    from glyphs_mcp_bridge import native_save
    glyphs, core, _, service = setup(host, tmp_path)
    result = service.create_document("Save As", "one")
    font = glyphs.fonts[0]
    destination = tmp_path / ("New" + suffix)
    request = prepare_save("save_test", result, str(destination), [result])
    writes = []
    def save(url, type_name, operation, error):
        writes.append((url, type_name, operation))
        if suffix == ".glyphspackage":
            destination.mkdir()
            (destination / "fontinfo.plist").write_text("{familyName = \"Save As\";}")
            (destination / "glyphs").mkdir()
        else:
            destination.write_text("{familyName = \"Save As\";}")
        font.filepath = str(destination)
        font.parent.isDocumentEdited = False
        return True, None
    font.parent.saveToURL_ofType_forSaveOperation_error_ = save
    monkeypatch.setitem(sys.modules, "Foundation", NS(NSURL=NS(fileURLWithPath_=lambda path: path)))
    monkeypatch.setitem(sys.modules, "AppKit", NS(NSSaveOperation=0, NSSaveAsOperation=1))
    saved = native_save.save_document(core.adapter, result["id"], str(destination), "save_as", BridgeError)
    receipt = verify_save(request, saved)
    assert receipt["documentId"] == result["id"] and len(writes) == 1
    with pytest.raises(Exception) as error:
        prepare_save("save_again", result, str(destination), [result])
    assert error.value.code == "destination_exists"
    assert len(writes) == 1


def test_bridge_http_route_and_client_transport_preserve_creation_identity(host, tmp_path, monkeypatch):
    from glyphs_mcp_bridge.http_server import BridgeHTTPServer
    from glyphs_mcp_sidecar.bridge_client import BridgeClient
    from glyphs_mcp_sidecar import bridge_client
    _, core, _, _ = setup(host, tmp_path)
    request = {**contract.options("HTTP", "one"), "bridgeSessionId": core.bridge_session_id}
    owner = object.__new__(BridgeHTTPServer)
    owner.core = core
    handler_class = owner._handler()
    handler = object.__new__(handler_class)
    handler.path = "/v1/documents/create"
    first = handler._route({"creation": request})
    assert handler._route({"creation": request})["id"] == first["id"]
    core.paused = True
    with pytest.raises(BridgeError) as error:
        handler._route({"creation": request})
    assert error.value.code == "server_stopped"
    def lost_response(*args, **kwargs):
        raise TimeoutError("response lost")
    monkeypatch.setattr(bridge_client, "urlopen", lost_response)
    with pytest.raises(BridgeClientError) as error:
        BridgeClient("http://localhost", "test").create_document(request)
    assert error.value.details == {"execution": "uncertain", "creationId": request["creationId"]}
