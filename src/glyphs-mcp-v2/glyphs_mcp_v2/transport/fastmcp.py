"""Catalog-driven FastMCP transport for the v2 application boundary."""

from __future__ import annotations

from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Set,
    Union,
)

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from pydantic import Field, WithJsonSchema
from typing_extensions import NotRequired, TypedDict

from ..application import GlyphsMCPApplication
from ..catalog import MODEL_AND_APP, TOOL_DEFINITIONS, ToolDefinition
from ..versions import SERVER_NAME, SERVER_VERSION


GlyphListField = Literal[
    "name",
    "id",
    "category",
    "subCategory",
    "unicode",
    "export",
    "leftKerningGroup",
    "rightKerningGroup",
    "mastersCompatible",
]
LayerRole = Literal[
    "master", "intermediate", "alternate", "backup", "smart", "color"
]
LayerDetail = Literal["summary", "metrics", "geometry", "full"]
OpenTypeKind = Literal["feature", "class", "prefix"]
CompatibilityMode = Literal["component_preserving", "decomposed_export"]
OverwritePolicy = Literal["fail_if_nonempty", "replace_if_match"]
RollbackStrategy = Literal["auto", "open_recovery_copy"]
GlyphNameList = Annotated[
    List[str],
    Field(min_length=1, max_length=64),
    WithJsonSchema(
        {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
            "maxItems": 64,
            "uniqueItems": True,
        }
    ),
]


def _enum_property(values: List[str]) -> Dict[str, Any]:
    return {
        "type": "string",
        "enum": list(values),
    }


def _open_object(properties: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
    }


def _compact_parameter_schema(value: Any) -> Any:
    """Drop redundant annotations without changing input validation."""

    if isinstance(value, dict):
        return {
            key: _compact_parameter_schema(item)
            for key, item in value.items()
            if key != "title" and not (key == "default" and item is None)
        }
    if isinstance(value, list):
        return [_compact_parameter_schema(item) for item in value]
    return value


GlyphUpdate = Annotated[
    Dict[str, Any],
    WithJsonSchema(
        _open_object(
            {
                "action": _enum_property(
                    ["create", "update", "delete"]
                )
            }
        )
    ),
]
OpenTypeUpdate = Annotated[
    Dict[str, Any],
    WithJsonSchema(
        _open_object(
            {
                "action": _enum_property(
                    ["create", "update", "move", "delete"]
                ),
                "kind": _enum_property(
                    ["feature", "class", "prefix"]
                ),
            }
        )
    ),
]
InstanceUpdate = Annotated[
    Dict[str, Any],
    WithJsonSchema(
        _open_object(
            {
                "action": _enum_property(
                    ["create", "update", "move", "delete"]
                ),
                "type": _enum_property(
                    ["static", "variable"]
                ),
            }
        )
    ),
]
MasterUpdate = Annotated[
    Dict[str, Any],
    WithJsonSchema(
        _open_object(
            {
                "action": _enum_property(
                    ["duplicate", "update", "move", "delete"]
                )
            }
        )
    ),
]
LayerUpdate = Annotated[
    Dict[str, Any],
    WithJsonSchema(
        _open_object(
            {
                "action": _enum_property(
                    ["duplicate", "update", "move", "delete"]
                ),
                "interpolation": {
                    "anyOf": [
                        _open_object(
                            {
                                "kind": _enum_property(
                                    ["intermediate", "alternate"]
                                )
                            }
                        ),
                        {"type": "null"},
                    ]
                },
            }
        )
    ),
]


class PairKerningUpdate(TypedDict):
    masterId: str
    left: Union[str, Dict[str, Any]]
    right: Union[str, Dict[str, Any]]
    value: Optional[float]
    entryKind: NotRequired[Literal["pair"]]
    direction: NotRequired[Literal["ltr", "rtl", "vertical"]]


class ContextKerningUpdate(TypedDict):
    entryKind: Literal["context"]
    masterId: str
    sequence: List[str]
    boundaryIndex: int
    value: Optional[float]


KerningUpdate = Union[PairKerningUpdate, ContextKerningUpdate]


class GlyphMetricsUpdate(TypedDict):
    scope: Literal["glyph"]
    glyphName: str
    leftMetricsKey: NotRequired[Optional[str]]
    rightMetricsKey: NotRequired[Optional[str]]
    widthMetricsKey: NotRequired[Optional[str]]


class LayerMetricsUpdate(TypedDict):
    scope: Literal["layer"]
    glyphName: str
    layerId: str
    leftMetricsKey: NotRequired[Optional[str]]
    rightMetricsKey: NotRequired[Optional[str]]
    widthMetricsKey: NotRequired[Optional[str]]


MetricsUpdate = Union[GlyphMetricsUpdate, LayerMetricsUpdate]


class ToolHandlers:
    """Concrete MCP signatures that delegate to the transport-neutral app."""

    def __init__(self, application: GlyphsMCPApplication) -> None:
        self._application = application

    def _invoke(self, tool: str, arguments: Dict[str, Any]) -> ToolResult:
        response = self._application.invoke(
            tool,
            {
                key: value
                for key, value in arguments.items()
                if key != "self" and value is not None
            },
        )
        return ToolResult(content=response.summary, structured_content=response.to_dict())

    async def get_server_info(self) -> ToolResult:
        return self._invoke("get_server_info", {})

    async def list_open_fonts(self) -> ToolResult:
        return self._invoke("list_open_fonts", {})

    async def open_edit_tab(
        self,
        documentId: str,
        glyphNames: GlyphNameList,
        masterId: Optional[str] = None,
    ) -> ToolResult:
        return self._invoke("open_edit_tab", locals())

    async def get_document_status(self, documentId: str) -> ToolResult:
        return self._invoke("get_document_status", locals())

    async def get_operation(
        self,
        operationId: str,
        pageSize: int = 100,
        cursor: Optional[str] = None,
    ) -> ToolResult:
        return self._invoke("get_operation", locals())

    async def list_glyphs(
        self,
        documentId: str,
        pageSize: int = 100,
        cursor: Optional[str] = None,
        fields: Optional[List[GlyphListField]] = None,
        includeLinks: bool = False,
    ) -> ToolResult:
        return self._invoke("list_glyphs", locals())

    async def list_instances(
        self,
        documentId: str,
        pageSize: int = 100,
        cursor: Optional[str] = None,
    ) -> ToolResult:
        return self._invoke("list_instances", locals())

    async def list_masters(
        self,
        documentId: str,
        pageSize: int = 100,
        cursor: Optional[str] = None,
    ) -> ToolResult:
        return self._invoke("list_masters", locals())

    async def list_layers(
        self,
        documentId: str,
        pageSize: int = 100,
        cursor: Optional[str] = None,
        glyphNames: Optional[List[str]] = None,
        roles: Optional[List[LayerRole]] = None,
        detail: LayerDetail = "summary",
    ) -> ToolResult:
        return self._invoke("list_layers", locals())

    async def list_kerning_pairs(
        self,
        documentId: str,
        pageSize: int = 100,
        cursor: Optional[str] = None,
        entryKind: Literal["pair", "context", "all"] = "pair",
    ) -> ToolResult:
        return self._invoke("list_kerning_pairs", locals())

    async def review_kerning_coverage(
        self,
        documentId: str,
        mode: Literal[
            "proof_families",
            "class_representatives",
            "class_cross_product",
            "glyph_expansion",
            "context_sequences",
        ] = "class_representatives",
        eligibleCount: Optional[int] = None,
        measuredCount: Optional[int] = None,
        skippedCount: int = 0,
    ) -> ToolResult:
        return self._invoke("review_kerning_coverage", locals())

    async def review_master_compatibility(
        self,
        documentId: str,
        mode: CompatibilityMode = "component_preserving",
        includeNonexporting: bool = False,
    ) -> ToolResult:
        return self._invoke("review_master_compatibility", locals())

    async def review_metrics_inheritance(
        self,
        documentId: str,
        glyphNames: Optional[List[str]] = None,
        tolerance: float = 0.01,
    ) -> ToolResult:
        return self._invoke("review_metrics_inheritance", locals())

    async def apply_metrics_updates(self, documentId: str, expectedDocumentFingerprint: str, updates: List[MetricsUpdate], reason: Optional[str] = None) -> ToolResult:
        return self._invoke("apply_metrics_updates", locals())

    async def review_anchor_consistency(self, documentId: str) -> ToolResult:
        return self._invoke("review_anchor_consistency", locals())

    async def apply_compatibility_updates(self, documentId: str, expectedDocumentFingerprint: str, updates: List[Dict[str, Any]], reason: Optional[str] = None) -> ToolResult:
        return self._invoke("apply_compatibility_updates", locals())

    async def apply_anchor_updates(self, documentId: str, expectedDocumentFingerprint: str, updates: List[Dict[str, Any]], reason: Optional[str] = None) -> ToolResult:
        return self._invoke("apply_anchor_updates", locals())

    async def apply_glyph_updates(self, documentId: str, expectedDocumentFingerprint: str, updates: List[GlyphUpdate], reason: Optional[str] = None) -> ToolResult:
        return self._invoke("apply_glyph_updates", locals())

    async def apply_kerning_updates(self, documentId: str, expectedDocumentFingerprint: str, updates: List[KerningUpdate], reason: Optional[str] = None) -> ToolResult:
        return self._invoke("apply_kerning_updates", locals())

    async def apply_opentype_updates(self, documentId: str, expectedDocumentFingerprint: str, updates: List[OpenTypeUpdate], reason: Optional[str] = None) -> ToolResult:
        return self._invoke("apply_opentype_updates", locals())

    async def list_opentype_items(
        self,
        documentId: str,
        pageSize: int = 100,
        cursor: Optional[str] = None,
        kinds: Optional[List[OpenTypeKind]] = None,
        tags: Optional[List[str]] = None,
        includeDisabled: bool = True,
    ) -> ToolResult:
        return self._invoke("list_opentype_items", locals())

    async def compile_opentype_features(
        self,
        documentId: str,
        expectedDocumentFingerprint: str,
        reason: Optional[str] = None,
    ) -> ToolResult:
        return self._invoke("compile_opentype_features", locals())

    async def apply_instance_updates(self, documentId: str, expectedDocumentFingerprint: str, updates: List[InstanceUpdate], reason: Optional[str] = None) -> ToolResult:
        return self._invoke("apply_instance_updates", locals())

    async def apply_master_updates(self, documentId: str, expectedDocumentFingerprint: str, updates: List[MasterUpdate], reason: Optional[str] = None) -> ToolResult:
        return self._invoke("apply_master_updates", locals())

    async def apply_layer_updates(self, documentId: str, expectedDocumentFingerprint: str, updates: List[LayerUpdate], reason: Optional[str] = None) -> ToolResult:
        return self._invoke("apply_layer_updates", locals())

    async def review_spacing(
        self,
        documentId: str,
        glyphNames: Optional[List[str]] = None,
        items: Optional[List[Dict[str, Any]]] = None,
        maxIterations: int = 5,
        tolerance: float = 1.0,
    ) -> ToolResult:
        return self._invoke("review_spacing", locals())

    async def apply_spacing(self, documentId: str, expectedDocumentFingerprint: str, items: List[Dict[str, Any]], reason: Optional[str] = None, maxIterations: int = 5, tolerance: float = 1.0) -> ToolResult:
        return self._invoke("apply_spacing", locals())

    async def review_export(
        self,
        documentId: str,
        destination: str,
        overwritePolicy: OverwritePolicy = "fail_if_nonempty",
        compatibilityMode: CompatibilityMode = "component_preserving",
        expectedDestinationFingerprint: Optional[str] = None,
        acknowledgedFindingIds: Optional[List[str]] = None,
    ) -> ToolResult:
        return self._invoke("review_export", locals())

    async def export_source_bundle(self, reviewId: str, confirm: bool = False) -> ToolResult:
        return self._invoke("export_source_bundle", locals())

    async def list_audit_events(
        self,
        documentId: Optional[str] = None,
        pageSize: int = 100,
        cursor: Optional[str] = None,
    ) -> ToolResult:
        return self._invoke("list_audit_events", locals())

    async def list_change_commits(
        self,
        documentId: str,
        pageSize: int = 100,
    ) -> ToolResult:
        return self._invoke("list_change_commits", locals())

    async def revert_change(
        self,
        documentId: str,
        operationId: str,
        expectedDocumentFingerprint: str,
    ) -> ToolResult:
        return self._invoke("revert_change", locals())

    async def execute_python(
        self,
        reason: Optional[str] = None,
        intendedEffect: Annotated[
            Literal["read", "document_edit", "files_or_external"],
            Field(
                description=(
                    "Declared effect: read, document_edit, or "
                    "files_or_external."
                )
            ),
        ] = "read",
        executionMode: Literal[
            "staged_document", "live_open_world"
        ] = "staged_document",
        code: Optional[str] = None,
        documentId: Optional[str] = None,
        glyphName: Optional[str] = None,
        masterId: Optional[str] = None,
        layerId: Optional[str] = None,
        expectedDocumentFingerprint: Optional[str] = None,
        reviewId: Optional[str] = None,
        confirm: bool = False,
        maxOutputChars: Annotated[int, Field(ge=1, le=8192)] = 8192,
        maxErrorChars: Annotated[int, Field(ge=1, le=8192)] = 8192,
    ) -> ToolResult:
        return self._invoke("execute_python", locals())

    async def rollback_python_execution(
        self,
        executionId: str,
        expectedAfterFingerprint: str,
        confirm: bool = False,
        strategy: RollbackStrategy = "auto",
    ) -> ToolResult:
        return self._invoke("rollback_python_execution", locals())


class CatalogRegistrar:
    """The only v2 component permitted to call FastMCP's registration API."""

    def __init__(self, server: FastMCP, application: GlyphsMCPApplication) -> None:
        self._server = server
        self._handlers = ToolHandlers(application)
        self._registered: Set[str] = set()

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._registered:
            raise RuntimeError("tool registered more than once: {}".format(definition.name))

        invoke = getattr(self._handlers, definition.handler_name)
        visibility = ["model", "app"] if definition.visibility == MODEL_AND_APP else ["app"]
        tool = self._server.tool(
            name=definition.name,
            title=definition.title,
            description=definition.description,
            output_schema=definition.discovery_output_schema,
            annotations=definition.annotations,
            meta={"ui": {"visibility": visibility}},
        )(invoke)
        tool.parameters = _compact_parameter_schema(tool.parameters)
        self._registered.add(definition.name)

    def register_all(self) -> None:
        for definition in TOOL_DEFINITIONS:
            self.register(definition)

    @property
    def registered_names(self) -> Set[str]:
        return set(self._registered)


def create_server(application: GlyphsMCPApplication) -> FastMCP:
    server = FastMCP(name=SERVER_NAME, version=SERVER_VERSION)
    registrar = CatalogRegistrar(server, application)
    registrar.register_all()
    return server


__all__ = ["CatalogRegistrar", "ToolHandlers", "create_server"]
