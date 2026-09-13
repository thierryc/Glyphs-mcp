"""Small, dependency-free cubic Bézier measurements and display geometry."""

from __future__ import annotations

import math
from typing import Any, Iterable


Point = tuple[float, float]
Cubic = tuple[Point, Point, Point, Point]

DEFAULT_SAMPLES_PER_CURVE = 51
MIN_SAMPLES_PER_CURVE = 9
DEFAULT_STROKE_LIMIT = 2000
DEFAULT_LENGTH_SCALE = 0.010
DEFAULT_MAX_LENGTH_EM = 0.12
HARD_MAX_LENGTH_EM = 0.25
ZERO_CURVATURE_EPSILON = 1.0e-12
OVERLAY_ALPHA = 0.65

POSITIVE_RGBA = (0.00, 0.62, 0.62, OVERLAY_ALPHA)
NEGATIVE_RGBA = (0.86, 0.18, 0.55, OVERLAY_ALPHA)


def _finite_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def _positive_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return int(default)
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _requested_sample_count(value: Any) -> int:
    count = max(MIN_SAMPLES_PER_CURVE, _positive_int(value, DEFAULT_SAMPLES_PER_CURVE))
    return count + 1 if count % 2 == 0 else count


def choose_sample_count(
    segment_count: int,
    *,
    requested: int = DEFAULT_SAMPLES_PER_CURVE,
    stroke_limit: int = DEFAULT_STROKE_LIMIT,
) -> tuple[int, bool]:
    """Return the previous Inspector's odd, deterministic sample count."""

    requested_count = _requested_sample_count(requested)
    segments = _positive_int(segment_count, 0)
    limit = _positive_int(stroke_limit, DEFAULT_STROKE_LIMIT)
    if segments <= 0 or limit <= 0 or segments * requested_count <= limit:
        return requested_count, False
    reduced = max(MIN_SAMPLES_PER_CURVE, limit // segments)
    if reduced % 2 == 0:
        reduced -= 1
    reduced = max(MIN_SAMPLES_PER_CURVE, reduced)
    return min(requested_count, reduced), reduced < requested_count


def overlay_line_widths(scale: float) -> tuple[float, float]:
    """Return the proven teeth and envelope widths for the current zoom."""

    zoom = max(_finite_float(scale, 1.0), 1.0e-6)
    return max(0.35, 0.75 * zoom**-0.9), max(0.5, 1.15 * zoom**-0.9)


def cubic_point(curve: Cubic, t: float) -> Point:
    p0, p1, p2, p3 = curve
    u = 1.0 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
    )


def _derivatives(curve: Cubic, t: float) -> tuple[Point, Point]:
    p0, p1, p2, p3 = curve
    u = 1.0 - t
    first = (
        3 * u * u * (p1[0] - p0[0]) + 6 * u * t * (p2[0] - p1[0]) + 3 * t * t * (p3[0] - p2[0]),
        3 * u * u * (p1[1] - p0[1]) + 6 * u * t * (p2[1] - p1[1]) + 3 * t * t * (p3[1] - p2[1]),
    )
    second = (
        6 * u * (p2[0] - 2 * p1[0] + p0[0]) + 6 * t * (p3[0] - 2 * p2[0] + p1[0]),
        6 * u * (p2[1] - 2 * p1[1] + p0[1]) + 6 * t * (p3[1] - 2 * p2[1] + p1[1]),
    )
    return first, second


def curvature(curve: Cubic, t: float) -> float:
    first, second = _derivatives(curve, t)
    speed = math.hypot(first[0], first[1])
    if speed <= ZERO_CURVATURE_EPSILON or not math.isfinite(speed):
        return 0.0
    value = (first[0] * second[1] - first[1] * second[0]) / speed**3
    return value if math.isfinite(value) else 0.0


def analyze_cubic(curve: Cubic, *, samples: int = 25) -> dict:
    count = max(5, min(int(samples), 129))
    measured = []
    signs = []
    for index in range(count):
        t = index / (count - 1)
        value = curvature(curve, t)
        measured.append((abs(value), value, t))
        if abs(value) > ZERO_CURVATURE_EPSILON:
            signs.append(1 if value > 0 else -1)
    maximum, signed, t = max(measured, key=lambda item: item[0])
    inflections = sum(left != right for left, right in zip(signs, signs[1:]))
    return {
        "point": cubic_point(curve, t),
        "t": t,
        "curvature": signed,
        "absoluteCurvature": maximum,
        "inflections": inflections,
    }


def analyze_cubics(curves: Iterable[Cubic], *, samples: int = 25) -> list[dict]:
    return [
        {"segment": index, **analyze_cubic(curve, samples=samples)}
        for index, curve in enumerate(curves)
    ]


def _flush_envelope(
    envelopes: list[dict], points: list[Point], sign: str, segment: int
) -> None:
    if len(points) >= 2:
        envelopes.append(
            {"segment": int(segment), "sign": str(sign), "points": list(points)}
        )
    points.clear()


def build_curvature_comb(
    curves: Iterable[Cubic],
    *,
    upm: float = 1000.0,
    samples: int = DEFAULT_SAMPLES_PER_CURVE,
    stroke_limit: int = DEFAULT_STROKE_LIMIT,
    length_scale: float = DEFAULT_LENGTH_SCALE,
    max_length_em: float = DEFAULT_MAX_LENGTH_EM,
) -> dict:
    """Return bounded teeth and connected endpoint envelopes in font units."""

    curve_values = list(curves or [])
    units = _finite_float(upm, 1000.0)
    if units <= 0.0:
        units = 1000.0
    limit = _positive_int(stroke_limit, DEFAULT_STROKE_LIMIT)
    length_factor = _finite_float(length_scale, DEFAULT_LENGTH_SCALE)
    if length_factor < 0.0:
        length_factor = DEFAULT_LENGTH_SCALE
    maximum_em = min(abs(_finite_float(max_length_em, DEFAULT_MAX_LENGTH_EM)), HARD_MAX_LENGTH_EM)
    maximum_length = units * maximum_em
    count, _sampling_reduced = choose_sample_count(
        len(curve_values), requested=samples, stroke_limit=limit
    )

    strokes: list[dict] = []
    envelopes: list[dict] = []
    cap_reached = False
    for segment, curve in enumerate(curve_values):
        envelope_points: list[Point] = []
        envelope_sign = ""
        for index in range(count):
            if len(strokes) >= limit:
                cap_reached = True
                _flush_envelope(envelopes, envelope_points, envelope_sign, segment)
                break
            t = index / (count - 1)
            point = cubic_point(curve, t)
            first, second = _derivatives(curve, t)
            speed = math.hypot(first[0], first[1])
            if speed <= ZERO_CURVATURE_EPSILON or not math.isfinite(speed):
                _flush_envelope(envelopes, envelope_points, envelope_sign, segment)
                envelope_sign = ""
                continue
            signed = (first[0] * second[1] - first[1] * second[0]) / speed**3
            if not math.isfinite(signed) or abs(signed) <= ZERO_CURVATURE_EPSILON:
                _flush_envelope(envelopes, envelope_points, envelope_sign, segment)
                envelope_sign = ""
                continue
            length = min(maximum_length, abs(signed) * units * units * length_factor)
            normal = (first[1] / speed, -first[0] / speed)
            start = (float(point[0]), float(point[1]))
            end = (
                start[0] + normal[0] * length,
                start[1] + normal[1] * length,
            )
            sign = "positive" if signed > 0.0 else "negative"
            if envelope_sign and sign != envelope_sign:
                _flush_envelope(envelopes, envelope_points, envelope_sign, segment)
            envelope_sign = sign
            envelope_points.append(end)
            strokes.append(
                {
                    "segment": int(segment),
                    "t": float(t),
                    "sign": sign,
                    "start": start,
                    "end": end,
                }
            )
        _flush_envelope(envelopes, envelope_points, envelope_sign, segment)
        if cap_reached:
            break

    return {
        "samplesPerCurve": int(count),
        "strokeCount": len(strokes),
        "strokeLimit": int(limit),
        "strokeCapReached": bool(cap_reached),
        "strokes": strokes,
        "envelopes": envelopes,
    }
