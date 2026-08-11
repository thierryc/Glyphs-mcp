# encoding: utf-8

"""Native AppKit utility panel for the one-document MCP change ledger."""

from __future__ import annotations

import objc
import AppKit
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
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

from document_changes_panel_model import (
    counts_text,
    detail_text,
    glyph_names_for_event,
    header_text,
    panel_rows,
    retention_text,
)
from i18n import tr
from mcp_tool_helpers import _font_object_id, _open_fonts_from_glyphs, _open_tab_on_main_thread
from mcp_tools_document_changes import (
    clear_closed_document,
    current_change_overview,
    document_change_markdown,
    reset_document_change_overview,
    tracked_document_object_id,
)


def _quiet_field(frame, text="", size=11, bold=False):
    field = NSTextField.alloc().initWithFrame_(frame)
    field.setStringValue_(str(text or ""))
    field.setEditable_(False)
    field.setSelectable_(True)
    field.setBordered_(False)
    field.setDrawsBackground_(False)
    try:
        field.setFont_(AppKit.NSFont.boldSystemFontOfSize_(size) if bold else AppKit.NSFont.systemFontOfSize_(size))
    except Exception:
        pass
    return field


class DocumentChangesPanelController(NSObject):
    """Own the read-only native panel and document-close cleanup callback."""

    def initWithPlugin_(self, plugin):
        self = objc.super(DocumentChangesPanelController, self).init()
        if self is None:
            return None
        self._plugin = plugin
        self._panel = None
        self._timer = None
        self._rows = []
        self._selected_event = None
        self._overview_warnings = []
        self._callback_registered = False
        try:
            Glyphs.addCallback(self.DocumentClosed_, DOCUMENTCLOSED)
            self._callback_registered = True
        except Exception:
            self._callback_registered = False
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
        object_id = None
        try:
            document = notification.object() if hasattr(notification, "object") else notification
            font = getattr(document, "font", None)
            if callable(font):
                font = font()
            if font is not None:
                object_id = _font_object_id(font)
        except Exception:
            object_id = None
        if object_id is not None:
            clear_closed_document(object_id)
        else:
            self._clear_if_tracked_document_is_closed()
        self.refresh()

    @objc.python_method
    def _clear_if_tracked_document_is_closed(self):
        snapshot = current_change_overview(limit=1)
        if snapshot.get("status") != "active":
            return
        tracked_object_id = tracked_document_object_id()
        fonts = list(_open_fonts_from_glyphs(Glyphs))
        if tracked_object_id is not None:
            if any(_font_object_id(font) == tracked_object_id for font in fonts):
                return
            reset_document_change_overview()
            return
        tracked = snapshot.get("target") or {}
        tracked_path = tracked.get("filePath")
        tracked_name = tracked.get("familyName")
        for font in fonts:
            path = getattr(font, "filepath", None)
            name = getattr(font, "familyName", None) or "Untitled font"
            if tracked_path and str(path or "") == str(tracked_path):
                return
            if not tracked_path and name == tracked_name:
                return
        reset_document_change_overview()

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
        width = 720
        height = 500
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskUtilityWindow
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0, 0), (width, height)), style, NSBackingStoreBuffered, False
        )
        panel.setTitle_(tr("changes.title"))
        panel.setFloatingPanel_(True)
        panel.setDelegate_(self)
        content = panel.contentView()
        margin = 18

        header = _quiet_field(((margin, height - 42), (width - margin * 2, 22)), "", size=14, bold=True)
        content.addSubview_(header)
        retention = _quiet_field(
            ((margin, height - 66), (width - margin * 2, 18)),
            tr("changes.retention"),
            size=10,
        )
        content.addSubview_(retention)
        counts = _quiet_field(((margin, height - 91), (width - margin * 2, 20)), "", size=11, bold=True)
        content.addSubview_(counts)

        table = NSTableView.alloc().initWithFrame_(((0, 0), (width - margin * 2, 220)))
        for identifier, title, column_width in (
            ("time", tr("changes.column.time"), 72),
            ("outcome", tr("changes.column.outcome"), 96),
            ("action", tr("changes.column.action"), 300),
            ("target", tr("changes.column.target"), 190),
        ):
            column = NSTableColumn.alloc().initWithIdentifier_(identifier)
            column.setTitle_(title)
            column.setWidth_(column_width)
            table.addTableColumn_(column)
        table.setDataSource_(self)
        table.setDelegate_(self)
        table.setAllowsMultipleSelection_(False)

        scroll = NSScrollView.alloc().initWithFrame_(((margin, 178), (width - margin * 2, 220)))
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(getattr(AppKit, "NSBezelBorder", 2))
        scroll.setDocumentView_(table)
        scroll.setAutoresizingMask_(NSViewWidthSizable)
        content.addSubview_(scroll)

        detail = _quiet_field(((margin, 76), (width - margin * 2, 88)), "", size=10)
        try:
            detail.setUsesSingleLineMode_(False)
            detail.cell().setWraps_(True)
            detail.cell().setLineBreakMode_(getattr(AppKit, "NSLineBreakByWordWrapping", 0))
        except Exception:
            pass
        content.addSubview_(detail)

        open_button = NSButton.alloc().initWithFrame_(((margin, 24), (112, 30)))
        open_button.setTitle_(tr("changes.open_target"))
        open_button.setTarget_(self)
        open_button.setAction_(self.OpenTarget_)
        content.addSubview_(open_button)

        copy_button = NSButton.alloc().initWithFrame_(((margin + 122, 24), (118, 30)))
        copy_button.setTitle_(tr("changes.copy_summary"))
        copy_button.setTarget_(self)
        copy_button.setAction_(self.CopySummary_)
        content.addSubview_(copy_button)

        reset_button = NSButton.alloc().initWithFrame_(((width - margin - 92, 24), (92, 30)))
        reset_button.setTitle_(tr("changes.reset"))
        reset_button.setTarget_(self)
        reset_button.setAction_(self.Reset_)
        content.addSubview_(reset_button)

        self._panel = panel
        self._header_field = header
        self._retention_field = retention
        self._counts_field = counts
        self._table = table
        self._detail_field = detail
        self._open_button = open_button
        self._copy_button = copy_button
        self._reset_button = reset_button

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
    def refresh(self):
        if not NSThread.isMainThread():
            NSOperationQueue.mainQueue().addOperationWithBlock_(self.refresh)
            return
        if self._panel is None:
            return
        snapshot = current_change_overview(limit=100)
        self._header_field.setStringValue_(header_text(snapshot, tr))
        self._retention_field.setStringValue_(retention_text(snapshot, tr))
        self._counts_field.setStringValue_(counts_text(snapshot, tr))
        selected_id = (self._selected_event or {}).get("eventId")
        self._rows = panel_rows(snapshot, tr)
        self._overview_warnings = list(snapshot.get("warnings") or [])
        self._table.reloadData()
        selected_index = -1
        if selected_id:
            for index, row in enumerate(self._rows):
                if row["event"].get("eventId") == selected_id:
                    selected_index = index
                    break
        if selected_index >= 0:
            self._table.selectRowIndexes_byExtendingSelection_(
                NSIndexSet.indexSetWithIndex_(selected_index), False
            )
            self._selected_event = self._rows[selected_index]["event"]
        elif self._rows:
            self._selected_event = self._rows[-1]["event"]
        else:
            self._selected_event = None
        self._detail_field.setStringValue_(
            detail_text(self._selected_event, tr, self._overview_warnings)
        )
        self._open_button.setEnabled_(bool(glyph_names_for_event(self._selected_event)))
        self._copy_button.setEnabled_(snapshot.get("status") == "active")
        self._reset_button.setEnabled_(snapshot.get("status") == "active" or bool(snapshot.get("warnings")))

    def numberOfRowsInTableView_(self, table_view):
        return len(self._rows)

    def tableView_objectValueForTableColumn_row_(self, table_view, column, row):
        if row < 0 or row >= len(self._rows):
            return ""
        identifier = str(column.identifier())
        return self._rows[row].get(identifier, "")

    def tableViewSelectionDidChange_(self, notification):
        try:
            index = int(self._table.selectedRow())
        except Exception:
            index = -1
        self._selected_event = self._rows[index]["event"] if 0 <= index < len(self._rows) else None
        self._detail_field.setStringValue_(
            detail_text(self._selected_event, tr, self._overview_warnings)
        )
        self._open_button.setEnabled_(bool(glyph_names_for_event(self._selected_event)))

    def OpenTarget_(self, sender):
        names = glyph_names_for_event(self._selected_event)
        if not names:
            return
        snapshot = current_change_overview(limit=1)
        target = snapshot.get("target") or {}
        font = None
        tracked_object_id = tracked_document_object_id()
        candidates = list(_open_fonts_from_glyphs(Glyphs))
        for candidate in candidates:
            if tracked_object_id is not None and _font_object_id(candidate) == tracked_object_id:
                font = candidate
                break
        if font is None:
            for candidate in candidates:
                filepath = getattr(candidate, "filepath", None)
                family_name = getattr(candidate, "familyName", None) or "Untitled font"
                if target.get("filePath") and str(filepath or "") == str(target.get("filePath")):
                    font = candidate
                    break
                if not target.get("filePath") and family_name == target.get("familyName"):
                    font = candidate
                    break
        if font is None:
            return
        master_id = ((self._selected_event or {}).get("target") or {}).get("masterId")
        layers = []
        for name in names:
            try:
                glyph = font.glyphs[name]
            except Exception:
                glyph = None
            if glyph is None:
                continue
            try:
                layer = glyph.layers[str(master_id)] if master_id else glyph.layers[0]
            except Exception:
                layer = None
            if layer is not None:
                layers.append(layer)
        if layers:
            _open_tab_on_main_thread(font, layers)

    def CopySummary_(self, sender):
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(document_change_markdown(limit=100), NSPasteboardTypeString)

    def Reset_(self, sender):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(tr("changes.reset_confirm_title"))
        alert.setInformativeText_(tr("changes.reset_confirm_body"))
        alert.addButtonWithTitle_(tr("changes.reset"))
        alert.addButtonWithTitle_(tr("common.cancel"))
        if alert.runModal() != NSAlertFirstButtonReturn:
            return
        reset_document_change_overview()
        self._selected_event = None
        self.refresh()


__all__ = ["DocumentChangesPanelController"]
