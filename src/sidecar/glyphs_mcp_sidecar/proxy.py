"""Offline stdio entry point for clients without local HTTP transport."""
import sys
from fastmcp import FastMCP
from fastmcp.resources import ResourceManager
from fastmcp.server.proxy import ProxyResource, ProxyResourceManager
from mcp.shared.exceptions import McpError
from mcp.types import METHOD_NOT_FOUND
from pydantic import Field

from .edit_workflow_ui import RESOURCE_MIME, preserve_ui_resource_metadata


class AppProxyResource(ProxyResource):
    # FastMCP 2.12's Resource pattern predates the standard parameterized MIME.
    mime_type: str = Field(default=RESOURCE_MIME)


class AppProxyResourceManager(ProxyResourceManager):
    async def get_resources(self):
        resources = await ResourceManager.get_resources(self)
        try:
            client = await self._get_client()
            async with client:
                for resource in await client.list_resources():
                    if str(resource.uri) not in resources:
                        cls = AppProxyResource if resource.mimeType == RESOURCE_MIME else ProxyResource
                        resources[str(resource.uri)] = cls.from_mcp_resource(client, resource)
        except McpError as exc:
            if exc.error.code != METHOD_NOT_FOUND:
                raise
        return resources


def create_proxy(target):
    proxy = FastMCP.as_proxy(target, name="Glyphs MCP")
    # Narrow compatibility adapter; keep the library's tools and result forwarding.
    proxy._resource_manager = AppProxyResourceManager(client_factory=proxy.client_factory)
    preserve_ui_resource_metadata(proxy)
    return proxy


def main():
    create_proxy(sys.argv[1]).run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
