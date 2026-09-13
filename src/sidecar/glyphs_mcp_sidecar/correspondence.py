"""External landmark matching, retained from the tested cyclic alignment policy.

Native Glyphs reorders nodes; this module supplies correspondence only.
"""

from __future__ import annotations

import math

from typing import Any, Dict, List, Optional, Sequence, Tuple

ALIGNMENT_DATA_VERSION = 1

MAX_MASTER_COUNT = 32

MAX_NODE_COUNT = 4096

EXTREMUM_TOLERANCE = 0.01

MAX_NORMALIZED_POSITION_DISTANCE = 0.25

MAX_TANGENT_DEVIATION_DEG = 45.0

CURVATURE_ZERO_TOLERANCE = 1.0e-6

_EPSILON = 1.0e-12

def _node_type(node: Dict[str, Any]) -> str:
    return str(node.get("type") or "").strip().lower()

def _is_oncurve(node: Dict[str, Any]) -> bool:
    return _node_type(node) != "offcurve"

def _point(node: Dict[str, Any]) -> Tuple[float, float]:
    return float(node.get("x")), float(node.get("y"))

def _sub(first: Tuple[float, float], second: Tuple[float, float]) -> Tuple[float, float]:
    return first[0] - second[0], first[1] - second[1]

def _cross(first: Tuple[float, float], second: Tuple[float, float]) -> float:
    return first[0] * second[1] - first[1] * second[0]

def _length(vector: Tuple[float, float]) -> float:
    return math.hypot(vector[0], vector[1])

def _angle(vector: Tuple[float, float]) -> Optional[float]:
    if _length(vector) <= _EPSILON:
        return None
    return math.atan2(vector[1], vector[0])

def _angle_difference_degrees(first: Optional[float], second: Optional[float]) -> Optional[float]:
    if first is None or second is None:
        return None if first is second else math.inf
    delta = (first - second + math.pi) % (2.0 * math.pi) - math.pi
    return abs(math.degrees(delta))

def _rotate(values: Sequence[Any], start: int) -> Tuple[Any, ...]:
    items = tuple(values)
    if not items:
        return tuple()
    index = int(start) % len(items)
    return items[index:] + items[:index]

def _kmp_prefix(pattern: Sequence[str]) -> List[int]:
    prefix = [0] * len(pattern)
    matched = 0
    for index in range(1, len(pattern)):
        while matched and pattern[index] != pattern[matched]:
            matched = prefix[matched - 1]
        if pattern[index] == pattern[matched]:
            matched += 1
            prefix[index] = matched
    return prefix

def _cyclic_matches(values: Sequence[str], pattern: Sequence[str]) -> List[int]:
    """Return every rotation whose complete sequence equals ``pattern`` in O(n)."""

    values_tuple = tuple(values)
    pattern_tuple = tuple(pattern)
    if len(values_tuple) != len(pattern_tuple) or not values_tuple:
        return []
    text = values_tuple + values_tuple[:-1]
    prefix = _kmp_prefix(pattern_tuple)
    matched = 0
    matches = []
    for text_index, value in enumerate(text):
        while matched and value != pattern_tuple[matched]:
            matched = prefix[matched - 1]
        if value == pattern_tuple[matched]:
            matched += 1
            if matched == len(pattern_tuple):
                start = text_index - len(pattern_tuple) + 1
                if start < len(values_tuple):
                    matches.append(start)
                matched = prefix[matched - 1]
    return matches

def _walk_between(count: int, start: int, end: int) -> List[int]:
    values = []
    index = (start + 1) % count
    while index != end:
        values.append(index)
        if len(values) >= count:
            return []
        index = (index + 1) % count
    return values

def _neighbor_oncurve(nodes: Sequence[Dict[str, Any]], node_index: int, step: int) -> Optional[int]:
    count = len(nodes)
    index = node_index
    for _ in range(count - 1):
        index = (index + step) % count
        if _is_oncurve(nodes[index]):
            return index
    return None

def _segment_kind(intermediate: Sequence[Dict[str, Any]], end_type: str) -> str:
    offcurves = [node for node in intermediate if _node_type(node) == "offcurve"]
    if not offcurves:
        return "line"
    if len(offcurves) == 2 and end_type == "curve":
        return "cubic"
    if end_type == "qcurve":
        return "quadratic"
    return "other"

def _endpoint_curvature(points: Sequence[Tuple[float, float]], at_end: bool) -> Optional[float]:
    if len(points) != 4:
        return 0.0
    p0, p1, p2, p3 = points
    if at_end:
        first = (3.0 * (p3[0] - p2[0]), 3.0 * (p3[1] - p2[1]))
        second = (
            6.0 * (p3[0] - 2.0 * p2[0] + p1[0]),
            6.0 * (p3[1] - 2.0 * p2[1] + p1[1]),
        )
    else:
        first = (3.0 * (p1[0] - p0[0]), 3.0 * (p1[1] - p0[1]))
        second = (
            6.0 * (p2[0] - 2.0 * p1[0] + p0[0]),
            6.0 * (p2[1] - 2.0 * p1[1] + p0[1]),
        )
    denominator = _length(first) ** 3
    if denominator <= _EPSILON:
        return None
    return _cross(first, second) / denominator

def _curvature_class(value: Optional[float]) -> str:
    if value is None:
        return "degenerate"
    if abs(float(value)) <= CURVATURE_ZERO_TOLERANCE:
        return "zero"
    return "positive" if value > 0.0 else "negative"

def _bounds(nodes: Sequence[Dict[str, Any]]) -> Tuple[float, float, float, float, float]:
    oncurves = [_point(node) for node in nodes if _is_oncurve(node)]
    if not oncurves:
        raise ValueError("path_has_no_oncurve_nodes")
    min_x = min(point[0] for point in oncurves)
    max_x = max(point[0] for point in oncurves)
    min_y = min(point[1] for point in oncurves)
    max_y = max(point[1] for point in oncurves)
    width = max_x - min_x
    height = max_y - min_y
    scale = math.hypot(width, height)
    if scale <= _EPSILON:
        raise ValueError("degenerate_path_bounds")
    return min_x, min_y, width, height, scale

def semantic_descriptor(nodes: Sequence[Dict[str, Any]], node_index: int) -> Dict[str, Any]:
    """Describe one on-curve landmark without depending on its raw path index."""

    count = len(nodes)
    if node_index < 0 or node_index >= count:
        raise ValueError("reference_node_out_of_range")
    node = nodes[node_index]
    if not _is_oncurve(node):
        raise ValueError("reference_node_not_oncurve")
    previous_index = _neighbor_oncurve(nodes, node_index, -1)
    next_index = _neighbor_oncurve(nodes, node_index, 1)
    if previous_index is None or next_index is None:
        raise ValueError("insufficient_oncurve_nodes")
    incoming_indices = _walk_between(count, previous_index, node_index)
    outgoing_indices = _walk_between(count, node_index, next_index)
    incoming_nodes = [nodes[index] for index in incoming_indices]
    outgoing_nodes = [nodes[index] for index in outgoing_indices]
    incoming_kind = _segment_kind(incoming_nodes, _node_type(node))
    outgoing_kind = _segment_kind(outgoing_nodes, _node_type(nodes[next_index]))

    point = _point(node)
    previous_point = _point(incoming_nodes[-1]) if incoming_nodes else _point(nodes[previous_index])
    next_point = _point(outgoing_nodes[0]) if outgoing_nodes else _point(nodes[next_index])
    incoming_tangent = _angle(_sub(point, previous_point))
    outgoing_tangent = _angle(_sub(next_point, point))

    incoming_points = [_point(nodes[previous_index])] + [_point(item) for item in incoming_nodes] + [point]
    outgoing_points = [point] + [_point(item) for item in outgoing_nodes] + [_point(nodes[next_index])]
    incoming_curvature = _endpoint_curvature(incoming_points, True) if incoming_kind == "cubic" else 0.0
    outgoing_curvature = _endpoint_curvature(outgoing_points, False) if outgoing_kind == "cubic" else 0.0

    min_x, min_y, width, height, scale = _bounds(nodes)
    normalized_x = 0.5 if width <= _EPSILON else (point[0] - min_x) / width
    normalized_y = 0.5 if height <= _EPSILON else (point[1] - min_y) / height
    extrema = []
    if width > _EPSILON:
        if normalized_x <= EXTREMUM_TOLERANCE:
            extrema.append("min_x")
        if normalized_x >= 1.0 - EXTREMUM_TOLERANCE:
            extrema.append("max_x")
    if height > _EPSILON:
        if normalized_y <= EXTREMUM_TOLERANCE:
            extrema.append("min_y")
        if normalized_y >= 1.0 - EXTREMUM_TOLERANCE:
            extrema.append("max_y")

    return {
        "nodeType": _node_type(node),
        "cornerClass": "smooth" if bool(node.get("smooth", False)) else "sharp",
        "extrema": tuple(extrema),
        "normalizedPosition": (float(normalized_x), float(normalized_y)),
        "incomingSegment": incoming_kind,
        "outgoingSegment": outgoing_kind,
        "incomingTangent": incoming_tangent,
        "outgoingTangent": outgoing_tangent,
        "incomingCurvature": None if incoming_curvature is None else float(incoming_curvature * scale),
        "outgoingCurvature": None if outgoing_curvature is None else float(outgoing_curvature * scale),
        "incomingCurvatureClass": _curvature_class(
            None if incoming_curvature is None else incoming_curvature * scale
        ),
        "outgoingCurvatureClass": _curvature_class(
            None if outgoing_curvature is None else outgoing_curvature * scale
        ),
    }

def _semantic_match(reference: Dict[str, Any], candidate: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    categorical_fields = (
        "nodeType",
        "cornerClass",
        "extrema",
        "incomingSegment",
        "outgoingSegment",
        "incomingCurvatureClass",
        "outgoingCurvatureClass",
    )
    conflicts = [field for field in categorical_fields if reference[field] != candidate[field]]
    reference_position = reference["normalizedPosition"]
    candidate_position = candidate["normalizedPosition"]
    position_distance = math.hypot(
        reference_position[0] - candidate_position[0],
        reference_position[1] - candidate_position[1],
    )
    incoming_tangent = _angle_difference_degrees(reference["incomingTangent"], candidate["incomingTangent"])
    outgoing_tangent = _angle_difference_degrees(reference["outgoingTangent"], candidate["outgoingTangent"])
    tangent_values = [value for value in (incoming_tangent, outgoing_tangent) if value is not None]
    max_tangent = max(tangent_values) if tangent_values else 0.0
    if position_distance > MAX_NORMALIZED_POSITION_DISTANCE:
        conflicts.append("normalizedPosition")
    if not math.isfinite(max_tangent) or max_tangent > MAX_TANGENT_DEVIATION_DEG:
        conflicts.append("tangent")
    return not conflicts, {
        "positionDistance": round(position_distance, 9),
        "maxTangentDeviationDeg": None if not math.isfinite(max_tangent) else round(max_tangent, 6),
        "conflicts": conflicts,
    }


def plan_joint_alignment(paths, *, reference_master_id, reference_node_index):
    """Match landmarks and retain the reference master's existing cyclic phase."""
    def error(code):
        return {"ok": False, "status": "manual_review_required", "errorType": code}
    values = sorted(list(paths), key=lambda p: str(p["masterId"]))
    ids = [str(p["masterId"]) for p in values]
    if not 1 <= len(values) <= MAX_MASTER_COUNT or len(set(ids)) != len(ids):
        return error("invalid_master_ids")
    if any(not p["closed"] for p in values):
        return error("open_path")
    if any(not 1 <= len(p["nodes"]) <= MAX_NODE_COUNT for p in values):
        return error("invalid_node_count")
    if any(not math.isfinite(float(n[k])) for p in values for n in p["nodes"] for k in ("x", "y")):
        return error("invalid_coordinate")
    reference = next((p for p in values if str(p["masterId"]) == reference_master_id), None)
    if reference is None:
        return error("reference_master_not_found")
    nodes = reference["nodes"]
    if isinstance(reference_node_index, bool) or not isinstance(reference_node_index, int) or not 0 <= reference_node_index < len(nodes):
        return error("reference_node_out_of_range")
    if not _is_oncurve(nodes[reference_node_index]):
        return error("reference_node_not_oncurve")
    if len({p["direction"] for p in values}) != 1:
        return error("contour_direction_mismatch")
    canonical = _rotate([_node_type(n) for n in nodes], reference_node_index)
    try:
        descriptor = semantic_descriptor(nodes, reference_node_index)
        masters = []
        for path in values:
            candidates = _cyclic_matches([_node_type(n) for n in path["nodes"]], canonical)
            if not candidates:
                return error("path_topology_mismatch")
            matching = ([reference_node_index] if path is reference else
                        [i for i in candidates if _is_oncurve(path["nodes"][i]) and
                         _semantic_match(descriptor, semantic_descriptor(path["nodes"], i))[0]])
            if len(matching) != 1:
                return error("landmark_ambiguous" if matching else "semantic_conflict")
            index = matching[0]
            shift = (index - reference_node_index) % len(nodes)
            masters.append({"masterId": str(path["masterId"]), "proposedStartNodeIndex": index,
                            "rotationOffset": shift, "nodeCount": len(nodes)})
    except ValueError as exc:
        return error(str(exc))
    count = sum(m["rotationOffset"] != 0 for m in masters)
    return {"ok": True, "status": "ready" if count else "already_aligned", "masters": masters,
            "canonicalNodeTypes": list(canonical), "summary": {"rotationCount": count}}
