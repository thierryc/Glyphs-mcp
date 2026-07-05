# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import (
    _font_resolution_error,
    _glyphs_show_glyphs_link_fields,
    _is_style_set_tag,
    _parse_style_set_substitutions,
    _resolve_font_by_index,
    _safe_json,
    _style_set_name_from_metadata,
)


def _unique_ordered(values):
    out = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


@mcp.tool()
async def list_style_sets(font_index: int = 0, include_inactive: bool = False) -> str:
    """List stylistic-set features with affected glyphs and clickable Glyphs links.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        include_inactive (bool): Include inactive ssXX features when true. Defaults to false.

    Returns:
        str: JSON object containing font metadata and a styleSets list. Each style
        set includes sourceGlyphs, replacementGlyphs, substitutions, and a
        group-level showMarkdown link for the replacement glyphs when possible.
    """
    try:
        font, fonts = _resolve_font_by_index(Glyphs, font_index)
        if not font:
            return json.dumps(_font_resolution_error(font_index, fonts))

        file_path = getattr(font, "filepath", None)
        style_sets = []

        for feature_index, feature in enumerate(list(getattr(font, "features", []) or [])):
            tag = str(getattr(feature, "name", "") or "")
            if not _is_style_set_tag(tag):
                continue

            active = bool(getattr(feature, "active", True))
            if not active and not include_inactive:
                continue

            parsed = _parse_style_set_substitutions(getattr(feature, "code", "") or "")
            substitutions = parsed.get("substitutions", [])
            source_glyphs = _unique_ordered([item.get("source") for item in substitutions if item.get("source")])
            replacement_glyphs = _unique_ordered(
                [item.get("replacement") for item in substitutions if item.get("replacement")]
            )
            display_name = _style_set_name_from_metadata(
                tag,
                notes=getattr(feature, "notes", None),
                labels=getattr(feature, "labels", None),
            )

            entry = {
                "tag": tag,
                "name": display_name or tag,
                "active": active,
                "automatic": bool(getattr(feature, "automatic", False)),
                "featureIndex": feature_index,
                "substitutionCount": len(substitutions),
                "sourceGlyphs": source_glyphs,
                "replacementGlyphs": replacement_glyphs,
                "substitutions": substitutions,
                "unsupportedRuleCount": int(parsed.get("unsupportedRuleCount", 0) or 0),
                "warnings": parsed.get("warnings", []),
            }
            entry.update(
                _glyphs_show_glyphs_link_fields(
                    file_path,
                    replacement_glyphs,
                    label="Open {} alternates in Glyphs".format(tag),
                )
            )
            style_sets.append(entry)

        return _safe_json(
            {
                "font": {
                    "familyName": getattr(font, "familyName", "") or "",
                    "filePath": file_path,
                },
                "styleSetCount": len(style_sets),
                "styleSets": style_sets,
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})
