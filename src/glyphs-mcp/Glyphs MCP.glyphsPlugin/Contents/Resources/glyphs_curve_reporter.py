# encoding: utf-8

"""Native Glyphs Edit View reporter for signed curvature combs."""

from __future__ import division, print_function, unicode_literals

import traceback

import objc  # type: ignore[import-not-found]
from AppKit import NSBezierPath, NSColor, NSPoint  # type: ignore[import-not-found]
from Foundation import NSClassFromString  # type: ignore[import-not-found]
from GlyphsApp import Glyphs  # type: ignore[import-not-found]
from GlyphsApp.plugins import ReporterPlugin  # type: ignore[import-not-found]

import curve_overlay_model
from mcp_tool_helpers import (
    _get_layer_id,
    _layer_components,
    _layer_paths,
    _normalized_node_type,
)


REPORTER_CLASS_NAME = "GlyphsMCPCurvatureReporter"
REPORTER_MENU_NAME = "Glyphs MCP Curvature"
REPORTER_MENU_PATH = "View > Show Glyphs MCP Curvature"


def _point_values(node):
    position = getattr(node, "position", None)
    if position is not None:
        try:
            return float(position.x), float(position.y)
        except Exception:
            pass
        try:
            return float(position[0]), float(position[1])
        except Exception:
            pass
    return float(getattr(node, "x", 0.0)), float(getattr(node, "y", 0.0))


def _path_direction(path):
    try:
        value = int(getattr(path, "direction"))
    except Exception:
        return None
    return value if value in (-1, 1) else None


def _plain_paths(layer):
    paths = []
    signature = []
    for path in list(_layer_paths(layer)):
        nodes = []
        node_signature = []
        for node in list(getattr(path, "nodes", None) or []):
            x, y = _point_values(node)
            node_type = _normalized_node_type(node)
            nodes.append({"x": x, "y": y, "type": node_type})
            node_signature.append((x, y, node_type))
        closed = bool(getattr(path, "closed", True))
        direction = _path_direction(path)
        record = {"nodes": nodes, "closed": closed}
        if direction is not None:
            record["direction"] = direction
        paths.append(record)
        signature.append((closed, direction, tuple(node_signature)))
    return paths, tuple(signature)


def _font_upm(layer):
    try:
        glyph = getattr(layer, "parent", None)
        font = getattr(glyph, "parent", None)
        value = float(getattr(font, "upm", 1000.0) or 1000.0)
        return value if value > 0.0 else 1000.0
    except Exception:
        return 1000.0


def _glyph_name(layer):
    try:
        return str(getattr(getattr(layer, "parent", None), "name", "") or "")
    except Exception:
        return ""


def _stroke_path(lines, line_width):
    path = NSBezierPath.bezierPath()
    path.setLineWidth_(float(line_width))
    for start, end in lines:
        path.moveToPoint_(NSPoint(float(start[0]), float(start[1])))
        path.lineToPoint_(NSPoint(float(end[0]), float(end[1])))
    path.stroke()


def _stroke_envelopes(envelopes, line_width):
    path = NSBezierPath.bezierPath()
    path.setLineWidth_(float(line_width))
    for points in envelopes:
        if len(points) < 2:
            continue
        path.moveToPoint_(NSPoint(float(points[0][0]), float(points[0][1])))
        for point in points[1:]:
            path.lineToPoint_(NSPoint(float(point[0]), float(point[1])))
    path.stroke()


def _set_color(sign):
    rgba = (
        curve_overlay_model.POSITIVE_RGBA
        if sign == "positive"
        else curve_overlay_model.NEGATIVE_RGBA
    )
    NSColor.colorWithDeviceRed_green_blue_alpha_(*rgba).set()


def draw_overlay_model(model, scale):
    """Draw a previously built pure overlay model into the current context."""

    zoom = max(float(scale or 1.0), 1.0e-6)
    teeth_width = max(0.35, 0.75 * zoom ** -0.9)
    envelope_width = max(0.5, 1.15 * zoom ** -0.9)
    for sign in ("positive", "negative"):
        strokes = [
            (stroke["start"], stroke["end"])
            for stroke in model.get("strokes") or []
            if stroke.get("sign") == sign
        ]
        envelopes = [
            envelope.get("points") or []
            for envelope in model.get("envelopes") or []
            if envelope.get("sign") == sign
        ]
        if strokes:
            _set_color(sign)
            _stroke_path(strokes, teeth_width)
        if envelopes:
            _set_color(sign)
            _stroke_envelopes(envelopes, envelope_width)


def _public_draw_snapshot(layer, model, *, cache_hit):
    return {
        "overlayDataVersion": curve_overlay_model.OVERLAY_DATA_VERSION,
        "glyphName": _glyph_name(layer),
        "layerId": _get_layer_id(layer),
        "cubicSegmentCount": int(model.get("segmentCount") or 0),
        "samplesPerCurve": int(model.get("samplesPerCurve") or 0),
        "strokeCount": int(model.get("strokeCount") or 0),
        "strokeLimit": int(model.get("strokeLimit") or 0),
        "strokeCapReached": bool(model.get("strokeCapReached")),
        "clampedStrokeCount": int(model.get("clampedStrokeCount") or 0),
        "degenerateSampleCount": int(model.get("degenerateSampleCount") or 0),
        "componentCountOmitted": int(model.get("componentCountOmitted") or 0),
        "combLengthClampEm": float(model.get("combLengthClampEm") or 0.0),
        "cacheHit": bool(cache_hit),
        "warnings": list(model.get("warnings") or []),
    }


class GlyphsMCPCurvatureReporter(ReporterPlugin):

    @objc.python_method
    def settings(self):
        self.menuName = REPORTER_MENU_NAME
        self.keyboardShortcut = None
        self._cache_key = None
        self._cache_model = None
        self._last_draw = None
        self._last_error = None

    @objc.python_method
    def conditionsAreMetForDrawing(self):
        """Avoid expensive redraws while Glyphs' text or hand tool is active."""

        try:
            controller = self.controller.view().window().windowController()
            if controller is None:
                return True
            tool = controller.toolDrawDelegate()
            for class_name in ("GlyphsToolText", "GlyphsToolHand"):
                tool_class = NSClassFromString(class_name)
                if tool_class is not None and tool.isKindOfClass_(tool_class):
                    return False
        except Exception:
            return True
        return True

    @objc.python_method
    def foreground(self, layer):
        if layer is None or not self.conditionsAreMetForDrawing():
            return
        try:
            paths, path_signature = _plain_paths(layer)
            upm = _font_upm(layer)
            component_count = len(list(_layer_components(layer)))
            cache_key = (
                id(layer),
                float(upm),
                int(component_count),
                path_signature,
            )
            cache_hit = cache_key == self._cache_key and self._cache_model is not None
            if cache_hit:
                model = self._cache_model
            else:
                model = curve_overlay_model.build_curve_overlay(
                    paths,
                    upm=upm,
                    component_count_omitted=component_count,
                )
                self._cache_key = cache_key
                self._cache_model = model

            draw_overlay_model(model, self.getScale())
            self._last_draw = _public_draw_snapshot(layer, model, cache_hit=cache_hit)
            self._last_error = None
        except Exception as error:
            self._last_error = {
                "code": "overlay_draw_failed",
                "message": str(error),
            }
            try:
                print("[Glyphs MCP][Curvature Overlay] {}".format(traceback.format_exc()))
            except Exception:
                pass

    @objc.python_method
    def foregroundInViewCoords(self):
        """Draw a compact legend and bounded warnings in the Edit View."""

        snapshot = self._last_draw
        if not snapshot or int(snapshot.get("cubicSegmentCount") or 0) <= 0:
            return
        try:
            font = getattr(Glyphs, "font", None)
            tab = getattr(font, "currentTab", None)
            viewport = getattr(tab, "viewPort", None)
            if tab is None or viewport is None:
                return
            scale = max(float(getattr(tab, "scale", None) or self.getScale() or 1.0), 1.0e-6)
            origin = viewport.origin
            position = NSPoint(float(origin.x) + 12.0 * scale, float(origin.y) + 12.0 * scale)
            parts = ["Curvature: + teal / - pink", "right-normal outside-ink placement", "raw paths only"]
            omitted = int(snapshot.get("componentCountOmitted") or 0)
            if omitted:
                parts.append("{} component{} omitted".format(omitted, "" if omitted == 1 else "s"))
            if snapshot.get("strokeCapReached"):
                parts.append("stroke cap reached")
            clamped = int(snapshot.get("clampedStrokeCount") or 0)
            if clamped:
                parts.append("{} clamped".format(clamped))
            color_factory = getattr(NSColor, "secondaryLabelColor", None)
            color = color_factory() if callable(color_factory) else NSColor.grayColor()
            self.drawTextAtPoint(
                " · ".join(parts),
                position,
                fontSize=10.0 * scale,
                fontColor=color,
            )
        except Exception:
            try:
                print("[Glyphs MCP][Curvature Overlay] {}".format(traceback.format_exc()))
            except Exception:
                pass

    @objc.python_method
    def overlayStateSnapshot(self):
        return {
            "overlayDataVersion": curve_overlay_model.OVERLAY_DATA_VERSION,
            "reporterClass": REPORTER_CLASS_NAME,
            "menuPath": REPORTER_MENU_PATH,
            "lastDraw": dict(self._last_draw) if self._last_draw else None,
            "lastError": dict(self._last_error) if self._last_error else None,
        }

    @objc.python_method
    def __file__(self):
        """Please leave this method unchanged."""
        return __file__


__all__ = [
    "GlyphsMCPCurvatureReporter",
    "REPORTER_CLASS_NAME",
    "REPORTER_MENU_NAME",
    "REPORTER_MENU_PATH",
    "draw_overlay_model",
]
