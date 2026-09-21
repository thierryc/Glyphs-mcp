"""Prepare closed native Glyphs actions against a disposable saved source."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from glyphs_mcp_protocol.native_actions import (
    ACTION_SPECS,
    MAX_JOB_STATE_BYTES,
    MAX_LAYER_CHANGES,
    MAX_TARGET_STATE_BYTES,
    state_hash,
    native_call_arguments,
    validate_options,
)

from .worker import WorkerError


GLYPH_METADATA_FIELDS = (
    "name", "unicode", "unicodes", "locked", "category", "subCategory", "script", "case",
    "direction", "productionName", "sortName", "sortNameKeep", "export", "color",
    "note", "leftMetricsKey", "rightMetricsKey", "widthMetricsKey",
    "topMetricsKey", "bottomMetricsKey", "tags", "group", "groupIdx", "storeGroup",
    "leftKerningGroup", "rightKerningGroup", "topKerningGroup", "bottomKerningGroup",
    "storeCategory", "storeSubCategory", "storeScript", "storeCase", "storeDirection",
    "storeProductionName", "storeSortName",
)
FONT_FEATURE_FIELDS = ("featurePrefixes", "classes", "features")


def _value(owner: Any, name: str, default=None):
    try:
        value = getattr(owner, name)
        return value() if callable(value) else value
    except Exception:
        return default


def _plain(value: Any, depth: int = 0) -> Any:
    if depth > 128:
        raise WorkerError("native action state exceeds the nesting limit")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise WorkerError("native action state contains a non-finite number")
        return value
    if isinstance(value, bytes):
        return {"$bytes": value.hex()}
    if isinstance(value, Mapping) or hasattr(value, "items"):
        try:
            items = value.items()
        except Exception as exc:
            raise WorkerError("native action state contains an unreadable mapping") from exc
        return {str(key): _plain(item, depth + 1) for key, item in sorted(items, key=lambda row: str(row[0]))}
    if isinstance(value, (list, tuple)) or hasattr(value, "objectAtIndex_"):
        try:
            return [_plain(item, depth + 1) for item in list(value)]
        except Exception as exc:
            raise WorkerError("native action state contains an unreadable collection") from exc
    if hasattr(value, "x") and hasattr(value, "y"):
        return {"$point": [float(value.x), float(value.y)]}
    if hasattr(value, "origin") and hasattr(value, "size"):
        return {"$rect": [_plain(value.origin, depth + 1), _plain(value.size, depth + 1)]}
    if hasattr(value, "width") and hasattr(value, "height"):
        return {"$size": [float(value.width), float(value.height)]}
    description = str(value)
    if "0x" in description and type(value).__module__ != "builtins":
        raise WorkerError("native action state contains a non-serializable native object")
    return description


def _property_list(owner: Any) -> Any:
    for name in ("propertyListValueFormat_error_", "propertyListValueFormat_", "propertyListValueFormat"):
        method = getattr(owner, name, None)
        if not callable(method):
            continue
        try:
            value = method(3, None) if name.endswith("_error_") else method(3)
        except TypeError:
            continue
        if isinstance(value, tuple):
            result, error = value[0], value[1] if len(value) > 1 else None
            if error is not None:
                raise WorkerError(f"Glyphs could not encode native action state: {error}")
            value = result
        if value is not None:
            return _plain(value)
    raise WorkerError("Glyphs does not expose a bounded persisted-state projection")


def persistent_state(owner: Any, scope: str) -> Any:
    if scope == "layer":
        return {"layer": _property_list(owner)}
    if scope == "glyph":
        property_list = _property_list(owner)
        if not isinstance(property_list, dict):
            raise WorkerError("Glyphs did not expose glyph metadata as a property list")
        return {
            "propertyList": {key: value for key, value in property_list.items()
                             if str(key).lower() not in {"layers", "layersv2"}},
            "metadata": {name: _plain(_value(owner, name, None)) for name in GLYPH_METADATA_FIELDS},
        }
    if scope == "font":
        result = {}
        for name in FONT_FEATURE_FIELDS:
            result[name] = [_property_list(item) for item in list(_value(owner, name, []) or [])]
        return result
    if scope == "feature_block":
        return {"featureBlock": _property_list(owner)}
    raise WorkerError("unsupported native action scope")


def encoded_size(state: Any) -> int:
    return len(json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _method(owner: Any, action: str):
    for selector in ACTION_SPECS[action]["selectors"]:
        method = getattr(owner, selector, None)
        if callable(method):
            return method
    raise WorkerError(f"Glyphs does not support native action {action}")


def invoke(owner: Any, action: str, arguments: Mapping[str, Any]) -> None:
    method = _method(owner, action)
    result = method(*native_call_arguments(action, arguments))
    if isinstance(result, tuple) and len(result) > 1 and result[1] is not None:
        raise WorkerError(f"Glyphs rejected native action {action}: {result[1]}")


def _named(collection: Any, name: str, field: str):
    try:
        item = collection[name]
    except Exception:
        item = None
    if item is not None and str(_value(item, field, "") or "") == name:
        return item
    for candidate in list(collection or []):
        if str(_value(candidate, field, "") or "") == name:
            return candidate
    return None


def _glyph(font: Any, name: str):
    glyph = _named(font.glyphs, name, "name")
    if glyph is None:
        raise WorkerError(f"glyph {name!r} is unavailable in the saved source")
    return glyph


def _layer(glyph: Any, identity: str):
    layer = _named(glyph.layers, identity, "layerId")
    if layer is None:
        raise WorkerError(f"layer {identity!r} in glyph {glyph.name!r} is unavailable")
    return layer


def _feature_block(font: Any, target: Mapping[str, Any]):
    collection_name = {"prefix": "featurePrefixes", "class": "classes", "feature": "features"}[target["blockType"]]
    for block in list(_value(font, collection_name, []) or []):
        identity = _value(block, "identifier", None) or _value(block, "id", None)
        if str(identity or "") == target["id"]:
            if _value(block, "automatic", None) not in (True, 1) or _value(block, "canBeAutomated", None) not in (True, 1):
                raise WorkerError("feature-block updates require an automatic, automatable target")
            return block
    raise WorkerError(f"feature block {target['id']!r} is unavailable in the saved source")


def _expand_layers(font: Any, targets: list[dict[str, Any]]) -> list[tuple[str, str, Any]]:
    masters = [str(_value(master, "id", "") or "") for master in list(font.masters or [])]
    result = []
    seen = set()
    for target in targets:
        glyph = _glyph(font, target["glyph"])
        scope = target["layers"]
        identities = masters if scope["scope"] == "all_masters" else scope["ids"]
        for identity in identities:
            key = (target["glyph"], identity)
            if key in seen:
                raise WorkerError("native action expands to a duplicate layer target")
            seen.add(key)
            result.append((target["glyph"], identity, _layer(glyph, identity)))
            if len(result) > MAX_LAYER_CHANGES:
                raise WorkerError("native action expands beyond 4,096 layers")
    return result


def _summary(owner: Any, scope: str) -> dict[str, Any]:
    if scope == "layer":
        values = {
            "width": _value(owner, "width", None),
            "paths": len(list(_value(owner, "paths", []) or [])),
            "components": len(list(_value(owner, "components", []) or [])),
            "anchors": len(list(_value(owner, "anchors", []) or [])),
        }
    elif scope == "glyph":
        values = {name: _plain(_value(owner, name, None)) for name in ACTION_SPECS["update_glyph_info"]["reportFields"]}
    elif scope == "feature_block":
        code = _value(owner, "code", "")
        values = {
            "name": _value(owner, "name", None),
            "codeLength": len(code) if isinstance(code, str) else 0,
            "automatic": _value(owner, "automatic", None),
            "disabled": _value(owner, "disabled", None),
        }
    else:
        values = {name: len(list(_value(owner, name, []) or [])) for name in FONT_FEATURE_FIELDS}
    return values


def prepare(font: Any, request: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    options = validate_options(request.get("options") or {})
    action, scope, arguments = options["action"], options["scope"], options["arguments"]
    if scope == "layer":
        owners = [(glyph, layer, owner, {}) for glyph, layer, owner in _expand_layers(font, options["targets"])]
    elif scope == "glyph":
        owners = [(target["glyph"], None, _glyph(font, target["glyph"]), {}) for target in options["targets"]]
    elif scope == "feature_block":
        owners = [(None, None, _feature_block(font, target), {
            "blockType": target["blockType"], "id": target["id"]
        }) for target in options["targets"]]
    else:
        owners = [(None, None, font, {})]

    changes, rows, total_bytes = [], [], 0
    for glyph_name, layer_id, owner, extra_target in owners:
        before = persistent_state(owner, scope)
        before_size = encoded_size(before)
        if before_size > MAX_TARGET_STATE_BYTES:
            raise WorkerError("native action target state exceeds 8 MiB")
        if total_bytes + before_size > MAX_JOB_STATE_BYTES:
            raise WorkerError("native action job state exceeds 64 MiB")
        before_summary = _summary(owner, scope)
        invoke(owner, action, arguments)
        after = persistent_state(owner, scope)
        after_size = encoded_size(after)
        after_summary = _summary(owner, scope)
        target_bytes = max(before_size, after_size)
        if after_size > MAX_TARGET_STATE_BYTES:
            raise WorkerError("native action target state exceeds 8 MiB")
        total_bytes += before_size + after_size
        if total_bytes > MAX_JOB_STATE_BYTES:
            raise WorkerError("native action job state exceeds 64 MiB")
        before_hash, after_hash = state_hash(before), state_hash(after)
        target = {"scope": scope}
        if glyph_name is not None:
            target["glyph"] = glyph_name
        if layer_id is not None:
            target["layer"] = layer_id
        target.update(extra_target)
        changed = before_hash != after_hash
        rows.append({
            "target": target,
            "status": "changed" if changed else "no_change",
            "before": before_summary,
            "after": after_summary,
            "stateBytes": target_bytes,
        })
        if changed:
            changes.append({
                "kind": "native_action", "action": action, "scope": scope,
                "arguments": copy.deepcopy(arguments),
                **({"glyph": glyph_name} if glyph_name is not None else {}),
                **({"layer": layer_id} if layer_id is not None else {}),
                **extra_target,
                "beforeHash": before_hash, "afterHash": after_hash,
            })
    return changes, {
        "claim": "Closed native Glyphs action prepared against the saved clean source; live application remains guarded and reversible.",
        "action": action,
        "scope": scope,
        "targets": rows,
        "targetCount": len(rows),
        "changedCount": len(changes),
        "noChangeCount": len(rows) - len(changes),
        "warnings": [],
    }
