"""Regression tests for active selection MCP tools."""

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
        / "mcp_tools_selection.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _FakeNode:
    def __init__(self, x, y, *, selected=False, node_type="line", smooth=False) -> None:
        self.position = (x, y)
        self.selected = selected
        self.type = node_type
        self.smooth = smooth


class _FakePath:
    def __init__(self, nodes, *, closed=True) -> None:
        self.nodes = nodes
        self.closed = closed


class McpToolsSelectionTests(unittest.TestCase):
    def _load_module(self, font=None):
        glyphs_obj = types.SimpleNamespace(font=font)
        glyphs_module = types.SimpleNamespace(Glyphs=glyphs_obj)
        helpers_module = types.SimpleNamespace(
            _active_font=lambda glyphs: getattr(glyphs, "font", None),
            _get_layer_id=lambda layer: getattr(layer, "layerId", None) or getattr(layer, "associatedMasterId", None),
            _get_left_sidebearing=lambda layer: getattr(layer, "leftSideBearing", None),
            _get_right_sidebearing=lambda layer: getattr(layer, "rightSideBearing", None),
            _glyphs_show_layer_link_fields=lambda *args, **kwargs: {"showMarkdown": kwargs.get("label", "Open layer")},
            _glyphs_show_link_fields=lambda *args, **kwargs: {"showMarkdown": kwargs.get("label", "Open glyph")},
            _layer_display_name=lambda _font, layer, master_id=None: getattr(layer, "name", None) or "Regular",
            _safe_json=lambda payload: json.dumps(payload),
        )

        module_name = "glyphs_mcp_test_mcp_tools_selection"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_module,
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": helpers_module,
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module

    def _selection_font(self):
        master = types.SimpleNamespace(id="m1", name="Regular")
        glyph = types.SimpleNamespace(
            name="A",
            unicode="0041",
            category="Letter",
            subCategory="Uppercase",
        )
        layer = types.SimpleNamespace(
            parent=glyph,
            name=None,
            layerId="layer-m1",
            associatedMasterId="m1",
            width=600,
            leftSideBearing=50,
            rightSideBearing=60,
            paths=[
                _FakePath(
                    [
                        _FakeNode(0, 0),
                        _FakeNode(100, 0, selected=True, smooth=True),
                        _FakeNode(100, 200),
                    ]
                )
            ],
        )
        glyph.layers = {"m1": layer}
        return types.SimpleNamespace(
            familyName="Selection Sans",
            filepath="/tmp/SelectionSans.glyphs",
            upm=1000,
            masters=[master],
            instances=[],
            glyphs={"A": glyph},
            selectedFontMaster=master,
            selectedLayers=[layer],
        )

    def test_get_selected_glyphs_reports_no_active_font(self) -> None:
        module = self._load_module(font=None)

        payload = json.loads(asyncio.run(module.get_selected_glyphs()))

        self.assertEqual(payload["error"], "No font is currently active")

    def test_get_selected_glyphs_returns_selected_layer_payload(self) -> None:
        module = self._load_module(self._selection_font())

        payload = json.loads(asyncio.run(module.get_selected_glyphs()))

        self.assertEqual(payload["fontName"], "Selection Sans")
        self.assertEqual(payload["selectedCount"], 1)
        selected = payload["selectedGlyphs"][0]
        self.assertEqual(selected["name"], "A")
        self.assertEqual(selected["layerName"], "Regular")
        self.assertEqual(selected["layerId"], "layer-m1")
        self.assertEqual(selected["showMarkdown"], "Open A Regular in Glyphs")

    def test_get_selected_nodes_reports_no_active_layer(self) -> None:
        font = self._selection_font()
        font.selectedLayers = []
        module = self._load_module(font)

        payload = json.loads(asyncio.run(module.get_selected_nodes()))

        self.assertEqual(payload["error"], "No active layer/glyph open in Edit view")

    def test_get_selected_nodes_returns_selected_node_without_mapping_when_disabled(self) -> None:
        module = self._load_module(self._selection_font())

        payload = json.loads(asyncio.run(module.get_selected_nodes(include_master_mapping=False)))

        self.assertEqual(payload["font"]["familyName"], "Selection Sans")
        self.assertEqual(payload["glyph"]["name"], "A")
        self.assertEqual(payload["layer"]["name"], "Regular")
        self.assertEqual(payload["nodeCount"], 1)
        node = payload["nodes"][0]
        self.assertEqual(node["pathIndex"], 0)
        self.assertEqual(node["nodeIndex"], 1)
        self.assertEqual(node["nodeType"], "line")
        self.assertTrue(node["smooth"])
        self.assertEqual(node["position"], {"x": 100.0, "y": 0.0})
        self.assertNotIn("mapping", node)


if __name__ == "__main__":
    unittest.main()
