"""Transport-neutral Glyphs MCP 2.0 operation and result contracts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from uuid import uuid4


API_MAJOR = 2
API_VERSION = "2.0"
RESULT_SCHEMA_VERSION = "2.0"
EFFECTS = ("read", "ui", "edit", "save", "files", "code")
STATUSES = ("success", "warning", "review_required", "partial", "skipped", "error")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class OperationMetadata:
    request_id: str
    run_id: str
    operation_id: str
    started_at: str
    completed_at: str
    duration_ms: int

    @classmethod
    def create(cls, *, operation_id: Optional[str] = None) -> "OperationMetadata":
        started = _utc_now()
        completed = _utc_now()
        return cls(
            request_id="req_{}".format(uuid4().hex),
            run_id="run_{}".format(uuid4().hex),
            operation_id=str(operation_id or "op_{}".format(uuid4().hex)),
            started_at=_iso(started),
            completed_at=_iso(completed),
            duration_ms=max(0, int((completed - started).total_seconds() * 1000)),
        )

    def with_timing(
        self,
        *,
        started_at: datetime,
        completed_at: datetime,
        duration_ms: int,
    ) -> "OperationMetadata":
        return OperationMetadata(
            request_id=self.request_id,
            run_id=self.run_id,
            operation_id=self.operation_id,
            started_at=_iso(started_at),
            completed_at=_iso(completed_at),
            duration_ms=max(0, int(duration_ms)),
        )


@dataclass(frozen=True)
class ToolWarning:
    code: str
    message: str
    target: Optional[Mapping[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        value: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.target is not None:
            value["target"] = dict(self.target)
        return value


@dataclass(frozen=True)
class ToolError:
    code: str
    message: str
    recoverable: bool
    details: Optional[Mapping[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        value: Dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
        }
        if self.details is not None:
            value["details"] = dict(self.details)
        return value


@dataclass(frozen=True)
class ToolResponse:
    tool: str
    effect: str
    ok: bool
    summary: str
    data: Mapping[str, Any] = field(default_factory=dict)
    warnings: Tuple[ToolWarning, ...] = ()
    error: Optional[ToolError] = None
    status: str = "success"
    metadata: OperationMetadata = field(default_factory=OperationMetadata.create)
    page: Optional[Mapping[str, Any]] = None
    audit_receipt: Optional[Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        if not self.tool:
            raise ValueError("tool is required")
        if self.effect not in EFFECTS:
            raise ValueError("unsupported effect: {}".format(self.effect))
        if self.status not in STATUSES:
            raise ValueError("unsupported status: {}".format(self.status))
        if self.ok and self.error is not None:
            raise ValueError("successful responses cannot contain an error")
        if not self.ok and self.error is None:
            raise ValueError("failed responses require an error")
        if not self.ok and self.status != "error":
            raise ValueError("failed responses must use error status")

    @classmethod
    def success(
        cls,
        *,
        tool: str,
        effect: str,
        summary: str,
        data: Mapping[str, Any],
        warnings: Sequence[ToolWarning] = (),
        status: str = "success",
        metadata: Optional[OperationMetadata] = None,
        page: Optional[Mapping[str, Any]] = None,
        audit_receipt: Optional[Mapping[str, Any]] = None,
    ) -> "ToolResponse":
        return cls(
            tool=tool,
            effect=effect,
            ok=True,
            summary=summary,
            data=dict(data),
            warnings=tuple(warnings),
            error=None,
            status=status,
            metadata=metadata or OperationMetadata.create(),
            page=dict(page) if page is not None else None,
            audit_receipt=dict(audit_receipt) if audit_receipt is not None else None,
        )

    @classmethod
    def failure(
        cls,
        *,
        tool: str,
        effect: str,
        summary: str,
        error: Optional[ToolError] = None,
        code: Optional[str] = None,
        message: Optional[str] = None,
        recoverable: bool = True,
        details: Optional[Mapping[str, Any]] = None,
        data: Optional[Mapping[str, Any]] = None,
        warnings: Sequence[ToolWarning] = (),
        metadata: Optional[OperationMetadata] = None,
        page: Optional[Mapping[str, Any]] = None,
        audit_receipt: Optional[Mapping[str, Any]] = None,
    ) -> "ToolResponse":
        if error is not None and any(value is not None for value in (code, message, details)):
            raise ValueError("failure accepts either error or scalar error fields")
        if error is None:
            if not code or message is None:
                raise ValueError("failure requires error or code and message")
            error = ToolError(code, message, bool(recoverable), details)
        return cls(
            tool=tool,
            effect=effect,
            ok=False,
            summary=summary,
            data=dict(data or {}),
            warnings=tuple(warnings),
            error=error,
            status="error",
            metadata=metadata or OperationMetadata.create(),
            page=dict(page) if page is not None else None,
            audit_receipt=dict(audit_receipt) if audit_receipt is not None else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resultSchemaVersion": RESULT_SCHEMA_VERSION,
            "apiVersion": API_VERSION,
            "requestId": self.metadata.request_id,
            "runId": self.metadata.run_id,
            "operationId": self.metadata.operation_id,
            "startedAt": self.metadata.started_at,
            "completedAt": self.metadata.completed_at,
            "durationMs": self.metadata.duration_ms,
            "ok": self.ok,
            "status": self.status,
            "tool": self.tool,
            "effect": self.effect,
            "summary": self.summary,
            "data": dict(self.data),
            "page": dict(self.page) if self.page is not None else None,
            "warnings": [warning.to_dict() for warning in self.warnings],
            "error": self.error.to_dict() if self.error is not None else None,
            "auditReceipt": dict(self.audit_receipt) if self.audit_receipt is not None else None,
        }


WARNING_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["code", "message"],
    "properties": {
        "code": {"type": "string", "minLength": 1},
        "message": {"type": "string", "minLength": 1},
        "target": {"type": "object"},
    },
    "additionalProperties": False,
}

ERROR_SCHEMA: Dict[str, Any] = {
    "oneOf": [
        {"type": "null"},
        {
            "type": "object",
            "required": ["code", "message", "recoverable"],
            "properties": {
                "code": {"type": "string", "minLength": 1},
                "message": {"type": "string", "minLength": 1},
                "recoverable": {"type": "boolean"},
                "details": {"type": "object"},
            },
            "additionalProperties": False,
        },
    ]
}

PAGE_SCHEMA: Dict[str, Any] = {
    "oneOf": [
        {"type": "null"},
        {
            "type": "object",
            "required": ["pageSize", "totalItems", "returnedItems", "offset", "nextCursor", "sourceFingerprint"],
            "properties": {
                "pageSize": {"type": "integer", "minimum": 1, "maximum": 500},
                "totalItems": {"type": "integer", "minimum": 0},
                "returnedItems": {"type": "integer", "minimum": 0, "maximum": 500},
                "offset": {"type": "integer", "minimum": 0},
                "nextCursor": {"type": ["string", "null"]},
                "sourceFingerprint": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
    ]
}

AUDIT_RECEIPT_SCHEMA: Dict[str, Any] = {
    "oneOf": [
        {"type": "null"},
        {
            "type": "object",
            "required": ["auditId", "timestamp"],
            "properties": {
                "auditId": {"type": "string", "minLength": 1},
                "timestamp": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
    ]
}


def result_schema(data_schema: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the normative v2 result envelope for one tool's data."""
    schema = {
        "type": "object",
        "required": [
            "resultSchemaVersion", "apiVersion", "requestId", "runId", "operationId",
            "startedAt", "completedAt", "durationMs", "ok", "status", "tool", "effect",
            "summary", "data", "page", "warnings", "error", "auditReceipt",
        ],
        "properties": {
            "resultSchemaVersion": {"type": "string", "const": RESULT_SCHEMA_VERSION},
            "apiVersion": {"type": "string", "const": API_VERSION},
            "requestId": {"type": "string", "pattern": "^req_"},
            "runId": {"type": "string", "pattern": "^run_"},
            "operationId": {"type": "string", "pattern": "^(op|review|exec)_"},
            "startedAt": {"type": "string"},
            "completedAt": {"type": "string"},
            "durationMs": {"type": "integer", "minimum": 0},
            "ok": {"type": "boolean"},
            "status": {"type": "string", "enum": list(STATUSES)},
            "tool": {"type": "string", "minLength": 1},
            "effect": {"type": "string", "enum": list(EFFECTS)},
            "summary": {"type": "string"},
            "data": {"type": "object"},
            "page": deepcopy(PAGE_SCHEMA),
            "warnings": {"type": "array", "items": deepcopy(WARNING_SCHEMA), "maxItems": 64},
            "error": deepcopy(ERROR_SCHEMA),
            "auditReceipt": deepcopy(AUDIT_RECEIPT_SCHEMA),
        },
        "additionalProperties": False,
    }
    then_properties: Dict[str, Any] = {"error": {"type": "null"}}
    # Most operations intentionally return an open data object. Repeating that
    # no-op schema in every discovery entry costs several KiB without adding a
    # constraint; only embed a tool-specific data schema when one exists.
    if dict(data_schema) != {"type": "object", "additionalProperties": True}:
        then_properties["data"] = deepcopy(dict(data_schema))
    schema["allOf"] = [
        {
            "if": {"properties": {"ok": {"const": True}}},
            "then": {"properties": then_properties},
            "else": {
                "properties": {
                    "status": {"const": "error"},
                    "error": {"type": "object"},
                }
            },
        }
    ]
    return schema


__all__ = [
    "API_MAJOR", "API_VERSION", "AUDIT_RECEIPT_SCHEMA", "EFFECTS", "ERROR_SCHEMA",
    "OperationMetadata", "PAGE_SCHEMA", "RESULT_SCHEMA_VERSION", "STATUSES", "ToolError",
    "ToolResponse", "ToolWarning", "WARNING_SCHEMA", "result_schema",
]
