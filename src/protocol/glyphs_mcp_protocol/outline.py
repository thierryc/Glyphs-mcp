"""Closed contracts and deterministic fingerprints for bounded outline editing."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Mapping

from .models import ProtocolError, canonical_json

NODE_TYPES = frozenset(("line", "curve", "qcurve", "offcurve"))
MAX_NODES = 4096
MAX_OPERATIONS = 256
MAX_LAYER_CHANGES = 4096


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolError("invalid_request", label + " must be an object")
    return value


def _closed(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    extra = sorted(set(value) - fields)
    if extra:
        raise ProtocolError("invalid_request", f"{label} has unexpected fields: {', '.join(extra)}")


def _text(value: Any, label: str, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ProtocolError("invalid_request", f"{label} must be 1-{maximum} characters")
    return value


def _index(value: Any, label: str, maximum: int = MAX_NODES) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ProtocolError("invalid_request", f"{label} must be an integer from 0 to {maximum}")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ProtocolError("invalid_request", label + " must be a finite number")
    return float(value)


def _hash(value: Any, label: str) -> str:
    text = str(value or "")
    if (len(text) != 71 or not text.startswith("sha256:") or
            any(character not in "0123456789abcdef" for character in text[7:])):
        raise ProtocolError("invalid_request", label + " must be a SHA-256 fingerprint")
    return text


def _node(value: Any, label: str) -> dict[str, Any]:
    item = _object(value, label)
    allowed = {"x", "y", "type", "smooth", "name"}
    _closed(item, allowed, label)
    if not {"x", "y", "type"} <= set(item):
        raise ProtocolError("invalid_request", label + " requires x, y and type")
    kind = str(item["type"])
    if kind not in NODE_TYPES:
        raise ProtocolError("invalid_request", label + " has an unsupported node type")
    result: dict[str, Any] = {"x": _number(item["x"], label + " x"),
                              "y": _number(item["y"], label + " y"), "type": kind}
    if "smooth" in item:
        if type(item["smooth"]) is not bool:
            raise ProtocolError("invalid_request", label + " smooth must be boolean")
        result["smooth"] = item["smooth"]
    if "name" in item:
        if item["name"] is not None and (not isinstance(item["name"], str) or len(item["name"]) > 255):
            raise ProtocolError("invalid_request", label + " name must be null or at most 255 characters")
        result["name"] = item["name"]
    return result


def _nodes(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 2 <= len(value) <= MAX_NODES:
        raise ProtocolError("invalid_request", f"{label} must contain 2-{MAX_NODES} nodes")
    return [_node(item, f"{label} {index}") for index, item in enumerate(value)]


def validate_operation(value: Any, *, resolved: bool = False) -> dict[str, Any]:
    item = _object(value, "outline operation")
    op = item.get("op")
    common = {"op", "path"}
    if op == "split_segment":
        allowed = common | {"startNode", "endNode", "fractions", "measure"}
        if resolved:
            allowed |= {"pathTimes", "inserted"}
        _closed(item, allowed, "split_segment")
        required = common | {"startNode", "endNode", "fractions"}
        if not required <= set(item):
            raise ProtocolError("invalid_request", "split_segment fields are incomplete")
        fractions = item["fractions"]
        if not isinstance(fractions, list) or not 1 <= len(fractions) <= 32:
            raise ProtocolError("invalid_request", "split fractions must contain 1-32 values")
        normalized = [_number(v, "split fraction") for v in fractions]
        if any(not 0 < v < 1 for v in normalized) or len(set(normalized)) != len(normalized):
            raise ProtocolError("invalid_request", "split fractions must be unique values between 0 and 1")
        measure = item.get("measure", "arc_length")
        if measure not in ("arc_length", "path_time"):
            raise ProtocolError("invalid_request", "split measure must be arc_length or path_time")
        result = {"op": op, "path": _index(item["path"], "split path"),
                  "startNode": _index(item["startNode"], "split startNode"),
                  "endNode": _index(item["endNode"], "split endNode"),
                  "fractions": normalized, "measure": measure}
        if resolved:
            times = item.get("pathTimes")
            inserted = item.get("inserted")
            if not isinstance(times, list) or len(times) != len(normalized):
                raise ProtocolError("invalid_request", "resolved split pathTimes do not match fractions")
            result["pathTimes"] = [_number(v, "split pathTime") for v in times]
            if any(not 0 < v < 1 for v in result["pathTimes"]):
                raise ProtocolError("invalid_request", "split pathTimes must be between 0 and 1")
            if not isinstance(inserted, list) or len(inserted) != len(normalized):
                raise ProtocolError("invalid_request", "resolved split coordinates do not match fractions")
            result["inserted"] = [_node(v, "inserted node") for v in inserted]
            if any(node["type"] == "offcurve" for node in result["inserted"]):
                raise ProtocolError("invalid_request", "split inserted nodes must be on-curve")
        return result
    if op == "update_nodes":
        _closed(item, common | {"updates"}, op)
        updates = item.get("updates")
        if not isinstance(updates, list) or not 1 <= len(updates) <= MAX_NODES:
            raise ProtocolError("invalid_request", "updates must contain 1-4096 entries")
        seen, output = set(), []
        for raw in updates:
            update = _object(raw, "node update")
            _closed(update, {"index", "position", "delta", "type", "smooth", "name"}, "node update")
            index = _index(update.get("index"), "node update index")
            if index in seen:
                raise ProtocolError("invalid_request", "node update indices must be unique")
            seen.add(index)
            if not set(update) - {"index"} or ("position" in update and "delta" in update):
                raise ProtocolError("invalid_request", "node update needs properties and at most one position mode")
            normalized_update: dict[str, Any] = {"index": index}
            for key, names in (("position", ("x", "y")), ("delta", ("dx", "dy"))):
                if key in update:
                    point = _object(update[key], "node " + key)
                    if set(point) != set(names):
                        raise ProtocolError("invalid_request", "node " + key + " requires exact coordinates")
                    normalized_update[key] = {name: _number(point[name], "node " + name) for name in names}
            if "type" in update:
                if update["type"] not in NODE_TYPES:
                    raise ProtocolError("invalid_request", "unsupported node type")
                normalized_update["type"] = update["type"]
            if "smooth" in update:
                if type(update["smooth"]) is not bool:
                    raise ProtocolError("invalid_request", "node smooth must be boolean")
                normalized_update["smooth"] = update["smooth"]
            if "name" in update:
                if update["name"] is not None and (not isinstance(update["name"], str) or len(update["name"]) > 255):
                    raise ProtocolError("invalid_request", "node name must be null or at most 255 characters")
                normalized_update["name"] = update["name"]
            output.append(normalized_update)
        return {"op": op, "path": _index(item.get("path"), "update path"), "updates": output}
    if op == "delete_nodes":
        _closed(item, common | {"nodes"}, op)
        nodes = item.get("nodes")
        if not isinstance(nodes, list) or not nodes or len(nodes) > MAX_NODES:
            raise ProtocolError("invalid_request", "delete_nodes requires 1-4096 indices")
        normalized = [_index(v, "delete node index") for v in nodes]
        if len(set(normalized)) != len(normalized):
            raise ProtocolError("invalid_request", "delete node indices must be unique")
        return {"op": op, "path": _index(item.get("path"), "delete path"), "nodes": normalized}
    if op == "remove_node":
        allowed = common | {"node"}
        if resolved:
            allowed.add("removedNodes")
        _closed(item, allowed, op)
        if not (common | {"node"}) <= set(item):
            raise ProtocolError("invalid_request", "remove_node fields are incomplete")
        node = _index(item.get("node"), "remove node")
        result = {"op": op, "path": _index(item.get("path"), "remove path"), "node": node}
        if resolved:
            removed = item.get("removedNodes")
            if not isinstance(removed, list) or not removed or len(removed) > MAX_NODES:
                raise ProtocolError("invalid_request", "resolved remove_node requires 1-4096 removedNodes")
            normalized = [_index(value, "removed node index") for value in removed]
            if len(set(normalized)) != len(normalized) or normalized != sorted(normalized):
                raise ProtocolError("invalid_request", "removedNodes must be unique and ascending")
            if node not in normalized:
                raise ProtocolError("invalid_request", "removedNodes must include the requested node")
            result["removedNodes"] = normalized
        return result
    if op in ("reverse_path", "delete_path"):
        _closed(item, common, op)
        return {"op": op, "path": _index(item.get("path"), op + " path")}
    if op == "set_start_node":
        _closed(item, common | {"node"}, op)
        return {"op": op, "path": _index(item.get("path"), "start path"),
                "node": _index(item.get("node"), "start node")}
    if op == "set_closed":
        _closed(item, common | {"closed", "startNode"}, op)
        if type(item.get("closed")) is not bool:
            raise ProtocolError("invalid_request", "set_closed closed must be boolean")
        result = {"op": op, "path": _index(item.get("path"), "closed path"), "closed": item["closed"]}
        if not item["closed"]:
            result["startNode"] = _index(item.get("startNode"), "open startNode")
        elif "startNode" in item:
            raise ProtocolError("invalid_request", "closing a path does not accept startNode")
        return result
    if op == "add_path":
        _closed(item, common | {"closed", "nodes"}, op)
        if type(item.get("closed")) is not bool:
            raise ProtocolError("invalid_request", "add_path closed must be boolean")
        return {"op": op, "path": _index(item.get("path"), "path insertion index"),
                "closed": item["closed"], "nodes": _nodes(item.get("nodes"), "path nodes")}
    raise ProtocolError("invalid_request", "unsupported outline operation: " + str(op))


def validate_options(value: Any) -> dict[str, Any]:
    options = _object(value, "outline_edit options")
    _closed(options, {"compatibilityPolicy", "targets"}, "outline_edit options")
    policy = options.get("compatibilityPolicy", "preserve")
    if policy not in ("preserve", "allow_incompatible"):
        raise ProtocolError("invalid_request", "unsupported compatibilityPolicy")
    targets = options.get("targets")
    if not isinstance(targets, list) or not 1 <= len(targets) <= 100:
        raise ProtocolError("invalid_request", "outline_edit requires 1-100 targets")
    total, normalized_targets = 0, []
    for target_number, raw in enumerate(targets):
        target = _object(raw, f"target {target_number}")
        _closed(target, {"glyph", "layers", "referenceLayer", "guards", "operations"}, "outline target")
        if set(target) != {"glyph", "layers", "referenceLayer", "guards", "operations"}:
            raise ProtocolError("invalid_request", "outline target fields are incomplete")
        layers = _object(target["layers"], "layer scope")
        _closed(layers, {"scope", "ids"}, "layer scope")
        scope = layers.get("scope")
        if scope == "all_masters":
            if set(layers) != {"scope"}:
                raise ProtocolError("invalid_request", "all_masters does not accept layer IDs")
            normalized_layers = {"scope": scope}
        elif scope == "ids":
            ids = layers.get("ids")
            if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_LAYER_CHANGES:
                raise ProtocolError("invalid_request", "explicit layer scope requires 1-4096 IDs")
            normalized_ids = [_text(v, "layer ID") for v in ids]
            if len(set(normalized_ids)) != len(normalized_ids):
                raise ProtocolError("invalid_request", "layer IDs must be unique")
            normalized_layers = {"scope": scope, "ids": normalized_ids}
        else:
            raise ProtocolError("invalid_request", "layer scope must be all_masters or ids")
        guards = target["guards"]
        if not isinstance(guards, list) or len(guards) > MAX_NODES:
            raise ProtocolError("invalid_request", "guards must be a bounded list")
        seen, normalized_guards = set(), []
        for guard in guards:
            guard = _object(guard, "path guard")
            if set(guard) != {"path", "hash"}:
                raise ProtocolError("invalid_request", "path guards require exact path and hash fields")
            path = _index(guard["path"], "guard path")
            if path in seen:
                raise ProtocolError("invalid_request", "path guards must be unique")
            seen.add(path)
            normalized_guards.append({"path": path, "hash": _hash(guard["hash"], "guard hash")})
        operations = target["operations"]
        if not isinstance(operations, list) or not operations or total + len(operations) > MAX_OPERATIONS:
            raise ProtocolError("invalid_request", "outline job must contain 1-256 operations")
        total += len(operations)
        normalized_targets.append({"glyph": _text(target["glyph"], "glyph"),
                                   "layers": normalized_layers,
                                   "referenceLayer": _text(target["referenceLayer"], "referenceLayer"),
                                   "guards": normalized_guards,
                                   "operations": [validate_operation(op) for op in operations]})
    return {"compatibilityPolicy": policy, "targets": normalized_targets}


def validate_change(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"kind", "glyph", "layer", "beforeHash", "afterHash", "operations"}
    _closed(value, fields, "outline change")
    if set(value) != fields:
        raise ProtocolError("invalid_request", "outline change fields are incomplete")
    operations = value["operations"]
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise ProtocolError("invalid_request", "outline change requires 1-256 operations")
    return {"kind": "outline", "glyph": _text(value["glyph"], "outline glyph"),
            "layer": _text(value["layer"], "outline layer"),
            "beforeHash": _hash(value["beforeHash"], "outline beforeHash"),
            "afterHash": _hash(value["afterHash"], "outline afterHash"),
            "operations": [validate_operation(op, resolved=True) for op in operations]}


def _float(value: Any) -> str:
    return float(value).hex()


def node_state(node: Any) -> list[Any]:
    return [_float(node["x"]), _float(node["y"]), str(node["type"]),
            bool(node.get("smooth", False)), node.get("name") or None]


def path_hash(path: Mapping[str, Any]) -> str:
    state = [bool(path["closed"]), bool(path.get("locked", False)),
             [node_state(node) for node in path["nodes"]]]
    return "sha256:" + hashlib.sha256(canonical_json(state).encode()).hexdigest()


def outline_state_hash(shapes: list[Mapping[str, Any]]) -> str:
    state = []
    for shape in shapes:
        if shape["kind"] == "path":
            state.append(["path", bool(shape["closed"]), bool(shape.get("locked", False)),
                          [node_state(node) for node in shape["nodes"]]])
        else:
            state.append(["component", shape.get("name"), shape.get("transform")])
    return "sha256:" + hashlib.sha256(canonical_json(state).encode()).hexdigest()
