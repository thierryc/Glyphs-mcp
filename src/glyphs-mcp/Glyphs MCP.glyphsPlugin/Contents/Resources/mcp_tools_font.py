# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json
import math

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import (
    _coerce_numeric,
    _component_transform_values,
    _custom_parameter,
    _font_format_metadata,
    _font_resolution_error,
    _get_component_automatic,
    _get_layer_id,
    _get_left_sidebearing,
    _get_right_sidebearing,
    _glyphs_show_layer_link_fields,
    _glyphs_show_link_fields,
    _layer_display_name,
    _layer_components,
    _layer_shape_summary,
    _open_fonts_from_glyphs,
    _resolve_font_by_index,
    _safe_attr,
    _safe_json,
)


def _font_by_index(font_index):
    font, _fonts = _resolve_font_by_index(Glyphs, font_index)
    return font


def _open_fonts():
    return _open_fonts_from_glyphs(Glyphs)


def _font_count():
    try:
        return len(_open_fonts())
    except Exception:
        return 0


def _master_by_id(font, master_id):
    if not font:
        return None
    master_id = str(master_id or "")
    try:
        for master in font.masters:
            if str(getattr(master, "id", "")) == master_id:
                return master
    except Exception:
        pass
    return None


def _actual_italic_angle(master):
    value = _coerce_numeric(getattr(master, "italicAngle", 0.0))
    return 0.0 if value is None else float(value)


def _validate_italic_angle(value):
    angle = _coerce_numeric(value)
    if angle is None:
        return None, "italic_angle must be a finite number"
    angle = float(angle)
    if not math.isfinite(angle):
        return None, "italic_angle must be finite"
    if not (-89.0 < angle < 89.0):
        return None, "italic_angle must be greater than -89 and less than 89"
    return angle, None


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
        for font_index, font in enumerate(_open_fonts()):
            fonts_info.append(
                {
                    "fontIndex": font_index,
                    "familyName": font.familyName or "",
                    "filePath": font.filepath,
                    "masterCount": len(font.masters),
                    "instanceCount": len(font.instances),
                    "glyphCount": len(font.glyphs),
                    "unitsPerEm": font.upm,
                    "versionMajor": getattr(font, "versionMajor", 0),
                    "versionMinor": getattr(font, "versionMinor", 0),
                    **_font_format_metadata(font),
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
        font = _font_by_index(font_index)
        if not font:
            return json.dumps(_font_resolution_error(font_index, _open_fonts()))

        file_path = getattr(font, "filepath", None)
        glyphs_info = []
        for glyph in font.glyphs:
            glyph_info = {
                "name": glyph.name,
                "unicode": glyph.unicode,
                "category": glyph.category,
                "subCategory": glyph.subCategory,
                "layerCount": len(glyph.layers),
                "leftKerningGroup": glyph.leftKerningGroup,
                "rightKerningGroup": glyph.rightKerningGroup,
                "export": glyph.export,
            }
            glyph_info.update(
                _glyphs_show_link_fields(
                    file_path,
                    glyph_name=glyph.name,
                    label="Open {} in Glyphs".format(glyph.name),
                )
            )
            glyphs_info.append(glyph_info)
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
        font = _font_by_index(font_index)
        if not font:
            return json.dumps(_font_resolution_error(font_index, _open_fonts()))

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
                    "italicAngle": _actual_italic_angle(master),
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
async def set_master_italic_angle(
    font_index: int = 0,
    master_id: str = "",
    italic_angle: float = 12.0,
    dry_run: bool = False,
    confirm: bool = False,
) -> str:
    """Set a master's Glyphs Font Info Metrics italicAngle.

    Uses the Glyphs source convention: positive values lean Latin outlines to
    the right. This is not the postscriptSlantAngle custom parameter.
    """
    try:
        font = _font_by_index(font_index)
        if not font:
            return _safe_json(_font_resolution_error(font_index, _open_fonts(), ok_key="ok"))

        master = _master_by_id(font, master_id)
        if not master:
            return _safe_json(
                {
                    "ok": False,
                    "error": "Master not found",
                    "fontIndex": font_index,
                    "masterId": str(master_id or ""),
                }
            )

        angle, error = _validate_italic_angle(italic_angle)
        if error:
            return _safe_json(
                {
                    "ok": False,
                    "error": error,
                    "fontIndex": font_index,
                    "masterId": str(master_id or ""),
                    "requestedItalicAngle": italic_angle,
                }
            )

        before = _actual_italic_angle(master)
        payload = {
            "ok": True,
            "dryRun": bool(dry_run),
            "fontIndex": font_index,
            "masterId": str(getattr(master, "id", master_id)),
            "masterName": getattr(master, "name", None),
            "before": {"italicAngle": before},
            "after": {"italicAngle": angle},
            "changed": abs(before - angle) > 0.01,
            "note": "Glyphs source convention: positive italicAngle values lean Latin outlines to the right.",
        }

        if dry_run:
            return _safe_json(payload)
        if not confirm:
            payload["ok"] = False
            payload["error"] = "Use dry_run=true first or confirm=true to mutate"
            return _safe_json(payload)

        master.italicAngle = angle
        payload["applied"] = True
        return _safe_json(payload)
    except Exception as e:
        return _safe_json({"ok": False, "error": str(e)})


@mcp.tool()
async def get_font_instances(font_index: int = 0) -> str:
    """Get instance information for a specific font.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.

    Returns:
        str: JSON-encoded list of font instances with their properties.
    """
    try:
        font = _font_by_index(font_index)
        if not font:
            return json.dumps(_font_resolution_error(font_index, _open_fonts()))

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
        font = _font_by_index(font_index)
        if not font:
            return json.dumps(_font_resolution_error(font_index, _open_fonts()))

        file_path = getattr(font, "filepath", None)
        glyph = font.glyphs[glyph_name]

        if not glyph:
            return json.dumps({"error": "Glyph '{}' not found in font".format(glyph_name)})

        layers_info = []
        for layer in glyph.layers:
            layer_id = _get_layer_id(layer)
            layer_name = _layer_display_name(font, layer)
            components = _layer_components(layer)
            layer_info = {
                "name": layer_name,
                "layerId": layer_id,
                "associatedMasterId": getattr(layer, "associatedMasterId", None),
                "width": layer.width,
                "leftSideBearing": _get_left_sidebearing(layer),
                "rightSideBearing": _get_right_sidebearing(layer),
                "pathCount": len(layer.paths),
                "componentCount": len(components),
                "anchorCount": len(layer.anchors),
            }
            layer_info.update(_layer_shape_summary(layer))
            layer_info.update(
                _glyphs_show_layer_link_fields(
                    file_path,
                    glyph_name=glyph.name,
                    layer_id=layer_id,
                    label="Open {} {} in Glyphs".format(glyph.name, layer_name),
                )
            )

            # Add component details
            component_payloads = []
            for component in components:
                component_payloads.append(
                    {
                        "name": component.componentName,
                        "transform": _component_transform_values(component),
                        "automatic": _get_component_automatic(component),
                        "traverseAnchors": _safe_attr(
                            component, "traverseAnchors", None
                        ),
                        "locked": _safe_attr(component, "locked", None),
                        "anchor": _safe_attr(component, "anchor", None),
                    }
                )
            layer_info["components"] = component_payloads

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
        glyph_details.update(_font_format_metadata(font))
        glyph_details.update(
            _glyphs_show_link_fields(
                file_path,
                glyph_name=glyph.name,
                label="Open {} in Glyphs".format(glyph.name),
            )
        )

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
        font = _font_by_index(font_index)
        if not font:
            return json.dumps(_font_resolution_error(font_index, _open_fonts()))

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
