"""Authoritative, catalog-driven Glyphs MCP 2.0 public surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from .contracts import result_schema


MODEL_AND_APP = "model+app"
APP_ONLY = "app"


FONT_DOCUMENT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": [
        "documentId",
        "legacyIndex",
        "familyName",
        "filePath",
        "hasFilePath",
        "hasUnsavedChanges",
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
        "hasFilePath": {"type": "boolean"},
        "hasUnsavedChanges": {"type": ["boolean", "null"]},
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


OPEN_DATA_SCHEMA: Dict[str, Any] = {"type": "object", "additionalProperties": True}


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
    open_world: bool = False
    idempotent: bool | None = None

    @property
    def annotations(self) -> Dict[str, object]:
        read_only = self.effect == "read"
        return {
            "title": self.title,
            "readOnlyHint": read_only,
            "destructiveHint": not read_only,
            "idempotentHint": read_only if self.idempotent is None else self.idempotent,
            "openWorldHint": self.open_world,
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        schema = result_schema(self.data_schema)
        schema["properties"]["tool"] = {"type": "string", "const": self.name}
        schema["properties"]["effect"] = {"type": "string", "const": self.effect}
        return schema


def _definition(
    name: str,
    title: str,
    description: str,
    category: str,
    effect: str = "read",
    *,
    data_schema: Mapping[str, Any] = OPEN_DATA_SCHEMA,
    open_world: bool = False,
    idempotent: bool | None = None,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        handler_name=name,
        title=title,
        description=description,
        category=category,
        effect=effect,
        visibility=MODEL_AND_APP,
        data_schema=data_schema,
        open_world=open_world,
        idempotent=idempotent,
    )


TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    _definition(
        "get_server_info",
        "Get Server Info",
        "Read the Glyphs MCP 2.0 runtime, API, host, and capability identity.",
        "server",
        data_schema={
            "type": "object",
            "required": ["serverName", "serverVersion", "apiMajor", "apiVersion", "capabilities", "host"],
            "properties": {
                "serverName": {"type": "string"},
                "serverVersion": {"type": "string"},
                "apiMajor": {"type": "integer", "const": 2},
                "apiVersion": {"type": "string", "const": "2.0"},
                "capabilities": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                "host": {
                    "type": "object",
                    "required": ["application", "applicationVersion", "buildNumber", "pythonVersion", "openDocumentCount"],
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
    _definition(
        "list_open_fonts",
        "List Open Fonts",
        "List open Glyphs documents with stable process-local document IDs and explicit dirty state.",
        "font",
        data_schema={
            "type": "object",
            "required": ["count", "documents"],
            "properties": {
                "count": {"type": "integer", "minimum": 0},
                "documents": {"type": "array", "items": FONT_DOCUMENT_SCHEMA},
            },
            "additionalProperties": False,
        },
    ),
    _definition("get_document_status", "Get Document Status", "Read one stable document's fingerprint, file-path state, and dirty state.", "font"),
    _definition("get_operation", "Get Operation", "Read a bounded page from a stored analysis, review, execution diff, or operation result.", "operations"),
    _definition("list_glyphs", "List Glyphs", "List paginated glyph metadata with optional field selection and links.", "glyphs"),
    _definition("list_instances", "List Instances", "List static and variable instances with internal and external axis coordinates.", "instances"),
    _definition("list_kerning_pairs", "List Kerning Pairs", "List paginated kerning pairs with typed key identity and provenance.", "kerning"),
    _definition("review_kerning_coverage", "Review Kerning Coverage", "Account honestly for eligible, measured, skipped, and untested pairs in one proof or exhaustive mode.", "kerning"),
    _definition("review_master_compatibility", "Review Master Compatibility", "Review authoritative host compatibility, structure, components, cycles, and transitive dependencies.", "compatibility"),
    _definition("review_metrics_inheritance", "Review Metrics Inheritance", "Review metrics keys and component-based metrics dependencies without changing Glyphs.", "spacing"),
    _definition("review_metrics_updates", "Review Metrics Updates", "Build a fingerprint-bound batch of metrics-key inheritance updates.", "spacing"),
    _definition("apply_metrics_updates", "Apply Metrics Updates", "Consume one reviewed metrics-inheritance batch in a verified transaction.", "spacing", "edit", idempotent=False),
    _definition("review_anchor_consistency", "Review Anchor Consistency", "Review semantic anchor sets, duplicates, composites, and stacked marks.", "anchors"),
    _definition("review_compatibility_updates", "Review Compatibility Updates", "Build an explicit fingerprint-bound path/component compatibility repair batch.", "compatibility"),
    _definition("apply_compatibility_updates", "Apply Compatibility Updates", "Consume one reviewed compatibility repair batch in a verified transaction.", "compatibility", "edit", idempotent=False),
    _definition("review_anchor_updates", "Review Anchor Updates", "Build a fingerprint-bound batch anchor change set without changing Glyphs.", "anchors"),
    _definition("apply_anchor_updates", "Apply Anchor Updates", "Consume one reviewed batch anchor change set in a verified transaction.", "anchors", "edit", idempotent=False),
    _definition("review_glyph_updates", "Review Glyph Updates", "Build a fingerprint-bound batch glyph-property change set.", "glyphs"),
    _definition("apply_glyph_updates", "Apply Glyph Updates", "Consume one reviewed batch glyph-property change set in a verified transaction.", "glyphs", "edit", idempotent=False),
    _definition("review_kerning_updates", "Review Kerning Updates", "Build a fingerprint-bound batch kerning change set with typed identities.", "kerning"),
    _definition("apply_kerning_updates", "Apply Kerning Updates", "Consume one reviewed batch kerning change set in a verified transaction.", "kerning", "edit", idempotent=False),
    _definition("review_spacing", "Review Spacing", "Run bounded detached fixed-point spacing simulation with dependency revalidation.", "spacing"),
    _definition("apply_spacing", "Apply Spacing", "Consume one reviewed spacing plan in a verified transaction.", "spacing", "edit", idempotent=False),
    _definition("review_export", "Review Export", "Review compatibility, instances, exclusions, and destination replacement policy.", "export", open_world=True),
    _definition("export_source_bundle", "Export Source Bundle", "Stage and atomically publish a reviewed designspace/UFO source bundle.", "export", "files", open_world=True, idempotent=False),
    _definition("list_audit_events", "List Audit Events", "List bounded redacted process-local v2 audit events.", "audit"),
    _definition("execute_python", "Execute Python", "Run bounded staged-document or explicitly approved open-world Python when typed tools do not fit.", "automation", "code", open_world=True, idempotent=False),
    _definition("rollback_python_execution", "Rollback Python Execution", "Apply a verified inverse document patch or open a separate recovery copy.", "automation", "edit", open_world=True, idempotent=False),
)


TOOL_CATALOG: Dict[str, ToolDefinition] = {definition.name: definition for definition in TOOL_DEFINITIONS}
if len(TOOL_CATALOG) != len(TOOL_DEFINITIONS):
    raise RuntimeError("duplicate Glyphs MCP 2.0 tool name")


__all__ = [
    "APP_ONLY",
    "FONT_DOCUMENT_SCHEMA",
    "MODEL_AND_APP",
    "OPEN_DATA_SCHEMA",
    "TOOL_CATALOG",
    "TOOL_DEFINITIONS",
    "ToolDefinition",
]
