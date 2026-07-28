# encoding: utf-8
"""Pure geometry helpers for the clean-room balanced italic first pass.

The engine deliberately knows nothing about GlyphsApp.  Paths are dictionaries
with a ``closed`` flag and an ordered ``nodes`` list.  Each node contains
``x``, ``y``, ``type``, and ``smooth`` values.
"""

from __future__ import division, print_function, unicode_literals

import copy
import math


PARALLEL_TOLERANCE_DEGREES = 3.0
PERPENDICULAR_TOLERANCE_DEGREES = 12.0
MIN_OVERLAP_RATIO = 0.65
MIN_SEGMENT_UPM_RATIO = 0.04
MIN_SEPARATION_UPM_RATIO = 0.01
MAX_SEPARATION_UPM_RATIO = 0.25
MIN_STEM_RATIO = 0.5
MAX_STEM_RATIO = 1.75
MAX_DELTA_UPM_RATIO = 0.03
MAX_DELTA_WIDTH_RATIO = 0.25
CURSIVY_FALLBACK_STEM_STRENGTH = 0.35


def validate_unit_interval(value, name):
    """Return a finite float in [0, 1], or raise ValueError."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError("{} must be a number from 0 to 1".format(name))
    if not math.isfinite(result) or result < 0.0 or result > 1.0:
        raise ValueError("{} must be a number from 0 to 1".format(name))
    return result


def _node_type(value):
    return str(value or "").strip().lower()


def topology_signature(paths):
    """Return the topology fields that balanced interpolation must preserve."""
    signature = []
    for path in list(paths or []):
        nodes = []
        for node in list(path.get("nodes") or []):
            nodes.append((_node_type(node.get("type")), bool(node.get("smooth", False))))
        signature.append((bool(path.get("closed", True)), tuple(nodes)))
    return tuple(signature)


def topology_matches(left, right):
    return topology_signature(left) == topology_signature(right)


def interpolate_paths(raw_paths, cursivy_paths, strength):
    """Interpolate compatible Raw and Cursivy path coordinates."""
    amount = validate_unit_interval(strength, "curve_strength")
    if not topology_matches(raw_paths, cursivy_paths):
        raise ValueError("raw and cursivy path topology differs")
    result = copy.deepcopy(raw_paths)
    for path_index, path in enumerate(result):
        raw_nodes = raw_paths[path_index].get("nodes") or []
        cursivy_nodes = cursivy_paths[path_index].get("nodes") or []
        for node_index, node in enumerate(path.get("nodes") or []):
            raw_node = raw_nodes[node_index]
            cursivy_node = cursivy_nodes[node_index]
            node["x"] = float(raw_node["x"]) + amount * (
                float(cursivy_node["x"]) - float(raw_node["x"])
            )
            node["y"] = float(raw_node["y"]) + amount * (
                float(cursivy_node["y"]) - float(raw_node["y"])
            )
    return result


def shear_paths(paths, angle, pivot_y):
    """Return an affine right-leaning shear around ``pivot_y``."""
    tangent = math.tan(math.radians(float(angle)))
    result = copy.deepcopy(paths)
    for path in result:
        for node in list(path.get("nodes") or []):
            node["x"] = float(node["x"]) + tangent * (float(node["y"]) - float(pivot_y))
            node["y"] = float(node["y"])
    return result


def _sub(a, b):
    return (float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _add(a, b):
    return (float(a[0]) + float(b[0]), float(a[1]) + float(b[1]))


def _mul(a, scalar):
    return (float(a[0]) * float(scalar), float(a[1]) * float(scalar))


def _dot(a, b):
    return float(a[0]) * float(b[0]) + float(a[1]) * float(b[1])


def _length(vector):
    return math.hypot(float(vector[0]), float(vector[1]))


def _unit(vector):
    length = _length(vector)
    if length <= 1e-9:
        return None
    return (float(vector[0]) / length, float(vector[1]) / length)


def _midpoint(a, b):
    return ((float(a[0]) + float(b[0])) * 0.5, (float(a[1]) + float(b[1])) * 0.5)


def _point(node):
    return (float(node["x"]), float(node["y"]))


def _line_segments(paths, upm):
    segments = []
    minimum_length = float(upm) * MIN_SEGMENT_UPM_RATIO
    for path_index, path in enumerate(list(paths or [])):
        if not bool(path.get("closed", True)):
            continue
        nodes = list(path.get("nodes") or [])
        count = len(nodes)
        if count < 4:
            continue
        for end_index, end_node in enumerate(nodes):
            start_index = (end_index - 1) % count
            previous_index = (start_index - 1) % count
            next_index = (end_index + 1) % count
            if any(
                _node_type(nodes[index].get("type")) != "line"
                for index in (previous_index, start_index, end_index, next_index)
            ):
                continue
            start = _point(nodes[start_index])
            end = _point(end_node)
            vector = _sub(end, start)
            length = _length(vector)
            direction = _unit(vector)
            if direction is None or length < minimum_length:
                continue
            segments.append(
                {
                    "pathIndex": path_index,
                    "startIndex": start_index,
                    "endIndex": end_index,
                    "start": start,
                    "end": end,
                    "midpoint": _midpoint(start, end),
                    "direction": direction,
                    "length": length,
                }
            )
    return segments


def _projected_overlap(first, second):
    axis = first["direction"]
    first_values = sorted((_dot(first["start"], axis), _dot(first["end"], axis)))
    second_values = sorted((_dot(second["start"], axis), _dot(second["end"], axis)))
    overlap = max(0.0, min(first_values[1], second_values[1]) - max(first_values[0], second_values[0]))
    return overlap / max(1e-9, min(first["length"], second["length"]))


def _nearest_stem_ratio(separation, stem_values):
    values = [float(value) for value in list(stem_values or []) if float(value) > 0.0]
    if not values:
        return None
    nearest = min(values, key=lambda value: abs(value - separation))
    return separation / nearest


def detect_stem_pairs(paths, upm=1000.0, stem_values=None):
    """Detect conservative opposite straight sides of vertical/diagonal stems."""
    units_per_em = float(upm or 1000.0)
    segments = _line_segments(paths, units_per_em)
    candidates = []
    rejected = []
    parallel_cosine = math.cos(math.radians(PARALLEL_TOLERANCE_DEGREES))
    perpendicular_sine = math.sin(math.radians(PERPENDICULAR_TOLERANCE_DEGREES))
    min_separation = units_per_em * MIN_SEPARATION_UPM_RATIO
    max_separation = units_per_em * MAX_SEPARATION_UPM_RATIO

    for first_index, first in enumerate(segments):
        for second_index in range(first_index + 1, len(segments)):
            second = segments[second_index]
            if first["pathIndex"] != second["pathIndex"]:
                continue
            pair_id = "{}:{}-{}:{}".format(
                first["pathIndex"],
                first["startIndex"],
                second["pathIndex"],
                second["startIndex"],
            )
            direction_dot = _dot(first["direction"], second["direction"])
            if direction_dot > -parallel_cosine:
                continue
            connector = _sub(second["midpoint"], first["midpoint"])
            connector_unit = _unit(connector)
            if connector_unit is None:
                continue
            perpendicular_error = abs(_dot(connector_unit, first["direction"]))
            if perpendicular_error > perpendicular_sine:
                rejected.append({"pairId": pair_id, "reason": "connector_not_perpendicular"})
                continue
            overlap_ratio = _projected_overlap(first, second)
            if overlap_ratio < MIN_OVERLAP_RATIO:
                rejected.append({"pairId": pair_id, "reason": "insufficient_overlap"})
                continue
            normal = (-first["direction"][1], first["direction"][0])
            separation = abs(_dot(connector, normal))
            if separation < min_separation or separation > max_separation:
                rejected.append({"pairId": pair_id, "reason": "implausible_separation"})
                continue
            stem_ratio = _nearest_stem_ratio(separation, stem_values)
            if stem_ratio is not None and (stem_ratio < MIN_STEM_RATIO or stem_ratio > MAX_STEM_RATIO):
                rejected.append({"pairId": pair_id, "reason": "outside_master_stem_range"})
                continue
            confidence = (
                0.45 * min(1.0, overlap_ratio)
                + 0.30 * max(0.0, 1.0 - perpendicular_error / max(perpendicular_sine, 1e-9))
                + 0.25 * min(first["length"], second["length"]) / max(first["length"], second["length"])
            )
            candidates.append(
                {
                    "pairId": pair_id,
                    "first": first,
                    "second": second,
                    "sourceWidth": separation,
                    "overlapRatio": overlap_ratio,
                    "stemRatio": stem_ratio,
                    "confidence": confidence,
                }
            )

    accepted = []
    used_nodes = set()
    for candidate in sorted(candidates, key=lambda item: item["confidence"], reverse=True):
        nodes = {
            (candidate["first"]["pathIndex"], candidate["first"]["startIndex"]),
            (candidate["first"]["pathIndex"], candidate["first"]["endIndex"]),
            (candidate["second"]["pathIndex"], candidate["second"]["startIndex"]),
            (candidate["second"]["pathIndex"], candidate["second"]["endIndex"]),
        }
        if nodes & used_nodes:
            rejected.append({"pairId": candidate["pairId"], "reason": "node_conflict"})
            continue
        used_nodes.update(nodes)
        accepted.append(candidate)

    return {
        "detectedCount": len(candidates),
        "acceptedCount": len(accepted),
        "accepted": accepted,
        "skipped": rejected,
    }


def _candidate_segment(paths, segment):
    nodes = paths[segment["pathIndex"]].get("nodes") or []
    start = _point(nodes[segment["startIndex"]])
    end = _point(nodes[segment["endIndex"]])
    return {
        "start": start,
        "end": end,
        "midpoint": _midpoint(start, end),
        "direction": _unit(_sub(end, start)),
    }


def _move_node(paths, path_index, node_index, delta):
    node = paths[path_index]["nodes"][node_index]
    node["x"] = float(node["x"]) + float(delta[0])
    node["y"] = float(node["y"]) + float(delta[1])


def compensate_stems(source_paths, candidate_paths, strength=1.0, upm=1000.0, stem_values=None):
    """Conservatively restore straight-stem perpendicular widths."""
    amount = validate_unit_interval(strength, "stem_compensation")
    if not topology_matches(source_paths, candidate_paths):
        raise ValueError("source and candidate path topology differs")
    result = copy.deepcopy(candidate_paths)
    detection = detect_stem_pairs(source_paths, upm=upm, stem_values=stem_values)
    compensated = []
    skipped = list(detection["skipped"])
    maximum_upm_delta = float(upm or 1000.0) * MAX_DELTA_UPM_RATIO

    for pair in detection["accepted"]:
        first = _candidate_segment(result, pair["first"])
        second = _candidate_segment(result, pair["second"])
        if first["direction"] is None or second["direction"] is None:
            skipped.append({"pairId": pair["pairId"], "reason": "degenerate_candidate_segment"})
            continue
        direction = _unit(_sub(first["direction"], second["direction"]))
        if direction is None:
            skipped.append({"pairId": pair["pairId"], "reason": "candidate_not_opposed"})
            continue
        normal = (-direction[1], direction[0])
        midpoint_delta = _sub(second["midpoint"], first["midpoint"])
        if _dot(midpoint_delta, normal) < 0.0:
            normal = (-normal[0], -normal[1])
        candidate_width = abs(_dot(midpoint_delta, normal))
        source_width = float(pair["sourceWidth"])
        target_width = candidate_width + amount * (source_width - candidate_width)
        delta_width = target_width - candidate_width
        maximum_delta = min(maximum_upm_delta, source_width * MAX_DELTA_WIDTH_RATIO)
        if not math.isfinite(delta_width) or abs(delta_width) > maximum_delta:
            skipped.append(
                {
                    "pairId": pair["pairId"],
                    "reason": "unsafe_width_delta",
                    "delta": delta_width,
                    "limit": maximum_delta,
                }
            )
            continue
        first_delta = _mul(normal, -0.5 * delta_width)
        second_delta = _mul(normal, 0.5 * delta_width)
        for node_index in (pair["first"]["startIndex"], pair["first"]["endIndex"]):
            _move_node(result, pair["first"]["pathIndex"], node_index, first_delta)
        for node_index in (pair["second"]["startIndex"], pair["second"]["endIndex"]):
            _move_node(result, pair["second"]["pathIndex"], node_index, second_delta)
        compensated.append(
            {
                "pairId": pair["pairId"],
                "pathIndex": pair["first"]["pathIndex"],
                "sourceWidth": source_width,
                "beforeWidth": candidate_width,
                "targetWidth": target_width,
                "afterWidth": target_width,
                "delta": delta_width,
                "confidence": pair["confidence"],
            }
        )

    return {
        "paths": result,
        "diagnostics": {
            "detectedPairCount": detection["detectedCount"],
            "acceptedPairCount": detection["acceptedCount"],
            "compensatedPairCount": len(compensated),
            "compensatedPairs": compensated,
            "skippedPairs": skipped,
        },
    }


def measure_stem_widths(source_paths, candidate_paths, upm=1000.0, stem_values=None):
    """Measure candidate widths for the accepted source straight-stem pairs."""
    if not topology_matches(source_paths, candidate_paths):
        raise ValueError("source and candidate path topology differs")
    detection = detect_stem_pairs(source_paths, upm=upm, stem_values=stem_values)
    measurements = []
    for pair in detection["accepted"]:
        first = _candidate_segment(candidate_paths, pair["first"])
        second = _candidate_segment(candidate_paths, pair["second"])
        if first["direction"] is None or second["direction"] is None:
            continue
        direction = _unit(_sub(first["direction"], second["direction"]))
        if direction is None:
            continue
        normal = (-direction[1], direction[0])
        midpoint_delta = _sub(second["midpoint"], first["midpoint"])
        candidate_width = abs(_dot(midpoint_delta, normal))
        source_width = float(pair["sourceWidth"])
        measurements.append(
            {
                "pairId": pair["pairId"],
                "pathIndex": pair["first"]["pathIndex"],
                "sourceWidth": source_width,
                "candidateWidth": candidate_width,
                "absoluteError": abs(candidate_width - source_width),
                "confidence": pair["confidence"],
            }
        )
    return {
        "detectedPairCount": detection["detectedCount"],
        "acceptedPairCount": detection["acceptedCount"],
        "measurements": measurements,
        "skippedPairs": detection["skipped"],
    }
