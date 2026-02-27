# encoding: utf-8

from __future__ import division, print_function, unicode_literals
import time
import objc
import AppKit
import threading
from GlyphsApp import Glyphs, EDIT_MENU # type: ignore[import-not-found]
from GlyphsApp.plugins import GeneralPlugin # type: ignore[import-not-found]
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSAlertSecondButtonReturn,
    NSAlertThirdButtonReturn,
    NSMenuItem,
    NSPanel,
    NSButton,
    NSProgressIndicator,
    NSPasteboard,
    NSPasteboardTypeString,
    NSTextField,
    NSPopUpButton,
    NSView,
    NSWorkspace,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskUtilityWindow,
    NSBackingStoreBuffered,
)
from Foundation import NSNumberFormatter, NSTimer, NSURL
from starlette.middleware import Middleware

from mcp_tools import mcp
from security import (
    McpNoOAuthWellKnownMiddleware,
    McpDiscoveryMiddleware,
    McpSessionIdMiddleware,
    OriginValidationMiddleware,
    StaticTokenAuthMiddleware,
)
from status_panel_helpers import endpoint_for, is_thread_running, status_text
from tool_profiles import PROFILE_FULL, PROFILE_ORDER, enabled_tool_names, is_valid_profile_name
from utils import (
    get_known_tools,
    get_mcp_tool_registry,
    get_tool_info,
    is_port_available,
    notify_server_started,
    replace_tool_registry_in_place,
)
from versioning import get_docs_url_latest, get_plugin_version


AUTOSTART_DEFAULTS_KEY = "io.anotherplanet.glyphs-mcp.autostart"
TOOL_PROFILE_DEFAULTS_KEY = "com.ap.cx.glyphs-mcp.toolProfile"
DEFAULT_TOOL_PROFILE = PROFILE_FULL


class MCPBridgePlugin(GeneralPlugin):

    @objc.python_method
    def settings(self):
        self._tool_registry_ref = None
        self._tool_registry_snapshot = None

        # Localized menu titles
        self.name_start = Glyphs.localize(
            {
                "en": "Start Glyphs MCP Server",
                "de": "Glyphs MCP-Server starten",
                "fr": "Démarrer le serveur MCP",
                "es": "Iniciar el servidor MCP",
                "pt": "Iniciar o servidor Glyphs MCP",
            }
        )
        self.name_running = Glyphs.localize(
            {
                "en": "Glyphs MCP Server is running",
                "de": "Glyphs MCP-Server läuft",
                "fr": "Le serveur MCP est en cours d'exécution",
                "es": "El servidor MCP está en ejecución",
                "pt": "O servidor MCP está em execução",
            }
        )
        self.name_status = Glyphs.localize(
            {
                "en": "Glyphs MCP Server Status…",
                "de": "Glyphs MCP-Server-Status…",
                "fr": "Statut du serveur MCP…",
                "es": "Estado del servidor MCP…",
                "pt": "Status do servidor MCP…",
            }
        )
        self.name_autostart = Glyphs.localize(
            {
                "en": "Auto-start server on launch",
                "de": "Server beim Start automatisch starten",
                "fr": "Démarrer le serveur au lancement",
                "es": "Iniciar el servidor al abrir",
                "pt": "Iniciar o servidor ao abrir",
            }
        )
        # Configuration
        self.default_port = 9680

    @objc.python_method
    def _selected_tool_profile_name(self):
        try:
            stored = Glyphs.defaults[TOOL_PROFILE_DEFAULTS_KEY]
        except Exception:
            stored = None

        try:
            name = str(stored) if stored else DEFAULT_TOOL_PROFILE
        except Exception:
            name = DEFAULT_TOOL_PROFILE

        if not is_valid_profile_name(name):
            return DEFAULT_TOOL_PROFILE
        return name

    @objc.python_method
    def _set_selected_tool_profile_name(self, name):
        try:
            value = str(name) if name else DEFAULT_TOOL_PROFILE
        except Exception:
            value = DEFAULT_TOOL_PROFILE
        if not is_valid_profile_name(value):
            value = DEFAULT_TOOL_PROFILE
        try:
            Glyphs.defaults[TOOL_PROFILE_DEFAULTS_KEY] = value
        except Exception:
            pass

    @objc.python_method
    def _ensure_full_tool_snapshot(self):
        if getattr(self, "_tool_registry_ref", None) is not None and getattr(self, "_tool_registry_snapshot", None) is not None:
            return True

        registry = get_mcp_tool_registry(mcp)
        if not isinstance(registry, dict):
            return False

        try:
            snapshot = dict(registry)
        except Exception:
            snapshot = None

        if snapshot is None:
            return False

        self._tool_registry_ref = registry
        self._tool_registry_snapshot = snapshot
        return True

    @objc.python_method
    def _apply_tool_profile_to_mcp_for_next_start(self):
        if not self._ensure_full_tool_snapshot():
            return False

        profile = self._selected_tool_profile_name()
        snapshot = getattr(self, "_tool_registry_snapshot", None) or {}
        registry = getattr(self, "_tool_registry_ref", None)

        all_names = set(snapshot.keys())
        enabled = enabled_tool_names(profile, all_names)
        filtered = {name: snapshot[name] for name in enabled if name in snapshot}

        try:
            replace_tool_registry_in_place(registry, filtered)
            return True
        except Exception:
            return False

    @objc.python_method
    def _autostart_enabled(self):
        try:
            value = Glyphs.defaults[AUTOSTART_DEFAULTS_KEY]
        except Exception:
            return False
        try:
            return bool(value)
        except Exception:
            return False

    @objc.python_method
    def _set_autostart_enabled(self, enabled):
        try:
            Glyphs.defaults[AUTOSTART_DEFAULTS_KEY] = bool(enabled)
        except Exception as e:
            try:
                print("[Glyphs MCP][Autostart] Failed to persist defaults: {}".format(e))
            except Exception:
                pass
            return

    @objc.python_method
    def _http_middleware(self):
        """Return security middleware for the embedded HTTP server."""
        middleware = [
            Middleware(McpNoOAuthWellKnownMiddleware),
            Middleware(McpDiscoveryMiddleware),
            Middleware(McpSessionIdMiddleware),
            Middleware(OriginValidationMiddleware),
        ]

        # Always include token middleware; it is a no-op unless the env token is set.
        middleware.append(Middleware(StaticTokenAuthMiddleware))
        return middleware

    @objc.python_method
    def start(self):
        try:
            self._ensure_full_tool_snapshot()
        except Exception:
            pass

        newMenuItem = NSMenuItem.new()
        newMenuItem.setTitle_(self.name_start)
        # Keep a reference so we can update the label later
        self.menuItem = newMenuItem
        newMenuItem.setTarget_(self)
        newMenuItem.setAction_(self.StartStopServer_)
        Glyphs.menu[EDIT_MENU].append(newMenuItem)

        status_item = NSMenuItem.new()
        status_item.setTitle_(self.name_status)
        status_item.setTarget_(self)
        status_item.setAction_(self.ShowStatusWindow_)
        Glyphs.menu[EDIT_MENU].append(status_item)
        self.statusMenuItem = status_item

        try:
            self._maybe_autostart_on_launch()
        except Exception:
            pass

    @objc.python_method
    def _start_server_on_port(self, port, sender, notify=True):
        try:
            self._apply_tool_profile_to_mcp_for_next_start()
        except Exception:
            pass

        self._server_thread = threading.Thread(
            target=mcp.run,
            kwargs=dict(
                transport="http",
                host="127.0.0.1",
                port=port,
                middleware=self._http_middleware(),
            ),
            daemon=True,
        )
        self._server_thread.start()
        self._port = port

        if notify:
            notify_server_started(port)
        self._show_startup_message(port)

        # Update menu title to indicate the server is running
        try:
            sender.setTitle_(self.name_running)
        except Exception:
            if hasattr(self, "menuItem"):
                self.menuItem.setTitle_(self.name_running)

        self._refresh_status_panel_if_visible()

    @objc.python_method
    def _maybe_autostart_on_launch(self):
        if not self._autostart_enabled():
            return
        if self._server_is_running():
            return
        if getattr(self, "_waiting_for_port", False):
            return

        if is_port_available(self.default_port, host="127.0.0.1"):
            self._start_server_on_port(
                self.default_port,
                getattr(self, "menuItem", None),
                notify=False,
            )
            return

        self._begin_autostart_wait_for_port(self.default_port)

    @objc.python_method
    def _cancel_autostart_wait(self):
        timer = getattr(self, "_autostart_timer", None)
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        self._autostart_timer = None
        self._autostart_waiting = False
        self._autostart_target_port = None
        self._autostart_deadline = None
        self._refresh_status_panel_if_visible()

    @objc.python_method
    def _begin_autostart_wait_for_port(self, port):
        if getattr(self, "_autostart_timer", None) is not None:
            return
        if getattr(self, "_waiting_for_port", False):
            return

        self._autostart_waiting = True
        self._autostart_target_port = int(port)
        self._autostart_deadline = time.monotonic() + 30.0
        self._autostart_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, self, "AutostartPoll:", None, True
        )
        self._refresh_status_panel_if_visible()

    def AutostartPoll_(self, timer):
        if self._server_is_running():
            self._cancel_autostart_wait()
            return
        if not self._autostart_enabled():
            self._cancel_autostart_wait()
            return

        port = getattr(self, "_autostart_target_port", self.default_port)

        if is_port_available(port, host="127.0.0.1"):
            self._cancel_autostart_wait()
            try:
                self._start_server_on_port(
                    port,
                    getattr(self, "menuItem", None),
                    notify=False,
                )
            except Exception as e:
                self._show_error("Failed to start server: {}".format(e))
            return

        deadline = getattr(self, "_autostart_deadline", None)
        try:
            if deadline is not None and time.monotonic() > float(deadline):
                self._cancel_autostart_wait()
                print(
                    "[Glyphs MCP] Auto-start skipped: port {} still busy.".format(
                        int(port)
                    )
                )
        except Exception:
            return

    @objc.python_method
    def _prompt_when_default_port_busy(self):
        message = (
            'I can\'t start the MCP server on "9680".\n\n'
            "Wait (preferred) until the previous instance has finished shutting down, "
            "or start on a custom port below."
        )

        alert = NSAlert.alloc().init()
        alert.setMessageText_("Glyphs MCP Server")
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("Wait (preferred)")
        alert.addButtonWithTitle_("Start on Custom Port")
        alert.addButtonWithTitle_("Cancel")

        port_field = NSTextField.alloc().initWithFrame_(((0, 0), (220, 24)))
        port_field.setPlaceholderString_("Custom port (1–65535)")
        port_field.setStringValue_("9681")
        try:
            formatter = NSNumberFormatter.alloc().init()
            formatter.setAllowsFloats_(False)
            port_field.setFormatter_(formatter)
        except Exception:
            pass

        accessory = NSView.alloc().initWithFrame_(((0, 0), (220, 24)))
        accessory.addSubview_(port_field)
        alert.setAccessoryView_(accessory)

        response = alert.runModal()
        if response == NSAlertFirstButtonReturn:
            return ("wait", None)
        if response == NSAlertSecondButtonReturn:
            try:
                value = int(port_field.stringValue().strip())
            except Exception:
                return ("custom", None)
            return ("custom", value)
        if response == NSAlertThirdButtonReturn:
            return (None, None)
        return (None, None)

    @objc.python_method
    def _cancel_wait_for_port(self):
        timer = getattr(self, "_wait_timer", None)
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        self._wait_timer = None
        self._waiting_for_port = False
        self._wait_target_port = None
        self._wait_sender = None

        panel = getattr(self, "_wait_panel", None)
        self._wait_panel = None
        try:
            if panel is not None:
                panel.orderOut_(None)
        except Exception:
            pass

        self._refresh_status_panel_if_visible()

    @objc.python_method
    def _begin_wait_for_port_and_start(self, port, sender):
        if is_port_available(port, host="127.0.0.1"):
            self._start_server_on_port(port, sender)
            return

        # If already waiting, just bring the panel forward.
        panel = getattr(self, "_wait_panel", None)
        if panel is not None:
            try:
                panel.makeKeyAndOrderFront_(None)
            except Exception:
                pass
            return

        self._waiting_for_port = True
        self._wait_target_port = int(port)
        self._wait_sender = sender
        self._refresh_status_panel_if_visible()

        width = 420
        height = 130
        rect = ((0, 0), (width, height))
        # Use an explicit Cancel button instead of a close widget to avoid
        # background retry timers continuing after the UI is dismissed.
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskUtilityWindow
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        panel.setTitle_("Glyphs MCP Server")
        panel.setFloatingPanel_(True)

        content = panel.contentView()
        margin = 16

        info = NSTextField.alloc().initWithFrame_(((margin, height - margin - 44), (width - margin * 2, 44)))
        info.setStringValue_(
            "Waiting for port {0} to become available…\nThis usually takes a few seconds.".format(
                int(port)
            )
        )
        info.setEditable_(False)
        info.setSelectable_(False)
        info.setBordered_(False)
        info.setDrawsBackground_(False)
        content.addSubview_(info)

        spinner = NSProgressIndicator.alloc().initWithFrame_(((margin, margin + 40), (18, 18)))
        spinner.setIndeterminate_(True)
        try:
            spinner.setUsesThreadedAnimation_(True)
        except Exception:
            pass
        style_spinning = globals().get("NSProgressIndicatorStyleSpinning") or globals().get(
            "NSProgressIndicatorSpinningStyle"
        )
        if style_spinning is not None:
            try:
                spinner.setStyle_(style_spinning)
            except Exception:
                pass
        try:
            spinner.startAnimation_(None)
        except Exception:
            pass
        content.addSubview_(spinner)

        cancel_w = 90
        cancel_h = 28
        cancel_btn = NSButton.alloc().initWithFrame_(((width - margin - cancel_w, margin), (cancel_w, cancel_h)))
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setTarget_(self)
        cancel_btn.setAction_(self.CancelWaitForPort_)
        content.addSubview_(cancel_btn)

        self._wait_panel = panel
        try:
            panel.makeKeyAndOrderFront_(None)
        except Exception:
            pass

        # Poll on the main runloop so AppKit remains responsive.
        self._wait_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, self, "WaitPoll:", None, True
        )

    def CancelWaitForPort_(self, sender):
        self._cancel_wait_for_port()

    def WaitPoll_(self, timer):
        port = getattr(self, "_wait_target_port", None)
        sender = getattr(self, "_wait_sender", None)
        if port is None:
            self._cancel_wait_for_port()
            return

        if not getattr(self, "_waiting_for_port", False):
            self._cancel_wait_for_port()
            return

        if not is_port_available(port, host="127.0.0.1"):
            return

        # Port is free: stop waiting UI first, then start server.
        self._cancel_wait_for_port()
        try:
            self._start_server_on_port(port, sender)
        except Exception as e:
            self._show_error("Failed to start server: {}".format(e))

    @objc.python_method
    def _show_error(self, text):
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Glyphs MCP Server")
        alert.setInformativeText_(text)
        alert.addButtonWithTitle_("OK")
        try:
            alert.runModal()
        except Exception:
            print(text)

    def StartStopServer_(self, sender):
        """Toggle the local FastMCP server running on localhost.

        Clicking the menu item starts the server (if stopped) or shows status if already running.
        """
        # Check if server is running and provide status
        if hasattr(self, "_server_thread") and self._server_thread.is_alive():
            self._show_server_status()
            return

        while True:
            if is_port_available(self.default_port, host="127.0.0.1"):
                port = self.default_port
                break

            action, custom_port = self._prompt_when_default_port_busy()
            if action == "wait":
                self._begin_wait_for_port_and_start(self.default_port, sender)
                return
            if action == "custom":
                if custom_port is None:
                    self._show_error("Enter a valid port number (1–65535).")
                    continue
                if not (1 <= custom_port <= 65535):
                    self._show_error("Port must be between 1 and 65535.")
                    continue
                if not is_port_available(custom_port, host="127.0.0.1"):
                    self._show_error(
                        "Port {} is already in use. Choose another port.".format(
                            custom_port
                        )
                    )
                    continue
                port = custom_port
                break
            return

        try:
            self._start_server_on_port(port, sender)
        except Exception as e:
            print("Failed to start server: {}".format(e))

    def ShowStatusWindow_(self, sender):
        """Open a small floating window with server status and endpoint."""
        try:
            self._ensure_status_panel()
            self._refresh_status_panel()
            self._status_panel.makeKeyAndOrderFront_(None)
        except Exception as e:
            self._show_error("Unable to open MCP status window: {}".format(e))

    @objc.python_method
    def _current_port(self):
        try:
            return int(getattr(self, "_port", self.default_port))
        except Exception:
            return int(self.default_port)

    @objc.python_method
    def _server_is_running(self):
        return is_thread_running(getattr(self, "_server_thread", None))

    @objc.python_method
    def _ensure_status_panel(self):
        if hasattr(self, "_status_panel") and self._status_panel is not None:
            return

        width = 420
        height = 230
        rect = ((0, 0), (width, height))
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskUtilityWindow
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        panel.setTitle_("Glyphs MCP Server")
        panel.setFloatingPanel_(True)

        content = panel.contentView()
        margin = 16
        row_h = 22
        row_gap = 8
        label_w = 80
        value_w = width - margin * 2 - label_w
        y = height - margin - row_h

        status_label = NSTextField.alloc().initWithFrame_(((margin, y), (label_w, row_h)))
        status_label.setStringValue_("Status:")
        status_label.setEditable_(False)
        status_label.setSelectable_(False)
        status_label.setBordered_(False)
        status_label.setDrawsBackground_(False)
        content.addSubview_(status_label)

        status_value = NSTextField.alloc().initWithFrame_(((margin + label_w, y), (value_w, row_h)))
        status_value.setEditable_(False)
        status_value.setSelectable_(True)
        status_value.setBordered_(False)
        status_value.setDrawsBackground_(False)
        content.addSubview_(status_value)

        y -= (row_h + row_gap)

        version_label = NSTextField.alloc().initWithFrame_(((margin, y), (label_w, row_h)))
        version_label.setStringValue_("Version:")
        version_label.setEditable_(False)
        version_label.setSelectable_(False)
        version_label.setBordered_(False)
        version_label.setDrawsBackground_(False)
        content.addSubview_(version_label)

        version_value = NSTextField.alloc().initWithFrame_(((margin + label_w, y), (value_w, row_h)))
        version_value.setEditable_(False)
        version_value.setSelectable_(True)
        version_value.setBordered_(False)
        version_value.setDrawsBackground_(False)
        content.addSubview_(version_value)

        y -= (row_h + row_gap)

        endpoint_label = NSTextField.alloc().initWithFrame_(((margin, y), (label_w, row_h)))
        endpoint_label.setStringValue_("Endpoint:")
        endpoint_label.setEditable_(False)
        endpoint_label.setSelectable_(False)
        endpoint_label.setBordered_(False)
        endpoint_label.setDrawsBackground_(False)
        content.addSubview_(endpoint_label)

        endpoint_value = NSTextField.alloc().initWithFrame_(((margin + label_w, y), (value_w, row_h)))
        endpoint_value.setEditable_(False)
        endpoint_value.setSelectable_(True)
        endpoint_value.setBordered_(False)
        endpoint_value.setDrawsBackground_(False)
        content.addSubview_(endpoint_value)

        y -= (row_h + row_gap)

        docs_label = NSTextField.alloc().initWithFrame_(((margin, y), (label_w, row_h)))
        docs_label.setStringValue_("Docs:")
        docs_label.setEditable_(False)
        docs_label.setSelectable_(False)
        docs_label.setBordered_(False)
        docs_label.setDrawsBackground_(False)
        content.addSubview_(docs_label)

        docs_value = NSTextField.alloc().initWithFrame_(((margin + label_w, y), (value_w, row_h)))
        docs_value.setEditable_(False)
        docs_value.setSelectable_(True)
        docs_value.setBordered_(False)
        docs_value.setDrawsBackground_(False)
        content.addSubview_(docs_value)

        y -= (row_h + row_gap)

        profile_label = NSTextField.alloc().initWithFrame_(((margin, y), (label_w, row_h)))
        profile_label.setStringValue_("Profile:")
        profile_label.setEditable_(False)
        profile_label.setSelectable_(False)
        profile_label.setBordered_(False)
        profile_label.setDrawsBackground_(False)
        content.addSubview_(profile_label)

        profile_popup = NSPopUpButton.alloc().initWithFrame_(((margin + label_w, y - 2), (value_w, row_h + 6)))
        try:
            profile_popup.removeAllItems()
        except Exception:
            pass
        try:
            profile_popup.addItemsWithTitles_(PROFILE_ORDER)
        except Exception:
            for item in PROFILE_ORDER:
                try:
                    profile_popup.addItemWithTitle_(item)
                except Exception:
                    pass
        profile_popup.setTarget_(self)
        profile_popup.setAction_(self.ChangeToolProfile_)
        content.addSubview_(profile_popup)

        button_w = 110
        button_h = 28
        button_y = margin
        button_gap = 10
        copy_button_x = width - margin - button_w
        docs_button_x = copy_button_x - button_gap - button_w

        autostart_w = max(10, docs_button_x - margin - 10)
        autostart_checkbox = NSButton.alloc().initWithFrame_(((margin, button_y), (autostart_w, button_h)))
        autostart_checkbox.setTitle_(getattr(self, "name_autostart", "Auto-start server on launch"))
        switch_type = getattr(AppKit, "NSSwitchButton", None) or getattr(AppKit, "NSButtonTypeSwitch", None)
        if switch_type is None:
            switch_type = 3
        try:
            autostart_checkbox.setButtonType_(switch_type)
        except Exception:
            pass
        autostart_checkbox.setTarget_(self)
        autostart_checkbox.setAction_(self.ToggleAutostart_)
        content.addSubview_(autostart_checkbox)

        open_docs_button = NSButton.alloc().initWithFrame_(((docs_button_x, button_y), (button_w, button_h)))
        open_docs_button.setTitle_("Open Docs")
        open_docs_button.setTarget_(self)
        open_docs_button.setAction_(self.OpenDocs_)
        content.addSubview_(open_docs_button)

        copy_button = NSButton.alloc().initWithFrame_(((copy_button_x, button_y), (button_w, button_h)))
        copy_button.setTitle_("Copy Endpoint")
        copy_button.setTarget_(self)
        copy_button.setAction_(self.CopyEndpoint_)
        content.addSubview_(copy_button)

        self._status_panel = panel
        self._status_field = status_value
        self._version_field = version_value
        self._endpoint_field = endpoint_value
        self._docs_field = docs_value
        self._autostart_checkbox = autostart_checkbox
        self._tool_profile_popup = profile_popup

    @objc.python_method
    def _refresh_status_panel_if_visible(self):
        panel = getattr(self, "_status_panel", None)
        if panel is None:
            return
        try:
            if panel.isVisible():
                self._refresh_status_panel()
        except Exception:
            return

    @objc.python_method
    def _refresh_status_panel(self):
        running = self._server_is_running()
        port = self._current_port()
        endpoint = endpoint_for(port)
        version = get_plugin_version()
        docs_url = get_docs_url_latest()
        tool_profile = self._selected_tool_profile_name()

        try:
            if getattr(self, "_waiting_for_port", False) and not running:
                self._status_field.setStringValue_(
                    "Waiting for port {}…".format(getattr(self, "_wait_target_port", self.default_port))
                )
            elif getattr(self, "_autostart_waiting", False) and not running:
                self._status_field.setStringValue_(
                    "Auto-start waiting for port {}…".format(
                        int(getattr(self, "_autostart_target_port", self.default_port))
                    )
                )
            else:
                self._status_field.setStringValue_(status_text(running))
        except Exception:
            pass
        try:
            self._endpoint_field.setStringValue_(endpoint)
        except Exception:
            pass
        try:
            field = getattr(self, "_version_field", None)
            if field is not None:
                field.setStringValue_(version)
        except Exception:
            pass
        try:
            field = getattr(self, "_docs_field", None)
            if field is not None:
                field.setStringValue_(docs_url)
        except Exception:
            pass
        try:
            popup = getattr(self, "_tool_profile_popup", None)
            if popup is not None:
                popup.selectItemWithTitle_(tool_profile)
        except Exception:
            pass
        try:
            checkbox = getattr(self, "_autostart_checkbox", None)
            if checkbox is not None:
                state_on = getattr(AppKit, "NSControlStateValueOn", getattr(AppKit, "NSOnState", 1))
                state_off = getattr(AppKit, "NSControlStateValueOff", getattr(AppKit, "NSOffState", 0))
                checkbox.setState_(state_on if self._autostart_enabled() else state_off)
        except Exception:
            pass

    def ChangeToolProfile_(self, sender):
        """Persist tool profile selection. Takes effect on next server start."""
        name = None
        try:
            item = sender.selectedItem()
            if item is not None:
                name = item.title()
        except Exception:
            name = None

        if not name:
            try:
                name = sender.titleOfSelectedItem()
            except Exception:
                name = None

        self._set_selected_tool_profile_name(name)
        self._refresh_status_panel_if_visible()

    def ToggleAutostart_(self, sender):
        """Toggle auto-start preference for the MCP server."""
        enabled = False
        try:
            enabled = bool(int(sender.state()))
        except Exception:
            try:
                enabled = bool(sender.state())
            except Exception:
                enabled = self._autostart_enabled()

        try:
            print(
                "[Glyphs MCP][Autostart] Toggle clicked: sender.state={!r} enabled={!r}".format(
                    sender.state() if sender is not None else None,
                    enabled,
                )
            )
        except Exception:
            pass

        self._set_autostart_enabled(enabled)

        try:
            try:
                stored = Glyphs.defaults[AUTOSTART_DEFAULTS_KEY]
            except Exception as e:
                stored = "ERROR: {}".format(e)
            try:
                contains = AUTOSTART_DEFAULTS_KEY in Glyphs.defaults
            except Exception as e:
                contains = "ERROR: {}".format(e)
            print(
                "[Glyphs MCP][Autostart] defaults: contains={!r} stored={!r} readback_enabled={!r}".format(
                    contains,
                    stored,
                    self._autostart_enabled(),
                )
            )
        except Exception:
            pass

        if not enabled:
            self._cancel_autostart_wait()
            self._refresh_status_panel_if_visible()
            return

        if not self._server_is_running():
            try:
                self._maybe_autostart_on_launch()
            except Exception:
                pass

        self._refresh_status_panel_if_visible()

    def CopyEndpoint_(self, sender):
        """Copy the current endpoint URL to the macOS clipboard."""
        endpoint = endpoint_for(self._current_port())
        try:
            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(endpoint, NSPasteboardTypeString)
        except Exception:
            print("Endpoint:", endpoint)

    def OpenDocs_(self, sender):
        """Open the documentation in the default browser."""
        docs_url = get_docs_url_latest()
        try:
            nsurl = NSURL.URLWithString_(docs_url)
            if nsurl is None:
                raise ValueError("Invalid URL")
            NSWorkspace.sharedWorkspace().openURL_(nsurl)
        except Exception as e:
            self._show_error("Unable to open docs URL:\n{}\n\n{}".format(docs_url, e))

    @objc.python_method
    def _show_server_status(self):
        """Show the current server status."""
        print(
            "Glyphs MCP Server is running on port {}.".format(getattr(self, '_port', '?'))
        )
        try:
            print("  Version: {}".format(get_plugin_version()))
        except Exception:
            pass
        print(
            "  HTTP endpoint: http://127.0.0.1:{}".format(getattr(self, '_port', '?'))
        )
        
        # Try to get tools information safely
        try:
            # Try multiple possible attribute names for tools
            tools = None
            for attr_name in ["_tools", "tools", "_tool_registry", "tool_registry", "_handlers"]:
                tools = getattr(mcp, attr_name, None)
                if tools:
                    break
            if tools:
                print("  Available tools: {} tools".format(len(tools)))
                print("  Tools available:")
                for tool_name in sorted(tools.keys()):
                    brief_desc = get_tool_info(mcp, tool_name)
                    print("    - {}: {}".format(tool_name, brief_desc))
            else:
                # Fallback: list the tools we know we defined
                known_tools = get_known_tools()
                print("  Available tools: {} tools".format(len(known_tools)))
                print("  Tools available:")
                for tool_name in known_tools:
                    print("    - {}".format(tool_name))
        except Exception as e:
            print("  Tools information unavailable: {}".format(e))
        
        print(
            "  To stop: restart Glyphs or use Activity Monitor to kill the process."
        )

    @objc.python_method
    def _show_startup_message(self, port):
        """Show startup success message."""
        print("Glyphs MCP Server started successfully!")
        try:
            print("  Version: {}".format(get_plugin_version()))
        except Exception:
            pass
        print("  Port: {}".format(port))
        print("  HTTP endpoint: http://127.0.0.1:{}".format(port))

        # Try to get tools information safely
        try:
            # Try multiple possible attribute names for tools
            tools = None
            for attr_name in ["_tools", "tools", "_tool_registry", "tool_registry", "_handlers"]:
                tools = getattr(mcp, attr_name, None)
                if tools:
                    break
            if tools:
                print("  Available tools: {} tools".format(len(tools)))
                print("  Tools available:")
                for tool_name in sorted(tools.keys()):
                    brief_desc = get_tool_info(mcp, tool_name)
                    print("    - {}: {}".format(tool_name, brief_desc))
            else:
                # Fallback: list the tools we know we defined
                known_tools = get_known_tools()
                print("  Available tools: {} tools".format(len(known_tools)))
                print("  Tools available:")
                for tool_name in known_tools:
                    print("    - {}".format(tool_name))
        except Exception as e:
            print("  Tools information unavailable: {}".format(e))

        print("  Server running in background (daemon thread)")

    @objc.python_method
    def __file__(self):
        """Please leave this method unchanged"""
        return __file__
