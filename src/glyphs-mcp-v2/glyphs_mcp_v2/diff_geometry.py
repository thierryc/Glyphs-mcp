"""Pure topology-compatible outline bands for the live change Reporter."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


Point = tuple[float, float]


class DifferenceTopologyError(ValueError):
    """Raised when old and live paths cannot be paired without guessing."""


@dataclass(frozen=True)
class PathSegment:
    kind: str
    points: tuple[Point, ...]


@dataclass(frozen=True)
class DifferenceBand:
    closed: bool
    baseline_segments: tuple[PathSegment, ...]
    current_segments: tuple[PathSegment, ...]


def _point(node: Mapping[str, Any]) -> Point:
    point = (float(node.get("x", 0.0)), float(node.get("y", 0.0)))
    if not all(math.isfinite(value) for value in point):
        raise ValueError("difference geometry contains a non-finite coordinate")
    return point


def _topology_matches(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    first_nodes = list(first.get("nodes") or [])
    second_nodes = list(second.get("nodes") or [])
    return (
        bool(first.get("closed")) == bool(second.get("closed"))
        and len(first_nodes) == len(second_nodes)
        and [str(node.get("type") or "line") for node in first_nodes]
        == [str(node.get("type") or "line") for node in second_nodes]
    )


def _geometry_matches(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    return _topology_matches(first, second) and all(
        _point(before) == _point(after)
        for before, after in zip(first.get("nodes") or [], second.get("nodes") or [])
    )


def path_segments(path: Mapping[str, Any]) -> tuple[PathSegment, ...]:
    """Return the exact drawable segments for one canonical path."""

    nodes = list(path.get("nodes") or [])
    oncurves = [
        index
        for index, node in enumerate(nodes)
        if str(node.get("type") or "line") != "offcurve"
    ]
    if not oncurves:
        return ()
    start_index = oncurves[0]
    current = nodes[start_index]
    sequence = (
        [nodes[(start_index + offset) % len(nodes)] for offset in range(1, len(nodes) + 1)]
        if bool(path.get("closed"))
        else nodes[start_index + 1 :]
    )
    result: list[PathSegment] = []
    handles: list[Mapping[str, Any]] = []
    for node in sequence:
        node_type = str(node.get("type") or "line")
        if node_type == "offcurve":
            handles.append(node)
            continue
        if node_type == "curve" and len(handles) >= 2:
            points = (
                _point(current),
                _point(handles[-2]),
                _point(handles[-1]),
                _point(node),
            )
            result.append(PathSegment("cubic", points))
        else:
            result.append(PathSegment("line", (_point(current), _point(node))))
        current = node
        handles = []
    return tuple(result)


def difference_bands(
    baseline_paths: Sequence[Mapping[str, Any]],
    current_paths: Sequence[Mapping[str, Any]],
) -> tuple[DifferenceBand, ...]:
    """Return exact corresponding-outline bands, skipping unchanged paths."""

    baseline = list(baseline_paths or [])
    current = list(current_paths or [])
    if len(baseline) != len(current):
        raise DifferenceTopologyError("outline path counts differ")
    result: list[DifferenceBand] = []
    for before_path, live_path in zip(baseline, current):
        if _geometry_matches(before_path, live_path):
            continue
        if not _topology_matches(before_path, live_path):
            raise DifferenceTopologyError("outline node topology differs")
        before_segments = path_segments(before_path)
        live_segments = path_segments(live_path)
        if (
            not before_segments
            or len(before_segments) != len(live_segments)
            or [segment.kind for segment in before_segments]
            != [segment.kind for segment in live_segments]
        ):
            raise DifferenceTopologyError("outline segment topology differs")
        result.append(
            DifferenceBand(
                closed=bool(before_path.get("closed")),
                baseline_segments=before_segments,
                current_segments=live_segments,
            )
        )
    return tuple(result)


__all__ = [
    "DifferenceBand",
    "DifferenceTopologyError",
    "PathSegment",
    "difference_bands",
    "path_segments",
]
