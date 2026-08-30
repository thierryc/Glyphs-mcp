"""Transport-neutral Glyphs MCP 2.0 application services."""

from __future__ import annotations

import copy
import os
import time
import traceback
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from .activity import (
    ActivityCancelled,
    OperationActivityStore,
    default_activity_store,
)
from .audit import AuditLog
from .canonical_tree import (
    CANONICAL_MODEL_SCHEMA_VERSION,
    REVERSIBILITY_COVERAGE,
    CanonicalFontTree,
    CanonicalSnapshot,
    MemoryObjectStore,
)
from .canonical_schema import CanonicalCoverage
from .catalog import TOOL_CATALOG
from .change_history import ActionCommit, ChangeHistory
from .change_lifecycle import DocumentHistoryLifecycle
from .change_trace import ActionTraceCoordinator
from .contracts import API_MAJOR, API_VERSION, OperationMetadata, ToolResponse, ToolWarning
from .detached_python import detached_python_registry_for_host
from .exporting import ExportPublicationError, destination_matches
from .generic_tools import (
    bind_relation_selector,
    build_change_set as build_generic_change_set,
    constraint_observation_request,
    evaluate_constraints as evaluate_generic_constraints,
    project_reference,
    reduce_references,
    resolve_selector,
)
from .knowledge import (
    get_knowledge as read_knowledge_entries,
    knowledge_manifest,
    search_knowledge as search_knowledge_corpus,
)
from .mechanics_registry import public_mechanics_registry
from .operations import OperationRecord, OperationStore
from .mutation import (
    CanonicalTargetMismatchError,
    MutationPlanner,
    RequestedEffectMismatchError,
    unsupported_change_diagnostics,
    writable_subset,
    lifecycle_capabilities,
)
from .observations import collect_constraint_context, collect_native_observations
from .pagination import CursorError, paginate
from .ports import HostAccessError, ReadOnlyHost
from .python_execution import PythonExecutionRequest, PythonExecutionService
from .runtime_identity import loaded_runtime_identity
from .runtime_safety import StaleScriptingRuntimeIncidentError
from .semantic import (
    ChangeSet,
    diff_models,
    fingerprint_model,
    public_change_dict,
    revert_change_set_onto,
)
from .saving import DocumentSaveError, SAVE_OVERWRITE_POLICIES
from .saved_source import SavedSourceService, SavedSourceSnapshot
from .source_bundle import BUNDLE_LAYOUT_VERSION, ExportPlan, SourceBundleError
from .transactions import StaleDocumentError, TransactionKernel, TransactionVerificationError
from .versions import SERVER_NAME, SERVER_VERSION


REVIEW_TTL_SECONDS = 15 * 60
RESULT_TTL_SECONDS = 60 * 60
PUBLIC_NORMALIZED_OPERATION_LIMIT = 100


def _healthy_scripting_runtime_safety() -> dict[str, Any]:
    return {
        "state": "healthy",
        "mode": "strict",
        "strictInterlockAvailable": True,
        "livePythonAvailable": True,
        "stagedPythonAvailable": True,
        "automaticRepairAvailable": False,
        "incidentId": None,
        "affectedSlotCount": 0,
        "nextAction": "none",
        "activeExecutionId": None,
        "currentIncident": None,
        "lastRepair": None,
        "recentTransitions": [],
    }


def _scripting_runtime_safety(host: Any) -> dict[str, Any]:
    reader = getattr(host, "scripting_runtime_safety_status", None)
    value = reader() if callable(reader) else None
    return (
        dict(value)
        if isinstance(value, Mapping)
        else _healthy_scripting_runtime_safety()
    )


def _value(arguments: Mapping[str, Any], snake: str, camel: Optional[str] = None, default: Any = None) -> Any:
    if snake in arguments:
        return arguments[snake]
    if camel and camel in arguments:
        return arguments[camel]
    return default


def _model_layer(glyph: Any, identity: Any) -> Mapping[str, Any] | None:
    if not isinstance(glyph, Mapping):
        return None
    layers = glyph.get("layers", ())
    if isinstance(layers, Mapping):
        candidate = layers.get(identity)
        return candidate if isinstance(candidate, Mapping) else None
    if not isinstance(layers, (list, tuple)):
        return None
    text = str(identity or "")
    direct = [layer for layer in layers if isinstance(layer, Mapping) and str(layer.get("id") or "") == text]
    if len(direct) == 1:
        return direct[0]
    masters = [
        layer
        for layer in layers
        if isinstance(layer, Mapping)
        and bool(layer.get("isMasterLayer"))
        and str(layer.get("masterId") or "") == text
    ]
    return masters[0] if len(masters) == 1 else None


def _iso_timestamp(value: float) -> str:
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _export_runtime_versions(host: Any) -> dict[str, Any]:
    """Capture only runtime identity that can affect exported source bytes."""

    runtime = host.runtime_snapshot()
    public = runtime.to_dict() if hasattr(runtime, "to_dict") else dict(runtime)
    return {
        key: public.get(key)
        for key in (
            "application",
            "applicationVersion",
            "buildNumber",
            "pythonVersion",
        )
    }


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
            if str(key)
            not in {
                "code",
                "source",
                "inverse",
                "plan",
                "beforeModel",
                "expectedAfterModel",
                "writableChangeSet",
                "executionContext",
            }
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
        "canonicalCoverage": commit.coverage.to_public_dict(),
    }


class GlyphsMCPApplication:
    def __init__(
        self,
        host: ReadOnlyHost,
        *,
        operations: Optional[OperationStore] = None,
        audit: Optional[AuditLog] = None,
        history: Optional[ChangeHistory] = None,
        activity: Optional[OperationActivityStore] = None,
        saved_sources: SavedSourceService | None = None,
    ) -> None:
        self._host = host
        self.activity = activity or default_activity_store()
        self._operations = operations or OperationStore()
        self._reviews = OperationStore()
        # Generic document previews and staged-Python previews intentionally
        # share one immutable process-local store.  ``apply_change`` is the
        # sole consumer of staged document patches.
        self._previews = self._reviews
        self._checkpoints = OperationStore(max_records=512)
        self._audit = audit or AuditLog()
        self._saved_sources = saved_sources
        if history is None:
            history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
            history.reset_for_schema_change(6, 7)
        self.history = history
        self.lifecycle = DocumentHistoryLifecycle(
            self.history,
            reset_tracking=getattr(host, "reset_verified_change_tracking", None),
        )
        self._trace = ActionTraceCoordinator(self.history)
        self._transactions = (
            TransactionKernel(
                host,
                observer=self._trace,
                activity=self.activity,
                persistence=self.lifecycle,
            )
            if hasattr(host, "capture_model")
            else None
        )
        self._mutation_planner = (
            MutationPlanner(host, activity=self.activity)
            if self._transactions is not None
            else None
        )
        self._python = (
            PythonExecutionService(
                host=host,
                transactions=self._transactions,
                reviews=self._reviews,
                checkpoints=self._checkpoints,
                audit=self._audit,
                operations=self._operations,
                trace=self._trace,
                activity=self.activity,
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
        started_at = datetime.now(timezone.utc)
        started_clock = time.perf_counter_ns()
        values = dict(arguments or {})
        definition = TOOL_CATALOG.get(handler_name)
        document_id = str(
            values.get("documentId") or values.get("document_id") or ""
        ) or None
        activity_token = self.activity.begin(
            document_id=document_id,
            tool=handler_name or "unknown",
            title=(
                definition.title
                if definition is not None
                else str(handler_name or "Glyphs MCP")
            ),
        )
        terminalized = False
        try:
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
                capture = getattr(self._host, "capture_snapshot", None)
                if not callable(capture):
                    capture = getattr(self._host, "capture_model", None)
                if callable(capture):
                    try:
                        self._trace.observe_model(
                            scope.document_id or "",
                            capture(scope.document_id or ""),
                        )
                    except Exception:
                        pass
            completed_at = datetime.now(timezone.utc)
            response = replace(
                response,
                metadata=response.metadata.with_timing(
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=(time.perf_counter_ns() - started_clock) // 1_000_000,
                ),
            )
            commit = self._trace.finish_action(scope, response)
            if scope.document_id:
                history_recorded = bool(
                    scope.history_recorded
                    and commit is not None
                    and not scope.history_boundary
                )
                warnings = response.warnings
                if not history_recorded and not scope.history_boundary:
                    warnings = warnings + (
                        ToolWarning(
                            code="history_not_recorded",
                            message=(
                                scope.history_warning
                                or "The execution result is valid, but change history was not recorded."
                            ),
                            target={"documentId": scope.document_id},
                        ),
                    )
                response = replace(
                    response,
                    data={**dict(response.data), "historyRecorded": history_recorded},
                    warnings=warnings,
                )
            self.activity.complete(
                activity_token,
                ok=response.ok,
                summary=response.summary,
                cancelled=bool(
                    response.error is not None
                    and response.error.code == "cancelled"
                ),
            )
            terminalized = True
            return response
        except BaseException as exc:
            if not terminalized:
                cancelled = isinstance(exc, ActivityCancelled) or type(exc).__name__ in {
                    "CancelledError",
                    "KeyboardInterrupt",
                }
                self.activity.complete(
                    activity_token,
                    ok=False,
                    summary=(
                        "Invocation cancelled"
                        if cancelled
                        else "Invocation ended unexpectedly"
                    ),
                    cancelled=cancelled,
                )
            raise
        finally:
            self.activity.release(activity_token)

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
        except ActivityCancelled as exc:
            return ToolResponse.failure(
                tool=handler_name,
                effect=definition.effect,
                summary="The operation was cancelled before live mutation.",
                code="cancelled",
                message=str(exc) or "The operation was cancelled.",
            )
        except (ValueError, TypeError) as exc:
            if os.environ.get("GLYPHS_MCP_DEBUG_CAPTURE"):
                traceback.print_exc()
            return ToolResponse.failure(
                tool=handler_name,
                effect=definition.effect,
                summary="The request is invalid.",
                code="invalid_request",
                message=str(exc),
            )
        except Exception as exc:
            if os.environ.get("GLYPHS_MCP_DEBUG_CAPTURE"):
                traceback.print_exc()
            return ToolResponse.failure(
                tool=handler_name,
                effect=definition.effect,
                summary="The operation failed safely.",
                code="internal_error",
                message="The operation failed before returning verified state.",
                details={"exceptionType": type(exc).__name__},
            )

    def _document_model(self, document_id: str) -> Mapping[str, Any]:
        if not document_id:
            raise ValueError("documentId is required")
        capture = getattr(self._host, "capture_stable_snapshot", None)
        if not callable(capture):
            capture = getattr(self._host, "capture_snapshot", None)
        if not callable(capture):
            capture = getattr(self._host, "capture_model", None)
        if not callable(capture):
            raise HostAccessError(
                "This host adapter does not expose document snapshots."
            )
        captured = capture(document_id)
        model = (
            captured
            if hasattr(captured, "document_fingerprint")
            else copy.deepcopy(dict(captured))
        )
        self._trace.observe_model(document_id, model)
        return model

    def _read_tree_references(
        self,
        model: Mapping[str, Any],
        references: Sequence[Any],
        selector: Mapping[str, Any],
    ) -> tuple[Any, ...]:
        values = list(references)
        relations = selector.get("relations") or ()
        if not isinstance(relations, (list, tuple)):
            raise ValueError("selector.relations must be a list")
        for reference in references:
            for relation in relations:
                if not isinstance(relation, Mapping):
                    raise ValueError("selector relations must be objects")
                child_selector = relation.get("selector")
                if not isinstance(child_selector, Mapping):
                    raise ValueError("relation.selector must be an object")
                bound = bind_relation_selector(reference, child_selector)
                children = resolve_selector(model, bound)
                values.extend(
                    self._read_tree_references(model, children, bound)
                )
        return tuple(values)

    def _read_projection_fields(
        self,
        selector: Mapping[str, Any],
        projection: Mapping[str, Any],
    ) -> set[str]:
        fields = {str(field) for field in projection.get("fields") or ()}
        for relation in selector.get("relations") or ():
            if not isinstance(relation, Mapping):
                raise ValueError("selector relations must be objects")
            child_selector = relation.get("selector")
            child_projection = relation.get("projection")
            if not isinstance(child_selector, Mapping) or not isinstance(
                child_projection, Mapping
            ):
                raise ValueError("relations require selector and projection objects")
            fields.update(
                self._read_projection_fields(child_selector, child_projection)
            )
        return fields

    def _with_persistence_observation(
        self,
        document_id: str,
        model: Mapping[str, Any],
        observations: Mapping[tuple[str, str], Mapping[str, Any]],
        *,
        requested_fields: Sequence[str],
        dirty: bool | None = None,
    ) -> Mapping[tuple[str, str], Mapping[str, Any]]:
        if "persistence" not in {str(value) for value in requested_fields}:
            return observations
        source = observations.get(("__document__", "persistence"))
        if dirty is None:
            try:
                dirty = next(
                    (
                        document.has_unsaved_changes
                        for document in self._host.list_documents()
                        if document.document_id == document_id
                    ),
                    None,
                )
            except Exception:
                dirty = None
        merged = dict(observations)
        merged[("__document__", "persistence")] = self.lifecycle.persistence_state(
            document_id,
            live_model=model,
            source_state=source,
            dirty=dirty,
        )
        return merged

    def _selector_cursor_binding(
        self, selector: Mapping[str, Any]
    ) -> dict[str, Any]:
        binding = {
            key: copy.deepcopy(value)
            for key, value in selector.items()
            if key != "cursor"
        }
        relations = []
        for relation in selector.get("relations") or ():
            if not isinstance(relation, Mapping) or not isinstance(
                relation.get("selector"), Mapping
            ):
                raise ValueError("relations require selector objects")
            relations.append(
                {
                    **{
                        key: copy.deepcopy(value)
                        for key, value in relation.items()
                        if key != "selector"
                    },
                    "selector": self._selector_cursor_binding(
                        relation["selector"]
                    ),
                }
            )
        if relations:
            binding["relations"] = relations
        return binding

    def _project_read_tree(
        self,
        *,
        model: Mapping[str, Any],
        reference: Any,
        selector: Mapping[str, Any],
        projection: Mapping[str, Any],
        observations: Mapping[tuple[str, str], Mapping[str, Any]],
        effective_metadata: Mapping[str, Mapping[str, Any]],
        document_fingerprint: str,
    ) -> dict[str, Any]:
        item = project_reference(
            reference,
            projection,
            observations=observations,
            effective_metadata=effective_metadata,
        )
        relations = selector.get("relations") or ()
        if not relations:
            return item
        related: dict[str, Any] = {}
        for relation in relations:
            if not isinstance(relation, Mapping):
                raise ValueError("selector relations must be objects")
            name = str(relation.get("name") or "")
            child_selector = relation.get("selector")
            child_projection = relation.get("projection")
            if (
                not name
                or name in related
                or not isinstance(child_selector, Mapping)
                or not isinstance(child_projection, Mapping)
            ):
                raise ValueError(
                    "relations require unique names, selectors, and projections"
                )
            bound = bind_relation_selector(reference, child_selector)
            children = resolve_selector(model, bound)
            projected = [
                self._project_read_tree(
                    model=model,
                    reference=child,
                    selector=bound,
                    projection=child_projection,
                    observations=observations,
                    effective_metadata=effective_metadata,
                    document_fingerprint=document_fingerprint,
                )
                for child in children
            ]
            scope_selector = self._selector_cursor_binding(bound)
            relation_scope = fingerprint_model(
                {
                    "tool": "read_document.relation",
                    "parent": reference.public_identity(),
                    "name": name,
                    "selector": scope_selector,
                    "projection": child_projection,
                    "canonicalModelSchemaVersion": CANONICAL_MODEL_SCHEMA_VERSION,
                }
            )
            page = paginate(
                projected,
                source_fingerprint=document_fingerprint,
                cursor_scope=relation_scope,
                page_size=int(bound.get("pageSize", 100)),
                cursor=bound.get("cursor"),
            )
            partial_count = sum(
                value.get("completeness") != "complete" for value in projected
            )
            related[name] = {
                "selectedCount": len(projected),
                "partialCount": partial_count,
                "items": list(page.items),
                "page": page.page.to_dict(),
                "reducers": reduce_references(
                    children, child_projection.get("reducers") or ()
                ),
            }
            if partial_count:
                item["completeness"] = "partial"
                item.setdefault("missingFields", []).append("relation:" + name)
        item["relations"] = related
        return item

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

    def _audited_save_failure(
        self,
        *,
        document_id: str,
        summary: str,
        code: str,
        message: str,
        metadata: OperationMetadata,
        reason: str,
        recoverable: bool = True,
        details: Optional[Mapping[str, Any]] = None,
        data: Optional[Mapping[str, Any]] = None,
    ) -> ToolResponse:
        receipt = self._audit.record(
            tool="save_document",
            effect="save",
            status="error",
            document_id=document_id or None,
            details={
                "operationId": metadata.operation_id,
                "errorCode": code,
                "reason": reason,
                **dict(details or {}),
            },
        )
        if data:
            try:
                self._operations.create(
                    kind="document_save_failure",
                    operation_id=metadata.operation_id,
                    ttl_seconds=RESULT_TTL_SECONDS,
                    payload={"documentId": document_id, **dict(data)},
                )
            except Exception:
                pass
        return ToolResponse.failure(
            tool="save_document",
            effect="save",
            summary=summary,
            code=code,
            message=message,
            recoverable=recoverable,
            details=details,
            data=data,
            metadata=metadata,
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




    def list_documents(self, arguments: Mapping[str, Any]) -> ToolResponse:
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
            tool="list_documents",
            effect="read",
            status="warning" if warnings else "success",
            summary="Found {} open Glyphs document(s).".format(len(documents)),
            warnings=warnings,
            data={
                "count": len(documents),
                "documents": [document.to_dict() for document in documents],
            },
        )

    def read_document(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        selector = arguments.get("selector")
        projection = arguments.get("projection")
        if not isinstance(selector, Mapping) or not isinstance(projection, Mapping):
            raise ValueError("read_document requires selector and projection objects")
        model = self._document_model(document_id)
        document_fingerprint = fingerprint_model(model)
        references = resolve_selector(model, selector)
        all_references = self._read_tree_references(model, references, selector)
        glyph_names = sorted(
            {
                reference.identity
                if reference.kind == "glyph"
                else str(reference.parent.get("glyphName") or "")
                for reference in all_references
                if reference.kind in {"glyph", "layer", "shape", "node", "anchor"}
            }
            - {""}
        )
        fields = self._read_projection_fields(selector, projection)
        observations, effective_metadata = collect_native_observations(
            self._host,
            document_id,
            fields,
            glyph_names,
            suppressed_errors=(HostAccessError,),
        )
        observations = self._with_persistence_observation(
            document_id,
            model,
            observations,
            requested_fields=tuple(fields),
        )
        items = [
            self._project_read_tree(
                model=model,
                reference=reference,
                selector=selector,
                projection=projection,
                observations=observations,
                effective_metadata=effective_metadata,
                document_fingerprint=document_fingerprint,
            )
            for reference in references
        ]
        cursor_scope = fingerprint_model(
            {
                "tool": "read_document",
                "documentId": document_id,
                "selector": self._selector_cursor_binding(selector),
                "projection": projection,
                "canonicalModelSchemaVersion": CANONICAL_MODEL_SCHEMA_VERSION,
            }
        )
        page = paginate(
            items,
            source_fingerprint=document_fingerprint,
            cursor_scope=cursor_scope,
            page_size=int(selector.get("pageSize", 100)),
            cursor=selector.get("cursor"),
        )
        partial_count = sum(item.get("completeness") != "complete" for item in items)
        reducers = reduce_references(
            references, projection.get("reducers") or ()
        )
        warnings = (
            (
                ToolWarning(
                    code="incomplete_observation",
                    message="One or more requested observations were unavailable.",
                    target={"partialCount": partial_count},
                ),
            )
            if partial_count
            else ()
        )
        return ToolResponse.success(
            tool="read_document",
            effect="read",
            status="warning" if warnings else "success",
            summary="Returned {} of {} selected canonical entities.".format(
                len(page.items), len(items)
            ),
            warnings=warnings,
            page=page.page.to_dict(),
            data={
                "documentId": document_id,
                "documentFingerprint": document_fingerprint,
                "canonicalModelSchemaVersion": CANONICAL_MODEL_SCHEMA_VERSION,
                "selectedCount": len(items),
                "partialCount": partial_count,
                "reducers": reducers,
                "items": list(page.items),
            },
        )

    def evaluate_constraints(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        constraints = list(arguments.get("constraints") or ())
        if not constraints:
            raise ValueError("evaluate_constraints requires at least one constraint")
        model = self._document_model(document_id)
        phases = tuple(
            phase
            for phase in ("before", "after")
            if any(str(item.get("phase") or "before") == phase for item in constraints)
        )
        results = []
        for phase in phases:
            observations, effective_metadata, _request = collect_constraint_context(
                self._host,
                document_id,
                model,
                constraints,
                phase=phase,
                suppressed_errors=(HostAccessError,),
            )
            observations = self._with_persistence_observation(
                document_id,
                model,
                observations,
                requested_fields=tuple(_request.get("fields") or ()),
            )
            results.append(
                evaluate_generic_constraints(
                    model,
                    constraints,
                    phase=phase,
                    observations=observations,
                    effective_metadata=effective_metadata,
                )
            )
        items = [item for result in results for item in result["items"]]
        failed = sum(not item["passed"] for item in items)
        return ToolResponse.success(
            tool="evaluate_constraints",
            effect="read",
            status="warning" if failed else "success",
            summary="Evaluated {} constraint(s); {} failed.".format(len(items), failed),
            data={
                "documentId": document_id,
                "documentFingerprint": fingerprint_model(model),
                "constraintCount": len(items),
                "passedCount": len(items) - failed,
                "failedCount": failed,
                "passed": failed == 0,
                "items": items,
            },
        )

    def preview_change(self, arguments: Mapping[str, Any]) -> ToolResponse:
        if self._mutation_planner is None:
            raise HostAccessError("This host adapter does not support detached mutation planning.")
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
        operations = list(arguments.get("operations") or ())
        constraints = list(arguments.get("constraints") or ())
        if not document_id or not expected:
            raise ValueError("documentId and expectedDocumentFingerprint are required")
        before = self._document_model(document_id)
        if fingerprint_model(before) != expected:
            return ToolResponse.failure(
                tool="preview_change",
                effect="read",
                summary="The document changed before preview.",
                code="stale_document",
                message="Read the current document fingerprint and try again.",
                metadata=metadata,
            )
        before_observations, before_metadata, _before_request = collect_constraint_context(
            self._host,
            document_id,
            before,
            constraints,
            phase="before",
            suppressed_errors=(HostAccessError,),
        )
        before_observations = self._with_persistence_observation(
            document_id,
            before,
            before_observations,
            requested_fields=tuple(_before_request.get("fields") or ()),
        )
        before_constraints = evaluate_generic_constraints(
            before,
            constraints,
            phase="before",
            observations=before_observations,
            effective_metadata=before_metadata,
        )
        if not before_constraints["passed"]:
            return ToolResponse.success(
                tool="preview_change",
                effect="read",
                status="review_required",
                summary="The change was not previewed because a precondition failed.",
                metadata=metadata,
                data={
                    "previewId": None,
                    "documentId": document_id,
                    "baseDocumentFingerprint": expected,
                    "proposedFingerprint": None,
                    "applicable": False,
                    "resolvedTargetCount": 0,
                    "normalizedOperations": [],
                    "normalizedOperationCount": 0,
                    "normalizedOperationsTruncated": False,
                    "changeSet": None,
                    "constraints": {
                        "before": before_constraints,
                        "after": None,
                    },
                    "blockers": ["precondition_failed"],
                    "fontSaved": False,
                },
            )
        generic_build = build_generic_change_set(before, operations)
        requested_change_set = generic_build.change_set
        normalized_operations = list(generic_build.normalized_operations)
        capabilities = tuple(
            sorted(
                set(generic_build.capabilities)
                | set(
                    lifecycle_capabilities(
                        requested_change_set, tool="preview_change"
                    )
                )
            )
        )
        diagnostics = unsupported_change_diagnostics(
            requested_change_set,
            limit=100,
            capabilities=capabilities,
        )
        if diagnostics["unsupportedCount"]:
            return ToolResponse.success(
                tool="preview_change",
                effect="read",
                status="review_required",
                summary="The requested operations include unsupported canonical writes.",
                metadata=metadata,
                data={
                    "previewId": None,
                    "documentId": document_id,
                    "baseDocumentFingerprint": expected,
                    "proposedFingerprint": requested_change_set.after_fingerprint,
                    "applicable": False,
                    "resolvedTargetCount": sum(
                        len(item.get("resolvedPaths") or ())
                        for item in normalized_operations
                    ),
                    "normalizedOperations": normalized_operations[
                        :PUBLIC_NORMALIZED_OPERATION_LIMIT
                    ],
                    "normalizedOperationCount": len(normalized_operations),
                    "normalizedOperationsTruncated": len(normalized_operations)
                    > PUBLIC_NORMALIZED_OPERATION_LIMIT,
                    "changeSet": requested_change_set.to_dict(),
                    "constraints": {"before": before_constraints, "after": None},
                    "blockers": ["unsupported_change"],
                    "diagnostics": diagnostics,
                    "fontSaved": False,
                },
            )
        writable = writable_subset(
            before, requested_change_set, capabilities=capabilities
        )
        after_observation_request = constraint_observation_request(
            requested_change_set.apply(before), constraints, phase="after"
        )
        execution_context = dict(generic_build.execution_context)
        if after_observation_request["fields"]:
            execution_context["constraintObservations"] = after_observation_request
        try:
            plan = self._mutation_planner.plan(
                document_id=document_id,
                expected_document_fingerprint=expected,
                requested_change_set=writable,
                operation_id=metadata.operation_id,
                before_model=before,
                capabilities=capabilities,
                execution_context=execution_context,
            )
        except StaleDocumentError:
            return ToolResponse.failure(
                tool="preview_change",
                effect="read",
                summary="The document changed during detached preview.",
                code="stale_document",
                message="Read the current document fingerprint and try again.",
                metadata=metadata,
            )
        except RequestedEffectMismatchError as exc:
            record = self._previews.create(
                kind="change_preview",
                ttl_seconds=REVIEW_TTL_SECONDS,
                payload={
                    "documentId": document_id,
                    "source": "declarative",
                    "baseDocumentFingerprint": expected,
                    "proposedFingerprint": requested_change_set.after_fingerprint,
                    "normalizedOperations": normalized_operations,
                    "constraints": {"before": before_constraints, "after": None},
                    "applicable": False,
                    "diagnostics": exc.to_public_dict(),
                },
            )
            return ToolResponse.success(
                tool="preview_change",
                effect="read",
                status="review_required",
                summary="Detached native execution did not preserve every requested effect.",
                metadata=metadata,
                data={
                    "previewId": record.operation_id,
                    "expiresAt": _iso_timestamp(record.expires_at),
                    "documentId": document_id,
                    "baseDocumentFingerprint": expected,
                    "proposedFingerprint": requested_change_set.after_fingerprint,
                    "applicable": False,
                    "resolvedTargetCount": sum(
                        len(item.get("resolvedPaths") or ())
                        for item in normalized_operations
                    ),
                    "normalizedOperations": normalized_operations[
                        :PUBLIC_NORMALIZED_OPERATION_LIMIT
                    ],
                    "normalizedOperationCount": len(normalized_operations),
                    "normalizedOperationsTruncated": len(normalized_operations)
                    > PUBLIC_NORMALIZED_OPERATION_LIMIT,
                    "changeSet": requested_change_set.to_dict(),
                    "constraints": {"before": before_constraints, "after": None},
                    "blockers": ["requested_effect_mismatch"],
                    "diagnostics": exc.to_public_dict(),
                    "fontSaved": False,
                },
            )
        expected_observations = self._with_persistence_observation(
            document_id,
            plan.expected_after_model,
            plan.expected_observations,
            requested_fields=tuple(after_observation_request.get("fields") or ()),
            dirty=bool(plan.observed_change_set.changes),
        )
        after_constraints = evaluate_generic_constraints(
            plan.expected_after_model,
            constraints,
            phase="after",
            observations=expected_observations,
            effective_metadata=plan.expected_effective_metadata,
        )
        plan = replace(
            plan,
            verification_constraints=tuple(copy.deepcopy(constraints)),
            expected_constraint_evidence=copy.deepcopy(after_constraints),
        )
        applicable = bool(after_constraints["passed"])
        record = self._previews.create(
            kind="change_preview",
            ttl_seconds=REVIEW_TTL_SECONDS,
            payload={
                "documentId": document_id,
                "source": "declarative",
                "baseDocumentFingerprint": expected,
                "proposedFingerprint": plan.after_fingerprint,
                "plan": plan,
                "normalizedOperations": normalized_operations,
                "constraints": {
                    "before": before_constraints,
                    "after": after_constraints,
                },
                "applicable": applicable,
            },
        )
        changes = [public_change_dict(change) for change in plan.observed_change_set.changes]
        first = paginate(
            changes,
            source_fingerprint=plan.after_fingerprint,
            cursor_scope=record.operation_id,
            page_size=100,
        )
        return ToolResponse.success(
            tool="preview_change",
            effect="read",
            status="success" if applicable else "review_required",
            summary=(
                "Created an immutable verified change preview."
                if applicable
                else "The detached result failed one or more postconditions."
            ),
            metadata=metadata,
            page=first.page.to_dict(),
            data={
                "previewId": record.operation_id,
                "expiresAt": _iso_timestamp(record.expires_at),
                "documentId": document_id,
                "baseDocumentFingerprint": expected,
                "proposedFingerprint": plan.after_fingerprint,
                "applicable": applicable,
                "resolvedTargetCount": sum(
                    len(item.get("resolvedPaths") or ())
                    for item in normalized_operations
                ),
                "normalizedOperations": normalized_operations[
                    :PUBLIC_NORMALIZED_OPERATION_LIMIT
                ],
                "normalizedOperationCount": len(normalized_operations),
                "normalizedOperationsTruncated": len(normalized_operations)
                > PUBLIC_NORMALIZED_OPERATION_LIMIT,
                "changeSet": {
                    "beforeFingerprint": plan.before_fingerprint,
                    "afterFingerprint": plan.after_fingerprint,
                    "changeCount": len(changes),
                    "changes": list(first.items),
                },
                "constraints": {
                    "before": before_constraints,
                    "after": after_constraints,
                },
                "blockers": [] if applicable else ["postcondition_failed"],
                "fontSaved": False,
            },
        )

    def apply_change(self, arguments: Mapping[str, Any]) -> ToolResponse:
        if self._transactions is None:
            raise HostAccessError("This host adapter does not support document transactions.")
        metadata = OperationMetadata.create()
        preview_id = str(_value(arguments, "preview_id", "previewId", "") or "")
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
        if not preview_id or not document_id or not expected:
            raise ValueError("previewId, documentId, and expectedDocumentFingerprint are required")
        record = self._previews.get(preview_id)
        if record is None or record.kind != "change_preview":
            return ToolResponse.failure(
                tool="apply_change",
                effect="edit",
                summary="The immutable preview is missing or expired.",
                code="preview_unavailable",
                message="Create a new preview and try again.",
                metadata=metadata,
            )
        payload = record.payload
        if (
            str(payload.get("documentId") or "") != document_id
            or str(payload.get("baseDocumentFingerprint") or "") != expected
        ):
            return ToolResponse.failure(
                tool="apply_change",
                effect="edit",
                summary="The preview belongs to another document state.",
                code="preview_mismatch",
                message="Apply the preview only to its exact source document and fingerprint.",
                metadata=metadata,
            )
        if not bool(payload.get("applicable")):
            return ToolResponse.failure(
                tool="apply_change",
                effect="edit",
                summary="The preview has unresolved blockers.",
                code="preview_blocked",
                message="Resolve the failed constraints and create a new preview.",
                metadata=metadata,
            )
        current = self._document_model(document_id)
        if fingerprint_model(current) != expected:
            return ToolResponse.failure(
                tool="apply_change",
                effect="edit",
                summary="The document changed after preview.",
                code="stale_document",
                message="The exact preview was not applied.",
                metadata=metadata,
            )
        if payload.get("source") == "python_staged":
            if self._python is None:
                raise HostAccessError("This host adapter does not support Python execution.")
            staged_changes = payload.get("changeSet")
            if isinstance(staged_changes, ChangeSet) and not staged_changes.changes:
                self._previews.discard(preview_id)
                receipt = self._audit.record(
                    tool="apply_change",
                    effect="edit",
                    status="success",
                    document_id=document_id,
                    details={
                        "operationId": metadata.operation_id,
                        "previewId": preview_id,
                        "source": "python_staged",
                        "codeHash": payload.get("codeHash"),
                        "observedChangeCount": 0,
                    },
                )
                return ToolResponse.success(
                    tool="apply_change",
                    effect="edit",
                    summary="The staged Python preview contains no document change; no transaction ran.",
                    metadata=metadata,
                    audit_receipt=receipt.to_dict(),
                    data={
                        "operationId": metadata.operation_id,
                        "previewId": preview_id,
                        "documentId": document_id,
                        "beforeFingerprint": expected,
                        "afterFingerprint": expected,
                        "observedChangeCount": 0,
                        "transactionCount": 0,
                        "fontSaved": False,
                        "sourceFileChanged": False,
                        "revert": {"available": False, "operationId": None},
                    },
                )
            response = self._python.apply_staged_preview(
                record,
                operation_id=metadata.operation_id,
                reason=str(_value(arguments, "reason") or ""),
            )
            if response.ok:
                self._previews.discard(preview_id)
            source_data = dict(response.data)
            data = {
                **source_data,
                "operationId": metadata.operation_id,
                "previewId": preview_id,
                "documentId": document_id,
                "observedChangeCount": int(source_data.get("changeCount") or 0),
                "revert": {
                    "available": bool(
                        (source_data.get("rollback") or {}).get("available")
                    ),
                    "operationId": metadata.operation_id if response.ok else None,
                },
            }
            receipt = self._audit.record(
                tool="apply_change",
                effect="edit",
                status=response.status,
                document_id=document_id,
                details={
                    "operationId": metadata.operation_id,
                    "previewId": preview_id,
                    "source": "python_staged",
                    "codeHash": payload.get("codeHash"),
                    "beforeFingerprint": source_data.get("beforeFingerprint"),
                    "afterFingerprint": source_data.get("afterFingerprint"),
                    "observedChangeCount": data["observedChangeCount"],
                    "errorCode": (
                        response.error.code if response.error is not None else None
                    ),
                },
            )
            return replace(
                response,
                tool="apply_change",
                effect="edit",
                metadata=metadata,
                data=data,
                audit_receipt=receipt.to_dict(),
            )
        plan = payload.get("plan")
        if plan is None or not hasattr(plan, "observed_change_set"):
            return ToolResponse.failure(
                tool="apply_change",
                effect="edit",
                summary="The stored preview is incomplete.",
                code="preview_corrupt",
                message="Create a new preview.",
                recoverable=False,
                metadata=metadata,
            )
        if not plan.observed_change_set.changes:
            self._previews.discard(preview_id)
            return ToolResponse.success(
                tool="apply_change",
                effect="edit",
                summary="The preview contains no document change; no transaction ran.",
                metadata=metadata,
                data={
                    "operationId": metadata.operation_id,
                    "previewId": preview_id,
                    "documentId": document_id,
                    "beforeFingerprint": expected,
                    "afterFingerprint": expected,
                    "observedChangeCount": 0,
                    "transactionCount": 0,
                    "fontSaved": False,
                    "revert": {"available": False, "operationId": None},
                },
            )
        exact_plan = replace(plan, operation_id=metadata.operation_id)
        self._trace.bind_document(document_id)
        try:
            result = self._transactions.apply_plan(exact_plan)
        except StaleDocumentError:
            return ToolResponse.failure(
                tool="apply_change",
                effect="edit",
                summary="The document changed before the verified transaction.",
                code="stale_document",
                message="The exact preview was not applied.",
                metadata=metadata,
            )
        except TransactionVerificationError as exc:
            return self._audited_edit_failure(
                tool="apply_change",
                document_id=document_id,
                summary="The exact preview failed read-back verification.",
                code="transaction_failed",
                message="The mutation was not verified.",
                metadata=metadata,
                audit_details=exc.to_public_dict(),
                data=exc.to_public_dict(),
            )
        self._previews.discard(preview_id)
        changes = [
            public_change_dict(change)
            for change in exact_plan.observed_change_set.changes
        ]
        self._operations.create(
            kind="mutation_diff",
            operation_id=metadata.operation_id,
            ttl_seconds=RESULT_TTL_SECONDS,
            payload={
                "items": changes,
                "itemKey": "changes",
                "sourceFingerprint": result.after_fingerprint,
                "metadata": {
                    "documentId": document_id,
                    "operationId": metadata.operation_id,
                    "previewId": preview_id,
                },
            },
        )
        first = paginate(
            changes,
            source_fingerprint=result.after_fingerprint,
            cursor_scope=metadata.operation_id,
            page_size=100,
        )
        receipt = self._audit.record(
            tool="apply_change",
            effect="edit",
            status=(
                "warning"
                if result.persistence_reconciliation.get("relationship")
                in {"saved_intermediate", "source_changed_unclassified"}
                else "success"
            ),
            document_id=document_id,
            details={
                "operationId": metadata.operation_id,
                "previewId": preview_id,
                "reason": _value(arguments, "reason"),
                "beforeFingerprint": result.before_fingerprint,
                "afterFingerprint": result.after_fingerprint,
                "observedChangeCount": result.observed_change_count,
                "previewSource": payload.get("source"),
                "persistenceReconciliation": dict(
                    result.persistence_reconciliation
                ),
            },
        )
        persistence_warning = ()
        if result.persistence_reconciliation.get("relationship") in {
            "saved_intermediate",
            "source_changed_unclassified",
        }:
            persistence_warning = (
                ToolWarning(
                    code="persistence_reconciled",
                    message=(
                        "The source changed while the transaction was active; "
                        "the verified live result was kept and unsaved history "
                        "was rebased to the observed disk state."
                    ),
                    target=dict(result.persistence_reconciliation),
                ),
            )
        return ToolResponse.success(
            tool="apply_change",
            effect="edit",
            status="warning" if persistence_warning else "success",
            summary="Applied the exact immutable preview through one verified transaction; the font was not saved.",
            metadata=metadata,
            audit_receipt=receipt.to_dict(),
            warnings=persistence_warning,
            page=first.page.to_dict(),
            data={
                "operationId": metadata.operation_id,
                "previewId": preview_id,
                "documentId": document_id,
                "beforeFingerprint": result.before_fingerprint,
                "afterFingerprint": result.after_fingerprint,
                "observedChangeCount": result.observed_change_count,
                "observedChangeSet": {
                    "changeCount": len(changes),
                    "changes": list(first.items),
                },
                "canonicalCoverage": result.coverage.to_public_dict(),
                "fontSaved": False,
                "sourceFileChanged": result.source_file_changed,
                "persistenceReconciliation": dict(
                    result.persistence_reconciliation
                ),
                "transactionCount": 1,
                "revert": {
                    "available": result.revert_available,
                    "operationId": (
                        metadata.operation_id if result.revert_available else None
                    ),
                },
            },
        )

    def search_knowledge(self, arguments: Mapping[str, Any]) -> ToolResponse:
        result = search_knowledge_corpus(
            str(arguments.get("query") or ""),
            topics=list(arguments.get("topics") or ()),
            authorities=list(arguments.get("authorities") or ()),
            glyphs_versions=list(
                _value(arguments, "glyphs_versions", "glyphsVersions", ()) or ()
            ),
        )
        items = list(result.pop("items"))
        source_fingerprint = str(result["manifest"]["corpusFingerprint"])
        cursor_scope = fingerprint_model(
            {
                "tool": "search_knowledge",
                "query": result["query"],
                "filters": result["filters"],
                "corpus": source_fingerprint,
            }
        )
        page = paginate(
            items,
            source_fingerprint=source_fingerprint,
            cursor_scope=cursor_scope,
            page_size=int(_value(arguments, "page_size", "pageSize", 20)),
            cursor=_value(arguments, "cursor"),
        )
        return ToolResponse.success(
            tool="search_knowledge",
            effect="read",
            summary="Returned {} of {} pinned Knowledge match(es).".format(
                len(page.items), len(items)
            ),
            page=page.page.to_dict(),
            data={**result, "items": list(page.items)},
        )

    def get_knowledge(self, arguments: Mapping[str, Any]) -> ToolResponse:
        entry_ids = list(_value(arguments, "entry_ids", "entryIds", ()) or ())
        result = read_knowledge_entries(entry_ids)
        warnings = (
            (
                ToolWarning(
                    code="knowledge_entries_missing",
                    message="One or more requested Knowledge IDs were not found.",
                    target={"missingIds": list(result["missingIds"])},
                ),
            )
            if result["missingIds"]
            else ()
        )
        return ToolResponse.success(
            tool="get_knowledge",
            effect="read",
            status="warning" if warnings else "success",
            summary="Returned {} of {} requested Knowledge entries.".format(
                result["foundCount"], result["requestedCount"]
            ),
            warnings=warnings,
            data=result,
        )

    def get_server_info(self, arguments: Mapping[str, Any]) -> ToolResponse:
        runtime = self._host.runtime_snapshot()
        scripting_safety = _scripting_runtime_safety(self._host)
        return ToolResponse.success(
            tool="get_server_info",
            effect="read",
            summary="Glyphs MCP {} is available with {} open document(s).".format(API_VERSION, runtime.open_document_count),
            data={
                "serverName": SERVER_NAME,
                "serverVersion": SERVER_VERSION,
                "apiMajor": API_MAJOR,
                "apiVersion": API_VERSION,
                "canonicalModelSchemaVersion": CANONICAL_MODEL_SCHEMA_VERSION,
                "runtimeIdentity": dict(loaded_runtime_identity()),
                "knowledge": knowledge_manifest(),
                "registries": {
                    **public_mechanics_registry(),
                    **detached_python_registry_for_host(self._host),
                },
                "capabilities": [
                    "stable_document_ids",
                    "generic_selectors",
                    "predicate_selectors",
                    "generic_projections",
                    "generic_reducers",
                    "generic_constraints",
                    "immutable_change_previews",
                    "exact_preview_apply",
                    "pinned_searchable_knowledge",
                    "fingerprint_bound_pagination",
                    "verified_transactions",
                    "save_tolerant_transactions",
                    "persistence_observations",
                    "permanent_python_fallback",
                    "detached_read_only_python",
                    "staged_python_previews",
                    "live_open_world_python",
                    "canonical_change_history",
                    "identity_structural_changes",
                    "source_file_fingerprints",
                    "recoverable_scripting_runtime",
                    "verified_document_activation",
                ],
                "host": runtime.to_dict(),
                "scriptingRuntimeSafety": {
                    key: scripting_safety[key]
                    for key in (
                        "state",
                        "mode",
                        "strictInterlockAvailable",
                        "livePythonAvailable",
                        "stagedPythonAvailable",
                        "automaticRepairAvailable",
                        "incidentId",
                        "affectedSlotCount",
                        "nextAction",
                    )
                },
            },
        )

    def get_runtime_status(
        self, arguments: Mapping[str, Any]
    ) -> ToolResponse:
        status = _scripting_runtime_safety(self._host)
        return ToolResponse.success(
            tool="get_runtime_status",
            effect="read",
            status="success" if status.get("state") == "healthy" else "warning",
            summary=(
                "The strict scripting interlock is healthy."
                if status.get("state") == "healthy"
                else "The strict scripting interlock requires recovery."
            ),
            data=status,
        )

    def repair_runtime(
        self, arguments: Mapping[str, Any]
    ) -> ToolResponse:
        repair = getattr(self._host, "repair_scripting_runtime", None)
        if not callable(repair):
            raise HostAccessError(
                "This host adapter does not expose scripting runtime repair."
            )
        expected_value = _value(
            arguments, "expected_incident_id", "expectedIncidentId"
        )
        expected_incident_id = (
            None if expected_value is None else str(expected_value or "")
        )
        if expected_incident_id == "":
            raise ValueError("expectedIncidentId must be non-empty when supplied")
        reason_value = _value(arguments, "reason")
        reason = None if reason_value is None else str(reason_value or "").strip()
        try:
            result = repair(
                expected_incident_id=expected_incident_id,
                trigger="agent",
            )
        except StaleScriptingRuntimeIncidentError as exc:
            status = _scripting_runtime_safety(self._host)
            receipt = self._audit.record(
                tool="repair_runtime",
                effect="code",
                status="error",
                document_id=None,
                details={
                    "reason": reason,
                    "expectedIncidentId": expected_incident_id,
                    "errorCode": "stale_scripting_runtime_incident",
                    "scriptingRuntimeSafety": status,
                },
            )
            return ToolResponse.failure(
                tool="repair_runtime",
                effect="code",
                summary="The scripting safety incident changed before repair.",
                code="stale_scripting_runtime_incident",
                message=str(exc),
                data={"scriptingRuntimeSafety": status},
                audit_receipt=receipt.to_dict(),
            )
        if not isinstance(result, Mapping):
            raise HostAccessError("Scripting runtime repair returned no status.")
        repair_value = result.get("repair")
        status_value = result.get("scriptingRuntimeSafety")
        if not isinstance(repair_value, Mapping) or not isinstance(
            status_value, Mapping
        ):
            raise HostAccessError("Scripting runtime repair evidence is incomplete.")
        repair_data = dict(repair_value)
        status_data = dict(status_value)
        outcome = str(repair_data.get("result") or "")
        ok = status_data.get("state") == "healthy"
        receipt = self._audit.record(
            tool="repair_runtime",
            effect="code",
            status="success" if ok else "error",
            document_id=None,
            details={
                "reason": reason,
                "expectedIncidentId": expected_incident_id,
                "repair": repair_data,
                "scriptingRuntimeSafety": status_data,
            },
        )
        data = {
            "repair": repair_data,
            "scriptingRuntimeSafety": status_data,
        }
        if ok:
            return ToolResponse.success(
                tool="repair_runtime",
                effect="code",
                summary=str(repair_data.get("message") or "Scripting runtime repaired."),
                data=data,
                audit_receipt=receipt.to_dict(),
            )
        return ToolResponse.failure(
            tool="repair_runtime",
            effect="code",
            summary="Scripting runtime repair did not restore strict coverage.",
            code=(
                "scripting_runtime_busy"
                if outcome == "busy"
                else "scripting_runtime_repair_incomplete"
            ),
            message=str(
                repair_data.get("message")
                or "Strict scripting safety remains unavailable."
            ),
            data=data,
            audit_receipt=receipt.to_dict(),
        )


    def open_document_view(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(
            _value(arguments, "document_id", "documentId", "") or ""
        )
        raw_names = _value(arguments, "glyph_names", "glyphNames")
        if not isinstance(raw_names, (list, tuple)):
            raise ValueError("glyphNames must be a list")
        if not 1 <= len(raw_names) <= 64:
            raise ValueError("glyphNames must contain between 1 and 64 names")
        if any(not isinstance(name, str) or not name.strip() for name in raw_names):
            raise ValueError("glyphNames must contain non-empty strings")
        glyph_names = tuple(raw_names)
        if len(set(glyph_names)) != len(glyph_names):
            raise ValueError("glyphNames must not contain duplicates")
        master_value = _value(arguments, "master_id", "masterId")
        master_id = None if master_value is None else str(master_value)
        if master_id == "":
            raise ValueError("masterId must be non-empty when supplied")
        activate_document = _value(
            arguments, "activate_document", "activateDocument", False
        )
        if not isinstance(activate_document, bool):
            raise ValueError("activateDocument must be a boolean")

        before = self._document_model(document_id)
        glyphs = before.get("glyphs", {})
        available_glyphs = (
            {str(name) for name in glyphs}
            if isinstance(glyphs, Mapping)
            else {
                str(glyph.get("name") or "")
                for glyph in glyphs
                if isinstance(glyph, Mapping)
            }
        )
        missing = [name for name in glyph_names if name not in available_glyphs]
        if missing:
            return ToolResponse.failure(
                tool="open_document_view",
                effect="ui",
                summary="The Edit tab was not opened because glyph targets are missing.",
                code="target_not_found",
                message="Unknown glyph name(s): {}.".format(", ".join(missing)),
                data={"documentId": document_id, "missingGlyphNames": missing},
            )
        if master_id is not None:
            masters = before.get("masters", ())
            master_ids = {
                str(master.get("id") or "")
                for master in (
                    masters.values() if isinstance(masters, Mapping) else masters
                )
                if isinstance(master, Mapping)
            }
            if master_id not in master_ids:
                return ToolResponse.failure(
                    tool="open_document_view",
                    effect="ui",
                    summary="The Edit tab was not opened because the master is missing.",
                    code="target_not_found",
                    message="The requested master is not part of the document.",
                    data={"documentId": document_id, "masterId": master_id},
                )

        opener = getattr(self._host, "open_edit_tab", None)
        if not callable(opener):
            raise HostAccessError("This host adapter cannot open Glyphs Edit tabs.")
        activation_reader = getattr(self._host, "document_activation_state", None)
        if not callable(activation_reader):
            raise HostAccessError(
                "This host adapter cannot verify the active Glyphs document."
            )

        def activation_state() -> dict[str, Any]:
            value = activation_reader(document_id)
            if not isinstance(value, Mapping):
                raise HostAccessError(
                    "The host adapter returned invalid document activation evidence."
                )
            active = value.get("active")
            if not isinstance(active, bool):
                raise HostAccessError(
                    "The host adapter did not verify the active Glyphs document."
                )
            for field in (
                "currentDocumentMatchesTarget",
                "activeFontMatchesTarget",
                "signalsAgree",
            ):
                if not isinstance(value.get(field), bool):
                    raise HostAccessError(
                        "The host adapter returned incomplete document activation "
                        "evidence."
                    )
            if active != bool(
                value["currentDocumentMatchesTarget"]
                and value["activeFontMatchesTarget"]
            ):
                raise HostAccessError(
                    "The host adapter returned inconsistent document activation "
                    "evidence."
                )
            active_document_id = value.get("activeDocumentId")
            if active_document_id is not None and not isinstance(
                active_document_id, str
            ):
                raise HostAccessError(
                    "The host adapter returned an invalid active document ID."
                )
            return dict(value)

        activation_before = activation_state()
        open_evidence = opener(
            document_id,
            glyph_names,
            master_id=master_id,
            activate_document=activate_document,
        )
        if open_evidence is None:
            open_evidence = {}
        if not isinstance(open_evidence, Mapping):
            raise HostAccessError(
                "The host adapter returned invalid Edit-tab evidence."
            )
        activation_after = activation_state()

        capture = getattr(self._host, "capture_stable_snapshot", None)
        if not callable(capture):
            capture = getattr(self._host, "capture_snapshot", None)
        if not callable(capture):
            capture = getattr(self._host, "capture_model", None)
        if not callable(capture):
            raise HostAccessError("This host adapter does not expose document snapshots.")
        after = capture(document_id)
        changes = diff_models(before, after)
        self._trace.observe_transition(
            document_id,
            before,
            after,
            change_set=changes,
            coverage=CanonicalCoverage.complete(),
        )
        changed = bool(changes.changes)
        warnings = (
            (
                ToolWarning(
                    code="document_changed_during_ui_action",
                    message=(
                        "The Edit tab opened, but the document also changed; "
                        "inspect the recorded semantic transition."
                    ),
                    target={"changeCount": len(changes.changes)},
                ),
            )
            if changed
            else ()
        )
        data = {
            "documentId": document_id,
            "glyphNames": list(glyph_names),
            "glyphCount": len(glyph_names),
            "masterId": master_id,
            "openedView": True,
            "activationRequested": activate_document,
            "activationAttempted": bool(
                open_evidence.get("activationAttempted", False)
            ),
            "activationMethods": list(
                open_evidence.get("activationMethods") or ()
            ),
            "activationErrors": list(
                open_evidence.get("activationErrors") or ()
            ),
            "activeBefore": activation_before["active"],
            "activeAfter": activation_after["active"],
            "activeDocumentIdBefore": activation_before.get("activeDocumentId"),
            "activeDocumentIdAfter": activation_after.get("activeDocumentId"),
            "currentDocumentMatchedBefore": activation_before[
                "currentDocumentMatchesTarget"
            ],
            "currentDocumentMatchedAfter": activation_after[
                "currentDocumentMatchesTarget"
            ],
            "activeFontMatchedBefore": activation_before[
                "activeFontMatchesTarget"
            ],
            "activeFontMatchedAfter": activation_after[
                "activeFontMatchesTarget"
            ],
            "activationSignalsAgreedBefore": activation_before["signalsAgree"],
            "activationSignalsAgreedAfter": activation_after["signalsAgree"],
            "activationVerified": (
                activation_after["active"] if activate_document else None
            ),
            "beforeFingerprint": changes.before_fingerprint,
            "afterFingerprint": changes.after_fingerprint,
            "documentChanged": changed,
            "observedChangeCount": len(changes.changes),
            "fontSaved": False,
        }
        if activate_document and not activation_after["active"]:
            return ToolResponse.failure(
                tool="open_document_view",
                effect="ui",
                summary=(
                    "The Edit tab opened, but Glyphs did not activate the "
                    "requested document."
                ),
                code="document_activation_failed",
                message=(
                    "Glyphs.currentDocument did not resolve to the requested "
                    "document after the activation attempt."
                ),
                details={
                    "documentId": document_id,
                    "activeDocumentId": activation_after.get("activeDocumentId"),
                },
                warnings=warnings,
                data=data,
            )

        return ToolResponse.success(
            tool="open_document_view",
            effect="ui",
            status="warning" if changed else "success",
            summary=(
                "Opened {} glyph(s) and activated the target Glyphs document."
                if activate_document
                else "Opened {} glyph(s) in a Glyphs Edit tab."
            ).format(len(glyph_names)),
            warnings=warnings,
            data=data,
        )


    def document_was_saved(
        self,
        document_id: str,
        *,
        correlation_token: str | None = None,
        source_path: str | None = None,
    ) -> bool:
        """Enqueue native-save convenience work without delaying Glyphs."""

        identity = str(document_id or "")

        def record(_context=None) -> bool:
            return self.lifecycle.document_was_saved(
                identity,
                make_copy=False,
                succeeded=True,
                correlation_token=correlation_token,
                source_state=(
                    {"filePath": source_path} if source_path else None
                ),
                saved_model=None,
            )

        if self._saved_sources is not None and source_path:
            self._saved_sources.resume_after_save(source_path)
        coordinator = getattr(self._saved_sources, "coordinator", None)
        if coordinator is not None:
            key = (source_path, identity) if source_path else identity
            return bool(
                coordinator.submit(
                    "history",
                    key,
                    record,
                    delay=0.25,
                )
            )
        return record()

    def document_was_closed(self, document_id: str) -> bool:
        """Enqueue process-local pruning after a native document close."""

        identity = str(document_id or "")
        coordinator = getattr(self._saved_sources, "coordinator", None)
        if coordinator is not None:
            return bool(
                coordinator.submit(
                    "cleanup",
                    ("document", identity),
                    lambda _context: self.lifecycle.document_was_closed(identity),
                )
            )
        return self.lifecycle.document_was_closed(identity)

    def save_document(self, arguments: Mapping[str, Any]) -> ToolResponse:
        # Save is a history boundary even when confirmation, stale-state, or
        # native verification refuses it. Save attempts never become visible
        # no-op commits and never emit history_not_recorded.
        self._trace.mark_history_boundary()
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
        reason = str(_value(arguments, "reason", default="") or "").strip()
        if not document_id or not expected:
            raise ValueError("documentId and expectedDocumentFingerprint are required")
        if not reason:
            raise ValueError("reason is required and must not be blank")
        if not bool(arguments.get("confirm")):
            return self._audited_save_failure(
                document_id=document_id,
                summary="The document was not saved because confirmation is missing.",
                code="confirmation_required",
                message="Call save_document with confirm=true after reading current fingerprints.",
                metadata=metadata,
                reason=reason,
            )
        overwrite_policy = str(
            _value(arguments, "overwrite_policy", "overwritePolicy", "fail_if_exists")
            or "fail_if_exists"
        )
        if overwrite_policy not in SAVE_OVERWRITE_POLICIES:
            raise ValueError("overwritePolicy must be fail_if_exists or replace_if_match")

        before = self._document_model(document_id)
        before_fingerprint = fingerprint_model(before)
        if before_fingerprint != expected:
            return self._audited_save_failure(
                document_id=document_id,
                summary="The document changed before it could be saved.",
                code="stale_document",
                message="Read the current document fingerprint and try again.",
                metadata=metadata,
                reason=reason,
                details={
                    "expectedDocumentFingerprint": expected,
                    "observedDocumentFingerprint": before_fingerprint,
                },
            )
        saver = getattr(self._host, "save_document", None)
        if not callable(saver):
            raise HostAccessError("This host adapter does not implement document saves.")
        if self._saved_sources is not None:
            barrier_paths = {
                str(value)
                for value in (
                    _value(arguments, "destination"),
                    (
                        getattr(self._host, "source_path_for_document")(document_id)
                        if callable(
                            getattr(self._host, "source_path_for_document", None)
                        )
                        else None
                    ),
                )
                if value
            }
            for barrier_path in barrier_paths:
                self._saved_sources.pause_for_save(barrier_path)
        try:
            save_token = self.lifecycle.begin_tool_save(document_id)
        except RuntimeError:
            return self._audited_save_failure(
                document_id=document_id,
                summary="Another save is already active for this document.",
                code="save_in_progress",
                message="Wait for the active save to finish and try again.",
                metadata=metadata,
                reason=reason,
            )

        result: Mapping[str, Any]
        try:
            self.activity.advance_current(
                "saving", "Saving the Glyphs document", cancellable=False
            )
            result = saver(
                document_id,
                expected_document_fingerprint=expected,
                destination=_value(arguments, "destination"),
                expected_source_file_fingerprint=_value(
                    arguments,
                    "expected_source_file_fingerprint",
                    "expectedSourceFileFingerprint",
                ),
                overwrite_policy=overwrite_policy,
                expected_destination_file_fingerprint=_value(
                    arguments,
                    "expected_destination_file_fingerprint",
                    "expectedDestinationFileFingerprint",
                ),
                notification_correlation_token=save_token,
                expected_snapshot=(
                    before if isinstance(before, CanonicalSnapshot) else None
                ),
            )
        except DocumentSaveError as exc:
            lifecycle = self.lifecycle.complete_tool_save(
                document_id,
                save_token,
                verified=False,
                expect_notification=exc.write_attempted,
            )
            failure_data = {
                "saveAttempted": exc.write_attempted,
                "saveVerified": False,
                "fontSaved": False,
                "stateMayHaveChanged": exc.write_attempted,
                "notificationObserved": lifecycle["notificationObserved"],
                **dict(exc.details),
            }
            return self._audited_save_failure(
                document_id=document_id,
                summary="The document save was refused or could not be verified.",
                code=exc.code,
                message=exc.message,
                recoverable=exc.recoverable,
                metadata=metadata,
                reason=reason,
                details=exc.details,
                data=failure_data,
            )
        except Exception:
            self.lifecycle.complete_tool_save(
                document_id, save_token, verified=False
            )
            raise

        saved_model = result.get("savedModel")
        saved_snapshot = result.get("savedSnapshot")
        if not isinstance(saved_model, Mapping):
            lifecycle = self.lifecycle.complete_tool_save(
                document_id,
                save_token,
                verified=False,
                expect_notification=bool(result.get("nativeSaveSucceeded")),
            )
            return self._audited_save_failure(
                document_id=document_id,
                summary="Glyphs returned from saving without canonical source proof.",
                code="save_verification_failed",
                message="The saved source could not be decoded and compared.",
                recoverable=False,
                metadata=metadata,
                reason=reason,
                data={
                    "saveAttempted": True,
                    "fontSaved": True,
                    "saveVerified": False,
                    "stateMayHaveChanged": True,
                    "notificationObserved": lifecycle["notificationObserved"],
                },
            )
        try:
            after_fingerprint = fingerprint_model(saved_model)
        except Exception as exc:
            lifecycle = self.lifecycle.complete_tool_save(
                document_id,
                save_token,
                verified=False,
                expect_notification=bool(result.get("nativeSaveSucceeded")),
            )
            failure_data = {
                key: _public_payload(value)
                for key, value in result.items()
                if key not in {"savedModel", "savedSnapshot"}
            }
            failure_data.update(
                {
                    "saveAttempted": True,
                    "fontSaved": bool(result.get("nativeSaveSucceeded")),
                    "saveVerified": False,
                    "stateMayHaveChanged": True,
                    "notificationObserved": lifecycle["notificationObserved"],
                }
            )
            return self._audited_save_failure(
                document_id=document_id,
                summary="The saved canonical source proof is invalid.",
                code="save_verification_failed",
                message="The saved source could not be fingerprinted canonically.",
                recoverable=False,
                metadata=metadata,
                reason=reason,
                details={"exceptionType": type(exc).__name__},
                data=failure_data,
            )
        document_changed = after_fingerprint != before_fingerprint
        save_mode = str(result.get("saveMode") or "")
        previous_file_path = str(result.get("previousFilePath") or "")
        saved_file_path = str(result.get("filePath") or "")
        requested_destination = str(
            _value(arguments, "destination", default="") or ""
        )

        def same_reported_path(left: str, right: str) -> bool:
            if not left or not right:
                return False
            # The adapter canonicalizes macOS' stable /tmp and /var aliases to
            # /private/... before invoking NSDocument. Compare the resolved
            # filesystem locations so a truthful native path does not turn a
            # verified Save As into a false failure. User-controlled links are
            # still rejected by the adapter before the native write.
            return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
                os.path.realpath(right)
            )

        path_evidence_valid = bool(saved_file_path)
        if save_mode == "save":
            path_evidence_valid = bool(
                path_evidence_valid
                and previous_file_path
                and same_reported_path(previous_file_path, saved_file_path)
                and not bool(result.get("pathChanged"))
            )
        elif save_mode == "save_as":
            path_evidence_valid = bool(
                path_evidence_valid
                and bool(result.get("pathChanged"))
                and (
                    not previous_file_path
                    or not same_reported_path(previous_file_path, saved_file_path)
                )
            )
        if requested_destination:
            path_evidence_valid = bool(
                path_evidence_valid
                and same_reported_path(requested_destination, saved_file_path)
            )
        original_source_proven = bool(
            save_mode != "save_as"
            or not previous_file_path
            or result.get("originalSourceUnchanged") is True
        )
        verification_failed = bool(
            save_mode not in {"save", "save_as"}
            or document_changed
            or result.get("dirtyAfter") is not False
            or not result.get("nativeSaveSucceeded")
            or not result.get("savedSourceFingerprint")
            or not path_evidence_valid
            or (
                save_mode == "save_as"
                and result.get("destinationChanged") is not True
            )
            or not original_source_proven
        )
        if verification_failed:
            lifecycle = self.lifecycle.complete_tool_save(
                document_id,
                save_token,
                verified=False,
                expect_notification=bool(result.get("nativeSaveSucceeded")),
            )
            failure_data = {
                key: _public_payload(value)
                for key, value in result.items()
                if key not in {"savedModel", "savedSnapshot"}
            }
            failure_data.update(
                {
                    "beforeFingerprint": before_fingerprint,
                    "afterFingerprint": after_fingerprint,
                    "documentChanged": document_changed,
                    "saveVerified": False,
                    "fontSaved": bool(result.get("nativeSaveSucceeded")),
                    "stateMayHaveChanged": True,
                    "notificationObserved": lifecycle["notificationObserved"],
                }
            )
            return self._audited_save_failure(
                document_id=document_id,
                summary="Glyphs saved bytes, but the complete save contract was not verified.",
                code="save_verification_failed",
                message="Inspect the current path, dirty state, and source fingerprints before retrying.",
                recoverable=False,
                metadata=metadata,
                reason=reason,
                data=failure_data,
            )

        if (
            self._saved_sources is not None
            and isinstance(saved_snapshot, SavedSourceSnapshot)
            and saved_snapshot.source_fingerprint
            == result.get("savedSourceFingerprint")
        ):
            self._saved_sources.publish_verified(saved_snapshot)
            self._saved_sources.coordinator.resume_after_save(
                saved_snapshot.path, delay=0.25
            )
        lifecycle = self.lifecycle.complete_tool_save(
            document_id,
            save_token,
            verified=True,
            expect_notification=True,
            source_state={
                "kind": result.get("fileKind"),
                "exists": True,
                "readable": True,
                "contentFingerprint": result.get("savedSourceFingerprint"),
                "filePath": result.get("filePath"),
            },
            saved_model=saved_model,
        )
        public_result = {
            key: _public_payload(value)
            for key, value in result.items()
            if key not in {"savedModel", "savedSnapshot"}
        }
        data = {
            "operationId": metadata.operation_id,
            "documentId": document_id,
            **public_result,
            "beforeFingerprint": before_fingerprint,
            "afterFingerprint": after_fingerprint,
            "saveAttempted": True,
            "nativeSaveSucceeded": True,
            "saveVerified": True,
            "fontSaved": True,
            "documentChanged": False,
            "notificationObserved": lifecycle["notificationObserved"],
            "historyReset": lifecycle["historyReset"],
            "changeTrackingReset": lifecycle["changeTrackingReset"],
            "historyRecorded": False,
        }
        self._operations.create(
            kind="document_save",
            operation_id=metadata.operation_id,
            ttl_seconds=RESULT_TTL_SECONDS,
            payload=data,
        )
        status = (
            "success"
            if lifecycle["historyReset"] and lifecycle["changeTrackingReset"]
            else "warning"
        )
        warnings = ()
        if status == "warning":
            warnings = (
                ToolWarning(
                    code="save_history_cleanup_incomplete",
                    message=(
                        "The source was saved and verified, but process-local "
                        "change-history cleanup did not complete."
                    ),
                    target={"documentId": document_id},
                ),
            )
        receipt = self._audit.record(
            tool="save_document",
            effect="save",
            status=status,
            document_id=document_id,
            details={
                "operationId": metadata.operation_id,
                "reason": reason,
                "saveMode": data.get("saveMode"),
                "beforeFingerprint": before_fingerprint,
                "afterFingerprint": after_fingerprint,
                "previousSourceFingerprint": data.get("previousSourceFingerprint"),
                "savedSourceFingerprint": data.get("savedSourceFingerprint"),
                "historyReset": data.get("historyReset"),
            },
        )
        return ToolResponse.success(
            tool="save_document",
            effect="save",
            status=status,
            summary=(
                "Saved the Glyphs document synchronously and verified the published source."
            ),
            metadata=metadata,
            warnings=warnings,
            audit_receipt=receipt.to_dict(),
            data=data,
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
            changes = [public_change_dict(change) for change in commit.change_set.changes]
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























    def preview_export(self, arguments: Mapping[str, Any]) -> ToolResponse:
        document_id = str(_value(arguments, "document_id", "documentId", "") or "")
        model = self._document_model(document_id)
        compatibility_mode = str(
            _value(
                arguments,
                "compatibility_mode",
                "compatibilityMode",
                "component_preserving",
            )
        )

        destination = str(_value(arguments, "destination", default="") or "")
        inspector = getattr(self._host, "inspect_export_destination", None)
        destination_state = inspector(destination) if callable(inspector) else dict(arguments.get("destination_state") or {"exists": False, "empty": True, "fingerprint": None})
        overwrite_policy = str(
            _value(
                arguments,
                "overwrite_policy",
                "overwritePolicy",
                "fail_if_nonempty",
            )
        )
        if overwrite_policy not in {"fail_if_nonempty", "replace_if_match"}:
            raise ValueError("unsupported overwrite policy")
        expected_destination_fingerprint = _value(
            arguments,
            "expected_destination_fingerprint",
            "expectedDestinationFingerprint",
        )
        blocking_codes: list[str] = []
        destination_exists = bool(destination_state.get("exists"))
        destination_empty = bool(
            destination_state.get("empty", not destination_exists)
        )
        if destination_exists and destination_state.get("kind") not in {
            None,
            "directory",
        }:
            blocking_codes.append("destination_not_directory")
        if destination_exists and not destination_empty:
            if overwrite_policy == "fail_if_nonempty":
                blocking_codes.append("destination_not_empty")
            elif (
                not expected_destination_fingerprint
                or expected_destination_fingerprint
                != destination_state.get("fingerprint")
            ):
                blocking_codes.append("destination_fingerprint_mismatch")
        result = {
            "ready": not blocking_codes,
            "blockingCodes": blocking_codes,
            "overwritePolicy": overwrite_policy,
        }
        document_fingerprint = fingerprint_model(model)
        runtime_versions = _export_runtime_versions(self._host)
        capture_source = getattr(self._host, "capture_source_file_state", None)
        source_state = capture_source(document_id) if callable(capture_source) else None
        source_fingerprint = (
            source_state.get("contentFingerprint")
            if isinstance(source_state, Mapping)
            and source_state.get("exists")
            and source_state.get("readable")
            else None
        )
        preflight = {
            "status": "skipped",
            "targetKinds": [],
            "bundleFingerprint": None,
            "manifestTreeSha256": None,
            "manifestSha256": None,
            "manifestSize": 0,
            "manifestFileCount": 0,
            "featureFileCount": 0,
            "ufoCount": 0,
            "designspaceFileCount": 0,
            "masterUFOCount": 0,
            "braceUFOCount": 0,
            "supportFileCount": 0,
            "error": None,
        }
        if result["ready"]:
            preflight_exporter = getattr(self._host, "preflight_source_bundle", None)
            if not callable(preflight_exporter):
                raise HostAccessError(
                    "This host adapter does not implement source-bundle preflight."
                )
            try:
                preflight_result = dict(
                    preflight_exporter(
                        {
                            "documentId": document_id,
                            "documentFingerprint": document_fingerprint,
                            "sourceFingerprint": source_fingerprint,
                            "canonicalModel": model,
                            "compatibilityMode": compatibility_mode,
                            "runtimeVersions": runtime_versions,
                        }
                    )
                )
                preflight.update(
                    {
                        "status": "passed",
                        "targetKinds": list(preflight_result.get("targetKinds") or []),
                        "bundleFingerprint": preflight_result.get("bundleFingerprint"),
                        "manifestTreeSha256": preflight_result.get("manifestTreeSha256"),
                        "manifestSha256": preflight_result.get("manifestSha256"),
                        "manifestSize": int(preflight_result.get("manifestSize") or 0),
                        "manifestFileCount": int(preflight_result.get("manifestFileCount") or 0),
                        "featureFileCount": int(
                            preflight_result.get("preflight", {}).get("featureFileCount")
                            or 0
                        ),
                        "ufoCount": int(
                            preflight_result.get("preflight", {}).get("ufoCount") or 0
                        ),
                        "designspaceFileCount": len(
                            preflight_result.get("designspaceFiles") or []
                        ),
                        "masterUFOCount": len(
                            preflight_result.get("masterUFOs") or []
                        ),
                        "braceUFOCount": len(
                            preflight_result.get("braceUFOs") or []
                        ),
                        "supportFileCount": len(
                            preflight_result.get("supportFiles") or []
                        ),
                    }
                )
                required_preflight_values = (
                    "bundleFingerprint",
                    "manifestTreeSha256",
                    "manifestSha256",
                )
                if any(not preflight[key] for key in required_preflight_values):
                    raise SourceBundleError(
                        "preflight_result_invalid",
                        "Source-bundle preflight did not return its required fingerprints.",
                    )
            except SourceBundleError as exc:
                preflight.update(
                    {
                        "status": "failed",
                        "bundleFingerprint": None,
                        "manifestTreeSha256": None,
                        "manifestSha256": None,
                        "error": exc.to_dict(),
                    }
                )
                result["ready"] = False
                result["blockingCodes"] = sorted(
                    set(result.get("blockingCodes", ()))
                    | {"source_bundle_preflight_failed"}
                )
        plan = ExportPlan(
            document_id=document_id,
            document_fingerprint=document_fingerprint,
            destination=destination,
            destination_state=destination_state,
            overwrite_policy=str(result["overwritePolicy"]),
            compatibility_mode=compatibility_mode,
            source_fingerprint=(
                str(source_fingerprint) if source_fingerprint else None
            ),
            runtime_versions=runtime_versions,
            reviewed_bundle_fingerprint=preflight.get("bundleFingerprint"),
            reviewed_manifest_tree_sha256=preflight.get("manifestTreeSha256"),
            reviewed_manifest_sha256=preflight.get("manifestSha256"),
        )
        preview = self._operations.create(
            kind="export_preview",
            ttl_seconds=REVIEW_TTL_SECONDS,
            payload={
                **plan.to_payload(),
                "review": result,
                "preflight": preflight,
            },
        )
        return ToolResponse.success(
            tool="preview_export",
            effect="read",
            status="review_required" if result["ready"] else "warning",
            summary="Export review is ready for confirmation." if result["ready"] else "Export review found blocking conditions.",
            data={
                "previewId": preview.operation_id,
                "expiresAt": _iso_timestamp(preview.expires_at),
                **result,
                "bundleLayoutVersion": BUNDLE_LAYOUT_VERSION,
                "compatibilityMode": compatibility_mode,
                "preflight": preflight,
            },
        )

    def apply_export(self, arguments: Mapping[str, Any]) -> ToolResponse:
        preview_id = str(_value(arguments, "preview_id", "previewId", "") or "")
        if not preview_id:
            raise ValueError("previewId is required")
        preview = self._operations.consume(preview_id)
        if preview is None or preview.kind != "export_preview":
            return ToolResponse.failure(
                tool="apply_export",
                effect="files",
                summary="The export preview is missing, expired, or consumed.",
                code="preview_unavailable",
                message="Export preview unavailable.",
            )
        payload = preview.payload
        if not payload.get("review", {}).get("ready"):
            return ToolResponse.failure(
                tool="apply_export",
                effect="files",
                summary="The reviewed export still has blocking conditions.",
                code="export_blocked",
                message="Resolve the reviewed blockers first.",
            )
        current = self._document_model(str(payload["documentId"]))
        if fingerprint_model(current) != payload.get("documentFingerprint"):
            return ToolResponse.failure(
                tool="apply_export",
                effect="files",
                summary="The document changed after export review.",
                code="stale_document",
                message="Export review is stale.",
            )
        current_runtime_versions = _export_runtime_versions(self._host)
        if current_runtime_versions != payload.get("runtimeVersions"):
            return ToolResponse.failure(
                tool="apply_export",
                effect="files",
                summary="The Glyphs runtime changed after export review.",
                code="runtime_changed",
                message="Create a new export review in the current runtime.",
            )
        reviewed_source_fingerprint = payload.get("sourceFingerprint")
        if reviewed_source_fingerprint:
            capture_source = getattr(self._host, "capture_source_file_state", None)
            current_source = (
                capture_source(str(payload["documentId"]))
                if callable(capture_source)
                else None
            )
            if (
                not isinstance(current_source, Mapping)
                or current_source.get("contentFingerprint")
                != reviewed_source_fingerprint
            ):
                return ToolResponse.failure(
                    tool="apply_export",
                    effect="files",
                    summary="The Glyphs source file changed after export review.",
                    code="source_changed",
                    message="Create a new export review for the current source bytes.",
                )
        inspector = getattr(self._host, "inspect_export_destination", None)
        if not callable(inspector):
            raise HostAccessError("This host adapter does not inspect export destinations.")
        destination_state = inspector(str(payload.get("destination") or ""))
        if not destination_matches(destination_state, payload.get("destinationState", {})):
            return ToolResponse.failure(
                tool="apply_export",
                effect="files",
                summary="The destination changed after export review; nothing was published.",
                code="destination_changed",
                message="Create a new export review for the current destination fingerprint.",
            )
        exporter = getattr(self._host, "export_source_bundle", None)
        if not callable(exporter):
            raise HostAccessError("This host adapter does not implement source-bundle export.")
        try:
            result = exporter(
                {
                    **dict(payload),
                    # The reviewed model is never persisted as staging state.
                    # Confirmation captures it again and hands this one immutable
                    # snapshot to the deterministic regeneration call.
                    "canonicalModel": current,
                    "runtimeVersions": current_runtime_versions,
                }
            )
        except SourceBundleError as exc:
            return ToolResponse.failure(
                tool="apply_export",
                effect="files",
                summary="The confirmed bundle failed deterministic regeneration.",
                code=exc.code,
                message=str(exc),
                details=exc.target,
            )
        except ExportPublicationError as exc:
            return ToolResponse.failure(
                tool="apply_export",
                effect="files",
                summary="The staged bundle was not published.",
                code="publication_refused",
                message=str(exc),
            )
        receipt = self._audit.record(
            tool="apply_export",
            effect="files",
            status="success",
            document_id=str(payload["documentId"]),
            details={"previewId": preview_id, "destination": payload.get("destination"), "publishedFingerprint": result.get("publishedFingerprint")},
        )

        return ToolResponse.success(
            tool="apply_export",
            effect="files",
            summary="Published the reviewed source bundle atomically.",
            audit_receipt=receipt.to_dict(),
            data={"previewId": preview_id, **dict(result)},
        )


    def list_history(self, arguments: Mapping[str, Any]) -> ToolResponse:
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
            tool="list_history",
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
        capture_started = time.perf_counter_ns()
        current = self._document_model(document_id)
        initial_capture_ms = (
            time.perf_counter_ns() - capture_started
        ) / 1_000_000
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
        revert_capabilities = lifecycle_capabilities(
            original.change_set, tool=original.tool
        )
        writable_inverse = writable_subset(
            current,
            inverse,
            capabilities=revert_capabilities,
        )
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
                capabilities=revert_capabilities,
                initial_stage_timings={
                    "initial_capture": initial_capture_ms
                },
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
            failure_data = {
                "operationId": operation_id,
                **exc.to_public_dict(),
            }
            return self._audited_edit_failure(
                tool="revert_change",
                document_id=document_id,
                summary="The revert failed verification.",
                code="transaction_failed",
                message="The revert was not verified.",
                audit_details=failure_data,
                data=failure_data,
            )
        persistence_is_warning = (
            result.persistence_reconciliation.get("relationship")
            in {"saved_intermediate", "source_changed_unclassified"}
        )
        receipt = self._audit.record(
            tool="revert_change",
            effect="edit",
            status="warning" if persistence_is_warning else "success",
            document_id=document_id,
            details={
                "operationId": metadata.operation_id,
                "revertedOperationId": operation_id,
                "beforeFingerprint": result.before_fingerprint,
                "afterFingerprint": result.after_fingerprint,
                "changeCount": result.change_count,
                "canonicalCoverage": result.coverage.to_public_dict(),
                "persistenceReconciliation": dict(
                    result.persistence_reconciliation
                ),
            },
        )
        persistence_warning = ()
        if persistence_is_warning:
            persistence_warning = (
                ToolWarning(
                    code="persistence_reconciled",
                    message=(
                        "The source changed while revert was active; the exact "
                        "live result was kept and history was rebased."
                    ),
                    target=dict(result.persistence_reconciliation),
                ),
            )
        return ToolResponse.success(
            tool="revert_change",
            effect="edit",
            status="warning" if persistence_warning else "success",
            summary="Reverted the selected change without overwriting unrelated later edits.",
            audit_receipt=receipt.to_dict(),
            metadata=metadata,
            warnings=persistence_warning,
            data={
                "operationId": metadata.operation_id,
                "revertedOperationId": operation_id,
                "documentId": document_id,
                "beforeFingerprint": result.before_fingerprint,
                "afterFingerprint": result.after_fingerprint,
                "requestedChangeCount": result.requested_change_count,
                "observedChangeCount": result.observed_change_count,
                "canonicalCoverage": result.coverage.to_public_dict(),
                "fontSaved": False,
                "sourceFileChanged": result.source_file_changed,
                "persistenceReconciliation": dict(
                    result.persistence_reconciliation
                ),
                "transactionCount": 1,
            },
        )

    def execute_python(self, arguments: Mapping[str, Any]) -> ToolResponse:
        if self._python is None:
            raise HostAccessError("This host adapter does not support Python execution.")
        mode = str(arguments.get("mode") or "read_only")
        if mode not in {"read_only", "staged_document", "live_open_world"}:
            raise ValueError("mode must be read_only, staged_document, or live_open_world")
        intended_effect = {
            "read_only": "read",
            "staged_document": "document_edit",
            "live_open_world": "files_or_external",
        }[mode]
        execution_mode = (
            "live_open_world" if mode in {"read_only", "live_open_world"}
            else "staged_document"
        )
        request = PythonExecutionRequest(
            code=_value(arguments, "code"),
            reason=_value(arguments, "reason"),
            intended_effect=intended_effect,
            execution_mode=execution_mode,
            document_id=_value(arguments, "document_id", "documentId"),
            glyph_name=_value(arguments, "glyph_name", "glyphName"),
            master_id=_value(arguments, "master_id", "masterId"),
            layer_id=_value(arguments, "layer_id", "layerId"),
            expected_document_fingerprint=_value(arguments, "expected_document_fingerprint", "expectedDocumentFingerprint"),
            review_id=_value(arguments, "approval_id", "approvalId"),
            confirm=bool(arguments.get("confirm", False)),
            max_output_chars=int(_value(arguments, "max_output_chars", "maxOutputChars", 8 * 1024)),
            max_error_chars=int(_value(arguments, "max_error_chars", "maxErrorChars", 8 * 1024)),
        )
        return self._python.execute(request)

__all__ = ["GlyphsMCPApplication"]
