"""Transport-neutral Glyphs MCP 2.0 result contracts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple


API_MAJOR = 2
API_VERSION = "2.0"
RESULT_SCHEMA_VERSION = "2.0"


@dataclass(frozen=True)
class ToolWarning:
    code: str
    message: str
    target: Optional[Mapping[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        value: Dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
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

    def __post_init__(self) -> None:
        if not self.tool:
            raise ValueError("tool is required")
        if self.effect not in {"read", "ui", "edit", "save", "files", "code"}:
            raise ValueError("unsupported effect: {}".format(self.effect))
        if self.ok and self.error is not None:
            raise ValueError("successful responses cannot contain an error")
        if not self.ok and self.error is None:
            raise ValueError("failed responses require an error")

    @classmethod
    def success(
        cls,
        *,
        tool: str,
        effect: str,
        summary: str,
        data: Mapping[str, Any],
        warnings: Sequence[ToolWarning] = (),
    ) -> "ToolResponse":
        return cls(
            tool=tool,
            effect=effect,
            ok=True,
            summary=summary,
            data=dict(data),
            warnings=tuple(warnings),
            error=None,
        )

    @classmethod
    def failure(
        cls,
        *,
        tool: str,
        effect: str,
        summary: str,
        error: ToolError,
        data: Optional[Mapping[str, Any]] = None,
        warnings: Sequence[ToolWarning] = (),
    ) -> "ToolResponse":
        return cls(
            tool=tool,
            effect=effect,
            ok=False,
            summary=summary,
            data=dict(data or {}),
            warnings=tuple(warnings),
            error=error,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resultSchemaVersion": RESULT_SCHEMA_VERSION,
            "apiVersion": API_VERSION,
            "ok": self.ok,
            "tool": self.tool,
            "effect": self.effect,
            "summary": self.summary,
            "data": dict(self.data),
            "warnings": [warning.to_dict() for warning in self.warnings],
            "error": self.error.to_dict() if self.error is not None else None,
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


def result_schema(data_schema: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the normative v2 result envelope for one tool's data."""
    schema = {
        "type": "object",
        "required": [
            "resultSchemaVersion",
            "apiVersion",
            "ok",
            "tool",
            "effect",
            "summary",
            "data",
            "warnings",
            "error",
        ],
        "properties": {
            "resultSchemaVersion": {
                "type": "string",
                "const": RESULT_SCHEMA_VERSION,
            },
            "apiVersion": {"type": "string", "const": API_VERSION},
            "ok": {"type": "boolean"},
            "tool": {"type": "string", "minLength": 1},
            "effect": {
                "type": "string",
                "enum": ["read", "ui", "edit", "save", "files", "code"],
            },
            "summary": {"type": "string"},
            "data": {"type": "object"},
            "warnings": {
                "type": "array",
                "items": deepcopy(WARNING_SCHEMA),
                "maxItems": 64,
            },
            "error": deepcopy(ERROR_SCHEMA),
        },
        "additionalProperties": False,
    }
    schema["allOf"] = [
        {
            "if": {
                "properties": {"ok": {"const": True}},
                "required": ["ok"],
            },
            "then": {
                "properties": {
                    "data": deepcopy(dict(data_schema)),
                    "error": {"type": "null"},
                }
            },
            "else": {
                "properties": {
                    "data": {"type": "object"},
                    "error": {
                        "type": "object",
                        "required": ["code", "message", "recoverable"],
                    },
                }
            },
        }
    ]
    return schema


__all__ = [
    "API_MAJOR",
    "API_VERSION",
    "ERROR_SCHEMA",
    "RESULT_SCHEMA_VERSION",
    "ToolError",
    "ToolResponse",
    "ToolWarning",
    "WARNING_SCHEMA",
    "result_schema",
]
