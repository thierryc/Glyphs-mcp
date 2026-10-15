"""Save-free Edit-tab transport, exact targeting and retry qualification."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
for component in ("protocol", "bridge", "sidecar"):
    sys.path.insert(0, str(ROOT / "src" / component))

from glyphs_mcp_protocol import edit_tabs as contract, ProtocolError, TOOL_NAMES
from glyphs_mcp_protocol.document_closing import OWNING_STATUSES
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_sidecar.bridge_client import BridgeClient, BridgeClientError
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.service import SidecarService, ServiceError


@pytest.fixture
def setup(tmp_path, monkeypatch):
    host = NS(fonts=[], font=None, shows=[], openings=[], activations=[], failure=None)

    class Font:
        def __init__(self, dirty=True):
            self.filepath, self.familyName = None, "Unsaved fixture"
            self.parent = NS(isDocumentEdited=dirty, changeCount=5)
            self.masters = [NS(id="M1"), NS(id="M2")]
            self.selectedFontMaster = self.masters[1]
            self.glyphs = {name: NS(layers={m.id: NS(name=name, layerId=m.id, width=600)
                                          for m in self.masters}) for name in ("A", "B")}
            self.tabs, self.currentTab = [], None
        def show(self):
            host.shows.append(self); host.font = self
            if host.failure == "show": raise RuntimeError("show failed")
        def newTab(self, content=""):
            host.openings.append((self, content))
            if host.failure == "before": raise RuntimeError("tab failed before attachment")
            if host.failure == "none": return None
            tab = NS(content=content, masterIndex=0)
            self.tabs.append(tab); self.currentTab = tab
            if host.failure == "after": raise RuntimeError("tab failed after attachment")
            return tab
        def save(self, *args, **kwargs): raise AssertionError("Tab opening must never save")
    host.documentController = lambda: NS()
    monkeypatch.setitem(sys.modules, "GlyphsApp", NS(GSFont=Font, Glyphs=host))
    monkeypatch.setitem(sys.modules, "AppKit", NS(NSApplication=NS(sharedApplication=lambda:
        NS(activateIgnoringOtherApps_=lambda flag: host.activations.append(flag)))))
    adapter = GlyphsAdapter(host)
    core = BridgeCore(adapter, lambda callback: callback())

    class Bridge:
        lose = False
        def status(self): return core.status()
        def documents(self): return core.list_documents()
        def open_edit_tab(self, request):
            try: result = core.open_edit_tab(request)
            except BridgeError as exc: raise BridgeClientError(exc.code, exc.message, exc.details) from exc
            if self.lose:
                self.lose = False
                raise BridgeClientError("bridge_unavailable", "lost response", {"execution": "uncertain"})
            return result
    bridge = Bridge()
    service = SidecarService(bridge, jobs=JobStore(tmp_path / "jobs"), worker=NS(status=lambda: {}))
    def add(dirty=True):
        font = Font(dirty); host.fonts.append(font)
        return font, adapter._id(font)
    return host, core, bridge, service, add


@pytest.mark.parametrize("content", [{}, {"text": "Aé\n/A/B"}, {"text": ""}, {"glyphs": ["B", "A", "B"]}])
def test_open_exact_unsaved_font_preserves_geometry_tabs_and_current_master(setup, content):
    host, core, _, service, add = setup
    font, identity = add(); other, _ = add(); host.font = other
    font.tabs.append(NS(content="existing", masterIndex=0))
    before = core.adapter.document_state(identity)
    result = service.open_edit_tab(identity, "one", **content)
    assert result["documentId"] == identity and result["masterId"] == "M2"
    assert result["created"] and result["activationRequested"]
    assert result["bridgeSessionId"] == core.bridge_session_id
    assert result["tabId"].startswith("edit_tab_") and len(font.tabs) == 2
    assert font.currentTab is font.tabs[-1] and font.currentTab.masterIndex == 1
    assert host.shows == [font] and host.activations == [True] and not other.tabs
    assert core.adapter.document_state(identity) == before
    assert all(layer.width == 600 for g in font.glyphs.values() for layer in g.layers.values())
    if "glyphs" in content:
        assert font.currentTab.content == [font.glyphs[n].layers["M2"] for n in content["glyphs"]]
    else: assert font.currentTab.content == content.get("text", "")
    assert contract.CAPABILITY in service.get_status()["writeCapabilities"]


def test_explicit_master_and_repeated_glyphs_use_exact_layers(setup):
    _, _, _, service, add = setup
    font, identity = add()
    result = service.open_edit_tab(identity, "one", glyphs=["A", "A"], master_id="M1")
    assert result["masterId"] == "M1" and font.currentTab.masterIndex == 0
    assert font.currentTab.content[0] is font.currentTab.content[1] is font.glyphs["A"].layers["M1"]


@pytest.mark.parametrize("kwargs", [{"text": "x", "glyphs": ["A"]}, {"glyphs": []},
    {"glyphs": ["A"] * 101}, {"glyphs": "A"}, {"glyphs": [1]}, {"glyphs": [""]},
    {"text": "x" * 4097}, {"text": 2}, {"text": "\x00"}, {"text": "\ud800"}, {"master_id": ""}])
def test_invalid_requests_never_open_or_show(setup, kwargs):
    host, _, _, service, add = setup
    _, identity = add()
    with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "one", **kwargs)
    assert exc.value.code == "invalid_request" and not host.openings and not host.shows


@pytest.mark.parametrize("kwargs", [{"glyphs": ["A", "missing"]}, {"master_id": "missing"},
    {"glyphs": ["A"], "master_id": "missing"}])
def test_missing_targets_reject_before_native_ui(setup, kwargs):
    host, _, _, service, add = setup
    _, identity = add()
    with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "one", **kwargs)
    assert exc.value.code == "target_not_found" and not host.openings and not host.shows


def test_missing_master_layer_rejects_without_partial_tab(setup):
    host, _, _, service, add = setup
    font, identity = add(); del font.glyphs["B"].layers["M2"]
    with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "one", glyphs=["A", "B"])
    assert exc.value.code == "target_not_found" and not host.openings


def test_lost_response_and_sidecar_restart_do_not_duplicate_tab(setup):
    host, _, bridge, service, add = setup
    font, identity = add(); bridge.lose = True
    with pytest.raises(ServiceError): service.open_edit_tab(identity, "one", text="A")
    restarted = SidecarService(bridge, jobs=JobStore(service.jobs.root))
    result = restarted.open_edit_tab(identity, "one", text="A")
    assert result == service.open_edit_tab(identity, "one", text="A")
    assert len(host.openings) == len(font.tabs) == 1
    assert len(host.shows) == len(host.activations) == 1
    assert restarted.open_edit_tab(identity, "two", text="A")["tabId"] != result["tabId"]
    assert len(font.tabs) == 2


def test_concurrent_sidecars_share_request_and_native_outcome(setup):
    host, _, bridge, service, add = setup
    font, identity = add()
    other = SidecarService(bridge, jobs=JobStore(service.jobs.root))
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda s: s.open_edit_tab(identity, "one"), [service, other]))
    assert results[0] == results[1] and len(host.openings) == len(font.tabs) == 1


def test_conflicts_closed_tab_document_and_restart_never_recreate(setup):
    host, core, _, service, add = setup
    font, identity = add(); other, second = add()
    service.open_edit_tab(identity, "one", text="A")
    for args in ((identity, {"text": "B"}), (second, {"text": "A"}), (identity, {"text": "A", "master_id": "M1"})):
        with pytest.raises(ServiceError) as exc: service.open_edit_tab(args[0], "one", **args[1])
        assert exc.value.code == "edit_tab_conflict"
    font.tabs.clear()
    with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "one", text="A")
    assert exc.value.code == "edit_tab_closed"
    host.fonts.remove(font)
    with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "one", text="A")
    assert exc.value.code == "document_not_found"
    core.bridge_session_id = "new-session"
    with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "one", text="A")
    assert exc.value.code == "edit_tab_outcome_unknown"
    assert len(host.openings) == 1 and not other.tabs


@pytest.mark.parametrize("failure,attached", [("show", False), ("before", False), ("after", True), ("none", False)])
def test_partial_native_failure_is_retained_and_not_replayed(setup, failure, attached):
    host, _, _, service, add = setup
    font, identity = add(); host.failure = failure
    errors = []
    for _ in range(2):
        with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "one")
        errors.append(exc.value.as_dict()); host.failure = None
    assert errors[0] == errors[1]
    assert errors[0]["code"] == ("edit_tab_open_failed" if failure == "show" else "edit_tab_outcome_unknown")
    assert bool(errors[0]["details"]["tabId"]) == attached
    assert len(host.shows) == 1 and len(host.openings) == (0 if failure == "show" else 1)
    assert len(font.tabs) == int(attached)


@pytest.mark.parametrize("state", sorted(OWNING_STATUSES - {"saving", "saved", "rolling_back"}))
def test_pending_sidecar_jobs_block_context_changes(setup, state):
    host, core, _, service, add = setup
    _, identity = add()
    job = service.jobs.create(core.adapter.document_state(identity), {"kind": "translate"})
    service.jobs.update(job["id"], status=state)
    with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "one")
    assert exc.value.code == "document_busy" and not host.openings


def test_native_ownership_paused_capabilities_and_session_guards(setup, monkeypatch):
    host, core, bridge, service, add = setup
    _, identity = add()
    request = {**contract.options(identity, "one"), "bridgeSessionId": core.bridge_session_id}
    core._operations["native"] = {"jobId": "native", "documentId": identity, "status": "ready"}
    with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "one")
    assert exc.value.code == "document_busy"
    core._operations.clear(); core.paused = True
    with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "one")
    assert exc.value.code == "server_stopped"
    core.paused = False
    with pytest.raises(BridgeError) as exc: core.open_edit_tab({**request, "bridgeSessionId": "old"})
    assert exc.value.code == "edit_tab_outcome_unknown"
    monkeypatch.setattr(bridge, "status", lambda: {"writeCapabilities": []})
    with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "two")
    assert exc.value.code == "unsupported_capability" and not host.openings


def test_corrupt_journal_and_native_limit_refuse_replay(setup):
    host, core, _, service, add = setup
    _, identity = add(); service.open_edit_tab(identity, "one")
    path = service.jobs.root / "edit-tab-openings" / (contract.options(identity, "one")["tabOpenId"] + ".json")
    path.write_text('{}')
    with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "one")
    assert exc.value.code == "edit_tab_outcome_unknown" and len(host.openings) == 1
    core._tab_openings.update({str(i): {} for i in range(1024)})
    with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "two")
    assert exc.value.code == "edit_tab_limit_reached" and len(host.openings) == 1


def test_protocol_bounds_closed_fields_and_unicode():
    options = contract.options("doc_1", "key", text="é" * 4096)
    request = {**options, "bridgeSessionId": "session"}
    assert contract.request(request) == request
    for invalid in ({**request, "extra": 1}, {**request, "tabOpenId": "wrong"}):
        with pytest.raises(ProtocolError): contract.request(invalid)


def test_headless_host_does_not_advertise_editor_action(setup):
    host, core, _, service, add = setup
    _, identity = add()
    del host.documentController
    assert contract.CAPABILITY not in core.status()["writeCapabilities"]
    assert contract.CAPABILITY not in service.get_status()["writeCapabilities"]
    with pytest.raises(ServiceError) as exc: service.open_edit_tab(identity, "one")
    assert exc.value.code == "unsupported_capability" and not host.openings


def test_http_mcp_schema_and_timeout_identity(setup, monkeypatch):
    from fastmcp import Client
    from glyphs_mcp_sidecar.server import create_server
    from glyphs_mcp_bridge.http_server import BridgeHTTPServer
    import glyphs_mcp_sidecar.bridge_client as transport
    _, core, _, service, add = setup
    font, identity = add()
    owner = object.__new__(BridgeHTTPServer); owner.core = core
    handler = object.__new__(owner._handler()); handler.path = "/v1/documents/edit-tab/open"
    request = {**contract.options(identity, "route"), "bridgeSessionId": core.bridge_session_id}
    assert handler._route({"tabOpening": request})["documentId"] == identity
    async def exercise():
        async with Client(create_server(service)) as client:
            catalog = {t.name: t for t in await client.list_tools()}
            assert set(catalog) == set(TOOL_NAMES) and len(catalog) == len(TOOL_NAMES)
            schema = catalog["open_edit_tab"].inputSchema
            assert set(schema["required"]) == {"document_id", "idempotency_key"}
            result = await client.call_tool("open_edit_tab", {"document_id": identity, "idempotency_key": "mcp", "glyphs": ["B", "A"], "master_id": "M1"})
            assert result.data["ok"] and result.data["data"]["masterId"] == "M1"
    asyncio.run(exercise())
    monkeypatch.setattr(transport, "urlopen", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(BridgeClientError) as exc: BridgeClient("http://localhost", "token").open_edit_tab(request)
    assert exc.value.details == {"execution": "uncertain", "tabOpenId": request["tabOpenId"]}
    assert len(font.tabs) == 2
