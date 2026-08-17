# encoding: utf-8

"""Native apply-first Changes panel for the isolated v2 bundle."""

from __future__ import annotations

from datetime import datetime

import AppKit
import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSButton,
    NSPanel,
    NSPasteboard,
    NSPasteboardTypeString,
    NSScrollView,
    NSTableColumn,
    NSTableView,
    NSTextField,
    NSViewWidthSizable,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskUtilityWindow,
)
from Foundation import NSIndexSet, NSObject, NSOperationQueue, NSThread, NSTimer
from GlyphsApp import DOCUMENTCLOSED, Glyphs  # type: ignore[import-not-found]

from .change_review import CHANGE_REVIEW_STORE, ChangeOperation
from .change_review_navigation import MAX_REVIEW_GLYPHS, open_changed_glyphs
from .runtime import active_host


def _quiet_field(frame, text="", size=11, bold=False):
    field = NSTextField.alloc().initWithFrame_(frame)
    field.setStringValue_(str(text or ""))
    field.setEditable_(False)
    field.setSelectable_(True)
    field.setBordered_(False)
    field.setDrawsBackground_(False)
    try:
        font = AppKit.NSFont.boldSystemFontOfSize_(size) if bold else AppKit.NSFont.systemFontOfSize_(size)
        field.setFont_(font)
    except Exception:
        pass
    return field


def _time_text(timestamp):
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime("%H:%M:%S")
    except Exception:
        return "—"


def _action_text(tool):
    return str(tool or "change").replace("_", " ").strip().title()


def _review_surface(operation):
    tool = operation.tool
    if "kerning" in tool:
        return "Review in the Edit/Kerning view with proof text."
    if "compatibility" in tool:
        return "Review with Compatibility display and the interpolation slider."
    if "instance" in tool:
        return "Review with Preview and interpolation controls."
    if "feature" in tool:
        return "Review in the feature editor or compilation report."
    return "Review the textual before/applied values below."


def _detail_text(operation, navigation_message=None):
    if operation is None:
        return "Select an applied operation to inspect it."
    mapping = operation.to_mapping(include_items=False)
    targets = operation.glyph_targets()
    lines = [
        "{} · {}".format(_action_text(operation.tool), operation.status),
        "Operation: {}".format(operation.operation_id),
        "Changes: {} · Glyphs: {} · Visual overlays: {}".format(
            mapping["changeCount"], mapping["affectedGlyphCount"], mapping["visualizableGlyphCount"]
        ),
    ]
    if operation.reason:
        lines.append("Reason: {}".format(operation.reason))
    if not targets:
        lines.append(_review_surface(operation))
    elif len(targets) > MAX_REVIEW_GLYPHS:
        lines.append("Too many glyph targets to open in one tab ({}; maximum {}).".format(len(targets), MAX_REVIEW_GLYPHS))
    if navigation_message:
        lines.append(str(navigation_message))
    return "\n".join(lines)


class DocumentChangesPanelController(NSObject):
    def initWithPlugin_(self, plugin):
        self = objc.super(DocumentChangesPanelController, self).init()
        if self is None:
            return None
        self._plugin = plugin
        self._panel = None
        self._timer = None
        self._rows = []
        self._selected_operation = None
        self._document_id = None
        self._navigation_message = None
        self._callback_registered = False
        try:
            Glyphs.addCallback(self.DocumentClosed_, DOCUMENTCLOSED)
            self._callback_registered = True
        except Exception:
            pass
        return self

    @objc.python_method
    def close(self):
        self._stop_timer()
        if self._callback_registered:
            try:
                Glyphs.removeCallback(self.DocumentClosed_)
            except Exception:
                pass
        self._callback_registered = False
        if self._panel is not None:
            try:
                self._panel.orderOut_(None)
            except Exception:
                pass
        self._panel = None

    def DocumentClosed_(self, notification):
        document_id = self._document_id
        if document_id:
            host = active_host()
            try:
                if host is None:
                    raise RuntimeError("host unavailable")
                host.native_font(document_id)
            except Exception:
                try:
                    CHANGE_REVIEW_STORE.select(document_id, None)
                except Exception:
                    pass
                self._selected_operation = None
                self._document_id = None
        self.refresh()

    @objc.python_method
    def show(self):
        self._ensure_panel()
        self.refresh()
        self._panel.makeKeyAndOrderFront_(None)
        self._start_timer()

    @objc.python_method
    def _ensure_panel(self):
        if self._panel is not None:
            return
        width, height, margin = 720, 500, 18
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskUtilityWindow
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0, 0), (width, height)), style, NSBackingStoreBuffered, False
        )
        panel.setTitle_("Glyphs MCP Changes")
        panel.setFloatingPanel_(True)
        panel.setDelegate_(self)
        content = panel.contentView()

        header = _quiet_field(((margin, height - 46), (width - margin * 2, 24)), "No open document", 14, True)
        content.addSubview_(header)
        counts = _quiet_field(((margin, height - 72), (width - margin * 2, 20)), "", 11, True)
        content.addSubview_(counts)

        table = NSTableView.alloc().initWithFrame_(((0, 0), (width - margin * 2, 240)))
        for identifier, title, column_width in (
            ("time", "Time", 72),
            ("status", "Status", 110),
            ("action", "Action", 300),
            ("targets", "Targets", 180),
        ):
            column = NSTableColumn.alloc().initWithIdentifier_(identifier)
            column.setTitle_(title)
            column.setWidth_(column_width)
            table.addTableColumn_(column)
        table.setDataSource_(self)
        table.setDelegate_(self)
        table.setTarget_(self)
        table.setDoubleAction_(self.OpenChangedGlyphs_)
        table.setAllowsMultipleSelection_(False)
        scroll = NSScrollView.alloc().initWithFrame_(((margin, 170), (width - margin * 2, 250)))
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(getattr(AppKit, "NSBezelBorder", 2))
        scroll.setDocumentView_(table)
        scroll.setAutoresizingMask_(NSViewWidthSizable)
        content.addSubview_(scroll)

        detail = _quiet_field(((margin, 70), (width - margin * 2, 86)), "", 10)
        try:
            detail.setUsesSingleLineMode_(False)
            detail.cell().setWraps_(True)
            detail.cell().setLineBreakMode_(getattr(AppKit, "NSLineBreakByWordWrapping", 0))
        except Exception:
            pass
        content.addSubview_(detail)

        open_button = NSButton.alloc().initWithFrame_(((margin, 24), (170, 30)))
        open_button.setTitle_("Open Changed Glyphs")
        open_button.setTarget_(self)
        open_button.setAction_(self.OpenChangedGlyphs_)
        content.addSubview_(open_button)

        copy_button = NSButton.alloc().initWithFrame_(((margin + 180, 24), (120, 30)))
        copy_button.setTitle_("Copy Details")
        copy_button.setTarget_(self)
        copy_button.setAction_(self.CopyDetails_)
        content.addSubview_(copy_button)

        self._panel = panel
        self._header_field = header
        self._counts_field = counts
        self._table = table
        self._detail_field = detail
        self._open_button = open_button
        self._copy_button = copy_button

    @objc.python_method
    def _start_timer(self):
        if self._timer is None:
            self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.5, self, "RefreshTimer:", None, True
            )

    @objc.python_method
    def _stop_timer(self):
        if self._timer is not None:
            try:
                self._timer.invalidate()
            except Exception:
                pass
        self._timer = None

    def RefreshTimer_(self, timer):
        self.refresh()

    def windowWillClose_(self, notification):
        self._stop_timer()

    @objc.python_method
    def _active_document(self):
        host = active_host()
        font = getattr(Glyphs, "font", None)
        if host is None or font is None:
            return None, None
        try:
            return host.document_id_for_font(font), font
        except Exception:
            return None, None

    @objc.python_method
    def refresh(self):
        if not NSThread.isMainThread():
            NSOperationQueue.mainQueue().addOperationWithBlock_(self.refresh)
            return
        if self._panel is None:
            return
        document_id, font = self._active_document()
        self._document_id = document_id
        operations = list(CHANGE_REVIEW_STORE.list_operations(document_id)) if document_id else []
        self._rows = [
            {
                "time": _time_text(operation.created_at),
                "status": operation.status.replace("_", " ").title(),
                "action": _action_text(operation.tool),
                "targets": "{} glyph{}".format(len(operation.glyph_targets()), "" if len(operation.glyph_targets()) == 1 else "s"),
                "operation": operation,
            }
            for operation in operations
        ]
        family = str(getattr(font, "familyName", "") or "Untitled font") if font is not None else "No open document"
        self._header_field.setStringValue_(family)
        self._counts_field.setStringValue_("{} recorded operation{}".format(len(operations), "" if len(operations) == 1 else "s"))
        selected_id = self._selected_operation.operation_id if self._selected_operation else None
        self._table.reloadData()
        selected_index = next(
            (index for index, row in enumerate(self._rows) if row["operation"].operation_id == selected_id),
            -1,
        )
        if selected_index < 0 and self._rows:
            selected_index = len(self._rows) - 1
        if selected_index >= 0:
            self._table.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(selected_index), False)
            self._selected_operation = self._rows[selected_index]["operation"]
            try:
                CHANGE_REVIEW_STORE.select(document_id, self._selected_operation.operation_id)
            except Exception:
                pass
        else:
            self._selected_operation = None
        self._update_detail()

    @objc.python_method
    def _update_detail(self):
        self._detail_field.setStringValue_(_detail_text(self._selected_operation, self._navigation_message))
        targets = self._selected_operation.glyph_targets() if self._selected_operation else ()
        self._open_button.setEnabled_(bool(targets) and len(targets) <= MAX_REVIEW_GLYPHS)
        self._copy_button.setEnabled_(self._selected_operation is not None)

    def numberOfRowsInTableView_(self, table_view):
        return len(self._rows)

    def tableView_objectValueForTableColumn_row_(self, table_view, column, row):
        if row < 0 or row >= len(self._rows):
            return ""
        return self._rows[row].get(str(column.identifier()), "")

    def tableViewSelectionDidChange_(self, notification):
        try:
            index = int(self._table.selectedRow())
        except Exception:
            index = -1
        self._selected_operation = self._rows[index]["operation"] if 0 <= index < len(self._rows) else None
        self._navigation_message = None
        if self._selected_operation is not None and self._document_id:
            try:
                CHANGE_REVIEW_STORE.select(self._document_id, self._selected_operation.operation_id)
                Glyphs.redraw()
            except Exception:
                pass
        self._update_detail()

    def OpenChangedGlyphs_(self, sender):
        operation = self._selected_operation
        host = active_host()
        if operation is None or host is None:
            return
        try:
            font = host.native_font(operation.document_id)
            CHANGE_REVIEW_STORE.select(operation.document_id, operation.operation_id)
            result = open_changed_glyphs(font, operation)
        except Exception:
            result = {"ok": False, "errorCode": "document_unavailable"}
        if result.get("ok"):
            mapping = operation.to_mapping(include_items=False)
            if mapping.get("visualizableGlyphCount"):
                try:
                    Glyphs.activateReporter("GlyphsMCPChangeReviewReporter")
                except Exception:
                    pass
            missing = int(result.get("missingGlyphCount") or 0)
            self._navigation_message = (
                "Opened {} glyph(s).{}".format(
                    result.get("openedGlyphCount"),
                    " {} missing target(s) were skipped.".format(missing) if missing else "",
                )
            )
        else:
            self._navigation_message = "Could not open targets: {}.".format(result.get("errorCode") or "unknown_error")
        try:
            Glyphs.redraw()
        except Exception:
            pass
        self._update_detail()

    def CopyDetails_(self, sender):
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(_detail_text(self._selected_operation, self._navigation_message), NSPasteboardTypeString)


__all__ = ["DocumentChangesPanelController"]
