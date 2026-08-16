"""In-memory MCP initialization, discovery, call, and reconnect tests for v2."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

from fastmcp import Client
import httpx
from jsonschema import validate


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.application import ReadOnlyApplication  # noqa: E402
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.ports import HostRuntimeSnapshot  # noqa: E402
from glyphs_mcp_v2.transport.fastmcp import create_server  # noqa: E402
from glyphs_mcp_v2.transport.http import create_http_app  # noqa: E402


class _EmptyHost:
    def runtime_snapshot(self):
        return HostRuntimeSnapshot(
            application="Glyphs",
            application_version="4.0",
            build_number="3400",
            python_version="3.12.3",
            open_document_count=0,
        )

    def list_documents(self):
        return ()


class V2TransportTests(unittest.TestCase):
    def test_catalog_discovery_and_structured_calls(self) -> None:
        server = create_server(ReadOnlyApplication(_EmptyHost()))

        async def exercise() -> None:
            async with Client(server) as client:
                tools = {tool.name: tool for tool in await client.list_tools()}
                self.assertEqual(set(tools), set(TOOL_CATALOG))
                for name, tool in tools.items():
                    self.assertEqual(tool.outputSchema, TOOL_CATALOG[name].output_schema)
                    self.assertTrue(tool.annotations.readOnlyHint)
                    self.assertFalse(tool.annotations.destructiveHint)

                result = await client.call_tool("list_open_fonts", {})
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content["apiVersion"], "2.0")
                self.assertEqual(result.structured_content["data"]["count"], 0)
                self.assertEqual(result.structured_content["data"]["documents"], [])
                validate(
                    result.structured_content,
                    TOOL_CATALOG["list_open_fonts"].output_schema,
                )

        asyncio.run(exercise())

    def test_client_can_initialize_again_after_disconnect(self) -> None:
        server = create_server(ReadOnlyApplication(_EmptyHost()))

        async def connect_once() -> None:
            async with Client(server) as client:
                tools = await client.list_tools()
                self.assertEqual(len(tools), len(TOOL_CATALOG))
                result = await client.call_tool("get_server_info", {})
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content["data"]["apiMajor"], 2)

        asyncio.run(connect_once())
        asyncio.run(connect_once())

    def test_streamable_http_can_initialize_across_fresh_lifespans(self) -> None:
        server = create_server(ReadOnlyApplication(_EmptyHost()))

        async def initialize_once(request_id: int) -> None:
            app = create_http_app(server)
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://glyphs-mcp-v2.test",
                    timeout=5,
                ) as client:
                    response = await client.post(
                        "/mcp/",
                        headers={
                            "Accept": "application/json, text/event-stream",
                            "MCP-Protocol-Version": "2025-03-26",
                        },
                        json={
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "2025-03-26",
                                "capabilities": {},
                                "clientInfo": {
                                    "name": "v2-restart-test",
                                    "version": "1",
                                },
                            },
                        },
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.headers.get("mcp-session-id"))

        asyncio.run(initialize_once(1))
        asyncio.run(initialize_once(2))


if __name__ == "__main__":
    unittest.main()
