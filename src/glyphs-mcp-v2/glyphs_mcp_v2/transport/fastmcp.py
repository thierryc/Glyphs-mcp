"""Catalog-driven FastMCP transport for the v2 application boundary."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult

from ..application import GlyphsMCPApplication
from ..catalog import MODEL_AND_APP, TOOL_DEFINITIONS, ToolDefinition
from ..versions import SERVER_NAME, SERVER_VERSION


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
        fields: Optional[List[str]] = None,
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

    async def list_kerning_pairs(
        self,
        documentId: str,
        pageSize: int = 100,
        cursor: Optional[str] = None,
    ) -> ToolResult:
        return self._invoke("list_kerning_pairs", locals())

    async def review_kerning_coverage(
        self,
        documentId: str,
        mode: str = "class_representatives",
        eligibleCount: Optional[int] = None,
        measuredCount: Optional[int] = None,
        skippedCount: int = 0,
    ) -> ToolResult:
        return self._invoke("review_kerning_coverage", locals())

    async def review_master_compatibility(
        self,
        documentId: str,
        mode: str = "component_preserving",
        includeNonexporting: bool = False,
    ) -> ToolResult:
        return self._invoke("review_master_compatibility", locals())

    async def review_metrics_inheritance(self, documentId: str) -> ToolResult:
        return self._invoke("review_metrics_inheritance", locals())

    async def review_metrics_updates(
        self,
        documentId: str,
        updates: List[Dict[str, Any]],
    ) -> ToolResult:
        return self._invoke("review_metrics_updates", locals())

    async def apply_metrics_updates(self, reviewId: str, confirm: bool = False) -> ToolResult:
        return self._invoke("apply_metrics_updates", locals())

    async def review_anchor_consistency(self, documentId: str) -> ToolResult:
        return self._invoke("review_anchor_consistency", locals())

    async def review_compatibility_updates(
        self,
        documentId: str,
        updates: List[Dict[str, Any]],
    ) -> ToolResult:
        return self._invoke("review_compatibility_updates", locals())

    async def apply_compatibility_updates(self, reviewId: str, confirm: bool = False) -> ToolResult:
        return self._invoke("apply_compatibility_updates", locals())

    async def review_anchor_updates(
        self,
        documentId: str,
        updates: List[Dict[str, Any]],
    ) -> ToolResult:
        return self._invoke("review_anchor_updates", locals())

    async def apply_anchor_updates(self, reviewId: str, confirm: bool = False) -> ToolResult:
        return self._invoke("apply_anchor_updates", locals())

    async def review_glyph_updates(
        self,
        documentId: str,
        updates: List[Dict[str, Any]],
    ) -> ToolResult:
        return self._invoke("review_glyph_updates", locals())

    async def apply_glyph_updates(self, reviewId: str, confirm: bool = False) -> ToolResult:
        return self._invoke("apply_glyph_updates", locals())

    async def review_kerning_updates(
        self,
        documentId: str,
        updates: List[Dict[str, Any]],
        coverageMode: str = "class_representatives",
    ) -> ToolResult:
        return self._invoke("review_kerning_updates", locals())

    async def apply_kerning_updates(self, reviewId: str, confirm: bool = False) -> ToolResult:
        return self._invoke("apply_kerning_updates", locals())

    async def review_spacing(
        self,
        documentId: str,
        glyphNames: Optional[List[str]] = None,
        items: Optional[List[Dict[str, Any]]] = None,
        maxIterations: int = 5,
        tolerance: float = 1.0,
    ) -> ToolResult:
        return self._invoke("review_spacing", locals())

    async def apply_spacing(self, reviewId: str, confirm: bool = False) -> ToolResult:
        return self._invoke("apply_spacing", locals())

    async def review_export(
        self,
        documentId: str,
        destination: str,
        overwritePolicy: str = "fail_if_nonempty",
        compatibilityMode: str = "component_preserving",
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
        commitId: str,
        expectedDocumentFingerprint: str,
    ) -> ToolResult:
        return self._invoke("revert_change", locals())

    async def execute_python(
        self,
        reason: Optional[str] = None,
        intendedEffect: str = "read",
        executionMode: str = "staged_document",
        code: Optional[str] = None,
        documentId: Optional[str] = None,
        glyphName: Optional[str] = None,
        masterId: Optional[str] = None,
        layerId: Optional[str] = None,
        expectedDocumentFingerprint: Optional[str] = None,
        reviewId: Optional[str] = None,
        confirm: bool = False,
        maxOutputChars: int = 8192,
        maxErrorChars: int = 8192,
    ) -> ToolResult:
        return self._invoke("execute_python", locals())

    async def rollback_python_execution(
        self,
        executionId: str,
        expectedAfterFingerprint: str,
        confirm: bool = False,
        strategy: str = "auto",
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
        self._server.tool(
            name=definition.name,
            title=definition.title,
            description=definition.description,
            tags={definition.category, definition.effect},
            output_schema=definition.output_schema,
            annotations=definition.annotations,
            meta={"ui": {"visibility": visibility}},
        )(invoke)
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
