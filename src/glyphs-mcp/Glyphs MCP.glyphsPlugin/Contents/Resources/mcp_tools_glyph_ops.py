# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json

from GlyphsApp import Glyphs, GSGlyph  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import (
    _append_font_glyph,
    _delete_font_glyph,
    _font_format_metadata,
    _font_resolution_error,
    _get_left_sidebearing,
    _get_right_sidebearing,
    _layer_display_name,
    _new_glyph,
    _resolve_font_by_index,
    _run_on_main_thread,
    _save_font_on_main_thread,
    _set_layer_metrics,
    _show_notification,
)


def _resolve_font_payload(font_index):
    font, fonts = _resolve_font_by_index(Glyphs, font_index)
    if not font:
        return None, _font_resolution_error(font_index, fonts, ok_key="success")
    return font, None


def _metric_matches(requested, actual):
    if requested is None:
        return True
    try:
        return abs(float(requested) - float(actual)) < 0.001
    except Exception:
        return requested == actual


@mcp.tool()
async def create_glyph(
    font_index: int = 0,
    glyph_name: str = None,
    unicode: str = None,
    category: str = None,
    sub_category: str = None,
) -> str:
    """Create a new glyph in the specified font.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        glyph_name (str): Name of the new glyph. Required.
        unicode (str): Unicode value for the glyph (e.g., "0041" for A). Optional.
        category (str): Category for the glyph (e.g., "Letter", "Number"). Optional.
        sub_category (str): Subcategory for the glyph (e.g., "Uppercase", "Lowercase"). Optional.

    Returns:
        str: JSON-encoded result with success status and glyph details.
    """
    try:
        font, error = _resolve_font_payload(font_index)
        if error:
            return json.dumps(error)

        if not glyph_name:
            return json.dumps({"error": "Glyph name is required"})

        # Check if glyph already exists
        if font.glyphs[glyph_name]:
            return json.dumps({"error": "Glyph '{}' already exists".format(glyph_name)})

        # Create new glyph
        new_glyph = _new_glyph(GSGlyph, glyph_name)

        if unicode:
            new_glyph.unicode = unicode
        if category:
            new_glyph.category = category
        if sub_category:
            new_glyph.subCategory = sub_category

        verified_glyph = _append_font_glyph(font, new_glyph, glyph_name)
        if not verified_glyph:
            return json.dumps(
                {
                    "success": False,
                    "error": "Glyph '{}' could not be verified after append".format(glyph_name),
                    "glyphName": glyph_name,
                    "fontIndex": font_index,
                }
            )

        # Send notification
        _show_notification(
            Glyphs,
            "Glyph Created", "Created glyph '{}' in {}".format(glyph_name, font.familyName)
        )

        return json.dumps(
            {
                "success": True,
                "message": "Created glyph '{}'".format(glyph_name),
                "glyph": {
                    "name": verified_glyph.name,
                    "unicode": verified_glyph.unicode,
                    "category": verified_glyph.category,
                    "subCategory": verified_glyph.subCategory,
                },
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def delete_glyph(font_index: int = 0, glyph_name: str = None) -> str:
    """Delete a glyph from the specified font.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        glyph_name (str): Name of the glyph to delete. Required.

    Returns:
        str: JSON-encoded result with success status.
    """
    try:
        font, error = _resolve_font_payload(font_index)
        if error:
            return json.dumps(error)

        if not glyph_name:
            return json.dumps({"error": "Glyph name is required"})

        glyph = font.glyphs[glyph_name]

        if not glyph:
            return json.dumps({"error": "Glyph '{}' not found".format(glyph_name)})

        if not _delete_font_glyph(font, glyph_name):
            return json.dumps(
                {
                    "success": False,
                    "error": "Glyph '{}' could not be verified after delete".format(glyph_name),
                    "glyphName": glyph_name,
                    "fontIndex": font_index,
                }
            )

        # Send notification
        _show_notification(
            Glyphs,
            "Glyph Deleted", "Deleted glyph '{}' from {}".format(glyph_name, font.familyName)
        )

        return json.dumps({"success": True, "message": "Deleted glyph '{}'".format(glyph_name)})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def update_glyph_properties(
    font_index: int = 0,
    glyph_name: str = None,
    unicode: str = None,
    category: str = None,
    sub_category: str = None,
    left_kerning_group: str = None,
    right_kerning_group: str = None,
    export: bool = None,
) -> str:
    """Update properties of an existing glyph.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        glyph_name (str): Name of the glyph to update. Required.
        unicode (str): New Unicode value. Optional.
        category (str): New category. Optional.
        sub_category (str): New subcategory. Optional.
        left_kerning_group (str): New left kerning group. Optional.
        right_kerning_group (str): New right kerning group. Optional.
        export (bool): Whether the glyph should be exported. Optional.

    Returns:
        str: JSON-encoded result with updated glyph properties.
    """
    try:
        font, error = _resolve_font_payload(font_index)
        if error:
            return json.dumps(error)

        if not glyph_name:
            return json.dumps({"error": "Glyph name is required"})

        glyph = font.glyphs[glyph_name]

        if not glyph:
            return json.dumps({"error": "Glyph '{}' not found".format(glyph_name)})

        def _mutate_properties():
            if unicode is not None:
                glyph.unicode = unicode
            if category is not None:
                glyph.category = category
            if sub_category is not None:
                glyph.subCategory = sub_category
            if left_kerning_group is not None:
                glyph.leftKerningGroup = left_kerning_group
            if right_kerning_group is not None:
                glyph.rightKerningGroup = right_kerning_group
            if export is not None:
                glyph.export = export

        _run_on_main_thread(_mutate_properties)

        return json.dumps(
            {
                "success": True,
                "message": "Updated glyph '{}'".format(glyph_name),
                "glyph": {
                    "name": glyph.name,
                    "unicode": glyph.unicode,
                    "category": glyph.category,
                    "subCategory": glyph.subCategory,
                    "leftKerningGroup": glyph.leftKerningGroup,
                    "rightKerningGroup": glyph.rightKerningGroup,
                    "export": glyph.export,
                },
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def copy_glyph(
    font_index: int = 0,
    source_glyph: str = None,
    target_glyph: str = None,
    copy_components: bool = True,
    copy_anchors: bool = True,
) -> str:
    """Copy a glyph's outline data to another glyph or create a new glyph with the copied data.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        source_glyph (str): Name of the source glyph to copy from. Required.
        target_glyph (str): Name of the target glyph. If it doesn't exist, it will be created. Required.
        copy_components (bool): Whether to copy components. Defaults to True.
        copy_anchors (bool): Whether to copy anchors. Defaults to True.

    Returns:
        str: JSON-encoded result with success status.
    """
    try:
        font, error = _resolve_font_payload(font_index)
        if error:
            return json.dumps(error)

        if not source_glyph or not target_glyph:
            return json.dumps(
                {"error": "Both source and target glyph names are required"}
            )

        src_glyph = font.glyphs[source_glyph]

        if not src_glyph:
            return json.dumps({"error": "Source glyph '{}' not found".format(source_glyph)})

        # Remove existing target glyph so we can duplicate cleanly
        tgt_glyph = font.glyphs[target_glyph]
        if tgt_glyph is not None:
            if not _delete_font_glyph(font, target_glyph):
                return json.dumps(
                    {
                        "success": False,
                        "error": "Existing target glyph '{}' could not be deleted before copy".format(target_glyph),
                        "glyphName": target_glyph,
                        "fontIndex": font_index,
                    }
                )

        # Duplicate glyph using Glyphs' native copying so all layer data and
        # metadata come across without hitting read-only attributes.
        duplicated = src_glyph.copy()
        duplicated.name = target_glyph
        duplicated = _append_font_glyph(font, duplicated, target_glyph)
        if not duplicated:
            return json.dumps(
                {
                    "success": False,
                    "error": "Glyph '{}' could not be verified after append".format(target_glyph),
                    "glyphName": target_glyph,
                    "fontIndex": font_index,
                }
            )

        # Optionally strip components/anchors from the duplicate
        if not copy_components or not copy_anchors:
            for layer in duplicated.layers:
                if not copy_components:
                    try:
                        _run_on_main_thread(lambda target_layer=layer: target_layer.setComponents_(None))
                    except Exception:
                        _run_on_main_thread(lambda target_layer=layer: setattr(target_layer, "components", []))
                if not copy_anchors:
                    _run_on_main_thread(lambda target_layer=layer: setattr(target_layer, "anchors", []))

        # Send notification
        _show_notification(
            Glyphs,
            "Glyph Copied", "Copied '{}' to '{}'".format(source_glyph, target_glyph)
        )

        return json.dumps(
            {
                "success": True,
                "message": "Copied glyph '{}' to '{}'".format(source_glyph, target_glyph),
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def update_glyph_metrics(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    width: int = None,
    left_sidebearing: int = None,
    right_sidebearing: int = None,
) -> str:
    """Update the metrics (width and sidebearings) of a glyph for a specific master.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        glyph_name (str): Name of the glyph to update. Required.
        master_id (str): Master ID. If None, updates all masters. Optional.
        width (int): New width value. Optional.
        left_sidebearing (int): New left sidebearing value. Optional.
        right_sidebearing (int): New right sidebearing value. Optional.

    Returns:
        str: JSON-encoded result with updated metrics.
    """
    try:
        font, error = _resolve_font_payload(font_index)
        if error:
            return json.dumps(error)

        if not glyph_name:
            return json.dumps({"error": "Glyph name is required"})

        glyph = font.glyphs[glyph_name]

        if not glyph:
            return json.dumps({"error": "Glyph '{}' not found".format(glyph_name)})

        # Determine which layers to update
        if master_id:
            layers = [glyph.layers[master_id]]
            if not layers[0]:
                return json.dumps({"error": "Master ID '{}' not found".format(master_id)})
        else:
            layers = [glyph.layers[master.id] for master in font.masters]

        updated_metrics = []
        warnings = []

        for layer in layers:
            _set_layer_metrics(
                layer,
                width=width,
                left_sidebearing=left_sidebearing,
                right_sidebearing=right_sidebearing,
            )

            actual_width = layer.width
            actual_lsb = _get_left_sidebearing(layer)
            actual_rsb = _get_right_sidebearing(layer)
            mismatches = []
            if not _metric_matches(width, actual_width):
                mismatches.append("width requested {} but Glyphs read back {}".format(width, actual_width))
            if not _metric_matches(left_sidebearing, actual_lsb):
                mismatches.append(
                    "left_sidebearing requested {} but Glyphs read back {}".format(
                        left_sidebearing, actual_lsb
                    )
                )
            if not _metric_matches(right_sidebearing, actual_rsb):
                mismatches.append(
                    "right_sidebearing requested {} but Glyphs read back {}".format(
                        right_sidebearing, actual_rsb
                    )
                )
            if mismatches:
                warnings.append(
                    {
                        "layerName": _layer_display_name(font, layer, master_id),
                        "messages": mismatches,
                    }
                )

            updated_metrics.append(
                {
                    "layerName": _layer_display_name(font, layer, master_id),
                    "width": actual_width,
                    "leftSideBearing": actual_lsb,
                    "rightSideBearing": actual_rsb,
                }
            )

        payload = {
            "success": True,
            "message": "Updated metrics for glyph '{}'".format(glyph_name),
            "metrics": updated_metrics,
        }
        if warnings:
            payload["warnings"] = warnings
        return json.dumps(payload)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def save_font(font_index: int = 0, path: str = None) -> str:
    """Save the font to disk.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        path (str): Path where to save the font. If None, saves to current location. Optional.

    Returns:
        str: JSON-encoded result with success status and save path.
    """
    try:
        font, error = _resolve_font_payload(font_index)
        if error:
            return json.dumps(error)

        existing_path = getattr(font, "filepath", None)
        requested_path = path or existing_path
        if not requested_path:
            return json.dumps(
                {"error": "No file path specified and font has not been saved before"}
            )

        format_before = _font_format_metadata(font)
        target_override = path if path else None
        saved_path = _save_font_on_main_thread(font, target_override)
        resolved_path = saved_path or getattr(font, "filepath", None) or requested_path
        format_after = _font_format_metadata(font)

        # Send notification
        _show_notification(
            Glyphs,
            "Font Saved", "Saved {} to {}".format(font.familyName, resolved_path)
        )

        return json.dumps(
            {
                "success": True,
                "message": "Saved font to {}".format(resolved_path),
                "path": resolved_path,
                "formatVersion": format_after["formatVersion"],
                "formatVersionBefore": format_before["formatVersion"],
                "formatVersionAfter": format_after["formatVersion"],
                "lastSavedAppVersion": format_after["lastSavedAppVersion"],
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})
