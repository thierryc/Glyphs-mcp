# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json

from GlyphsApp import Glyphs, GSNode, GSPath  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import (
    _apply_path_specs_and_metrics,
    _font_format_metadata,
    _font_resolution_error,
    _get_layer_id,
    _get_left_sidebearing,
    _get_right_sidebearing,
    _glyphs_show_layer_link_fields,
    _layer_display_name,
    _layer_paths,
    _layer_path_summary,
    _layer_shape_summary,
    _mapping_keys,
    _node_orientation,
    _node_raw_connection,
    _node_raw_type,
    _normalized_node_type,
    _resolve_font_by_index,
    _safe_json,
    _shape_attribute_metadata,
    _show_notification,
)


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
            pathDataVersion (int): Payload version. Version 2 includes raw node
                types and additive compatibility metadata.
            paths (list): List of paths, each containing:
                nodes (list): List of nodes with x, y, type, smooth properties
                closed (bool): Whether the path is closed
            width (int): Glyph width
            leftSideBearing (int): Left side bearing
            rightSideBearing (int): Right side bearing
    """
    try:
        font, fonts = _resolve_font_by_index(Glyphs, font_index)
        if not font:
            return json.dumps(_font_resolution_error(font_index, fonts))
        
        if not glyph_name:
            return json.dumps({"error": "Glyph name is required"})
        
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
        
        # Serialize paths without flattening raw Glyphs 4 node types or shape
        # metadata. Attribute values stay read-only in this compatibility pass;
        # their keys and group relationship are exposed for diagnostics.
        paths_data = []
        unsupported_node_types = []
        try:
            layer_shapes = list(getattr(layer, "shapes", None) or [])
        except Exception:
            layer_shapes = []
        shape_indices = {id(shape): index for index, shape in enumerate(layer_shapes)}

        for path_index, path in enumerate(_layer_paths(layer)):
            nodes_data = []
            for node_index, node in enumerate(path.nodes):
                raw_type = _node_raw_type(node)
                node_type = _normalized_node_type(node)
                orientation, raw_orientation = _node_orientation(node)
                if node_type == "unknown":
                    unsupported_node_types.append(
                        {
                            "pathIndex": path_index,
                            "nodeIndex": node_index,
                            "rawType": raw_type,
                        }
                    )
                try:
                    attributes = getattr(node, "attributes", None)
                except Exception:
                    attributes = None
                try:
                    user_data = getattr(node, "userData", None)
                except Exception:
                    user_data = None
                nodes_data.append(
                    {
                        "nodeIndex": node_index,
                        "x": float(node.position.x),
                        "y": float(node.position.y),
                        "type": node_type,
                        "rawType": raw_type,
                        "smooth": bool(getattr(node, "smooth", False)),
                        "rawConnection": _node_raw_connection(node),
                        "orientation": orientation,
                        "rawOrientation": raw_orientation,
                        "name": getattr(node, "name", None),
                        "attributeKeys": _mapping_keys(attributes),
                        "hasUserData": bool(_mapping_keys(user_data)),
                    }
                )

            path_metadata = _shape_attribute_metadata(path)
            paths_data.append(
                {
                    "pathIndex": path_index,
                    "shapeIndex": shape_indices.get(id(path)),
                    "nodes": nodes_data,
                    "closed": bool(getattr(path, "closed", True)),
                    "locked": bool(getattr(path, "locked", False)),
                    **path_metadata,
                }
            )
        
        layer_id = _get_layer_id(layer)
        layer_name = _layer_display_name(font, layer, getattr(layer, "associatedMasterId", None))
        result = {
            "pathDataVersion": 2,
            "glyphName": glyph_name,
            "masterId": getattr(layer, 'associatedMasterId', None),
            "masterName": layer_name,
            "layerId": layer_id,
            "paths": paths_data,
            "width": getattr(layer, 'width', 0),
            "leftSideBearing": _get_left_sidebearing(layer) or 0,
            "rightSideBearing": _get_right_sidebearing(layer) or 0
        }
        result.update(_font_format_metadata(font))
        shape_summary = _layer_shape_summary(layer)
        warnings = list(shape_summary.get("compatibilityWarnings") or [])
        if unsupported_node_types:
            warnings.append(
                "One or more node types are not normalized by the current Glyphs Python wrapper. "
                "Their raw types are preserved, and unsafe rewrites will be rejected."
            )
        if any(
            path_data["attributeKeys"] or path_data["hasUserData"]
            for path_data in paths_data
        ):
            warnings.append(
                "Path attributes and user data are read-only in this compatibility pass and are "
                "preserved automatically by set_glyph_paths."
            )
        result["compatibility"] = {
            **shape_summary,
            "metadataPolicy": "preserve",
            "unsupportedNodeTypes": unsupported_node_types,
            "safeForTopologyRewrite": not unsupported_node_types,
            "warnings": warnings,
        }
        result.update(
            _glyphs_show_layer_link_fields(
                getattr(font, "filepath", None),
                glyph_name=glyph_name,
                layer_id=layer_id,
                label="Open {} {} in Glyphs".format(glyph_name, layer_name),
            )
        )
        
        return _safe_json(result)
        
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
        font, fonts = _resolve_font_by_index(Glyphs, font_index)
        if not font:
            return json.dumps(_font_resolution_error(font_index, fonts, ok_key="success"))
        
        if not glyph_name:
            return json.dumps({"error": "Glyph name is required"})
        
        if not paths_data:
            return json.dumps({"error": "Path data is required"})
        
        # Parse the JSON path data
        try:
            path_info = json.loads(paths_data)
        except ValueError as e:
            return json.dumps({"error": "Invalid JSON in paths_data: {}".format(str(e))})
        if not isinstance(path_info, dict):
            return _safe_json(
                {
                    "success": False,
                    "error": "paths_data must decode to a JSON object",
                }
            )
        
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
        
        metadata_policy = path_info.get("metadataPolicy", "preserve")
        if metadata_policy != "preserve":
            return _safe_json(
                {
                    "success": False,
                    "error": "Unsupported metadataPolicy",
                    "metadataPolicy": metadata_policy,
                    "allowedMetadataPolicies": ["preserve"],
                }
            )

        path_specs = path_info.get("paths", [])
        if not isinstance(path_specs, list):
            return _safe_json(
                {
                    "success": False,
                    "error": "paths must be a JSON array",
                }
            )

        replace_result = _apply_path_specs_and_metrics(
            layer,
            path_specs,
            GSPath,
            GSNode,
            width=float(path_info["width"]) if "width" in path_info else None,
            left_sidebearing=float(path_info["leftSideBearing"]) if "leftSideBearing" in path_info else None,
            right_sidebearing=float(path_info["rightSideBearing"]) if "rightSideBearing" in path_info else None,
        )
        if not replace_result.get("ok"):
            return _safe_json(
                {
                    "success": False,
                    "error": replace_result.get("error") or "Failed to replace glyph paths",
                    "glyphName": glyph_name,
                    "fontIndex": font_index,
                    "expectedPathCount": len(path_specs),
                    "pathCount": replace_result.get("pathCount", 0),
                    "nodeCount": replace_result.get("nodeCount", 0),
                    "details": replace_result.get("details", []),
                    "rolledBack": replace_result.get("rolledBack"),
                }
            )

        # Send notification
        _show_notification(
            Glyphs,
            "Paths Updated", 
            "Updated paths for glyph '{}' in {}".format(glyph_name, font.familyName)
        )
        
        return _safe_json({
            "success": True,
            "message": "Updated paths for glyph '{}'".format(glyph_name),
            "pathDataVersion": 2,
            "metadataPolicy": "preserve",
            "pathEditMode": replace_result.get("pathEditMode"),
            "rolledBack": replace_result.get("rolledBack", False),
            **_layer_path_summary(layer),
        })
        
    except Exception as e:
        return json.dumps({"error": str(e)})
