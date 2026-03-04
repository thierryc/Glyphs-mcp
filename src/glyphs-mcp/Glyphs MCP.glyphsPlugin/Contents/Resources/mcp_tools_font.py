# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import (
    _coerce_numeric,
    _custom_parameter,
    _get_component_automatic,
    _get_left_sidebearing,
    _get_right_sidebearing,
    _safe_attr,
    _safe_json,
)


@mcp.tool()
async def list_open_fonts() -> str:
    """Return information about all fonts currently open in Glyphs.

    Returns:
        str: A JSON-encoded list where each item contains:
            familyName (str): Font family name.
            filePath (str|None): Absolute path to the .glyphs file, or None if unsaved.
            masterCount (int): Number of masters in the font.
            instanceCount (int): Number of instances in the font.
            glyphCount (int): Number of glyphs in the font.
            unitsPerEm (int): Units per em (UPM) size.
            versionMajor (int): Font version major.
            versionMinor (int): Font version minor.
    """
    try:
        fonts_info = []
        for font in Glyphs.fonts:
            fonts_info.append(
                {
                    "familyName": font.familyName or "",
                    "filePath": font.filepath,
                    "masterCount": len(font.masters),
                    "instanceCount": len(font.instances),
                    "glyphCount": len(font.glyphs),
                    "unitsPerEm": font.upm,
                    "versionMajor": getattr(font, "versionMajor", 0),
                    "versionMinor": getattr(font, "versionMinor", 0),
                }
            )
        print(json.dumps(fonts_info))
        return json.dumps(fonts_info)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_font_glyphs(font_index: int = 0) -> str:
    """Get all glyphs in a specific font.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.

    Returns:
        str: JSON-encoded list of glyphs with their properties.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts))
                }
            )

        font = Glyphs.fonts[font_index]
        glyphs_info = []
        for glyph in font.glyphs:
            glyphs_info.append(
                {
                    "name": glyph.name,
                    "unicode": glyph.unicode,
                    "category": glyph.category,
                    "subCategory": glyph.subCategory,
                    "layerCount": len(glyph.layers),
                    "leftKerningGroup": glyph.leftKerningGroup,
                    "rightKerningGroup": glyph.rightKerningGroup,
                    "export": glyph.export,
                }
            )
        return json.dumps(glyphs_info)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_font_masters(font_index: int = 0) -> str:
    """Get master information for a specific font.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.

    Returns:
        str: JSON-encoded list of font masters with their properties.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts))
                }
            )

        font = Glyphs.fonts[font_index]

        # Prepare axis tag list once for this font
        axes = []
        try:
            axes = list(getattr(font, "axes", []) or [])
        except Exception:
            axes = []

        def axis_value_for(master, tags: set):
            try:
                if not axes:
                    return None
                # Build axis tag/name list
                tag_list = []
                for a in axes:
                    tag = getattr(a, "axisTag", None) or getattr(a, "name", "")
                    tag_list.append(str(tag).lower())
                values = list(getattr(master, "axes", []) or [])
                for i, t in enumerate(tag_list):
                    if t in tags and i < len(values):
                        return values[i]
            except Exception:
                pass
            return None

        masters_info = []
        for master in font.masters:
            weight_val = axis_value_for(master, {"wght", "weight"})
            width_val = axis_value_for(master, {"wdth", "width"})
            # Fallbacks if axes are unavailable
            if weight_val is None:
                weight_val = getattr(master, "weightValue", None)
            if width_val is None:
                width_val = getattr(master, "widthValue", None)

            masters_info.append(
                {
                    "name": master.name,
                    "id": master.id,
                    "weight": weight_val,
                    "width": width_val,
                    "slantAngle": _custom_parameter(master, "postscriptSlantAngle", 0),
                    # GSFontMaster may not have `customName` in Glyphs 3; use safe access
                    "customName": getattr(master, "customName", None),
                    "ascender": master.ascender,
                    "capHeight": master.capHeight,
                    "descender": master.descender,
                    "xHeight": master.xHeight,
                }
            )
        return json.dumps(masters_info)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_font_instances(font_index: int = 0) -> str:
    """Get instance information for a specific font.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.

    Returns:
        str: JSON-encoded list of font instances with their properties.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts))
                }
            )

        font = Glyphs.fonts[font_index]
        instances_info = []
        for instance in font.instances:
            weight_val = _coerce_numeric(_safe_attr(instance, "weight"))
            width_val = _coerce_numeric(_safe_attr(instance, "width"))
            interpolation_weight = _coerce_numeric(
                _safe_attr(instance, "interpolationWeight")
            )
            interpolation_width = _coerce_numeric(
                _safe_attr(instance, "interpolationWidth")
            )
            instances_info.append(
                {
                    "name": _safe_attr(instance, "name", ""),
                    "weight": weight_val,
                    "width": width_val,
                    "customName": _safe_attr(instance, "customName"),
                    "interpolationWeight": interpolation_weight,
                    "interpolationWidth": interpolation_width,
                    "active": bool(_safe_attr(instance, "active", False)),
                    "export": bool(_safe_attr(instance, "export", False)),
                }
            )
        return _safe_json(instances_info)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_glyph_details(font_index: int = 0, glyph_name: str = "A") -> str:
    """Get detailed information about a specific glyph.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        glyph_name (str): Name of the glyph. Defaults to "A".

    Returns:
        str: JSON-encoded glyph details including layers and components.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts))
                }
            )

        font = Glyphs.fonts[font_index]
        glyph = font.glyphs[glyph_name]

        if not glyph:
            return json.dumps({"error": "Glyph '{}' not found in font".format(glyph_name)})

        layers_info = []
        for layer in glyph.layers:
            layer_info = {
                "name": layer.name,
                "width": layer.width,
                "leftSideBearing": _get_left_sidebearing(layer),
                "rightSideBearing": _get_right_sidebearing(layer),
                "pathCount": len(layer.paths),
                "componentCount": len(layer.components),
                "anchorCount": len(layer.anchors),
            }

            # Add component details
            components = []
            for component in layer.components:
                components.append(
                    {
                        "name": component.componentName,
                        "transform": list(component.transform),
                        "automatic": _get_component_automatic(component),
                    }
                )
            layer_info["components"] = components

            layers_info.append(layer_info)

        glyph_details = {
            "name": glyph.name,
            "unicode": glyph.unicode,
            "category": glyph.category,
            "subCategory": glyph.subCategory,
            "script": glyph.script,
            "productionName": glyph.productionName,
            "layers": layers_info,
        }

        return json.dumps(glyph_details)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_font_kerning(font_index: int = 0, master_id: str = None) -> str:
    """Get kerning information for a specific font and master.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        master_id (str): Master ID. If None, uses the first master.

    Returns:
        str: JSON-encoded kerning pairs and values.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts))
                }
            )

        font = Glyphs.fonts[font_index]

        if master_id is None:
            master_id = font.masters[0].id

        kerning_info = []
        kerning = font.kerning.get(master_id, {})

        for left_group, right_dict in kerning.items():
            for right_group, value in right_dict.items():
                kerning_info.append(
                    {"left": left_group, "right": right_group, "value": value}
                )

        return json.dumps(
            {
                "masterId": master_id,
                "kerningPairs": kerning_info,
                "pairCount": len(kerning_info),
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})

