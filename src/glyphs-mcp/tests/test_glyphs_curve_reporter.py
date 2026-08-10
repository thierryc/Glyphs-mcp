"""Host-isolated tests for the native Glyphs curvature Reporter."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


class _Point:
    def __init__(self, x=0.0, y=0.0):
        self.x = float(x)
        self.y = float(y)

    def __getitem__(self, index):
        return (self.x, self.y)[index]


class _CapturedPath:
    created = []

    def __init__(self):
        self.width = None
        self.commands = []
        self.did_stroke = False
        self.__class__.created.append(self)

    @classmethod
    def bezierPath(cls):
        return cls()

    def setLineWidth_(self, width):
        self.width = float(width)

    def moveToPoint_(self, point):
        self.commands.append(("move", point.x, point.y))

    def lineToPoint_(self, point):
        self.commands.append(("line", point.x, point.y))

    def stroke(self):
        self.did_stroke = True


class _Color:
    active = []

    def __init__(self, rgba):
        self.rgba = tuple(rgba)

    def set(self):
        self.__class__.active.append(self.rgba)


class _NSColor:
    @staticmethod
    def colorWithDeviceRed_green_blue_alpha_(*rgba):
        return _Color(rgba)

    @staticmethod
    def secondaryLabelColor():
        return _Color((0.5, 0.5, 0.5, 1.0))

    @staticmethod
    def grayColor():
        return _Color((0.5, 0.5, 0.5, 1.0))


class _ReporterPlugin:
    def getScale(self):
        return 1.0

    def drawTextAtPoint(self, text, position, fontSize=10.0, fontColor=None, align="bottomleft"):
        self.drawnText = {
            "text": text,
            "position": (position.x, position.y),
            "fontSize": fontSize,
        }


class GlyphsCurveReporterTests(unittest.TestCase):
    def _load_module(self):
        resources = _resources_dir()
        sys.path.insert(0, str(resources))
        glyphs = types.SimpleNamespace(font=None)
        objc_module = types.SimpleNamespace(python_method=lambda fn: fn)
        appkit = types.SimpleNamespace(
            NSBezierPath=_CapturedPath,
            NSColor=_NSColor,
            NSPoint=lambda x=0.0, y=0.0: _Point(x, y),
        )
        foundation = types.SimpleNamespace(NSClassFromString=lambda _name: None)
        glyphs_app = types.SimpleNamespace(Glyphs=glyphs)
        plugins = types.SimpleNamespace(ReporterPlugin=_ReporterPlugin)
        helpers = types.SimpleNamespace(
            _get_layer_id=lambda layer: getattr(layer, "layerId", None),
            _layer_components=lambda layer: list(getattr(layer, "components", []) or []),
            _layer_paths=lambda layer: list(getattr(layer, "paths", []) or []),
            _normalized_node_type=lambda node: str(getattr(node, "type", "")).lower(),
        )
        spec = importlib.util.spec_from_file_location(
            "glyphs_mcp_test_glyphs_curve_reporter",
            resources / "glyphs_curve_reporter.py",
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "objc": objc_module,
                "AppKit": appkit,
                "Foundation": foundation,
                "GlyphsApp": glyphs_app,
                "GlyphsApp.plugins": plugins,
                "mcp_tool_helpers": helpers,
            },
        ):
            spec.loader.exec_module(module)
        return module, glyphs

    @staticmethod
    def _layer():
        node_types = ["line", "offcurve", "offcurve", "curve"]
        points = [(0, 0), (20, 0), (100, 60), (100, 100)]
        nodes = [
            types.SimpleNamespace(position=_Point(x, y), type=node_type)
            for (x, y), node_type in zip(points, node_types)
        ]
        path = types.SimpleNamespace(nodes=nodes, closed=False, direction=1)
        font = types.SimpleNamespace(upm=1000)
        glyph = types.SimpleNamespace(name="a", parent=font)
        return types.SimpleNamespace(
            paths=[path],
            components=[],
            parent=glyph,
            layerId="m1",
        )

    def setUp(self) -> None:
        _CapturedPath.created = []
        _Color.active = []

    def test_reporter_draws_teeth_and_envelope_and_reports_state(self) -> None:
        module, _glyphs = self._load_module()
        reporter = module.GlyphsMCPCurvatureReporter()
        reporter.settings()
        layer = self._layer()
        before = [
            (node.position.x, node.position.y, node.type)
            for node in layer.paths[0].nodes
        ]

        reporter.foreground(layer)
        state = reporter.overlayStateSnapshot()

        self.assertEqual(reporter.menuName, "Glyphs MCP Curvature")
        self.assertGreater(state["lastDraw"]["strokeCount"], 0)
        self.assertEqual(state["lastDraw"]["glyphName"], "a")
        self.assertFalse(state["lastDraw"]["cacheHit"])
        self.assertTrue(any(path.did_stroke for path in _CapturedPath.created))
        self.assertGreater(
            sum(1 for path in _CapturedPath.created for command in path.commands if command[0] == "line"),
            state["lastDraw"]["strokeCount"],
            "The connected envelope should add line commands beyond the comb teeth.",
        )
        self.assertIn(module.curve_overlay_model.POSITIVE_RGBA, _Color.active)
        self.assertEqual(module.curve_overlay_model.POSITIVE_RGBA[-1], 0.65)
        self.assertEqual(state["lastDraw"]["samplesPerCurve"], 51)
        self.assertEqual(state["lastDraw"]["combLengthClampEm"], 0.12)
        after = [
            (node.position.x, node.position.y, node.type)
            for node in layer.paths[0].nodes
        ]
        self.assertEqual(before, after)

    def test_cache_hits_then_invalidates_after_node_movement(self) -> None:
        module, _glyphs = self._load_module()
        reporter = module.GlyphsMCPCurvatureReporter()
        reporter.settings()
        layer = self._layer()

        reporter.foreground(layer)
        reporter.foreground(layer)
        self.assertTrue(reporter.overlayStateSnapshot()["lastDraw"]["cacheHit"])

        layer.paths[0].nodes[1].position.x += 1.0
        reporter.foreground(layer)
        self.assertFalse(reporter.overlayStateSnapshot()["lastDraw"]["cacheHit"])

    def test_cache_invalidates_when_path_direction_changes(self) -> None:
        module, _glyphs = self._load_module()
        reporter = module.GlyphsMCPCurvatureReporter()
        reporter.settings()
        layer = self._layer()

        with mock.patch.object(
            module.curve_overlay_model,
            "build_curve_overlay",
            wraps=module.curve_overlay_model.build_curve_overlay,
        ) as build:
            reporter.foreground(layer)
            reporter.foreground(layer)
            self.assertEqual(build.call_count, 1)
            self.assertEqual(build.call_args.args[0][0]["direction"], 1)

            layer.paths[0].direction = -1
            reporter.foreground(layer)

            self.assertEqual(build.call_count, 2)
            self.assertEqual(build.call_args.args[0][0]["direction"], -1)
            self.assertFalse(reporter.overlayStateSnapshot()["lastDraw"]["cacheHit"])

    def test_components_are_omitted_and_reported(self) -> None:
        module, _glyphs = self._load_module()
        reporter = module.GlyphsMCPCurvatureReporter()
        reporter.settings()
        layer = self._layer()
        layer.components = [object(), object()]

        reporter.foreground(layer)
        last_draw = reporter.overlayStateSnapshot()["lastDraw"]

        self.assertEqual(last_draw["componentCountOmitted"], 2)
        self.assertIn("components_omitted", [item["code"] for item in last_draw["warnings"]])

    def test_drawing_failure_is_contained_and_reported(self) -> None:
        module, _glyphs = self._load_module()
        reporter = module.GlyphsMCPCurvatureReporter()
        reporter.settings()

        with mock.patch.object(
            module.curve_overlay_model,
            "build_curve_overlay",
            side_effect=RuntimeError("boom"),
        ), mock.patch("builtins.print"):
            reporter.foreground(self._layer())

        state = reporter.overlayStateSnapshot()
        self.assertIsNone(state["lastDraw"])
        self.assertEqual(state["lastError"]["code"], "overlay_draw_failed")
        self.assertIn("boom", state["lastError"]["message"])

    def test_view_coordinate_legend_reports_omissions_and_clamping(self) -> None:
        module, glyphs = self._load_module()
        reporter = module.GlyphsMCPCurvatureReporter()
        reporter.settings()
        reporter._last_draw = {
            "cubicSegmentCount": 1,
            "componentCountOmitted": 2,
            "strokeCapReached": True,
            "clampedStrokeCount": 3,
        }
        glyphs.font = types.SimpleNamespace(
            currentTab=types.SimpleNamespace(
                viewPort=types.SimpleNamespace(origin=_Point(10, 20)),
                scale=2.0,
            )
        )

        reporter.foregroundInViewCoords()

        self.assertIn("+ teal / - pink", reporter.drawnText["text"])
        self.assertIn("right-normal outside-ink placement", reporter.drawnText["text"])
        self.assertIn("2 components omitted", reporter.drawnText["text"])
        self.assertIn("stroke cap reached", reporter.drawnText["text"])
        self.assertIn("3 clamped", reporter.drawnText["text"])


if __name__ == "__main__":
    unittest.main()
