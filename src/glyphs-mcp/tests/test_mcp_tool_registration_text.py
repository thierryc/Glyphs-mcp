"""Guards against shipping unregistered MCP tools.

These tests are intentionally text-based because the MCP tool module imports
GlyphsApp, which is not available in the normal unit test runner.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


def _tool_module_paths() -> list[Path]:
    resources = _resources_dir()
    return sorted(resources.glob("mcp_tools_*.py"))


class McpToolRegistrationTextTests(unittest.TestCase):
    def test_gscomponent_automatic_is_compat_safe(self) -> None:
        resources = _resources_dir()
        paths = [resources / "mcp_tool_helpers.py"] + _tool_module_paths()
        text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in paths if p.is_file())
        self.assertIsNone(
            re.search(r"\"automatic\"\\s*:\\s*component\\.automatic\\b", text),
            "Tool modules must not access GSComponent.automatic directly; use a compatibility helper.",
        )

    def _assert_async_tool_decorated(self, function_name: str) -> None:
        tool_files = _tool_module_paths()
        self.assertGreater(len(tool_files), 0, "Expected at least one mcp_tools_*.py tool module")

        found_path: Path | None = None
        found_lines: list[str] | None = None
        found_index: int | None = None

        for path in tool_files:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines):
                if re.match(rf"^\s*async def {re.escape(function_name)}\s*\(", line):
                    found_path = path
                    found_lines = lines
                    found_index = i
                    break
            if found_path is not None:
                break

        def strip_comment(line: str) -> str:
            return line.split("#", 1)[0].strip()

        def prev_significant_line(start_index: int) -> tuple[int, str] | tuple[None, None]:
            assert found_lines is not None
            for i in range(start_index - 1, -1, -1):
                s = strip_comment(found_lines[i])
                if not s:
                    continue
                return i, s
            return None, None

        self.assertIsNotNone(
            found_index,
            f"Expected to find async def {function_name}(...) in one of: {[p.name for p in tool_files]}",
        )
        assert found_index is not None
        assert found_path is not None

        i1, prev1 = prev_significant_line(found_index)
        self.assertEqual(
            prev1,
            "@mcp.tool()",
            f"{function_name} must be decorated with @mcp.tool() (found in {found_path.name})",
        )

        i2, prev2 = prev_significant_line(i1)  # type: ignore[arg-type]
        self.assertNotEqual(
            prev2,
            "@mcp.tool()",
            f"{function_name} must not be double-decorated with @mcp.tool() (found in {found_path.name})",
        )

    def test_set_spacing_params_is_decorated(self) -> None:
        self._assert_async_tool_decorated("set_spacing_params")

    def test_generate_kerning_tab_is_decorated(self) -> None:
        self._assert_async_tool_decorated("generate_kerning_tab")

    def test_list_style_sets_is_decorated(self) -> None:
        self._assert_async_tool_decorated("list_style_sets")

    def test_glyphs_show_bridge_route_is_registered(self) -> None:
        resources = _resources_dir()
        route_path = resources / "mcp_show_routes.py"
        text = route_path.read_text(encoding="utf-8", errors="replace")

        self.assertIn('@mcp.custom_route("/glyphs-show/", methods=["GET"]', text)
        self.assertIn("glyphs_show_bridge", text)

    def test_http_transport_uses_explicit_mcp_path(self) -> None:
        resources = _resources_dir()
        plugin_path = resources / "glyphs_plugin.py"
        text = plugin_path.read_text(encoding="utf-8", errors="replace")

        self.assertIn('transport="http"', text)
        self.assertIn('path="/mcp/"', text)

    def test_plugin_uses_single_menu_item_for_status_window(self) -> None:
        resources = _resources_dir()
        plugin_path = resources / "glyphs_plugin.py"
        text = plugin_path.read_text(encoding="utf-8", errors="replace")

        self.assertEqual(text.count("NSMenuItem.new()"), 1)
        self.assertEqual(text.count("Glyphs.menu[EDIT_MENU].append("), 1)
        self.assertIn("self.name_menu = tr(\"menu.main\")", text)
        self.assertIn("newMenuItem.setTitle_(self.name_menu)", text)
        self.assertIn("newMenuItem.setAction_(self.ShowStatusWindow_)", text)
        self.assertNotIn("status_item = NSMenuItem.new()", text)
        self.assertNotIn("self.statusMenuItem", text)
        self.assertNotIn("newMenuItem.setAction_(self.StartStopServer_)", text)

    def test_status_window_has_start_stop_server_control(self) -> None:
        resources = _resources_dir()
        plugin_path = resources / "glyphs_plugin.py"
        text = plugin_path.read_text(encoding="utf-8", errors="replace")

        self.assertIn("def ToggleServer_(self, sender):", text)
        self.assertIn("def StartServer_(self, sender):", text)
        self.assertIn("def StopServer_(self, sender):", text)
        self.assertIn("server_button.setAction_(self.ToggleServer_)", text)
        self.assertIn("button.setTitle_(tr(\"server.start\"))", text)
        self.assertIn("button.setTitle_(tr(\"server.starting\"))", text)
        self.assertIn("button.setTitle_(tr(\"server.stop\"))", text)
        self.assertIn("button.setTitle_(tr(\"server.stopping\"))", text)

    def test_status_window_uses_titlebar_version_and_dot_status(self) -> None:
        resources = _resources_dir()
        plugin_path = resources / "glyphs_plugin.py"
        text = plugin_path.read_text(encoding="utf-8", errors="replace")

        self.assertIn('panel.setTitle_("{} {}".format(tr("app.title"), get_plugin_version()))', text)
        self.assertIn('panel.setTitle_("{} {}".format(tr("app.title"), version))', text)
        self.assertIn("self._status_dot_field = status_dot", text)
        self.assertIn('dot.setStringValue_("●")', text)
        self.assertIn("dot.setToolTip_(status_value)", text)
        self.assertNotIn("self._header_field", text)
        self.assertNotIn("self._status_field", text)
        self.assertNotIn("self._version_field", text)
        self.assertNotIn("header_value =", text)
        self.assertNotIn("version_label =", text)

    def test_status_window_uses_inline_url_icon_buttons(self) -> None:
        resources = _resources_dir()
        plugin_path = resources / "glyphs_plugin.py"
        text = plugin_path.read_text(encoding="utf-8", errors="replace")

        self.assertIn("endpoint_copy_button = self._small_icon_button(", text)
        self.assertIn("self.CopyEndpoint_", text)
        self.assertIn('tr("copy.tooltip")', text)
        self.assertNotIn("docs_open_button = self._small_icon_button(", text)
        self.assertNotIn("open_docs_button = NSButton", text)
        self.assertNotIn("copy_button = NSButton", text)
        self.assertNotIn('setTitle_(tr("docs.open"))', text)
        self.assertNotIn('setTitle_(tr("endpoint.copy"))', text)
        self.assertNotIn('tr("docs.tooltip")', text)
        self.assertNotIn("self._docs_field", text)
        self.assertNotIn('tr("activity.label")', text)
        self.assertNotIn('tr("endpoint.label")', text)
        self.assertNotIn('tr("docs.label")', text)

    def test_status_window_matches_new_compact_layout_controls(self) -> None:
        resources = _resources_dir()
        plugin_path = resources / "glyphs_plugin.py"
        text = plugin_path.read_text(encoding="utf-8", errors="replace")

        self.assertIn("center_x = width / 2.0", text)
        self.assertIn("dot_y = height - 114", text)
        self.assertIn("activity_y = controls_y + 38", text)
        self.assertIn("status_dot.setAlignment_", text)
        self.assertIn("activity_value.setAlignment_", text)
        self.assertIn("footer.setAlignment_", text)
        self.assertIn("debug_checkbox.setTitle_(tr(\"debug.short\"))", text)
        self.assertIn("autostart_checkbox.setTitle_(tr(\"autostart.short\"))", text)
        self.assertIn('tr("feedback.footer")', text)
        self.assertIn('"info.circle"', text)

    def test_status_window_has_starting_state_and_pulsing_blue_dot(self) -> None:
        resources = _resources_dir()
        plugin_path = resources / "glyphs_plugin.py"
        i18n_path = resources / "i18n.py"
        text = plugin_path.read_text(encoding="utf-8", errors="replace")
        i18n_text = i18n_path.read_text(encoding="utf-8", errors="replace")

        self.assertIn("def _mark_server_starting(self):", text)
        self.assertIn("self._starting_server = True", text)
        self.assertIn('self._activity_text = tr("status.starting")', text)
        self.assertIn("self._activity_state = \"starting\"", text)
        self.assertIn("def _finish_server_starting(self, error=None):", text)
        self.assertIn("self._starting_server = False", text)
        self.assertIn("self._finish_server_starting(error=e)", text)
        self.assertIn("self._finish_server_starting_soon()", text)
        self.assertIn("\"starting\": (\"systemBlueColor\", \"blueColor\")", text)
        self.assertIn("\"waiting\": (\"systemBlueColor\", \"blueColor\")", text)
        self.assertIn("\"stopping\": (\"systemBlueColor\", \"blueColor\")", text)
        self.assertIn("\"error\": (\"systemRedColor\", \"redColor\")", text)
        self.assertIn("return state in (\"starting\", \"waiting\", \"stopping\")", text)
        self.assertIn("def _start_status_dot_pulse(self):", text)
        self.assertIn("def PulseStatusDot_(self, timer):", text)
        self.assertIn("dot.setAlphaValue_(0.35 if dim else 1.0)", text)
        self.assertIn("def _stop_status_dot_pulse(self):", text)
        self.assertIn("dot.setAlphaValue_(1.0)", text)
        self.assertIn('status_state = "starting"', text)
        self.assertIn('status_value = tr("status.starting")', text)
        self.assertIn('activity_text = tr("status.starting")', text)
        self.assertIn('"server.starting"', i18n_text)
        self.assertIn('"status.starting"', i18n_text)
        self.assertNotIn('status_state = "active"', text)
        self.assertNotIn('status_state = "error"', text)
        self.assertNotIn('"active": ("systemBlueColor", "blueColor")', text)

    def test_status_window_project_link_opens_ap_cx(self) -> None:
        resources = _resources_dir()
        plugin_path = resources / "glyphs_plugin.py"
        i18n_path = resources / "i18n.py"
        text = plugin_path.read_text(encoding="utf-8", errors="replace")
        i18n_text = i18n_path.read_text(encoding="utf-8", errors="replace")

        self.assertIn('PROJECT_URL = "https://ap.cx/tools/glyphs-mcp"', text)
        self.assertIn("def OpenFeedback_(self, sender):", text)
        self.assertIn("NSURL.URLWithString_(PROJECT_URL)", text)
        self.assertIn('tr("feedback.footer")', text)
        self.assertIn("Vibe coded with ✨ by Thierry Charbonnel t@ap.cx", i18n_text)
        self.assertIn("Open project page", i18n_text)
        self.assertNotIn("mailto:", text)
        self.assertNotIn("github.com/thierryc/Glyphs-mcp/issues/new", text)

    def test_activity_status_middleware_tracks_latest_command(self) -> None:
        resources = _resources_dir()
        plugin_path = resources / "glyphs_plugin.py"
        text = plugin_path.read_text(encoding="utf-8", errors="replace")

        self.assertIn("class McpActivityStatusMiddleware:", text)
        self.assertIn("Middleware(McpActivityStatusMiddleware, recorder=self._record_activity)", text)
        self.assertIn('return "tools/call: {}".format(params.get("name"))', text)
        self.assertIn('self._activity_text = tr("activity.idle")', text)
        self.assertIn("def _record_activity(self, message, state=\"ok\"):", text)
        self.assertIn("self._activity_field = activity_value", text)

    def test_server_startup_has_stop_handle(self) -> None:
        resources = _resources_dir()
        plugin_path = resources / "glyphs_plugin.py"
        text = plugin_path.read_text(encoding="utf-8", errors="replace")

        self.assertIn("import uvicorn", text)
        self.assertIn("app = mcp.http_app(", text)
        self.assertIn("self._server = uvicorn.Server(config)", text)
        self.assertIn("target=self._server.run", text)
        self.assertIn("server.should_exit = True", text)
        self.assertNotIn("target=mcp.run", text)

    def test_startup_diagnostics_patch_wraps_start_button_action(self) -> None:
        resources = _resources_dir()
        plugin_path = resources / "plugin.py"
        text = plugin_path.read_text(encoding="utf-8", errors="replace")

        self.assertIn('hasattr(MCPBridgePlugin, "StartServer_")', text)
        self.assertIn("_orig_StartServer_ = MCPBridgePlugin.StartServer_", text)
        self.assertIn("MCPBridgePlugin.StartServer_ = _patched_StartServer_", text)
        self.assertNotIn("StartStopServer_", text)

    def test_plugin_exposes_editable_default_port(self) -> None:
        resources = _resources_dir()
        plugin_path = resources / "glyphs_plugin.py"
        text = plugin_path.read_text(encoding="utf-8", errors="replace")

        self.assertIn('DEFAULT_PORT_DEFAULTS_KEY = "com.ap.cx.glyphs-mcp.port"', text)
        self.assertIn("def _configured_default_port(self):", text)
        self.assertIn("def _set_configured_default_port(self, port):", text)
        self.assertIn("DEFAULT_PORT = 9680", text)
        self.assertIn("self.default_port = self._configured_default_port()", text)
        self.assertIn('tr("port.label")', text)
        self.assertIn("port_field.setEditable_(True)", text)
        self.assertIn("port_button.setAction_(self.ChangePort_)", text)
        self.assertIn("def ChangePort_(self, sender):", text)
        self.assertNotIn('port_field.setStringValue_("9681")', text)
        self.assertNotIn('tr("portbusy.custom")', text)

    def test_review_kerning_bumper_is_decorated(self) -> None:
        self._assert_async_tool_decorated("review_kerning_bumper")

    def test_apply_kerning_bumper_is_decorated(self) -> None:
        self._assert_async_tool_decorated("apply_kerning_bumper")

    def test_compensated_tuning_tools_are_decorated(self) -> None:
        self._assert_async_tool_decorated("measure_stem_ratio")
        self._assert_async_tool_decorated("review_compensated_tuning")
        self._assert_async_tool_decorated("apply_compensated_tuning")

    def test_stem_metric_tools_are_decorated(self) -> None:
        self._assert_async_tool_decorated("review_master_stem_metrics")
        self._assert_async_tool_decorated("set_master_stem_metrics")

    def test_master_italic_angle_tool_is_decorated(self) -> None:
        self._assert_async_tool_decorated("set_master_italic_angle")

    def test_italic_first_pass_tools_are_decorated(self) -> None:
        self._assert_async_tool_decorated("review_italic_first_pass")
        self._assert_async_tool_decorated("apply_italic_first_pass")

    def test_visual_review_tool_is_decorated(self) -> None:
        self._assert_async_tool_decorated("render_glyph_review_image")


if __name__ == "__main__":
    unittest.main()
