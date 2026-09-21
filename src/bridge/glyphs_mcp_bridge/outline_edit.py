"""Native outline operations with identity-preserving snapshots and restoration."""

from __future__ import annotations

from typing import Any, Mapping

from glyphs_mcp_protocol.outline import outline_state_hash


def native_remove_available():
    """Return whether this Glyphs host exposes its keep-shape node remover."""
    try:
        from GlyphsApp import GSPath  # type: ignore[import-not-found]
        return callable(getattr(GSPath(), "removeNodeCheckKeepShape_", None))
    except Exception:
        return False


def _call(value):
    return value() if callable(value) else value


def _value(owner, name, default=None):
    try:
        return _call(getattr(owner, name))
    except Exception:
        return default


def _point(owner):
    point = _value(owner, "position", owner)
    return float(_value(point, "x", 0) or 0), float(_value(point, "y", 0) or 0)


def _identity(owner):
    try:
        import objc  # type: ignore[import-not-found]
        return int(objc.pyobjc_id(owner))
    except Exception:
        return id(owner)


def _node_state(node):
    x, y = _point(node)
    return {"x": x, "y": y, "type": str(_value(node, "type", "") or "").lower(),
            "smooth": bool(_value(node, "smooth", False)),
            "name": None if _value(node, "name", None) is None else str(_value(node, "name", None))}


def _is_path(shape):
    return hasattr(shape, "nodes") and hasattr(shape, "closed")


def _transform(shape):
    value = _value(shape, "transform", None)
    try:
        return [float(item) for item in value]
    except Exception:
        return None


def shape_state(layer):
    shapes = list(_value(layer, "shapes", []) or [])
    if not shapes:
        shapes = list(_value(layer, "paths", []) or []) + list(_value(layer, "components", []) or [])
    result = []
    for shape in shapes:
        if _is_path(shape):
            nodes = list(_value(shape, "nodes", []) or [])
            if len(nodes) > 4096:
                raise ValueError("path exceeds the 4,096-node limit")
            result.append({"kind": "path", "closed": bool(_value(shape, "closed", False)),
                           "locked": bool(_value(shape, "locked", False)),
                           "nodes": [_node_state(node) for node in nodes]})
        else:
            result.append({"kind": "component", "name": str(_value(shape, "componentName", "") or ""),
                           "transform": _transform(shape)})
    return result


def hash_layer(layer):
    return outline_state_hash(shape_state(layer))


def _path_snap(path):
    nodes = list(path.nodes)
    properties = []
    for node in nodes:
        properties.append({"node": node, "position": _point(node), "type": _value(node, "type"),
                           "connection": _value(node, "connection", None),
                           "smooth": bool(_value(node, "smooth", False)),
                           "name": _value(node, "name", None), "orientation": _value(node, "orientation", None)})
    return {"path": path, "nodes": nodes, "properties": properties,
            "closed": bool(_value(path, "closed", False)), "locked": bool(_value(path, "locked", False))}


def capture(layer, _change=None):
    shapes = list(_value(layer, "shapes", []) or [])
    paths = list(_value(layer, "paths", []) or [])
    return {"shapes": shapes, "paths": [_path_snap(path) for path in paths]}


def _set_shapes(layer, shapes):
    shapes = list(shapes)
    try:
        layer.shapes = shapes
        if [_identity(item) for item in layer.shapes] == [_identity(item) for item in shapes]:
            return
    except Exception:
        pass
    collection = layer.shapes
    for index in range(len(collection) - 1, -1, -1):
        del collection[index]
    for shape in shapes:
        collection.append(shape)
    if [_identity(item) for item in layer.shapes] != [_identity(item) for item in shapes]:
        raise ValueError("Glyphs did not restore exact shape order")


def _set_nodes(path, nodes):
    nodes = list(nodes)
    try:
        path.nodes = nodes
        if [_identity(item) for item in path.nodes] == [_identity(item) for item in nodes]:
            return
    except Exception:
        pass
    collection = path.nodes
    for index in range(len(collection) - 1, -1, -1):
        del collection[index]
    for node in nodes:
        collection.append(node)
    if [_identity(item) for item in path.nodes] != [_identity(item) for item in nodes]:
        raise ValueError("Glyphs did not restore exact node order")


def _selected(layer):
    try:
        return list(layer.selection)
    except Exception:
        return []


def _retain_selection(layer, selected):
    live = [node for path in _paths(layer) for node in list(path.nodes)]
    for name in ("anchors", "components", "guides"):
        live.extend(list(_value(layer, name, []) or []))
    identities = {_identity(item) for item in live}
    wanted = [item for item in selected if _identity(item) in identities]
    try:
        layer.selection = wanted
    except Exception:
        pass


def restore(layer, snapshot):
    selected = _selected(layer)
    _set_shapes(layer, snapshot["shapes"])
    for item in snapshot["paths"]:
        path = item["path"]
        _set_nodes(path, item["nodes"])
        path.closed = item["closed"]
        try:
            path.locked = item["locked"]
        except Exception:
            pass
        for state in item["properties"]:
            node = state["node"]
            node.position = state["position"]
            node.type = state["type"]
            if state["connection"] is not None:
                try:
                    node.connection = state["connection"]
                except Exception:
                    node.smooth = state["smooth"]
            else:
                node.smooth = state["smooth"]
            node.name = "" if state["name"] is None else state["name"]
            if state["orientation"] is not None:
                try:
                    node.orientation = state["orientation"]
                except Exception:
                    pass
    _retain_selection(layer, selected)


def _paths(layer):
    return list(layer.paths)


def _path(layer, index, *, allow_end=False):
    paths = _paths(layer)
    if index == len(paths) and allow_end:
        return None
    if index < 0 or index >= len(paths):
        raise ValueError("outline path index is unavailable")
    path = paths[index]
    if bool(_value(path, "locked", False)):
        raise ValueError("locked outline paths cannot be edited")
    return path


def _references(layer, nodes):
    wanted = {_identity(node) for node in nodes}
    for hint in list(_value(layer, "hints", []) or []):
        for field in ("originNode", "targetNode", "otherNode1", "otherNode2"):
            node = _value(hint, field, None)
            if node is not None and _identity(node) in wanted:
                return True
    return False


def _validate(path):
    nodes = list(path.nodes)
    if not 2 <= len(nodes) <= 4096:
        raise ValueError("resulting path must contain 2-4,096 nodes")
    kinds = [str(node.type).lower() for node in nodes]
    if any(kind not in ("line", "curve", "qcurve", "offcurve") for kind in kinds):
        raise ValueError("path contains an unsupported node type")
    oncurves = [index for index, kind in enumerate(kinds) if kind != "offcurve"]
    if len(oncurves) < 2:
        raise ValueError("path requires at least two on-curve nodes")
    if not path.closed and (kinds[0] == "offcurve" or kinds[-1] == "offcurve"):
        raise ValueError("open paths must begin and end on-curve")
    ends = oncurves if path.closed else oncurves[1:]
    for end in ends:
        cursor, controls = (end - 1) % len(nodes), 0
        while kinds[cursor] == "offcurve" and cursor != end:
            controls += 1
            cursor = (cursor - 1) % len(nodes)
        if (controls == 0 and kinds[end] != "line"
                or controls == 2 and kinds[end] != "curve"
                or controls not in (0, 2) and not (controls > 0 and kinds[end] == "qcurve")):
            raise ValueError("resulting path has malformed line, cubic, or quadratic segments")


def _make_start(path, index):
    nodes = list(path.nodes)
    if index >= len(nodes) or str(nodes[index].type).lower() == "offcurve":
        raise ValueError("start node must be an existing on-curve node")
    target = nodes[index]
    method = getattr(target, "makeNodeFirst", None)
    if callable(method):
        method()
    else:
        path.makeNodeFirst_(nodes[(index - 1) % len(nodes)])


def _segment_start(path, end):
    nodes = list(path.nodes)
    if end >= len(nodes) or str(nodes[end].type).lower() == "offcurve":
        raise ValueError("split endNode must be an existing on-curve node")
    cursor = (end - 1) % len(nodes)
    while cursor != end and str(nodes[cursor].type).lower() == "offcurve":
        if not path.closed and cursor == 0:
            break
        cursor = (cursor - 1) % len(nodes)
    if cursor == end or str(nodes[cursor].type).lower() == "offcurve" or not path.closed and cursor > end:
        raise ValueError("split segment has no valid preceding on-curve")
    return cursor


def _new_path(spec):
    from GlyphsApp import GSNode, GSPath  # type: ignore[import-not-found]
    path = GSPath()
    path.closed = spec["closed"]
    nodes = []
    for raw in spec["nodes"]:
        node = GSNode()
        node.position = (raw["x"], raw["y"])
        node.type = raw["type"]
        node.smooth = raw.get("smooth", False)
        if "name" in raw:
            node.name = "" if raw["name"] is None else raw["name"]
        nodes.append(node)
    _set_nodes(path, nodes)
    _validate(path)
    return path


def _insert_path(layer, path_index, path):
    paths = _paths(layer)
    if path_index > len(paths):
        raise ValueError("path insertion index is unavailable")
    shapes = list(_value(layer, "shapes", []) or [])
    if not shapes:
        layer.paths.insert(path_index, path)
        return
    if path_index < len(paths):
        shape_index = shapes.index(paths[path_index])
    elif paths:
        shape_index = shapes.index(paths[-1]) + 1
    else:
        shape_index = len(shapes)
    shapes.insert(shape_index, path)
    _set_shapes(layer, shapes)


def _remove_path(layer, path):
    shapes = list(_value(layer, "shapes", []) or [])
    if shapes:
        shapes.remove(path)
        _set_shapes(layer, shapes)
    else:
        layer.paths.remove(path)


def apply_operation(layer, operation):
    op, index = operation["op"], operation["path"]
    if op == "add_path":
        _insert_path(layer, index, _new_path(operation))
        return
    path = _path(layer, index)
    if op == "split_segment":
        nodes = list(path.nodes)
        if operation["startNode"] >= len(nodes) or operation["endNode"] >= len(nodes):
            raise ValueError("split segment indices are unavailable")
        if _segment_start(path, operation["endNode"]) != operation["startNode"]:
            raise ValueError("split startNode does not identify the requested segment")
        upper = 1.0
        for parameter in sorted(operation["pathTimes"], reverse=True):
            local = parameter / upper
            path.insertNodeWithPathTime_(operation["endNode"] + local)
            upper = parameter
    elif op == "update_nodes":
        nodes = list(path.nodes)
        for update in operation["updates"]:
            if update["index"] >= len(nodes):
                raise ValueError("node update index is unavailable")
            node = nodes[update["index"]]
            if "position" in update:
                node.position = (update["position"]["x"], update["position"]["y"])
            if "delta" in update:
                x, y = _point(node)
                node.position = (x + update["delta"]["dx"], y + update["delta"]["dy"])
            for key in ("type", "smooth"):
                if key in update:
                    setattr(node, key, update[key])
            if "name" in update:
                node.name = "" if update["name"] is None else update["name"]
    elif op == "delete_nodes":
        nodes = list(path.nodes)
        removed = [nodes[item] for item in operation["nodes"] if item < len(nodes)]
        if len(removed) != len(operation["nodes"]):
            raise ValueError("node deletion index is unavailable")
        if _references(layer, removed):
            raise ValueError("node deletion is blocked by a native hint reference")
        _set_nodes(path, [node for position, node in enumerate(nodes) if position not in set(operation["nodes"])])
    elif op == "remove_node":
        nodes = list(path.nodes)
        index = operation["node"]
        if index >= len(nodes):
            raise ValueError("remove_node index is unavailable")
        target = nodes[index]
        if str(_value(target, "type", "") or "").lower() == "offcurve":
            raise ValueError("remove_node requires an existing on-curve node")
        expected = operation["removedNodes"]
        if any(position >= len(nodes) for position in expected):
            raise ValueError("resolved native removal index is unavailable")
        affected = [nodes[position] for position in expected]
        if _references(layer, affected):
            raise ValueError("node removal is blocked by a native hint reference")
        method = getattr(path, "removeNodeCheckKeepShape_", None)
        if not callable(method):
            raise ValueError("Glyphs does not support native shape-preserving node removal")
        before_ids = [_identity(node) for node in nodes]
        if not bool(method(target)):
            raise ValueError("Glyphs rejected shape-preserving node removal")
        after_nodes = list(path.nodes)
        after_ids = {_identity(node) for node in after_nodes}
        if len(after_ids) != len(after_nodes):
            raise ValueError("Glyphs returned duplicate node identities after removal")
        actual = [position for position, identity in enumerate(before_ids) if identity not in after_ids]
        added = [node for node in after_nodes if _identity(node) not in set(before_ids)]
        if added or actual != expected or before_ids[index] in after_ids:
            raise ValueError("Glyphs native removal did not match the prepared node set")
    elif op == "reverse_path":
        path.reverse()
    elif op == "set_start_node":
        if not path.closed:
            raise ValueError("only closed paths have a start node")
        _make_start(path, operation["node"])
    elif op == "set_closed":
        if operation["closed"]:
            path.closed = True
        else:
            if not path.closed:
                raise ValueError("path is already open")
            _make_start(path, operation["startNode"])
            nodes = list(path.nodes)
            while nodes and str(nodes[-1].type).lower() == "offcurve":
                if _references(layer, [nodes[-1]]):
                    raise ValueError("opening path is blocked by a native hint reference")
                nodes.pop()
            _set_nodes(path, nodes)
            path.closed = False
    elif op == "delete_path":
        nodes = list(path.nodes)
        if _references(layer, nodes):
            raise ValueError("path deletion is blocked by a native hint reference")
        _remove_path(layer, path)
        return
    else:
        raise ValueError("unsupported outline operation")
    _validate(path)


def apply(layer, change):
    selected = _selected(layer)
    try:
        for operation in change["operations"]:
            apply_operation(layer, operation)
    finally:
        _retain_selection(layer, selected)
