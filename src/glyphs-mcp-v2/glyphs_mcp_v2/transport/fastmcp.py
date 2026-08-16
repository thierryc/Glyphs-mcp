"""Catalog-driven FastMCP transport for the v2 application boundary."""

from __future__ import annotations

from typing import Callable, Set

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult

from ..application import ReadOnlyApplication
from ..catalog import MODEL_AND_APP, TOOL_DEFINITIONS, ToolDefinition
from ..versions import SERVER_NAME, SERVER_VERSION


class CatalogRegistrar:
    """The only v2 component permitted to call FastMCP's registration API."""

    def __init__(self, server: FastMCP, application: ReadOnlyApplication) -> None:
        self._server = server
        self._application = application
        self._registered: Set[str] = set()

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._registered:
            raise RuntimeError("tool registered more than once: {}".format(definition.name))

        async def invoke() -> ToolResult:
            response = self._application.invoke(definition.handler_name)
            return ToolResult(
                content=response.summary,
                structured_content=response.to_dict(),
            )

        invoke.__name__ = definition.name
        invoke.__doc__ = definition.description
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


def create_server(application: ReadOnlyApplication) -> FastMCP:
    server = FastMCP(name=SERVER_NAME, version=SERVER_VERSION)
    registrar = CatalogRegistrar(server, application)
    registrar.register_all()
    return server


__all__ = ["CatalogRegistrar", "create_server"]
