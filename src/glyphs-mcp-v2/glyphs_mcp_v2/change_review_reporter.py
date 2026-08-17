# encoding: utf-8

"""Drawing-only Edit View overlay for the selected verified v2 operation."""

from __future__ import annotations

import copy

import objc
from AppKit import NSBezierPath, NSColor, NSGraphicsContext, NSPoint
from GlyphsApp import Glyphs  # type: ignore[import-not-found]
from GlyphsApp.plugins import ReporterPlugin  # type: ignore[import-not-found]

from .change_review import CHANGE_REVIEW_STORE, resolve_outline_overlay
from .runtime import active_host

try:
    import candidate_difference_model
except Exception:  # pragma: no cover - bundle always carries the pure model
    candidate_difference_model = None


REPORTER_MENU_NAME = "Glyphs MCP Changes"
CURRENT_RGBA = (0.96, 0.55, 0.18, 0.58)
STALE_RGBA = (0.42, 0.42, 0.45, 0.52)


def _point(value):
    try:
        return [float(value.x), float(value.y)]
    except Exception:
        try:
            return [float(value[0]), float(value[1])]
        except Exception:
            return [0.0, 0.0]


def _values(value):
    if value is None:
        return []
    try:
        return [value[index] for index in range(len(value))]
    except Exception:
        try:
            return list(value)
        except Exception:
            return []


def _plain_paths(layer):
    paths = _values(getattr(layer, "paths", None))
    if not paths:
        paths = [shape for shape in _values(getattr(layer, "shapes", None)) if getattr(shape, "nodes", None) is not None]
    result = []
    for path in paths:
        nodes = []
        for node in _values(getattr(path, "nodes", None)):
            position = _point(getattr(node, "position", (0, 0)))
            nodes.append(
                {
                    "x": position[0],
                    "y": position[1],
                    "type": str(getattr(node, "type", "line") or "line").lower(),
                    "smooth": bool(getattr(node, "smooth", False)),
                    "name": getattr(node, "name", None),
                }
            )
        result.append({"closed": bool(getattr(path, "closed", True)), "nodes": nodes})
    return result


def _node_point(node):
    return float(node.get("x", 0.0)), float(node.get("y", 0.0))


def _path_segments(path_data):
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
    result, handles = [], []
    for node in sequence:
        if str(node.get("type")) == "offcurve":
            handles.append(node)
            continue
        if str(node.get("type")) == "curve" and len(handles) >= 2:
            result.append(
                (
                    "cubic",
                    (
                        _node_point(current),
                        _node_point(handles[-2]),
                        _node_point(handles[-1]),
                        _node_point(node),
                    ),
                )
            )
        else:
            result.append(("line", (_node_point(current), _node_point(node))))
        handles = []
        current = node
    return result


def _ns_point(point):
    return NSPoint(float(point[0]), float(point[1]))


def _append_segments(path, segments, *, reverse=False, move=True):
    if not segments:
        return False
    start = segments[-1][1][-1] if reverse else segments[0][1][0]
    if move:
        path.moveToPoint_(_ns_point(start))
    ordered = reversed(segments) if reverse else segments
    for kind, points in ordered:
        if kind == "cubic":
            if reverse:
                start_point, control1, control2, _end = points
                path.curveToPoint_controlPoint1_controlPoint2_(
                    _ns_point(start_point), _ns_point(control2), _ns_point(control1)
                )
            else:
                _start, control1, control2, end = points
                path.curveToPoint_controlPoint1_controlPoint2_(
                    _ns_point(end), _ns_point(control1), _ns_point(control2)
                )
        else:
            path.lineToPoint_(_ns_point(points[0] if reverse else points[-1]))
    return True


def _difference_path(before_paths, applied_paths):
    if len(before_paths) != len(applied_paths):
        return None
    result = NSBezierPath.bezierPath()
    changed = 0
    for before, applied in zip(before_paths, applied_paths):
        if before == applied:
            continue
        if bool(before.get("closed")) != bool(applied.get("closed")):
            return None
        before_segments = _path_segments(before)
        applied_segments = _path_segments(applied)
        if (
            not before_segments
            or len(before_segments) != len(applied_segments)
            or [segment[0] for segment in before_segments] != [segment[0] for segment in applied_segments]
        ):
            return None
        if not _append_segments(result, before_segments):
            return None
        if before.get("closed"):
            result.closePath()
            _append_segments(result, applied_segments, reverse=True)
        else:
            result.lineToPoint_(_ns_point(applied_segments[-1][1][-1]))
            _append_segments(result, applied_segments, reverse=True, move=False)
        result.closePath()
        changed += 1
    return result if changed else None


def _draw_delta(before_paths, applied_paths, *, stale):
    if NSGraphicsContext.currentContext() is None:
        return False
    difference = _difference_path(before_paths, applied_paths)
    if difference is None:
        return False
    rgba = STALE_RGBA if stale else CURRENT_RGBA
    NSColor.colorWithDeviceRed_green_blue_alpha_(*rgba).set()
    if stale:
        try:
            difference.setLineWidth_(1.5)
            difference.setLineDash_count_phase_([5.0, 3.0], 2, 0.0)
            difference.stroke()
        except Exception:
            difference.fill()
    else:
        difference.fill()
    return True


def _context(layer):
    glyph = getattr(layer, "parent", None)
    font = getattr(glyph, "parent", None) if glyph is not None else None
    glyph_name = str(getattr(glyph, "name", "") or "")
    layer_id = str(getattr(layer, "layerId", getattr(layer, "id", "")) or "")
    master_id = str(getattr(layer, "associatedMasterId", "") or layer_id)
    return font, glyph_name, layer_id, master_id


class GlyphsMCPChangeReviewReporter(ReporterPlugin):
    @objc.python_method
    def settings(self):
        self.menuName = REPORTER_MENU_NAME
        self.keyboardShortcut = None
        self._last_draw = None
        try:
            CHANGE_REVIEW_STORE.add_listener(getattr(Glyphs, "redraw", None))
        except Exception:
            pass

    @objc.python_method
    def foreground(self, layer):
        self._last_draw = None
        if layer is None:
            return
        host = active_host()
        font, glyph_name, layer_id, master_id = _context(layer)
        if host is None or font is None or not glyph_name:
            return
        try:
            document_id = host.document_id_for_font(font)
        except Exception:
            return
        operation = CHANGE_REVIEW_STORE.selected(document_id)
        if operation is None or not operation.reviewable:
            return
        live_paths = _plain_paths(layer)
        overlay = resolve_outline_overlay(
            operation,
            glyph_name=glyph_name,
            layer_id=layer_id,
            master_id=master_id,
            live_paths=live_paths,
        )
        if overlay is None:
            return
        before_paths = copy.deepcopy(list(overlay["beforePaths"]))
        applied_paths = copy.deepcopy(list(overlay["appliedPaths"]))
        stale = bool(overlay["stale"])
        analysis = (
            candidate_difference_model.analyze_difference(before_paths, applied_paths)
            if candidate_difference_model is not None
            else {"topologyCompatible": True, "geometryDifferencePresent": before_paths != applied_paths}
        )
        if not analysis.get("topologyCompatible") or not analysis.get("geometryDifferencePresent"):
            return
        if not _draw_delta(before_paths, applied_paths, stale=stale):
            return
        self._last_draw = {
            "operationId": operation.operation_id,
            "glyphName": glyph_name,
            "layerId": layer_id,
            "stale": stale,
            "changedPathCount": int(analysis.get("changedPathCount") or 0),
            "maxOutlineDisplacement": analysis.get("maxOutlineDisplacement"),
        }

    @objc.python_method
    def foregroundInViewCoords(self):
        draw = self._last_draw
        if not draw:
            return
        tab = getattr(getattr(Glyphs, "font", None), "currentTab", None)
        origin = getattr(tab, "selectedLayerOrigin", None) if tab is not None else None
        if origin is None:
            return
        label = "Glyphs MCP change {}{}".format(
            str(draw.get("operationId") or "")[:12],
            " · STALE" if draw.get("stale") else "",
        )
        try:
            scale = float(getattr(tab, "scale", 1.0) or 1.0)
            self.drawTextAtPoint(label, origin, 10.0 / max(scale, 0.01))
        except Exception:
            pass


__all__ = ["GlyphsMCPChangeReviewReporter"]
