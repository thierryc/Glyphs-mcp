"""Closed native action dispatch, persisted-state guards, and exact snapshots."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from glyphs_mcp_protocol.native_actions import (
    ACTION_SPECS,
    GLYPH_ACTIONS,
    LAYER_ACTIONS,
    MAX_TARGET_STATE_BYTES,
    NATIVE_ACTIONS,
    native_call_arguments,
    state_hash,
)


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
FEATURE_BLOCK_COLLECTIONS = {"prefix": "featurePrefixes", "class": "classes", "feature": "features"}
LAYER_SCALAR_FIELDS = (
    "name", "width", "vertWidth", "vertOrigin", "leftMetricsKey", "rightMetricsKey",
    "widthMetricsKey", "topMetricsKey", "bottomMetricsKey", "color",
)
LAYER_COLLECTION_FIELDS = ("shapes", "anchors", "hints", "guides", "annotations")


def _value(owner: Any, name: str, default=None):
    try:
        value = getattr(owner, name)
        return value() if callable(value) else value
    except Exception:
        return default


def _plain(value: Any, depth: int = 0) -> Any:
    if depth > 128:
        raise ValueError("native action state exceeds the nesting limit")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("native action state contains a non-finite number")
        return value
    if isinstance(value, bytes):
        return {"$bytes": value.hex()}
    if isinstance(value, Mapping) or hasattr(value, "items"):
        items = value.items()
        return {str(key): _plain(item, depth + 1) for key, item in sorted(items, key=lambda row: str(row[0]))}
    if isinstance(value, (list, tuple)) or hasattr(value, "objectAtIndex_"):
        return [_plain(item, depth + 1) for item in list(value)]
    if hasattr(value, "x") and hasattr(value, "y"):
        return {"$point": [float(value.x), float(value.y)]}
    if hasattr(value, "origin") and hasattr(value, "size"):
        return {"$rect": [_plain(value.origin, depth + 1), _plain(value.size, depth + 1)]}
    if hasattr(value, "width") and hasattr(value, "height"):
        return {"$size": [float(value.width), float(value.height)]}
    description = str(value)
    if "0x" in description and type(value).__module__ != "builtins":
        raise ValueError("native action state contains a non-serializable native object")
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
                raise ValueError(f"Glyphs could not encode native action state: {error}")
            value = result
        if value is not None:
            return _plain(value)
    raise ValueError("Glyphs does not expose a bounded persisted-state projection")


def _feature_block(font: Any, change: Mapping[str, Any]) -> tuple[str, int, Any]:
    block_type = change.get("blockType")
    identity = str(change.get("id") or "")
    collection_name = FEATURE_BLOCK_COLLECTIONS.get(block_type)
    if not collection_name or not identity:
        raise ValueError("feature-block target is incomplete")
    for index, block in enumerate(list(_value(font, collection_name, []) or [])):
        observed = _value(block, "identifier", None) or _value(block, "id", None)
        if str(observed or "") == identity:
            return collection_name, index, block
    raise ValueError("feature block is unavailable")


def persistent_state(owner: Any, scope: str, change: Mapping[str, Any] | None = None) -> Any:
    if scope == "layer":
        result = {"layer": _property_list(owner)}
    elif scope == "glyph":
        property_list = _property_list(owner)
        if not isinstance(property_list, dict):
            raise ValueError("Glyphs did not expose glyph metadata as a property list")
        result = {
            "propertyList": {key: value for key, value in property_list.items()
                             if str(key).lower() not in {"layers", "layersv2"}},
            "metadata": {name: _plain(_value(owner, name, None)) for name in GLYPH_METADATA_FIELDS},
        }
    elif scope == "font":
        result = {name: [_property_list(item) for item in list(_value(owner, name, []) or [])]
                  for name in FONT_FEATURE_FIELDS}
    elif scope == "feature_block":
        if change is None:
            result = {"featureBlock": _property_list(owner)}
        else:
            _collection, _index, block = _feature_block(owner, change)
            result = {"featureBlock": _property_list(block)}
    else:
        raise ValueError("unsupported native action scope")
    size = encoded_size(result)
    if size > MAX_TARGET_STATE_BYTES:
        raise ValueError("native action target state exceeds 8 MiB")
    return result


def encoded_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def current_hash(owner: Any, scope: str, change: Mapping[str, Any] | None = None) -> str:
    return state_hash(persistent_state(owner, scope, change))


def _copy_native(value: Any):
    method = getattr(value, "copy", None)
    if callable(method):
        return method()
    return copy.deepcopy(value)


def _write_feature_property(block: Any, key: str, item: Any) -> None:
    if key in ("id", "identifier"):
        return
    name = "name" if key == "tag" else key
    try:
        setattr(block, name, _copy_native(item))
        return
    except Exception:
        selector = "set" + name[:1].upper() + name[1:] + "_"
        setter = getattr(block, selector, None)
        if not callable(setter):
            raise
        setter(_copy_native(item))


def _restore_feature_properties(block: Any, wanted: Mapping[str, Any]) -> None:
    current = _property_list(block)
    for key in set(current) - set(wanted):
        if key in ("automatic", "disabled"):
            _write_feature_property(block, key, False)
        elif key not in ("id", "identifier", "tag", "name", "code"):
            _write_feature_property(block, key, None)
    for key, item in wanted.items():
        _write_feature_property(block, key, item)
    if _property_list(block) != dict(wanted):
        raise ValueError("Glyphs did not restore the feature block")


def capture(owner: Any, scope: str, change: Mapping[str, Any] | None = None) -> dict[str, Any]:
    # Prove the bounded projection before retaining a native object graph.
    state = persistent_state(owner, scope, change)
    if scope == "layer":
        value = _copy_native(owner)
    elif scope == "glyph":
        value = {name: _copy_native(_value(owner, name, None)) for name in GLYPH_METADATA_FIELDS}
    elif scope == "font":
        objects = {name: list(_value(owner, name, []) or []) for name in FONT_FEATURE_FIELDS}
        value = {name: [_copy_native(item) for item in objects[name]] for name in FONT_FEATURE_FIELDS}
    elif scope == "feature_block":
        if change is None:
            value = _copy_native(owner)
            collection_name = None
            index = None
        else:
            collection_name, index, block = _feature_block(owner, change)
            value = _copy_native(block)
    else:
        raise ValueError("unsupported native action scope")
    result = {"scope": scope, "value": value, "encodedBytes": encoded_size(state)}
    if scope == "font":
        result.update(objects=objects, propertyLists=state)
    if scope == "feature_block" and change is not None:
        result.update(
            collection=collection_name, index=index, id=change["id"],
            blockType=change["blockType"], propertyList=state["featureBlock"],
        )
    if scope == "layer":
        layer_state = state.get("layer", {}) if isinstance(state, Mapping) else {}
        result["restoreBackground"] = "background" in layer_state
        result["restoreBackgroundImage"] = "backgroundImage" in layer_state
    return result


def _replace_collection(owner: Any, name: str, values: list[Any]) -> None:
    values = list(values)
    try:
        setattr(owner, name, values)
        observed = list(_value(owner, name, []) or [])
        if len(observed) == len(values):
            return
    except Exception:
        pass
    collection = getattr(owner, name)
    for index in range(len(collection) - 1, -1, -1):
        del collection[index]
    for value in values:
        collection.append(value)
    if len(list(collection)) != len(values):
        raise ValueError(f"Glyphs did not restore {name}")


def _restore_layer(
    owner: Any,
    snapshot: Any,
    *,
    restore_background: bool,
    restore_background_image: bool,
) -> None:
    copier = getattr(owner, "getCopyOfContentFromLayer_doSelection_", None)
    if callable(copier):
        copier(snapshot, False)
    else:
        for name in LAYER_COLLECTION_FIELDS:
            _replace_collection(owner, name, [_copy_native(item) for item in list(_value(snapshot, name, []) or [])])
    for name in LAYER_SCALAR_FIELDS:
        wanted = _value(snapshot, name, None)
        if _plain(_value(owner, name, None)) == _plain(wanted):
            continue
        try:
            setattr(owner, name, _copy_native(wanted))
        except Exception:
            # Some absent optional properties are read-only on particular builds.
            if _value(owner, name, None) != _value(snapshot, name, None):
                raise
    wanted_background = _value(snapshot, "background", None) if restore_background else None
    current_background = _value(owner, "background", None) if restore_background else None
    if restore_background and wanted_background is not None and current_background is not None:
        background_copier = getattr(current_background, "getCopyOfContentFromLayer_doSelection_", None)
        if callable(background_copier):
            background_copier(wanted_background, False)
        else:
            for name in LAYER_COLLECTION_FIELDS:
                _replace_collection(
                    current_background, name,
                    [_copy_native(item) for item in list(_value(wanted_background, name, []) or [])],
                )
    wanted_image = _value(snapshot, "backgroundImage", None) if restore_background_image else None
    if restore_background_image:
        setattr(owner, "backgroundImage", None if wanted_image is None else _copy_native(wanted_image))


def restore(owner: Any, snapshot: Mapping[str, Any]) -> None:
    scope, value = snapshot["scope"], snapshot["value"]
    if scope == "layer":
        _restore_layer(
            owner,
            value,
            restore_background=bool(snapshot.get("restoreBackground")),
            restore_background_image=bool(snapshot.get("restoreBackgroundImage")),
        )
    elif scope == "glyph":
        for name in GLYPH_METADATA_FIELDS:
            wanted = value[name]
            if _plain(_value(owner, name, None)) != _plain(wanted):
                setattr(owner, name, _copy_native(wanted))
    elif scope == "font":
        objects = snapshot.get("objects")
        property_lists = snapshot.get("propertyLists")
        if not isinstance(objects, Mapping) or not isinstance(property_lists, Mapping):
            raise ValueError("font feature snapshot is incomplete")
        for name in FONT_FEATURE_FIELDS:
            retained = list(objects.get(name, []))
            wanted_rows = list(property_lists.get(name, []))
            if len(retained) != len(wanted_rows):
                raise ValueError("font feature snapshot is inconsistent")
            _replace_collection(owner, name, retained)
            observed = list(_value(owner, name, []) or [])
            if len(observed) != len(wanted_rows):
                raise ValueError(f"Glyphs did not restore {name}")
            for block, wanted in zip(observed, wanted_rows):
                if not isinstance(wanted, Mapping):
                    raise ValueError("font feature property list is unavailable")
                _restore_feature_properties(block, wanted)
    elif scope == "feature_block":
        collection_name = snapshot.get("collection")
        index = snapshot.get("index")
        wanted = snapshot.get("propertyList")
        if not isinstance(collection_name, str) or type(index) is not int or not isinstance(wanted, dict):
            raise ValueError("feature-block snapshot is incomplete")
        observed = list(_value(owner, collection_name, []) or [])
        if index >= len(observed):
            raise ValueError("feature block is unavailable for restoration")
        _restore_feature_properties(observed[index], wanted)
    else:
        raise ValueError("unsupported native action scope")


def _method(owner: Any, action: str):
    for selector in ACTION_SPECS[action]["selectors"]:
        method = getattr(owner, selector, None)
        if callable(method):
            return method
    raise ValueError(f"Glyphs does not support native action {action}")


def invoke(owner: Any, action: str, arguments: Mapping[str, Any], change: Mapping[str, Any] | None = None) -> None:
    target = _feature_block(owner, change)[2] if ACTION_SPECS[action]["scope"] == "feature_block" and change is not None else owner
    method = _method(target, action)
    result = method(*native_call_arguments(action, arguments))
    if isinstance(result, tuple) and len(result) > 1 and result[1] is not None:
        raise ValueError(f"Glyphs rejected native action {action}: {result[1]}")


@lru_cache(maxsize=1)
def _probed_actions() -> tuple[str, ...]:
    try:
        from Foundation import NSUndoManager  # type: ignore[import-not-found]
        from GlyphsApp import GSFeature, GSFont, GSFontMaster, GSGlyph, GSLayer  # type: ignore[import-not-found]
        undo = NSUndoManager.alloc().init()
        if not all(callable(getattr(undo, name, None)) for name in (
            "beginUndoGrouping", "endUndoGrouping", "registerUndoWithTarget_handler_",
            "disableUndoRegistration", "enableUndoRegistration",
        )):
            return ()
    except Exception:
        return ()

    try:
        font = GSFont()
        master = GSFontMaster(); font.masters.append(master)
        glyph = GSGlyph("glyphsMcpCapabilityProbe"); font.glyphs.append(glyph)
        layer = GSLayer(); layer.layerId = master.id; layer.associatedMasterId = master.id
        glyph.layers[master.id] = layer
        feature = GSFeature.alloc().init()
        feature.name = "glyphsMcpProbe"
        feature.code = ""
        feature.automatic = True
        font.features.append(feature)
        feature_id = _value(feature, "identifier", None) or _value(feature, "id", None)
        owners = {"layer": layer, "glyph": glyph, "font": font, "feature_block": font}
    except Exception:
        return ()
    result = []
    for action in NATIVE_ACTIONS:
        scope = ACTION_SPECS[action]["scope"]
        owner = owners[scope]
        change = ({"blockType": "feature", "id": str(feature_id)} if scope == "feature_block" else None)
        if owner is None:
            continue
        selector_owner = feature if scope == "feature_block" else owner
        if not feature_id and scope == "feature_block":
            continue
        if not any(callable(getattr(selector_owner, selector, None)) for selector in ACTION_SPECS[action]["selectors"]):
            continue
        try:
            before = current_hash(owner, scope, change)
            snapshot = capture(owner, scope, change)
            restore(owner, snapshot)
            if current_hash(owner, scope, change) != before:
                continue
        except Exception:
            continue
        result.append(action)
    return tuple(sorted(result))


def available_actions() -> list[str]:
    """Return the immutable-per-process startup probe as a fresh public list."""
    return list(_probed_actions())


def scope_for(action: str) -> str:
    return ACTION_SPECS[action]["scope"]
