# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json
import traceback

from GlyphsApp import (  # type: ignore[import-not-found]
    CORNER,
    Glyphs,
    GSAnchor,
    GSComponent,
    GSHandle,
    GSHint,
    GSNode,
    GSPath,
)

from mcp_runtime import mcp
from mcp_tool_helpers import _get_component_automatic


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
                    "automatic": _get_component_automatic(component),
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
            if x_offset or y_offset or x_scale != 1 or y_scale != 1:
                for attr_name in ("automaticAlignment", "automatic"):
                    try:
                        setattr(component, attr_name, False)
                        break
                    except Exception:
                        continue
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
async def add_corner_to_all_masters(
    _corner_name: str | None = None,
    _alignment: str | int | None = None,
) -> str:
    """Add a corner component hint at the selected node(s) across all masters.

    This tool:
    - Processes all selected *nodes* (including extra/intersection nodes) in the active layer.
    - Processes selected intersection *handles* (``GSHandle``) by reusing their index path.
    - Skips other non-node selections (reported in the result).
    - Maps nodes across masters strictly by (pathIndex, nodeIndex) within layer.paths.
    - Skips + reports masters where the corresponding path/node index is missing.

    Args:
        _corner_name: Corner component name (e.g. ``_corner.inktrap``). Required.
        _alignment: Optional corner alignment. Accepted values are
            ``left``/``right``/``center`` (case-insensitive) or ``0``/``1``/``2``.
            Glyphs mapping: left=0, right=1, center=2.

    Returns:
        JSON encoded result with per-master add/skip details.
    """
    try:
        font = Glyphs.font
        if not font:
            return json.dumps({"error": "No font is currently active"})

        def _available_corner_names(current_font):
            names = []
            try:
                glyphs = getattr(current_font, "glyphs", []) or []
            except Exception:
                glyphs = []
            for g in glyphs:
                try:
                    name = getattr(g, "name", None)
                except Exception:
                    continue
                if isinstance(name, str) and name.startswith("_corner."):
                    names.append(name)
            return sorted(set(names))

        available_corners = _available_corner_names(font)
        corner_name = (_corner_name or "").strip() if _corner_name is not None else ""
        if not corner_name:
            return json.dumps(
                {
                    "error": "Missing required parameter: _corner_name",
                    "directive": "Re-run add_corner_to_all_masters and pass `_corner_name` set to one of `availableCorners` (full Glyphs corner component glyph name, e.g. `_corner.inktrap`).",
                    "availableCorners": available_corners,
                    "example": {"_corner_name": available_corners[0] if available_corners else "_corner.<name>"},
                }
            )
        if not corner_name.startswith("_corner."):
            return json.dumps(
                {
                    "error": "Invalid _corner_name (must start with '_corner.')",
                    "cornerName": corner_name,
                    "directive": "Pass the full corner glyph name, e.g. `_corner.inktrap`. Choose one from `availableCorners` and retry.",
                    "availableCorners": available_corners,
                }
            )
        if available_corners and corner_name not in available_corners:
            return json.dumps(
                {
                    "error": "Corner component not found in current font",
                    "cornerName": corner_name,
                    "directive": "Choose a value from `availableCorners` and retry. If the corner glyph is missing, create it in the font first.",
                    "availableCorners": available_corners,
                }
            )

        alignment_requested = _alignment
        alignment_value = None
        alignment_label = None
        if _alignment is not None:
            alignment_map = {"left": 0, "right": 1, "center": 2}
            label_map = {0: "left", 1: "right", 2: "center"}

            if isinstance(_alignment, str):
                normalized = _alignment.strip().lower()
                if normalized == "":
                    return json.dumps(
                        {
                            "error": "Invalid _alignment",
                            "alignment": _alignment,
                            "allowedAlignments": ["left", "right", "center", 0, 1, 2],
                            "directive": "Pass `_alignment` as `left`, `right`, `center`, or numeric `0`, `1`, `2`.",
                        }
                    )
                if normalized in alignment_map:
                    alignment_value = alignment_map[normalized]
                    alignment_label = normalized
                elif normalized in ("0", "1", "2"):
                    alignment_value = int(normalized)
                    alignment_label = label_map[alignment_value]
                else:
                    return json.dumps(
                        {
                            "error": "Invalid _alignment",
                            "alignment": _alignment,
                            "allowedAlignments": ["left", "right", "center", 0, 1, 2],
                            "directive": "Pass `_alignment` as `left`, `right`, `center`, or numeric `0`, `1`, `2`.",
                        }
                    )
            elif isinstance(_alignment, int):
                if _alignment in (0, 1, 2):
                    alignment_value = int(_alignment)
                    alignment_label = label_map[alignment_value]
                else:
                    return json.dumps(
                        {
                            "error": "Invalid _alignment",
                            "alignment": _alignment,
                            "allowedAlignments": ["left", "right", "center", 0, 1, 2],
                            "directive": "Pass `_alignment` as `left`, `right`, `center`, or numeric `0`, `1`, `2`.",
                        }
                    )
            else:
                return json.dumps(
                    {
                        "error": "Invalid _alignment",
                        "alignment": _alignment,
                        "allowedAlignments": ["left", "right", "center", 0, 1, 2],
                        "directive": "Pass `_alignment` as `left`, `right`, `center`, or numeric `0`, `1`, `2`.",
                    }
                )

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
                    "availableCorners": available_corners,
                    "skippedSelection": skipped_selection,
                }
            )

        masters = list(getattr(font, "masters", []) or [])
        results = []
        total_added = 0
        total_updated = 0
        total_skipped = 0

        for master in masters:
            master_result = {
                "masterId": getattr(master, "id", None),
                "masterName": getattr(master, "name", ""),
                "addedCount": 0,
                "updatedCount": 0,
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

                existing_hint = None
                for hint in t_hints:
                    try:
                        if getattr(hint, "type", None) != CORNER:
                            continue
                        if getattr(hint, "name", None) != corner_name:
                            continue
                        if getattr(hint, "originNode", None) is t_node:
                            existing_hint = hint
                            break
                    except Exception:
                        continue

                if existing_hint is not None:
                    if alignment_value is not None:
                        current_alignment = getattr(existing_hint, "options", None)
                        if current_alignment != alignment_value:
                            try:
                                existing_hint.options = alignment_value
                                master_result["updatedCount"] += 1
                                total_updated += 1
                            except Exception:
                                master_result["skipped"].append(
                                    {
                                        "pathIndex": p_index,
                                        "nodeIndex": n_index,
                                        "reason": "Failed to update corner alignment on existing hint",
                                    }
                                )
                                total_skipped += 1
                        else:
                            master_result["skipped"].append(
                                {
                                    "pathIndex": p_index,
                                    "nodeIndex": n_index,
                                    "reason": "Corner hint already exists with requested alignment",
                                }
                            )
                            total_skipped += 1
                    else:
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
                if alignment_value is not None:
                    new_hint.options = alignment_value
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

                existing_hint = None
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
                        existing_hint = hint
                        break
                    except Exception:
                        continue

                if existing_hint is not None:
                    if alignment_value is not None:
                        current_alignment = getattr(existing_hint, "options", None)
                        if current_alignment != alignment_value:
                            try:
                                existing_hint.options = alignment_value
                                master_result["updatedCount"] += 1
                                total_updated += 1
                            except Exception:
                                master_result["skipped"].append(
                                    {
                                        "type": "GSHandle",
                                        "originIndex": origin_index_list or None,
                                        "reason": "Failed to update corner alignment on existing hint",
                                    }
                                )
                                total_skipped += 1
                        else:
                            master_result["skipped"].append(
                                {
                                    "type": "GSHandle",
                                    "originIndex": origin_index_list or None,
                                    "reason": "Corner hint already exists with requested alignment",
                                }
                            )
                            total_skipped += 1
                    else:
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
                if alignment_value is not None:
                    new_hint.options = alignment_value
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
                "availableCorners": available_corners,
                "alignmentRequested": alignment_requested,
                "alignmentApplied": alignment_value,
                "alignmentLabel": alignment_label,
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
                "totalUpdated": total_updated,
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

#+#+#+#+#+#+#+#+assistant to=functions.apply_patch>exit code: 0, success? We'll craft real patch.
