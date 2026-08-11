# encoding: utf-8

"""Shared duck-typed snapshot, verification, and rollback for node positions."""

from __future__ import annotations

import math


POSITION_TOLERANCE = 1.0e-5


def _values(sequence):
    try:
        return list(sequence or [])
    except Exception:
        return []


def _point_values(value):
    try:
        return float(value.x), float(value.y)
    except Exception:
        try:
            return float(value[0]), float(value[1])
        except Exception:
            return 0.0, 0.0


def _position(node):
    return _point_values(getattr(node, "position", None))


def _positions_match(first, second):
    try:
        return (
            all(math.isfinite(float(value)) for value in first + second)
            and math.hypot(float(first[0]) - float(second[0]), float(first[1]) - float(second[1]))
            <= POSITION_TOLERANCE
        )
    except Exception:
        return False


def _raw_value(obj, selector_name, attribute_name):
    try:
        methods = getattr(obj, "pyobjc_instanceMethods", None)
        selector = getattr(methods, selector_name, None)
        if callable(selector):
            return int(selector())
    except Exception:
        pass
    try:
        value = getattr(obj, attribute_name, None)
        return int(value) if value is not None else None
    except Exception:
        return None


def _orientation(node):
    value = _raw_value(node, "orientation", "rawOrientation")
    if value is not None:
        return value
    try:
        value = getattr(node, "orientation", None)
        return int(value) if value is not None else None
    except Exception:
        return None


def _normalized_type(node):
    try:
        return str(getattr(node, "type", "") or "").strip().lower()
    except Exception:
        return ""


def _name_value(node):
    try:
        value = getattr(node, "name", None)
    except Exception:
        value = None
    return "" if value is None else str(value)


def _same_object(first, second):
    if first is second:
        return True
    try:
        if bool(first == second):
            return True
    except Exception:
        pass
    # Some host collections return a fresh Python façade for the same stable
    # native object. Test doubles commonly expose that backing object through
    # ``_node``/``__wrapped__``; real PyObjC façades normally compare equal.
    for attribute_name in ("_node", "__wrapped__"):
        try:
            first_backing = getattr(first, attribute_name)
            second_backing = getattr(second, attribute_name)
        except Exception:
            continue
        if first_backing is second_backing:
            return True
        try:
            if bool(first_backing == second_backing):
                return True
        except Exception:
            pass
    return False


def _same_object_sequence(current, expected):
    return len(current) == len(expected) and all(
        _same_object(first, second) for first, second in zip(current, expected)
    )


def _node_state(node, node_type_getter):
    try:
        name = getattr(node, "name", None)
        name = None if name is None else str(name)
    except Exception:
        name = None
    return {
        "node": node,
        "position": _position(node),
        "type": str(node_type_getter(node)),
        "rawType": _raw_value(node, "type", "rawType"),
        "rawConnection": _raw_value(node, "connection", "rawConnection"),
        "smooth": bool(getattr(node, "smooth", False)),
        "orientation": _orientation(node),
        "name": name,
    }


def _anchor_state(anchor):
    return {
        "anchor": anchor,
        "name": str(getattr(anchor, "name", "") or ""),
        "position": _point_values(getattr(anchor, "position", None)),
    }


def _anchors_preserved(layer, states):
    current = _values(getattr(layer, "anchors", None))
    expected = [state["anchor"] for state in states]
    if not _same_object_sequence(current, expected):
        return False
    for anchor, state in zip(current, states):
        if str(getattr(anchor, "name", "") or "") != state["name"]:
            return False
        if not _positions_match(_point_values(getattr(anchor, "position", None)), state["position"]):
            return False
    return True


def snapshot_layer(layer, paths, node_type_getter=None):
    getter = node_type_getter or _normalized_type
    path_states = []
    for path in list(paths or []):
        path_states.append(
            {
                "path": path,
                "closed": bool(getattr(path, "closed", True)),
                "locked": bool(getattr(path, "locked", False)),
                "nodes": [_node_state(node, getter) for node in _values(getattr(path, "nodes", None))],
            }
        )
    try:
        shapes = _values(getattr(layer, "shapes", None))
        has_shapes = hasattr(layer, "shapes")
    except Exception:
        shapes = []
        has_shapes = False
    return {
        "layer": layer,
        "paths": path_states,
        "pathObjects": [item["path"] for item in path_states],
        "hasShapes": has_shapes,
        "shapeObjects": shapes,
        "width": getattr(layer, "width", None),
        "anchors": [_anchor_state(anchor) for anchor in _values(getattr(layer, "anchors", None))],
        "nodeTypeGetter": getter,
    }


def validate_update_preconditions(snapshot, updates):
    for update in updates:
        path_index = int(update["pathIndex"])
        node_index = int(update["nodeIndex"])
        if path_index < 0 or path_index >= len(snapshot["paths"]):
            return "path_index {} out of range".format(path_index), "path_not_found"
        path_state = snapshot["paths"][path_index]
        if path_state["locked"]:
            return "Path {} is locked".format(path_index), "path_locked"
        if node_index < 0 or node_index >= len(path_state["nodes"]):
            return "node_index {} out of range for path {}".format(node_index, path_index), "node_not_found"
        node_state = path_state["nodes"][node_index]
        expected = update.get("expected")
        if expected is not None and not _positions_match(
            node_state["position"],
            (float(expected["x"]), float(expected["y"])),
        ):
            return (
                "Target path {} node {} no longer has the expected position".format(path_index, node_index),
                "stale_target",
            )
        expected_type = update.get("expectedType")
        if expected_type is not None and str(node_state["type"]) != str(expected_type):
            return (
                "Target path {} node {} no longer has the expected type".format(path_index, node_index),
                "stale_target",
            )
    return None, None


def _verify_node_protected(node, state, getter):
    return (
        str(getter(node)) == state["type"]
        and _raw_value(node, "type", "rawType") == state["rawType"]
        and _raw_value(node, "connection", "rawConnection") == state["rawConnection"]
        and bool(getattr(node, "smooth", False)) == state["smooth"]
        and _orientation(node) == state["orientation"]
        and _name_value(node) == ("" if state["name"] is None else state["name"])
    )


def verify_layer(snapshot, expected_positions):
    layer = snapshot["layer"]
    current_paths = []
    try:
        current_paths = _values(getattr(layer, "paths", None))
    except Exception:
        pass
    if not current_paths and snapshot["hasShapes"]:
        current_paths = [shape for shape in _values(getattr(layer, "shapes", None)) if hasattr(shape, "nodes")]
    if not _same_object_sequence(current_paths, snapshot["pathObjects"]):
        return "Path order, count, or identity changed"
    if snapshot["hasShapes"] and not _same_object_sequence(
        _values(getattr(layer, "shapes", None)), snapshot["shapeObjects"]
    ):
        return "Layer shape order, count, or identity changed"
    if getattr(layer, "width", None) != snapshot["width"]:
        return "Layer width changed"
    if not _anchors_preserved(layer, snapshot["anchors"]):
        return "Layer anchors changed"

    getter = snapshot["nodeTypeGetter"]
    for path_index, (path, path_state) in enumerate(zip(current_paths, snapshot["paths"])):
        if bool(getattr(path, "closed", True)) != path_state["closed"]:
            return "Path {} closure changed".format(path_index)
        if bool(getattr(path, "locked", False)) != path_state["locked"]:
            return "Path {} lock state changed".format(path_index)
        nodes = _values(getattr(path, "nodes", None))
        if len(nodes) != len(path_state["nodes"]):
            return "Path {} node count changed".format(path_index)
        if not _same_object_sequence(nodes, [state["node"] for state in path_state["nodes"]]):
            return "Path {} node order or identity changed".format(path_index)
        for node_index, (node, node_state) in enumerate(zip(nodes, path_state["nodes"])):
            if not _verify_node_protected(node, node_state, getter):
                return "Path {} node {} protected state changed".format(path_index, node_index)
            wanted = expected_positions.get((path_index, node_index), node_state["position"])
            if not _positions_match(_position(node), wanted):
                return "Path {} node {} read-back did not match the expected position".format(path_index, node_index)
    return None


def _set_raw_value(node, selector_name, attribute_name, value):
    if value is None:
        return True
    for method_name in ("set{}_".format(selector_name[:1].upper() + selector_name[1:]),):
        try:
            method = getattr(node, method_name, None)
            if callable(method):
                method(int(value))
                return True
        except Exception:
            pass
    for name in (attribute_name, selector_name):
        try:
            setattr(node, name, int(value))
            return True
        except Exception:
            pass
    return False


def _replace_sequence(owner, attribute_name, values):
    wanted = list(values)
    try:
        setattr(owner, attribute_name, wanted)
        return True
    except Exception:
        pass
    try:
        current = getattr(owner, attribute_name)
    except Exception:
        return False
    try:
        current[:] = wanted
        return True
    except Exception:
        pass
    try:
        current.removeAllObjects()
        current.addObjectsFromArray_(wanted)
        return True
    except Exception:
        return False


def restore_layer(snapshot):
    errors = []
    layer = snapshot["layer"]
    if snapshot["hasShapes"] and not _same_object_sequence(
        _values(getattr(layer, "shapes", None)), snapshot["shapeObjects"]
    ):
        if not _replace_sequence(layer, "shapes", snapshot["shapeObjects"]):
            errors.append({"message": "Layer shape-order rollback failed"})
    current_paths = _values(getattr(layer, "paths", None))
    if not _same_object_sequence(current_paths, snapshot["pathObjects"]):
        if not snapshot["hasShapes"] and not _replace_sequence(layer, "paths", snapshot["pathObjects"]):
            errors.append({"message": "Layer path-order rollback failed"})
    for path_index, path_state in enumerate(snapshot["paths"]):
        path = path_state["path"]
        expected_nodes = [state["node"] for state in path_state["nodes"]]
        if not _same_object_sequence(_values(getattr(path, "nodes", None)), expected_nodes):
            if not _replace_sequence(path, "nodes", expected_nodes):
                errors.append({"pathIndex": path_index, "message": "Node-order rollback failed"})
        try:
            if bool(getattr(path, "closed", True)) != path_state["closed"]:
                path.closed = path_state["closed"]
            if bool(getattr(path, "locked", False)) != path_state["locked"]:
                path.locked = path_state["locked"]
        except Exception as exc:
            errors.append({"pathIndex": path_index, "message": str(exc)})
        for node_index, node_state in enumerate(path_state["nodes"]):
            node = node_state["node"]
            try:
                node.position = tuple(node_state["position"])
                if _raw_value(node, "type", "rawType") != node_state["rawType"]:
                    _set_raw_value(node, "type", "rawType", node_state["rawType"])
                if _raw_value(node, "connection", "rawConnection") != node_state["rawConnection"]:
                    _set_raw_value(node, "connection", "rawConnection", node_state["rawConnection"])
                if bool(getattr(node, "smooth", False)) != node_state["smooth"]:
                    node.smooth = node_state["smooth"]
                if (
                    node_state["orientation"] is not None
                    and _orientation(node) != node_state["orientation"]
                ):
                    try:
                        node.orientation = node_state["orientation"]
                    except Exception:
                        _set_raw_value(node, "orientation", "rawOrientation", node_state["orientation"])
                expected_name = "" if node_state["name"] is None else node_state["name"]
                if _name_value(node) != expected_name:
                    # GSNode.name is a string property. Assigning Python None in
                    # Glyphs 4 creates the literal name "None".
                    node.name = expected_name
            except Exception as exc:
                errors.append({"pathIndex": path_index, "nodeIndex": node_index, "message": str(exc)})
    current_anchors = _values(getattr(layer, "anchors", None))
    expected_anchors = [state["anchor"] for state in snapshot["anchors"]]
    if not _same_object_sequence(current_anchors, expected_anchors):
        if not _replace_sequence(layer, "anchors", expected_anchors):
            errors.append({"message": "Layer anchor-order rollback failed"})
    for anchor_index, state in enumerate(snapshot["anchors"]):
        try:
            anchor = state["anchor"]
            if str(getattr(anchor, "name", "") or "") != state["name"]:
                anchor.name = state["name"]
            if not _positions_match(_point_values(getattr(anchor, "position", None)), state["position"]):
                anchor.position = tuple(state["position"])
        except Exception as exc:
            errors.append({"anchorIndex": anchor_index, "message": str(exc)})
    try:
        if snapshot["width"] is not None and getattr(layer, "width", None) != snapshot["width"]:
            layer.width = snapshot["width"]
    except Exception as exc:
        errors.append({"message": "Width rollback failed: {}".format(exc)})
    verification_error = verify_layer(snapshot, {})
    if verification_error:
        errors.append({"message": verification_error})
    return errors


def _failure(error, error_code, *, began=False, ended=False, rollback=None):
    return {
        "ok": False,
        "error": str(error),
        "errorCode": str(error_code),
        "changed": [],
        "verification": {"succeeded": False, "changedNodeCount": 0},
        "rollback": rollback or {"attempted": False, "succeeded": True, "errors": []},
        "changeBatch": {"available": True, "began": bool(began), "ended": bool(ended)},
    }


def apply_position_updates(layer, paths, updates, node_type_getter=None):
    """Apply all proposed positions or restore the complete captured node state."""

    begin_changes = getattr(layer, "beginChanges", None)
    end_changes = getattr(layer, "endChanges", None)
    if not callable(begin_changes) or not callable(end_changes):
        result = _failure(
            "Confirmed mutation requires callable layer.beginChanges() and layer.endChanges().",
            "change_batch_unavailable",
        )
        result["changeBatch"]["available"] = False
        return result

    snapshot = snapshot_layer(layer, paths, node_type_getter=node_type_getter)
    precondition_error, precondition_code = validate_update_preconditions(snapshot, updates)
    if precondition_error:
        return _failure(precondition_error, precondition_code)

    expected_positions = {
        (int(update["pathIndex"]), int(update["nodeIndex"])): (
            float(update["proposed"]["x"]),
            float(update["proposed"]["y"]),
        )
        for update in updates
    }
    began = False
    ended = False
    mutation_error = None
    verification_error = None
    end_error = None
    rollback_attempted = False
    rollback_errors = []

    try:
        begin_changes()
        began = True
    except Exception as exc:
        return _failure("layer.beginChanges() failed: {}".format(exc), "begin_changes_failed")

    try:
        try:
            for update in sorted(updates, key=lambda item: (int(item["pathIndex"]), int(item["nodeIndex"]))):
                node = snapshot["paths"][int(update["pathIndex"])]["nodes"][int(update["nodeIndex"])]["node"]
                point = update["proposed"]
                node.position = (float(point["x"]), float(point["y"]))
            verification_error = verify_layer(snapshot, expected_positions)
        except Exception as exc:
            mutation_error = str(exc)
        if mutation_error or verification_error:
            rollback_attempted = True
            rollback_errors = restore_layer(snapshot)
    finally:
        try:
            end_changes()
            ended = True
        except Exception as exc:
            end_error = str(exc)

    if not mutation_error and not verification_error and not end_error:
        verification_error = verify_layer(snapshot, expected_positions)
    if (verification_error or end_error) and not rollback_attempted:
        rollback_attempted = True
        rollback_errors = restore_layer(snapshot)
    if rollback_attempted:
        retry_error = verify_layer(snapshot, {})
        if retry_error:
            rollback_errors.extend(restore_layer(snapshot))

    failure = mutation_error or verification_error or end_error
    if failure:
        if mutation_error:
            code = "mutation_failed"
            message = mutation_error
        elif end_error:
            code = "end_changes_failed"
            message = "layer.endChanges() failed: {}".format(end_error)
        else:
            code = "verification_failed"
            message = verification_error
        return _failure(
            message,
            code,
            began=began,
            ended=ended,
            rollback={
                "attempted": bool(rollback_attempted),
                "succeeded": bool(rollback_attempted) and not rollback_errors,
                "errors": rollback_errors,
            },
        )

    changed = []
    for update in updates:
        path_index = int(update["pathIndex"])
        node_index = int(update["nodeIndex"])
        before = snapshot["paths"][path_index]["nodes"][node_index]["position"]
        after = _position(snapshot["paths"][path_index]["nodes"][node_index]["node"])
        if not _positions_match(before, after):
            changed.append(
                {
                    "pathIndex": path_index,
                    "nodeIndex": node_index,
                    "before": {"x": before[0], "y": before[1]},
                    "after": {"x": after[0], "y": after[1]},
                }
            )
    return {
        "ok": True,
        "changed": changed,
        "verification": {
            "succeeded": True,
            "changedNodeCount": len(changed),
            "protectedStatePreserved": True,
            "untargetedNodesPreserved": True,
        },
        "rollback": {"attempted": False, "succeeded": True, "errors": []},
        "changeBatch": {"available": True, "began": began, "ended": ended},
    }


__all__ = [
    "POSITION_TOLERANCE",
    "apply_position_updates",
    "restore_layer",
    "snapshot_layer",
    "validate_update_preconditions",
    "verify_layer",
]
