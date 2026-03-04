# encoding: utf-8

"""Clean-room compensated tuning engine (Tim Ahrens multiple-master method).

This module implements compensated scaling for outline points using two masters:
  - base (e.g. Regular) coordinates (x_r, y_r)
  - reference heavier (e.g. Bold) coordinates (x_b, y_b)

It intentionally avoids importing GlyphsApp at import-time so it can be unit-tested
outside of Glyphs. The MCP tools call into this module from within Glyphs, passing
real layer/path/node data extracted from GS* objects.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence, Tuple


def clamp(value: float, lo: float, hi: float) -> float:
    v = float(value)
    if v < lo:
        return float(lo)
    if v > hi:
        return float(hi)
    return v


def round_half_away_from_zero(x: float) -> int:
    """Round to nearest int, with .5 values rounded away from zero."""
    xf = float(x)
    if xf >= 0.0:
        return int(math.floor(xf + 0.5))
    return -int(math.floor(abs(xf) + 0.5))


def units(value: float, *, round_units: bool = True) -> float | int:
    if not round_units:
        return float(value)
    return round_half_away_from_zero(float(value))


def keep_stroke_to_exponent_a(keep_stroke: float) -> float:
    """Map keep_stroke ∈ [0..1] to stroke exponent a ∈ [0..1].

    keep_stroke=1 means maximum compensation (a=0).
    keep_stroke=0 means geometric scaling (a=1).
    """
    ks = clamp(float(keep_stroke), 0.0, 1.0)
    return 1.0 - ks


def compute_q(*, scale: float, b: float, a: float) -> float:
    """Compute compensated interpolation factor q.

    Tim Ahrens method:
      q = (scale^(a - 1) - b) / (1 - b)
    where:
      - scale is sx or sy
      - a ∈ [0..1] is the stroke scale exponent
      - b is the ratio of stem thickness (ref/base), typically > 1

    q=1 means "use base only". q=0 means "use reference only".
    """
    s = float(scale)
    if s <= 0.0:
        raise ValueError("scale must be > 0")
    bf = float(b)
    if abs(1.0 - bf) < 1e-9:
        raise ValueError("b must be != 1")
    af = clamp(float(a), 0.0, 1.0)
    return (math.pow(s, af - 1.0) - bf) / (1.0 - bf)


def clamp_q(q: float) -> float:
    return clamp(float(q), 0.0, 1.0)


def italic_shear(italic_angle_degrees: float) -> float:
    """Return shear factor i = tan(angleRadians)."""
    return math.tan(math.radians(float(italic_angle_degrees)))


def transform_point(
    *,
    xr: float,
    yr: float,
    xb: float,
    yb: float,
    sx: float,
    sy: float,
    qx: float,
    qy: float,
    shear: float = 0.0,
    tx: float = 0.0,
    ty: float = 0.0,
) -> Tuple[float, float]:
    """Transform a single point using compensated scaling with optional italic shear."""
    y = float(sy) * (float(qy) * float(yr) + (1.0 - float(qy)) * float(yb))

    # Work in de-slanted coordinate system for x when shear is non-zero.
    ur = float(xr) - float(yr) * float(shear)
    ub = float(xb) - float(yb) * float(shear)
    u = float(sx) * (float(qx) * ur + (1.0 - float(qx)) * ub)
    x = u + y * float(shear)

    return (x + float(tx), y + float(ty))


def interpolate_metric(*, mr: float, mb: float, s: float, q: float) -> float:
    """Interpolate+scale a metric value (e.g. advance width) using the same logic as x."""
    return float(s) * (float(q) * float(mr) + (1.0 - float(q)) * float(mb))


def black_runs_from_intersections(xs: Sequence[float]) -> List[float]:
    """Return black-run widths given sorted intersection x-values (excluding start/end points).

    Assumes the scan starts outside the outline on the left, so black regions are
    between (xs[0], xs[1]), (xs[2], xs[3]) ...
    """
    out: List[float] = []
    n = len(xs)
    # Ignore odd tail.
    limit = n - (n % 2)
    for i in range(0, limit, 2):
        w = float(xs[i + 1]) - float(xs[i])
        if w > 0:
            out.append(w)
    return out


def _median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    items = sorted(float(v) for v in values)
    n = len(items)
    mid = n // 2
    if n % 2 == 1:
        return items[mid]
    return 0.5 * (items[mid - 1] + items[mid])


def stem_thickness_from_scanlines(
    *,
    scanlines_xs: Sequence[Sequence[float]],
    min_width: float = 5.0,
    max_width: Optional[float] = None,
) -> Optional[float]:
    """Estimate a robust stem thickness from multiple scanlines.

    For each scanline, compute black runs and take the median run width.
    Across scanlines, take the median of those per-scanline medians.
    """
    per_line: List[float] = []
    max_w = float(max_width) if max_width is not None else None
    for xs in scanlines_xs:
        runs = black_runs_from_intersections(xs)
        runs = [w for w in runs if w >= float(min_width) and (max_w is None or w <= max_w)]
        med = _median(runs)
        if med is None:
            continue
        per_line.append(float(med))
    return _median(per_line)


def iqr_ratio(values: Sequence[float]) -> Optional[float]:
    """Return IQR/median as a simple dispersion metric."""
    if not values:
        return None
    items = sorted(float(v) for v in values)
    n = len(items)
    if n < 4:
        return 0.0
    q1 = items[n // 4]
    q3 = items[(3 * n) // 4]
    med = _median(items)
    if med is None or abs(med) < 1e-9:
        return None
    return (q3 - q1) / med

