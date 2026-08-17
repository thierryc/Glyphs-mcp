# encoding: utf-8

"""Drawing-only Edit View projection of the latest MCP mutation."""

from __future__ import annotations

import objc
from AppKit import NSBezierPath, NSColor, NSGraphicsContext, NSPoint
from GlyphsApp.plugins import ReporterPlugin  # type: ignore[import-not-found]

from .adapters.document import native_layer_to_model
from .diff_overlay import overlay_for_layer
from .runtime import active_history, active_host


BEFORE_RGBA = (0.95, 0.24, 0.16, 0.82)
TARGET_STALE_RGBA = (0.35, 0.38, 0.44, 0.74)
METRIC_RGBA = (0.95, 0.48, 0.12, 0.72)


def _point(value):
    return NSPoint(float(value[0]), float(value[1]))


def _segments(path_data):
    nodes = list(path_data.get("nodes") or [])
    if not nodes:
        return []
    oncurve = [index for index, node in enumerate(nodes) if str(node.get("type")) != "offcurve"]
    if not oncurve:
        return []
    start_index = oncurve[0]
    current = nodes[start_index]
    sequence = (
        [nodes[(start_index + offset) % len(nodes)] for offset in range(1, len(nodes) + 1)]
        if path_data.get("closed")
        else nodes[start_index + 1 :]
    )
    result = []
    handles = []
    for node in sequence:
        if str(node.get("type")) == "offcurve":
            handles.append(node)
            continue
        start = (float(current.get("x", 0)), float(current.get("y", 0)))
        end = (float(node.get("x", 0)), float(node.get("y", 0)))
        if str(node.get("type")) == "curve" and len(handles) >= 2:
            result.append(
                (
                    "curve",
                    start,
                    (float(handles[-2].get("x", 0)), float(handles[-2].get("y", 0))),
                    (float(handles[-1].get("x", 0)), float(handles[-1].get("y", 0))),
                    end,
                )
            )
        else:
            result.append(("line", start, end))
        current = node
        handles = []
    return result


def _bezier(paths):
    result = NSBezierPath.bezierPath()
    changed = 0
    for path_data in paths:
        segments = _segments(path_data)
        if not segments:
            continue
        result.moveToPoint_(_point(segments[0][1]))
        for segment in segments:
            if segment[0] == "curve":
                result.curveToPoint_controlPoint1_controlPoint2_(
                    _point(segment[4]), _point(segment[2]), _point(segment[3])
                )
            else:
                result.lineToPoint_(_point(segment[2]))
        if path_data.get("closed"):
            result.closePath()
        changed += 1
    return result if changed else None


def _set_color(rgba):
    NSColor.colorWithDeviceRed_green_blue_alpha_(*rgba).set()


def _stroke_paths(paths, rgba, width, dashed=False):
    path = _bezier(paths)
    if path is None:
        return False
    _set_color(rgba)
    path.setLineWidth_(width)
    if dashed:
        try:
            path.setLineDash_count_phase_([7.0, 4.0], 2, 0.0)
        except Exception:
            pass
    path.stroke()
    return True


def _stroke_anchor(position, rgba, radius):
    _set_color(rgba)
    x, y = float(position[0]), float(position[1])
    marker = NSBezierPath.bezierPathWithOvalInRect_(((x - radius, y - radius), (radius * 2, radius * 2)))
    marker.setLineWidth_(max(0.8, radius / 2.5))
    marker.stroke()


class GlyphsMCPChangeDiffReporter(ReporterPlugin):
    """Render the recorded before state; never mutate or navigate Glyphs."""

    @objc.python_method
    def settings(self):
        self.menuName = "Glyphs MCP Changes"
        self._stale = False

    @objc.python_method
    def foreground(self, layer):
        self._stale = False
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
            layer_model = native_layer_to_model(layer)
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
        width = max(1.2 / max(scale, 0.01), 0.5)
        _stroke_paths(overlay.before_paths, BEFORE_RGBA, width * 1.8, dashed=False)
        if overlay.stale:
            _stroke_paths(overlay.target_paths, TARGET_STALE_RGBA, width * 1.4, dashed=True)
        radius = max(4.0 / max(scale, 0.01), 2.0)
        for name, position in overlay.before_anchors.items():
            if overlay.target_anchors.get(name) != position:
                _stroke_anchor(position, BEFORE_RGBA, radius)
        if overlay.before_width != overlay.target_width and overlay.before_width is not None:
            _set_color(METRIC_RGBA)
            metric = NSBezierPath.bezierPath()
            metric.moveToPoint_(NSPoint(float(overlay.before_width), -80.0))
            metric.lineToPoint_(NSPoint(float(overlay.before_width), 820.0))
            metric.setLineWidth_(width)
            metric.stroke()
        self._stale = bool(overlay.stale)

    @objc.python_method
    def foregroundInViewCoords(self):
        if not self._stale:
            return
        try:
            self.drawTextAtPoint("MCP target edited afterward", NSPoint(18, 22), 10)
        except Exception:
            pass

    @objc.python_method
    def __file__(self):
        return __file__


__all__ = ["GlyphsMCPChangeDiffReporter"]
