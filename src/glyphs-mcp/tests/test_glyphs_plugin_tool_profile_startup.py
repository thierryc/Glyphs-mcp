"""Fail-closed startup tests for restricted Glyphs MCP tool profiles."""

from __future__ import annotations

import importlib.util
import asyncio
import gc
import sys
import threading as stdlib_threading
import types
import unittest
import warnings
from pathlib import Path
from unittest import mock


def _module_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
        / "glyphs_plugin.py"
    )


class _FakeMCP:
    def __init__(self, events):
        self.events = events
        self.http_calls = []

    def http_app(self, **kwargs):
        self.events.append("http_app")
        self.http_calls.append(kwargs)
        return object()


class _FakeConfig:
    def __init__(self, app, **kwargs):
        self.app = app
        self.kwargs = kwargs


class _FakeServer:
    def __init__(self, config):
        self.config = config
        self.should_exit = False


class _FakeThread:
    def __init__(self, target, args, daemon):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True


def _load_plugin_module(mcp):
    class _GlyphsStub:
        defaults = {}
        menu = {1: []}

    appkit = types.ModuleType("AppKit")
    for name in (
        "NSAlert",
        "NSMenuItem",
        "NSPanel",
        "NSButton",
        "NSProgressIndicator",
        "NSPasteboard",
        "NSTextField",
        "NSPopUpButton",
        "NSView",
        "NSWorkspace",
    ):
        setattr(appkit, name, object)
    appkit.NSAlertFirstButtonReturn = 1
    appkit.NSPasteboardTypeString = "public.utf8-plain-text"
    appkit.NSWindowStyleMaskTitled = 1
    appkit.NSWindowStyleMaskClosable = 2
    appkit.NSWindowStyleMaskUtilityWindow = 4
    appkit.NSBackingStoreBuffered = 2

    foundation = types.ModuleType("Foundation")
    foundation.NSNumberFormatter = object
    foundation.NSOperationQueue = object
    foundation.NSTimer = object
    foundation.NSURL = object

    glyphs_app = types.ModuleType("GlyphsApp")
    glyphs_app.Glyphs = _GlyphsStub
    glyphs_app.EDIT_MENU = 1
    glyphs_plugins = types.ModuleType("GlyphsApp.plugins")
    glyphs_plugins.GeneralPlugin = object

    objc = types.ModuleType("objc")
    objc.python_method = lambda function: function

    middleware = types.ModuleType("starlette.middleware")
    middleware.Middleware = object

    modules = {
        "objc": objc,
        "AppKit": appkit,
        "Foundation": foundation,
        "GlyphsApp": glyphs_app,
        "GlyphsApp.plugins": glyphs_plugins,
        "uvicorn": types.ModuleType("uvicorn"),
        "starlette": types.ModuleType("starlette"),
        "starlette.middleware": middleware,
        "mcp_tools": types.SimpleNamespace(mcp=mcp),
        "security": types.SimpleNamespace(
            McpErrorEnvelopeMiddleware=object,
            McpNormalizeMcpPathMiddleware=object,
            McpNoOAuthWellKnownMiddleware=object,
            McpDiscoveryMiddleware=object,
            OriginValidationMiddleware=object,
            StaticTokenAuthMiddleware=object,
        ),
        "debug_event_logging": types.SimpleNamespace(
            McpDebugEventLoggingMiddleware=object,
            set_enabled=lambda _enabled: None,
        ),
        "status_panel_helpers": types.SimpleNamespace(
            endpoint_for=lambda port: "http://127.0.0.1:{}".format(port),
            is_thread_running=lambda _thread: False,
            server_exit_kind=lambda **_kwargs: "intentional",
            server_lifecycle_state=lambda *_args, **_kwargs: "stopped",
            should_emit_start_success=lambda *_args, **_kwargs: False,
            should_show_start_failure_alert=lambda *_args, **_kwargs: False,
            status_text=lambda running: "running" if running else "stopped",
        ),
        "i18n": types.SimpleNamespace(tr=lambda key, **_values: key),
        "tool_profiles": types.SimpleNamespace(
            PROFILE_EDIT="Edit",
            PROFILE_ORDER=("Read-only", "Edit"),
            enabled_tool_names=lambda _profile, names: set(names),
            is_valid_profile_name=lambda name: name in {"Read-only", "Edit"},
            normalize_profile_name=lambda name: name,
        ),
        "update_checker": types.SimpleNamespace(
            UpdatePreferences=object,
            cached_update_result=lambda *_args, **_kwargs: None,
            fetch_update=lambda *_args, **_kwargs: None,
        ),
        "update_helper": types.SimpleNamespace(
            OPT_IN_DEFAULTS_KEY="test.update.enabled",
            UpdateHelperError=RuntimeError,
            cancel_prepare=lambda *_args, **_kwargs: True,
            glyphs_major_from_version=lambda _version: 4,
            read_request_status=lambda *_args, **_kwargs: None,
            start_prepare=lambda *_args, **_kwargs: None,
            verified_stage_is_ready=lambda *_args, **_kwargs: False,
            verify_installed_helper=lambda *_args, **_kwargs: None,
        ),
        "utils": types.SimpleNamespace(
            get_known_tools=lambda: [],
            get_mcp_tool_registry=lambda _mcp: {},
            get_tool_info=lambda *_args: "",
            is_port_available=lambda *_args, **_kwargs: True,
            notify_server_started=lambda *_args, **_kwargs: None,
            replace_tool_registry_in_place=lambda *_args: None,
        ),
        "versioning": types.SimpleNamespace(
            get_docs_url_latest=lambda: "https://example.test/docs",
            get_plugin_version=lambda: "1.7.0",
            get_runtime_info=lambda: {},
            get_runtime_label=lambda: "1.7.0+test",
        ),
    }

    module_name = "glyphs_mcp_test_tool_profile_startup_{}".format(id(mcp))
    spec = importlib.util.spec_from_file_location(module_name, _module_path())
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    module.uvicorn = types.SimpleNamespace(Config=_FakeConfig, Server=_FakeServer)
    module.threading = types.SimpleNamespace(Thread=_FakeThread)
    return module


class ToolProfileStartupTests(unittest.TestCase):
    def _start(self, profile, apply_result, *, notify=True):
        events = []
        mcp = _FakeMCP(events)
        module = _load_plugin_module(mcp)
        plugin = module.MCPBridgePlugin()
        failures = []
        polls = []

        plugin._mark_server_starting = lambda: events.append("mark_starting")
        plugin._selected_tool_profile_name = lambda: profile

        def apply_profile(selected_profile):
            events.append("apply_profile")
            self.assertEqual(selected_profile, profile)
            if isinstance(apply_result, Exception):
                raise apply_result
            return apply_result

        plugin._apply_tool_profile_to_mcp_for_next_start = apply_profile
        plugin._http_middleware = lambda: []
        module._reset_sse_app_status_for_new_event_loop = (
            lambda: events.append("reset_sse") or True
        )
        plugin._handle_start_request_exception = (
            lambda error, port, show_alert=False: failures.append((error, port, show_alert))
        )
        plugin._begin_server_start_poll = lambda: polls.append(True)
        plugin._refresh_status_panel_if_visible = lambda: events.append("refresh")

        result = plugin._start_server_on_port(9680, None, notify=notify)
        return result, plugin, mcp, events, failures, polls

    def test_successful_restricted_filter_reaches_http_app(self):
        result, plugin, mcp, events, failures, polls = self._start("Read-only", True)

        self.assertTrue(result)
        self.assertEqual(len(mcp.http_calls), 1)
        self.assertLess(events.index("apply_profile"), events.index("http_app"))
        self.assertLess(events.index("reset_sse"), events.index("http_app"))
        self.assertEqual(failures, [])
        self.assertEqual(polls, [True])
        self.assertTrue(plugin._server_thread.started)

    def test_failed_restricted_filter_aborts_before_http_app(self):
        result, plugin, mcp, events, failures, polls = self._start("Read-only", False)

        self.assertFalse(result)
        self.assertEqual(mcp.http_calls, [])
        self.assertNotIn("http_app", events)
        self.assertIsNone(getattr(plugin, "_server_thread", None))
        self.assertEqual(polls, [])
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0][0], RuntimeError)
        self.assertIn("Read-only", str(failures[0][0]))
        self.assertEqual(failures[0][1:], (9680, True))

    def test_exceptional_restricted_filter_aborts_before_http_app(self):
        controlled_error = RuntimeError("controlled profile failure")
        result, plugin, mcp, events, failures, polls = self._start(
            "Read-only", controlled_error, notify=False
        )

        self.assertFalse(result)
        self.assertEqual(mcp.http_calls, [])
        self.assertNotIn("http_app", events)
        self.assertIsNone(getattr(plugin, "_server_thread", None))
        self.assertEqual(polls, [])
        self.assertEqual(failures, [(controlled_error, 9680, False)])

    def test_restricted_start_verifies_live_registry_before_http_app(self):
        events = []
        mcp = _FakeMCP(events)
        module = _load_plugin_module(mcp)
        registry = {"get_server_info": object(), "delete_glyph": object()}
        module.get_mcp_tool_registry = lambda _mcp: registry
        module.enabled_tool_names = lambda profile, _names: (
            {"get_server_info"} if profile == "Read-only" else set(registry)
        )
        def replace_with_wrong_key(registry_value, _filtered):
            retained = registry_value["delete_glyph"]
            registry_value.clear()
            registry_value["delete_glyph"] = retained

        module.replace_tool_registry_in_place = replace_with_wrong_key

        plugin = module.MCPBridgePlugin()
        plugin._tool_registry_ref = None
        plugin._tool_registry_snapshot = None
        failures = []
        plugin._mark_server_starting = lambda: events.append("mark_starting")
        plugin._selected_tool_profile_name = lambda: "Read-only"
        plugin._http_middleware = lambda: []
        plugin._handle_start_request_exception = (
            lambda error, port, show_alert=False: failures.append((error, port, show_alert))
        )

        result = plugin._start_server_on_port(9680, None)

        self.assertFalse(result)
        self.assertEqual(set(registry), {"delete_glyph"})
        self.assertEqual(mcp.http_calls, [])
        self.assertNotIn("http_app", events)
        self.assertIsNone(getattr(plugin, "_server_thread", None))
        self.assertEqual(len(failures), 1)

    def test_verified_restricted_registry_reaches_http_app(self):
        events = []
        mcp = _FakeMCP(events)
        module = _load_plugin_module(mcp)
        registry = {"get_server_info": object(), "delete_glyph": object()}
        module.get_mcp_tool_registry = lambda _mcp: registry
        module.enabled_tool_names = lambda profile, _names: (
            {"get_server_info"} if profile == "Read-only" else set(registry)
        )

        def replace_registry(registry_value, filtered):
            registry_value.clear()
            registry_value.update(filtered)

        module.replace_tool_registry_in_place = replace_registry

        plugin = module.MCPBridgePlugin()
        plugin._tool_registry_ref = None
        plugin._tool_registry_snapshot = None
        failures = []
        polls = []
        plugin._mark_server_starting = lambda: events.append("mark_starting")
        plugin._selected_tool_profile_name = lambda: "Read-only"
        plugin._http_middleware = lambda: []
        plugin._handle_start_request_exception = (
            lambda error, port, show_alert=False: failures.append((error, port, show_alert))
        )
        plugin._begin_server_start_poll = lambda: polls.append(True)
        plugin._refresh_status_panel_if_visible = lambda: events.append("refresh")

        result = plugin._start_server_on_port(9680, None)

        self.assertTrue(result)
        self.assertEqual(set(registry), {"get_server_info"})
        self.assertEqual(len(mcp.http_calls), 1)
        self.assertEqual(failures, [])
        self.assertEqual(polls, [True])
        self.assertTrue(plugin._server_thread.started)

    def test_edit_profile_remains_available_when_filtering_fails(self):
        for apply_result in (False, RuntimeError("controlled profile failure")):
            with self.subTest(apply_result=apply_result):
                result, plugin, mcp, events, failures, polls = self._start("Edit", apply_result)

                self.assertTrue(result)
                self.assertEqual(len(mcp.http_calls), 1)
                self.assertLess(events.index("apply_profile"), events.index("http_app"))
                self.assertEqual(failures, [])
                self.assertEqual(polls, [True])
                self.assertTrue(plugin._server_thread.started)

    def test_live_prior_server_thread_blocks_reset_and_new_http_app(self):
        events = []
        mcp = _FakeMCP(events)
        module = _load_plugin_module(mcp)
        active_thread = object()
        module.is_thread_running = lambda thread: thread is active_thread
        module._reset_sse_app_status_for_new_event_loop = (
            lambda: events.append("reset_sse") or True
        )

        plugin = module.MCPBridgePlugin()
        plugin._server_thread = active_thread

        result = plugin._start_server_on_port(9680, None)

        self.assertFalse(result)
        self.assertNotIn("reset_sse", events)
        self.assertNotIn("http_app", events)

    def test_sse_app_status_reset_clears_prior_loop_state(self):
        module = _load_plugin_module(_FakeMCP([]))
        event = object()
        app_status = types.SimpleNamespace(
            should_exit=True,
            should_exit_event=event,
        )
        sse_package = types.ModuleType("sse_starlette")
        sse_package.__path__ = []
        sse_module = types.ModuleType("sse_starlette.sse")
        sse_module.AppStatus = app_status

        with mock.patch.dict(
            sys.modules,
            {
                "sse_starlette": sse_package,
                "sse_starlette.sse": sse_module,
            },
        ):
            reset = module._reset_sse_app_status_for_new_event_loop()

        self.assertTrue(reset)
        self.assertFalse(app_status.should_exit)
        self.assertIsNone(app_status.should_exit_event)

    def test_sse_app_status_reset_tolerates_layout_without_app_status(self):
        module = _load_plugin_module(_FakeMCP([]))
        sse_package = types.ModuleType("sse_starlette")
        sse_package.__path__ = []
        sse_module = types.ModuleType("sse_starlette.sse")

        with mock.patch.dict(
            sys.modules,
            {
                "sse_starlette": sse_package,
                "sse_starlette.sse": sse_module,
            },
        ):
            reset = module._reset_sse_app_status_for_new_event_loop()

        self.assertFalse(reset)

    def test_real_fastmcp_initialize_survives_three_fresh_event_loop_threads(self):
        # Several compatibility tests install a lightweight FastMCP stand-in.
        # Temporarily import the pinned package from a clean module-cache view.
        saved_modules = {
            name: loaded
            for name, loaded in sys.modules.items()
            if name == "fastmcp" or name.startswith("fastmcp.")
        }
        for name in saved_modules:
            sys.modules.pop(name, None)

        module = _load_plugin_module(_FakeMCP([]))
        try:
            import fastmcp
            import httpx
            from fastmcp import FastMCP

            self.assertEqual(fastmcp.__version__, "2.12.0")
            server = FastMCP("Glyphs MCP restart lifecycle regression", version="1")

            @server.tool()
            def ping():
                return "pong"

            responses = []
            errors = []

            async def initialize_once(request_id):
                module._reset_sse_app_status_for_new_event_loop()
                app = server.http_app(path="/mcp/", transport="http")
                async with app.router.lifespan_context(app):
                    transport = httpx.ASGITransport(
                        app=app,
                        raise_app_exceptions=True,
                    )
                    async with httpx.AsyncClient(
                        transport=transport,
                        base_url="http://glyphs-mcp.test",
                        timeout=5,
                    ) as client:
                        response = await client.post(
                            "/mcp/",
                            headers={
                                "Accept": "application/json, text/event-stream",
                                "MCP-Protocol-Version": "2025-03-26",
                            },
                            json={
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "method": "initialize",
                                "params": {
                                    "protocolVersion": "2025-03-26",
                                    "capabilities": {},
                                    "clientInfo": {
                                        "name": "restart-regression",
                                        "version": "1",
                                    },
                                },
                            },
                        )
                        responses.append(
                            (
                                response.status_code,
                                bool(response.headers.get("mcp-session-id")),
                                response.text.startswith("event: message"),
                            )
                        )

            def run_in_fresh_thread(request_id):
                # mcp 1.12.4 can leave a closed in-memory receive stream for
                # cyclic collection after a test-only ASGI session ends.  It
                # is unrelated to the cross-loop assertion, so collect it in
                # this thread without leaking a ResourceWarning into neighbors.
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", ResourceWarning)
                    try:
                        asyncio.run(initialize_once(request_id))
                    except BaseException as error:
                        errors.append(error)
                    finally:
                        gc.collect()

            for request_id in (1, 2, 3):
                thread = stdlib_threading.Thread(
                    target=run_in_fresh_thread,
                    args=(request_id,),
                )
                thread.start()
                thread.join(10)
                self.assertFalse(thread.is_alive())

            self.assertEqual(errors, [])
            self.assertEqual(responses, [(200, True, True)] * 3)
        finally:
            module._reset_sse_app_status_for_new_event_loop()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                gc.collect()
            for name in list(sys.modules):
                if name == "fastmcp" or name.startswith("fastmcp."):
                    sys.modules.pop(name, None)
            sys.modules.update(saved_modules)


if __name__ == "__main__":
    unittest.main()
