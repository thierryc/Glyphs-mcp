from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


RESOURCES = (
    Path(__file__).resolve().parent.parent
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)
sys.path.insert(0, str(RESOURCES))

import outline_candidate_state  # noqa: E402


_CG_EVENTS = []


class _Point:
    def __init__(self, x=0.0, y=0.0):
        self.x, self.y = float(x), float(y)

    def __getitem__(self, index):
        return (self.x, self.y)[index]


class _Path:
    created = []
    fail_draw = False

    def __init__(self):
        self.commands = []
        self.filled = False
        self.stroked = False
        self.width = None
        self.__class__.created.append(self)

    @classmethod
    def bezierPath(cls):
        return cls()

    def appendBezierPath_(self, other):
        self.commands.extend(other.commands)

    def moveToPoint_(self, point):
        self.commands.append(("move", point.x, point.y))

    def lineToPoint_(self, point):
        self.commands.append(("line", point.x, point.y))

    def curveToPoint_controlPoint1_controlPoint2_(self, point, c1, c2):
        self.commands.append(("curve", point.x, point.y, c1.x, c1.y, c2.x, c2.y))

    def closePath(self):
        self.commands.append(("close",))

    def setLineWidth_(self, width):
        self.width = float(width)

    def fill(self):
        if self.__class__.fail_draw:
            raise RuntimeError("simulated_mask_failure")
        self.filled = True
        _CG_EVENTS.append(("fill", tuple(self.commands)))

    def stroke(self):
        if self.__class__.fail_draw:
            raise RuntimeError("simulated_mask_failure")
        self.stroked = True
        _CG_EVENTS.append(("stroke", self.width, tuple(self.commands)))


class _ColorValue:
    active = []

    def __init__(self, rgba):
        self.rgba = tuple(rgba)

    def set(self):
        self.__class__.active.append(self.rgba)


class _Color:
    @staticmethod
    def colorWithDeviceRed_green_blue_alpha_(*rgba):
        return _ColorValue(rgba)


class _CGContext:
    fail_draw = False


class _NSContext:
    def __init__(self, context):
        self.context = context

    def CGContext(self):
        return self.context


class _GraphicsContext:
    current = _NSContext(_CGContext())

    @classmethod
    def currentContext(cls):
        return cls.current


class _Reporter:
    def getScale(self):
        return 1.0

    def drawTextAtPoint(self, *args, **kwargs):
        self.lastText = args[0]


def _event(name):
    def record(*args):
        _CG_EVENTS.append((name,) + tuple(args[1:] if args else ()))

    return record


def _fill_path(context):
    if context.fail_draw:
        raise RuntimeError("simulated_mask_failure")
    _CG_EVENTS.append(("fillpath",))


class CandidateReporterTests(unittest.TestCase):
    def setUp(self):
        outline_candidate_state.STORE.reset()
        _Path.created = []
        _Path.fail_draw = False
        _ColorValue.active = []
        _CG_EVENTS[:] = []
        _GraphicsContext.current = _NSContext(_CGContext())
        _CGContext.fail_draw = False

    def _load(self):
        spec = importlib.util.spec_from_file_location(
            "glyphs_mcp_test_candidate_reporter",
            RESOURCES / "glyphs_candidate_reporter.py",
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        glyphs = types.SimpleNamespace(redraw=lambda: None, font=None)
        helpers = types.SimpleNamespace(
            _get_layer_id=lambda layer: getattr(layer, "layerId", None),
            _layer_paths=lambda layer: list(getattr(layer, "paths", []) or []),
            _normalized_node_type=lambda node: node.type,
        )
        quartz = types.SimpleNamespace(
            CGContextAddCurveToPoint=_event("curve"),
            CGContextAddLineToPoint=_event("line"),
            CGContextBeginPath=_event("beginpath"),
            CGContextClosePath=_event("closepath"),
            CGContextFillPath=_fill_path,
            CGContextMoveToPoint=_event("move"),
            CGContextRestoreGState=_event("restore"),
            CGContextSaveGState=_event("save"),
            CGContextSetRGBFillColor=_event("fillcolor"),
        )
        with mock.patch.dict(
            sys.modules,
            {
                "objc": types.SimpleNamespace(python_method=lambda function: function),
                "AppKit": types.SimpleNamespace(
                    NSBezierPath=_Path,
                    NSColor=_Color,
                    NSGraphicsContext=_GraphicsContext,
                    NSPoint=lambda x=0, y=0: _Point(x, y),
                ),
                "GlyphsApp": types.SimpleNamespace(Glyphs=glyphs),
                "GlyphsApp.plugins": types.SimpleNamespace(ReporterPlugin=_Reporter),
                "Quartz": quartz,
                "mcp_tool_helpers": helpers,
            },
        ):
            spec.loader.exec_module(module)
        module._test_glyphs = glyphs
        return module

    @staticmethod
    def _fixture(closed=False, identical=False):
        points = [(0, 0), (20, 0), (100, 60), (100, 100)]
        kinds = ["line", "offcurve", "offcurve", "curve"]
        nodes = [types.SimpleNamespace(position=_Point(x, y), type=kind) for (x, y), kind in zip(points, kinds)]
        live_path = types.SimpleNamespace(nodes=nodes, closed=closed)
        font = types.SimpleNamespace(filepath=None, upm=1000, currentTab=None)
        glyph = types.SimpleNamespace(name="a", parent=font, layers=[])
        layer = types.SimpleNamespace(paths=[live_path], parent=glyph, layerId="m1", userData={})
        glyph.layers = [layer]
        source = {
            "paths": [
                {
                    "closed": closed,
                    "nodes": [
                        {"x": x, "y": y, "type": kind, "smooth": False}
                        for (x, y), kind in zip(points, kinds)
                    ],
                }
            ],
            "components": [],
            "anchors": [],
            "shapeOrder": [{"kind": "path", "index": 0}],
            "width": 400,
            "protected": {},
        }
        candidate = copy.deepcopy(source)
        if not identical:
            candidate["paths"][0]["nodes"][1]["x"] = 30
        entry = {
            "entryId": "e1",
            "fontKey": "memory:{}".format(id(font)),
            "glyphName": "a",
            "sourceLayerId": "m1",
            "operation": "tunni",
            "source": source,
            "candidate": candidate,
        }
        # A legacy field is deliberately present and must be ignored.
        outline_candidate_state.STORE.put_session(
            {"sessionId": "s1", "operation": "tunni", "showCurvature": True, "entries": [entry]}
        )
        return layer

    def test_draws_only_golden_difference_group(self):
        module = self._load()
        reporter = module.GlyphsMCPCandidateReporter()
        reporter.settings()
        layer = self._fixture()

        reporter.foreground(layer)
        state = reporter.overlayStateSnapshot()

        self.assertEqual(reporter.menuName, "Glyphs MCP Candidate")
        self.assertEqual(state["displayMode"], "difference_only")
        self.assertEqual(state["lastDraw"]["changedNodeCount"], 1)
        self.assertTrue(state["lastDraw"]["geometryDifferencePresent"])
        self.assertEqual(state["lastDraw"]["changedPathCount"], 1)
        self.assertEqual(state["lastDraw"]["differenceGroupCount"], 1)
        self.assertEqual(
            state["lastDraw"]["differenceCompositor"],
            "appkit_topology_paired_contour_ribbons",
        )
        self.assertEqual(state["lastDraw"]["curvatureStrokeCount"], 0)
        self.assertFalse(state["lastDraw"]["stale"])
        self.assertEqual(module.DIFFERENCE_RGBA[-1], 0.82)
        self.assertIn(module.DIFFERENCE_RGBA, _ColorValue.active)
        self.assertEqual(len(_Path.created), 1)
        self.assertTrue(_Path.created[0].filled)
        self.assertFalse(any(event[0] == "blend" for event in _CG_EVENTS))
        self.assertFalse(any("oval" in command for path in _Path.created for command in path.commands))

    def test_closed_paths_use_reversed_contour_ribbons(self):
        module = self._load()
        reporter = module.GlyphsMCPCandidateReporter()
        reporter.settings()

        reporter.foreground(self._fixture(closed=True))

        self.assertEqual(
            sum(1 for command in _Path.created[0].commands if command[0] == "close"),
            2,
        )
        self.assertTrue(_Path.created[0].filled)

    def test_identical_geometry_draws_nothing_over_glyph(self):
        module = self._load()
        reporter = module.GlyphsMCPCandidateReporter()
        reporter.settings()

        reporter.foreground(self._fixture(identical=True))
        state = reporter.overlayStateSnapshot()["lastDraw"]

        self.assertFalse(state["geometryDifferencePresent"])
        self.assertEqual(state["differenceGroupCount"], 0)
        self.assertEqual(_Path.created, [])

    def test_source_edit_marks_candidate_stale_and_uses_coral(self):
        module = self._load()
        reporter = module.GlyphsMCPCandidateReporter()
        reporter.settings()
        layer = self._fixture()
        layer.paths[0].nodes[0].position.x = 5

        reporter.foreground(layer)

        self.assertTrue(reporter.overlayStateSnapshot()["lastDraw"]["stale"])
        self.assertIn(module.STALE_DIFFERENCE_RGBA, _ColorValue.active)

    def test_removing_all_live_paths_fails_closed_on_topology_change(self):
        module = self._load()
        reporter = module.GlyphsMCPCandidateReporter()
        reporter.settings()
        layer = self._fixture()
        layer.paths = []

        with mock.patch("builtins.print"):
            reporter.foreground(layer)

        state = reporter.overlayStateSnapshot()
        self.assertIsNone(state["lastDraw"])
        self.assertEqual(
            state["lastError"]["code"],
            "candidate_difference_topology_incompatible",
        )
        self.assertFalse(any(path.filled for path in _Path.created))

    def test_component_expansion_failure_draws_no_raw_path_fallback(self):
        module = self._load()
        reporter = module.GlyphsMCPCandidateReporter()
        reporter.settings()
        layer = self._fixture()
        layer.components = [object()]
        layer.copy = mock.Mock(side_effect=RuntimeError("simulated_copy_failure"))

        with mock.patch("builtins.print"):
            reporter.foreground(layer)

        state = reporter.overlayStateSnapshot()
        self.assertIsNone(state["lastDraw"])
        self.assertEqual(state["lastError"]["code"], "candidate_component_expansion_failed")
        self.assertFalse(any(path.filled for path in _Path.created))

    def test_background_never_draws_a_source_outline(self):
        module = self._load()
        reporter = module.GlyphsMCPCandidateReporter()
        reporter.settings()

        reporter.background(self._fixture())

        self.assertEqual(_Path.created, [])
        self.assertEqual(_CG_EVENTS, [])

    def test_candidate_curvature_is_ignored_even_for_legacy_session(self):
        module = self._load()
        reporter = module.GlyphsMCPCandidateReporter()
        reporter.settings()

        with mock.patch("builtins.print"):
            reporter.foreground(self._fixture())

        self.assertEqual(reporter.overlayStateSnapshot()["lastDraw"]["curvatureStrokeCount"], 0)
        self.assertFalse(hasattr(module, "curve_overlay_model"))

    def test_missing_graphics_context_fails_closed(self):
        module = self._load()
        reporter = module.GlyphsMCPCandidateReporter()
        reporter.settings()
        _GraphicsContext.current = None

        with mock.patch("builtins.print"):
            reporter.foreground(self._fixture())
        state = reporter.overlayStateSnapshot()

        self.assertIsNone(state["lastDraw"])
        self.assertEqual(state["lastError"]["code"], "difference_graphics_context_unavailable")
        self.assertFalse(any(path.filled for path in _Path.created))

    def test_appkit_fill_failure_draws_no_fallback(self):
        module = self._load()
        reporter = module.GlyphsMCPCandidateReporter()
        reporter.settings()
        _Path.fail_draw = True

        with mock.patch("builtins.print"):
            reporter.foreground(self._fixture())
        state = reporter.overlayStateSnapshot()

        self.assertIsNone(state["lastDraw"])
        self.assertEqual(state["lastError"]["code"], "candidate_difference_draw_failed")
        self.assertEqual(len(_Path.created), 1)
        self.assertFalse(_Path.created[0].filled)

    def test_unmatched_master_is_not_drawn(self):
        module = self._load()
        reporter = module.GlyphsMCPCandidateReporter()
        reporter.settings()
        layer = self._fixture()
        other = types.SimpleNamespace(paths=layer.paths, parent=layer.parent, layerId="m2", userData={})

        reporter.foreground(other)

        self.assertIsNone(reporter.overlayStateSnapshot()["lastDraw"])

    def test_materialized_layer_compares_current_geometry_to_live_source(self):
        module = self._load()
        reporter = module.GlyphsMCPCandidateReporter()
        reporter.settings()
        source_layer = self._fixture()
        source = copy.deepcopy(outline_candidate_state.STORE.get_session("s1")["entries"][0]["source"])
        generated = copy.deepcopy(source)
        generated["paths"][0]["nodes"][1]["x"] = 30

        current_path = copy.deepcopy(source_layer.paths[0])
        current_path.nodes[1].position.x = 32
        materialized = types.SimpleNamespace(
            paths=[current_path], parent=source_layer.parent, layerId="candidate-1", userData={}
        )
        entry = {
            "entryId": "e1",
            "glyphName": "a",
            "sourceLayerId": "m1",
            "operation": "tunni",
            "source": source,
            "candidate": generated,
        }
        materialized.userData[module.LAYER_METADATA_KEY] = json.dumps({"entry": entry})
        source_layer.parent.layers.append(materialized)
        outline_candidate_state.STORE.reset()

        reporter.foreground(materialized)
        state = reporter.overlayStateSnapshot()["lastDraw"]

        self.assertTrue(state["materialized"])
        self.assertEqual(state["changedNodeCount"], 1)
        self.assertGreater(state["maxNodeMovement"], 11.9)
        drawn_coordinates = [
            command[1:]
            for path in _Path.created
            for command in path.commands
            if command[0] in {"move", "line", "curve"}
        ]
        self.assertTrue(any(32.0 in coordinates for coordinates in drawn_coordinates))

    def test_status_label_is_compact_and_reports_no_difference(self):
        module = self._load()
        reporter = module.GlyphsMCPCandidateReporter()
        reporter.settings()
        layer = self._fixture(identical=True)
        module._test_glyphs.font = layer.parent.parent
        module._test_glyphs.font.currentTab = types.SimpleNamespace(
            viewPort=types.SimpleNamespace(origin=_Point(0, 0)),
            scale=1.0,
        )

        reporter.foreground(layer)
        reporter.foregroundInViewCoords()

        self.assertEqual(reporter.lastText, "No visible outline difference")

    def test_real_appkit_contour_ribbons_change_only_exclusive_region_when_available(self):
        if os.environ.get("GLYPHS_MCP_RUN_APPKIT_DRAWING_TESTS") != "1":
            self.skipTest("real AppKit drawing requires an opted-in application context")
        try:
            import AppKit  # type: ignore[import-not-found]
            import Quartz  # type: ignore[import-not-found]  # noqa: F401
        except Exception:
            self.skipTest("AppKit and Quartz drawing APIs are unavailable")

        spec = importlib.util.spec_from_file_location(
            "glyphs_mcp_real_appkit_candidate_reporter",
            RESOURCES / "glyphs_candidate_reporter.py",
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        glyphs = types.SimpleNamespace(redraw=lambda: None, font=None)
        helpers = types.SimpleNamespace(
            _get_layer_id=lambda layer: getattr(layer, "layerId", None),
            _layer_paths=lambda layer: list(getattr(layer, "paths", []) or []),
            _normalized_node_type=lambda node: node.type,
        )
        with mock.patch.dict(
            sys.modules,
            {
                "objc": types.SimpleNamespace(python_method=lambda function: function),
                "GlyphsApp": types.SimpleNamespace(Glyphs=glyphs),
                "GlyphsApp.plugins": types.SimpleNamespace(ReporterPlugin=_Reporter),
                "mcp_tool_helpers": helpers,
            },
        ):
            spec.loader.exec_module(module)

        def rectangle(right):
            return {
                "closed": True,
                "nodes": [
                    {"x": 10.0, "y": 10.0, "type": "line"},
                    {"x": float(right), "y": 10.0, "type": "line"},
                    {"x": float(right), "y": 60.0, "type": "line"},
                    {"x": 10.0, "y": 60.0, "type": "line"},
                ],
            }

        def render(with_difference):
            width = height = 100
            buffer = bytearray(width * height * 4)
            color_space = Quartz.CGColorSpaceCreateDeviceRGB()
            cg_context = Quartz.CGBitmapContextCreate(
                buffer,
                width,
                height,
                8,
                width * 4,
                color_space,
                Quartz.kCGImageAlphaPremultipliedLast,
            )
            context = AppKit.NSGraphicsContext.graphicsContextWithCGContext_flipped_(cg_context, False)
            AppKit.NSGraphicsContext.saveGraphicsState()
            AppKit.NSGraphicsContext.setCurrentContext_(context)
            try:
                Quartz.CGContextSetRGBFillColor(cg_context, 1.0, 1.0, 1.0, 1.0)
                Quartz.CGContextFillRect(cg_context, Quartz.CGRectMake(0.0, 0.0, 100.0, 100.0))
                Quartz.CGContextSetRGBFillColor(cg_context, 0.0, 0.0, 0.0, 1.0)
                Quartz.CGContextFillRect(cg_context, Quartz.CGRectMake(10.0, 10.0, 50.0, 50.0))
                if with_difference:
                    module._draw_difference(
                        [rectangle(60.0)],
                        [rectangle(70.0)],
                        module.DIFFERENCE_RGBA,
                        1.0,
                    )
            finally:
                context.flushGraphics()
                AppKit.NSGraphicsContext.restoreGraphicsState()
            return bytes(buffer)

        baseline = render(False)
        difference = render(True)
        def components(buffer, x, y):
            row = 99 - int(y)
            offset = (row * 100 + int(x)) * 4
            return tuple(buffer[offset : offset + 4])

        self.assertEqual(components(baseline, 30, 30), components(difference, 30, 30))
        self.assertEqual(components(baseline, 90, 90), components(difference, 90, 90))
        self.assertNotEqual(components(baseline, 65, 30), components(difference, 65, 30))


if __name__ == "__main__":
    unittest.main()
