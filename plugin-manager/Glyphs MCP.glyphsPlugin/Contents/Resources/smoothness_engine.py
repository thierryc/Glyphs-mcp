"""Pure helpers for detecting tangent-smooth joins from handle collinearity.

This module intentionally avoids GlyphsApp imports so it can be unit-tested
outside Glyphs.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def _node_get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _node_type(node: Any) -> str:
    t = _node_get(node, "type", None)
    return str(t) if t is not None else ""


def _node_smooth(node: Any) -> bool:
    return bool(_node_get(node, "smooth", False))


def _node_xy(node: Any) -> Tuple[float, float]:
    """Return (x, y) for a node-like object.

    Supported shapes:
    - Glyphs nodes (node.position.x/y, node.x/y)
    - dict nodes ({x, y}, or {position: {x,y}} / {position: (x,y)})
    """

    if node is None:
        return (0.0, 0.0)

    # position attribute / key (Glyphs uses NSPoint-like objects)
    pos = _node_get(node, "position", None)
    if pos is not None:
        if isinstance(pos, dict):
            return (float(pos.get("x", 0.0)), float(pos.get("y", 0.0)))
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            return (float(pos[0]), float(pos[1]))
        x = getattr(pos, "x", None)
        y = getattr(pos, "y", None)
        if x is not None and y is not None:
            return (float(x), float(y))

    # direct x/y
    x = _node_get(node, "x", None)
    y = _node_get(node, "y", None)
    if x is not None and y is not None:
        return (float(x), float(y))

    return (0.0, 0.0)


def _vec(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float]:
    return (b[0] - a[0], b[1] - a[1])


def _length(v: Tuple[float, float]) -> float:
    return math.hypot(v[0], v[1])


def _angle_deg(v1: Tuple[float, float], v2: Tuple[float, float]) -> Optional[float]:
    l1 = _length(v1)
    l2 = _length(v2)
    if l1 <= 0.0 or l2 <= 0.0:
        return None
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    c = max(-1.0, min(1.0, dot / (l1 * l2)))
    return float(math.degrees(math.acos(c)))


def compute_join_angle_deg(
    node_xy: Tuple[float, float],
    prev_handle_xy: Tuple[float, float],
    next_handle_xy: Tuple[float, float],
) -> Dict[str, Optional[float]]:
    """Compute join angle (deg) + handle lengths for a cubic join.

    Incoming tangent direction at the join is proportional to (node - prev_handle).
    Outgoing tangent direction at the join is proportional to (next_handle - node).
    A tangent-smooth join yields an angle near 0 degrees.
    """

    vin = _vec(prev_handle_xy, node_xy)  # prev handle -> node
    vout = _vec(node_xy, next_handle_xy)  # node -> next handle
    angle = _angle_deg(vin, vout)
    return {
        "angleDeg": angle,
        "handleInLen": _length(vin),
        "handleOutLen": _length(vout),
    }


def evaluate_collinear_handles_at_node(
    nodes: Sequence[Any],
    node_index: int,
    *,
    closed: bool,
    threshold_deg: float,
    min_handle_len: float,
    allowed_node_types: Iterable[str] = ("curve",),
) -> Dict[str, Any]:
    """Evaluate a node index for "should be smooth" based on adjacent handles.

    Returns:
        dict with:
          - ok (bool)
          - nodeIndex (int)
          - reason (str) when ok=False
          - angleDeg/handleInLen/handleOutLen/nodeType/smooth when ok=True
    """

    node_count = len(nodes)
    if node_index < 0 or node_index >= node_count:
        return {"ok": False, "nodeIndex": int(node_index), "reason": "index_out_of_range"}

    node = nodes[node_index]
    node_type = _node_type(node)
    if node_type == "offcurve":
        return {"ok": False, "nodeIndex": int(node_index), "reason": "offcurve"}

    if node_type not in set(str(t) for t in allowed_node_types):
        return {"ok": False, "nodeIndex": int(node_index), "reason": "node_type_not_supported", "nodeType": node_type}

    prev_index = node_index - 1
    next_index = node_index + 1
    if closed and node_count > 0:
        prev_index %= node_count
        next_index %= node_count
    else:
        if prev_index < 0 or next_index >= node_count:
            return {"ok": False, "nodeIndex": int(node_index), "reason": "no_neighbors", "nodeType": node_type}

    prev_node = nodes[prev_index]
    next_node = nodes[next_index]
    if _node_type(prev_node) != "offcurve" or _node_type(next_node) != "offcurve":
        return {"ok": False, "nodeIndex": int(node_index), "reason": "no_both_handles", "nodeType": node_type}

    node_xy = _node_xy(node)
    prev_xy = _node_xy(prev_node)
    next_xy = _node_xy(next_node)
    metrics = compute_join_angle_deg(node_xy, prev_xy, next_xy)

    angle = metrics.get("angleDeg")
    handle_in_len = float(metrics.get("handleInLen") or 0.0)
    handle_out_len = float(metrics.get("handleOutLen") or 0.0)

    if min(handle_in_len, handle_out_len) < float(min_handle_len):
        return {
            "ok": False,
            "nodeIndex": int(node_index),
            "reason": "too_short_handles",
            "nodeType": node_type,
            "handleInLen": handle_in_len,
            "handleOutLen": handle_out_len,
        }

    if angle is None:
        return {"ok": False, "nodeIndex": int(node_index), "reason": "degenerate_angle", "nodeType": node_type}

    if float(angle) > float(threshold_deg):
        return {
            "ok": False,
            "nodeIndex": int(node_index),
            "reason": "angle_too_large",
            "nodeType": node_type,
            "angleDeg": float(angle),
            "handleInLen": handle_in_len,
            "handleOutLen": handle_out_len,
        }

    return {
        "ok": True,
        "nodeIndex": int(node_index),
        "nodeType": node_type,
        "smooth": _node_smooth(node),
        "angleDeg": float(angle),
        "handleInLen": handle_in_len,
        "handleOutLen": handle_out_len,
    }


def find_collinear_handle_nodes(
    nodes: Sequence[Any],
    *,
    closed: bool,
    threshold_deg: float = 3.0,
    min_handle_len: float = 5.0,
    node_indices: Optional[Sequence[int]] = None,
    include_already_smooth: bool = False,
    allowed_node_types: Iterable[str] = ("curve",),
) -> List[Dict[str, Any]]:
    """Return candidate nodes that meet the smoothness heuristic."""

    if node_indices is None:
        indices: Sequence[int] = list(range(len(nodes)))
    else:
        indices = [int(i) for i in node_indices]

    candidates: List[Dict[str, Any]] = []
    for i in indices:
        r = evaluate_collinear_handles_at_node(
            nodes,
            int(i),
            closed=bool(closed),
            threshold_deg=float(threshold_deg),
            min_handle_len=float(min_handle_len),
            allowed_node_types=allowed_node_types,
        )
        if not r.get("ok"):
            continue
        if (not include_already_smooth) and bool(r.get("smooth", False)):
            continue
        candidates.append(
            {
                "nodeIndex": int(r["nodeIndex"]),
                "nodeType": str(r.get("nodeType", "")),
                "smooth": bool(r.get("smooth", False)),
                "angleDeg": float(r.get("angleDeg", 0.0)),
                "handleInLen": float(r.get("handleInLen", 0.0)),
                "handleOutLen": float(r.get("handleOutLen", 0.0)),
            }
        )

    return candidates

