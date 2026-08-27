"""Authoritative, catalog-driven Glyphs MCP 2.0 public surface."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from .canonical_tree import CANONICAL_MODEL_SCHEMA_VERSION
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

OPENTYPE_ITEM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": [
        "kind", "order", "collectionOrder", "id", "name", "tag", "code",
        "automatic", "disabled", "notes", "labels", "stylisticSet",
        "substitutions", "unsupportedRuleCount", "warnings",
    ],
    "properties": {
        "kind": {"type": "string", "enum": ["feature", "class", "prefix"]},
        "order": {"type": "integer", "minimum": 0},
        "collectionOrder": {"type": "integer", "minimum": 0},
        "id": {"type": "string"},
        "name": {"type": "string"},
        "tag": {"type": "string"},
        "code": {"type": "string"},
        "automatic": {"type": "boolean"},
        "disabled": {"type": "boolean"},
        "notes": {"type": ["string", "null"]},
        "labels": {"type": "array", "items": {"type": "object"}},
        "stylisticSet": {"type": "boolean"},
        "substitutions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["source", "replacement"],
                "properties": {
                    "source": {"type": "string"},
                    "replacement": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "unsupportedRuleCount": {"type": "integer", "minimum": 0},
        "warnings": {"type": "array", "items": {"type": "string"}},
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
    open_world: bool = False
    idempotent: bool | None = None

    @property
    def annotations(self) -> Dict[str, object]:
        read_only = self.effect == "read"
        destructive = self.effect in {"edit", "save", "files", "code"}
        return {
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": read_only if self.idempotent is None else self.idempotent,
            "openWorldHint": self.open_world,
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        schema = result_schema(self.data_schema)
        schema["properties"]["tool"] = {"type": "string", "const": self.name}
        schema["properties"]["effect"] = {"type": "string", "const": self.effect}
        return schema

    @property
    def discovery_output_schema(self) -> Dict[str, Any]:
        """Publish one compact envelope while preserving typed tool data.

        ``output_schema`` remains the normative runtime contract used for
        validation. Discovery does not need to repeat the complete warning,
        error, pagination, and conditional-success definitions for every tool.
        """

        return {
            "type": "object",
            "required": [
                "resultSchemaVersion", "apiVersion", "requestId", "runId",
                "operationId", "startedAt", "completedAt", "durationMs", "ok",
                "status", "tool", "effect", "summary", "data", "page",
                "warnings", "error", "auditReceipt",
            ],
            "properties": {
                "resultSchemaVersion": {"type": "string", "const": "2.0"},
                "apiVersion": {"type": "string", "const": "2.0"},
                "requestId": {"type": "string"},
                "runId": {"type": "string"},
                "operationId": {"type": "string"},
                "startedAt": {"type": "string"},
                "completedAt": {"type": "string"},
                "durationMs": {"type": "integer"},
                "ok": {"type": "boolean"},
                "status": {"type": "string"},
                "tool": {"type": "string", "const": self.name},
                "effect": {"type": "string", "const": self.effect},
                "summary": {"type": "string"},
                "data": deepcopy(dict(self.data_schema)),
                "page": {"type": ["object", "null"]},
                "warnings": {"type": "array", "items": {"type": "object"}},
                "error": {"type": ["object", "null"]},
                "auditReceipt": {"type": ["object", "null"]},
            },
            "additionalProperties": False,
        }


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
        "Read server, API, host, and capabilities.",
        "server",
        data_schema={
            "type": "object",
            "required": ["serverName", "serverVersion", "apiMajor", "apiVersion", "canonicalModelSchemaVersion", "capabilities", "host"],
            "properties": {
                "serverName": {"type": "string"},
                "serverVersion": {"type": "string"},
                "apiMajor": {"type": "integer", "const": 2},
                "apiVersion": {"type": "string", "const": "2.0"},
                "canonicalModelSchemaVersion": {
                    "type": "integer",
                    "const": CANONICAL_MODEL_SCHEMA_VERSION,
                },
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
        "List open fonts with stable IDs and dirty state.",
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
    _definition(
        "open_edit_tab",
        "Open Edit Tab",
        "Open named glyphs in a Glyphs Edit tab.",
        "font",
        "ui",
        idempotent=False,
    ),
    _definition("get_document_status", "Get Document Status", "Read document fingerprint, path, and dirty state.", "font"),
    _definition("get_operation", "Get Operation", "Read a stored operation page.", "operations"),
    _definition("list_glyphs", "List Glyphs", "List glyphs; fields=name|id|category|subCategory|unicode|export|leftKerningGroup|rightKerningGroup|mastersCompatible.", "glyphs"),
    _definition("list_masters", "List Masters", "List masters, angles, and axis coordinates.", "masters"),
    _definition("list_layers", "List Layers", "List layers; roles=master|intermediate|alternate|backup|smart|color.", "layers"),
    _definition("list_instances", "List Instances", "List static and variable instances and axes.", "instances"),
    _definition("list_kerning_pairs", "List Kerning Pairs", "List kerning; entryKind=pair|context|all.", "kerning"),
    _definition("review_kerning_coverage", "Review Kerning Coverage", "Modes: proof_families|class_representatives|class_cross_product|glyph_expansion|context_sequences.", "kerning"),
    _definition("review_master_compatibility", "Review Master Compatibility", "Review mode=component_preserving|decomposed_export compatibility.", "compatibility"),
    _definition("review_metrics_inheritance", "Review Metrics Inheritance", "Review metrics inheritance.", "spacing"),
    _definition("apply_metrics_updates", "Apply Metrics Updates", "Apply metrics-key updates transactionally.", "spacing", "edit", idempotent=False),
    _definition("review_anchor_consistency", "Review Anchor Consistency", "Review anchor consistency.", "anchors"),
    _definition("apply_compatibility_updates", "Apply Compatibility Updates", "Apply path/component repairs transactionally.", "compatibility", "edit", idempotent=False),
    _definition("apply_anchor_updates", "Apply Anchor Updates", "Apply anchor updates transactionally.", "anchors", "edit", idempotent=False),
    _definition("apply_glyph_updates", "Apply Glyph Updates", "Glyph action=create|update|delete; apply transactionally.", "glyphs", "edit", idempotent=False),
    _definition("apply_kerning_updates", "Apply Kerning Updates", "Kerning entryKind=pair|context; direction=ltr|rtl|vertical.", "kerning", "edit", idempotent=False),
    _definition("apply_opentype_updates", "Apply OpenType Updates", "OpenType action=create|update|move|delete; kind=feature|class|prefix.", "features", "edit", idempotent=False),
    _definition(
        "list_opentype_items",
        "List OpenType Items",
        "List ordered features, classes, prefixes, and parsed stylistic-set substitutions.",
        "features",
        data_schema={
            "type": "object",
            "required": ["documentId", "count", "items"],
            "properties": {
                "documentId": {"type": "string"},
                "count": {"type": "integer", "minimum": 0},
                "items": {"type": "array", "items": OPENTYPE_ITEM_SCHEMA},
            },
            "additionalProperties": True,
        },
    ),
    _definition(
        "compile_opentype_features",
        "Compile OpenType Features",
        "Preflight on a detached copy, then compile live without updateFeatures or save.",
        "features",
        "ui",
        idempotent=False,
        data_schema={
            "type": "object",
            "required": [
                "documentId", "beforeFingerprint", "observedAfterFingerprint",
                "observedChangeCount", "stateMayHaveChanged", "sourceFileChanged",
                "fontSaved", "preflightSucceeded", "liveAttempted", "liveSucceeded",
            ],
            "properties": {
                "documentId": {"type": "string"},
                "beforeFingerprint": {"type": "string"},
                "observedAfterFingerprint": {"type": "string"},
                "observedChangeCount": {"type": "integer", "minimum": 0},
                "stateMayHaveChanged": {"type": "boolean"},
                "sourceFileChanged": {"type": "boolean"},
                "fontSaved": {"type": "boolean", "const": False},
                "preflightSucceeded": {"type": "boolean"},
                "liveAttempted": {"type": "boolean"},
                "liveSucceeded": {"type": "boolean"},
                "errorType": {"type": ["string", "null"]},
                "errorMessage": {"type": ["string", "null"]},
            },
            "additionalProperties": True,
        },
    ),
    _definition("apply_instance_updates", "Apply Instance Updates", "Instance action=create|update|move|delete; type=static|variable.", "instances", "edit", idempotent=False),
    _definition("apply_master_updates", "Apply Master Updates", "Master action=duplicate|update|move|delete.", "masters", "edit", idempotent=False),
    _definition("apply_layer_updates", "Apply Layer Updates", "Layer action=duplicate|update|move|delete; interpolation=intermediate|alternate.", "layers", "edit", idempotent=False),
    _definition("review_spacing", "Review Spacing", "Review bounded spacing simulation.", "spacing"),
    _definition("apply_spacing", "Apply Spacing", "Apply spacing targets transactionally.", "spacing", "edit", idempotent=False),
    _definition("review_export", "Review Export", "compatibilityMode=component_preserving|decomposed_export; overwritePolicy=fail_if_nonempty|replace_if_match.", "export", open_world=True),
    _definition("export_source_bundle", "Export Source Bundle", "Publish a reviewed source bundle.", "export", "files", open_world=True, idempotent=False),
    _definition("list_audit_events", "List Audit Events", "List redacted audit events.", "audit"),
    _definition(
        "list_change_commits",
        "List Change Commits",
        "List document change commits.",
        "audit",
    ),
    _definition(
        "revert_change",
        "Revert Change",
        "Revert one compatible change commit.",
        "audit",
        "edit",
        idempotent=False,
    ),
    _definition(
        "execute_python",
        "Execute Python",
        "intendedEffect=read|document_edit|files_or_external; executionMode=staged_document|live_open_world.",
        "automation",
        "code",
        open_world=True,
        idempotent=False,
    ),
    _definition("rollback_python_execution", "Rollback Python Execution", "Rollback strategy=auto|open_recovery_copy.", "automation", "edit", open_world=True, idempotent=False),
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
