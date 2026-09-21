"""Non-blocking, visible-layer comparison against a saved or Git reference."""

import json
from threading import RLock, Thread
from time import monotonic

import objc
from AppKit import NSColor, NSEvent, NSGraphicsContext, NSPoint
from Foundation import NSBundle, NSClassFromString
from GlyphsApp import DOCUMENTWASSAVED, DOCUMENTOPENED, DOCUMENTACTIVATED, TABDIDOPEN, UPDATEEDITVIEWFRAME, Glyphs, UPDATEINTERFACE
from GlyphsApp.plugins import ReporterPlugin
from PyObjCTools import AppHelper

from glyphs_mcp_companions import publish, withdraw, visible_layer, invalidate_view, wake_reporter
from reference_core.client import ReferenceReader
from reference_core.geometry import comparison, resolved_layer_elements
from glyphs_reference_inspector import drawing, menus


PREFERENCES = "com.ap.cx.glyphs-reference-inspector.references"
QUIET_SECONDS = 0.15
LABEL_GAP_POINTS = 12.0
MANIFEST = {"protocol": 1, "id": "reference-inspector", "version": "0.1.0",
            "capabilities": ["reference.saved", "reference.file", "reference.git", "reference.github", "reference.overlay"]}


def _value(owner, key, default=None):
    try:
        value = getattr(owner, key)
        return value() if callable(value) else value
    except Exception:
        return default


def _label_point(layer, scale):
    try:
        descender = float(_value(_value(layer, "master"), "descender", -200.0))
    except (TypeError, ValueError):
        descender = -200.0
    return NSPoint(0, descender - LABEL_GAP_POINTS / max(float(scale or 1), .01))


class GlyphsReferenceInspector(ReporterPlugin):
    @objc.python_method
    def settings(self):
        self.menuName = "Changes Against Reference"
        self._reader = ReferenceReader(str(NSBundle.mainBundle().bundlePath()))
        self._lock = RLock()
        self._pending = None
        self._busy = False
        self._generation = 0
        self._epoch = 0
        self._source_key = None
        self._published = None
        self._context = None
        self._refresh_scheduled = False
        self._refresh_deadline = 0.0
        self._menu = None
        self._specs = {}
        try:
            self._specs = json.loads(str(Glyphs.defaults[PREFERENCES] or "{}"))
            if not isinstance(self._specs, dict):
                self._specs = {}
        except Exception:
            pass

    @objc.python_method
    def start(self):
        self._menu = menus.install_menu(self)
        Glyphs.addCallback(self.update_, UPDATEINTERFACE)
        Glyphs.addCallback(self.saved_, DOCUMENTWASSAVED)
        for event in (DOCUMENTOPENED, DOCUMENTACTIVATED, TABDIDOPEN, UPDATEEDITVIEWFRAME):
            Glyphs.addCallback(self.attached_, event)
        publish(MANIFEST)
        self.attached_(None)

    @objc.typedSelector(b"v@:")
    def willActivate(self):
        # Glyphs sets activeReporters after this callback.
        self.attached_(None)

    def attached_(self, sender):
        wake_reporter(self, AppHelper)

    @objc.typedSelector(b"v@:@")
    def setController_(self, controller):
        self._controller = controller
        self.attached_(None)

    @objc.typedSelector(b"v@:")
    def willDeactivate(self):
        self._clear_overlay()

    @objc.python_method
    def _source(self):
        return str(_value(_value(Glyphs, "font"), "filepath", "") or "")

    @objc.python_method
    def _spec(self):
        return self._specs.get(self._source(), {"kind": "last_saved"})

    @objc.python_method
    def _configure(self, spec):
        if spec is None or not self._source():
            return
        self._specs[self._source()] = spec
        while len(self._specs) > 128:
            self._specs.pop(next(iter(self._specs)))
        Glyphs.defaults[PREFERENCES] = json.dumps(self._specs)
        Glyphs.activateReporter(self)
        self.refreshReference_(None)

    def useLastSaved_(self, sender):
        self._configure({"kind": "last_saved"})

    def chooseFile_(self, sender):
        self._configure(menus.choose_file())

    def chooseLocalGit_(self, sender):
        self._configure(menus.choose_git("local_git", self._spec()))

    def chooseGitHub_(self, sender):
        self._configure(menus.choose_git("github", self._spec()))

    def refreshReference_(self, sender):
        self._epoch += 1
        self._source_key = None
        self.update_(None)

    def validateMenuItem_(self, item):
        return bool(self._source())

    @objc.typedSelector(b"v@:@")
    def menuNeedsUpdate_(self, menu):
        menus.refresh_menu(menu, self._source(), self._spec(), has_font=_value(Glyphs, "font") is not None)

    def saved_(self, sender):
        if self._spec().get("kind") == "last_saved":
            self.refreshReference_(None)

    @objc.python_method
    def _target(self):
        if self not in list(_value(Glyphs, "activeReporters", []) or []):
            return None, None
        font = _value(Glyphs, "font")
        layer = visible_layer(Glyphs)
        if layer is None:
            return None, None
        context = (int(objc.pyobjc_id(font)), int(objc.pyobjc_id(layer)), self._source(),
                   json.dumps(self._spec(), sort_keys=True), self._epoch)
        return layer, context

    @objc.python_method
    def _clear_overlay(self):
        self._generation += 1
        self._context = self._source_key = self._published = None
        with self._lock:
            self._pending = None

    def update_(self, sender):
        layer, context = self._target()
        if context is None:
            self._clear_overlay()
            return
        self._generation += 1
        with self._lock:
            self._pending = None
        changed_context = context != self._context
        if changed_context:
            self._context = context
            self._source_key = None
            self._published = {"identity": context[1], "label": "Loading reference…", "paths": None}
        # Preserve completed paths during edits. Only a font/layer/reference
        # switch may clear them; never collect geometry inside this callback.
        delay = 0.0 if changed_context else QUIET_SECONDS
        self._refresh_deadline = monotonic() + delay
        self._schedule_refresh(delay)

    @objc.python_method
    def _schedule_refresh(self, delay):
        if not self._refresh_scheduled:
            self._refresh_scheduled = True
            AppHelper.callLater(delay, self._refresh_when_idle)

    @objc.python_method
    def _refresh_when_idle(self):
        self._refresh_scheduled = False
        layer, context = self._target()
        if context != self._context:
            self.update_(None)
            return
        if context is None:
            return
        remaining = self._refresh_deadline - monotonic()
        # This is a conservative held-button guard, not an event tracker.
        # One deferred callback exists only while a refresh is pending.
        if NSEvent.pressedMouseButtons():
            self._refresh_deadline = monotonic() + QUIET_SECONDS
            self._schedule_refresh(QUIET_SECONDS)
            return
        if remaining > 0:
            self._schedule_refresh(remaining)
            return
        self._capture(layer, context)

    @objc.python_method
    def _capture(self, layer, context):
        identity = context[1]
        try:
            source = context[2]
            if not source:
                raise ValueError("Save this font before choosing a reference")
            glyph = _value(layer, "parent")
            master = _value(layer, "master")
            outline, open_outline = resolved_layer_elements(layer, context="current layer")
            live = {"outline": outline, "width": float(layer.width),
                    "openOutline": open_outline,
                    "anchors": {str(a.name): [float(a.position.x), float(a.position.y)] for a in layer.anchors}}
            request = {"source": source, "reference": self._spec(), "epoch": self._epoch,
                       "refresh": self._epoch > 0, "glyph": str(glyph.name), "layer": str(layer.layerId),
                       "masterLayer": bool(_value(layer, "isMasterLayer", False)),
                       "masterName": str(_value(master, "name", "") or "")}
            key = (identity, json.dumps(request, sort_keys=True), json.dumps(live, separators=(",", ":")))
            if key == self._source_key:
                return
            with self._lock:
                self._pending = (self._generation, identity, request, live, key)
                if self._busy:
                    return
                self._busy = True
            Thread(target=self._prepare_pending, name="glyphs-reference", daemon=True).start()
        except Exception as error:
            self._publish(self._generation, identity, "Reference unavailable: " + str(error), None, None)

    @objc.python_method
    def _prepare_pending(self):
        while True:
            with self._lock:
                item, self._pending = self._pending, None
                if item is None:
                    self._busy = False
                    return
            generation, identity, request, live, key = item
            try:
                reference = self._reader.read(request)
                plan = comparison(reference, live)
                label = reference["label"]
                if reference.get("missingGlyph"):
                    label += " · Glyph absent from reference"
                elif plan["width"]:
                    before, after = plan["width"]
                    label += " · Width {:+g}".format(after-before)
                elif not plan["outlineChanged"] and not plan["anchors"]:
                    label += " · No changes"
                AppHelper.callAfter(self._publish, generation, identity, label, plan, key)
            except Exception as error:
                AppHelper.callAfter(self._publish, generation, identity, "Reference unavailable: " + str(error), None, None)

    @objc.python_method
    def _publish(self, generation, identity, label, plan, key):
        if generation != self._generation:
            return
        if self._target()[1] != self._context or NSEvent.pressedMouseButtons():
            self.update_(None)
            return
        paths = drawing.prepare(plan) if plan is not None else (self._published or {}).get("paths")
        # A failed refresh keeps the last usable overlay and exposes the error.
        # Commit the deduplication key only after a successful publication.
        self._source_key = key
        if self._published and self._published["label"] == label and self._published["paths"] is paths:
            return
        self._published = {"identity": identity, "label": label,
                           "paths": paths}
        if self._menu is not None:
            self._menu.setToolTip_(label)
        invalidate_view(Glyphs)

    @objc.python_method
    def conditionsAreMetForDrawing(self):
        """Hide the indication while Glyphs' text or temporary hand tool is active."""
        try:
            controller = self._controller.view().window().windowController()
            if controller is None:
                return True
            tool = controller.toolDrawDelegate()
            for class_name in ("GlyphsToolText", "GlyphsToolHand"):
                tool_class = NSClassFromString(class_name)
                if tool_class is not None and tool.isKindOfClass_(tool_class):
                    return False
        except Exception:
            # Drawing may precede controller attachment during restored startup.
            return True
        return True

    @objc.python_method
    def foreground(self, layer):
        # Only Glyphs' active-edit callback may draw the comparison. Inactive
        # occurrences can share this exact layer object with the edited glyph.
        if layer is None or not self.conditionsAreMetForDrawing():
            return
        NSGraphicsContext.saveGraphicsState()
        try:
            published = self._published
            if not published or int(objc.pyobjc_id(layer)) != published["identity"]:
                return
            scale = float(self.getScale() or 1)
            if published["paths"] is not None:
                drawing.paint(published["paths"], scale)
            self.drawTextAtPoint(published["label"], _label_point(layer, scale), fontSize=10,
                                 align="topleft",
                                 fontColor=NSColor.secondaryLabelColor())
        finally:
            NSGraphicsContext.restoreGraphicsState()

    @objc.python_method
    def __del__(self):
        for callback in (self.update_, self.saved_, self.attached_):
            try:
                Glyphs.removeCallback(callback)
            except Exception:
                pass
        withdraw(MANIFEST["id"])

    @objc.python_method
    def __file__(self):
        return __file__
