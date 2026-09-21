"""Closed contracts shared by native-action preparation and application.

This module deliberately contains names and validation only.  A request cannot
provide a selector, Python expression, menu item, or state projection.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from .models import ProtocolError, canonical_json


MAX_TARGETS = 100
MAX_LAYER_CHANGES = 4096
MAX_TARGET_STATE_BYTES = 8 * 1024 * 1024
MAX_JOB_STATE_BYTES = 64 * 1024 * 1024


_LAYER_REPORT_FIELDS = ("width", "paths", "components", "anchors")
_GLYPH_REPORT_FIELDS = ("name", "unicode", "category", "subCategory", "script")
_FONT_REPORT_FIELDS = ("featurePrefixes", "classes", "features")
_FEATURE_BLOCK_REPORT_FIELDS = ("name", "codeLength", "automatic", "disabled")


def _spec(
    scope: str,
    selector: str,
    *,
    arguments: Mapping[str, Mapping[str, Any]] | None = None,
    call_arguments: tuple[Any, ...] = (),
) -> dict[str, Any]:
    return {
        "scope": scope,
        "selectors": (selector,),
        "arguments": dict(arguments or {}),
        "callArguments": call_arguments,
        "projection": {"layer": "layer_property_list", "glyph": "glyph_metadata", "font": "font_features", "feature_block": "feature_block_property_list"}[scope],
        "reportFields": {"layer": _LAYER_REPORT_FIELDS, "glyph": _GLYPH_REPORT_FIELDS, "font": _FONT_REPORT_FIELDS, "feature_block": _FEATURE_BLOCK_REPORT_FIELDS}[scope],
        "target": {"layer": "explicit_layers", "glyph": "explicit_glyphs", "font": "font", "feature_block": "explicit_feature_blocks"}[scope],
    }


# This is the only native selector registry. Requests cannot extend it.
ACTION_SPECS = {
    "update_metrics": _spec("layer", "syncMetrics"),
    "correct_path_direction": _spec("layer", "correctPathDirection"),
    "round_coordinates": _spec("layer", "roundCoordinates"),
    "add_extremes": _spec(
        "layer", "addNodesAtExtremes",
        arguments={"force": {"type": "boolean", "default": False}},
        call_arguments=("$force", False),
    ),
    "cleanup_paths": _spec("layer", "cleanUpPaths"),
    "remove_overlap": _spec("layer", "removeOverlap", call_arguments=(False,)),
    "add_missing_anchors": _spec("layer", "addMissingAnchors"),
    "align_components": _spec("layer", "doAlignComponents"),
    "decompose_components": _spec("layer", "decomposeComponents"),
    "decompose_corners": _spec("layer", "decomposeCorners"),
    "make_components": _spec("layer", "makeComponents"),
    "reinterpolate": _spec("layer", "reinterpolate"),
    "connect_open_paths": _spec("layer", "connectAllOpenPaths"),
    "swap_foreground_background": _spec("layer", "swapForegroundWithBackground"),
    "update_glyph_info": _spec("glyph", "updateGlyphInfo", call_arguments=(False,)),
    "update_features": _spec("font", "updateFeatures"),
    "update_automatic_feature_block": _spec("feature_block", "update"),
}

NATIVE_ACTIONS = tuple(ACTION_SPECS)
LAYER_ACTIONS = frozenset(name for name, spec in ACTION_SPECS.items() if spec["scope"] == "layer")
GLYPH_ACTIONS = frozenset(name for name, spec in ACTION_SPECS.items() if spec["scope"] == "glyph")
FONT_ACTIONS = frozenset(name for name, spec in ACTION_SPECS.items() if spec["scope"] == "font")
FEATURE_BLOCK_ACTIONS = frozenset(name for name, spec in ACTION_SPECS.items() if spec["scope"] == "feature_block")


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolError("invalid_request", f"{label} must be an object")
    return value


def _closed(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unexpected = sorted(set(value) - allowed)
    if unexpected:
        raise ProtocolError("invalid_request", f"{label} has unexpected fields: {', '.join(unexpected)}")


def _text(value: Any, label: str, maximum: int = 255) -> str:
    if not isinstance(value, str):
        raise ProtocolError("invalid_request", f"{label} must be a string")
    result = value.strip()
    if not result or len(result) > maximum:
        raise ProtocolError("invalid_request", f"{label} must be 1-{maximum} characters")
    return result


def _hash(value: Any, label: str) -> str:
    result = str(value or "")
    if len(result) != 71 or not result.startswith("sha256:"):
        raise ProtocolError("invalid_request", f"{label} must be a SHA-256 fingerprint")
    try:
        int(result[7:], 16)
    except ValueError as exc:
        raise ProtocolError("invalid_request", f"{label} must be a SHA-256 fingerprint") from exc
    return result


def normalize_arguments(action: str, value: Any = None) -> dict[str, Any]:
    arguments = {} if value is None else _object(value, "native action arguments")
    accepted = ACTION_SPECS[action]["arguments"]
    _closed(arguments, set(accepted), f"{action} arguments")
    normalized = {}
    for name, contract in accepted.items():
        item = arguments.get(name, contract["default"])
        if contract["type"] == "boolean" and not isinstance(item, bool):
            raise ProtocolError("invalid_request", f"{action} {name} must be a boolean")
        normalized[name] = item
    if not accepted and arguments:
        raise ProtocolError("invalid_request", f"{action} does not accept arguments")
    return normalized


def native_call_arguments(action: str, arguments: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(
        arguments[value[1:]] if isinstance(value, str) and value.startswith("$") else value
        for value in ACTION_SPECS[action]["callArguments"]
    )


def _layer_scope(value: Any) -> dict[str, Any]:
    scope = _object(value, "layer scope")
    _closed(scope, {"scope", "ids"}, "layer scope")
    name = scope.get("scope")
    if name == "all_masters":
        if set(scope) != {"scope"}:
            raise ProtocolError("invalid_request", "all_masters does not accept layer IDs")
        return {"scope": "all_masters"}
    if name != "ids":
        raise ProtocolError("invalid_request", "layer scope must be all_masters or ids")
    ids = scope.get("ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_LAYER_CHANGES:
        raise ProtocolError("invalid_request", "layer IDs must contain 1-4,096 values")
    normalized = [_text(item, "layer ID") for item in ids]
    if len(normalized) != len(set(normalized)):
        raise ProtocolError("invalid_request", "layer IDs must be unique")
    return {"scope": "ids", "ids": normalized}


def validate_options(value: Any) -> dict[str, Any]:
    options = _object(value, "native_action options")
    _closed(options, {"action", "targets", "arguments"}, "native_action options")
    action = _text(options.get("action"), "native action", maximum=80)
    spec = ACTION_SPECS.get(action)
    if spec is None:
        raise ProtocolError("unsupported_action", f"unsupported native action: {action}")
    arguments = normalize_arguments(action, options.get("arguments"))
    scope = spec["scope"]
    if scope == "font":
        if "targets" in options:
            raise ProtocolError("invalid_request", f"{action} does not accept targets")
        return {"action": action, "scope": scope, "arguments": arguments}

    targets = options.get("targets")
    if not isinstance(targets, list) or not 1 <= len(targets) <= MAX_TARGETS:
        raise ProtocolError("invalid_request", "native_action requires 1-100 targets")
    normalized = []
    seen = set()
    for raw in targets:
        target = _object(raw, "native action target")
        if scope == "feature_block":
            allowed = {"blockType", "id"}
        else:
            allowed = {"glyph", "layers"} if scope == "layer" else {"glyph"}
        _closed(target, allowed, "native action target")
        if set(target) != allowed:
            raise ProtocolError("invalid_request", f"{scope} target fields are incomplete")
        if scope == "feature_block":
            block_type = target.get("blockType")
            if block_type not in ("prefix", "class", "feature"):
                raise ProtocolError("invalid_request", "feature blockType must be prefix, class or feature")
            identity = _text(target.get("id"), "feature block id")
            key = (block_type, identity)
            if key in seen:
                raise ProtocolError("invalid_request", "native action feature-block targets must be unique")
            seen.add(key)
            normalized.append({"blockType": block_type, "id": identity})
            continue
        glyph = _text(target.get("glyph"), "glyph")
        if glyph in seen:
            raise ProtocolError("invalid_request", "native action glyph targets must be unique")
        seen.add(glyph)
        item = {"glyph": glyph}
        if scope == "layer":
            item["layers"] = _layer_scope(target.get("layers"))
        normalized.append(item)
    return {"action": action, "scope": scope, "arguments": arguments, "targets": normalized}


def validate_change(value: Mapping[str, Any]) -> dict[str, Any]:
    action = _text(value.get("action"), "native action", maximum=80)
    spec = ACTION_SPECS.get(action)
    if spec is None:
        raise ProtocolError("unsupported_change", f"unsupported native action: {action}")
    scope = value.get("scope")
    if scope != spec["scope"]:
        raise ProtocolError("invalid_request", "native action scope does not match its action")
    common = {"kind", "action", "scope", "arguments", "beforeHash", "afterHash"}
    required = set(common)
    if scope == "layer":
        required.update(("glyph", "layer"))
    elif scope == "glyph":
        required.add("glyph")
    elif scope == "feature_block":
        required.update(("blockType", "id"))
    if set(value) != required:
        raise ProtocolError("invalid_request", "native action change fields are incomplete or unexpected")
    result = {
        "kind": "native_action",
        "action": action,
        "scope": scope,
        "arguments": normalize_arguments(action, value.get("arguments")),
        "beforeHash": _hash(value.get("beforeHash"), "native action beforeHash"),
        "afterHash": _hash(value.get("afterHash"), "native action afterHash"),
    }
    if scope in ("layer", "glyph"):
        result["glyph"] = _text(value.get("glyph"), "native action glyph")
    if scope == "layer":
        result["layer"] = _text(value.get("layer"), "native action layer")
    if scope == "feature_block":
        block_type = value.get("blockType")
        if block_type not in ("prefix", "class", "feature"):
            raise ProtocolError("invalid_request", "native action feature blockType is invalid")
        result["blockType"] = block_type
        result["id"] = _text(value.get("id"), "native action feature block id")
    if result["beforeHash"] == result["afterHash"]:
        raise ProtocolError("invalid_request", "native action change has no effect")
    return result


def state_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def recognized_actions(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item for item in value if isinstance(item, str) and item in ACTION_SPECS})
