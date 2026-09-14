"""Asynchronous visible-layer analysis with a drawing-only Reporter callback."""

from __future__ import annotations

from threading import RLock, Thread

import objc  # type: ignore[import-not-found]
from AppKit import NSBezierPath, NSColor, NSGraphicsContext, NSPoint, NSFont, NSFontAttributeName, NSMakeRect  # type: ignore[import-not-found]
from Foundation import NSString  # type: ignore[import-not-found]
from GlyphsApp import CURVE, OFFCURVE, DOCUMENTOPENED, DOCUMENTACTIVATED, TABDIDOPEN, UPDATEEDITVIEWFRAME, Glyphs, UPDATEINTERFACE  # type: ignore[import-not-found]
from GlyphsApp.plugins import ReporterPlugin  # type: ignore[import-not-found]
from PyObjCTools import AppHelper  # type: ignore[import-not-found]

from curve_core import (
    NEGATIVE_RGBA,
    POSITIVE_RGBA,
    build_curvature_comb,
    overlay_line_widths,
)
from glyphs_mcp_companions import publish, withdraw, visible_layer, invalidate_view, wake_reporter


MANIFEST = {
    "protocol": 1,
    "id": "curve-inspector",
    "version": "0.1.0",
    "capabilities": ["curve.measure", "curve.overlay"],
}


def _value(owner, name, default=None):
    try:
        value = getattr(owner, name)
        return value() if callable(value) else value
    except Exception:
        return default


def _position(node):
    point = _value(node, "position", node)
    return float(_value(point, "x", 0) or 0), float(_value(point, "y", 0) or 0)


def extract_visible_cubics(layer, *, maximum=128, node_limit=8192, path_limit=512):
    """Copy only this layer's direct cubics, plus honest bounded coverage evidence."""
    result = []
    reason = None
    visited = 0
    paths = _value(layer, "paths", ()) or ()
    components = _value(layer, "components", None)
    component_count = len(components) if components is not None else None
    for path_index, path in enumerate(paths):
        if path_index >= path_limit:
            reason = "path_limit"
            break
        nodes = _value(path, "nodes", ()) or ()
        count = len(nodes)
        closed = bool(_value(path, "closed", True))
        for index, node in enumerate(nodes):
            if visited >= node_limit:
                reason = "node_limit"
                break
            visited += 1
            if _value(node, "type", None) != CURVE or count < 4:
                continue
            if not closed and index < 3:
                continue
            indices = tuple((index - offset) % count for offset in (3, 2, 1, 0))
            start, first_control, second_control, end = (nodes[item] for item in indices)
            if any(_value(item, "type", None) != OFFCURVE
                   for item in (first_control, second_control)):
                continue
            # Inspect one additional valid cubic; never count the rest of the layer.
            if len(result) == maximum:
                reason = "cubic_limit"
                break
            result.append(tuple(_position(item) for item in
                                (start, first_control, second_control, end)))
        if reason:
            break
    coverage = {
        "returnedCubicCount": len(result),
        "cubicCount": len(result) if reason is None else None,
        "cubicCountLowerBound": len(result) + (reason == "cubic_limit"),
        "complete": reason is None,
        "limitReason": reason,
        "cubicLimit": maximum,
        "nodeLimit": node_limit,
        "pathLimit": path_limit,
        "omittedComponentCount": component_count,
    }
    return result, coverage


def coverage_notice(coverage, model):
    """Prepare one compact notice off the drawing path; complete refers to raw cubics."""
    parts = []
    reason = coverage["limitReason"]
    if reason == "cubic_limit":
        parts.append("partial: first %d cubics; more exist" % coverage["returnedCubicCount"])
    elif reason:
        parts.append("partial: inspection limit reached")
    components = coverage["omittedComponentCount"]
    if components is None:
        parts.append("component coverage unavailable")
    elif components:
        parts.append("%d component%s omitted" % (components, "s" if components != 1 else ""))
    if model.get("samplesPerCurve", 51) < 51:
        parts.append("reduced sampling")
    if model.get("strokeCapReached"):
        parts.append("stroke limit reached")
    # State the rendering ceiling; do not imply every displayed tooth was clamped.
    if parts:
        parts.append("length capped at 0.12em")
    return "Curve Inspector · " + " · ".join(parts) if parts else ""


class GlyphsCurveInspector(ReporterPlugin):
    @objc.python_method
    def settings(self):
        self.menuName = "Curve Inspector"
        self._cache = {
            "samplesPerCurve": 51,
            "strokeCount": 0,
            "strokeLimit": 2000,
            "strokeCapReached": False,
            "strokes": [],
            "envelopes": [],
        }
        self._generation = 0
        self._pending = None
        self._busy = False
        self._lock = RLock()
        self._source_key = None
        self._layer_id = None
        self._cache_layer_id = None

    @objc.python_method
    def start(self):
        Glyphs.addCallback(self.update_, UPDATEINTERFACE)
        for event in (DOCUMENTOPENED, DOCUMENTACTIVATED, TABDIDOPEN, UPDATEEDITVIEWFRAME):
            Glyphs.addCallback(self.attached_, event)
        publish(MANIFEST)
        self.attached_(None)

    @objc.typedSelector(b"v@:")
    def willActivate(self):
        # Glyphs updates activeReporters after this callback. Refresh on the
        # next main-loop turn without waiting for a canvas interaction.
        self.attached_(None)

    def attached_(self, sender):
        wake_reporter(self, AppHelper)

    @objc.typedSelector(b"v@:@")
    def setController_(self, controller):
        self._controller = controller
        self.attached_(None)

    @objc.typedSelector(b"v@:")
    def willDeactivate(self):
        self._clear_overlay()

    @objc.python_method
    def _clear_overlay(self):
        with self._lock:
            self._generation += 1
            self._source_key = None
            self._cache_layer_id = None
            self._pending = None

    def update_(self, _sender):
        if self not in list(_value(Glyphs, "activeReporters", []) or []):
            self._clear_overlay()
            return
        font = _value(Glyphs, "font", None)
        layer = visible_layer(Glyphs)
        curves, coverage = extract_visible_cubics(layer)
        upm = float(_value(font, "upm", 1000.0) or 1000.0) if font is not None else 1000.0
        try:
            layer_id = int(objc.pyobjc_id(layer)) if layer is not None else None
        except Exception:
            layer_id = id(layer) if layer is not None else None
        source_key = (layer_id, upm, tuple(curves), tuple(sorted(coverage.items())))
        with self._lock:
            if source_key == self._source_key:
                return
            self._source_key = source_key
            self._layer_id = layer_id
            if self._cache_layer_id != layer_id:
                self._cache_layer_id = None
            self._generation += 1
            self._pending = (self._generation, curves, upm, coverage)
            if self._busy:
                return
            self._busy = True
        Thread(target=self._analyze_pending, name="glyphs-curve-inspector", daemon=True).start()

    @objc.python_method
    def _analyze_pending(self):
        while True:
            with self._lock:
                pending = self._pending
                self._pending = None
                if pending is None:
                    self._busy = False
                    return
            generation, curves, upm, coverage = pending
            result = build_curvature_comb(curves, upm=upm)
            result["coverage"] = coverage
            result["notice"] = coverage_notice(coverage, result)
            AppHelper.callAfter(self._publish, generation, result)

    @objc.python_method
    def _publish(self, generation, result):
        with self._lock:
            if generation != self._generation:
                return
            next_cache = dict(result)
            changed = (next_cache != self._cache
                       or self._cache_layer_id != self._layer_id)
            self._cache = next_cache
            self._cache_layer_id = self._layer_id
        if changed:
            try:
                invalidate_view(Glyphs)
            except Exception:
                pass

    @objc.python_method
    def foreground(self, layer):
        NSGraphicsContext.saveGraphicsState()
        try:
            """Draw cached teeth and envelopes; geometry extraction occurs elsewhere."""
            if self._cache_layer_id != int(objc.pyobjc_id(layer)):
                return
            cache = self._cache
            scale = max(float(self.getScale() or 1.0), 1e-6)
            teeth_width, envelope_width = overlay_line_widths(scale)
            for sign, rgba in (("positive", POSITIVE_RGBA), ("negative", NEGATIVE_RGBA)):
                teeth = NSBezierPath.bezierPath()
                teeth.setLineWidth_(teeth_width)
                tooth_count = 0
                for item in cache.get("strokes", []):
                    if item["sign"] != sign:
                        continue
                    teeth.moveToPoint_(NSPoint(*item["start"]))
                    teeth.lineToPoint_(NSPoint(*item["end"]))
                    tooth_count += 1
                if tooth_count:
                    NSColor.colorWithDeviceRed_green_blue_alpha_(*rgba).set()
                    teeth.stroke()

                envelopes = NSBezierPath.bezierPath()
                envelopes.setLineWidth_(envelope_width)
                envelope_count = 0
                for item in cache.get("envelopes", []):
                    points = item["points"] if item["sign"] == sign else []
                    if len(points) < 2:
                        continue
                    envelopes.moveToPoint_(NSPoint(*points[0]))
                    for point in points[1:]:
                        envelopes.lineToPoint_(NSPoint(*point))
                    envelope_count += 1
                if envelope_count:
                    NSColor.colorWithDeviceRed_green_blue_alpha_(*rgba).set()
                    envelopes.stroke()
        finally:
            NSGraphicsContext.restoreGraphicsState()

    @objc.python_method
    def foregroundInViewCoords(self):
        # View positioning only: no curve extraction, font traversal or mutation.
        layer = visible_layer(Glyphs)
        if layer is None or self._cache_layer_id != int(objc.pyobjc_id(layer)):
            return
        notice = self._cache.get("notice", "")
        if not notice:
            return
        tab = _value(_value(Glyphs, "font"), "currentTab")
        viewport = _value(tab, "safeViewPort")
        if viewport is None:
            return
        NSGraphicsContext.saveGraphicsState()
        try:
            position = NSPoint(viewport.origin.x + 12, viewport.origin.y + 34)
            size = NSString.stringWithString_(notice).sizeWithAttributes_(
                {NSFontAttributeName: NSFont.labelFontOfSize_(10)})
            background = NSMakeRect(position.x - 4, position.y - size.height - 4,
                                    size.width + 8, size.height + 8)
            NSColor.textBackgroundColor().colorWithAlphaComponent_(0.94).set()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(background, 3, 3).fill()
            self.drawTextAtPoint(notice, position,
                                 fontSize=10 * float(self.getScale() or 1), align="topleft",
                                 fontColor=NSColor.labelColor())
        finally:
            NSGraphicsContext.restoreGraphicsState()

    @objc.python_method
    def inactiveLayerForeground(self, layer):
        self.foreground(layer)

    @objc.python_method
    def __del__(self):
        try:
            Glyphs.removeCallback(self.update_)
            Glyphs.removeCallback(self.attached_)
        except Exception:
            pass
        withdraw(MANIFEST["id"])

    @objc.python_method
    def __file__(self):
        return __file__
