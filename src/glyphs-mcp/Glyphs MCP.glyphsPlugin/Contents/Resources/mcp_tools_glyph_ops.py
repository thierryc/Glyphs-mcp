# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json

from GlyphsApp import Glyphs, GSGlyph  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import (
    _get_left_sidebearing,
    _get_right_sidebearing,
    _save_font_on_main_thread,
    _set_sidebearing,
)


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
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts))
                }
            )

        if not glyph_name:
            return json.dumps({"error": "Glyph name is required"})

        font = Glyphs.fonts[font_index]

        # Check if glyph already exists
        if font.glyphs[glyph_name]:
            return json.dumps({"error": "Glyph '{}' already exists".format(glyph_name)})

        # Create new glyph
        new_glyph = GSGlyph(glyph_name)

        if unicode:
            new_glyph.unicode = unicode
        if category:
            new_glyph.category = category
        if sub_category:
            new_glyph.subCategory = sub_category

        font.glyphs.append(new_glyph)

        # Send notification
        Glyphs.showNotification(
            "Glyph Created", "Created glyph '{}' in {}".format(glyph_name, font.familyName)
        )

        return json.dumps(
            {
                "success": True,
                "message": "Created glyph '{}'".format(glyph_name),
                "glyph": {
                    "name": new_glyph.name,
                    "unicode": new_glyph.unicode,
                    "category": new_glyph.category,
                    "subCategory": new_glyph.subCategory,
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
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts))
                }
            )

        if not glyph_name:
            return json.dumps({"error": "Glyph name is required"})

        font = Glyphs.fonts[font_index]
        glyph = font.glyphs[glyph_name]

        if not glyph:
            return json.dumps({"error": "Glyph '{}' not found".format(glyph_name)})

        del font.glyphs[glyph_name]

        # Send notification
        Glyphs.showNotification(
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
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts))
                }
            )

        if not glyph_name:
            return json.dumps({"error": "Glyph name is required"})

        font = Glyphs.fonts[font_index]
        glyph = font.glyphs[glyph_name]

        if not glyph:
            return json.dumps({"error": "Glyph '{}' not found".format(glyph_name)})

        # Update properties
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
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts))
                }
            )

        if not source_glyph or not target_glyph:
            return json.dumps(
                {"error": "Both source and target glyph names are required"}
            )

        font = Glyphs.fonts[font_index]
        src_glyph = font.glyphs[source_glyph]

        if not src_glyph:
            return json.dumps({"error": "Source glyph '{}' not found".format(source_glyph)})

        # Remove existing target glyph so we can duplicate cleanly
        tgt_glyph = font.glyphs[target_glyph]
        if tgt_glyph is not None:
            font.removeGlyph_(tgt_glyph)

        # Duplicate glyph using Glyphs' native copying so all layer data and
        # metadata come across without hitting read-only attributes.
        duplicated = src_glyph.copy()
        duplicated.name = target_glyph
        font.glyphs.append(duplicated)

        # Optionally strip components/anchors from the duplicate
        if not copy_components or not copy_anchors:
            for layer in duplicated.layers:
                if not copy_components:
                    try:
                        layer.setComponents_(None)
                    except Exception:
                        layer.components = []
                if not copy_anchors:
                    layer.anchors = []

        # Send notification
        Glyphs.showNotification(
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
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts))
                }
            )

        if not glyph_name:
            return json.dumps({"error": "Glyph name is required"})

        font = Glyphs.fonts[font_index]
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

        for layer in layers:
            if width is not None:
                layer.width = width
            if left_sidebearing is not None:
                _set_sidebearing(layer, "leftSideBearing", "LSB", left_sidebearing)
            if right_sidebearing is not None:
                _set_sidebearing(layer, "rightSideBearing", "RSB", right_sidebearing)

            updated_metrics.append(
                {
                    "layerName": layer.name,
                    "width": layer.width,
                    "leftSideBearing": _get_left_sidebearing(layer),
                    "rightSideBearing": _get_right_sidebearing(layer),
                }
            )

        return json.dumps(
            {
                "success": True,
                "message": "Updated metrics for glyph '{}'".format(glyph_name),
                "metrics": updated_metrics,
            }
        )
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
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts))
                }
            )

        font = Glyphs.fonts[font_index]

        existing_path = getattr(font, "filepath", None)
        requested_path = path or existing_path
        if not requested_path:
            return json.dumps(
                {"error": "No file path specified and font has not been saved before"}
            )

        target_override = path if path else None
        saved_path = _save_font_on_main_thread(font, target_override)
        resolved_path = saved_path or getattr(font, "filepath", None) or requested_path

        # Send notification
        Glyphs.showNotification(
            "Font Saved", "Saved {} to {}".format(font.familyName, resolved_path)
        )

        return json.dumps(
            {
                "success": True,
                "message": "Saved font to {}".format(resolved_path),
                "path": resolved_path,
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})

