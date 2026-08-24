# encoding: utf-8

"""Drawing-only Edit View projection of the latest MCP mutation."""

from __future__ import annotations

import objc
from AppKit import NSBezierPath, NSColor, NSGraphicsContext, NSPoint
from GlyphsApp.plugins import ReporterPlugin  # type: ignore[import-not-found]

from .adapters.document import native_layer_overlay_state
from .diff_geometry import DifferenceTopologyError, difference_bands
from .diff_overlay import overlay_for_layer
from .runtime import active_history, active_host


DIFFERENCE_RGBA = (1.0, 0.58, 0.08, 0.46)
METRIC_RGBA = (1.0, 0.58, 0.08, 0.34)


def _point(value):
    return NSPoint(float(value[0]), float(value[1]))


def _set_color(rgba):
    NSColor.colorWithDeviceRed_green_blue_alpha_(*rgba).set()


def _append_segments(path, segments, *, reverse=False, move=True):
    start = segments[-1].points[-1] if reverse else segments[0].points[0]
    if move:
        path.moveToPoint_(_point(start))
    ordered = reversed(segments) if reverse else segments
    for segment in ordered:
        if segment.kind == "cubic":
            start_point, control1, control2, end = segment.points
            if reverse:
                path.curveToPoint_controlPoint1_controlPoint2_(
                    _point(start_point), _point(control2), _point(control1)
                )
            else:
                path.curveToPoint_controlPoint1_controlPoint2_(
                    _point(end), _point(control1), _point(control2)
                )
        else:
            end = segment.points[0] if reverse else segment.points[-1]
            path.lineToPoint_(_point(end))


def _draw_difference(baseline_paths, current_paths):
    bands = difference_bands(baseline_paths, current_paths)
    if not bands:
        return 0
    difference_path = NSBezierPath.bezierPath()
    for band in bands:
        _append_segments(difference_path, band.baseline_segments)
        if band.closed:
            difference_path.closePath()
            _append_segments(difference_path, band.current_segments, reverse=True)
        else:
            difference_path.lineToPoint_(_point(band.current_segments[-1].points[-1]))
            _append_segments(
                difference_path,
                band.current_segments,
                reverse=True,
                move=False,
            )
        difference_path.closePath()
    _set_color(DIFFERENCE_RGBA)
    difference_path.fill()
    return len(bands)


def _draw_anchor_delta(baseline, current, radius):
    _set_color(DIFFERENCE_RGBA)
    path = NSBezierPath.bezierPath()
    path.moveToPoint_(_point(baseline))
    path.lineToPoint_(_point(current))
    path.setLineWidth_(max(radius, 1.0))
    path.stroke()


def _fill_metric_delta(baseline, current):
    left, right = sorted((float(baseline), float(current)))
    if left == right:
        return
    _set_color(METRIC_RGBA)
    band = NSBezierPath.bezierPath()
    band.moveToPoint_(NSPoint(left, -80.0))
    band.lineToPoint_(NSPoint(right, -80.0))
    band.lineToPoint_(NSPoint(right, 820.0))
    band.lineToPoint_(NSPoint(left, 820.0))
    band.closePath()
    band.fill()


class GlyphsMCPChangeDiffReporter(ReporterPlugin):
    """Fill the live geometric delta from the pre-agent baseline."""

    @objc.python_method
    def settings(self):
        self.menuName = "Glyphs MCP Changes"

    @objc.python_method
    def foreground(self, layer):
        if NSGraphicsContext.currentContext() is None or layer is None:
            return
        history = active_history()
        host = active_host()
        if history is None or host is None:
            return
        glyph = getattr(layer, "parent", None)
        font = getattr(glyph, "parent", None) if glyph is not None else None
        glyph_name = str(getattr(glyph, "name", "") or "")
        if font is None or not glyph_name:
            return
        try:
            document_id = host.document_id_for_font(font)
            layer_model = native_layer_overlay_state(layer)
            session = history.latest_session_diff(document_id)
            overlay = None
            for layer_key in dict.fromkeys(
                str(value or "")
                for value in (layer_model.get("id"), layer_model.get("masterId"))
                if value
            ):
                candidate = overlay_for_layer(
                    trees=history.trees,
                    session=session,
                    glyph_name=glyph_name,
                    layer_key=layer_key,
                    live_layer=layer_model,
                )
                if candidate.visible:
                    overlay = candidate
                    break
        except Exception:
            return
        if overlay is None or not overlay.visible:
            return
        try:
            scale = float(self.getScale() or 1.0)
        except Exception:
            scale = 1.0
        try:
            _draw_difference(overlay.baseline_paths, overlay.current_paths)
        except DifferenceTopologyError:
            return
        radius = max(2.4 / max(scale, 0.01), 1.0)
        for name, position in overlay.baseline_anchors.items():
            current = overlay.current_anchors.get(name)
            if current is not None and current != position:
                _draw_anchor_delta(position, current, radius)
        if (
            overlay.baseline_width is not None
            and overlay.current_width is not None
            and overlay.baseline_width != overlay.current_width
        ):
            _fill_metric_delta(overlay.baseline_width, overlay.current_width)

    @objc.python_method
    def __file__(self):
        return __file__


__all__ = ["GlyphsMCPChangeDiffReporter"]
