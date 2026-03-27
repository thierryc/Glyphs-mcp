"""Regression tests for MCP path tool wrappers."""

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
        / "mcp_tools_paths.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _Point:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class _FakeGSNode:
    def __init__(self) -> None:
        self._position = _Point(0.0, 0.0)
        self.type = "line"
        self.smooth = False

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value) -> None:
        self._position = _Point(float(value[0]), float(value[1]))


class _FakeGSPath:
    def __init__(self) -> None:
        self.nodes = []
        self.closed = True


class _FakeLayer:
    def __init__(self, path) -> None:
        self.name = "Master 1"
        self.associatedMasterId = "m1"
        self.width = 500
        self.paths = [path]


class McpToolsPathsTests(unittest.TestCase):
    def _load_module(self):
        path = _FakeGSPath()
        node = _FakeGSNode()
        node.position = (10.0, 20.0)
        path.nodes.append(node)
        layer = _FakeLayer(path)
        font = types.SimpleNamespace(
            selectedFontMaster=types.SimpleNamespace(id="m1"),
            masters=[types.SimpleNamespace(id="m1")],
            glyphs={"A": types.SimpleNamespace(layers={"m1": layer})},
            familyName="Unit Test Sans",
        )
        glyphs_module = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(fonts=[font], showNotification=lambda *args, **kwargs: None),
            GSNode=_FakeGSNode,
            GSPath=_FakeGSPath,
        )
        helper_calls = {"set_sidebearing": []}

        def fake_set_sidebearing(layer_obj, attr_name, legacy_attr, value):
            helper_calls["set_sidebearing"].append((attr_name, legacy_attr, value))
            setattr(layer_obj, legacy_attr, value)
            layer_obj.width = -1
            return True

        helpers_module = types.SimpleNamespace(
            _clear_layer_paths=lambda layer_obj: setattr(layer_obj, "paths", []),
            _safe_json=lambda payload: json.dumps(payload),
            _get_left_sidebearing=lambda layer_obj: getattr(layer_obj, "LSB", 0),
            _get_right_sidebearing=lambda layer_obj: getattr(layer_obj, "RSB", 0),
            _set_sidebearing=fake_set_sidebearing,
        )
        module_name = "glyphs_mcp_test_mcp_tools_paths"
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
        return module, layer, helper_calls

    def test_get_glyph_paths_uses_sidebearing_helpers(self) -> None:
        module, layer, _helper_calls = self._load_module()
        layer.LSB = 42
        layer.RSB = 58

        payload = json.loads(asyncio.run(module.get_glyph_paths(font_index=0, glyph_name="A", master_id="m1")))

        self.assertEqual(payload["leftSideBearing"], 42)
        self.assertEqual(payload["rightSideBearing"], 58)

    def test_set_glyph_paths_uses_sidebearing_helper_setter(self) -> None:
        module, layer, helper_calls = self._load_module()

        payload = json.loads(
            asyncio.run(
                module.set_glyph_paths(
                    font_index=0,
                    glyph_name="A",
                    master_id="m1",
                    paths_data=json.dumps(
                        {
                            "paths": [
                                {
                                    "nodes": [
                                        {"x": 0, "y": 0, "type": "line", "smooth": False},
                                        {"x": 100, "y": 0, "type": "line", "smooth": False},
                                        {"x": 100, "y": 200, "type": "line", "smooth": False},
                                    ],
                                    "closed": True,
                                }
                            ],
                            "width": 700,
                            "leftSideBearing": 50,
                            "rightSideBearing": 75,
                        }
                    ),
                )
            )
        )

        self.assertTrue(payload["success"])
        self.assertEqual(layer.width, 700.0)
        self.assertEqual(helper_calls["set_sidebearing"], [("leftSideBearing", "LSB", 50.0), ("rightSideBearing", "RSB", 75.0)])
        self.assertEqual(layer.LSB, 50.0)
        self.assertEqual(layer.RSB, 75.0)


if __name__ == "__main__":
    unittest.main()
