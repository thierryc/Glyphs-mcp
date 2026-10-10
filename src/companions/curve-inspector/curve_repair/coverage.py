"""Declared multi-axis coverage; preflight before copying or trial mutation."""
from __future__ import annotations
from itertools import product
import math
from .geometry import RepairError

MAX_LOCATIONS = 4096


def locations(master_locations, *, special_locations=(), configured=(), boundaries=(), region=None):
    masters = tuple(tuple(float(v) for v in p) for p in master_locations)
    if not masters:
        raise RepairError("coverage_incomplete", "No master locations available.")
    dimensions = len(masters[0])
    specials = tuple(tuple(float(v) for v in p) for p in special_locations)
    extra = (*specials, *(tuple(float(v) for v in p) for p in configured))
    if any(len(p) != dimensions or any(not math.isfinite(v) for v in p) for p in (*masters, *extra)):
        raise RepairError("invalid_designspace")
    bounds = tuple((min(p[i] for p in masters), max(p[i] for p in masters)) for i in range(dimensions))
    if region is not None:
        region = tuple(tuple(float(v) for v in r) for r in region)
        if len(region) != dimensions or any(len(r) != 2 or not all(math.isfinite(v) for v in r)
                                          or r[0] > r[1] or r[0] < b[0] or r[1] > b[1]
                                          for r, b in zip(region, bounds)):
            raise RepairError("invalid_region", "The explicit region must lie inside the master bounds.")
        bounds = region
    def inside(p): return all(low <= v <= high for v, (low, high) in zip(p, bounds))
    lattice, interleaved = [], []
    for axis, (low, high) in enumerate(bounds):
        breaks = {low, high}
        # Configured instances are mandatory probes, not interpolation-cell boundaries.
        breaks.update(p[axis] for p in (*masters, *specials) if low <= p[axis] <= high)
        for boundary_axis, value in boundaries:
            if boundary_axis == axis and low <= value <= high:
                breaks.add(float(value))
        ordered = sorted(breaks)
        if low == high:
            lattice.append((low,)); interleaved.append((low,)); continue
        standard, independent = set(), set()
        for start, end in zip(ordered, ordered[1:]):
            standard.update(start + (end-start)*t for t in (0, .25, .5, .75, 1))
            independent.update(start + (end-start)*t for t in (.125, .375, .625, .875))
        for boundary_axis, value in boundaries:
            if boundary_axis != axis or not low <= value <= high:
                continue
            epsilon = (high-low)*1e-6
            standard.update(max(low, min(high, value+delta)) for delta in (-epsilon, 0, epsilon))
        lattice.append(tuple(sorted(standard))); interleaved.append(tuple(sorted(independent)))
    # Fixed axes overlap in both sets; varying axes do not, except boundary
    # probes. The exact union is checked after the conservative preflight.
    standard_count = math.prod(map(len, lattice))
    independent_count = math.prod(map(len, interleaved))
    if max(standard_count, independent_count) > MAX_LOCATIONS:
        raise RepairError("location_budget_exceeded", "More than 4096 locations; choose an explicit narrower axis region.")
    result = set(product(*lattice)) | set(product(*interleaved))
    result.update(p for p in (*masters, *extra) if inside(p))
    if len(result) > MAX_LOCATIONS:
        raise RepairError("location_budget_exceeded", "More than 4096 locations; choose an explicit narrower axis region.")
    return {"locations": tuple(sorted(result)), "region": bounds, "complete": True,
            "requested": len(result), "evaluated": 0, "limit": MAX_LOCATIONS,
            "evidence": "sampled-native; continuous bounds apply only to each corresponding cubic pair"}
