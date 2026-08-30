# encoding: utf-8

"""Non-blocking Edit View comparison with the latest saved source."""

from __future__ import annotations

import time

import objc
from AppKit import NSBezierPath, NSColor, NSGraphicsContext, NSPoint
from Foundation import NSNotificationCenter, NSOperationQueue
from GlyphsApp import (  # type: ignore[import-not-found]
    DOCUMENTACTIVATED,
    DOCUMENTCLOSED,
    DOCUMENTOPENED,
    DOCUMENTWASSAVED,
    UPDATEINTERFACE,
    Glyphs,
)
from GlyphsApp.plugins import ReporterPlugin  # type: ignore[import-not-found]

from .adapters.document import NativeLayerOverlayProjector
from .diff_overlay import (
    LayerDiffPlan,
    LayerVisualState,
    SavedLayerGeometryCache,
    build_layer_diff_plan,
)
from .saved_source import (
    SavedSourceRefresh,
    default_saved_source_service,
    normalize_source_path,
)


SAVED_RGBA = (1.0, 0.32, 0.06, 0.82)
DIFFERENCE_RGBA = (1.0, 0.58, 0.08, 0.46)
METRIC_RGBA = (1.0, 0.58, 0.08, 0.34)
NATIVE_WILL_SAVE_NOTIFICATION = "NSDocumentWillSaveNotification"


def _native_value(value):
    return value() if callable(value) else value


def _font_source_path(font):
    return normalize_source_path(_native_value(getattr(font, "filepath", None)))


def _notification_source_path(notification):
    try:
        source = _native_value(getattr(notification, "object", None))
    except Exception:
        return None
    candidates = (
        source,
        _native_value(getattr(source, "font", None)) if source is not None else None,
    )
    for candidate in candidates:
        path = _font_source_path(candidate) if candidate is not None else None
        if path is not None:
            return path
    return None


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


def _draw_difference(bands):
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


def _stroke_saved_segments(segment_paths, closed_paths, width):
    outline = NSBezierPath.bezierPath()
    path_count = 0
    for index, segments in enumerate(segment_paths):
        if not segments:
            continue
        _append_segments(outline, segments)
        if index < len(closed_paths) and closed_paths[index]:
            outline.closePath()
        path_count += 1
    if not path_count:
        return 0
    _set_color(SAVED_RGBA)
    outline.setLineWidth_(width)
    outline.stroke()
    return path_count


def _stroke_anchor(position, radius, rgba):
    _set_color(rgba)
    x, y = float(position[0]), float(position[1])
    marker = NSBezierPath.bezierPathWithOvalInRect_(
        ((x - radius, y - radius), (radius * 2.0, radius * 2.0))
    )
    marker.setLineWidth_(max(radius / 2.5, 0.8))
    marker.stroke()


def _stroke_saved_anchor(position, radius):
    _stroke_anchor(position, radius, SAVED_RGBA)


def _stroke_added_anchor(position, radius):
    _stroke_anchor(position, radius, DIFFERENCE_RGBA)


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
    """Draw only immutable plans prepared outside the drawing callback."""

    @objc.python_method
    def settings(self):
        self.menuName = "Changes Since Save"
        self._saved_sources = default_saved_source_service()
        self._plan_cache = {}
        self._projection_versions = {}
        self._projection_pending = set()
        self._saved_geometry_cache = SavedLayerGeometryCache()
        self._active_paths = set()
        self._callbacks = []
        self._unsubscribe_saved_sources = None
        self._native_notification_center = None
        self._interface_generation = 0
        self._disposed = False
        self._last_projection_duration_ms = 0.0

    @objc.python_method
    def start(self):
        self._unsubscribe_saved_sources = self._saved_sources.subscribe(
            self._saved_source_updated
        )
        for callback, event in (
            (self.DocumentChanged_, DOCUMENTOPENED),
            (self.DocumentChanged_, DOCUMENTACTIVATED),
            (self.DocumentSaved_, DOCUMENTWASSAVED),
            (self.DocumentChanged_, DOCUMENTCLOSED),
            (self.InterfaceChanged_, UPDATEINTERFACE),
        ):
            try:
                Glyphs.addCallback(callback, event)
                self._callbacks.append((callback, event))
            except Exception:
                pass
        try:
            center = NSNotificationCenter.defaultCenter()
            center.addObserver_selector_name_object_(
                self,
                "DocumentWillSave:",
                NATIVE_WILL_SAVE_NOTIFICATION,
                None,
            )
            self._native_notification_center = center
        except Exception:
            self._native_notification_center = None
        self._refresh_open_fonts(force=True)

    def DocumentWillSave_(self, notification):
        path = _notification_source_path(notification)
        paths = (path,) if path is not None else tuple(self._active_paths)
        for path in paths:
            self._saved_sources.pause_for_save(path)

    def DocumentChanged_(self, _notification):
        self._refresh_open_fonts(force=False)

    def DocumentSaved_(self, notification):
        self._refresh_open_fonts(force=False)
        path = _notification_source_path(notification)
        paths = (path,) if path is not None else tuple(self._active_paths)
        for path in paths:
            self._saved_sources.resume_after_save(path)

    def InterfaceChanged_(self, _notification):
        self._interface_generation += 1

    @objc.python_method
    def _refresh_open_fonts(self, *, force):
        paths = {
            path
            for font in list(getattr(Glyphs, "fonts", ()) or ())
            if (path := _font_source_path(font)) is not None
        }
        self._active_paths = set(paths)

        def retained(changed):
            if not changed or self._disposed:
                return
            self._plan_cache = {
                key: value for key, value in self._plan_cache.items() if key[0] in paths
            }
            self._request_redraw()

        self._saved_sources.request_retain_only(paths, completed=retained)
        for path in sorted(paths):
            self._saved_sources.request_refresh(path, force=bool(force))

    @objc.python_method
    def _saved_source_updated(self, result: SavedSourceRefresh):
        if self._disposed:
            return
        self._plan_cache = {
            key: value for key, value in self._plan_cache.items() if key[0] != result.path
        }
        self._projection_versions = {
            key: value
            for key, value in self._projection_versions.items()
            if key[0] != result.path
        }
        self._request_redraw()

    @objc.python_method
    def _request_redraw(self):
        if self._disposed:
            return

        def redraw():
            if self._disposed:
                return
            try:
                Glyphs.redraw()
            except Exception:
                pass

        NSOperationQueue.mainQueue().addOperationWithBlock_(redraw)

    @objc.python_method
    def _layer_request(self, layer):
        glyph = getattr(layer, "parent", None)
        font = getattr(glyph, "parent", None) if glyph is not None else None
        glyph_name = str(getattr(glyph, "name", "") or "")
        source_path = _font_source_path(font)
        layer_key = str(
            getattr(layer, "layerId", None)
            or getattr(layer, "id", None)
            or getattr(layer, "associatedMasterId", None)
            or ""
        )
        if not source_path or not glyph_name or not layer_key:
            return None
        return (source_path, glyph_name, layer_key)

    @objc.python_method
    def _schedule_projection(self, key, layer, snapshot):
        version = (snapshot.source_fingerprint, self._interface_generation)
        if self._projection_versions.get(key) == version or key in self._projection_pending:
            return
        self._projection_pending.add(key)
        projector = [None]

        def capture_plain_layer():
            if self._disposed or key not in self._projection_pending:
                return
            current = self._saved_sources.store.snapshot(key[0])
            if current is None or current.source_fingerprint != snapshot.source_fingerprint:
                self._projection_pending.discard(key)
                return
            started = time.perf_counter_ns()
            try:
                if projector[0] is None:
                    projector[0] = NativeLayerOverlayProjector(layer)
                complete = projector[0].step(budget_seconds=0.002)
            except Exception:
                self._projection_pending.discard(key)
                return
            self._last_projection_duration_ms = (
                time.perf_counter_ns() - started
            ) / 1_000_000
            if not complete:
                NSOperationQueue.mainQueue().addOperationWithBlock_(
                    capture_plain_layer
                )
                return
            layer_model = projector[0].result()

            def prepare(_context):
                live_state = LayerVisualState.from_layer(layer_model)
                candidates = tuple(
                    dict.fromkeys(
                        str(value or "")
                        for value in (
                            layer_model.get("id"),
                            layer_model.get("masterId"),
                            key[2],
                        )
                        if value
                    )
                )
                plan = LayerDiffPlan(visible=False)
                for layer_key in candidates:
                    saved_geometry = self._saved_geometry_cache.get_or_prepare(
                        source_fingerprint=snapshot.source_fingerprint,
                        baseline_model=snapshot.model,
                        glyph_name=key[1],
                        layer_key=layer_key,
                    )
                    candidate = build_layer_diff_plan(
                        baseline_model=snapshot.model,
                        glyph_name=key[1],
                        layer_key=layer_key,
                        live_state=live_state,
                        saved_geometry=saved_geometry,
                    )
                    if candidate.visible:
                        return candidate
                    plan = candidate
                return plan

            def completed(plan):
                if self._disposed:
                    return
                previous = self._plan_cache.get(key)
                values = dict(self._plan_cache)
                values[key] = plan
                self._plan_cache = values
                self._projection_versions[key] = version
                self._projection_pending.discard(key)
                if plan != previous:
                    self._request_redraw()

            def failed(_error):
                self._projection_pending.discard(key)

            accepted = self._saved_sources.coordinator.submit(
                "diff",
                key,
                prepare,
                completed=completed,
                failed=failed,
            )
            if accepted is None:
                self._projection_pending.discard(key)

        NSOperationQueue.mainQueue().addOperationWithBlock_(capture_plain_layer)

    @objc.python_method
    def foreground(self, layer):
        if NSGraphicsContext.currentContext() is None or layer is None:
            return
        key = self._layer_request(layer)
        if key is None:
            return
        snapshot = self._saved_sources.store.snapshot(key[0])
        if snapshot is None:
            return
        self._schedule_projection(key, layer, snapshot)
        plan = self._plan_cache.get(key)
        if plan is None or not plan.visible:
            return
        try:
            scale = float(self.getScale() or 1.0)
        except Exception:
            scale = 1.0
        outline_width = max(1.2 / max(scale, 0.01), 0.5)
        _draw_difference(plan.bands)
        _stroke_saved_segments(
            plan.baseline_segments,
            tuple(bool(path.get("closed")) for path in plan.baseline_paths),
            outline_width,
        )
        radius = max(4.0 / max(scale, 0.01), 2.0)
        for name in sorted(set(plan.baseline_anchors) | set(plan.current_anchors)):
            baseline = plan.baseline_anchors.get(name)
            current = plan.current_anchors.get(name)
            if baseline == current:
                continue
            if baseline is not None:
                _stroke_saved_anchor(baseline, radius)
            elif current is not None:
                _stroke_added_anchor(current, radius)
            if baseline is not None and current is not None:
                _draw_anchor_delta(baseline, current, outline_width)
        if (
            plan.baseline_width is not None
            and plan.current_width is not None
            and plan.baseline_width != plan.current_width
        ):
            _draw_metric_delta(
                plan.baseline_width,
                plan.current_width,
                outline_width,
            )

    @objc.python_method
    def _teardown(self):
        if self._disposed:
            return
        self._disposed = True
        for callback, event in tuple(self._callbacks):
            try:
                Glyphs.removeCallback(callback, event)
            except TypeError:
                try:
                    Glyphs.removeCallback(callback)
                except Exception:
                    pass
            except Exception:
                pass
        self._callbacks = []
        center = self._native_notification_center
        if center is not None:
            try:
                center.removeObserver_(self)
            except Exception:
                pass
        self._native_notification_center = None
        unsubscribe = self._unsubscribe_saved_sources
        self._unsubscribe_saved_sources = None
        if callable(unsubscribe):
            unsubscribe()
        for key in tuple(self._projection_pending):
            self._saved_sources.coordinator.invalidate(key)
        self._projection_pending.clear()
        self._plan_cache = {}
        self._projection_versions = {}
        self._saved_geometry_cache.clear()

    def __del__(self):
        try:
            self._teardown()
        except Exception:
            pass

    @objc.python_method
    def __file__(self):
        return __file__


__all__ = ["GlyphsMCPChangeDiffReporter"]
