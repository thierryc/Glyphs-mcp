"""FastMCP registry-layout compatibility tests."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_utils():
    resources = (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )
    spec = importlib.util.spec_from_file_location("glyphs_mcp_test_utils_registry", resources / "utils.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Tool:
    """Small stand-in retaining a useful tool docstring."""

    __doc__ = "Registry test tool.\n\nMore details."


class ToolRegistryCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.utils = _load_utils()

    def test_discovers_legacy_direct_registry(self) -> None:
        registry = {"review_curve_quality": _Tool()}
        server = types.SimpleNamespace(_tools=registry)

        self.assertIs(self.utils.get_mcp_tool_registry(server), registry)
        self.assertEqual(
            self.utils.get_tool_info(server, "review_curve_quality"),
            "Registry test tool.",
        )

    def test_discovers_current_fastmcp_tool_manager_registry(self) -> None:
        registry = {
            "review_tunni_geometry": _Tool(),
            "apply_tunni_balance": _Tool(),
        }
        manager = types.SimpleNamespace(_tools=registry)
        server = types.SimpleNamespace(_tool_manager=manager)

        discovered = self.utils.get_mcp_tool_registry(server)
        self.assertIs(discovered, registry)

        self.utils.replace_tool_registry_in_place(
            discovered,
            {"review_tunni_geometry": registry["review_tunni_geometry"]},
        )
        self.assertEqual(set(manager._tools), {"review_tunni_geometry"})

    def test_empty_manager_registry_is_still_discoverable(self) -> None:
        registry = {}
        server = types.SimpleNamespace(_tool_manager=types.SimpleNamespace(_tools=registry))

        self.assertIs(self.utils.get_mcp_tool_registry(server), registry)

    def test_authoritative_manager_wins_over_legacy_direct_decoy(self) -> None:
        manager_registry = {"review_curve_quality": _Tool()}
        direct_decoy = {"execute_code": _Tool()}
        server = types.SimpleNamespace(
            _tool_manager=types.SimpleNamespace(_tools=manager_registry),
            _tools=direct_decoy,
        )

        discovered = self.utils.get_mcp_tool_registry(server)

        self.assertIs(discovered, manager_registry)
        self.assertNotIn("execute_code", discovered)

    def test_real_fastmcp_protocol_filter_round_trip_preserves_schemas(self) -> None:
        # Some older compatibility tests install a lightweight ``fastmcp``
        # stand-in. Import the required pinned package in a clean module-cache
        # window, then restore the surrounding suite's exact state.
        saved_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "fastmcp" or name.startswith("fastmcp.")
        }
        for name in saved_modules:
            sys.modules.pop(name, None)

        try:
            import fastmcp
            from fastmcp import Client, FastMCP
            from fastmcp.exceptions import ToolError

            self.assertEqual(fastmcp.__version__, "2.12.0")
            self._exercise_real_fastmcp_round_trip(Client, FastMCP, ToolError)
        finally:
            for name in list(sys.modules):
                if name == "fastmcp" or name.startswith("fastmcp."):
                    sys.modules.pop(name, None)
            sys.modules.update(saved_modules)

    def _exercise_real_fastmcp_round_trip(self, Client, FastMCP, ToolError) -> None:
        server = FastMCP("Glyphs MCP tool-profile regression")

        @server.tool()
        def review_curve_quality(glyph_name: str, samples_per_curve: int = 51) -> str:
            """Review one glyph's sampled curvature."""

            return "{}:{}".format(glyph_name, samples_per_curve)

        @server.tool()
        def review_tunni_geometry(glyph_name: str, path_index: int) -> str:
            """Review one path's Tunni geometry."""

            return "{}:{}".format(glyph_name, path_index)

        @server.tool()
        def apply_tunni_balance(confirm: bool = False) -> str:
            """Apply one explicitly confirmed balance operation."""

            return "applied" if confirm else "not confirmed"

        # FastMCP keeps protocol handlers connected to the live ToolManager even
        # after ASGI construction. This mirrors the plug-in's next-start model.
        self.assertIsNotNone(server.http_app())
        registry = self.utils.get_mcp_tool_registry(server)
        self.assertIs(registry, server._tool_manager._tools)
        full_registry = dict(registry)
        readonly_names = {"review_curve_quality", "review_tunni_geometry"}

        async def exercise_profile_round_trip() -> None:
            async with Client(server) as client:
                edit_tools = {tool.name: tool for tool in await client.list_tools()}
                self.assertEqual(set(edit_tools), set(full_registry))
                review_schema = edit_tools["review_curve_quality"].inputSchema
                self.assertIn("glyph_name", review_schema["properties"])
                self.assertIn("samples_per_curve", review_schema["properties"])

                self.utils.replace_tool_registry_in_place(
                    registry,
                    {name: full_registry[name] for name in readonly_names},
                )
                readonly_tools = {tool.name: tool for tool in await client.list_tools()}
                self.assertEqual(set(readonly_tools), readonly_names)
                self.assertEqual(
                    readonly_tools["review_curve_quality"].inputSchema,
                    review_schema,
                )
                with self.assertRaises(ToolError):
                    await client.call_tool("apply_tunni_balance", {"confirm": True})

                self.utils.replace_tool_registry_in_place(registry, full_registry)
                restored_tools = {tool.name: tool for tool in await client.list_tools()}
                self.assertEqual(set(restored_tools), set(full_registry))
                self.assertEqual(
                    restored_tools["review_curve_quality"].inputSchema,
                    review_schema,
                )
                applied = await client.call_tool(
                    "apply_tunni_balance",
                    {"confirm": True},
                )
                self.assertFalse(applied.is_error)

        asyncio.run(exercise_profile_round_trip())


if __name__ == "__main__":
    unittest.main()
