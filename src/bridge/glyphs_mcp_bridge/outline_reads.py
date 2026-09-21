"""Bounded, stale-checked path and segment geometry reads."""

import base64
import binascii
import json
import math

from glyphs_mcp_protocol.outline import path_hash
from glyphs_mcp_protocol.reads import PATH_NODE_PAGE_LIMIT, PATH_PAGE_LIMIT

from .core import BridgeError
from .context import value


def _point(owner):
    position = value(owner, "position", owner)
    return float(value(position, "x", 0) or 0), float(value(position, "y", 0) or 0)


def _node(node):
    x, y = _point(node)
    kind = str(value(node, "type", "") or "").lower()
    if kind not in ("line", "curve", "qcurve", "offcurve"):
        raise BridgeError("unsupported_read", "path contains an unsupported native node type")
    name = value(node, "name", None)
    return {"x": x, "y": y, "type": kind, "smooth": bool(value(node, "smooth", False)),
            "name": str(name) if name is not None else None}


def path_state(path):
    nodes = list(value(path, "nodes", []) or [])
    if len(nodes) > 4096:
        raise BridgeError("unsupported_read", "path exceeds the 4,096-node safety limit")
    return {"closed": bool(value(path, "closed", False)), "locked": bool(value(path, "locked", False)),
            "nodes": [_node(node) for node in nodes]}


def _layer(adapter, font, request):
    if set(request) - {"kind", "glyph", "layer", "index", "path", "endNode", "limit", "cursor"}:
        raise BridgeError("invalid_request", "path selectors contain unsupported fields")
    name, identity = request.get("glyph"), request.get("layer")
    if not isinstance(name, str) or not name or not isinstance(identity, str) or not identity:
        raise BridgeError("invalid_request", "path selectors require glyph and exact layer ID")
    return adapter._entity(font, "layer", {"glyph": name, "id": identity})


def _paths(layer):
    return list(value(layer, "paths", []) or [])


def _path(layer, index):
    if type(index) is not int or index < 0:
        raise BridgeError("invalid_request", "path index must be a non-negative integer")
    paths = _paths(layer)
    if index >= len(paths):
        raise BridgeError("target_not_found", "path index is unavailable")
    return paths[index]


def _bounds(nodes):
    if not nodes:
        return None
    xs, ys = [node["x"] for node in nodes], [node["y"] for node in nodes]
    return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}


def _segment_count(state):
    oncurves = sum(node["type"] != "offcurve" for node in state["nodes"])
    return oncurves if state["closed"] else max(0, oncurves - 1)


def _shape_index(layer, path, fallback):
    shapes = value(layer, "shapes", None)
    if shapes is None:
        return fallback
    try:
        return shapes.index(path)
    except Exception:
        for index, shape in enumerate(shapes):
            if shape is path:
                return index
    return None


def _cursor(prefix, payload):
    return prefix + base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def _decode(cursor, prefix):
    if not isinstance(cursor, str) or not cursor.startswith(prefix) or len(cursor) > 4096:
        raise BridgeError("invalid_request", "use the unmodified nextCursor from the previous path page")
    try:
        result = json.loads(base64.b64decode(cursor[len(prefix):], altchars=b"-_", validate=True))
    except (ValueError, TypeError, binascii.Error, RecursionError) as error:
        raise BridgeError("invalid_request", "invalid path cursor") from error
    if not isinstance(result, dict):
        raise BridgeError("invalid_request", "invalid path cursor")
    return result


def _page_guard(adapter, font, document_id, request, total, fingerprint, prefix):
    cursor = _decode(request["cursor"], prefix) if "cursor" in request else None
    offset = cursor.get("offset") if cursor else 0
    expected = {"document": document_id, "glyph": request["glyph"], "layer": request["layer"],
                "total": total, "generation": adapter._generation(font), "dirty": adapter._dirty(font),
                "hash": fingerprint, "selector": [request["kind"], request.get("index")]}
    if (type(offset) is not int or offset < 0 or offset > total
            or cursor and set(cursor) != set(expected) | {"offset"}
            or cursor and any(cursor.get(key) != item for key, item in expected.items())):
        raise BridgeError("stale_path_cursor", "path geometry changed; restart the path read")
    return offset, expected


def paths_page(adapter, font, document_id, request, fields):
    if set(request) - {"kind", "glyph", "layer", "limit", "cursor"}:
        raise BridgeError("invalid_request", "path pages accept only kind, glyph, layer, limit and cursor")
    if fields != ["items"]:
        raise BridgeError("unsupported_read", "path pages use fields [items]")
    layer, limit = _layer(adapter, font, request), request.get("limit", PATH_PAGE_LIMIT)
    if type(limit) is not int or not 1 <= limit <= PATH_PAGE_LIMIT:
        raise BridgeError("invalid_request", "path page limit must be an integer from 1 to 100")
    paths = _paths(layer)
    total = len(paths)
    cursor = _decode(request["cursor"], "ps1.") if "cursor" in request else None
    guard = {"document": document_id, "glyph": request["glyph"], "layer": request["layer"],
             "total": total, "generation": adapter._generation(font), "dirty": adapter._dirty(font)}
    offset = cursor.get("offset") if cursor else 0
    if (type(offset) is not int or offset < 0 or offset > total
            or cursor and set(cursor) != set(guard) | {"offset", "after"}
            or cursor and any(cursor.get(key) != item for key, item in guard.items())
            or cursor and (offset == 0 or path_hash(path_state(paths[offset-1])) != cursor.get("after"))):
        raise BridgeError("stale_path_cursor", "path geometry changed; restart the path read")
    items = []
    for index in range(offset, min(len(paths), offset + limit)):
        state = path_state(paths[index])
        items.append({"index": index, "shapeIndex": _shape_index(layer, paths[index], index), "open": not state["closed"],
                      "closed": state["closed"], "locked": state["locked"],
                      "nodeCount": len(state["nodes"]), "segmentCount": _segment_count(state),
                      "bounds": _bounds(state["nodes"]), "pathHash": path_hash(state)})
    end = offset + len(items)
    next_cursor = _cursor("ps1.", {**guard, "offset": end, "after": items[-1]["pathHash"]}) if end < len(paths) else None
    return [{"entity": dict(request), "values": {"items": items, "total": len(paths),
             "returned": len(items), "complete": end == len(paths), "nextCursor": next_cursor}}]


def path_page(adapter, font, document_id, request, fields):
    if set(request) - {"kind", "glyph", "layer", "index", "limit", "cursor"}:
        raise BridgeError("invalid_request", "path reads accept only kind, glyph, layer, index, limit and cursor")
    if fields != ["nodes"]:
        raise BridgeError("unsupported_read", "path reads use fields [nodes]")
    layer = _layer(adapter, font, request)
    path = _path(layer, request.get("index"))
    state, limit = path_state(path), request.get("limit", PATH_NODE_PAGE_LIMIT)
    if type(limit) is not int or not 1 <= limit <= PATH_NODE_PAGE_LIMIT:
        raise BridgeError("invalid_request", "path node limit must be an integer from 1 to 256")
    fingerprint = path_hash(state)
    offset, guard = _page_guard(adapter, font, document_id, request, len(state["nodes"]), fingerprint, "pn1.")
    nodes = [{"index": index, **state["nodes"][index]}
             for index in range(offset, min(len(state["nodes"]), offset + limit))]
    end = offset + len(nodes)
    next_cursor = _cursor("pn1.", {**guard, "offset": end}) if end < len(state["nodes"]) else None
    values = {"index": request["index"], "closed": state["closed"], "locked": state["locked"],
              "pathHash": fingerprint, "nodes": nodes, "total": len(state["nodes"]),
              "returned": len(nodes), "complete": end == len(state["nodes"]), "nextCursor": next_cursor}
    return [{"entity": dict(request), "values": values}]


def segment_data(state, end_index):
    nodes, closed = state["nodes"], state["closed"]
    if type(end_index) is not int or not 0 <= end_index < len(nodes):
        raise BridgeError("target_not_found", "segment end node is unavailable")
    if nodes[end_index]["type"] == "offcurve":
        raise BridgeError("invalid_request", "segment endNode must be on-curve")
    indices, cursor = [end_index], (end_index - 1) % len(nodes)
    while cursor != end_index and nodes[cursor]["type"] == "offcurve":
        indices.append(cursor)
        if not closed and cursor == 0:
            break
        cursor = (cursor - 1) % len(nodes)
    if nodes[cursor]["type"] == "offcurve" or cursor == end_index:
        raise BridgeError("invalid_request", "segment has no preceding on-curve node")
    if not closed and cursor > end_index:
        raise BridgeError("invalid_request", "open path segment wraps its endpoints")
    indices.append(cursor)
    indices.reverse()
    controls = indices[1:-1]
    end_type = nodes[end_index]["type"]
    if not controls and end_type == "line":
        kind = "line"
    elif len(controls) == 2 and end_type == "curve":
        kind = "curve"
    elif controls and end_type == "qcurve":
        kind = "qcurve"
    else:
        raise BridgeError("unsupported_read", "segment is malformed or has an unsupported type")
    points = [[nodes[index]["x"], nodes[index]["y"]] for index in indices]
    return kind, indices[0], controls, points


def point_at(kind, points, t):
    if kind == "line":
        a, b = points
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    if kind == "curve":
        a, b, c, d = points
        u = 1 - t
        return (u**3*a[0] + 3*u*u*t*b[0] + 3*u*t*t*c[0] + t**3*d[0],
                u**3*a[1] + 3*u*u*t*b[1] + 3*u*t*t*c[1] + t**3*d[1])
    controls, pieces = points[1:-1], []
    start = points[0]
    for index, control in enumerate(controls):
        end = points[-1] if index == len(controls) - 1 else [
            (control[0] + controls[index + 1][0]) / 2, (control[1] + controls[index + 1][1]) / 2]
        pieces.append((start, control, end))
        start = end
    scaled = min(t * len(pieces), len(pieces) - 1e-15)
    a, b, c = pieces[int(scaled)]
    local, u = scaled - int(scaled), 1 - (scaled - int(scaled))
    return (u*u*a[0] + 2*u*local*b[0] + local*local*c[0],
            u*u*a[1] + 2*u*local*b[1] + local*local*c[1])


def sampled(kind, points, count):
    values = [point_at(kind, points, index / count) for index in range(count + 1)]
    lengths, total = [0.0], 0.0
    for before, after in zip(values, values[1:]):
        total += math.hypot(after[0] - before[0], after[1] - before[1])
        lengths.append(total)
    return values, lengths, total


def converged_samples(kind, points):
    if kind == "line":
        return sampled(kind, points, 1)
    previous = None
    for count in (16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
        result = sampled(kind, points, count)
        if previous is not None and abs(result[2] - previous) <= max(1e-7, result[2] * 1e-7):
            return result
        previous = result[2]
    raise BridgeError("measurement_failed", "arc-length measurement did not converge within 4,096 samples")


def segment(adapter, font, document_id, request, fields):
    if set(request) != {"kind", "glyph", "layer", "path", "endNode"}:
        raise BridgeError("invalid_request", "segment reads require exact kind, glyph, layer, path and endNode fields")
    allowed = {"type", "startNode", "endNode", "controlNodes", "points", "length", "pathHash"}
    if not fields or set(fields) - allowed:
        raise BridgeError("unsupported_read", "segment fields are type, startNode, endNode, controlNodes, points, length and pathHash")
    layer = _layer(adapter, font, request)
    state = path_state(_path(layer, request.get("path")))
    kind, start, controls, points = segment_data(state, request.get("endNode"))
    all_values = {"type": kind, "startNode": start, "endNode": request["endNode"],
                  "controlNodes": controls, "points": points,
                  "length": converged_samples(kind, points)[2], "pathHash": path_hash(state)}
    return [{"entity": dict(request), "values": {field: all_values[field] for field in dict.fromkeys(fields)}}]
