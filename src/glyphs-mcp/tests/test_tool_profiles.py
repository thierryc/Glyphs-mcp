"""Tests for tool_profiles preset logic."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


class ToolProfilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources_dir()))
        global tool_profiles  # noqa: PLW0603 - simple test import
        import tool_profiles as tool_profiles  # type: ignore

    def test_readonly_excludes_exec_tools(self) -> None:
        enabled = tool_profiles.enabled_tool_names(
            tool_profiles.PROFILE_READONLY,
            {"execute_code", "execute_code_with_context", "get_server_info", "list_open_fonts", "list_style_sets"},
        )
        self.assertNotIn("execute_code", enabled)
        self.assertNotIn("execute_code_with_context", enabled)
        self.assertIn("get_server_info", enabled)
        self.assertIn("list_open_fonts", enabled)
        self.assertIn("list_style_sets", enabled)

    def test_only_readonly_and_edit_profiles_are_shown(self) -> None:
        self.assertEqual(
            tool_profiles.PROFILE_ORDER,
            [tool_profiles.PROFILE_READONLY, tool_profiles.PROFILE_EDIT],
        )
        self.assertEqual(set(tool_profiles.PROFILES), set(tool_profiles.PROFILE_ORDER))

    def test_edit_profile_returns_all_names(self) -> None:
        all_tools = {
            "execute_code",
            "execute_code_with_context",
            "list_open_fonts",
            "review_spacing",
            "generate_kerning_tab",
            "set_glyph_paths",
        }
        enabled = tool_profiles.enabled_tool_names(tool_profiles.PROFILE_EDIT, all_tools)
        self.assertEqual(enabled, all_tools)

    def test_edit_is_default_fallback_and_most_capable(self) -> None:
        all_names = {"a", "b", "delete_glyph", "ExportDesignspaceAndUFO"}
        enabled = tool_profiles.enabled_tool_names("Missing profile", all_names)
        self.assertEqual(enabled, all_names)

    def test_legacy_profiles_normalize_to_two_current_profiles(self) -> None:
        self.assertEqual(tool_profiles.normalize_profile_name("Core (Read-only)"), tool_profiles.PROFILE_READONLY)
        for legacy_name in (
            "Full",
            "Kerning",
            "Spacing",
            "Kerning + Spacing",
            "Paths / Outlines",
            "Editing",
        ):
            self.assertEqual(
                tool_profiles.normalize_profile_name(legacy_name),
                tool_profiles.PROFILE_EDIT,
                msg=legacy_name,
            )

    def test_edit_includes_italic_tools_and_readonly_does_not(self) -> None:
        italic_tools = {
            "review_master_stem_metrics",
            "set_master_stem_metrics",
            "set_master_italic_angle",
            "review_italic_first_pass",
            "apply_italic_first_pass",
        }
        universe = set(tool_profiles.CORE_READONLY_TOOLS) | {"execute_code", "execute_code_with_context"} | italic_tools

        readonly = tool_profiles.enabled_tool_names(tool_profiles.PROFILE_READONLY, universe)
        editing = tool_profiles.enabled_tool_names(tool_profiles.PROFILE_EDIT, universe)

        self.assertTrue(italic_tools.isdisjoint(readonly))
        self.assertTrue(italic_tools.issubset(editing))

    def test_visual_review_is_available_through_readonly_surface(self) -> None:
        visual_tool = "render_glyph_review_image"
        universe = set(tool_profiles.CORE_READONLY_TOOLS) | {"execute_code", "execute_code_with_context"} | {visual_tool}

        self.assertIn(visual_tool, tool_profiles.enabled_tool_names(tool_profiles.PROFILE_READONLY, universe))
        self.assertIn(visual_tool, tool_profiles.enabled_tool_names(tool_profiles.PROFILE_EDIT, universe))

    def test_annotation_read_tools_are_available_through_readonly_surface(self) -> None:
        read_tools = {"get_glyph_annotations", "get_glyph_annotation_groups"}
        edit_tools = {
            "add_glyph_annotation",
            "add_glyph_annotation_group",
            "update_glyph_annotation",
            "delete_glyph_annotation",
            "clear_glyph_annotations",
        }
        universe = set(tool_profiles.CORE_READONLY_TOOLS) | edit_tools

        readonly = tool_profiles.enabled_tool_names(tool_profiles.PROFILE_READONLY, universe)
        editing = tool_profiles.enabled_tool_names(tool_profiles.PROFILE_EDIT, universe)

        self.assertTrue(read_tools.issubset(readonly))
        self.assertTrue(edit_tools.isdisjoint(readonly))
        self.assertTrue(read_tools.issubset(editing))
        self.assertTrue(edit_tools.issubset(editing))

    def test_feedback_inspection_and_preview_tools_are_readonly_but_app_actions_are_not(self) -> None:
        read_tools = {
            "show_glyphs_status",
            "show_font_feedback",
            "show_glyph_feedback",
            "show_opentype_features",
            "preview_spacing_feedback",
            "preview_kerning_feedback",
            "preview_handle_smoothing_feedback",
        }
        app_actions = {"apply_feedback_plan", "open_feedback_target"}
        universe = set(tool_profiles.CORE_READONLY_TOOLS) | app_actions

        readonly = tool_profiles.enabled_tool_names(tool_profiles.PROFILE_READONLY, universe)
        editing = tool_profiles.enabled_tool_names(tool_profiles.PROFILE_EDIT, universe)

        self.assertTrue(read_tools.issubset(readonly))
        self.assertTrue(app_actions.isdisjoint(readonly))
        self.assertTrue(read_tools.issubset(editing))
        self.assertTrue(app_actions.issubset(editing))
