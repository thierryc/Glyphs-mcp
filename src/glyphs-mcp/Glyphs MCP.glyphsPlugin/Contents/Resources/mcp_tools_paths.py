# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json

from GlyphsApp import Glyphs, GSNode, GSPath  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import _clear_layer_paths, _safe_json


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
