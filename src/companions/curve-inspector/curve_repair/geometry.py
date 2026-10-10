"""Regularity certificates, signed G1/G2 diagnostics and continuous bounds.

Coordinates supplied to diagnostics are em-normalized. Unlike the display
helper, singular curvature is never represented as zero.
"""
from __future__ import annotations

import math
from curve_core.geometry import _derivatives, cubic_point

EPS = 1e-12
ANGLE_TOLERANCE = 1e-6
CURVATURE_ABSOLUTE = 1e-6
CURVATURE_RELATIVE = 1e-5


class RepairError(ValueError):
    def __init__(self, code, detail=""):
        self.code = code
        self.detail = detail or code.replace("_", " ")
        super().__init__(self.detail)


def add(a, b): return (a[0] + b[0], a[1] + b[1])
def sub(a, b): return (a[0] - b[0], a[1] - b[1])
def mul(a, k): return (a[0] * k, a[1] * k)
def dot(a, b): return a[0] * b[0] + a[1] * b[1]
def det(a, b): return a[0] * b[1] - a[1] * b[0]
def norm(a): return math.hypot(*a)


def finite_curve(curve):
    if len(curve) != 4 or any(len(p) != 2 for p in curve):
        raise RepairError("invalid_cubic")
    if any(not math.isfinite(float(v)) for p in curve for v in p):
        raise RepairError("nonfinite_geometry")


def normalized(curve, upm, origin=None):
    if not math.isfinite(upm) or upm <= 0:
        raise RepairError("invalid_upm")
    origin = origin or curve[0]
    result = tuple(mul(sub(p, origin), 1 / upm) for p in curve)
    finite_curve(result)
    return result


def split(controls):
    """de Casteljau at 1/2; also used for quadratic derivative polygons."""
    levels = [tuple(controls)]
    while len(levels[-1]) > 1:
        levels.append(tuple(mul(add(a, b), .5) for a, b in zip(levels[-1], levels[-1][1:])))
    return tuple(level[0] for level in levels), tuple(level[-1] for level in reversed(levels))


def certify_regular(curve, *, max_depth=20, budget=8192):
    finite_curve(curve)
    derivatives = tuple(mul(sub(b, a), 3) for a, b in zip(curve, curve[1:]))
    stack = [(derivatives, 0)]
    visited = 0
    while stack:
        polygon, depth = stack.pop()
        visited += 1
        if visited > budget:
            raise RepairError("unresolved_regularity", "Regularity subdivision budget exceeded.")
        # A separating axis excludes zero from the derivative's convex hull.
        if any(min(p[axis] for p in polygon) > EPS or max(p[axis] for p in polygon) < -EPS
               for axis in (0, 1)):
            continue
        if norm(polygon[0]) <= EPS or norm(polygon[-1]) <= EPS:
            raise RepairError("undefined_curvature", "A curve has zero or unresolved speed.")
        if depth >= max_depth:
            raise RepairError("unresolved_regularity", "Possible cusp or near-zero speed.")
        left, right = split(polygon)
        stack.extend(((left, depth + 1), (right, depth + 1)))


def signed_curvature(curve, t):
    finite_curve(curve)
    first, second = _derivatives(curve, t)
    speed = norm(first)
    if speed <= EPS:
        raise RepairError("undefined_curvature")
    result = det(first, second) / speed**3
    if not math.isfinite(result):
        raise RepairError("undefined_curvature")
    return first, result


def diagnose_join(left, right):
    finite_curve(left); finite_curve(right)
    if norm(sub(left[-1], right[0])) > EPS:
        raise RepairError("incompatible_correspondence", "Join endpoints differ.")
    v_left, k_left = signed_curvature(left, 1)
    v_right, k_right = signed_curvature(right, 0)
    angle = abs(math.atan2(det(v_left, v_right), dot(v_left, v_right)))
    error = abs(k_left - k_right)
    limit = CURVATURE_ABSOLUTE + CURVATURE_RELATIVE * max(abs(k_left), abs(k_right))
    g1 = dot(v_left, v_right) > 0 and angle <= ANGLE_TOLERANCE
    return {"g1": g1, "g2": g1 and error <= limit, "angle": angle,
            "curvatureLeft": k_left, "curvatureRight": k_right,
            "curvatureError": error, "curvatureTolerance": limit}


def integrated_difference(before, after):
    finite_curve(before); finite_curve(after)
    points = tuple(sub(b, a) for a, b in zip(before, after))
    value = math.fsum(dot(points[i], points[j]) * math.comb(3, i) * math.comb(3, j)
                      / (7 * math.comb(6, i+j)) for i in range(4) for j in range(4))
    return max(0.0, value)


def deviation(before, after, tolerance, *, max_depth=20, budget=8192):
    """Return conservative continuous same-parameter bounds, not sample maxima."""
    finite_curve(before); finite_curve(after)
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise RepairError("invalid_tolerance")
    difference = tuple(sub(b, a) for a, b in zip(before, after))
    if all(p == (0, 0) for p in difference):
        return {"accepted": True, "lower": 0.0, "upper": 0.0, "integral": 0.0}
    margin = EPS * max(1.0, *(norm(p) for p in difference))
    lower, upper, visited = 0.0, 0.0, 0
    stack = [(difference, 0)]
    while stack:
        controls, depth = stack.pop()
        visited += 1
        low = max(norm(controls[0]), norm(controls[-1]), norm(cubic_point(controls, .5)))
        high = max(norm(p) for p in controls) + margin
        lower = max(lower, max(0, low - margin))
        if lower > tolerance:
            return {"accepted": False, "lower": lower,
                    "upper": max(norm(p) for p in difference) + margin,
                    "integral": integrated_difference(before, after)}
        if high <= tolerance:
            upper = max(upper, high)
            continue
        if depth >= max_depth or visited > budget:
            raise RepairError("unresolved_deviation", "Cannot certify the requested deviation bound.")
        left, right = split(controls)
        stack.extend(((left, depth + 1), (right, depth + 1)))
    return {"accepted": True, "lower": lower, "upper": upper,
            "integral": integrated_difference(before, after)}


def check_pair(before, after, upm, tolerance_em):
    origin = before[0]
    source = normalized(before, upm, origin)
    trial = normalized(after, upm, origin)
    certify_regular(source); certify_regular(trial)
    # Subtract stored coordinates before normalization. Subtracting separately
    # translated/scaled points can add cancellation error at an exact limit.
    # A zero cubic and the difference cubic have the same deviation polynomial.
    difference = tuple(mul(sub(b, a), 1/upm) for a, b in zip(before, after))
    result = deviation(((0., 0.),)*4, difference, tolerance_em)
    if not result["accepted"]:
        raise RepairError("excess_deviation", "Effective outline deviation exceeds the tolerance.")
    return result


def no_regression(before, after):
    """Every affected smooth neighbor is checked against the immutable baseline."""
    if before["g2"] and not after["g2"]:
        return False
    if before["g1"] and not after["g1"]:
        return False
    return (after["angle"] <= before["angle"] + ANGLE_TOLERANCE and
            after["curvatureError"] <= before["curvatureError"] + before["curvatureTolerance"])


def chain_deviation(before, after, upm, tolerance_em, *, budget=16384):
    """Certified continuous bound with different native segment counts.

Each cubic is within epsilon of its parameterized chord subdivision (a
Bernstein convex-hull bound). Match the two resulting polylines by normalized
chord arc length. Their difference is linear between the union of breakpoints,
so endpoint maxima plus both flattening errors bound all corresponding points
and hence bidirectional geometric distance. This can overestimate deviation.
No exact corresponding-cubic integral is claimed for this new correspondence.
"""
    if not before or not after: raise RepairError("incompatible_correspondence")
    if not math.isfinite(tolerance_em) or tolerance_em <= 0: raise RepairError("invalid_tolerance")
    origin = before[0][0]
    left = tuple(normalized(c, upm, origin) for c in before)
    right = tuple(normalized(c, upm, origin) for c in after)
    for c in (*left, *right): certify_regular(c)
    if left == right: return {"upper": 0., "integral": None}
    epsilon = tolerance_em/64
    def flatten(curves):
        points, visited = [curves[0][0]], 0
        for curve in curves:
            if norm(sub(points[-1], curve[0])) > EPS: raise RepairError("incompatible_correspondence")
            stack = [(curve, 0)]
            while stack:
                c, depth = stack.pop(); visited += 1
                if visited > budget: raise RepairError("unresolved_deviation", "Native outline subdivision budget exceeded.")
                chord = tuple(add(c[0], mul(sub(c[-1], c[0]), i/3)) for i in range(4))
                flat = max(norm(sub(a, b)) for a, b in zip(c, chord)) + EPS
                if flat <= epsilon:
                    if norm(sub(c[-1], points[-1])) <= EPS:
                        raise RepairError("unresolved_deviation", "A flattened segment has unresolved length.")
                    points.append(c[-1])
                else:
                    if depth >= 24: raise RepairError("unresolved_deviation")
                    a, b = split(c); stack.extend(((b, depth+1), (a, depth+1)))
        distances = [0.]
        for a, b in zip(points, points[1:]): distances.append(distances[-1] + norm(sub(b, a)))
        if distances[-1] <= EPS: raise RepairError("undefined_curvature")
        return points, tuple(v/distances[-1] for v in distances)
    lp, lt = flatten(left); rp, rt = flatten(right)
    i = j = 0; maximum = 0.
    for t in sorted(set((*lt, *rt))):
        while i < len(lt)-2 and lt[i+1] < t: i += 1
        while j < len(rt)-2 and rt[j+1] < t: j += 1
        a = add(lp[i], mul(sub(lp[i+1], lp[i]), (t-lt[i])/(lt[i+1]-lt[i])))
        b = add(rp[j], mul(sub(rp[j+1], rp[j]), (t-rt[j])/(rt[j+1]-rt[j])))
        maximum = max(maximum, norm(sub(a, b)))
    upper = maximum + 2*epsilon + EPS*max(1., *(norm(p) for p in (*lp, *rp)))
    if upper > tolerance_em:
        raise RepairError("excess_deviation", "Native transition exceeds the tolerance, or its continuous bound cannot certify it.")
    return {"upper": upper, "integral": None}
