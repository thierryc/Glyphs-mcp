# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import _get_left_sidebearing, _get_right_sidebearing, _safe_json


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

