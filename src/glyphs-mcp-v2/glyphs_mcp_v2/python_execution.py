"""Reviewed staged Python execution and honest live open-world fallback."""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Mapping, Optional, Protocol

from .audit import AuditLog
from .contracts import ToolResponse, ToolWarning
from .operations import OperationRecord, OperationStore
from .pagination import paginate
from .mutation import (
    CanonicalTargetMismatchError,
    MutationPlanner,
    VerifiedMutationPlan,
    unsupported_change_diagnostics,
    writable_subset,
)
from .semantic import ChangeSet, diff_models, fingerprint_model
from .transactions import StaleDocumentError, TransactionKernel, TransactionVerificationError

if TYPE_CHECKING:
    from .change_trace import ActionTraceCoordinator


REVIEW_TTL_SECONDS = 15 * 60
ROLLBACK_TTL_SECONDS = 60 * 60
DIFF_TTL_SECONDS = 60 * 60
DEFAULT_OUTPUT_CHARS = 8 * 1024
MAX_OUTPUT_CHARS = 8 * 1024


class PythonPolicyError(ValueError):
    pass


_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "GlyphsApp",
        "os",
        "pathlib",
        "shutil",
        "socket",
        "subprocess",
        "sys",
        "tempfile",
        "urllib",
        "http",
    }
)
_FORBIDDEN_CALL_NAMES = frozenset(
    {"open", "exec", "eval", "compile", "__import__", "exit", "quit"}
)
_FORBIDDEN_METHOD_NAMES = frozenset(
    {"save", "close", "show", "write", "unlink", "remove", "system", "popen"}
)


def validate_staged_code(code: str) -> None:
    """Reject obvious live/global/external constructs; this is not a sandbox."""
    if not isinstance(code, str) or not code.strip():
        raise PythonPolicyError("code is required")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise PythonPolicyError("Python code is not syntactically valid") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in _FORBIDDEN_IMPORT_ROOTS:
                    raise PythonPolicyError("staged code cannot import {}".format(alias.name))
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in _FORBIDDEN_IMPORT_ROOTS:
                raise PythonPolicyError("staged code cannot import {}".format(node.module))
        elif isinstance(node, ast.Name) and node.id == "Glyphs":
            raise PythonPolicyError("staged code cannot access the live Glyphs singleton")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALL_NAMES:
                raise PythonPolicyError("staged code cannot call {}".format(node.func.id))
            if isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_METHOD_NAMES:
                raise PythonPolicyError("staged code cannot call .{}()".format(node.func.attr))


def obvious_external_effects(code: str) -> tuple[str, ...]:
    """Identify constructs that cannot safely use the direct read-intent path."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise PythonPolicyError("Python code is not syntactically valid") from exc
    findings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            findings.update(
                alias.name.split(".", 1)[0]
                for alias in node.names
                if alias.name.split(".", 1)[0] in _FORBIDDEN_IMPORT_ROOTS
            )
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in _FORBIDDEN_IMPORT_ROOTS:
                findings.add(root)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALL_NAMES:
                findings.add(node.func.id)
            elif isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_METHOD_NAMES:
                findings.add("." + node.func.attr)
    return tuple(sorted(findings))


def _code_hash(code: str) -> str:
    return "sha256:{}".format(hashlib.sha256(code.encode("utf-8")).hexdigest())


def _bounded(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "\n… output truncated"


def _iso_timestamp(value: float) -> str:
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _context_details(request: "PythonExecutionRequest") -> dict[str, Any]:
    return {
        "documentId": request.document_id,
        "glyphName": request.glyph_name,
        "masterId": request.master_id,
        "layerId": request.layer_id,
    }


@dataclass(frozen=True)
class PythonExecutionRequest:
    code: Optional[str] = None
    reason: Optional[str] = None
    intended_effect: str = "read"
    execution_mode: str = "staged_document"
    document_id: Optional[str] = None
    glyph_name: Optional[str] = None
    master_id: Optional[str] = None
    layer_id: Optional[str] = None
    expected_document_fingerprint: Optional[str] = None
    review_id: Optional[str] = None
    confirm: bool = False
    max_output_chars: int = DEFAULT_OUTPUT_CHARS
    max_error_chars: int = DEFAULT_OUTPUT_CHARS

    def to_stored_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "reason": self.reason,
            "intendedEffect": self.intended_effect,
            "executionMode": self.execution_mode,
            "documentId": self.document_id,
            "glyphName": self.glyph_name,
            "masterId": self.master_id,
            "layerId": self.layer_id,
            "expectedDocumentFingerprint": self.expected_document_fingerprint,
            "maxOutputChars": min(max(1, int(self.max_output_chars)), MAX_OUTPUT_CHARS),
            "maxErrorChars": min(max(1, int(self.max_error_chars)), MAX_OUTPUT_CHARS),
        }

    @classmethod
    def from_stored_dict(cls, value: Mapping[str, Any]) -> "PythonExecutionRequest":
        return cls(
            code=value.get("code"),
            reason=value.get("reason"),
            intended_effect=str(value.get("intendedEffect") or "read"),
            execution_mode=str(value.get("executionMode") or "staged_document"),
            document_id=value.get("documentId"),
            glyph_name=value.get("glyphName"),
            master_id=value.get("masterId"),
            layer_id=value.get("layerId"),
            expected_document_fingerprint=value.get("expectedDocumentFingerprint"),
            max_output_chars=int(value.get("maxOutputChars") or DEFAULT_OUTPUT_CHARS),
            max_error_chars=int(value.get("maxErrorChars") or DEFAULT_OUTPUT_CHARS),
        )


class PythonExecutionHost(Protocol):
    def capture_model(self, document_id: str) -> Mapping[str, Any]:
        ...

    def preview_python(
        self, request: PythonExecutionRequest, before_model: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        ...

    def run_live_python(self, request: PythonExecutionRequest) -> Mapping[str, Any]:
        ...

    def create_recovery_copy(self, document_id: str, execution_id: str) -> str:
        ...

    def open_recovery_copy(self, path: str) -> None:
        ...


class PythonExecutionService:
    def __init__(
        self,
        *,
        host: PythonExecutionHost,
        transactions: TransactionKernel,
        reviews: OperationStore,
        checkpoints: OperationStore,
        audit: AuditLog,
        operations: Optional[OperationStore] = None,
        trace: Optional["ActionTraceCoordinator"] = None,
    ) -> None:
        self._host = host
        self._transactions = transactions
        self._reviews = reviews
        self._checkpoints = checkpoints
        self._audit = audit
        self._operations = operations or OperationStore(max_records=512)
        self._trace = trace

    def _store_diff(self, changes: ChangeSet) -> tuple[OperationRecord, Mapping[str, Any]]:
        items = [change.to_dict() for change in changes.changes]
        operation = self._operations.create(
            kind="python_diff",
            ttl_seconds=DIFF_TTL_SECONDS,
            payload={
                "items": items,
                "itemKey": "changes",
                "sourceFingerprint": changes.after_fingerprint,
                "metadata": {
                    "beforeFingerprint": changes.before_fingerprint,
                    "afterFingerprint": changes.after_fingerprint,
                    "changeCount": len(items),
                    "supported": changes.supported,
                },
            },
        )
        first = paginate(
            items,
            source_fingerprint=changes.after_fingerprint,
            cursor_scope=operation.operation_id,
            page_size=100,
        )
        return operation, {
            **dict(operation.payload["metadata"]),
            "changes": list(first.items),
            "operationId": operation.operation_id,
            "page": first.page.to_dict(),
        }

    @staticmethod
    def _failure(
        code: str,
        message: str,
        *,
        recoverable: bool = True,
        data: Optional[Mapping[str, Any]] = None,
        receipt: Optional[Mapping[str, Any]] = None,
    ) -> ToolResponse:
        return ToolResponse.failure(
            tool="execute_python",
            effect="code",
            summary=message,
            code=code,
            message=message,
            recoverable=recoverable,
            data=data,
            audit_receipt=receipt,
        )

    def execute(self, request: PythonExecutionRequest) -> ToolResponse:
        """Execute one request and guarantee one audit receipt for every result.

        Individual execution paths may emit a richer receipt when they know the
        complete observed state.  This boundary supplies the redacted fallback
        for every other returned failure so new refusal paths cannot silently
        bypass the audit ledger.
        """
        response = self._execute(request)
        if response.ok or response.audit_receipt is not None:
            return response
        details: dict[str, Any] = {
            "errorCode": response.error.code if response.error is not None else "unknown_error",
            "reason": request.reason,
            "declaredEffect": request.intended_effect,
            "executionMode": request.execution_mode,
            "context": _context_details(request),
            "expectedDocumentFingerprint": request.expected_document_fingerprint,
            "reviewId": request.review_id,
            "stateMayHaveChanged": bool(response.data.get("stateMayHaveChanged", False)),
        }
        if request.code:
            details["codeHash"] = _code_hash(request.code)
        if "documentIds" in response.data:
            details["scopeViolations"] = list(response.data.get("documentIds") or [])
        if "unsupportedCount" in response.data:
            details["unsupportedCount"] = int(response.data.get("unsupportedCount") or 0)
        archive_mismatch = response.data.get("nativeArchiveMismatch")
        if isinstance(archive_mismatch, Mapping):
            details["nativeArchiveMismatch"] = {
                "mismatchCount": int(archive_mismatch.get("mismatchCount") or 0),
                "truncated": bool(archive_mismatch.get("truncated")),
            }
        receipt = self._audit.record(
            tool="execute_python",
            effect="code",
            status="error",
            document_id=request.document_id,
            details=details,
        )
        return replace(response, audit_receipt=receipt.to_dict())

    def _execute(self, request: PythonExecutionRequest) -> ToolResponse:
        if self._trace is not None and request.document_id:
            self._trace.bind_document(request.document_id)
        if request.review_id:
            if not request.confirm:
                return self._failure("confirmation_required", "confirm=true is required to consume a Python review.")
            record = self._reviews.consume(request.review_id)
            if record is None or record.kind != "python_review":
                return self._failure("review_unavailable", "The Python review is missing, expired, or already consumed.")
            stored = PythonExecutionRequest.from_stored_dict(record.payload["request"])
            if self._trace is not None and stored.document_id:
                self._trace.bind_document(stored.document_id)
            if stored.execution_mode == "staged_document":
                return self._confirm_staged(
                    stored, record.payload, review_id=record.operation_id
                )
            return self._confirm_live(stored, record.payload, review_id=record.operation_id)

        if not request.code or not request.reason:
            return self._failure("invalid_request", "code and reason are required.")
        if request.intended_effect not in {"read", "document_edit", "files_or_external"}:
            return self._failure("invalid_effect", "intendedEffect is not supported.")
        if request.execution_mode not in {"staged_document", "live_open_world"}:
            return self._failure("invalid_execution_mode", "executionMode is not supported.")
        if request.intended_effect == "read":
            try:
                external_findings = obvious_external_effects(request.code or "")
            except PythonPolicyError as exc:
                return self._failure("invalid_code", str(exc))
            if external_findings:
                return self._failure(
                    "effect_review_required",
                    "The code contains obvious external or lifecycle effects; declare files_or_external and use live_open_world review.",
                    data={"constructs": list(external_findings)},
                )
            return self._execute_read(request)
        if not request.document_id or not request.expected_document_fingerprint:
            return self._failure(
                "document_context_required",
                "Document mutations and external execution require an explicit document and fingerprint.",
            )
        if request.execution_mode == "staged_document":
            return self._preview_staged(request)
        return self._preview_live(request)

    def _execute_read(self, request: PythonExecutionRequest) -> ToolResponse:
        before = None
        if request.document_id:
            before = dict(self._host.capture_model(request.document_id))
        try:
            result = self._host.run_live_python(request)
        except Exception:
            if request.document_id and before is not None and self._trace is not None:
                try:
                    self._trace.observe_transition(
                        request.document_id,
                        before,
                        dict(self._host.capture_model(request.document_id)),
                    )
                except Exception:
                    pass
            raise
        after = None
        violated = False
        if request.document_id:
            after = dict(self._host.capture_model(request.document_id))
            violated = fingerprint_model(before) != fingerprint_model(after)
            if self._trace is not None:
                self._trace.observe_transition(request.document_id, before, after)
        scope_violations = sorted(set(result.get("scopeViolations") or []))
        if request.document_id and violated and request.document_id not in scope_violations:
            scope_violations.append(request.document_id)
        undeclared = [value for value in scope_violations if value != request.document_id]
        receipt = self._audit.record(
            tool="execute_python",
            effect="code",
            status="warning" if violated or undeclared else "success",
            document_id=request.document_id,
            details={
                "codeHash": _code_hash(request.code or ""),
                "reason": request.reason,
                "declaredEffect": "read",
                "context": _context_details(request),
                "observedDocumentChange": violated,
                "scopeViolations": scope_violations,
            },
        )
        warnings = ()
        status = "success"
        if violated:
            status = "warning"
            warnings = (
                ToolWarning(
                    code="read_intent_violated",
                    message="The read-intent Python changed the declared document.",
                    target={"documentId": request.document_id},
                ),
            )
        if undeclared:
            status = "warning"
            warnings += (
                ToolWarning(
                    code="undeclared_document_mutation",
                    message="The read-intent Python changed document(s) outside its declared context.",
                    target={"documentIds": undeclared},
                ),
            )
        return ToolResponse.success(
            tool="execute_python",
            effect="code",
            status=status,
            summary="Python completed with bounded output.",
            warnings=warnings,
            audit_receipt=receipt.to_dict(),
            data={
                "codeHash": _code_hash(request.code or ""),
                "stdout": _bounded(result.get("stdout"), min(request.max_output_chars, MAX_OUTPUT_CHARS)),
                "stderr": _bounded(result.get("stderr"), min(request.max_error_chars, MAX_OUTPUT_CHARS)),
                "observedDocumentChange": violated,
                "scopeViolations": scope_violations,
                "transactional": False,
                "rollback": {"coverage": "unavailable", "available": False},
                "timeoutEnforcement": "cooperative",
            },
        )

    def _preview_staged(self, request: PythonExecutionRequest) -> ToolResponse:
        try:
            validate_staged_code(request.code or "")
        except PythonPolicyError as exc:
            return self._failure("staged_policy_violation", str(exc), recoverable=True)
        before = dict(self._host.capture_model(request.document_id or ""))
        if self._trace is not None and request.document_id:
            self._trace.observe_model(request.document_id, before)
        before_fingerprint = fingerprint_model(before)
        if before_fingerprint != request.expected_document_fingerprint:
            return self._failure("stale_document", "The document changed before staged execution.")
        try:
            preview = self._host.preview_python(request, before)
            after = dict(preview["afterModel"])
            after_fingerprint = fingerprint_model(after)
            provided_changes = preview.get("changeSet")
            if isinstance(provided_changes, ChangeSet):
                if (
                    provided_changes.before_fingerprint != before_fingerprint
                    or provided_changes.after_fingerprint != after_fingerprint
                ):
                    raise ValueError("host staged change set does not match its models")
                changes = provided_changes
            else:
                changes = diff_models(before, after)
        except Exception as exc:
            return self._failure(
                "python_preview_failed",
                "Detached Python preview failed: {}".format(type(exc).__name__),
            )
        scope_violations = list(preview.get("scopeViolations") or [])
        if scope_violations:
            return self._failure(
                "staged_scope_violation",
                "Staged Python changed one or more live documents; confirmation is refused.",
                data={"documentIds": scope_violations},
            )
        context_violations = preview.get("contextViolations")
        if (
            isinstance(context_violations, Mapping)
            and int(context_violations.get("count") or 0) > 0
        ):
            return self._failure(
                "staged_context_violation",
                "Staged Python changed fields outside its explicit glyph/layer context; confirmation is refused.",
                data={
                    "violationCount": int(context_violations.get("count") or 0),
                    "violationPaths": list(context_violations.get("paths") or [])[:100],
                    "truncated": bool(context_violations.get("truncated")),
                },
            )
        archive_comparison = preview.get("nativeArchiveComparison")
        archive_mismatch = (
            isinstance(archive_comparison, Mapping)
            and not bool(archive_comparison.get("equivalent"))
        )
        if archive_mismatch or bool(preview.get("unsupportedNativeChange")):
            bounded_comparison = (
                {
                    "equivalent": False,
                    "mismatchCount": int(archive_comparison.get("mismatchCount") or 0),
                    "mismatchLocations": list(archive_comparison.get("mismatchLocations") or [])[:100],
                    "truncated": bool(archive_comparison.get("truncated"))
                    or len(list(archive_comparison.get("mismatchLocations") or [])) > 100,
                    "directDeltaCount": int(archive_comparison.get("directDeltaCount") or 0),
                    "replayDeltaCount": int(archive_comparison.get("replayDeltaCount") or 0),
                }
                if isinstance(archive_comparison, Mapping)
                else {
                    "equivalent": False,
                    "mismatchCount": 1,
                    "mismatchLocations": [],
                    "truncated": False,
                }
            )
            return self._failure(
                "unsupported_staged_change",
                "The detached script changed native fields outside the canonical semantic model.",
                data={"unsupportedPaths": [], "nativeArchiveMismatch": bounded_comparison},
            )
        diagnostics = unsupported_change_diagnostics(changes, limit=100)
        provided_writable = preview.get("writableChangeSet")
        if isinstance(provided_writable, ChangeSet):
            if provided_writable.before_fingerprint != before_fingerprint:
                return self._failure(
                    "python_preview_failed",
                    "Detached Python preview returned a stale writable change set.",
                )
            try:
                writable_after = provided_writable.apply(before)
            except (KeyError, ValueError):
                return self._failure(
                    "python_preview_failed",
                    "Detached Python preview returned an invalid writable change set.",
                )
            if fingerprint_model(writable_after) != provided_writable.after_fingerprint:
                return self._failure(
                    "python_preview_failed",
                    "Detached Python preview returned an unreproducible writable change set.",
                )
            writable_changes = provided_writable
        else:
            writable_changes = writable_subset(before, changes)
        supports = getattr(self._host, "supports_change_set", None)
        host_supported = bool(supports(writable_changes)) if callable(supports) else True
        if diagnostics["unsupportedCount"] or not host_supported:
            if not diagnostics["unsupportedCount"] and not host_supported:
                diagnostics = {
                    "unsupportedCount": len(writable_changes.changes),
                    "changedRoots": list(
                        dict.fromkeys(change.path[0] for change in writable_changes.changes)
                    ),
                    "unsupportedPaths": [
                        list(change.path) for change in writable_changes.changes[:100]
                    ],
                    "truncated": len(writable_changes.changes) > 100,
                }
            return self._failure(
                "unsupported_staged_change",
                "The staged script changed document fields outside the supported semantic model.",
                data=diagnostics,
            )
        diff_operation, public_change_set = self._store_diff(changes)
        review = self._reviews.create(
            kind="python_review",
            ttl_seconds=REVIEW_TTL_SECONDS,
            payload={
                "request": request.to_stored_dict(),
                "codeHash": _code_hash(request.code or ""),
                "changeSet": changes,
                "writableChangeSet": writable_changes,
                "expectedAfterModel": after,
                "stdout": _bounded(preview.get("stdout"), min(request.max_output_chars, MAX_OUTPUT_CHARS)),
                "stderr": _bounded(preview.get("stderr"), min(request.max_error_chars, MAX_OUTPUT_CHARS)),
                "scopeViolations": list(preview.get("scopeViolations") or []),
                "diffOperationId": diff_operation.operation_id,
            },
        )
        receipt = self._audit.record(
            tool="execute_python",
            effect="code",
            status="review_required",
            document_id=request.document_id,
            details={
                "codeHash": _code_hash(request.code or ""),
                "reason": request.reason,
                "declaredEffect": request.intended_effect,
                "executionMode": request.execution_mode,
                "context": _context_details(request),
                "beforeFingerprint": before_fingerprint,
                "proposedFingerprint": changes.after_fingerprint,
                "changeCount": len(changes.changes),
                "scopeViolations": list(preview.get("scopeViolations") or []),
            },
        )
        return ToolResponse.success(
            tool="execute_python",
            effect="code",
            status="review_required",
            summary="Detached Python produced a reviewed semantic change set; the live document is unchanged.",
            audit_receipt=receipt.to_dict(),
            data={
                "reviewId": review.operation_id,
                "expiresAt": _iso_timestamp(review.expires_at),
                "codeHash": _code_hash(request.code or ""),
                "executionMode": "staged_document",
                "liveDocumentChanged": False,
                "changeSet": public_change_set,
                "operationId": diff_operation.operation_id,
                "stdout": _bounded(preview.get("stdout"), min(request.max_output_chars, MAX_OUTPUT_CHARS)),
                "stderr": _bounded(preview.get("stderr"), min(request.max_error_chars, MAX_OUTPUT_CHARS)),
            },
        )

    def _preview_live(self, request: PythonExecutionRequest) -> ToolResponse:
        current = self._host.capture_model(request.document_id or "")
        if self._trace is not None and request.document_id:
            self._trace.observe_model(request.document_id, current)
        if fingerprint_model(current) != request.expected_document_fingerprint:
            return self._failure("stale_document", "The document changed before Python review.")
        review = self._reviews.create(
            kind="python_review",
            ttl_seconds=REVIEW_TTL_SECONDS,
            payload={
                "request": request.to_stored_dict(),
                "codeHash": _code_hash(request.code or ""),
            },
        )
        receipt = self._audit.record(
            tool="execute_python",
            effect="code",
            status="review_required",
            document_id=request.document_id,
            details={
                "codeHash": _code_hash(request.code or ""),
                "reason": request.reason,
                "declaredEffect": request.intended_effect,
                "executionMode": "live_open_world",
                "context": _context_details(request),
                "beforeFingerprint": request.expected_document_fingerprint,
            },
        )
        return ToolResponse.success(
            tool="execute_python",
            effect="code",
            status="review_required",
            summary="Open-world Python is approval-bound and has not executed.",
            audit_receipt=receipt.to_dict(),
            data={
                "reviewId": review.operation_id,
                "expiresAt": _iso_timestamp(review.expires_at),
                "codeHash": _code_hash(request.code or ""),
                "executionMode": "live_open_world",
                "liveDocumentChanged": False,
                "externalEffectsVerifiable": False,
            },
        )

    def _confirm_staged(
        self,
        request: PythonExecutionRequest,
        payload: Mapping[str, Any],
        *,
        review_id: str,
    ) -> ToolResponse:
        changes = payload.get("changeSet")
        writable = payload.get("writableChangeSet") or changes
        expected_after = payload.get("expectedAfterModel")
        if (
            not isinstance(changes, ChangeSet)
            or not isinstance(writable, ChangeSet)
            or not isinstance(expected_after, Mapping)
        ):
            return self._failure("review_corrupt", "The stored staged review is incomplete.", recoverable=False)
        before = dict(self._host.capture_model(request.document_id or ""))
        plan = VerifiedMutationPlan(
            document_id=request.document_id or "",
            operation_id=review_id,
            before_model=before,
            expected_after_model=dict(expected_after),
            writable_change_set=writable,
            observed_change_set=changes,
        )
        try:
            transaction = self._transactions.apply_plan(plan)
        except StaleDocumentError:
            return self._failure("stale_document", "The document changed after Python review.")
        except TransactionVerificationError as exc:
            receipt = self._audit.record(
                tool="execute_python",
                effect="code",
                status="error",
                document_id=request.document_id,
                details={
                    "codeHash": payload.get("codeHash"),
                    "reason": request.reason,
                    "executionMode": "staged_document",
                    "context": _context_details(request),
                    "errorCode": "transaction_failed",
                    "rollbackAttempted": True,
                    "rollbackSucceeded": exc.rollback_succeeded,
                },
            )
            return self._failure(
                "transaction_failed",
                "The reviewed Python patch failed verification.",
                data={"rollbackAttempted": True, "rollbackSucceeded": exc.rollback_succeeded},
                receipt=receipt.to_dict(),
            )
        checkpoint = self._checkpoints.create(
            kind="python_checkpoint",
            ttl_seconds=ROLLBACK_TTL_SECONDS,
            payload={
                "documentId": request.document_id,
                "codeHash": payload.get("codeHash"),
                "beforeFingerprint": transaction.before_fingerprint,
                "afterFingerprint": transaction.after_fingerprint,
                "beforeModel": before,
                "inverse": transaction.inverse,
                "contributionId": review_id,
                "coverage": "document_inverse",
                "recoveryPath": None,
            },
        )
        receipt = self._audit.record(
            tool="execute_python",
            effect="code",
            status="success",
            document_id=request.document_id,
            details={
                "codeHash": payload.get("codeHash"),
                "reason": request.reason,
                "executionMode": "staged_document",
                "context": _context_details(request),
                "beforeFingerprint": transaction.before_fingerprint,
                "afterFingerprint": transaction.after_fingerprint,
                "changeCount": transaction.change_count,
                "rollbackCoverage": "document_inverse",
            },
        )
        return ToolResponse.success(
            tool="execute_python",
            effect="code",
            summary="The reviewed Python change set was applied and verified without rerunning the script.",
            audit_receipt=receipt.to_dict(),
            data={
                "executionId": checkpoint.operation_id,
                "codeHash": payload.get("codeHash"),
                "beforeFingerprint": transaction.before_fingerprint,
                "afterFingerprint": transaction.after_fingerprint,
                "changeCount": transaction.change_count,
                "transactional": True,
                "externalEffectsVerifiable": True,
                "rollback": {
                    "available": True,
                    "coverage": "document_inverse",
                    "expiresAt": _iso_timestamp(checkpoint.expires_at),
                },
                "stdout": payload.get("stdout", ""),
                "stderr": payload.get("stderr", ""),
            },
        )

    def _confirm_live(
        self,
        request: PythonExecutionRequest,
        payload: Mapping[str, Any],
        *,
        review_id: str,
    ) -> ToolResponse:
        before = dict(self._host.capture_model(request.document_id or ""))
        if self._trace is not None and request.document_id:
            self._trace.observe_model(request.document_id, before)
        before_fingerprint = fingerprint_model(before)
        if before_fingerprint != request.expected_document_fingerprint:
            return self._failure("stale_document", "The document changed after Python review.")
        try:
            recovery_path = self._host.create_recovery_copy(request.document_id or "", review_id)
        except Exception as exc:
            return self._failure(
                "recovery_checkpoint_failed",
                "Open-world Python was not run because its recovery copy failed: {}".format(type(exc).__name__),
                data={"stateMayHaveChanged": False},
            )
        try:
            result = self._host.run_live_python(request)
            after = dict(result.get("afterModel") or self._host.capture_model(request.document_id or ""))
        except Exception as exc:
            after = dict(self._host.capture_model(request.document_id or ""))
            if self._trace is not None and request.document_id:
                self._trace.observe_transition(request.document_id, before, after)
            after_fingerprint = fingerprint_model(after)
            checkpoint = self._checkpoints.create(
                kind="python_checkpoint",
                ttl_seconds=ROLLBACK_TTL_SECONDS,
                payload={
                    "documentId": request.document_id,
                    "codeHash": payload.get("codeHash"),
                    "beforeFingerprint": before_fingerprint,
                    "afterFingerprint": after_fingerprint,
                    "inverse": None,
                    "coverage": "recovery_only",
                    "recoveryPath": recovery_path,
                },
            )
            self._register_recovery(checkpoint, recovery_path)
            receipt = self._audit.record(
                tool="execute_python",
                effect="code",
                status="error",
                document_id=request.document_id,
                details={
                    "codeHash": payload.get("codeHash"),
                    "reason": request.reason,
                    "executionMode": "live_open_world",
                    "context": _context_details(request),
                    "beforeFingerprint": before_fingerprint,
                    "afterFingerprint": after_fingerprint,
                    "rollbackCoverage": "recovery_only",
                    "exceptionType": type(exc).__name__,
                },
            )
            return self._failure(
                "python_execution_failed",
                "Open-world Python failed: {}".format(type(exc).__name__),
                data={
                    "stateMayHaveChanged": True,
                    "executionId": checkpoint.operation_id,
                    "afterFingerprint": after_fingerprint,
                    "rollback": {
                        "available": True,
                        "coverage": "recovery_only",
                        "expiresAt": _iso_timestamp(checkpoint.expires_at),
                    },
                },
                receipt=receipt.to_dict(),
            )
        changes = diff_models(before, after)
        if self._trace is not None and request.document_id:
            self._trace.observe_transition(
                request.document_id,
                before,
                after,
                change_set=changes,
            )
        supports = getattr(self._host, "supports_change_set", None)
        host_supported = bool(supports(changes)) if callable(supports) else True
        complete_coverage = getattr(self._host, "complete_observed_diff_covered", None)
        observed_complete = (
            bool(complete_coverage(changes, result)) if callable(complete_coverage) else True
        )
        coverage = (
            "document_inverse"
            if changes.supported and host_supported and observed_complete
            else "recovery_only"
        )
        checkpoint_payload = {
            "documentId": request.document_id,
            "codeHash": payload.get("codeHash"),
            "beforeFingerprint": before_fingerprint,
            "afterFingerprint": changes.after_fingerprint,
            "beforeModel": before,
            "inverse": (
                writable_subset(after, changes.inverse())
                if coverage == "document_inverse"
                else None
            ),
            "coverage": coverage,
            "recoveryPath": recovery_path,
        }
        checkpoint = self._checkpoints.create(
            kind="python_checkpoint",
            ttl_seconds=ROLLBACK_TTL_SECONDS,
            payload=checkpoint_payload,
        )
        recovery_persisted = self._register_recovery(checkpoint, recovery_path)
        receipt = self._audit.record(
            tool="execute_python",
            effect="code",
            status="success",
            document_id=request.document_id,
            details={
                "codeHash": payload.get("codeHash"),
                "reason": request.reason,
                "executionMode": "live_open_world",
                "context": _context_details(request),
                "beforeFingerprint": before_fingerprint,
                "afterFingerprint": changes.after_fingerprint,
                "changeCount": len(changes.changes),
                "rollbackCoverage": coverage,
                "externalEffectsVerifiable": False,
                "scopeViolations": list(result.get("scopeViolations") or []),
                "recoveryPersisted": recovery_persisted,
            },
        )
        return ToolResponse.success(
            tool="execute_python",
            effect="code",
            summary="Open-world Python executed with a private recovery checkpoint.",
            audit_receipt=receipt.to_dict(),
            warnings=(
                ToolWarning(
                    code="external_effects_unverifiable",
                    message="Files, processes, network, preferences, saves, and other external effects are not reversible.",
                ),
            ) + (
                (
                    ToolWarning(
                        code="undeclared_document_mutation",
                        message="Open-world Python changed document(s) outside its declared context.",
                        target={"documentIds": list(result.get("scopeViolations") or [])},
                    ),
                )
                if result.get("scopeViolations")
                else ()
            ),
            status="warning",
            data={
                "executionId": checkpoint.operation_id,
                "codeHash": payload.get("codeHash"),
                "beforeFingerprint": before_fingerprint,
                "afterFingerprint": changes.after_fingerprint,
                "transactional": False,
                "externalEffectsVerifiable": False,
                "timeoutEnforcement": "cooperative",
                "scopeViolations": list(result.get("scopeViolations") or []),
                "recoveryAvailableAfterRestart": recovery_persisted,
                "rollback": {
                    "available": True,
                    "coverage": coverage,
                    "expiresAt": _iso_timestamp(checkpoint.expires_at),
                },
                "stdout": _bounded(result.get("stdout"), min(request.max_output_chars, MAX_OUTPUT_CHARS)),
                "stderr": _bounded(result.get("stderr"), min(request.max_error_chars, MAX_OUTPUT_CHARS)),
            },
        )

    def _register_recovery(self, checkpoint: OperationRecord, recovery_path: str) -> bool:
        register = getattr(self._host, "register_recovery_checkpoint", None)
        if not callable(register):
            return False
        try:
            register(
                checkpoint.operation_id,
                str(checkpoint.payload.get("documentId") or ""),
                recovery_path,
                str(checkpoint.payload.get("afterFingerprint") or ""),
            )
            return True
        except Exception:
            return False

    def _rollback_failure(
        self,
        *,
        code: str,
        summary: str,
        execution_id: str,
        document_id: Optional[str] = None,
        recoverable: bool = True,
        data: Optional[Mapping[str, Any]] = None,
    ) -> ToolResponse:
        receipt = self._audit.record(
            tool="rollback_python_execution",
            effect="edit",
            status="error",
            document_id=document_id,
            details={"executionId": execution_id, "errorCode": code, **dict(data or {})},
        )
        return ToolResponse.failure(
            tool="rollback_python_execution",
            effect="edit",
            summary=summary,
            code=code,
            message=summary,
            recoverable=recoverable,
            data=data,
            audit_receipt=receipt.to_dict(),
        )

    def rollback(
        self,
        *,
        execution_id: str,
        expected_after_fingerprint: str,
        confirm: bool,
        strategy: str = "auto",
    ) -> ToolResponse:
        if not confirm:
            return ToolResponse.failure(
                tool="rollback_python_execution",
                effect="edit",
                summary="confirm=true is required for rollback.",
                code="confirmation_required",
                message="Rollback was not confirmed.",
            )
        if strategy not in {"auto", "open_recovery_copy"}:
            return self._rollback_failure(
                code="invalid_strategy",
                summary="Unknown rollback strategy.",
                execution_id=execution_id,
            )
        checkpoint = self._checkpoints.get(execution_id)
        if checkpoint is None or checkpoint.kind != "python_checkpoint":
            finder = getattr(self._host, "find_recovery_checkpoint", None)
            persisted = finder(execution_id) if callable(finder) else None
            if not isinstance(persisted, Mapping):
                return self._rollback_failure(
                    code="checkpoint_unavailable",
                    summary="The Python checkpoint is missing, expired, or consumed.",
                    execution_id=execution_id,
                    recoverable=False,
                )
            payload = {
                **dict(persisted),
                "coverage": "recovery_only",
                "inverse": None,
            }
        else:
            payload = checkpoint.payload
        document_id = str(payload.get("documentId") or "")
        if self._trace is not None and document_id:
            self._trace.bind_document(document_id)
        if expected_after_fingerprint != payload.get("afterFingerprint"):
            return self._rollback_failure(
                code="stale_document",
                summary="The requested rollback fingerprint does not match the checkpoint.",
                execution_id=execution_id,
                document_id=document_id,
            )
        if strategy == "open_recovery_copy":
            path = payload.get("recoveryPath")
            if not path:
                return self._rollback_failure(
                    code="recovery_unavailable",
                    summary="This checkpoint has no serialized recovery copy.",
                    execution_id=execution_id,
                    document_id=document_id,
                    recoverable=False,
                )
            try:
                if self._trace is not None:
                    try:
                        self._trace.observe_model(document_id, self._host.capture_model(document_id))
                    except Exception:
                        pass
                self._host.open_recovery_copy(str(path))
            except Exception:
                return self._rollback_failure(
                    code="recovery_open_failed",
                    summary="Glyphs could not open the serialized recovery copy.",
                    execution_id=execution_id,
                    document_id=document_id,
                )
            receipt = self._audit.record(
                tool="rollback_python_execution",
                effect="edit",
                status="success",
                document_id=document_id,
                details={"executionId": execution_id, "strategy": strategy, "workingDocumentReplaced": False},
            )
            return ToolResponse.success(
                tool="rollback_python_execution",
                effect="edit",
                summary="Opened the checkpoint as a separate recovery document.",
                audit_receipt=receipt.to_dict(),
                data={"executionId": execution_id, "strategy": strategy, "workingDocumentReplaced": False},
            )
        inverse = payload.get("inverse")
        required_before = payload.get("beforeModel")
        if not isinstance(inverse, ChangeSet) or not isinstance(required_before, Mapping):
            return self._rollback_failure(
                code="automatic_rollback_unavailable",
                summary="Automatic rollback is not covered; use open_recovery_copy instead.",
                execution_id=execution_id,
                document_id=document_id,
                data={"coverage": payload.get("coverage")},
            )
        if fingerprint_model(required_before) != payload.get("beforeFingerprint"):
            return self._rollback_failure(
                code="checkpoint_corrupt",
                summary="The rollback checkpoint does not reproduce its declared baseline.",
                execution_id=execution_id,
                document_id=document_id,
                recoverable=False,
            )
        try:
            current = self._host.capture_model(document_id)
        except Exception:
            return self._rollback_failure(
                code="document_unavailable",
                summary="The original document is closed or replaced; rollback was not attempted.",
                execution_id=execution_id,
                document_id=document_id,
            )
        if self._trace is not None:
            self._trace.observe_model(document_id, current)
        if fingerprint_model(current) != expected_after_fingerprint:
            return self._rollback_failure(
                code="stale_document",
                summary="The document changed after Python execution; rollback was not attempted.",
                execution_id=execution_id,
                document_id=document_id,
            )
        try:
            plan = MutationPlanner(self._host).plan(
                document_id=document_id,
                expected_document_fingerprint=expected_after_fingerprint,
                requested_change_set=inverse,
                operation_id="rollback_{}".format(execution_id),
                before_model=current,
                dirty_state_intent="rollback",
                removes_contribution_id=str(payload.get("contributionId") or "") or None,
                required_after_model=required_before,
            )
            result = self._transactions.apply_plan(plan)
        except CanonicalTargetMismatchError as exc:
            mismatch = exc.mismatch
            return self._rollback_failure(
                code="rollback_not_exact",
                summary="The detached inverse could not reproduce the checkpoint baseline; nothing was rolled back.",
                execution_id=execution_id,
                document_id=document_id,
                data={
                    "intendedAfterFingerprint": payload.get("beforeFingerprint"),
                    "observedAfterFingerprint": fingerprint_model(
                        exc.observed_after_model
                    ),
                    "mismatchCount": len(mismatch.changes),
                    "mismatchPaths": [
                        list(change.path) for change in mismatch.changes[:100]
                    ],
                    "mismatchPathsTruncated": len(mismatch.changes) > 100,
                },
            )
        except (StaleDocumentError, TransactionVerificationError) as exc:
            return self._rollback_failure(
                code="rollback_failed",
                summary="Python rollback failed verification.",
                execution_id=execution_id,
                document_id=document_id,
                data={
                    "afterStateRestored": bool(
                        isinstance(exc, TransactionVerificationError) and exc.rollback_succeeded
                    )
                },
            )
        if result.after_fingerprint != payload.get("beforeFingerprint"):
            return self._rollback_failure(
                code="rollback_not_exact",
                summary="The verified rollback did not restore the checkpoint baseline.",
                execution_id=execution_id,
                document_id=document_id,
                recoverable=False,
            )
        self._checkpoints.discard(execution_id)
        receipt = self._audit.record(
            tool="rollback_python_execution",
            effect="edit",
            status="success",
            document_id=document_id,
            details={
                "executionId": execution_id,
                "strategy": "auto",
                "beforeFingerprint": result.before_fingerprint,
                "afterFingerprint": result.after_fingerprint,
                "changeCount": result.change_count,
            },
        )
        return ToolResponse.success(
            tool="rollback_python_execution",
            effect="edit",
            summary="The Python document change was rolled back and verified.",
            audit_receipt=receipt.to_dict(),
            data={
                "executionId": execution_id,
                "strategy": "auto",
                "beforeFingerprint": result.before_fingerprint,
                "afterFingerprint": result.after_fingerprint,
                "checkpointConsumed": True,
            },
        )


__all__ = [
    "DEFAULT_OUTPUT_CHARS",
    "DIFF_TTL_SECONDS",
    "MAX_OUTPUT_CHARS",
    "PythonExecutionHost",
    "PythonExecutionRequest",
    "PythonExecutionService",
    "PythonPolicyError",
    "REVIEW_TTL_SECONDS",
    "ROLLBACK_TTL_SECONDS",
    "validate_staged_code",
    "obvious_external_effects",
]
