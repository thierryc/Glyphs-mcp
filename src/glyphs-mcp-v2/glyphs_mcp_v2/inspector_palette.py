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

from glyphs_litsquare_palette import (
    PALETTE_HEIGHT as METADATA_HEIGHT,
    GlyphsMCPLitSquareMetadataPalette,
)

from .activity import ActivitySnapshot, default_activity_store


PALETTE_NAME = "Glyphs MCP"
STATUS_HEIGHT = 38
PALETTE_HEIGHT = METADATA_HEIGHT + STATUS_HEIGHT
CAPSULE_DELAY_SECONDS = 2.0
SUCCESS_LINGER_SECONDS = 3.0


def _quiet_field(frame, text="", size=10.0):
    field = NSTextField.alloc().initWithFrame_(frame)
    field.setStringValue_(str(text or ""))
    field.setEditable_(False)
    field.setSelectable_(False)
    field.setBezeled_(False)
    field.setDrawsBackground_(False)
    field.setFont_(NSFont.systemFontOfSize_(size))
    return field


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
        metadata_view.setFrame_(NSMakeRect(0, 0, 260, METADATA_HEIGHT))

        root = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 260, PALETTE_HEIGHT))
        metadata_view.setAutoresizingMask_(NSViewWidthSizable)
        root.addSubview_(metadata_view)

        status = NSView.alloc().initWithFrame_(
            NSMakeRect(0, METADATA_HEIGHT, 260, STATUS_HEIGHT)
        )
        status.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        root.addSubview_(status)

        field = _quiet_field(NSMakeRect(10, 8, 190, 22), "Ready", 10.5)
        field.setAutoresizingMask_(NSViewWidthSizable)
        field.setToolTip_("Glyphs MCP is ready")
        status.addSubview_(field)

        cancel = NSButton.alloc().initWithFrame_(NSMakeRect(202, 7, 50, 24))
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
        self._activity_field = field
        self._cancel_button = cancel
        self._activity_store = default_activity_store()
        self._activity_snapshot = None
        self._activity_unsubscribe = None
        self._activity_timer = None
        self._capsule = None
        self._capsule_label = None

    @objc.python_method
    def start(self):
        GlyphsMCPLitSquareMetadataPalette.start(self)
        self._activity_unsubscribe = self._activity_store.subscribe(
            self._activity_changed
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
        self._stop_activity_timer()
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
        try:
            controller = self.windowController()
            document = controller.document() if controller is not None else None
            font = document.font() if document is not None else None
            if font is None:
                return None
            from .runtime import active_host

            host = active_host()
            return host.document_id_for_font(font) if host is not None else None
        except Exception:
            return None

    @objc.python_method
    def _activity_changed(self, _snapshot):
        if NSThread.isMainThread():
            self._refresh_activity()
        else:
            NSOperationQueue.mainQueue().addOperationWithBlock_(
                self._refresh_activity
            )

    @objc.python_method
    def _refresh_activity(self):
        snapshot = self._activity_store.current(self._document_id())
        self._activity_snapshot = snapshot
        self._render_activity(snapshot)
        if snapshot.active or snapshot.state in ("success", "cancelled"):
            self._start_activity_timer()
        else:
            self._stop_activity_timer()
            self._hide_capsule()

    @objc.python_method
    def _render_activity(self, snapshot: ActivitySnapshot):
        if snapshot.active:
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
            text = "Ready"
        self._activity_field.setStringValue_(text)
        self._activity_field.setToolTip_(text)
        self._cancel_button.setHidden_(
            not bool(snapshot.active and snapshot.cancellable)
        )
        try:
            if snapshot.state == "error":
                self._activity_field.setTextColor_(NSColor.systemRedColor())
            elif snapshot.active:
                self._activity_field.setTextColor_(NSColor.labelColor())
            else:
                self._activity_field.setTextColor_(NSColor.secondaryLabelColor())
        except Exception:
            pass
        if (
            snapshot.active
            and snapshot.elapsed_seconds >= CAPSULE_DELAY_SECONDS
            and not self._palette_is_visible()
        ):
            self._show_capsule(text)
        else:
            self._hide_capsule()

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
        snapshot = self._activity_store.current(self._document_id())
        self._activity_snapshot = snapshot
        if (
            snapshot.state in ("success", "cancelled")
            and snapshot.completed_at is not None
            and snapshot.observed_at - snapshot.completed_at
            >= SUCCESS_LINGER_SECONDS
        ):
            self._activity_store.dismiss(snapshot.document_id)
            return
        self._render_activity(snapshot)

    def cancelActivity_(self, _sender):
        snapshot = getattr(self, "_activity_snapshot", None)
        if snapshot is not None:
            self._activity_store.request_cancel(snapshot.activity_id)

    @objc.python_method
    def _document_window(self):
        try:
            controller = self.windowController()
            return controller.window() if controller is not None else None
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
