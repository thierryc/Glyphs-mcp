"""Verified Save, Save As, and applied-job acceptance contracts."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest


REPO = Path(__file__).resolve().parents[3]
for root in (REPO / "src" / "protocol", REPO / "src" / "bridge", REPO / "src" / "sidecar"):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from glyphs_mcp_bridge.core import BridgeCore, BridgeError  # noqa: E402
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter  # noqa: E402
from glyphs_mcp_sidecar.bridge_client import BridgeClientError  # noqa: E402
from glyphs_mcp_sidecar.jobs import JobStore  # noqa: E402
from glyphs_mcp_sidecar.service import ServiceError, SidecarService  # noqa: E402
from glyphs_mcp_sidecar.source import source_hash  # noqa: E402


def _patch(path: Path) -> dict:
    return {
        "version": 1,
        "jobId": "job_accept",
        "documentId": "doc_1",
        "sourcePath": str(path),
        "sourceHash": "sha256:" + "a" * 64,
        "generation": 1,
        "changes": [
            {
                "kind": "set",
                "glyph": "A",
                "layer": "M1",
                "field": "width",
                "before": 600,
                "after": 608,
            }
        ],
        "summary": "Increase A width",
    }


class _Queue:
    def __init__(self):
        self.items = []

    def __call__(self, callback):
        self.items.append(callback)

    def drain(self):
        while self.items:
            self.items.pop(0)()


class _BridgeSaveAdapter:
    def __init__(self, path: Path):
        self.path = str(path)
        self.dirty = False
        self.value = 600
        self.save_calls = []

    def list_documents(self):
        return [{"id": "doc_1", "path": self.path, "dirty": self.dirty, "generation": 1}]

    def document_state(self, _document_id):
        return self.list_documents()[0]

    def current_value(self, _document_id, _change, **_options):
        return self.value

    def apply_change(self, _document_id, change, *, reverse=False):
        self.value = change["before"] if reverse else change["after"]
        self.dirty = True

    def capture_state(self, *_args, **_kwargs):
        return None

    def begin_undo(self, _document_id):
        return None

    def end_undo(self, _document_id, _name):
        return None

    def save_document(self, _document_id, target, mode):
        self.save_calls.append((target, mode))
        Path(target).write_bytes(b"saved by bridge")
        self.path = str(target)
        self.dirty = False
        return {
            "writeAttempted": True,
            "nativeSaveSucceeded": True,
            "nativeError": None,
            "path": self.path,
            "dirty": False,
            "generation": 0,
        }


def test_bridge_accepts_only_current_applied_targets_and_closes_discard(tmp_path):
    source = tmp_path / "Accept.glyphs"
    source.write_bytes(b"before")
    adapter = _BridgeSaveAdapter(source)
    queue = _Queue()
    core = BridgeCore(adapter, queue)
    core.begin_apply(_patch(source))
    queue.drain()
    assert core.operation("job_accept")["status"] == "applied"

    request = {
        "saveId": "job_accept",
        "documentId": "doc_1",
        "saveMode": "save",
        "previousPath": str(source),
        "path": str(source),
    }
    assert core.begin_accept("job_accept", request)["status"] == "accepting"
    queue.drain()
    saved = core.operation("job_accept")
    assert saved["status"] == "saved"
    assert adapter.save_calls == [(str(source), "save")]
    accepted = core.complete_accept(
        "job_accept", verified=True, receipt={"sourceHashAfter": "sha256:x"}
    )
    assert accepted["status"] == "accepted"
    with pytest.raises(BridgeError) as caught:
        core.discard("job_accept")
    assert caught.value.code == "job_not_discardable"


def test_bridge_target_conflict_refuses_accept_before_native_save(tmp_path):
    source = tmp_path / "Conflict.glyphs"
    source.write_bytes(b"before")
    adapter = _BridgeSaveAdapter(source)
    queue = _Queue()
    core = BridgeCore(adapter, queue)
    core.begin_apply(_patch(source)); queue.drain()
    adapter.value = 700
    core.begin_accept("job_accept", {
        "saveId": "job_accept", "documentId": "doc_1", "saveMode": "save",
        "previousPath": str(source), "path": str(source),
    })
    queue.drain()
    result = core.operation("job_accept")
    assert result["status"] == "applied"
    assert result["error"]["code"] == "target_conflict"
    assert adapter.save_calls == []


def test_bridge_accept_schedule_failure_is_prewrite_and_retryable(tmp_path):
    source = tmp_path / "Schedule.glyphs"
    source.write_bytes(b"before")
    adapter = _BridgeSaveAdapter(source)
    queue = _Queue()
    core = BridgeCore(adapter, queue)
    core.begin_apply(_patch(source)); queue.drain()

    def unavailable(_callback):
        raise RuntimeError("main-thread dispatcher unavailable")

    core.schedule = unavailable
    result = core.begin_accept("job_accept", {
        "saveId": "job_accept", "documentId": "doc_1", "saveMode": "save",
        "previousPath": str(source), "path": str(source),
    })
    assert result["status"] == "applied"
    assert result["error"]["code"] == "native_write_failed"
    assert adapter.save_calls == []
    assert core._operations["job_accept"]["resolved"]


def test_document_lock_blocks_accept_while_generic_save_owns_document(tmp_path):
    source = tmp_path / "Locked.glyphs"
    source.write_bytes(b"before")
    adapter = _BridgeSaveAdapter(source)
    queue = _Queue(); core = BridgeCore(adapter, queue)
    core.begin_apply(_patch(source)); queue.drain()
    core._saves["save_existing"] = {
        "saveId": "save_existing", "documentId": "doc_1", "status": "saving"
    }
    with pytest.raises(BridgeError) as caught:
        core.begin_accept("job_accept", {
            "saveId": "job_accept", "documentId": "doc_1", "saveMode": "save",
            "previousPath": str(source), "path": str(source),
        })
    assert caught.value.code == "document_busy"
    assert adapter.save_calls == []


class _NativeDocument:
    def __init__(self, font):
        self.font = font
        self.isDocumentEdited = True
        self.hasUnautosavedChanges = True
        self.changeCount = 4
        self.calls = []

    def saveToURL_ofType_forSaveOperation_error_(self, url, type_name, operation, error):
        self.calls.append((str(url), type_name, operation, error))
        Path(str(url)).write_bytes(b"native save")
        self.font.filepath = str(url)
        self.isDocumentEdited = False
        self.hasUnautosavedChanges = False
        self.changeCount = 0
        return True, None


class _NativeFont:
    def __init__(self, path):
        self.filepath = str(path) if path else None
        self.familyName = "Save Test"
        self.parent = _NativeDocument(self)
        self.save = Mock(side_effect=AssertionError("GSFont.save must not be used"))


def _native_modules():
    foundation = ModuleType("Foundation")

    class NSURL:
        @staticmethod
        def fileURLWithPath_(path):
            return path

    foundation.NSURL = NSURL
    appkit = ModuleType("AppKit")
    appkit.NSSaveOperation = 0
    appkit.NSSaveAsOperation = 1
    return {"Foundation": foundation, "AppKit": appkit}


def test_adapter_uses_direct_nsdocument_selector_for_save_and_save_as(tmp_path):
    source = tmp_path / "Native.glyphs"
    source.write_bytes(b"before")
    font = _NativeFont(source)
    adapter = GlyphsAdapter(SimpleNamespace(fonts=[font], font=font))
    document_id = adapter.list_documents()[0]["id"]
    with patch.dict(sys.modules, _native_modules()):
        current = adapter.save_document(document_id, str(source), "save")
        target = tmp_path / "Native.glyphspackage"
        saved_as = adapter.save_document(document_id, str(target), "save_as")
    assert current["nativeSaveSucceeded"] and saved_as["nativeSaveSucceeded"]
    assert font.parent.calls[0][1:3] == ("com.schriftgestaltung.glyphs", 0)
    assert font.parent.calls[1][1:3] == ("com.glyphsapp.glyphspackage", 1)
    font.save.assert_not_called()


def test_post_selector_exception_is_write_attempted_and_selector_runs_once(tmp_path):
    source = tmp_path / "PostSelector.glyphs"
    source.write_bytes(b"before")
    font = _NativeFont(source)
    adapter = GlyphsAdapter(SimpleNamespace(fonts=[font], font=font))
    document_id = adapter.list_documents()[0]["id"]
    adapter._document_state = Mock(side_effect=RuntimeError("state unavailable"))
    with patch.dict(sys.modules, _native_modules()):
        with pytest.raises(BridgeError) as caught:
            adapter.save_document(document_id, str(source), "save")
    assert caught.value.code == "save_verification_failed"
    assert caught.value.details["writeAttempted"] is True
    assert len(font.parent.calls) == 1
    font.save.assert_not_called()


class _SidecarSaveBridge:
    def __init__(self, source: Path):
        self.document = {
            "id": "doc_1", "familyName": "Receipt", "path": str(source),
            "dirty": True, "generation": 4,
        }
        self.save_calls = []

    def status(self):
        return {"protocol": 1, "activity": "ready"}

    def documents(self):
        return [dict(self.document)]

    def _native(self, request):
        self.save_calls.append(dict(request))
        target = Path(request["path"])
        if target.suffix.lower() == ".glyphspackage":
            target.mkdir(parents=True)
            (target / "fontinfo.plist").write_bytes(b"verified saved package")
        else:
            target.write_bytes(b"verified saved source")
        self.document.update(path=request["path"], dirty=False, generation=0)
        return {
            "writeAttempted": True, "nativeSaveSucceeded": True,
            "nativeError": None, "path": request["path"], "dirty": False,
            "generation": 0,
        }

    def save(self, request):
        return {
            "saveId": request["saveId"], "documentId": request["documentId"],
            "status": "saved", "native": self._native(request), "error": None,
        }

    def accept(self, job_id, request):
        return {
            "jobId": job_id, "documentId": request["documentId"], "status": "saved",
            "completedChanges": 1, "totalChanges": 1,
            "nativeSave": self._native(request), "receipt": None, "error": None,
        }

    def complete_accept(self, job_id, *, verified, receipt=None, error=None):
        return {
            "jobId": job_id, "documentId": "doc_1",
            "status": "accepted" if verified else "accept_uncertain",
            "completedChanges": 1, "totalChanges": 1,
            "nativeSave": None, "receipt": receipt, "error": error,
        }


def test_sidecar_save_as_is_create_only_and_preserves_original(tmp_path):
    source = tmp_path / "Original.glyphs"
    source.write_bytes(b"original")
    bridge = _SidecarSaveBridge(source)
    service = SidecarService(bridge, jobs=JobStore(tmp_path / "jobs"), worker=object())
    target = tmp_path / "Copy.glyphspackage"
    receipt = service.save_document("doc_1", destination=str(target))
    assert receipt["saveMode"] == "save_as"
    assert receipt["originalSourceUnchanged"] is True
    assert source.read_bytes() == b"original"
    assert receipt["sourceHashAfter"] == source_hash(target)

    existing = tmp_path / "Existing.glyphs"
    existing.write_bytes(b"do not replace")
    bridge.document.update(path=str(source), dirty=True)
    with pytest.raises(ServiceError) as caught:
        service.save_document("doc_1", destination=str(existing))
    assert caught.value.code == "destination_exists"
    assert existing.read_bytes() == b"do not replace"


def test_save_preflight_rejects_unsafe_unsupported_and_open_paths_before_native(tmp_path):
    source = tmp_path / "Source.glyphs"
    source.write_bytes(b"source")
    bridge = _SidecarSaveBridge(source)
    service = SidecarService(bridge, jobs=JobStore(tmp_path / "jobs"), worker=object())

    other = tmp_path / "Other.glyphs"
    other.write_bytes(b"other")
    original_documents = bridge.documents
    bridge.documents = lambda: [
        *original_documents(),
        {"id": "doc_2", "path": str(other), "dirty": False, "generation": 0},
    ]
    cases = [
        ("relative.glyphs", "invalid_destination"),
        (str(tmp_path / "Unsupported.ufo"), "unsupported_source_format"),
        (str(source), "destination_exists"),
        (str(other), "destination_open_in_glyphs"),
    ]
    for destination, code in cases:
        with pytest.raises(ServiceError) as caught:
            service.save_document("doc_1", destination=destination)
        assert caught.value.code == code

    linked_destination = tmp_path / "Linked.glyphs"
    linked_destination.symlink_to(other)
    with pytest.raises(ServiceError) as caught:
        service.save_document("doc_1", destination=str(linked_destination))
    assert caught.value.code == "unsafe_path"

    linked_source = tmp_path / "LinkedSource.glyphs"
    linked_source.symlink_to(source)
    bridge.document["path"] = str(linked_source)
    with pytest.raises(ServiceError) as caught:
        service.save_document("doc_1")
    assert caught.value.code == "unsafe_path"
    assert bridge.save_calls == []


def test_package_source_rejects_symbolic_linked_directories_before_native(tmp_path):
    package = tmp_path / "Unsafe.glyphspackage"
    package.mkdir()
    (package / "fontinfo.plist").write_bytes(b"source")
    external = tmp_path / "external"
    external.mkdir()
    (external / "glyph.glyph").write_bytes(b"outside")
    (package / "glyphs").symlink_to(external, target_is_directory=True)
    bridge = _SidecarSaveBridge(package)
    service = SidecarService(bridge, jobs=JobStore(tmp_path / "jobs"), worker=object())
    with pytest.raises(ServiceError) as caught:
        service.save_document("doc_1")
    assert caught.value.code == "source_unavailable"
    assert bridge.save_calls == []


def test_pathless_and_package_sources_save_as_in_both_formats(tmp_path):
    target_package = tmp_path / "Untitled.glyphspackage"
    bridge = _SidecarSaveBridge(tmp_path / "unused.glyphs")
    bridge.document.update(path=None, dirty=True)
    service = SidecarService(bridge, jobs=JobStore(tmp_path / "pathless-jobs"), worker=object())
    pathless = service.save_document("doc_1", destination=str(target_package))
    assert pathless["previousPath"] is None
    assert pathless["saveMode"] == "save_as"
    assert source_hash(target_package) == pathless["sourceHashAfter"]

    original_package = tmp_path / "Original.glyphspackage"
    original_package.mkdir()
    (original_package / "fontinfo.plist").write_bytes(b"original package")
    flat_target = tmp_path / "Converted.glyphs"
    bridge = _SidecarSaveBridge(original_package)
    service = SidecarService(bridge, jobs=JobStore(tmp_path / "package-jobs"), worker=object())
    converted = service.save_document("doc_1", destination=str(flat_target))
    assert converted["originalSourceUnchanged"] is True
    assert (original_package / "fontinfo.plist").read_bytes() == b"original package"
    assert flat_target.is_file()


def test_clean_repeated_save_accepts_an_unchanged_resulting_hash(tmp_path):
    source = tmp_path / "Repeated.glyphs"
    source.write_bytes(b"initial")
    bridge = _SidecarSaveBridge(source)
    service = SidecarService(bridge, jobs=JobStore(tmp_path / "jobs"), worker=object())
    first = service.save_document("doc_1")
    second = service.save_document("doc_1")
    assert first["sourceHashAfter"] == second["sourceHashBefore"]
    assert second["sourceHashBefore"] == second["sourceHashAfter"]
    assert second["dirtyBefore"] is False


def test_accept_job_re_saves_changed_source_and_publishes_receipt_first(tmp_path):
    source = tmp_path / "Applied.glyphs"
    source.write_bytes(b"job baseline")
    bridge = _SidecarSaveBridge(source)
    jobs = JobStore(tmp_path / "jobs")
    service = SidecarService(bridge, jobs=jobs, worker=object())
    job = jobs.create(dict(bridge.document), {"kind": "width_delta"})
    baseline = source_hash(source)
    jobs.write_json(job["id"], "patch.json", {"bulk": True})
    jobs.update(
        job["id"], status="applied", sourceHash=baseline,
        summary="Applied edit", changeCount=1,
    )
    source.write_bytes(b"manual save before acceptance")
    release = jobs.release_bulk_artifacts

    def release_after_receipt(job_id):
        assert (jobs.path(job_id) / "receipt.json").is_file()
        release(job_id)

    jobs.release_bulk_artifacts = release_after_receipt

    result = service.accept_job(job["id"])
    assert result["status"] == "accepted"
    assert result["receipt"]["sourceChangedSinceJob"] is True
    assert result["receipt"]["verification"] == "native_and_source_hash"
    assert (jobs.path(job["id"]) / "receipt.json").is_file()
    assert not (jobs.path(job["id"]) / "patch.json").exists()
    repeated = service.accept_job(job["id"])
    assert repeated["status"] == "accepted"
    assert len(bridge.save_calls) == 1
    with pytest.raises(ServiceError) as caught:
        service.discard_job(job["id"])
    assert caught.value.code == "job_not_discardable"


def test_generic_save_refuses_an_applied_job(tmp_path):
    source = tmp_path / "Owned.glyphs"
    source.write_bytes(b"source")
    bridge = _SidecarSaveBridge(source)
    jobs = JobStore(tmp_path / "jobs")
    service = SidecarService(bridge, jobs=jobs, worker=object())
    job = jobs.create(dict(bridge.document), {"kind": "width_delta"})
    jobs.update(job["id"], status="applied")
    with pytest.raises(ServiceError) as caught:
        service.save_document("doc_1")
    assert caught.value.code == "job_acceptance_required"
    assert bridge.save_calls == []


def test_native_false_after_write_makes_acceptance_terminal_and_unverified(tmp_path):
    source = tmp_path / "Unverified.glyphs"
    source.write_bytes(b"before")
    adapter = _BridgeSaveAdapter(source)

    def failed_save(_document_id, target, mode):
        adapter.save_calls.append((target, mode))
        Path(target).write_bytes(b"possibly saved")
        return {
            "writeAttempted": True, "nativeSaveSucceeded": False,
            "nativeError": "native false", "path": str(target), "dirty": False,
        }

    adapter.save_document = failed_save
    queue = _Queue(); core = BridgeCore(adapter, queue)
    core.begin_apply(_patch(source)); queue.drain()
    core.begin_accept("job_accept", {
        "saveId": "job_accept", "documentId": "doc_1", "saveMode": "save",
        "previousPath": str(source), "path": str(source),
    }); queue.drain()
    result = core.operation("job_accept")
    assert result["status"] == "accept_uncertain"
    assert result["error"]["code"] == "save_verification_failed"
    with pytest.raises(BridgeError):
        core.discard("job_accept")


def test_post_write_dirty_mismatch_makes_sidecar_acceptance_uncertain(tmp_path):
    source = tmp_path / "DirtyAfter.glyphs"
    source.write_bytes(b"baseline")
    bridge = _SidecarSaveBridge(source)
    jobs = JobStore(tmp_path / "jobs")
    service = SidecarService(bridge, jobs=jobs, worker=object())
    job = jobs.create(dict(bridge.document), {"kind": "width_delta"})
    jobs.update(job["id"], status="applied", sourceHash=source_hash(source))
    original_accept = bridge.accept

    def dirty_accept(job_id, request):
        operation = original_accept(job_id, request)
        operation["nativeSave"]["dirty"] = True
        return operation

    bridge.accept = dirty_accept
    result = service.accept_job(job["id"])
    assert result["status"] == "accept_uncertain"
    assert result["error"]["code"] == "save_verification_failed"
    assert result["error"]["details"]["writeAttempted"] is True
    with pytest.raises(ServiceError):
        service.discard_job(job["id"])


def test_accept_timeout_reconciles_same_operation_without_replaying_save(tmp_path):
    source = tmp_path / "Timeout.glyphs"
    source.write_bytes(b"baseline")
    bridge = _SidecarSaveBridge(source)
    jobs = JobStore(tmp_path / "jobs")
    service = SidecarService(bridge, jobs=jobs, worker=object())
    job = jobs.create(dict(bridge.document), {"kind": "width_delta"})
    jobs.update(job["id"], status="applied", sourceHash=source_hash(source))
    operations = {}

    def timed_out_accept(job_id, request):
        operations[job_id] = {
            "jobId": job_id, "documentId": request["documentId"], "status": "saved",
            "completedChanges": 1, "totalChanges": 1,
            "nativeSave": bridge._native(request), "receipt": None, "error": None,
        }
        raise BridgeClientError(
            "bridge_unavailable", "response lost",
            {"execution": "uncertain", "jobId": job_id, "saveId": request["saveId"]},
        )

    bridge.accept = timed_out_accept
    bridge.operation = lambda job_id: operations[job_id]
    with pytest.raises(ServiceError):
        service.accept_job(job["id"])
    assert jobs.get(job["id"])["status"] == "accepting"
    result = service.get_job(job["id"])
    assert result["status"] == "accepted"
    assert len(bridge.save_calls) == 1


def test_prewrite_native_failure_leaves_applied_job_retryable(tmp_path):
    source = tmp_path / "Retryable.glyphs"
    source.write_bytes(b"before")
    adapter = _BridgeSaveAdapter(source)

    def refused(*_args):
        raise BridgeError(
            "native_save_failed", "selector unavailable",
            details={"writeAttempted": False},
        )

    adapter.save_document = refused
    queue = _Queue(); core = BridgeCore(adapter, queue)
    core.begin_apply(_patch(source)); queue.drain()
    core.begin_accept("job_accept", {
        "saveId": "job_accept", "documentId": "doc_1", "saveMode": "save",
        "previousPath": str(source), "path": str(source),
    }); queue.drain()
    result = core.operation("job_accept")
    assert result["status"] == "applied"
    assert result["error"]["details"]["writeAttempted"] is False


def test_restart_promotes_a_published_acceptance_receipt(tmp_path):
    source = tmp_path / "Restart.glyphs"
    source.write_bytes(b"saved")
    jobs = JobStore(tmp_path / "jobs")
    document = {"id": "doc_1", "path": str(source), "dirty": False, "generation": 0}
    job = jobs.create(document, {"kind": "width_delta"})
    receipt = {
        "saveId": job["id"], "jobId": job["id"], "documentId": "doc_1",
        "nativeSaveSucceeded": True, "verification": "native_and_source_hash",
        "sourceHashAfter": source_hash(source),
    }
    jobs.update(job["id"], status="accepting")
    jobs.write_json(job["id"], "receipt.json", receipt)
    service = SidecarService(SimpleNamespace(), jobs=jobs, worker=object())
    restored = service.jobs.get(job["id"])
    assert restored["status"] == "accepted"
    assert restored["receipt"] == receipt


def test_restart_without_bridge_operation_or_receipt_is_accept_uncertain(tmp_path):
    source = tmp_path / "Lost.glyphs"
    source.write_bytes(b"saved or not")
    jobs = JobStore(tmp_path / "jobs")
    document = {"id": "doc_1", "path": str(source), "dirty": False, "generation": 0}
    job = jobs.create(document, {"kind": "width_delta"})
    jobs.update(job["id"], status="accepting", saveRequest={"saveId": job["id"]})

    def missing(_job_id):
        raise BridgeClientError("job_not_found", "operation lost")

    service = SidecarService(
        SimpleNamespace(operation=missing), jobs=jobs, worker=object()
    )
    restored = service.get_job(job["id"])
    assert restored["status"] == "accept_uncertain"
    assert restored["error"]["code"] == "bridge_operation_lost"
    assert restored["error"]["details"]["writeAttempted"] is True


def test_accepting_job_remains_active_without_finished_timestamp(tmp_path):
    source = tmp_path / "Active.glyphs"
    source.write_bytes(b"source")
    jobs = JobStore(tmp_path / "jobs")
    job = jobs.create(
        {"id": "doc_1", "path": str(source), "dirty": True, "generation": 1},
        {"kind": "width_delta"},
    )
    value = jobs.update(job["id"], status="accepting")
    assert "finishedAt" not in value


def test_v2_save_modules_do_not_import_or_delegate_to_legacy_save_font():
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            REPO / "src/sidecar/glyphs_mcp_sidecar/saving.py",
            REPO / "src/bridge/glyphs_mcp_bridge/saving.py",
            REPO / "src/bridge/glyphs_mcp_bridge/native_save.py",
        )
    )
    assert "save_font" not in sources
    assert "GSFont.save" not in sources
    assert "saveDocument_" not in sources
