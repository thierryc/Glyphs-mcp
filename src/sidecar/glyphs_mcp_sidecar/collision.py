"""Bounded, two-pass horizontal clearance policy over native intersections."""

import math

from .spacing import bounds


HEIGHTS = (.05, .15, .35, .65, .75)
CLAIM = "Detect and correct measured horizontal collisions; unsampled heights and optical kerning are not guaranteed."


def validate_options(raw):
    defaults = {"pairs": [], "masters": [], "direction": "LTR", "targetGap": 5.0, "denseStep": 10.0}
    if not isinstance(raw, dict) or set(raw) - set(defaults):
        raise ValueError("unknown kerning collision options")
    options = {**defaults, **raw}
    pairs = options["pairs"]
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 3000:
        raise ValueError("pairs must contain 1-3000 explicit glyph-name pairs")
    if any(not isinstance(p, list) or len(p) != 2 or any(not isinstance(n, str) or not n.strip() for n in p) for p in pairs):
        raise ValueError("each pair requires two non-empty glyph names")
    if len({tuple(p) for p in pairs}) != len(pairs):
        raise ValueError("pairs must be unique")
    masters = options["masters"]
    if not isinstance(masters, list) or len(masters) > 100 or any(not isinstance(m, str) or not m for m in masters) or len(set(masters)) != len(masters):
        raise ValueError("masters must contain unique master IDs")
    if options["direction"] != "LTR":
        raise ValueError("the horizontal collision workflow currently supports LTR pairs")
    for key, low, high in (("targetGap", 0, 1000), ("denseStep", .1, 100)):
        number = options[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not low <= number <= high:
            raise ValueError(key + " is outside the supported finite range")
    return options


def measure(left, right, adjustment, *, target_gap=5, dense_step=10):
    lb, rb = bounds(left), bounds(right)
    low, high = max(lb[1], rb[1]), min(lb[1] + lb[3], rb[1] + rb[3])
    if high <= low:
        return None
    if (high - low) / dense_step > 4096:
        raise ValueError("dense scan exceeds 4096 heights")

    def edge(layer, rect, y, index):
        hits = list(layer.intersectionsBetweenPoints((rect[0] - 1, y), (rect[0] + rect[2] + 1, y), components=True) or [])
        if len(hits) < 4:
            return None
        return float(hits[index].x)

    def scan(heights):
        results = []
        for y in heights:
            l, r = edge(left, lb, y, -2), edge(right, rb, y, 1)
            if l is not None and r is not None:
                results.append((float(left.width) + adjustment + r - l, y))
        return results

    coarse = scan(low + t * (high - low) for t in HEIGHTS)
    coarse_min = min((gap for gap, _ in coarse), default=None)
    refined = coarse_min is None or coarse_min <= target_gap + max(10, dense_step)
    samples = list(coarse)
    if refined:
        samples += scan(low + i * dense_step for i in range(math.floor((high - low) / dense_step) + 1))
    if not samples:
        return None
    gap, y = min(samples)
    return {"coarseGap": coarse_min, "minGap": gap, "worstY": y, "refined": refined,
            "sampleCount": len(samples), "denseStep": dense_step, "yRange": [low, high]}
