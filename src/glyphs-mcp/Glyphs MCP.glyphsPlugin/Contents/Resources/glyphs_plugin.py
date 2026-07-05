# encoding: utf-8

from __future__ import division, print_function, unicode_literals
import json
import time
import objc
import AppKit
import threading
import uvicorn
from GlyphsApp import Glyphs, EDIT_MENU # type: ignore[import-not-found]
from GlyphsApp.plugins import GeneralPlugin # type: ignore[import-not-found]
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
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
from Foundation import NSNumberFormatter, NSOperationQueue, NSTimer, NSURL
from starlette.middleware import Middleware

from mcp_tools import mcp
from security import (
    McpErrorEnvelopeMiddleware,
    McpNormalizeMcpPathMiddleware,
    McpNoOAuthWellKnownMiddleware,
    McpDiscoveryMiddleware,
    OriginValidationMiddleware,
    StaticTokenAuthMiddleware,
)
from debug_event_logging import (
    McpDebugEventLoggingMiddleware,
    set_enabled as set_debug_event_logging_enabled,
)
from status_panel_helpers import endpoint_for, is_thread_running, status_text
from i18n import tr
from tool_profiles import (
    PROFILE_EDIT,
    PROFILE_ORDER,
    enabled_tool_names,
    is_valid_profile_name,
    normalize_profile_name,
)
from utils import (
    get_known_tools,
    get_mcp_tool_registry,
    get_tool_info,
    is_port_available,
    notify_server_started,
    replace_tool_registry_in_place,
)
from versioning import get_docs_url_latest, get_plugin_version, get_runtime_info, get_runtime_label


AUTOSTART_DEFAULTS_KEY = "io.anotherplanet.glyphs-mcp.autostart"
TOOL_PROFILE_DEFAULTS_KEY = "com.ap.cx.glyphs-mcp.toolProfile"
DEBUG_LOG_DEFAULTS_KEY = "com.ap.cx.glyphs-mcp.debugLogAllEvents"
DEFAULT_PORT_DEFAULTS_KEY = "com.ap.cx.glyphs-mcp.port"
PORT_DEFAULTS_INITIALIZED_KEY = "com.ap.cx.glyphs-mcp.portInitialized"
DEFAULT_TOOL_PROFILE = PROFILE_EDIT
DEFAULT_PORT = 9680
PROJECT_URL = "https://ap.cx/tools/glyphs-mcp"


class McpActivityStatusMiddleware:
    """Track the latest MCP HTTP/JSON-RPC activity for the status window."""

    def __init__(self, app, recorder=None):
        self.app = app
        self.recorder = recorder

    def _record(self, message, state="ok"):
        if self.recorder is None:
            return
        try:
            self.recorder(message, state)
        except Exception:
            pass

    def _request_label(self, scope, body):
        method = scope.get("method") or "?"
        path = scope.get("path") or "?"
        if method != "POST" or not str(path).startswith("/mcp"):
            return "{} {}".format(method, path)

        try:
            payload = json.loads(body.decode("utf-8", errors="replace") or "{}")
        except Exception:
            return "{} {}".format(method, path)

        if isinstance(payload, list) and payload:
            payload = payload[0]
        if not isinstance(payload, dict):
            return "{} {}".format(method, path)

        rpc_method = payload.get("method") or "POST {}".format(path)
        if rpc_method == "tools/call":
            params = payload.get("params")
            if isinstance(params, dict) and params.get("name"):
                return "tools/call: {}".format(params.get("name"))
        return str(rpc_method)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        body_events = []
        body = b""
        if scope.get("method") == "POST":
            while True:
                message = await receive()
                body_events.append(message)
                if message.get("type") == "http.request":
                    body += message.get("body") or b""
                    if not message.get("more_body", False):
                        break
                else:
                    break

        label = self._request_label(scope, body)
        self._record(label, "active")

        event_index = 0

        async def replay_receive():
            nonlocal event_index
            if event_index < len(body_events):
                event = body_events[event_index]
                event_index += 1
                return event
            return await receive()

        response_status = None

        async def send_wrapper(message):
            nonlocal response_status
            if message.get("type") == "http.response.start":
                response_status = message.get("status")
            await send(message)

        try:
            await self.app(scope, replay_receive if body_events else receive, send_wrapper)
        except Exception as exc:
            self._record("Error: {}".format(exc), "error")
            raise

        try:
            if response_status is not None and int(response_status) >= 400:
                self._record("Error: HTTP {}".format(int(response_status)), "error")
            else:
                self._record(label, "ok")
        except Exception:
            self._record(label, "ok")


class MCPBridgePlugin(GeneralPlugin):

    @objc.python_method
    def settings(self):
        self._tool_registry_ref = None
        self._tool_registry_snapshot = None

        # Localized menu titles (via Glyphs.localize in i18n.tr)
        self.name_menu = tr("menu.main")
        self.name_autostart = tr("menu.autostart")
        self._activity_text = tr("activity.idle")
        self._activity_state = "idle"
        # Configuration
        self.default_port = self._configured_default_port()
        try:
            set_debug_event_logging_enabled(self._debug_logging_enabled())
        except Exception:
            pass

    @objc.python_method
    def _configured_default_port(self):
        try:
            initialized = bool(Glyphs.defaults[PORT_DEFAULTS_INITIALIZED_KEY])
        except Exception:
            initialized = False

        if not initialized:
            self._set_configured_default_port(DEFAULT_PORT)
            try:
                Glyphs.defaults[PORT_DEFAULTS_INITIALIZED_KEY] = True
            except Exception:
                pass
            return DEFAULT_PORT

        try:
            value = Glyphs.defaults[DEFAULT_PORT_DEFAULTS_KEY]
        except Exception:
            value = None

        try:
            port = int(value)
        except Exception:
            self._set_configured_default_port(DEFAULT_PORT)
            return DEFAULT_PORT

        if 1 <= port <= 65535:
            return port

        self._set_configured_default_port(DEFAULT_PORT)
        return DEFAULT_PORT

    @objc.python_method
    def _set_configured_default_port(self, port):
        try:
            value = int(port)
        except Exception:
            value = DEFAULT_PORT
        if not (1 <= value <= 65535):
            value = DEFAULT_PORT

        self.default_port = value
        try:
            Glyphs.defaults[DEFAULT_PORT_DEFAULTS_KEY] = int(value)
            Glyphs.defaults[PORT_DEFAULTS_INITIALIZED_KEY] = True
        except Exception as e:
            try:
                print("[Glyphs MCP][Port] Failed to persist default port: {}".format(e))
            except Exception:
                pass

    @objc.python_method
    def _selected_tool_profile_name(self):
        try:
            stored = Glyphs.defaults[TOOL_PROFILE_DEFAULTS_KEY]
        except Exception:
            stored = None

        try:
            name = normalize_profile_name(stored) if stored else DEFAULT_TOOL_PROFILE
        except Exception:
            name = DEFAULT_TOOL_PROFILE

        if not is_valid_profile_name(name):
            return DEFAULT_TOOL_PROFILE
        return name

    @objc.python_method
    def _set_selected_tool_profile_name(self, name):
        try:
            value = normalize_profile_name(name) if name else DEFAULT_TOOL_PROFILE
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
    def _debug_logging_enabled(self):
        try:
            value = Glyphs.defaults[DEBUG_LOG_DEFAULTS_KEY]
        except Exception:
            return False
        try:
            return bool(value)
        except Exception:
            return False

    @objc.python_method
    def _set_debug_logging_enabled(self, enabled):
        try:
            Glyphs.defaults[DEBUG_LOG_DEFAULTS_KEY] = bool(enabled)
        except Exception as e:
            try:
                print("[Glyphs MCP][DebugLog] Failed to persist defaults: {}".format(e))
            except Exception:
                pass
            return

    @objc.python_method
    def _http_middleware(self):
        """Return security middleware for the embedded HTTP server."""
        middleware = [
            Middleware(McpActivityStatusMiddleware, recorder=self._record_activity),
            Middleware(McpDebugEventLoggingMiddleware),
            Middleware(McpNormalizeMcpPathMiddleware),
            Middleware(McpErrorEnvelopeMiddleware),
            Middleware(McpNoOAuthWellKnownMiddleware),
            Middleware(McpDiscoveryMiddleware),
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
        newMenuItem.setTitle_(self.name_menu)
        self.menuItem = newMenuItem
        newMenuItem.setTarget_(self)
        newMenuItem.setAction_(self.ShowStatusWindow_)
        Glyphs.menu[EDIT_MENU].append(newMenuItem)

        try:
            self._maybe_autostart_on_launch()
        except Exception:
            pass

    @objc.python_method
    def _start_server_on_port(self, port, sender, notify=True):
        self._mark_server_starting()
        try:
            self._apply_tool_profile_to_mcp_for_next_start()
        except Exception:
            pass

        try:
            app = mcp.http_app(
                path="/mcp/",
                transport="http",
                middleware=self._http_middleware(),
            )
            config = uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                timeout_graceful_shutdown=0,
                lifespan="on",
            )
            self._server = uvicorn.Server(config)
            self._server_thread = threading.Thread(
                target=self._server.run,
                daemon=True,
            )
            self._server_thread.start()
            self._port = port
        except Exception as e:
            self._finish_server_starting(error=e)
            raise

        if notify:
            notify_server_started(port)
        self._show_startup_message(port)

        self._finish_server_starting_soon()
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
                self._show_error(tr("error.start_server", error=e))
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
        message = tr("portbusy.message", port=self.default_port)

        alert = NSAlert.alloc().init()
        alert.setMessageText_(tr("app.title"))
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_(tr("portbusy.wait"))
        alert.addButtonWithTitle_(tr("common.cancel"))

        response = alert.runModal()
        if response == NSAlertFirstButtonReturn:
            return ("wait", None)
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
        panel.setTitle_(tr("app.title"))
        panel.setFloatingPanel_(True)

        content = panel.contentView()
        margin = 16

        info = NSTextField.alloc().initWithFrame_(((margin, height - margin - 44), (width - margin * 2, 44)))
        info.setStringValue_(
            tr("wait.info", port=int(port))
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
        cancel_btn.setTitle_(tr("common.cancel"))
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
            self._show_error(tr("error.start_server", error=e))

    @objc.python_method
    def _show_error(self, text):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(tr("app.title"))
        alert.setInformativeText_(text)
        alert.addButtonWithTitle_(tr("common.ok"))
        try:
            alert.runModal()
        except Exception:
            print(text)

    def ToggleServer_(self, sender):
        """Start or stop the local FastMCP server from the status panel."""
        if getattr(self, "_stopping_server", False):
            return
        if self._server_is_running():
            self.StopServer_(sender)
            return
        self.StartServer_(sender)

    def StartServer_(self, sender):
        """Start the local FastMCP server on the configured localhost port."""
        if getattr(self, "_stopping_server", False):
            return
        if self._server_is_running():
            self._refresh_status_panel_if_visible()
            return

        port = int(self.default_port)
        if not is_port_available(port, host="127.0.0.1"):
            action, _ = self._prompt_when_default_port_busy()
            if action == "wait":
                self._begin_wait_for_port_and_start(port, sender)
            return

        try:
            self._start_server_on_port(port, sender)
        except Exception as e:
            print("Failed to start server: {}".format(e))
            self._show_error(tr("error.start_server", error=e))

    def StopServer_(self, sender):
        """Request a graceful shutdown of the embedded MCP HTTP server."""
        if getattr(self, "_stopping_server", False):
            return

        thread = getattr(self, "_server_thread", None)
        server = getattr(self, "_server", None)
        if not is_thread_running(thread):
            self._finish_stop_server()
            return
        if server is None:
            self._show_error(tr("error.stop_server", error="missing server handle"))
            return

        self._stopping_server = True
        try:
            if server is not None:
                server.should_exit = True
        except Exception as e:
            self._stopping_server = False
            self._show_error(tr("error.stop_server", error=e))
            return

        self._refresh_status_panel_if_visible()
        self._begin_stop_poll()

    @objc.python_method
    def _begin_stop_poll(self):
        if getattr(self, "_stop_timer", None) is not None:
            return
        self._stop_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.2, self, "StopPoll:", None, True
        )

    def StopPoll_(self, timer):
        thread = getattr(self, "_server_thread", None)
        if is_thread_running(thread):
            return
        self._finish_stop_server()

    @objc.python_method
    def _finish_stop_server(self):
        timer = getattr(self, "_stop_timer", None)
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        self._stop_timer = None
        self._stopping_server = False
        self._server = None
        self._server_thread = None
        self._port = None
        self._refresh_status_panel_if_visible()

    def ShowStatusWindow_(self, sender):
        """Open a small floating window with server status and endpoint."""
        try:
            self._ensure_status_panel()
            self._refresh_status_panel()
            self._status_panel.makeKeyAndOrderFront_(None)
            self._refresh_status_panel()
        except Exception as e:
            self._show_error(tr("error.open_status_window", error=e))

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
    def _mark_server_starting(self):
        self._starting_server = True
        self._activity_text = tr("status.starting")
        self._activity_state = "starting"
        self._refresh_status_panel_if_visible()

    @objc.python_method
    def _finish_server_starting_soon(self):
        timer = getattr(self, "_starting_timer", None)
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        self._starting_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.35, self, "StartingPoll:", None, False
        )

    def StartingPoll_(self, timer):
        self._finish_server_starting()

    @objc.python_method
    def _finish_server_starting(self, error=None):
        timer = getattr(self, "_starting_timer", None)
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        self._starting_timer = None
        self._starting_server = False

        if error is not None:
            self._activity_text = "Error: {}".format(error)
            self._activity_state = "error"
        elif self._server_is_running() and getattr(self, "_activity_state", None) == "starting":
            self._activity_text = tr("activity.idle")
            self._activity_state = "idle"

        self._refresh_status_panel_if_visible()

    @objc.python_method
    def _record_activity(self, message, state="ok"):
        text = str(message or "").strip() or tr("activity.idle")
        self._activity_text = text
        self._activity_state = str(state or "ok")
        self._schedule_status_refresh()

    @objc.python_method
    def _schedule_status_refresh(self):
        try:
            NSOperationQueue.mainQueue().addOperationWithBlock_(
                lambda: self._refresh_status_panel_if_visible()
            )
        except Exception:
            try:
                self._refresh_status_panel_if_visible()
            except Exception:
                pass

    @objc.python_method
    def _quiet_text_field(self, frame, value="", selectable=False, bold=False, size=13):
        field = NSTextField.alloc().initWithFrame_(frame)
        field.setStringValue_(value)
        field.setEditable_(False)
        field.setSelectable_(bool(selectable))
        field.setBordered_(False)
        field.setDrawsBackground_(False)
        try:
            font = AppKit.NSFont.boldSystemFontOfSize_(size) if bold else AppKit.NSFont.systemFontOfSize_(size)
            field.setFont_(font)
        except Exception:
            pass
        return field

    @objc.python_method
    def _small_icon_button(self, frame, symbol, fallback, tooltip, action):
        button = NSButton.alloc().initWithFrame_(frame)
        button.setTitle_(fallback)
        button.setTarget_(self)
        button.setAction_(action)
        try:
            button.setToolTip_(tooltip)
        except Exception:
            pass
        try:
            button.setBordered_(False)
        except Exception:
            pass
        try:
            image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol, tooltip)
            if image is not None:
                button.setImage_(image)
                button.setTitle_("")
        except Exception:
            pass
        return button

    @objc.python_method
    def _status_color(self, state):
        color_names = {
            "running": ("systemGreenColor", "greenColor"),
            "starting": ("systemBlueColor", "blueColor"),
            "waiting": ("systemBlueColor", "blueColor"),
            "stopping": ("systemBlueColor", "blueColor"),
            "error": ("systemRedColor", "redColor"),
            "stopped": ("systemGrayColor", "grayColor"),
            "idle": ("secondaryLabelColor", "grayColor"),
            "ok": ("secondaryLabelColor", "grayColor"),
        }
        preferred, fallback = color_names.get(state, ("secondaryLabelColor", "grayColor"))
        for name in (preferred, fallback):
            try:
                method = getattr(AppKit.NSColor, name)
                return method()
            except Exception:
                pass
        return None

    @objc.python_method
    def _status_state_is_pulsing(self, state):
        return state in ("starting", "waiting", "stopping")

    @objc.python_method
    def _update_status_dot_pulse(self, state):
        panel = getattr(self, "_status_panel", None)
        visible = False
        try:
            visible = bool(panel is not None and panel.isVisible())
        except Exception:
            visible = False

        if visible and self._status_state_is_pulsing(state):
            self._start_status_dot_pulse()
        else:
            self._stop_status_dot_pulse()

    @objc.python_method
    def _start_status_dot_pulse(self):
        if getattr(self, "_status_dot_pulse_timer", None) is not None:
            return
        self._status_dot_pulse_dim = False
        self._status_dot_pulse_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.55, self, "PulseStatusDot:", None, True
        )

    def PulseStatusDot_(self, timer):
        panel = getattr(self, "_status_panel", None)
        try:
            if panel is None or not panel.isVisible():
                self._stop_status_dot_pulse()
                return
        except Exception:
            self._stop_status_dot_pulse()
            return

        dot = getattr(self, "_status_dot_field", None)
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
        dot = getattr(self, "_status_dot_field", None)
        if dot is not None:
            try:
                dot.setAlphaValue_(1.0)
            except Exception:
                pass

    @objc.python_method
    def _ensure_status_panel(self):
        if hasattr(self, "_status_panel") and self._status_panel is not None:
            return

        width = 368
        height = 300
        rect = ((0, 0), (width, height))
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskUtilityWindow
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        panel.setTitle_("{} {}".format(tr("app.title"), get_runtime_label()))
        panel.setFloatingPanel_(True)

        content = panel.contentView()
        margin = 18
        row_h = 20
        icon_w = 22
        icon_gap = 4
        center_x = width / 2.0

        endpoint_y = height - 48
        endpoint_x = margin + 12
        endpoint_value_w = width - endpoint_x - margin - icon_w - icon_gap
        endpoint_value = self._quiet_text_field(
            ((endpoint_x, endpoint_y), (endpoint_value_w, row_h)),
            "",
            selectable=True,
            bold=True,
            size=10,
        )
        content.addSubview_(endpoint_value)

        endpoint_copy_button = self._small_icon_button(
            ((endpoint_x + endpoint_value_w + icon_gap, endpoint_y - 1), (icon_w, icon_w)),
            "doc.on.doc",
            "C",
            tr("copy.tooltip"),
            self.CopyEndpoint_,
        )
        content.addSubview_(endpoint_copy_button)

        dot_w = 24
        dot_y = height - 114
        status_dot = self._quiet_text_field(
            ((center_x - dot_w / 2.0, dot_y), (dot_w, row_h + 4)),
            "●",
            selectable=False,
            size=18,
        )
        try:
            status_dot.setAlignment_(getattr(AppKit, "NSTextAlignmentCenter", 2))
        except Exception:
            pass
        content.addSubview_(status_dot)

        server_button_w = 78
        server_button_h = 30
        server_button_y = dot_y - 36
        server_button = NSButton.alloc().initWithFrame_(
            ((center_x - server_button_w / 2.0, server_button_y), (server_button_w, server_button_h))
        )
        server_button.setTarget_(self)
        server_button.setAction_(self.ToggleServer_)
        content.addSubview_(server_button)

        controls_y = 74
        activity_y = controls_y + 38
        activity_w = width - margin * 2
        activity_value = self._quiet_text_field(
            ((margin, activity_y), (activity_w, row_h)),
            tr("activity.idle"),
            selectable=True,
            size=12,
        )
        try:
            activity_value.setAlignment_(getattr(AppKit, "NSTextAlignmentCenter", 2))
        except Exception:
            pass
        content.addSubview_(activity_value)

        port_label = self._quiet_text_field(
            ((margin, controls_y + 2), (34, row_h)),
            tr("port.label"),
            selectable=False,
            size=11,
        )
        content.addSubview_(port_label)

        port_field_w = 58
        port_field = NSTextField.alloc().initWithFrame_(((margin + 36, controls_y - 2), (port_field_w, row_h + 4)))
        port_field.setEditable_(True)
        port_field.setSelectable_(True)
        try:
            formatter = NSNumberFormatter.alloc().init()
            formatter.setAllowsFloats_(False)
            port_field.setFormatter_(formatter)
        except Exception:
            pass
        port_field.setTarget_(self)
        port_field.setAction_(self.ChangePort_)
        content.addSubview_(port_field)

        port_button = NSButton.alloc().initWithFrame_(
            ((margin + 36 + port_field_w + 5, controls_y - 4), (42, row_h + 8))
        )
        port_button.setTitle_(tr("port.apply"))
        port_button.setTarget_(self)
        port_button.setAction_(self.ChangePort_)
        content.addSubview_(port_button)

        profile_label_x = margin + 36 + port_field_w + 5 + 42 + 10
        profile_x = profile_label_x
        profile_popup = NSPopUpButton.alloc().initWithFrame_(
            ((profile_x, controls_y - 3), (width - margin - profile_x, row_h + 7))
        )
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

        checkbox_y = 40
        debug_checkbox = NSButton.alloc().initWithFrame_(((margin + 110, checkbox_y), (150, 22)))
        debug_checkbox.setTitle_(tr("debug.short"))
        switch_type = getattr(AppKit, "NSSwitchButton", None) or getattr(AppKit, "NSButtonTypeSwitch", None)
        if switch_type is None:
            switch_type = 3
        try:
            debug_checkbox.setButtonType_(switch_type)
        except Exception:
            pass
        debug_checkbox.setTarget_(self)
        debug_checkbox.setAction_(self.ToggleDebugLogging_)
        content.addSubview_(debug_checkbox)

        autostart_checkbox = NSButton.alloc().initWithFrame_(((margin, checkbox_y), (104, 22)))
        autostart_checkbox.setTitle_(tr("autostart.short"))
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

        footer = self._quiet_text_field(
            ((margin, 13), (width - margin * 2, 18)),
            tr("feedback.footer"),
            selectable=False,
            size=10,
        )
        try:
            footer.setAlignment_(getattr(AppKit, "NSTextAlignmentCenter", 2))
        except Exception:
            pass
        try:
            color = self._status_color("idle")
            if color is not None:
                footer.setTextColor_(color)
        except Exception:
            pass
        content.addSubview_(footer)

        feedback_button = self._small_icon_button(
            ((width - margin - icon_w, 10), (icon_w, icon_w)),
            "info.circle",
            "i",
            tr("feedback.tooltip"),
            self.OpenFeedback_,
        )
        content.addSubview_(feedback_button)

        self._status_panel = panel
        self._status_dot_field = status_dot
        self._server_button = server_button
        self._activity_field = activity_value
        self._endpoint_field = endpoint_value
        self._port_field = port_field
        self._autostart_checkbox = autostart_checkbox
        self._tool_profile_popup = profile_popup
        self._debug_logging_checkbox = debug_checkbox

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
        version = get_runtime_label()
        tool_profile = self._selected_tool_profile_name()
        status_state = "running" if running else "stopped"
        status_value = tr("status." + status_text(running))

        try:
            if getattr(self, "_starting_server", False):
                status_state = "starting"
                status_value = tr("status.starting")
            elif getattr(self, "_stopping_server", False):
                status_state = "stopping"
                status_value = tr("status.stopping")
            elif getattr(self, "_waiting_for_port", False) and not running:
                status_state = "waiting"
                status_value = tr(
                    "status.waiting",
                    port=getattr(self, "_wait_target_port", self.default_port),
                )
            elif getattr(self, "_autostart_waiting", False) and not running:
                status_state = "waiting"
                status_value = tr(
                    "status.autostart_waiting",
                    port=int(
                        getattr(self, "_autostart_target_port", self.default_port)
                    ),
                )
            dot = getattr(self, "_status_dot_field", None)
            if dot is not None:
                dot.setStringValue_("●")
                try:
                    dot.setToolTip_(status_value)
                except Exception:
                    pass
                color = self._status_color(status_state)
                if color is not None:
                    dot.setTextColor_(color)
            self._update_status_dot_pulse(status_state)
        except Exception:
            pass
        try:
            button = getattr(self, "_server_button", None)
            if button is not None:
                if getattr(self, "_starting_server", False):
                    button.setTitle_(tr("server.starting"))
                    button.setEnabled_(False)
                elif getattr(self, "_stopping_server", False):
                    button.setTitle_(tr("server.stopping"))
                    button.setEnabled_(False)
                elif getattr(self, "_waiting_for_port", False) or getattr(self, "_autostart_waiting", False):
                    button.setTitle_(tr("server.start"))
                    button.setEnabled_(False)
                elif running:
                    button.setTitle_(tr("server.stop"))
                    button.setEnabled_(True)
                else:
                    button.setTitle_(tr("server.start"))
                    button.setEnabled_(True)
        except Exception:
            pass
        try:
            panel = getattr(self, "_status_panel", None)
            if panel is not None:
                panel.setTitle_("{} {}".format(tr("app.title"), version))
        except Exception:
            pass
        try:
            field = getattr(self, "_activity_field", None)
            if field is not None:
                activity_text = ""
                if getattr(self, "_starting_server", False):
                    activity_text = tr("status.starting")
                elif running:
                    activity_text = getattr(self, "_activity_text", tr("activity.idle")) or tr("activity.idle")
                field.setStringValue_(activity_text)
                color = self._status_color(getattr(self, "_activity_state", "idle"))
                if color is not None:
                    field.setTextColor_(color)
        except Exception:
            pass
        try:
            self._endpoint_field.setStringValue_(endpoint)
        except Exception:
            pass
        try:
            field = getattr(self, "_port_field", None)
            if field is not None:
                field.setStringValue_(str(int(self.default_port)))
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
        try:
            checkbox = getattr(self, "_debug_logging_checkbox", None)
            if checkbox is not None:
                state_on = getattr(AppKit, "NSControlStateValueOn", getattr(AppKit, "NSOnState", 1))
                state_off = getattr(AppKit, "NSControlStateValueOff", getattr(AppKit, "NSOffState", 0))
                checkbox.setState_(state_on if self._debug_logging_enabled() else state_off)
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

    def ChangePort_(self, sender):
        """Persist the default server port. Takes effect on next server start."""
        field = getattr(self, "_port_field", None)
        try:
            raw = field.stringValue() if field is not None else sender.stringValue()
            port = int(str(raw).strip())
        except Exception:
            self._show_error(tr("port.invalid"))
            self._refresh_status_panel_if_visible()
            return

        if not (1 <= port <= 65535):
            self._show_error(tr("port.invalid"))
            self._refresh_status_panel_if_visible()
            return

        self._set_configured_default_port(port)
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

    def ToggleDebugLogging_(self, sender):
        """Toggle verbose event logging (HTTP + SSE) for debugging."""
        enabled = False
        try:
            enabled = bool(int(sender.state()))
        except Exception:
            try:
                enabled = bool(sender.state())
            except Exception:
                enabled = self._debug_logging_enabled()

        self._set_debug_logging_enabled(enabled)
        try:
            set_debug_event_logging_enabled(enabled)
        except Exception:
            pass

        try:
            print("[Glyphs MCP][DebugLog] enabled={!r}".format(enabled))
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
            self._show_error(tr("error.open_docs", url=docs_url, error=e))

    def OpenFeedback_(self, sender):
        """Open the Glyphs MCP project page."""
        try:
            nsurl = NSURL.URLWithString_(PROJECT_URL)
            if nsurl is None:
                raise ValueError("Invalid URL")
            NSWorkspace.sharedWorkspace().openURL_(nsurl)
        except Exception as e:
            self._show_error(tr("error.open_feedback", url=PROJECT_URL, error=e))

    @objc.python_method
    def _show_server_status(self):
        """Show the current server status."""
        print(
            "Glyphs MCP Server is running on port {}.".format(getattr(self, '_port', '?'))
        )
        try:
            print("  Version: {}".format(get_plugin_version()))
            print("  Runtime ID: {}".format(get_runtime_info().get("runtimeId", "?")))
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
            "  To stop: click Stop in the Glyphs MCP Server status window."
        )

    @objc.python_method
    def _show_startup_message(self, port):
        """Show startup success message."""
        print("Glyphs MCP Server started successfully!")
        try:
            print("  Version: {}".format(get_plugin_version()))
            print("  Runtime ID: {}".format(get_runtime_info().get("runtimeId", "?")))
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
