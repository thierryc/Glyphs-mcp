"""Small native action panel. No preview or proposal lifecycle in human UI."""
import objc
import GlyphsApp as native_app
from AppKit import (NSPanel, NSTextField, NSButton, NSMenuItem, NSSegmentedControl, NSMakeRect,
                    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
                    NSWindowStyleMaskUtilityWindow, NSBackingStoreBuffered,
                    NSApplication, NSScreen, NSFont)
from Foundation import NSObject, NSNumberFormatter
from GlyphsApp import Glyphs, EDIT_MENU, UPDATEINTERFACE, DOCUMENTACTIVATED, TABDIDOPEN, UPDATEEDITVIEWFRAME
from PyObjCTools import AppHelper
from curve_repair.native import freeze, effective, effective_chain, identity, value
from curve_repair.joins import has_line_join
from curve_repair.actions import resolve_scope, apply_steps, default_limit, validate_limit
from glyphs_mcp_companions import visible_layer


def install_menu(owner):
    item = NSMenuItem.new()
    item.setTitle_("Inspect & Repair…")
    item.setTarget_(owner); item.setAction_(owner.openRepair_)
    item.setToolTip_("Curve Inspector · Inspect & Repair")
    Glyphs.menu[EDIT_MENU].append(item)
    return item


class RepairController(NSObject):
    @objc.python_method
    def setup(self, reporter):
        self.reporter = reporter
        self._closed = self._scheduled = False
        self._task = self._font = None
        self._scope_key = None
        self._limit_font = None
        self._shown = False
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 280, 146),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskUtilityWindow,
            NSBackingStoreBuffered, False)
        self.panel.setTitle_("Curve Inspector")
        self.panel.setReleasedWhenClosed_(False); self.panel.setDelegate_(self)
        self.panel.setFloatingPanel_(True); self.panel.setHidesOnDeactivate_(True)
        self.panel.setBecomesKeyOnlyIfNeeded_(True)
        self.panel.setFrameAutosaveName_("CurveInspectorDirectPanel")
        view = self.panel.contentView()
        def button(title, rect, action, kind=None):
            c = NSButton.alloc().initWithFrame_(NSMakeRect(*rect))
            c.setTitle_(title); c.setTarget_(self); c.setAction_(action)
            if kind is not None: c.setButtonType_(kind)
            view.addSubview_(c); return c
        self.mode = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(12, 114, 256, 24))
        self.mode.setSegmentCount_(2)
        self.mode.setLabel_forSegment_("Star", 0); self.mode.setLabel_forSegment_("Default node", 1)
        self.mode.setWidth_forSegment_(128, 0); self.mode.setWidth_forSegment_(128, 1)
        self.mode.setSelectedSegment_(0)
        self.mode.setTarget_(self); self.mode.setAction_(self.changed_)
        self.mode.setToolTip_("Star: dynamic native repair. Default node: store the native repaired geometry as regular editable nodes. Only joins needing repair are changed; Default node also resolves existing stars.")
        view.addSubview_(self.mode)
        label = NSTextField.labelWithString_("Max change")
        label.setFrame_(NSMakeRect(12, 86, 84, 20)); view.addSubview_(label)
        self.limit = NSTextField.alloc().initWithFrame_(NSMakeRect(101, 84, 70, 24))
        self.limit.setDelegate_(self)
        self.number_formatter = NSNumberFormatter.alloc().init()
        self.number_formatter.setNumberStyle_(1)
        self.number_formatter.setMaximumFractionDigits_(6)
        self.number_formatter.setUsesGroupingSeparator_(False)
        self.limit.setToolTip_("Maximum change to the effective outline, in font units. Default: 0.001 × UPM. Applies to both modes, including optional Tunni balancing.")
        view.addSubview_(self.limit)
        units = NSTextField.labelWithString_("units")
        units.setFrame_(NSMakeRect(178, 86, 70, 20)); view.addSubview_(units)
        self.all_masters = button("All masters", (12, 57, 256, 22), self.changed_, 3)
        self.all_masters.setState_(0)
        self.all_masters.setToolTip_("Every corresponding master must pass before this contour is changed. Backup and special layers are excluded.")
        self.status = NSTextField.labelWithString_("")
        self.status.setFrame_(NSMakeRect(12, 32, 256, 18))
        self.status.setFont_(NSFont.systemFontOfSize_(11)); view.addSubview_(self.status)
        self.apply_button = button("Apply", (12, 4, 256, 27), self.apply_)
        self.apply_button.setToolTip_("Apply directly to the current selection, or the whole glyph/font when nothing is selected. Does not save the font.")
        for event in (UPDATEINTERFACE, DOCUMENTACTIVATED, TABDIDOPEN, UPDATEEDITVIEWFRAME):
            Glyphs.addCallback(self.queueCheck_, event)
        self.check_source()
        return self

    @objc.python_method
    def show(self):
        self.check_source()
        if not self._shown:
            restored = self.panel.setFrameUsingName_("CurveInspectorDirectPanel")
            self.panel.setContentSize_((280, 146))
            if not restored:
                window = NSApplication.sharedApplication().mainWindow()
                screen = window.screen() if window else NSScreen.mainScreen()
                if screen:
                    bounds = screen.visibleFrame(); frame = self.panel.frame()
                    self.panel.setFrameOrigin_((bounds.origin.x+bounds.size.width-frame.size.width-24,
                                               bounds.origin.y+bounds.size.height-frame.size.height-80))
            self._shown = True
        self.panel.makeKeyAndOrderFront_(None)

    @objc.python_method
    def message(self, text, detail=None):
        self.status.setStringValue_(text)
        self.status.setToolTip_(detail or text)

    @objc.python_method
    def limit_units(self):
        number = self.number_formatter.numberFromString_(str(self.limit.stringValue()).strip())
        return validate_limit(number)

    def controlTextDidChange_(self, _notification):
        self.check_source()

    def changed_(self, _sender):
        self.check_source()

    def queueCheck_(self, _sender):
        if self._closed or self._scheduled or self._task is not None: return
        self._scheduled = True
        AppHelper.callAfter(self.check_source)

    @objc.python_method
    def check_source(self):
        self._scheduled = False
        if self._closed or self._task is not None: return
        try:
            scope = resolve_scope(Glyphs, visible_layer, capture=False)
            if identity(scope.font) != identity(self._limit_font):
                self._limit_font = scope.font
                self.limit.setStringValue_(self.number_formatter.stringFromNumber_(default_limit(scope.font)))
            limit = self.limit_units()
            font_selection = value(scope.font, "selection", ()) or () if scope.layer is None else ()
            key = (identity(scope.font), identity(scope.layer), scope.background,
                   scope.description, tuple(identity(i) for i in scope.selection),
                   tuple(identity(g) for g in font_selection),
                   str(value(value(scope.font, "selectedFontMaster"), "id", "")),
                   int(self.mode.selectedSegment()), bool(self.all_masters.state()), limit)
            if key != self._scope_key:
                self._scope_key = key
                self.message(scope.description + " · " + ("All masters" if self.all_masters.state() else
                             "This layer" if scope.layer is not None else "Current master"))
            self.apply_button.setEnabled_(bool(scope.glyphs))
        except Exception as exc:
            self._scope_key = None
            self.message(str(exc)); self.apply_button.setEnabled_(False)

    def apply_(self, _sender):
        if self._task is not None: return
        try:
            scope = resolve_scope(Glyphs, visible_layer)
            self._font = scope.font
            self._task = apply_steps(scope, native_app,
                method="default-node" if self.mode.selectedSegment() else "star",
                all_masters=bool(self.all_masters.state()), max_change_units=self.limit_units())
            self.apply_button.setEnabled_(False)
            for control in (self.mode, self.all_masters, self.limit): control.setEnabled_(False)
            self.message("Applying · " + scope.description)
            AppHelper.callAfter(self.advance)
        except Exception as exc:
            self.message("Cannot apply: " + str(exc))
            self.finish()

    @objc.python_method
    def advance(self):
        if self._task is None: return
        if self._closed or identity(Glyphs.font) != identity(self._font):
            self.message("Stopped · document changed", "Completed contours remain undoable per glyph.")
            self.finish(); return
        try:
            result = next(self._task)
            self.message(result.message(), result.details())
            self.reporter.attached_(None)
            AppHelper.callAfter(self.advance)
        except StopIteration as done:
            result = done.value
            self.message(result.message(), result.details())
            self.finish()
        except Exception as exc:
            self.message("Stopped: " + str(exc), "Completed contours remain undoable per glyph. " + str(exc))
            self.finish()

    @objc.python_method
    def finish(self):
        if self._task is not None: self._task.close()
        self._task = self._font = None
        for control in (self.mode, self.all_masters, self.limit): control.setEnabled_(True)
        try: valid = self.limit_units() > 0
        except Exception: valid = False
        self.apply_button.setEnabled_(not self._closed and Glyphs.font is not None and valid)

    def windowWillClose_(self, _notification):
        self._closed = True
        self.finish()
        Glyphs.removeCallback(self.queueCheck_)
        self.reporter._repair_window = None


def open_controller(reporter):
    if reporter._repair_window is None:
        reporter._repair_window = RepairController.alloc().init().setup(reporter)
    reporter._repair_window.show()
