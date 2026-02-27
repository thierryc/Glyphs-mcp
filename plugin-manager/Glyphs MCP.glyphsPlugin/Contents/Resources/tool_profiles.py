# encoding: utf-8

"""Tool profile definitions for reducing MCP tool surface (prompt footprint).

This module is intentionally pure (no Glyphs/AppKit/FastMCP imports) so it can
be unit-tested outside Glyphs.
"""

from __future__ import division, print_function, unicode_literals


PROFILE_FULL = "Full"
PROFILE_CORE_READONLY = "Core (Read-only)"
PROFILE_KERNING = "Kerning"
PROFILE_SPACING = "Spacing"
PROFILE_KERNING_SPACING = "Kerning + Spacing"
PROFILE_PATHS = "Paths / Outlines"
PROFILE_EDITING = "Editing"


PROFILE_ORDER = [
    PROFILE_FULL,
    PROFILE_CORE_READONLY,
    PROFILE_KERNING,
    PROFILE_SPACING,
    PROFILE_KERNING_SPACING,
    PROFILE_PATHS,
    PROFILE_EDITING,
]


CORE_READONLY_TOOLS = {
    "list_open_fonts",
    "get_font_glyphs",
    "get_font_masters",
    "get_font_instances",
    "get_glyph_details",
    "get_font_kerning",
    "get_glyph_components",
    "get_selected_glyphs",
    "get_selected_font_and_master",
    "get_selected_nodes",
    "get_glyph_paths",
    "docs_search",
    "docs_get",
}


EXEC_TOOLS = {"execute_code", "execute_code_with_context"}


KERNING_EXTRAS = {
    "generate_kerning_tab",
    "review_kerning_bumper",
    "apply_kerning_bumper",
    "set_kerning_pair",
}


SPACING_EXTRAS = {
    "review_spacing",
    "apply_spacing",
    "set_spacing_params",
    "set_spacing_guides",
}


PATHS_EXTRAS = {
    "set_glyph_paths",
    "review_collinear_handles",
    "apply_collinear_handles_smooth",
}


EDITING_EXTRAS = {
    "create_glyph",
    "copy_glyph",
    "update_glyph_properties",
    "update_glyph_metrics",
    "add_component_to_glyph",
    "add_anchor_to_glyph",
    "set_glyph_paths",
}


PROFILES = {
    PROFILE_FULL: {"mode": "full"},
    PROFILE_CORE_READONLY: {"mode": "allowlist", "tools": set(CORE_READONLY_TOOLS)},
    PROFILE_KERNING: {"mode": "allowlist", "tools": set(CORE_READONLY_TOOLS | EXEC_TOOLS | KERNING_EXTRAS)},
    PROFILE_SPACING: {"mode": "allowlist", "tools": set(CORE_READONLY_TOOLS | EXEC_TOOLS | SPACING_EXTRAS)},
    PROFILE_KERNING_SPACING: {
        "mode": "allowlist",
        "tools": set(CORE_READONLY_TOOLS | EXEC_TOOLS | KERNING_EXTRAS | SPACING_EXTRAS),
    },
    PROFILE_PATHS: {"mode": "allowlist", "tools": set(CORE_READONLY_TOOLS | EXEC_TOOLS | PATHS_EXTRAS)},
    PROFILE_EDITING: {"mode": "allowlist", "tools": set(CORE_READONLY_TOOLS | EXEC_TOOLS | EDITING_EXTRAS)},
}


def is_valid_profile_name(name):
    try:
        return bool(name) and str(name) in PROFILES
    except Exception:
        return False


def enabled_tool_names(profile_name, all_tool_names):
    """Return the enabled tool names for the requested profile.

    Full profile returns all tool names as-is.
    Other profiles return allowlist ∩ all_tool_names (unknown tools are ignored).
    """
    profile = PROFILES.get(str(profile_name))
    if not profile:
        profile = PROFILES.get(PROFILE_FULL)

    mode = profile.get("mode")
    if mode == "full":
        return set(all_tool_names or set())

    allowlist = set(profile.get("tools") or set())
    return allowlist.intersection(set(all_tool_names or set()))

