"""Transport-neutral Glyphs MCP 2.0 application services."""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from .audit import AuditLog
from .canonical_tree import (
    CANONICAL_MODEL_SCHEMA_VERSION,
    REVERSIBILITY_COVERAGE,
    CanonicalFontTree,
    MemoryObjectStore,
)
from .catalog import TOOL_CATALOG
from .change_history import ActionCommit, ChangeHistory
from .change_trace import ActionTraceCoordinator
from .contracts import API_MAJOR, API_VERSION, OperationMetadata, ToolResponse, ToolWarning
from .exporting import ExportPublicationError, destination_matches
from .operations import OperationRecord, OperationStore
from .mutation import (
    CanonicalTargetMismatchError,
    MutationPlanner,
    unsupported_change_diagnostics,
    writable_subset,
)
from .pagination import CursorError, paginate
from .ports import HostAccessError, ReadOnlyHost
from .python_execution import PythonExecutionRequest, PythonExecutionService
from .semantic import ChangeSet, diff_models, fingerprint_model, revert_change_set_onto
from .transactions import StaleDocumentError, TransactionKernel, TransactionVerificationError
from .versions import SERVER_NAME, SERVER_VERSION
from .workflows import (
    build_opentype_updates,
    list_glyphs as model_list_glyphs,
    list_instances as model_list_instances,
    list_kerning_pairs as model_list_kerning_pairs,
    review_anchor_consistency as model_review_anchor_consistency,
    review_anchor_updates as build_anchor_updates,
    review_compatibility_updates as build_compatibility_updates,
    review_export as model_review_export,
    review_glyph_updates as build_glyph_updates,
    review_kerning_coverage,
    review_kerning_updates as build_kerning_updates,
    review_master_compatibility as model_review_master_compatibility,
    review_metrics_inheritance as model_review_metrics_inheritance,
    review_metrics_updates as build_metrics_updates,
    simulate_spacing,
)


REVIEW_TTL_SECONDS = 15 * 60
RESULT_TTL_SECONDS = 60 * 60


def _value(arguments: Mapping[str, Any], snake: str, camel: Optional[str] = None, default: Any = None) -> Any:
    if snake in arguments:
        return arguments[snake]
    if camel and camel in arguments:
        return arguments[camel]
    return default


def _iso_timestamp(value: float) -> str:
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _public_payload(value: Any) -> Any:
    if isinstance(value, ChangeSet):
        return {
            "beforeFingerprint": value.before_fingerprint,
            "afterFingerprint": value.after_fingerprint,
            "changeCount": len(value.changes),
            "supported": value.supported,
        }
    if isinstance(value, PythonExecutionRequest):
        stored = value.to_stored_dict()
        stored.pop("code", None)
        return stored
    if isinstance(value, Mapping):
        return {
            str(key): _public_payload(item)
            for key, item in value.items()
            if str(key) not in {"code", "source", "inverse"}
        }
    if isinstance(value, (list, tuple)):
        return [_public_payload(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _change_commit_summary(commit: ActionCommit) -> dict[str, Any]:
    glyphs = commit.changed_glyphs
    roots: list[str] = []
    for change in commit.change_set.changes:
        if change.path and change.path[0] not in roots:
            roots.append(change.path[0])
    return {
        "operationId": commit.operation_id,
        # External working-tree observations are internal graph nodes, not
        # public operations. Never leak their private change_* identifiers as
        # though a caller could inspect or revert them.
        "parentOperationId": (
            commit.parent_id
            if str(commit.parent_id or "").startswith(("op_", "review_", "exec_"))
            else None
        ),
        "tool": commit.tool,
        "effect": commit.effect,
        "status": commit.status,
        "createdAt": _iso_timestamp(commit.created_at),
        "reason": commit.reason,
        "changed": commit.changed,
        "changeCount": len(commit.change_set.changes),
        "changedRoots": roots,
        "changedGlyphCount": len(glyphs),
        "changedGlyphsPreview": list(glyphs[:20]),
        "changedGlyphsTruncated": len(glyphs) > 20,
        "beforeFingerprint": commit.change_set.before_fingerprint,
        "afterFingerprint": commit.change_set.after_fingerprint,
    }


class GlyphsMCPApplication:
    def __init__(
        self,
        host: ReadOnlyHost,
        *,
        operations: Optional[OperationStore] = None,
        audit: Optional[AuditLog] = None,
        history: Optional[ChangeHistory] = None,
    ) -> None:
        self._host = host
        self._operations = operations or OperationStore()
        self._reviews = OperationStore()
        self._checkpoints = OperationStore(max_records=512)
        self._audit = audit or AuditLog()
        self.history = history or ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        self._trace = ActionTraceCoordinator(self.history)
        self._transactions = (
            TransactionKernel(host, observer=self._trace)
            if hasattr(host, "capture_model")
            else None
        )
        self._mutation_planner = MutationPlanner(host) if self._transactions is not None else None
        self._python = (
            PythonExecutionService(
                host=host,
                transactions=self._transactions,
                reviews=self._reviews,
                checkpoints=self._checkpoints,
                audit=self._audit,
                operations=self._operations,
                trace=self._trace,
            )
            if self._transactions is not None
            and hasattr(host, "preview_python")
            and hasattr(host, "run_live_python")
            else None
        )
        self._handlers: Dict[str, Callable[[Mapping[str, Any]], ToolResponse]] = {
            name: getattr(self, definition.handler_name)
            for name, definition in TOOL_CATALOG.items()
            if callable(getattr(self, definition.handler_name, None))
        }

    def invoke(
        self,
        handler_name: str,
        arguments: Optional[Mapping[str, Any]] = None,
    ) -> ToolResponse:
        values = dict(arguments or {})
        definition = TOOL_CATALOG.get(handler_name)
        scope = self._trace.start_action(
            handler_name or "unknown",
            definition.effect if definition is not None else "read",
            values,
        )
        response = self._invoke_untraced(handler_name, values)
        if (
            definition is not None
            and definition.effect == "edit"
            and response.audit_receipt is None
        ):
            # Edit calls are part of the durable action ledger even when
            # validation or conflict detection refuses them before mutation.
            # Handlers that already emitted a richer receipt remain untouched.
            receipt = self._audit.record(
                tool=handler_name,
                effect="edit",
                status=response.status,
                document_id=scope.document_id,
                details={
                    "operationId": response.metadata.operation_id,
                    "errorCode": response.error.code if response.error is not None else None,
                    "mutated": bool(response.ok),
                },
            )
            response = replace(response, audit_receipt=receipt.to_dict())
        if (
            self._trace.needs_initial_observation(scope)
            and self.history.head_tree_hash(scope.document_id or "") is None
        ):
            capture = getattr(self._host, "capture_model", None)
            if callable(capture):
                try:
                    self._trace.observe_model(
                        scope.document_id or "",
                        copy.deepcopy(dict(capture(scope.document_id or ""))),
                    )
                except Exception:
                    pass
        self._trace.finish_action(scope, response)
        return response

    def _invoke_untraced(
        self,
        handler_name: str,
        arguments: Optional[Mapping[str, Any]] = None,
    ) -> ToolResponse:
        definition = TOOL_CATALOG.get(handler_name)
        handler = self._handlers.get(handler_name)
        if definition is None or handler is None:
            return ToolResponse.failure(
                tool=handler_name or "unknown",
                effect=definition.effect if definition is not None else "read",
                summary="Unknown Glyphs MCP 2.0 operation.",
                code="unknown_tool",
                message="The requested operation is not part of this runtime.",
                recoverable=False,
            )
        try:
            return handler(dict(arguments or {}))
        except CursorError as exc:
            return ToolResponse.failure(
                tool=handler_name,
                effect=definition.effect,
                summary="The result cursor is invalid or stale.",
                code="invalid_cursor",
                message=str(exc),
            )
        except HostAccessError as exc:
            return ToolResponse.failure(
                tool=handler_name,
                effect=definition.effect,
                summary="Glyphs host state is temporarily unavailable.",
                code="host_unavailable",
                message=str(exc) or "Glyphs host state is unavailable.",
            )
        except (ValueError, TypeError) as exc:
            return ToolResponse.failure(
                tool=handler_name,
                effect=definition.effect,
                summary="The request is invalid.",
                code="invalid_request",
                message=str(exc),
            )
        except Exception as exc:
            return ToolResponse.failure(
                tool=handler_name,
                effect=definition.effect,
                summary="The operation failed safely.",
                code="internal_error",
                message="The operation failed before returning verified state.",
                details={"exceptionType": type(exc).__name__},
            )

    def _document_model(self, document_id: str) -> dict[str, Any]:
        if not document_id:
            raise ValueError("documentId is required")
        capture = getattr(self._host, "capture_model", None)
        if not callable(capture):
            raise HostAccessError("This host adapter does not expose document snapshots.")
        model = copy.deepcopy(dict(capture(document_id)))
        self._trace.observe_model(document_id, model)
        return model

    def _audited_edit_failure(
        self,
        *,
        tool: str,
        document_id: str,
        summary: str,
        code: str,
        message: str,
        metadata: Optional[OperationMetadata] = None,
        audit_details: Optional[Mapping[str, Any]] = None,
        error_details: Optional[Mapping[str, Any]] = None,
        data: Optional[Mapping[str, Any]] = None,
    ) -> ToolResponse:
        resolved_metadata = metadata or OperationMetadata.create()
        receipt = self._audit.record(
            tool=tool,
            effect="edit",
            status="error",
            document_id=document_id,
            details={
                "operationId": resolved_metadata.operation_id,
                "errorCode": code,
                **dict(audit_details or {}),
            },
        )
        return ToolResponse.failure(
            tool=tool,
            effect="edit",
            summary=summary,
            code=code,
            message=message,
            details=error_details,
            data=data,
            metadata=resolved_metadata,
            audit_receipt=receipt.to_dict(),
        )

    def _page_items(
        self,
        *,
        kind: str,
        items: Sequence[Mapping[str, Any]],
        item_key: str,
        source_fingerprint: str,
        metadata: Optional[Mapping[str, Any]] = None,
        page_size: int = 100,
    ) -> tuple[OperationRecord, dict[str, Any], Mapping[str, Any]]:
        values = [copy.deepcopy(dict(item)) for item in items]
        operation = self._operations.create(
            kind=kind,
            ttl_seconds=RESULT_TTL_SECONDS,
            payload={
                "items": values,
                "itemKey": item_key,
                "sourceFingerprint": source_fingerprint,
                "metadata": dict(metadata or {}),
            },
        )
        first = paginate(
            values,
            source_fingerprint=source_fingerprint,
            cursor_scope=operation.operation_id,
            page_size=page_size,
        )
        public = {**dict(metadata or {}), item_key: list(first.items)}
        return operation, public, first.page.to_dict()

    def _paged_analysis(
        self,
        *,
        kind: str,
        result: Mapping[str, Any],
        item_key: str,
        source_fingerprint: str,
    ) -> tuple[dict[str, Any], Mapping[str, Any]]:
        metadata = {key: copy.deepcopy(value) for key, value in result.items() if key != item_key}
        operation, public, page = self._page_items(
            kind=kind,
            items=list(result.get(item_key) or []),
            item_key=item_key,
            source_fingerprint=source_fingerprint,
            metadata=metadata,
        )
        public["operationId"] = operation.operation_id
        return public, page

    def _direct_apply(
        self,
        arguments: Mapping[str, Any],
        *,
        tool: str,
        builder: Callable[[Mapping[str, Any], Sequence[Mapping[str, Any]]], ChangeSet],
        item_key: str = "updates",
    ) -> ToolResponse:
        if self._transactions is None or self._mutation_planner is None:
            raise HostAccessError("This host adapter does not support document transactions.")
        metadata = OperationMetadata.create()
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        expected = str(
            _value(
                arguments,
                "expected_document_fingerprint",
                "expectedDocumentFingerprint",
                "",
            )
            or ""
        )
        items = list(arguments.get(item_key) or [])
        if not document_id or not expected:
            raise ValueError("documentId and expectedDocumentFingerprint are required")
        if not items:
            raise ValueError("{} requires at least one explicit item".format(tool))
        before = self._document_model(document_id)
        if fingerprint_model(before) != expected:
            return self._audited_edit_failure(
                tool=tool,
                document_id=document_id,
                summary="The document changed before detached mutation planning.",
                code="stale_document",
                message="Read the current document fingerprint and try again.",
                metadata=metadata,
            )
        requested_model_diff = builder(before, items)
        diagnostics = unsupported_change_diagnostics(requested_model_diff, limit=100)
        if diagnostics["unsupportedCount"]:
            return self._audited_edit_failure(
                tool=tool,
                document_id=document_id,
                summary="The requested batch contains fields outside this mutation milestone.",
                code="unsupported_change",
                message="Structural and unsupported fields were not mutated.",
                metadata=metadata,
                audit_details=diagnostics,
                error_details=diagnostics,
            )
        requested = writable_subset(before, requested_model_diff)
        self._trace.bind_document(document_id)
        try:
            plan = self._mutation_planner.plan(
                document_id=document_id,
                expected_document_fingerprint=expected,
                requested_change_set=requested,
                operation_id=metadata.operation_id,
                before_model=before,
            )
            result = self._transactions.apply_plan(plan)
        except StaleDocumentError:
            return self._audited_edit_failure(
                tool=tool,
                document_id=document_id,
                summary="The document changed before the verified transaction.",
                code="stale_document",
                message="The document changed.",
                metadata=metadata,
            )
        except TransactionVerificationError as exc:
            failure_data = {
                "rollbackAttempted": True,
                "rollbackSucceeded": exc.rollback_succeeded,
            }
            return self._audited_edit_failure(
                tool=tool,
                document_id=document_id,
                summary="The mutation failed complete read-back verification.",
                code="transaction_failed",
                message="The mutation was not verified.",
                metadata=metadata,
                audit_details=failure_data,
                data=failure_data,
            )

        observed_items = [change.to_dict() for change in plan.observed_change_set.changes]
        changed_glyphs: list[str] = []
        for change in plan.observed_change_set.changes:
            if len(change.path) >= 2 and change.path[0] == "glyphs" and change.path[1] not in changed_glyphs:
                changed_glyphs.append(change.path[1])
        self._operations.create(
            kind="mutation_diff",
            operation_id=metadata.operation_id,
            ttl_seconds=RESULT_TTL_SECONDS,
            payload={
                "items": observed_items,
                "itemKey": "changes",
                "sourceFingerprint": result.after_fingerprint,
                "metadata": {
                    "documentId": document_id,
                    "operationId": metadata.operation_id,
                    "beforeFingerprint": result.before_fingerprint,
                    "afterFingerprint": result.after_fingerprint,
                    "requestedChangeCount": result.requested_change_count,
                    "observedChangeCount": result.observed_change_count,
                    "affectedGlyphCount": len(changed_glyphs),
                },
            },
        )
        page = paginate(
            observed_items,
            source_fingerprint=result.after_fingerprint,
            cursor_scope=metadata.operation_id,
            page_size=100,
        )
        receipt = self._audit.record(
            tool=tool,
            effect="edit",
            status="success",
            document_id=document_id,
            details={
                "operationId": metadata.operation_id,
                "reason": _value(arguments, "reason"),
                "beforeFingerprint": result.before_fingerprint,
                "afterFingerprint": result.after_fingerprint,
                "requestedChangeCount": result.requested_change_count,
                "observedChangeCount": result.observed_change_count,
                "affectedGlyphCount": len(changed_glyphs),
            },
        )
        return ToolResponse.success(
            tool=tool,
            effect="edit",
            summary="Applied one explicit batch through detached simulation and one verified transaction; the font was not saved.",
            metadata=metadata,
            audit_receipt=receipt.to_dict(),
            page=page.page.to_dict(),
            data={
                "operationId": metadata.operation_id,
                "documentId": document_id,
                "beforeFingerprint": result.before_fingerprint,
                "afterFingerprint": result.after_fingerprint,
                "requestedChangeCount": result.requested_change_count,
                "observedChangeCount": result.observed_change_count,
                "affectedGlyphCount": len(changed_glyphs),
                "observedChangeSet": {
                    "beforeFingerprint": result.before_fingerprint,
                    "afterFingerprint": result.after_fingerprint,
                    "changeCount": result.observed_change_count,
                    "changes": list(page.items),
                },
                "fontSaved": False,
                "transactionCount": 1,
                "revert": {"available": True, "operationId": metadata.operation_id},
            },
        )

    def get_server_info(self, arguments: Mapping[str, Any]) -> ToolResponse:
        runtime = self._host.runtime_snapshot()
        return ToolResponse.success(
            tool="get_server_info",
            effect="read",
            summary="Glyphs MCP {} is available with {} open document(s).".format(API_VERSION, runtime.open_document_count),
            data={
                "serverName": SERVER_NAME,
                "serverVersion": SERVER_VERSION,
                "apiMajor": API_MAJOR,
                "apiVersion": API_VERSION,
                "capabilities": [
                    "stable_document_ids",
                    "typed_operation_envelopes",
                    "fingerprint_bound_pagination",
                    "verified_transactions",
                    "staged_python",
                    "python_rollback",
                    "production_reviews",
                    "canonical_change_history",
                ],
                "host": runtime.to_dict(),
            },
        )

    def list_open_fonts(self, arguments: Mapping[str, Any]) -> ToolResponse:
        documents = tuple(self._host.list_documents())
        warnings = tuple(
            ToolWarning(
                code="dirty_state_unavailable",
                message="Glyphs did not expose authoritative dirty state for this document.",
                target={"documentId": document.document_id},
            )
            for document in documents
            if document.has_unsaved_changes is None
        )
        return ToolResponse.success(
            tool="list_open_fonts",
            effect="read",
            status="warning" if warnings else "success",
            summary="Found {} open Glyphs document(s).".format(len(documents)),
            warnings=warnings,
            data={"count": len(documents), "documents": [document.to_dict() for document in documents]},
        )

    def get_document_status(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        model = self._document_model(document_id)
        snapshot = next((item for item in self._host.list_documents() if item.document_id == document_id), None)
        if snapshot is None:
            raise HostAccessError("The document is no longer open.")
        return ToolResponse.success(
            tool="get_document_status",
            effect="read",
            summary="Read the current document fingerprint and file state.",
            data={
                "document": snapshot.to_dict(),
                "documentFingerprint": fingerprint_model(model),
                "canonicalModelSchemaVersion": CANONICAL_MODEL_SCHEMA_VERSION,
                "reversibilityCoverage": REVERSIBILITY_COVERAGE,
            },
        )

    def get_operation(self, arguments: Mapping[str, Any]) -> ToolResponse:
        operation_id = str(_value(arguments, "operation_id", "operationId", "") or "")
        record = self._operations.get(operation_id) or self._reviews.get(operation_id) or self._checkpoints.get(operation_id)
        if record is None:
            commit = self.history.get_commit(operation_id)
            if commit is None:
                return ToolResponse.failure(
                    tool="get_operation",
                    effect="read",
                    summary="The operation is missing or expired.",
                    code="operation_unavailable",
                    message="The operation is unavailable.",
                    recoverable=False,
                )
            self._trace.bind_document(commit.document_id)
            changes = [change.to_dict() for change in commit.change_set.changes]
            page = paginate(
                changes,
                source_fingerprint=commit.change_set.after_fingerprint,
                cursor_scope=commit.commit_id,
                page_size=int(_value(arguments, "page_size", "pageSize", 100)),
                cursor=_value(arguments, "cursor"),
            )
            return ToolResponse.success(
                tool="get_operation",
                effect="read",
                summary="Read the bounded semantic diff for one unsaved-session change commit.",
                data={
                    "operationId": commit.commit_id,
                    "kind": "change_commit",
                    "createdAt": _iso_timestamp(commit.created_at),
                    "expiresAt": None,
                    "payload": {
                        **_change_commit_summary(commit),
                        "changes": list(page.items),
                    },
                },
                page=page.page.to_dict(),
            )
        payload = record.payload
        stored_document_id = str(
            payload.get("documentId")
            or (payload.get("metadata") or {}).get("documentId")
            or ""
        )
        if stored_document_id:
            self._trace.bind_document(stored_document_id)
        page_data = None
        public_payload: Any
        if isinstance(payload.get("items"), Sequence) and not isinstance(payload.get("items"), (str, bytes)):
            source_fingerprint = str(payload.get("sourceFingerprint") or fingerprint_model(payload.get("items")))
            page = paginate(
                list(payload.get("items") or []),
                source_fingerprint=source_fingerprint,
                cursor_scope=record.operation_id,
                page_size=int(_value(arguments, "page_size", "pageSize", 100)),
                cursor=_value(arguments, "cursor"),
            )
            page_data = page.page.to_dict()
            public_payload = {
                **dict(payload.get("metadata") or {}),
                str(payload.get("itemKey") or "items"): list(page.items),
            }
        else:
            public_payload = _public_payload(payload)
        return ToolResponse.success(
            tool="get_operation",
            effect="read",
            summary="Read the bounded operation record.",
            data={
                "operationId": record.operation_id,
                "kind": record.kind,
                "createdAt": _iso_timestamp(record.created_at),
                "expiresAt": _iso_timestamp(record.expires_at),
                "payload": public_payload,
            },
            page=page_data,
        )

    def _list_model_items(
        self,
        *,
        tool: str,
        arguments: Mapping[str, Any],
        producer: Callable[[Mapping[str, Any]], Sequence[Mapping[str, Any]]],
        item_key: str,
    ) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        model = self._document_model(document_id)
        source_fingerprint = fingerprint_model(model)
        items = list(producer(model))
        cursor_scope = fingerprint_model(
            {"tool": tool, "documentId": document_id, "items": items}
        )
        page = paginate(
            items,
            source_fingerprint=source_fingerprint,
            cursor_scope=cursor_scope,
            page_size=int(_value(arguments, "page_size", "pageSize", 100)),
            cursor=_value(arguments, "cursor"),
        )
        return ToolResponse.success(
            tool=tool,
            effect="read",
            summary="Returned {} of {} item(s).".format(len(page.items), len(items)),
            page=page.page.to_dict(),
            data={"documentId": document_id, "count": len(items), item_key: list(page.items)},
        )

    def list_glyphs(self, arguments: Mapping[str, Any]) -> ToolResponse:
        fields = _value(arguments, "fields", default=None)
        include_links = bool(_value(arguments, "include_links", "includeLinks", False))
        return self._list_model_items(
            tool="list_glyphs",
            arguments=arguments,
            producer=lambda model: model_list_glyphs(
                model, fields=fields, include_links=include_links
            ),
            item_key="glyphs",
        )

    def list_instances(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._list_model_items(tool="list_instances", arguments=arguments, producer=model_list_instances, item_key="instances")

    def list_kerning_pairs(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._list_model_items(tool="list_kerning_pairs", arguments=arguments, producer=model_list_kerning_pairs, item_key="pairs")

    def review_kerning_coverage(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        model = self._document_model(document_id)
        result = review_kerning_coverage(
            model,
            mode=str(_value(arguments, "mode", default="class_representatives")),
            eligible_count=_value(arguments, "eligible_count", "eligibleCount"),
            measured_count=_value(arguments, "measured_count", "measuredCount"),
            skipped_count=int(_value(arguments, "skipped_count", "skippedCount", 0)),
        )
        return ToolResponse.success(
            tool="review_kerning_coverage",
            effect="read",
            status="success" if result["complete"] else "partial",
            summary="Accounted for {} eligible kerning pair(s); {} remain untested.".format(
                result["eligibleCount"], result["untestedCount"]
            ),
            data={
                "documentId": document_id,
                "documentFingerprint": fingerprint_model(model),
                **result,
            },
        )

    def review_master_compatibility(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        model = self._document_model(document_id)
        result = model_review_master_compatibility(
            model,
            mode=str(_value(arguments, "mode", default="component_preserving")),
            include_nonexporting=bool(_value(arguments, "include_nonexporting", "includeNonexporting", False)),
        )
        dependency_result = {
            "componentDependencyCount": result.get("componentDependencyCount", 0),
            "componentDependencies": result.get("componentDependencies", []),
        }
        dependency_public, dependency_page = self._paged_analysis(
            kind="component_dependency_review",
            result=dependency_result,
            item_key="componentDependencies",
            source_fingerprint=fingerprint_model(
                {"document": model, "dependencies": dependency_result}
            ),
        )
        result = {key: value for key, value in result.items() if key != "componentDependencies"}
        public, page = self._paged_analysis(
            kind="compatibility_review",
            result=result,
            item_key="findings",
            source_fingerprint=fingerprint_model({"document": model, "review": result}),
        )
        public["componentDependencies"] = dependency_public["componentDependencies"]
        public["componentDependencyOperationId"] = dependency_public["operationId"]
        public["componentDependenciesPage"] = dependency_page
        return ToolResponse.success(
            tool="review_master_compatibility",
            effect="read",
            status="warning" if result["hasHardFailures"] else "success",
            summary="Reviewed master compatibility across {} glyph(s).".format(result["reviewedGlyphCount"]),
            data={"documentId": document_id, "documentFingerprint": fingerprint_model(model), **public},
            page=page,
        )

    def review_metrics_inheritance(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        model = self._document_model(document_id)
        result = model_review_metrics_inheritance(model)
        public, page = self._paged_analysis(
            kind="metrics_review",
            result=result,
            item_key="findings",
            source_fingerprint=fingerprint_model({"document": model, "review": result}),
        )
        return ToolResponse.success(
            tool="review_metrics_inheritance",
            effect="read",
            status="warning" if result["findings"] else "success",
            summary="Reviewed metrics inheritance across {} glyph(s).".format(result["reviewedGlyphCount"]),
            data={"documentId": document_id, "documentFingerprint": fingerprint_model(model), **public},
            page=page,
        )

    def review_anchor_consistency(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        model = self._document_model(document_id)
        result = model_review_anchor_consistency(model)
        public, page = self._paged_analysis(
            kind="anchor_review",
            result=result,
            item_key="findings",
            source_fingerprint=fingerprint_model({"document": model, "review": result}),
        )
        return ToolResponse.success(
            tool="review_anchor_consistency",
            effect="read",
            status="warning" if result["findings"] else "success",
            summary="Reviewed anchor consistency across {} glyph(s).".format(result["reviewedGlyphCount"]),
            data={"documentId": document_id, "documentFingerprint": fingerprint_model(model), **public},
            page=page,
        )

    def apply_compatibility_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._direct_apply(arguments, tool="apply_compatibility_updates", builder=build_compatibility_updates)

    def apply_metrics_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._direct_apply(arguments, tool="apply_metrics_updates", builder=build_metrics_updates)

    def apply_anchor_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._direct_apply(arguments, tool="apply_anchor_updates", builder=build_anchor_updates)

    def apply_glyph_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._direct_apply(arguments, tool="apply_glyph_updates", builder=build_glyph_updates)

    def apply_kerning_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._direct_apply(arguments, tool="apply_kerning_updates", builder=build_kerning_updates)

    def apply_opentype_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._direct_apply(arguments, tool="apply_opentype_updates", builder=build_opentype_updates)

    def review_spacing(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        model = self._document_model(document_id)
        requested_items = list(arguments.get("items") or [])
        if not requested_items:
            names = set(_value(arguments, "glyph_names", "glyphNames", []) or [])
            for name, glyph in model.get("glyphs", {}).items():
                if names and name not in names:
                    continue
                for master_id, layer in glyph.get("layers", {}).items():
                    requested_items.append(
                        {
                            "glyphName": name,
                            "masterId": master_id,
                            "width": layer.get("width") or 0,
                            "category": glyph.get("category"),
                            "targetWidth": layer.get("width") or 0,
                            "hostOwnsWidth": bool(layer.get("hasAlignedWidth")),
                        }
                    )
        else:
            for item in requested_items:
                glyph = model.get("glyphs", {}).get(item.get("glyphName"))
                layer = (
                    glyph.get("layers", {}).get(item.get("masterId"))
                    if isinstance(glyph, Mapping)
                    else None
                )
                if isinstance(layer, Mapping):
                    item["hostOwnsWidth"] = bool(layer.get("hasAlignedWidth"))
        simulation = simulate_spacing(
            requested_items,
            max_iterations=int(_value(arguments, "max_iterations", "maxIterations", 5)),
            tolerance=float(_value(arguments, "tolerance", default=1)),
        )
        simulation_public, _simulation_page = self._paged_analysis(
            kind="spacing_analysis",
            result=simulation,
            item_key="items",
            source_fingerprint=fingerprint_model({"document": model, "spacing": simulation}),
        )
        return ToolResponse.success(
            tool="review_spacing",
            effect="read",
            status="warning" if simulation.get("actionableCount") else "success",
            summary="Simulated spacing to a bounded fixed point; the document is unchanged.",
            data={
                "documentId": document_id,
                "documentFingerprint": fingerprint_model(model),
                "simulation": simulation_public,
            },
        )

    def apply_spacing(self, arguments: Mapping[str, Any]) -> ToolResponse:
        def build(
            model: Mapping[str, Any],
            items: Sequence[Mapping[str, Any]],
        ) -> ChangeSet:
            for source in items:
                glyph = model.get("glyphs", {}).get(source.get("glyphName"))
                layer = (
                    glyph.get("layers", {}).get(source.get("masterId"))
                    if isinstance(glyph, Mapping)
                    else None
                )
                if not isinstance(layer, Mapping):
                    raise ValueError(
                        "unknown spacing target: {}/{}".format(
                            source.get("glyphName"), source.get("masterId")
                        )
                    )
                if bool(layer.get("hasAlignedWidth")):
                    raise ValueError(
                        "spacing target has a Glyphs-owned automatically aligned width: {}/{}".format(
                            source.get("glyphName"), source.get("masterId")
                        )
                    )
            simulation = simulate_spacing(
                items,
                max_iterations=int(_value(arguments, "max_iterations", "maxIterations", 5)),
                tolerance=float(_value(arguments, "tolerance", default=1)),
            )
            after = copy.deepcopy(dict(model))
            for item in simulation["items"]:
                if item.get("status") != "ready":
                    continue
                glyph = after.get("glyphs", {}).get(item.get("glyphName"))
                layer = glyph.get("layers", {}).get(item.get("masterId")) if isinstance(glyph, Mapping) else None
                if not isinstance(layer, dict):
                    raise ValueError(
                        "unknown spacing target: {}/{}".format(
                            item.get("glyphName"), item.get("masterId")
                        )
                    )
                layer["width"] = item["proposedWidth"]
            return diff_models(model, after)

        return self._direct_apply(
            arguments,
            tool="apply_spacing",
            builder=build,
            item_key="items",
        )

    def review_export(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        model = self._document_model(document_id)
        compatibility = model_review_master_compatibility(model, mode=str(_value(arguments, "compatibility_mode", "compatibilityMode", "component_preserving")))
        destination = str(_value(arguments, "destination", default="") or "")
        inspector = getattr(self._host, "inspect_export_destination", None)
        destination_state = inspector(destination) if callable(inspector) else dict(arguments.get("destination_state") or {"exists": False, "empty": True, "fingerprint": None})
        result = model_review_export(
            destination_state=destination_state,
            compatibility=compatibility,
            overwrite_policy=str(_value(arguments, "overwrite_policy", "overwritePolicy", "fail_if_nonempty")),
            expected_destination_fingerprint=_value(arguments, "expected_destination_fingerprint", "expectedDestinationFingerprint"),
            acknowledged_finding_ids=list(_value(arguments, "acknowledged_finding_ids", "acknowledgedFindingIds", []) or []),
        )
        export_dependencies = {
            "componentDependencyCount": compatibility.get("componentDependencyCount", 0),
            "componentDependencies": compatibility.get("componentDependencies", []),
        }
        dependency_public, dependency_page = self._paged_analysis(
            kind="export_component_dependencies",
            result=export_dependencies,
            item_key="componentDependencies",
            source_fingerprint=fingerprint_model(
                {"document": model, "dependencies": export_dependencies}
            ),
        )
        compatibility_output = {
            key: value for key, value in compatibility.items() if key != "componentDependencies"
        }
        compatibility_public, compatibility_page = self._paged_analysis(
            kind="export_compatibility_review",
            result=compatibility_output,
            item_key="findings",
            source_fingerprint=fingerprint_model({"document": model, "compatibility": compatibility}),
        )
        compatibility_public["componentDependencies"] = dependency_public["componentDependencies"]
        compatibility_public["componentDependencyOperationId"] = dependency_public["operationId"]
        compatibility_public["componentDependenciesPage"] = dependency_page
        review = self._operations.create(
            kind="export_review",
            ttl_seconds=REVIEW_TTL_SECONDS,
            payload={
                "documentId": document_id,
                "documentFingerprint": fingerprint_model(model),
                "destination": destination,
                "destinationState": destination_state,
                "compatibility": compatibility,
                "review": result,
            },
        )
        return ToolResponse.success(
            tool="review_export",
            effect="read",
            status="review_required" if result["ready"] else "warning",
            summary="Export review is ready for confirmation." if result["ready"] else "Export review found blocking conditions.",
            data={"reviewId": review.operation_id, "expiresAt": _iso_timestamp(review.expires_at), **result, "compatibility": compatibility_public},
            page=compatibility_page,
        )

    def export_source_bundle(self, arguments: Mapping[str, Any]) -> ToolResponse:
        review_id = str(_value(arguments, "review_id", "reviewId", "") or "")
        if not bool(arguments.get("confirm")):
            raise ValueError("confirm=true is required")
        review = self._operations.consume(review_id)
        if review is None or review.kind != "export_review":
            return ToolResponse.failure(
                tool="export_source_bundle",
                effect="files",
                summary="The export review is missing, expired, or consumed.",
                code="review_unavailable",
                message="Export review unavailable.",
            )
        payload = review.payload
        if not payload.get("review", {}).get("ready"):
            return ToolResponse.failure(
                tool="export_source_bundle",
                effect="files",
                summary="The reviewed export still has blocking conditions.",
                code="export_blocked",
                message="Resolve the reviewed blockers first.",
            )
        current = self._document_model(str(payload["documentId"]))
        if fingerprint_model(current) != payload.get("documentFingerprint"):
            return ToolResponse.failure(
                tool="export_source_bundle",
                effect="files",
                summary="The document changed after export review.",
                code="stale_document",
                message="Export review is stale.",
            )
        inspector = getattr(self._host, "inspect_export_destination", None)
        if not callable(inspector):
            raise HostAccessError("This host adapter does not inspect export destinations.")
        destination_state = inspector(str(payload.get("destination") or ""))
        if not destination_matches(destination_state, payload.get("destinationState", {})):
            return ToolResponse.failure(
                tool="export_source_bundle",
                effect="files",
                summary="The destination changed after export review; nothing was published.",
                code="destination_changed",
                message="Create a new export review for the current destination fingerprint.",
            )
        exporter = getattr(self._host, "export_source_bundle", None)
        if not callable(exporter):
            raise HostAccessError("This host adapter does not implement source-bundle export.")
        try:
            result = exporter(payload)
        except ExportPublicationError as exc:
            return ToolResponse.failure(
                tool="export_source_bundle",
                effect="files",
                summary="The staged bundle was not published.",
                code="publication_refused",
                message=str(exc),
            )
        receipt = self._audit.record(
            tool="export_source_bundle",
            effect="files",
            status="success",
            document_id=str(payload["documentId"]),
            details={"reviewId": review_id, "destination": payload.get("destination"), "publishedFingerprint": result.get("publishedFingerprint")},
        )
        return ToolResponse.success(
            tool="export_source_bundle",
            effect="files",
            summary="Published the reviewed source bundle atomically.",
            audit_receipt=receipt.to_dict(),
            data={"reviewId": review_id, **dict(result)},
        )

    def list_audit_events(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = _value(arguments, "document_id", "documentId")
        events = [event.to_dict() for event in self._audit.list_events(document_id=document_id)]
        source_fingerprint = fingerprint_model({"events": events})
        page = paginate(
            events,
            source_fingerprint=source_fingerprint,
            cursor_scope="list_audit_events:{}".format(document_id or "*"),
            page_size=int(_value(arguments, "page_size", "pageSize", 100)),
            cursor=_value(arguments, "cursor"),
        )
        return ToolResponse.success(
            tool="list_audit_events",
            effect="read",
            summary="Returned {} of {} audit event(s).".format(len(page.items), len(events)),
            page=page.page.to_dict(),
            data={"count": len(events), "events": list(page.items)},
        )

    def list_change_commits(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        if not document_id:
            raise ValueError("documentId is required")
        self._trace.bind_document(document_id)
        items = [
            _change_commit_summary(commit)
            for commit in self.history.list_commits(document_id)
        ]
        source_fingerprint = fingerprint_model({"documentId": document_id, "commits": items})
        operation, public, page = self._page_items(
            kind="change_log",
            items=items,
            item_key="commits",
            source_fingerprint=source_fingerprint,
            metadata={"documentId": document_id, "count": len(items)},
            page_size=int(_value(arguments, "page_size", "pageSize", 100)),
        )
        public["operationId"] = operation.operation_id
        return ToolResponse.success(
            tool="list_change_commits",
            effect="read",
            summary="Returned {} of {} MCP action commit(s) since the last save.".format(
                len(public["commits"]), len(items)
            ),
            data=public,
            page=page,
        )

    def revert_change(self, arguments: Mapping[str, Any]) -> ToolResponse:
        if self._transactions is None:
            raise HostAccessError("This host adapter does not support document transactions.")
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        operation_id = str(_value(arguments, "operation_id", "operationId", "") or "")
        expected = str(
            _value(
                arguments,
                "expected_document_fingerprint",
                "expectedDocumentFingerprint",
                "",
            )
            or ""
        )
        if not document_id or not operation_id or not expected:
            raise ValueError("documentId, operationId, and expectedDocumentFingerprint are required")
        original = self.history.get_commit(operation_id)
        if original is None or original.document_id != document_id or original.source != "agent":
            return ToolResponse.failure(
                tool="revert_change",
                effect="edit",
                summary="The requested change commit is unavailable for this document.",
                code="change_commit_unavailable",
                message="Choose a current unsaved-session change commit.",
            )
        if not original.changed:
            return ToolResponse.failure(
                tool="revert_change",
                effect="edit",
                summary="The selected tool call made no document change.",
                code="change_commit_empty",
                message="There is no document delta to revert.",
            )
        current = self._document_model(document_id)
        current_fingerprint = fingerprint_model(current)
        if current_fingerprint != expected:
            return ToolResponse.failure(
                tool="revert_change",
                effect="edit",
                summary="The document fingerprint changed before revert.",
                code="stale_document",
                message="Read the current document fingerprint and try again.",
            )
        inverse, conflicts = revert_change_set_onto(current, original.change_set)
        if inverse is None:
            return ToolResponse.failure(
                tool="revert_change",
                effect="edit",
                summary="Later edits overlap the selected change; nothing was reverted.",
                code="revert_conflict",
                message="Resolve or explicitly replace the conflicting fields first.",
                details={"conflictPaths": [list(path) for path in conflicts[:100]]},
                data={"operationId": operation_id, "conflictCount": len(conflicts)},
            )
        # The complete observed inverse defines the intended canonical tree.
        # Writable paths bound what the host may touch; detached reconciliation
        # selects a cause-independent replay that must reproduce the tree.
        intended_after = inverse.apply(current)
        writable_inverse = writable_subset(current, inverse)
        metadata = OperationMetadata.create()
        try:
            plan = self._mutation_planner.plan(
                document_id=document_id,
                expected_document_fingerprint=current_fingerprint,
                requested_change_set=writable_inverse,
                operation_id=metadata.operation_id,
                before_model=current,
                dirty_state_intent="revert",
                removes_contribution_id=operation_id,
                required_after_model=intended_after,
            )
        except CanonicalTargetMismatchError as exc:
            mismatch = exc.mismatch
            return ToolResponse.failure(
                tool="revert_change",
                effect="edit",
                summary="The detached inverse could not reproduce the intended rebased state; nothing was reverted.",
                code="revert_not_exact",
                message="Glyphs derived additional state while simulating the inverse patch.",
                details={
                    "intendedAfterFingerprint": inverse.after_fingerprint,
                    "observedAfterFingerprint": fingerprint_model(exc.observed_after_model),
                    "mismatchCount": len(mismatch.changes),
                    "mismatchPaths": [list(change.path) for change in mismatch.changes[:100]],
                    "mismatchPathsTruncated": len(mismatch.changes) > 100,
                },
                data={
                    "operationId": operation_id,
                    "intendedAfterFingerprint": inverse.after_fingerprint,
                    "observedAfterFingerprint": fingerprint_model(
                        exc.observed_after_model
                    ),
                },
            )
        self._trace.bind_document(document_id)
        try:
            result = self._transactions.apply_plan(plan)
        except StaleDocumentError:
            return ToolResponse.failure(
                tool="revert_change",
                effect="edit",
                summary="The document changed before revert; nothing was applied.",
                code="stale_document",
                message="The document changed.",
            )
        except TransactionVerificationError as exc:
            return self._audited_edit_failure(
                tool="revert_change",
                document_id=document_id,
                summary="The revert failed verification.",
                code="transaction_failed",
                message="The revert was not verified.",
                audit_details={
                    "operationId": operation_id,
                    "rollbackAttempted": True,
                    "rollbackSucceeded": exc.rollback_succeeded,
                },
            )
        receipt = self._audit.record(
            tool="revert_change",
            effect="edit",
            status="success",
            document_id=document_id,
            details={
                "operationId": metadata.operation_id,
                "revertedOperationId": operation_id,
                "beforeFingerprint": result.before_fingerprint,
                "afterFingerprint": result.after_fingerprint,
                "changeCount": result.change_count,
            },
        )
        return ToolResponse.success(
            tool="revert_change",
            effect="edit",
            summary="Reverted the selected change without overwriting unrelated later edits.",
            audit_receipt=receipt.to_dict(),
            metadata=metadata,
            data={
                "operationId": metadata.operation_id,
                "revertedOperationId": operation_id,
                "documentId": document_id,
                "beforeFingerprint": result.before_fingerprint,
                "afterFingerprint": result.after_fingerprint,
                "requestedChangeCount": result.requested_change_count,
                "observedChangeCount": result.observed_change_count,
                "fontSaved": False,
                "transactionCount": 1,
            },
        )

    def execute_python(self, arguments: Mapping[str, Any]) -> ToolResponse:
        if self._python is None:
            raise HostAccessError("This host adapter does not support Python execution.")
        request = PythonExecutionRequest(
            code=_value(arguments, "code"),
            reason=_value(arguments, "reason"),
            intended_effect=str(_value(arguments, "intended_effect", "intendedEffect", "read")),
            execution_mode=str(_value(arguments, "execution_mode", "executionMode", "staged_document")),
            document_id=_value(arguments, "document_id", "documentId"),
            glyph_name=_value(arguments, "glyph_name", "glyphName"),
            master_id=_value(arguments, "master_id", "masterId"),
            layer_id=_value(arguments, "layer_id", "layerId"),
            expected_document_fingerprint=_value(arguments, "expected_document_fingerprint", "expectedDocumentFingerprint"),
            review_id=_value(arguments, "review_id", "reviewId"),
            confirm=bool(arguments.get("confirm", False)),
            max_output_chars=int(_value(arguments, "max_output_chars", "maxOutputChars", 8 * 1024)),
            max_error_chars=int(_value(arguments, "max_error_chars", "maxErrorChars", 8 * 1024)),
        )
        return self._python.execute(request)

    def rollback_python_execution(self, arguments: Mapping[str, Any]) -> ToolResponse:
        if self._python is None:
            raise HostAccessError("This host adapter does not support Python rollback.")
        return self._python.rollback(
            execution_id=str(_value(arguments, "execution_id", "executionId", "") or ""),
            expected_after_fingerprint=str(_value(arguments, "expected_after_fingerprint", "expectedAfterFingerprint", "") or ""),
            confirm=bool(arguments.get("confirm", False)),
            strategy=str(arguments.get("strategy") or "auto"),
        )


# The old internal class name remains import-compatible for the already-committed
# foundation tests. It is not a registered v2 API alias.
ReadOnlyApplication = GlyphsMCPApplication


__all__ = ["GlyphsMCPApplication", "ReadOnlyApplication"]
