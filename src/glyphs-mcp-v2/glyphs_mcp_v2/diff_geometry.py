"""Pure topology-compatible outline bands for the live change Reporter."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


Point = tuple[float, float]


class DifferenceTopologyError(ValueError):
    """Raised when old and live paths cannot be paired without guessing."""


class DiffPreparationCancelled(RuntimeError):
    """Raised at a cooperative geometry-preparation cancellation point."""


def _checkpoint(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise DiffPreparationCancelled("difference preparation was cancelled")


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


def _topology_matches(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    *,
    cancelled: Callable[[], bool] | None = None,
) -> bool:
    first_nodes = list(first.get("nodes") or [])
    second_nodes = list(second.get("nodes") or [])
    if (
        bool(first.get("closed")) != bool(second.get("closed"))
        or len(first_nodes) != len(second_nodes)
    ):
        return False
    for before, after in zip(first_nodes, second_nodes):
        _checkpoint(cancelled)
        if str(before.get("type") or "line") != str(
            after.get("type") or "line"
        ):
            return False
    return True


def _geometry_matches(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    *,
    cancelled: Callable[[], bool] | None = None,
) -> bool:
    if not _topology_matches(first, second, cancelled=cancelled):
        return False
    for before, after in zip(first.get("nodes") or [], second.get("nodes") or []):
        _checkpoint(cancelled)
        if _point(before) != _point(after):
            return False
    return True


def path_segments(
    path: Mapping[str, Any],
    *,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[PathSegment, ...]:
    """Return the exact drawable segments for one canonical path."""

    nodes = list(path.get("nodes") or [])
    oncurves = []
    for index, node in enumerate(nodes):
        _checkpoint(cancelled)
        if str(node.get("type") or "line") != "offcurve":
            oncurves.append(index)
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
        _checkpoint(cancelled)
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
    *,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[DifferenceBand, ...]:
    """Return exact corresponding-outline bands, skipping unchanged paths."""

    baseline = list(baseline_paths or [])
    current = list(current_paths or [])
    if len(baseline) != len(current):
        raise DifferenceTopologyError("outline path counts differ")
    result: list[DifferenceBand] = []
    for before_path, live_path in zip(baseline, current):
        _checkpoint(cancelled)
        if _geometry_matches(before_path, live_path, cancelled=cancelled):
            continue
        if not _topology_matches(before_path, live_path, cancelled=cancelled):
            raise DifferenceTopologyError("outline node topology differs")
        before_segments = path_segments(before_path, cancelled=cancelled)
        live_segments = path_segments(live_path, cancelled=cancelled)
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
    "DiffPreparationCancelled",
    "DifferenceTopologyError",
    "PathSegment",
    "difference_bands",
    "path_segments",
]
