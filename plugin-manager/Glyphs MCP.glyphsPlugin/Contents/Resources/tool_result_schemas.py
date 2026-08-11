# encoding: utf-8

"""Small shared structured-result contracts for catalog-registered tools."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from fastmcp.tools.tool import ToolResult


RESULT_SCHEMA_VERSION = 1
FEEDBACK_SCHEMA_VERSION = "1.0"


WARNING_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["code", "message"],
    "properties": {
        "code": {"type": "string"},
        "message": {"type": "string"},
        "target": {"type": ["object", "null"]},
    },
    "additionalProperties": True,
}

ERROR_SCHEMA: Dict[str, Any] = {
    "type": ["object", "null"],
    "required": ["code", "message", "recoverable"],
    "properties": {
        "code": {"type": "string"},
        "message": {"type": "string"},
        "recoverable": {"type": "boolean"},
        "details": {},
    },
    "additionalProperties": False,
}


def _workflow_schema(domain: str) -> Dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "resultSchemaVersion",
            "ok",
            "tool",
            "mode",
            "status",
            "target",
            "summary",
            "warnings",
            "data",
            "error",
        ],
        "properties": {
            "resultSchemaVersion": {"type": "integer", "const": RESULT_SCHEMA_VERSION},
            "ok": {"type": "boolean"},
            "tool": {"type": "string"},
            "mode": {"type": "string", "enum": ["review", "dry_run", "confirmed", "ui"]},
            "status": {"type": "string", "enum": ["success", "warning", "partial", "error"]},
            "target": {"type": "object"},
            "summary": {"type": "object"},
            "warnings": {"type": "array", "items": WARNING_SCHEMA, "maxItems": 64},
            "data": {
                "type": "object",
                "description": "{}-specific bounded result fields.".format(domain),
                "additionalProperties": True,
            },
            "error": ERROR_SCHEMA,
        },
        "additionalProperties": False,
    }


FEEDBACK_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": [
        "schemaVersion",
        "kind",
        "status",
        "title",
        "summary",
        "target",
        "items",
        "warnings",
        "actions",
        "progress",
        "result",
    ],
    "properties": {
        "schemaVersion": {"type": "string", "const": FEEDBACK_SCHEMA_VERSION},
        "kind": {"type": "string"},
        "status": {"type": "string", "enum": ["ready", "warning", "working", "success", "partial", "error"]},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "target": {"type": "object"},
        "items": {"type": "array", "items": {"type": "object"}},
        "warnings": {"type": "array", "items": {}},
        "actions": {"type": "array", "items": {"type": "object"}, "maxItems": 2},
        "progress": {"type": "object"},
        "result": {"type": "object"},
        "error": {"type": ["object", "null"]},
    },
    "additionalProperties": False,
}


DOCUMENT_AUDIT_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": [
        "documentAuditSchemaVersion",
        "ok",
        "status",
        "sessionId",
        "startedAt",
        "target",
        "counts",
        "entries",
        "omittedEntryCount",
        "unattributedOperationCount",
        "crossDocumentAttemptCount",
        "lastSave",
        "warnings",
        "error",
    ],
    "properties": {
        "documentAuditSchemaVersion": {"type": "integer", "const": 1},
        "ok": {"type": "boolean"},
        "status": {"type": "string", "enum": ["idle", "active", "error"]},
        "sessionId": {"type": ["string", "null"]},
        "startedAt": {"type": ["string", "null"]},
        "target": {"type": "object"},
        "counts": {
            "type": "object",
            "required": ["changed", "no_change", "succeeded", "saved", "failed", "uncertain"],
            "properties": {
                "changed": {"type": "integer", "minimum": 0},
                "no_change": {"type": "integer", "minimum": 0},
                "succeeded": {"type": "integer", "minimum": 0},
                "saved": {"type": "integer", "minimum": 0},
                "failed": {"type": "integer", "minimum": 0},
                "uncertain": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
        "entries": {
            "type": "array",
            "maxItems": 100,
            "items": {
                "type": "object",
                "required": [
                    "eventId",
                    "timestamp",
                    "tool",
                    "title",
                    "effect",
                    "outcome",
                    "target",
                    "summary",
                    "warnings",
                    "opaque",
                ],
                "properties": {
                    "eventId": {"type": "string"},
                    "timestamp": {"type": "string"},
                    "tool": {"type": "string"},
                    "title": {"type": "string"},
                    "effect": {"type": "string", "enum": ["edit", "save", "code"]},
                    "outcome": {
                        "type": "string",
                        "enum": ["changed", "no_change", "succeeded", "saved", "failed", "uncertain"],
                    },
                    "target": {"type": "object"},
                    "summary": {"type": "string"},
                    "warnings": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
                    "opaque": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        "omittedEntryCount": {"type": "integer", "minimum": 0},
        "unattributedOperationCount": {"type": "integer", "minimum": 0},
        "crossDocumentAttemptCount": {"type": "integer", "minimum": 0},
        "lastSave": {"type": ["object", "null"]},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "error": ERROR_SCHEMA,
    },
    "additionalProperties": False,
}


OUTPUT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "candidate": _workflow_schema("candidate session"),
    "curve": _workflow_schema("curve geometry"),
    "outline": _workflow_schema("outline editing"),
    "spacing": _workflow_schema("spacing"),
    "kerning": _workflow_schema("kerning"),
    "feedback": FEEDBACK_OUTPUT_SCHEMA,
    "document-audit": DOCUMENT_AUDIT_OUTPUT_SCHEMA,
}


def schema_for(key: Optional[str]) -> Optional[Dict[str, Any]]:
    return OUTPUT_SCHEMAS.get(str(key)) if key else None


def _json_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except Exception:
            return {"value": raw}
        return dict(value) if isinstance(value, dict) else {"value": value}
    return {"value": raw}


def _warning(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        code = str(value.get("code") or "warning")
        message = str(value.get("message") or value.get("reason") or code.replace("_", " "))
        out = {"code": code, "message": message}
        if isinstance(value.get("target"), dict):
            out["target"] = value["target"]
        for key, item in value.items():
            if key not in out and key not in {"message", "target"}:
                out[key] = item
        return out
    return {"code": "warning", "message": str(value)}


def _bounded_warnings(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    values: List[Any] = list(payload.get("warnings") or [])
    for segment in payload.get("segments") or []:
        if isinstance(segment, dict):
            values.extend(segment.get("warnings") or [])
    for join in payload.get("joins") or []:
        if isinstance(join, dict) and join.get("warning"):
            values.append(join["warning"])
    return [_warning(value) for value in values[:64]]


def _error(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    value = payload.get("error")
    if value is None:
        value = payload.get("reason")
    if value is None:
        return None
    if isinstance(value, dict):
        code = str(value.get("code") or payload.get("errorType") or "tool_error")
        message = str(value.get("message") or value.get("error") or code.replace("_", " "))
        details = {key: item for key, item in value.items() if key not in {"code", "message", "recoverable"}}
        out = {"code": code, "message": message, "recoverable": bool(value.get("recoverable", True))}
        if details:
            out["details"] = details
        return out
    return {
        "code": str(payload.get("errorType") or payload.get("reason") or "tool_error"),
        "message": str(value),
        "recoverable": True,
    }


def _mode(effect: str, arguments: Dict[str, Any]) -> str:
    if arguments.get("confirm") is True:
        return "confirmed"
    if arguments.get("dry_run") is True:
        return "dry_run"
    if effect == "ui":
        return "ui"
    if effect in {"edit", "save", "files", "code"}:
        return "confirmed"
    return "review"


def workflow_tool_result(tool_name: str, effect: str, raw: Any, arguments: Dict[str, Any]) -> ToolResult:
    """Add structured content while preserving the exact legacy text content."""

    if isinstance(raw, ToolResult):
        return raw
    payload = _json_payload(raw)
    error = _error(payload)
    ok = bool(payload.get("ok", error is None))
    warnings = _bounded_warnings(payload)
    raw_status = str(payload.get("status") or "").lower()
    if not ok:
        status = "error"
    elif raw_status == "partial":
        status = "partial"
    elif warnings:
        status = "warning"
    else:
        status = "success"
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    data = {
        key: value
        for key, value in payload.items()
        if key not in {"ok", "target", "summary", "warnings", "error", "errorType"}
    }
    structured = {
        "resultSchemaVersion": RESULT_SCHEMA_VERSION,
        "ok": ok,
        "tool": tool_name,
        "mode": _mode(effect, arguments),
        "status": status,
        "target": target,
        "summary": summary,
        "warnings": warnings,
        "data": data,
        "error": error,
    }
    return ToolResult(content=raw, structured_content=structured)


__all__ = [
    "DOCUMENT_AUDIT_OUTPUT_SCHEMA",
    "FEEDBACK_OUTPUT_SCHEMA",
    "OUTPUT_SCHEMAS",
    "RESULT_SCHEMA_VERSION",
    "schema_for",
    "workflow_tool_result",
]
