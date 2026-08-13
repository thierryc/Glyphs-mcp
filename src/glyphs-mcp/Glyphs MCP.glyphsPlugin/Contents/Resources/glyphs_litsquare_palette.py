# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Compact LitSquare metadata Palette for Glyphs 3 and Glyphs 4."""

import objc
from AppKit import (
    NSAlert,
    NSButton,
    NSColor,
    NSFont,
    NSImage,
    NSImageOnly,
    NSMakeRect,
    NSPasteboard,
    NSPasteboardTypeString,
    NSScrollView,
    NSSegmentedControl,
    NSTextField,
    NSTextView,
    NSView,
    NSViewHeightSizable,
    NSViewMinYMargin,
    NSViewWidthSizable,
)
from Foundation import NSNotificationCenter, NSOperationQueue
from GlyphsApp import (
    DOCUMENTACTIVATED,
    DOCUMENTOPENED,
    DOCUMENTWILLCLOSE,
    Glyphs,
    UPDATEINTERFACE,
)
from GlyphsApp.plugins import PalettePlugin

from glyphs_litsquare_adapter import (
    INSPECTOR_NAME,
    METADATA_CHANGED_NOTIFICATION,
    full_metadata_selection_snapshot,
    metadata_selection_snapshot,
    replace_metadata_selection_transaction,
    selected_path_snapshot,
    set_path_roles_transaction,
)
from litsquare_metadata import canonical_json, parse_metadata_json, parse_path_role_json


PALETTE_NAME = INSPECTOR_NAME
PALETTE_HEIGHT = 215
_SCOPES = ("font", "glyph", "layer", "paths")
_MIXED_VALUE = "mixedvalue"
_HELP_TEXT = (
    "This advanced inspector reads and edits LitSquare metadata stored directly "
    "in the current Glyphs font.\n\n"
    "Font, Glyph, and Layer show the direct userData[\"com.litsquare\"] "
    "dictionary at that level. Values are not copied between levels. Paths show "
    "the selected paths' attributes[\"com.litsquare.role\"] value as JSON.\n\n"
    "Blank means unset. mixedvalue means the selected objects have different "
    "values. Valid JSON is applied when the editor loses focus; invalid JSON is "
    "not written.\n\n"
    "The text-and-magnifying-glass button switches the active tab to a read-only "
    "view of complete native userData or selected-path attributes. This may "
    "include data owned by Glyphs or other plug-ins. Copy exports the visible "
    "JSON projection.\n\n"
    "Changes are undoable and this inspector never saves the font automatically."
)


def _value(value):
    return value() if callable(value) else value


def _label(frame, text=""):
    control = NSTextField.alloc().initWithFrame_(frame)
    control.setEditable_(False)
    control.setSelectable_(False)
    control.setBezeled_(False)
    control.setDrawsBackground_(False)
    control.setStringValue_(text)
    return control


def _color(selector, fallback):
    method = getattr(NSColor, selector, None)
    if callable(method):
        try:
            return method()
        except Exception:
            pass
    return fallback()


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


class GlyphsMCPLitSquareMetadataPalette(PalettePlugin):
    """Document-bound JSON editor for direct LitSquare domains."""

    @objc.python_method
    def settings(self):
        self.name = PALETTE_NAME
        self.sortId = 72
        self._snapshot_fingerprint = None
        self._copy_text = ""
        self._callbacks = []
        self._refresh_pending = False
        self._editor_scope = "font"
        self._editor_targets = []
        self._editor_baseline = ""
        self._editor_native_info = ""
        self._editor_native_info_error = False
        self._editor_dirty = False
        self._editor_mixed = False
        self._editor_programmatic = False
        self._editor_commit_in_progress = False
        self._inspect_all_metadata = False

        self.min = PALETTE_HEIGHT
        self.max = PALETTE_HEIGHT
        self.dialog = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, 260, PALETTE_HEIGHT)
        )
        try:
            self.dialog.setController_(self)
        except Exception:
            pass

        self.scopeControl = NSSegmentedControl.alloc().initWithFrame_(
            NSMakeRect(8, 185, 244, 22)
        )
        self.scopeControl.setSegmentCount_(4)
        for index, title in enumerate(("Font", "Glyph", "Layer", "Paths")):
            self.scopeControl.setLabel_forSegment_(title, index)
        self.scopeControl.setSelectedSegment_(0)
        self.scopeControl.setTarget_(self)
        self.scopeControl.setAction_("scopeChanged:")
        self.scopeControl.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        self.dialog.addSubview_(self.scopeControl)

        self.scrollView = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(8, 39, 244, 138)
        )
        self.scrollView.setHasVerticalScroller_(True)
        self.scrollView.setHasHorizontalScroller_(True)
        self.scrollView.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.textView = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 240, 134))
        self.textView.setEditable_(True)
        self.textView.setSelectable_(True)
        self.textView.setRichText_(False)
        self.textView.setDelegate_(self)
        self.textView.setFont_(NSFont.userFixedPitchFontOfSize_(10.0))
        self.textView.setString_("")
        self.scrollView.setDocumentView_(self.textView)
        self.dialog.addSubview_(self.scrollView)

        self.infoLabel = _label(NSMakeRect(8, 8, 128, 22))
        self.infoLabel.setFont_(NSFont.systemFontOfSize_(9.0))
        self.infoLabel.setAutoresizingMask_(
            NSViewWidthSizable | NSViewMinYMargin
        )
        self.dialog.addSubview_(self.infoLabel)

        self.inspectButton = _symbol_button(
            NSMakeRect(144, 7, 24, 24),
            "text.magnifyingglass",
            "Inspect All Metadata",
            "⌕",
            self,
            "toggleAllMetadata:",
        )
        self.dialog.addSubview_(self.inspectButton)
        self._update_inspect_button()

        self.helpButton = _symbol_button(
            NSMakeRect(172, 7, 24, 24),
            "info.circle",
            "Inspector Help",
            "ⓘ",
            self,
            "showHelp:",
        )
        self.dialog.addSubview_(self.helpButton)

        self.copyButton = _symbol_button(
            NSMakeRect(200, 7, 24, 24),
            "doc.on.doc",
            "Copy",
            "⧉",
            self,
            "copy:",
        )
        self.dialog.addSubview_(self.copyButton)

        self.refreshButton = _symbol_button(
            NSMakeRect(228, 7, 24, 24),
            "arrow.clockwise",
            "Refresh",
            "↻",
            self,
            "refresh:",
        )
        self.dialog.addSubview_(self.refreshButton)

    @objc.python_method
    def start(self):
        for event in (
            UPDATEINTERFACE,
            DOCUMENTOPENED,
            DOCUMENTACTIVATED,
            DOCUMENTWILLCLOSE,
        ):
            Glyphs.addCallback(self.update, event)
            self._callbacks.append((self.update, event))
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, "metadataDidChange:", METADATA_CHANGED_NOTIFICATION, None
        )
        self._schedule_refresh()

    @objc.python_method
    def __del__(self):
        for callback, event in getattr(self, "_callbacks", []):
            try:
                Glyphs.removeCallback(callback, event)
            except TypeError:
                try:
                    Glyphs.removeCallback(callback)
                except Exception:
                    pass
            except Exception:
                pass
        try:
            NSNotificationCenter.defaultCenter().removeObserver_name_object_(
                self, METADATA_CHANGED_NOTIFICATION, None
            )
        except Exception:
            pass

    def minHeight(self):
        return PALETTE_HEIGHT

    def maxHeight(self):
        return PALETTE_HEIGHT

    @objc.python_method
    def update(self, sender):
        self._schedule_refresh()

    def metadataDidChange_(self, notification):
        self._schedule_refresh()

    def scopeChanged_(self, sender):
        if self._editor_dirty:
            if not self._commit_editor_text(
                self._editor_scope, str(self.textView.string())
            ):
                try:
                    self.scopeControl.setSelectedSegment_(
                        _SCOPES.index(self._editor_scope)
                    )
                except Exception:
                    pass
                return
        self._snapshot_fingerprint = None
        self._refresh()

    def refresh_(self, sender):
        self._snapshot_fingerprint = None
        self._refresh()

    def copy_(self, sender):
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(
            self._copy_text or "", NSPasteboardTypeString
        )

    def showHelp_(self, sender):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(PALETTE_NAME)
        alert.setInformativeText_(_HELP_TEXT)
        alert.addButtonWithTitle_("OK")
        alert.runModal()

    def toggleAllMetadata_(self, sender):
        if not self._inspect_all_metadata and self._editor_dirty:
            if not self._commit_editor_text(
                self._editor_scope, str(self.textView.string())
            ):
                return
        self._inspect_all_metadata = not self._inspect_all_metadata
        self._update_inspect_button()
        self._snapshot_fingerprint = None
        self._refresh()

    def textDidBeginEditing_(self, notification):
        try:
            if notification.object() != self.textView:
                return
        except Exception:
            return
        if self._editor_mixed:
            try:
                self.textView.selectAll_(None)
            except Exception:
                pass

    def textDidChange_(self, notification):
        if self._editor_programmatic or self._inspect_all_metadata:
            return
        try:
            if notification.object() != self.textView:
                return
        except Exception:
            return
        text = str(self.textView.string())
        self._copy_text = text
        self._editor_dirty = text != self._editor_baseline
        self.textView.setTextColor_(
            _color("controlTextColor", NSColor.blackColor)
        )
        if not self._editor_dirty:
            self._set_info(
                self._editor_native_info, self._editor_native_info_error
            )
            if self._editor_mixed:
                self.textView.setTextColor_(
                    _color("secondaryLabelColor", NSColor.disabledControlTextColor)
                )
            return
        try:
            self._parse_editor_text(self._editor_scope, text)
            self._set_info("Valid JSON")
        except Exception:
            self._set_info("Invalid JSON", error=True)

    def textDidEndEditing_(self, notification):
        try:
            if notification.object() != self.textView:
                return
        except Exception:
            return
        if (
            self._inspect_all_metadata
            or self._editor_commit_in_progress
            or not self._editor_dirty
        ):
            return
        self._commit_editor_text(self._editor_scope, str(self.textView.string()))

    def textView_doCommandBySelector_(self, text_view, command_selector):
        if text_view != self.textView or str(command_selector) != "cancelOperation:":
            return False
        self._editor_programmatic = True
        try:
            self.textView.setString_(self._editor_baseline)
            self.textView.setTextColor_(
                _color("secondaryLabelColor", NSColor.disabledControlTextColor)
                if self._editor_mixed
                else _color("controlTextColor", NSColor.blackColor)
            )
        finally:
            self._editor_programmatic = False
        self._copy_text = self._editor_baseline
        self._editor_dirty = False
        self._set_info(self._editor_native_info, self._editor_native_info_error)
        return True

    @objc.python_method
    def _parse_editor_text(self, scope, text):
        if scope == "paths":
            return parse_path_role_json(text)
        return parse_metadata_json(text)[0]

    @objc.python_method
    def _commit_editor_text(self, scope, text):
        if self._inspect_all_metadata:
            return False
        try:
            native = self._parse_editor_text(scope, text)
        except Exception:
            self._set_info("Invalid JSON", error=True)
            return False
        if not self._editor_targets:
            return False
        self._editor_commit_in_progress = True
        try:
            if scope == "paths":
                result = set_path_roles_transaction(
                    [dict(target) for target in self._editor_targets],
                    role=native,
                    dry_run=False,
                    confirm=True,
                    font=self._font(),
                )
            else:
                result = replace_metadata_selection_transaction(
                    scope,
                    [dict(target) for target in self._editor_targets],
                    native,
                    font=self._font(),
                )
            if not result.get("ok"):
                error = result.get("error")
                if isinstance(error, dict):
                    error = error.get("message")
                raise ValueError(error or "The value could not be changed.")
            self._editor_dirty = False
            self._set_info("Valid JSON")
            self._snapshot_fingerprint = None
            self._refresh()
            return True
        except Exception as exc:
            message = str(exc or "Invalid input")
            self._set_info(
                "Invalid JSON" if message.startswith("Invalid input") else message,
                error=True,
            )
            return False
        finally:
            self._editor_commit_in_progress = False

    @objc.python_method
    def _set_info(self, message, error=False):
        message = str(message or "")
        self.infoLabel.setStringValue_(message)
        self.infoLabel.setTextColor_(
            _color("systemRedColor", NSColor.redColor)
            if error
            else _color("secondaryLabelColor", NSColor.disabledControlTextColor)
        )

    @objc.python_method
    def _update_inspect_button(self):
        active = bool(self._inspect_all_metadata)
        label = "Show LitSquare Metadata" if active else "Inspect All Metadata"
        try:
            self.inspectButton.setState_(1 if active else 0)
        except Exception:
            pass
        self.inspectButton.setToolTip_(label)
        try:
            self.inspectButton.setAccessibilityLabel_(label)
            self.inspectButton.setAccessibilityValue_("On" if active else "Off")
        except Exception:
            pass
        setter = getattr(self.inspectButton, "setContentTintColor_", None)
        if callable(setter):
            try:
                setter(
                    _color("controlAccentColor", NSColor.blueColor)
                    if active
                    else _color(
                        "secondaryLabelColor", NSColor.disabledControlTextColor
                    )
                )
            except Exception:
                pass

    @objc.python_method
    def _font(self):
        controller = self.windowController()
        if controller is None:
            return None
        document = _value(getattr(controller, "document", None))
        if document is None:
            return None
        return _value(getattr(document, "font", None))

    @objc.python_method
    def _scope(self):
        try:
            index = int(self.scopeControl.selectedSegment())
        except Exception:
            index = 0
        return _SCOPES[index] if 0 <= index < len(_SCOPES) else "font"

    @objc.python_method
    def _schedule_refresh(self):
        if self._refresh_pending:
            return
        self._refresh_pending = True
        try:
            NSOperationQueue.mainQueue().addOperationWithBlock_(
                self._perform_scheduled_refresh
            )
        except Exception:
            self._perform_scheduled_refresh()

    @objc.python_method
    def _perform_scheduled_refresh(self):
        self._refresh_pending = False
        self._refresh()

    @objc.python_method
    def _refresh(self):
        font = self._font()
        scope = self._scope()
        if font is None:
            rendered = {
                "fingerprint": "no-context:{}".format(scope),
                "text": "",
                "targets": [],
                "enabled": False,
                "mixed": False,
                "info": "No document",
                "infoError": False,
            }
        else:
            try:
                rendered = self._render(font, scope)
            except Exception as exc:
                rendered = {
                    "fingerprint": "error:{}:{}".format(scope, repr(exc)),
                    "text": "",
                    "targets": [],
                    "enabled": False,
                    "mixed": False,
                    "info": "Invalid JSON",
                    "infoError": True,
                }
        if rendered["fingerprint"] == self._snapshot_fingerprint:
            return
        self._snapshot_fingerprint = rendered["fingerprint"]
        self._editor_scope = scope
        self._editor_targets = [dict(target) for target in rendered.get("targets") or []]
        self._editor_baseline = str(rendered.get("text") or "")
        self._editor_native_info = str(rendered.get("info") or "")
        self._editor_native_info_error = bool(rendered.get("infoError"))
        self._editor_dirty = False
        self._editor_mixed = bool(rendered.get("mixed"))
        self._copy_text = self._editor_baseline
        self._editor_programmatic = True
        try:
            self.textView.setString_(self._editor_baseline)
            self.textView.setEditable_(bool(rendered.get("enabled")))
            self.textView.setTextColor_(
                _color("secondaryLabelColor", NSColor.disabledControlTextColor)
                if self._editor_mixed
                else _color("controlTextColor", NSColor.blackColor)
            )
        finally:
            self._editor_programmatic = False
        self._set_info(self._editor_native_info, self._editor_native_info_error)

    @objc.python_method
    def _render(self, font, scope):
        if self._inspect_all_metadata:
            return self._render_all_metadata(font, scope)
        if scope == "paths":
            snapshot = selected_path_snapshot(font=font)
            paths = snapshot.get("paths") or []
            aggregation = snapshot.get("aggregation") or {}
            targets = paths if snapshot.get("ok") else []
            state = str(aggregation.get("state") or "no_context")
            mixed = state == "mixed"
            info = ""
            info_error = False
            enabled = bool(targets) and state != "no_context"
            if not enabled:
                text = ""
                info = "No selection"
            elif mixed:
                text = _MIXED_VALUE
                info = "Mixed values"
            elif state == "valid":
                text = canonical_json({"role": aggregation.get("sharedRole")})
                info = "Valid JSON"
            elif state == "unassigned":
                text = ""
                info = "Unset"
            else:
                raw = paths[0].get("rawRole") if paths else None
                text = canonical_json({"role": raw})
                info = "Invalid value"
                info_error = True
        else:
            snapshot = metadata_selection_snapshot(scope, font=font)
            entries = snapshot.get("entries") or []
            targets = [entry.get("target") for entry in entries if entry.get("target")]
            mixed = bool(snapshot.get("summary", {}).get("mixed"))
            result = snapshot.get("sharedResult") or {}
            state = str(result.get("state") or "no_context")
            enabled = bool(targets) and state != "unsupported_schema"
            info = ""
            info_error = False
            if not targets:
                text = ""
                info = "No selection"
            elif mixed:
                text = _MIXED_VALUE
                info = "Mixed values"
            elif result.get("value") is None:
                text = ""
                info = "Unset"
            else:
                text = canonical_json(result.get("value"))
                info = {
                    "empty": "Empty",
                    "valid": "Valid JSON",
                    "valid_with_warnings": "Valid with warnings",
                }.get(state, "")
            if state == "invalid":
                info = "Invalid value"
                info_error = True
            elif state == "unsupported_schema":
                info = "Unsupported schema"
                info_error = True
        fingerprint = canonical_json(
            {
                "scope": scope,
                "text": text,
                "targets": targets,
                "enabled": enabled,
                "mixed": mixed,
                "info": info,
                "infoError": info_error,
            }
        )
        return {
            "fingerprint": fingerprint,
            "text": text,
            "targets": targets,
            "enabled": enabled,
            "mixed": mixed,
            "info": info,
            "infoError": info_error,
        }

    @objc.python_method
    def _render_all_metadata(self, font, scope):
        snapshot = full_metadata_selection_snapshot(scope, font=font)
        entries = snapshot.get("entries") or []
        summary = snapshot.get("summary") or {}
        target_count = int(summary.get("targetCount") or 0)
        warning_count = int(summary.get("warningCount") or 0)
        if not entries:
            text = ""
            info = "No selection"
        else:
            text = canonical_json({"scope": scope, "targets": entries})
            if warning_count:
                info = "Projection warning"
                if target_count > 1:
                    info += " · {} targets".format(target_count)
            elif target_count > 1:
                info = "All metadata · {} targets".format(target_count)
            else:
                info = "All metadata"
        fingerprint = canonical_json(
            {
                "mode": "all_metadata",
                "scope": scope,
                "text": text,
                "targetCount": target_count,
                "warningCount": warning_count,
                "info": info,
            }
        )
        return {
            "fingerprint": fingerprint,
            "text": text,
            "targets": [],
            "enabled": False,
            "mixed": False,
            "info": info,
            "infoError": False,
        }

    @objc.python_method
    def __file__(self):
        return __file__


__all__ = ["GlyphsMCPLitSquareMetadataPalette", "PALETTE_NAME"]
