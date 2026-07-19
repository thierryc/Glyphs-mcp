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
        self.rawType = 1
        self.rawConnection = 0
        self.smooth = False
        self.orientation = 0
        self.name = None
        self.attributes = {}
        self.userData = {}

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
        self.locked = False
        self.attributes = {}
        self.userData = {}


class _FakeLayer:
    def __init__(self, path) -> None:
        self.name = "Master 1"
        self.associatedMasterId = "m1"
        self.width = 500
        self.paths = [path]
        self.fail_path_replace = False


def _open_fonts_from_glyphs(glyphs):
    fonts = []
    try:
        fonts.extend(list(getattr(glyphs, "fonts", None) or []))
    except Exception:
        pass
    try:
        for document in list(getattr(glyphs, "documents", None) or []):
            font = getattr(document, "font", None)
            if font is not None and font not in fonts:
                fonts.append(font)
    except Exception:
        pass
    try:
        font = getattr(getattr(glyphs, "currentDocument", None), "font", None)
        if font is not None and font not in fonts:
            fonts.append(font)
    except Exception:
        pass
    try:
        font = getattr(glyphs, "font", None)
        if font is not None and font not in fonts:
            fonts.append(font)
    except Exception:
        pass
    return fonts


def _resolve_font_by_index(glyphs, font_index):
    fonts = _open_fonts_from_glyphs(glyphs)
    index = int(font_index)
    if index < 0 or index >= len(fonts):
        return None, fonts
    return fonts[index], fonts


def _font_resolution_error(font_index, fonts=None, ok_key=None):
    payload = {
        "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(fonts or [])),
        "fontIndex": font_index,
        "availableFontCount": len(fonts or []),
        "availableFonts": [],
    }
    if ok_key == "success":
        payload["success"] = False
    if ok_key == "ok":
        payload["ok"] = False
    return payload


class McpToolsPathsTests(unittest.TestCase):
    def _load_module(self, broken_fonts=False):
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
        if broken_fonts:
            class BrokenGlyphs:
                @property
                def fonts(self):
                    raise RuntimeError("broken fonts proxy")

            glyphs_obj = BrokenGlyphs()
            glyphs_obj.documents = [types.SimpleNamespace(font=font)]
            glyphs_obj.currentDocument = types.SimpleNamespace(font=font)
            glyphs_obj.font = font
        else:
            glyphs_obj = types.SimpleNamespace(fonts=[font], showNotification=lambda *args, **kwargs: None)
        glyphs_module = types.SimpleNamespace(
            Glyphs=glyphs_obj,
            GSNode=_FakeGSNode,
            GSPath=_FakeGSPath,
        )
        glyphs_module.Glyphs.showNotification = lambda *args, **kwargs: None
        helper_calls = {"set_sidebearing": []}

        def fake_set_sidebearing(layer_obj, attr_name, legacy_attr, value):
            helper_calls["set_sidebearing"].append((attr_name, legacy_attr, value))
            setattr(layer_obj, legacy_attr, value)
            layer_obj.width = -1
            return True

        def fake_layer_path_summary(layer_obj):
            return {
                "pathCount": len(getattr(layer_obj, "paths", []) or []),
                "nodeCount": sum(len(path.nodes) for path in getattr(layer_obj, "paths", []) or []),
            }

        def fake_replace_layer_paths_and_metrics(
            layer_obj,
            path_specs,
            path_class,
            node_class,
            width=None,
            left_sidebearing=None,
            right_sidebearing=None,
        ):
            if getattr(layer_obj, "fail_path_replace", False):
                return {"ok": False, "error": "Path write verification failed", "pathCount": 0, "nodeCount": 0}
            paths = []
            for path_spec in path_specs:
                path_obj = path_class()
                path_obj.closed = bool(path_spec.get("closed", True))
                for node_spec in path_spec.get("nodes", []):
                    node_obj = node_class()
                    node_obj.position = (node_spec["x"], node_spec["y"])
                    node_obj.type = node_spec.get("type", "line")
                    node_obj.smooth = bool(node_spec.get("smooth", False))
                    path_obj.nodes.append(node_obj)
                paths.append(path_obj)
            layer_obj.paths = paths
            if left_sidebearing is not None:
                fake_set_sidebearing(layer_obj, "leftSideBearing", "LSB", left_sidebearing)
            if right_sidebearing is not None:
                fake_set_sidebearing(layer_obj, "rightSideBearing", "RSB", right_sidebearing)
            if width is not None:
                layer_obj.width = width
            result = fake_layer_path_summary(layer_obj)
            result["ok"] = True
            result["pathEditMode"] = "topology-rewrite"
            result["rolledBack"] = False
            return result

        helpers_module = types.SimpleNamespace(
            _apply_path_specs_and_metrics=fake_replace_layer_paths_and_metrics,
            _font_format_metadata=lambda font_obj: {
                "formatVersion": getattr(font_obj, "formatVersion", None),
                "lastSavedAppVersion": getattr(font_obj, "appVersion", None),
            },
            _font_resolution_error=_font_resolution_error,
            _safe_json=lambda payload: json.dumps(payload),
            _get_layer_id=lambda layer_obj: getattr(layer_obj, "associatedMasterId", None),
            _get_left_sidebearing=lambda layer_obj: getattr(layer_obj, "LSB", 0),
            _get_right_sidebearing=lambda layer_obj: getattr(layer_obj, "RSB", 0),
            _glyphs_show_layer_link_fields=lambda *args, **kwargs: {},
            _layer_display_name=lambda _font, layer_obj, master_id=None: getattr(layer_obj, "name", None) or "Master 1",
            _layer_paths=lambda layer_obj: list(getattr(layer_obj, "paths", []) or []),
            _layer_path_summary=fake_layer_path_summary,
            _layer_shape_summary=lambda layer_obj: {
                "shapeCount": len(getattr(layer_obj, "paths", []) or []),
                "pathCount": len(getattr(layer_obj, "paths", []) or []),
                "componentCount": 0,
                "imageCount": 0,
                "shapeGroupCount": 0,
                "otherShapeCount": 0,
                "shapeTypeCounts": {"path": len(getattr(layer_obj, "paths", []) or [])},
            },
            _mapping_keys=lambda mapping: sorted(list((mapping or {}).keys())),
            _node_orientation=lambda node_obj: (
                {0: "left", 1: "right", 2: "center"}.get(
                    getattr(node_obj, "orientation", None),
                    "unknown",
                ),
                getattr(node_obj, "orientation", None),
            ),
            _node_raw_connection=lambda node_obj: getattr(node_obj, "rawConnection", None),
            _node_raw_type=lambda node_obj: getattr(node_obj, "rawType", None),
            _normalized_node_type=lambda node_obj: getattr(node_obj, "type", "unknown"),
            _resolve_font_by_index=_resolve_font_by_index,
            _shape_attribute_metadata=lambda shape: {
                "attributeKeys": sorted(list(getattr(shape, "attributes", {}).keys())),
                "groupId": getattr(shape, "attributes", {}).get("shapeGroup"),
                "hasUserData": bool(getattr(shape, "userData", {})),
            },
            _show_notification=lambda *args, **kwargs: None,
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
        self.assertEqual(payload["pathDataVersion"], 2)
        self.assertEqual(payload["paths"][0]["nodes"][0]["rawType"], 1)
        self.assertEqual(payload["paths"][0]["nodes"][0]["orientation"], "left")
        self.assertEqual(payload["paths"][0]["nodes"][0]["rawOrientation"], 0)

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

    def test_paths_fall_back_when_fonts_proxy_fails(self) -> None:
        module, layer, _helper_calls = self._load_module(broken_fonts=True)

        read_payload = json.loads(asyncio.run(module.get_glyph_paths(font_index=0, glyph_name="A", master_id="m1")))
        write_payload = json.loads(
            asyncio.run(
                module.set_glyph_paths(
                    font_index=0,
                    glyph_name="A",
                    master_id="m1",
                    paths_data=json.dumps({"paths": [], "width": 600}),
                )
            )
        )

        self.assertEqual(read_payload["glyphName"], "A")
        self.assertTrue(write_payload["success"])
        self.assertEqual(layer.width, 600.0)

    def test_set_glyph_paths_reports_failed_write_verification(self) -> None:
        module, layer, _helper_calls = self._load_module()
        layer.fail_path_replace = True

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
                                    "nodes": [{"x": 0, "y": 0, "type": "line", "smooth": False}],
                                    "closed": True,
                                }
                            ]
                        }
                    ),
                )
            )
        )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"], "Path write verification failed")
        self.assertEqual(payload["expectedPathCount"], 1)


if __name__ == "__main__":
    unittest.main()
