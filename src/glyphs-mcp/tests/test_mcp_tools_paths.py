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
            paths,
            width=None,
            left_sidebearing=None,
            right_sidebearing=None,
        ):
            if getattr(layer_obj, "fail_path_replace", False):
                return {"ok": False, "error": "Path write verification failed", "pathCount": 0, "nodeCount": 0}
            layer_obj.paths = list(paths or [])
            if left_sidebearing is not None:
                fake_set_sidebearing(layer_obj, "leftSideBearing", "LSB", left_sidebearing)
            if right_sidebearing is not None:
                fake_set_sidebearing(layer_obj, "rightSideBearing", "RSB", right_sidebearing)
            if width is not None:
                layer_obj.width = width
            result = fake_layer_path_summary(layer_obj)
            result["ok"] = True
            return result

        helpers_module = types.SimpleNamespace(
            _clear_layer_paths=lambda layer_obj: setattr(layer_obj, "paths", []),
            _font_resolution_error=_font_resolution_error,
            _safe_json=lambda payload: json.dumps(payload),
            _get_layer_id=lambda layer_obj: getattr(layer_obj, "associatedMasterId", None),
            _get_left_sidebearing=lambda layer_obj: getattr(layer_obj, "LSB", 0),
            _get_right_sidebearing=lambda layer_obj: getattr(layer_obj, "RSB", 0),
            _glyphs_show_layer_link_fields=lambda *args, **kwargs: {},
            _layer_display_name=lambda _font, layer_obj, master_id=None: getattr(layer_obj, "name", None) or "Master 1",
            _layer_path_summary=fake_layer_path_summary,
            _replace_layer_paths_and_metrics=fake_replace_layer_paths_and_metrics,
            _resolve_font_by_index=_resolve_font_by_index,
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
