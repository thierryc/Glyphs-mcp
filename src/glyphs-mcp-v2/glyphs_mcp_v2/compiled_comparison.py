"""Format-aware comparison profiles for compiled OpenType binaries."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


FORMAT_COMPARISON_PROFILES: Mapping[str, Mapping[str, Any]] = {
    "truetype_behavioral": {
        "outlineFormats": ("glyf",),
        "topologyRequired": False,
        "tolerances": {
            "advanceWidth": 0.0,
            "verticalAdvance": 0.0,
            "outlineDistance": 1.0,
        },
    },
    "cff_contour": {
        "outlineFormats": ("CFF", "CFF2"),
        "topologyRequired": True,
        "tolerances": {
            "advanceWidth": 0.0,
            "verticalAdvance": 0.0,
            "coordinateDelta": 1.0,
        },
    },
}


def _outline_format(font: Any) -> str:
    if "glyf" in font:
        return "glyf"
    if "CFF2" in font:
        return "CFF2"
    if "CFF " in font:
        return "CFF"
    return "unknown"


def _profile_name(left_format: str, right_format: str) -> str | None:
    pair = {left_format, right_format}
    if pair == {"glyf"}:
        return "truetype_behavioral"
    if pair.issubset({"CFF", "CFF2"}):
        return "cff_contour"
    return None


def _load_font(path: str | Path, location: Mapping[str, float] | None) -> tuple[Any, str, bool]:
    try:
        from fontTools.ttLib import TTFont
    except ImportError as exc:  # pragma: no cover - release environment contract
        raise RuntimeError("compiled comparison requires FontTools") from exc
    font = TTFont(str(path), recalcBBoxes=False, recalcTimestamp=False)
    outline_format = _outline_format(font)
    variable = "fvar" in font
    if variable:
        try:
            from fontTools.varLib.instancer import instantiateVariableFont
        except ImportError as exc:  # pragma: no cover - release environment contract
            font.close()
            raise RuntimeError("variable comparison requires FontTools instancer") from exc
        requested = dict(location or {})
        for axis in font["fvar"].axes:
            requested.setdefault(str(axis.axisTag), float(axis.defaultValue))
        instantiated = instantiateVariableFont(font, requested, inplace=False)
        font.close()
        font = instantiated
    return font, outline_format, variable


def _cmap(font: Any) -> dict[int, str]:
    result: dict[int, str] = {}
    table = font.get("cmap")
    for subtable in getattr(table, "tables", ()):
        if getattr(subtable, "isUnicode", lambda: False)():
            result.update({int(codepoint): str(name) for codepoint, name in subtable.cmap.items()})
    return result


def _metric_map(font: Any, table_name: str) -> Mapping[str, tuple[int, int]]:
    table = font.get(table_name)
    metrics = getattr(table, "metrics", {}) if table is not None else {}
    return {
        str(name): (int(value[0]), int(value[1]))
        for name, value in dict(metrics).items()
    }


def _maximum_metric_delta(
    left: Mapping[str, tuple[int, int]],
    right: Mapping[str, tuple[int, int]],
    glyphs: Iterable[str],
) -> tuple[float, list[dict[str, Any]]]:
    maximum = 0.0
    mismatches: list[dict[str, Any]] = []
    for name in glyphs:
        if name not in left or name not in right:
            continue
        delta = abs(float(left[name][0]) - float(right[name][0]))
        maximum = max(maximum, delta)
        if delta:
            mismatches.append(
                {
                    "glyph": name,
                    "expected": left[name][0],
                    "observed": right[name][0],
                    "absoluteDelta": delta,
                }
            )
    return maximum, mismatches


class _SamplingPen:
    """Small segment sampler with component decomposition through glyph sets."""

    def __init__(self, glyph_set: Any, *, steps: int = 12) -> None:
        from fontTools.pens.basePen import BasePen

        class Pen(BasePen):
            def __init__(inner_self) -> None:
                super().__init__(glyph_set)
                inner_self.contours: list[list[tuple[float, float]]] = []
                inner_self.current: list[tuple[float, float]] | None = None

            def _moveTo(inner_self, point: Sequence[float]) -> None:
                inner_self.current = [(float(point[0]), float(point[1]))]
                inner_self.contours.append(inner_self.current)

            def _lineTo(inner_self, point: Sequence[float]) -> None:
                if inner_self.current is not None:
                    inner_self.current.append((float(point[0]), float(point[1])))

            def _curveToOne(inner_self, p1, p2, p3) -> None:
                p0 = inner_self._getCurrentPoint()
                if p0 is None or inner_self.current is None:
                    return
                for index in range(1, steps + 1):
                    t = index / steps
                    u = 1.0 - t
                    inner_self.current.append(
                        (
                            u**3 * p0[0]
                            + 3 * u * u * t * p1[0]
                            + 3 * u * t * t * p2[0]
                            + t**3 * p3[0],
                            u**3 * p0[1]
                            + 3 * u * u * t * p1[1]
                            + 3 * u * t * t * p2[1]
                            + t**3 * p3[1],
                        )
                    )

            def _qCurveToOne(inner_self, p1, p2) -> None:
                p0 = inner_self._getCurrentPoint()
                if p0 is None or inner_self.current is None:
                    return
                for index in range(1, steps + 1):
                    t = index / steps
                    u = 1.0 - t
                    inner_self.current.append(
                        (
                            u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
                        )
                    )

            def _closePath(inner_self) -> None:
                if (
                    inner_self.current
                    and inner_self.current[-1] != inner_self.current[0]
                ):
                    inner_self.current.append(inner_self.current[0])
                inner_self.current = None

            def _endPath(inner_self) -> None:
                inner_self.current = None

        self.pen = Pen()

    @property
    def contours(self) -> list[list[tuple[float, float]]]:
        return self.pen.contours


def _sampled_contours(glyph_set: Any, name: str) -> list[list[tuple[float, float]]]:
    wrapper = _SamplingPen(glyph_set)
    glyph_set[name].draw(wrapper.pen)
    return wrapper.contours


def _resample_contour(
    points: Sequence[tuple[float, float]], count: int = 64
) -> list[tuple[float, float]]:
    if not points:
        return []
    if len(points) == 1:
        return [points[0]] * count
    lengths = [0.0]
    for left, right in zip(points, points[1:]):
        lengths.append(lengths[-1] + math.dist(left, right))
    total = lengths[-1]
    if total == 0:
        return [points[0]] * count
    result: list[tuple[float, float]] = []
    segment = 0
    for index in range(count):
        target = total * index / count
        while segment + 1 < len(lengths) and lengths[segment + 1] < target:
            segment += 1
        next_segment = min(segment + 1, len(points) - 1)
        span = lengths[next_segment] - lengths[segment]
        ratio = 0.0 if span == 0 else (target - lengths[segment]) / span
        left, right = points[segment], points[next_segment]
        result.append(
            (
                left[0] + (right[0] - left[0]) * ratio,
                left[1] + (right[1] - left[1]) * ratio,
            )
        )
    return result


def _cyclic_distance(
    left: Sequence[tuple[float, float]], right: Sequence[tuple[float, float]]
) -> float:
    if len(left) != len(right) or not left:
        return math.inf
    left_values = list(left)
    left_offset = min(
        range(len(left_values)), key=lambda index: left_values[index]
    )
    left_values = left_values[left_offset:] + left_values[:left_offset]
    best = math.inf
    for candidate in (list(right), list(reversed(right))):
        offset = min(range(len(candidate)), key=lambda index: candidate[index])
        candidate = candidate[offset:] + candidate[:offset]
        best = min(
            best,
            max(
                math.dist(expected, observed)
                for expected, observed in zip(left_values, candidate)
            ),
        )
    return best


def _topology_independent_distance(
    left: Sequence[Sequence[tuple[float, float]]],
    right: Sequence[Sequence[tuple[float, float]]],
) -> float | None:
    if len(left) != len(right):
        return None
    left = sorted(
        (_resample_contour(contour) for contour in left),
        key=lambda contour: min(contour) if contour else (0.0, 0.0),
    )
    right = sorted(
        (_resample_contour(contour) for contour in right),
        key=lambda contour: min(contour) if contour else (0.0, 0.0),
    )
    maximum = 0.0
    for left_contour, right_contour in zip(left, right):
        distance = _cyclic_distance(left_contour, right_contour)
        if not math.isfinite(distance):
            return None
        maximum = max(maximum, distance)
    return maximum


def _recording(glyph_set: Any, name: str) -> list[tuple[str, tuple[Any, ...]]]:
    from fontTools.pens.recordingPen import DecomposingRecordingPen

    pen = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(pen)
    return list(pen.value)


def _recording_signature(
    recording: Sequence[tuple[str, tuple[Any, ...]]]
) -> list[tuple[str, int]]:
    return [
        (operation, len(arguments)) for operation, arguments in recording
    ]


def _coordinates(value: Any) -> list[float]:
    result: list[float] = []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result.append(float(value))
    elif isinstance(value, (list, tuple)):
        for item in value:
            result.extend(_coordinates(item))
    return result


def _cff_coordinate_delta(
    left: Sequence[tuple[str, tuple[Any, ...]]],
    right: Sequence[tuple[str, tuple[Any, ...]]],
) -> tuple[bool, float | None]:
    left_signature = _recording_signature(left)
    right_signature = _recording_signature(right)
    if left_signature != right_signature:
        return False, None
    left_values = _coordinates(left)
    right_values = _coordinates(right)
    if len(left_values) != len(right_values):
        return False, None
    return True, max(
        (abs(expected - observed) for expected, observed in zip(left_values, right_values)),
        default=0.0,
    )


def compare_compiled_fonts(
    expected_path: str | Path,
    observed_path: str | Path,
    *,
    location: Mapping[str, float] | None = None,
    tolerances: Mapping[str, float] | None = None,
    glyph_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compare two binaries and report profile, tolerances, and observed maxima."""

    expected, expected_format, expected_variable = _load_font(expected_path, location)
    observed, observed_format, observed_variable = _load_font(observed_path, location)
    try:
        profile_name = _profile_name(expected_format, observed_format)
        if profile_name is None:
            return {
                "passed": False,
                "profile": None,
                "formats": {"expected": expected_format, "observed": observed_format},
                "blockers": ["outline_format_mismatch"],
            }
        profile = dict(FORMAT_COMPARISON_PROFILES[profile_name])
        resolved_tolerances = {
            **dict(profile["tolerances"]),
            **{str(name): float(value) for name, value in dict(tolerances or {}).items()},
        }
        expected_order = list(expected.getGlyphOrder())
        observed_order = list(observed.getGlyphOrder())
        selected = list(glyph_names or expected_order)
        missing_expected = sorted(set(selected) - set(expected_order))
        missing_observed = sorted(set(selected) - set(observed_order))
        comparable = [
            name
            for name in selected
            if name in expected_order and name in observed_order
        ]
        expected_hmtx = _metric_map(expected, "hmtx")
        observed_hmtx = _metric_map(observed, "hmtx")
        advance_delta, advance_mismatches = _maximum_metric_delta(
            expected_hmtx, observed_hmtx, comparable
        )
        expected_vmtx = _metric_map(expected, "vmtx")
        observed_vmtx = _metric_map(observed, "vmtx")
        vertical_delta, vertical_mismatches = _maximum_metric_delta(
            expected_vmtx, observed_vmtx, comparable
        )
        expected_glyphs = expected.getGlyphSet()
        observed_glyphs = observed.getGlyphSet()
        topology_mismatches: list[str] = []
        outline_mismatches: list[dict[str, Any]] = []
        maximum_outline_delta = 0.0
        unmeasured_outline_count = 0
        for name in comparable:
            if profile_name == "truetype_behavioral":
                left = _sampled_contours(expected_glyphs, name)
                right = _sampled_contours(observed_glyphs, name)
                if (
                    _recording_signature(_recording(expected_glyphs, name))
                    != _recording_signature(_recording(observed_glyphs, name))
                ):
                    topology_mismatches.append(name)
                delta = _topology_independent_distance(left, right)
            else:
                topology_equal, delta = _cff_coordinate_delta(
                    _recording(expected_glyphs, name),
                    _recording(observed_glyphs, name),
                )
                if not topology_equal:
                    topology_mismatches.append(name)
            if delta is None:
                unmeasured_outline_count += 1
                continue
            maximum_outline_delta = max(maximum_outline_delta, delta)
            tolerance_name = (
                "outlineDistance"
                if profile_name == "truetype_behavioral"
                else "coordinateDelta"
            )
            if delta > resolved_tolerances[tolerance_name]:
                outline_mismatches.append(
                    {
                        "glyph": name,
                        "observed": delta,
                        "tolerance": resolved_tolerances[tolerance_name],
                    }
                )
        cmap_equal = _cmap(expected) == _cmap(observed)
        topology_blocking = bool(
            profile["topologyRequired"] and topology_mismatches
        )
        blockers = []
        if missing_expected or missing_observed:
            blockers.append("glyph_coverage_mismatch")
        if not cmap_equal:
            blockers.append("cmap_mismatch")
        if advance_delta > resolved_tolerances["advanceWidth"]:
            blockers.append("advance_width_delta")
        if vertical_delta > resolved_tolerances["verticalAdvance"]:
            blockers.append("vertical_advance_delta")
        if topology_blocking:
            blockers.append("contour_topology_mismatch")
        if unmeasured_outline_count:
            blockers.append("outline_distance_unavailable")
        if outline_mismatches:
            blockers.append("outline_delta")
        outline_maximum_name = (
            "outlineDistance"
            if profile_name == "truetype_behavioral"
            else "coordinateDelta"
        )
        return {
            "passed": not blockers,
            "profile": {
                "name": profile_name,
                "topologyRequired": bool(profile["topologyRequired"]),
            },
            "formats": {
                "expected": expected_format,
                "observed": observed_format,
                "expectedVariable": expected_variable,
                "observedVariable": observed_variable,
            },
            "location": dict(location or {}),
            "tolerances": resolved_tolerances,
            "observedMaxima": {
                "advanceWidth": advance_delta,
                "verticalAdvance": vertical_delta,
                outline_maximum_name: maximum_outline_delta,
            },
            "glyphCount": len(comparable),
            "cmapEqual": cmap_equal,
            "topologyMismatchCount": len(topology_mismatches),
            "topologyMismatches": topology_mismatches[:100],
            "topologyMismatchesTruncated": len(topology_mismatches) > 100,
            "unmeasuredOutlineCount": unmeasured_outline_count,
            "metricMismatches": {
                "horizontal": advance_mismatches[:100],
                "vertical": vertical_mismatches[:100],
            },
            "outlineMismatches": outline_mismatches[:100],
            "missingGlyphs": {
                "expected": missing_expected[:100],
                "observed": missing_observed[:100],
            },
            "blockers": list(dict.fromkeys(blockers)),
        }
    finally:
        expected.close()
        observed.close()


__all__ = ["FORMAT_COMPARISON_PROFILES", "compare_compiled_fonts"]
