# encoding: utf-8

"""Host-independent fixed horizontal IconGrid centering contract."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, Iterable, Optional, Tuple


ROOT_KEY = "com.litsquare.icongrid"
CHANGED_NOTIFICATION = "com.litsquare.icongrid.changed"
SCHEMA_VERSION = 1
CENTER_MODE = "coordinate"


class IconGridCenteringError(ValueError):
    """Raised when a centering change cannot preserve the domain contract."""


def _mapping(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return dict(value)
    try:
        return dict(value.items())
    except Exception:
        pass
    try:
        return {key: value[key] for key in value.keys()}
    except Exception:
        return None


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _normalized_bounds(value: Any) -> Optional[Tuple[float, float, float, float]]:
    bounds = _mapping(value)
    if bounds is None:
        return None
    x = _finite(bounds.get("x"))
    y = _finite(bounds.get("y"))
    width = _finite(bounds.get("width"))
    height = _finite(bounds.get("height"))
    if None in (x, y, width, height):
        return None
    opposite_x = x + width
    opposite_y = y + height
    return min(x, opposite_x), min(y, opposite_y), max(x, opposite_x), max(y, opposite_y)


def validate_policy_root(raw: Any, present: bool) -> Dict[str, Any]:
    """Validate only the owned reverse-domain root while preserving unknown fields."""

    if not present:
        return {
            "state": "missing",
            "label": "Missing",
            "schemaVersion": None,
            "policyPresent": False,
            "policyValid": False,
            "storedX": None,
            "value": None,
            "errors": [],
            "warnings": [],
        }
    root = _mapping(raw)
    if root is None:
        return {
            "state": "invalid",
            "label": "Invalid",
            "schemaVersion": None,
            "policyPresent": False,
            "policyValid": False,
            "storedX": None,
            "value": raw,
            "errors": [{"path": "$", "message": "IconGrid user data must be a dictionary."}],
            "warnings": [],
        }
    if not root:
        return {
            "state": "empty",
            "label": "Empty",
            "schemaVersion": None,
            "policyPresent": False,
            "policyValid": False,
            "storedX": None,
            "value": {},
            "errors": [],
            "warnings": [],
        }
    version = root.get("schemaVersion")
    policy_present = "centerX" in root
    if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
        return {
            "state": "invalid",
            "label": "Invalid",
            "schemaVersion": version,
            "policyPresent": policy_present,
            "policyValid": False,
            "storedX": None,
            "value": root,
            "errors": [{"path": "$.schemaVersion", "message": "schemaVersion must be a positive integer."}],
            "warnings": [],
        }
    if version > SCHEMA_VERSION:
        return {
            "state": "unsupported_schema",
            "label": "Unsupported schema",
            "schemaVersion": version,
            "policyPresent": policy_present,
            "policyValid": False,
            "storedX": None,
            "value": root,
            "errors": [],
            "warnings": [{"path": "$.schemaVersion", "message": "Future schemas are read-only."}],
        }
    policy = _mapping(root.get("centerX")) if policy_present else None
    stored_x = _finite(policy.get("x")) if policy is not None else None
    valid = bool(
        policy is not None
        and policy.get("mode") == CENTER_MODE
        and stored_x is not None
    )
    errors = []
    if policy_present and not valid:
        errors.append(
            {
                "path": "$.centerX",
                "message": "centerX must use coordinate mode with a finite x value.",
            }
        )
    return {
        "state": "valid" if not errors else "invalid",
        "label": "Valid v1" if not errors else "Invalid",
        "schemaVersion": version,
        "policyPresent": policy_present,
        "policyValid": bool(policy_present and valid),
        "storedX": stored_x if valid else None,
        "value": root,
        "errors": errors,
        "warnings": [],
    }


def content_union(entries: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve finite union bounds from path and component content records."""

    entries = list(entries)
    valid_bounds = []
    for entry in entries:
        bounds = _normalized_bounds(entry.get("bounds")) if isinstance(entry, dict) else None
        if bounds is not None:
            valid_bounds.append(bounds)
    if not valid_bounds:
        return {
            "shapeCount": len(entries),
            "validShapeCount": 0,
            "bounds": None,
            "centerX": None,
        }
    xmin = min(item[0] for item in valid_bounds)
    ymin = min(item[1] for item in valid_bounds)
    xmax = max(item[2] for item in valid_bounds)
    ymax = max(item[3] for item in valid_bounds)
    return {
        "shapeCount": len(entries),
        "validShapeCount": len(valid_bounds),
        "bounds": {"x": xmin, "y": ymin, "width": xmax - xmin, "height": ymax - ymin},
        "centerX": (xmin + xmax) / 2.0,
    }


def center_candidates(width: Any, entries: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    layer_width = _finite(width)
    advance_x = layer_width / 2.0 if layer_width is not None else None
    content = content_union(entries)
    return {
        "advance": {"available": advance_x is not None, "x": advance_x},
        "layerContent": {
            "available": content["centerX"] is not None,
            "shapeCount": content["shapeCount"],
            "validShapeCount": content["validShapeCount"],
            "bounds": content["bounds"],
            "x": content["centerX"],
        },
    }


def resolve_center(width: Any, policy: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve only the direct fixed-coordinate policy."""

    layer_width = _finite(width)
    advance_center = layer_width / 2.0 if layer_width is not None else None
    policy_present = bool(policy.get("policyPresent"))
    if not policy_present:
        state = "default"
        fallback = False
        resolved = advance_center
        stored = None
    elif policy.get("state") == "unsupported_schema":
        state = "unsupported_schema"
        fallback = True
        resolved = advance_center
        stored = None
    elif not policy.get("policyValid"):
        state = "invalid"
        fallback = True
        resolved = advance_center
        stored = None
    else:
        state = "valid"
        fallback = False
        stored = policy.get("storedX")
        resolved = stored
    return {
        "state": state,
        "mode": CENTER_MODE if policy.get("policyValid") else None,
        "policyPresent": policy_present,
        "storedX": stored,
        "resolvedX": resolved,
        "fallback": fallback,
    }


def propose_set(raw: Any, present: bool, center_x: Any) -> Dict[str, Any]:
    coordinate = _finite(center_x)
    if coordinate is None:
        raise IconGridCenteringError("IconGrid horizontal center must be a finite number.")
    validation = validate_policy_root(raw, present)
    if validation["state"] == "unsupported_schema":
        raise IconGridCenteringError("Unsupported IconGrid centering schema is read-only.")
    if validation["state"] not in {"missing", "empty", "valid", "invalid"}:
        raise IconGridCenteringError("Invalid IconGrid centering data cannot be changed safely.")
    proposed = copy.deepcopy(validation.get("value") or {})
    if proposed and proposed.get("schemaVersion") != SCHEMA_VERSION:
        raise IconGridCenteringError("Invalid IconGrid centering data cannot be changed safely.")
    existing_policy = _mapping(proposed.get("centerX")) or {}
    existing_policy.pop("role", None)
    existing_policy["mode"] = CENTER_MODE
    existing_policy["x"] = coordinate
    proposed["schemaVersion"] = SCHEMA_VERSION
    proposed["centerX"] = existing_policy
    return proposed


def propose_reset(raw: Any, present: bool) -> Tuple[bool, Optional[Dict[str, Any]]]:
    validation = validate_policy_root(raw, present)
    if validation["state"] == "missing":
        return False, None
    if validation["state"] == "unsupported_schema":
        raise IconGridCenteringError("Unsupported IconGrid centering schema is read-only.")
    root = _mapping(validation.get("value"))
    if root is None or root.get("schemaVersion") != SCHEMA_VERSION:
        raise IconGridCenteringError("Invalid IconGrid centering data cannot be reset safely.")
    root.pop("centerX", None)
    meaningful = {key: value for key, value in root.items() if key != "schemaVersion"}
    if not meaningful:
        return False, None
    return True, root


def state_fingerprint(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "CENTER_MODE",
    "CHANGED_NOTIFICATION",
    "IconGridCenteringError",
    "ROOT_KEY",
    "SCHEMA_VERSION",
    "center_candidates",
    "content_union",
    "propose_reset",
    "propose_set",
    "resolve_center",
    "state_fingerprint",
    "validate_policy_root",
]
