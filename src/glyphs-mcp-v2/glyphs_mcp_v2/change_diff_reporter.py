# encoding: utf-8

"""Stable, non-blocking Edit View comparison with a pinned reference."""

from __future__ import annotations

import time

import objc
from AppKit import NSBezierPath, NSColor, NSGraphicsContext, NSPoint
from Foundation import NSNotificationCenter, NSObject, NSOperationQueue
from GlyphsApp import (  # type: ignore[import-not-found]
    DOCUMENTACTIVATED,
    DOCUMENTCLOSED,
    DOCUMENTOPENED,
    DOCUMENTWASSAVED,
    UPDATEINTERFACE,
    Glyphs,
)
try:
    from GlyphsApp import UPDATEEDITVIEWFRAME  # type: ignore[import-not-found]
except ImportError:  # Glyphs builds predating the exported Python constant.
    UPDATEEDITVIEWFRAME = "GSUpdateEditViewFrame"
from GlyphsApp.plugins import ReporterPlugin  # type: ignore[import-not-found]

from .adapters.document import NativeLayerOverlayProjector
from .comparison_reference import (
    ReferenceUpdate,
    default_comparison_reference_service,
    native_font_identity,
)
from .diff_overlay import (
    LayerDiffPlan,
    LayerVisualState,
    SavedLayerGeometryCache,
    build_layer_diff_plan,
)
from .projection_queue import (
    JobToken,
    PlanVersion,
    PreparedPlan,
    PreparedPlanCache,
    ProjectionRequestQueue,
    ViewStamp,
)
from .saved_source import normalize_source_path
from .visual_work import VisualWorkSnapshot, default_visual_work_gate


SAVED_HEX = "#3FE2A6"
DIFFERENCE_HEX = "#3FD1E2"
METRIC_HEX = "#3FDAC4"
SAVED_RGBA = (63.0 / 255.0, 226.0 / 255.0, 166.0 / 255.0, 0.78)
DIFFERENCE_RGBA = (63.0 / 255.0, 209.0 / 255.0, 226.0 / 255.0, 0.26)
METRIC_RGBA = (63.0 / 255.0, 218.0 / 255.0, 196.0 / 255.0, 0.18)
NATIVE_WILL_SAVE_NOTIFICATION = "NSDocumentWillSaveNotification"
PROJECTION_SETTLE_DELAY_SECONDS = 0.025
RAPID_INTERFACE_EVENT_SECONDS = 0.075
RAPID_SETTLE_DELAY_SECONDS = 0.100
POST_MCP_RESUME_DELAY_SECONDS = 0.250
VIEW_STABILITY_INTERVAL_SECONDS = 0.016
MAXIMUM_STABILITY_SAMPLES = 4
CAPTURE_SLICE_MAXIMUM_SECONDS = 0.002
# Leave scheduling/property-access headroom beneath the public 2 ms ceiling.
CAPTURE_SLICE_BUDGET_SECONDS = 0.001
CAPTURE_SLICE_INTERVAL_SECONDS = 0.016
PLAN_CACHE_CAPACITY = 128
REPORTER_CLASS_NAME = "GlyphsMCPChangeDiffReporter"


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


def _class_name(value):
    try:
        name = value.__class__.__name__
        if name:
            return str(name)
    except Exception:
        pass
    try:
        return str(value.className())
    except Exception:
        return ""


def _controller_identity(controller):
    try:
        return ("controller", int(hash(controller)))
    except Exception:
        return ("controller", id(controller))


def _number(value, default=0.0):
    try:
        return float(_native_value(value))
    except Exception:
        return float(default)


def _point_components(value):
    value = _native_value(value)
    if value is None:
        return None
    try:
        return (_number(getattr(value, "x")), _number(getattr(value, "y")))
    except Exception:
        pass
    try:
        return (_number(value[0]), _number(value[1]))
    except Exception:
        return str(value)


def _size_components(value):
    value = _native_value(value)
    if value is None:
        return None
    try:
        return (
            _number(getattr(value, "width")),
            _number(getattr(value, "height")),
        )
    except Exception:
        pass
    try:
        return (_number(value[0]), _number(value[1]))
    except Exception:
        return str(value)


def _rect_components(value):
    value = _native_value(value)
    if value is None:
        return None
    try:
        return (
            _point_components(getattr(value, "origin")),
            _size_components(getattr(value, "size")),
        )
    except Exception:
        pass
    try:
        return tuple(_number(item) for item in value)
    except Exception:
        return str(value)


def _cursor_components(value):
    value = _native_value(value)
    if value is None:
        return None
    try:
        return (
            _number(getattr(value, "location")),
            _number(getattr(value, "length")),
        )
    except Exception:
        pass
    try:
        return tuple(_number(item) for item in value)
    except Exception:
        return value


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
    """Publish stable immutable plans; keep drawing callbacks drawing-only."""

    @objc.python_method
    def settings(self):
        # Glyphs prefixes Reporter menu names with “Show”.
        self.menuName = "Changes Against Reference"
        self._references = default_comparison_reference_service()
        self._saved_sources = self._references.saved_sources
        self._projection_state = ProjectionRequestQueue(
            delay_seconds=PROJECTION_SETTLE_DELAY_SECONDS,
            stability_interval_seconds=VIEW_STABILITY_INTERVAL_SECONDS,
            maximum_stability_samples=MAXIMUM_STABILITY_SAMPLES,
        )
        self._prepared_plan_cache = PreparedPlanCache(
            capacity=PLAN_CACHE_CAPACITY
        )
        self._saved_geometry_cache = SavedLayerGeometryCache(
            capacity=PLAN_CACHE_CAPACITY
        )
        self._visual_work = default_visual_work_gate()
        visual_snapshot = self._visual_work.current()
        self._controllers = {}
        self._last_interface_event_at = {}
        self._active_paths = set()
        self._callbacks = []
        self._unsubscribe_references = None
        self._unsubscribe_visual_work = None
        self._native_notification_center = None
        self._active_controller_identity = None
        self._reporter_active = False
        self._visual_sequence = visual_snapshot.sequence
        self._resume_sequence = visual_snapshot.sequence
        self._visual_suspended = visual_snapshot.suspended
        self._visual_pause_active = visual_snapshot.suspended
        self._suspension_started_at = (
            time.monotonic() if visual_snapshot.suspended else None
        )
        self._resume_generation = 0
        self._flush_generation = 0
        self._flush_deadline = None
        self._capture_serial = 0
        self._capture_jobs = {}
        self._disposed = False
        self._diagnostics = {
            "interfaceEvents": 0,
            "frameEvents": 0,
            "capturesStarted": 0,
            "capturesCompleted": 0,
            "cancellations": 0,
            "cacheHits": 0,
            "publications": 0,
            "targetedRedraws": 0,
            "globalFallbacks": 0,
            "suspensions": int(visual_snapshot.suspended),
            "resumes": 0,
            "activityCancellations": 0,
            "foregroundSkips": 0,
            "captureSlices": 0,
            "overBudgetCaptureSlices": 0,
            "rapidSettleDeferrals": 0,
            "completedSuspensionMs": 0.0,
            "lastCaptureMs": 0.0,
            "maximumCaptureMs": 0.0,
            "lastPreparationMs": 0.0,
            "maximumPreparationMs": 0.0,
            "maximumCaptureSliceMs": 0.0,
        }
        self._redraw_fallback_records = []

    @objc.python_method
    def start(self):
        self._unsubscribe_visual_work = self._visual_work.subscribe(
            self._visual_work_changed
        )
        self._visual_work_changed(self._visual_work.current())
        self._unsubscribe_references = self._references.subscribe(
            self._reference_updated
        )
        for callback, event in (
            (self.DocumentChanged_, DOCUMENTOPENED),
            (self.DocumentChanged_, DOCUMENTACTIVATED),
            (self.DocumentSaved_, DOCUMENTWASSAVED),
            (self.DocumentChanged_, DOCUMENTCLOSED),
            (self.InterfaceChanged_, UPDATEINTERFACE),
            (self.EditViewFrameChanged_, UPDATEEDITVIEWFRAME),
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
        self.performSelector_withObject_afterDelay_(
            "initialActivationCheck:", None, 0.0
        )

    @objc.python_method
    def _visual_work_changed(self, snapshot: VisualWorkSnapshot):
        """Flip the draw guard synchronously, then marshal UI work to AppKit."""

        if self._disposed or not isinstance(snapshot, VisualWorkSnapshot):
            return
        if snapshot.suspended:
            # This assignment deliberately precedes main-queue dispatch.  MCP
            # handlers may queue native work immediately after acquiring.
            self._visual_suspended = True

        def publish_visual_state():
            self._apply_visual_work_snapshot(snapshot)

        NSOperationQueue.mainQueue().addOperationWithBlock_(
            publish_visual_state
        )

    @objc.python_method
    def _apply_visual_work_snapshot(self, snapshot):
        if self._disposed or snapshot.sequence < self._visual_sequence:
            return
        self._visual_sequence = snapshot.sequence
        if snapshot.suspended:
            self._visual_suspended = True
            self._resume_generation += 1
            if not self._visual_pause_active:
                self._visual_pause_active = True
                self._suspension_started_at = time.monotonic()
                self._diagnostics["suspensions"] += 1
                self._suspend_projection_work(activity=True)
            return
        if not self._visual_pause_active:
            return
        self._resume_generation += 1
        generation = self._resume_generation
        self._resume_sequence = snapshot.sequence
        self.performSelector_withObject_afterDelay_(
            "resumeVisualWork:", generation, POST_MCP_RESUME_DELAY_SECONDS
        )

    @objc.python_method
    def _finish_suspension_timing(self):
        started = self._suspension_started_at
        if started is not None:
            self._diagnostics["completedSuspensionMs"] += max(
                0.0, (time.monotonic() - started) * 1000.0
            )
        self._suspension_started_at = None
        self._visual_pause_active = False

    @objc.typedSelector(b"v@:@")
    def resumeVisualWork_(self, sender):
        try:
            generation = int(sender)
        except Exception:
            generation = self._resume_generation
        if self._disposed or generation != self._resume_generation:
            return
        current_visual_work = self._visual_work.current()
        if (
            current_visual_work.suspended
            or current_visual_work.sequence != self._resume_sequence
        ):
            return
        if not self._reporter_is_active():
            self._reporter_active = False
            self._visual_suspended = True
            self._finish_suspension_timing()
            return
        self._reporter_active = True
        self._finish_suspension_timing()
        self._visual_suspended = False
        self._diagnostics["resumes"] += 1
        self._reconcile_current_view()

    @objc.python_method
    def _suspend_projection_work(self, *, activity):
        sessions = self._projection_state.sessions()
        pending_sessions = {
            session.session_identity
            for session in sessions
            if session.capture_requested or session.capture_token is not None
        }
        pending_sessions.update(
            job["token"].session_identity for job in self._capture_jobs.values()
        )
        self._capture_jobs.clear()
        self._flush_generation += 1
        self._flush_deadline = None
        suspended = self._projection_state.suspend(clear_published=True)
        for session in sessions:
            self._saved_sources.coordinator.invalidate(
                session.session_identity, kind="diff"
            )
        cancelled_count = len(suspended.cancelled_tokens)
        self._diagnostics["cancellations"] += cancelled_count
        if activity:
            self._diagnostics["activityCancellations"] += len(
                pending_sessions
            )
        for controller_identity in suspended.invalidated_controllers:
            self._invalidate_controller(controller_identity)

    def DocumentWillSave_(self, notification):
        path = _notification_source_path(notification)
        paths = (path,) if path is not None else tuple(self._active_paths)
        for source_path in paths:
            self._saved_sources.pause_for_save(source_path)

    def DocumentChanged_(self, _notification):
        self._refresh_open_fonts(force=False)
        self._cleanup_sessions()
        self._references.notify_sessions()

    def DocumentSaved_(self, notification):
        self._refresh_open_fonts(force=False)
        path = _notification_source_path(notification)
        paths = (path,) if path is not None else tuple(self._active_paths)
        for source_path in paths:
            self._saved_sources.resume_after_save(source_path)

    def InterfaceChanged_(self, _notification):
        if self._disposed:
            return
        self._diagnostics["interfaceEvents"] += 1
        if self._visual_suspended:
            return
        self._cleanup_sessions()
        was_active = self._reporter_active
        if self._sync_reporter_activation(interface_event=True) and was_active:
            self._reconcile_current_view(interface_event=True)

    def EditViewFrameChanged_(self, _notification):
        if self._disposed:
            return
        self._diagnostics["frameEvents"] += 1
        if self._visual_suspended:
            return
        if not self._sync_reporter_activation():
            return
        controller = self._current_controller()
        if controller is None:
            return
        controller_identity = _controller_identity(controller)
        self._active_controller_identity = controller_identity
        self._controllers[controller_identity] = controller
        session, cancelled = self._projection_state.note_view_frame(
            controller_identity
        )
        if cancelled is not None and session is not None:
            self._saved_sources.coordinator.invalidate(
                session.session_identity, kind="diff"
            )
            self._diagnostics["cancellations"] += 1
        self._arm_state_flush(controller_identity)

    @objc.typedSelector(b"v@:@")
    def initialActivationCheck_(self, _sender):
        if self._disposed:
            return
        self._sync_reporter_activation()

    @objc.python_method
    def _reporter_is_active(self):
        try:
            reporters = list(getattr(Glyphs, "activeReporters", None) or ())
        except Exception:
            return False
        for reporter in reporters:
            if reporter is self or _class_name(reporter) == REPORTER_CLASS_NAME:
                return True
        return False

    @objc.python_method
    def _sync_reporter_activation(self, *, interface_event=False):
        active = self._reporter_is_active()
        if active == self._reporter_active:
            return active
        self._reporter_active = active
        self._references.notify_sessions()
        if not active:
            self._visual_suspended = True
            self._resume_generation += 1
            self._suspend_projection_work(activity=False)
            self._active_controller_identity = None
        else:
            if self._visual_work.current().suspended or self._visual_pause_active:
                self._visual_suspended = True
            else:
                self._visual_suspended = False
                self._reconcile_current_view(
                    interface_event=interface_event
                )
        return active

    @objc.python_method
    def _callback_controller(self):
        try:
            return _native_value(getattr(self, "controller", None))
        except Exception:
            return None

    @objc.python_method
    def _current_controller(self):
        controller = self._callback_controller()
        if controller is not None:
            return controller
        try:
            font = _native_value(getattr(Glyphs, "font", None))
            return _native_value(getattr(font, "currentTab", None))
        except Exception:
            return None

    @objc.python_method
    def _current_layer(self, controller=None):
        if controller is not None:
            try:
                layer = _native_value(getattr(controller, "activeLayer", None))
                if layer is not None:
                    return layer
            except Exception:
                pass
        try:
            return self.activeLayer()
        except Exception:
            return None

    @objc.python_method
    def _layer_request(self, layer):
        glyph = getattr(layer, "parent", None)
        font = getattr(glyph, "parent", None) if glyph is not None else None
        glyph_name = str(getattr(glyph, "name", "") or "")
        document_key = native_font_identity(font)
        layer_key = str(
            getattr(layer, "layerId", None)
            or getattr(layer, "id", None)
            or ""
        )
        if not document_key or not glyph_name or not layer_key:
            return None
        return (document_key, glyph_name, layer_key)

    @objc.python_method
    def _reference_snapshot(self, layer):
        glyph = getattr(layer, "parent", None)
        font = getattr(glyph, "parent", None) if glyph is not None else None
        if font is None:
            return None
        return self._references.snapshot_for_source(
            _font_source_path(font),
            native_identity=native_font_identity(font),
        )

    @objc.python_method
    def _sample_view_stamp(self, controller, layer=None):
        if controller is None:
            return None
        if layer is None:
            layer = self._current_layer(controller)
        active_key = self._layer_request(layer) if layer is not None else None
        try:
            scale = _number(getattr(controller, "scale", 1.0), 1.0)
            viewport = _rect_components(getattr(controller, "viewPort", None))
            bounds = _rect_components(getattr(controller, "bounds", None))
            cursor = _cursor_components(getattr(controller, "layersCursor", None))
            origin = _point_components(
                getattr(controller, "selectedLayerOrigin", None)
            )
        except Exception:
            return None
        return ViewStamp.create(
            controller_identity=_controller_identity(controller),
            active_layer_key=active_key,
            layer_cursor=cursor,
            scale=scale,
            viewport=viewport,
            bounds=bounds,
            selected_layer_origin=origin,
        )

    @objc.python_method
    def _reconcile_current_view(self, *, interface_event=False):
        if (
            self._disposed
            or self._visual_suspended
            or not self._reporter_active
            or not self._reporter_is_active()
        ):
            return
        controller = self._current_controller()
        layer = self._current_layer(controller)
        if controller is None or layer is None:
            return
        controller_identity = _controller_identity(controller)
        key = self._layer_request(layer)
        if key is None:
            return
        snapshot = self._reference_snapshot(layer)
        if snapshot is None:
            existing = self._projection_state.session(controller_identity)
            if existing is not None:
                cancelled = self._projection_state.invalidate_content(
                    controller_identity,
                    clear_published=True,
                    request_invalidation=True,
                )
                if cancelled is not None:
                    self._saved_sources.coordinator.invalidate(
                        existing.session_identity, kind="diff"
                    )
                    self._diagnostics["cancellations"] += 1
                self._arm_state_flush(controller_identity)
            return
        for other in self._projection_state.sessions():
            if other.controller_identity == controller_identity:
                continue
            if not other.capture_requested and other.capture_token is None:
                continue
            cancelled_other = self._projection_state.invalidate_content(
                other.controller_identity,
                clear_published=False,
                request_invalidation=False,
            )
            self._saved_sources.coordinator.invalidate(
                other.session_identity, kind="diff"
            )
            if cancelled_other is not None:
                self._diagnostics["cancellations"] += 1
        self._active_controller_identity = controller_identity
        self._controllers[controller_identity] = controller
        rapid = False
        if interface_event:
            now = time.monotonic()
            previous_event = self._last_interface_event_at.get(
                controller_identity
            )
            rapid = (
                previous_event is not None
                and now - previous_event < RAPID_INTERFACE_EVENT_SECONDS
            )
            self._last_interface_event_at[controller_identity] = now
        settle_delay = (
            RAPID_SETTLE_DELAY_SECONDS
            if rapid
            else PROJECTION_SETTLE_DELAY_SECONDS
        )
        if rapid:
            self._diagnostics["rapidSettleDeferrals"] += 1
        session, cancelled = self._projection_state.note_interface_change(
            controller_identity,
            active_key=key,
            reference_fingerprint=snapshot.source_fingerprint,
            delay_seconds=settle_delay,
        )
        self._saved_sources.coordinator.invalidate(
            session.session_identity, kind="diff"
        )
        if cancelled is not None:
            self._diagnostics["cancellations"] += 1
        self._arm_state_flush(controller_identity)

    @objc.python_method
    def _arm_state_flush(self, controller_identity):
        if (
            self._disposed
            or self._visual_suspended
            or controller_identity is None
        ):
            return
        delay = self._projection_state.remaining_delay(controller_identity)
        if delay is None:
            return
        deadline = time.monotonic() + delay
        if self._flush_deadline is not None and self._flush_deadline <= deadline + 0.0005:
            return
        self._flush_generation += 1
        generation = self._flush_generation
        self._flush_deadline = deadline
        self.performSelector_withObject_afterDelay_(
            "flushProjectionState:", generation, delay
        )

    @objc.typedSelector(b"v@:@")
    def flushProjectionState_(self, sender):
        try:
            generation = int(sender)
        except Exception:
            generation = self._flush_generation
        if (
            self._disposed
            or self._visual_suspended
            or generation != self._flush_generation
        ):
            return
        self._flush_deadline = None
        if not self._sync_reporter_activation():
            return
        controller_identity = self._active_controller_identity
        controller = self._controllers.get(controller_identity)
        if controller is None:
            return
        current_controller = self._current_controller()
        if (
            current_controller is not None
            and _controller_identity(current_controller) != controller_identity
        ):
            self._reconcile_current_view()
            return
        layer = self._current_layer(controller)
        stamp = self._sample_view_stamp(controller, layer)
        if stamp is None:
            return

        capture = self._projection_state.sample_capture(
            controller_identity, stamp
        )
        if capture.status == "ready" and capture.token is not None:
            self._begin_projection(capture.token)
        elif capture.status == "abandoned":
            self._diagnostics["cancellations"] += 1

        invalidation = self._projection_state.sample_invalidation(
            controller_identity, stamp
        )
        if invalidation.status == "ready":
            self._invalidate_controller(controller_identity)
        self._arm_state_flush(controller_identity)

    @objc.python_method
    def _validate_job(self, token, *, require_stable_stamp):
        if (
            self._disposed
            or self._visual_suspended
            or not self._reporter_is_active()
        ):
            return None
        session = self._projection_state.session_for_token(token)
        if session is None:
            return None
        if self._active_controller_identity != session.controller_identity:
            return None
        controller = self._controllers.get(session.controller_identity)
        if controller is None:
            return None
        current_controller = self._current_controller()
        if current_controller is not None and (
            _controller_identity(current_controller) != session.controller_identity
        ):
            return None
        layer = self._current_layer(controller)
        if layer is None or self._layer_request(layer) != token.active_key:
            return None
        snapshot = self._reference_snapshot(layer)
        if (
            snapshot is None
            or snapshot.source_fingerprint != token.reference_fingerprint
        ):
            return None
        stamp = (
            self._sample_view_stamp(controller, layer)
            if require_stable_stamp
            else None
        )
        if not self._projection_state.is_current(token, stamp=stamp):
            return None
        return controller, layer, snapshot

    @objc.python_method
    def _cancel_projection(self, token, *, retry_if_view_changed):
        for job_id, job in tuple(self._capture_jobs.items()):
            if job["token"] == token:
                self._capture_jobs.pop(job_id, None)
        session = self._projection_state.session_for_token(token)
        if session is None:
            return
        self._saved_sources.coordinator.invalidate(
            session.session_identity, kind="diff"
        )
        retried = False
        if retry_if_view_changed and self._projection_state.is_current(token):
            retried = self._projection_state.retry_after_view_change(token)
        if not retried:
            self._projection_state.cancel_job(token)
        self._diagnostics["cancellations"] += 1
        if retried:
            self._arm_state_flush(session.controller_identity)

    @objc.python_method
    def _begin_projection(self, token: JobToken):
        validated = self._validate_job(token, require_stable_stamp=True)
        if validated is None:
            self._cancel_projection(token, retry_if_view_changed=True)
            return
        _controller, initial_layer, snapshot = validated
        self._capture_serial += 1
        job_id = "capture_{}".format(self._capture_serial)
        self._capture_jobs[job_id] = {
            "token": token,
            "initialLayer": initial_layer,
            "snapshot": snapshot,
            "projector": None,
            "startedNs": time.perf_counter_ns(),
        }
        self._diagnostics["capturesStarted"] += 1
        self.performSelector_withObject_afterDelay_(
            "advanceProjectionCapture:", job_id, 0.0
        )

    @objc.typedSelector(b"v@:@")
    def advanceProjectionCapture_(self, sender):
        job_id = str(sender)
        job = self._capture_jobs.get(job_id)
        if job is None or self._visual_suspended:
            return
        token = job["token"]
        validated = self._validate_job(token, require_stable_stamp=True)
        if validated is None:
            self._capture_jobs.pop(job_id, None)
            self._cancel_projection(token, retry_if_view_changed=True)
            return
        _controller, current_layer, _snapshot = validated
        if (
            current_layer is not job["initialLayer"]
            and self._layer_request(current_layer) != token.active_key
        ):
            self._capture_jobs.pop(job_id, None)
            self._cancel_projection(token, retry_if_view_changed=False)
            return
        try:
            if job["projector"] is None:
                job["projector"] = NativeLayerOverlayProjector(current_layer)
            slice_started = time.perf_counter_ns()
            complete = job["projector"].step(
                budget_seconds=CAPTURE_SLICE_BUDGET_SECONDS
            )
            elapsed_ms = (
                time.perf_counter_ns() - slice_started
            ) / 1_000_000.0
        except Exception:
            self._capture_jobs.pop(job_id, None)
            self._cancel_projection(token, retry_if_view_changed=False)
            return
        self._diagnostics["captureSlices"] += 1
        self._diagnostics["maximumCaptureSliceMs"] = max(
            self._diagnostics["maximumCaptureSliceMs"], elapsed_ms
        )
        if elapsed_ms > CAPTURE_SLICE_MAXIMUM_SECONDS * 1000.0:
            self._diagnostics["overBudgetCaptureSlices"] += 1
        if not complete:
            self.performSelector_withObject_afterDelay_(
                "advanceProjectionCapture:",
                job_id,
                CAPTURE_SLICE_INTERVAL_SECONDS,
            )
            return
        try:
            layer_model = job["projector"].result()
        except Exception:
            self._capture_jobs.pop(job_id, None)
            self._cancel_projection(token, retry_if_view_changed=False)
            return
        self._capture_jobs.pop(job_id, None)
        capture_ms = (
            time.perf_counter_ns() - job["startedNs"]
        ) / 1_000_000.0
        self._diagnostics["lastCaptureMs"] = capture_ms
        self._diagnostics["maximumCaptureMs"] = max(
            self._diagnostics["maximumCaptureMs"], capture_ms
        )
        self._diagnostics["capturesCompleted"] += 1
        if self._validate_job(token, require_stable_stamp=True) is None:
            self._cancel_projection(token, retry_if_view_changed=True)
            return
        self._submit_projection_preparation(
            token, job["snapshot"], layer_model
        )

    @objc.python_method
    def _submit_projection_preparation(self, token, snapshot, layer_model):
        def prepare(context):
            preparation_started = time.perf_counter_ns()
            if context.cancelled():
                return None
            live_state = LayerVisualState.from_layer(
                layer_model, cancelled=context.cancelled
            )
            version = PlanVersion(
                active_key=token.active_key,
                reference_fingerprint=token.reference_fingerprint,
                live_fingerprint=live_state.fingerprint,
            )
            cached = self._prepared_plan_cache.get(version)
            if cached is not None:
                elapsed = (
                    time.perf_counter_ns() - preparation_started
                ) / 1_000_000.0
                return cached, True, elapsed
            plan = LayerDiffPlan(visible=False)
            layer_key = str(layer_model.get("id") or "")
            if layer_key and layer_key == token.active_key[2]:
                saved_geometry = self._saved_geometry_cache.get_or_prepare(
                    source_fingerprint=token.reference_fingerprint,
                    baseline_model=snapshot.model,
                    glyph_name=token.active_key[1],
                    layer_key=layer_key,
                    cancelled=context.cancelled,
                )
                plan = build_layer_diff_plan(
                    baseline_model=snapshot.model,
                    glyph_name=token.active_key[1],
                    layer_key=layer_key,
                    live_state=live_state,
                    saved_geometry=saved_geometry,
                    cancelled=context.cancelled,
                )
            if context.cancelled():
                return None
            prepared = PreparedPlan(version=version, plan=plan)
            if context.cancelled():
                return None
            self._prepared_plan_cache.put(prepared)
            elapsed = (
                time.perf_counter_ns() - preparation_started
            ) / 1_000_000.0
            return prepared, False, elapsed

        def completed(result):
            def publish():
                if result is None or self._visual_suspended:
                    self._cancel_projection(
                        token, retry_if_view_changed=False
                    )
                    return
                validated_publish = self._validate_job(
                    token, require_stable_stamp=True
                )
                if validated_publish is None:
                    self._cancel_projection(
                        token, retry_if_view_changed=True
                    )
                    return
                prepared, cache_hit, preparation_ms = result
                changed = self._projection_state.publish(token, prepared)
                if not self._projection_state.session_for_token(token):
                    return
                self._diagnostics["lastPreparationMs"] = preparation_ms
                self._diagnostics["maximumPreparationMs"] = max(
                    self._diagnostics["maximumPreparationMs"],
                    preparation_ms,
                )
                self._diagnostics["cacheHits"] += int(bool(cache_hit))
                self._diagnostics["publications"] += 1
                if changed:
                    session = self._projection_state.session_for_token(token)
                    if session is not None:
                        self._arm_state_flush(session.controller_identity)

            NSOperationQueue.mainQueue().addOperationWithBlock_(publish)

        def failed(_error):
            NSOperationQueue.mainQueue().addOperationWithBlock_(
                lambda: self._cancel_projection(
                    token, retry_if_view_changed=False
                )
            )

        session = self._projection_state.session_for_token(token)
        if session is None or self._visual_suspended:
            self._cancel_projection(token, retry_if_view_changed=False)
            return
        accepted = self._saved_sources.coordinator.submit(
            "diff",
            session.session_identity,
            prepare,
            completed=completed,
            failed=failed,
        )
        if accepted is None:
            self._cancel_projection(token, retry_if_view_changed=False)

    @objc.python_method
    def _invalidate_controller(self, controller_identity):
        controller = self._controllers.get(controller_identity)
        if controller is None:
            controller = self._current_controller()
        try:
            redraw = getattr(controller, "redraw", None)
            if not callable(redraw):
                raise AttributeError("GSEditViewController.redraw is unavailable")
            redraw()
            self._diagnostics["targetedRedraws"] += 1
            return
        except Exception as error:
            self._diagnostics["globalFallbacks"] += 1
            self._redraw_fallback_records.append(
                {
                    "controller": str(controller_identity),
                    "reason": str(error),
                    "time": time.monotonic(),
                }
            )
            if len(self._redraw_fallback_records) > PLAN_CACHE_CAPACITY:
                del self._redraw_fallback_records[:-PLAN_CACHE_CAPACITY]
        try:
            Glyphs.redraw()
        except Exception:
            pass

    @objc.python_method
    def _refresh_open_fonts(self, *, force):
        fonts = list(getattr(Glyphs, "fonts", ()) or ())
        paths = set()
        document_keys = set()
        for font in fonts:
            path = _font_source_path(font)
            identity = native_font_identity(font)
            if path is not None:
                paths.add(path)
            if identity is not None:
                document_keys.add(identity)
                self._references.ensure_source(path, native_identity=identity)
        self._active_paths = set(paths)

        def retained(changed):
            if not changed:
                return

            def publish_retention():
                if self._disposed:
                    return
                for session in self._projection_state.sessions():
                    key = session.active_key
                    if key is not None and key[0] not in document_keys:
                        removed = self._projection_state.remove(
                            session.controller_identity
                        )
                        if removed is not None:
                            self._saved_sources.coordinator.invalidate(
                                removed.session_identity, kind="diff"
                            )
                            self._controllers.pop(
                                removed.controller_identity, None
                            )

            NSOperationQueue.mainQueue().addOperationWithBlock_(
                publish_retention
            )

        self._saved_sources.request_retain_only(paths, completed=retained)
        for source_path in sorted(paths):
            self._saved_sources.request_refresh(source_path, force=bool(force))

    @objc.python_method
    def _reference_updated(self, result: ReferenceUpdate):
        def publish_update():
            if self._disposed:
                return
            active_identity = self._active_controller_identity
            for session in self._projection_state.sessions():
                key = session.active_key
                if key is None or key[0] != result.session_key:
                    continue
                fingerprint = result.status.source_fingerprint
                if (
                    fingerprint == session.reference_fingerprint
                    and (
                        session.published_plan is not None
                        or not result.status.ready
                    )
                ):
                    continue
                cancelled = self._projection_state.invalidate_content(
                    session.controller_identity,
                    clear_published=True,
                    request_invalidation=(
                        self._reporter_active
                        and session.controller_identity == active_identity
                    ),
                )
                self._saved_sources.coordinator.invalidate(
                    session.session_identity, kind="diff"
                )
                if cancelled is not None:
                    self._diagnostics["cancellations"] += 1
            if (
                self._reporter_active
                and not self._visual_suspended
                and result.status.ready
            ):
                self._reconcile_current_view()

        NSOperationQueue.mainQueue().addOperationWithBlock_(publish_update)

    @objc.python_method
    def _cleanup_sessions(self):
        fonts = list(getattr(Glyphs, "fonts", ()) or ())
        controller_identities = set()
        observed_tabs = not fonts
        for font in fonts:
            try:
                tabs = getattr(font, "tabs", None)
                if tabs is None:
                    continue
                observed_tabs = True
                for controller in list(tabs or ()):
                    controller_identities.add(_controller_identity(controller))
                    self._controllers[_controller_identity(controller)] = controller
            except Exception:
                continue
        current = self._current_controller()
        if current is not None:
            current_identity = _controller_identity(current)
            controller_identities.add(current_identity)
            self._controllers[current_identity] = current
        if not observed_tabs:
            return
        for session in self._projection_state.retain(controller_identities):
            self._saved_sources.coordinator.invalidate(
                session.session_identity, kind="diff"
            )
            self._controllers.pop(session.controller_identity, None)
            self._last_interface_event_at.pop(
                session.controller_identity, None
            )

    @objc.python_method
    def _diagnostics_snapshot(self):
        return {
            "scope": "application",
            "policy": {
                "mcpPauseEnabled": True,
                "overlayHiddenWhilePaused": True,
                "resumeDelayMs": POST_MCP_RESUME_DELAY_SECONDS * 1000.0,
                "captureSliceBudgetMs": CAPTURE_SLICE_BUDGET_SECONDS
                * 1000.0,
                "captureSliceCadenceMs": CAPTURE_SLICE_INTERVAL_SECONDS
                * 1000.0,
                "overBudgetThresholdMs": CAPTURE_SLICE_MAXIMUM_SECONDS
                * 1000.0,
            },
            "counters": {
                "suspensions": self._diagnostics["suspensions"],
                "resumes": self._diagnostics["resumes"],
                "activityCancellations": self._diagnostics[
                    "activityCancellations"
                ],
                "foregroundSkips": self._diagnostics["foregroundSkips"],
                "captureSlices": self._diagnostics["captureSlices"],
                "overBudgetSlices": self._diagnostics[
                    "overBudgetCaptureSlices"
                ],
                "rapidSettleDeferrals": self._diagnostics[
                    "rapidSettleDeferrals"
                ],
                "captures": self._diagnostics["capturesCompleted"],
                "cacheHits": self._diagnostics["cacheHits"],
                "publications": self._diagnostics["publications"],
            },
            "timingsMs": {
                "completedSuspension": self._diagnostics[
                    "completedSuspensionMs"
                ],
                "lastCapture": self._diagnostics["lastCaptureMs"],
                "maximumCapture": self._diagnostics["maximumCaptureMs"],
                "lastPreparation": self._diagnostics[
                    "lastPreparationMs"
                ],
                "maximumPreparation": self._diagnostics[
                    "maximumPreparationMs"
                ],
                "maximumSlice": self._diagnostics[
                    "maximumCaptureSliceMs"
                ],
            },
        }

    @objc.python_method
    def foreground(self, layer):
        if self._visual_suspended:
            self._diagnostics["foregroundSkips"] += 1
            return
        if layer is None or NSGraphicsContext.currentContext() is None:
            return
        controller = self._callback_controller()
        if controller is None:
            return
        key = self._layer_request(layer)
        if key is None:
            return
        prepared = self._projection_state.published_for(
            _controller_identity(controller), key
        )
        if prepared is None or not prepared.plan.visible:
            return
        plan = prepared.plan
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
        unsubscribe_visual_work = self._unsubscribe_visual_work
        self._unsubscribe_visual_work = None
        if callable(unsubscribe_visual_work):
            unsubscribe_visual_work()
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
        try:
            NSObject.cancelPreviousPerformRequestsWithTarget_(self)
        except Exception:
            pass
        unsubscribe = self._unsubscribe_references
        self._unsubscribe_references = None
        if callable(unsubscribe):
            unsubscribe()
        for session in self._projection_state.clear():
            self._saved_sources.coordinator.invalidate(
                session.session_identity, kind="diff"
            )
        self._controllers.clear()
        self._last_interface_event_at.clear()
        self._capture_jobs.clear()
        self._resume_generation += 1
        self._flush_generation += 1
        self._flush_deadline = None

    def __del__(self):
        try:
            self._teardown()
        except Exception:
            pass

    @objc.python_method
    def __file__(self):
        return __file__


__all__ = ["GlyphsMCPChangeDiffReporter"]
