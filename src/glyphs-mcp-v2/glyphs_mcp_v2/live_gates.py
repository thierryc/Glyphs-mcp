"""Explicit disposable-font gates for this milestone's Glyphs 4 live run."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from uuid import uuid4

from .adapters.document import (
    _classify_native_clone_archive_mismatches,
    _compare_native_archives,
    _decoded_native_archive_tree,
    _native_archive_fingerprint,
    _save_font_copy,
    _serialized_font_archive,
)
from .semantic import diff_models, fingerprint_model


DISPOSABLE_FAMILY_PREFIX = "Glyphs MCP V2 Disposable"


def _plain_attribute(value: Any, name: str) -> Any:
    result = getattr(value, name, None)
    return result() if callable(result) else result


def _reported_dirty_state(host: Any, document_id: str) -> Optional[bool]:
    list_documents = getattr(host, "list_documents", None)
    if not callable(list_documents):
        return None
    for document in list_documents():
        if str(getattr(document, "document_id", "") or "") == document_id:
            return getattr(document, "has_unsaved_changes", None)
    return None


def _unused_feature_tags(model: Mapping[str, Any], count: int) -> list[str]:
    existing = {
        str(item.get("id") or item.get("name") or "")
        for item in model.get("features", [])
        if isinstance(item, Mapping)
    }
    candidates = ["cv{:02d}".format(index) for index in range(99, 0, -1)]
    candidates.extend("ss{:02d}".format(index) for index in range(20, 0, -1))
    available = [tag for tag in candidates if tag not in existing]
    if len(available) < count:
        raise ValueError("the disposable font has no free standard feature tags for the live gate")
    return available[:count]


def _unique_name(prefix: str, existing: Sequence[str]) -> str:
    occupied = {str(value) for value in existing}
    for index in range(1000):
        candidate = prefix if index == 0 else "{}{}".format(prefix, index)
        if candidate not in occupied:
            return candidate
    raise ValueError("the disposable font has no free live-gate identity")


def _assert_unique_unicode_assignments(
    model: Mapping[str, Any], *, phase: str
) -> None:
    """Refuse a live fixture that could summon Glyphs' modal repair UI."""

    glyphs = model.get("glyphs", {})
    if not isinstance(glyphs, Mapping):
        return
    owners: dict[str, list[str]] = {}
    for key, glyph in glyphs.items():
        if not isinstance(glyph, Mapping):
            continue
        glyph_name = str(glyph.get("name") or key)
        values = glyph.get("unicodes")
        if values is None:
            values = [glyph.get("unicode")]
        elif isinstance(values, str):
            values = [values]
        for value in values or ():
            codepoint = str(value or "").strip().upper()
            if not codepoint:
                continue
            if codepoint.startswith("U+"):
                codepoint = codepoint[2:]
            owners.setdefault(codepoint, []).append(glyph_name)
    duplicates = [
        (codepoint, names)
        for codepoint, names in sorted(owners.items())
        if len(set(names)) > 1
    ]
    if not duplicates:
        return
    codepoint, names = duplicates[0]
    raise ValueError(
        "{} live-gate model has duplicate Unicode U+{} in glyphs {}; "
        "qualification refuses modal repair workflows".format(
            phase,
            codepoint,
            ", ".join(dict.fromkeys(names)),
        )
    )


def _resolve_live_runtime(application: Any, host: Any) -> tuple[Any, Any]:
    if application is None or host is None:
        from .runtime import active_application, active_host

        application = application or active_application()
        host = host or active_host()
    if application is None or host is None:
        raise RuntimeError("the Glyphs MCP v2 runtime must be active before running the live gate")
    return application, host


class _StructuralGateSession:
    """Small generic driver over the public apply/revert contract."""

    def __init__(
        self,
        application: Any,
        host: Any,
        document_id: str,
        current_fingerprint: str,
    ) -> None:
        self.application = application
        self.host = host
        self.document_id = document_id
        self.current_fingerprint = str(current_fingerprint)
        self.active: list[str] = []
        self.successful: list[str] = []
        self.refusals: list[str] = []
        self.single_transactions = True
        self.audit_receipts = True
        self.change_log_commits = True
        self.stage_timings: dict[str, Mapping[str, float]] = {}
        self.commits: dict[str, Any] = {}

    def model(self) -> Mapping[str, Any]:
        capture = getattr(self.host, "capture_snapshot", None)
        if not callable(capture):
            capture = getattr(self.host, "capture_model", None)
        if not callable(capture):
            raise RuntimeError("the live gate host exposes no canonical capture")
        return capture(self.document_id)

    def fingerprint(self) -> str:
        return fingerprint_model(self.model())

    def invoke(self, tool: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        response = self.application.invoke(tool, arguments)
        return response.to_dict() if hasattr(response, "to_dict") else dict(response)

    def _success(self, tool: str, response: Mapping[str, Any]) -> Mapping[str, Any]:
        if not response.get("ok"):
            error = response.get("error") or {}
            raise AssertionError(
                "{} failed: {} ({}) details={}".format(
                    tool,
                    error.get("message") or response.get("summary") or "unknown error",
                    error.get("code") or "unknown",
                    dict(error.get("details") or {}),
                )
            )
        data = dict(response.get("data") or {})
        one_transaction = data.get("transactionCount") == 1
        has_receipt = bool(response.get("auditReceipt"))
        self.single_transactions = self.single_transactions and one_transaction
        self.audit_receipts = self.audit_receipts and has_receipt
        if not one_transaction:
            raise AssertionError("{} did not report exactly one live transaction".format(tool))
        if not has_receipt:
            raise AssertionError("{} did not emit an audit receipt".format(tool))
        before_fingerprint = str(data.get("beforeFingerprint") or "")
        after_fingerprint = str(data.get("afterFingerprint") or "")
        if before_fingerprint != self.current_fingerprint or not after_fingerprint:
            raise AssertionError(
                "{} did not return the verified fingerprint transition".format(tool)
            )
        self.current_fingerprint = after_fingerprint
        return data

    def apply(self, tool: str, updates: Sequence[Mapping[str, Any]]) -> str:
        response = self.invoke(
            tool,
            {
                "documentId": self.document_id,
                "expectedDocumentFingerprint": self.current_fingerprint,
                "updates": [dict(item) for item in updates],
                "reason": "Glyphs MCP v2 verified structural live qualification",
            },
        )
        data = self._success(tool, response)
        operation_id = str(data.get("operationId") or response.get("operationId") or "")
        if not operation_id:
            raise AssertionError("{} returned no canonical operation ID".format(tool))
        self.commits[operation_id] = self._require_change_log_commit(
            operation_id, tool
        )
        self._record_stage_timings(operation_id)
        self.active.append(operation_id)
        self.successful.append(operation_id)
        return operation_id

    def revert(self, operation_id: str) -> None:
        response = self.invoke(
            "revert_change",
            {
                "documentId": self.document_id,
                "operationId": operation_id,
                "expectedDocumentFingerprint": self.current_fingerprint,
            },
        )
        data = self._success("revert_change", response)
        reverted_id = str(data.get("operationId") or response.get("operationId") or "")
        if not reverted_id:
            raise AssertionError("revert_change returned no canonical operation ID")
        self.commits[reverted_id] = self._require_change_log_commit(
            reverted_id, "revert_change"
        )
        self._record_stage_timings(reverted_id)
        self.active.remove(operation_id)
        self.successful.append(reverted_id)

    def _record_stage_timings(self, operation_id: str) -> None:
        kernel = getattr(self.application, "_transactions", None)
        diagnostics = getattr(kernel, "diagnostic_stage_timings", None)
        if callable(diagnostics):
            values = diagnostics(operation_id)
            if values:
                self.stage_timings[operation_id] = {
                    str(name): float(value) for name, value in values.items()
                }

    def _require_change_log_commit(self, operation_id: str, tool: str) -> Any:
        history = getattr(self.application, "history", None)
        getter = getattr(history, "get_commit", None)
        commit = getter(operation_id) if callable(getter) else None
        matches = (
            commit is not None
            and commit.document_id == self.document_id
            and commit.tool == tool
        )
        self.change_log_commits = self.change_log_commits and matches
        if not matches:
            raise AssertionError("{} was not recorded in the canonical Change Log".format(tool))
        return commit

    def change_set(self, operation_id: str) -> Any:
        commit = self.commits.get(operation_id)
        change_set = getattr(commit, "change_set", None)
        if change_set is None:
            raise AssertionError(
                "{} has no verified canonical change set".format(operation_id)
            )
        return change_set

    def round_trip(
        self, tool: str, batches: Sequence[Sequence[Mapping[str, Any]]]
    ) -> None:
        operations = [self.apply(tool, updates) for updates in batches]
        for operation_id in reversed(operations):
            self.revert(operation_id)

    def refuse(
        self,
        tool: str,
        expected_code: str,
        updates: Sequence[Mapping[str, Any]],
        *,
        stale: bool = False,
    ) -> None:
        response = self.invoke(
            tool,
            {
                "documentId": self.document_id,
                "expectedDocumentFingerprint": (
                    "sha256:stale" if stale else self.current_fingerprint
                ),
                "updates": [dict(item) for item in updates],
                "reason": "Glyphs MCP v2 verified structural atomic refusal gate",
            },
        )
        code = str((response.get("error") or {}).get("code") or "")
        if response.get("ok") or code != expected_code:
            raise AssertionError("expected {} refusal, got {}".format(expected_code, code))
        self.refusals.append(code)

    def cleanup(self) -> list[str]:
        failures: list[str] = []
        for operation_id in tuple(reversed(self.active)):
            try:
                response = self.invoke(
                    "revert_change",
                    {
                        "documentId": self.document_id,
                        "operationId": operation_id,
                        "expectedDocumentFingerprint": self.current_fingerprint,
                    },
                )
                if response.get("ok"):
                    data = dict(response.get("data") or {})
                    if str(data.get("beforeFingerprint") or "") != self.current_fingerprint:
                        raise AssertionError("cleanup revert returned a stale fingerprint")
                    self.current_fingerprint = str(data.get("afterFingerprint") or "")
                    if not self.current_fingerprint:
                        raise AssertionError("cleanup revert returned no after fingerprint")
                    self.active.remove(operation_id)
                else:
                    failures.append(operation_id)
            except Exception:
                failures.append(operation_id)
        return failures


class _StagedPythonGateSession:
    """Thin qualification driver over public staged preview/confirm/rollback."""

    def __init__(
        self,
        application: Any,
        host: Any,
        document_id: str,
        current_fingerprint: str,
    ) -> None:
        self.application = application
        self.host = host
        self.document_id = document_id
        self.current_fingerprint = str(current_fingerprint)
        self.active: list[dict[str, str]] = []
        self.pending_review_id: Optional[str] = None
        self.operation_ids: list[str] = []
        self.rollback_operation_ids: list[str] = []
        self.preview_count = 0
        self.confirm_count = 0
        self.rollback_count = 0
        self.audit_receipts = True
        self.change_log_commits = True

    @staticmethod
    def _plain_response(value: Any) -> Mapping[str, Any]:
        return value.to_dict() if hasattr(value, "to_dict") else dict(value)

    def invoke(self, tool: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._plain_response(self.application.invoke(tool, arguments))

    def fingerprint(self) -> str:
        return fingerprint_model(self.host.capture_model(self.document_id))

    @staticmethod
    def _require_ok(tool: str, response: Mapping[str, Any]) -> Mapping[str, Any]:
        if not response.get("ok"):
            error = response.get("error") or {}
            data = response.get("data") or {}
            archive = (
                data.get("nativeArchiveMismatch", {})
                if isinstance(data, Mapping)
                else {}
            )
            diagnostic = ""
            if isinstance(archive, Mapping) and archive:
                diagnostic = "; native mismatch count={}, locations={!r}".format(
                    int(archive.get("mismatchCount") or 0),
                    list(archive.get("mismatchLocations") or [])[:3],
                )
            verification_failure = (
                str(data.get("verificationFailure") or "")[:500]
                if isinstance(data, Mapping)
                else ""
            )
            if verification_failure:
                diagnostic += "; verification={!r}".format(verification_failure)
            raise AssertionError(
                "{} failed: {} ({}){}".format(
                    tool,
                    error.get("message") or response.get("summary") or "unknown error",
                    error.get("code") or "unknown",
                    diagnostic,
                )
            )
        return dict(response.get("data") or {})

    def _require_receipt(self, tool: str, response: Mapping[str, Any]) -> None:
        present = bool(response.get("auditReceipt"))
        self.audit_receipts = self.audit_receipts and present
        if not present:
            raise AssertionError("{} did not emit an audit receipt".format(tool))

    def _require_commit(self, operation_id: str, tool: str) -> None:
        history = getattr(self.application, "history", None)
        getter = getattr(history, "get_commit", None)
        commit = getter(operation_id) if callable(getter) else None
        matches = bool(
            commit is not None
            and commit.document_id == self.document_id
            and commit.tool == tool
            and commit.changed
        )
        self.change_log_commits = self.change_log_commits and matches
        if not matches:
            raise AssertionError(
                "{} was not recorded as a changed canonical action".format(tool)
            )

    def preview_and_confirm(self, code: str, *, reason: str) -> dict[str, str]:
        before = self.current_fingerprint
        preview = self.invoke(
            "execute_python",
            {
                "code": code,
                "reason": reason,
                "intendedEffect": "document_edit",
                "executionMode": "staged_document",
                "documentId": self.document_id,
                "expectedDocumentFingerprint": before,
            },
        )
        preview_data = self._require_ok("execute_python preview", preview)
        self._require_receipt("execute_python preview", preview)
        if preview.get("status") != "review_required":
            raise AssertionError("staged Python did not return review_required")
        if preview_data.get("liveDocumentChanged") is not False:
            raise AssertionError("staged preview claimed a live document change")
        if self.fingerprint() != before:
            raise AssertionError("staged preview changed the live document")
        review_id = str(preview_data.get("reviewId") or "")
        if not review_id:
            raise AssertionError("staged preview returned no review ID")
        self.pending_review_id = review_id
        self.preview_count += 1

        confirmed = self.invoke(
            "execute_python", {"reviewId": review_id, "confirm": True}
        )
        confirmed_data = self._require_ok("execute_python confirmation", confirmed)
        self._require_receipt("execute_python confirmation", confirmed)
        operation_id = str(confirmed.get("operationId") or "")
        execution_id = str(confirmed_data.get("executionId") or "")
        after = str(confirmed_data.get("afterFingerprint") or "")
        if operation_id != review_id:
            raise AssertionError("confirmation did not reuse the exact review ID")
        if not execution_id or not after:
            raise AssertionError("confirmation returned no rollback checkpoint")
        if confirmed_data.get("transactionCount") != 1:
            raise AssertionError("confirmation did not use one live transaction")
        if confirmed_data.get("fontSaved") is not False:
            raise AssertionError("confirmation did not report fontSaved=false")
        if str(confirmed_data.get("beforeFingerprint") or "") != before:
            raise AssertionError("confirmation did not use the reviewed baseline")
        if self.fingerprint() != after:
            raise AssertionError("confirmed live state does not match its fingerprint")
        self._require_commit(operation_id, "execute_python")
        self.current_fingerprint = after
        record = {
            "operationId": operation_id,
            "executionId": execution_id,
            "afterFingerprint": after,
        }
        self.active.append(record)
        self.operation_ids.append(operation_id)
        self.confirm_count += 1
        self.pending_review_id = None
        return record

    def rollback(self, record: Mapping[str, str]) -> str:
        response = self.invoke(
            "rollback_python_execution",
            {
                "executionId": record["executionId"],
                "expectedAfterFingerprint": self.current_fingerprint,
                "strategy": "auto",
                "confirm": True,
            },
        )
        data = self._require_ok("rollback_python_execution", response)
        self._require_receipt("rollback_python_execution", response)
        if data.get("transactionCount") != 1:
            raise AssertionError("Python rollback did not use one live transaction")
        after = str(data.get("afterFingerprint") or "")
        operation_id = str(response.get("operationId") or "")
        if not after or not operation_id:
            raise AssertionError("Python rollback returned no verified transition")
        if self.fingerprint() != after:
            raise AssertionError("Python rollback state does not match its fingerprint")
        self._require_commit(operation_id, "rollback_python_execution")
        self.current_fingerprint = after
        self.active.remove(dict(record))
        self.rollback_operation_ids.append(operation_id)
        self.rollback_count += 1
        return operation_id

    def revert(self, record: Mapping[str, str]) -> str:
        response = self.invoke(
            "revert_change",
            {
                "operationId": record["operationId"],
                "documentId": self.document_id,
                "expectedDocumentFingerprint": self.current_fingerprint,
            },
        )
        data = self._require_ok("revert_change", response)
        self._require_receipt("revert_change", response)
        if data.get("transactionCount") != 1:
            raise AssertionError("Change Log revert did not use one live transaction")
        after = str(data.get("afterFingerprint") or "")
        operation_id = str(response.get("operationId") or "")
        if not after or not operation_id:
            raise AssertionError("Change Log revert returned no verified transition")
        if self.fingerprint() != after:
            raise AssertionError("Change Log revert state does not match its fingerprint")
        self._require_commit(operation_id, "revert_change")
        self.current_fingerprint = after
        self.active.remove(dict(record))
        self.rollback_operation_ids.append(operation_id)
        self.rollback_count += 1
        # Generic revert consumes the contribution, so its parallel Python
        # checkpoint is intentionally no longer useful to this diagnostic.
        checkpoints = getattr(self.application, "_checkpoints", None)
        discard = getattr(checkpoints, "discard", None)
        if callable(discard):
            discard(record["executionId"])
        return operation_id

    def _discard_pending_review(self) -> None:
        if not self.pending_review_id:
            return
        reviews = getattr(self.application, "_reviews", None)
        getter = getattr(reviews, "get", None)
        record = getter(self.pending_review_id) if callable(getter) else None
        payload = getattr(record, "payload", {}) if record is not None else {}
        context = payload.get("executionContext", {}) if isinstance(payload, Mapping) else {}
        evidence_id = str(context.get("nativeReplayEvidenceId") or "") if isinstance(context, Mapping) else ""
        release = getattr(self.host, "release_staged_replay_evidence", None)
        if evidence_id and callable(release):
            release(evidence_id)
        discard = getattr(reviews, "discard", None)
        if callable(discard):
            discard(self.pending_review_id)
        self.pending_review_id = None

    def cleanup(self) -> list[str]:
        failures: list[str] = []
        self._discard_pending_review()
        for record in reversed(tuple(self.active)):
            try:
                self.rollback(record)
            except Exception as exc:
                failures.append(
                    "{}: {}".format(record["operationId"], str(exc)[:240])
                )
        return failures


def verify_open_edit_tab(
    font: Any,
    glyph_names: Sequence[str] = (),
    *,
    application: Any = None,
    host: Any = None,
) -> Mapping[str, Any]:
    """Open a typed Edit tab while proving document state stays unchanged."""

    family_name = str(getattr(font, "familyName", "") or "")
    if not family_name.startswith(DISPOSABLE_FAMILY_PREFIX):
        raise ValueError(
            "live v2 gates require a disposable font whose family name starts with {!r}".format(
                DISPOSABLE_FAMILY_PREFIX
            )
        )
    application, host = _resolve_live_runtime(application, host)
    document_id_for_font = getattr(host, "document_id_for_font", None)
    capture_model = getattr(host, "capture_stable_snapshot", None)
    if not callable(capture_model):
        capture_model = getattr(host, "capture_snapshot", None)
    if not callable(capture_model):
        capture_model = getattr(host, "capture_model", None)
    if not callable(document_id_for_font) or not callable(capture_model):
        raise RuntimeError("the active host does not expose the Edit-tab live-gate boundary")

    document_id = str(document_id_for_font(font) or "")
    if not document_id:
        raise RuntimeError("the disposable font has no stable v2 document ID")
    baseline = capture_model(document_id)
    baseline_fingerprint = fingerprint_model(baseline)
    glyphs = baseline.get("glyphs", {})
    available = list(glyphs) if isinstance(glyphs, Mapping) else [
        str(item.get("name") or "")
        for item in glyphs
        if isinstance(item, Mapping) and item.get("name")
    ]
    requested = tuple(glyph_names) if glyph_names else tuple(available[:2])
    if not requested:
        raise ValueError("the Edit-tab live gate requires at least one glyph")
    missing = [name for name in requested if name not in available]
    if missing:
        raise ValueError(
            "the Edit-tab live gate cannot find glyph(s): {}".format(
                ", ".join(missing)
            )
        )

    before_path = _plain_attribute(font, "filepath")
    before_master = _plain_attribute(font, "selectedFontMaster")
    before_master_id = str(_plain_attribute(before_master, "id") or "")
    before_dirty = _reported_dirty_state(host, document_id)
    arguments = {
        "documentId": document_id,
        "glyphNames": list(requested),
    }
    if before_master_id:
        arguments["masterId"] = before_master_id
    response = application.invoke("open_edit_tab", arguments)
    result = response.to_dict() if hasattr(response, "to_dict") else dict(response)
    if not result.get("ok"):
        error = result.get("error") or {}
        raise AssertionError(
            "open_edit_tab failed: {} ({})".format(
                error.get("message") or result.get("summary") or "unknown error",
                error.get("code") or "unknown",
            )
        )

    data = dict(result.get("data") or {})
    after = capture_model(document_id)
    after_fingerprint = fingerprint_model(after)
    after_path = _plain_attribute(font, "filepath")
    after_master = _plain_attribute(font, "selectedFontMaster")
    after_master_id = str(_plain_attribute(after_master, "id") or "")
    after_dirty = _reported_dirty_state(host, document_id)
    if data.get("beforeFingerprint") != baseline_fingerprint:
        raise AssertionError("open_edit_tab did not report the baseline fingerprint")
    if data.get("afterFingerprint") != after_fingerprint:
        raise AssertionError("open_edit_tab did not report the observed after fingerprint")
    if data.get("documentChanged") or data.get("observedChangeCount") != 0:
        raise AssertionError("open_edit_tab reported an unexpected document mutation")
    if after_fingerprint != baseline_fingerprint:
        raise AssertionError("open_edit_tab changed the canonical document")
    if after_path != before_path:
        raise AssertionError("open_edit_tab changed the working document path")
    if after_master_id != before_master_id:
        raise AssertionError("open_edit_tab changed the active master")
    if before_dirty is not None and after_dirty != before_dirty:
        raise AssertionError("open_edit_tab changed the reported dirty state")
    return {
        "documentId": document_id,
        "familyName": family_name,
        "glyphNames": list(requested),
        "documentFingerprint": baseline_fingerprint,
        "openedTab": bool(data.get("openedTab")),
        "documentUnchanged": True,
        "workingPathUnchanged": True,
        "activeMasterUnchanged": True,
        "reportedDirtyStateUnchanged": before_dirty is None or after_dirty == before_dirty,
    }


def verify_copy_and_make_copy(
    font: Any,
    output_path: str,
    *,
    application: Any = None,
    host: Any = None,
) -> Mapping[str, Any]:
    """Verify clone/archive invariants without saving the working document."""

    family_name = str(getattr(font, "familyName", "") or "")
    if not family_name.startswith(DISPOSABLE_FAMILY_PREFIX):
        raise ValueError(
            "live v2 gates require a disposable font whose family name starts with {!r}".format(
                DISPOSABLE_FAMILY_PREFIX
            )
        )
    destination = Path(output_path)
    if not destination.is_absolute() or destination.exists():
        raise ValueError("the live-gate output must be a new explicit absolute path")
    if not destination.parent.is_dir():
        raise ValueError("the live-gate output parent must already exist")

    application, host = _resolve_live_runtime(application, host)
    document_id_for_font = getattr(host, "document_id_for_font", None)
    capture_model = getattr(host, "capture_snapshot", None)
    capture_detached = getattr(host, "_capture_detached_model", None)
    reconcile_detached = getattr(host, "_reconcile_detached_clone", None)
    instance_ids_for_font = getattr(host, "_instance_ids_for_font", None)
    if not all(
        callable(value)
        for value in (
            document_id_for_font,
            capture_model,
            capture_detached,
            reconcile_detached,
            instance_ids_for_font,
        )
    ):
        raise RuntimeError(
            "the active host does not expose the detached-copy proof boundary"
        )
    document_id = str(document_id_for_font(font) or "")
    if not document_id:
        raise RuntimeError("the disposable font has no stable v2 document ID")
    before_model = capture_model(document_id)
    before_fingerprint = fingerprint_model(before_model)
    before_path = getattr(font, "filepath", None)
    document = getattr(font, "parent", None)
    before_native_dirty = (
        getattr(document, "isDocumentEdited", None)
        if document is not None
        else None
    )
    before_native_dirty = (
        before_native_dirty()
        if callable(before_native_dirty)
        else before_native_dirty
    )
    before_dirty = _reported_dirty_state(host, document_id)

    clone = font.copy()
    if clone is None or clone is font:
        raise AssertionError("GSFont.copy() did not return a detached clone")
    instance_ids = instance_ids_for_font(document_id, font)
    observed_clone = capture_detached(
        clone,
        before_model,
        instance_ids=instance_ids,
        document_path=before_path,
    )
    normalized_clone, _projection = reconcile_detached(
        clone,
        before_model,
        observed_clone,
        document_id=document_id,
        instance_ids=instance_ids,
        observed_is_complete=True,
    )
    clone_fingerprint = fingerprint_model(normalized_clone)
    if clone_fingerprint != before_fingerprint:
        residual = diff_models(before_model, normalized_clone)
        raise AssertionError(
            "GSFont.copy() changed the canonical document model; "
            "changes={}; firstPaths={!r}".format(
                len(residual.changes),
                [list(change.path) for change in residual.changes[:20]],
            )
        )
    source_archive = _serialized_font_archive(font)
    clone_archive = _serialized_font_archive(clone)
    archive_comparison = _compare_native_archives(
        source_archive,
        clone_archive,
        limit=20,
    )
    archive_coverage = {
        "complete": True,
        "coveredCount": 0,
        "uncoveredLocations": [],
    }
    if not archive_comparison["equivalent"]:
        artifacts = getattr(_projection, "artifacts", None)
        artifact_paths = tuple(
            change.path
            for change in getattr(artifacts, "changes", ())
        )
        archive_coverage = _classify_native_clone_archive_mismatches(
            archive_comparison["mismatchLocations"],
            artifact_paths=artifact_paths,
            direct_tree=_decoded_native_archive_tree(source_archive),
            replay_tree=_decoded_native_archive_tree(clone_archive),
        )
        if archive_comparison["truncated"] or not archive_coverage["complete"]:
            raise AssertionError(
                "GSFont.copy() changed unmodeled serialized document state; "
                "mismatches={!r}; truncated={}".format(
                    archive_coverage["uncoveredLocations"],
                    archive_comparison["truncated"],
                )
            )

    _save_font_copy(font, destination)
    os.chmod(destination, 0o600)

    after_path = getattr(font, "filepath", None)
    after_native_dirty = (
        getattr(document, "isDocumentEdited", None)
        if document is not None
        else None
    )
    after_native_dirty = (
        after_native_dirty()
        if callable(after_native_dirty)
        else after_native_dirty
    )
    after_dirty = _reported_dirty_state(host, document_id)
    after_fingerprint = fingerprint_model(capture_model(document_id))
    if (
        after_path != before_path
        or after_native_dirty != before_native_dirty
        or after_dirty != before_dirty
    ):
        raise AssertionError("GSFont.save(makeCopy=True) changed the working path or dirty state")
    if after_fingerprint != before_fingerprint:
        raise AssertionError("the live working document changed during the copy gate")
    return {
        "familyName": family_name,
        "documentFingerprint": before_fingerprint,
        "copyFingerprint": clone_fingerprint,
        "outputPath": str(destination),
        "outputMode": "0600",
        "nativeCloneArtifactCount": len(
            getattr(getattr(_projection, "artifacts", None), "changes", ())
        ),
        "nativeArchiveCoveredMismatchCount": archive_coverage["coveredCount"],
        "workingPathUnchanged": True,
        "dirtyStateUnchanged": True,
    }


def verify_schema_v3_structural_kernel(
    font: Any,
    *,
    application: Any = None,
    host: Any = None,
) -> Mapping[str, Any]:
    """Exercise schema-v3 mutations through the active public application.

    This is an explicit disposable Glyphs 4 qualification gate, not an MCP
    capability. It deliberately composes the same typed tools and generic
    ``revert_change`` operation that a client uses. Every successful forward
    operation is tracked and reverted in reverse order if a later assertion
    fails, so the live document must finish at its exact canonical baseline.
    """

    family_name = str(getattr(font, "familyName", "") or "")
    if not family_name.startswith(DISPOSABLE_FAMILY_PREFIX):
        raise ValueError(
            "live v2 gates require a disposable font whose family name starts with {!r}".format(
                DISPOSABLE_FAMILY_PREFIX
            )
        )
    application, host = _resolve_live_runtime(application, host)
    document_id_for_font = getattr(host, "document_id_for_font", None)
    capture_model = getattr(host, "capture_snapshot", None)
    if not callable(capture_model):
        capture_model = getattr(host, "capture_model", None)
    if not callable(document_id_for_font) or not callable(capture_model):
        raise RuntimeError("the active host does not expose the structural live-gate boundary")
    document_id = str(document_id_for_font(font) or "")
    if not document_id:
        raise RuntimeError("the disposable font has no stable v2 document ID")

    baseline = capture_model(document_id)
    _assert_unique_unicode_assignments(baseline, phase="baseline")
    baseline_fingerprint = fingerprint_model(baseline)
    before_path = _plain_attribute(font, "filepath")
    before_master = _plain_attribute(font, "selectedFontMaster")
    before_master_id = str(_plain_attribute(before_master, "id") or "")
    before_dirty = _reported_dirty_state(host, document_id)
    suffix = baseline_fingerprint.split(":")[-1][:6]

    glyph_names = list((baseline.get("glyphs") or {}).keys())
    if not glyph_names:
        raise ValueError("the schema-v3 live gate requires one existing disposable glyph")
    probe_a = glyph_names[0]
    probe_b = glyph_names[1] if len(glyph_names) > 1 else probe_a
    glyph_a = _unique_name("mcpV2Gate{}A".format(suffix), glyph_names)
    glyph_b = _unique_name(
        "mcpV2Gate{}B".format(suffix), [*glyph_names, glyph_a]
    )
    selective_a = _unique_name(
        "mcpV2Gate{}C".format(suffix), [*glyph_names, glyph_a, glyph_b]
    )
    selective_b = _unique_name(
        "mcpV2Gate{}D".format(suffix),
        [*glyph_names, glyph_a, glyph_b, selective_a],
    )
    feature_a, feature_b = _unused_feature_tags(baseline, 2)
    class_name = _unique_name(
        "_MCPV2Gate{}".format(suffix),
        [
            str(item.get("name") or "")
            for item in baseline.get("classes", [])
            if isinstance(item, Mapping)
        ],
    )
    prefix_name = _unique_name(
        "MCP V2 Gate {}".format(suffix),
        [
            str(item.get("name") or "")
            for item in baseline.get("featurePrefixes", [])
            if isinstance(item, Mapping)
        ],
    )
    instance_ids = {
        str(item.get("id") or "")
        for item in baseline.get("instances", [])
        if isinstance(item, Mapping)
    }
    instance_a = _unique_name("mcp_gate_{}_a".format(suffix), instance_ids)
    instance_b = _unique_name(
        "mcp_gate_{}_b".format(suffix), [*instance_ids, instance_a]
    )
    baseline_instances = [
        item for item in baseline.get("instances", []) if isinstance(item, Mapping)
    ]
    instance_axes = list(baseline_instances[0].get("axes") or []) if baseline_instances else []

    qualified_domains: list[str] = []
    session = _StructuralGateSession(
        application,
        host,
        document_id,
        baseline_fingerprint,
    )

    try:
        session.round_trip(
            "apply_glyph_updates",
            [
                (
                    {"action": "create", "glyphName": glyph_a, "export": True},
                    {"action": "create", "glyphName": glyph_b, "export": True},
                ),
                (
                    {"action": "update", "glyphName": glyph_a, "export": False},
                    {"action": "update", "glyphName": glyph_b, "category": "Symbol"},
                ),
                (
                    {"action": "delete", "glyphName": glyph_a},
                    {"action": "delete", "glyphName": glyph_b},
                ),
            ],
        )
        qualified_domains.append("glyphs")

        session.round_trip(
            "apply_opentype_updates",
            [
                (
                    {"action": "create", "kind": "feature", "name": feature_a, "code": "sub {0} by {0};".format(probe_a)},
                    {"action": "create", "kind": "feature", "name": feature_b, "code": "sub {0} by {0};".format(probe_a)},
                    {"action": "create", "kind": "class", "name": class_name, "code": probe_a},
                    {"action": "create", "kind": "prefix", "name": prefix_name, "code": "languagesystem DFLT dflt;"},
                ),
                (
                    {"action": "update", "kind": "feature", "name": feature_a, "code": "sub {0} {0} by {0};".format(probe_a), "disabled": True},
                    {"action": "move", "kind": "feature", "name": feature_b, "index": 0},
                    {"action": "update", "kind": "class", "name": class_name, "code": "{} {}".format(probe_a, probe_b)},
                    {"action": "update", "kind": "prefix", "name": prefix_name, "code": "languagesystem latn dflt;"},
                ),
                (
                    {"action": "delete", "kind": "feature", "name": feature_a},
                    {"action": "delete", "kind": "feature", "name": feature_b},
                    {"action": "delete", "kind": "class", "name": class_name},
                    {"action": "delete", "kind": "prefix", "name": prefix_name},
                ),
            ],
        )
        qualified_domains.append("opentype")

        session.round_trip(
            "apply_instance_updates",
            [
                (
                    {"action": "create", "instanceId": instance_a, "name": "MCP V2 Gate Static", "type": "static", "included": True, "axes": instance_axes},
                    {"action": "create", "instanceId": instance_b, "name": "MCP V2 Gate Variable", "type": "variable", "included": True, "axes": instance_axes},
                ),
                (
                    {"action": "update", "instanceId": instance_a, "name": "MCP V2 Gate Static Updated", "included": False},
                    {"action": "move", "instanceId": instance_b, "index": 0},
                ),
                (
                    {"action": "delete", "instanceId": instance_a},
                    {"action": "delete", "instanceId": instance_b},
                ),
            ],
        )
        qualified_domains.append("instances")

        selective_first = session.apply(
            "apply_glyph_updates",
            [{"action": "create", "glyphName": selective_a, "export": True}],
        )
        selective_second = session.apply(
            "apply_glyph_updates",
            [{"action": "create", "glyphName": selective_b, "export": True}],
        )
        session.revert(selective_first)
        if selective_b not in session.model().get("glyphs", {}):
            raise AssertionError("selective revert removed an unrelated later glyph")
        session.revert(selective_second)
        qualified_domains.append("selective_revert")

        session.refuse(
            "apply_glyph_updates",
            "stale_document",
            [{"action": "update", "glyphName": probe_a, "export": False}],
            stale=True,
        )
        session.refuse(
            "apply_glyph_updates",
            "invalid_request",
            [{"action": "create", "glyphName": probe_a, "export": True}],
        )
        qualified_domains.append("atomic_refusal")
    except BaseException:
        cleanup_failures = session.cleanup()
        final = session.fingerprint()
        if cleanup_failures or final != baseline_fingerprint:
            raise RuntimeError(
                "schema-v3 live-gate cleanup failed for {} operation(s); final fingerprint {}".format(
                    len(cleanup_failures), final
                )
            )
        raise

    final_fingerprint = session.fingerprint()
    after_path = _plain_attribute(font, "filepath")
    after_master = _plain_attribute(font, "selectedFontMaster")
    after_master_id = str(_plain_attribute(after_master, "id") or "")
    after_dirty = _reported_dirty_state(host, document_id)
    if final_fingerprint != baseline_fingerprint:
        raise AssertionError("schema-v3 live gate did not restore the canonical baseline")
    if after_path != before_path:
        raise AssertionError("schema-v3 live gate changed the working document path")
    if after_master_id != before_master_id:
        raise AssertionError("schema-v3 live gate changed the active master")
    if before_dirty is not None and after_dirty != before_dirty:
        raise AssertionError("schema-v3 live gate changed the reported dirty state")
    return {
        "documentId": document_id,
        "familyName": family_name,
        "baselineFingerprint": baseline_fingerprint,
        "finalFingerprint": final_fingerprint,
        "qualifiedDomains": qualified_domains,
        "successfulTransactionCount": len(session.successful),
        "operationIds": session.successful,
        "refusalCount": len(session.refusals),
        "refusalCodes": session.refusals,
        "exactBaselineRestored": True,
        "workingPathUnchanged": True,
        "activeMasterUnchanged": True,
        "reportedDirtyStateUnchanged": before_dirty is None or after_dirty == before_dirty,
        "singleTransactionResponses": session.single_transactions,
        "auditReceiptsPresent": session.audit_receipts,
        "changeLogCommitsPresent": session.change_log_commits,
    }


def verify_schema_v4_master_lifecycle(
    font: Any,
    *,
    application: Any = None,
    host: Any = None,
) -> Mapping[str, Any]:
    """Duplicate, edit, reorder, delete, and exactly revert one master."""

    gate_started = time.perf_counter_ns()
    family_name = str(getattr(font, "familyName", "") or "")
    if not family_name.startswith(DISPOSABLE_FAMILY_PREFIX):
        raise ValueError(
            "live v2 gates require a disposable font whose family name starts with {!r}".format(
                DISPOSABLE_FAMILY_PREFIX
            )
        )
    application, host = _resolve_live_runtime(application, host)
    document_id_for_font = getattr(host, "document_id_for_font", None)
    capture_model = getattr(host, "capture_snapshot", None)
    if not callable(capture_model):
        capture_model = getattr(host, "capture_model", None)
    if not callable(document_id_for_font) or not callable(capture_model):
        raise RuntimeError("the active host does not expose the master live-gate boundary")
    document_id = str(document_id_for_font(font) or "")
    baseline = capture_model(document_id)
    _assert_unique_unicode_assignments(baseline, phase="baseline")
    baseline_fingerprint = fingerprint_model(baseline)
    masters = [
        master
        for master in baseline.get("masters", [])
        if isinstance(master, Mapping)
    ]
    if not masters:
        raise ValueError("the schema-v4 master gate requires one existing master")
    source = masters[0]
    source_id = str(source.get("id") or "")
    if not source_id:
        raise ValueError("the schema-v4 master gate requires stable master IDs")
    before_path = _plain_attribute(font, "filepath")
    before_master = _plain_attribute(font, "selectedFontMaster")
    before_master_id = str(_plain_attribute(before_master, "id") or "")
    before_dirty = _reported_dirty_state(host, document_id)
    new_id = str(uuid4()).upper()
    session = _StructuralGateSession(
        application,
        host,
        document_id,
        baseline_fingerprint,
    )

    try:
        duplicate = session.apply(
            "apply_master_updates",
            [
                {
                    "action": "duplicate",
                    "sourceMasterId": source_id,
                    "masterId": new_id,
                    "name": "MCP V2 Gate Master",
                    "index": min(1, len(masters)),
                }
            ],
        )
        duplicate_changes = session.change_set(duplicate).changes
        if not any(
            change.path == ("masters", new_id)
            and not change.before_present
            and change.after_present
            for change in duplicate_changes
        ):
            raise AssertionError("master duplication did not add exactly one master")
        expected_glyphs = set((baseline.get("glyphs") or {}).keys())
        duplicated_layer_glyphs = {
            change.path[1]
            for change in duplicate_changes
            if len(change.path) == 4
            and change.path[0] == "glyphs"
            and change.path[2] == "layers"
            and change.path[3] == new_id
            and not change.before_present
            and change.after_present
        }
        if duplicated_layer_glyphs != expected_glyphs:
            raise AssertionError("master duplication did not add every owned glyph layer")

        updated = session.apply(
            "apply_master_updates",
            [
                {
                    "action": "update",
                    "masterId": new_id,
                    "name": "MCP V2 Gate Master Updated",
                    "italicAngle": float(source.get("italicAngle") or 0) + 1,
                }
            ],
        )
        moved = session.apply(
            "apply_master_updates",
            [{"action": "move", "masterId": new_id, "index": 0}],
        )
        deleted = session.apply(
            "apply_master_updates",
            [{"action": "delete", "masterId": new_id}],
        )
        delete_changes = session.change_set(deleted).changes
        if not any(
            change.path == ("masters", new_id)
            and change.before_present
            and not change.after_present
            for change in delete_changes
        ):
            raise AssertionError("master deletion left the target in the collection")
        deleted_layer_glyphs = {
            change.path[1]
            for change in delete_changes
            if len(change.path) == 4
            and change.path[0] == "glyphs"
            and change.path[2] == "layers"
            and change.path[3] == new_id
            and change.before_present
            and not change.after_present
        }
        if deleted_layer_glyphs != expected_glyphs:
            raise AssertionError("master deletion did not remove every owned glyph layer")

        for operation_id in (deleted, moved, updated, duplicate):
            session.revert(operation_id)

        session.refuse(
            "apply_master_updates",
            "stale_document",
            [
                {
                    "action": "duplicate",
                    "sourceMasterId": source_id,
                    "masterId": str(uuid4()).upper(),
                    "name": "Stale Gate Master",
                }
            ],
            stale=True,
        )
        session.refuse(
            "apply_master_updates",
            "invalid_request",
            [
                {
                    "action": "duplicate",
                    "sourceMasterId": source_id,
                    "masterId": source_id,
                    "name": "Duplicate ID",
                }
            ],
        )
    except BaseException:
        cleanup_failures = session.cleanup()
        final = session.fingerprint()
        if cleanup_failures or final != baseline_fingerprint:
            raise RuntimeError(
                "schema-v4 master gate cleanup failed for {} operation(s); final fingerprint {}".format(
                    len(cleanup_failures), final
                )
            )
        raise

    final_fingerprint = session.fingerprint()
    after_path = _plain_attribute(font, "filepath")
    after_master = _plain_attribute(font, "selectedFontMaster")
    after_master_id = str(_plain_attribute(after_master, "id") or "")
    after_dirty = _reported_dirty_state(host, document_id)
    if final_fingerprint != baseline_fingerprint:
        raise AssertionError("schema-v4 master gate did not restore the canonical baseline")
    if after_path != before_path:
        raise AssertionError("schema-v4 master gate changed the working document path")
    if after_master_id != before_master_id:
        raise AssertionError("schema-v4 master gate changed the active master")
    if before_dirty is not None and after_dirty != before_dirty:
        raise AssertionError("schema-v4 master gate changed the reported dirty state")
    timing_totals = {
        name: sum(values.get(name, 0.0) for values in session.stage_timings.values())
        for name in (
            "initial_capture",
            "clone",
            "detached_apply",
            "verification",
            "live_apply",
            "settled_verification",
            "history",
            "total",
        )
    }
    return {
        "documentId": document_id,
        "familyName": family_name,
        "baselineFingerprint": baseline_fingerprint,
        "finalFingerprint": final_fingerprint,
        "qualifiedDomains": ["master_lifecycle", "atomic_refusal"],
        "successfulTransactionCount": len(session.successful),
        "operationIds": session.successful,
        "refusalCount": len(session.refusals),
        "refusalCodes": session.refusals,
        "exactBaselineRestored": True,
        "workingPathUnchanged": True,
        "activeMasterUnchanged": True,
        "reportedDirtyStateUnchanged": before_dirty is None
        or after_dirty == before_dirty,
        "singleTransactionResponses": session.single_transactions,
        "auditReceiptsPresent": session.audit_receipts,
        "changeLogCommitsPresent": session.change_log_commits,
        "stageTimingsByOperation": dict(session.stage_timings),
        "stageTimingTotalsMs": timing_totals,
        "gateDurationMs": (
            time.perf_counter_ns() - gate_started
        ) / 1_000_000,
    }


def verify_schema_v5_layer_lifecycle(
    font: Any,
    *,
    application: Any = None,
    host: Any = None,
) -> Mapping[str, Any]:
    """Round-trip one intermediate layer through every public lifecycle action."""

    gate_started = time.perf_counter_ns()
    family_name = str(getattr(font, "familyName", "") or "")
    if not family_name.startswith(DISPOSABLE_FAMILY_PREFIX):
        raise ValueError(
            "live v2 gates require a disposable font whose family name starts with {!r}".format(
                DISPOSABLE_FAMILY_PREFIX
            )
        )
    application, host = _resolve_live_runtime(application, host)
    document_id_for_font = getattr(host, "document_id_for_font", None)
    capture_model = getattr(host, "capture_snapshot", None)
    if not callable(capture_model):
        capture_model = getattr(host, "capture_model", None)
    if not callable(document_id_for_font) or not callable(capture_model):
        raise RuntimeError("the active host does not expose the layer live-gate boundary")
    document_id = str(document_id_for_font(font) or "")
    baseline = capture_model(document_id)
    _assert_unique_unicode_assignments(baseline, phase="baseline")
    baseline_fingerprint = fingerprint_model(baseline)
    axis_tags = [
        str(axis.get("tag") or "")
        for master in baseline.get("masters", [])
        if isinstance(master, Mapping)
        for axis in master.get("axes", [])
        if isinstance(axis, Mapping) and axis.get("tag")
    ]
    if not axis_tags:
        raise ValueError("the schema-v5 layer gate requires one known font axis")
    glyph_name = ""
    source_layer_id = ""
    source_master_id = ""
    master_prefix_length = 0
    glyphs = baseline.get("glyphs", {})
    if isinstance(glyphs, Mapping):
        for candidate_name in sorted(glyphs):
            glyph = glyphs[candidate_name]
            layers = glyph.get("layers", ()) if isinstance(glyph, Mapping) else ()
            if not isinstance(layers, (list, tuple)):
                continue
            candidate_master_prefix = 0
            for layer in layers:
                if isinstance(layer, Mapping) and bool(layer.get("isMasterLayer")):
                    candidate_master_prefix += 1
                else:
                    break
            for layer in layers:
                if isinstance(layer, Mapping) and bool(layer.get("isMasterLayer")):
                    glyph_name = str(candidate_name)
                    source_layer_id = str(layer.get("id") or "")
                    source_master_id = str(layer.get("masterId") or source_layer_id)
                    master_prefix_length = candidate_master_prefix
                    break
            if source_layer_id:
                break
    if not glyph_name or not source_layer_id or not source_master_id:
        raise ValueError("the schema-v5 layer gate requires one stable master layer")

    before_path = _plain_attribute(font, "filepath")
    before_master = _plain_attribute(font, "selectedFontMaster")
    before_master_id = str(_plain_attribute(before_master, "id") or "")
    before_dirty = _reported_dirty_state(host, document_id)
    new_id = str(uuid4()).upper()
    sentinel_id = str(uuid4()).upper()
    axis_tag = axis_tags[0]
    session = _StructuralGateSession(
        application,
        host,
        document_id,
        baseline_fingerprint,
    )

    try:
        duplicate = session.apply(
            "apply_layer_updates",
            [
                {
                    "action": "duplicate",
                    "glyphName": glyph_name,
                    "sourceLayerId": source_layer_id,
                    "layerId": new_id,
                    "masterId": source_master_id,
                    "name": "{125}",
                    "interpolation": {
                        "kind": "intermediate",
                        "coordinates": {axis_tag: 125},
                    },
                    "index": master_prefix_length,
                }
            ],
        )
        duplicate_changes = session.change_set(duplicate).changes
        if not any(
            change.path == ("glyphs", glyph_name, "layers", new_id)
            and not change.before_present
            and change.after_present
            for change in duplicate_changes
        ):
            raise AssertionError("layer duplication did not add one identity-addressed layer")

        updated = session.apply(
            "apply_layer_updates",
            [
                {
                    "action": "update",
                    "glyphName": glyph_name,
                    "layerId": new_id,
                    "name": "[400]",
                    "interpolation": {
                        "kind": "alternate",
                        "ranges": {axis_tag: {"min": 400, "max": None}},
                    },
                }
            ],
        )
        sentinel = session.apply(
            "apply_layer_updates",
            [
                {
                    "action": "duplicate",
                    "glyphName": glyph_name,
                    "sourceLayerId": source_layer_id,
                    "layerId": sentinel_id,
                    "masterId": source_master_id,
                    "name": "MCP layer order sentinel",
                    "interpolation": None,
                    "index": master_prefix_length + 1,
                }
            ],
        )
        moved = session.apply(
            "apply_layer_updates",
            [
                {
                    "action": "move",
                    "glyphName": glyph_name,
                    "layerId": new_id,
                    "index": master_prefix_length + 1,
                }
            ],
        )
        if not any(
            change.path == ("glyphs", glyph_name, "layers", "$order")
            for change in session.change_set(moved).changes
        ):
            raise AssertionError("layer move did not change the canonical non-master order")
        deleted = session.apply(
            "apply_layer_updates",
            [{"action": "delete", "glyphName": glyph_name, "layerId": new_id}],
        )
        if not any(
            change.path == ("glyphs", glyph_name, "layers", new_id)
            and change.before_present
            and not change.after_present
            for change in session.change_set(deleted).changes
        ):
            raise AssertionError("layer deletion left the target in the collection")

        for operation_id in (deleted, moved, sentinel, updated, duplicate):
            session.revert(operation_id)

        session.refuse(
            "apply_layer_updates",
            "stale_document",
            [{"action": "move", "glyphName": glyph_name, "layerId": source_layer_id, "index": 0}],
            stale=True,
        )
        session.refuse(
            "apply_layer_updates",
            "invalid_request",
            [{"action": "delete", "glyphName": glyph_name, "layerId": source_layer_id}],
        )
    except BaseException:
        cleanup_failures = session.cleanup()
        final = session.fingerprint()
        if cleanup_failures or final != baseline_fingerprint:
            raise RuntimeError(
                "schema-v5 layer gate cleanup failed for {} operation(s); final fingerprint {}".format(
                    len(cleanup_failures), final
                )
            )
        raise

    final_fingerprint = session.fingerprint()
    after_path = _plain_attribute(font, "filepath")
    after_master = _plain_attribute(font, "selectedFontMaster")
    after_master_id = str(_plain_attribute(after_master, "id") or "")
    after_dirty = _reported_dirty_state(host, document_id)
    if final_fingerprint != baseline_fingerprint:
        raise AssertionError("schema-v5 layer gate did not restore the canonical baseline")
    if after_path != before_path:
        raise AssertionError("schema-v5 layer gate changed the working document path")
    if after_master_id != before_master_id:
        raise AssertionError("schema-v5 layer gate changed the active master")
    if before_dirty is not None and after_dirty != before_dirty:
        raise AssertionError("schema-v5 layer gate changed the reported dirty state")
    return {
        "documentId": document_id,
        "familyName": family_name,
        "baselineFingerprint": baseline_fingerprint,
        "finalFingerprint": final_fingerprint,
        "qualifiedDomains": ["layer_lifecycle", "interpolation_rules", "atomic_refusal"],
        "successfulTransactionCount": len(session.successful),
        "operationIds": session.successful,
        "refusalCount": len(session.refusals),
        "refusalCodes": session.refusals,
        "exactBaselineRestored": True,
        "workingPathUnchanged": True,
        "activeMasterUnchanged": True,
        "reportedDirtyStateUnchanged": before_dirty is None or after_dirty == before_dirty,
        "singleTransactionResponses": session.single_transactions,
        "auditReceiptsPresent": session.audit_receipts,
        "changeLogCommitsPresent": session.change_log_commits,
        "stageTimingsByOperation": dict(session.stage_timings),
        "gateDurationMs": (time.perf_counter_ns() - gate_started) / 1_000_000,
    }


def verify_context_kerning(
    font: Any,
    *,
    application: Any = None,
    host: Any = None,
) -> Mapping[str, Any]:
    """Round-trip both contextual boundaries in ``L quoteright A``.

    This is a disposable Glyphs 4 mutation gate for the typed storage and
    transaction contract. Exported shaping remains a separate visual QA step.
    """

    gate_started = time.perf_counter_ns()
    family_name = str(getattr(font, "familyName", "") or "")
    if not family_name.startswith(DISPOSABLE_FAMILY_PREFIX):
        raise ValueError(
            "live v2 gates require a disposable font whose family name starts with {!r}".format(
                DISPOSABLE_FAMILY_PREFIX
            )
        )
    application, host = _resolve_live_runtime(application, host)
    document_id_for_font = getattr(host, "document_id_for_font", None)
    capture_model = getattr(host, "capture_snapshot", None)
    if not callable(capture_model):
        capture_model = getattr(host, "capture_model", None)
    if not callable(document_id_for_font) or not callable(capture_model):
        raise RuntimeError(
            "the active host does not expose the contextual kerning live-gate boundary"
        )
    document_id = str(document_id_for_font(font) or "")
    baseline = capture_model(document_id)
    _assert_unique_unicode_assignments(baseline, phase="baseline")
    baseline_fingerprint = fingerprint_model(baseline)
    glyphs = baseline.get("glyphs", {})
    required_glyphs = ("L", "quoteright", "A")
    if not isinstance(glyphs, Mapping) or any(
        name not in glyphs for name in required_glyphs
    ):
        raise ValueError(
            "the contextual kerning gate requires L, quoteright, and A"
        )
    masters = [
        str(master.get("id") or "")
        for master in baseline.get("masters", [])
        if isinstance(master, Mapping) and master.get("id")
    ]
    if not masters:
        raise ValueError(
            "the contextual kerning gate requires one stable master ID"
        )
    master_id = masters[0]
    before_path = _plain_attribute(font, "filepath")
    before_master = _plain_attribute(font, "selectedFontMaster")
    before_master_id = str(_plain_attribute(before_master, "id") or "")
    before_dirty = _reported_dirty_state(host, document_id)
    baseline_archive = _serialized_font_archive(font)
    baseline_archive_fingerprint = _native_archive_fingerprint(baseline_archive)
    baseline_kerning = baseline.get("kerning", {})
    baseline_contexts = (
        baseline_kerning.get("context", {})
        if isinstance(baseline_kerning, Mapping)
        else {}
    )

    def changed_value(context_key: str, fallback: float) -> float:
        values = baseline_contexts.get(context_key, {})
        existing = values.get(master_id) if isinstance(values, Mapping) else None
        return float(existing) + 1.0 if existing is not None else fallback

    first_value = changed_value("L * quoteright A", -40.0)
    second_value = changed_value("L quoteright * A", 80.0)
    session = _StructuralGateSession(
        application,
        host,
        document_id,
        baseline_fingerprint,
    )

    try:
        operation_id = session.apply(
            "apply_kerning_updates",
            [
                {
                    "entryKind": "context",
                    "masterId": master_id,
                    "sequence": list(required_glyphs),
                    "boundaryIndex": 1,
                    "value": first_value,
                },
                {
                    "entryKind": "context",
                    "masterId": master_id,
                    "sequence": list(required_glyphs),
                    "boundaryIndex": 2,
                    "value": second_value,
                },
            ],
        )
        observed_contexts: list[Mapping[str, Any]] = []
        cursor = None
        while True:
            response = session.invoke(
                "list_kerning_pairs",
                {
                    "documentId": document_id,
                    "entryKind": "context",
                    "pageSize": 500,
                    "cursor": cursor,
                },
            )
            if not response.get("ok"):
                raise AssertionError(
                    "contextual kerning readback failed: {}".format(
                        response.get("summary") or response.get("error")
                    )
                )
            observed_contexts.extend(
                item
                for item in (response.get("data") or {}).get("pairs", [])
                if isinstance(item, Mapping)
            )
            cursor = (response.get("page") or {}).get("nextCursor")
            if not cursor:
                break
        observed = {
            (
                str(item.get("masterId") or ""),
                tuple(item.get("sequence") or ()),
                item.get("boundaryIndex"),
            ): item.get("value")
            for item in observed_contexts
            if item.get("editable")
        }
        expected_sequence = tuple(required_glyphs)
        if observed.get((master_id, expected_sequence, 1)) != first_value:
            raise AssertionError("first L quoteright A context did not read back")
        if observed.get((master_id, expected_sequence, 2)) != second_value:
            raise AssertionError("second L quoteright A context did not read back")

        after_apply = session.model()
        after_kerning = after_apply.get("kerning", {})
        if isinstance(baseline_kerning, Mapping) and isinstance(
            after_kerning, Mapping
        ):
            for direction in ("ltr", "rtl", "vertical"):
                if after_kerning.get(direction, {}) != baseline_kerning.get(
                    direction, {}
                ):
                    raise AssertionError(
                        "contextual update changed {} pair kerning".format(
                            direction
                        )
                    )
        session.revert(operation_id)
        session.refuse(
            "apply_kerning_updates",
            "invalid_request",
            [
                {
                    "entryKind": "context",
                    "masterId": master_id,
                    "sequence": ["L", "A"],
                    "boundaryIndex": 1,
                    "value": -10,
                }
            ],
        )
    except BaseException:
        cleanup_failures = session.cleanup()
        final = session.fingerprint()
        if cleanup_failures or final != baseline_fingerprint:
            raise RuntimeError(
                "contextual kerning gate cleanup failed for {} operation(s); final fingerprint {}".format(
                    len(cleanup_failures), final
                )
            )
        raise

    final_fingerprint = session.fingerprint()
    final_archive = _serialized_font_archive(font)
    archive_comparison = _compare_native_archives(
        baseline_archive,
        final_archive,
        limit=20,
    )
    after_path = _plain_attribute(font, "filepath")
    after_master = _plain_attribute(font, "selectedFontMaster")
    after_master_id = str(_plain_attribute(after_master, "id") or "")
    after_dirty = _reported_dirty_state(host, document_id)
    if final_fingerprint != baseline_fingerprint:
        raise AssertionError(
            "contextual kerning gate did not restore the canonical baseline"
        )
    if not archive_comparison["equivalent"]:
        raise AssertionError(
            "contextual kerning gate did not restore the native archive; mismatches={!r}".format(
                archive_comparison["mismatchLocations"]
            )
        )
    if after_path != before_path:
        raise AssertionError(
            "contextual kerning gate changed the working document path"
        )
    if after_master_id != before_master_id:
        raise AssertionError("contextual kerning gate changed the active master")
    if before_dirty is not None and after_dirty != before_dirty:
        raise AssertionError(
            "contextual kerning gate changed the reported dirty state"
        )
    return {
        "documentId": document_id,
        "familyName": family_name,
        "masterId": master_id,
        "baselineFingerprint": baseline_fingerprint,
        "finalFingerprint": final_fingerprint,
        "baselineArchiveFingerprint": baseline_archive_fingerprint,
        "finalArchiveFingerprint": _native_archive_fingerprint(final_archive),
        "qualifiedDomains": [
            "context_storage",
            "context_readback",
            "pair_domain_preservation",
            "atomic_refusal",
        ],
        "operationIds": session.successful,
        "refusalCodes": session.refusals,
        "exactCanonicalBaselineRestored": True,
        "exactNativeArchiveRestored": True,
        "nativeArchiveBytesUnchanged": baseline_archive == final_archive,
        "workingPathUnchanged": True,
        "activeMasterUnchanged": True,
        "reportedDirtyStateUnchanged": before_dirty is None
        or after_dirty == before_dirty,
        "singleTransactionResponses": session.single_transactions,
        "auditReceiptsPresent": session.audit_receipts,
        "changeLogCommitsPresent": session.change_log_commits,
        "gateDurationMs": (time.perf_counter_ns() - gate_started) / 1_000_000,
    }


def verify_staged_python_structural_replay(
    font: Any,
    *,
    application: Any = None,
    host: Any = None,
) -> Mapping[str, Any]:
    """Qualify schema-v5 structural replay on one disposable Glyphs 4 font."""

    family_name = str(getattr(font, "familyName", "") or "")
    if not family_name.startswith(DISPOSABLE_FAMILY_PREFIX):
        raise ValueError(
            "live v2 gates require a disposable font whose family name starts with {!r}".format(
                DISPOSABLE_FAMILY_PREFIX
            )
        )
    application, host = _resolve_live_runtime(application, host)
    document_id_for_font = getattr(host, "document_id_for_font", None)
    capture_model = getattr(host, "capture_snapshot", None)
    if not callable(capture_model):
        capture_model = getattr(host, "capture_model", None)
    if not callable(document_id_for_font) or not callable(capture_model):
        raise RuntimeError(
            "the active host does not expose the staged structural live-gate boundary"
        )
    document_id = str(document_id_for_font(font) or "")
    if not document_id:
        raise RuntimeError("the disposable font has no stable v2 document ID")

    gate_started = time.perf_counter_ns()
    baseline = capture_model(document_id)
    _assert_unique_unicode_assignments(baseline, phase="baseline")
    baseline_fingerprint = fingerprint_model(baseline)
    baseline_archive = _serialized_font_archive(font)
    baseline_archive_fingerprint = _native_archive_fingerprint(baseline_archive)
    before_path = _plain_attribute(font, "filepath")
    before_master = _plain_attribute(font, "selectedFontMaster")
    before_master_id = str(_plain_attribute(before_master, "id") or "")
    before_dirty = _reported_dirty_state(host, document_id)

    glyphs = baseline.get("glyphs", {})
    masters = [item for item in baseline.get("masters", []) if isinstance(item, Mapping)]
    instances = [item for item in baseline.get("instances", []) if isinstance(item, Mapping)]
    features = [item for item in baseline.get("features", []) if isinstance(item, Mapping)]
    classes = [item for item in baseline.get("classes", []) if isinstance(item, Mapping)]
    prefixes = [item for item in baseline.get("featurePrefixes", []) if isinstance(item, Mapping)]
    if not isinstance(glyphs, Mapping) or not glyphs or not masters:
        raise ValueError("the staged structural gate requires glyphs and at least one master")
    suffix = uuid4().hex[:8]
    source_glyph_name = str(next(iter(glyphs)))
    source_master_id = str(masters[0].get("id") or "")
    if not source_master_id:
        raise ValueError("the staged structural gate requires a stable master ID")
    glyph_name = _unique_name(
        "mcpStagedGlyph{}".format(suffix), [str(name) for name in glyphs]
    )
    master_id = str(uuid4()).upper()
    master_name = _unique_name(
        "MCP Staged Master {}".format(suffix),
        [str(item.get("name") or "") for item in masters],
    )
    layer_id = str(uuid4()).upper()
    layer_name = "MCP Staged Layer {}".format(suffix)
    instance_name = _unique_name(
        "MCP Staged Instance {}".format(suffix),
        [str(item.get("name") or "") for item in instances],
    )
    feature_name = _unused_feature_tags(baseline, 2)[0]
    revert_feature_name = _unused_feature_tags(baseline, 2)[1]
    class_name = _unique_name(
        "MCP_STAGED_CLASS_{}".format(suffix),
        [str(item.get("name") or "") for item in classes],
    )
    prefix_name = _unique_name(
        "MCP Staged Prefix {}".format(suffix),
        [str(item.get("name") or "") for item in prefixes],
    )
    instance_constructor = "font.instances[0].copy()" if instances else "GSInstance()"
    feature_constructor = "font.features[0].copy()" if features else "GSFeature()"
    class_constructor = "font.classes[0].copy()" if classes else "GSClass()"
    prefix_constructor = (
        "font.featurePrefixes[0].copy()" if prefixes else "GSFeaturePrefix()"
    )

    add_code = "\n".join(
        (
            "source_glyph = font.glyphs[{!r}]".format(source_glyph_name),
            "added_glyph = source_glyph.copy()",
            "added_glyph.name = {!r}".format(glyph_name),
            "added_glyph.unicode = None",
            "font.glyphs.append(added_glyph)",
            "source_master = font.masters[0]",
            "added_master = source_master.copy()",
            "added_master.id = {!r}".format(master_id),
            "added_master.name = {!r}".format(master_name),
            "font.masters.append(added_master)",
            "for candidate_glyph in list(font.glyphs):",
            "    owned_layer = candidate_glyph.layers[{!r}].copy()".format(source_master_id),
            "    owned_layer.layerId = {!r}".format(master_id),
            "    owned_layer.associatedMasterId = {!r}".format(master_id),
            "    candidate_glyph.layers[{!r}] = owned_layer".format(master_id),
            "review_glyph = font.glyphs[{!r}]".format(source_glyph_name),
            "review_layer = review_glyph.layers[{!r}].copy()".format(source_master_id),
            "review_layer.layerId = {!r}".format(layer_id),
            "review_layer.associatedMasterId = {!r}".format(source_master_id),
            "review_layer.name = {!r}".format(layer_name),
            "review_glyph.layers.append(review_layer)",
            "added_instance = {}".format(instance_constructor),
            "added_instance.name = {!r}".format(instance_name),
            "font.instances.append(added_instance)",
            "added_feature = {}".format(feature_constructor),
            "added_feature.name = {!r}".format(feature_name),
            "added_feature.automatic = False",
            "added_feature.code = {!r}".format(
                "sub {0} by {0};".format(source_glyph_name)
            ),
            "font.features.append(added_feature)",
            "added_class = {}".format(class_constructor),
            "added_class.name = {!r}".format(class_name),
            "added_class.automatic = False",
            "added_class.code = {!r}".format(source_glyph_name),
            "font.classes.append(added_class)",
            "added_prefix = {}".format(prefix_constructor),
            "added_prefix.name = {!r}".format(prefix_name),
            "added_prefix.automatic = False",
            "added_prefix.code = 'languagesystem DFLT dflt;'",
            "font.featurePrefixes.append(added_prefix)",
        )
    )
    reorder_code = "\n".join(
        (
            "def move_last_first(collection):",
            "    values = list(collection)",
            "    collection.setter([values[-1]] + values[:-1])",
            "move_last_first(font.masters)",
            "move_last_first(font.instances)",
            "move_last_first(font.features)",
            "move_last_first(font.classes)",
            "move_last_first(font.featurePrefixes)",
        )
    )
    delete_code = "\n".join(
        (
            "def remove_named(collection, target_name):",
            "    for target_index, target in enumerate(list(collection)):",
            "        if str(target.name) == target_name:",
            "            del collection[target_index]",
            "            return",
            "    raise ValueError('missing staged structural target: ' + target_name)",
            "review_glyph = font.glyphs[{!r}]".format(source_glyph_name),
            # Glyphs assigns a fresh native identity when a copied layer is
            # appended. The add preview records that authoritative identity,
            # so the later independent tool call must rediscover the retained
            # entity by its unique semantic name instead of assuming the
            # pre-attachment candidate ID survived.
            "retained_layers = [candidate_layer for candidate_layer in list(review_glyph.layers) if str(candidate_layer.name) != {!r}]".format(
                layer_name
            ),
            "if len(retained_layers) == len(review_glyph.layers):",
            "    raise ValueError('missing staged structural layer: ' + {!r})".format(
                layer_name
            ),
            "ordered_layers = MGOrderedDictionary.alloc().initWithCapacity_(len(retained_layers))",
            "for retained_layer in retained_layers:",
            "    ordered_layers.setObject_forKey_(retained_layer, str(retained_layer.layerId))",
            "review_glyph.setLayers_(ordered_layers)",
            "del font.glyphs[{!r}]".format(glyph_name),
            # Master-layer membership is owned by the master lifecycle.
            # Glyphs removes the associated layer from every glyph when the
            # master is deleted; deleting those layers first is redundant and
            # makes Glyphs recreate them while the master still exists.
            "for target_index, target in enumerate(list(font.masters)):",
            "    if str(target.id) == {!r}:".format(master_id),
            "        del font.masters[target_index]",
            "        break",
            "remove_named(font.instances, {!r})".format(instance_name),
            "remove_named(font.features, {!r})".format(feature_name),
            "remove_named(font.classes, {!r})".format(class_name),
            "remove_named(font.featurePrefixes, {!r})".format(prefix_name),
        )
    )
    revert_code = "\n".join(
        (
            "added_feature = {}".format(feature_constructor),
            "added_feature.name = {!r}".format(revert_feature_name),
            "added_feature.automatic = False",
            "added_feature.code = {!r}".format(
                "sub {0} by {0};".format(source_glyph_name)
            ),
            "font.features.append(added_feature)",
        )
    )

    session = _StagedPythonGateSession(
        application, host, document_id, baseline_fingerprint
    )
    try:
        added = session.preview_and_confirm(
            add_code, reason="Glyphs MCP v2 staged structural add qualification"
        )
        reordered = session.preview_and_confirm(
            reorder_code, reason="Glyphs MCP v2 staged structural order qualification"
        )
        deleted = session.preview_and_confirm(
            delete_code, reason="Glyphs MCP v2 staged structural delete qualification"
        )
        if session.current_fingerprint != baseline_fingerprint:
            observed = dict(capture_model(document_id))
            composition = diff_models(baseline, observed)
            diagnostics = [
                {
                    "path": "/".join(change.path),
                    "before": repr(change.before)[:120],
                    "after": repr(change.after)[:120],
                }
                for change in composition.changes[:20]
            ]
            raise AssertionError(
                "add/reorder/delete composition left {} canonical change(s): {!r}".format(
                    len(composition.changes), diagnostics
                )
            )
        session.rollback(deleted)
        session.rollback(reordered)
        session.rollback(added)
        change_log_target = session.preview_and_confirm(
            revert_code, reason="Glyphs MCP v2 staged structural Change Log qualification"
        )
        session.revert(change_log_target)
    except BaseException:
        cleanup_failures = session.cleanup()
        final = session.fingerprint()
        if cleanup_failures or final != baseline_fingerprint:
            raise RuntimeError(
                "staged structural gate cleanup failed for {} operation(s); final fingerprint {}; failures={!r}".format(
                    len(cleanup_failures), final, cleanup_failures[:3]
                )
            )
        raise

    final_fingerprint = session.fingerprint()
    final_archive = _serialized_font_archive(font)
    final_archive_fingerprint = _native_archive_fingerprint(final_archive)
    archive_comparison = _compare_native_archives(
        baseline_archive,
        final_archive,
        limit=20,
    )
    after_path = _plain_attribute(font, "filepath")
    after_master = _plain_attribute(font, "selectedFontMaster")
    after_master_id = str(_plain_attribute(after_master, "id") or "")
    after_dirty = _reported_dirty_state(host, document_id)
    evidence_store = getattr(host, "_native_replay_evidence", None)
    evidence_count = (
        int(evidence_store.record_count())
        if callable(getattr(evidence_store, "record_count", None))
        else 0
    )
    if final_fingerprint != baseline_fingerprint:
        raise AssertionError("staged structural gate did not restore the canonical baseline")
    if not archive_comparison["equivalent"]:
        raise AssertionError(
            "staged structural gate did not restore the native archive; "
            "mismatches={!r}; truncated={}".format(
                archive_comparison["mismatchLocations"],
                archive_comparison["truncated"],
            )
        )
    if after_path != before_path:
        raise AssertionError("staged structural gate changed the working document path")
    if after_master_id != before_master_id:
        raise AssertionError("staged structural gate changed the active master")
    if before_dirty is not None and after_dirty != before_dirty:
        raise AssertionError("staged structural gate changed the reported dirty state")
    if evidence_count:
        raise AssertionError("staged structural gate retained preview-native evidence")
    return {
        "documentId": document_id,
        "familyName": family_name,
        "baselineFingerprint": baseline_fingerprint,
        "finalFingerprint": final_fingerprint,
        "baselineArchiveFingerprint": baseline_archive_fingerprint,
        "finalArchiveFingerprint": final_archive_fingerprint,
        "qualifiedDomains": [
            "glyph_membership",
            "master_lifecycle",
            "layer_membership",
            "instance_lifecycle",
            "opentype_lifecycle",
            "ordered_collections",
            "python_rollback",
            "change_log_revert",
        ],
        "previewCount": session.preview_count,
        "confirmedTransactionCount": session.confirm_count,
        "rollbackTransactionCount": session.rollback_count,
        "operationIds": session.operation_ids,
        "rollbackOperationIds": session.rollback_operation_ids,
        "exactCanonicalBaselineRestored": True,
        "exactNativeArchiveRestored": True,
        "nativeArchiveBytesUnchanged": baseline_archive == final_archive,
        "workingPathUnchanged": True,
        "activeMasterUnchanged": True,
        "reportedDirtyStateUnchanged": before_dirty is None or after_dirty == before_dirty,
        "auditReceiptsPresent": session.audit_receipts,
        "changeLogCommitsPresent": session.change_log_commits,
        "pendingNativeEvidenceCount": evidence_count,
        "gateDurationMs": (time.perf_counter_ns() - gate_started) / 1_000_000,
    }


__all__ = [
    "DISPOSABLE_FAMILY_PREFIX",
    "verify_copy_and_make_copy",
    "verify_context_kerning",
    "verify_open_edit_tab",
    "verify_schema_v3_structural_kernel",
    "verify_schema_v4_master_lifecycle",
    "verify_schema_v5_layer_lifecycle",
    "verify_staged_python_structural_replay",
]
