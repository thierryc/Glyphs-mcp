"""Regression tests for MCP smoothness tools."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _module_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
        / "mcp_tools_smoothness.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _FakeNode:
    def __init__(self) -> None:
        self.type = "curve"
        self.connection = 0
        self._smooth = False

    @property
    def smooth(self):
        return self._smooth

    @smooth.setter
    def smooth(self, value) -> None:  # pragma: no cover - tool should not rely on this alone
        self._smooth = bool(self._smooth)

    def setConnection_(self, value) -> None:
        self.connection = int(value)
        self._smooth = int(value) == 100


class McpToolsSmoothnessTests(unittest.TestCase):
    def _load_module(self):
        node = _FakeNode()
        path = types.SimpleNamespace(nodes=[node], closed=True)
        layer = types.SimpleNamespace(paths=[path])
        glyph = types.SimpleNamespace(layers={"m1": layer})
        font = types.SimpleNamespace(glyphs={"A": glyph})
        glyphs_module = types.SimpleNamespace(Glyphs=types.SimpleNamespace(fonts=[font]), GSSMOOTH=100)
        smoothness_engine = types.SimpleNamespace(
            evaluate_collinear_handles_at_node=lambda *args, **kwargs: {"ok": True},
            find_collinear_handle_nodes=lambda *args, **kwargs: [],
        )
        module_name = "glyphs_mcp_test_mcp_tools_smoothness"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_module,
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": types.SimpleNamespace(_safe_json=lambda payload: json.dumps(payload)),
                "smoothness_engine": smoothness_engine,
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, node

    def test_apply_collinear_handles_smooth_uses_connection_mutation(self) -> None:
        module, node = self._load_module()

        payload = json.loads(
            asyncio.run(
                module.apply_collinear_handles_smooth(
                    font_index=0,
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    node_indices=["0"],
                    confirm=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["applied"], [0])
        self.assertTrue(node.smooth)
        self.assertEqual(node.connection, 100)


if __name__ == "__main__":
    unittest.main()
