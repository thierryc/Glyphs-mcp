# encoding: utf-8

"""Deterministic, host-independent cyclic alignment for compatible paths."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


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


def _descriptor_payload(descriptor: Dict[str, Any]) -> Dict[str, Any]:
    def angle_value(value: Optional[float]) -> Optional[float]:
        return None if value is None else round(math.degrees(value), 6)

    position = descriptor["normalizedPosition"]
    return {
        "nodeType": descriptor["nodeType"],
        "cornerClass": descriptor["cornerClass"],
        "extrema": list(descriptor["extrema"]),
        "normalizedPosition": {"x": round(position[0], 9), "y": round(position[1], 9)},
        "neighboringSegments": {
            "incoming": descriptor["incomingSegment"],
            "outgoing": descriptor["outgoingSegment"],
        },
        "tangentDegrees": {
            "incoming": angle_value(descriptor["incomingTangent"]),
            "outgoing": angle_value(descriptor["outgoingTangent"]),
        },
        "normalizedCurvature": {
            "incoming": descriptor["incomingCurvature"],
            "outgoing": descriptor["outgoingCurvature"],
            "incomingClass": descriptor["incomingCurvatureClass"],
            "outgoingClass": descriptor["outgoingCurvatureClass"],
        },
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


def _error(code: str, message: str, **details: Any) -> Dict[str, Any]:
    result = {
        "ok": False,
        "alignmentDataVersion": ALIGNMENT_DATA_VERSION,
        "status": "manual_review_required",
        "error": message,
        "errorType": code,
    }
    if details:
        result["details"] = details
    return result


def _validated_paths(paths: Iterable[Dict[str, Any]]) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    values = list(paths or [])
    if not values:
        return None, _error("target_masters_required", "At least one target master is required.")
    if len(values) > MAX_MASTER_COUNT:
        return None, _error("master_limit_exceeded", "Target master count exceeds the bounded limit.")
    master_ids = [str(path.get("masterId") or "") for path in values]
    if any(not master_id for master_id in master_ids) or len(master_ids) != len(set(master_ids)):
        return None, _error("invalid_master_ids", "Target master IDs must be nonempty and unique.")
    for path in values:
        nodes = list(path.get("nodes") or [])
        if not bool(path.get("closed", False)):
            return None, _error(
                "open_path",
                "Start-node alignment never rotates open paths.",
                masterId=str(path.get("masterId") or ""),
            )
        if not nodes or len(nodes) > MAX_NODE_COUNT:
            return None, _error(
                "invalid_node_count",
                "Each target path must have a bounded nonzero node count.",
                masterId=str(path.get("masterId") or ""),
                nodeCount=len(nodes),
            )
        try:
            points = [_point(node) for node in nodes]
        except Exception:
            return None, _error("invalid_coordinate", "Every node coordinate must be numeric.")
        if any(not math.isfinite(value) for point in points for value in point):
            return None, _error("invalid_coordinate", "Every node coordinate must be finite.")
    return sorted(values, key=lambda item: str(item["masterId"])), None


def plan_joint_alignment(
    paths: Iterable[Dict[str, Any]],
    *,
    reference_master_id: str,
    reference_node_index: int,
) -> Dict[str, Any]:
    """Plan one joint cyclic phase for a corresponding closed-path set."""

    values, validation_error = _validated_paths(paths)
    if validation_error:
        return validation_error
    assert values is not None
    by_master = {str(path["masterId"]): path for path in values}
    reference = by_master.get(str(reference_master_id))
    if reference is None:
        return _error("reference_master_not_found", "The reference master is not in target_master_ids.")
    if isinstance(reference_node_index, bool) or not isinstance(reference_node_index, int):
        return _error("reference_node_invalid", "reference_node_index must be an integer.")
    reference_nodes = list(reference.get("nodes") or [])
    if reference_node_index < 0 or reference_node_index >= len(reference_nodes):
        return _error("reference_node_out_of_range", "The reference node index is out of range.")
    if not _is_oncurve(reference_nodes[reference_node_index]):
        return _error("reference_node_not_oncurve", "The reference node must be on-curve.")
    directions = {path.get("direction") for path in values if path.get("direction") is not None}
    if len(directions) > 1:
        return _error("contour_direction_mismatch", "Target contour directions do not match.")

    reference_types = tuple(_node_type(node) for node in reference_nodes)
    canonical_types = _rotate(reference_types, reference_node_index)
    try:
        reference_descriptor = semantic_descriptor(reference_nodes, reference_node_index)
    except ValueError as exc:
        return _error(str(exc), str(exc).replace("_", " ").capitalize() + ".")

    master_results = []
    blockers = []
    for path in values:
        master_id = str(path["masterId"])
        nodes = list(path.get("nodes") or [])
        types = tuple(_node_type(node) for node in nodes)
        if len(types) != len(canonical_types):
            blockers.append(
                {
                    "masterId": master_id,
                    "code": "path_topology_mismatch",
                    "field": "nodeCount",
                    "expected": len(canonical_types),
                    "actual": len(types),
                }
            )
            continue
        topology_candidates = [
            index
            for index in _cyclic_matches(types, canonical_types)
            if _is_oncurve(nodes[index])
        ]
        if not topology_candidates:
            blockers.append(
                {"masterId": master_id, "code": "path_topology_mismatch", "field": "cyclicNodeTypes"}
            )
            continue

        if master_id == str(reference_master_id):
            semantic_candidates = [reference_node_index]
            evidence = {reference_node_index: {"positionDistance": 0.0, "maxTangentDeviationDeg": 0.0, "conflicts": []}}
        else:
            semantic_candidates = []
            evidence = {}
            for candidate_index in topology_candidates:
                try:
                    descriptor = semantic_descriptor(nodes, candidate_index)
                    matches, match_evidence = _semantic_match(reference_descriptor, descriptor)
                except ValueError as exc:
                    matches = False
                    match_evidence = {"conflicts": [str(exc)]}
                evidence[candidate_index] = match_evidence
                if matches:
                    semantic_candidates.append(candidate_index)
        if not semantic_candidates:
            blockers.append(
                {
                    "masterId": master_id,
                    "code": "semantic_conflict",
                    "topologyCandidateCount": len(topology_candidates),
                    "candidates": [
                        {"nodeIndex": index, **evidence.get(index, {})}
                        for index in topology_candidates[:16]
                    ],
                }
            )
            continue
        if len(semantic_candidates) != 1:
            blockers.append(
                {
                    "masterId": master_id,
                    "code": "landmark_ambiguous",
                    "candidateNodeIndices": semantic_candidates[:16],
                    "candidateCount": len(semantic_candidates),
                }
            )
            continue
        selected_index = int(semantic_candidates[0])
        descriptor = semantic_descriptor(nodes, selected_index)
        master_results.append(
            {
                "masterId": master_id,
                "currentStartNodeIndex": 0,
                "proposedStartNodeIndex": selected_index,
                "rotationOffset": selected_index,
                "nodeCount": len(nodes),
                "topologyCandidateCount": len(topology_candidates),
                "semanticEvidence": evidence.get(selected_index, {}),
                "landmark": _descriptor_payload(descriptor),
            }
        )

    if blockers:
        code = str(blockers[0].get("code") or "alignment_blocked")
        return _error(
            code,
            "Joint start-node alignment requires manual review.",
            blockers=blockers[:MAX_MASTER_COUNT],
        )
    if len(master_results) != len(values):
        return _error("alignment_incomplete", "Not every target master produced one alignment result.")

    changed_count = sum(1 for item in master_results if item["rotationOffset"] != 0)
    return {
        "ok": True,
        "alignmentDataVersion": ALIGNMENT_DATA_VERSION,
        "status": "already_aligned" if changed_count == 0 else "ready",
        "reference": {
            "masterId": str(reference_master_id),
            "nodeIndex": int(reference_node_index),
            "landmark": _descriptor_payload(reference_descriptor),
        },
        "canonicalNodeTypes": list(canonical_types),
        "masters": master_results,
        "summary": {
            "masterCount": len(master_results),
            "rotationCount": changed_count,
            "unchangedCount": len(master_results) - changed_count,
        },
    }


__all__ = [
    "ALIGNMENT_DATA_VERSION",
    "MAX_MASTER_COUNT",
    "MAX_NODE_COUNT",
    "plan_joint_alignment",
    "semantic_descriptor",
]
