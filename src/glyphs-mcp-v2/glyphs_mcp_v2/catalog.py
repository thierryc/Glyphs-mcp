"""Single authoritative catalog for the Glyphs MCP v2 hard-reset surface."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from .canonical_tree import CANONICAL_MODEL_SCHEMA_VERSION
from .contracts import result_schema


MODEL_AND_APP = "model+app"
APP_ONLY = "app"
OPEN_DATA_SCHEMA: Dict[str, Any] = {"type": "object", "additionalProperties": True}
FINGERPRINT_SCHEMA: Dict[str, Any] = {
    "type": "string",
    "pattern": "^sha256:[0-9a-f]{64}$",
}
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
        "documentId": {"type": "string", "pattern": "^doc_"},
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


def _closed(required: tuple[str, ...], properties: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "type": "object",
        "required": list(required),
        "properties": dict(properties),
        # Application responses add ``historyRecorded`` for document-bound
        # actions at the common trace boundary.
        "additionalProperties": True,
    }


LIST_DOCUMENTS_DATA_SCHEMA = _closed(
    ("count", "documents"),
    {
        "count": {"type": "integer", "minimum": 0},
        "documents": {"type": "array", "items": FONT_DOCUMENT_SCHEMA},
    },
)
READ_DOCUMENT_DATA_SCHEMA = _closed(
    (
        "documentId",
        "documentFingerprint",
        "canonicalModelSchemaVersion",
        "selectedCount",
        "partialCount",
        "items",
    ),
    {
        "documentId": {"type": "string"},
        "documentFingerprint": deepcopy(FINGERPRINT_SCHEMA),
        "canonicalModelSchemaVersion": {
            "type": "integer",
            "const": CANONICAL_MODEL_SCHEMA_VERSION,
        },
        "selectedCount": {"type": "integer", "minimum": 0},
        "partialCount": {"type": "integer", "minimum": 0},
        "reducers": {"type": "object"},
        "items": {"type": "array", "items": {"type": "object"}},
    },
)
CONSTRAINT_DATA_SCHEMA = _closed(
    (
        "documentId",
        "documentFingerprint",
        "constraintCount",
        "passedCount",
        "failedCount",
        "passed",
        "items",
    ),
    {
        "documentId": {"type": "string"},
        "documentFingerprint": deepcopy(FINGERPRINT_SCHEMA),
        "constraintCount": {"type": "integer", "minimum": 0},
        "passedCount": {"type": "integer", "minimum": 0},
        "failedCount": {"type": "integer", "minimum": 0},
        "passed": {"type": "boolean"},
        "items": {"type": "array", "items": {"type": "object"}},
    },
)
PREVIEW_CHANGE_DATA_SCHEMA = _closed(
    (
        "previewId",
        "documentId",
        "baseDocumentFingerprint",
        "proposedFingerprint",
        "applicable",
        "resolvedTargetCount",
        "normalizedOperations",
        "changeSet",
        "constraints",
        "blockers",
        "fontSaved",
    ),
    {
        "previewId": {"type": ["string", "null"]},
        "expiresAt": {"type": "string"},
        "documentId": {"type": "string"},
        "baseDocumentFingerprint": deepcopy(FINGERPRINT_SCHEMA),
        "proposedFingerprint": {
            "anyOf": [deepcopy(FINGERPRINT_SCHEMA), {"type": "null"}]
        },
        "applicable": {"type": "boolean"},
        "resolvedTargetCount": {"type": "integer", "minimum": 0},
        "normalizedOperations": {"type": "array", "items": {"type": "object"}},
        "changeSet": {"type": ["object", "null"]},
        "constraints": {"type": "object"},
        "blockers": {"type": "array", "items": {"type": "string"}},
        "fontSaved": {"type": "boolean", "const": False},
    },
)
APPLY_CHANGE_DATA_SCHEMA = _closed(
    (
        "operationId",
        "previewId",
        "documentId",
        "beforeFingerprint",
        "afterFingerprint",
        "observedChangeCount",
        "transactionCount",
        "fontSaved",
        "revert",
    ),
    {
        "operationId": {"type": "string", "pattern": "^op_"},
        "previewId": {"type": "string", "pattern": "^preview_"},
        "documentId": {"type": "string"},
        "beforeFingerprint": deepcopy(FINGERPRINT_SCHEMA),
        "afterFingerprint": deepcopy(FINGERPRINT_SCHEMA),
        "observedChangeCount": {"type": "integer", "minimum": 0},
        "observedChangeSet": {"type": "object"},
        "canonicalCoverage": {"type": "object"},
        "transactionCount": {"type": "integer", "minimum": 0, "maximum": 1},
        "fontSaved": {"type": "boolean", "const": False},
        "sourceFileChanged": {"type": "boolean"},
        "persistenceReconciliation": {"type": "object"},
        "revert": {"type": "object"},
    },
)
KNOWLEDGE_SEARCH_DATA_SCHEMA = _closed(
    ("query", "filters", "matchCount", "items", "manifest"),
    {
        "query": {"type": "string"},
        "filters": {"type": "object"},
        "matchCount": {"type": "integer", "minimum": 0},
        "items": {"type": "array", "items": {"type": "object"}},
        "manifest": {"type": "object"},
    },
)
KNOWLEDGE_GET_DATA_SCHEMA = _closed(
    ("requestedCount", "foundCount", "missingIds", "items", "manifest"),
    {
        "requestedCount": {"type": "integer", "minimum": 1},
        "foundCount": {"type": "integer", "minimum": 0},
        "missingIds": {"type": "array", "items": {"type": "string"}},
        "items": {"type": "array", "items": {"type": "object"}},
        "manifest": {"type": "object"},
    },
)

# Export schemas remain named because deterministic export tests validate the
# same implementation through the new public names.
REVIEW_EXPORT_DATA_SCHEMA = OPEN_DATA_SCHEMA
EXPORT_SOURCE_BUNDLE_DATA_SCHEMA = OPEN_DATA_SCHEMA


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
    destructive_hint: bool | None = None

    def __post_init__(self) -> None:
        if self.visibility not in {MODEL_AND_APP, APP_ONLY}:
            raise ValueError("unsupported visibility")
        if self.effect not in {"read", "ui", "edit", "save", "files", "code"}:
            raise ValueError("unsupported effect")

    @property
    def annotations(self) -> Dict[str, bool]:
        read_only = self.effect == "read"
        destructive = (
            bool(self.destructive_hint)
            if self.destructive_hint is not None
            else self.effect in {"edit", "save", "files", "code"}
        )
        idempotent = (
            bool(self.idempotent)
            if self.idempotent is not None
            else read_only
        )
        return {
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": idempotent,
            "openWorldHint": bool(self.open_world),
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        schema = result_schema(self.data_schema)
        schema["properties"]["tool"] = {"type": "string", "const": self.name}
        schema["properties"]["effect"] = {"type": "string", "const": self.effect}
        return schema

    @property
    def discovery_output_schema(self) -> Dict[str, Any]:
        return deepcopy(self.output_schema)


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
    destructive_hint: bool | None = None,
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
        destructive_hint=destructive_hint,
    )


TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    _definition(
        "get_server_info",
        "Get Server Info",
        "Read the v2 contract, exact loaded-code identity, permanent Python fallback, Knowledge version, host, and capabilities.",
        "server",
    ),
    _definition(
        "list_documents",
        "List Documents",
        "List open Glyphs documents with stable process-local IDs.",
        "document",
        data_schema=LIST_DOCUMENTS_DATA_SCHEMA,
    ),
    _definition(
        "read_document",
        "Read Document",
        "Read canonical entities and computed observations through one selector and projection.",
        "document",
        data_schema=READ_DOCUMENT_DATA_SCHEMA,
    ),
    _definition(
        "evaluate_constraints",
        "Evaluate Constraints",
        "Evaluate reusable field constraints without changing the document.",
        "document",
        data_schema=CONSTRAINT_DATA_SCHEMA,
    ),
    _definition(
        "preview_change",
        "Preview Change",
        "Resolve exact targets and mechanically simulate generic operations into one immutable preview.",
        "change",
        data_schema=PREVIEW_CHANGE_DATA_SCHEMA,
    ),
    _definition(
        "apply_change",
        "Apply Change",
        "Apply one exact immutable preview through the verified transaction kernel without rerunning planning.",
        "change",
        "edit",
        data_schema=APPLY_CHANGE_DATA_SCHEMA,
        idempotent=False,
    ),
    _definition("get_operation", "Get Operation", "Read one bounded operation or preview record.", "history"),
    _definition("list_history", "List History", "List unsaved-session verified change commits.", "history"),
    _definition("revert_change", "Revert Change", "Revert one compatible verified change without overwriting unrelated later edits.", "history", "edit", idempotent=False),
    _definition(
        "search_knowledge",
        "Search Knowledge",
        "Search the pinned offline font-design and Glyphs-coding corpus with citations and version filters.",
        "knowledge",
        data_schema=KNOWLEDGE_SEARCH_DATA_SCHEMA,
    ),
    _definition(
        "get_knowledge",
        "Get Knowledge",
        "Retrieve exact pinned Knowledge entries by stable ID.",
        "knowledge",
        data_schema=KNOWLEDGE_GET_DATA_SCHEMA,
    ),
    _definition(
        "execute_python",
        "Execute Python",
        "Permanent backup for Glyphs tasks not covered by declarative operations. Consult get_server_info.data.registries.pythonExecution before generating detached read-only or staged-document code. A stale optional fingerprint rebases read-only execution to the latest stable snapshot; staged writes remain strict. Live-open-world remains an explicit external-effect boundary.",
        "python",
        "code",
        open_world=True,
        idempotent=False,
    ),
    _definition("preview_export", "Preview Export", "Create an immutable source-bundle export preview.", "export", data_schema=REVIEW_EXPORT_DATA_SCHEMA),
    _definition("apply_export", "Apply Export", "Publish one exact reviewed source bundle.", "export", "files", data_schema=EXPORT_SOURCE_BUNDLE_DATA_SCHEMA, idempotent=False),
    _definition("save_document", "Save Document", "Explicitly save or Save As with source and destination verification.", "document", "save", idempotent=False),
    _definition("open_document_view", "Open Document View", "Open exact glyphs in a Glyphs Edit tab without document mutation intent.", "host", "ui", idempotent=False),
    _definition("get_runtime_status", "Get Runtime Status", "Read strict Python runtime-interlock health and recovery evidence.", "runtime"),
    _definition("repair_runtime", "Repair Runtime", "Repair manager-owned Python runtime-interlock state.", "runtime", "code", idempotent=True, destructive_hint=False),
)


TOOL_CATALOG: Dict[str, ToolDefinition] = {
    definition.name: definition for definition in TOOL_DEFINITIONS
}
if len(TOOL_CATALOG) != len(TOOL_DEFINITIONS):
    raise RuntimeError("duplicate Glyphs MCP v2 tool name")

REQUIRED_TOOL_COHORTS = (
    frozenset({"preview_change", "apply_change"}),
    frozenset({"preview_export", "apply_export"}),
    frozenset({"search_knowledge", "get_knowledge"}),
    frozenset({"get_runtime_status", "repair_runtime", "execute_python"}),
)
for cohort in REQUIRED_TOOL_COHORTS:
    if not cohort.issubset(TOOL_CATALOG):
        raise RuntimeError(
            "incomplete Glyphs MCP v2 cohort: {}".format(
                ", ".join(sorted(cohort - set(TOOL_CATALOG)))
            )
        )


__all__ = [
    "APP_ONLY",
    "EXPORT_SOURCE_BUNDLE_DATA_SCHEMA",
    "FONT_DOCUMENT_SCHEMA",
    "MODEL_AND_APP",
    "OPEN_DATA_SCHEMA",
    "REQUIRED_TOOL_COHORTS",
    "REVIEW_EXPORT_DATA_SCHEMA",
    "TOOL_CATALOG",
    "TOOL_DEFINITIONS",
    "ToolDefinition",
]
