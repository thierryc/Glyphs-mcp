# encoding: utf-8

"""Drawing-only Edit View comparison with the latest source saved on disk."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import RLock

import objc
from AppKit import NSBezierPath, NSColor, NSGraphicsContext, NSPoint
from Foundation import NSOperationQueue, NSTimer
from GlyphsApp import (  # type: ignore[import-not-found]
    DOCUMENTACTIVATED,
    DOCUMENTCLOSED,
    DOCUMENTOPENED,
    DOCUMENTWASSAVED,
    Glyphs,
)
from GlyphsApp.plugins import ReporterPlugin  # type: ignore[import-not-found]

from .adapters.document import native_layer_overlay_state
from .diff_geometry import (
    DifferenceTopologyError,
    difference_bands,
    path_segments,
)
from .diff_overlay import overlay_for_layer
from .saved_baseline import SavedBaselineCache, normalize_source_path


SAVED_RGBA = (1.0, 0.32, 0.06, 0.82)
DIFFERENCE_RGBA = (1.0, 0.58, 0.08, 0.46)
METRIC_RGBA = (1.0, 0.58, 0.08, 0.34)
SOURCE_POLL_SECONDS = 2.0


def _native_value(value):
    return value() if callable(value) else value


def _font_source_path(font):
    return normalize_source_path(_native_value(getattr(font, "filepath", None)))


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


def _stroke_saved_paths(paths, width):
    outline = NSBezierPath.bezierPath()
    path_count = 0
    for path_data in paths:
        segments = path_segments(path_data)
        if not segments:
            continue
        _append_segments(outline, segments)
        if bool(path_data.get("closed")):
            outline.closePath()
        path_count += 1
    if not path_count:
        return 0
    _set_color(SAVED_RGBA)
    outline.setLineWidth_(width)
    outline.stroke()
    return path_count


def _stroke_saved_anchor(position, radius):
    _set_color(SAVED_RGBA)
    x, y = float(position[0]), float(position[1])
    marker = NSBezierPath.bezierPathWithOvalInRect_(
        ((x - radius, y - radius), (radius * 2.0, radius * 2.0))
    )
    marker.setLineWidth_(max(radius / 2.5, 0.8))
    marker.stroke()


def _draw_anchor_delta(baseline, current, width):
    _set_color(DIFFERENCE_RGBA)
    path = NSBezierPath.bezierPath()
    path.moveToPoint_(_point(baseline))
    path.lineToPoint_(_point(current))
    path.setLineWidth_(max(width, 1.0))
    path.stroke()


def _draw_metric_delta(baseline, current, width):
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
    _set_color(SAVED_RGBA)
    marker = NSBezierPath.bezierPath()
    marker.moveToPoint_(NSPoint(float(baseline), -80.0))
    marker.lineToPoint_(NSPoint(float(baseline), 820.0))
    marker.setLineWidth_(width)
    marker.stroke()


class GlyphsMCPChangeDiffReporter(ReporterPlugin):
    """Draw the gap between the live layer and its latest saved source."""

    @objc.python_method
    def settings(self):
        self.menuName = "Changes Since Save"
        self._baseline_cache = SavedBaselineCache()
        self._baseline_executor = None
        self._baseline_inflight = set()
        self._baseline_pending = {}
        self._baseline_active_paths = set()
        self._baseline_lock = RLock()
        self._baseline_callbacks = []
        self._baseline_timer = None

    @objc.python_method
    def start(self):
        self._baseline_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="glyphs-mcp-saved-baseline",
        )
        for callback, event in (
            (self.DocumentChanged_, DOCUMENTOPENED),
            (self.DocumentChanged_, DOCUMENTACTIVATED),
            (self.DocumentSaved_, DOCUMENTWASSAVED),
            (self.DocumentChanged_, DOCUMENTCLOSED),
        ):
            try:
                Glyphs.addCallback(callback, event)
                self._baseline_callbacks.append(callback)
            except Exception:
                pass
        try:
            self._baseline_timer = (
                NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    SOURCE_POLL_SECONDS,
                    self,
                    "pollSavedSources:",
                    None,
                    True,
                )
            )
        except Exception:
            self._baseline_timer = None
        self._refresh_open_fonts(force=True)

    def DocumentChanged_(self, _notification):
        self._refresh_open_fonts(force=False)

    def DocumentSaved_(self, _notification):
        self._refresh_open_fonts(force=True)

    def pollSavedSources_(self, _timer):
        self._refresh_open_fonts(force=False)

    @objc.python_method
    def _refresh_open_fonts(self, *, force):
        paths = {
            path
            for font in list(getattr(Glyphs, "fonts", ()) or ())
            if (path := _font_source_path(font)) is not None
        }
        with self._baseline_lock:
            self._baseline_active_paths = set(paths)
        if self._baseline_cache.retain_only(paths):
            self._request_redraw()
        for path in sorted(paths):
            self._schedule_refresh(path, force=bool(force))

    @objc.python_method
    def _schedule_refresh(self, path, *, force):
        executor = self._baseline_executor
        if executor is None:
            return
        with self._baseline_lock:
            if path not in self._baseline_active_paths:
                return
            if path in self._baseline_inflight:
                self._baseline_pending[path] = bool(
                    force or self._baseline_pending.get(path, False)
                )
                return
            self._baseline_inflight.add(path)
        future = executor.submit(
            self._baseline_cache.refresh,
            path,
            force=bool(force),
        )
        future.add_done_callback(
            lambda completed, source_path=path: self._refresh_finished(
                source_path, completed
            )
        )

    @objc.python_method
    def _refresh_finished(self, path, future: Future):
        try:
            changed = bool(future.result())
        except Exception:
            changed = False
        with self._baseline_lock:
            self._baseline_inflight.discard(path)
            pending = path in self._baseline_pending
            force = self._baseline_pending.pop(path, False)
            active = path in self._baseline_active_paths
            active_paths = set(self._baseline_active_paths)
        if not active:
            self._baseline_cache.retain_only(active_paths)
            changed = False
        if changed:
            self._request_redraw()
        if pending and active:
            self._schedule_refresh(path, force=force)

    @objc.python_method
    def _request_redraw(self):
        def redraw():
            try:
                Glyphs.redraw()
            except Exception:
                pass

        NSOperationQueue.mainQueue().addOperationWithBlock_(redraw)

    @objc.python_method
    def foreground(self, layer):
        if NSGraphicsContext.currentContext() is None or layer is None:
            return
        glyph = getattr(layer, "parent", None)
        font = getattr(glyph, "parent", None) if glyph is not None else None
        glyph_name = str(getattr(glyph, "name", "") or "")
        source_path = _font_source_path(font)
        snapshot = self._baseline_cache.snapshot(source_path)
        if snapshot is None or not glyph_name:
            return
        try:
            layer_model = native_layer_overlay_state(layer)
            overlay = None
            for layer_key in dict.fromkeys(
                str(value or "")
                for value in (layer_model.get("id"), layer_model.get("masterId"))
                if value
            ):
                candidate = overlay_for_layer(
                    baseline_model=snapshot.model,
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
        outline_width = max(1.2 / max(scale, 0.01), 0.5)
        try:
            _draw_difference(overlay.baseline_paths, overlay.current_paths)
        except (DifferenceTopologyError, ValueError):
            pass
        try:
            _stroke_saved_paths(overlay.baseline_paths, outline_width)
        except ValueError:
            pass
        radius = max(4.0 / max(scale, 0.01), 2.0)
        for name, position in overlay.baseline_anchors.items():
            current = overlay.current_anchors.get(name)
            if current == position:
                continue
            _stroke_saved_anchor(position, radius)
            if current is not None:
                _draw_anchor_delta(position, current, outline_width)
        if (
            overlay.baseline_width is not None
            and overlay.current_width is not None
            and overlay.baseline_width != overlay.current_width
        ):
            _draw_metric_delta(
                overlay.baseline_width,
                overlay.current_width,
                outline_width,
            )

    @objc.python_method
    def __file__(self):
        return __file__


__all__ = ["GlyphsMCPChangeDiffReporter"]
