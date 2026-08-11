"""Independent cubic Bezier geometry helpers for Glyphs MCP.

This module is deliberately host-independent: it imports neither GlyphsApp nor
AppKit/PyObjC.  Callers pass plain node dictionaries so the mathematics can be
tested outside Glyphs and shared by JSON review and image rendering.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


Point = Tuple[float, float]

GEOMETRY_DATA_VERSION = 1
CURVE_QUALITY_DATA_VERSION = 2
DEFAULT_SAMPLES_PER_CURVE = 51
MIN_SAMPLES_PER_CURVE = 9
MAX_SAMPLES_PER_CURVE = 257
MAX_SAMPLE_DETAIL_SEGMENTS = 64
MAX_ADAPTIVE_RECURSION = 16
MAX_SELF_INTERSECTIONS = 8

_EPSILON = 1.0e-12
_PARALLEL_RELATIVE_EPSILON = 1.0e-9
_MIN_RATIO = 0.01
_MAX_RATIO = 0.99
DEFAULT_MAX_GRID_TANGENT_DEVIATION_DEG = 0.25
_GRID_NEIGHBORHOOD_RADIUS = 2


def _node_value(node: Any, key: str, default: Any = None) -> Any:
    if isinstance(node, dict):
        return node.get(key, default)
    return getattr(node, key, default)


def _node_type(node: Any) -> str:
    return str(_node_value(node, "type", "") or "").lower()


def _node_point(node: Any) -> Point:
    x = float(_node_value(node, "x", 0.0))
    y = float(_node_value(node, "y", 0.0))
    return (x, y)


def _finite_point(point: Point) -> bool:
    return math.isfinite(point[0]) and math.isfinite(point[1])


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _scale(value: Point, factor: float) -> Point:
    return (value[0] * factor, value[1] * factor)


def _length(value: Point) -> float:
    return math.hypot(value[0], value[1])


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _point_payload(point: Point) -> Dict[str, float]:
    return {"x": float(point[0]), "y": float(point[1])}


def _grid_scalar(value: float, grid_step: float) -> Any:
    if math.isclose(grid_step, round(grid_step), rel_tol=0.0, abs_tol=1.0e-12):
        rounded = round(value)
        if math.isclose(value, rounded, rel_tol=0.0, abs_tol=1.0e-9):
            return int(rounded)
    return float(value)


def _grid_point_payload(point: Point, grid_step: float) -> Dict[str, Any]:
    return {
        "x": _grid_scalar(point[0], grid_step),
        "y": _grid_scalar(point[1], grid_step),
    }


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _angle_degrees(a: Point, b: Point) -> float:
    length_product = _length(a) * _length(b)
    if length_product <= _EPSILON:
        return float("inf")
    cosine = max(-1.0, min(1.0, _dot(a, b) / length_product))
    return math.degrees(math.acos(cosine))


def _grid_axis_values(value: float, grid_step: float) -> List[float]:
    scaled = value / grid_step
    base = math.floor(scaled)
    values = {
        float(index) * grid_step
        for index in range(
            int(base) - _GRID_NEIGHBORHOOD_RADIUS,
            int(base) + _GRID_NEIGHBORHOOD_RADIUS + 2,
        )
    }
    return sorted(values)


def _tunni_metrics_for_points(
    p0: Point,
    p1: Point,
    p2: Point,
    p3: Point,
    *,
    upm: float,
    min_handle_length: float,
) -> Optional[Dict[str, Any]]:
    v1 = _sub(p1, p0)
    v2 = _sub(p2, p3)
    len1 = _length(v1)
    len2 = _length(v2)
    if len1 < min_handle_length or len2 < min_handle_length:
        return None
    determinant = _cross(v1, v2)
    if abs(determinant) <= max(_PARALLEL_RELATIVE_EPSILON * len1 * len2, _EPSILON):
        return None
    delta = _sub(p3, p0)
    start_parameter = _cross(delta, v2) / determinant
    end_parameter = _cross(delta, v1) / determinant
    if not math.isfinite(start_parameter) or not math.isfinite(end_parameter):
        return None
    if start_parameter <= 0.0 or end_parameter <= 0.0:
        return None
    tunni_point = _add(p0, _scale(v1, start_parameter))
    if not _finite_point(tunni_point):
        return None
    start_distance = _length(_sub(tunni_point, p0))
    end_distance = _length(_sub(tunni_point, p3))
    if (
        start_distance <= _EPSILON
        or end_distance <= _EPSILON
        or start_distance > upm * 8.0
        or end_distance > upm * 8.0
    ):
        return None
    start_ratio = len1 / start_distance
    end_ratio = len2 / end_distance
    if not (_MIN_RATIO <= start_ratio <= _MAX_RATIO and _MIN_RATIO <= end_ratio <= _MAX_RATIO):
        return None
    imbalance = abs(start_ratio - end_ratio) / max(abs(start_ratio), abs(end_ratio), _EPSILON)
    return {
        "tunniPoint": tunni_point,
        "ratios": (start_ratio, end_ratio),
        "relativeImbalance": imbalance,
    }


def _best_grid_tunni_candidate(
    p0: Point,
    p1: Point,
    p2: Point,
    p3: Point,
    ideal1: Point,
    ideal2: Point,
    *,
    upm: float,
    grid_step: float,
    imbalance_threshold: float,
    min_handle_length: float,
    max_tangent_deviation_deg: float,
) -> Optional[Dict[str, Any]]:
    original1 = _sub(p1, p0)
    original2 = _sub(p2, p3)
    max_move = upm * 0.25
    best = None
    best_key = None
    points1 = [
        (x, y)
        for x in _grid_axis_values(ideal1[0], grid_step)
        for y in _grid_axis_values(ideal1[1], grid_step)
    ]
    points2 = [
        (x, y)
        for x in _grid_axis_values(ideal2[0], grid_step)
        for y in _grid_axis_values(ideal2[1], grid_step)
    ]
    for candidate1 in points1:
        tangent1 = _sub(candidate1, p0)
        if _dot(tangent1, original1) <= 0.0 or _length(_sub(candidate1, p1)) > max_move:
            continue
        angle1 = _angle_degrees(original1, tangent1)
        if angle1 > max_tangent_deviation_deg:
            continue
        for candidate2 in points2:
            tangent2 = _sub(candidate2, p3)
            if _dot(tangent2, original2) <= 0.0 or _length(_sub(candidate2, p2)) > max_move:
                continue
            angle2 = _angle_degrees(original2, tangent2)
            if angle2 > max_tangent_deviation_deg:
                continue
            metrics = _tunni_metrics_for_points(
                p0,
                candidate1,
                candidate2,
                p3,
                upm=upm,
                min_handle_length=min_handle_length,
            )
            if metrics is None or metrics["relativeImbalance"] > imbalance_threshold + 1.0e-12:
                continue
            ideal_distance = (
                (candidate1[0] - ideal1[0]) ** 2
                + (candidate1[1] - ideal1[1]) ** 2
                + (candidate2[0] - ideal2[0]) ** 2
                + (candidate2[1] - ideal2[1]) ** 2
            )
            key = (
                float(metrics["relativeImbalance"]),
                max(float(angle1), float(angle2)),
                float(ideal_distance),
                float(candidate1[0]),
                float(candidate1[1]),
                float(candidate2[0]),
                float(candidate2[1]),
            )
            if best_key is None or key < best_key:
                best_key = key
                best = {
                    "handle1": candidate1,
                    "handle2": candidate2,
                    "metrics": metrics,
                    "tangentDeviationDeg": {
                        "handle1": float(angle1),
                        "handle2": float(angle2),
                        "maximum": max(float(angle1), float(angle2)),
                    },
                }
    return best


def _finite_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _segment_index_value(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _rejected_segment(
    segment_end_node_index: Any,
    reason: str,
    *,
    node_indices: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": False,
        "eligible": False,
        "segmentEndNodeIndex": _segment_index_value(segment_end_node_index),
        "reason": str(reason),
    }
    if node_indices is not None:
        payload["nodeIndices"] = dict(node_indices)
    return payload


def _validated_tunni_parameters(
    upm: Any,
    imbalance_threshold: Any,
    min_handle_length: Any,
) -> Tuple[Optional[Tuple[float, float, float]], Optional[str]]:
    upm_value = _finite_float(upm)
    if upm_value is None or upm_value <= 0.0:
        return None, "invalid_upm"
    imbalance_value = _finite_float(imbalance_threshold)
    if imbalance_value is None or not 0.0 <= imbalance_value <= 1.0:
        return None, "invalid_imbalance_threshold"
    minimum_value = _finite_float(min_handle_length)
    if minimum_value is None or minimum_value < 0.0:
        return None, "invalid_min_handle_length"
    return (upm_value, imbalance_value, max(1.0, minimum_value)), None


def clamp_samples_per_curve(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError, OverflowError):
        count = DEFAULT_SAMPLES_PER_CURVE
    count = max(MIN_SAMPLES_PER_CURVE, min(MAX_SAMPLES_PER_CURVE, count))
    if count % 2 == 0:
        count = count + 1 if count < MAX_SAMPLES_PER_CURVE else count - 1
    return count


def _path_index(index: int, count: int, closed: bool) -> Optional[int]:
    if closed and count:
        return int(index) % int(count)
    if index < 0 or index >= count:
        return None
    return int(index)


def extract_cubic_segment(
    nodes: Sequence[Any],
    segment_end_node_index: int,
    *,
    closed: bool,
) -> Dict[str, Any]:
    """Extract the four points for the cubic ending at an on-curve node."""

    count = len(nodes)
    end_index = _segment_index_value(segment_end_node_index)
    if end_index is None:
        return _rejected_segment(None, "invalid_segment_index")
    if end_index < 0 or end_index >= count:
        return _rejected_segment(end_index, "index_out_of_range")
    if count < 4:
        return _rejected_segment(end_index, "insufficient_nodes")

    indices = [_path_index(end_index - delta, count, bool(closed)) for delta in (3, 2, 1, 0)]
    if any(index is None for index in indices):
        return _rejected_segment(end_index, "open_path_boundary")
    start_index, handle1_index, handle2_index, resolved_end_index = [int(index) for index in indices]

    start_node = nodes[start_index]
    handle1_node = nodes[handle1_index]
    handle2_node = nodes[handle2_index]
    end_node = nodes[resolved_end_index]
    if _node_type(end_node) != "curve":
        return _rejected_segment(end_index, "end_node_not_curve")
    if _node_type(handle1_node) != "offcurve" or _node_type(handle2_node) != "offcurve":
        return _rejected_segment(end_index, "missing_cubic_handles")
    if _node_type(start_node) == "offcurve":
        return _rejected_segment(end_index, "missing_start_oncurve")

    try:
        points = [_node_point(node) for node in (start_node, handle1_node, handle2_node, end_node)]
    except (TypeError, ValueError, OverflowError):
        return _rejected_segment(end_index, "nonfinite_coordinate")
    if not all(_finite_point(point) for point in points):
        return _rejected_segment(end_index, "nonfinite_coordinate")

    return {
        "ok": True,
        "segmentEndNodeIndex": end_index,
        "nodeIndices": {
            "start": start_index,
            "handle1": handle1_index,
            "handle2": handle2_index,
            "end": resolved_end_index,
        },
        "points": tuple(points),
    }


def cubic_segment_end_indices(nodes: Sequence[Any], *, closed: bool) -> List[int]:
    out: List[int] = []
    for index in range(len(nodes)):
        if extract_cubic_segment(nodes, index, closed=bool(closed)).get("ok"):
            out.append(index)
    return out


def analyze_tunni_segment(
    nodes: Sequence[Any],
    segment_end_node_index: int,
    *,
    closed: bool,
    upm: float = 1000.0,
    imbalance_threshold: float = 0.05,
    min_handle_length: float = 1.0,
    grid_step: Optional[float] = None,
    max_grid_tangent_deviation_deg: float = DEFAULT_MAX_GRID_TANGENT_DEVIATION_DEG,
) -> Dict[str, Any]:
    """Review one cubic and propose a conservative Tunni balance."""

    validated, parameter_reason = _validated_tunni_parameters(upm, imbalance_threshold, min_handle_length)
    if parameter_reason:
        return _rejected_segment(segment_end_node_index, parameter_reason)
    assert validated is not None
    upm_value, imbalance_value, minimum_handle_value = validated
    grid_value = None
    if grid_step is not None:
        grid_value = _finite_float(grid_step)
        if grid_value is None or grid_value <= 0.0:
            return _rejected_segment(segment_end_node_index, "invalid_grid_step")
    angle_limit = _finite_float(max_grid_tangent_deviation_deg)
    if angle_limit is None or not 0.0 <= angle_limit <= 45.0:
        return _rejected_segment(segment_end_node_index, "invalid_grid_tangent_deviation")

    segment = extract_cubic_segment(nodes, segment_end_node_index, closed=bool(closed))
    if not segment.get("ok"):
        return segment

    p0, p1, p2, p3 = segment["points"]
    v1 = _sub(p1, p0)
    v2 = _sub(p2, p3)
    len1 = _length(v1)
    len2 = _length(v2)
    result: Dict[str, Any] = {
        "ok": True,
        "eligible": False,
        "segmentEndNodeIndex": int(segment["segmentEndNodeIndex"]),
        "nodeIndices": dict(segment["nodeIndices"]),
        "handleLengths": {"start": float(len1), "end": float(len2)},
    }
    if len1 < minimum_handle_value or len2 < minimum_handle_value:
        result["reason"] = "handle_too_short"
        return result

    determinant = _cross(v1, v2)
    parallel_limit = _PARALLEL_RELATIVE_EPSILON * len1 * len2
    if abs(determinant) <= max(parallel_limit, _EPSILON):
        result["reason"] = "parallel_handle_lines"
        return result

    delta = _sub(p3, p0)
    start_parameter = _cross(delta, v2) / determinant
    end_parameter = _cross(delta, v1) / determinant
    tunni_point = _add(p0, _scale(v1, start_parameter))
    if not _finite_point(tunni_point) or not math.isfinite(start_parameter) or not math.isfinite(end_parameter):
        result["reason"] = "nonfinite_intersection"
        return result
    result["tunniPoint"] = _point_payload(tunni_point)
    result["lineParameters"] = {"start": float(start_parameter), "end": float(end_parameter)}
    if start_parameter <= 0.0 or end_parameter <= 0.0:
        result["reason"] = "intersection_behind_endpoint"
        return result

    start_distance = _length(_sub(tunni_point, p0))
    end_distance = _length(_sub(tunni_point, p3))
    max_distance = upm_value * 8.0
    result["intersectionDistances"] = {"start": float(start_distance), "end": float(end_distance)}
    if start_distance > max_distance or end_distance > max_distance:
        result["reason"] = "intersection_too_distant"
        return result
    if start_distance <= _EPSILON or end_distance <= _EPSILON:
        result["reason"] = "intersection_at_endpoint"
        return result

    start_ratio = len1 / start_distance
    end_ratio = len2 / end_distance
    result["ratios"] = {"start": float(start_ratio), "end": float(end_ratio)}
    if not (_MIN_RATIO <= start_ratio <= _MAX_RATIO and _MIN_RATIO <= end_ratio <= _MAX_RATIO):
        result["reason"] = "ratio_out_of_bounds"
        return result

    imbalance = abs(start_ratio - end_ratio) / max(abs(start_ratio), abs(end_ratio), _EPSILON)
    target_ratio = (start_ratio + end_ratio) / 2.0
    proposed1 = _add(p0, _scale(_sub(tunni_point, p0), target_ratio))
    proposed2 = _add(p3, _scale(_sub(tunni_point, p3), target_ratio))
    delta1 = _sub(proposed1, p1)
    delta2 = _sub(proposed2, p2)
    result["relativeImbalance"] = float(imbalance)
    result["targetRatio"] = float(target_ratio)
    result["before"] = {
        "handle1": _point_payload(p1),
        "handle2": _point_payload(p2),
    }
    result["idealProposed"] = {
        "handle1": _point_payload(proposed1),
        "handle2": _point_payload(proposed2),
        "deltas": {
            "handle1": _point_payload(delta1),
            "handle2": _point_payload(delta2),
        },
    }
    max_move = upm_value * 0.25
    result["movement"] = {"handle1": _length(delta1), "handle2": _length(delta2)}
    if max(_length(delta1), _length(delta2)) > max_move:
        result["reason"] = "proposed_movement_too_large"
        return result
    if imbalance < imbalance_value:
        result["reason"] = "below_imbalance_threshold"
        return result

    if grid_value is None:
        result["proposed"] = dict(result["idealProposed"])
        result["grid"] = {"policy": "continuous", "onGrid": None}
    else:
        candidate = _best_grid_tunni_candidate(
            p0,
            p1,
            p2,
            p3,
            proposed1,
            proposed2,
            upm=upm_value,
            grid_step=grid_value,
            imbalance_threshold=imbalance_value,
            min_handle_length=minimum_handle_value,
            max_tangent_deviation_deg=float(angle_limit),
        )
        if candidate is None:
            result["grid"] = {
                "policy": "font",
                "step": float(grid_value),
                "onGrid": False,
                "maxTangentDeviationDeg": float(angle_limit),
            }
            result["reason"] = "no_safe_grid_candidate"
            return result
        grid1 = candidate["handle1"]
        grid2 = candidate["handle2"]
        grid_delta1 = _sub(grid1, p1)
        grid_delta2 = _sub(grid2, p2)
        ideal_adjust1 = _sub(grid1, proposed1)
        ideal_adjust2 = _sub(grid2, proposed2)
        post_ratios = candidate["metrics"]["ratios"]
        result["proposed"] = {
            "handle1": _grid_point_payload(grid1, grid_value),
            "handle2": _grid_point_payload(grid2, grid_value),
            "deltas": {
                "handle1": _grid_point_payload(grid_delta1, grid_value),
                "handle2": _grid_point_payload(grid_delta2, grid_value),
            },
        }
        result["movement"] = {
            "handle1": _length(grid_delta1),
            "handle2": _length(grid_delta2),
        }
        result["grid"] = {
            "policy": "font",
            "step": float(grid_value),
            "onGrid": True,
            "adjustmentFromIdeal": {
                "handle1": _point_payload(ideal_adjust1),
                "handle2": _point_payload(ideal_adjust2),
            },
            "postRatios": {
                "start": float(post_ratios[0]),
                "end": float(post_ratios[1]),
            },
            "postRelativeImbalance": float(candidate["metrics"]["relativeImbalance"]),
            "tangentDeviationDeg": candidate["tangentDeviationDeg"],
            "maxTangentDeviationDeg": float(angle_limit),
        }

    result["eligible"] = True
    result["reason"] = None
    return result


def analyze_tunni_path(
    nodes: Sequence[Any],
    *,
    closed: bool,
    upm: float,
    segment_end_node_indices: Optional[Sequence[int]] = None,
    imbalance_threshold: float = 0.05,
    min_handle_length: float = 1.0,
    grid_step: Optional[float] = None,
    max_grid_tangent_deviation_deg: float = DEFAULT_MAX_GRID_TANGENT_DEVIATION_DEG,
) -> List[Dict[str, Any]]:
    if segment_end_node_indices is None:
        requested_indices: List[Any] = cubic_segment_end_indices(nodes, closed=bool(closed))
    else:
        requested_indices = list(segment_end_node_indices)
    resolved_indices = [(raw_index, _segment_index_value(raw_index)) for raw_index in requested_indices]
    validated, parameter_reason = _validated_tunni_parameters(upm, imbalance_threshold, min_handle_length)
    if parameter_reason:
        if not resolved_indices:
            return [_rejected_segment(None, parameter_reason)]
        return [
            _rejected_segment(
                resolved_index,
                "invalid_segment_index" if resolved_index is None else parameter_reason,
            )
            for _raw_index, resolved_index in resolved_indices
        ]
    assert validated is not None
    upm_value, imbalance_value, minimum_handle_value = validated
    results: List[Dict[str, Any]] = []
    for _raw_index, resolved_index in resolved_indices:
        if resolved_index is None:
            results.append(_rejected_segment(None, "invalid_segment_index"))
            continue
        results.append(
            analyze_tunni_segment(
                nodes,
                resolved_index,
                closed=bool(closed),
                upm=upm_value,
                imbalance_threshold=imbalance_value,
                min_handle_length=minimum_handle_value,
                grid_step=grid_step,
                max_grid_tangent_deviation_deg=max_grid_tangent_deviation_deg,
            )
        )
    return results


def cubic_sample(points: Sequence[Point], t: float) -> Dict[str, Any]:
    """Return point, derivatives, and signed curvature at ``t``."""

    p0, p1, p2, p3 = points
    t = max(0.0, min(1.0, float(t)))
    u = 1.0 - t
    point = (
        u * u * u * p0[0] + 3.0 * u * u * t * p1[0] + 3.0 * u * t * t * p2[0] + t * t * t * p3[0],
        u * u * u * p0[1] + 3.0 * u * u * t * p1[1] + 3.0 * u * t * t * p2[1] + t * t * t * p3[1],
    )
    derivative = (
        3.0 * (u * u * (p1[0] - p0[0]) + 2.0 * u * t * (p2[0] - p1[0]) + t * t * (p3[0] - p2[0])),
        3.0 * (u * u * (p1[1] - p0[1]) + 2.0 * u * t * (p2[1] - p1[1]) + t * t * (p3[1] - p2[1])),
    )
    second_derivative = (
        6.0 * (u * (p2[0] - 2.0 * p1[0] + p0[0]) + t * (p3[0] - 2.0 * p2[0] + p1[0])),
        6.0 * (u * (p2[1] - 2.0 * p1[1] + p0[1]) + t * (p3[1] - 2.0 * p2[1] + p1[1])),
    )
    speed = _length(derivative)
    if speed <= _EPSILON:
        curvature = None
    else:
        curvature = _cross(derivative, second_derivative) / (speed * speed * speed)
        if not math.isfinite(curvature):
            curvature = None
    return {
        "t": float(t),
        "point": point,
        "derivative": derivative,
        "secondDerivative": second_derivative,
        "speed": float(speed),
        "curvature": curvature,
    }


def curvature_comb_samples(points: Sequence[Point], *, sample_count: int = DEFAULT_SAMPLES_PER_CURVE) -> List[Dict[str, Any]]:
    count = clamp_samples_per_curve(sample_count)
    return [cubic_sample(points, index / float(count - 1)) for index in range(count)]


def _quadratic_roots(a: float, b: float, c: float) -> List[float]:
    scale = max(abs(a), abs(b), abs(c), 1.0)
    epsilon = _EPSILON * scale
    if abs(a) <= epsilon:
        if abs(b) <= epsilon:
            return []
        return [-c / b]
    discriminant = b * b - 4.0 * a * c
    if discriminant < -epsilon:
        return []
    if abs(discriminant) <= epsilon:
        return [-b / (2.0 * a)]
    root = math.sqrt(max(0.0, discriminant))
    q = -0.5 * (b + math.copysign(root, b))
    if abs(q) <= epsilon:
        return [-b / (2.0 * a)]
    return [q / a, c / q]


def _unit_roots(values: Iterable[float], *, include_endpoints: bool = False) -> List[float]:
    result: List[float] = []
    lower = -1.0e-10 if include_endpoints else 1.0e-10
    upper = 1.0 + 1.0e-10 if include_endpoints else 1.0 - 1.0e-10
    for value in sorted(float(item) for item in values if math.isfinite(float(item))):
        if value < lower or value > upper:
            continue
        value = max(0.0, min(1.0, value))
        if not result or abs(value - result[-1]) > 1.0e-8:
            result.append(value)
    return result


def _cubic_coefficients(points: Sequence[Point]) -> Tuple[Point, Point, Point, Point]:
    p0, p1, p2, p3 = points
    a = (
        -p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0],
        -p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1],
    )
    b = (
        3.0 * p0[0] - 6.0 * p1[0] + 3.0 * p2[0],
        3.0 * p0[1] - 6.0 * p1[1] + 3.0 * p2[1],
    )
    c = (3.0 * (p1[0] - p0[0]), 3.0 * (p1[1] - p0[1]))
    return a, b, c, p0


def _event_point(points: Sequence[Point], t: float, **extra: Any) -> Dict[str, Any]:
    sample = cubic_sample(points, t)
    payload: Dict[str, Any] = {
        "t": float(t),
        "point": _point_payload(sample["point"]),
    }
    payload.update(extra)
    return payload


def _adaptive_integral(function, start: float, end: float, tolerance: float, max_depth: int) -> float:
    def simpson(a: float, b: float, fa: float, fm: float, fb: float) -> float:
        return (b - a) * (fa + 4.0 * fm + fb) / 6.0

    a = float(start)
    b = float(end)
    middle = (a + b) / 2.0
    fa = float(function(a))
    fm = float(function(middle))
    fb = float(function(b))
    whole = simpson(a, b, fa, fm, fb)

    def recurse(left, right, f_left, f_middle, f_right, estimate, allowed, depth):
        center = (left + right) / 2.0
        left_middle = (left + center) / 2.0
        right_middle = (center + right) / 2.0
        f_left_middle = float(function(left_middle))
        f_right_middle = float(function(right_middle))
        left_estimate = simpson(left, center, f_left, f_left_middle, f_middle)
        right_estimate = simpson(center, right, f_middle, f_right_middle, f_right)
        delta = left_estimate + right_estimate - estimate
        if depth <= 0 or abs(delta) <= 15.0 * allowed:
            return left_estimate + right_estimate + delta / 15.0
        return recurse(
            left, center, f_left, f_left_middle, f_middle, left_estimate, allowed / 2.0, depth - 1
        ) + recurse(
            center, right, f_middle, f_right_middle, f_right, right_estimate, allowed / 2.0, depth - 1
        )

    return float(recurse(a, b, fa, fm, fb, whole, max(float(tolerance), 1.0e-12), int(max_depth)))


def cubic_arc_length(points: Sequence[Point], *, tolerance: float = 1.0e-7) -> float:
    control_length = sum(_length(_sub(points[index + 1], points[index])) for index in range(3))
    absolute_tolerance = max(float(tolerance) * max(control_length, 1.0), 1.0e-10)
    return _adaptive_integral(
        lambda t: cubic_sample(points, t)["speed"],
        0.0,
        1.0,
        absolute_tolerance,
        MAX_ADAPTIVE_RECURSION,
    )


def _arc_length_parameters(points: Sequence[Point], sample_count: int) -> List[float]:
    count = clamp_samples_per_curve(sample_count)
    dense_count = min(2049, max(129, (count - 1) * 8 + 1))
    dense_t = [index / float(dense_count - 1) for index in range(dense_count)]
    dense_points = [cubic_sample(points, t)["point"] for t in dense_t]
    cumulative = [0.0]
    for index in range(1, dense_count):
        cumulative.append(cumulative[-1] + _length(_sub(dense_points[index], dense_points[index - 1])))
    total = cumulative[-1]
    if total <= _EPSILON:
        return [index / float(count - 1) for index in range(count)]
    result = [0.0]
    cursor = 1
    for index in range(1, count - 1):
        wanted = total * index / float(count - 1)
        while cursor < len(cumulative) - 1 and cumulative[cursor] < wanted:
            cursor += 1
        before = cumulative[cursor - 1]
        after = cumulative[cursor]
        fraction = 0.0 if after <= before else (wanted - before) / (after - before)
        result.append(dense_t[cursor - 1] + fraction * (dense_t[cursor] - dense_t[cursor - 1]))
    result.append(1.0)
    return result


def _distance_to_line(point: Point, start: Point, end: Point) -> float:
    chord = _sub(end, start)
    length = _length(chord)
    if length <= _EPSILON:
        return _length(_sub(point, start))
    return abs(_cross(_sub(point, start), chord)) / length


def _split_cubic(points: Sequence[Point]) -> Tuple[Tuple[Point, ...], Tuple[Point, ...]]:
    p0, p1, p2, p3 = points
    p01 = _scale(_add(p0, p1), 0.5)
    p12 = _scale(_add(p1, p2), 0.5)
    p23 = _scale(_add(p2, p3), 0.5)
    p012 = _scale(_add(p01, p12), 0.5)
    p123 = _scale(_add(p12, p23), 0.5)
    middle = _scale(_add(p012, p123), 0.5)
    return (p0, p01, p012, middle), (middle, p123, p23, p3)


def _flatten_cubic(points: Sequence[Point], tolerance: float) -> List[Tuple[float, Point]]:
    output: List[Tuple[float, Point]] = [(0.0, points[0])]

    def recurse(segment: Sequence[Point], t0: float, t1: float, depth: int) -> None:
        flatness = max(
            _distance_to_line(segment[1], segment[0], segment[3]),
            _distance_to_line(segment[2], segment[0], segment[3]),
        )
        if depth <= 0 or flatness <= tolerance or len(output) >= 2048:
            output.append((t1, segment[3]))
            return
        left, right = _split_cubic(segment)
        middle = (t0 + t1) / 2.0
        recurse(left, t0, middle, depth - 1)
        recurse(right, middle, t1, depth - 1)

    recurse(points, 0.0, 1.0, 12)
    return output


def _line_intersection(a0: Point, a1: Point, b0: Point, b1: Point) -> Optional[Tuple[float, float, Point]]:
    r = _sub(a1, a0)
    s = _sub(b1, b0)
    determinant = _cross(r, s)
    if abs(determinant) <= 1.0e-12 * max(_length(r) * _length(s), 1.0):
        return None
    delta = _sub(b0, a0)
    u = _cross(delta, r) / determinant
    t = _cross(delta, s) / determinant
    if not (0.0 <= t <= 1.0 and 0.0 <= u <= 1.0):
        return None
    return t, u, _add(a0, _scale(r, t))


def _self_intersections(points: Sequence[Point], upm: float) -> List[Dict[str, Any]]:
    flattened = _flatten_cubic(points, max(float(upm) * 1.0e-5, 1.0e-6))
    found: List[Dict[str, Any]] = []
    segment_count = len(flattened) - 1
    for first in range(segment_count):
        for second in range(first + 2, segment_count):
            if first == 0 and second == segment_count - 1:
                continue
            intersection = _line_intersection(
                flattened[first][1], flattened[first + 1][1],
                flattened[second][1], flattened[second + 1][1],
            )
            if intersection is None:
                continue
            local_first, local_second, point = intersection
            t1 = flattened[first][0] + local_first * (flattened[first + 1][0] - flattened[first][0])
            t2 = flattened[second][0] + local_second * (flattened[second + 1][0] - flattened[second][0])
            if abs(t1 - t2) <= 1.0e-5:
                continue
            if any(abs(t1 - item["t1"]) < 1.0e-4 and abs(t2 - item["t2"]) < 1.0e-4 for item in found):
                continue
            found.append({"t1": float(t1), "t2": float(t2), "point": _point_payload(point)})
            if len(found) >= MAX_SELF_INTERSECTIONS:
                return found
    return found


def analyze_curve_events(points: Sequence[Point], *, upm: float) -> Dict[str, Any]:
    """Return bounded analytic/adaptive events for one finite cubic."""

    a, b, c, _d = _cubic_coefficients(points)
    extrema: List[Dict[str, Any]] = []
    for axis, coordinate in (("x", 0), ("y", 1)):
        roots = _unit_roots(_quadratic_roots(3.0 * a[coordinate], 2.0 * b[coordinate], c[coordinate]))
        extrema.extend(_event_point(points, t, axis=axis) for t in roots)
    derivative_a = _scale(a, 3.0)
    derivative_b = _scale(b, 2.0)
    inflection_roots = _quadratic_roots(
        -_cross(derivative_a, derivative_b),
        2.0 * _cross(c, derivative_a),
        _cross(c, derivative_b),
    )
    inflections = [_event_point(points, t) for t in _unit_roots(inflection_roots)]

    candidates = set(_quadratic_roots(3.0 * a[0], 2.0 * b[0], c[0]))
    candidates.update(_quadratic_roots(3.0 * a[1], 2.0 * b[1], c[1]))
    candidates.update((0.0, 1.0))
    control_length = sum(_length(_sub(points[index + 1], points[index])) for index in range(3))
    stationary_limit = max(control_length, 1.0) * 1.0e-9
    stationary = []
    cusps = []
    for t in _unit_roots(candidates, include_endpoints=True):
        sample = cubic_sample(points, t)
        if sample["speed"] > stationary_limit:
            continue
        event = _event_point(points, t)
        stationary.append(event)
        if _length(sample["secondDerivative"]) > stationary_limit:
            cusps.append(dict(event))

    length = cubic_arc_length(points)
    turn_tolerance = 1.0e-8
    signed_turn = _adaptive_integral(
        lambda t: (
            _cross(cubic_sample(points, t)["derivative"], cubic_sample(points, t)["secondDerivative"])
            / max(cubic_sample(points, t)["speed"] ** 2, _EPSILON)
        ),
        0.0,
        1.0,
        turn_tolerance,
        MAX_ADAPTIVE_RECURSION,
    )
    absolute_turn = _adaptive_integral(
        lambda t: abs(
            _cross(cubic_sample(points, t)["derivative"], cubic_sample(points, t)["secondDerivative"])
            / max(cubic_sample(points, t)["speed"] ** 2, _EPSILON)
        ),
        0.0,
        1.0,
        turn_tolerance,
        MAX_ADAPTIVE_RECURSION,
    )
    return {
        "extrema": sorted(extrema, key=lambda item: (item["t"], item["axis"])),
        "inflections": inflections,
        "stationaryPoints": stationary,
        "cusps": cusps,
        "selfIntersections": _self_intersections(points, upm),
        "arcLength": float(length),
        "normalizedArcLength": float(length / max(float(upm), _EPSILON)),
        "turningAngle": {
            "signedDegrees": float(math.degrees(signed_turn)),
            "absoluteDegrees": float(math.degrees(absolute_turn)),
        },
    }


def _spike_ratio(max_abs: float, median_abs: float) -> Tuple[Optional[float], bool]:
    if max_abs <= 0.0:
        return 0.0, False
    if median_abs <= 0.0:
        return None, True
    return float(max_abs / median_abs), False


def analyze_curve_segment(
    segment: Dict[str, Any],
    *,
    upm: float,
    samples_per_curve: int,
    spike_ratio_threshold: float,
    include_samples: bool,
    analysis_mode: str = "sampled_v1",
) -> Dict[str, Any]:
    if not segment.get("ok"):
        return dict(segment)

    upm_value = _finite_float(upm)
    if upm_value is None or upm_value <= 0.0:
        return _rejected_segment(
            segment.get("segmentEndNodeIndex"),
            "invalid_upm",
            node_indices=segment.get("nodeIndices"),
        )
    spike_threshold_value = _finite_float(spike_ratio_threshold)
    if spike_threshold_value is None or spike_threshold_value <= 0.0:
        return _rejected_segment(
            segment.get("segmentEndNodeIndex"),
            "invalid_spike_ratio_threshold",
            node_indices=segment.get("nodeIndices"),
        )

    if analysis_mode == "adaptive":
        sample_parameters = _arc_length_parameters(segment["points"], samples_per_curve)
        samples = [cubic_sample(segment["points"], t) for t in sample_parameters]
    else:
        samples = curvature_comb_samples(segment["points"], sample_count=samples_per_curve)
    valid = [float(sample["curvature"]) for sample in samples if sample.get("curvature") is not None]
    absolute = [abs(value) for value in valid]
    warnings: List[Dict[str, Any]] = []
    degenerate_t = [float(sample["t"]) for sample in samples if sample.get("curvature") is None]
    if degenerate_t:
        warnings.append({"code": "degenerate_tangent", "sampleCount": len(degenerate_t)})

    if absolute:
        min_abs = min(absolute)
        max_abs = max(absolute)
        median_abs = float(statistics.median(absolute))
        signed_min = min(valid)
        signed_max = max(valid)
    else:
        min_abs = max_abs = median_abs = 0.0
        signed_min = signed_max = 0.0
    spike_ratio, spike_ratio_infinite = _spike_ratio(max_abs, median_abs)

    sign_changes = 0
    last_sign = 0
    sign_epsilon = 1.0 / (upm_value * 1000000.0)
    for value in valid:
        sign = 1 if value > sign_epsilon else -1 if value < -sign_epsilon else 0
        if sign and last_sign and sign != last_sign:
            sign_changes += 1
        if sign:
            last_sign = sign
    if spike_ratio_infinite or (
        spike_ratio is not None and spike_ratio > spike_threshold_value and max_abs > 0.0
    ):
        warnings.append(
            {
                "code": "curvature_spike",
                "ratio": float(spike_ratio) if spike_ratio is not None else None,
                "ratioInfinite": bool(spike_ratio_infinite),
            }
        )

    payload: Dict[str, Any] = {
        "ok": True,
        "segmentEndNodeIndex": int(segment["segmentEndNodeIndex"]),
        "nodeIndices": dict(segment["nodeIndices"]),
        "sampleCount": len(samples),
        "sampling": "arc_length" if analysis_mode == "adaptive" else "uniform_parameter",
        "curvature": {
            "signedMin": float(signed_min),
            "signedMax": float(signed_max),
            "minAbs": float(min_abs),
            "maxAbs": float(max_abs),
            "medianAbs": float(median_abs),
            "normalizedMaxAbs": float(max_abs * upm_value),
            "spikeRatio": float(spike_ratio) if spike_ratio is not None else None,
            "spikeRatioInfinite": bool(spike_ratio_infinite),
        },
        "inflectionSignChanges": int(sign_changes),
        "degenerateTangents": degenerate_t,
        "endpointCurvature": {
            "start": samples[0].get("curvature"),
            "end": samples[-1].get("curvature"),
        },
        "warnings": warnings,
    }
    if analysis_mode == "adaptive":
        payload["events"] = analyze_curve_events(segment["points"], upm=upm_value)
    if include_samples:
        payload["samples"] = [
            {
                "t": float(sample["t"]),
                "x": float(sample["point"][0]),
                "y": float(sample["point"][1]),
                "curvature": sample.get("curvature"),
                "normalizedCurvature": (
                    float(sample["curvature"]) * upm_value if sample.get("curvature") is not None else None
                ),
            }
            for sample in samples
        ]
    return payload


def _path_segments(nodes: Sequence[Any], closed: bool) -> List[Dict[str, Any]]:
    count = len(nodes)
    oncurve = [index for index in range(count) if _node_type(nodes[index]) != "offcurve"]
    if len(oncurve) < 2:
        return []
    pairs: List[Tuple[int, int]] = []
    if closed:
        pairs = [(oncurve[index - 1], oncurve[index]) for index in range(len(oncurve))]
    else:
        pairs = [(oncurve[index - 1], oncurve[index]) for index in range(1, len(oncurve))]
    output: List[Dict[str, Any]] = []
    for start, end in pairs:
        between: List[int] = []
        cursor = (start + 1) % count
        while cursor != end:
            between.append(cursor)
            cursor = (cursor + 1) % count
            if len(between) > count:
                break
        if _node_type(nodes[end]) == "curve" and len(between) == 2 and all(
            _node_type(nodes[index]) == "offcurve" for index in between
        ):
            extracted = extract_cubic_segment(nodes, end, closed=closed)
            if extracted.get("ok"):
                output.append({
                    "kind": "curve",
                    "startNodeIndex": start,
                    "endNodeIndex": end,
                    "segmentEndNodeIndex": end,
                    "points": extracted["points"],
                })
        elif not between and _node_type(nodes[end]) != "offcurve":
            try:
                start_point = _node_point(nodes[start])
                end_point = _node_point(nodes[end])
            except (TypeError, ValueError, OverflowError):
                continue
            if _finite_point(start_point) and _finite_point(end_point):
                output.append({
                    "kind": "line",
                    "startNodeIndex": start,
                    "endNodeIndex": end,
                    "segmentEndNodeIndex": end,
                    "points": (start_point, end_point),
                })
    return output


def _segment_endpoint_metrics(segment: Dict[str, Any], at_end: bool) -> Tuple[Point, Optional[float]]:
    if segment["kind"] == "line":
        return _sub(segment["points"][1], segment["points"][0]), 0.0
    sample = cubic_sample(segment["points"], 1.0 if at_end else 0.0)
    return sample["derivative"], sample.get("curvature")


def _adaptive_joins(
    nodes: Sequence[Any],
    *,
    closed: bool,
    upm: float,
    selected: set,
    discontinuity_threshold: float,
) -> List[Dict[str, Any]]:
    segments = _path_segments(nodes, closed)
    by_start = {int(segment["startNodeIndex"]): segment for segment in segments}
    joins: List[Dict[str, Any]] = []
    for incoming in segments:
        join_index = int(incoming["endNodeIndex"])
        outgoing = by_start.get(join_index)
        if outgoing is None:
            continue
        incoming_end = int(incoming["segmentEndNodeIndex"])
        outgoing_end = int(outgoing["segmentEndNodeIndex"])
        if selected and incoming_end not in selected and outgoing_end not in selected:
            continue
        incoming_tangent, incoming_curvature = _segment_endpoint_metrics(incoming, True)
        outgoing_tangent, outgoing_curvature = _segment_endpoint_metrics(outgoing, False)
        tangent_angle = _angle_degrees(incoming_tangent, outgoing_tangent)
        degenerate = not math.isfinite(tangent_angle)
        declared_smooth = bool(_node_value(nodes[join_index], "smooth", False))
        geometrically_smooth = not degenerate and tangent_angle <= 1.0
        warnings: List[Dict[str, Any]] = []
        if degenerate:
            warnings.append({"code": "degenerate_join_tangent", "message": "A join tangent is degenerate."})
        if declared_smooth != geometrically_smooth:
            warnings.append({
                "code": "declared_geometric_smooth_mismatch",
                "message": "The declared smooth flag and measured tangent continuity disagree.",
            })
        relative = None
        if incoming_curvature is not None and outgoing_curvature is not None:
            relative = abs(float(incoming_curvature) - float(outgoing_curvature)) / max(
                abs(float(incoming_curvature)), abs(float(outgoing_curvature)), 1.0 / upm
            )
            if geometrically_smooth and relative > discontinuity_threshold:
                warnings.append({
                    "code": "curvature_discontinuity",
                    "message": "Endpoint curvature changes across a geometrically smooth join.",
                    "ratio": float(relative),
                })
        kind = "{}_{}".format(incoming["kind"], outgoing["kind"])
        payload: Dict[str, Any] = {
            "nodeIndex": join_index,
            "incomingSegmentEndNodeIndex": incoming_end,
            "outgoingSegmentEndNodeIndex": outgoing_end,
            "kind": kind,
            "declaredSmooth": declared_smooth,
            "geometricSmooth": geometrically_smooth,
            "g0Distance": 0.0,
            "g0Continuous": True,
            "g1AngleDegrees": None if degenerate else float(tangent_angle),
            "g1Continuous": geometrically_smooth,
            "incomingCurvature": incoming_curvature,
            "outgoingCurvature": outgoing_curvature,
            "relativeDiscontinuity": relative,
            "g2Continuous": bool(geometrically_smooth and relative is not None and relative <= discontinuity_threshold),
            "warnings": warnings,
            "warning": warnings[0] if warnings else None,
        }
        joins.append(payload)
    return joins


def analyze_curve_quality_path(
    nodes: Sequence[Any],
    *,
    closed: bool,
    upm: float,
    segment_end_node_indices: Optional[Sequence[int]] = None,
    samples_per_curve: int = DEFAULT_SAMPLES_PER_CURVE,
    discontinuity_threshold: float = 0.25,
    spike_ratio_threshold: float = 4.0,
    include_samples: bool = False,
    analysis_mode: str = "adaptive",
) -> Dict[str, Any]:
    if segment_end_node_indices is None:
        requested_indices: List[Any] = cubic_segment_end_indices(nodes, closed=bool(closed))
    else:
        requested_indices = list(segment_end_node_indices)
    resolved_indices = [(raw_index, _segment_index_value(raw_index)) for raw_index in requested_indices]
    sample_count = clamp_samples_per_curve(samples_per_curve)
    mode = str(analysis_mode or "adaptive").strip().lower()
    if mode not in {"adaptive", "sampled_v1"}:
        return _curve_quality_rejection("invalid_analysis_mode", sample_count, len(resolved_indices), mode)
    upm_value = _finite_float(upm)
    if upm_value is None or upm_value <= 0.0:
        return _curve_quality_rejection("invalid_upm", sample_count, len(resolved_indices))
    discontinuity_value = _finite_float(discontinuity_threshold)
    if discontinuity_value is None or discontinuity_value < 0.0:
        return _curve_quality_rejection("invalid_discontinuity_threshold", sample_count, len(resolved_indices))
    spike_threshold_value = _finite_float(spike_ratio_threshold)
    if spike_threshold_value is None or spike_threshold_value <= 0.0:
        return _curve_quality_rejection("invalid_spike_ratio_threshold", sample_count, len(resolved_indices))
    segments: List[Dict[str, Any]] = []
    for _raw_index, resolved_index in resolved_indices:
        if resolved_index is None:
            segments.append(_rejected_segment(None, "invalid_segment_index"))
            continue
        extracted = extract_cubic_segment(nodes, resolved_index, closed=bool(closed))
        segments.append(
            analyze_curve_segment(
                extracted,
                upm=upm_value,
                samples_per_curve=sample_count,
                spike_ratio_threshold=spike_threshold_value,
                include_samples=bool(include_samples),
                analysis_mode=mode,
            )
        )

    all_segments = {
        index: extract_cubic_segment(nodes, index, closed=bool(closed))
        for index in cubic_segment_end_indices(nodes, closed=bool(closed))
    }
    by_start = {
        int(segment["nodeIndices"]["start"]): segment
        for segment in all_segments.values()
        if segment.get("ok")
    }
    selected = {resolved_index for _raw_index, resolved_index in resolved_indices if resolved_index is not None}
    if mode == "adaptive":
        joins = _adaptive_joins(
            nodes,
            closed=bool(closed),
            upm=upm_value,
            selected=selected,
            discontinuity_threshold=discontinuity_value,
        )
    else:
        joins: List[Dict[str, Any]] = []
        for end_index, incoming in sorted(all_segments.items()):
            join_index = int(incoming["nodeIndices"]["end"])
            if not bool(_node_value(nodes[join_index], "smooth", False)):
                continue
            outgoing = by_start.get(join_index)
            if outgoing is None:
                continue
            outgoing_end = int(outgoing["segmentEndNodeIndex"])
            if end_index not in selected and outgoing_end not in selected:
                continue
            incoming_value = cubic_sample(incoming["points"], 1.0).get("curvature")
            outgoing_value = cubic_sample(outgoing["points"], 0.0).get("curvature")
            if incoming_value is None or outgoing_value is None:
                joins.append(
                    {
                        "nodeIndex": join_index,
                        "incomingSegmentEndNodeIndex": int(end_index),
                        "outgoingSegmentEndNodeIndex": outgoing_end,
                        "relativeDiscontinuity": None,
                        "warning": {"code": "degenerate_join_tangent"},
                    }
                )
                continue
            relative = abs(float(incoming_value) - float(outgoing_value)) / max(
                abs(float(incoming_value)), abs(float(outgoing_value)), 1.0 / upm_value
            )
            warning = None
            if relative > discontinuity_value:
                warning = {"code": "curvature_discontinuity", "ratio": float(relative)}
            joins.append(
                {
                    "nodeIndex": join_index,
                    "incomingSegmentEndNodeIndex": int(end_index),
                    "outgoingSegmentEndNodeIndex": outgoing_end,
                    "incomingCurvature": float(incoming_value),
                    "outgoingCurvature": float(outgoing_value),
                    "relativeDiscontinuity": float(relative),
                    "warning": warning,
                }
            )

    warning_count = sum(len(segment.get("warnings") or []) for segment in segments) + sum(
        1 for join in joins if join.get("warning")
    )
    return {
        "ok": True,
        "geometryDataVersion": CURVE_QUALITY_DATA_VERSION,
        "analysisMode": mode,
        "samplesPerCurve": sample_count,
        "segments": segments,
        "joins": joins,
        "summary": {
            "requestedSegmentCount": len(resolved_indices),
            "analyzedSegmentCount": sum(1 for segment in segments if segment.get("ok")),
            "joinCount": len(joins),
            "warningCount": int(warning_count),
        },
    }


def _curve_quality_rejection(
    reason: str,
    sample_count: int,
    requested_count: int,
    analysis_mode: str = "adaptive",
) -> Dict[str, Any]:
    return {
        "ok": False,
        "geometryDataVersion": CURVE_QUALITY_DATA_VERSION,
        "analysisMode": str(analysis_mode),
        "samplesPerCurve": int(sample_count),
        "segments": [],
        "joins": [],
        "reason": str(reason),
        "summary": {
            "requestedSegmentCount": int(requested_count),
            "analyzedSegmentCount": 0,
            "joinCount": 0,
            "warningCount": 0,
        },
    }


__all__ = [
    "CURVE_QUALITY_DATA_VERSION",
    "DEFAULT_SAMPLES_PER_CURVE",
    "GEOMETRY_DATA_VERSION",
    "MAX_SAMPLE_DETAIL_SEGMENTS",
    "analyze_curve_events",
    "analyze_curve_quality_path",
    "analyze_tunni_path",
    "analyze_tunni_segment",
    "clamp_samples_per_curve",
    "cubic_arc_length",
    "cubic_sample",
    "cubic_segment_end_indices",
    "curvature_comb_samples",
    "extract_cubic_segment",
]
