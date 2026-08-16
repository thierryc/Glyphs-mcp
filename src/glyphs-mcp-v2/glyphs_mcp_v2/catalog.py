"""Authoritative typed catalog for the first Glyphs MCP 2.0 slice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from .contracts import result_schema


MODEL_AND_APP = "model+app"


FONT_DOCUMENT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": [
        "documentId",
        "legacyIndex",
        "familyName",
        "filePath",
        "saved",
        "active",
        "masterCount",
        "instanceCount",
        "glyphCount",
        "unitsPerEm",
        "versionMajor",
        "versionMinor",
        "formatVersion",
        "lastSavedAppVersion",
    ],
    "properties": {
        "documentId": {"type": "string", "pattern": "^doc_[0-9A-Za-z_-]+$"},
        "legacyIndex": {"type": "integer", "minimum": 0},
        "familyName": {"type": "string"},
        "filePath": {"type": ["string", "null"]},
        "saved": {"type": "boolean"},
        "active": {"type": "boolean"},
        "masterCount": {"type": "integer", "minimum": 0},
        "instanceCount": {"type": "integer", "minimum": 0},
        "glyphCount": {"type": "integer", "minimum": 0},
        "unitsPerEm": {"type": "integer", "minimum": 1},
        "versionMajor": {"type": "integer"},
        "versionMinor": {"type": "integer"},
        "formatVersion": {"type": ["integer", "null"]},
        "lastSavedAppVersion": {"type": ["string", "null"]},
    },
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    handler_name: str
    title: str
    description: str
    category: str
    effect: str
    visibility: str
    data_schema: Mapping[str, Any]

    @property
    def annotations(self) -> Dict[str, object]:
        read_only = self.effect == "read"
        return {
            "title": self.title,
            "readOnlyHint": read_only,
            "destructiveHint": not read_only,
            "idempotentHint": read_only,
            "openWorldHint": False,
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        schema = result_schema(self.data_schema)
        schema["properties"]["tool"] = {"type": "string", "const": self.name}
        schema["properties"]["effect"] = {"type": "string", "const": self.effect}
        return schema


TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="get_server_info",
        handler_name="get_server_info",
        title="Get Server Info",
        description="Read the Glyphs MCP 2.0 runtime, API, host, and capability identity without changing Glyphs.",
        category="server",
        effect="read",
        visibility=MODEL_AND_APP,
        data_schema={
            "type": "object",
            "required": [
                "serverName",
                "serverVersion",
                "apiMajor",
                "apiVersion",
                "capabilities",
                "host",
            ],
            "properties": {
                "serverName": {"type": "string"},
                "serverVersion": {"type": "string"},
                "apiMajor": {"type": "integer", "const": 2},
                "apiVersion": {"type": "string", "const": "2.0"},
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "host": {
                    "type": "object",
                    "required": [
                        "application",
                        "applicationVersion",
                        "buildNumber",
                        "pythonVersion",
                        "openDocumentCount",
                    ],
                    "properties": {
                        "application": {"type": "string"},
                        "applicationVersion": {"type": "string"},
                        "buildNumber": {"type": "string"},
                        "pythonVersion": {"type": "string"},
                        "openDocumentCount": {"type": "integer", "minimum": 0},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
    ),
    ToolDefinition(
        name="list_open_fonts",
        handler_name="list_open_fonts",
        title="List Open Fonts",
        description="List open Glyphs documents with stable process-local document IDs and immutable font summaries.",
        category="font",
        effect="read",
        visibility=MODEL_AND_APP,
        data_schema={
            "type": "object",
            "required": ["count", "documents"],
            "properties": {
                "count": {"type": "integer", "minimum": 0},
                "documents": {
                    "type": "array",
                    "items": FONT_DOCUMENT_SCHEMA,
                },
            },
            "additionalProperties": False,
        },
    ),
)

TOOL_CATALOG: Dict[str, ToolDefinition] = {
    definition.name: definition for definition in TOOL_DEFINITIONS
}
if len(TOOL_CATALOG) != len(TOOL_DEFINITIONS):
    raise RuntimeError("duplicate Glyphs MCP 2.0 tool name")


__all__ = [
    "FONT_DOCUMENT_SCHEMA",
    "MODEL_AND_APP",
    "TOOL_CATALOG",
    "TOOL_DEFINITIONS",
    "ToolDefinition",
]
