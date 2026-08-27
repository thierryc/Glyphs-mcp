# encoding: utf-8

"""Glyphs 4 adapter for unified MCP activity and LitSquare metadata.

The process state is supplied by :mod:`glyphs_mcp_v2.activity`; this module is
the only layer that knows about AppKit, palette visibility, or the transient
fallback capsule.
"""

from __future__ import annotations

import AppKit
import objc
from AppKit import (
    NSButton,
    NSColor,
    NSFont,
    NSMakeRect,
    NSTextField,
    NSView,
    NSViewMaxXMargin,
    NSViewMinXMargin,
    NSViewMinYMargin,
    NSViewWidthSizable,
    NSVisualEffectView,
)
from Foundation import NSOperationQueue, NSThread, NSTimer

from glyphs_litsquare_palette import GlyphsMCPLitSquareMetadataPalette
from i18n import tr

from .activity import ActivitySnapshot, default_activity_store
from .connection_status import (
    TRANSITIONAL_CONNECTION_STATES,
    ConnectionStatusSnapshot,
    default_connection_status_store,
    indicator_presentation,
)


PALETTE_NAME = "Glyphs MCP"
COMPACT_METADATA_HEIGHT = 190
STATUS_HEIGHT = 28
PALETTE_HEIGHT = COMPACT_METADATA_HEIGHT + STATUS_HEIGHT
CAPSULE_DELAY_SECONDS = 2.0
SUCCESS_LINGER_SECONDS = 3.0
ERROR_LINGER_SECONDS = 8.0
ORPHAN_GRACE_SECONDS = 30.0
STATUS_DOT_PULSE_SECONDS = 0.55


def _quiet_field(frame, text="", size=10.0):
    field = NSTextField.alloc().initWithFrame_(frame)
    field.setStringValue_(str(text or ""))
    field.setEditable_(False)
    field.setSelectable_(False)
    field.setBezeled_(False)
    field.setDrawsBackground_(False)
    field.setFont_(NSFont.systemFontOfSize_(size))
    return field


def _native_value(value):
    return value() if callable(value) else value


def _font_from_window(window):
    controller = _native_value(getattr(window, "windowController", None))
    document = _native_value(getattr(controller, "document", None))
    return _native_value(getattr(document, "font", None))


class _PassThroughCapsule(NSVisualEffectView):
    """A drawing-only overlay that never steals editor interaction."""

    def hitTest_(self, point):
        return None


class GlyphsMCPInspectorPalette(GlyphsMCPLitSquareMetadataPalette):
    """One native palette for lightweight status, activity, and metadata."""

    @objc.python_method
    def settings(self):
        GlyphsMCPLitSquareMetadataPalette.settings(self)
        metadata_view = self.dialog
        metadata_view.setFrame_(NSMakeRect(0, 0, 260, COMPACT_METADATA_HEIGHT))
        self.scopeControl.setFrame_(NSMakeRect(8, 160, 244, 22))
        self.scrollView.setFrame_(NSMakeRect(8, 37, 244, 115))
        self.textView.setFrame_(NSMakeRect(0, 0, 240, 111))
        self.infoLabel.setFrame_(NSMakeRect(8, 5, 128, 22))
        for button, x in (
            (self.inspectButton, 144),
            (self.helpButton, 172),
            (self.copyButton, 200),
            (self.refreshButton, 228),
        ):
            button.setFrame_(NSMakeRect(x, 4, 24, 24))

        root = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 260, PALETTE_HEIGHT))
        metadata_view.setAutoresizingMask_(NSViewWidthSizable)
        root.addSubview_(metadata_view)

        status = NSView.alloc().initWithFrame_(
            NSMakeRect(0, COMPACT_METADATA_HEIGHT, 260, STATUS_HEIGHT)
        )
        status.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        root.addSubview_(status)

        dot = NSView.alloc().initWithFrame_(
            NSMakeRect(10, ((STATUS_HEIGHT - 7.0) / 2.0) + 1.5, 7.0, 7.0)
        )
        try:
            dot.setWantsLayer_(True)
            dot_layer = dot.layer()
            if dot_layer is not None:
                dot_layer.setCornerRadius_(3.5)
                dot_layer.setBackgroundColor_(
                    NSColor.secondaryLabelColor().CGColor()
                )
        except Exception:
            pass
        dot.setToolTip_(tr("palette.ready"))
        status.addSubview_(dot)

        field = _quiet_field(NSMakeRect(22, 3, 178, 20), tr("palette.ready"), 10.5)
        field.setAutoresizingMask_(NSViewWidthSizable)
        field.setToolTip_(tr("palette.ready"))
        status.addSubview_(field)

        cancel = NSButton.alloc().initWithFrame_(NSMakeRect(202, 2, 50, 24))
        cancel.setTitle_("Cancel")
        cancel.setBezelStyle_(getattr(AppKit, "NSBezelStyleInline", 15))
        cancel.setTarget_(self)
        cancel.setAction_("cancelActivity:")
        cancel.setHidden_(True)
        cancel.setAutoresizingMask_(NSViewMinXMargin)
        status.addSubview_(cancel)

        self.name = PALETTE_NAME
        self.min = PALETTE_HEIGHT
        self.max = PALETTE_HEIGHT
        self.dialog = root
        self._metadata_view = metadata_view
        self._status_view = status
        self._status_dot_view = dot
        self._activity_field = field
        self._cancel_button = cancel
        self._activity_store = default_activity_store()
        self._connection_store = default_connection_status_store()
        self._activity_snapshot = None
        self._connection_snapshot = self._connection_store.current()
        self._activity_document_id = None
        self._activity_window = None
        self._activity_unsubscribe = None
        self._connection_unsubscribe = None
        self._activity_timer = None
        self._status_dot_pulse_timer = None
        self._status_dot_pulse_dim = False
        self._capsule = None
        self._capsule_label = None

    @objc.python_method
    def start(self):
        GlyphsMCPLitSquareMetadataPalette.start(self)
        self._activity_unsubscribe = self._activity_store.subscribe(
            self._activity_changed
        )
        self._connection_unsubscribe = self._connection_store.subscribe(
            self._connection_changed
        )
        self._refresh_activity()

    @objc.python_method
    def __del__(self):
        unsubscribe = getattr(self, "_activity_unsubscribe", None)
        if unsubscribe is not None:
            try:
                unsubscribe()
            except Exception:
                pass
            self._activity_unsubscribe = None
        unsubscribe = getattr(self, "_connection_unsubscribe", None)
        if unsubscribe is not None:
            try:
                unsubscribe()
            except Exception:
                pass
            self._connection_unsubscribe = None
        self._stop_activity_timer()
        self._stop_status_dot_pulse()
        self._hide_capsule()
        try:
            GlyphsMCPLitSquareMetadataPalette.__del__(self)
        except Exception:
            pass

    def minHeight(self):
        return PALETTE_HEIGHT

    def maxHeight(self):
        return PALETTE_HEIGHT

    @objc.python_method
    def _document_id(self):
        window = self.dialog.window()
        if window is None:
            self._activity_document_id = None
            self._activity_window = None
            return None
        if window is not self._activity_window:
            self._activity_document_id = None
            self._activity_window = window
        try:
            font = self._font() or _font_from_window(window)
            if font is not None:
                from .runtime import active_host

                host = active_host()
                if host is not None:
                    document_id = host.document_id_for_font(font)
                    self._activity_document_id = document_id
        except Exception:
            pass
        return self._activity_document_id

    @objc.python_method
    def _activity_changed(self, _snapshot):
        if NSThread.isMainThread():
            self._refresh_activity()
        else:
            NSOperationQueue.mainQueue().addOperationWithBlock_(
                self._refresh_activity
            )

    @objc.python_method
    def _connection_changed(self, _snapshot):
        if NSThread.isMainThread():
            self._refresh_activity()
        else:
            NSOperationQueue.mainQueue().addOperationWithBlock_(
                self._refresh_activity
            )

    @objc.python_method
    def _refresh_activity(self):
        snapshot = self._activity_store.current(self._document_id())
        connection = self._connection_store.current()
        self._activity_snapshot = snapshot
        self._connection_snapshot = connection
        self._render_activity(snapshot, connection)
        if (
            snapshot.active
            or snapshot.state in ("success", "cancelled", "error")
            or connection.state in TRANSITIONAL_CONNECTION_STATES
        ):
            self._start_activity_timer()
        else:
            self._stop_activity_timer()
            self._hide_capsule()

    @objc.python_method
    def _render_activity(
        self,
        snapshot: ActivitySnapshot,
        connection: ConnectionStatusSnapshot,
    ):
        presentation = indicator_presentation(
            connection.state,
            snapshot.state,
            snapshot.elapsed_seconds,
            snapshot.active,
            heavy_after_seconds=CAPSULE_DELAY_SECONDS,
        )
        if presentation.text_key is not None:
            text = tr(presentation.text_key)
        elif snapshot.active:
            seconds = int(snapshot.elapsed_seconds)
            suffix = " · {} s".format(seconds) if seconds >= 1 else ""
            text = "{}{}".format(snapshot.message, suffix)
        elif snapshot.state == "error":
            text = snapshot.summary or snapshot.message or "Needs attention"
        elif snapshot.state == "cancelled":
            text = "Cancelled"
        elif snapshot.state == "success":
            text = snapshot.summary or "Completed"
        else:
            text = tr("palette.ready")
        self._activity_field.setStringValue_(text)
        self._activity_field.setToolTip_(text)
        self._cancel_button.setHidden_(
            not bool(
                connection.state == "running"
                and snapshot.active
                and snapshot.cancellable
            )
        )
        try:
            if presentation.text_key == "status.error":
                self._activity_field.setTextColor_(NSColor.systemRedColor())
            elif presentation.text_key is not None:
                self._activity_field.setTextColor_(NSColor.secondaryLabelColor())
            elif snapshot.state == "error":
                self._activity_field.setTextColor_(NSColor.systemRedColor())
            elif snapshot.active:
                self._activity_field.setTextColor_(NSColor.labelColor())
            else:
                self._activity_field.setTextColor_(NSColor.secondaryLabelColor())
        except Exception:
            pass
        dot_tooltip = (
            connection.message
            if presentation.text_key is not None and connection.message
            else text
        )
        self._render_status_dot(presentation, dot_tooltip)
        if (
            connection.state == "running"
            and snapshot.active
            and snapshot.elapsed_seconds >= CAPSULE_DELAY_SECONDS
            and not self._palette_is_visible()
        ):
            self._show_capsule(text)
        else:
            self._hide_capsule()

    @objc.python_method
    def _status_dot_color(self, tone):
        color_names = {
            "green": ("systemGreenColor", "greenColor"),
            "blue": ("systemBlueColor", "blueColor"),
            "magenta": ("systemPinkColor", "magentaColor"),
            "red": ("systemRedColor", "redColor"),
            "gray": ("secondaryLabelColor", "grayColor"),
        }
        preferred, fallback = color_names.get(
            str(tone or "gray"),
            color_names["gray"],
        )
        for name in (preferred, fallback):
            try:
                return getattr(NSColor, name)()
            except Exception:
                pass
        return None

    @objc.python_method
    def _render_status_dot(self, presentation, tooltip):
        dot = getattr(self, "_status_dot_view", None)
        if dot is None:
            return
        try:
            dot.setToolTip_(str(tooltip or ""))
            color = self._status_dot_color(presentation.tone)
            dot_layer = dot.layer()
            if color is not None and dot_layer is not None:
                dot_layer.setBackgroundColor_(color.CGColor())
        except Exception:
            pass
        self._update_status_dot_pulse(bool(presentation.pulsing))

    @objc.python_method
    def _update_status_dot_pulse(self, pulsing):
        if bool(pulsing) and self._palette_is_visible():
            self._start_status_dot_pulse()
        else:
            self._stop_status_dot_pulse()

    @objc.python_method
    def _start_status_dot_pulse(self):
        if getattr(self, "_status_dot_pulse_timer", None) is not None:
            return
        self._status_dot_pulse_dim = False
        self._status_dot_pulse_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            STATUS_DOT_PULSE_SECONDS,
            self,
            "statusDotPulse:",
            None,
            True,
        )

    def statusDotPulse_(self, _timer):
        if not self._palette_is_visible():
            self._stop_status_dot_pulse()
            return
        dot = getattr(self, "_status_dot_view", None)
        if dot is None:
            self._stop_status_dot_pulse()
            return
        dim = not bool(getattr(self, "_status_dot_pulse_dim", False))
        self._status_dot_pulse_dim = dim
        try:
            dot.setAlphaValue_(0.35 if dim else 1.0)
        except Exception:
            pass

    @objc.python_method
    def _stop_status_dot_pulse(self):
        timer = getattr(self, "_status_dot_pulse_timer", None)
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        self._status_dot_pulse_timer = None
        self._status_dot_pulse_dim = False
        dot = getattr(self, "_status_dot_view", None)
        if dot is not None:
            try:
                dot.setAlphaValue_(1.0)
            except Exception:
                pass

    @objc.python_method
    def _palette_is_visible(self):
        try:
            if self.dialog.window() is None:
                return False
            hidden = getattr(self.dialog, "isHiddenOrHasHiddenAncestor", None)
            if callable(hidden) and hidden():
                return False
            visible = self.dialog.visibleRect()
            return float(visible.size.height) >= float(STATUS_HEIGHT - 4)
        except Exception:
            return False

    @objc.python_method
    def _start_activity_timer(self):
        if self._activity_timer is not None:
            return
        self._activity_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "activityTimer:", None, True
        )

    @objc.python_method
    def _stop_activity_timer(self):
        timer = getattr(self, "_activity_timer", None)
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        self._activity_timer = None

    def activityTimer_(self, _timer):
        self._activity_store.reconcile_orphans(
            grace_seconds=ORPHAN_GRACE_SECONDS
        )
        snapshot = self._activity_store.current(self._document_id())
        connection = self._connection_store.current()
        self._activity_snapshot = snapshot
        self._connection_snapshot = connection
        if (
            snapshot.state in ("success", "cancelled")
            and snapshot.completed_at is not None
            and snapshot.observed_at - snapshot.completed_at
            >= SUCCESS_LINGER_SECONDS
        ):
            self._activity_store.dismiss(snapshot.document_id)
            return
        if (
            snapshot.state == "error"
            and snapshot.completed_at is not None
            and snapshot.observed_at - snapshot.completed_at
            >= ERROR_LINGER_SECONDS
        ):
            self._activity_store.dismiss(snapshot.document_id)
            return
        self._render_activity(snapshot, connection)

    def cancelActivity_(self, _sender):
        snapshot = getattr(self, "_activity_snapshot", None)
        if snapshot is not None:
            self._activity_store.request_cancel(snapshot.activity_id)

    @objc.python_method
    def _document_window(self):
        try:
            return self.dialog.window()
        except Exception:
            return None

    @objc.python_method
    def _show_capsule(self, text):
        window = self._document_window()
        content = window.contentView() if window is not None else None
        if content is None:
            return
        if self._capsule is None or self._capsule.superview() is not content:
            self._hide_capsule()
            capsule = _PassThroughCapsule.alloc().initWithFrame_(
                NSMakeRect(0, 0, 280, 34)
            )
            try:
                capsule.setMaterial_(getattr(AppKit, "NSVisualEffectMaterialHUDWindow", 13))
                capsule.setBlendingMode_(getattr(AppKit, "NSVisualEffectBlendingModeWithinWindow", 0))
                capsule.setState_(getattr(AppKit, "NSVisualEffectStateActive", 1))
                capsule.setWantsLayer_(True)
                capsule.layer().setCornerRadius_(10.0)
                capsule.layer().setMasksToBounds_(True)
            except Exception:
                pass
            label = _quiet_field(NSMakeRect(12, 6, 256, 22), text, 11.0)
            try:
                label.setAlignment_(getattr(AppKit, "NSTextAlignmentCenter", 2))
                label.setTextColor_(NSColor.labelColor())
            except Exception:
                pass
            capsule.addSubview_(label)
            capsule.setAutoresizingMask_(
                NSViewMinXMargin | NSViewMaxXMargin | NSViewMinYMargin
            )
            content.addSubview_(capsule)
            self._capsule = capsule
            self._capsule_label = label
        bounds = content.bounds()
        width = min(280.0, max(180.0, float(bounds.size.width) - 24.0))
        self._capsule.setFrame_(
            NSMakeRect(
                max(12.0, (float(bounds.size.width) - width) / 2.0),
                max(12.0, float(bounds.size.height) - 46.0),
                width,
                34.0,
            )
        )
        self._capsule_label.setFrame_(NSMakeRect(12, 6, width - 24, 22))
        self._capsule_label.setStringValue_(str(text or "Working"))
        self._capsule.setHidden_(False)

    @objc.python_method
    def _hide_capsule(self):
        capsule = getattr(self, "_capsule", None)
        if capsule is not None:
            try:
                capsule.removeFromSuperview()
            except Exception:
                pass
        self._capsule = None
        self._capsule_label = None


__all__ = ["GlyphsMCPInspectorPalette", "PALETTE_NAME"]
