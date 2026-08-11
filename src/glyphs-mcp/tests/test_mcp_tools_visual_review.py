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
        self.components = []
        self.anchors = []
        self.guides = []
        self.completeBezierPath = object()
        self.bezierPath = object()
        self.parent = None


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
    payload = {"error": "Font index {} out of range. Available fonts: {}".format(font_index, len(fonts or []))}
    if ok_key == "ok":
        payload["ok"] = False
    return payload


class McpToolsVisualReviewTests(unittest.TestCase):
    def _load_module(self, selected_layers=True, module_name="glyphs_mcp_test_mcp_tools_visual_review", broken_fonts=False):
        master_1 = types.SimpleNamespace(id="m1", name="Regular", ascender=800, descender=-200, xHeight=500, capHeight=700)
        master_2 = types.SimpleNamespace(id="m2", name="Bold", ascender=810, descender=-210, xHeight=510, capHeight=710)
        layer_1 = _FakeLayer("m1", "Regular", width=500.0)
        layer_2 = _FakeLayer("m2", "Bold", width=520.0)
        glyph = types.SimpleNamespace(name="A", layers={"m1": layer_1, "m2": layer_2})
        layer_1.parent = glyph
        layer_2.parent = glyph
        font = types.SimpleNamespace(
            familyName="Unit Test Sans",
            upm=1000,
            glyphs={"A": glyph},
            masters=[master_1, master_2],
            selectedFontMaster=master_1,
            selectedLayers=[layer_1] if selected_layers else [],
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
            glyphs_obj = types.SimpleNamespace(fonts=[font], font=font)
        glyphs_module = types.SimpleNamespace(Glyphs=glyphs_obj)
        helpers_module = types.SimpleNamespace(
            _font_resolution_error=_font_resolution_error,
            _get_layer_id=lambda layer_obj: getattr(layer_obj, "associatedMasterId", None),
            _get_left_sidebearing=lambda layer_obj: getattr(layer_obj, "leftSideBearing", None),
            _get_right_sidebearing=lambda layer_obj: getattr(layer_obj, "rightSideBearing", None),
            _layer_components=lambda layer_obj: list(getattr(layer_obj, "components", []) or []),
            _layer_display_name=lambda _font, layer_obj, master_id=None: getattr(layer_obj, "name", None) or "Regular",
            _layer_paths=lambda layer_obj: list(getattr(layer_obj, "paths", []) or []),
            _normalized_node_type=lambda node: str(getattr(node, "type", "")).lower(),
            _resolve_font_by_index=_resolve_font_by_index,
            _safe_json=lambda payload: json.dumps(payload),
        )
        fastmcp_mod = types.ModuleType("fastmcp")
        fastmcp_utilities_mod = types.ModuleType("fastmcp.utilities")
        fastmcp_types_mod = types.ModuleType("fastmcp.utilities.types")
        fastmcp_mod.Image = _FakeImage
        fastmcp_types_mod.Image = _FakeImage
        fastmcp_utilities_mod.types = fastmcp_types_mod
        fastmcp_mod.utilities = fastmcp_utilities_mod

        engine_spec = importlib.util.spec_from_file_location(
            "outline_geometry_engine", _module_path().parent / "outline_geometry_engine.py"
        )
        self.assertIsNotNone(engine_spec)
        engine = importlib.util.module_from_spec(engine_spec)
        assert engine_spec.loader is not None
        engine_spec.loader.exec_module(engine)

        model_spec = importlib.util.spec_from_file_location(
            "curve_overlay_model", _module_path().parent / "curve_overlay_model.py"
        )
        self.assertIsNotNone(model_spec)
        model = importlib.util.module_from_spec(model_spec)
        assert model_spec.loader is not None
        with mock.patch.dict(sys.modules, {"outline_geometry_engine": engine}):
            model_spec.loader.exec_module(model)

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
                "tool_registration": types.SimpleNamespace(glyphs_tool=lambda *_args, **_kwargs: (lambda fn: fn)),
                "mcp_tool_helpers": helpers_module,
                "outline_geometry_engine": engine,
                "curve_overlay_model": model,
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

        def fake_render(render_items, master, columns, image_width, include_components, overlays, upm):
            captured["glyphNames"] = [item["glyphName"] for item in render_items]
            captured["layerIds"] = [item["layerId"] for item in render_items]
            captured["masterId"] = master.id
            captured["columns"] = columns
            captured["imageWidth"] = image_width
            captured["includeComponents"] = include_components
            captured["overlays"] = list(overlays)
            captured["upm"] = upm
            return png_bytes, {
                "imageWidth": image_width,
                "imageHeight": 900,
                "rowCount": 1,
                "columnCount": columns,
                "curvatureSamplesPerCurve": 51 if "curvature" in overlays else None,
                "curvatureStrokeCount": 7 if "curvature" in overlays else None,
                "curvatureStrokeLimit": 20000 if "curvature" in overlays else None,
                "curvatureStrokeCapReached": False if "curvature" in overlays else None,
                "curvatureWarnings": [],
            }

        module._render_contact_sheet_png = fake_render
        module._run_on_main_thread = lambda fn: fn()
        return captured

    @staticmethod
    def _curve_path(points, direction=None):
        node_types = ["line", "offcurve", "offcurve", "curve"]
        nodes = [
            types.SimpleNamespace(position=_Point(point[0], point[1]), type=node_type, smooth=False)
            for point, node_type in zip(points, node_types)
        ]
        return types.SimpleNamespace(nodes=nodes, closed=False, direction=direction)

    def _capture_curvature_drawing(self, module, paths, *, upm=1000.0, sample_count=9, stroke_limit=1000):
        current_color = {"rgba": None}
        strokes = []

        class CapturedColor:
            def __init__(self, rgba):
                self.rgba = tuple(rgba)

            def set(self):
                current_color["rgba"] = self.rgba

        class CapturedNSColor:
            @staticmethod
            def colorWithDeviceRed_green_blue_alpha_(*rgba):
                return CapturedColor(rgba)

        def capture_stroke(x1, y1, x2, y2, width):
            strokes.append(
                {
                    "start": (float(x1), float(y1)),
                    "end": (float(x2), float(y2)),
                    "width": float(width),
                    "rgba": current_color["rgba"],
                }
            )

        state = module._new_curvature_stroke_state(stroke_limit)
        layer = types.SimpleNamespace(paths=list(paths))
        with mock.patch.object(module, "NSColor", CapturedNSColor), mock.patch.object(
            module, "_stroke_line", side_effect=capture_stroke
        ):
            module._draw_curvature_comb(layer, upm, 1.0, sample_count, state)
        return strokes, state

    def test_uses_selected_glyphs_when_names_omitted(self) -> None:
        module, _font = self._load_module()
        captured = self._stub_renderer(module)

        result = asyncio.run(module.render_glyph_review_image())
        metadata = json.loads(result[0])

        self.assertTrue(metadata["ok"])
        self.assertEqual(metadata["glyphNames"], ["A"])
        self.assertEqual(captured["glyphNames"], ["A"])
        self.assertEqual(captured["overlays"], ["metrics", "sidebearings", "bounds"])
        self.assertNotIn("curvatureSamplesPerCurve", metadata["image"])
        self.assertNotIn("curvature", metadata)
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
        self.assertIn("curvature", metadata["supportedOverlays"])
        self.assertEqual(len(result), 1)

    def test_curvature_overlay_is_accepted_and_reported(self) -> None:
        module, _font = self._load_module()
        captured = self._stub_renderer(module)

        result = asyncio.run(module.render_glyph_review_image(glyph_names=["A"], overlays=["curvature"]))
        metadata = json.loads(result[0])

        self.assertTrue(metadata["ok"])
        self.assertEqual(captured["overlays"], ["curvature"])
        self.assertEqual(captured["upm"], 1000.0)
        self.assertEqual(metadata["image"]["curvatureSamplesPerCurve"], 51)
        self.assertEqual(metadata["image"]["curvatureStrokeCount"], 7)
        self.assertFalse(metadata["image"]["curvatureStrokeCapReached"])
        self.assertTrue(metadata["curvature"]["signed"])
        self.assertEqual(metadata["curvature"]["combLengthClampEm"], 0.25)
        self.assertEqual(metadata["curvature"]["componentCountOmitted"], 0)
        legend = metadata["curvature"]["legend"]
        self.assertIn("right normal", legend["normalConvention"])
        self.assertIn("correctly wound counters", legend["pathDirectionRule"])
        self.assertEqual(
            [(entry["sign"], entry["color"]) for entry in legend["entries"]],
            [("positive", "#009E9E"), ("negative", "#DB2E8C")],
        )

    def test_curvature_overlay_reports_components_omitted_from_raw_path_comb(self) -> None:
        module, font = self._load_module()
        font.glyphs["A"].layers["m1"].components = [object(), object()]
        self._stub_renderer(module)

        result = asyncio.run(
            module.render_glyph_review_image(
                glyph_names=["A"],
                include_components=True,
                overlays=["curvature"],
            )
        )
        metadata = json.loads(result[0])

        self.assertEqual(metadata["curvature"]["componentCountOmitted"], 2)
        self.assertEqual(metadata["glyphs"][0]["curvature"]["componentCountOmitted"], 2)
        self.assertEqual(len(metadata["warnings"]), 2)
        self.assertIn("omitted 2 component(s) across 1 glyph layer(s)", metadata["warnings"][0])
        self.assertIn("PNG curvature overlay is deprecated", metadata["warnings"][1])

    def test_curvature_sampling_reduces_deterministically_at_cap(self) -> None:
        module, _font = self._load_module()
        cubic_nodes = [
            types.SimpleNamespace(position=_Point(0, 0), type="line", smooth=False),
            types.SimpleNamespace(position=_Point(20, 0), type="offcurve", smooth=False),
            types.SimpleNamespace(position=_Point(100, 60), type="offcurve", smooth=False),
            types.SimpleNamespace(position=_Point(100, 100), type="curve", smooth=False),
        ]
        paths = [types.SimpleNamespace(nodes=cubic_nodes, closed=False) for _ in range(400)]
        layer = types.SimpleNamespace(paths=paths)

        first = module._curvature_render_sample_count([{"layer": layer}], ["curvature"])
        second = module._curvature_render_sample_count([{"layer": layer}], ["curvature"])
        count, warning = first

        self.assertEqual(first, second)
        self.assertEqual(count, 49)
        self.assertIsNotNone(warning)
        self.assertIn("reduced from 51 to 49", warning)

    def test_curvature_comb_draws_right_normal_magnitude_in_signed_colors(self) -> None:
        module, _font = self._load_module()
        negative_points = ((0, 0), (0, 100), (100, 100), (100, 0))
        positive_points = ((0, 0), (0, -100), (100, -100), (100, 0))
        paths = [self._curve_path(negative_points), self._curve_path(positive_points)]

        strokes, state = self._capture_curvature_drawing(module, paths, sample_count=9)
        samples = []
        for points in (negative_points, positive_points):
            samples.extend(module.outline_geometry_engine.curvature_comb_samples(points, sample_count=9))

        self.assertEqual(len(strokes), 18)
        self.assertEqual(state["drawn"], 18)
        for stroke, sample in zip(strokes, samples):
            curvature = float(sample["curvature"])
            derivative = sample["derivative"]
            speed = float(sample["speed"])
            right_normal = (float(derivative[1]) / speed, -float(derivative[0]) / speed)
            displacement = (
                stroke["end"][0] - stroke["start"][0],
                stroke["end"][1] - stroke["start"][1],
            )
            right_normal_length = displacement[0] * right_normal[0] + displacement[1] * right_normal[1]
            self.assertGreater(right_normal_length, 0.0)
            if curvature > 0.0:
                self.assertEqual(stroke["rgba"], module.CURVATURE_POSITIVE_RGBA)
            else:
                self.assertEqual(stroke["rgba"], module.CURVATURE_NEGATIVE_RGBA)

    def test_png_forwards_direction_and_reversed_path_flips_right_normal_placement(self) -> None:
        module, _font = self._load_module()
        points = ((0, 0), (20, 0), (100, 60), (100, 100))
        clockwise = self._curve_path(points, direction=1)
        counterclockwise = self._curve_path(tuple(reversed(points)), direction=-1)

        captured_paths = []
        original_build = module.curve_overlay_model.build_curve_overlay

        def capture(paths, **kwargs):
            captured_paths.append(paths)
            return original_build(paths, **kwargs)

        with mock.patch.object(module.curve_overlay_model, "build_curve_overlay", side_effect=capture):
            forward, _state = self._capture_curvature_drawing(module, [clockwise], sample_count=9)
            reverse, _state = self._capture_curvature_drawing(module, [counterclockwise], sample_count=9)

        self.assertEqual(captured_paths[0][0]["direction"], 1)
        self.assertEqual(captured_paths[1][0]["direction"], -1)
        for first, second in zip(forward, reversed(reverse)):
            self.assertNotEqual(first["rgba"], second["rgba"])
            self.assertAlmostEqual(first["start"][0], second["start"][0])
            self.assertAlmostEqual(first["start"][1], second["start"][1])
            self.assertAlmostEqual(
                first["end"][0] - first["start"][0],
                -(second["end"][0] - second["start"][0]),
            )
            self.assertAlmostEqual(
                first["end"][1] - first["start"][1],
                -(second["end"][1] - second["start"][1]),
            )

    def test_curvature_comb_scales_with_upm_and_clamps_to_quarter_em(self) -> None:
        module, _font = self._load_module()
        path = self._curve_path(((0, 0), (25, 0), (75, 50), (100, 50)))

        def sample(curvature):
            return {
                "point": (0.0, 0.0),
                "derivative": (1.0, 0.0),
                "speed": 1.0,
                "curvature": curvature,
            }

        with mock.patch.object(
            module.outline_geometry_engine, "curvature_comb_samples", return_value=[sample(0.001)]
        ):
            strokes_1000, _state = self._capture_curvature_drawing(module, [path], upm=1000.0)
        with mock.patch.object(
            module.outline_geometry_engine, "curvature_comb_samples", return_value=[sample(0.0005)]
        ):
            strokes_2000, _state = self._capture_curvature_drawing(module, [path], upm=2000.0)

        self.assertAlmostEqual(strokes_1000[0]["end"][1], -20.0)
        self.assertAlmostEqual(strokes_2000[0]["end"][1], -40.0)

        with mock.patch.object(
            module.outline_geometry_engine, "curvature_comb_samples", return_value=[sample(1.0)]
        ):
            positive_clamp, _state = self._capture_curvature_drawing(module, [path], upm=1000.0)
        with mock.patch.object(
            module.outline_geometry_engine, "curvature_comb_samples", return_value=[sample(-1.0)]
        ):
            negative_clamp, _state = self._capture_curvature_drawing(module, [path], upm=1000.0)

        self.assertAlmostEqual(positive_clamp[0]["end"][1], -250.0)
        self.assertAlmostEqual(negative_clamp[0]["end"][1], -250.0)

    def test_curvature_comb_enforces_actual_stroke_cap_and_reports_warning(self) -> None:
        module, _font = self._load_module()
        path = self._curve_path(((0, 0), (25, 0), (75, 50), (100, 50)))
        samples = [
            {
                "point": (float(index), 0.0),
                "derivative": (1.0, 0.0),
                "speed": 1.0,
                "curvature": 0.001,
            }
            for index in range(10)
        ]
        with mock.patch.object(module.outline_geometry_engine, "curvature_comb_samples", return_value=samples):
            strokes, state = self._capture_curvature_drawing(module, [path], stroke_limit=3)

        self.assertEqual(len(strokes), 3)
        self.assertEqual(state, {"limit": 3, "remaining": 0, "drawn": 3, "capReached": True})
        self.assertEqual(
            module._curvature_render_warnings(None, state),
            ["Curvature overlay reached the hard 3-stroke render cap; no additional comb strokes were drawn."],
        )

    def test_curvature_cap_warning_and_counts_are_exposed_by_tool(self) -> None:
        module, _font = self._load_module()
        self._stub_renderer(module)
        stub_renderer = module._render_contact_sheet_png
        cap_warning = "Curvature overlay reached the hard 20000-stroke render cap; no additional comb strokes were drawn."

        def capped_renderer(*args):
            png_bytes, info = stub_renderer(*args)
            info.update(
                {
                    "curvatureStrokeCount": 20000,
                    "curvatureStrokeLimit": 20000,
                    "curvatureStrokeCapReached": True,
                    "curvatureWarnings": [cap_warning],
                }
            )
            return png_bytes, info

        module._render_contact_sheet_png = capped_renderer
        result = asyncio.run(module.render_glyph_review_image(glyph_names=["A"], overlays=["curvature"]))
        metadata = json.loads(result[0])

        self.assertEqual(metadata["image"]["curvatureStrokeCount"], 20000)
        self.assertEqual(metadata["image"]["curvatureStrokeLimit"], 20000)
        self.assertTrue(metadata["image"]["curvatureStrokeCapReached"])
        self.assertIn(cap_warning, metadata["warnings"])

    def test_real_appkit_curvature_render_returns_png_when_available(self) -> None:
        module, font = self._load_module()
        if any(
            value is None
            for value in (
                module.NSImage,
                module.NSBezierPath,
                module.NSBitmapImageRep,
                module.NSGraphicsContext,
                module.NSMakeRect,
            )
        ):
            self.skipTest("AppKit drawing APIs are unavailable")

        layer = font.glyphs["A"].layers["m1"]
        layer.paths = [self._curve_path(((50, 50), (50, 250), (250, 250), (250, 50)))]
        fill_path = module.NSBezierPath.bezierPathWithRect_(module.NSMakeRect(50.0, 50.0, 200.0, 200.0))
        layer.completeBezierPath = fill_path
        layer.bezierPath = fill_path
        item = {
            "glyphName": "A",
            "layer": layer,
            "width": 500.0,
            "bounds": {
                "minX": 50.0,
                "maxX": 250.0,
                "minY": 50.0,
                "maxY": 250.0,
                "width": 200.0,
                "height": 200.0,
            },
        }
        master = font.masters[0]

        png_bytes, info = module._render_contact_sheet_png(
            [item], master, 1, 360, True, ["curvature"], 1000.0
        )

        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(png_bytes), 100)
        self.assertEqual(info["columnCount"], 1)
        self.assertEqual(info["rowCount"], 1)
        self.assertGreater(info["curvatureStrokeCount"], 0)

    def test_include_base64_adds_data_uri_fallback(self) -> None:
        module, _font = self._load_module()
        self._stub_renderer(module, png_bytes=b"png")

        result = asyncio.run(module.render_glyph_review_image(glyph_names=["A"], include_base64=True))
        metadata = json.loads(result[0])

        self.assertTrue(metadata["ok"])
        self.assertEqual(metadata["dataUri"], "data:image/png;base64,cG5n")
        self.assertIsInstance(result[1], _FakeImage)

    def test_tool_requires_clients_to_display_returned_image_content(self) -> None:
        module, _font = self._load_module()
        self._stub_renderer(module, png_bytes=b"png")

        description = inspect.getdoc(module.render_glyph_review_image) or ""
        self.assertIn("display the returned MCP image content directly", description)
        self.assertIn("are not image previews", description)

        result = asyncio.run(module.render_glyph_review_image(glyph_names=["A"]))
        metadata = json.loads(result[0])
        presentation_note = " ".join(metadata["notes"])
        self.assertIn("Display the returned MCP image content directly in the chat", presentation_note)
        self.assertIn("do not replace it with only metadata or an Open in Glyphs link", presentation_note)
        self.assertIsInstance(result[1], _FakeImage)

    def test_render_falls_back_when_fonts_proxy_fails(self) -> None:
        module, _font = self._load_module(broken_fonts=True)
        captured = self._stub_renderer(module)

        result = asyncio.run(module.render_glyph_review_image(glyph_names=["A"]))
        metadata = json.loads(result[0])

        self.assertTrue(metadata["ok"])
        self.assertEqual(captured["glyphNames"], ["A"])
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
