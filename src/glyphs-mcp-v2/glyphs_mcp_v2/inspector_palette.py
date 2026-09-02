# encoding: utf-8

"""Glyphs 4 adapter for unified MCP activity and LitSquare metadata.

The process state is supplied by :mod:`glyphs_mcp_v2.activity`; this module is
the only layer that knows about AppKit, palette visibility, or the transient
fallback capsule.
"""

from __future__ import annotations

from threading import Thread

import AppKit
import objc
from AppKit import (
    NSApp,
    NSButton,
    NSColor,
    NSFont,
    NSImage,
    NSImageOnly,
    NSMakeRect,
    NSOpenPanel,
    NSPanel,
    NSPasteboard,
    NSPopUpButton,
    NSTextField,
    NSView,
    NSViewMaxXMargin,
    NSViewMinXMargin,
    NSViewMinYMargin,
    NSViewWidthSizable,
    NSVisualEffectView,
)
from Foundation import NSBundle, NSObject, NSOperationQueue, NSThread, NSTimer

import glyphs_litsquare_palette as _metadata_palette
from glyphs_litsquare_palette import GlyphsMCPLitSquareMetadataPalette
from i18n import tr

from .activity import ActivitySnapshot, default_activity_store
from .connection_status import (
    TRANSITIONAL_CONNECTION_STATES,
    ConnectionStatusSnapshot,
    default_connection_status_store,
    indicator_presentation,
)
from .comparison_reference import default_comparison_reference_service
from .comparison_reference_ui import (
    REFERENCE_KINDS,
    REFERENCE_LABELS,
    initial_reference_drafts,
    reference_form_presentation,
    reference_presentation,
    reference_spec_from_draft,
    unavailable_reference_presentation,
)
from .versions import palette_display_name


# Glyphs owns the native palette header and accepts one plain string only. A
# middle dot plus a parenthetical Glyphs build keeps both runtime identifiers
# compact without depending on private sidebar view hierarchy or hard-coding.
PALETTE_NAME = palette_display_name(
    NSBundle.mainBundle().objectForInfoDictionaryKey_("CFBundleVersion")
)
COMPACT_METADATA_HEIGHT = 190
STATUS_HEIGHT = 28
REFERENCE_PALETTE_HEIGHT = 52
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


def _symbol_button(frame, symbol_name, label, fallback, target, action):
    button = NSButton.alloc().initWithFrame_(frame)
    button.setTitle_("")
    image = None
    factory = getattr(
        NSImage, "imageWithSystemSymbolName_accessibilityDescription_", None
    )
    if callable(factory):
        try:
            image = factory(symbol_name, label)
        except Exception:
            image = None
    if image is not None:
        try:
            image.setTemplate_(True)
        except Exception:
            pass
        button.setImage_(image)
        button.setImagePosition_(NSImageOnly)
    else:
        button.setTitle_(fallback)
    button.setBordered_(False)
    button.setToolTip_(label)
    try:
        button.setAccessibilityLabel_(label)
    except Exception:
        pass
    button.setTarget_(target)
    button.setAction_(action)
    return button


def _set_placeholder(field, value):
    try:
        field.cell().setPlaceholderString_(str(value or ""))
    except Exception:
        pass


def _set_accessibility_description(control, value):
    try:
        control.setAccessibilityHelp_(str(value or ""))
    except Exception:
        try:
            control.setAccessibilityValue_(str(value or ""))
        except Exception:
            pass


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


class ComparisonReferenceSheetController(NSObject):
    """Small source-conditional sheet retained by its Palette owner."""

    WIDTH = 420.0

    @objc.python_method
    def _configure(self, owner, spec, drafts):
        self._owner = owner
        current = dict(spec or {"kind": "last_saved"})
        self._kind = str(current.get("kind") or "last_saved")
        if self._kind not in REFERENCE_KINDS:
            self._kind = "last_saved"
        self._drafts = initial_reference_drafts(current)
        for kind, value in dict(drafts or {}).items():
            if kind in self._drafts and isinstance(value, dict):
                self._drafts[kind].update(
                    {key: str(item or "") for key, item in value.items()}
                )
        self._advanced = False

        style = getattr(AppKit, "NSWindowStyleMaskTitled", 1)
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, self.WIDTH, 146),
            style,
            getattr(AppKit, "NSBackingStoreBuffered", 2),
            False,
        )
        self.panel.setTitle_("Comparison Reference")
        self.panel.setReleasedWhenClosed_(False)
        content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, self.WIDTH, 146))
        self.panel.setContentView_(content)
        self._content = content

        self._source_label = _quiet_field(NSMakeRect(20, 0, 104, 22), "Compare against:", 10.5)
        content.addSubview_(self._source_label)
        self._source_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(126, 0, 274, 24), False
        )
        self._source_popup.addItemsWithTitles_(
            [REFERENCE_LABELS[kind] for kind in REFERENCE_KINDS]
        )
        self._source_popup.selectItemAtIndex_(REFERENCE_KINDS.index(self._kind))
        self._source_popup.setTarget_(self)
        self._source_popup.setAction_("sourceChanged:")
        content.addSubview_(self._source_popup)

        self._explanation = _quiet_field(NSMakeRect(20, 0, 380, 30), "", 9.5)
        try:
            self._explanation.setLineBreakMode_(getattr(AppKit, "NSLineBreakByWordWrapping", 0))
            self._explanation.setMaximumNumberOfLines_(2)
        except Exception:
            pass
        content.addSubview_(self._explanation)

        self._repository_label = _quiet_field(NSMakeRect(20, 0, 96, 22), "Repository", 10.0)
        self._repository = NSTextField.alloc().initWithFrame_(NSMakeRect(126, 0, 198, 22))
        self._repository.setDelegate_(self)
        self._choose = NSButton.alloc().initWithFrame_(NSMakeRect(330, 0, 70, 24))
        self._choose.setTitle_("Choose…")
        self._choose.setBezelStyle_(getattr(AppKit, "NSBezelStyleRounded", 1))
        self._choose.setTarget_(self)
        self._choose.setAction_("chooseRepository:")
        for control in (self._repository_label, self._repository, self._choose):
            content.addSubview_(control)

        self._revision_label = _quiet_field(NSMakeRect(20, 0, 96, 22), "Revision", 10.0)
        self._revision = NSTextField.alloc().initWithFrame_(NSMakeRect(126, 0, 274, 22))
        self._revision.setDelegate_(self)
        content.addSubview_(self._revision_label)
        content.addSubview_(self._revision)

        self._advanced_button = NSButton.alloc().initWithFrame_(NSMakeRect(18, 0, 18, 18))
        self._advanced_button.setTitle_("")
        self._advanced_button.setButtonType_(
            getattr(AppKit, "NSButtonTypePushOnPushOff", 1)
        )
        self._advanced_button.setBezelStyle_(
            getattr(AppKit, "NSBezelStyleDisclosure", 5)
        )
        self._advanced_button.setTarget_(self)
        self._advanced_button.setAction_("advancedChanged:")
        try:
            self._advanced_button.setAccessibilityLabel_("Advanced Options")
        except Exception:
            pass
        content.addSubview_(self._advanced_button)
        self._advanced_label = _quiet_field(
            NSMakeRect(40, 0, 160, 18), "Advanced Options", 9.5
        )
        content.addSubview_(self._advanced_label)

        self._font_path_label = _quiet_field(NSMakeRect(20, 0, 96, 22), "Font Path", 10.0)
        self._font_path = NSTextField.alloc().initWithFrame_(NSMakeRect(126, 0, 274, 22))
        self._font_path.setDelegate_(self)
        _set_placeholder(self._font_path, "repository-relative .glyphs or .glyphspackage")
        content.addSubview_(self._font_path_label)
        content.addSubview_(self._font_path)

        self._validation = _quiet_field(NSMakeRect(20, 0, 380, 16), "", 9.0)
        try:
            self._validation.setTextColor_(NSColor.systemRedColor())
        except Exception:
            pass
        content.addSubview_(self._validation)

        self._cancel = NSButton.alloc().initWithFrame_(NSMakeRect(246, 8, 74, 26))
        self._cancel.setTitle_("Cancel")
        self._cancel.setBezelStyle_(getattr(AppKit, "NSBezelStyleRounded", 1))
        self._cancel.setTarget_(self)
        self._cancel.setAction_("cancel:")
        try:
            self._cancel.setKeyEquivalent_("\x1b")
        except Exception:
            pass
        content.addSubview_(self._cancel)

        self._primary = NSButton.alloc().initWithFrame_(NSMakeRect(326, 8, 74, 26))
        self._primary.setBezelStyle_(getattr(AppKit, "NSBezelStyleRounded", 1))
        self._primary.setTarget_(self)
        self._primary.setAction_("submit:")
        try:
            self._primary.setKeyEquivalent_("\r")
        except Exception:
            pass
        content.addSubview_(self._primary)

        self._load_draft()
        self._layout(False)
        try:
            self.panel.setInitialFirstResponder_(self._source_popup)
        except Exception:
            pass

    @objc.python_method
    def _save_current_draft(self):
        if self._kind not in {"local_git", "github"}:
            return
        self._drafts[self._kind] = {
            "repository": str(self._repository.stringValue()).strip(),
            "revision": str(self._revision.stringValue()).strip(),
            "fontPath": str(self._font_path.stringValue()).strip(),
        }

    @objc.python_method
    def _load_draft(self):
        draft = self._drafts.get(self._kind, {})
        self._repository.setStringValue_(str(draft.get("repository") or ""))
        self._revision.setStringValue_(str(draft.get("revision") or ""))
        self._font_path.setStringValue_(str(draft.get("fontPath") or ""))

    @objc.python_method
    def _current_form(self):
        self._save_current_draft()
        return reference_form_presentation(
            self._kind,
            self._drafts.get(self._kind, {}),
            advanced=self._advanced,
        )

    @objc.python_method
    def _resize(self, height, animate):
        old = self.panel.frame()
        target = self.panel.frameRectForContentRect_(
            NSMakeRect(0, 0, self.WIDTH, float(height))
        )
        if float(old.size.height) > 0:
            target = NSMakeRect(
                float(old.origin.x),
                float(old.origin.y) + float(old.size.height) - float(target.size.height),
                float(target.size.width),
                float(target.size.height),
            )
        try:
            self.panel.setFrame_display_animate_(target, True, bool(animate))
        except Exception:
            self.panel.setFrame_display_(target, True)
        self._content.setFrame_(NSMakeRect(0, 0, self.WIDTH, float(height)))

    @objc.python_method
    def _layout(self, animate):
        form = self._current_form()
        height = float(form.sheet_height)
        self._resize(height, animate)

        self._source_label.setFrame_(NSMakeRect(20, height - 40, 104, 22))
        self._source_popup.setFrame_(NSMakeRect(126, height - 41, 274, 24))
        self._explanation.setFrame_(NSMakeRect(20, height - 75, 380, 30))
        self._explanation.setStringValue_(form.explanation)

        self._repository_label.setFrame_(NSMakeRect(20, height - 105, 96, 22))
        repository_width = 198 if self._kind == "local_git" else 274
        self._repository.setFrame_(
            NSMakeRect(126, height - 106, repository_width, 22)
        )
        self._choose.setFrame_(NSMakeRect(330, height - 107, 70, 24))
        self._revision_label.setFrame_(NSMakeRect(20, height - 137, 96, 22))
        self._revision.setFrame_(NSMakeRect(126, height - 138, 274, 22))
        self._advanced_button.setFrame_(NSMakeRect(18, height - 164, 18, 18))
        self._advanced_label.setFrame_(NSMakeRect(40, height - 164, 160, 18))
        self._font_path_label.setFrame_(NSMakeRect(20, height - 201, 96, 22))
        self._font_path.setFrame_(NSMakeRect(126, height - 202, 274, 22))
        self._validation.setFrame_(NSMakeRect(20, 39, 380, 16))

        for control in (self._repository_label, self._repository, self._choose):
            control.setHidden_(not form.show_repository)
        self._revision_label.setHidden_(not form.show_revision)
        self._revision.setHidden_(not form.show_revision)
        self._advanced_button.setHidden_(not form.show_advanced)
        self._advanced_label.setHidden_(not form.show_advanced)
        self._font_path_label.setHidden_(not form.show_font_path)
        self._font_path.setHidden_(not form.show_font_path)
        self._choose.setHidden_(self._kind != "local_git")

        _set_placeholder(self._repository, form.repository_placeholder)
        _set_placeholder(self._revision, form.revision_placeholder)
        self._validation.setStringValue_(form.validation_message)
        self._validation.setHidden_(not bool(form.validation_message))
        self._primary.setTitle_(form.action_title)
        self._primary.setEnabled_(form.action_enabled)
        primary_width = 112.0 if self._kind == "last_saved" else 96.0
        self._primary.setFrame_(NSMakeRect(self.WIDTH - 20 - primary_width, 8, primary_width, 26))
        self._cancel.setFrame_(NSMakeRect(self.WIDTH - 26 - primary_width - 74, 8, 74, 26))

    def sourceChanged_(self, sender):
        self._save_current_draft()
        index = max(0, min(int(sender.indexOfSelectedItem()), len(REFERENCE_KINDS) - 1))
        self._kind = REFERENCE_KINDS[index]
        self._advanced = False
        self._advanced_button.setState_(0)
        self._load_draft()
        self._layout(True)

    def advancedChanged_(self, sender):
        self._advanced = bool(int(sender.state()))
        self._layout(True)

    def controlTextDidChange_(self, _notification):
        form = self._current_form()
        self._validation.setStringValue_(form.validation_message)
        self._validation.setHidden_(not bool(form.validation_message))
        self._primary.setEnabled_(form.action_enabled)

    def chooseRepository_(self, _sender):
        chooser = NSOpenPanel.openPanel()
        chooser.setCanChooseDirectories_(True)
        chooser.setCanChooseFiles_(False)
        chooser.setAllowsMultipleSelection_(False)
        chooser.setPrompt_("Choose Repository")

        def complete(response):
            if int(response) != int(getattr(AppKit, "NSModalResponseOK", 1)):
                return
            urls = chooser.URLs()
            if urls:
                path = urls[0].path()
                self._repository.setStringValue_(str(path or ""))
                self.controlTextDidChange_(None)

        chooser.beginSheetModalForWindow_completionHandler_(self.panel, complete)

    @objc.python_method
    def _close(self):
        parent = self.panel.sheetParent()
        if parent is not None:
            parent.endSheet_(self.panel)
        else:
            try:
                NSApp.abortModal()
            except Exception:
                pass
            self.panel.orderOut_(None)

    def cancel_(self, _sender):
        self._close()

    def submit_(self, _sender):
        self._save_current_draft()
        try:
            spec = reference_spec_from_draft(
                self._kind, self._drafts.get(self._kind, {})
            )
        except Exception as error:
            self._validation.setStringValue_(str(error))
            self._validation.setHidden_(False)
            return
        owner = self._owner
        drafts = {kind: dict(value) for kind, value in self._drafts.items()}
        self._close()
        owner._submit_reference_spec(spec, drafts)

    @objc.python_method
    def present(self, window):
        if window is not None:
            window.beginSheet_completionHandler_(self.panel, self._sheet_completed)
        else:
            self.panel.center()
            self.panel.makeKeyAndOrderFront_(None)
            NSApp.runModalForWindow_(self.panel)

    @objc.python_method
    def _sheet_completed(self, _response):
        owner = getattr(self, "_owner", None)
        if owner is not None and getattr(owner, "_reference_sheet", None) is self:
            owner._reference_sheet = None


class GlyphsMCPComparisonReferencePalette(_metadata_palette.PalettePlugin):
    """Compact, document-bound comparison source in its own native section."""

    @objc.python_method
    def settings(self):
        self.name = "Comparison Reference"
        self.sortId = 71
        self.min = REFERENCE_PALETTE_HEIGHT
        self.max = REFERENCE_PALETTE_HEIGHT
        self.dialog = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, 260, REFERENCE_PALETTE_HEIGHT)
        )
        try:
            self.dialog.setController_(self)
        except Exception:
            pass

        self._reference_primary = _quiet_field(NSMakeRect(8, 28, 172, 18), "Last Saved", 10.5)
        self._reference_secondary = _quiet_field(NSMakeRect(8, 6, 190, 17), "", 9.0)
        for field in (self._reference_primary, self._reference_secondary):
            field.setAutoresizingMask_(NSViewWidthSizable)
            try:
                field.setLineBreakMode_(getattr(AppKit, "NSLineBreakByTruncatingMiddle", 5))
                field.setUsesSingleLineMode_(True)
            except Exception:
                pass
            self.dialog.addSubview_(field)

        self._reference_change_button = NSButton.alloc().initWithFrame_(
            NSMakeRect(186, 25, 66, 24)
        )
        self._reference_change_button.setTitle_("Change…")
        self._reference_change_button.setBezelStyle_(
            getattr(AppKit, "NSBezelStyleInline", 15)
        )
        self._reference_change_button.setFont_(NSFont.systemFontOfSize_(9.0))
        self._reference_change_button.setTarget_(self)
        self._reference_change_button.setAction_("configureComparisonReference:")
        self._reference_change_button.setAutoresizingMask_(NSViewMinXMargin)
        self.dialog.addSubview_(self._reference_change_button)

        self._reference_copy_button = _symbol_button(
            NSMakeRect(202, 1, 24, 24),
            "doc.on.doc",
            "Copy full commit SHA",
            "⧉",
            self,
            "copyComparisonSHA:",
        )
        self._reference_refresh_button = _symbol_button(
            NSMakeRect(228, 1, 24, 24),
            "arrow.clockwise",
            "Refresh comparison reference",
            "↻",
            self,
            "refreshComparisonReference:",
        )
        for button in (self._reference_copy_button, self._reference_refresh_button):
            button.setAutoresizingMask_(NSViewMinXMargin)
            self.dialog.addSubview_(button)

        self._reference_store = default_comparison_reference_service()
        self._reference_unsubscribe = None
        self._callbacks = []
        self._reference_refresh_pending = False
        self._reference_sha = None
        self._reference_spec = {"kind": "last_saved"}
        self._reference_drafts = initial_reference_drafts(self._reference_spec)
        self._reference_last_ui_error = None
        self._reference_failed_spec = None
        self._reference_sheet = None
        self._reference_document_id = None
        self._reference_window = None
        self._last_reference_public = None
        self._reference_request_serial = 0
        self._render_reference(
            reference_presentation(
                {
                    "state": "ready",
                    "reference": self._reference_spec,
                    "resolved": None,
                    "origin": "default",
                }
            )
        )

    @objc.python_method
    def start(self):
        self._reference_unsubscribe = self._reference_store.subscribe(
            self._reference_changed
        )
        for event in (
            _metadata_palette.UPDATEINTERFACE,
            _metadata_palette.DOCUMENTOPENED,
            _metadata_palette.DOCUMENTACTIVATED,
            _metadata_palette.DOCUMENTWILLCLOSE,
        ):
            _metadata_palette.Glyphs.addCallback(self.update, event)
            self._callbacks.append((self.update, event))
        self._schedule_reference_refresh()

    @objc.python_method
    def __del__(self):
        sheet = getattr(self, "_reference_sheet", None)
        if sheet is not None:
            try:
                sheet._close()
            except Exception:
                pass
            self._reference_sheet = None
        for callback, event in getattr(self, "_callbacks", []):
            try:
                _metadata_palette.Glyphs.removeCallback(callback, event)
            except TypeError:
                try:
                    _metadata_palette.Glyphs.removeCallback(callback)
                except Exception:
                    pass
            except Exception:
                pass
        self._callbacks = []
        unsubscribe = getattr(self, "_reference_unsubscribe", None)
        if unsubscribe is not None:
            try:
                unsubscribe()
            except Exception:
                pass
        self._reference_unsubscribe = None

    def minHeight(self):
        return REFERENCE_PALETTE_HEIGHT

    def maxHeight(self):
        return REFERENCE_PALETTE_HEIGHT

    @objc.python_method
    def update(self, _sender):
        self._schedule_reference_refresh()

    @objc.python_method
    def _schedule_reference_refresh(self):
        if self._reference_refresh_pending:
            return
        self._reference_refresh_pending = True

        def refresh():
            self._reference_refresh_pending = False
            self._refresh_reference_card()

        NSOperationQueue.mainQueue().addOperationWithBlock_(refresh)

    @objc.python_method
    def _reference_changed(self, _update):
        if NSThread.isMainThread():
            self._schedule_reference_refresh()
        else:
            NSOperationQueue.mainQueue().addOperationWithBlock_(
                self._schedule_reference_refresh
            )

    @objc.python_method
    def _document_id(self):
        window = self.dialog.window()
        if window is None:
            self._reference_document_id = None
            self._reference_window = None
            return None
        if window is not self._reference_window:
            self._reference_document_id = None
            self._reference_window = window
        try:
            controller = _native_value(getattr(self, "windowController", None))
            document = _native_value(getattr(controller, "document", None))
            font = _native_value(getattr(document, "font", None))
            if font is None:
                font = _font_from_window(window)
            if font is not None:
                from .runtime import active_host

                host = active_host()
                if host is not None:
                    self._reference_document_id = host.document_id_for_font(font)
        except Exception:
            pass
        return self._reference_document_id

    @objc.python_method
    def _refresh_reference_card(self):
        document_id = self._document_id()
        if not document_id:
            self._render_reference(
                unavailable_reference_presentation("No active font document")
            )
            return
        try:
            from .runtime import active_host

            host = active_host()
            if host is None:
                raise RuntimeError("Glyphs MCP is not running")
            source_path = host.source_path_for_document(document_id)
            native_identity = host.comparison_reference_identity_for_document(
                document_id
            )
            self._reference_store.bind_document(
                document_id,
                source_path=source_path,
                native_identity=native_identity,
            )
            status = self._reference_store.status_for_document(document_id)
        except Exception as error:
            self._render_reference(unavailable_reference_presentation(str(error)))
            return
        if status is None:
            self._render_reference(
                unavailable_reference_presentation("Reference state unavailable")
            )
            return
        public = status.to_dict()
        if (
            self._reference_last_ui_error
            and public.get("error") is None
            and public.get("state") in {"ready", "stale_cached"}
        ):
            self._reference_last_ui_error = None
        self._last_reference_public = public
        self._reference_spec = dict(
            public.get("reference") or {"kind": "last_saved"}
        )
        if not self._reference_last_ui_error:
            self._reference_drafts = initial_reference_drafts(self._reference_spec)
            self._reference_failed_spec = None
        self._render_reference(
            reference_presentation(
                public,
                ui_error=self._reference_last_ui_error,
            )
        )

    @objc.python_method
    def _render_reference(self, presentation):
        self._reference_primary.setStringValue_(presentation.primary)
        self._reference_primary.setToolTip_(presentation.tooltip)
        self._reference_secondary.setStringValue_(presentation.secondary)
        self._reference_secondary.setToolTip_(presentation.tooltip)
        _set_accessibility_description(
            self._reference_primary, presentation.accessibility_description
        )

        is_last_saved = presentation.kind == "last_saved" and not presentation.secondary
        if is_last_saved:
            self._reference_primary.setFrame_(NSMakeRect(8, 17, 172, 18))
            self._reference_change_button.setFrame_(NSMakeRect(186, 14, 66, 24))
        else:
            self._reference_primary.setFrame_(NSMakeRect(8, 28, 172, 18))
            self._reference_change_button.setFrame_(NSMakeRect(186, 25, 66, 24))
        self._reference_secondary.setHidden_(not bool(presentation.secondary))
        self._reference_refresh_button.setHidden_(not presentation.show_refresh)
        self._reference_copy_button.setHidden_(not presentation.show_copy)
        self._reference_sha = presentation.resolved_commit

        right = 252.0
        if presentation.show_refresh:
            right = min(right, 228.0)
        if presentation.show_copy:
            right = min(right, 202.0)
        self._reference_secondary.setFrame_(
            NSMakeRect(8, 6, max(80.0, right - 12.0), 17)
        )

    @objc.python_method
    def _render_pending(self, reference, refreshing):
        prior = dict(self._last_reference_public or {})
        prior["state"] = "refreshing" if refreshing else "resolving"
        prior["reference"] = dict(reference or self._reference_spec)
        if not refreshing:
            prior["resolved"] = None
        prior["error"] = None
        self._render_reference(reference_presentation(prior))

    @objc.python_method
    def _invoke_document_view_configuration(self, arguments, pending_reference=None):
        document_id = self._document_id()
        if not document_id:
            self._reference_last_ui_error = "No active font document"
            self._refresh_reference_card()
            return
        values = {
            "documentId": document_id,
            "_configurationOrigin": "sidebar",
            **dict(arguments),
        }
        refreshing = bool(arguments.get("refreshComparisonReference"))
        attempted_spec = dict(pending_reference or self._reference_spec)
        self._reference_request_serial += 1
        request_serial = self._reference_request_serial
        self._reference_last_ui_error = None
        self._render_pending(attempted_spec, refreshing)

        def work():
            try:
                from .runtime import active_application

                application = active_application()
                if application is None:
                    raise RuntimeError("Glyphs MCP is not running")
                response = application.invoke("configure_document_view", values)
                payload = response.to_dict()
                error = payload.get("error")
                message = (
                    str(error.get("message") or "Configuration failed")
                    if isinstance(error, dict)
                    else None
                )
            except Exception as error:
                message = str(error)

            def completed():
                if request_serial != self._reference_request_serial:
                    return
                if self._document_id() != document_id:
                    self._schedule_reference_refresh()
                    return
                self._reference_last_ui_error = message
                self._reference_failed_spec = attempted_spec if message else None
                self._refresh_reference_card()

            NSOperationQueue.mainQueue().addOperationWithBlock_(completed)

        Thread(target=work, name="glyphs-mcp-reference-ui", daemon=True).start()

    @objc.python_method
    def _submit_reference_spec(self, spec, drafts):
        self._reference_drafts = {
            kind: dict(value) for kind, value in dict(drafts or {}).items()
        }
        self._reference_spec = dict(spec)
        self._invoke_document_view_configuration(
            {"comparisonReference": dict(spec)},
            pending_reference=spec,
        )

    def refreshComparisonReference_(self, _sender):
        self._invoke_document_view_configuration(
            {"refreshComparisonReference": True},
            pending_reference=self._reference_spec,
        )

    def copyComparisonSHA_(self, _sender):
        sha = getattr(self, "_reference_sha", None)
        if not sha:
            return
        try:
            pasteboard = NSPasteboard.generalPasteboard()
            pasteboard.clearContents()
            pasteboard.writeObjects_([str(sha)])
        except Exception:
            pass

    def configureComparisonReference_(self, _sender):
        if self._reference_sheet is not None:
            try:
                self._reference_sheet.panel.makeKeyAndOrderFront_(None)
            except Exception:
                pass
            return
        spec = self._reference_failed_spec or self._reference_spec
        drafts = self._reference_drafts
        if not drafts:
            drafts = initial_reference_drafts(spec)
        controller = ComparisonReferenceSheetController.alloc().init()
        controller._configure(self, spec, drafts)
        self._reference_sheet = controller
        controller.present(self.dialog.window())


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


__all__ = [
    "GlyphsMCPComparisonReferencePalette",
    "GlyphsMCPInspectorPalette",
    "PALETTE_NAME",
]
