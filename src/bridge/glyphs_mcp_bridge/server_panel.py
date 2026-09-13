"""Application-wide MCP settings with quiet, asynchronous status checks."""

import json
import subprocess
from pathlib import Path
from threading import Thread

import objc
import AppKit as AK
from Foundation import NSURL, NSNotificationCenter
from GlyphsApp import EDIT_MENU, Glyphs, UPDATEINTERFACE
from GlyphsApp.plugins import GeneralPlugin
from PyObjCTools import AppHelper

from .lifecycle import BRIDGE_VERSION, bridge_lifecycle as runtime


WELCOME_KEY = "com.ap.cx.glyphs-mcp.welcomeShown"


class GlyphsMCPServerPlugin(GeneralPlugin):
    @objc.python_method
    def settings(self):
        self.name = "Glyphs MCP Server"
        self.window = self.welcome = None
        self._welcome_observers = []
        self._welcome_pending = False
        self._scheduled = self._checking = False
        self._action = None
        self._serial = 0
        self._data = {}
        self._rendered = None
        self._notice = ""
        self._last_port = "9680"

    @objc.python_method
    def start(self):
        if runtime.menu_item is None:
            item = AK.NSMenuItem.new()
            item.setTitle_("Glyphs MCP Server…")
            item.setTarget_(self)
            item.setAction_(self.showSettings_)
            Glyphs.menu[EDIT_MENU].append(item)
            runtime.menu_item, runtime.menu_target = item, self
            self._schedule_welcome()
        runtime.start(Glyphs, UPDATEINTERFACE)

    def showSettings_(self, sender):
        if self.window is None:
            self._build_window()
        self.window.makeKeyAndOrderFront_(None)
        self._run("status")

    @objc.python_method
    def _build_window(self):
        self.window = self._create_window("server_panel.json")

    @objc.python_method
    def _schedule_welcome(self):
        if not self._welcome_pending:
            self._welcome_pending = True
            AppHelper.callAfter(self._try_welcome)

    @objc.python_method
    def _try_welcome(self):
        self._welcome_pending = False
        center = NSNotificationCenter.defaultCenter()
        if not Glyphs.defaults[WELCOME_KEY]:
            if not self._welcome_observers:
                for event in (AK.NSApplicationDidFinishLaunchingNotification,
                              AK.NSApplicationDidBecomeActiveNotification, AK.NSWindowDidBecomeKeyNotification):
                    self._welcome_observers.append(center.addObserverForName_object_queue_usingBlock_(
                        event, None, None, lambda _: self._schedule_welcome()))
            if not AK.NSApp.isActive() or AK.NSApp.modalWindow() is not None:
                return
            try:
                self.showWelcome_(None)
            except Exception as error:
                print("[Glyphs MCP] Welcome unavailable: " + str(error))
        if Glyphs.defaults[WELCOME_KEY]:
            for observer in self._welcome_observers:
                center.removeObserver_(observer)
            self._welcome_observers.clear()

    def showWelcome_(self, sender):
        if self.welcome is None:
            self.welcome = self._create_window("welcome_panel.json")
        self.welcome.makeKeyAndOrderFront_(None)
        if self.welcome.isVisible():
            Glyphs.defaults[WELCOME_KEY] = True

    def closeWelcome_(self, sender):
        self.welcome.close()

    @objc.python_method
    def _create_window(self, filename):
        layout = json.loads(Path(__file__).with_name(filename).read_text())
        window = AK.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            AK.NSMakeRect(0, 0, *layout["size"]), AK.NSWindowStyleMaskTitled | AK.NSWindowStyleMaskClosable,
            AK.NSBackingStoreBuffered, False)
        window.setTitle_(layout["title"])
        window.setReleasedWhenClosed_(False)
        window.center()
        for spec in layout["controls"]:
            kind = spec["kind"]
            classes = {"box": AK.NSBox, "button": AK.NSButton, "field": AK.NSTextField, "label": AK.NSTextField}
            item = classes[kind].alloc().initWithFrame_(AK.NSMakeRect(*spec["frame"]))
            for setter, value in spec.get("properties", {}).items():
                if isinstance(value, dict):
                    value = getattr(AK.NSColor, value["color"])()
                getattr(item, setter)(value)
            if "text" in spec:
                text = spec["text"].format(projectVersion=layout.get("releaseLabel", layout.get("projectVersion", "development")), bridgeVersion=BRIDGE_VERSION)
                (item.setTitle_ if kind == "button" else item.setStringValue_)(text)
            if kind in ("label", "field"):
                item.setFont_((AK.NSFont.boldSystemFontOfSize_ if spec.get("bold") else AK.NSFont.systemFontOfSize_)(spec.get("size", 13)))
                item.setTextColor_(getattr(AK.NSColor, spec.get("color", "labelColor"))())
            if "action" in spec:
                item.setTarget_(self)
                item.setAction_(getattr(self, spec["action"]))
            if "link" in spec:
                item.setToolTip_(spec["link"])
            window.contentView().addSubview_(item)
            if "id" in spec:
                setattr(self, "_" + spec["id"], item)

        return window

    def toggleServer_(self, sender):
        self._operate("stop" if self._data.get("running") else "start")

    def applyPort_(self, sender):
        self._operate("port", self._port.stringValue().strip())

    @objc.python_method
    def _operate(self, action, *args):
        if self._action:
            return
        try:
            if action in ("stop", "port") and runtime.core and runtime.core.status()["activeOperations"]:
                raise RuntimeError("Wait for the current font operation to finish, then try again.")
            if action == "start":
                runtime.start(Glyphs, UPDATEINTERFACE)
                if not runtime.ready:
                    raise RuntimeError(runtime.startup_error or "The Glyphs connection could not start.")
            self._run(action, *args)
        except Exception as error:
            self._notice = str(error)
            self._render()

    def changeAutomatic_(self, sender):
        self._run("auto-on" if sender.state() else "auto-off")

    def openLink_(self, sender):
        AK.NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(sender.toolTip()))

    def openLogs_(self, sender):
        AK.NSWorkspace.sharedWorkspace().openURL_(NSURL.fileURLWithPath_(str(Path.home() / "Library/Logs/Glyphs MCP")))

    def copyURL_(self, sender):
        board = AK.NSPasteboard.generalPasteboard()
        board.clearContents()
        board.setString_forType_(self._url.stringValue(), AK.NSPasteboardTypeString)

    @objc.python_method
    def _run(self, action, *args):
        if self._action or (action == "status" and self._checking):
            return
        self._serial += 1
        if action == "status":
            self._checking = True
        else:
            self._action = action
            self._notice = {"start": "Starting…", "stop": "Stopping…"}.get(action, "Applying…")
            self._render()
        Thread(target=self._control, args=(self._serial, action, args), name="glyphs-server-settings", daemon=True).start()

    @objc.python_method
    def _control(self, serial, action, args):
        try:
            root = Path.home() / "Library/Application Support/Glyphs MCP/lean-v2"
            receipt = json.loads((root / "installation.json").read_text())
            result = subprocess.run([receipt["python"], str(root / "sidecar/control.py"), action, *args],
                                    capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout)
        except Exception as error:
            data = {"ok": False, "error": "Server controls unavailable: " + str(error)}
        AppHelper.callAfter(self._finish, serial, action, data)

    @objc.python_method
    def _finish(self, serial, action, result):
        if action == "status":
            self._checking = False
        if serial != self._serial:
            return
        self._action = None
        if result["ok"]:
            self._data = result["data"]
            if action != "status":
                self._notice = "Port updated. Use the new URL in your AI connections." if action == "port" else ""
        else:
            self._notice = result.get("error", "Server unavailable")
        self._render()
        if not self._scheduled:
            self._scheduled = True
            AppHelper.callLater(2, self._poll)

    @objc.python_method
    def _render(self):
        state = (self._data, runtime.ready, self._action, self._notice)
        if state == self._rendered:
            return
        self._rendered = state
        running = self._data.get("running", False)
        self._status.setStringValue_("●  " + ("Running" if running else "Stopped" if self._data else "Checking connection…"))
        self._status.setTextColor_(AK.NSColor.systemGreenColor() if running else AK.NSColor.secondaryLabelColor())
        self._bridge.setStringValue_("Connected to Glyphs" if runtime.ready else "Glyphs connection stopped")
        self._toggle.setTitle_("Stop Server" if running else "Start Server")
        self._url.setStringValue_(self._data.get("url", "http://127.0.0.1:9680/mcp/"))
        if self._port.stringValue() == self._last_port:
            self._port.setStringValue_(str(self._data.get("port", 9680)))
        self._last_port = str(self._data.get("port", 9680))
        self._auto.setState_(bool(self._data.get("autoStart", False)))
        for control in (self._toggle, self._auto, self._apply, self._port):
            control.setEnabled_(self._action is None)
        self._message.setStringValue_(self._notice or "Changing the port restarts a running server. Update your AI connections to use the new URL.")

    @objc.python_method
    def _poll(self):
        self._scheduled = False
        if self.window.isVisible():
            self._run("status")

    @objc.python_method
    def __file__(self):
        return __file__
