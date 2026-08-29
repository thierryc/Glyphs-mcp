# encoding: utf-8

"""Passive native panel for the current unsaved-session tool-call history."""

from __future__ import annotations

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
from Foundation import NSIndexSet, NSObject, NSOperationQueue, NSThread
from GlyphsApp import (  # type: ignore[import-not-found]
    DOCUMENTACTIVATED,
    DOCUMENTCLOSED,
    Glyphs,
)

from .change_log_model import ChangeLogModel
from .runtime import active_history, active_host


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


class DocumentChangesPanelController(NSObject):
    """Display-only panel; it owns no editor navigation or Reporter state."""

    def initWithPlugin_(self, plugin):
        self = objc.super(DocumentChangesPanelController, self).init()
        if self is None:
            return None
        self._plugin = plugin
        self._panel = None
        self._rows = []
        self._selected_commit_id = None
        self._document_id = None
        self._unsubscribe = None
        self._callbacks = []
        history = active_history()
        self._model = ChangeLogModel(history) if history is not None else None
        if history is not None:
            self._unsubscribe = history.subscribe(self._history_changed)
        for callback, event in (
            (self.DocumentActivated_, DOCUMENTACTIVATED),
            (self.DocumentClosed_, DOCUMENTCLOSED),
        ):
            try:
                Glyphs.addCallback(callback, event)
                self._callbacks.append(callback)
            except Exception:
                pass
        return self

    @objc.python_method
    def close(self):
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            except Exception:
                pass
            self._unsubscribe = None
        for callback in self._callbacks:
            try:
                Glyphs.removeCallback(callback)
            except Exception:
                pass
        self._callbacks = []
        if self._panel is not None:
            try:
                self._panel.orderOut_(None)
            except Exception:
                pass
        self._panel = None

    def DocumentActivated_(self, notification):
        self.refresh()

    def DocumentClosed_(self, notification):
        self.refresh()

    @objc.python_method
    def _history_changed(self, document_id):
        if self._panel is None:
            return
        if NSThread.isMainThread():
            self.refresh()
        else:
            NSOperationQueue.mainQueue().addOperationWithBlock_(self.refresh)

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
    def show(self):
        self._ensure_panel()
        self.refresh()
        # Do not force editor navigation or alter its view state.
        self._panel.orderFront_(None)

    @objc.python_method
    def _ensure_panel(self):
        if self._panel is not None:
            return
        width, height, margin = 760, 520, 18
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskUtilityWindow
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0, 0), (width, height)), style, NSBackingStoreBuffered, False
        )
        panel.setTitle_("Glyphs MCP Change Log")
        panel.setFloatingPanel_(False)
        panel.setDelegate_(self)
        content = panel.contentView()

        header = _quiet_field(((margin, height - 44), (width - margin * 2, 22)), "No open document", 14, True)
        content.addSubview_(header)
        counts = _quiet_field(((margin, height - 70), (width - margin * 2, 18)), "", 10)
        content.addSubview_(counts)

        table = NSTableView.alloc().initWithFrame_(((0, 0), (width - margin * 2, 238)))
        for identifier, title, column_width in (
            ("time", "Time", 74),
            ("status", "Result", 92),
            ("action", "Command", 292),
            ("targets", "Changed targets", 250),
        ):
            column = NSTableColumn.alloc().initWithIdentifier_(identifier)
            column.setTitle_(title)
            column.setWidth_(column_width)
            table.addTableColumn_(column)
        table.setDataSource_(self)
        table.setDelegate_(self)
        table.setAllowsMultipleSelection_(False)
        scroll = NSScrollView.alloc().initWithFrame_(((margin, 184), (width - margin * 2, 250)))
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(getattr(AppKit, "NSBezelBorder", 2))
        scroll.setDocumentView_(table)
        scroll.setAutoresizingMask_(NSViewWidthSizable)
        content.addSubview_(scroll)

        detail = _quiet_field(((margin, 60), (width - margin * 2, 108)), "", 10)
        try:
            detail.setUsesSingleLineMode_(False)
            detail.cell().setWraps_(True)
            detail.cell().setLineBreakMode_(getattr(AppKit, "NSLineBreakByWordWrapping", 0))
        except Exception:
            pass
        content.addSubview_(detail)

        copy_button = NSButton.alloc().initWithFrame_(((margin, 18), (120, 30)))
        copy_button.setTitle_("Copy Details")
        copy_button.setTarget_(self)
        copy_button.setAction_(self.CopyDetails_)
        content.addSubview_(copy_button)

        self._panel = panel
        self._header_field = header
        self._counts_field = counts
        self._table = table
        self._detail_field = detail
        self._copy_button = copy_button

    @objc.python_method
    def refresh(self):
        if not NSThread.isMainThread():
            NSOperationQueue.mainQueue().addOperationWithBlock_(self.refresh)
            return
        if self._panel is None:
            return
        document_id, font = self._active_document()
        self._document_id = document_id
        rows = self._model.rows(document_id) if self._model is not None and document_id else ()
        self._rows = list(rows)
        family = str(getattr(font, "familyName", "") or "Untitled font") if font is not None else "No open document"
        self._header_field.setStringValue_(family)
        self._counts_field.setStringValue_(
            "{} tool call{} since the last save".format(len(rows), "" if len(rows) == 1 else "s")
        )
        self._table.reloadData()
        selected_index = next(
            (index for index, row in enumerate(rows) if row.commit_id == self._selected_commit_id),
            -1,
        )
        if selected_index < 0 and rows:
            selected_index = len(rows) - 1
        if selected_index >= 0:
            self._table.selectRowIndexes_byExtendingSelection_(
                NSIndexSet.indexSetWithIndex_(selected_index), False
            )
            self._selected_commit_id = rows[selected_index].commit_id
        else:
            self._selected_commit_id = None
        self._update_detail()

    @objc.python_method
    def _update_detail(self):
        text = (
            self._model.detail(self._selected_commit_id)
            if self._model is not None and self._selected_commit_id
            else "No MCP tool calls have been recorded since the last save."
        )
        self._detail_field.setStringValue_(text)
        self._copy_button.setEnabled_(bool(self._selected_commit_id))

    def numberOfRowsInTableView_(self, table_view):
        return len(self._rows)

    def tableView_objectValueForTableColumn_row_(self, table_view, column, row):
        if row < 0 or row >= len(self._rows):
            return ""
        return getattr(self._rows[row], str(column.identifier()), "")

    def tableViewSelectionDidChange_(self, notification):
        try:
            index = int(self._table.selectedRow())
        except Exception:
            index = -1
        self._selected_commit_id = self._rows[index].commit_id if 0 <= index < len(self._rows) else None
        self._update_detail()

    def CopyDetails_(self, sender):
        if not self._selected_commit_id or self._model is None:
            return
        text = self._model.detail(self._selected_commit_id)
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(text, NSPasteboardTypeString)


__all__ = ["DocumentChangesPanelController"]
