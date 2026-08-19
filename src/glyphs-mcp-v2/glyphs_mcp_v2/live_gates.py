"""Explicit disposable-font gates for this milestone's Glyphs 4 live run."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .adapters.document import (
    _save_font_copy,
    _serialized_font_fingerprint,
    native_font_to_model,
)
from .semantic import fingerprint_model


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

    def __init__(self, application: Any, host: Any, document_id: str) -> None:
        self.application = application
        self.host = host
        self.document_id = document_id
        self.active: list[str] = []
        self.successful: list[str] = []
        self.refusals: list[str] = []
        self.single_transactions = True
        self.audit_receipts = True
        self.change_log_commits = True

    def model(self) -> Mapping[str, Any]:
        return dict(self.host.capture_model(self.document_id))

    def fingerprint(self) -> str:
        return fingerprint_model(self.model())

    def invoke(self, tool: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        response = self.application.invoke(tool, arguments)
        return response.to_dict() if hasattr(response, "to_dict") else dict(response)

    def _success(self, tool: str, response: Mapping[str, Any]) -> Mapping[str, Any]:
        if not response.get("ok"):
            error = response.get("error") or {}
            raise AssertionError(
                "{} failed: {} ({})".format(
                    tool,
                    error.get("message") or response.get("summary") or "unknown error",
                    error.get("code") or "unknown",
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
        return data

    def apply(self, tool: str, updates: Sequence[Mapping[str, Any]]) -> str:
        response = self.invoke(
            tool,
            {
                "documentId": self.document_id,
                "expectedDocumentFingerprint": self.fingerprint(),
                "updates": [dict(item) for item in updates],
                "reason": "Glyphs MCP v2 schema-v3 live qualification",
            },
        )
        data = self._success(tool, response)
        operation_id = str(data.get("operationId") or response.get("operationId") or "")
        if not operation_id:
            raise AssertionError("{} returned no canonical operation ID".format(tool))
        self._require_change_log_commit(operation_id, tool)
        self.active.append(operation_id)
        self.successful.append(operation_id)
        return operation_id

    def revert(self, operation_id: str) -> None:
        response = self.invoke(
            "revert_change",
            {
                "documentId": self.document_id,
                "operationId": operation_id,
                "expectedDocumentFingerprint": self.fingerprint(),
            },
        )
        data = self._success("revert_change", response)
        reverted_id = str(data.get("operationId") or response.get("operationId") or "")
        if not reverted_id:
            raise AssertionError("revert_change returned no canonical operation ID")
        self._require_change_log_commit(reverted_id, "revert_change")
        self.active.remove(operation_id)
        self.successful.append(reverted_id)

    def _require_change_log_commit(self, operation_id: str, tool: str) -> None:
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
        before = self.fingerprint()
        response = self.invoke(
            tool,
            {
                "documentId": self.document_id,
                "expectedDocumentFingerprint": "sha256:stale" if stale else before,
                "updates": [dict(item) for item in updates],
                "reason": "Glyphs MCP v2 schema-v3 atomic refusal gate",
            },
        )
        code = str((response.get("error") or {}).get("code") or "")
        if response.get("ok") or code != expected_code:
            raise AssertionError("expected {} refusal, got {}".format(expected_code, code))
        if self.fingerprint() != before:
            raise AssertionError("a refused live-gate request changed the document")
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
                        "expectedDocumentFingerprint": self.fingerprint(),
                    },
                )
                if response.get("ok"):
                    self.active.remove(operation_id)
                else:
                    failures.append(operation_id)
            except Exception:
                failures.append(operation_id)
        return failures


def verify_copy_and_make_copy(font: Any, output_path: str) -> Mapping[str, Any]:
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

    before_model = native_font_to_model(font)
    before_fingerprint = fingerprint_model(before_model)
    before_path = getattr(font, "filepath", None)
    document = getattr(font, "parent", None)
    before_dirty = getattr(document, "isDocumentEdited", None) if document is not None else None
    before_dirty = before_dirty() if callable(before_dirty) else before_dirty

    clone = font.copy()
    if clone is None or clone is font:
        raise AssertionError("GSFont.copy() did not return a detached clone")
    clone_fingerprint = fingerprint_model(native_font_to_model(clone))
    if clone_fingerprint != before_fingerprint:
        raise AssertionError("GSFont.copy() changed the canonical document model")
    if _serialized_font_fingerprint(clone) != _serialized_font_fingerprint(font):
        raise AssertionError("GSFont.copy() changed the serialized document archive")

    _save_font_copy(font, destination)
    os.chmod(destination, 0o600)

    after_path = getattr(font, "filepath", None)
    after_dirty = getattr(document, "isDocumentEdited", None) if document is not None else None
    after_dirty = after_dirty() if callable(after_dirty) else after_dirty
    after_fingerprint = fingerprint_model(native_font_to_model(font))
    if after_path != before_path or after_dirty != before_dirty:
        raise AssertionError("GSFont.save(makeCopy=True) changed the working path or dirty state")
    if after_fingerprint != before_fingerprint:
        raise AssertionError("the live working document changed during the copy gate")
    return {
        "familyName": family_name,
        "documentFingerprint": before_fingerprint,
        "copyFingerprint": clone_fingerprint,
        "outputPath": str(destination),
        "outputMode": "0600",
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
    capture_model = getattr(host, "capture_model", None)
    if not callable(document_id_for_font) or not callable(capture_model):
        raise RuntimeError("the active host does not expose the structural live-gate boundary")
    document_id = str(document_id_for_font(font) or "")
    if not document_id:
        raise RuntimeError("the disposable font has no stable v2 document ID")

    baseline = dict(capture_model(document_id))
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
    session = _StructuralGateSession(application, host, document_id)

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


__all__ = [
    "DISPOSABLE_FAMILY_PREFIX",
    "verify_copy_and_make_copy",
    "verify_schema_v3_structural_kernel",
]
