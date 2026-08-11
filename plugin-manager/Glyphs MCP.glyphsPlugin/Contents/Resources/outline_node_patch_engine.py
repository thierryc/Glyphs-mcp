# encoding: utf-8

"""Pure validation and grid planning for explicit outline node patches."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext


MAX_NODE_POSITION_UPDATES = 256
POSITION_TOLERANCE = 1.0e-5
GRID_POLICIES = ("font", "continuous")

_REQUIRED_UPDATE_KEYS = {
    "path_index",
    "node_index",
    "expected_x",
    "expected_y",
    "expected_type",
    "x",
    "y",
}


def _finite_number(value, name):
    if isinstance(value, bool):
        raise ValueError("{} must be a finite number".format(name))
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("{} must be a finite number".format(name))
    if not math.isfinite(number):
        raise ValueError("{} must be a finite number".format(name))
    return number


def _strict_index(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("{} must be an integer".format(name))
    if value < 0:
        raise ValueError("{} must be nonnegative".format(name))
    return int(value)


def round_half_away_from_zero(value):
    number = float(value)
    if number >= 0.0:
        return int(math.floor(number + 0.5))
    return -int(math.floor(abs(number) + 0.5))


def normalize_grid_policy(value):
    if not isinstance(value, str) or value not in GRID_POLICIES:
        return None, "grid_policy must be one of: {}".format(", ".join(GRID_POLICIES))
    return value, None


def resolve_grid_policy(grid_policy, grid_length, grid_subdivision=1):
    policy, error = normalize_grid_policy(grid_policy)
    if error:
        return None, error

    try:
        subdivision = int(grid_subdivision)
    except (TypeError, ValueError, OverflowError):
        subdivision = 1
    subdivision = max(1, subdivision)

    if policy == "continuous":
        try:
            reported_length = float(grid_length)
            if not math.isfinite(reported_length) or reported_length < 0.0:
                reported_length = None
        except (TypeError, ValueError, OverflowError):
            reported_length = None
        return {
            "requestedPolicy": "continuous",
            "effectivePolicy": "continuous",
            "gridLength": reported_length,
            "gridSubDivision": subdivision,
            "snapStep": None,
            "fontGridDisabled": reported_length == 0.0,
        }, None

    try:
        length = float(grid_length)
    except (TypeError, ValueError, OverflowError):
        return None, "font.gridLength must be a finite nonnegative number"
    if not math.isfinite(length) or length < 0.0:
        return None, "font.gridLength must be a finite nonnegative number"
    return {
        "requestedPolicy": "font",
        "effectivePolicy": "continuous" if length == 0.0 else "font",
        "gridLength": length,
        "gridSubDivision": subdivision,
        "snapStep": length if length > 0.0 else None,
        "fontGridDisabled": length == 0.0,
    }, None


def _grid_scalar(value, grid_step):
    if grid_step is None:
        return float(value)
    try:
        with localcontext() as context:
            context.prec = 50
            decimal_value = Decimal(str(float(value)))
            decimal_step = Decimal(str(float(grid_step)))
            grid_index = (decimal_value / decimal_step).to_integral_value(rounding=ROUND_HALF_UP)
            snapped = float(grid_index * decimal_step)
    except (InvalidOperation, ValueError, OverflowError, ZeroDivisionError):
        snapped = round_half_away_from_zero(float(value) / float(grid_step)) * float(grid_step)
    if math.isclose(grid_step, round(grid_step), rel_tol=0.0, abs_tol=1.0e-12):
        rounded = round(snapped)
        if math.isclose(snapped, rounded, rel_tol=0.0, abs_tol=1.0e-9):
            return int(rounded)
    return float(snapped)


def _point(x, y):
    return {"x": x, "y": y}


def positions_match(first, second, tolerance=POSITION_TOLERANCE):
    try:
        return math.hypot(
            float(first[0]) - float(second[0]),
            float(first[1]) - float(second[1]),
        ) <= float(tolerance)
    except (TypeError, ValueError, OverflowError, IndexError):
        return False


def prepare_node_position_updates(
    updates,
    *,
    grid_policy="font",
    grid_length=1.0,
    grid_subdivision=1,
):
    """Validate explicit updates and return authoritative grid-aware proposals."""

    if not isinstance(updates, list) or not updates:
        return None, "updates must be a nonempty list"
    if len(updates) > MAX_NODE_POSITION_UPDATES:
        return None, "updates exceeds the {}-node limit".format(MAX_NODE_POSITION_UPDATES)

    grid, error = resolve_grid_policy(grid_policy, grid_length, grid_subdivision)
    if error:
        return None, error

    normalized = []
    seen = set()
    for update_index, raw in enumerate(updates):
        if not isinstance(raw, dict):
            return None, "updates[{}] must be an object".format(update_index)
        missing = sorted(_REQUIRED_UPDATE_KEYS - set(raw))
        unknown = sorted(set(raw) - _REQUIRED_UPDATE_KEYS)
        if missing:
            return None, "updates[{}] is missing: {}".format(update_index, ", ".join(missing))
        if unknown:
            return None, "updates[{}] has unknown fields: {}".format(update_index, ", ".join(unknown))

        try:
            path_index = _strict_index(raw["path_index"], "updates[{}].path_index".format(update_index))
            node_index = _strict_index(raw["node_index"], "updates[{}].node_index".format(update_index))
            expected_x = _finite_number(raw["expected_x"], "updates[{}].expected_x".format(update_index))
            expected_y = _finite_number(raw["expected_y"], "updates[{}].expected_y".format(update_index))
            requested_x = _finite_number(raw["x"], "updates[{}].x".format(update_index))
            requested_y = _finite_number(raw["y"], "updates[{}].y".format(update_index))
        except ValueError as exc:
            return None, str(exc)

        expected_type = raw["expected_type"]
        if not isinstance(expected_type, str) or not expected_type.strip():
            return None, "updates[{}].expected_type must be a nonempty string".format(update_index)
        expected_type = expected_type.strip().lower()

        target = (path_index, node_index)
        if target in seen:
            return None, "updates contains duplicate target path {} node {}".format(path_index, node_index)
        seen.add(target)

        proposed_x = _grid_scalar(requested_x, grid["snapStep"])
        proposed_y = _grid_scalar(requested_y, grid["snapStep"])
        snapped = not positions_match(
            (requested_x, requested_y),
            (proposed_x, proposed_y),
            tolerance=1.0e-9,
        )
        normalized.append(
            {
                "pathIndex": path_index,
                "nodeIndex": node_index,
                "expectedType": expected_type,
                "expected": _point(expected_x, expected_y),
                "requested": _point(requested_x, requested_y),
                "proposed": _point(proposed_x, proposed_y),
                "snapped": snapped,
            }
        )

    return {"grid": grid, "updates": normalized}, None


__all__ = [
    "GRID_POLICIES",
    "MAX_NODE_POSITION_UPDATES",
    "POSITION_TOLERANCE",
    "normalize_grid_policy",
    "positions_match",
    "prepare_node_position_updates",
    "resolve_grid_policy",
    "round_half_away_from_zero",
]
