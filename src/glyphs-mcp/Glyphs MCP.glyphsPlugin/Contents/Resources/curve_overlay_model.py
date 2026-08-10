"""Pure signed-curvature comb geometry for native and image renderers.

The module deliberately imports neither GlyphsApp nor AppKit/PyObjC.  It turns
plain path snapshots into bounded line segments and envelope polylines that a
host-specific renderer can draw.  Signed curvature itself is supplied by the
shared clean-room cubic engine.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

import outline_geometry_engine


Point = Tuple[float, float]

OVERLAY_DATA_VERSION = 1
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

LEGEND = {
    "signedCurvatureFormula": "cross(B'(t), B''(t)) / |B'(t)|^3",
    "normalConvention": "comb magnitude along right normal (dy, -dx) / |B'(t)|; sign controls color only",
    "pathDirectionRule": "placement follows the path right normal; reversing path direction reverses the display side, so correctly wound counters draw into counter space",
    "zeroCurvature": "not drawn",
    "entries": [
        {
            "sign": "positive",
            "direction": "right normal placement; teal sign color",
            "color": "#009E9E",
            "rgba": list(POSITIVE_RGBA),
        },
        {
            "sign": "negative",
            "direction": "right normal placement; pink sign color",
            "color": "#DB2E8C",
            "rgba": list(NEGATIVE_RGBA),
        },
    ],
}


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
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)
    return max(0, number)


def _requested_sample_count(value: Any) -> int:
    count = _positive_int(value, DEFAULT_SAMPLES_PER_CURVE)
    count = max(MIN_SAMPLES_PER_CURVE, count)
    if count % 2 == 0:
        count += 1
    return count


def _segment_count(paths: Sequence[Dict[str, Any]]) -> int:
    count = 0
    for path in list(paths or []):
        nodes = list(path.get("nodes") or [])
        count += len(
            outline_geometry_engine.cubic_segment_end_indices(
                nodes,
                closed=bool(path.get("closed", True)),
            )
        )
    return int(count)


def choose_sample_count(
    segment_count: int,
    *,
    requested: int = DEFAULT_SAMPLES_PER_CURVE,
    stroke_limit: int = DEFAULT_STROKE_LIMIT,
) -> Tuple[int, bool]:
    """Return an odd deterministic sample count and whether it was reduced."""

    requested_count = _requested_sample_count(requested)
    segments = max(0, _positive_int(segment_count, 0))
    limit = _positive_int(stroke_limit, DEFAULT_STROKE_LIMIT)
    if segments <= 0 or limit <= 0 or segments * requested_count <= limit:
        return requested_count, False

    reduced = max(MIN_SAMPLES_PER_CURVE, limit // segments)
    if reduced % 2 == 0:
        reduced -= 1
    reduced = max(MIN_SAMPLES_PER_CURVE, reduced)
    return min(requested_count, reduced), reduced < requested_count


def _flush_envelope(
    envelopes: List[Dict[str, Any]],
    points: List[Point],
    sign: str,
    segment_end_node_index: int,
) -> None:
    if len(points) >= 2:
        envelopes.append(
            {
                "sign": str(sign),
                "segmentEndNodeIndex": int(segment_end_node_index),
                "points": list(points),
            }
        )
    points[:] = []


def build_curve_overlay(
    paths: Sequence[Dict[str, Any]],
    *,
    upm: float = 1000.0,
    samples_per_curve: int = DEFAULT_SAMPLES_PER_CURVE,
    stroke_limit: int = DEFAULT_STROKE_LIMIT,
    length_scale: float = DEFAULT_LENGTH_SCALE,
    max_length_em: float = DEFAULT_MAX_LENGTH_EM,
    component_count_omitted: int = 0,
) -> Dict[str, Any]:
    """Build bounded comb teeth and curvature-envelope polylines.

    ``paths`` contains dictionaries with ``nodes`` and ``closed`` keys plus an
    optional documented ``direction`` value (``-1`` counterclockwise, ``1``
    clockwise). Teeth and envelope points are returned in font units. Display
    placement uses curvature magnitude along the path's right normal, matching
    the outside-of-glyph convention used by SpeedPunk: correctly wound outer
    contours draw outward and correctly wound counters draw into their white
    interior. Signed curvature still controls teal/pink color and envelope
    splitting. Envelope runs never cross a segment boundary, sign change,
    zero-curvature sample, or degenerate tangent.
    """

    path_values = list(paths or [])
    upm_value = _finite_float(upm, 1000.0)
    if upm_value <= 0.0:
        upm_value = 1000.0
    limit = _positive_int(stroke_limit, DEFAULT_STROKE_LIMIT)
    length_factor = _finite_float(length_scale, DEFAULT_LENGTH_SCALE)
    if length_factor < 0.0:
        length_factor = DEFAULT_LENGTH_SCALE
    requested_max_em = abs(_finite_float(max_length_em, DEFAULT_MAX_LENGTH_EM))
    maximum_length_em = min(requested_max_em, HARD_MAX_LENGTH_EM)
    maximum_length = maximum_length_em * upm_value
    omitted_components = _positive_int(component_count_omitted, 0)

    segment_count = _segment_count(path_values)
    sample_count, sampling_reduced = choose_sample_count(
        segment_count,
        requested=samples_per_curve,
        stroke_limit=limit,
    )

    strokes: List[Dict[str, Any]] = []
    envelopes: List[Dict[str, Any]] = []
    degenerate_count = 0
    zero_count = 0
    clamped_count = 0
    cap_reached = False

    for path_index, path in enumerate(path_values):
        nodes = list(path.get("nodes") or [])
        closed = bool(path.get("closed", True))
        for end_index in outline_geometry_engine.cubic_segment_end_indices(nodes, closed=closed):
            segment = outline_geometry_engine.extract_cubic_segment(nodes, end_index, closed=closed)
            if not segment.get("ok"):
                continue

            envelope_points: List[Point] = []
            envelope_sign = ""
            samples = outline_geometry_engine.curvature_comb_samples(
                segment["points"],
                sample_count=sample_count,
            )
            for sample in samples:
                if len(strokes) >= limit:
                    cap_reached = True
                    _flush_envelope(envelopes, envelope_points, envelope_sign, end_index)
                    break

                curvature = sample.get("curvature")
                derivative = sample.get("derivative")
                speed = _finite_float(sample.get("speed"), 0.0)
                if curvature is None or derivative is None or speed <= ZERO_CURVATURE_EPSILON:
                    degenerate_count += 1
                    _flush_envelope(envelopes, envelope_points, envelope_sign, end_index)
                    envelope_sign = ""
                    continue

                curvature_value = _finite_float(curvature, 0.0)
                if abs(curvature_value) <= ZERO_CURVATURE_EPSILON:
                    zero_count += 1
                    _flush_envelope(envelopes, envelope_points, envelope_sign, end_index)
                    envelope_sign = ""
                    continue

                raw_length = abs(curvature_value) * upm_value * upm_value * length_factor
                length = min(maximum_length, raw_length)
                clamped = not math.isclose(length, raw_length, rel_tol=0.0, abs_tol=1.0e-12)
                if clamped:
                    clamped_count += 1

                normal = (
                    float(derivative[1]) / speed,
                    -float(derivative[0]) / speed,
                )
                start = (float(sample["point"][0]), float(sample["point"][1]))
                end = (
                    start[0] + normal[0] * length,
                    start[1] + normal[1] * length,
                )
                sign = "positive" if curvature_value > 0.0 else "negative"
                if envelope_sign and sign != envelope_sign:
                    _flush_envelope(envelopes, envelope_points, envelope_sign, end_index)
                envelope_sign = sign
                envelope_points.append(end)
                strokes.append(
                    {
                        "pathIndex": int(path_index),
                        "segmentEndNodeIndex": int(end_index),
                        "t": float(sample.get("t", 0.0)),
                        "sign": sign,
                        "start": start,
                        "end": end,
                        "curvature": curvature_value,
                        "clamped": bool(clamped),
                    }
                )

            _flush_envelope(envelopes, envelope_points, envelope_sign, end_index)
            if cap_reached:
                break
        if cap_reached:
            break

    warnings: List[Dict[str, Any]] = []
    if sampling_reduced:
        warnings.append(
            {
                "code": "sampling_reduced",
                "requestedSamplesPerCurve": _requested_sample_count(samples_per_curve),
                "samplesPerCurve": int(sample_count),
            }
        )
    if cap_reached:
        warnings.append({"code": "stroke_cap_reached", "strokeLimit": int(limit)})
    if clamped_count:
        warnings.append({"code": "comb_length_clamped", "sampleCount": int(clamped_count)})
    if degenerate_count:
        warnings.append({"code": "degenerate_tangent", "sampleCount": int(degenerate_count)})
    if omitted_components:
        warnings.append({"code": "components_omitted", "componentCount": int(omitted_components)})

    return {
        "overlayDataVersion": OVERLAY_DATA_VERSION,
        "signed": True,
        "samplesPerCurve": int(sample_count),
        "requestedSamplesPerCurve": _requested_sample_count(samples_per_curve),
        "strokeLimit": int(limit),
        "strokeCount": len(strokes),
        "strokeCapReached": bool(cap_reached),
        "segmentCount": int(segment_count),
        "componentCountOmitted": int(omitted_components),
        "degenerateSampleCount": int(degenerate_count),
        "zeroCurvatureSampleCount": int(zero_count),
        "clampedStrokeCount": int(clamped_count),
        "lengthScale": float(length_factor),
        "combLengthClampEm": float(maximum_length_em),
        "hardCombLengthClampEm": float(HARD_MAX_LENGTH_EM),
        "strokes": strokes,
        "envelopes": envelopes,
        "legend": LEGEND,
        "warnings": warnings,
    }


__all__ = [
    "DEFAULT_LENGTH_SCALE",
    "DEFAULT_MAX_LENGTH_EM",
    "DEFAULT_SAMPLES_PER_CURVE",
    "DEFAULT_STROKE_LIMIT",
    "HARD_MAX_LENGTH_EM",
    "LEGEND",
    "NEGATIVE_RGBA",
    "OVERLAY_ALPHA",
    "OVERLAY_DATA_VERSION",
    "POSITIVE_RGBA",
    "build_curve_overlay",
    "choose_sample_count",
]
