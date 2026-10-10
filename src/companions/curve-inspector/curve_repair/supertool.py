# Copyright 2019 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Modified Python adaptation of SuperTool's harmonization/Tunni computations.

Source: ccc71ee39ef72c0c34267410d2b9ebee454ec98c. Modifications: finite and
degeneracy guards, optional explicit G1 alignment and separate balancing.
Vector helpers are independently implemented; no SCGlyphsLib code is included.
"""
from __future__ import annotations
import math
from itertools import product
from .geometry import EPS, RepairError, add, sub, mul, dot, det, norm, finite_curve, diagnose_join
from .geometry import integrated_difference


def intersection(a, b, c, d):
    u, v = sub(b, a), sub(d, c)
    denominator = det(u, v)
    if norm(u) <= EPS or norm(v) <= EPS or abs(denominator) <= EPS * norm(u) * norm(v):
        raise RepairError("degenerate_intersection", "Parallel or degenerate tangent construction.")
    result = add(a, mul(u, det(sub(c, a), v) / denominator))
    if not all(math.isfinite(x) for x in result):
        raise RepairError("degenerate_intersection")
    return result


def harmonize(left, right):
    finite_curve(left); finite_curve(right)
    left, right = list(left), list(right)
    diagnostic = diagnose_join(left, right)
    if diagnostic["g2"]:
        return tuple(left), tuple(right)
    join = left[3]
    incoming, outgoing = sub(join, left[2]), sub(right[1], join)
    a, b = norm(incoming), norm(outgoing)
    if not diagnostic["g1"]:
        # Explicit bounded handle route: oriented tangent bisector, then the
        # upstream harmonization. Acceptance still checks the original outline.
        if dot(incoming, outgoing) <= 0:
            raise RepairError("opposite_tangents")
        direction = add(mul(incoming, 1/a), mul(outgoing, 1/b))
        direction = mul(direction, 1/norm(direction))
        left[2] = sub(join, mul(direction, dot(incoming, direction)))
        right[1] = add(join, mul(direction, dot(outgoing, direction)))
    direction = mul(sub(join, left[2]), 1/norm(sub(join, left[2])))
    n_left, n_right = det(direction, sub(left[1], join)), det(direction, sub(right[2], join))
    if n_left * n_right <= 0 or min(abs(n_left), abs(n_right)) <= EPS:
        raise RepairError("curvature_sign_conflict", "No well-conditioned positive G2 handle solution.")
    crossing = intersection(left[1], left[2], right[1], right[2])
    denominators = norm(sub(left[2], crossing)), norm(sub(right[1], right[2]))
    if min(denominators) <= EPS:
        raise RepairError("degenerate_intersection")
    p0 = norm(sub(left[1], left[2])) / denominators[0]
    p1 = norm(sub(crossing, right[1])) / denominators[1]
    ratio = math.sqrt(p0 * p1)
    if not math.isfinite(ratio) or ratio <= EPS:
        raise RepairError("degenerate_intersection")
    t = ratio / (ratio + 1)
    candidate = add(mul(left[2], 1-t), mul(right[1], t))
    translation = sub(join, candidate)
    left[2], right[1] = add(left[2], translation), add(right[1], translation)
    if not diagnose_join(left, right)["g2"]:
        raise RepairError("continuity_failed", "The final handles do not establish G2.")
    return tuple(left), tuple(right)


def balance(curve):
    finite_curve(curve)
    p0, p1, p2, p3 = curve
    crossing = intersection(p0, p1, p2, p3)
    start, end = norm(sub(p0, crossing)), norm(sub(p3, crossing))
    if min(start, end) <= EPS:
        raise RepairError("degenerate_intersection")
    x, y = norm(sub(p0, p1))/start, norm(sub(p2, p3))/end
    if (x > 1 and y > 1) or (x < .01 and y < .01):
        raise RepairError("tunni_unsupported", "Upstream balancing excludes this handle distribution.")
    q = (x+y)/2
    return p0, add(p0, mul(sub(crossing, p0), q)), add(p3, mul(sub(crossing, p3), q)), p3


def fit_grid(left, right, original_left, original_right, step, origin=(0, 0)):
    """Choose a nearby grid-realizable G2 candidate, never change the font grid.

    The upstream continuous candidate is retained when the grid is disabled.
    Search only floor/ceil coordinates of its two join handles (≤16 pairs),
    ordered by the exact original-to-candidate integral. No optimum is claimed.
    """
    if step <= 0: return left, right
    def choices(point):
        return tuple(product(*[tuple(sorted({math.floor((v+offset)/step)*step-offset,
                                             math.ceil((v+offset)/step)*step-offset})) for v, offset in zip(point, origin)]))
    candidates = []
    for incoming, outgoing in product(choices(left[2]), choices(right[1])):
        a, b = (*left[:2], incoming, left[3]), (right[0], outgoing, *right[2:])
        try:
            if not diagnose_join(a, b)["g2"]: continue
        except RepairError:
            continue
        score = integrated_difference(original_left, a) + integrated_difference(original_right, b)
        candidates.append((score, a, b))
    if not candidates: raise RepairError("grid_incompatible", "No nearby G2 handle candidate survives the font grid; use native stars or explicitly disable the grid yourself.")
    _, a, b = min(candidates)
    return a, b
