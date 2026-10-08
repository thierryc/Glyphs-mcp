"""Document lifecycle safety, native targeting and recovery through public tools."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
for component in ("protocol", "bridge", "sidecar"):
    sys.path.insert(0, str(ROOT / "src" / component))

from glyphs_mcp_protocol import document_closing as closing, document_importing as importing
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_sidecar.bridge_client import BridgeClient, BridgeClientError
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.service import SidecarService, ServiceError


@pytest.fixture
def setup(tmp_path, monkeypatch):
    host = NS(fonts=[], font=None, imports=[], shows=[], closes=[], saves=[], activations=[],
              close_failure=None, save_failure=False, import_failure=False, pathless_import=False)

    class Font:
        def __init__(self, path=None, dirty=False):
            self.filepath, self.familyName = path, "Fixture"
            self.parent = NS(isDocumentEdited=dirty, changeCount=5)
        def show(self):
            host.shows.append(self); host.font = self
        def close(self, ignoreChanges=True):
            host.closes.append((self, ignoreChanges))
            if host.close_failure == "before": raise RuntimeError("native close failed")
            if host.close_failure == "async": return
            host.fonts.remove(self)
            if host.close_failure == "after": raise RuntimeError("window callback failed")

    def open_font(path, showInterface=True):
        host.imports.append((path, showInterface))
        font = Font(None if host.pathless_import else path)
        host.fonts.append(font)
        if host.import_failure: raise RuntimeError("import failed after attachment")
        return font

    host.open = open_font
    monkeypatch.setitem(sys.modules, "GlyphsApp", NS(GSFont=Font))
    monkeypatch.setitem(sys.modules, "AppKit", NS(NSApplication=NS(sharedApplication=lambda:
        NS(activateIgnoringOtherApps_=lambda value: host.activations.append(value)))))
    adapter = GlyphsAdapter(host)
    def save(document_id, path, mode):
        font = adapter._font(document_id); host.saves.append((document_id, path, mode))
        if host.save_failure:
            return {"nativeSaveSucceeded": False, "writeAttempted": True, "nativeError": "disk full"}
        Path(path).write_text("saved source")
        font.filepath, font.parent.isDocumentEdited, font.parent.changeCount = path, False, 0
        return {**adapter.document_state(document_id), "nativeSaveSucceeded": True, "writeAttempted": True}
    adapter.save_document = save
    core = BridgeCore(adapter, lambda callback: callback())

    class Bridge:
        lose = None
        def status(self): return core.status()
        def documents(self): return core.list_documents()
        def invoke(self, action, request):
            try: result = getattr(core, action)(request)
            except BridgeError as exc: raise BridgeClientError(exc.code, exc.message, exc.details) from exc
            if self.lose == action:
                self.lose = None
                raise BridgeClientError("bridge_unavailable", "lost response", {"execution": "uncertain"})
            return result
        def import_document(self, request): return self.invoke("import_document", request)
        def activate_document(self, request): return self.invoke("activate_document", request)
        def close_document(self, request): return self.invoke("close_document", request)
        def save(self, request): return self.invoke("begin_save", request)
        def save_operation(self, identity): return core.save_operation(identity)

    bridge = Bridge()
    service = SidecarService(bridge, jobs=JobStore(tmp_path / "jobs"), worker=NS(status=lambda: {}))
    def add(path=None, dirty=False):
        font = Font(path, dirty); host.fonts.append(font)
        return font, adapter._id(font)
    return host, core, bridge, service, add


def source(tmp_path, suffix=".glyphs"):
    path = tmp_path / ("Font é" + suffix)
    if suffix == ".ufo":
        path.mkdir(); (path / "metainfo.plist").write_text("UFO fixture")
    else: path.write_text("source fixture")
    return path


def test_clean_close_preserves_other_dirty_font_and_retries_after_lost_response(setup):
    host, _, bridge, service, add = setup
    font, identity = add(); other, _ = add(dirty=True)
    bridge.lose = "close_document"
    with pytest.raises(ServiceError): service.close_document(identity, "one")
    restarted = SidecarService(bridge, jobs=service.jobs)
    result = restarted.close_document(identity, "one")
    assert result["closed"] and not result["discardedUnsavedChanges"]
    assert host.fonts == [other] and host.closes == [(font, True)] and not host.saves
    assert result == service.close_document(identity, "one")


@pytest.mark.parametrize("dirty", [True, None])
def test_unsaved_or_unknown_state_requires_explicit_choice(setup, dirty):
    host, _, _, service, add = setup
    font, identity = add(dirty=dirty)
    with pytest.raises(ServiceError) as exc: service.close_document(identity, "one")
    assert exc.value.code == "unsaved_changes_required" and not host.closes
    result = service.close_document(identity, "discard", "discard")
    assert result["discardedUnsavedChanges"] and not host.saves and font not in host.fonts


@pytest.mark.parametrize("mode,destination", [("cancel", None), ("refuse", "/tmp/X.glyphs"),
    ("discard", "/tmp/X.glyphs"), ("save", "relative.glyphs")])
def test_invalid_close_options_do_not_mutate(setup, mode, destination):
    host, _, _, service, add = setup
    _, identity = add(dirty=True)
    with pytest.raises(ServiceError) as exc: service.close_document(identity, "one", mode, destination)
    assert exc.value.code == "invalid_request" and not host.closes and not host.saves


@pytest.mark.parametrize("state", sorted(closing.OWNING_STATUSES - {"saving", "saved", "rolling_back"}))
def test_pending_jobs_block_close_without_save_or_discard(setup, state):
    host, core, _, service, add = setup
    _, identity = add(dirty=True)
    job = service.jobs.create(core.adapter.document_state(identity), {"kind": "translate"})
    service.jobs.update(job["id"], status=state)
    with pytest.raises(ServiceError) as exc: service.close_document(identity, "one", "discard")
    assert exc.value.code == "document_busy" and exc.value.details["jobId"] == job["id"]
    assert not host.closes and not host.saves


def test_native_ready_job_blocks_close_even_when_sidecar_does_not_know_it(setup):
    host, core, _, service, add = setup
    _, identity = add()
    core._operations["job_native"] = {"jobId": "job_native", "documentId": identity, "status": "ready"}
    with pytest.raises(ServiceError) as exc: service.close_document(identity, "one")
    assert exc.value.code == "document_busy" and not host.closes
    core._operations["job_native"]["status"] = "discarded"
    assert service.close_document(identity, "one")["closed"]


def test_unresolved_script_blocks_close_and_terminal_job_does_not(setup):
    host, core, _, service, add = setup
    _, identity = add()
    job = service.jobs.create(core.adapter.document_state(identity), {"kind": "python_script"})
    service.jobs.update(job["id"], status="failed", resultKind="script",
                        bridgeOperation={"scriptResult": {"executed": True}})
    with pytest.raises(ServiceError) as exc: service.close_document(identity, "one")
    assert exc.value.code == "document_busy" and not host.closes
    service.jobs.update(job["id"], status="completed")
    assert service.close_document(identity, "one")["closed"]


def test_job_registration_and_close_serialize_between_sidecars(setup, tmp_path, monkeypatch):
    host, _, bridge, service, add = setup
    _, identity = add(str(source(tmp_path)))
    entered, release, close_started = Event(), Event(), Event()
    second = SidecarService(bridge, jobs=JobStore(service.jobs.root))
    def validate(*args):
        entered.set(); assert release.wait(2)
        return {"kind": "width_delta", "delta": 8, "options": {}}
    monkeypatch.setattr(service, "validate_job_request", validate)
    monkeypatch.setattr(service, "_native_preparation_available", lambda request: False)
    import glyphs_mcp_sidecar.service as service_module
    monkeypatch.setattr(service_module, "Thread", lambda **kwargs: NS(start=lambda: None))
    def close():
        close_started.set()
        return second.close_document(identity, "close")
    with ThreadPoolExecutor(max_workers=2) as pool:
        registration = pool.submit(service.start_job, identity, kind="width_delta", delta=8)
        assert entered.wait(2)
        closing = pool.submit(close); assert close_started.wait(2)
        assert not closing.done()
        release.set(); job = registration.result(timeout=3)
        with pytest.raises(ServiceError) as exc: closing.result(timeout=3)
    assert exc.value.code == "document_busy" and exc.value.details["jobId"] == job["id"]
    assert not host.closes


def test_save_and_close_verifies_save_as_and_preserves_original(setup, tmp_path):
    host, _, _, service, add = setup
    original = source(tmp_path); before = original.read_bytes()
    font, identity = add(str(original), True)
    target = tmp_path / "New.glyphs"
    result = service.close_document(identity, "one", "save", str(target))
    assert result["closed"] and result["path"] == str(target)
    assert result["saveReceipt"]["originalSourceUnchanged"] is True
    assert original.read_bytes() == before and target.read_text() == "saved source"
    assert len(host.saves) == len(host.closes) == 1 and font not in host.fonts
    assert service.close_document(identity, "one", "save", str(target)) == result


def test_failed_save_leaves_font_open_and_never_replays(setup, tmp_path):
    host, _, _, service, add = setup
    font, identity = add(str(source(tmp_path)), True); host.save_failure = True
    for _ in range(2):
        with pytest.raises(ServiceError): service.close_document(identity, "one", "save")
    assert host.fonts == [font] and len(host.saves) == 1 and not host.closes


def test_pathless_save_close_requires_new_destination(setup, tmp_path):
    host, _, _, service, add = setup
    _, identity = add(dirty=True)
    with pytest.raises(ServiceError) as exc: service.close_document(identity, "one", "save")
    assert exc.value.code == "document_path_required" and not host.closes and not host.saves
    result = service.close_document(identity, "with-destination", "save", str(tmp_path / "Native.glyphs"))
    assert result["closed"] and len(host.saves) == 1


def test_failed_checkpoint_keeps_saved_font_open(setup, tmp_path, monkeypatch):
    host, _, _, service, add = setup
    _, identity = add(str(source(tmp_path)), True)
    original = service.save_document
    def save(*args, **kwargs):
        return {**original(*args, **kwargs), "checkpoint": {"status": "failed", "message": "Git failed"}}
    monkeypatch.setattr(service, "save_document", save)
    for _ in range(2):
        with pytest.raises(ServiceError) as exc: service.close_document(identity, "one", "save")
        assert exc.value.code == "closing_checkpoint_failed"
    assert len(host.saves) == 1 and not host.closes


def test_unreadable_close_journal_never_dispatches(setup):
    host, _, _, service, add = setup
    _, identity = add()
    service.close_document(identity, "one")
    next((service.jobs.root / "document-closings").glob("*.json")).write_text("broken")
    with pytest.raises(ServiceError) as exc: service.close_document(identity, "one")
    assert exc.value.code == "closing_outcome_unknown" and len(host.closes) == 1


def test_lost_save_outcome_reconciles_without_resaving(setup, tmp_path, monkeypatch):
    host, core, bridge, service, add = setup
    _, identity = add(str(source(tmp_path)), True)
    bridge.lose = "begin_save"
    original = bridge.save_operation
    monkeypatch.setattr(bridge, "save_operation", lambda identity: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(ServiceError): service.close_document(identity, "one", "save")
    assert len(host.saves) == 1 and not host.closes
    monkeypatch.setattr(bridge, "save_operation", original)
    assert service.close_document(identity, "one", "save")["closed"]
    assert len(host.saves) == len(host.closes) == 1


def test_later_edits_after_saved_close_intent_are_preserved(setup, tmp_path, monkeypatch):
    host, core, bridge, service, add = setup
    font, identity = add(str(source(tmp_path)), True)
    original = bridge.close_document
    monkeypatch.setattr(bridge, "close_document", lambda request: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(ServiceError): service.close_document(identity, "one", "save")
    font.parent.isDocumentEdited = True; font.parent.changeCount = 9
    monkeypatch.setattr(bridge, "close_document", original)
    with pytest.raises(ServiceError) as exc: service.close_document(identity, "one", "save")
    assert exc.value.code == "stale_document" and len(host.saves) == 1 and not host.closes


def test_changed_saved_file_prevents_close_without_another_save(setup, tmp_path, monkeypatch):
    host, _, bridge, service, add = setup
    path = source(tmp_path); _, identity = add(str(path), True)
    original = bridge.close_document
    monkeypatch.setattr(bridge, "close_document", lambda request: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(ServiceError): service.close_document(identity, "one", "save")
    path.write_text("external change")
    monkeypatch.setattr(bridge, "close_document", original)
    with pytest.raises(ServiceError) as exc: service.close_document(identity, "one", "save")
    assert exc.value.code == "closing_save_unverified" and len(host.saves) == 1 and not host.closes


def test_key_conflicts_bridge_restart_and_closed_ids_do_not_retarget(setup):
    host, core, _, service, add = setup
    _, first = add(); _, second = add()
    service.close_document(first, "one")
    with pytest.raises(ServiceError) as exc: service.close_document(second, "one")
    assert exc.value.code == "closing_conflict"
    with pytest.raises(ServiceError) as exc: service.activate_document(first)
    assert exc.value.code == "document_not_found" and not host.shows
    core.bridge_session_id = "new-session"
    with pytest.raises(ServiceError) as exc: service.close_document(first, "one")
    assert exc.value.code == "closing_outcome_unknown" and len(host.closes) == 1


@pytest.mark.parametrize("failure", ["before", "after", "async"])
def test_native_close_failure_is_observed_without_replaying(setup, failure):
    host, _, _, service, add = setup
    font, identity = add(); host.close_failure = failure
    if failure == "after":
        assert service.close_document(identity, "one")["closed"]
    else:
        for _ in range(2):
            with pytest.raises(ServiceError) as exc: service.close_document(identity, "one")
            assert exc.value.code == "closing_outcome_unknown"
        if failure == "async":
            host.fonts.remove(font)
            assert service.close_document(identity, "one")["closed"]
    assert len(host.closes) == 1


def test_activate_shows_exact_font_without_mutating_or_reopening(setup):
    host, _, _, service, add = setup
    font, identity = add(dirty=True); other, _ = add(); host.font = other
    for _ in range(2):
        result = service.activate_document(identity)
        assert result["id"] == identity and result["isCurrent"] is True and result["dirty"] is True
    assert host.shows == [font, font] and host.activations == [True, True]
    assert not host.closes and not host.saves and not host.imports


@pytest.mark.parametrize("suffix", [".ufo", ".otf", ".ttf"])
def test_import_reports_source_limitations_and_saves_to_new_native_source(setup, tmp_path, suffix):
    host, _, _, service, _ = setup
    path = source(tmp_path, suffix)
    before = (path / "metainfo.plist").read_bytes() if path.is_dir() else path.read_bytes()
    result = service.import_document(str(path), "one")
    assert result["sourcePath"] == str(path) and result["sourceFormat"] == suffix[1:]
    assert result["requiresSaveAs"] and result["viewOnlyUntilSaveAs"] == (suffix != ".ufo")
    assert bool(result["warnings"]) == (suffix != ".ufo")
    assert not host.saves and not host.closes
    with pytest.raises(ServiceError) as exc: service.save_document(result["id"])
    assert exc.value.code == "document_path_required"
    saved = service.close_document(result["id"], "close", "save", str(tmp_path / "Native.glyphs"))
    assert saved["saveReceipt"]["originalSourceUnchanged"] is True
    after = (path / "metainfo.plist").read_bytes() if path.is_dir() else path.read_bytes()
    assert before == after


def test_pathless_import_retry_lost_response_and_closed_font(setup, tmp_path):
    host, _, bridge, service, _ = setup
    host.pathless_import = True; bridge.lose = "import_document"
    path = source(tmp_path, ".otf")
    with pytest.raises(ServiceError): service.import_document(str(path), "one")
    restarted = SidecarService(bridge, jobs=service.jobs)
    result = restarted.import_document(str(path), "one")
    assert result["path"] is None and len(host.imports) == 1
    service.close_document(result["id"], "close")
    with pytest.raises(ServiceError) as exc: restarted.import_document(str(path), "one")
    assert exc.value.code == "document_not_found" and len(host.imports) == 1


@pytest.mark.parametrize("path", ["relative.ttf", "/tmp/font.glyphs", "/tmp/missing.ttf", "/tmp/bad\n.otf"])
def test_invalid_import_is_rejected_before_dispatch(setup, path):
    host, _, _, service, _ = setup
    with pytest.raises(ServiceError): service.import_document(path, "one")
    assert not host.imports


def test_import_failure_does_not_replay_native_call(setup, tmp_path):
    host, _, _, service, _ = setup
    host.import_failure = True; path = source(tmp_path, ".ttf")
    for _ in range(2):
        with pytest.raises(ServiceError) as exc: service.import_document(str(path), "one")
        assert exc.value.code == "importing_failed"
    assert len(host.imports) == 1 and len(host.fonts) == 1 and not host.closes


def test_import_reuses_dirty_source_and_refreshes_saved_native_state(setup, tmp_path):
    host, _, _, service, add = setup
    path = source(tmp_path, ".otf"); font, identity = add(str(path), True)
    result = service.import_document(str(path), "one")
    assert result["id"] == identity and result["alreadyOpen"] and result["dirty"]
    assert not host.imports
    service.save_document(identity, destination=str(tmp_path / "Native.glyphs"))
    fresh = service.import_document(str(path), "one")
    assert fresh["id"] == identity and not fresh["requiresSaveAs"] and not fresh["viewOnlyUntilSaveAs"]


def test_imported_font_does_not_block_unrelated_native_save(setup, tmp_path):
    _, _, _, service, add = setup
    imported = source(tmp_path, ".ttf"); service.import_document(str(imported), "one")
    _, identity = add(str(source(tmp_path)), True)
    assert service.save_document(identity)["nativeSaveSucceeded"]


@pytest.mark.parametrize("suffix", [".ufo", ".otf", ".ttf"])
def test_wrong_import_source_types_are_rejected(setup, tmp_path, suffix):
    host, _, _, service, _ = setup
    path = tmp_path / ("Wrong" + suffix)
    if suffix == ".ufo": path.write_text("not a folder")
    else: path.mkdir()
    with pytest.raises(ServiceError) as exc: service.import_document(str(path), "one")
    assert exc.value.code == "invalid_request" and not host.imports


def test_import_conflicting_key_and_bridge_restart_require_reconciliation(setup, tmp_path):
    host, core, _, service, _ = setup
    path = source(tmp_path, ".ttf"); service.import_document(str(path), "one")
    other = source(tmp_path, ".otf")
    with pytest.raises(ServiceError) as exc: service.import_document(str(other), "one")
    assert exc.value.code == "importing_conflict"
    core.bridge_session_id = "new-session"
    with pytest.raises(ServiceError) as exc: service.import_document(str(path), "one")
    assert exc.value.code == "importing_outcome_unknown" and len(host.imports) == 1


def test_capability_and_control_reservation_rejections_preserve_fonts(setup, monkeypatch):
    host, _, bridge, service, add = setup
    _, identity = add()
    monkeypatch.setattr(bridge, "status", lambda: {"writeCapabilities": []})
    for call in (lambda: service.close_document(identity, "one"), lambda: service.activate_document(identity)):
        with pytest.raises(ServiceError) as exc: call()
        assert exc.value.code == "unsupported_capability"
    service.lifecycle.reservation = {"id": "reserved", "deadline": float("inf")}
    with pytest.raises(ServiceError) as exc: service.close_document(identity, "one")
    assert exc.value.code == "service_reserved" and not host.closes and not host.shows


@pytest.mark.parametrize("action,identity", [("close_document", "closeId"), ("import_document", "importId"), ("activate_document", "documentId")])
def test_transport_retains_action_identity_on_timeouts(monkeypatch, action, identity):
    import glyphs_mcp_sidecar.bridge_client as transport
    monkeypatch.setattr(transport, "urlopen", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    request = "doc_1" if identity == "documentId" else {identity: "opaque"}
    with pytest.raises(BridgeClientError) as exc: getattr(BridgeClient("http://localhost", "token"), action)(request)
    assert exc.value.details == {"execution": "uncertain", identity: "doc_1" if identity == "documentId" else "opaque"}


def test_http_routes_and_mcp_catalog_use_same_document_operations(setup, tmp_path):
    from fastmcp import Client
    from glyphs_mcp_sidecar.server import create_server
    from glyphs_mcp_bridge.http_server import BridgeHTTPServer
    host, core, _, service, _ = setup
    owner = object.__new__(BridgeHTTPServer); owner.core = core
    handler = object.__new__(owner._handler())
    path = source(tmp_path, ".ttf")
    request = {**importing.options(str(path), "route"), "bridgeSessionId": core.bridge_session_id}
    handler.path = "/v1/documents/import"; imported = handler._route({"importing": request})
    handler.path = "/v1/documents/activate"; assert handler._route({"documentId": imported["id"]})["isCurrent"]
    state = core.adapter.document_state(imported["id"])
    request = {"closeId": closing.options(imported["id"], "route", "refuse", None)["closeId"],
               "documentId": imported["id"], "bridgeSessionId": core.bridge_session_id,
               "state": {k: state[k] for k in ("path", "dirty", "generation")}, "discard": False}
    handler.path = "/v1/documents/close"; assert handler._route({"closing": request})["closed"]
    async def exercise():
        async with Client(create_server(service)) as client:
            catalog = {tool.name: tool for tool in await client.list_tools()}
            assert len(catalog) == 17
            assert set(catalog["close_document"].inputSchema["required"]) == {"document_id", "idempotency_key"}
            imported = (await client.call_tool("import_document", {"path": str(path), "idempotency_key": "mcp"})).data
            assert imported["ok"]
            identity = imported["data"]["id"]
            assert (await client.call_tool("activate_document", {"document_id": identity})).data["ok"]
            assert (await client.call_tool("close_document", {"document_id": identity, "idempotency_key": "mcp"})).data["data"]["closed"]
    asyncio.run(exercise())
