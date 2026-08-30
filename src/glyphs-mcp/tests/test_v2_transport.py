"""In-memory discovery, strict input, call, and reconnect tests for v2."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

from fastmcp import Client
from fastmcp.exceptions import ToolError
import httpx
from jsonschema import validate


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.contracts import ToolResponse  # noqa: E402
from glyphs_mcp_v2.ports import HostRuntimeSnapshot  # noqa: E402
from glyphs_mcp_v2.transport.fastmcp import create_server  # noqa: E402
from glyphs_mcp_v2.transport.http import create_http_app  # noqa: E402


class _EmptyHost:
    def runtime_snapshot(self):
        return HostRuntimeSnapshot(
            application="Glyphs",
            application_version="4.0",
            build_number="4004",
            python_version="3.12.3",
            open_document_count=0,
        )

    def list_documents(self):
        return ()

    def scripting_runtime_safety_status(self):
        return {
            "state": "healthy",
            "mode": "strict",
            "strictInterlockAvailable": True,
            "livePythonAvailable": True,
            "stagedPythonAvailable": True,
            "automaticRepairAvailable": False,
            "incidentId": None,
            "affectedSlotCount": 0,
            "nextAction": "none",
            "activeExecutionId": None,
            "currentIncident": None,
            "lastRepair": None,
            "recentTransitions": [],
        }

    def repair_scripting_runtime(self, *, expected_incident_id=None, trigger="agent"):
        del expected_incident_id
        return {
            "repair": {
                "trigger": trigger,
                "result": "not_needed",
                "beforeState": "healthy",
                "afterState": "healthy",
            },
            "scriptingRuntimeSafety": self.scripting_runtime_safety_status(),
        }


class _CapturingApplication:
    def __init__(self):
        self.calls = []

    def invoke(self, tool, arguments):
        self.calls.append((tool, arguments))
        definition = TOOL_CATALOG[tool]
        return ToolResponse.failure(
            tool=tool,
            effect=definition.effect,
            summary="Captured without execution.",
            code="captured",
            message="The transport arguments were captured.",
        )


def _walk_objects(schema):
    if isinstance(schema, dict):
        if schema.get("type") == "object" and "properties" in schema:
            yield schema
        for value in schema.values():
            yield from _walk_objects(value)
    elif isinstance(schema, list):
        for value in schema:
            yield from _walk_objects(value)


class V2TransportTests(unittest.TestCase):
    def test_catalog_discovery_is_exact_and_annotation_complete(self) -> None:
        server = create_server(GlyphsMCPApplication(_EmptyHost()))

        async def exercise() -> None:
            async with Client(server) as client:
                tools = {tool.name: tool for tool in await client.list_tools()}
                self.assertEqual(set(tools), set(TOOL_CATALOG))
                for name, tool in tools.items():
                    definition = TOOL_CATALOG[name]
                    self.assertEqual(
                        tool.outputSchema, definition.discovery_output_schema
                    )
                    self.assertEqual(
                        tool.annotations.readOnlyHint,
                        definition.annotations["readOnlyHint"],
                    )
                    self.assertEqual(
                        tool.annotations.destructiveHint,
                        definition.annotations["destructiveHint"],
                    )
                    self.assertEqual(
                        tool.annotations.idempotentHint,
                        definition.annotations["idempotentHint"],
                    )
                    self.assertEqual(
                        tool.annotations.openWorldHint,
                        definition.annotations["openWorldHint"],
                    )
                self.assertNotIn("review_spacing", tools)
                self.assertNotIn("apply_glyph_updates", tools)
                self.assertNotIn("rollback_python_execution", tools)

        asyncio.run(exercise())

    def test_generic_input_schemas_are_closed_and_selector_owns_pagination(self) -> None:
        server = create_server(GlyphsMCPApplication(_EmptyHost()))

        async def exercise() -> None:
            async with Client(server) as client:
                tools = {tool.name: tool for tool in await client.list_tools()}
                for name in ("read_document", "evaluate_constraints", "preview_change"):
                    schema = tools[name].inputSchema
                    for object_schema in _walk_objects(schema):
                        self.assertFalse(
                            object_schema.get("additionalProperties", True),
                            (name, object_schema),
                        )
                read_schema = tools["read_document"].inputSchema
                self.assertNotIn("pageSize", read_schema["properties"])
                selector = read_schema["properties"]["selector"]
                selector_definition = read_schema["$defs"][
                    selector["$ref"].rsplit("/", 1)[-1]
                ]
                self.assertIn("pageSize", selector_definition["properties"])
                self.assertIn("cursor", selector_definition["properties"])
                self.assertIn("relations", selector_definition["properties"])
                view_schema = tools["open_document_view"].inputSchema
                activation = view_schema["properties"]["activateDocument"]
                self.assertEqual(activation["type"], "boolean")
                self.assertFalse(activation["default"])

        asyncio.run(exercise())

    def test_real_client_returns_structured_generic_and_knowledge_results(self) -> None:
        server = create_server(GlyphsMCPApplication(_EmptyHost()))

        async def exercise() -> None:
            async with Client(server) as client:
                for name, arguments in (
                    ("get_server_info", {}),
                    ("list_documents", {}),
                    ("search_knowledge", {"query": "negative sidebearing"}),
                    (
                        "get_knowledge",
                        {"entryIds": ["practice.negative-sidebearings"]},
                    ),
                ):
                    result = await client.call_tool(name, arguments)
                    self.assertFalse(result.is_error)
                    payload = result.structured_content
                    self.assertTrue(payload["ok"])
                    validate(payload, TOOL_CATALOG[name].output_schema)
                self.assertEqual(
                    payload["data"]["items"][0]["id"],
                    "practice.negative-sidebearings",
                )

        asyncio.run(exercise())

    def test_transport_rejects_legacy_extra_and_nonfinite_shapes(self) -> None:
        server = create_server(GlyphsMCPApplication(_EmptyHost()))

        async def exercise() -> None:
            async with Client(server) as client:
                invalid = (
                    (
                        "read_document",
                        {
                            "documentId": "doc_x",
                            "selector": {"entity": "glyph"},
                            "projection": {"fields": ["name"]},
                            "pageSize": 10,
                        },
                    ),
                    (
                        "preview_change",
                        {
                            "documentId": "doc_x",
                            "expectedDocumentFingerprint": "sha256:" + "0" * 64,
                            "operations": [
                                {
                                    "op": "remove",
                                    "target": {"entity": "glyph", "ids": ["A"]},
                                    "field": "width",
                                }
                            ],
                        },
                    ),
                    (
                        "preview_change",
                        {
                            "documentId": "doc_x",
                            "expectedDocumentFingerprint": "sha256:" + "0" * 64,
                            "operations": [
                                {
                                    "op": "translate",
                                    "target": {"entity": "layer", "ids": ["L"]},
                                    "delta": {"x": float("inf"), "y": 0},
                                }
                            ],
                        },
                    ),
                )
                for name, arguments in invalid:
                    with self.subTest(tool=name), self.assertRaises(ToolError):
                        await client.call_tool(name, arguments)

        asyncio.run(exercise())

    def test_typed_generic_arguments_reach_application_as_plain_values(self) -> None:
        application = _CapturingApplication()
        server = create_server(application)

        async def exercise() -> None:
            async with Client(server) as client:
                await client.call_tool(
                    "preview_change",
                    {
                        "documentId": "doc_test",
                        "expectedDocumentFingerprint": "sha256:" + "1" * 64,
                        "operations": [
                            {
                                "op": "set",
                                "target": {
                                    "entity": "layer",
                                    "ids": ["L1"],
                                    "parent": {"glyphName": "A"},
                                },
                                "field": "width",
                                "value": 520,
                            }
                        ],
                    },
                )
                await client.call_tool(
                    "open_document_view",
                    {
                        "documentId": "doc_test",
                        "glyphNames": ["A"],
                        "activateDocument": True,
                    },
                )

        asyncio.run(exercise())
        tool, arguments = application.calls[0]
        self.assertEqual(tool, "preview_change")
        self.assertIs(type(arguments["operations"][0]), dict)
        self.assertEqual(arguments["operations"][0]["value"], 520)
        self.assertNotIn("numeric", arguments["operations"][0])
        tool, arguments = application.calls[1]
        self.assertEqual(tool, "open_document_view")
        self.assertIs(arguments["activateDocument"], True)

    def test_client_reconnect_and_http_endpoint_remain_stable(self) -> None:
        server = create_server(GlyphsMCPApplication(_EmptyHost()))

        async def connect_once() -> None:
            async with Client(server) as client:
                self.assertEqual(len(await client.list_tools()), len(TOOL_CATALOG))
                result = await client.call_tool("get_server_info", {})
                self.assertFalse(result.is_error)

        asyncio.run(connect_once())
        asyncio.run(connect_once())

        async def http_probe() -> None:
            app = create_http_app(server)
            transport = httpx.ASGITransport(app=app)
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.get("/mcp/")
                    self.assertIn(response.status_code, {400, 406})

        asyncio.run(http_probe())


if __name__ == "__main__":
    unittest.main()
