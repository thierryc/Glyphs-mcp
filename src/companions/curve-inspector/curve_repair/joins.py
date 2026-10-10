"""Source-node adjacency and ordered native line/curve expansion.

Mapping uses segment roles and source order, never nearest-point fitting.
Raindrops add one cubic at each line-adjacent end of a source cubic on the
qualified host. Missing/extra drawing elements fail closed.
"""
from dataclasses import dataclass
import math

from .geometry import RepairError, add, sub, mul, norm, dot


def point(node):
    return float(node.position.x), float(node.position.y)


def line_cubic(a, b):
    return a, add(a, mul(sub(b, a), 1/3)), add(a, mul(sub(b, a), 2/3)), b


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    kind: str
    indices: tuple
    curve: tuple


def source_segments(path, app):
    nodes = tuple(path.nodes)
    on = [i for i, node in enumerate(nodes) if node.type != app.OFFCURVE]
    if len(on) < 2: raise RepairError("open_endpoint", "Select a node between two segments.")
    pairs = list(zip(on, on[1:]))
    if path.closed: pairs.insert(0, (on[-1], on[0]))
    result = []
    for start, end in pairs:
        indices = tuple(range(start, end+1)) if start < end else tuple(range(start, len(nodes))) + tuple(range(end+1))
        if nodes[end].type == app.LINE and len(indices) == 2:
            kind, curve = "line", line_cubic(point(nodes[start]), point(nodes[end]))
        elif (nodes[end].type == app.CURVE and len(indices) == 4 and
              all(nodes[i].type == app.OFFCURVE for i in indices[1:3])):
            kind, curve = "curve", tuple(point(nodes[i]) for i in indices)
        else:
            raise RepairError("unsupported_segment", "This path contains a quadratic or unsupported segment ordering.")
        result.append(Segment(start, end, kind, indices, curve))
    return tuple(result)


def source_join(path, index, app):
    edges = source_segments(path, app)
    left = next((s for s in edges if s.end == index), None)
    right = next((s for s in edges if s.start == index), None)
    if left is None or right is None:
        raise RepairError("open_endpoint", "An open endpoint has only one adjoining segment.")
    if left.kind == right.kind == "line":
        raise RepairError("line_line", "Two straight segments do not need a curve repair.")
    return left, right


def join_kind(path, index, app):
    left, right = source_join(path, index, app)
    return left.kind + "-" + right.kind


def has_line_join(path, app):
    edges = source_segments(path, app)
    outgoing = {s.start: s for s in edges}
    return any(a.end in outgoing and a.kind != outgoing[a.end].kind for a in edges)


@dataclass(frozen=True)
class NativeChain:
    groups: tuple  # (source end node, tuple of effective cubics)
    edges: tuple
    closed: bool

    @property
    def curves(self):
        return tuple(c for _, group in self.groups for c in group)

    def join(self, index):
        groups = dict(self.groups)
        left = next((s for s in self.edges if s.end == index), None)
        right = next((s for s in self.edges if s.start == index), None)
        if left is None or right is None: raise RepairError("open_endpoint")
        return groups[left.end][-1], groups[right.end][0]


def drawing_chain(path, bezier, app, grid_step=0):
    edges = source_segments(path, app)
    nodes = tuple(path.nodes)
    incoming = {s.end: s for s in edges}
    outgoing = {s.start: s for s in edges}
    star = lambda i: int(nodes[i].connection) == app.GSSUPERSMOOTH
    expansions = {s.end: int(star(s.start) and s.start in incoming and incoming[s.start].kind == "line") +
                  int(star(s.end) and s.end in outgoing and outgoing[s.end].kind == "line")
                  for s in edges if s.kind == "curve"}
    elements, start, current, closed_seen = [], None, None, False
    for i in range(int(bezier.elementCount())):
        try: kind, pts = bezier.elementAtIndex_associatedPoints_(i)
        except Exception as exc: raise RepairError("native_unqualified", "Native drawing extraction failed.") from exc
        pts = tuple((float(p.x), float(p.y)) for p in pts)
        if any(not math.isfinite(v) for p in pts for v in p): raise RepairError("nonfinite_geometry")
        if kind == 0:
            if len(pts) != 1: raise RepairError("incompatible_correspondence")
            if start is not None:
                if not closed_seen or norm(sub(pts[0], start)) > 1e-9: raise RepairError("incompatible_correspondence")
                continue
            start = current = pts[0]
        elif kind in (1, 2):
            if current is None or closed_seen: raise RepairError("incompatible_correspondence")
            if kind == 1 and len(pts) == 1: curve = line_cubic(current, pts[0])
            elif kind == 2 and len(pts) == 3: curve = (current, *pts)
            else: raise RepairError("incompatible_correspondence")
            elements.append(("line" if kind == 1 else "curve", curve))
            current = pts[-1]
        elif kind == 3:
            if not path.closed or closed_seen or current is None:
                raise RepairError("incompatible_correspondence", "Native closing geometry cannot be mapped.")
            if norm(sub(current, start)) > 1e-9:
                # AppKit close-to contributes the closing straight segment.
                # The ordered source-role check below must account for it.
                elements.append(("line", line_cubic(current, start)))
                current = start
            closed_seen = True
        else: raise RepairError("incompatible_correspondence")
    if start is None or bool(path.closed) != closed_seen: raise RepairError("incompatible_correspondence")
    def matches(actual, raw):
        rounded = tuple(math.floor(v/grid_step+.5)*grid_step for v in raw) if grid_step > 0 else raw
        return min(norm(sub(actual, raw)), norm(sub(actual, rounded))) <= 1e-8
    if not star(edges[0].start) and not matches(start, point(nodes[edges[0].start])):
        raise RepairError("incompatible_correspondence", "Native start differs from its source anchor.")
    groups, cursor = [], 0
    for edge in edges:
        size = 1 + expansions.get(edge.end, 0)
        group = elements[cursor:cursor+size]; cursor += size
        if len(group) != size or any(kind != edge.kind for kind, _ in group):
            raise RepairError("native_unqualified", "Native transition omitted a segment or has an unqualified expansion.")
        curves = tuple(curve for _, curve in group)
        if not star(edge.end) and not matches(curves[-1][-1], point(nodes[edge.end])):
            raise RepairError("incompatible_correspondence", "Native endpoint differs from its source anchor.")
        if edge.kind == "curve" and size == 1:
            if any(not matches(a, b) for a, b in zip(curves[0][1:3], edge.curve[1:3])):
                raise RepairError("incompatible_correspondence", "An ordinary native handle changed unexpectedly.")
        if edge.kind == "line" and grid_step == 0:
            a, b = edge.curve[0], edge.curve[-1]
            v = sub(b, a); length2 = dot(v, v)
            if length2 <= 1e-20: raise RepairError("undefined_curvature", "A straight segment has zero length.")
            ts = [dot(sub(p, a), v)/length2 for p in (curves[0][0], curves[0][-1])]
            if (ts[0] < -1e-9 or ts[1] > 1+1e-9 or ts[0] >= ts[1] or
                any(norm(sub(p, add(a, mul(v, t)))) > 1e-8 for p, t in zip((curves[0][0], curves[0][-1]), ts))):
                raise RepairError("short_line", "The straight segment is too short for this native transition.")
        groups.append((edge.end, curves))
    if cursor != len(elements): raise RepairError("incompatible_correspondence", "Native transition coverage is incomplete.")
    return NativeChain(tuple(groups), edges, bool(path.closed))
