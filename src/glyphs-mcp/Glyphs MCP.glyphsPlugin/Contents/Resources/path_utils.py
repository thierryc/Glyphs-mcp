# encoding: utf-8

from __future__ import division, print_function, unicode_literals
from typing import List, Tuple, Dict, Optional
from math import hypot, sqrt, atan2, cos, sin, degrees

try:
    from GlyphsApp import GSPath, GSNode, Glyphs  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - loaded inside Glyphs
    GSPath = object  # type: ignore
    GSNode = object  # type: ignore
    Glyphs = None

Point = Tuple[float, float]


# --- Basic geometry ---------------------------------------------------------

def add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def mul(a: Point, k: float) -> Point:
    return (a[0] * k, a[1] * k)


def lerp(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def length(v: Point) -> float:
    return hypot(v[0], v[1])


def normalize(v: Point) -> Point:
    l = length(v)
    if l == 0:
        return (0.0, 0.0)
    return (v[0] / l, v[1] / l)


def angle(v: Point) -> float:
    return atan2(v[1], v[0])


def angle_between(v1: Point, v2: Point) -> float:
    a = angle(v1)
    b = angle(v2)
    d = abs(a - b)
    while d > 3.141592653589793:
        d -= 2.0 * 3.141592653589793
    return abs(d)


# --- Cubic Bezier helpers ---------------------------------------------------

def cubic_point(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    u = 1.0 - t
    uu = u * u
    uuu = uu * u
    tt = t * t
    ttt = tt * t
    x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
    y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
    return (x, y)


def split_cubic(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Tuple[Tuple[Point, Point, Point, Point], Tuple[Point, Point, Point, Point]]:
    a = lerp(p0, p1, t)
    b = lerp(p1, p2, t)
    c = lerp(p2, p3, t)
    d = lerp(a, b, t)
    e = lerp(b, c, t)
    m = lerp(d, e, t)
    left = (p0, a, d, m)
    right = (m, e, c, p3)
    return left, right


# --- Path structure utilities ----------------------------------------------

def is_oncurve(node: GSNode) -> bool:
    return getattr(node, "type", "offcurve") != "offcurve"


def oncurve_indices(path: GSPath) -> List[int]:
    result = []
    for i, n in enumerate(path.nodes):
        if is_oncurve(n):
            result.append(i)
    return result


def neighbors(path: GSPath, node_index: int) -> Tuple[int, int]:
    count = len(path.nodes)
    closed = bool(getattr(path, "closed", True))
    if closed and count > 0:
        return (node_index - 1) % count, (node_index + 1) % count
    return max(0, node_index - 1), min(count - 1, node_index + 1)


def segment_for_oncurve(path: GSPath, oncurve_index: int) -> Dict:
    count = len(path.nodes)
    closed = bool(getattr(path, "closed", True))
    # Find next on-curve index
    j = oncurve_index
    off = []
    while True:
        j = (j + 1) % count if closed else (j + 1)
        if j >= count:
            break
        n = path.nodes[j]
        if is_oncurve(n):
            break
        off.append(j)
    return {
        "start": oncurve_index,
        "offcurves": off,
        "end": j if j < count else (0 if closed else count - 1),
    }


def prev_oncurve_index(path: GSPath, node_index: int) -> Optional[int]:
    count = len(path.nodes)
    closed = bool(getattr(path, "closed", True))
    i = node_index
    for _ in range(count):
        i = (i - 1) % count if closed else (i - 1)
        if i < 0:
            return None
        if is_oncurve(path.nodes[i]):
            return i
    return None


def next_oncurve_index(path: GSPath, node_index: int) -> Optional[int]:
    count = len(path.nodes)
    closed = bool(getattr(path, "closed", True))
    i = node_index
    for _ in range(count):
        i = (i + 1) % count if closed else (i + 1)
        if i >= count:
            return None
        if is_oncurve(path.nodes[i]):
            return i
    return None


# --- Editing operations -----------------------------------------------------

def insert_oncurve_in_segment(path: GSPath, oncurve_index: int, t: float, smooth: bool = False) -> int:
    """Split the segment starting at oncurve_index at parameter t (0..1).

    Returns the index of the newly inserted on-curve node after the split.
    Supports line segments (0 off-curves) and cubic segments (2 off-curves).
    """
    info = segment_for_oncurve(path, oncurve_index)
    start = info["start"]
    end = info["end"]
    off = info["offcurves"]

    # Gather points
    p0 = (path.nodes[start].position.x, path.nodes[start].position.y)
    p3 = (path.nodes[end].position.x, path.nodes[end].position.y)

    if len(off) == 0:
        # Line segment
        m = lerp(p0, p3, t)
        # Insert a new on-curve before `end`
        new_node = GSNode()
        new_node.type = "line"
        new_node.position = m
        new_node.smooth = bool(smooth)
        insert_at = end  # inserting before end keeps ordering
        path.nodes.insert(insert_at, new_node)
        return insert_at

    # Treat any other case as cubic-like; fall back if not 2 offcurves
    p1 = (path.nodes[off[0]].position.x, path.nodes[off[0]].position.y)
    p2 = (path.nodes[off[-1]].position.x, path.nodes[off[-1]].position.y)  # if more than 2, use last two
    if len(off) >= 2:
        p1 = (path.nodes[off[0]].position.x, path.nodes[off[0]].position.y)
        p2 = (path.nodes[off[1]].position.x, path.nodes[off[1]].position.y)

    left, right = split_cubic(p0, p1, p2, p3, max(0.0, min(1.0, t)))
    # left: (p0, a, d, m) ; right: (m, e, c, p3)
    (_, a, d, m) = left
    (m2, e, c, _) = right
    assert abs(m[0] - m2[0]) < 1e-6 and abs(m[1] - m2[1]) < 1e-6

    # Rewrite the original segment to: start, a, d, m, e, c, end
    # Update existing nodes when possible, then insert the rest

    # Ensure there is at least one offcurve after start
    if len(off) == 0:
        # shouldn't happen here
        pass
    elif len(off) == 1:
        # convert to cubic by updating off[0] to `a` and inserting `d`
        path.nodes[off[0]].position = a
        n_d = GSNode()
        n_d.type = "offcurve"
        n_d.position = d
        path.nodes.insert(off[0] + 1, n_d)
        off = [off[0], off[0] + 1]
    else:
        # have at least two off-curves
        path.nodes[off[0]].position = a
        path.nodes[off[1]].position = d

    # Insert the split on-curve m before end (index may shift as we insert)
    insert_at = end
    n_m = GSNode()
    n_m.type = "curve"
    n_m.position = m
    n_m.smooth = bool(smooth)
    path.nodes.insert(insert_at, n_m)

    # After inserting m, end index shifts by +1
    end += 1

    # Insert/update the handles for the right part: e, c
    n_e = GSNode()
    n_e.type = "offcurve"
    n_e.position = e
    path.nodes.insert(end, n_e)

    n_c = GSNode()
    n_c.type = "offcurve"
    n_c.position = c
    path.nodes.insert(end + 1, n_c)

    return insert_at


def correct_path_direction_all_layers(glyph) -> int:
    """Run correctPathDirection() on all master layers of a glyph. Returns count."""
    count = 0
    font = glyph.parent
    for m in font.masters:
        l = glyph.layers[m.id]
        try:
            l.correctPathDirection()
            count += 1
        except Exception:
            pass
    return count


def balance_smooth_handles(layer, alpha: float = 0.33, clamp: float = 0.6, path_index: Optional[int] = None) -> int:
    """Balance handles for smooth on-curve nodes.

    - Direction: use tangent along the chord from previous to next on-curve
    - Lengths: handleLenIn = alpha * dist(prevOC, OC), handleLenOut = alpha * dist(OC, nextOC)
    - Clamp: cap each handle length to `clamp * chordLen`

    Returns number of handles adjusted.
    """
    adjusted = 0
    paths = layer.paths if path_index is None else [layer.paths[path_index]]
    for path in paths:
        oc_idx = oncurve_indices(path)
        for i, node_index in enumerate(oc_idx):
            node = path.nodes[node_index]
            if not getattr(node, "smooth", False):
                continue
            prev_idx = oc_idx[i - 1] if i > 0 else (oc_idx[-1] if bool(getattr(path, "closed", True)) and oc_idx else None)
            next_idx = oc_idx[(i + 1) % len(oc_idx)] if oc_idx else None
            if prev_idx is None or next_idx is None:
                continue
            p_prev = (path.nodes[prev_idx].position.x, path.nodes[prev_idx].position.y)
            p_cur = (node.position.x, node.position.y)
            p_next = (path.nodes[next_idx].position.x, path.nodes[next_idx].position.y)

            v_tan = normalize(sub(p_next, p_prev))
            dist_in = length(sub(p_cur, p_prev))
            dist_out = length(sub(p_next, p_cur))
            L_in = min(clamp * dist_in, alpha * dist_in)
            L_out = min(clamp * dist_out, alpha * dist_out)

            # Find neighboring off-curves immediately before/after node
            # before
            b_index = node_index - 1
            if b_index < 0:
                b_index = len(path.nodes) - 1 if bool(getattr(path, "closed", True)) else None
            a_index = node_index + 1 if node_index + 1 < len(path.nodes) else (0 if bool(getattr(path, "closed", True)) else None)
            if b_index is None or a_index is None:
                continue

            b_node = path.nodes[b_index]
            a_node = path.nodes[a_index]
            if getattr(b_node, "type", "offcurve") != "offcurve" or getattr(a_node, "type", "offcurve") != "offcurve":
                # Do not force-convert lines to curves
                continue

            # Place handles colinear with tangent
            new_b = sub(p_cur, mul(v_tan, L_in))
            new_a = add(p_cur, mul(v_tan, L_out))
            b_node.position = new_b
            a_node.position = new_a
            adjusted += 2
    return adjusted


def nearly_colinear(p_prev: Point, p: Point, p_next: Point, angle_thresh_deg: float = 2.0, dist_thresh: float = 2.0) -> bool:
    # Reject removal if point is too far from the straight chord
    v1 = sub(p, p_prev)
    v2 = sub(p_next, p)
    if length(v1) < 1e-6 or length(v2) < 1e-6:
        return False
    ang = degrees(angle_between(v1, v2))
    if abs(180.0 - ang) > angle_thresh_deg:
        return False
    # Perpendicular distance from p to line (p_prev -> p_next)
    x0, y0 = p
    x1, y1 = p_prev
    x2, y2 = p_next
    num = abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1)
    den = sqrt((y2 - y1) ** 2 + (x2 - x1) ** 2)
    if den == 0:
        return False
    d = num / den
    return d <= dist_thresh


def remove_redundant_line_nodes(layer, path_index: Optional[int] = None, angle_thresh_deg: float = 2.0, dist_thresh: float = 2.0) -> int:
    """Remove on-curve nodes that sit on straight lines between neighbors (line-only case).

    Only removes when both adjacent segments are lines, preserving basic shape and avoiding curve edits.
    Returns number of on-curve nodes removed.
    """
    removed = 0
    paths = layer.paths if path_index is None else [layer.paths[path_index]]
    for path in paths:
        # Collect indices to remove first (so we don't invalidate as we go)
        to_remove = []
        occ = oncurve_indices(path)
        n_on = len(occ)
        if n_on < 3:
            continue
        for k, idx in enumerate(occ):
            prev_idx = occ[k - 1]
            next_idx = occ[(k + 1) % n_on]
            # Check if both adjacent segments are straight lines (no off-curves in between)
            seg_prev = segment_for_oncurve(path, prev_idx)
            seg_cur = segment_for_oncurve(path, idx)
            if len(seg_prev["offcurves"]) != 0 or len(seg_cur["offcurves"]) != 0:
                continue
            p_prev = (path.nodes[prev_idx].position.x, path.nodes[prev_idx].position.y)
            p = (path.nodes[idx].position.x, path.nodes[idx].position.y)
            p_next = (path.nodes[seg_cur["end"]].position.x, path.nodes[seg_cur["end"]].position.y)
            if nearly_colinear(p_prev, p, p_next, angle_thresh_deg, dist_thresh):
                to_remove.append(idx)

        # Remove nodes by descending index to keep indices valid
        for idx in sorted(to_remove, reverse=True):
            try:
                del path.nodes[idx]
                removed += 1
            except Exception:
                pass
    return removed


def outline_compatibility_report(glyph) -> Dict:
    """Produce a simple compatibility report across masters for a glyph.

    Checks:
      - path count
      - for each path: on-curve count, closed flag, and node type sequence signature
    """
    font = glyph.parent
    report = {
        "glyph": getattr(glyph, "name", None),
        "masters": [],
        "issues": [],
    }
    baseline = None
    for m in font.masters:
        layer = glyph.layers[m.id]
        sigs = []
        for p in layer.paths:
            types = [getattr(n, "type", "offcurve") for n in p.nodes if getattr(n, "type", "offcurve") != "offcurve"]
            sigs.append({
                "onCurveCount": len([1 for n in p.nodes if getattr(n, "type", "offcurve") != "offcurve"]),
                "closed": bool(getattr(p, "closed", True)),
                "typeSequence": types,
            })
        entry = {
            "masterId": m.id,
            "masterName": m.name,
            "pathCount": len(layer.paths),
            "pathSignatures": sigs,
        }
        report["masters"].append(entry)
        if baseline is None:
            baseline = entry

    # Compare to baseline
    if baseline is None:
        return report
    for entry in report["masters"][1:]:
        if entry["pathCount"] != baseline["pathCount"]:
            report["issues"].append("Path count differs: {} vs {}".format(entry["masterName"], report["masters"][0]["masterName"]))
            continue
        for i, (a, b) in enumerate(zip(entry["pathSignatures"], report["masters"][0]["pathSignatures"])):
            if a["onCurveCount"] != b["onCurveCount"]:
                report["issues"].append("Path {} on-curve count differs in {}".format(i, entry["masterName"]))
            if bool(a["closed"]) != bool(b["closed"]):
                report["issues"].append("Path {} closed/open differs in {}".format(i, entry["masterName"]))
            if len(a["typeSequence"]) != len(b["typeSequence"]):
                report["issues"].append("Path {} type-sequence length differs in {}".format(i, entry["masterName"]))

    return report


def apply_across_masters(glyph, func, *args, **kwargs) -> int:
    """Run `func(layer, *args, **kwargs)` for each master layer. Returns sum of results."""
    total = 0
    for m in glyph.parent.masters:
        layer = glyph.layers[m.id]
        try:
            res = func(layer, *args, **kwargs)
            if isinstance(res, int):
                total += res
        except Exception:
            pass
    return total

