"""Prepare typed outline operations against detached native layer copies."""

from __future__ import annotations

import bisect
import math

from glyphs_mcp_protocol.outline import outline_state_hash, path_hash, validate_options

from .worker import WorkerError


def _value(owner, name, default=None):
    try:
        value = getattr(owner, name)
        return value() if callable(value) else value
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


def _node(node):
    x, y = _point(node)
    return {"x": x, "y": y, "type": str(_value(node, "type", "") or "").lower(),
            "smooth": bool(_value(node, "smooth", False)),
            "name": None if _value(node, "name", None) is None else str(_value(node, "name", None))}


def _path_state(path):
    nodes = list(_value(path, "nodes", []) or [])
    if len(nodes) > 4096:
        raise WorkerError("path exceeds the 4,096-node limit")
    return {"closed": bool(_value(path, "closed", False)), "locked": bool(_value(path, "locked", False)),
            "nodes": [_node(node) for node in nodes]}


def _shape_state(layer):
    shapes = list(_value(layer, "shapes", []) or [])
    if not shapes:
        shapes = list(layer.paths) + list(_value(layer, "components", []) or [])
    result = []
    for shape in shapes:
        if hasattr(shape, "nodes") and hasattr(shape, "closed"):
            result.append({"kind": "path", **_path_state(shape)})
        else:
            transform = _value(shape, "transform", None)
            try:
                transform = [float(item) for item in transform]
            except Exception:
                transform = None
            result.append({"kind": "component", "name": str(_value(shape, "componentName", "") or ""),
                           "transform": transform})
    return result


def _paths(layer):
    return list(layer.paths)


def _path(layer, index, allow_end=False):
    paths = _paths(layer)
    if allow_end and index == len(paths):
        return None
    if index < 0 or index >= len(paths):
        raise WorkerError("outline path index is unavailable")
    path = paths[index]
    if bool(_value(path, "locked", False)):
        raise WorkerError("locked outline paths cannot be edited")
    return path


def _segment(state, end):
    nodes, closed = state["nodes"], state["closed"]
    if end >= len(nodes) or nodes[end]["type"] == "offcurve":
        raise WorkerError("split endNode must be an existing on-curve node")
    indices, cursor = [end], (end - 1) % len(nodes)
    while cursor != end and nodes[cursor]["type"] == "offcurve":
        indices.append(cursor)
        if not closed and cursor == 0:
            break
        cursor = (cursor - 1) % len(nodes)
    if nodes[cursor]["type"] == "offcurve" or cursor == end or not closed and cursor > end:
        raise WorkerError("split segment has no valid preceding on-curve")
    indices.append(cursor)
    indices.reverse()
    controls, end_type = indices[1:-1], nodes[end]["type"]
    if not controls and end_type == "line":
        kind = "line"
    elif len(controls) == 2 and end_type == "curve":
        kind = "curve"
    elif controls and end_type == "qcurve":
        kind = "qcurve"
    else:
        raise WorkerError("split segment is malformed or unsupported")
    return kind, indices[0], [[nodes[i]["x"], nodes[i]["y"]] for i in indices]


def _at(kind, points, t):
    if kind == "line":
        a, b = points
        return a[0] + (b[0]-a[0])*t, a[1] + (b[1]-a[1])*t
    if kind == "curve":
        a, b, c, d = points
        u = 1-t
        return (u**3*a[0]+3*u*u*t*b[0]+3*u*t*t*c[0]+t**3*d[0],
                u**3*a[1]+3*u*u*t*b[1]+3*u*t*t*c[1]+t**3*d[1])
    controls, pieces, start = points[1:-1], [], points[0]
    for index, control in enumerate(controls):
        end = points[-1] if index == len(controls)-1 else [(control[0]+controls[index+1][0])/2,
                                                           (control[1]+controls[index+1][1])/2]
        pieces.append((start, control, end)); start = end
    scaled = min(t*len(pieces), len(pieces)-1e-15)
    index, local = int(scaled), scaled-int(scaled)
    a, b, c = pieces[index]; u = 1-local
    return u*u*a[0]+2*u*local*b[0]+local*local*c[0], u*u*a[1]+2*u*local*b[1]+local*local*c[1]


def _samples(kind, points, count):
    values = [_at(kind, points, i/count) for i in range(count+1)]
    lengths, total = [0.0], 0.0
    for a, b in zip(values, values[1:]):
        total += math.hypot(b[0]-a[0], b[1]-a[1]); lengths.append(total)
    return lengths, total


def _path_times(kind, points, fractions, measure):
    if measure == "path_time" or kind == "line":
        _lengths, total = _samples(kind, points, 1 if kind == "line" else 16)
        if total <= 1e-12:
            raise WorkerError("cannot split a degenerate segment")
        return list(fractions)
    previous = None
    for count in (16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
        lengths, total = _samples(kind, points, count)
        if previous is not None and abs(total-previous) <= max(1e-7, total*1e-7):
            if total <= 1e-12:
                raise WorkerError("cannot split a degenerate segment")
            result = []
            for fraction in fractions:
                wanted = fraction*total
                index = min(max(1, bisect.bisect_left(lengths, wanted)), count)
                span = lengths[index]-lengths[index-1]
                local = 0 if span == 0 else (wanted-lengths[index-1])/span
                result.append((index-1+local)/count)
            return result
        previous = total
    raise WorkerError("arc-length measurement did not converge within 4,096 samples")


def _set_nodes(path, nodes):
    nodes = list(nodes)
    expected = [_identity(node) for node in nodes]
    try:
        path.nodes = nodes
        if [_identity(node) for node in path.nodes] == expected: return
    except Exception:
        pass
    for index in range(len(path.nodes)-1, -1, -1):
        del path.nodes[index]
    for node in nodes:
        path.nodes.append(node)
    if [_identity(node) for node in path.nodes] != expected:
        raise WorkerError("Glyphs did not retain exact path nodes")


def _set_shapes(layer, shapes):
    shapes = list(shapes)
    expected = [_identity(shape) for shape in shapes]
    try:
        layer.shapes = shapes
        if [_identity(shape) for shape in layer.shapes] == expected: return
    except Exception:
        pass
    for index in range(len(layer.shapes)-1, -1, -1):
        del layer.shapes[index]
    for shape in shapes:
        layer.shapes.append(shape)
    if [_identity(shape) for shape in layer.shapes] != expected:
        raise WorkerError("Glyphs did not retain exact shape order")


def _hinted(layer, nodes):
    identities = {_identity(node) for node in nodes}
    return any(_value(hint, field, None) is not None and _identity(_value(hint, field, None)) in identities
               for hint in list(_value(layer, "hints", []) or [])
               for field in ("originNode", "targetNode", "otherNode1", "otherNode2"))


def _hinted_identities(layer):
    return {_identity(node)
            for hint in list(_value(layer, "hints", []) or [])
            for field in ("originNode", "targetNode", "otherNode1", "otherNode2")
            for node in [_value(hint, field, None)] if node is not None}


def _remove_node_native(layer, path, operation):
    nodes = list(path.nodes)
    index = operation["node"]
    if index >= len(nodes):
        raise WorkerError("remove_node index is unavailable")
    target = nodes[index]
    if str(_value(target, "type", "") or "").lower() == "offcurve":
        raise WorkerError("remove_node requires an existing on-curve node")
    method = getattr(path, "removeNodeCheckKeepShape_", None)
    if not callable(method):
        raise WorkerError("Glyphs does not support native shape-preserving node removal")

    before_ids = [_identity(node) for node in nodes]
    before_states = [_node(node) for node in nodes]
    hinted = _hinted_identities(layer)
    if not bool(method(target)):
        raise WorkerError("Glyphs rejected shape-preserving node removal")

    after_nodes = list(path.nodes)
    after_by_id = {_identity(node): node for node in after_nodes}
    if len(after_by_id) != len(after_nodes):
        raise WorkerError("Glyphs returned duplicate node identities after removal")
    added = [node for node in after_nodes if _identity(node) not in set(before_ids)]
    removed = [position for position, identity in enumerate(before_ids) if identity not in after_by_id]
    if added or not removed or before_ids[index] in after_by_id:
        raise WorkerError("Glyphs did not perform the requested shape-preserving removal")
    removed_nodes = [nodes[position] for position in removed]
    if hinted.intersection(_identity(node) for node in removed_nodes):
        raise WorkerError("node removal is blocked by a native hint reference")

    adjusted = []
    for position, identity in enumerate(before_ids):
        survivor = after_by_id.get(identity)
        if survivor is None:
            continue
        after_state = _node(survivor)
        if after_state != before_states[position]:
            adjusted.append({"index": position, "before": before_states[position], "after": after_state})
    resolved = {**operation, "removedNodes": removed}
    diagnostic = {"path": operation["path"], "requestedNode": index,
                  "removedNodes": removed, "adjustedNodes": adjusted}
    return resolved, diagnostic


def _validate(path):
    state = _path_state(path)
    nodes = state["nodes"]
    if len(nodes) < 2 or sum(node["type"] != "offcurve" for node in nodes) < 2:
        raise WorkerError("resulting path is structurally invalid")
    if not state["closed"] and (nodes[0]["type"] == "offcurve" or nodes[-1]["type"] == "offcurve"):
        raise WorkerError("open paths must begin and end on-curve")
    oncurves = [i for i, node in enumerate(nodes) if node["type"] != "offcurve"]
    for end in (oncurves if state["closed"] else oncurves[1:]):
        _segment(state, end)


def _start(path, index):
    nodes = list(path.nodes)
    if index >= len(nodes) or str(nodes[index].type).lower() == "offcurve":
        raise WorkerError("start node must be an existing on-curve node")
    target, method = nodes[index], getattr(nodes[index], "makeNodeFirst", None)
    method() if callable(method) else path.makeNodeFirst_(nodes[(index-1) % len(nodes)])


def _new_path(operation):
    from GlyphsApp import GSNode, GSPath  # type: ignore[import-not-found]
    path = GSPath(); path.closed = operation["closed"]
    nodes = []
    for item in operation["nodes"]:
        node = GSNode(); node.position = (item["x"], item["y"]); node.type = item["type"]
        node.smooth = item.get("smooth", False)
        if "name" in item: node.name = "" if item["name"] is None else item["name"]
        nodes.append(node)
    _set_nodes(path, nodes); _validate(path)
    return path


def _insert_path(layer, index, path):
    paths, shapes = _paths(layer), list(_value(layer, "shapes", []) or [])
    if index > len(paths): raise WorkerError("path insertion index is unavailable")
    if not shapes: layer.paths.insert(index, path); return
    position = shapes.index(paths[index]) if index < len(paths) else shapes.index(paths[-1])+1 if paths else len(shapes)
    shapes.insert(position, path); _set_shapes(layer, shapes)


def _apply(layer, operation):
    op, index = operation["op"], operation["path"]
    if op == "add_path":
        _insert_path(layer, index, _new_path(operation)); return operation, [], None
    path = _path(layer, index)
    inserted = []
    if op == "split_segment":
        state = _path_state(path); kind, start, points = _segment(state, operation["endNode"])
        if start != operation["startNode"]: raise WorkerError("split startNode does not identify the requested segment")
        times = _path_times(kind, points, operation["fractions"], operation["measure"])
        records, upper = {}, 1.0
        for parameter in sorted(times, reverse=True):
            path.insertNodeWithPathTime_(operation["endNode"] + parameter/upper)
            records[parameter] = list(path.nodes)[operation["endNode"]]; upper = parameter
        inserted = [_node(records[time]) for time in times]
        operation = {**operation, "pathTimes": times, "inserted": inserted}
    elif op == "update_nodes":
        nodes = list(path.nodes)
        for update in operation["updates"]:
            if update["index"] >= len(nodes): raise WorkerError("node update index is unavailable")
            node = nodes[update["index"]]
            if "position" in update: node.position = (update["position"]["x"], update["position"]["y"])
            if "delta" in update:
                x, y = _point(node); node.position = (x+update["delta"]["dx"], y+update["delta"]["dy"])
            for key in ("type", "smooth"):
                if key in update: setattr(node, key, update[key])
            if "name" in update: node.name = "" if update["name"] is None else update["name"]
    elif op == "delete_nodes":
        nodes = list(path.nodes)
        if any(item >= len(nodes) for item in operation["nodes"]): raise WorkerError("node deletion index is unavailable")
        removed = [nodes[item] for item in operation["nodes"]]
        if _hinted(layer, removed): raise WorkerError("node deletion is blocked by a native hint reference")
        deleted = set(operation["nodes"]); _set_nodes(path, [node for i, node in enumerate(nodes) if i not in deleted])
    elif op == "remove_node":
        operation, removal = _remove_node_native(layer, path, operation)
    elif op == "reverse_path": path.reverse()
    elif op == "set_start_node":
        if not path.closed: raise WorkerError("only closed paths have a start node")
        _start(path, operation["node"])
    elif op == "set_closed":
        if operation["closed"]: path.closed = True
        else:
            if not path.closed: raise WorkerError("path is already open")
            _start(path, operation["startNode"]); nodes = list(path.nodes)
            while nodes and str(nodes[-1].type).lower() == "offcurve":
                if _hinted(layer, [nodes[-1]]): raise WorkerError("opening path is blocked by a native hint reference")
                nodes.pop()
            _set_nodes(path, nodes); path.closed = False
    elif op == "delete_path":
        if _hinted(layer, list(path.nodes)): raise WorkerError("path deletion is blocked by a native hint reference")
        shapes = list(_value(layer, "shapes", []) or [])
        if shapes: shapes.remove(path); _set_shapes(layer, shapes)
        else: layer.paths.remove(path)
        return operation, inserted, None
    else: raise WorkerError("unsupported outline operation")
    _validate(path)
    return operation, inserted, removal if op == "remove_node" else None


def _glyph(font, name):
    try: glyph = font.glyphs[name]
    except Exception: glyph = None
    if glyph is None: raise WorkerError(f"glyph {name!r} is unavailable")
    return glyph


def _layer(glyph, identity):
    try: layer = glyph.layers[identity]
    except Exception: layer = None
    if layer is None or str(_value(layer, "layerId", "")) != identity:
        raise WorkerError(f"layer {identity!r} is unavailable")
    return layer


def _copy(layer):
    clone = layer.copy()
    if clone is None: raise WorkerError("Glyphs could not copy an outline layer")
    return clone


def _compare(layer):
    result = _value(layer, "compareString", None)
    if not isinstance(result, str):
        raise WorkerError("native master compatibility evidence is unavailable")
    return result


def _ordinary(font, glyph):
    result = []
    for master in list(font.masters or []):
        identity = str(master.id or "")
        result.append((identity, _layer(glyph, identity)))
    return result


def prepare(font, request):
    options = validate_options(request.get("options"))
    changes, rows, expanded, edits, glyph_states = [], [], 0, {}, {}
    for target in options["targets"]:
        glyph = _glyph(font, target["glyph"])
        if target["glyph"] not in glyph_states:
            ordinary = _ordinary(font, glyph)
            glyph_states[target["glyph"]] = {"ordinary": ordinary,
                "simulations": {identity: layer for identity, layer in ordinary}}
        state = glyph_states[target["glyph"]]; ordinary = state["ordinary"]
        reference = _layer(glyph, target["referenceLayer"])
        reference_paths = _paths(reference)
        for guard in target["guards"]:
            if guard["path"] >= len(reference_paths) or path_hash(_path_state(reference_paths[guard["path"]])) != guard["hash"]:
                raise WorkerError("reference path guard is stale")
        if target["layers"]["scope"] == "all_masters":
            selected = ordinary
        else:
            selected = [(identity, _layer(glyph, identity)) for identity in target["layers"]["ids"]]
        if not selected:
            raise WorkerError("outline target selected no writable layers")
        expanded += len(selected)
        if expanded > 4096: raise WorkerError("outline job expands beyond 4,096 layer changes")
        for identity, layer in selected:
            key = (target["glyph"], identity)
            if key not in edits:
                clone = _copy(layer)
                edits[key] = {"layer": layer, "clone": clone,
                    "beforeHash": outline_state_hash(_shape_state(layer)),
                    "beforeNodes": sum(len(path.nodes) for path in _paths(layer)),
                    "operations": [], "inserted": [], "removals": [], "rawDeletions": 0}
                if identity in state["simulations"]:
                    state["simulations"][identity] = clone
            edit = edits[key]; clone = edit["clone"]
            for operation in target["operations"]:
                item, additions, removal = _apply(clone, dict(operation))
                edit["operations"].append(item); edit["inserted"].extend(additions)
                if removal is not None:
                    edit["removals"].append(removal)
                if operation["op"] == "delete_nodes":
                    edit["rawDeletions"] += 1
    if not edits:
        raise WorkerError("outline job selected no writable layers")
    for (glyph_name, identity), edit in edits.items():
        after_hash = outline_state_hash(_shape_state(edit["clone"]))
        after_nodes = sum(len(path.nodes) for path in _paths(edit["clone"]))
        if edit["beforeHash"] == after_hash: raise WorkerError("outline operations have no effect")
        changes.append({"kind": "outline", "glyph": glyph_name, "layer": identity,
                        "beforeHash": edit["beforeHash"], "afterHash": after_hash,
                        "operations": edit["operations"]})
        rows.append({"glyph": glyph_name, "layer": identity, "status": "ready",
                     "rawNodeDelta": after_nodes-edit["beforeNodes"], "insertedNodes": edit["inserted"],
                     "nativeRemovals": edit["removals"], "rawDeletionCount": edit["rawDeletions"],
                     "beforeHash": edit["beforeHash"], "afterHash": after_hash})
    incompatible = []
    for glyph_name, state in glyph_states.items():
        before = {identity: _compare(layer) for identity, layer in state["ordinary"]}
        after = {identity: _compare(state["simulations"][identity])
                 for identity, _ in state["ordinary"]}
        ids = list(before)
        for left_pos, left in enumerate(ids):
            for right in ids[left_pos+1:]:
                if (before[left] == before[right]) != (after[left] == after[right]):
                    incompatible.append({"glyph": glyph_name, "layers": [left, right]})
    if incompatible and options["compatibilityPolicy"] == "preserve":
        raise WorkerError("outline edit would change ordinary-master compatibility")
    warnings = []
    if any(edit["rawDeletions"] for edit in edits.values()):
        warnings.append("delete_nodes performs raw topology deletion and may change contour geometry; use remove_node for Glyphs-native shape-preserving removal.")
    if incompatible:
        warnings.append("Explicitly allowed incompatible master topology.")
    report = {"claim": "Prepared typed outline edits on detached native copies; native removals use Glyphs keep-shape behavior; no font was saved.",
              "policy": options["compatibilityPolicy"], "layers": rows,
              "compatibilityChanges": incompatible,
              "warnings": warnings,
              "warning": ("Explicitly allowed incompatible master topology."
                          if incompatible else warnings[0] if warnings else None)}
    return changes, report
