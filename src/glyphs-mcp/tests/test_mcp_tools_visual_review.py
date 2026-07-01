"""Regression tests for visual review image MCP tool."""

from __future__ import annotations

import asyncio
import inspect
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
        / "mcp_tools_visual_review.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _FakeImage:
    def __init__(self, path=None, data=None, format=None, annotations=None):
        self.path = path
        self.data = data
        self.format = format
        self.annotations = annotations


class _FakeObjCMeta(type):
    registry: dict[str, type] = {}

    def __new__(mcls, name, bases, namespace):
        if name in mcls.registry:
            raise RuntimeError(f"{name} is overriding existing Objective-C class")
        cls = super().__new__(mcls, name, bases, namespace)
        mcls.registry[name] = cls
        return cls


class _FakeNSObject(metaclass=_FakeObjCMeta):
    @classmethod
    def alloc(cls):
        return cls()

    def init(self):
        return self

    def performSelectorOnMainThread_withObject_waitUntilDone_(self, selector, obj, _wait):
        getattr(self, selector.replace(":", "_"))(obj)


class _FakeObjCModule:
    @staticmethod
    def super(cls, obj):
        return super(cls, obj)

    @staticmethod
    def lookUpClass(name):
        if name not in _FakeObjCMeta.registry:
            raise KeyError(name)
        return _FakeObjCMeta.registry[name]


class _FakeNSThread:
    @staticmethod
    def isMainThread():
        return False


class _Point:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class _Size:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height


class _Rect:
    def __init__(self, x: float, y: float, width: float, height: float) -> None:
        self.origin = _Point(x, y)
        self.size = _Size(width, height)


class _FakeLayer:
    def __init__(self, master_id: str, name: str, width: float = 500.0) -> None:
        self.name = name
        self.associatedMasterId = master_id
        self.width = width
        self.leftSideBearing = 40.0
        self.rightSideBearing = 60.0
        self.bounds = _Rect(-10.0, -20.0, 420.0, 720.0)
        self.paths = []
        self.anchors = []
        self.guides = []
        self.completeBezierPath = object()
        self.bezierPath = object()
        self.parent = None


class McpToolsVisualReviewTests(unittest.TestCase):
    def _load_module(self, selected_layers=True, module_name="glyphs_mcp_test_mcp_tools_visual_review"):
        master_1 = types.SimpleNamespace(id="m1", name="Regular", ascender=800, descender=-200, xHeight=500, capHeight=700)
        master_2 = types.SimpleNamespace(id="m2", name="Bold", ascender=810, descender=-210, xHeight=510, capHeight=710)
        layer_1 = _FakeLayer("m1", "Regular", width=500.0)
        layer_2 = _FakeLayer("m2", "Bold", width=520.0)
        glyph = types.SimpleNamespace(name="A", layers={"m1": layer_1, "m2": layer_2})
        layer_1.parent = glyph
        layer_2.parent = glyph
        font = types.SimpleNamespace(
            familyName="Unit Test Sans",
            glyphs={"A": glyph},
            masters=[master_1, master_2],
            selectedFontMaster=master_1,
            selectedLayers=[layer_1] if selected_layers else [],
        )

        glyphs_module = types.SimpleNamespace(Glyphs=types.SimpleNamespace(fonts=[font], font=font))
        helpers_module = types.SimpleNamespace(
            _get_layer_id=lambda layer_obj: getattr(layer_obj, "associatedMasterId", None),
            _get_left_sidebearing=lambda layer_obj: getattr(layer_obj, "leftSideBearing", None),
            _get_right_sidebearing=lambda layer_obj: getattr(layer_obj, "rightSideBearing", None),
            _safe_json=lambda payload: json.dumps(payload),
        )
        fastmcp_mod = types.ModuleType("fastmcp")
        fastmcp_utilities_mod = types.ModuleType("fastmcp.utilities")
        fastmcp_types_mod = types.ModuleType("fastmcp.utilities.types")
        fastmcp_mod.Image = _FakeImage
        fastmcp_types_mod.Image = _FakeImage
        fastmcp_utilities_mod.types = fastmcp_types_mod
        fastmcp_mod.utilities = fastmcp_utilities_mod

        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_module,
                "fastmcp": fastmcp_mod,
                "fastmcp.utilities": fastmcp_utilities_mod,
                "fastmcp.utilities.types": fastmcp_types_mod,
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": helpers_module,
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, font

    def _configure_fake_objc(self, module, *, reset_registry: bool = False) -> None:
        if reset_registry:
            _FakeObjCMeta.registry = {}
        module.objc = _FakeObjCModule()
        module.NSObject = _FakeNSObject
        module.NSThread = _FakeNSThread
        module._OBJC_MAIN_THREAD_HELPER_CLASS = None

    def _stub_renderer(self, module, png_bytes=b"png"):
        captured = {}

        def fake_render(render_items, master, columns, image_width, include_components, overlays):
            captured["glyphNames"] = [item["glyphName"] for item in render_items]
            captured["layerIds"] = [item["layerId"] for item in render_items]
            captured["masterId"] = master.id
            captured["columns"] = columns
            captured["imageWidth"] = image_width
            captured["includeComponents"] = include_components
            captured["overlays"] = list(overlays)
            return png_bytes, {"imageWidth": image_width, "imageHeight": 900, "rowCount": 1, "columnCount": columns}

        module._render_contact_sheet_png = fake_render
        module._run_on_main_thread = lambda fn: fn()
        return captured

    def test_uses_selected_glyphs_when_names_omitted(self) -> None:
        module, _font = self._load_module()
        captured = self._stub_renderer(module)

        result = asyncio.run(module.render_glyph_review_image())
        metadata = json.loads(result[0])

        self.assertTrue(metadata["ok"])
        self.assertEqual(metadata["glyphNames"], ["A"])
        self.assertEqual(captured["glyphNames"], ["A"])
        self.assertEqual(captured["overlays"], ["metrics", "sidebearings", "bounds"])
        self.assertIsInstance(result[1], _FakeImage)
        self.assertEqual(result[1].data, b"png")
        self.assertEqual(result[1].format, "png")

    def test_missing_glyph_returns_error_with_warning(self) -> None:
        module, _font = self._load_module()

        result = asyncio.run(module.render_glyph_review_image(glyph_names=["Missing"]))
        metadata = json.loads(result[0])

        self.assertFalse(metadata["ok"])
        self.assertEqual(metadata["error"], "No renderable glyph layers found.")
        self.assertIn("Glyph 'Missing' not found; skipped.", metadata["warnings"])
        self.assertEqual(len(result), 1)

    def test_master_id_selects_requested_layer(self) -> None:
        module, _font = self._load_module()
        captured = self._stub_renderer(module)

        result = asyncio.run(module.render_glyph_review_image(glyph_names=["A"], master_id="m2", overlays=["bounds"]))
        metadata = json.loads(result[0])

        self.assertTrue(metadata["ok"])
        self.assertEqual(metadata["masterId"], "m2")
        self.assertEqual(metadata["masterName"], "Bold")
        self.assertEqual(metadata["glyphs"][0]["layerId"], "m2")
        self.assertEqual(metadata["glyphs"][0]["layerName"], "Bold")
        self.assertEqual(captured["layerIds"], ["m2"])
        self.assertEqual(captured["overlays"], ["bounds"])

    def test_invalid_overlay_returns_supported_overlay_error(self) -> None:
        module, _font = self._load_module()

        result = asyncio.run(module.render_glyph_review_image(glyph_names=["A"], overlays=["bogus"]))
        metadata = json.loads(result[0])

        self.assertFalse(metadata["ok"])
        self.assertIn("Unsupported overlay(s): bogus", metadata["error"])
        self.assertIn("nodes", metadata["supportedOverlays"])
        self.assertEqual(len(result), 1)

    def test_include_base64_adds_data_uri_fallback(self) -> None:
        module, _font = self._load_module()
        self._stub_renderer(module, png_bytes=b"png")

        result = asyncio.run(module.render_glyph_review_image(glyph_names=["A"], include_base64=True))
        metadata = json.loads(result[0])

        self.assertTrue(metadata["ok"])
        self.assertEqual(metadata["dataUri"], "data:image/png;base64,cG5n")
        self.assertIsInstance(result[1], _FakeImage)

    def test_no_selection_without_names_returns_error(self) -> None:
        module, _font = self._load_module(selected_layers=False)

        result = asyncio.run(module.render_glyph_review_image())
        metadata = json.loads(result[0])

        self.assertFalse(metadata["ok"])
        self.assertEqual(metadata["error"], "No glyph_names provided and no selected glyphs found.")
        self.assertEqual(len(result), 1)

    def test_tool_omits_return_annotation_to_avoid_structured_image_serialization(self) -> None:
        module, _font = self._load_module()

        self.assertIs(
            inspect.signature(module.render_glyph_review_image).return_annotation,
            inspect.Signature.empty,
        )

    def test_main_thread_helper_reuses_objc_class_for_repeated_calls(self) -> None:
        module, _font = self._load_module()
        self._configure_fake_objc(module, reset_registry=True)

        self.assertEqual(module._run_on_main_thread(lambda: "first"), "first")
        self.assertEqual(module._run_on_main_thread(lambda: "second"), "second")

        self.assertEqual(list(_FakeObjCMeta.registry), [module._OBJC_MAIN_THREAD_HELPER_CLASS_NAME])

    def test_main_thread_helper_looks_up_existing_objc_class_after_reload(self) -> None:
        first_module, _font = self._load_module(module_name="glyphs_mcp_test_mcp_tools_visual_review_first")
        self._configure_fake_objc(first_module, reset_registry=True)
        first_class = first_module._get_main_thread_helper_class()
        self.assertEqual(first_module._run_on_main_thread(lambda: "first"), "first")

        second_module, _font = self._load_module(module_name="glyphs_mcp_test_mcp_tools_visual_review_second")
        self._configure_fake_objc(second_module)
        self.assertEqual(second_module._run_on_main_thread(lambda: "second"), "second")

        self.assertIs(first_class, second_module._get_main_thread_helper_class())
        self.assertEqual(list(_FakeObjCMeta.registry), [second_module._OBJC_MAIN_THREAD_HELPER_CLASS_NAME])


if __name__ == "__main__":
    unittest.main()
