# encoding: utf-8

"""Tool profile definitions for reducing MCP tool surface (prompt footprint).

This module is intentionally pure (no Glyphs/AppKit/FastMCP imports) so it can
be unit-tested outside Glyphs.
"""

from __future__ import division, print_function, unicode_literals


PROFILE_READONLY = "Read-only"
PROFILE_EDIT = "Edit"


PROFILE_ORDER = [
    PROFILE_READONLY,
    PROFILE_EDIT,
]


CORE_READONLY_TOOLS = {
    "list_open_fonts",
    "get_font_glyphs",
    "get_font_masters",
    "get_font_instances",
    "get_glyph_details",
    "get_font_kerning",
    "list_style_sets",
    "get_glyph_components",
    "get_selected_glyphs",
    "get_selected_font_and_master",
    "get_selected_nodes",
    "get_glyph_paths",
    "get_glyph_annotations",
    "get_glyph_annotation_groups",
    "render_glyph_review_image",
    "docs_search",
    "docs_get",
}


PROFILES = {
    PROFILE_READONLY: {"mode": "allowlist", "tools": set(CORE_READONLY_TOOLS)},
    PROFILE_EDIT: {"mode": "full"},
}


LEGACY_PROFILE_ALIASES = {
    "Full": PROFILE_EDIT,
    "Core (Read-only)": PROFILE_READONLY,
    "Kerning": PROFILE_EDIT,
    "Spacing": PROFILE_EDIT,
    "Kerning + Spacing": PROFILE_EDIT,
    "Paths / Outlines": PROFILE_EDIT,
    "Editing": PROFILE_EDIT,
}


def normalize_profile_name(name):
    try:
        value = str(name) if name else PROFILE_EDIT
    except Exception:
        return PROFILE_EDIT
    return LEGACY_PROFILE_ALIASES.get(value, value)


def is_valid_profile_name(name):
    try:
        return bool(name) and normalize_profile_name(name) in PROFILES
    except Exception:
        return False


def enabled_tool_names(profile_name, all_tool_names):
    """Return the enabled tool names for the requested profile.

    Edit returns all tool names as-is. Read-only returns allowlist ∩ all_tool_names
    (unknown tools are ignored).
    """
    profile = PROFILES.get(normalize_profile_name(profile_name))
    if not profile:
        profile = PROFILES.get(PROFILE_EDIT)

    mode = profile.get("mode")
    if mode == "full":
        return set(all_tool_names or set())

    allowlist = set(profile.get("tools") or set())
    return allowlist.intersection(set(all_tool_names or set()))
