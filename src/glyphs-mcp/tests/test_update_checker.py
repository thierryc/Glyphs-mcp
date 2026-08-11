"""Tests for notification-only GitHub update checks."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


def _module_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
        / "update_checker.py"
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_module():
    module_name = "glyphs_mcp_test_update_checker"
    spec = importlib.util.spec_from_file_location(module_name, _module_path())
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_plugin_module(update_checker):
    notifications = []
    opened_urls = []

    class GlyphsStub:
        defaults = {}
        menu = {1: []}

        @staticmethod
        def showNotification(title, message):
            notifications.append((title, message))

    class TimerStub:
        def invalidate(self):
            return None

    class TimerFactory:
        @staticmethod
        def scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            *_args,
        ):
            return TimerStub()

    class MainQueue:
        def addOperationWithBlock_(self, block):
            block()

    class URLStub:
        @staticmethod
        def URLWithString_(url):
            return url

    class WorkspaceStub:
        @classmethod
        def sharedWorkspace(cls):
            return cls()

        def openURL_(self, url):
            opened_urls.append(url)
            return True

    class PanelControllerStub:
        @classmethod
        def alloc(cls):
            return cls()

        def initWithPlugin_(self, _plugin):
            return self

        def show(self):
            return None

    foundation = types.ModuleType("Foundation")
    foundation.NSNumberFormatter = object
    foundation.NSOperationQueue = types.SimpleNamespace(
        mainQueue=lambda: MainQueue()
    )
    foundation.NSTimer = TimerFactory
    foundation.NSURL = URLStub

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
    ):
        setattr(appkit, name, object)
    appkit.NSWorkspace = WorkspaceStub
    appkit.NSAlertFirstButtonReturn = 1
    appkit.NSPasteboardTypeString = "public.utf8-plain-text"
    appkit.NSWindowStyleMaskTitled = 1
    appkit.NSWindowStyleMaskClosable = 2
    appkit.NSWindowStyleMaskUtilityWindow = 4
    appkit.NSBackingStoreBuffered = 2

    glyphs_app = types.ModuleType("GlyphsApp")
    glyphs_app.Glyphs = GlyphsStub
    glyphs_app.EDIT_MENU = 1
    glyphs_plugins = types.ModuleType("GlyphsApp.plugins")
    glyphs_plugins.GeneralPlugin = object

    objc = types.ModuleType("objc")
    objc.python_method = lambda function: function

    middleware = types.ModuleType("starlette.middleware")
    middleware.Middleware = object

    def tr(key, **values):
        if key == "update.available":
            return "available {}".format(values.get("version"))
        if key == "update.error":
            return "error {}".format(values.get("error"))
        if key == "menu.update_available":
            return "{} update".format(values.get("name"))
        if key == "update.verified_not_installed":
            return "ready {} but not installed".format(
                values.get("version")
            )
        return key

    modules = {
        "objc": objc,
        "AppKit": appkit,
        "Foundation": foundation,
        "GlyphsApp": glyphs_app,
        "GlyphsApp.plugins": glyphs_plugins,
        "uvicorn": types.ModuleType("uvicorn"),
        "starlette": types.ModuleType("starlette"),
        "starlette.middleware": middleware,
        "mcp_tools": types.SimpleNamespace(mcp=object()),
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
        "document_changes_panel": types.SimpleNamespace(
            DocumentChangesPanelController=PanelControllerStub,
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
        "i18n": types.SimpleNamespace(tr=tr),
        "update_checker": update_checker,
        "update_helper": types.SimpleNamespace(
            OPT_IN_DEFAULTS_KEY="com.ap.cx.glyphs-mcp.inAppUpdatesEnabled",
            UpdateHelperError=RuntimeError,
            cancel_prepare=lambda _process: True,
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
            is_port_available=lambda _port: True,
            notify_server_started=lambda *_args, **_kwargs: None,
            replace_tool_registry_in_place=lambda *_args: None,
        ),
        "versioning": types.SimpleNamespace(
            get_docs_url_latest=lambda: "https://example.test/docs",
            get_plugin_version=lambda: "1.5.4",
            get_runtime_info=lambda: {},
            get_runtime_label=lambda: "1.5.4+test",
        ),
    }

    module_name = "glyphs_mcp_test_glyphs_plugin_updates"
    spec = importlib.util.spec_from_file_location(
        module_name,
        _module_path().parent / "glyphs_plugin.py",
    )
    assert spec and spec.loader
    plugin_module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, modules):
        spec.loader.exec_module(plugin_module)
    plugin_module._test_opened_urls = opened_urls
    return plugin_module, GlyphsStub, notifications


class _Response:
    def __init__(self, payload, status=200):
        self.status = status
        self._data = (
            payload
            if isinstance(payload, bytes)
            else json.dumps(payload).encode("utf-8")
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self):
        return self.status

    def read(self, _limit):
        return self._data


class _ControlStub:
    def __init__(self):
        self.hidden = None
        self.enabled = None
        self.title = None
        self.value = None
        self.tooltip = None
        self.frame = None

    def setHidden_(self, value):
        self.hidden = bool(value)

    def setEnabled_(self, value):
        self.enabled = bool(value)

    def setTitle_(self, value):
        self.title = value

    def setStringValue_(self, value):
        self.value = value

    def setToolTip_(self, value):
        self.tooltip = value

    def setTextColor_(self, _value):
        return None

    def setFrame_(self, value):
        self.frame = value


class UpdateCheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_module()

    def stable_release(self, tag="v1.6.0", **overrides):
        payload = {
            "tag_name": tag,
            "draft": False,
            "prerelease": False,
            "published_at": "2026-07-29T12:00:00Z",
            "html_url": "https://attacker.invalid/not-trusted",
        }
        payload.update(overrides)
        return payload

    def test_compares_stable_semantic_versions(self):
        newer = self.module.parse_release_metadata(
            self.stable_release("v1.6.0"),
            "1.5.4",
            checked_at=100,
        )
        equal = self.module.parse_release_metadata(
            self.stable_release("v1.5.4"),
            "1.5.4",
            checked_at=100,
        )
        older = self.module.parse_release_metadata(
            self.stable_release("v1.5.3"),
            "1.5.4",
            checked_at=100,
        )

        self.assertTrue(newer.update_available)
        self.assertFalse(equal.update_available)
        self.assertFalse(older.update_available)
        self.assertEqual(newer.latest_version, "1.6.0")

    def test_derives_release_url_and_ignores_remote_html_url(self):
        result = self.module.parse_release_metadata(
            self.stable_release(),
            "1.5.4",
        )
        self.assertEqual(
            result.release_url,
            "https://github.com/thierryc/Glyphs-mcp/releases/tag/v1.6.0",
        )
        self.assertNotIn("attacker.invalid", result.release_url)

    def test_rejects_drafts_prereleases_and_malformed_versions(self):
        invalid_payloads = (
            self.stable_release(draft=True),
            self.stable_release(prerelease=True),
            self.stable_release(published_at=None),
            self.stable_release("1.6.0"),
            self.stable_release("v1.6.0-beta.1"),
            {"tag_name": "v1.6.0"},
            [],
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(self.module.UpdateCheckError):
                    self.module.parse_release_metadata(payload, "1.5.4")

        with self.assertRaises(self.module.UpdateCheckError):
            self.module.parse_release_metadata(
                self.stable_release(),
                "dev",
            )

    def test_fetch_uses_timeout_and_expected_headers(self):
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["accept"] = request.headers.get("Accept")
            captured["user_agent"] = request.headers.get("User-agent")
            return _Response(self.stable_release())

        result = self.module.fetch_update(
            "1.5.4",
            opener=opener,
            checked_at=200,
        )

        self.assertTrue(result.update_available)
        self.assertEqual(captured["url"], self.module.GITHUB_LATEST_RELEASE_API)
        self.assertEqual(captured["timeout"], 10)
        self.assertEqual(captured["accept"], "application/vnd.github+json")
        self.assertEqual(
            captured["user_agent"],
            self.module.UPDATE_USER_AGENT,
        )

    def test_live_qa_fixture_is_a_valid_available_release(self):
        fixture = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "github_latest_release_1.6.0.json"
        )
        result = self.module.parse_release_metadata(
            json.loads(fixture.read_text(encoding="utf-8")),
            "1.5.4",
        )
        self.assertTrue(result.update_available)
        self.assertEqual(result.latest_version, "1.6.0")
        self.assertEqual(
            result.release_url,
            "https://github.com/thierryc/Glyphs-mcp/releases/tag/v1.6.0",
        )

    def test_fetch_wraps_transport_and_json_errors(self):
        def broken_opener(_request, timeout):
            raise TimeoutError("offline after {}".format(timeout))

        with self.assertRaisesRegex(
            self.module.UpdateCheckError,
            "Could not retrieve",
        ):
            self.module.fetch_update("1.5.4", opener=broken_opener)

        with self.assertRaisesRegex(
            self.module.UpdateCheckError,
            "not valid UTF-8 JSON",
        ):
            self.module.fetch_update(
                "1.5.4",
                opener=lambda *_args, **_kwargs: _Response(b"{broken"),
            )

    def test_rejects_oversized_metadata(self):
        oversized = b"x" * (self.module.MAX_RELEASE_METADATA_BYTES + 1)
        with self.assertRaisesRegex(
            self.module.UpdateCheckError,
            "unexpectedly large",
        ):
            self.module.fetch_update(
                "1.5.4",
                opener=lambda *_args, **_kwargs: _Response(oversized),
            )

    def test_contributor_override_requires_https_or_loopback_http(self):
        self.assertEqual(
            self.module.update_api_url(
                {
                    self.module.UPDATE_API_URL_ENV:
                        "http://127.0.0.1:8765/latest"
                }
            ),
            "http://127.0.0.1:8765/latest",
        )
        self.assertEqual(
            self.module.update_api_url(
                {
                    self.module.UPDATE_API_URL_ENV:
                        "https://updates.example.test/latest"
                }
            ),
            "https://updates.example.test/latest",
        )
        for invalid in (
            "http://updates.example.test/latest",
            "file:///tmp/release.json",
            "https://user:password@example.test/latest",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(self.module.UpdateCheckError):
                    self.module.update_api_url(
                        {self.module.UPDATE_API_URL_ENV: invalid}
                    )

    def test_preferences_default_enabled_persist_and_throttle(self):
        store = {}
        preferences = self.module.UpdatePreferences(store)

        self.assertTrue(preferences.enabled)
        self.assertTrue(preferences.check_is_due(now=100))
        preferences.record_attempt(now=100)
        self.assertIsNone(preferences.last_checked_at)
        self.assertFalse(preferences.check_is_due(now=101))
        self.assertTrue(
            preferences.check_is_due(
                now=100 + self.module.UPDATE_CHECK_INTERVAL_SECONDS
            )
        )

        result = self.module.parse_release_metadata(
            self.stable_release(),
            "1.5.4",
            checked_at=100,
        )
        preferences.record_result(result)
        self.assertFalse(preferences.check_is_due(now=101))
        self.assertTrue(
            preferences.check_is_due(
                now=100 + self.module.UPDATE_CHECK_INTERVAL_SECONDS
            )
        )
        self.assertEqual(preferences.latest_version, "1.6.0")

        preferences.set_enabled(False)
        self.assertFalse(preferences.enabled)
        self.assertFalse(preferences.check_is_due(now=999999))
        preferences.set_enabled(True)
        self.assertTrue(preferences.enabled)

    def test_notification_is_recorded_once_per_version(self):
        preferences = self.module.UpdatePreferences({})
        self.assertTrue(preferences.should_notify("1.6.0"))
        preferences.mark_notified("1.6.0")
        self.assertFalse(preferences.should_notify("1.6.0"))
        self.assertTrue(preferences.should_notify("1.6.1"))

    def test_cached_result_preserves_offline_availability(self):
        result = self.module.cached_update_result(
            "1.5.4",
            "1.6.0",
            checked_at=123,
        )
        self.assertTrue(result.update_available)
        self.assertEqual(result.checked_at, 123)

    def test_plugin_integration_is_non_blocking_and_notification_only(self):
        plugin_text = (
            _module_path().parent / "glyphs_plugin.py"
        ).read_text(encoding="utf-8")

        self.assertIn("threading.Thread(", plugin_text)
        self.assertIn("NSOperationQueue.mainQueue().addOperationWithBlock_", plugin_text)
        self.assertIn('name="GlyphsMCPUpdateCheck"', plugin_text)
        self.assertIn("Glyphs.showNotification(", plugin_text)
        self.assertIn("self.CheckForUpdates_", plugin_text)
        self.assertIn("self.ToggleUpdateChecks_", plugin_text)
        self.assertIn("self.OpenUpdateRelease_", plugin_text)
        self.assertIn('setTitle_(tr("update.action"))', plugin_text)
        self.assertIn('setToolTip_(tr("update.action_tooltip"))', plugin_text)
        self.assertIn("setBezelColor_(AppKit.NSColor.systemBlueColor())", plugin_text)
        self.assertIn("setContentTintColor_(AppKit.NSColor.whiteColor())", plugin_text)
        self.assertIn("update_banner.addSubview_(update_status)", plugin_text)
        self.assertIn("update_banner.addSubview_(update_action_button)", plugin_text)
        self.assertIn("update_banner.addSubview_(view_release_button)", plugin_text)
        self.assertIn("systemGreenColor", plugin_text)
        self.assertNotIn('tr("update.installer_required")', plugin_text)
        self.assertIn('tr("update.disable_checks")', plugin_text)
        self.assertIn('tr("update.enable_checks")', plugin_text)
        self.assertIn("check_button.setEnabled_", plugin_text)
        self.assertIn("self._update_check_generation += 1", plugin_text)
        self.assertNotIn("download_update", plugin_text)
        self.assertNotIn("install_update", plugin_text)
        self.assertNotIn("GlyphsMCPInstaller.zip", plugin_text)
        self.assertNotIn("pip install", plugin_text)

    def test_staging_only_labels_are_explicit_across_product_surfaces(self):
        i18n_path = _module_path().parent / "i18n.py"
        module_name = "glyphs_mcp_test_update_labels"
        spec = importlib.util.spec_from_file_location(module_name, i18n_path)
        assert spec and spec.loader
        i18n = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(i18n)

        self.assertEqual(
            i18n.STRINGS["update.action"],
            {
                "en": "Prepare Update",
                "de": "Update vorbereiten",
                "fr": "Préparer la mise à jour",
                "es": "Preparar actualización",
                "pt": "Preparar atualização",
                "zh-Hans": "准备更新",
            },
        )
        ready = i18n.STRINGS["update.verified_not_installed"]["en"]
        self.assertIn("is ready", ready)
        self.assertIn("not installed", ready)
        self.assertNotIn("signed", ready)
        self.assertEqual(
            i18n.STRINGS["update.available"]["en"],
            "A new version is available: {version}.",
        )
        self.assertEqual(
            i18n.STRINGS["update.notification.message"]["en"],
            "Version {version} is available. Open Glyphs MCP Server to learn more.",
        )

        content_view = (
            _repo_root()
            / "macos-installer/GlyphsMCPInstaller/Sources/ContentView.swift"
        ).read_text(encoding="utf-8")
        installer_model = (
            _repo_root()
            / "macos-installer/GlyphsMCPInstaller/Sources/InstallerViewModel.swift"
        ).read_text(encoding="utf-8")
        terminal_installer = (
            _repo_root() / "src/glyphs-mcp/scripts/install_cli.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Make future updates easier", content_view)
        self.assertIn("install it when you’re ready", content_view)
        self.assertNotIn("Enable verified update preparation", content_view)
        self.assertIn("Set up future updates", installer_model)
        self.assertIn("Make future updates easier", terminal_installer)
        for path in (
            _repo_root() / "macos-installer/GlyphsMCPInstaller/Resources/en.lproj/Localizable.strings",
            _repo_root() / "macos-installer/GlyphsMCPInstaller/Resources/fr.lproj/Localizable.strings",
            _repo_root() / "macos-installer/GlyphsMCPInstaller/Resources/zh-Hans.lproj/Localizable.strings",
        ):
            localized = path.read_text(encoding="utf-8")
            self.assertIn("Make future updates easier", localized)
            self.assertIn("Set up future updates", localized)

    def test_all_update_strings_cover_every_plugin_language(self):
        i18n_path = _module_path().parent / "i18n.py"
        module_name = "glyphs_mcp_test_update_i18n"
        spec = importlib.util.spec_from_file_location(module_name, i18n_path)
        assert spec and spec.loader
        i18n = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(i18n)

        expected_languages = {"en", "de", "fr", "es", "pt", "zh-Hans"}
        update_keys = [
            key
            for key in i18n.STRINGS
            if key.startswith("update.") or key in {
                "menu.update_available",
                "error.open_update",
            }
        ]
        self.assertTrue(update_keys)
        for key in update_keys:
            with self.subTest(key=key):
                self.assertEqual(
                    set(i18n.STRINGS[key]),
                    expected_languages,
                )

    def test_update_toggle_defaults_on_persists_and_rechecks_when_enabled(self):
        plugin_module, glyphs, _notifications = _load_plugin_module(self.module)
        glyphs.defaults.clear()
        plugin = plugin_module.MCPBridgePlugin()
        plugin.settings()
        plugin._refresh_status_panel_if_visible = lambda: None
        plugin._refresh_update_menu_item = lambda: None
        checks = []
        plugin._begin_update_check = (
            lambda manual=False, force=False:
                checks.append((manual, force)) or True
        )

        self.assertTrue(plugin._update_checks_enabled())
        plugin.ToggleUpdateChecks_(None)
        self.assertFalse(plugin._update_checks_enabled())
        self.assertEqual(checks, [])

        restarted = plugin_module.MCPBridgePlugin()
        restarted.settings()
        self.assertFalse(restarted._update_checks_enabled())

        plugin.ToggleUpdateChecks_(None)
        self.assertTrue(plugin._update_checks_enabled())
        self.assertEqual(checks, [(False, True)])

    def test_available_update_notifies_once_and_persists_result(self):
        plugin_module, glyphs, notifications = _load_plugin_module(self.module)
        glyphs.defaults.clear()
        plugin = plugin_module.MCPBridgePlugin()
        plugin.settings()
        plugin._refresh_status_panel_if_visible = lambda: None
        plugin._refresh_update_menu_item = lambda: None
        result = self.module.parse_release_metadata(
            self.stable_release(),
            "1.5.4",
            checked_at=500,
        )

        plugin._finish_update_check(0, result, None, False)
        plugin._finish_update_check(0, result, None, False)

        self.assertEqual(plugin._update_state, "available")
        self.assertEqual(plugin._update_latest_version, "1.6.0")
        self.assertEqual(len(notifications), 1)
        self.assertEqual(
            glyphs.defaults[self.module.UPDATE_LATEST_VERSION_KEY],
            "1.6.0",
        )
        self.assertEqual(
            glyphs.defaults[self.module.UPDATE_LAST_CHECKED_AT_KEY],
            500,
        )

    def test_update_requires_explicit_action_before_opening_trusted_release(self):
        plugin_module, glyphs, _notifications = _load_plugin_module(self.module)
        glyphs.defaults.clear()
        plugin = plugin_module.MCPBridgePlugin()
        plugin.settings()
        plugin._refresh_status_panel_if_visible = lambda: None
        plugin._refresh_update_menu_item = lambda: None
        result = self.module.parse_release_metadata(
            self.stable_release(),
            "1.5.4",
            checked_at=500,
        )

        plugin._finish_update_check(0, result, None, False)
        self.assertEqual(plugin_module._test_opened_urls, [])

        plugin.OpenUpdateRelease_(None)
        self.assertEqual(
            plugin_module._test_opened_urls,
            ["https://github.com/thierryc/Glyphs-mcp/releases/tag/v1.6.0"],
        )

    def test_ready_stage_hides_prepare_and_keeps_trusted_release_available(self):
        plugin_module, glyphs, _notifications = _load_plugin_module(self.module)
        glyphs.defaults.clear()
        plugin = plugin_module.MCPBridgePlugin()
        plugin.settings()
        plugin._server_is_running = lambda: False
        plugin._current_port = lambda: 9680
        plugin._selected_tool_profile_name = lambda: "Edit"
        plugin._update_status_dot_pulse = lambda _state: None
        plugin._status_color = lambda _state: None
        plugin._update_state = "available"
        plugin._update_latest_version = "1.6.0"
        plugin._update_release_url = "https://github.com/thierryc/Glyphs-mcp/releases/tag/v1.6.0"
        plugin._update_status_text = "available 1.6.0"
        plugin._helper_state = "ready"
        plugin._update_action_button = _ControlStub()
        plugin._view_release_button = _ControlStub()
        plugin._update_status_field = _ControlStub()
        plugin._update_banner = _ControlStub()
        plugin._update_banner_width = 384

        plugin._refresh_status_panel()

        self.assertTrue(plugin._update_action_button.hidden)
        self.assertFalse(plugin._view_release_button.hidden)
        self.assertTrue(plugin._view_release_button.enabled)
        self.assertFalse(plugin._update_banner.hidden)
        self.assertEqual(
            plugin._view_release_button.frame,
            ((266, 13), (106, 28)),
        )
        self.assertEqual(
            plugin._update_status_field.value,
            "ready 1.6.0 but not installed",
        )

    def test_detection_never_prepares_and_one_update_action_authorizes_once(self):
        plugin_module, glyphs, _notifications = _load_plugin_module(self.module)
        glyphs.defaults.clear()
        plugin = plugin_module.MCPBridgePlugin()
        plugin.settings()
        plugin._refresh_status_panel_if_visible = lambda: None
        plugin._refresh_update_menu_item = lambda: None
        preparations = []
        plugin._begin_update_preparation = (
            lambda: preparations.append(
                (
                    plugin._update_latest_version,
                    plugin._current_glyphs_major(),
                )
            )
        )
        result = self.module.parse_release_metadata(
            self.stable_release(),
            "1.5.4",
            checked_at=500,
        )

        plugin._finish_update_check(0, result, None, False)
        self.assertEqual(preparations, [])

        plugin._helper_state = "compatible"
        plugin.UpdateAction_(None)
        self.assertEqual(preparations, [("1.6.0", 4)])


class ActivityStatusMiddlewareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.update_checker = _load_module()
        cls.plugin_module, _glyphs, _notifications = _load_plugin_module(
            cls.update_checker
        )

    def run_request(
        self,
        *,
        method="POST",
        path="/mcp/",
        status=200,
        headers=(),
        body=b'{"jsonrpc":"2.0","method":"initialize"}',
    ):
        activity = []

        async def app(_scope, receive, send):
            if method == "POST":
                while True:
                    message = await receive()
                    if not message.get("more_body", False):
                        break
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        request_sent = False

        async def receive():
            nonlocal request_sent
            if request_sent:
                return {"type": "http.disconnect"}
            request_sent = True
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }

        async def send(_message):
            return None

        middleware = self.plugin_module.McpActivityStatusMiddleware(
            app,
            recorder=lambda message, state="ok": activity.append(
                (message, state)
            ),
        )
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": list(headers),
        }
        asyncio.run(middleware(scope, receive, send))
        return activity

    def test_stale_session_404_is_a_neutral_reconnect(self):
        activity = self.run_request(
            status=404,
            headers=((b"mcp-session-id", b"stale-session"),),
        )

        self.assertEqual(
            activity,
            [("initialize", "active"), ("Client reconnecting", "ok")],
        )

    def test_session_cleanup_and_discovery_requests_are_not_visible(self):
        for method, path, headers in (
            (
                "DELETE",
                "/mcp/",
                ((b"mcp-session-id", b"stale-session"),),
            ),
            ("GET", "/.well-known/oauth-protected-resource", ()),
            ("GET", "/mcp/.well-known/oauth-protected-resource", ()),
            ("GET", "/mcp/", ((b"accept", b"text/html"),)),
        ):
            with self.subTest(method=method, path=path):
                self.assertEqual(
                    self.run_request(
                        method=method,
                        path=path,
                        status=404,
                        headers=headers,
                    ),
                    [],
                )

    def test_genuine_mcp_http_error_remains_visible(self):
        activity = self.run_request(status=500)

        self.assertEqual(
            activity,
            [("initialize", "active"), ("Error: HTTP 500", "error")],
        )

    def test_sse_request_remains_visible(self):
        activity = self.run_request(
            method="GET",
            status=200,
            headers=((b"accept", b"text/event-stream, application/json"),),
        )

        self.assertEqual(
            activity,
            [("GET /mcp/", "active"), ("GET /mcp/", "ok")],
        )


if __name__ == "__main__":
    unittest.main()
