"""Open native sources without duplicate windows, saves or retry replay."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace as NS
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
for component in ("protocol", "bridge", "sidecar"):
    sys.path.insert(0, str(ROOT / "src" / component))

from glyphs_mcp_protocol import document_opening as contract
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_sidecar.bridge_client import BridgeClient, BridgeClientError
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.service import SidecarService, ServiceError


class Host:
    def __init__(self):
        self.fonts, self.calls = [], []
        self.failure = None

    def open(self, path, showInterface=True):
        self.calls.append((path, showInterface))
        if self.failure == "none":
            return None
        font = NS(filepath=path, familyName="Opened Family", parent=NS(isDocumentEdited=False, changeCount=0))
        self.fonts.append(font)
        if self.failure == "after_attachment":
            raise RuntimeError("window failed after attachment")
        if self.failure == "wrong_source":
            font.filepath = str(Path(path).with_name("Other.glyphs"))
        return font


class Bridge:
    def __init__(self, core):
        self.core, self.calls, self.lose_response = core, 0, False

    def status(self):
        return self.core.status()

    def documents(self):
        return self.core.list_documents()

    def open_document(self, request):
        self.calls += 1
        try:
            result = self.core.open_document(request)
        except BridgeError as exc:
            raise BridgeClientError(exc.code, exc.message, exc.details) from exc
        if self.lose_response:
            self.lose_response = False
            raise BridgeClientError("bridge_unavailable", "lost response", {"execution": "uncertain", "openId": request["openId"]})
        return result


def setup(tmp_path):
    host = Host()
    core = BridgeCore(GlyphsAdapter(host), lambda callback: callback())
    bridge = Bridge(core)
    service = SidecarService(bridge, jobs=JobStore(tmp_path / "jobs"), worker=NS(status=lambda: {}))
    return host, core, bridge, service


def source(tmp_path, suffix=".glyphs", name="Source"):
    path = tmp_path / (name + suffix)
    if suffix == ".glyphspackage":
        path.mkdir(); (path / "fontinfo.plist").write_text("fixture")
    else:
        path.write_text("fixture")
    return path


@pytest.mark.parametrize("value", [None, "", "relative.glyphs", "~/Font.glyphs", "file:///tmp/Font.glyphs",
                                  "/tmp/Font.otf", "/tmp/Font.glyphs\n", "/tmp/Font\x00.glyphs"])
def test_invalid_paths_do_not_dispatch(tmp_path, value):
    host, _, bridge, service = setup(tmp_path)
    with pytest.raises(ServiceError) as error:
        service.open_document(value, "one")
    assert error.value.code in {"invalid_request", "unsupported_format"}
    assert not bridge.calls and not host.fonts


@pytest.mark.parametrize("key", [None, "", "x" * 256, "bad\nkey"])
def test_invalid_keys_do_not_dispatch(tmp_path, key):
    host, _, bridge, service = setup(tmp_path)
    with pytest.raises(ServiceError) as error:
        service.open_document(str(source(tmp_path)), key)
    assert error.value.code == "invalid_request"
    assert not bridge.calls and not host.fonts


@pytest.mark.parametrize("kind", ["missing", "wrong_file", "wrong_folder"])
def test_missing_or_wrong_source_types_do_not_dispatch(tmp_path, kind):
    host, _, bridge, service = setup(tmp_path)
    path = tmp_path / ("Missing.glyphs" if kind == "missing" else "Wrong.glyphspackage" if kind == "wrong_file" else "Wrong.glyphs")
    if kind == "wrong_file": path.write_text("wrong")
    if kind == "wrong_folder": path.mkdir()
    with pytest.raises(ServiceError) as error:
        service.open_document(str(path), "one")
    assert error.value.code == ("file_not_found" if kind == "missing" else "invalid_request")
    assert not bridge.calls and not host.fonts


@pytest.mark.parametrize("suffix", [".glyphs", ".glyphspackage"])
def test_opens_source_and_preserves_other_unsaved_font(tmp_path, suffix):
    host, core, _, service = setup(tmp_path)
    original = NS(filepath=None, familyName="Unsaved", parent=NS(isDocumentEdited=True, changeCount=17))
    host.fonts.append(original)
    before = core.adapter.document_state(core.adapter._id(original))
    path = source(tmp_path, suffix, "Unicode é and spaces")
    result = service.open_document(str(path), "one")
    assert result["path"] == str(path.resolve()) and result["id"].startswith("doc_")
    assert result["familyName"] == "Opened Family" and result["alreadyOpen"] is False
    assert result["dirty"] is False and result["generation"] == 0
    assert host.calls == [(str(path.resolve()), True)] and len(host.fonts) == 2
    assert core.adapter.document_state(before["id"]) == before
    assert "document.open.v1" in service.get_status()["writeCapabilities"]


def test_already_open_dirty_source_and_alias_are_reused_without_reload(tmp_path):
    host, core, _, service = setup(tmp_path)
    path = source(tmp_path)
    existing = NS(filepath=str(path), familyName="Edited", parent=NS(isDocumentEdited=True, changeCount=19))
    host.fonts.append(existing)
    before = core.adapter.document_state(core.adapter._id(existing))
    alias = tmp_path / "Alias.glyphs"; alias.symlink_to(path)
    result = service.open_document(str(alias), "one")
    assert result["alreadyOpen"] is True and result["id"] == before["id"]
    assert result["dirty"] is True and result["generation"] == 19
    assert core.adapter.document_state(before["id"]) == before
    assert host.calls == [] and host.fonts == [existing]


def test_ambiguous_open_sources_do_not_select_an_arbitrary_font(tmp_path):
    host, core, _, service = setup(tmp_path)
    path = source(tmp_path)
    host.fonts = [NS(filepath=str(path), familyName=name, parent=NS(isDocumentEdited=True, changeCount=7))
                  for name in ("First copy", "Second copy")]
    with pytest.raises(ServiceError) as error:
        service.open_document(str(path), "one")
    assert error.value.code == "ambiguous_document"
    assert set(error.value.details["documentIds"]) == {core.adapter._id(font) for font in host.fonts}
    assert error.value.details["openingAttempted"] is False and not host.calls
    assert all(font.parent.isDocumentEdited for font in host.fonts)


def test_lost_response_and_sidecar_restart_return_the_original_document(tmp_path):
    host, _, bridge, service = setup(tmp_path)
    path = source(tmp_path); bridge.lose_response = True
    with pytest.raises(ServiceError) as error:
        service.open_document(str(path), "one")
    assert error.value.details["execution"] == "uncertain"
    restarted = SidecarService(bridge, jobs=service.jobs)
    result = restarted.open_document(str(path), "one")
    assert result == service.open_document(str(path), "one")
    assert len(host.calls) == len(host.fonts) == 1
    host.fonts[0].parent.changeCount = 7; host.fonts[0].parent.isDocumentEdited = True
    path.unlink()
    fresh = restarted.open_document(str(path), "one")
    assert fresh["dirty"] is True and fresh["generation"] == 7
    assert len(host.calls) == 1


def test_concurrent_services_and_distinct_keys_do_not_duplicate_the_font(tmp_path):
    host, _, bridge, first = setup(tmp_path)
    path = source(tmp_path)
    second = SidecarService(bridge, jobs=first.jobs)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: pair[0].open_document(str(path), pair[1]), [(first, "one"), (second, "two")]))
    assert results[0]["id"] == results[1]["id"]
    assert len(host.calls) == len(host.fonts) == 1


def test_retry_keeps_original_binding_after_family_rename_or_save_as(tmp_path):
    host, _, _, service = setup(tmp_path)
    path = source(tmp_path); changed_path = source(tmp_path, name="Saved As")
    original = service.open_document(str(path), "one")
    host.fonts[0].familyName = "Renamed Family"; host.fonts[0].filepath = str(changed_path)
    result = service.open_document(str(path), "one")
    assert result["id"] == original["id"] and result["path"] == str(changed_path)
    assert result["familyName"] == "Renamed Family" and len(host.calls) == 1


def test_retargeted_file_alias_cannot_redirect_an_existing_key(tmp_path):
    host, _, _, service = setup(tmp_path)
    path = source(tmp_path); other = source(tmp_path, name="Other")
    alias = tmp_path / "Alias.glyphs"; alias.symlink_to(path)
    service.open_document(str(alias), "one")
    alias.unlink(); alias.symlink_to(other)
    with pytest.raises(ServiceError) as error: service.open_document(str(alias), "one")
    assert error.value.code == "opening_conflict" and len(host.calls) == 1


def test_conflicting_keys_and_closed_documents_do_not_reopen(tmp_path):
    host, core, _, service = setup(tmp_path)
    path = source(tmp_path); other = source(tmp_path, name="Other")
    service.open_document(str(path), "one")
    with pytest.raises(ServiceError) as error:
        service.open_document(str(other), "one")
    assert error.value.code == "opening_conflict"
    direct = {**contract.options(str(other), "one"), "bridgeSessionId": core.bridge_session_id}
    with pytest.raises(BridgeError) as error:
        core.open_document(direct)
    assert error.value.code == "opening_conflict"
    host.fonts.clear()
    with pytest.raises(ServiceError) as error:
        service.open_document(str(path), "one")
    assert error.value.code == "document_not_found" and len(host.calls) == 1
    service.open_document(str(path), "new-user-request")
    assert len(host.calls) == 2


def test_bridge_restart_and_corrupt_record_require_reconciliation(tmp_path):
    host, core, bridge, service = setup(tmp_path)
    path = source(tmp_path); service.open_document(str(path), "one")
    bridge.core = BridgeCore(core.adapter, lambda callback: callback())
    with pytest.raises(ServiceError) as error:
        service.open_document(str(path), "one")
    assert error.value.code == "opening_outcome_unknown" and len(host.calls) == 1
    next((service.jobs.root / "document-openings").glob("*.json")).write_text("broken")
    with pytest.raises(ServiceError) as error:
        service.open_document(str(path), "one")
    assert error.value.code == "opening_outcome_unknown" and len(host.calls) == 1


@pytest.mark.parametrize("failure", ["none", "after_attachment", "wrong_source"])
def test_native_failure_is_retained_without_replay_or_implicit_close(tmp_path, failure):
    host, _, _, service = setup(tmp_path)
    path = source(tmp_path); host.failure = failure
    for _ in range(2):
        with pytest.raises(ServiceError) as error:
            service.open_document(str(path), "one")
        assert error.value.code == "opening_failed"
        if failure == "after_attachment": assert error.value.details["documentId"].startswith("doc_")
    assert len(host.calls) == 1
    assert len(host.fonts) == (0 if failure == "none" else 1)


def test_capability_stop_reservation_and_capacity_checks(tmp_path, monkeypatch):
    from glyphs_mcp_bridge import document_opening
    host, core, bridge, service = setup(tmp_path)
    path = source(tmp_path)
    monkeypatch.setattr(document_opening, "MAX_OPENINGS", 1)
    first = service.open_document(str(path), "one")
    with pytest.raises(ServiceError) as error: service.open_document(str(path), "two")
    assert error.value.code == "opening_limit_reached"
    assert service.open_document(str(path), "one")["id"] == first["id"]
    core.paused = True
    with pytest.raises(ServiceError) as error: service.open_document(str(path), "one")
    assert error.value.code == "server_stopped"
    core.paused = False
    monkeypatch.setattr(bridge, "status", lambda: {"writeCapabilities": []})
    with pytest.raises(ServiceError) as error: service.open_document(str(path), "three")
    assert error.value.code == "unsupported_capability"
    service.lifecycle.reservation = {"id": "reserved", "deadline": float("inf")}
    with pytest.raises(ServiceError) as error: service.open_document(str(path), "four")
    assert error.value.code == "service_reserved" and len(host.calls) == 1


def test_bridge_transport_marks_open_timeouts_uncertain(tmp_path, monkeypatch):
    import glyphs_mcp_sidecar.bridge_client as transport
    request = {**contract.options(str(source(tmp_path)), "one"), "bridgeSessionId": "session"}
    def unavailable(*args, **kwargs): raise TimeoutError("timed out")
    monkeypatch.setattr(transport, "urlopen", unavailable)
    with pytest.raises(BridgeClientError) as error:
        BridgeClient("http://localhost", "token").open_document(request)
    assert error.value.details == {"execution": "uncertain", "openId": request["openId"]}


def test_bridge_http_route_preserves_the_open_identity(tmp_path):
    from glyphs_mcp_bridge.http_server import BridgeHTTPServer
    host, core, _, _ = setup(tmp_path)
    request = {**contract.options(str(source(tmp_path)), "one"), "bridgeSessionId": core.bridge_session_id}
    owner = object.__new__(BridgeHTTPServer); owner.core = core
    handler = object.__new__(owner._handler()); handler.path = "/v1/documents/open"
    first = handler._route({"opening": request})
    assert handler._route({"opening": request})["id"] == first["id"] and len(host.calls) == 1
    with pytest.raises(BridgeError) as error:
        handler._route({"opening": {**request, "unknown": True}})
    assert error.value.code == "invalid_request"
    core.paused = True
    with pytest.raises(BridgeError) as error: handler._route({"opening": request})
    assert error.value.code == "server_stopped"


def test_mcp_open_needs_no_existing_document_or_save(tmp_path):
    from fastmcp import Client
    from glyphs_mcp_sidecar.server import create_server
    host, _, _, service = setup(tmp_path)
    path = source(tmp_path)
    async def exercise():
        async with Client(create_server(service)) as client:
            catalog = {tool.name: tool for tool in await client.list_tools()}
            assert len(catalog) == 17
            assert set(catalog["open_document"].inputSchema["required"]) == {"path", "idempotency_key"}
            first = await client.call_tool("open_document", {"path": str(path), "idempotency_key": "client"})
            second = await client.call_tool("open_document", {"path": str(path), "idempotency_key": "client"})
            assert first.data["ok"] and first.data["data"]["id"] == second.data["data"]["id"]
    asyncio.run(exercise())
    assert len(host.calls) == len(host.fonts) == 1
