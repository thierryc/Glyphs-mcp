"""Compact native selection reads; no persistent state, editing or history."""
from __future__ import annotations

import math
from typing import Any, Mapping
from glyphs_mcp_protocol.reads import SELECTION_NODE_LIMIT, SELECTION_NODE_MAX
from .core import BridgeError

COUNT_FIELDS = ("selectedNodeCount", "selectedAnchorCount", "selectedComponentCount",
                "selectedGuideCount", "selectedOtherCount")

def read(layer: Any, request: Mapping[str, Any], fields: list[str], identity) -> dict[str, Any]:
    detailed = "nodes" in fields
    limit = request.get("nodeLimit", SELECTION_NODE_LIMIT)
    if "nodeLimit" in request and not detailed:
        raise BridgeError("invalid_request", "nodeLimit requires the nodes field")
    if detailed and (set(request) - {"kind", "nodeLimit"} or type(limit) is not int
                     or not 1 <= limit <= SELECTION_NODE_MAX):
        raise BridgeError("invalid_request", "selection details accept only kind and nodeLimit (integer 1-256)")
    values = {}
    if "glyph" in fields:
        values["glyph"] = layer.parent.name if layer is not None else None
    if "layer" in fields:
        values["layer"] = layer.layerId if layer is not None else None
    counts = dict.fromkeys(COUNT_FIELDS, 0)
    if detailed or any(field in counts for field in fields):
        items = []
        if layer is not None:
            try:
                from GlyphsApp import GSNode, GSAnchor, GSComponent, GSGuide

                selection = layer.selection
                if selection is None:
                    raise ValueError("native selection collection is unavailable")
                classes = (GSNode, GSAnchor, GSComponent, GSGuide)
                selected_nodes = []
                for item in selection:
                    category = next((i for i, native in enumerate(classes) if isinstance(item, native)), 4)
                    counts[COUNT_FIELDS[category]] += 1
                    if detailed and category == 0 and len(selected_nodes) < limit:
                        selected_nodes.append(item)
                if selected_nodes:
                    items = _selected_node_details(layer, selected_nodes, identity)
            except Exception as error:
                raise BridgeError("unsupported_read", "native selection evidence unavailable: " + str(error)) from error
        values.update({field: counts[field] for field in fields if field in counts})
        if detailed:
            values["nodes"] = None if layer is None else {
                "total": counts["selectedNodeCount"], "returned": len(items), "limit": limit,
                "complete": len(items) == counts["selectedNodeCount"], "items": items,
            }
    return values

def _selected_node_details(layer: Any, nodes: list[Any], identity) -> list[dict[str, Any]]:
    # Paths-only indices: components in layer.shapes must not shift these.
    parents = {identity(node.parent) for node in nodes}
    paths = {}
    for index, path in enumerate(layer.paths):
        path_id = identity(path)
        if path_id in parents:
            if identity(path.parent) != identity(layer):
                raise ValueError("selected path does not belong to the active layer")
            paths[path_id] = (index, path)
            if len(paths) == len(parents):
                break
    if len(paths) != len(parents):
        raise ValueError("selected node parent is absent from the active layer paths")
    result = []
    for node in nodes:
        path_index, path = paths[identity(node.parent)]
        index = node.index
        if (not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(path.nodes)
                or identity(path.nodes[index]) != identity(node)):
            raise ValueError("selected node index does not identify the native node")
        x, y = float(node.position.x), float(node.position.y)
        kind, smooth = node.type, node.smooth
        if not (math.isfinite(x) and math.isfinite(y) and isinstance(kind, str) and kind
                and isinstance(smooth, bool)):
            raise ValueError("selected node properties are unavailable or invalid")
        result.append({"x": x, "y": y, "type": kind, "smooth": smooth,
                       "pathIndex": path_index, "nodeIndex": index})
    return result

