# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Bounded, Glyphs-independent measurements for candidate display geometry."""

import math


CANDIDATE_DIFFERENCE_DATA_VERSION = 1
DEFAULT_SAMPLES_PER_CURVE = 33
MIN_SAMPLES_PER_CURVE = 9
MAX_SAMPLES_PER_CURVE = 257
DEFAULT_MAX_SAMPLES = 100000


def _sample_count(value):
    if type(value) is not int:
        raise ValueError("samples_per_curve must be an integer")
    value = max(MIN_SAMPLES_PER_CURVE, min(MAX_SAMPLES_PER_CURVE, value))
    if value % 2 == 0:
        value = value + 1 if value < MAX_SAMPLES_PER_CURVE else value - 1
    return value


def _point(node):
    x = float(node.get("x", 0.0))
    y = float(node.get("y", 0.0))
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("nonfinite_coordinate")
    return (x, y)


def _topology_matches(source, candidate):
    source_nodes = list(source.get("nodes") or [])
    candidate_nodes = list(candidate.get("nodes") or [])
    return (
        bool(source.get("closed")) == bool(candidate.get("closed"))
        and len(source_nodes) == len(candidate_nodes)
        and [node.get("type") for node in source_nodes]
        == [node.get("type") for node in candidate_nodes]
    )


def _geometry_matches(source, candidate):
    if not _topology_matches(source, candidate):
        return False
    return all(
        _point(before) == _point(after)
        for before, after in zip(source.get("nodes") or [], candidate.get("nodes") or [])
    )


def _segments(path):
    nodes = list(path.get("nodes") or [])
    oncurves = [index for index, node in enumerate(nodes) if node.get("type") != "offcurve"]
    if not oncurves:
        return []
    start_index = oncurves[0]
    start = nodes[start_index]
    if bool(path.get("closed")):
        sequence = [nodes[(start_index + offset) % len(nodes)] for offset in range(1, len(nodes) + 1)]
    else:
        sequence = nodes[start_index + 1 :]
    result = []
    handles = []
    current = start
    for node in sequence:
        if node.get("type") == "offcurve":
            handles.append(node)
            continue
        if node.get("type") == "curve" and len(handles) >= 2:
            result.append(("cubic", (_point(current), _point(handles[-2]), _point(handles[-1]), _point(node))))
        else:
            result.append(("line", (_point(current), _point(node))))
        handles = []
        current = node
    return result


def _interpolate_line(points, t):
    start, end = points
    return (
        start[0] + (end[0] - start[0]) * t,
        start[1] + (end[1] - start[1]) * t,
    )


def _interpolate_cubic(points, t):
    p0, p1, p2, p3 = points
    mt = 1.0 - t
    a = mt * mt * mt
    b = 3.0 * mt * mt * t
    c = 3.0 * mt * t * t
    d = t * t * t
    return (
        a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
        a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
    )


def _distance(first, second):
    return math.hypot(second[0] - first[0], second[1] - first[1])


def analyze_difference(
    source_paths,
    candidate_paths,
    samples_per_curve=DEFAULT_SAMPLES_PER_CURVE,
    max_samples=DEFAULT_MAX_SAMPLES,
):
    """Measure a bounded, parameter-aligned source/candidate outline delta.

    The measurement is informational for the Reporter label. It is not used
    for candidate eligibility, review, acceptance, or mutation.
    """

    count = _sample_count(samples_per_curve)
    if type(max_samples) is not int or max_samples < 1:
        raise ValueError("max_samples must be a positive integer")
    source_paths = list(source_paths or [])
    candidate_paths = list(candidate_paths or [])
    path_count = max(len(source_paths), len(candidate_paths))
    changed_path_count = 0
    node_count = 0
    maximum_node = 0.0
    maximum_outline = 0.0
    topology_compatible = len(source_paths) == len(candidate_paths)
    sampled = 0
    truncated = False

    for path_index in range(path_count):
        if path_index >= len(source_paths) or path_index >= len(candidate_paths):
            changed_path_count += 1
            topology_compatible = False
            continue
        source = source_paths[path_index]
        candidate = candidate_paths[path_index]
        if _geometry_matches(source, candidate):
            node_count += len(source.get("nodes") or [])
            continue
        changed_path_count += 1
        if not _topology_matches(source, candidate):
            topology_compatible = False
            continue
        for before, after in zip(source.get("nodes") or [], candidate.get("nodes") or []):
            maximum_node = max(maximum_node, _distance(_point(before), _point(after)))
            node_count += 1
        source_segments = _segments(source)
        candidate_segments = _segments(candidate)
        if (
            len(source_segments) != len(candidate_segments)
            or [item[0] for item in source_segments] != [item[0] for item in candidate_segments]
        ):
            topology_compatible = False
            continue
        for source_segment, candidate_segment in zip(source_segments, candidate_segments):
            segment_type = source_segment[0]
            segment_samples = count if segment_type == "cubic" else 3
            interpolate = _interpolate_cubic if segment_type == "cubic" else _interpolate_line
            for sample_index in range(segment_samples):
                if sampled >= max_samples:
                    truncated = True
                    break
                t = sample_index / float(max(1, segment_samples - 1))
                maximum_outline = max(
                    maximum_outline,
                    _distance(
                        interpolate(source_segment[1], t),
                        interpolate(candidate_segment[1], t),
                    ),
                )
                sampled += 1
            if truncated:
                break
        if truncated:
            break

    geometry_difference = bool(changed_path_count)
    return {
        "candidateDifferenceDataVersion": CANDIDATE_DIFFERENCE_DATA_VERSION,
        "geometryDifferencePresent": geometry_difference,
        "topologyCompatible": bool(topology_compatible),
        "changedPathCount": int(changed_path_count),
        "comparedNodeCount": int(node_count),
        "maxNodeMovement": float(maximum_node) if topology_compatible else None,
        "maxOutlineDisplacement": float(maximum_outline) if topology_compatible else None,
        "samplesPerCurve": int(count),
        "sampleCount": int(sampled),
        "samplingTruncated": bool(truncated),
    }


__all__ = [
    "CANDIDATE_DIFFERENCE_DATA_VERSION",
    "DEFAULT_MAX_SAMPLES",
    "DEFAULT_SAMPLES_PER_CURVE",
    "analyze_difference",
]
