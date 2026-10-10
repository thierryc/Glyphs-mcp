"""Match native AppKit drawing elements to source nodes without nearest fitting.

Qualified selector signature: Glyphs 4.1.1 (4108), PyObjC's one-input/out-point
elementAtIndex_associatedPoints_. Other topologies fail closed.
"""
from __future__ import annotations
from collections import namedtuple
from dataclasses import dataclass
import math
from .geometry import RepairError, norm, sub

Point = namedtuple("Point", "x y")


@dataclass(frozen=True)
class OutlineNode:
    position: Point
    type: str
    connection: int


@dataclass(frozen=True)
class OutlinePath:
    nodes: tuple
    closed: bool


def drawing_outline(path, bezier, *, star_connection, curve_type, offcurve_type, line_type, grid_step=0):
    nodes = tuple(path.nodes)
    oncurves = [i for i, node in enumerate(nodes) if node.type != offcurve_type]
    if not oncurves: raise RepairError("incompatible_correspondence")
    start = oncurves[-1] if path.closed else oncurves[0]
    ordered = [i for i in oncurves if i > start] + [i for i in oncurves if i <= start] if path.closed else oncurves[1:]
    count = len(nodes)
    positions, cursor, moved, closed_seen = {}, 0, False, False
    initial = None
    for index in range(int(bezier.elementCount())):
        try: kind, points = bezier.elementAtIndex_associatedPoints_(index)
        except Exception as exc:
            raise RepairError("native_unqualified", "Native drawing-path extraction is unavailable on this host.") from exc
        points = tuple(Point(float(p.x), float(p.y)) for p in points)
        if any(not math.isfinite(v) for point in points for v in point): raise RepairError("nonfinite_geometry")
        if kind == 0:  # AppKit move-to
            if len(points) != 1: raise RepairError("incompatible_correspondence")
            if moved:
                # Glyphs emits a redundant trailing move after a closed path.
                if not closed_seen or cursor != len(ordered) or norm(sub(points[0], initial)) > 1e-9:
                    raise RepairError("incompatible_correspondence", "Multiple native drawing subpaths.")
                continue
            initial = points[0]; positions[start] = initial; moved = True
        elif kind in (1, 2):
            if not moved or closed_seen or cursor >= len(ordered): raise RepairError("incompatible_correspondence")
            end = ordered[cursor]; cursor += 1
            if kind == 1:
                if len(points) != 1 or nodes[end].type != line_type: raise RepairError("incompatible_correspondence")
                positions[end] = points[0]
            else:
                controls = ((end-2) % count, (end-1) % count)
                if (len(points) != 3 or nodes[end].type != curve_type or
                        any(nodes[i].type != offcurve_type for i in controls)):
                    raise RepairError("incompatible_correspondence", "Native drawing changes cubic topology.")
                for i, point in zip((*controls, end), points): positions[i] = point
        elif kind == 3:
            if not path.closed or cursor != len(ordered): raise RepairError("incompatible_correspondence")
            closed_seen = True
        else:
            raise RepairError("incompatible_correspondence", "Unknown native drawing element.")
    if cursor != len(ordered) or len(positions) != count or (path.closed and not closed_seen):
        raise RepairError("incompatible_correspondence", "Native drawing coverage is incomplete.")
    # Every non-star point must match its source or the host's qualified grid
    # rounding. Source order/type matching is exact; no nearest fitting.
    for i, node in enumerate(nodes):
        if int(node.connection) != star_connection:
            p = node.position
            raw = (float(p.x), float(p.y))
            rounded = tuple(math.floor(v/grid_step+.5)*grid_step for v in raw) if grid_step > 0 else raw
            if min(norm(sub(positions[i], raw)), norm(sub(positions[i], rounded))) > 1e-9:
                raise RepairError("incompatible_correspondence", "Native drawing/source mismatch at node {}: {} versus {}.".format(i, tuple(positions[i]), (float(p.x), float(p.y))))
    return OutlinePath(tuple(OutlineNode(positions[i], node.type, int(node.connection)) for i, node in enumerate(nodes)), bool(path.closed))
