"""Disposable Glyphs 4 qualification gates for the v2 hard-reset contract.

These helpers are not MCP tools.  They exercise only the public generic
surface and prove that a disposable live document returns to its exact
canonical baseline without an implicit save.
"""

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
    reader = getattr(host, "list_documents", None)
    if not callable(reader):
        return None
    for document in reader():
        if str(getattr(document, "document_id", "") or "") == document_id:
            return getattr(document, "has_unsaved_changes", None)
    return None


def _assert_disposable(font: Any) -> str:
    family_name = str(getattr(font, "familyName", "") or "")
    if not family_name.startswith(DISPOSABLE_FAMILY_PREFIX):
        raise ValueError(
            "live v2 gates require a disposable font whose family name starts "
            "with {!r}".format(DISPOSABLE_FAMILY_PREFIX)
        )
    return family_name


def _assert_unique_unicode_assignments(
    model: Mapping[str, Any], *, phase: str
) -> None:
    """Refuse fixtures that could summon Glyphs' modal Unicode repair UI."""

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
            codepoint = str(value or "").strip().upper().removeprefix("U+")
            if codepoint:
                owners.setdefault(codepoint, []).append(glyph_name)
    duplicates = [
        (codepoint, names)
        for codepoint, names in sorted(owners.items())
        if len(set(names)) > 1
    ]
    if duplicates:
        codepoint, names = duplicates[0]
        raise ValueError(
            "{} live-gate model has duplicate Unicode U+{} in glyphs {}; "
            "qualification refuses modal repair workflows".format(
                phase, codepoint, ", ".join(dict.fromkeys(names))
            )
        )


def _resolve_live_runtime(application: Any, host: Any) -> tuple[Any, Any]:
    if application is None or host is None:
        from .runtime import active_application, active_host

        application = application or active_application()
        host = host or active_host()
    if application is None or host is None:
        raise RuntimeError(
            "the Glyphs MCP v2 runtime must be active before running the live gate"
        )
    return application, host


def _capture(host: Any, document_id: str) -> Mapping[str, Any]:
    capture = getattr(host, "capture_snapshot", None)
    if not callable(capture):
        capture = getattr(host, "capture_model", None)
    if not callable(capture):
        raise RuntimeError("the live-gate host exposes no canonical capture")
    return capture(document_id)


def _document_id(font: Any, host: Any) -> str:
    resolver = getattr(host, "document_id_for_font", None)
    if not callable(resolver):
        raise RuntimeError("the live-gate host exposes no stable document identity")
    document_id = str(resolver(font) or "")
    if not document_id:
        raise RuntimeError("the disposable font has no stable v2 document ID")
    return document_id


def _plain_response(value: Any) -> Mapping[str, Any]:
    return value.to_dict() if hasattr(value, "to_dict") else dict(value)


class _GenericGateSession:
    """Drive immutable previews, exact applies, and conflict-aware reverts."""

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
        self.operation_ids: list[str] = []
        self.preview_count = 0
        self.transaction_count = 0
        self.refusal_count = 0
        self.audit_receipts = True
        self.history_entries = True

    def invoke(self, tool: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        return _plain_response(self.application.invoke(tool, arguments))

    @staticmethod
    def _require_ok(tool: str, response: Mapping[str, Any]) -> Mapping[str, Any]:
        if not response.get("ok"):
            error = response.get("error") or {}
            raise AssertionError(
                "{} failed: {} ({})".format(
                    tool,
                    error.get("message") or response.get("summary") or "unknown error",
                    error.get("code") or "unknown",
                )
            )
        return dict(response.get("data") or {})

    def _require_history(self, operation_id: str, tool: str) -> None:
        history = getattr(self.application, "history", None)
        getter = getattr(history, "get_commit", None)
        commit = getter(operation_id) if callable(getter) else None
        matches = bool(
            commit is not None
            and commit.document_id == self.document_id
            and commit.tool == tool
            and commit.changed
        )
        self.history_entries = self.history_entries and matches
        if not matches:
            raise AssertionError(
                "{} was not recorded as a changed history entry".format(tool)
            )

    def apply(
        self,
        operations: Sequence[Mapping[str, Any]],
        *,
        constraints: Sequence[Mapping[str, Any]] = (),
        reason: str,
    ) -> str:
        preview = self.invoke(
            "preview_change",
            {
                "documentId": self.document_id,
                "expectedDocumentFingerprint": self.current_fingerprint,
                "operations": [dict(item) for item in operations],
                "constraints": [dict(item) for item in constraints],
            },
        )
        preview_data = self._require_ok("preview_change", preview)
        if not preview_data.get("applicable") or not preview_data.get("previewId"):
            raise AssertionError("preview_change returned an inapplicable preview")
        if fingerprint_model(_capture(self.host, self.document_id)) != self.current_fingerprint:
            raise AssertionError("preview_change mutated the live document")
        self.preview_count += 1

        applied = self.invoke(
            "apply_change",
            {
                "documentId": self.document_id,
                "previewId": preview_data["previewId"],
                "expectedDocumentFingerprint": self.current_fingerprint,
                "reason": reason,
            },
        )
        data = self._require_ok("apply_change", applied)
        if data.get("transactionCount") != 1:
            raise AssertionError("apply_change did not report one transaction")
        if data.get("fontSaved") is not False:
            raise AssertionError("apply_change did not report fontSaved=false")
        if str(data.get("beforeFingerprint") or "") != self.current_fingerprint:
            raise AssertionError("apply_change did not consume the preview baseline")
        after = str(data.get("afterFingerprint") or "")
        if not after or fingerprint_model(_capture(self.host, self.document_id)) != after:
            raise AssertionError("apply_change read-back fingerprint is not live")
        operation_id = str(data.get("operationId") or "")
        if not operation_id:
            raise AssertionError("apply_change returned no operation ID")
        self.audit_receipts = self.audit_receipts and bool(applied.get("auditReceipt"))
        if not self.audit_receipts:
            raise AssertionError("apply_change returned no audit receipt")
        self._require_history(operation_id, "apply_change")
        self.current_fingerprint = after
        self.active.append(operation_id)
        self.operation_ids.append(operation_id)
        self.transaction_count += 1
        return operation_id

    def revert(self, operation_id: str) -> str:
        response = self.invoke(
            "revert_change",
            {
                "documentId": self.document_id,
                "operationId": operation_id,
                "expectedDocumentFingerprint": self.current_fingerprint,
            },
        )
        data = self._require_ok("revert_change", response)
        if data.get("transactionCount") != 1:
            raise AssertionError("revert_change did not report one transaction")
        if str(data.get("beforeFingerprint") or "") != self.current_fingerprint:
            raise AssertionError("revert_change used a stale baseline")
        after = str(data.get("afterFingerprint") or "")
        if not after or fingerprint_model(_capture(self.host, self.document_id)) != after:
            raise AssertionError("revert_change read-back fingerprint is not live")
        revert_id = str(data.get("operationId") or "")
        if not revert_id:
            raise AssertionError("revert_change returned no operation ID")
        self.audit_receipts = self.audit_receipts and bool(response.get("auditReceipt"))
        self._require_history(revert_id, "revert_change")
        self.current_fingerprint = after
        self.active.remove(operation_id)
        self.operation_ids.append(revert_id)
        self.transaction_count += 1
        return revert_id

    def round_trip(
        self, operations: Sequence[Mapping[str, Any]], *, reason: str
    ) -> None:
        self.revert(self.apply(operations, reason=reason))

    def refuse_stale(self, operations: Sequence[Mapping[str, Any]]) -> None:
        response = self.invoke(
            "preview_change",
            {
                "documentId": self.document_id,
                "expectedDocumentFingerprint": "sha256:" + "0" * 64,
                "operations": [dict(item) for item in operations],
                "constraints": [],
            },
        )
        if response.get("ok") or (response.get("error") or {}).get("code") != "stale_document":
            raise AssertionError("preview_change did not atomically refuse stale input")
        self.refusal_count += 1

    def cleanup(self) -> list[str]:
        failures: list[str] = []
        for operation_id in reversed(tuple(self.active)):
            try:
                self.revert(operation_id)
            except Exception:
                failures.append(operation_id)
        return failures


def verify_open_document_view(
    font: Any,
    glyph_names: Sequence[str] = (),
    *,
    application: Any = None,
    host: Any = None,
) -> Mapping[str, Any]:
    """Open one public document view and prove the document did not change."""

    family_name = _assert_disposable(font)
    application, host = _resolve_live_runtime(application, host)
    document_id = _document_id(font, host)
    baseline = _capture(host, document_id)
    baseline_fingerprint = fingerprint_model(baseline)
    glyphs = baseline.get("glyphs", {})
    available = list(glyphs) if isinstance(glyphs, Mapping) else []
    requested = tuple(glyph_names) if glyph_names else tuple(available[:2])
    if not requested or any(name not in available for name in requested):
        raise ValueError("the document-view gate requires exact existing glyph names")
    master = _plain_attribute(font, "selectedFontMaster")
    master_id = str(_plain_attribute(master, "id") or "")
    arguments: dict[str, Any] = {
        "documentId": document_id,
        "glyphNames": list(requested),
    }
    if master_id:
        arguments["masterId"] = master_id
    response = _plain_response(application.invoke("open_document_view", arguments))
    data = _GenericGateSession._require_ok("open_document_view", response)
    after_fingerprint = fingerprint_model(_capture(host, document_id))
    if after_fingerprint != baseline_fingerprint:
        raise AssertionError("open_document_view changed the canonical document")
    return {
        "documentId": document_id,
        "familyName": family_name,
        "glyphNames": list(requested),
        "documentFingerprint": baseline_fingerprint,
        "openedView": bool(data.get("openedView") or data.get("openedTab")),
        "documentUnchanged": True,
    }


def verify_copy_and_make_copy(
    font: Any,
    output_path: str,
    *,
    application: Any = None,
    host: Any = None,
) -> Mapping[str, Any]:
    """Verify detached clone/archive invariants without saving the document."""

    family_name = _assert_disposable(font)
    destination = Path(output_path)
    if not destination.is_absolute() or destination.exists():
        raise ValueError("the live-gate output must be a new explicit absolute path")
    if not destination.parent.is_dir():
        raise ValueError("the live-gate output parent must already exist")
    _application, host = _resolve_live_runtime(application, host)
    document_id = _document_id(font, host)
    capture_detached = getattr(host, "_capture_detached_model", None)
    reconcile_detached = getattr(host, "_reconcile_detached_clone", None)
    instance_ids_for_font = getattr(host, "_instance_ids_for_font", None)
    if not all(
        callable(value)
        for value in (capture_detached, reconcile_detached, instance_ids_for_font)
    ):
        raise RuntimeError("the host exposes no detached-copy proof boundary")
    before = _capture(host, document_id)
    before_fingerprint = fingerprint_model(before)
    before_path = _plain_attribute(font, "filepath")
    before_dirty = _reported_dirty_state(host, document_id)
    clone = font.copy()
    if clone is None or clone is font:
        raise AssertionError("GSFont.copy() did not return a detached clone")
    instance_ids = instance_ids_for_font(document_id, font)
    observed = capture_detached(
        clone,
        before,
        instance_ids=instance_ids,
        document_path=before_path,
    )
    normalized, projection = reconcile_detached(
        clone,
        before,
        observed,
        document_id=document_id,
        instance_ids=instance_ids,
        observed_is_complete=True,
    )
    clone_fingerprint = fingerprint_model(normalized)
    if clone_fingerprint != before_fingerprint:
        residual = diff_models(before, normalized)
        raise AssertionError(
            "GSFont.copy() changed {} canonical value(s)".format(
                len(residual.changes)
            )
        )
    source_archive = _serialized_font_archive(font)
    clone_archive = _serialized_font_archive(clone)
    comparison = _compare_native_archives(source_archive, clone_archive, limit=20)
    covered_count = 0
    if not comparison["equivalent"]:
        artifact_paths = tuple(
            change.path
            for change in getattr(getattr(projection, "artifacts", None), "changes", ())
        )
        coverage = _classify_native_clone_archive_mismatches(
            comparison["mismatchLocations"],
            artifact_paths=artifact_paths,
            direct_tree=_decoded_native_archive_tree(source_archive),
            replay_tree=_decoded_native_archive_tree(clone_archive),
        )
        covered_count = int(coverage["coveredCount"])
        if comparison["truncated"] or not coverage["complete"]:
            raise AssertionError("GSFont.copy() changed unmodeled serialized state")
    _save_font_copy(font, destination)
    os.chmod(destination, 0o600)
    after_dirty = _reported_dirty_state(host, document_id)
    if _plain_attribute(font, "filepath") != before_path:
        raise AssertionError("makeCopy changed the working document path")
    if before_dirty is not None and after_dirty != before_dirty:
        raise AssertionError("makeCopy changed the reported dirty state")
    if fingerprint_model(_capture(host, document_id)) != before_fingerprint:
        raise AssertionError("makeCopy changed the live document")
    return {
        "familyName": family_name,
        "documentFingerprint": before_fingerprint,
        "copyFingerprint": clone_fingerprint,
        "outputPath": str(destination),
        "outputMode": "0600",
        "nativeArchiveCoveredMismatchCount": covered_count,
        "workingPathUnchanged": True,
        "dirtyStateUnchanged": True,
    }


def _generic_gate_context(
    font: Any, application: Any, host: Any
) -> tuple[str, Any, Any, str, Mapping[str, Any], _GenericGateSession]:
    family_name = _assert_disposable(font)
    application, host = _resolve_live_runtime(application, host)
    document_id = _document_id(font, host)
    baseline = _capture(host, document_id)
    _assert_unique_unicode_assignments(baseline, phase="baseline")
    baseline_fingerprint = fingerprint_model(baseline)
    return (
        family_name,
        application,
        host,
        document_id,
        baseline,
        _GenericGateSession(
            application, host, document_id, baseline_fingerprint
        ),
    )


def _finish_generic_gate(
    *,
    family_name: str,
    host: Any,
    document_id: str,
    baseline: Mapping[str, Any],
    session: _GenericGateSession,
    domains: Sequence[str],
    gate_started: int,
) -> Mapping[str, Any]:
    final = _capture(host, document_id)
    baseline_fingerprint = fingerprint_model(baseline)
    final_fingerprint = fingerprint_model(final)
    if final_fingerprint != baseline_fingerprint:
        raise AssertionError("generic live gate did not restore the canonical baseline")
    return {
        "documentId": document_id,
        "familyName": family_name,
        "baselineFingerprint": baseline_fingerprint,
        "finalFingerprint": final_fingerprint,
        "qualifiedDomains": list(domains),
        "previewCount": session.preview_count,
        "successfulTransactionCount": session.transaction_count,
        "refusalCount": session.refusal_count,
        "operationIds": list(session.operation_ids),
        "exactBaselineRestored": True,
        "singleTransactionResponses": True,
        "auditReceiptsPresent": session.audit_receipts,
        "historyEntriesPresent": session.history_entries,
        "fontSaved": False,
        "gateDurationMs": (time.perf_counter_ns() - gate_started) / 1_000_000,
    }


def verify_generic_change_lifecycle(
    font: Any,
    *,
    application: Any = None,
    host: Any = None,
) -> Mapping[str, Any]:
    """Round-trip generic scalar, collection, master, and layer mechanics."""

    started = time.perf_counter_ns()
    family, application, host, document_id, baseline, session = _generic_gate_context(
        font, application, host
    )
    glyphs = baseline.get("glyphs", {})
    masters = [item for item in baseline.get("masters", ()) if isinstance(item, Mapping)]
    if not isinstance(glyphs, Mapping) or not glyphs or not masters:
        raise ValueError("the generic gate requires a glyph and master")
    glyph_name = str(next(iter(glyphs)))
    glyph = glyphs[glyph_name]
    glyph_id = str(glyph.get("name") or glyph_name)
    master_id = str(masters[0].get("id") or "")
    layers = glyph.get("layers", ()) if isinstance(glyph, Mapping) else ()
    source_layer = next(
        (item for item in layers if isinstance(item, Mapping) and item.get("id")),
        None,
    )
    if source_layer is None or not master_id:
        raise ValueError("the generic gate requires stable master and layer IDs")
    new_master_id = str(uuid4()).upper()
    new_layer_id = str(uuid4()).upper()
    feature_id = "mcp{}".format(uuid4().hex[:4])
    scalar = [
        {
            "op": "set",
            "target": {"entity": "glyph", "ids": [glyph_id]},
            "field": "export",
            "value": not bool(glyph.get("export", True)),
        }
    ]
    feature = [
        {
            "op": "insert",
            "target": {"entity": "document", "ids": ["document"]},
            "field": "features",
            "value": {
                "id": feature_id,
                "name": feature_id,
                "code": "sub {} by {};".format(glyph_name, glyph_name),
                "automatic": False,
                "disabled": False,
            },
        }
    ]
    master = [
        {
            "op": "duplicate",
            "target": {"entity": "master", "ids": [master_id]},
            "newId": new_master_id,
            "overrides": {"name": "MCP Generic Gate Master"},
            "index": min(1, len(masters)),
        }
    ]
    layer = [
        {
            "op": "duplicate",
            "target": {
                "entity": "layer",
                "ids": [str(source_layer["id"])],
                "parent": {"glyphName": glyph_name},
            },
            "newId": new_layer_id,
            "overrides": {
                "name": "MCP Generic Gate Layer",
                "masterId": str(source_layer.get("masterId") or master_id),
            },
        }
    ]
    try:
        session.round_trip(scalar, reason="generic scalar qualification")
        session.round_trip(feature, reason="generic OpenType collection qualification")
        session.round_trip(master, reason="generic owned master qualification")
        session.round_trip(layer, reason="generic owned layer qualification")
        session.refuse_stale(scalar)
    except BaseException:
        failures = session.cleanup()
        if failures or fingerprint_model(_capture(host, document_id)) != fingerprint_model(baseline):
            raise RuntimeError(
                "generic gate cleanup failed for {} operation(s)".format(len(failures))
            )
        raise
    return _finish_generic_gate(
        family_name=family,
        host=host,
        document_id=document_id,
        baseline=baseline,
        session=session,
        domains=("scalar_fields", "opentype_collections", "master_ownership", "layer_ownership", "atomic_refusal"),
        gate_started=started,
    )


def verify_generic_kerning_lifecycle(
    font: Any,
    *,
    application: Any = None,
    host: Any = None,
) -> Mapping[str, Any]:
    """Insert and revert one exact context entry without touching pair domains."""

    started = time.perf_counter_ns()
    family, application, host, document_id, baseline, session = _generic_gate_context(
        font, application, host
    )
    masters = [item for item in baseline.get("masters", ()) if isinstance(item, Mapping)]
    if not masters or not masters[0].get("id"):
        raise ValueError("the kerning gate requires one stable master ID")
    key = "MCP * Generic Context {}".format(uuid4().hex[:6])
    operation = [
        {
            "op": "insert",
            "target": {"entity": "document", "ids": ["document"]},
            "field": "kerning.context",
            "newId": key,
            "value": {str(masters[0]["id"]): -40},
        }
    ]
    try:
        session.round_trip(operation, reason="generic contextual kerning qualification")
        session.refuse_stale(operation)
    except BaseException:
        failures = session.cleanup()
        if failures or fingerprint_model(_capture(host, document_id)) != fingerprint_model(baseline):
            raise RuntimeError("generic kerning gate cleanup failed")
        raise
    return _finish_generic_gate(
        family_name=family,
        host=host,
        document_id=document_id,
        baseline=baseline,
        session=session,
        domains=("context_storage", "pair_domain_preservation", "atomic_refusal"),
        gate_started=started,
    )


def verify_staged_python_preview_lifecycle(
    font: Any,
    *,
    application: Any = None,
    host: Any = None,
) -> Mapping[str, Any]:
    """Apply one detached Python patch through apply_change, then revert it."""

    started = time.perf_counter_ns()
    family, application, host, document_id, baseline, session = _generic_gate_context(
        font, application, host
    )
    preview = session.invoke(
        "execute_python",
        {
            "mode": "staged_document",
            "code": "font.note = 'Glyphs MCP staged qualification'",
            "reason": "qualify the permanent staged Python fallback",
            "documentId": document_id,
            "expectedDocumentFingerprint": session.current_fingerprint,
        },
    )
    preview_data = session._require_ok("execute_python", preview)
    if not preview_data.get("previewId") or fingerprint_model(_capture(host, document_id)) != session.current_fingerprint:
        raise AssertionError("staged Python did not return an immutable non-live preview")
    session.preview_count += 1
    applied = session.invoke(
        "apply_change",
        {
            "documentId": document_id,
            "previewId": preview_data["previewId"],
            "expectedDocumentFingerprint": session.current_fingerprint,
            "reason": "apply the exact staged Python patch",
        },
    )
    data = session._require_ok("apply_change", applied)
    operation_id = str(data.get("operationId") or "")
    if data.get("transactionCount") != 1 or not operation_id:
        raise AssertionError("staged Python apply did not use one generic transaction")
    session.audit_receipts = session.audit_receipts and bool(applied.get("auditReceipt"))
    session._require_history(operation_id, "apply_change")
    session.current_fingerprint = str(data.get("afterFingerprint") or "")
    session.active.append(operation_id)
    session.operation_ids.append(operation_id)
    session.transaction_count += 1
    try:
        session.revert(operation_id)
    except BaseException:
        session.cleanup()
        raise
    return _finish_generic_gate(
        family_name=family,
        host=host,
        document_id=document_id,
        baseline=baseline,
        session=session,
        domains=("staged_python", "immutable_preview", "generic_apply", "history_revert"),
        gate_started=started,
    )


__all__ = [
    "DISPOSABLE_FAMILY_PREFIX",
    "verify_copy_and_make_copy",
    "verify_generic_change_lifecycle",
    "verify_generic_kerning_lifecycle",
    "verify_open_document_view",
    "verify_staged_python_preview_lifecycle",
]
