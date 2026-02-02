# encoding: utf-8

from __future__ import division, print_function, unicode_literals
import json
import traceback
from dataclasses import asdict

try:
    import objc  # type: ignore[import-not-found]
    from Foundation import NSObject  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - PyObjC should be available inside Glyphs
    objc = None
    NSObject = None
from GlyphsApp import (
    Glyphs,
    GSGlyph,
    GSLayer,
    GSPath,
    GSNode,
    GSHandle,
    GSComponent,
    GSAnchor,
    GSHint,
    CORNER,
)  # type: ignore[import-not-found]
from fastmcp import FastMCP
from export_designspace_ufo import (
    ExportDesignspaceAndUFO as ExportDesignspaceAndUFOExporter,
    ExportOptions,
)

# Initialize FastMCP server
mcp = FastMCP(name="Glyphs MCP Server", version="1.0.0")


def _custom_parameter(obj, key, default=None):
    """Safely read a value from Glyphs' CustomParametersProxy.

    The proxy does not implement dict.get(). Iterate entries and match by name.
    """
    try:
        cp = getattr(obj, "customParameters", None)
        if cp is None:
            return default
        for item in cp:
            if getattr(item, "name", None) == key:
                return getattr(item, "value", default)
    except Exception:
        pass
    return default


def _sanitize_for_json(value):
    """Convert Glyphs/PyObjC objects to JSON-serializable primitives."""
    if value is None:
        return None

    if isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, (list, tuple, set)):
        return [_sanitize_for_json(v) for v in value]

    if isinstance(value, dict):
        return {str(k): _sanitize_for_json(v) for k, v in value.items()}

    try:
        return float(value)
    except (TypeError, ValueError):
        pass

    try:
        return str(value)
    except Exception:
        return None


def _safe_json(data):
    return json.dumps(_sanitize_for_json(data))


def _safe_attr(obj, attr_name, default=None):
    """Fetch an attribute without crashing on proxies or selectors."""
    try:
        value = getattr(obj, attr_name)
        if callable(value):
            return value()
        return value
    except AttributeError:
        return default
    except Exception:
        return default


def _coerce_numeric(value):
    """Convert Glyphs/AppKit objects or selectors to plain floats/ints."""
    if value is None:
        return None

    try:
        if callable(value):
            value = value()
    except Exception:
        return None

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        pass

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clear_layer_paths(layer):
    """Remove all paths from a layer without touching components/anchors."""
    try:
        existing = list(getattr(layer, "paths", []) or [])
    except Exception:
        existing = []

    for path in existing:
        removed = False
        try:
            if hasattr(layer, "removePath_"):
                layer.removePath_(path)
                removed = True
        except Exception:
            removed = False

        if not removed:
            try:
                layer.paths.remove(path)
                removed = True
            except Exception:
                pass

        if not removed:
            try:
                idx = layer.paths.index(path)
                del layer.paths[idx]
            except Exception:
                pass


def _get_sidebearing(layer, attr_name, legacy_attr):
    """Return a sidebearing value even for proxy layers lacking modern attrs."""
    value = None
    try:
        value = getattr(layer, attr_name, None)
    except Exception:
        value = None

    value = _coerce_numeric(value)

    if value is None:
        fallback = getattr(layer, legacy_attr, None)
        value = _coerce_numeric(fallback)

    return value


def _get_left_sidebearing(layer):
    return _get_sidebearing(layer, "leftSideBearing", "LSB")


def _get_right_sidebearing(layer):
    return _get_sidebearing(layer, "rightSideBearing", "RSB")


def _set_sidebearing(layer, attr_name, legacy_attr, value):
    """Attempt to set a sidebearing using both modern and legacy attributes."""
    if value is None:
        return False

    try:
        setattr(layer, attr_name, value)
        return True
    except Exception:
        pass

    try:
        setattr(layer, legacy_attr, value)
        return True
    except Exception:
        return False


def _save_font_on_main_thread(font, requested_path=None):
    """Invoke font.save(...) on the Glyphs main thread via NSObject helper."""
    if objc is None or NSObject is None:
        if requested_path:
            font.save(requested_path)
            return requested_path
        font.save()
        return getattr(font, "filepath", None)

    class _FontSaveHelper(NSObject):  # type: ignore[misc,valid-type]
        def init(self):
            self = objc.super(_FontSaveHelper, self).init()
            if self is None:
                return None
            self._font = font
            self._path = requested_path
            self.error = None
            self.saved_path = None
            return self

        def saveFont_(self, _obj):
            try:
                if self._path:
                    self._font.save(self._path)
                else:
                    self._font.save()
                self.saved_path = getattr(self._font, "filepath", None) or self._path
            except Exception as exc:  # pragma: no cover - bubbled to caller
                self.error = exc

    helper = _FontSaveHelper.alloc().init()
    helper.performSelectorOnMainThread_withObject_waitUntilDone_("saveFont:", None, True)

    if getattr(helper, "error", None) is not None:
        raise helper.error

    return getattr(helper, "saved_path", None) or getattr(font, "filepath", None) or requested_path


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
                        "automatic": component.automatic,
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
async def get_glyph_components(
    font_index: int = 0, glyph_name: str = None, master_id: str = None
) -> str:
    """Get detailed component information from a glyph's layers.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        glyph_name (str): Name of the glyph to get components from. Required.
        master_id (str): Master ID. If None, gets components from all masters. Optional.

    Returns:
        str: JSON-encoded list of components with their properties including:
            - Component name
            - Transform matrix (scale, rotation, position)
            - Automatic alignment status
            - Layer information
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

        # Determine which layers to check
        if master_id:
            layers = [(master_id, glyph.layers[master_id])]
            if not layers[0][1]:
                return json.dumps({"error": "Master ID '{}' not found".format(master_id)})
        else:
            layers = [(master.id, glyph.layers[master.id]) for master in font.masters]

        components_info = []

        for mid, layer in layers:
            layer_components = []

            for component in layer.components:
                # Extract transform values
                transform = component.transform
                component_data = {
                    "name": component.componentName,
                    "transform": {
                        "xScale": transform[0],
                        "xyScale": transform[1],
                        "yxScale": transform[2],
                        "yScale": transform[3],
                        "xOffset": transform[4],
                        "yOffset": transform[5],
                    },
                    "automatic": component.automatic,
                }

                # Check if the component glyph exists
                component_glyph = font.glyphs[component.componentName]
                if component_glyph:
                    component_data["componentGlyphExists"] = True
                    component_data["componentUnicode"] = component_glyph.unicode
                    component_data["componentCategory"] = component_glyph.category
                else:
                    component_data["componentGlyphExists"] = False

                layer_components.append(component_data)

            # Find master name for this layer
            master_name = None
            for master in font.masters:
                if master.id == mid:
                    master_name = master.name
                    break

            components_info.append(
                {
                    "masterId": mid,
                    "masterName": master_name or layer.name,
                    "layerName": layer.name,
                    "componentCount": len(layer_components),
                    "components": layer_components,
                }
            )

        return json.dumps(
            {
                "glyphName": glyph_name,
                "totalLayers": len(components_info),
                "layers": components_info,
            }
        )

    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def add_component_to_glyph(
    font_index: int = 0,
    glyph_name: str = None,
    component_name: str = None,
    master_id: str = None,
    x_offset: float = 0,
    y_offset: float = 0,
    x_scale: float = 1,
    y_scale: float = 1,
) -> str:
    """Add a component to a glyph's layer.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        glyph_name (str): Name of the glyph to add component to. Required.
        component_name (str): Name of the glyph to use as component. Required.
        master_id (str): Master ID. If None, adds to all masters. Optional.
        x_offset (float): X offset for the component. Defaults to 0.
        y_offset (float): Y offset for the component. Defaults to 0.
        x_scale (float): X scale factor. Defaults to 1.
        y_scale (float): Y scale factor. Defaults to 1.

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

        if not glyph_name or not component_name:
            return json.dumps(
                {"error": "Both glyph_name and component_name are required"}
            )

        font = Glyphs.fonts[font_index]
        glyph = font.glyphs[glyph_name]

        if not glyph:
            return json.dumps({"error": "Glyph '{}' not found".format(glyph_name)})

        if not font.glyphs[component_name]:
            return json.dumps(
                {"error": "Component glyph '{}' not found".format(component_name)}
            )

        # Determine which layers to update
        if master_id:
            layers = [glyph.layers[master_id]]
            if not layers[0]:
                return json.dumps({"error": "Master ID '{}' not found".format(master_id)})
        else:
            layers = [glyph.layers[master.id] for master in font.masters]

        for layer in layers:
            component = GSComponent(component_name)
            # Set transform: [xScale, 0, 0, yScale, xOffset, yOffset]
            component.transform = (x_scale, 0, 0, y_scale, x_offset, y_offset)
            layer.components.append(component)

        return json.dumps(
            {
                "success": True,
                "message": "Added component '{}' to glyph '{}'".format(component_name, glyph_name),
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def add_anchor_to_glyph(
    font_index: int = 0,
    glyph_name: str = None,
    anchor_name: str = None,
    master_id: str = None,
    x: float = None,
    y: float = None,
) -> str:
    """Add an anchor to a glyph's layer.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        glyph_name (str): Name of the glyph to add anchor to. Required.
        anchor_name (str): Name of the anchor (e.g., "top", "bottom"). Required.
        master_id (str): Master ID. If None, adds to all masters. Optional.
        x (float): X position of the anchor. Required.
        y (float): Y position of the anchor. Required.

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

        if not glyph_name or not anchor_name:
            return json.dumps({"error": "Both glyph_name and anchor_name are required"})

        if x is None or y is None:
            return json.dumps({"error": "Both x and y coordinates are required"})

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

        for layer in layers:
            anchor = GSAnchor(anchor_name, (x, y))
            layer.anchors.append(anchor)

        return json.dumps(
            {
                "success": True,
                "message": "Added anchor '{}' to glyph '{}'".format(anchor_name, glyph_name),
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def set_kerning_pair(
    font_index: int = 0,
    master_id: str = None,
    left: str = None,
    right: str = None,
    value: int = None,
) -> str:
    """Set kerning value for a specific pair.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        master_id (str): Master ID. If None, uses the first master. Optional.
        left (str): Left glyph name or kerning group (e.g., "@MMK_L_A"). Required.
        right (str): Right glyph name or kerning group (e.g., "@MMK_R_V"). Required.
        value (int): Kerning value. Use 0 to remove kerning. Required.

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

        if not left or not right:
            return json.dumps(
                {"error": "Both left and right glyph/group names are required"}
            )

        if value is None:
            return json.dumps({"error": "Kerning value is required"})

        font = Glyphs.fonts[font_index]

        if master_id is None:
            master_id = font.masters[0].id

        # Initialize kerning dictionary if needed
        if master_id not in font.kerning:
            font.kerning[master_id] = {}

        if left not in font.kerning[master_id]:
            font.kerning[master_id][left] = {}

        if value == 0:
            # Remove kerning if it exists
            if right in font.kerning[master_id][left]:
                del font.kerning[master_id][left][right]
            message = "Removed kerning for '{}' - '{}'".format(left, right)
        else:
            # Set kerning value
            font.kerning[master_id][left][right] = value
            message = "Set kerning for '{}' - '{}' to {}".format(left, right, value)

        # Send notification
        Glyphs.showNotification("Kerning Updated", message)

        return json.dumps(
            {
                "success": True,
                "message": message,
                "kerning": {
                    "left": left,
                    "right": right,
                    "value": value,
                    "masterId": master_id,
                },
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_selected_glyphs() -> str:
    """Get information about currently selected glyphs in the active font view.

    Returns:
        str: JSON-encoded list of selected glyph names and their properties.
    """
    try:
        if not Glyphs.font:
            return json.dumps({"error": "No font is currently active"})

        selected = []
        for layer in Glyphs.font.selectedLayers:
            glyph = layer.parent
            selected.append(
                {
                    "name": glyph.name,
                    "unicode": glyph.unicode,
                    "category": glyph.category,
                    "subCategory": glyph.subCategory,
                    "layerName": layer.name,
                    "width": layer.width,
                }
            )

        return json.dumps(
            {
                "fontName": Glyphs.font.familyName,
                "selectedCount": len(selected),
                "selectedGlyphs": selected,
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_selected_font_and_master() -> str:
    """Get information about the currently selected font and master from the active font view.
    
    Returns:
        str: JSON-encoded object containing:
            fontInfo (dict): Information about the selected font including name, path, and counts.
            currentMaster (dict): Information about the currently selected master.
            selectedGlyphs (list): List of currently selected glyphs.
    """
    try:
        if not Glyphs.font:
            return json.dumps({"error": "No font is currently active"})
        
        font = Glyphs.font
        
        # Get font information
        font_info = {
            "familyName": font.familyName or "",
            "filePath": font.filepath,
            "masterCount": len(font.masters),
            "instanceCount": len(font.instances),
            "glyphCount": len(font.glyphs),
            "unitsPerEm": font.upm,
            "versionMajor": getattr(font, "versionMajor", 0),
            "versionMinor": getattr(font, "versionMinor", 0),
        }
        
        # Get current master (the one being edited)
        current_master = None
        if font.selectedFontMaster:
            master = font.selectedFontMaster
            current_master = {
                "name": master.name,
                "id": master.id,
                # GSFontMaster may not have `customName` in Glyphs 3; use safe access
                "customName": getattr(master, "customName", None),
                "ascender": master.ascender,
                "capHeight": master.capHeight,
                "descender": master.descender,
                "xHeight": master.xHeight,
                "weight": getattr(master, "weight", ""),
                "width": getattr(master, "width", ""),
            }
        
        # Get selected glyphs
        selected_glyphs = []
        for layer in font.selectedLayers:
            glyph = layer.parent
            left_bearing = _get_left_sidebearing(layer)
            right_bearing = _get_right_sidebearing(layer)
            selected_glyphs.append({
                "name": glyph.name,
                "unicode": glyph.unicode,
                "category": glyph.category,
                "subCategory": glyph.subCategory,
                "layerName": layer.name,
                "width": layer.width,
                "leftSideBearing": left_bearing,
                "rightSideBearing": right_bearing,
            })
        
        return _safe_json({
            "fontInfo": font_info,
            "currentMaster": current_master,
            "selectedGlyphs": selected_glyphs,
            "selectedGlyphCount": len(selected_glyphs),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_selected_nodes(include_master_mapping: bool = True) -> str:
    """Return detailed information about the currently selected node(s) in the active edit view.

    The payload is designed to be actionable for writing follow‑up code that edits paths
    (e.g., insert a point before/after the selected node) and to help find the corresponding
    node across masters in the same glyph without being overly complex.

    Returns:
        str: JSON with fields:
            font (dict): active font info
            glyph (dict): active glyph info
            layer (dict): active layer info
            nodes (list): selected node entries, each with
                - pathIndex (int): index in layer.paths
                - nodeIndex (int): index in path.nodes
                - nodeType (str): 'line' | 'curve' | 'qcurve' | 'offcurve'
                - smooth (bool)
                - position (dict): {x, y}
                - closed (bool): whether the path is closed
                - onCurveIndex (int|null): ordinal among on‑curve nodes in the path
                - segment (dict): neighbor and segment information
                - pathSignature (dict): simple structural fingerprint
                - mapping (list|empty): per‑master mapping hints (present when include_master_mapping)
    """
    try:
        font = Glyphs.font
        if not font:
            return json.dumps({"error": "No font is currently active"})

        # Active glyph/layer come from the edit view
        if not font.selectedLayers or len(font.selectedLayers) == 0:
            return json.dumps({"error": "No active layer/glyph open in Edit view"})

        layer = font.selectedLayers[0]
        glyph = layer.parent

        # Helper: basic info blocks
        def font_info(f):
            return {
                "familyName": f.familyName or "",
                "filePath": f.filepath,
                "upm": f.upm,
                "masterCount": len(f.masters),
            }

        def layer_info(l):
            info = {
                "name": getattr(l, "name", ""),
                "associatedMasterId": getattr(l, "associatedMasterId", None),
                "width": getattr(l, "width", 0),
            }
            # layerId is not always present in older API; guard safely
            lid = getattr(l, "layerId", None)
            if lid is None:
                lid = getattr(l, "id", None)
            info["id"] = lid
            return info

        def oncurve_indices_for(path):
            idx = []
            # node.type is a string in Glyphs 3 Python API (e.g. 'offcurve', 'line', 'curve')
            for i, n in enumerate(path.nodes):
                if getattr(n, "type", "offcurve") != "offcurve":
                    idx.append(i)
            return idx

        # Compute selected nodes by scanning selection or nodes' .selected flag
        selected_nodes = []
        for p_index, path in enumerate(layer.paths):
            # Fast path: walk nodes and check .selected
            oc_indices = oncurve_indices_for(path)
            oc_positions = {i: k for k, i in enumerate(oc_indices)}  # nodeIndex -> onCurve ordinal

            node_count = len(path.nodes)
            for n_index, node in enumerate(path.nodes):
                if not getattr(node, "selected", False):
                    continue

                # Determine on-curve ordinal (None for offcurve)
                oncurve_ordinal = oc_positions.get(n_index, None)

                # Neighbor indices (wrap for closed paths)
                closed = bool(getattr(path, "closed", True))
                prev_index = (n_index - 1) % node_count if closed and node_count else max(0, n_index - 1)
                next_index = (n_index + 1) % node_count if closed and node_count else min(node_count - 1, n_index + 1)

                # Segment context: determine surrounding on-curves
                # Find previous on-curve index moving backward
                prev_oncurve_node_index = None
                k = n_index
                for _ in range(node_count):
                    k = (k - 1) % node_count if closed else (k - 1)
                    if k < 0:
                        break
                    if getattr(path.nodes[k], "type", "offcurve") != "offcurve":
                        prev_oncurve_node_index = k
                        break

                # Find next on-curve index moving forward
                next_oncurve_node_index = None
                k = n_index
                for _ in range(node_count):
                    k = (k + 1) % node_count if closed else (k + 1)
                    if k >= node_count:
                        break
                    if getattr(path.nodes[k], "type", "offcurve") != "offcurve":
                        next_oncurve_node_index = k
                        break

                # Compute off-curve ordinal inside the segment (prev_oncurve -> next_oncurve)
                offcurve_index_in_segment = None
                offcurve_count_in_segment = None
                if getattr(node, "type", "offcurve") == "offcurve" and prev_oncurve_node_index is not None and next_oncurve_node_index is not None:
                    # Collect segment nodes (exclusive of prev_oncurve, inclusive of node, exclusive of next_oncurve)
                    seg_nodes = []
                    i = prev_oncurve_node_index
                    while True:
                        i = (i + 1) % node_count if closed else (i + 1)
                        if i == next_oncurve_node_index or i >= node_count:
                            break
                        seg_nodes.append(i)
                        if closed and i == (node_count - 1) and next_oncurve_node_index == 0:
                            # wrap condition handled by while logic
                            pass

                    offcurve_seq = [idx for idx in seg_nodes if getattr(path.nodes[idx], "type", "offcurve") == "offcurve"]
                    offcurve_count_in_segment = len(offcurve_seq)
                    try:
                        offcurve_index_in_segment = offcurve_seq.index(n_index)
                    except ValueError:
                        offcurve_index_in_segment = None

                # Simple structural fingerprint for this path
                path_signature = {
                    "closed": closed,
                    "nodeCount": node_count,
                    "onCurveCount": len(oc_indices),
                }

                entry = {
                    "pathIndex": p_index,
                    "nodeIndex": n_index,
                    "nodeType": getattr(node, "type", "offcurve"),
                    "smooth": bool(getattr(node, "smooth", False)),
                    "position": {
                        "x": float(getattr(node, "position", (0, 0))[0]),
                        "y": float(getattr(node, "position", (0, 0))[1]),
                    },
                    "closed": closed,
                    "onCurveIndex": oncurve_ordinal,
                    "segment": {
                        "prevNodeIndex": prev_index,
                        "nextNodeIndex": next_index,
                        "prevOnCurveNodeIndex": prev_oncurve_node_index,
                        "nextOnCurveNodeIndex": next_oncurve_node_index,
                        "offCurveIndexInSegment": offcurve_index_in_segment,
                        "offCurveCountInSegment": offcurve_count_in_segment,
                    },
                    "pathSignature": path_signature,
                }

                selected_nodes.append(entry)

        # If requested, compute a per‑master mapping for each selected node
        if include_master_mapping and selected_nodes and glyph is not None:
            masters = list(font.masters)
            for node_entry in selected_nodes:
                mapping = []

                src_path_index = node_entry["pathIndex"]
                src_oncurve_index = node_entry.get("onCurveIndex")
                src_closed = bool(node_entry.get("closed", True))
                src_node_type = node_entry.get("nodeType")

                # Get source path on-curve count for fallback mapping
                try:
                    src_path = layer.paths[src_path_index]
                except Exception:
                    continue
                src_oc_indices = oncurve_indices_for(src_path)
                src_oc_count = len(src_oc_indices)

                for master in masters:
                    t_layer = glyph.layers[master.id]

                    # Choose target path: prefer same index; fallback to path with closest on‑curve count
                    t_paths = list(t_layer.paths)
                    if not t_paths:
                        mapping.append({
                            "masterId": master.id,
                            "masterName": master.name,
                            "layerName": getattr(t_layer, "name", ""),
                            "pathIndex": None,
                            "nodeIndex": None,
                            "onCurveIndex": None,
                            "note": "No paths in target layer",
                        })
                        continue

                    if 0 <= src_path_index < len(t_paths):
                        t_path_index = src_path_index
                    else:
                        # find closest by on-curve count
                        best_idx = 0
                        best_score = None
                        for pi, p in enumerate(t_paths):
                            oc_cnt = len(oncurve_indices_for(p))
                            score = abs(oc_cnt - src_oc_count)
                            if best_score is None or score < best_score:
                                best_idx, best_score = pi, score
                        t_path_index = best_idx

                    t_path = t_paths[t_path_index]
                    t_oc_indices = oncurve_indices_for(t_path)
                    t_oc_count = len(t_oc_indices)

                    t_node_index = None
                    t_oncurve_index = None
                    note = None

                    if src_oncurve_index is None:
                        # Selected node is off‑curve: map within the segment around the analogous on‑curve
                        # Use next on‑curve as anchor if present, otherwise previous.
                        seg = node_entry.get("segment", {})
                        # Prefer mapping to the next on-curve segment if available
                        anchor_oncurve_ordinal = None
                        if seg.get("nextOnCurveNodeIndex") is not None:
                            # derive ordinal of next on‑curve in source path
                            try:
                                anchor_oncurve_ordinal = src_oc_indices.index(seg["nextOnCurveNodeIndex"])
                            except Exception:
                                anchor_oncurve_ordinal = None
                        if anchor_oncurve_ordinal is None and seg.get("prevOnCurveNodeIndex") is not None:
                            try:
                                anchor_oncurve_ordinal = src_oc_indices.index(seg["prevOnCurveNodeIndex"])
                            except Exception:
                                anchor_oncurve_ordinal = None

                        if anchor_oncurve_ordinal is not None and anchor_oncurve_ordinal < t_oc_count:
                            # find corresponding on‑curve node index in target path
                            anchor_oncurve_node_index = t_oc_indices[anchor_oncurve_ordinal]
                            # Build the segment before that on‑curve in the target path
                            # Find previous on‑curve node index in target path
                            node_count = len(t_path.nodes)
                            j = anchor_oncurve_node_index
                            prev_oncurve_node_index = None
                            for _ in range(node_count):
                                j = (j - 1) % node_count if bool(getattr(t_path, "closed", True)) else (j - 1)
                                if j < 0:
                                    break
                                if getattr(t_path.nodes[j], "type", "offcurve") != "offcurve":
                                    prev_oncurve_node_index = j
                                    break

                            # Enumerate off‑curves in that segment and map by ordinal
                            off_seq = []
                            if prev_oncurve_node_index is not None:
                                i = prev_oncurve_node_index
                                closed_t = bool(getattr(t_path, "closed", True))
                                while True:
                                    i = (i + 1) % node_count if closed_t else (i + 1)
                                    if i == anchor_oncurve_node_index or i >= node_count:
                                        break
                                    if getattr(t_path.nodes[i], "type", "offcurve") == "offcurve":
                                        off_seq.append(i)
                            src_off_idx = seg.get("offCurveIndexInSegment")
                            if off_seq and src_off_idx is not None:
                                clamped = max(0, min(int(src_off_idx), len(off_seq) - 1))
                                t_node_index = off_seq[clamped]
                                t_oncurve_index = anchor_oncurve_ordinal
                            else:
                                note = "No matching off‑curve in segment; skipping"
                        else:
                            note = "Could not determine anchor on‑curve ordinal"
                    else:
                        # Selected node is on‑curve: map by on‑curve ordinal
                        if src_oncurve_index < t_oc_count:
                            t_oncurve_index = int(src_oncurve_index)
                            t_node_index = t_oc_indices[t_oncurve_index]
                        else:
                            note = "On‑curve ordinal out of range in target; skipping"

                    mapping.append({
                        "masterId": master.id,
                        "masterName": master.name,
                        "layerName": getattr(t_layer, "name", ""),
                        "pathIndex": t_path_index,
                        "nodeIndex": t_node_index,
                        "onCurveIndex": t_oncurve_index,
                        "note": note,
                    })

                node_entry["mapping"] = mapping

        result = {
            "font": font_info(font),
            "glyph": {
                "name": getattr(glyph, "name", None),
                "unicode": getattr(glyph, "unicode", None),
            },
            "layer": layer_info(layer),
            "nodeCount": len(selected_nodes),
            "nodes": selected_nodes,
        }

        return json.dumps(result)

    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def add_croner_corner_to_all_masters(corner_name: str = "_corner.croner") -> str:
    """Add a corner component hint at the selected node(s) across all masters.

    This tool:
    - Processes all selected *nodes* (including extra/intersection nodes) in the active layer.
    - Processes selected intersection *handles* (``GSHandle``) by reusing their index path.
    - Skips other non-node selections (reported in the result).
    - Maps nodes across masters strictly by (pathIndex, nodeIndex) within layer.paths.
    - Skips + reports masters where the corresponding path/node index is missing.

    Args:
        corner_name: Corner component name (e.g. ``_corner.croner``).

    Returns:
        JSON encoded result with per-master add/skip details.
    """
    try:
        font = Glyphs.font
        if not font:
            return json.dumps({"error": "No font is currently active"})

        if not font.selectedLayers or len(font.selectedLayers) == 0:
            return json.dumps({"error": "No active layer/glyph open in Edit view"})

        layer = font.selectedLayers[0]
        glyph = layer.parent
        if glyph is None:
            return json.dumps({"error": "No active glyph found for current layer"})

        def _index_path_to_list(index_path):
            if index_path is None:
                return None
            try:
                length = int(index_path.length())
                return [int(index_path.indexAtPosition_(i)) for i in range(length)]
            except Exception:
                try:
                    return [int(v) for v in index_path]
                except Exception:
                    return None

        raw_selection = list(getattr(layer, "selection", []) or [])
        skipped_selection = []
        selected_handles = []

        # Collect selected handles (used for intersections) and report other non-node selections.
        for item in raw_selection:
            if isinstance(item, GSHandle):
                try:
                    origin_index = item.object()  # NSIndexPath
                except Exception:
                    origin_index = None
                if origin_index is None:
                    skipped_selection.append(
                        {"type": "GSHandle", "reason": "Could not read handle index path"}
                    )
                    continue
                try:
                    stem = int(item.flag())
                except Exception:
                    stem = None
                selected_handles.append(
                    {
                        "originIndex": origin_index,
                        "originIndexList": _index_path_to_list(origin_index),
                        "stem": stem,
                    }
                )
                continue

            if not isinstance(item, GSNode):
                item_type = type(item).__name__
                reason = "Not a node or intersection handle"
                skipped_selection.append({"type": item_type, "reason": reason})

        # Gather selected nodes from the path graph to obtain stable indices.
        selected_nodes = []
        for p_index, path in enumerate(getattr(layer, "paths", []) or []):
            for n_index, node in enumerate(getattr(path, "nodes", []) or []):
                if not getattr(node, "selected", False):
                    continue
                node_type = getattr(node, "type", "offcurve")
                if node_type == "offcurve":
                    skipped_selection.append(
                        {
                            "type": "GSNode",
                            "pathIndex": p_index,
                            "nodeIndex": n_index,
                            "nodeType": node_type,
                            "reason": "Off-curve nodes are not supported for corner components",
                        }
                    )
                    continue
                selected_nodes.append(
                    {
                        "pathIndex": p_index,
                        "nodeIndex": n_index,
                        "nodeType": node_type,
                        "position": {
                            "x": float(getattr(node, "position", (0, 0))[0]),
                            "y": float(getattr(node, "position", (0, 0))[1]),
                        },
                    }
                )

        if not selected_nodes and not selected_handles:
            return json.dumps(
                {
                    "error": "No applicable nodes/handles selected (select on-curve nodes or intersection handles)",
                    "cornerName": corner_name,
                    "skippedSelection": skipped_selection,
                }
            )

        masters = list(getattr(font, "masters", []) or [])
        results = []
        total_added = 0
        total_skipped = 0

        for master in masters:
            master_result = {
                "masterId": getattr(master, "id", None),
                "masterName": getattr(master, "name", ""),
                "addedCount": 0,
                "skipped": [],
            }

            try:
                t_layer = glyph.layers[master.id]
            except Exception:
                master_result["skipped"].append({"reason": "Master layer not found"})
                total_skipped += len(selected_nodes)
                results.append(master_result)
                continue

            t_paths = list(getattr(t_layer, "paths", []) or [])
            t_hints = list(getattr(t_layer, "hints", []) or [])

            for locator in selected_nodes:
                p_index = int(locator["pathIndex"])
                n_index = int(locator["nodeIndex"])

                if p_index < 0 or p_index >= len(t_paths):
                    master_result["skipped"].append(
                        {
                            "pathIndex": p_index,
                            "nodeIndex": n_index,
                            "reason": "Path index out of range in target master",
                        }
                    )
                    total_skipped += 1
                    continue

                t_path = t_paths[p_index]
                t_nodes = list(getattr(t_path, "nodes", []) or [])
                if n_index < 0 or n_index >= len(t_nodes):
                    master_result["skipped"].append(
                        {
                            "pathIndex": p_index,
                            "nodeIndex": n_index,
                            "reason": "Node index out of range in target master",
                        }
                    )
                    total_skipped += 1
                    continue

                t_node = t_nodes[n_index]
                t_node_type = getattr(t_node, "type", "offcurve")
                if t_node_type == "offcurve":
                    master_result["skipped"].append(
                        {
                            "pathIndex": p_index,
                            "nodeIndex": n_index,
                            "reason": "Target node is off-curve in this master",
                        }
                    )
                    total_skipped += 1
                    continue

                already_exists = False
                for hint in t_hints:
                    try:
                        if getattr(hint, "type", None) != CORNER:
                            continue
                        if getattr(hint, "name", None) != corner_name:
                            continue
                        if getattr(hint, "originNode", None) is t_node:
                            already_exists = True
                            break
                    except Exception:
                        continue

                if already_exists:
                    master_result["skipped"].append(
                        {
                            "pathIndex": p_index,
                            "nodeIndex": n_index,
                            "reason": "Corner hint already exists at this node",
                        }
                    )
                    total_skipped += 1
                    continue

                new_hint = GSHint()
                new_hint.type = CORNER
                new_hint.name = corner_name
                new_hint.originNode = t_node
                t_layer.hints.append(new_hint)
                t_hints.append(new_hint)

                master_result["addedCount"] += 1
                total_added += 1

            for handle_locator in selected_handles:
                origin_index = handle_locator.get("originIndex")
                origin_index_list = handle_locator.get("originIndexList") or []
                stem = handle_locator.get("stem")

                # Best-effort validation: hint index paths generally start with (shapeIndex, nodeIndex).
                if len(origin_index_list) >= 2:
                    shape_index = int(origin_index_list[0])
                    node_index = int(origin_index_list[1])
                    shapes = list(getattr(t_layer, "shapes", []) or [])

                    if shape_index < 0 or shape_index >= len(shapes):
                        master_result["skipped"].append(
                            {
                                "type": "GSHandle",
                                "originIndex": origin_index_list,
                                "reason": "Shape index out of range in target master",
                            }
                        )
                        total_skipped += 1
                        continue

                    shape = shapes[shape_index]
                    if not isinstance(shape, GSPath):
                        master_result["skipped"].append(
                            {
                                "type": "GSHandle",
                                "originIndex": origin_index_list,
                                "reason": "Target shape at index is not a path",
                            }
                        )
                        total_skipped += 1
                        continue

                    t_nodes = list(getattr(shape, "nodes", []) or [])
                    if node_index < 0 or node_index >= len(t_nodes):
                        master_result["skipped"].append(
                            {
                                "type": "GSHandle",
                                "originIndex": origin_index_list,
                                "reason": "Node index out of range in target master shape",
                            }
                        )
                        total_skipped += 1
                        continue

                already_exists = False
                for hint in t_hints:
                    try:
                        if getattr(hint, "type", None) != CORNER:
                            continue
                        if getattr(hint, "name", None) != corner_name:
                            continue
                        if getattr(hint, "originIndex", None) != origin_index:
                            continue
                        if stem is not None and getattr(hint, "stem", None) != stem:
                            continue
                        already_exists = True
                        break
                    except Exception:
                        continue

                if already_exists:
                    master_result["skipped"].append(
                        {
                            "type": "GSHandle",
                            "originIndex": origin_index_list or None,
                            "reason": "Corner hint already exists at this index path",
                        }
                    )
                    total_skipped += 1
                    continue

                new_hint = GSHint()
                new_hint.type = CORNER
                new_hint.name = corner_name
                new_hint.originIndex = origin_index
                if stem is not None:
                    try:
                        new_hint.stem = stem
                    except Exception:
                        pass
                t_layer.hints.append(new_hint)
                t_hints.append(new_hint)

                master_result["addedCount"] += 1
                total_added += 1

            results.append(master_result)

        return json.dumps(
            {
                "success": True,
                "cornerName": corner_name,
                "font": {
                    "familyName": getattr(font, "familyName", "") or "",
                    "filePath": getattr(font, "filepath", None),
                },
                "glyph": {
                    "name": getattr(glyph, "name", None),
                    "unicode": getattr(glyph, "unicode", None),
                },
                "activeLayer": {
                    "name": getattr(layer, "name", ""),
                    "associatedMasterId": getattr(layer, "associatedMasterId", None),
                },
                "selection": {
                    "nodeCount": len(selected_nodes),
                    "nodes": selected_nodes,
                    "handleCount": len(selected_handles),
                    "handles": [
                        {
                            "originIndex": h.get("originIndexList"),
                            "stem": h.get("stem"),
                        }
                        for h in selected_handles
                    ],
                    "skippedSelection": skipped_selection,
                },
                "mastersProcessed": len(masters),
                "totalAdded": total_added,
                "totalSkipped": total_skipped,
                "results": results,
            }
        )

    except Exception as exc:
        return json.dumps(
            {
                "error": str(exc) or repr(exc),
                "errorType": type(exc).__name__,
                "traceback": traceback.format_exception(type(exc), exc, exc.__traceback__),
            }
        )


def _normalise_name_sequence(value):
    if not value:
        return []
    if isinstance(value, str):
        cleaned = value.replace(",", " ").split()
        return [name.strip() for name in cleaned if name.strip()]
    try:
        return [str(name).strip() for name in value if str(name).strip()]
    except TypeError:
        return []


@mcp.tool()
async def ExportDesignspaceAndUFO(
    font_index: int = 0,
    include_variable: bool = True,
    include_static: bool = True,
    brace_layers_mode: str = "layers",
    include_build_script: bool = True,
    decompose_glyphs: list | tuple | str | None = None,
    remove_overlap_glyphs: list | tuple | str | None = None,
    keep_glyphs_lib: bool = False,
    production_names: bool = False,
    decompose_smart_components: bool = True,
    decompose_smart_corners: bool = True,
    output_directory: str | None = None,
    open_destination: bool = False,
) -> str:
    """Export designspace and UFO packages for the selected font.

    Args:
        font_index: Index of the font in ``Glyphs.fonts`` to export.
        include_variable: Whether to generate variable designspace/UFO sources.
        include_static: Whether to generate static designspace/UFO sources.
        brace_layers_mode: ``"layers"`` keeps brace layers as glyph layers,
            ``"separate_ufos"`` exports them as standalone masters.
        include_build_script: Include a ``build.sh`` helper script.
        decompose_glyphs: Optional sequence of glyph names to decompose before
            export.
        remove_overlap_glyphs: Optional sequence of glyph names where overlaps
            should be removed before export.
        keep_glyphs_lib: Reserved for parity with the original script. When
            ``True`` the Glyphs lib is preserved (currently a no-op).
        production_names: Reserved for parity with the original script.
        decompose_smart_components: Decompose smart components before export.
        decompose_smart_corners: Decompose corner components before export.
        output_directory: Optional explicit destination directory. Required for
            unsaved fonts.
        open_destination: If ``True`` and the environment supports it, open the
            destination folder in Finder after export.

    Returns:
        JSON encoded dictionary with output paths and log messages.
    """

    log_messages = []
    options = None
    font = None

    def _capture_log(message):
        if message:
            log_messages.append(message)

    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(
                        font_index, len(Glyphs.fonts)
                    )
                }
            )

        font = Glyphs.fonts[font_index]

        brace_mode = (brace_layers_mode or "layers").strip().lower()

        options = ExportOptions(
            include_variable=include_variable,
            include_static=include_static,
            brace_layers_mode=brace_mode,
            include_build_script=include_build_script,
            decompose_glyphs=_normalise_name_sequence(decompose_glyphs),
            remove_overlap_glyphs=_normalise_name_sequence(remove_overlap_glyphs),
            keep_glyphs_lib=keep_glyphs_lib,
            production_names=production_names,
            decompose_smart_components=decompose_smart_components,
            decompose_smart_corners=decompose_smart_corners,
            output_directory=output_directory,
            open_destination=open_destination,
        )

        exporter = ExportDesignspaceAndUFOExporter(
            font, options=options, logger=_capture_log
        )
        result = exporter.run()

        return json.dumps(
            {
                "success": True,
                "outputDirectory": result.output_directory,
                "designspaceFiles": result.designspace_files,
                "masterUFOs": result.master_ufos,
                "braceUFOs": result.brace_ufos,
                "supportFiles": result.support_files,
                "log": result.log,
            }
        )
    except Exception as exc:
        error_payload = {
            "error": str(exc) or repr(exc),
            "errorType": type(exc).__name__,
            "traceback": traceback.format_exception(type(exc), exc, exc.__traceback__),
        }
        if font is not None:
            font_details = {"familyName": getattr(font, "familyName", None)}
            font_parent = getattr(font, "parent", None)
            if font_parent is not None:
                try:
                    file_url_obj = font_parent.fileURL()
                    if file_url_obj is not None:
                        font_details["filePath"] = getattr(file_url_obj, "path", lambda: None)()
                except Exception:
                    font_details["filePath"] = None
            error_payload["font"] = font_details
        if options is not None:
            error_payload["options"] = asdict(options)
        if log_messages:
            error_payload["log"] = log_messages
        return json.dumps(error_payload)


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


@mcp.tool()
async def get_glyph_paths(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None
) -> str:
    """Get the path data for a glyph in a simple JSON format suitable for LLM editing.
    
    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        glyph_name (str): Name of the glyph. Required.
        master_id (str): Master ID. If None, uses the current selected master. Optional.
    
    Returns:
        str: JSON-encoded path data containing:
            paths (list): List of paths, each containing:
                nodes (list): List of nodes with x, y, type, smooth properties
                closed (bool): Whether the path is closed
            width (int): Glyph width
            leftSideBearing (int): Left side bearing
            rightSideBearing (int): Right side bearing
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
        
        # Determine which master to use
        if master_id:
            layer = glyph.layers[master_id]
            if not layer:
                return json.dumps({"error": "Master ID '{}' not found".format(master_id)})
        else:
            # Use the selected master or first master
            if font.selectedFontMaster:
                layer = glyph.layers[font.selectedFontMaster.id]
            else:
                layer = glyph.layers[font.masters[0].id]
        
        # Ensure we have a valid layer
        if not layer:
            return json.dumps({"error": "No valid layer found for glyph '{}'".format(glyph_name)})
        
        # Serialize paths
        paths_data = []
        for path in getattr(layer, 'paths', []):
            nodes_data = []
            for node in path.nodes:
                nodes_data.append({
                    "x": float(node.position.x),
                    "y": float(node.position.y),
                    "type": getattr(node, 'type', 'line'),
                    "smooth": getattr(node, 'smooth', False)
                })
            
            paths_data.append({
                "nodes": nodes_data,
                "closed": getattr(path, 'closed', True)
            })
        
        result = {
            "glyphName": glyph_name,
            "masterId": getattr(layer, 'associatedMasterId', None),
            "masterName": layer.name,
            "paths": paths_data,
            "width": getattr(layer, 'width', 0),
            "leftSideBearing": getattr(layer, 'leftSideBearing', 0),
            "rightSideBearing": getattr(layer, 'rightSideBearing', 0)
        }
        
        return json.dumps(result)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def set_glyph_paths(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    paths_data: str = None
) -> str:
    """Set the path data for a glyph from JSON, replacing existing paths.
    
    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        glyph_name (str): Name of the glyph. Required.
        master_id (str): Master ID. If None, uses the current selected master. Optional.
        paths_data (str): JSON string containing path data in the format returned by get_glyph_paths. Required.
    
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
        
        if not paths_data:
            return json.dumps({"error": "Path data is required"})
        
        # Parse the JSON path data
        try:
            path_info = json.loads(paths_data)
        except ValueError as e:
            return json.dumps({"error": "Invalid JSON in paths_data: {}".format(str(e))})
        
        font = Glyphs.fonts[font_index]
        glyph = font.glyphs[glyph_name]
        
        if not glyph:
            return json.dumps({"error": "Glyph '{}' not found".format(glyph_name)})
        
        # Determine which master to use
        if master_id:
            layer = glyph.layers[master_id]
            if not layer:
                return json.dumps({"error": "Master ID '{}' not found".format(master_id)})
        else:
            # Use the selected master or first master
            if font.selectedFontMaster:
                layer = glyph.layers[font.selectedFontMaster.id]
            else:
                layer = glyph.layers[font.masters[0].id]
        
        # Clear existing paths (but keep components, anchors, etc.)
        _clear_layer_paths(layer)
        
        # Build new paths from the JSON data
        if "paths" in path_info:
            for path_data in path_info["paths"]:
                new_path = GSPath()

                # Add nodes
                if "nodes" in path_data:
                    for node_data in path_data["nodes"]:
                        new_node = GSNode()
                        new_node.position = (
                            float(node_data.get("x", 0.0)),
                            float(node_data.get("y", 0.0)),
                        )
                        new_node.type = node_data.get("type", "line")
                        new_node.smooth = bool(node_data.get("smooth", False))
                        new_path.nodes.append(new_node)

                # Set closed property
                new_path.closed = bool(path_data.get("closed", True))

                # Add the path to the layer via the mutable collection
                try:
                    layer.paths.append(new_path)
                except Exception:
                    # Fallback if append is unavailable
                    if hasattr(layer, "addPath_"):
                        layer.addPath_(new_path)
        
        # Update metrics if provided
        if "width" in path_info:
            layer.width = float(path_info["width"])
        if "leftSideBearing" in path_info:
            layer.leftSideBearing = float(path_info["leftSideBearing"])
        if "rightSideBearing" in path_info:
            layer.rightSideBearing = float(path_info["rightSideBearing"])
        
        # Send notification
        Glyphs.showNotification(
            "Paths Updated", 
            "Updated paths for glyph '{}' in {}".format(glyph_name, font.familyName)
        )
        
        return _safe_json({
            "success": True,
            "message": "Updated paths for glyph '{}'".format(glyph_name),
            "pathCount": len(getattr(layer, "paths", [])),
            "nodeCount": sum(len(path.nodes) for path in getattr(layer, "paths", []))
        })
        
    except Exception as e:
        return json.dumps({"error": str(e)})
