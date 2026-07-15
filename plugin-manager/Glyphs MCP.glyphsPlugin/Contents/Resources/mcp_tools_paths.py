# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json

from GlyphsApp import Glyphs, GSNode, GSPath  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import (
    _font_resolution_error,
    _get_layer_id,
    _get_left_sidebearing,
    _get_right_sidebearing,
    _glyphs_show_layer_link_fields,
    _layer_display_name,
    _layer_path_summary,
    _replace_layer_paths_and_metrics,
    _resolve_font_by_index,
    _safe_json,
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
        
        layer_id = _get_layer_id(layer)
        layer_name = _layer_display_name(font, layer, getattr(layer, "associatedMasterId", None))
        result = {
            "glyphName": glyph_name,
            "masterId": getattr(layer, 'associatedMasterId', None),
            "masterName": layer_name,
            "layerId": layer_id,
            "paths": paths_data,
            "width": getattr(layer, 'width', 0),
            "leftSideBearing": _get_left_sidebearing(layer) or 0,
            "rightSideBearing": _get_right_sidebearing(layer) or 0
        }
        result.update(
            _glyphs_show_layer_link_fields(
                getattr(font, "filepath", None),
                glyph_name=glyph_name,
                layer_id=layer_id,
                label="Open {} {} in Glyphs".format(glyph_name, layer_name),
            )
        )
        
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
        
        # Build new paths from the JSON data
        new_paths = []
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
                new_paths.append(new_path)

        replace_result = _replace_layer_paths_and_metrics(
            layer,
            new_paths,
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
                    "expectedPathCount": len(new_paths),
                    "pathCount": replace_result.get("pathCount", 0),
                    "nodeCount": replace_result.get("nodeCount", 0),
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
            **_layer_path_summary(layer),
        })
        
    except Exception as e:
        return json.dumps({"error": str(e)})
