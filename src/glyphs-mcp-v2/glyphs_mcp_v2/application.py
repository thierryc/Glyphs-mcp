"""Transport-neutral Glyphs MCP 2.0 application services."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from .audit import AuditLog
from .catalog import TOOL_CATALOG
from .contracts import API_MAJOR, API_VERSION, ToolError, ToolResponse, ToolWarning
from .exporting import ExportPublicationError, destination_matches
from .operations import OperationRecord, OperationStore
from .pagination import CursorError, paginate
from .ports import HostAccessError, ReadOnlyHost
from .python_execution import PythonExecutionRequest, PythonExecutionService
from .semantic import ChangeSet, diff_models, fingerprint_model
from .transactions import StaleDocumentError, TransactionKernel, TransactionVerificationError
from .versions import SERVER_NAME, SERVER_VERSION
from .workflows import (
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


class GlyphsMCPApplication:
    def __init__(
        self,
        host: ReadOnlyHost,
        *,
        operations: Optional[OperationStore] = None,
        audit: Optional[AuditLog] = None,
    ) -> None:
        self._host = host
        self._operations = operations or OperationStore()
        self._reviews = OperationStore()
        self._checkpoints = OperationStore(max_records=512)
        self._audit = audit or AuditLog()
        self._transactions = TransactionKernel(host) if hasattr(host, "capture_model") else None
        self._python = (
            PythonExecutionService(
                host=host,
                transactions=self._transactions,
                reviews=self._reviews,
                checkpoints=self._checkpoints,
                audit=self._audit,
                operations=self._operations,
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
        definition = TOOL_CATALOG.get(handler_name)
        handler = self._handlers.get(handler_name)
        if definition is None or handler is None:
            return ToolResponse.failure(
                tool=handler_name or "unknown",
                effect=definition.effect if definition is not None else "read",
                summary="Unknown Glyphs MCP 2.0 operation.",
                error=ToolError(
                    code="unknown_tool",
                    message="The requested operation is not part of this runtime.",
                    recoverable=False,
                ),
            )
        try:
            return handler(dict(arguments or {}))
        except CursorError as exc:
            return ToolResponse.failure(
                tool=handler_name,
                effect=definition.effect,
                summary="The result cursor is invalid or stale.",
                error=ToolError(code="invalid_cursor", message=str(exc), recoverable=True),
            )
        except HostAccessError as exc:
            return ToolResponse.failure(
                tool=handler_name,
                effect=definition.effect,
                summary="Glyphs host state is temporarily unavailable.",
                error=ToolError(
                    code="host_unavailable",
                    message=str(exc) or "Glyphs host state is unavailable.",
                    recoverable=True,
                ),
            )
        except (ValueError, TypeError) as exc:
            return ToolResponse.failure(
                tool=handler_name,
                effect=definition.effect,
                summary="The request is invalid.",
                error=ToolError(code="invalid_request", message=str(exc), recoverable=True),
            )
        except Exception as exc:
            return ToolResponse.failure(
                tool=handler_name,
                effect=definition.effect,
                summary="The operation failed safely.",
                error=ToolError(
                    code="internal_error",
                    message="The operation failed before returning verified state.",
                    recoverable=True,
                    details={"exceptionType": type(exc).__name__},
                ),
            )

    def _document_model(self, document_id: str) -> dict[str, Any]:
        if not document_id:
            raise ValueError("documentId is required")
        capture = getattr(self._host, "capture_model", None)
        if not callable(capture):
            raise HostAccessError("This host adapter does not expose document snapshots.")
        return copy.deepcopy(dict(capture(document_id)))

    def _review_record(
        self,
        *,
        kind: str,
        tool: str,
        document_id: str,
        change_set: ChangeSet,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> OperationRecord:
        payload = {
            "tool": tool,
            "documentId": document_id,
            "changeSet": change_set,
            "beforeFingerprint": change_set.before_fingerprint,
            "afterFingerprint": change_set.after_fingerprint,
        }
        payload.update(dict(extra or {}))
        return self._reviews.create(kind=kind, payload=payload, ttl_seconds=REVIEW_TTL_SECONDS)

    def _review_response(
        self,
        *,
        tool: str,
        document_id: str,
        change_set: ChangeSet,
        review: OperationRecord,
        data: Optional[Mapping[str, Any]] = None,
    ) -> ToolResponse:
        receipt = self._audit.record(
            tool=tool,
            effect="read",
            status="review_required",
            document_id=document_id,
            details={
                "reviewId": review.operation_id,
                "beforeFingerprint": change_set.before_fingerprint,
                "afterFingerprint": change_set.after_fingerprint,
                "changeCount": len(change_set.changes),
            },
        )
        items = [change.to_dict() for change in change_set.changes]
        operation, public_change_set, page = self._page_items(
            kind="mutation_diff",
            items=items,
            item_key="changes",
            source_fingerprint=change_set.after_fingerprint,
            metadata={
                "beforeFingerprint": change_set.before_fingerprint,
                "afterFingerprint": change_set.after_fingerprint,
                "changeCount": len(items),
                "supported": change_set.supported,
            },
        )
        values = {
            "reviewId": review.operation_id,
            "expiresAt": _iso_timestamp(review.expires_at),
            "documentId": document_id,
            "operationId": operation.operation_id,
            "changeSet": public_change_set,
        }
        values.update(dict(data or {}))
        return ToolResponse.success(
            tool=tool,
            effect="read",
            status="review_required",
            summary="Created a fingerprint-bound review; the document is unchanged.",
            data=values,
            audit_receipt=receipt.to_dict(),
            page=page,
        )

    def _page_items(
        self,
        *,
        kind: str,
        items: Sequence[Mapping[str, Any]],
        item_key: str,
        source_fingerprint: str,
        metadata: Optional[Mapping[str, Any]] = None,
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
            page_size=100,
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

    def _apply_review(self, arguments: Mapping[str, Any], *, expected_tool: str, apply_tool: str) -> ToolResponse:
        if self._transactions is None:
            raise HostAccessError("This host adapter does not support document transactions.")
        review_id = str(_value(arguments, "review_id", "reviewId", "") or "")
        if not bool(arguments.get("confirm")):
            raise ValueError("confirm=true is required")
        review = self._reviews.consume(review_id)
        if review is None or review.kind != "mutation_review" or review.payload.get("tool") != expected_tool:
            return ToolResponse.failure(
                tool=apply_tool,
                effect="edit",
                summary="The review is missing, expired, consumed, or belongs to another tool.",
                error=ToolError(code="review_unavailable", message="The review cannot be applied.", recoverable=True),
            )
        change_set = review.payload.get("changeSet")
        if not isinstance(change_set, ChangeSet):
            raise ValueError("stored review has no valid change set")
        try:
            result = self._transactions.apply(
                document_id=str(review.payload["documentId"]),
                expected_fingerprint=str(review.payload["beforeFingerprint"]),
                change_set=change_set,
            )
        except StaleDocumentError:
            return ToolResponse.failure(
                tool=apply_tool,
                effect="edit",
                summary="The document changed after review; no mutation was attempted.",
                error=ToolError(code="stale_document", message="Review fingerprint is stale.", recoverable=True),
            )
        except TransactionVerificationError as exc:
            receipt = self._audit.record(
                tool=apply_tool,
                effect="edit",
                status="error",
                document_id=str(review.payload["documentId"]),
                details={
                    "reviewId": review_id,
                    "errorCode": "transaction_failed",
                    "rollbackAttempted": True,
                    "rollbackSucceeded": exc.rollback_succeeded,
                },
            )
            return ToolResponse.failure(
                tool=apply_tool,
                effect="edit",
                summary="The mutation failed verification.",
                error=ToolError(code="transaction_failed", message="The mutation was not verified.", recoverable=True),
                data={"rollbackAttempted": True, "rollbackSucceeded": exc.rollback_succeeded},
                audit_receipt=receipt.to_dict(),
            )
        receipt = self._audit.record(
            tool=apply_tool,
            effect="edit",
            status="success",
            document_id=result.document_id,
            details={
                "reviewId": review_id,
                "beforeFingerprint": result.before_fingerprint,
                "afterFingerprint": result.after_fingerprint,
                "changeCount": result.change_count,
            },
        )
        return ToolResponse.success(
            tool=apply_tool,
            effect="edit",
            summary="Applied one reviewed batch in a verified transaction; the font was not saved.",
            audit_receipt=receipt.to_dict(),
            data={
                "reviewId": review_id,
                "documentId": result.document_id,
                "beforeFingerprint": result.before_fingerprint,
                "afterFingerprint": result.after_fingerprint,
                "changeCount": result.change_count,
                "fontSaved": False,
                "transactionCount": 1,
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
            },
        )

    def get_operation(self, arguments: Mapping[str, Any]) -> ToolResponse:
        operation_id = str(_value(arguments, "operation_id", "operationId", "") or "")
        record = self._operations.get(operation_id) or self._reviews.get(operation_id) or self._checkpoints.get(operation_id)
        if record is None:
            return ToolResponse.failure(
                tool="get_operation",
                effect="read",
                summary="The operation is missing or expired.",
                error=ToolError(code="operation_unavailable", message="The operation is unavailable.", recoverable=False),
            )
        payload = record.payload
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

    def review_compatibility_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        changes = build_compatibility_updates(
            self._document_model(document_id), list(arguments.get("updates") or [])
        )
        review = self._review_record(
            kind="mutation_review",
            tool="review_compatibility_updates",
            document_id=document_id,
            change_set=changes,
        )
        return self._review_response(
            tool="review_compatibility_updates",
            document_id=document_id,
            change_set=changes,
            review=review,
        )

    def apply_compatibility_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._apply_review(
            arguments,
            expected_tool="review_compatibility_updates",
            apply_tool="apply_compatibility_updates",
        )

    def review_metrics_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        changes = build_metrics_updates(
            self._document_model(document_id), list(arguments.get("updates") or [])
        )
        review = self._review_record(
            kind="mutation_review",
            tool="review_metrics_updates",
            document_id=document_id,
            change_set=changes,
        )
        return self._review_response(
            tool="review_metrics_updates",
            document_id=document_id,
            change_set=changes,
            review=review,
        )

    def apply_metrics_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._apply_review(
            arguments,
            expected_tool="review_metrics_updates",
            apply_tool="apply_metrics_updates",
        )

    def review_anchor_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        changes = build_anchor_updates(self._document_model(document_id), list(arguments.get("updates") or []))
        review = self._review_record(kind="mutation_review", tool="review_anchor_updates", document_id=document_id, change_set=changes)
        return self._review_response(tool="review_anchor_updates", document_id=document_id, change_set=changes, review=review)

    def apply_anchor_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._apply_review(arguments, expected_tool="review_anchor_updates", apply_tool="apply_anchor_updates")

    def review_glyph_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        changes = build_glyph_updates(self._document_model(document_id), list(arguments.get("updates") or []))
        review = self._review_record(kind="mutation_review", tool="review_glyph_updates", document_id=document_id, change_set=changes)
        return self._review_response(tool="review_glyph_updates", document_id=document_id, change_set=changes, review=review)

    def apply_glyph_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._apply_review(arguments, expected_tool="review_glyph_updates", apply_tool="apply_glyph_updates")

    def review_kerning_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        model = self._document_model(document_id)
        changes = build_kerning_updates(model, list(arguments.get("updates") or []))
        coverage = review_kerning_coverage(model, mode=str(_value(arguments, "coverage_mode", "coverageMode", "class_representatives")))
        review = self._review_record(
            kind="mutation_review",
            tool="review_kerning_updates",
            document_id=document_id,
            change_set=changes,
            extra={"coverage": coverage},
        )
        return self._review_response(
            tool="review_kerning_updates",
            document_id=document_id,
            change_set=changes,
            review=review,
            data={"coverage": coverage},
        )

    def apply_kerning_updates(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._apply_review(arguments, expected_tool="review_kerning_updates", apply_tool="apply_kerning_updates")

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
                        }
                    )
        simulation = simulate_spacing(
            requested_items,
            max_iterations=int(_value(arguments, "max_iterations", "maxIterations", 5)),
            tolerance=float(_value(arguments, "tolerance", default=1)),
        )
        after = copy.deepcopy(model)
        for item in simulation["items"]:
            if item.get("status") != "ready":
                continue
            glyph = after.get("glyphs", {}).get(item.get("glyphName"))
            layer = glyph.get("layers", {}).get(item.get("masterId")) if isinstance(glyph, Mapping) else None
            if isinstance(layer, dict):
                layer["width"] = item["proposedWidth"]
        changes = diff_models(model, after)
        simulation_public, _simulation_page = self._paged_analysis(
            kind="spacing_analysis",
            result=simulation,
            item_key="items",
            source_fingerprint=fingerprint_model({"document": model, "spacing": simulation}),
        )
        review = self._review_record(kind="mutation_review", tool="review_spacing", document_id=document_id, change_set=changes, extra={"simulation": simulation})
        return self._review_response(tool="review_spacing", document_id=document_id, change_set=changes, review=review, data={"simulation": simulation_public})

    def apply_spacing(self, arguments: Mapping[str, Any]) -> ToolResponse:
        return self._apply_review(arguments, expected_tool="review_spacing", apply_tool="apply_spacing")

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
                error=ToolError(code="review_unavailable", message="Export review unavailable.", recoverable=True),
            )
        payload = review.payload
        if not payload.get("review", {}).get("ready"):
            return ToolResponse.failure(
                tool="export_source_bundle",
                effect="files",
                summary="The reviewed export still has blocking conditions.",
                error=ToolError(code="export_blocked", message="Resolve the reviewed blockers first.", recoverable=True),
            )
        current = self._document_model(str(payload["documentId"]))
        if fingerprint_model(current) != payload.get("documentFingerprint"):
            return ToolResponse.failure(
                tool="export_source_bundle",
                effect="files",
                summary="The document changed after export review.",
                error=ToolError(code="stale_document", message="Export review is stale.", recoverable=True),
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
                error=ToolError(
                    code="destination_changed",
                    message="Create a new export review for the current destination fingerprint.",
                    recoverable=True,
                ),
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
                error=ToolError(code="publication_refused", message=str(exc), recoverable=True),
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
