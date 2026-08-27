"""In-memory MCP initialization, discovery, call, and reconnect tests for v2."""

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


def _array_items(property_schema):
    for candidate in property_schema.get("anyOf", [property_schema]):
        if candidate.get("type") == "array":
            return candidate["items"]
    raise AssertionError("property does not contain an array schema")


def _referenced_definition(tool_schema, reference):
    return tool_schema["$defs"][reference.rsplit("/", 1)[-1]]


def _resolved_schema(tool_schema, schema):
    if "$ref" in schema:
        return _referenced_definition(tool_schema, schema["$ref"])
    return schema


def _update_definition(tool_schema):
    items = tool_schema["properties"]["updates"]["items"]
    return _resolved_schema(tool_schema, items)


class V2TransportTests(unittest.TestCase):
    def test_catalog_discovery_and_structured_calls(self) -> None:
        server = create_server(ReadOnlyApplication(_EmptyHost()))

        async def exercise() -> None:
            async with Client(server) as client:
                tools = {tool.name: tool for tool in await client.list_tools()}
                self.assertEqual(set(tools), set(TOOL_CATALOG))
                for name, tool in tools.items():
                    self.assertEqual(
                        tool.outputSchema,
                        TOOL_CATALOG[name].discovery_output_schema,
                    )
                    self.assertEqual(
                        tool.annotations.readOnlyHint,
                        TOOL_CATALOG[name].annotations["readOnlyHint"],
                    )
                    self.assertEqual(
                        tool.annotations.destructiveHint,
                        TOOL_CATALOG[name].annotations["destructiveHint"],
                    )

                python_tool = tools["execute_python"]
                python_schema = python_tool.inputSchema
                edit_tab_schema = tools["open_edit_tab"].inputSchema
                glyph_names_schema = edit_tab_schema["properties"]["glyphNames"]
                self.assertEqual(glyph_names_schema["type"], "array")
                self.assertEqual(glyph_names_schema["minItems"], 1)
                self.assertEqual(glyph_names_schema["maxItems"], 64)
                self.assertTrue(glyph_names_schema["uniqueItems"])
                self.assertEqual(
                    glyph_names_schema["items"]["minLength"], 1
                )
                self.assertFalse(tools["open_edit_tab"].annotations.readOnlyHint)
                self.assertFalse(
                    tools["open_edit_tab"].annotations.destructiveHint
                )
                self.assertEqual(
                    tools["list_kerning_pairs"].inputSchema["properties"][
                        "entryKind"
                    ]["enum"],
                    ["pair", "context", "all"],
                )
                self.assertEqual(
                    tools["review_kerning_coverage"].inputSchema["properties"][
                        "mode"
                    ]["enum"][-1],
                    "context_sequences",
                )
                kerning_update_schema = tools[
                    "apply_kerning_updates"
                ].inputSchema["properties"]["updates"]["items"]
                self.assertIn("anyOf", kerning_update_schema)
                intended_effect_schema = python_schema["properties"][
                    "intendedEffect"
                ]
                intended_effect_values = [
                    "read",
                    "document_edit",
                    "files_or_external",
                ]
                self.assertEqual(
                    intended_effect_schema["enum"], intended_effect_values
                )
                self.assertEqual(intended_effect_schema["type"], "string")
                self.assertEqual(intended_effect_schema["default"], "read")
                for value in intended_effect_values:
                    self.assertIn(value, intended_effect_schema["description"])
                    self.assertIn(value, python_tool.description)
                    validate(
                        {"intendedEffect": value},
                        python_schema,
                    )
                execution_mode_values = ["staged_document", "live_open_world"]
                self.assertEqual(
                    python_schema["properties"]["executionMode"]["enum"],
                    execution_mode_values,
                )
                for name in ("maxOutputChars", "maxErrorChars"):
                    self.assertEqual(
                        python_schema["properties"][name]["minimum"], 1
                    )
                    self.assertEqual(
                        python_schema["properties"][name]["maximum"], 8192
                    )

                result = await client.call_tool("list_open_fonts", {})
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content["apiVersion"], "2.0")
                self.assertEqual(result.structured_content["data"]["count"], 0)
                self.assertEqual(result.structured_content["data"]["documents"], [])
                validate(
                    result.structured_content,
                    TOOL_CATALOG["list_open_fonts"].output_schema,
                )

                with self.assertRaises(ToolError) as rejected:
                    await client.call_tool(
                        "execute_python",
                        {
                            "reason": "transport enum regression",
                            "intendedEffect": "read_only",
                            "code": "print('not dispatched')",
                        },
                    )
                rejection = str(rejected.exception)
                self.assertIn("'read_only' is not one of", rejection)
                for value in intended_effect_values:
                    self.assertIn(value, rejection)

                with self.assertRaises(ToolError) as rejected:
                    await client.call_tool(
                        "execute_python",
                        {
                            "reason": "transport enum regression",
                            "intendedEffect": "read",
                            "executionMode": "detached",
                            "code": "print('not dispatched')",
                        },
                    )
                rejection = str(rejected.exception)
                self.assertIn("'detached' is not one of", rejection)
                for value in execution_mode_values:
                    self.assertIn(value, rejection)

                glyph_fields = [
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
                layer_roles = [
                    "master",
                    "intermediate",
                    "alternate",
                    "backup",
                    "smart",
                    "color",
                ]
                compatibility_modes = [
                    "component_preserving",
                    "decomposed_export",
                ]
                overwrite_policies = [
                    "fail_if_nonempty",
                    "replace_if_match",
                ]
                rollback_strategies = ["auto", "open_recovery_copy"]

                glyph_fields_schema = tools["list_glyphs"].inputSchema[
                    "properties"
                ]["fields"]
                layer_roles_schema = tools["list_layers"].inputSchema[
                    "properties"
                ]["roles"]
                compatibility_mode_schema = tools[
                    "review_master_compatibility"
                ].inputSchema["properties"]["mode"]
                self.assertEqual(
                    _array_items(glyph_fields_schema)["enum"], glyph_fields
                )
                self.assertEqual(
                    _array_items(layer_roles_schema)["enum"], layer_roles
                )
                self.assertEqual(
                    compatibility_mode_schema["enum"], compatibility_modes
                )
                export_schema = tools["review_export"].inputSchema
                self.assertEqual(
                    export_schema["properties"]["compatibilityMode"]["enum"],
                    compatibility_modes,
                )
                self.assertEqual(
                    export_schema["properties"]["overwritePolicy"]["enum"],
                    overwrite_policies,
                )
                self.assertEqual(
                    tools["rollback_python_execution"]
                    .inputSchema["properties"]["strategy"]["enum"],
                    rollback_strategies,
                )

                described_enums = [
                    (
                        tools["list_glyphs"],
                        glyph_fields,
                    ),
                    (
                        tools["list_layers"],
                        layer_roles,
                    ),
                    (
                        tools["review_master_compatibility"],
                        compatibility_modes,
                    ),
                    (
                        tools["review_export"],
                        overwrite_policies,
                    ),
                    (
                        tools["review_export"],
                        compatibility_modes,
                    ),
                    (
                        tools["rollback_python_execution"],
                        rollback_strategies,
                    ),
                    (
                        tools["list_kerning_pairs"],
                        ["pair", "context", "all"],
                    ),
                    (
                        tools["review_kerning_coverage"],
                        [
                            "proof_families",
                            "class_representatives",
                            "class_cross_product",
                            "glyph_expansion",
                            "context_sequences",
                        ],
                    ),
                    (
                        python_tool,
                        intended_effect_values,
                    ),
                    (
                        python_tool,
                        ["staged_document", "live_open_world"],
                    ),
                ]
                for tool, values in described_enums:
                    for value in values:
                        with self.subTest(tool=tool.name, value=value):
                            self.assertIn(value, tool.description)

                update_enums = {
                    "apply_glyph_updates": {
                        "action": ["create", "update", "delete"],
                    },
                    "apply_opentype_updates": {
                        "action": ["create", "update", "move", "delete"],
                        "kind": ["feature", "class", "prefix"],
                    },
                    "apply_instance_updates": {
                        "action": ["create", "update", "move", "delete"],
                        "type": ["static", "variable"],
                    },
                    "apply_master_updates": {
                        "action": ["duplicate", "update", "move", "delete"],
                    },
                    "apply_layer_updates": {
                        "action": ["duplicate", "update", "move", "delete"],
                    },
                }
                for tool_name, expected_fields in update_enums.items():
                    update_schema = _update_definition(
                        tools[tool_name].inputSchema
                    )
                    for field, values in expected_fields.items():
                        with self.subTest(tool=tool_name, field=field):
                            field_schema = update_schema["properties"][field]
                            self.assertEqual(field_schema["enum"], values)
                            for value in values:
                                self.assertIn(
                                    value, tools[tool_name].description
                                )
                                validate(
                                    {
                                        "documentId": "doc_test",
                                        "expectedDocumentFingerprint": (
                                            "sha256:test"
                                        ),
                                        "updates": [{field: value}],
                                    },
                                    tools[tool_name].inputSchema,
                                )

                layer_schema = tools["apply_layer_updates"].inputSchema
                layer_update = _update_definition(layer_schema)
                interpolation_schema = next(
                    candidate
                    for candidate in layer_update["properties"][
                        "interpolation"
                    ]["anyOf"]
                    if candidate.get("type") != "null"
                )
                interpolation = _resolved_schema(
                    layer_schema, interpolation_schema
                )
                self.assertEqual(
                    interpolation["properties"]["kind"]["enum"],
                    ["intermediate", "alternate"],
                )
                for kind in ("intermediate", "alternate"):
                    self.assertIn(
                        kind, tools["apply_layer_updates"].description
                    )
                    validate(
                        {
                            "documentId": "doc_test",
                            "expectedDocumentFingerprint": "sha256:test",
                            "updates": [
                                {"interpolation": {"kind": kind}}
                            ],
                        },
                        layer_schema,
                    )

                accepted_inputs = [
                    (
                        "list_glyphs",
                        {"documentId": "doc_test", "fields": glyph_fields},
                    ),
                    (
                        "list_layers",
                        {"documentId": "doc_test", "roles": layer_roles},
                    ),
                    (
                        "review_master_compatibility",
                        {
                            "documentId": "doc_test",
                            "mode": compatibility_modes[-1],
                        },
                    ),
                    (
                        "review_export",
                        {
                            "documentId": "doc_test",
                            "destination": "/tmp/export",
                            "overwritePolicy": overwrite_policies[-1],
                            "compatibilityMode": compatibility_modes[-1],
                        },
                    ),
                    (
                        "rollback_python_execution",
                        {
                            "executionId": "execution_test",
                            "expectedAfterFingerprint": "sha256:test",
                            "strategy": rollback_strategies[-1],
                        },
                    ),
                ]
                for tool_name, arguments in accepted_inputs:
                    validate(arguments, tools[tool_name].inputSchema)

                invalid_inputs = [
                    (
                        "list_glyphs",
                        {"documentId": "doc_test", "fields": ["bogus"]},
                        glyph_fields,
                    ),
                    (
                        "list_layers",
                        {"documentId": "doc_test", "roles": ["bogus"]},
                        layer_roles,
                    ),
                    (
                        "review_master_compatibility",
                        {"documentId": "doc_test", "mode": "bogus"},
                        compatibility_modes,
                    ),
                    (
                        "review_export",
                        {
                            "documentId": "doc_test",
                            "destination": "/tmp/export",
                            "overwritePolicy": "bogus",
                        },
                        overwrite_policies,
                    ),
                    (
                        "review_export",
                        {
                            "documentId": "doc_test",
                            "destination": "/tmp/export",
                            "compatibilityMode": "bogus",
                        },
                        compatibility_modes,
                    ),
                    (
                        "rollback_python_execution",
                        {
                            "executionId": "execution_test",
                            "expectedAfterFingerprint": "sha256:test",
                            "strategy": "bogus",
                        },
                        rollback_strategies,
                    ),
                    (
                        "apply_glyph_updates",
                        {
                            "documentId": "doc_test",
                            "expectedDocumentFingerprint": "sha256:test",
                            "updates": [{"action": "bogus"}],
                        },
                        update_enums["apply_glyph_updates"]["action"],
                    ),
                    (
                        "apply_opentype_updates",
                        {
                            "documentId": "doc_test",
                            "expectedDocumentFingerprint": "sha256:test",
                            "updates": [{"action": "bogus"}],
                        },
                        update_enums["apply_opentype_updates"]["action"],
                    ),
                    (
                        "apply_opentype_updates",
                        {
                            "documentId": "doc_test",
                            "expectedDocumentFingerprint": "sha256:test",
                            "updates": [{"kind": "bogus"}],
                        },
                        update_enums["apply_opentype_updates"]["kind"],
                    ),
                    (
                        "apply_instance_updates",
                        {
                            "documentId": "doc_test",
                            "expectedDocumentFingerprint": "sha256:test",
                            "updates": [{"action": "bogus"}],
                        },
                        update_enums["apply_instance_updates"]["action"],
                    ),
                    (
                        "apply_instance_updates",
                        {
                            "documentId": "doc_test",
                            "expectedDocumentFingerprint": "sha256:test",
                            "updates": [{"type": "bogus"}],
                        },
                        update_enums["apply_instance_updates"]["type"],
                    ),
                    (
                        "apply_master_updates",
                        {
                            "documentId": "doc_test",
                            "expectedDocumentFingerprint": "sha256:test",
                            "updates": [{"action": "bogus"}],
                        },
                        update_enums["apply_master_updates"]["action"],
                    ),
                    (
                        "apply_layer_updates",
                        {
                            "documentId": "doc_test",
                            "expectedDocumentFingerprint": "sha256:test",
                            "updates": [{"action": "bogus"}],
                        },
                        update_enums["apply_layer_updates"]["action"],
                    ),
                    (
                        "apply_layer_updates",
                        {
                            "documentId": "doc_test",
                            "expectedDocumentFingerprint": "sha256:test",
                            "updates": [
                                {"interpolation": {"kind": "bogus"}}
                            ],
                        },
                        ["intermediate", "alternate"],
                    ),
                ]
                for tool_name, arguments, allowed_values in invalid_inputs:
                    with self.subTest(tool=tool_name), self.assertRaises(
                        ToolError
                    ) as rejected:
                        await client.call_tool(tool_name, arguments)
                    rejection = str(rejected.exception)
                    self.assertIn("Input validation error", rejection)
                    for value in allowed_values:
                        self.assertIn(value, rejection)

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
                self.assertEqual(
                    result.structured_content["data"][
                        "canonicalModelSchemaVersion"
                    ],
                    6,
                )

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
