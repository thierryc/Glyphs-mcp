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
            tool_profiles.PROFILE_CORE_READONLY,
            {"execute_code", "execute_code_with_context", "list_open_fonts"},
        )
        self.assertNotIn("execute_code", enabled)
        self.assertNotIn("execute_code_with_context", enabled)
        self.assertIn("list_open_fonts", enabled)

    def test_all_non_readonly_profiles_include_exec_tools(self) -> None:
        all_tools = {
            "execute_code",
            "execute_code_with_context",
            "list_open_fonts",
            "review_spacing",
            "generate_kerning_tab",
            "set_glyph_paths",
        }
        for name in tool_profiles.PROFILE_ORDER:
            if name in (tool_profiles.PROFILE_FULL, tool_profiles.PROFILE_CORE_READONLY):
                continue
            enabled = tool_profiles.enabled_tool_names(name, all_tools)
            self.assertIn("execute_code", enabled, msg=name)
            self.assertIn("execute_code_with_context", enabled, msg=name)

    def test_kerning_plus_spacing_contains_union(self) -> None:
        # A curated tool universe that includes kerning+spacing extras.
        universe = set(tool_profiles.CORE_READONLY_TOOLS) | set(tool_profiles.EXEC_TOOLS) | set(tool_profiles.KERNING_EXTRAS) | set(tool_profiles.SPACING_EXTRAS)
        enabled = tool_profiles.enabled_tool_names(tool_profiles.PROFILE_KERNING_SPACING, universe)
        for tool in tool_profiles.KERNING_EXTRAS | tool_profiles.SPACING_EXTRAS:
            self.assertIn(tool, enabled)

    def test_full_returns_all_names(self) -> None:
        all_names = {"a", "b", "delete_glyph", "ExportDesignspaceAndUFO"}
        enabled = tool_profiles.enabled_tool_names(tool_profiles.PROFILE_FULL, all_names)
        self.assertEqual(enabled, all_names)

