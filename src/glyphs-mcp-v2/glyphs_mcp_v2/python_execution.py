"""Reviewed staged Python execution and honest live open-world fallback."""

from __future__ import annotations

import ast
import hashlib
import logging
import os
import re
import traceback
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional, Protocol

from .activity import ActivityCancelled, OperationActivityStore
from .audit import AuditLog
from .canonical_schema import CanonicalCoverage, CoverageStatus
from .contracts import OperationMetadata, ToolResponse, ToolWarning
from .detached_python import (
    ALLOWED_IMPORT_ROOTS,
    DANGEROUS_IMPORT_ROOTS,
    HOST_EFFECT_METHOD_NAMES,
    POLICY_FORBIDDEN_CALL_NAMES,
    StagedImportUnavailable,
    detached_python_registry_for_host,
    unavailable_standard_builtin_names,
)
from .operations import OperationRecord, OperationStore
from .pagination import paginate
from .mutation import (
    CanonicalTargetMismatchError,
    MutationPlanner,
    VerifiedMutationPlan,
    staged_lifecycle_capabilities,
    unsupported_change_diagnostics,
    writable_subset,
)
from .semantic import ChangeSet, diff_models, fingerprint_model, public_change_dict
from .saved_source import source_state_changed
from .runtime_safety import (
    SourceSaveForbiddenError,
    ScriptingRuntimeUnavailableError,
    agent_recovery_directive,
)
from .transactions import StaleDocumentError, TransactionKernel, TransactionVerificationError

if TYPE_CHECKING:
    from .change_trace import ActionTraceCoordinator


REVIEW_TTL_SECONDS = 15 * 60
ROLLBACK_TTL_SECONDS = 60 * 60
DIFF_TTL_SECONDS = 60 * 60
DEFAULT_OUTPUT_CHARS = 8 * 1024
MAX_OUTPUT_CHARS = 8 * 1024
MAX_ERROR_MESSAGE_CHARS = 500
DETACHED_SOURCE_NAME = "<glyphs-mcp-staged>"
_ABSOLUTE_PATH = re.compile(
    r"(?<![A-Za-z0-9_])(?:/Users|/private|/var|/tmp)/[^\s\"']+"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|password|secret)"
    r"\s*[:=]\s*[^\s,;]+"
)
_LOGGER = logging.getLogger(__name__)


class PythonPolicyError(ValueError):
    pass


def _is_source_save_method(name: str) -> bool:
    """Return whether one Python/Objective-C spelling can save an NSDocument."""

    compact = str(name or "").replace("_", "").lower()
    return bool(
        compact == "save"
        or compact.startswith("savedocument")
        or compact.startswith("savetourl")
        or compact.startswith("autosave")
        or compact.startswith("writetourl")
        or compact.startswith("writesafelytourl")
    )


def _static_string(
    node: ast.AST,
    assignments: Mapping[str, str],
) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return assignments.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_string(node.left, assignments)
        right = _static_string(node.right, assignments)
        return left + right if left is not None and right is not None else None
    if isinstance(node, ast.JoinedStr):
        values = []
        for value in node.values:
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                return None
            values.append(value.value)
        return "".join(values)
    return None


def _definitely_working_source_expression(node: ast.AST) -> bool:
    """Recognize direct AST roots for an open Glyphs document/font.

    Calls are deliberately not followed: ``font.copy().save()`` targets a
    detached object and remains a legitimate open-world external operation.
    Runtime identity interposition covers aliases and reflective expressions
    that cannot be proven safely at this static review boundary.
    """

    if isinstance(node, ast.Name):
        return node.id == "font"
    if isinstance(node, ast.Subscript):
        return _definitely_working_source_expression(node.value)
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == "Glyphs":
            return node.attr in {
                "currentDocument",
                "documents",
                "font",
                "fonts",
            }
        return _definitely_working_source_expression(node.value)
    return False


def validate_no_source_save(code: str) -> None:
    """Refuse statically addressable working-document save entry points.

    This is a capability rule rather than an effect declaration: reviewed
    ``live_open_world`` Python must still use the typed ``save_document`` tool.
    Literal and constant-composed ``getattr`` spellings are covered so callers
    cannot bypass the rule merely by avoiding attribute-call syntax.
    """

    if not isinstance(code, str) or not code.strip():
        return
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise PythonPolicyError("Python code is not syntactically valid") from exc
    assignments: dict[str, str] = {}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value_node = node.value
            if value_node is None:
                continue
            value = _static_string(value_node, assignments)
            if value is None:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if (
                    isinstance(target, ast.Name)
                    and assignments.get(target.id) != value
                ):
                    assignments[target.id] = value
                    changed = True
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        method_name: Optional[str] = None
        receiver: Optional[ast.AST] = None
        if isinstance(node.func, ast.Attribute):
            method_name = node.func.attr
            receiver = node.func.value
        elif isinstance(node.func, ast.Name):
            method_name = node.func.id
        if (
            method_name is not None
            and receiver is not None
            and _is_source_save_method(method_name)
            and _definitely_working_source_expression(receiver)
        ):
            raise PythonPolicyError(
                "execute_python cannot save the working Glyphs source; use save_document"
            )
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "hasattr", "setattr"}
            and len(node.args) >= 2
        ):
            dynamic_name = _static_string(node.args[1], assignments)
            if (
                dynamic_name is not None
                and _is_source_save_method(dynamic_name)
                and _definitely_working_source_expression(node.args[0])
            ):
                raise PythonPolicyError(
                    "execute_python cannot access working-source save selectors; use save_document"
                )


def validate_staged_code(code: str) -> None:
    """Reject obvious live/global/external constructs; this is not a sandbox."""
    if not isinstance(code, str) or not code.strip():
        raise PythonPolicyError("code is required")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise PythonPolicyError("Python code is not syntactically valid") from exc
    validate_no_source_save(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in DANGEROUS_IMPORT_ROOTS:
                    raise PythonPolicyError("staged code cannot import {}".format(alias.name))
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in DANGEROUS_IMPORT_ROOTS:
                raise PythonPolicyError("staged code cannot import {}".format(node.module))
        elif isinstance(node, ast.Name) and node.id == "Glyphs":
            raise PythonPolicyError("staged code cannot access the live Glyphs singleton")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in POLICY_FORBIDDEN_CALL_NAMES:
                raise PythonPolicyError("staged code cannot call {}".format(node.func.id))
            if isinstance(node.func, ast.Attribute) and node.func.attr in HOST_EFFECT_METHOD_NAMES:
                raise PythonPolicyError("staged code cannot call .{}()".format(node.func.attr))

def _code_hash(code: str) -> str:
    return "sha256:{}".format(hashlib.sha256(code.encode("utf-8")).hexdigest())


def _bounded(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit]


def _bounded_streams(
    stdout: Any,
    stderr: Any,
    *,
    max_output_chars: int,
    max_error_chars: int,
) -> dict[str, Any]:
    stdout_text = str(stdout or "")
    stderr_text = str(stderr or "")
    output_limit = min(max(1, int(max_output_chars)), MAX_OUTPUT_CHARS)
    error_limit = min(max(1, int(max_error_chars)), MAX_OUTPUT_CHARS)
    return {
        "stdout": _bounded(stdout_text, output_limit),
        "stderr": _bounded(stderr_text, error_limit),
        "stdoutTruncated": len(stdout_text) > output_limit,
        "stderrTruncated": len(stderr_text) > error_limit,
        "stdoutOriginalChars": len(stdout_text),
        "stderrOriginalChars": len(stderr_text),
        "maxOutputCharsApplied": output_limit,
        "maxErrorCharsApplied": error_limit,
    }


def _sanitized_exception_message(exc: BaseException) -> str:
    message = " ".join(str(exc).replace("\x00", "").split())
    message = _ABSOLUTE_PATH.sub("<path>", message)
    message = _SECRET_ASSIGNMENT.sub(
        lambda match: "{}=<redacted>".format(match.group(1)), message
    )
    return message[:MAX_ERROR_MESSAGE_CHARS]


def _staged_exception_line(exc: BaseException) -> Optional[int]:
    current = exc.__traceback__
    staged_line: Optional[int] = None
    while current is not None:
        if current.tb_frame.f_code.co_filename == DETACHED_SOURCE_NAME:
            staged_line = current.tb_lineno
        current = current.tb_next
    return staged_line


def _exception_line(exc: BaseException) -> Optional[int]:
    line = getattr(exc, "lineno", None)
    if isinstance(line, int) and line > 0:
        return line
    staged_line = _staged_exception_line(exc)
    if staged_line is not None:
        return staged_line
    current = exc.__traceback__
    while current is not None and current.tb_next is not None:
        current = current.tb_next
    return current.tb_lineno if current is not None else None


def _script_explicitly_raises_assertion(code: str, line: Optional[int]) -> bool:
    """Recognize assertions authored in the detached script, not host assertions."""

    if line is None:
        return False
    try:
        tree = ast.parse(code or "", mode="exec")
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not (
            int(getattr(node, "lineno", -1))
            <= line
            <= int(getattr(node, "end_lineno", getattr(node, "lineno", -1)))
        ):
            continue
        if isinstance(node, ast.Assert):
            return True
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        if isinstance(raised, ast.Name) and raised.id == "AssertionError":
            return True
        if isinstance(raised, ast.Attribute) and raised.attr == "AssertionError":
            return True
    return False


def _classify_detached_error(
    exc: BaseException,
    *,
    code: str,
    generic_code: str,
    generic_message: str,
    contract: Mapping[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    """Return a structural detached failure without parsing exception strings."""

    evidence: dict[str, Any] = {
        "detachedPythonContractFingerprint": contract["contractFingerprint"],
        "detachedPythonContractPath": (
            "get_server_info.data.registries.pythonExecution.detachedNamespace"
        ),
    }
    if isinstance(exc, StagedImportUnavailable):
        evidence.update(
            {
                "import": str(exc.requested_import)[:240],
                "importRoot": str(exc.import_root)[:120],
                "allowedImportRoots": sorted(ALLOWED_IMPORT_ROOTS),
            }
        )
        return (
            "staged_import_unavailable",
            "The detached Python import is outside the advertised import roots.",
            evidence,
        )
    if isinstance(exc, NameError):
        symbol = str(getattr(exc, "name", "") or "")
        if symbol in unavailable_standard_builtin_names():
            evidence.update(
                {
                    "symbol": symbol[:120],
                    "availableBuiltins": list(contract["builtins"]),
                }
            )
            return (
                "staged_symbol_unavailable",
                "The standard Python symbol is intentionally unavailable in detached execution.",
                evidence,
            )
    if isinstance(exc, AssertionError):
        line = _staged_exception_line(exc)
        if _script_explicitly_raises_assertion(code, line):
            evidence["assertionOrigin"] = "staged_script"
            return (
                "staged_assertion_failed",
                "The detached script rejected its own candidate.",
                evidence,
            )
    return generic_code, generic_message, evidence


def _python_error_details(
    exc: BaseException,
    *,
    phase: str,
    code: str,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "phase": str(phase or "evaluation"),
        "exceptionType": type(exc).__name__,
        "message": _sanitized_exception_message(exc),
        "codeHash": _code_hash(code or ""),
    }
    symbol = getattr(exc, "name", None)
    if symbol:
        details["symbol"] = str(symbol)[:120]
    line = _exception_line(exc)
    if line is not None:
        details["line"] = int(line)
    return details


def _debug_python_exception() -> None:
    if os.environ.get("GLYPHS_MCP_DEBUG_CAPTURE"):
        _LOGGER.debug("Full Python execution traceback:\n%s", traceback.format_exc(limit=40))


def _staged_canonical_coverage(
    changes: ChangeSet,
    replay_context: Mapping[str, Any],
) -> CanonicalCoverage:
    """Separate complete semantic proof from exact native opaque evidence."""

    if not replay_context.get("nativeReplayEvidenceId"):
        return CanonicalCoverage.complete()
    opaque_paths = tuple(
        change.path
        for change in changes.changes
        if change.before_present != change.after_present
    )
    if not opaque_paths:
        return CanonicalCoverage.complete()
    return CanonicalCoverage(
        status=CoverageStatus.COMPLETE_WITH_OPAQUE_PRESERVATION,
        opaque_paths=opaque_paths,
    )


def _recovery_only_canonical_coverage(
    changes: ChangeSet | None = None,
) -> CanonicalCoverage:
    return CanonicalCoverage(
        status=CoverageStatus.RECOVERY_ONLY,
        unsupported_paths=(
            tuple(change.path for change in changes.changes)
            if changes is not None
            else ()
        ),
    )


def _iso_timestamp(value: float) -> str:
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _context_details(request: "PythonExecutionRequest") -> dict[str, Any]:
    return {
        "documentId": request.document_id,
        "glyphName": request.glyph_name,
        "masterId": request.master_id,
        "layerId": request.layer_id,
    }


def _source_state_changed(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> bool:
    return source_state_changed(before, after)


def _observed_document_changes(
    result: Mapping[str, Any], request: "PythonExecutionRequest"
) -> list[dict[str, Any]]:
    supplied = result.get("observedDocumentChanges")
    if isinstance(supplied, (list, tuple)):
        normalized = []
        for item in supplied:
            if not isinstance(item, Mapping):
                continue
            document_id = str(item.get("documentId") or "")
            if not document_id:
                continue
            normalized.append(
                {
                    "documentId": document_id,
                    "beforeFingerprint": item.get("beforeFingerprint"),
                    "afterFingerprint": item.get("afterFingerprint"),
                    "declared": document_id == request.document_id,
                }
            )
        return sorted(normalized, key=lambda item: item["documentId"])

    changes: list[dict[str, Any]] = []
    before = result.get("beforeModel")
    after = result.get("afterModel")
    if (
        request.document_id
        and isinstance(before, Mapping)
        and isinstance(after, Mapping)
    ):
        before_fingerprint = fingerprint_model(before)
        after_fingerprint = fingerprint_model(after)
        if before_fingerprint != after_fingerprint:
            changes.append(
                {
                    "documentId": request.document_id,
                    "beforeFingerprint": before_fingerprint,
                    "afterFingerprint": after_fingerprint,
                    "declared": True,
                }
            )
    for document_id in sorted(set(result.get("scopeViolations") or [])):
        if document_id == request.document_id:
            continue
        changes.append(
            {
                "documentId": str(document_id),
                "beforeFingerprint": None,
                "afterFingerprint": None,
                "declared": False,
            }
        )
    return changes


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
    progress_callback: Optional[Callable[[str, str, bool], None]] = field(
        default=None, repr=False, compare=False
    )
    checkpoint_callback: Optional[Callable[[], None]] = field(
        default=None, repr=False, compare=False
    )

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


class ObservedLivePythonError(RuntimeError):
    """Carry exact before/after evidence when live Python raises."""

    def __init__(self, cause: BaseException, result: Mapping[str, Any]) -> None:
        super().__init__(str(cause) or type(cause).__name__)
        self.cause = cause
        self.result = result


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
        activity: Optional[OperationActivityStore] = None,
    ) -> None:
        self._host = host
        self._transactions = transactions
        self._reviews = reviews
        self._checkpoints = checkpoints
        self._audit = audit
        self._operations = operations or OperationStore(max_records=512)
        self._trace = trace
        self._activity = activity

    def _runtime_safety_evidence(
        self, exc: BaseException | None = None
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        snapshot = (
            exc.snapshot
            if isinstance(exc, ScriptingRuntimeUnavailableError)
            else None
        )
        if snapshot is not None:
            return snapshot.to_dict(), agent_recovery_directive(snapshot)
        read_status = getattr(self._host, "scripting_runtime_safety_status", None)
        value = read_status() if callable(read_status) else {}
        status = dict(value) if isinstance(value, Mapping) else {}
        incident = status.get("currentIncident")
        incident_id = (
            str(incident.get("incidentId") or "")
            if isinstance(incident, Mapping)
            else str(status.get("incidentId") or "")
        )
        directive = None
        if incident_id and bool(status.get("automaticRepairAvailable")):
            directive = {
                "tool": "repair_runtime",
                "arguments": {"expectedIncidentId": incident_id},
                "verifyWith": "get_runtime_status",
                "retryOriginalCall": True,
                "maxRepairAttempts": 1,
            }
        return status, directive

    def _capture_document_state(self, document_id: str) -> Mapping[str, Any]:
        capture = getattr(self._host, "capture_stable_snapshot", None)
        if not callable(capture):
            capture = getattr(self._host, "capture_snapshot", None)
        if not callable(capture):
            capture = self._host.capture_model
        value = capture(document_id)
        return value if isinstance(value, Mapping) else dict(value)

    def _document_dirty_state(self, document_id: str) -> bool | None:
        try:
            return next(
                (
                    document.has_unsaved_changes
                    for document in self._host.list_documents()
                    if document.document_id == document_id
                ),
                None,
            )
        except Exception:
            return None

    def _source_file_state(
        self, document_id: str
    ) -> Mapping[str, Any] | None:
        capture = getattr(self._host, "capture_source_file_state", None)
        if not callable(capture):
            return None
        try:
            value = capture(document_id)
        except Exception:
            return None
        return dict(value) if isinstance(value, Mapping) else None

    def _detached_contract(self) -> Mapping[str, Any]:
        return detached_python_registry_for_host(self._host)["pythonExecution"][
            "detachedNamespace"
        ]

    def _detached_policy_failure(
        self, request: PythonExecutionRequest
    ) -> ToolResponse | None:
        try:
            validate_staged_code(request.code or "")
        except PythonPolicyError as exc:
            cause = (
                exc.__cause__
                if isinstance(exc.__cause__, BaseException)
                else exc
            )
            return self._failure(
                "staged_policy_violation",
                str(exc),
                recoverable=True,
                details=_python_error_details(
                    cause, phase="compile", code=request.code or ""
                ),
            )
        return None

    def _detached_failure(
        self,
        request: PythonExecutionRequest,
        exc: BaseException,
        *,
        before_model: Mapping[str, Any],
        dirty_before: bool | None,
        source_before: Mapping[str, Any] | None,
        phase: str,
        generic_code: str,
        generic_message: str,
    ) -> ToolResponse:
        """Return classified failure evidence and prove the live state when possible."""

        observed_result: Mapping[str, Any] = {}
        cause = exc
        if isinstance(exc, ObservedLivePythonError):
            cause = exc.cause
            observed_result = exc.result
        code, message, contract_evidence = _classify_detached_error(
            cause,
            code=request.code or "",
            generic_code=generic_code,
            generic_message=generic_message,
            contract=self._detached_contract(),
        )
        details = _python_error_details(
            cause, phase=phase, code=request.code or ""
        )
        details.update(contract_evidence)
        document_id = request.document_id or ""
        base_fingerprint = fingerprint_model(before_model)
        live_after_fingerprint: str | None = None
        evidence_complete = True
        try:
            live_after_fingerprint = fingerprint_model(
                self._capture_document_state(document_id)
            )
        except BaseException:
            evidence_complete = False
        dirty_after = self._document_dirty_state(document_id)
        source_after = self._source_file_state(document_id)
        source_changed = _source_state_changed(source_before, source_after)
        live_changed = bool(
            live_after_fingerprint is not None
            and live_after_fingerprint != base_fingerprint
        )
        if live_after_fingerprint is None:
            state_may_have_changed = True
            safety_statement = (
                "No preview was created and the detached clone was discarded; "
                "live-state read-back was incomplete."
            )
        elif live_changed:
            state_may_have_changed = True
            safety_statement = (
                "No preview was created and the detached clone was discarded; "
                "the live document changed concurrently and must be read again."
            )
        else:
            state_may_have_changed = False
            safety_statement = (
                "No preview was created, the detached clone was discarded, and "
                "the live document fingerprint is unchanged."
            )
        observed_changes = _observed_document_changes(observed_result, request)
        stage_timings = dict(
            getattr(exc, "stage_timings", {})
            or getattr(cause, "stage_timings", {})
            or observed_result.get("stageTimings", {})
            or {}
        )
        return self._failure(
            code,
            message,
            details=details,
            data={
                "codeHash": _code_hash(request.code or ""),
                "previewCreated": False,
                "detachedCloneDiscarded": True,
                "liveDocumentWasExecutionTarget": False,
                "baseDocumentFingerprint": base_fingerprint,
                "liveAfterFingerprint": live_after_fingerprint,
                "liveDocumentChanged": live_changed,
                "dirtyBefore": dirty_before,
                "dirtyAfter": dirty_after,
                "sourceFileChanged": source_changed,
                "fontSaved": False,
                "stateMayHaveChanged": state_may_have_changed,
                "safetyEvidenceComplete": evidence_complete,
                "safetyStatement": safety_statement,
                "observedDocumentChanges": observed_changes,
                "transactional": True,
                "rollback": {"coverage": "not_needed", "available": False},
                "stageTimings": stage_timings,
                **_bounded_streams(
                    observed_result.get("stdout"),
                    observed_result.get("stderr"),
                    max_output_chars=request.max_output_chars,
                    max_error_chars=request.max_error_chars,
                ),
            },
        )

    @staticmethod
    def _replay_context(value: Mapping[str, Any]) -> dict[str, Any]:
        context = value.get("executionContext")
        if not isinstance(context, Mapping):
            return {}
        return {str(key): item for key, item in context.items()}

    def _release_replay_evidence(self, context: Mapping[str, Any]) -> None:
        evidence_id = str(context.get("nativeReplayEvidenceId") or "")
        release = getattr(self._host, "release_staged_replay_evidence", None)
        if evidence_id and callable(release):
            try:
                release(evidence_id)
            except Exception:
                pass

    def _store_diff(
        self,
        changes: ChangeSet,
        *,
        coverage: CanonicalCoverage | None = None,
    ) -> tuple[OperationRecord, Mapping[str, Any]]:
        resolved_coverage = coverage or CanonicalCoverage.complete()
        items = [public_change_dict(change) for change in changes.changes]
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
                    "canonicalCoverage": resolved_coverage.to_public_dict(),
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
        details: Optional[Mapping[str, Any]] = None,
        receipt: Optional[Mapping[str, Any]] = None,
    ) -> ToolResponse:
        return ToolResponse.failure(
            tool="execute_python",
            effect="code",
            summary=message,
            code=code,
            message=message,
            recoverable=recoverable,
            details=details,
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
        if (
            response.error is not None
            and isinstance(response.error.details, Mapping)
        ):
            details["pythonError"] = dict(response.error.details)
        observed_changes = response.data.get("observedDocumentChanges")
        if isinstance(observed_changes, (list, tuple)):
            details["observedDocumentChanges"] = list(observed_changes)
        elif "documentIds" in response.data:
            details["observedDocumentChanges"] = [
                {
                    "documentId": str(document_id),
                    "beforeFingerprint": None,
                    "afterFingerprint": None,
                    "declared": str(document_id) == request.document_id,
                }
                for document_id in response.data.get("documentIds") or []
            ]
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
            if record is None or record.kind != "python_live_approval":
                return self._failure("review_unavailable", "The open-world Python approval is missing, expired, or already consumed.")
            stored = PythonExecutionRequest.from_stored_dict(record.payload["request"])
            try:
                validate_no_source_save(stored.code or "")
            except PythonPolicyError as exc:
                if isinstance(exc.__cause__, SyntaxError):
                    return self._failure(
                        "invalid_code",
                        str(exc),
                        details=_python_error_details(
                            exc.__cause__,
                            phase="compile",
                            code=stored.code or "",
                        ),
                    )
                return self._failure("source_save_forbidden", str(exc))
            if self._trace is not None and stored.document_id:
                self._trace.bind_document(stored.document_id)
            return self._confirm_live(stored, record.payload, review_id=record.operation_id)

        if not request.code or not request.reason:
            return self._failure("invalid_request", "code and reason are required.")
        try:
            validate_no_source_save(request.code)
        except PythonPolicyError as exc:
            if isinstance(exc.__cause__, SyntaxError):
                return self._failure(
                    "invalid_code",
                    str(exc),
                    details=_python_error_details(
                        exc.__cause__,
                        phase="compile",
                        code=request.code or "",
                    ),
                )
            return self._failure("source_save_forbidden", str(exc))
        if not 1 <= int(request.max_output_chars) <= MAX_OUTPUT_CHARS:
            return self._failure(
                "invalid_request",
                "maxOutputChars must be between 1 and {}.".format(MAX_OUTPUT_CHARS),
            )
        if not 1 <= int(request.max_error_chars) <= MAX_OUTPUT_CHARS:
            return self._failure(
                "invalid_request",
                "maxErrorChars must be between 1 and {}.".format(MAX_OUTPUT_CHARS),
            )
        if request.intended_effect not in {"read", "document_edit", "files_or_external"}:
            return self._failure("invalid_effect", "intendedEffect is not supported.")
        if request.execution_mode not in {"staged_document", "live_open_world"}:
            return self._failure("invalid_execution_mode", "executionMode is not supported.")
        if request.intended_effect == "read":
            if not request.document_id:
                return self._failure(
                    "document_context_required",
                    "read_only requires a documentId so execution can use a detached clone; use live_open_world for global host inspection.",
                )
            policy_failure = self._detached_policy_failure(request)
            if policy_failure is not None:
                return policy_failure
            return self._execute_read(request)
        if not request.document_id or not request.expected_document_fingerprint:
            return self._failure(
                "document_context_required",
                "Document mutations and external execution require an explicit document and fingerprint.",
            )
        if request.execution_mode == "staged_document":
            policy_failure = self._detached_policy_failure(request)
            if policy_failure is not None:
                return policy_failure
            return self._preview_staged(request)
        return self._preview_live(request)

    def _execute_read(self, request: PythonExecutionRequest) -> ToolResponse:
        if request.document_id:
            return self._execute_detached_read(request)
        capture_source = getattr(self._host, "capture_source_file_state", None)
        source_before = (
            capture_source(request.document_id)
            if request.document_id and callable(capture_source)
            else None
        )
        fallback_before = (
            self._capture_document_state(request.document_id)
            if request.document_id
            and not bool(
                getattr(self._host, "observes_live_python_exceptions", False)
            )
            else None
        )
        try:
            result = self._host.run_live_python(request)
        except ObservedLivePythonError as observed_error:
            _debug_python_exception()
            result = observed_error.result
            source_save_blocked = isinstance(
                observed_error.cause, SourceSaveForbiddenError
            )
            runtime_unavailable = isinstance(
                observed_error.cause, ScriptingRuntimeUnavailableError
            )
            runtime_safety, agent_recovery = self._runtime_safety_evidence(
                observed_error.cause
            )
            runtime_busy = bool(
                isinstance(
                    observed_error.cause, ScriptingRuntimeUnavailableError
                )
                and runtime_safety.get("state") == "active"
            )
            runtime_unavailable = bool(
                runtime_unavailable
                or runtime_safety.get("state")
                in {"degraded", "recovery_required"}
            )
            source_save_blocked = bool(source_save_blocked and not runtime_unavailable)
            if request.document_id and self._trace is not None:
                before = result.get("beforeModel")
                after = result.get("afterModel")
                if isinstance(before, Mapping) and isinstance(after, Mapping):
                    failed_changes = diff_models(before, after)
                    self._trace.observe_transition(
                        request.document_id,
                        before,
                        after,
                        change_set=failed_changes,
                        coverage=_recovery_only_canonical_coverage(
                            failed_changes
                        ),
                    )
            details = _python_error_details(
                observed_error.cause,
                phase="evaluation",
                code=request.code or "",
            )
            observed_document_changes = _observed_document_changes(
                result, request
            )
            receipt = self._audit.record(
                tool="execute_python",
                effect="code",
                status="error",
                document_id=request.document_id,
                details={
                    "reason": request.reason,
                    "declaredEffect": "read",
                    "context": _context_details(request),
                    "observedDocumentChanges": observed_document_changes,
                    "sourceSaveBlocked": source_save_blocked,
                    "scriptingRuntimeUnavailable": runtime_unavailable,
                    "scriptingRuntimeSafety": runtime_safety,
                    **details,
                },
            )
            return self._failure(
                (
                    "source_save_forbidden"
                    if source_save_blocked
                    else (
                        "scripting_runtime_busy"
                        if runtime_busy
                        else (
                            "scripting_runtime_unavailable"
                            if runtime_unavailable
                            else "python_execution_failed"
                        )
                    )
                ),
                (
                    "Python was stopped at the working-source save boundary."
                    if source_save_blocked
                    else (
                        "Another live Python execution owns the scripting interlock."
                        if runtime_busy
                        else (
                            "Strict scripting safety is unavailable."
                            if runtime_unavailable
                            else "Python evaluation failed safely."
                        )
                    )
                ),
                details=details,
                data={
                    "codeHash": _code_hash(request.code or ""),
                    "observedDocumentChanges": observed_document_changes,
                    "transactional": False,
                    "scriptingRuntimeSafety": runtime_safety,
                    **(
                        {"agentRecovery": agent_recovery}
                        if agent_recovery is not None
                        else {}
                    ),
                    "rollback": {
                        "coverage": "unavailable",
                        "available": False,
                    },
                    **_bounded_streams(
                        result.get("stdout"),
                        result.get("stderr"),
                        max_output_chars=request.max_output_chars,
                        max_error_chars=request.max_error_chars,
                    ),
                },
                receipt=receipt.to_dict(),
            )
        except Exception as exc:
            _debug_python_exception()
            source_save_blocked = isinstance(exc, SourceSaveForbiddenError)
            runtime_unavailable = isinstance(
                exc, ScriptingRuntimeUnavailableError
            )
            runtime_safety, agent_recovery = self._runtime_safety_evidence(exc)
            runtime_busy = bool(
                isinstance(exc, ScriptingRuntimeUnavailableError)
                and runtime_safety.get("state") == "active"
            )
            runtime_unavailable = bool(
                runtime_unavailable
                or runtime_safety.get("state")
                in {"degraded", "recovery_required"}
            )
            source_save_blocked = bool(source_save_blocked and not runtime_unavailable)
            result: dict[str, Any] = {}
            if (
                request.document_id
                and fallback_before is not None
                and self._trace is not None
            ):
                try:
                    failed_after = self._capture_document_state(
                        request.document_id
                    )
                    failed_changes = diff_models(
                        fallback_before, failed_after
                    )
                    self._trace.observe_transition(
                        request.document_id,
                        fallback_before,
                        failed_after,
                        change_set=failed_changes,
                        coverage=_recovery_only_canonical_coverage(failed_changes),
                    )
                    result = {
                        "beforeModel": fallback_before,
                        "afterModel": failed_after,
                    }
                except Exception:
                    pass
            details = _python_error_details(
                exc, phase="evaluation", code=request.code or ""
            )
            return self._failure(
                (
                    "source_save_forbidden"
                    if source_save_blocked
                    else (
                        "scripting_runtime_busy"
                        if runtime_busy
                        else (
                            "scripting_runtime_unavailable"
                            if runtime_unavailable
                            else "python_execution_failed"
                        )
                    )
                ),
                (
                    "Python was stopped at the working-source save boundary."
                    if source_save_blocked
                    else (
                        "Another live Python execution owns the scripting interlock."
                        if runtime_busy
                        else (
                            "Strict scripting safety is unavailable."
                            if runtime_unavailable
                            else "Python evaluation failed safely."
                        )
                    )
                ),
                details=details,
                data={
                    "codeHash": _code_hash(request.code or ""),
                    "observedDocumentChanges": _observed_document_changes(
                        result, request
                    ),
                    "transactional": False,
                    "scriptingRuntimeSafety": runtime_safety,
                    **(
                        {"agentRecovery": agent_recovery}
                        if agent_recovery is not None
                        else {}
                    ),
                    "rollback": {
                        "coverage": "unavailable",
                        "available": False,
                    },
                    **_bounded_streams(
                        "",
                        "",
                        max_output_chars=request.max_output_chars,
                        max_error_chars=request.max_error_chars,
                    ),
                },
            )
        after = None
        violated = False
        observed_change_count = 0
        if request.document_id:
            before = result.get("beforeModel")
            after = result.get("afterModel")
            if not isinstance(before, Mapping) or not isinstance(after, Mapping):
                raise RuntimeError(
                    "live Python host returned no canonical observation"
                )
            violated = fingerprint_model(before) != fingerprint_model(after)
            observed_change_count = len(diff_models(before, after).changes)
            if self._trace is not None:
                observed = diff_models(before, after)
                self._trace.observe_transition(
                    request.document_id,
                    before,
                    after,
                    change_set=observed,
                    coverage=(
                        _recovery_only_canonical_coverage(observed)
                        if violated
                        else CanonicalCoverage.complete()
                    ),
                )
        source_after = (
            capture_source(request.document_id)
            if request.document_id and callable(capture_source)
            else None
        )
        source_file_changed = bool(
            source_before is not None
            and (
                source_after is None
                or source_before.get("contentFingerprint")
                != source_after.get("contentFingerprint")
                or source_before.get("exists") != source_after.get("exists")
            )
        )
        if violated or source_file_changed:
            force_dirty = getattr(self._host, "force_document_dirty", None)
            if callable(force_dirty) and request.document_id:
                try:
                    force_dirty(request.document_id)
                except Exception:
                    pass
        observed_document_changes = _observed_document_changes(result, request)
        undeclared = [
            item["documentId"]
            for item in observed_document_changes
            if not item["declared"]
        ]
        receipt = self._audit.record(
            tool="execute_python",
            effect="code",
            status="warning" if violated or source_file_changed or undeclared else "success",
            document_id=request.document_id,
            details={
                "codeHash": _code_hash(request.code or ""),
                "reason": request.reason,
                "declaredEffect": "read",
                "context": _context_details(request),
                "observedDocumentChanges": observed_document_changes,
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
        if source_file_changed:
            status = "warning"
            warnings += (
                ToolWarning(
                    code="source_file_changed",
                    message="Read-intent Python changed the Glyphs source file.",
                    target={"documentId": request.document_id},
                ),
            )
        if undeclared:
            status = "warning"
            warnings += (
                ToolWarning(
                    code="observed_undeclared_document_change",
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
                **_bounded_streams(
                    result.get("stdout"),
                    result.get("stderr"),
                    max_output_chars=request.max_output_chars,
                    max_error_chars=request.max_error_chars,
                ),
                "observedDocumentChanges": observed_document_changes,
                "changed": bool(violated),
                "observedChangeCount": observed_change_count,
                "stateMayHaveChanged": bool(violated or source_file_changed),
                "sourceFileChanged": source_file_changed,
                "fontSaved": False,
                "transactional": False,
                "rollback": {"coverage": "unavailable", "available": False},
                "timeoutEnforcement": "cooperative",
            },
        )

    def _execute_detached_read(
        self, request: PythonExecutionRequest
    ) -> ToolResponse:
        """Run document-bound read Python on a clone and prove live purity."""

        document_id = request.document_id or ""
        before = self._capture_document_state(document_id)
        before_fingerprint = fingerprint_model(before)
        requested_fingerprint = request.expected_document_fingerprint
        requested_fingerprint_matched = (
            None
            if not requested_fingerprint
            else requested_fingerprint == before_fingerprint
        )
        source_before = self._source_file_state(document_id)
        dirty_before = self._document_dirty_state(document_id)
        try:
            result = self._host.preview_python(request, before)
        except ActivityCancelled:
            raise
        except BaseException as exc:
            _debug_python_exception()
            cause = (
                exc.cause
                if isinstance(exc, ObservedLivePythonError)
                else exc
            )
            return self._detached_failure(
                request,
                exc,
                before_model=before,
                dirty_before=dirty_before,
                source_before=source_before,
                phase="evaluation",
                generic_code=(
                    "source_save_forbidden"
                    if isinstance(cause, SourceSaveForbiddenError)
                    else "python_execution_failed"
                ),
                generic_message=(
                    "Detached read-only Python was stopped at the source-save boundary."
                    if isinstance(cause, SourceSaveForbiddenError)
                    else "Detached read-only Python failed safely."
                ),
            )
        replay_context: dict[str, Any] = {}
        try:
            after = result.get("afterModel")
            if not isinstance(after, Mapping):
                raise ValueError(
                    "detached read-only Python returned no canonical clone state"
                )
            replay_context = dict(result.get("executionContext") or {})
            self._release_replay_evidence(replay_context)
            detached_changes = diff_models(before, after)
        except ActivityCancelled:
            raise
        except BaseException as exc:
            self._release_replay_evidence(replay_context)
            return self._detached_failure(
                request,
                ObservedLivePythonError(exc, result),
                before_model=before,
                dirty_before=dirty_before,
                source_before=source_before,
                phase="verification",
                generic_code="python_execution_failed",
                generic_message=(
                    "Detached read-only Python returned invalid verification evidence."
                ),
            )
        live_after = self._capture_document_state(document_id)
        live_after_fingerprint = fingerprint_model(live_after)
        live_changed = live_after_fingerprint != before_fingerprint
        dirty_after = self._document_dirty_state(document_id)
        source_after = self._source_file_state(document_id)
        source_changed = _source_state_changed(source_before, source_after)
        observed_document_changes = list(
            result.get("observedDocumentChanges") or ()
        )
        warnings: list[ToolWarning] = []
        if requested_fingerprint_matched is False:
            warnings.append(
                ToolWarning(
                    code="read_rebased_to_current_document",
                    message=(
                        "The supplied document fingerprint was stale; detached "
                        "read-only Python used the latest stable live snapshot."
                    ),
                    target={
                        "documentId": document_id,
                        "expectedDocumentFingerprint": requested_fingerprint,
                        "baseDocumentFingerprint": before_fingerprint,
                    },
                )
            )
        if detached_changes.changes:
            warnings.append(
                ToolWarning(
                    code="read_intent_changed_detached_clone",
                    message=(
                        "The code changed only its detached clone; the live "
                        "document remained outside the execution context."
                    ),
                    target={"changeCount": len(detached_changes.changes)},
                )
            )
        if live_changed or observed_document_changes:
            warnings.append(
                ToolWarning(
                    code="live_state_changed_concurrently",
                    message=(
                        "Live document state changed while detached Python was "
                        "running; read the document again before planning."
                    ),
                    target={"documentId": document_id},
                )
            )
        if source_changed:
            warnings.append(
                ToolWarning(
                    code="persistence_changed_during_read",
                    message=(
                        "The source file changed concurrently; detached Python "
                        "did not write the working source."
                    ),
                    target={"documentId": document_id},
                )
            )
        receipt = self._audit.record(
            tool="execute_python",
            effect="code",
            status="warning" if warnings else "success",
            document_id=document_id,
            details={
                "codeHash": _code_hash(request.code or ""),
                "reason": request.reason,
                "declaredEffect": "read",
                "executionMode": "detached_read_only",
                "beforeFingerprint": before_fingerprint,
                "liveAfterFingerprint": live_after_fingerprint,
                "expectedDocumentFingerprint": requested_fingerprint,
                "expectedDocumentFingerprintMatched": requested_fingerprint_matched,
                "detachedChangeCount": len(detached_changes.changes),
                "sourceFileChanged": source_changed,
            },
        )
        return ToolResponse.success(
            tool="execute_python",
            effect="code",
            status="warning" if warnings else "success",
            summary="Detached read-only Python completed; the live document was not an execution target.",
            warnings=tuple(warnings),
            audit_receipt=receipt.to_dict(),
            data={
                "codeHash": _code_hash(request.code or ""),
                **_bounded_streams(
                    result.get("stdout"),
                    result.get("stderr"),
                    max_output_chars=request.max_output_chars,
                    max_error_chars=request.max_error_chars,
                ),
                "executionMode": "detached_read_only",
                "baseDocumentFingerprint": before_fingerprint,
                "expectedDocumentFingerprint": requested_fingerprint,
                "expectedDocumentFingerprintMatched": requested_fingerprint_matched,
                "liveAfterFingerprint": live_after_fingerprint,
                "liveDocumentChanged": live_changed,
                "detachedDocumentChanged": bool(detached_changes.changes),
                "detachedChangeCount": len(detached_changes.changes),
                "observedDocumentChanges": observed_document_changes,
                "dirtyBefore": dirty_before,
                "dirtyAfter": dirty_after,
                "sourceFileChanged": source_changed,
                "stateMayHaveChanged": live_changed,
                "fontSaved": False,
                "transactional": True,
                "rollback": {"coverage": "not_needed", "available": False},
                "timeoutEnforcement": "cooperative",
                "stageTimings": dict(result.get("stageTimings") or {}),
            },
        )

    def _preview_staged(self, request: PythonExecutionRequest) -> ToolResponse:
        before = self._capture_document_state(request.document_id or "")
        if self._trace is not None and request.document_id:
            self._trace.observe_model(request.document_id, before)
        before_fingerprint = fingerprint_model(before)
        if before_fingerprint != request.expected_document_fingerprint:
            return self._failure("stale_document", "The document changed before staged execution.")
        document_id = request.document_id or ""
        dirty_before = self._document_dirty_state(document_id)
        source_before = self._source_file_state(document_id)
        phase = {"value": "setup"}

        def progress(name: str, message: str, cancellable: bool = True) -> None:
            phase["value"] = str(name or phase["value"])
            if self._activity is not None:
                self._activity.advance_current(
                    phase["value"], message, cancellable=bool(cancellable)
                )

        def checkpoint() -> None:
            if self._activity is not None:
                self._activity.checkpoint_current()

        execution_request = replace(
            request,
            progress_callback=progress,
            checkpoint_callback=checkpoint,
        )
        try:
            progress("cloning", "Cloning and capturing the document", True)
            checkpoint()
            preview = self._host.preview_python(execution_request, before)
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
        except ActivityCancelled:
            raise
        except BaseException as exc:
            _debug_python_exception()
            return self._detached_failure(
                request,
                exc,
                before_model=before,
                dirty_before=dirty_before,
                source_before=source_before,
                phase=phase["value"],
                generic_code="python_preview_failed",
                generic_message="Detached Python preview failed safely.",
            )
        observed_document_changes = _observed_document_changes(preview, request)
        undeclared_document_changes = [
            item
            for item in observed_document_changes
            if not bool(item.get("declared"))
        ]
        replay_context = self._replay_context(preview)
        if undeclared_document_changes:
            self._release_replay_evidence(replay_context)
            return self._failure(
                "staged_scope_violation",
                "Staged Python changed one or more live documents; confirmation is refused.",
                data={"observedDocumentChanges": undeclared_document_changes},
            )
        context_violations = preview.get("contextViolations")
        if (
            isinstance(context_violations, Mapping)
            and int(context_violations.get("count") or 0) > 0
        ):
            self._release_replay_evidence(replay_context)
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
            self._release_replay_evidence(replay_context)
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
        try:
            capabilities = staged_lifecycle_capabilities(before, after, changes)
        except ValueError as exc:
            self._release_replay_evidence(replay_context)
            return self._failure(
                "unsupported_staged_change",
                str(exc),
                data={
                    "unsupportedCount": 1,
                    "changedRoots": list(
                        dict.fromkeys(
                            change.path[0]
                            for change in changes.changes
                            if change.path
                        )
                    ),
                    "unsupportedPaths": [],
                    "truncated": False,
                },
            )
        provided_capabilities = tuple(
            sorted(set(str(value) for value in preview.get("capabilities", ())) )
        )
        if provided_capabilities and provided_capabilities != capabilities:
            self._release_replay_evidence(replay_context)
            return self._failure(
                "python_preview_failed",
                "Detached Python preview returned inconsistent lifecycle capabilities.",
            )
        diagnostics = unsupported_change_diagnostics(
            changes, limit=100, capabilities=capabilities
        )
        provided_writable = preview.get("writableChangeSet")
        if isinstance(provided_writable, ChangeSet):
            if provided_writable.before_fingerprint != before_fingerprint:
                self._release_replay_evidence(replay_context)
                return self._failure(
                    "python_preview_failed",
                    "Detached Python preview returned a stale writable change set.",
                )
            try:
                writable_after = provided_writable.apply(before)
            except (KeyError, ValueError):
                self._release_replay_evidence(replay_context)
                return self._failure(
                    "python_preview_failed",
                    "Detached Python preview returned an invalid writable change set.",
                )
            if fingerprint_model(writable_after) != provided_writable.after_fingerprint:
                self._release_replay_evidence(replay_context)
                return self._failure(
                    "python_preview_failed",
                    "Detached Python preview returned an unreproducible writable change set.",
                )
            writable_changes = provided_writable
        else:
            writable_changes = writable_subset(
                before, changes, capabilities=capabilities
            )
        supports = getattr(self._host, "supports_change_set", None)
        if callable(supports):
            try:
                host_supported = bool(
                    supports(writable_changes, capabilities=capabilities)
                )
            except TypeError:
                host_supported = bool(supports(writable_changes))
        else:
            host_supported = True
        if diagnostics["unsupportedCount"] or not host_supported:
            self._release_replay_evidence(replay_context)
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
        canonical_coverage = _staged_canonical_coverage(changes, replay_context)
        bounded_streams = _bounded_streams(
            preview.get("stdout"),
            preview.get("stderr"),
            max_output_chars=request.max_output_chars,
            max_error_chars=request.max_error_chars,
        )
        diff_operation, public_change_set = self._store_diff(
            changes,
            coverage=canonical_coverage,
        )
        review = self._reviews.create(
            kind="change_preview",
            ttl_seconds=REVIEW_TTL_SECONDS,
            payload={
                "source": "python_staged",
                "documentId": request.document_id,
                "baseDocumentFingerprint": before_fingerprint,
                "proposedFingerprint": changes.after_fingerprint,
                "applicable": True,
                "request": request.to_stored_dict(),
                "codeHash": _code_hash(request.code or ""),
                "changeSet": changes,
                "writableChangeSet": writable_changes,
                "expectedAfterModel": after,
                "capabilities": capabilities,
                "executionContext": replay_context,
                "boundedStreams": bounded_streams,
                "observedDocumentChanges": observed_document_changes,
                "stageTimings": dict(preview.get("stageTimings") or {}),
                "diffOperationId": diff_operation.operation_id,
                "canonicalCoverage": canonical_coverage,
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
                "capabilities": list(capabilities),
                "observedDocumentChanges": observed_document_changes,
                "stageTimings": dict(preview.get("stageTimings") or {}),
                "canonicalCoverage": canonical_coverage.to_public_dict(),
            },
        )
        glyphs = before.get("glyphs", {})
        large_scope_warning = (
            (
                ToolWarning(
                    code="large_staged_scope",
                    message=(
                        "This full-document staged preview is large; prefer an "
                        "explicit glyph/layer scope when the task permits it."
                    ),
                    target={
                        "glyphCount": len(glyphs)
                        if isinstance(glyphs, Mapping)
                        else len(tuple(glyphs or ())),
                        "stageTimings": dict(preview.get("stageTimings") or {}),
                    },
                ),
            )
            if not request.glyph_name
            and (
                len(glyphs)
                if isinstance(glyphs, Mapping)
                else len(tuple(glyphs or ()))
            )
            >= 300
            else ()
        )
        return ToolResponse.success(
            tool="execute_python",
            effect="code",
            status="success",
            summary="Detached Python produced an immutable semantic preview; the live document is unchanged.",
            audit_receipt=receipt.to_dict(),
            warnings=large_scope_warning,
            data={
                "previewId": review.operation_id,
                "expiresAt": _iso_timestamp(review.expires_at),
                "documentId": request.document_id,
                "baseDocumentFingerprint": before_fingerprint,
                "proposedFingerprint": changes.after_fingerprint,
                "applicable": True,
                "resolvedTargetCount": len(changes.changes),
                "normalizedOperations": [],
                "codeHash": _code_hash(request.code or ""),
                "executionMode": "staged_document",
                "liveDocumentChanged": False,
                "changeSet": public_change_set,
                "constraints": {
                    "before": {
                        "baseDocumentFingerprintMatched": True,
                        "scopeViolationCount": 0,
                    },
                    "after": {
                        "nativeArchiveEquivalent": True,
                        "semanticPatchReproducible": True,
                    },
                },
                "blockers": [],
                "fontSaved": False,
                "operationId": diff_operation.operation_id,
                "canonicalCoverage": canonical_coverage.to_public_dict(),
                "stageTimings": dict(preview.get("stageTimings") or {}),
                "observedDocumentChanges": observed_document_changes,
                **bounded_streams,
            },
        )

    def _preview_live(self, request: PythonExecutionRequest) -> ToolResponse:
        current = self._capture_document_state(request.document_id or "")
        if self._trace is not None and request.document_id:
            self._trace.observe_model(request.document_id, current)
        if fingerprint_model(current) != request.expected_document_fingerprint:
            return self._failure("stale_document", "The document changed before Python review.")
        review = self._reviews.create(
            kind="python_live_approval",
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
                "approvalId": review.operation_id,
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
        before = self._capture_document_state(request.document_id or "")
        capabilities = tuple(
            sorted(set(str(value) for value in payload.get("capabilities", ())))
        )
        execution_context = dict(payload.get("executionContext") or {})
        evidence_validator = getattr(
            self._host, "validate_staged_replay_evidence", None
        )
        if callable(evidence_validator):
            try:
                evidence_available = bool(
                    evidence_validator(
                        request.document_id or "",
                        execution_context,
                        before_fingerprint=fingerprint_model(before),
                        after_fingerprint=fingerprint_model(expected_after),
                        capabilities=capabilities,
                    )
                )
            except Exception:
                evidence_available = False
            if not evidence_available:
                self._release_replay_evidence(execution_context)
                return self._failure(
                    "review_unavailable",
                    "The staged structural replay evidence is missing, expired, or mismatched.",
                )
        plan = VerifiedMutationPlan(
            document_id=request.document_id or "",
            operation_id=review_id,
            before_model=before,
            expected_after_model=dict(expected_after),
            writable_change_set=writable,
            observed_change_set=changes,
            capabilities=capabilities,
            execution_context=execution_context,
            coverage=(
                payload.get("canonicalCoverage")
                if isinstance(payload.get("canonicalCoverage"), CanonicalCoverage)
                else CanonicalCoverage.complete()
            ),
        )
        try:
            transaction = self._transactions.apply_plan(plan)
        except StaleDocumentError:
            return self._failure("stale_document", "The document changed after Python review.")
        except TransactionVerificationError as exc:
            verification_failure = (str(exc) or "transaction verification failed")[:500]
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
                    "verificationFailure": verification_failure,
                    **exc.to_public_dict(),
                },
            )
            return self._failure(
                "transaction_failed",
                "The reviewed Python patch failed verification.",
                data={
                    "verificationFailure": verification_failure,
                    **exc.to_public_dict(),
                },
                receipt=receipt.to_dict(),
            )
        finally:
            self._release_replay_evidence(execution_context)
        checkpoint = (
            self._checkpoints.create(
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
                    "capabilities": capabilities,
                    "canonicalCoverage": transaction.coverage,
                },
            )
            if transaction.revert_available
            else None
        )
        receipt = self._audit.record(
            tool="execute_python",
            effect="code",
            status=(
                "warning"
                if transaction.persistence_reconciliation.get("relationship")
                in {"saved_intermediate", "source_changed_unclassified"}
                else "success"
            ),
            document_id=request.document_id,
            details={
                "codeHash": payload.get("codeHash"),
                "operationId": review_id,
                "reason": request.reason,
                "executionMode": "staged_document",
                "context": _context_details(request),
                "beforeFingerprint": transaction.before_fingerprint,
                "afterFingerprint": transaction.after_fingerprint,
                "changeCount": transaction.change_count,
                "capabilities": list(capabilities),
                "rollbackCoverage": "document_inverse",
                "canonicalCoverage": transaction.coverage.to_public_dict(),
                "persistenceReconciliation": dict(
                    transaction.persistence_reconciliation
                ),
            },
        )
        persistence_warning = ()
        if transaction.persistence_reconciliation.get("relationship") in {
            "saved_intermediate",
            "source_changed_unclassified",
        }:
            persistence_warning = (
                ToolWarning(
                    code="persistence_reconciled",
                    message=(
                        "The source changed while the staged patch was applied; "
                        "the exact live result was kept and history was rebased."
                    ),
                    target=dict(transaction.persistence_reconciliation),
                ),
            )
        return ToolResponse.success(
            tool="execute_python",
            effect="code",
            summary="The reviewed Python change set was applied and verified without rerunning the script.",
            status="warning" if persistence_warning else "success",
            warnings=persistence_warning,
            audit_receipt=receipt.to_dict(),
            metadata=OperationMetadata.create(operation_id=review_id),
            data={
                "executionId": checkpoint.operation_id if checkpoint else None,
                "codeHash": payload.get("codeHash"),
                "beforeFingerprint": transaction.before_fingerprint,
                "afterFingerprint": transaction.after_fingerprint,
                "changeCount": transaction.change_count,
                "transactionCount": 1,
                "fontSaved": False,
                "sourceFileChanged": transaction.source_file_changed,
                "persistenceReconciliation": dict(
                    transaction.persistence_reconciliation
                ),
                "transactional": True,
                "externalEffectsVerifiable": True,
                "canonicalCoverage": transaction.coverage.to_public_dict(),
                "rollback": {
                    "available": transaction.revert_available,
                    "coverage": "document_inverse",
                    "expiresAt": (
                        _iso_timestamp(checkpoint.expires_at) if checkpoint else None
                    ),
                },
                "stageTimings": dict(payload.get("stageTimings") or {}),
                "observedDocumentChanges": list(
                    payload.get("observedDocumentChanges") or []
                ),
                **dict(
                    payload.get("boundedStreams")
                    or _bounded_streams(
                        payload.get("stdout"),
                        payload.get("stderr"),
                        max_output_chars=request.max_output_chars,
                        max_error_chars=request.max_error_chars,
                    )
                ),
            },
        )

    def apply_staged_preview(
        self,
        record: OperationRecord,
        *,
        operation_id: str,
        reason: Optional[str] = None,
    ) -> ToolResponse:
        """Apply an immutable staged-Python patch without rerunning code."""

        if (
            record.kind != "change_preview"
            or record.payload.get("source") != "python_staged"
        ):
            return self._failure(
                "preview_mismatch",
                "The preview is not a staged-Python document preview.",
            )
        stored = PythonExecutionRequest.from_stored_dict(record.payload["request"])
        if reason is not None:
            stored = replace(stored, reason=reason)
        return self._confirm_staged(
            stored,
            record.payload,
            review_id=operation_id,
        )

    def _confirm_live(
        self,
        request: PythonExecutionRequest,
        payload: Mapping[str, Any],
        *,
        review_id: str,
    ) -> ToolResponse:
        before = self._capture_document_state(request.document_id or "")
        capture_source = getattr(self._host, "capture_source_file_state", None)
        source_before = (
            capture_source(request.document_id or "")
            if callable(capture_source)
            else None
        )
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

        def failed_execution(
            exc: BaseException,
            after: Mapping[str, Any],
            result: Optional[Mapping[str, Any]] = None,
        ) -> ToolResponse:
            source_save_blocked = isinstance(exc, SourceSaveForbiddenError)
            runtime_safety, agent_recovery = self._runtime_safety_evidence(exc)
            runtime_busy = bool(
                isinstance(exc, ScriptingRuntimeUnavailableError)
                and runtime_safety.get("state") == "active"
            )
            runtime_unavailable = bool(
                isinstance(exc, ScriptingRuntimeUnavailableError)
                or runtime_safety.get("state")
                in {"degraded", "recovery_required"}
            )
            source_save_blocked = bool(source_save_blocked and not runtime_unavailable)
            source_after = (
                capture_source(request.document_id or "")
                if callable(capture_source)
                else None
            )
            source_file_changed = bool(
                source_before is not None
                and (
                    source_after is None
                    or source_before.get("contentFingerprint")
                    != source_after.get("contentFingerprint")
                    or source_before.get("exists") != source_after.get("exists")
                )
            )
            failed_changes = diff_models(before, after)
            if failed_changes.changes or source_file_changed:
                force_dirty = getattr(self._host, "force_document_dirty", None)
                if callable(force_dirty) and request.document_id:
                    try:
                        force_dirty(request.document_id)
                    except Exception:
                        pass
            if self._trace is not None and request.document_id:
                self._trace.observe_transition(
                    request.document_id,
                    before,
                    after,
                    change_set=failed_changes,
                    coverage=_recovery_only_canonical_coverage(
                        failed_changes
                    ),
                )
            after_fingerprint = fingerprint_model(after)
            checkpoint = self._checkpoints.create(
                kind="python_checkpoint",
                ttl_seconds=ROLLBACK_TTL_SECONDS,
                payload={
                    "documentId": request.document_id,
                    "codeHash": payload.get("codeHash"),
                    "beforeFingerprint": before_fingerprint,
                    "afterFingerprint": after_fingerprint,
                    "stateMayHaveChanged": True,
                    "sourceFileChanged": source_file_changed,
                    "inverse": None,
                    "coverage": "recovery_only",
                    "recoveryPath": recovery_path,
                },
            )
            self._register_recovery(checkpoint, recovery_path)
            error_details = _python_error_details(
                exc,
                phase="evaluation",
                code=request.code or "",
            )
            observed_document_changes = _observed_document_changes(
                result or {"beforeModel": before, "afterModel": after}, request
            )
            observed_result = result or {}
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
                    "observedDocumentChanges": observed_document_changes,
                    "sourceSaveBlocked": source_save_blocked,
                    "scriptingRuntimeUnavailable": runtime_unavailable,
                    "scriptingRuntimeSafety": runtime_safety,
                    **error_details,
                },
            )
            return self._failure(
                (
                    "source_save_forbidden"
                    if source_save_blocked
                    else (
                        "scripting_runtime_busy"
                        if runtime_busy
                        else (
                            "scripting_runtime_safety_lost"
                            if runtime_unavailable
                            else "python_execution_failed"
                        )
                    )
                ),
                (
                    "Open-world Python was stopped at the working-source save boundary."
                    if source_save_blocked
                    else (
                        "Another live Python execution owns the scripting interlock."
                        if runtime_busy
                        else (
                            "Open-world Python ended with degraded scripting safety."
                            if runtime_unavailable
                            else "Open-world Python failed safely."
                        )
                    )
                ),
                details=error_details,
                data={
                    "stateMayHaveChanged": True,
                    "executionId": checkpoint.operation_id,
                    "afterFingerprint": after_fingerprint,
                    "observedAfterFingerprint": after_fingerprint,
                    "observedChangeCount": len(failed_changes.changes),
                    "changed": bool(failed_changes.changes),
                    "rollbackAttempted": False,
                    "rollbackSucceeded": False,
                    "sourceFileChanged": source_file_changed,
                    "fontSaved": False,
                    "observedDocumentChanges": observed_document_changes,
                    "scriptingRuntimeSafety": runtime_safety,
                    **(
                        {"agentRecovery": agent_recovery}
                        if agent_recovery is not None
                        else {}
                    ),
                    **_bounded_streams(
                        observed_result.get("stdout"),
                        observed_result.get("stderr"),
                        max_output_chars=request.max_output_chars,
                        max_error_chars=request.max_error_chars,
                    ),
                    "rollback": {
                        "available": True,
                        "coverage": "recovery_only",
                        "expiresAt": _iso_timestamp(checkpoint.expires_at),
                    },
                },
                receipt=receipt.to_dict(),
            )

        try:
            result = self._host.run_live_python(request)
            after = result.get("afterModel")
            if not isinstance(after, Mapping):
                after = self._capture_document_state(
                    request.document_id or ""
                )
        except ObservedLivePythonError as exc:
            result = exc.result
            after = result.get("afterModel")
            if not isinstance(after, Mapping):
                after = self._capture_document_state(
                    request.document_id or ""
                )
            return failed_execution(exc.cause, after, result)
        except Exception as exc:
            after = self._capture_document_state(request.document_id or "")
            return failed_execution(exc, after)
        changes = diff_models(before, after)
        source_after = (
            capture_source(request.document_id or "")
            if callable(capture_source)
            else None
        )
        source_file_changed = bool(
            source_before is not None
            and (
                source_after is None
                or source_before.get("contentFingerprint")
                != source_after.get("contentFingerprint")
                or source_before.get("exists") != source_after.get("exists")
            )
        )
        if changes.changes:
            force_dirty = getattr(self._host, "force_document_dirty", None)
            if callable(force_dirty) and request.document_id:
                try:
                    force_dirty(request.document_id)
                except Exception:
                    pass
        if source_file_changed:
            return failed_execution(
                RuntimeError("the Glyphs source file changed during live Python"),
                after,
                result,
            )
        canonical_coverage = _recovery_only_canonical_coverage(changes)
        if self._trace is not None and request.document_id:
            self._trace.observe_transition(
                request.document_id,
                before,
                after,
                change_set=changes,
                coverage=canonical_coverage,
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
            "canonicalCoverage": canonical_coverage,
            "recoveryPath": recovery_path,
        }
        checkpoint = self._checkpoints.create(
            kind="python_checkpoint",
            ttl_seconds=ROLLBACK_TTL_SECONDS,
            payload=checkpoint_payload,
        )
        recovery_persisted = self._register_recovery(checkpoint, recovery_path)
        observed_document_changes = _observed_document_changes(result, request)
        undeclared_document_ids = [
            item["documentId"]
            for item in observed_document_changes
            if not bool(item.get("declared"))
        ]
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
                "changed": bool(changes.changes),
                "rollbackCoverage": coverage,
                "externalEffectsVerifiable": False,
                "observedDocumentChanges": observed_document_changes,
                "recoveryPersisted": recovery_persisted,
                "canonicalCoverage": canonical_coverage.to_public_dict(),
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
                        code="observed_undeclared_document_change",
                        message="Open-world Python changed document(s) outside its declared context.",
                        target={"documentIds": undeclared_document_ids},
                    ),
                )
                if undeclared_document_ids
                else ()
            ),
            status="warning",
            data={
                "executionId": checkpoint.operation_id,
                "codeHash": payload.get("codeHash"),
                "beforeFingerprint": before_fingerprint,
                "afterFingerprint": changes.after_fingerprint,
                "changeCount": len(changes.changes),
                "changed": bool(changes.changes),
                "transactional": False,
                "externalEffectsVerifiable": False,
                "timeoutEnforcement": "cooperative",
                "observedDocumentChanges": observed_document_changes,
                "recoveryAvailableAfterRestart": recovery_persisted,
                "fontSaved": False,
                "sourceFileChanged": False,
                "canonicalCoverage": canonical_coverage.to_public_dict(),
                "rollback": {
                    "available": True,
                    "coverage": coverage,
                    "expiresAt": _iso_timestamp(checkpoint.expires_at),
                },
                **_bounded_streams(
                    result.get("stdout"),
                    result.get("stderr"),
                    max_output_chars=request.max_output_chars,
                    max_error_chars=request.max_error_chars,
                ),
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

    def _recovery_failure(
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
            tool="recover_python_checkpoint",
            effect="edit",
            status="error",
            document_id=document_id,
            details={"executionId": execution_id, "errorCode": code, **dict(data or {})},
        )
        return ToolResponse.failure(
            tool="recover_python_checkpoint",
            effect="edit",
            summary=summary,
            code=code,
            message=summary,
            recoverable=recoverable,
            data=data,
            audit_receipt=receipt.to_dict(),
        )

    def recover_checkpoint(
        self,
        *,
        execution_id: str,
        expected_after_fingerprint: str,
        confirm: bool,
        strategy: str = "auto",
    ) -> ToolResponse:
        if not confirm:
            return ToolResponse.failure(
                tool="recover_python_checkpoint",
                effect="edit",
                summary="confirm=true is required for rollback.",
                code="confirmation_required",
                message="Rollback was not confirmed.",
            )
        if strategy not in {"auto", "open_recovery_copy"}:
            return self._recovery_failure(
                code="invalid_strategy",
                summary="Unknown rollback strategy.",
                execution_id=execution_id,
            )
        checkpoint = self._checkpoints.get(execution_id)
        if checkpoint is None or checkpoint.kind != "python_checkpoint":
            finder = getattr(self._host, "find_recovery_checkpoint", None)
            persisted = finder(execution_id) if callable(finder) else None
            if not isinstance(persisted, Mapping):
                return self._recovery_failure(
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
            return self._recovery_failure(
                code="stale_document",
                summary="The requested rollback fingerprint does not match the checkpoint.",
                execution_id=execution_id,
                document_id=document_id,
            )
        if strategy == "open_recovery_copy":
            path = payload.get("recoveryPath")
            if not path:
                return self._recovery_failure(
                    code="recovery_unavailable",
                    summary="This checkpoint has no serialized recovery copy.",
                    execution_id=execution_id,
                    document_id=document_id,
                    recoverable=False,
                )
            try:
                if self._trace is not None:
                    try:
                        self._trace.observe_model(
                            document_id,
                            self._capture_document_state(document_id),
                        )
                    except Exception:
                        pass
                self._host.open_recovery_copy(str(path))
            except Exception:
                return self._recovery_failure(
                    code="recovery_open_failed",
                    summary="Glyphs could not open the serialized recovery copy.",
                    execution_id=execution_id,
                    document_id=document_id,
                )
            receipt = self._audit.record(
                tool="recover_python_checkpoint",
                effect="edit",
                status="success",
                document_id=document_id,
                details={"executionId": execution_id, "strategy": strategy, "workingDocumentReplaced": False},
            )
            return ToolResponse.success(
                tool="recover_python_checkpoint",
                effect="edit",
                summary="Opened the checkpoint as a separate recovery document.",
                audit_receipt=receipt.to_dict(),
                data={"executionId": execution_id, "strategy": strategy, "workingDocumentReplaced": False},
            )
        inverse = payload.get("inverse")
        required_before = payload.get("beforeModel")
        if not isinstance(inverse, ChangeSet) or not isinstance(required_before, Mapping):
            return self._recovery_failure(
                code="automatic_rollback_unavailable",
                summary="Automatic rollback is not covered; use open_recovery_copy instead.",
                execution_id=execution_id,
                document_id=document_id,
                data={"coverage": payload.get("coverage")},
            )
        if fingerprint_model(required_before) != payload.get("beforeFingerprint"):
            return self._recovery_failure(
                code="checkpoint_corrupt",
                summary="The rollback checkpoint does not reproduce its declared baseline.",
                execution_id=execution_id,
                document_id=document_id,
                recoverable=False,
            )
        try:
            current = self._capture_document_state(document_id)
        except Exception:
            return self._recovery_failure(
                code="document_unavailable",
                summary="The original document is closed or replaced; rollback was not attempted.",
                execution_id=execution_id,
                document_id=document_id,
            )
        if self._trace is not None:
            self._trace.observe_model(document_id, current)
        if fingerprint_model(current) != expected_after_fingerprint:
            return self._recovery_failure(
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
                capabilities=tuple(
                    sorted(
                        set(
                            str(value)
                            for value in payload.get("capabilities", ())
                        )
                    )
                ),
                coverage=(
                    payload.get("canonicalCoverage")
                    if isinstance(payload.get("canonicalCoverage"), CanonicalCoverage)
                    else CanonicalCoverage.complete()
                ),
            )
            result = self._transactions.apply_plan(plan)
        except CanonicalTargetMismatchError as exc:
            mismatch = exc.mismatch
            return self._recovery_failure(
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
            verification_failure = (
                str(exc) or "transaction verification failed"
            )[:500]
            return self._recovery_failure(
                code="rollback_failed",
                summary="Python rollback failed verification.",
                execution_id=execution_id,
                document_id=document_id,
                data={
                    "verificationFailure": verification_failure,
                    "afterStateRestored": bool(
                        isinstance(exc, TransactionVerificationError) and exc.rollback_succeeded
                    )
                },
            )
        if result.after_fingerprint != payload.get("beforeFingerprint"):
            return self._recovery_failure(
                code="rollback_not_exact",
                summary="The verified rollback did not restore the checkpoint baseline.",
                execution_id=execution_id,
                document_id=document_id,
                recoverable=False,
            )
        self._checkpoints.discard(execution_id)
        receipt = self._audit.record(
            tool="recover_python_checkpoint",
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
            tool="recover_python_checkpoint",
            effect="edit",
            summary="The Python document change was rolled back and verified.",
            audit_receipt=receipt.to_dict(),
            data={
                "executionId": execution_id,
                "strategy": "auto",
                "beforeFingerprint": result.before_fingerprint,
                "afterFingerprint": result.after_fingerprint,
                "transactionCount": 1,
                "fontSaved": False,
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
    "SourceSaveForbiddenError",
    "REVIEW_TTL_SECONDS",
    "ROLLBACK_TTL_SECONDS",
    "validate_no_source_save",
    "validate_staged_code",
]
