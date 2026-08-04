# encoding: utf-8

from __future__ import division, print_function, unicode_literals
import json
import os
import time
import traceback
import uuid
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
from status_panel_helpers import (
    endpoint_for,
    is_thread_running,
    server_exit_kind,
    server_lifecycle_state,
    should_emit_start_success,
    should_show_start_failure_alert,
    status_text,
)
from i18n import tr
from tool_profiles import (
    PROFILE_EDIT,
    PROFILE_ORDER,
    enabled_tool_names,
    is_valid_profile_name,
    normalize_profile_name,
)
from update_checker import (
    UpdatePreferences,
    cached_update_result,
    fetch_update,
)
from update_helper import (
    OPT_IN_DEFAULTS_KEY as IN_APP_UPDATES_DEFAULTS_KEY,
    UpdateHelperError,
    cancel_prepare,
    glyphs_major_from_version,
    read_request_status,
    start_prepare,
    verified_stage_is_ready,
    verify_installed_helper,
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
AUTOMATIC_UPDATE_CHECK_DELAY_SECONDS = 5.0


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
        self._server = None
        self._server_thread = None
        self._server_thread_error = None
        self._server_was_ready = False
        self._startup_notify = False
        self._starting_server = False
        self._stopping_server = False
        self._starting_timer = None
        self._port = None
        self._update_preferences = UpdatePreferences(Glyphs.defaults)
        self._update_check_timer = None
        self._update_check_thread = None
        self._update_check_generation = 0
        self._update_state = "idle"
        self._update_latest_version = None
        self._update_release_url = None
        self._update_status_text = ""
        self._helper_probe = None
        self._helper_state = "unknown"
        self._helper_error = None
        self._helper_probe_generation = 0
        self._preparation_process = None
        self._preparation_timer = None
        self._preparation_request_id = None
        self._preparation_version = None
        self._preparation_glyphs_major = None

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
        self._restore_cached_update_state()

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
    def _update_checks_enabled(self):
        try:
            return bool(self._update_preferences.enabled)
        except Exception:
            return True

    @objc.python_method
    def _in_app_updates_opted_in(self):
        try:
            return bool(Glyphs.defaults[IN_APP_UPDATES_DEFAULTS_KEY])
        except Exception:
            return False

    @objc.python_method
    def _current_glyphs_major(self):
        return glyphs_major_from_version(getattr(Glyphs, "versionNumber", 4))

    @objc.python_method
    def _allow_development_update_helper(self):
        try:
            override = str(os.environ.get("GLYPHS_MCP_UPDATE_API_URL") or "")
            return (
                "+" in str(get_plugin_version())
                and (
                    override.startswith("http://127.0.0.1")
                    or override.startswith("http://localhost")
                )
            )
        except Exception:
            return False

    @objc.python_method
    def _cancel_preparation_timer(self):
        timer = getattr(self, "_preparation_timer", None)
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        self._preparation_timer = None

    @objc.python_method
    def _begin_helper_probe(self):
        if (
            not self._update_checks_enabled()
            or getattr(self, "_update_state", None) != "available"
            or not getattr(self, "_update_latest_version", None)
        ):
            return False
        if not self._in_app_updates_opted_in():
            self._helper_probe = None
            self._helper_state = "not_opted_in"
            self._helper_error = None
            self._refresh_status_panel_if_visible()
            return False

        thread = getattr(self, "_helper_probe_thread", None)
        if thread is not None and thread.is_alive():
            return False
        self._helper_probe_generation += 1
        generation = self._helper_probe_generation
        version = self._update_latest_version
        glyphs_major = self._current_glyphs_major()
        self._helper_state = "probing"
        self._helper_error = None
        self._refresh_status_panel_if_visible()

        def run_probe():
            probe = None
            failure = None
            ready = False
            try:
                probe = verify_installed_helper(
                    allow_development_signature=self._allow_development_update_helper()
                )
                ready = verified_stage_is_ready(
                    version,
                    glyphs_major,
                    allow_development_signature=self._allow_development_update_helper(),
                )
            except Exception as error:
                failure = error

            def finish():
                if generation != getattr(self, "_helper_probe_generation", 0):
                    return
                self._helper_probe_thread = None
                self._helper_probe = probe
                self._helper_error = failure
                self._helper_state = (
                    "ready" if ready else ("compatible" if probe is not None else "unavailable")
                )
                self._refresh_status_panel_if_visible()

            try:
                NSOperationQueue.mainQueue().addOperationWithBlock_(finish)
            except Exception:
                pass

        self._helper_probe_thread = threading.Thread(
            target=run_probe,
            name="GlyphsMCPUpdaterProbe",
            daemon=True,
        )
        self._helper_probe_thread.start()
        return True

    @objc.python_method
    def _begin_update_preparation(self):
        if (
            not self._update_checks_enabled()
            or not self._in_app_updates_opted_in()
            or getattr(self, "_helper_state", None)
            not in ("compatible", "error")
        ):
            return False
        version = getattr(self, "_update_latest_version", None)
        if not version:
            return False
        request_id = str(uuid.uuid4())
        glyphs_major = self._current_glyphs_major()
        self._preparation_request_id = request_id
        self._preparation_version = version
        self._preparation_glyphs_major = glyphs_major
        self._helper_state = "authorizing"
        self._helper_error = None
        self._refresh_status_panel_if_visible()

        def verify_and_start():
            process = None
            failure = None
            try:
                probe = verify_installed_helper(
                    allow_development_signature=self._allow_development_update_helper()
                )
                prior_probe = getattr(self, "_helper_probe", None)
                if prior_probe is None or probe.cdhash != prior_probe.cdhash:
                    raise UpdateHelperError("The updater helper changed after it was verified.")
                process = start_prepare(version, glyphs_major, request_id, path=probe.path)
            except Exception as error:
                failure = error

            def finish():
                if request_id != getattr(self, "_preparation_request_id", None):
                    if process is not None:
                        try:
                            cancel_prepare(process)
                        except Exception:
                            pass
                    return
                if failure is not None or process is None:
                    self._preparation_process = None
                    self._helper_state = "error"
                    self._helper_error = failure or UpdateHelperError(
                        "Could not start update preparation."
                    )
                    self._refresh_status_panel_if_visible()
                    return
                self._preparation_process = process
                self._helper_state = "resolving"
                self._cancel_preparation_timer()
                self._preparation_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    0.25,
                    self,
                    self.UpdatePreparationPoll_,
                    None,
                    True,
                )
                self._refresh_status_panel_if_visible()

            try:
                NSOperationQueue.mainQueue().addOperationWithBlock_(finish)
            except Exception:
                if process is not None:
                    try:
                        cancel_prepare(process)
                    except Exception:
                        pass

        threading.Thread(
            target=verify_and_start,
            name="GlyphsMCPUpdaterAuthorize",
            daemon=True,
        ).start()
        return True

    def UpdatePreparationPoll_(self, timer):
        request_id = getattr(self, "_preparation_request_id", None)
        version = getattr(self, "_preparation_version", None)
        glyphs_major = getattr(self, "_preparation_glyphs_major", None)
        process = getattr(self, "_preparation_process", None)
        if not request_id or not version or glyphs_major not in (3, 4):
            self._cancel_preparation_timer()
            return
        try:
            status = read_request_status(request_id, version, glyphs_major)
        except Exception as error:
            status = None
            if process is None or process.poll() is not None:
                self._helper_state = "error"
                self._helper_error = error
        if status is not None:
            phase = status.get("phase")
            if phase in ("resolving", "downloading", "verifying", "preparing"):
                self._helper_state = phase
            elif phase == "ready":
                self._cancel_preparation_timer()
                self._preparation_process = None
                if verified_stage_is_ready(
                    version,
                    glyphs_major,
                    allow_development_signature=self._allow_development_update_helper(),
                ):
                    self._helper_state = "ready"
                    self._helper_error = None
                else:
                    self._helper_state = "error"
                    self._helper_error = UpdateHelperError(
                        "The verified update receipt could not be validated."
                    )
            elif phase in ("failed", "cancelled"):
                self._cancel_preparation_timer()
                self._preparation_process = None
                self._helper_state = "compatible" if phase == "cancelled" else "error"
                self._helper_error = (
                    None
                    if phase == "cancelled"
                    else UpdateHelperError(
                        status.get("message") or "Update preparation failed."
                    )
                )
        elif process is not None and process.poll() is not None:
            self._cancel_preparation_timer()
            try:
                output = process.communicate()[0]
            except Exception:
                output = ""
            self._preparation_process = None
            self._helper_state = "error"
            self._helper_error = UpdateHelperError(
                str(output or "Update preparation ended unexpectedly.").strip()
            )
        self._refresh_status_panel_if_visible()

    @objc.python_method
    def _restore_cached_update_state(self):
        self._update_latest_version = None
        self._update_release_url = None
        self._update_status_text = ""
        if not self._update_checks_enabled():
            self._update_state = "disabled"
            return

        latest = None
        try:
            latest = self._update_preferences.latest_version
        except Exception:
            latest = None
        if not latest:
            self._update_state = "idle"
            return

        try:
            cached = cached_update_result(
                get_plugin_version(),
                latest,
                checked_at=(
                    self._update_preferences.last_checked_at
                    if self._update_preferences.last_checked_at is not None
                    else time.time()
                ),
            )
        except Exception:
            self._update_state = "idle"
            return

        if cached.update_available:
            self._update_state = "available"
            self._update_latest_version = cached.latest_version
            self._update_release_url = cached.release_url
            self._update_status_text = tr(
                "update.available",
                version=cached.latest_version,
            )
        else:
            self._update_state = "up_to_date"

    @objc.python_method
    def _cancel_update_check_timer(self):
        timer = getattr(self, "_update_check_timer", None)
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        self._update_check_timer = None

    @objc.python_method
    def _schedule_automatic_update_check(self):
        self._cancel_update_check_timer()
        if not self._update_checks_enabled():
            return
        try:
            if not self._update_preferences.check_is_due():
                return
        except Exception:
            pass
        self._update_check_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            AUTOMATIC_UPDATE_CHECK_DELAY_SECONDS,
            self,
            "AutomaticUpdateCheck:",
            None,
            False,
        )

    def AutomaticUpdateCheck_(self, timer):
        self._update_check_timer = None
        self._begin_update_check(manual=False, force=False)

    @objc.python_method
    def _begin_update_check(self, manual=False, force=False):
        if not self._update_checks_enabled():
            return False
        thread = getattr(self, "_update_check_thread", None)
        if thread is not None:
            try:
                if thread.is_alive():
                    return False
            except Exception:
                pass
        if not manual and not force:
            try:
                if not self._update_preferences.check_is_due():
                    return False
            except Exception:
                pass

        self._cancel_update_check_timer()
        self._update_check_generation += 1
        generation = self._update_check_generation
        self._update_state = "checking"
        self._update_status_text = tr("update.checking")
        try:
            self._update_preferences.record_attempt()
        except Exception:
            pass
        self._refresh_status_panel_if_visible()
        self._refresh_update_menu_item()

        def run_check():
            result = None
            failure = None
            try:
                result = fetch_update(get_plugin_version())
            except Exception as error:
                failure = error

            def finish():
                self._finish_update_check(
                    generation,
                    result,
                    failure,
                    bool(manual),
                )

            try:
                NSOperationQueue.mainQueue().addOperationWithBlock_(finish)
            except Exception:
                try:
                    print(
                        "[Glyphs MCP][Updates] Could not deliver update result: {}".format(
                            failure or "main queue unavailable"
                        )
                    )
                except Exception:
                    pass

        self._update_check_thread = threading.Thread(
            target=run_check,
            name="GlyphsMCPUpdateCheck",
            daemon=True,
        )
        self._update_check_thread.start()
        return True

    @objc.python_method
    def _finish_update_check(self, generation, result, failure, manual):
        if generation != getattr(self, "_update_check_generation", 0):
            return
        self._update_check_thread = None
        if not self._update_checks_enabled():
            return

        if failure is not None or result is None:
            if manual:
                self._update_state = "error"
                self._update_status_text = tr(
                    "update.error",
                    error=str(failure or "unknown error"),
                )
            else:
                self._restore_cached_update_state()
                try:
                    print(
                        "[Glyphs MCP][Updates] Background check failed: {}".format(
                            failure or "unknown error"
                        )
                    )
                except Exception:
                    pass
            self._refresh_status_panel_if_visible()
            self._refresh_update_menu_item()
            return

        try:
            self._update_preferences.record_result(result)
        except Exception:
            pass

        prior_version = getattr(self, "_update_latest_version", None)
        self._update_latest_version = result.latest_version
        self._update_release_url = result.release_url
        if result.update_available:
            if prior_version and prior_version != result.latest_version:
                self._helper_probe_generation += 1
                self._helper_probe = None
                self._helper_state = "unknown"
                self._helper_error = None
            self._update_state = "available"
            self._update_status_text = tr(
                "update.available",
                version=result.latest_version,
            )
            try:
                if self._update_preferences.should_notify(result.latest_version):
                    try:
                        Glyphs.showNotification(
                            tr("update.notification.title"),
                            tr(
                                "update.notification.message",
                                version=result.latest_version,
                            ),
                        )
                    finally:
                        self._update_preferences.mark_notified(
                            result.latest_version
                        )
            except Exception:
                pass
        else:
            self._update_state = "up_to_date"
            self._update_release_url = None
            self._update_status_text = tr("update.up_to_date") if manual else ""

        self._refresh_status_panel_if_visible()
        self._refresh_update_menu_item()
        if result.update_available and prior_version != result.latest_version:
            panel = getattr(self, "_status_panel", None)
            try:
                if panel is not None and panel.isVisible():
                    self._begin_helper_probe()
            except Exception:
                pass

    @objc.python_method
    def _refresh_update_menu_item(self):
        item = getattr(self, "menuItem", None)
        if item is None:
            return
        title = self.name_menu
        if (
            self._update_checks_enabled()
            and getattr(self, "_update_state", None) == "available"
        ):
            title = tr("menu.update_available", name=self.name_menu)
        try:
            item.setTitle_(title)
        except Exception:
            pass

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
        self._refresh_update_menu_item()
        self._schedule_automatic_update_check()

        try:
            self._maybe_autostart_on_launch()
        except Exception as error:
            self._handle_start_request_exception(
                error,
                self.default_port,
                show_alert=False,
            )

    @objc.python_method
    def _start_server_on_port(self, port, sender, notify=True):
        self._mark_server_starting()
        self._startup_notify = bool(notify)
        self._server_thread_error = None
        self._server_was_ready = False
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
                target=self._run_server_thread,
                args=(self._server,),
                daemon=True,
            )
            self._server_thread.start()
            self._port = port
        except Exception as error:
            self._handle_start_request_exception(
                error,
                port,
                show_alert=bool(notify),
            )
            return False

        try:
            self._begin_server_start_poll()
        except Exception as error:
            try:
                self._server.should_exit = True
            except Exception:
                pass
            self._handle_start_request_exception(
                error,
                port,
                show_alert=bool(notify),
            )
            return False
        self._refresh_status_panel_if_visible()
        return True

    @objc.python_method
    def _run_server_thread(self, server):
        error_detail = None
        try:
            server.run()
        except BaseException:
            error_detail = traceback.format_exc()
            self._server_thread_error = error_detail
        finally:
            try:
                NSOperationQueue.mainQueue().addOperationWithBlock_(
                    lambda: self._server_thread_did_exit(server, error_detail)
                )
            except Exception:
                if error_detail:
                    try:
                        print("[Glyphs MCP][Server] {}".format(error_detail))
                    except Exception:
                        pass

    @objc.python_method
    def _server_thread_did_exit(self, server, error_detail=None):
        if server is not getattr(self, "_server", None):
            return
        exit_kind = server_exit_kind(
            server_started=getattr(server, "started", False),
            was_ready=getattr(self, "_server_was_ready", False),
            stop_requested=getattr(self, "_stopping_server", False),
        )
        if exit_kind == "intentional":
            self._finish_stop_server()
            return

        port = self._current_port()
        message = tr(
            (
                "error.unexpected_exit"
                if exit_kind == "unexpected"
                else "error.startup_failed"
            ),
            port=port,
        )
        detail = error_detail or getattr(self, "_server_thread_error", None)
        if not detail:
            detail = (
                "Uvicorn server thread exited after readiness."
                if exit_kind == "unexpected"
                else "Uvicorn server thread exited before readiness."
            )
        self._record_server_failure(
            message,
            detail=detail,
            show_alert=should_show_start_failure_alert(
                getattr(self, "_startup_notify", False),
                exit_kind,
            ),
        )

    @objc.python_method
    def _log_server_failure(self, message, detail=None):
        text = "[Glyphs MCP][Server] {}".format(message)
        if detail:
            text = "{}\n{}".format(text, str(detail).rstrip())
        try:
            self.logError(text)
            return
        except Exception:
            pass
        try:
            print(text)
        except Exception:
            pass

    @objc.python_method
    def _record_server_failure(self, message, detail=None, show_alert=False):
        self._cancel_server_start_poll()
        self._starting_server = False
        self._stopping_server = False
        self._activity_text = str(message)
        self._activity_state = "error"
        self._log_server_failure(message, detail)
        self._server = None
        self._server_thread = None
        self._server_thread_error = None
        self._server_was_ready = False
        self._startup_notify = False
        self._port = None
        self._refresh_status_panel_if_visible()
        if show_alert:
            self._show_error(message)

    @objc.python_method
    def _handle_start_request_exception(self, error, port, show_alert=False):
        detail = traceback.format_exc()
        if detail.strip() == "NoneType: None":
            detail = "{}: {}".format(type(error).__name__, error)
        self._record_server_failure(
            tr("error.startup_failed", port=int(port)),
            detail=detail,
            show_alert=show_alert,
        )

    @objc.python_method
    def _maybe_autostart_on_launch(self):
        if not self._autostart_enabled():
            return
        if self._server_is_running() or getattr(self, "_starting_server", False):
            return
        if is_thread_running(getattr(self, "_server_thread", None)):
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
            except Exception as error:
                self._handle_start_request_exception(
                    error,
                    port,
                    show_alert=False,
                )
            return

        deadline = getattr(self, "_autostart_deadline", None)
        try:
            if deadline is not None and time.monotonic() > float(deadline):
                self._cancel_autostart_wait()
                self._record_server_failure(
                    tr("error.startup_failed", port=int(port)),
                    detail=(
                        "Auto-start timed out because port {} remained busy."
                    ).format(int(port)),
                    show_alert=False,
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
        except Exception as error:
            self._handle_start_request_exception(
                error,
                port,
                show_alert=True,
            )

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
        if (
            getattr(self, "_stopping_server", False)
            or getattr(self, "_starting_server", False)
        ):
            return
        if self._server_is_running():
            self.StopServer_(sender)
            return
        self.StartServer_(sender)

    def StartServer_(self, sender):
        """Start the local FastMCP server on the configured localhost port."""
        if (
            getattr(self, "_stopping_server", False)
            or getattr(self, "_starting_server", False)
        ):
            return
        if self._server_is_running():
            self._refresh_status_panel_if_visible()
            return
        if is_thread_running(getattr(self, "_server_thread", None)):
            return

        port = int(self.default_port)
        if not is_port_available(port, host="127.0.0.1"):
            action, _ = self._prompt_when_default_port_busy()
            if action == "wait":
                self._begin_wait_for_port_and_start(port, sender)
            return

        try:
            self._start_server_on_port(port, sender)
        except Exception as error:
            self._handle_start_request_exception(
                error,
                port,
                show_alert=True,
            )

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
        self._cancel_server_start_poll()
        timer = getattr(self, "_stop_timer", None)
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        self._stop_timer = None
        self._starting_server = False
        self._stopping_server = False
        self._server = None
        self._server_thread = None
        self._server_thread_error = None
        self._server_was_ready = False
        self._startup_notify = False
        self._port = None
        self._activity_text = tr("activity.idle")
        self._activity_state = "idle"
        self._refresh_status_panel_if_visible()

    def ShowStatusWindow_(self, sender):
        """Open a small floating window with server status and endpoint."""
        try:
            self._ensure_status_panel()
            self._refresh_status_panel()
            self._status_panel.makeKeyAndOrderFront_(None)
            self._refresh_status_panel()
            self._begin_helper_probe()
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
        return server_lifecycle_state(
            getattr(self, "_server", None),
            getattr(self, "_server_thread", None),
        ) == "running"

    @objc.python_method
    def _mark_server_starting(self):
        self._starting_server = True
        self._activity_text = tr("status.starting")
        self._activity_state = "starting"
        self._refresh_status_panel_if_visible()

    @objc.python_method
    def _begin_server_start_poll(self):
        timer = getattr(self, "_starting_timer", None)
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        self._starting_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.1, self, "StartingPoll:", None, True
        )

    def StartingPoll_(self, timer):
        server = getattr(self, "_server", None)
        thread = getattr(self, "_server_thread", None)
        state = server_lifecycle_state(server, thread)
        if state == "running":
            self._finish_server_starting()
            return
        if state == "stopped":
            self._server_thread_did_exit(
                server,
                getattr(self, "_server_thread_error", None),
            )
            return
        self._refresh_status_panel_if_visible()

    @objc.python_method
    def _cancel_server_start_poll(self):
        timer = getattr(self, "_starting_timer", None)
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        self._starting_timer = None

    @objc.python_method
    def _finish_server_starting(self):
        ready = self._server_is_running()
        if not should_emit_start_success(
            ready,
            getattr(self, "_server_was_ready", False),
        ):
            return

        self._cancel_server_start_poll()
        self._starting_server = False
        self._server_was_ready = True
        self._activity_text = tr("activity.idle")
        self._activity_state = "idle"

        port = self._current_port()
        if getattr(self, "_startup_notify", False):
            notify_server_started(port)
        self._startup_notify = False
        self._show_startup_message(port)

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

        width = 420
        height = 380
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

        update_banner_w = width - margin * 2
        update_banner_h = 54
        update_banner_y = height - 110
        update_banner = NSView.alloc().initWithFrame_(
            ((margin, update_banner_y), (update_banner_w, update_banner_h))
        )
        try:
            update_banner.setWantsLayer_(True)
            update_banner.layer().setCornerRadius_(9.0)
            background = AppKit.NSColor.systemGreenColor().colorWithAlphaComponent_(0.10)
            update_banner.layer().setBackgroundColor_(background.CGColor())
        except Exception:
            pass
        update_banner.setHidden_(True)
        content.addSubview_(update_banner)

        update_y = 7
        update_button_w = 106
        update_status = self._quiet_text_field(
            (
                (12, update_y),
                (update_banner_w - 24 - update_button_w - 8, 40),
            ),
            "",
            selectable=True,
            bold=True,
            size=11,
        )
        try:
            update_status.setUsesSingleLineMode_(False)
            update_status.cell().setWraps_(True)
            update_status.cell().setLineBreakMode_(
                getattr(AppKit, "NSLineBreakByWordWrapping", 0)
            )
        except Exception:
            pass
        update_banner.addSubview_(update_status)

        update_action_button = NSButton.alloc().initWithFrame_(
            (
                (update_banner_w - 12 - update_button_w, 13),
                (update_button_w, 28),
            )
        )
        update_action_button.setTitle_(tr("update.action"))
        update_action_button.setToolTip_(tr("update.action_tooltip"))
        update_action_button.setTarget_(self)
        update_action_button.setAction_(self.UpdateAction_)
        # This click is explicit consent for one exact displayed version.
        try:
            update_action_button.setBezelColor_(AppKit.NSColor.systemBlueColor())
        except Exception:
            pass
        try:
            update_action_button.setContentTintColor_(AppKit.NSColor.whiteColor())
        except Exception:
            pass
        update_banner.addSubview_(update_action_button)

        view_release_button = NSButton.alloc().initWithFrame_(
            (
                (update_banner_w - 12 - update_button_w, 13),
                (update_button_w, 28),
            )
        )
        view_release_button.setTitle_(tr("update.view_release"))
        view_release_button.setToolTip_(tr("update.view_release_tooltip"))
        view_release_button.setTarget_(self)
        view_release_button.setAction_(self.OpenUpdateRelease_)
        update_banner.addSubview_(view_release_button)

        dot_w = 24
        dot_y = height - 142
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

        controls_y = 126
        activity_y = controls_y + 38
        activity_w = width - margin * 2
        activity_value = self._quiet_text_field(
            ((margin, activity_y), (activity_w, 34)),
            tr("activity.idle"),
            selectable=True,
            size=11,
        )
        try:
            activity_value.setAlignment_(getattr(AppKit, "NSTextAlignmentCenter", 2))
        except Exception:
            pass
        try:
            activity_value.setUsesSingleLineMode_(False)
            activity_value.cell().setWraps_(True)
            activity_value.cell().setLineBreakMode_(
                getattr(AppKit, "NSLineBreakByWordWrapping", 0)
            )
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

        checkbox_y = 89
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

        update_controls_y = 49
        check_updates_button = NSButton.alloc().initWithFrame_(
            ((margin, update_controls_y), (112, 28))
        )
        check_updates_button.setTitle_(tr("update.check_now"))
        check_updates_button.setTarget_(self)
        check_updates_button.setAction_(self.CheckForUpdates_)
        content.addSubview_(check_updates_button)

        toggle_updates_button = NSButton.alloc().initWithFrame_(
            ((margin + 120, update_controls_y), (width - margin * 2 - 120, 28))
        )
        toggle_updates_button.setTarget_(self)
        toggle_updates_button.setAction_(self.ToggleUpdateChecks_)
        content.addSubview_(toggle_updates_button)

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
        self._update_banner = update_banner
        self._update_banner_width = update_banner_w
        self._update_status_field = update_status
        self._update_action_button = update_action_button
        self._view_release_button = view_release_button
        self._check_updates_button = check_updates_button
        self._toggle_updates_button = toggle_updates_button

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
            elif (
                not running
                and getattr(self, "_activity_state", None) == "error"
            ):
                status_state = "error"
                status_value = tr("status.error")
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
                elif (
                    running
                    or getattr(self, "_activity_state", None) == "error"
                ):
                    activity_text = getattr(self, "_activity_text", tr("activity.idle")) or tr("activity.idle")
                field.setStringValue_(activity_text)
                try:
                    field.setToolTip_(activity_text or None)
                except Exception:
                    pass
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
        try:
            checks_enabled = self._update_checks_enabled()
            checking = getattr(self, "_update_state", None) == "checking"
            helper_state = getattr(self, "_helper_state", "unknown")
            preparation_active = helper_state in (
                "authorizing",
                "resolving",
                "downloading",
                "verifying",
                "preparing",
                "cancelling",
            )
            check_button = getattr(self, "_check_updates_button", None)
            if check_button is not None:
                check_button.setEnabled_(
                    bool(checks_enabled and not checking and not preparation_active)
                )
                check_button.setTitle_(
                    tr("update.checking_short")
                    if checking
                    else tr("update.check_now")
                )

            toggle_button = getattr(self, "_toggle_updates_button", None)
            if toggle_button is not None:
                toggle_button.setTitle_(
                    tr("update.disable_checks")
                    if checks_enabled
                    else tr("update.enable_checks")
                )
                toggle_button.setEnabled_(True)

            update_text = (
                getattr(self, "_update_status_text", "")
                if checks_enabled
                else tr("update.disabled")
            )
            if checks_enabled and getattr(self, "_update_state", None) == "available":
                if helper_state in ("probing", "authorizing", "resolving"):
                    update_text = tr("update.preparing")
                elif helper_state == "downloading":
                    update_text = tr("update.downloading")
                elif helper_state == "verifying":
                    update_text = tr("update.verifying")
                elif helper_state == "preparing":
                    update_text = tr("update.preparing")
                elif helper_state == "cancelling":
                    update_text = tr("update.cancelling")
                elif helper_state == "ready":
                    update_text = tr(
                        "update.verified_not_installed",
                        version=getattr(self, "_update_latest_version", ""),
                    )
                elif helper_state == "error":
                    update_text = tr(
                        "update.preparation_error",
                        error=str(
                            getattr(self, "_helper_error", None)
                            or "unknown error"
                        )[:400],
                    )
            update_field = getattr(self, "_update_status_field", None)
            if update_field is not None:
                update_field.setStringValue_(update_text)
                update_field.setHidden_(not bool(update_text))
                try:
                    update_field.setToolTip_(update_text or None)
                except Exception:
                    pass
                update_color_state = "error" if helper_state == "error" else "idle"
                color = self._status_color(update_color_state)
                if getattr(self, "_update_state", None) == "available" and helper_state != "error":
                    try:
                        color = AppKit.NSColor.labelColor()
                    except Exception:
                        color = self._status_color("running")
                if color is not None:
                    update_field.setTextColor_(color)

            update_button = getattr(self, "_update_action_button", None)
            update_available = bool(
                checks_enabled
                and getattr(self, "_update_state", None) == "available"
                and getattr(self, "_update_release_url", None)
            )
            show_update = False
            show_cancel = False
            if update_button is not None:
                show_update = bool(
                    update_available
                    and helper_state in ("compatible", "error")
                    and self._in_app_updates_opted_in()
                )
                show_cancel = bool(
                    update_available
                    and helper_state
                    in (
                        "authorizing",
                        "resolving",
                        "downloading",
                        "verifying",
                        "preparing",
                        "cancelling",
                    )
                )
                update_button.setHidden_(not (show_update or show_cancel))
                update_button.setEnabled_(show_update or (show_cancel and helper_state != "cancelling"))
                update_button.setTitle_(
                    tr("common.cancel")
                    if show_cancel
                    else (
                        tr("update.retry")
                        if helper_state == "error"
                        else tr("update.action")
                    )
                )
                update_button.setToolTip_(tr("update.action_tooltip"))
            release_button = getattr(self, "_view_release_button", None)
            show_release = False
            if release_button is not None:
                show_release = bool(
                    update_available
                    and helper_state in ("not_opted_in", "unavailable", "error", "ready")
                )
                release_button.setHidden_(not show_release)
                release_button.setEnabled_(show_release)

            banner = getattr(self, "_update_banner", None)
            if banner is not None:
                banner.setHidden_(not bool(update_text))
                try:
                    banner_color_name = (
                        "systemRedColor"
                        if helper_state == "error" or getattr(self, "_update_state", None) == "error"
                        else (
                            "systemGreenColor"
                            if getattr(self, "_update_state", None) == "available"
                            else "secondaryLabelColor"
                        )
                    )
                    banner_color = getattr(AppKit.NSColor, banner_color_name)()
                    banner_color = banner_color.colorWithAlphaComponent_(0.10)
                    banner.layer().setBackgroundColor_(banner_color.CGColor())
                except Exception:
                    pass

            banner_w = getattr(self, "_update_banner_width", 384)
            button_w = 106
            button_x = banner_w - 12 - button_w
            label_w = banner_w - 24 - button_w - 8
            if show_update and show_release:
                release_x = button_x - 8 - button_w
                label_w = max(80, release_x - 20)
            else:
                release_x = button_x
                if not (show_update or show_cancel or show_release):
                    label_w = banner_w - 24
            try:
                if update_field is not None:
                    update_field.setFrame_(((12, 7), (label_w, 40)))
                if update_button is not None:
                    update_button.setFrame_(((button_x, 13), (button_w, 28)))
                if release_button is not None:
                    release_button.setFrame_(((release_x, 13), (button_w, 28)))
            except Exception:
                pass
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
            except Exception as error:
                self._handle_start_request_exception(
                    error,
                    self.default_port,
                    show_alert=False,
                )

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

    def CheckForUpdates_(self, sender):
        """Run a user-requested update metadata check."""
        if not self._update_checks_enabled():
            return
        if getattr(self, "_helper_state", None) in (
            "authorizing",
            "resolving",
            "downloading",
            "verifying",
            "preparing",
            "cancelling",
        ):
            return
        self._begin_update_check(manual=True, force=True)

    def ToggleUpdateChecks_(self, sender):
        """Enable or disable notification-only update checks."""
        enabled = not self._update_checks_enabled()
        try:
            self._update_preferences.set_enabled(enabled)
        except Exception:
            return

        self._cancel_update_check_timer()
        self._update_check_generation += 1
        self._update_check_thread = None
        if enabled:
            self._restore_cached_update_state()
            self._begin_update_check(manual=False, force=True)
        else:
            process = getattr(self, "_preparation_process", None)
            if process is not None:
                try:
                    cancel_prepare(process)
                except Exception:
                    pass
            self._cancel_preparation_timer()
            self._helper_probe_generation += 1
            self._update_state = "disabled"
            self._update_latest_version = None
            self._update_release_url = None
            self._update_status_text = ""
            self._refresh_status_panel_if_visible()
            self._refresh_update_menu_item()

    def UpdateAction_(self, sender):
        """Authorize or cancel preparation for the exact displayed release."""
        state = getattr(self, "_helper_state", None)
        if state in (
            "authorizing",
            "resolving",
            "downloading",
            "verifying",
            "preparing",
            "cancelling",
        ):
            if state == "cancelling":
                return
            process = getattr(self, "_preparation_process", None)
            if process is not None:
                try:
                    cancel_prepare(process)
                    self._helper_state = "cancelling"
                except Exception as error:
                    self._helper_state = "error"
                    self._helper_error = error
            else:
                self._preparation_request_id = None
                self._helper_state = "compatible"
            self._refresh_status_panel_if_visible()
            return
        self._begin_update_preparation()

    def OpenUpdateRelease_(self, sender):
        """Open the exact trusted GitHub release page for the cached update."""
        release_url = getattr(self, "_update_release_url", None)
        if not release_url:
            return
        try:
            nsurl = NSURL.URLWithString_(release_url)
            if nsurl is None:
                raise ValueError("Invalid URL")
            NSWorkspace.sharedWorkspace().openURL_(nsurl)
        except Exception as error:
            self._show_error(
                tr(
                    "error.open_update",
                    url=release_url,
                    error=error,
                )
            )

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
