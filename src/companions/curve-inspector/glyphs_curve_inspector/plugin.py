"""Asynchronous visible-layer analysis with a drawing-only Reporter callback."""

from __future__ import annotations

from threading import RLock, Thread

import objc  # type: ignore[import-not-found]
from AppKit import NSBezierPath, NSColor, NSGraphicsContext, NSPoint  # type: ignore[import-not-found]
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


def extract_visible_cubics(layer, *, maximum=128):
    result = []
    for path in list(_value(layer, "paths", []) or []):
        nodes = list(_value(path, "nodes", []) or [])
        closed = bool(_value(path, "closed", True))
        for index, node in enumerate(nodes):
            if _value(node, "type", None) != CURVE or len(nodes) < 4:
                continue
            if not closed and index < 3:
                continue
            indices = (
                tuple((index - offset) % len(nodes) for offset in (3, 2, 1, 0))
                if closed
                else (index - 3, index - 2, index - 1, index)
            )
            start, first_control, second_control, end = (
                nodes[item] for item in indices
            )
            controls = (first_control, second_control)
            if any(_value(item, "type", None) != OFFCURVE for item in controls):
                continue
            result.append(
                (
                    _position(start),
                    _position(first_control),
                    _position(second_control),
                    _position(end),
                )
            )
            if len(result) >= maximum:
                return result
    return result


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
        curves = extract_visible_cubics(layer) if layer is not None else []
        upm = float(_value(font, "upm", 1000.0) or 1000.0) if font is not None else 1000.0
        try:
            layer_id = int(objc.pyobjc_id(layer)) if layer is not None else None
        except Exception:
            layer_id = id(layer) if layer is not None else None
        source_key = (layer_id, upm, tuple(curves))
        with self._lock:
            if source_key == self._source_key:
                return
            self._source_key = source_key
            self._layer_id = layer_id
            if self._cache_layer_id != layer_id:
                self._cache_layer_id = None
            self._generation += 1
            self._pending = (self._generation, curves, upm)
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
            generation, curves, upm = pending
            result = build_curvature_comb(curves, upm=upm)
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
