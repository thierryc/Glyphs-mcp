# encoding: utf-8

"""Clean-room kerning collision / gap measurement helpers.

This module is intentionally GlyphsApp-free at import time so it can be unit
tested outside of Glyphs. The MCP tools call into it from within Glyphs,
passing real GSFont/GSGlyph/GSLayer objects.

Core ideas:
  - Measure the minimum horizontal gap between two glyph outlines across their
    vertical overlap range, by sampling scanlines (y positions).
  - Use a BubbleKern-style scan strategy: a few normalized scan heights, with an
    optional dense refinement pass when near the target threshold.
  - Provide deterministic "bumper" recommendations: the minimal kerning
    loosening required to satisfy a minimum gap constraint.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_SCAN_HEIGHTS: Tuple[float, ...] = (0.05, 0.15, 0.35, 0.65, 0.75)


def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        value = getattr(obj, name)
        return value() if callable(value) else value
    except Exception:
        return default


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if callable(value):
            value = value()
    except Exception:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _round_half_away_from_zero(x: float) -> int:
    xf = float(x)
    if xf >= 0.0:
        return int(math.floor(xf + 0.5))
    return -int(math.floor(abs(xf) + 0.5))


def normalize_scan_mode(mode: str) -> Tuple[str, List[str]]:
    warnings: List[str] = []
    m = (mode or "").strip().lower()
    if m not in ("two_pass", "dense_only", "heights_only"):
        warnings.append("Invalid scan_mode '{}'; using 'two_pass'.".format(mode))
        m = "two_pass"
    return m, warnings


def normalize_scan_heights(heights: Optional[Sequence[float]]) -> Tuple[List[float], List[str]]:
    warnings: List[str] = []
    if not heights:
        return list(DEFAULT_SCAN_HEIGHTS), warnings

    out: List[float] = []
    for h in heights:
        try:
            hf = float(h)
        except Exception:
            continue
        if hf < 0.0 or hf > 1.0:
            warnings.append("scan_heights value {} out of range; ignored.".format(h))
            continue
        out.append(hf)

    if not out:
        warnings.append("No valid scan_heights provided; using defaults.")
        return list(DEFAULT_SCAN_HEIGHTS), warnings

    # Deterministic order; duplicates removed.
    out = sorted(set(out))
    return out, warnings


def should_refine_two_pass(*, quick_min_gap: Optional[float], target_gap: float, dense_step: float) -> bool:
    """Decide whether to run the dense refinement pass.

    Heuristic:
      - Always refine if quick min gap is None (no samples).
      - Refine if quick min gap is within a small margin above the target, or
        below it (near-miss / collision).
    """

    if quick_min_gap is None:
        return True

    try:
        margin = max(10.0, float(dense_step))
    except Exception:
        margin = 10.0
    return float(quick_min_gap) <= float(target_gap) + margin


def _point_x(pt: Any) -> Optional[float]:
    if pt is None:
        return None
    try:
        return float(pt.x)
    except Exception:
        pass
    try:
        return float(pt[0])
    except Exception:
        return None


def bounds_tuple(layer: Any) -> Optional[Tuple[float, float, float, float]]:
    """Return (min_x, max_x, min_y, max_y) for layer.bounds."""

    b = _safe_attr(layer, "bounds")
    if not b:
        return None

    origin = _safe_attr(b, "origin")
    size = _safe_attr(b, "size")
    if not origin or not size:
        return None

    ox = _coerce_float(_safe_attr(origin, "x"))
    oy = _coerce_float(_safe_attr(origin, "y"))
    sw = _coerce_float(_safe_attr(size, "width"))
    sh = _coerce_float(_safe_attr(size, "height"))
    if ox is None or oy is None or sw is None or sh is None:
        return None

    return (ox, ox + sw, oy, oy + sh)


def overlap_y_range(
    left_bounds: Tuple[float, float, float, float],
    right_bounds: Tuple[float, float, float, float],
) -> Optional[Tuple[float, float]]:
    _, _, ly0, ly1 = left_bounds
    _, _, ry0, ry1 = right_bounds
    y_min = max(float(ly0), float(ry0))
    y_max = min(float(ly1), float(ry1))
    if y_max <= y_min:
        return None
    return (y_min, y_max)


def _frange(y_min: float, y_max: float, step: float) -> List[float]:
    if step <= 0:
        step = 1.0
    out: List[float] = []
    y = float(y_min)
    stop = float(y_max) + 1e-9
    while y <= stop:
        out.append(y)
        y += step
    return out


def _measure_edges_at_y(
    layer: Any,
    y: float,
    include_components: bool,
    start_x: float,
    end_x: float,
) -> Tuple[Optional[float], Optional[float]]:
    """Return (left_edge_x, right_edge_x) using intersectionsBetweenPoints."""

    try:
        intersections = layer.intersectionsBetweenPoints((start_x, y), (end_x, y), components=include_components)
    except Exception:
        return (None, None)

    try:
        n = len(intersections)
    except Exception:
        return (None, None)

    # Per Glyphs docs: [0] start, [-1] end, [1] first intersection, [-2] last intersection.
    if n < 4:
        return (None, None)

    left = _point_x(intersections[1])
    right = _point_x(intersections[-2])
    return (left, right)


def _scanline_setup(bounds: Tuple[float, float, float, float]) -> Tuple[float, float]:
    min_x, max_x, _, _ = bounds
    return (float(min_x) - 1.0, float(max_x) + 1.0)


@dataclass(frozen=True)
class KerningSource:
    left_key: str | None
    right_key: str | None


def _string_keys_kerning(kerning_master: Any) -> Dict[str, Dict[str, Any]]:
    """Normalize kerning dict for stable string-key lookups."""

    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(kerning_master, dict):
        return out

    for lk, rv in kerning_master.items():
        if rv is None:
            continue
        try:
            lk_s = str(lk)
        except Exception:
            continue
        if lk_s not in out:
            out[lk_s] = {}
        if not isinstance(rv, dict):
            continue
        for rk, v in rv.items():
            try:
                rk_s = str(rk)
            except Exception:
                continue
            out[lk_s][rk_s] = v
    return out


def resolve_explicit_kerning_value(
    *,
    kerning_master: Dict[str, Dict[str, Any]] | Any,
    left_glyph_id: str | None,
    left_glyph_name: str,
    left_class_key: str | None,
    right_glyph_id: str | None,
    right_glyph_name: str,
    right_class_key: str | None,
) -> Tuple[float, KerningSource]:
    """Resolve kerning value + explicit source keys using precedence.

    Precedence:
      1) glyph–glyph
      2) glyph–rightClass
      3) leftClass–glyph
      4) leftClass–rightClass

    Notes:
      - Glyphs' internal kerning dict may use glyph IDs for exceptions.
      - Some environments/scripts may still have glyph names as keys; we try both.
    """

    kerning = _string_keys_kerning(kerning_master)

    left_glyph_keys = [k for k in (left_glyph_id, left_glyph_name) if isinstance(k, str) and k]
    right_glyph_keys = [k for k in (right_glyph_id, right_glyph_name) if isinstance(k, str) and k]

    def _lookup(lk: str, rk: str) -> Optional[float]:
        if lk not in kerning:
            return None
        if rk not in kerning[lk]:
            return None
        v = kerning[lk].get(rk)
        vf = _coerce_float(v)
        if vf is None:
            return None
        return float(vf)

    # 1) glyph–glyph
    for lk in left_glyph_keys:
        for rk in right_glyph_keys:
            v = _lookup(lk, rk)
            if v is not None:
                return v, KerningSource(left_key=lk, right_key=rk)

    # 2) glyph–rightClass
    if isinstance(right_class_key, str) and right_class_key:
        for lk in left_glyph_keys:
            v = _lookup(lk, right_class_key)
            if v is not None:
                return v, KerningSource(left_key=lk, right_key=right_class_key)

    # 3) leftClass–glyph
    if isinstance(left_class_key, str) and left_class_key:
        for rk in right_glyph_keys:
            v = _lookup(left_class_key, rk)
            if v is not None:
                return v, KerningSource(left_key=left_class_key, right_key=rk)

    # 4) leftClass–rightClass
    if (
        isinstance(left_class_key, str)
        and left_class_key
        and isinstance(right_class_key, str)
        and right_class_key
    ):
        v = _lookup(left_class_key, right_class_key)
        if v is not None:
            return v, KerningSource(left_key=left_class_key, right_key=right_class_key)

    return 0.0, KerningSource(left_key=None, right_key=None)


@dataclass(frozen=True)
class PairGapResult:
    min_gap: float
    worst_y: float | None
    band_min_gaps: List[float | None]
    sample_count: int
    refined: bool


def measure_pair_min_gap(
    *,
    left_layer: Any,
    right_layer: Any,
    kerning_value: float,
    scan_mode: str,
    scan_heights: Sequence[float],
    dense_step: float,
    bands: int,
    include_components: bool = True,
    target_gap: float = 0.0,
) -> Optional[PairGapResult]:
    """Measure min gap across y-overlap for a given kerning value.

    Returns None when measurement is impossible (no bounds/overlap/samples).
    """

    mode, _ = normalize_scan_mode(scan_mode)

    lb = bounds_tuple(left_layer)
    rb = bounds_tuple(right_layer)
    if not lb or not rb:
        return None

    overlap = overlap_y_range(lb, rb)
    if not overlap:
        return None
    y_min, y_max = overlap

    if bands <= 0:
        bands = 8

    left_width = _coerce_float(_safe_attr(left_layer, "width")) or 0.0
    shift = float(left_width) + float(kerning_value)

    l_start_x, l_end_x = _scanline_setup(lb)
    r_start_x, r_end_x = _scanline_setup(rb)

    heights, _ = normalize_scan_heights(scan_heights)
    quick_ys = [y_min + h * (y_max - y_min) for h in heights]

    def _band_index(y: float) -> int:
        if y_max <= y_min:
            return 0
        t = (float(y) - float(y_min)) / (float(y_max) - float(y_min))
        idx = int(math.floor(t * bands))
        return max(0, min(bands - 1, idx))

    def _measure(ys: Iterable[float]) -> Tuple[Optional[float], Optional[float], List[float | None], int]:
        min_gap = None
        worst_y = None
        band_mins: List[float | None] = [None for _ in range(bands)]
        samples = 0

        for y in ys:
            l_left, l_right = _measure_edges_at_y(
                left_layer,
                float(y),
                include_components=include_components,
                start_x=l_start_x,
                end_x=l_end_x,
            )
            r_left, r_right = _measure_edges_at_y(
                right_layer,
                float(y),
                include_components=include_components,
                start_x=r_start_x,
                end_x=r_end_x,
            )

            if l_right is None or r_left is None:
                continue

            gap = shift + float(r_left) - float(l_right)
            samples += 1

            b = _band_index(float(y))
            if band_mins[b] is None or gap < float(band_mins[b]):  # type: ignore[arg-type]
                band_mins[b] = float(gap)

            if min_gap is None or gap < float(min_gap):
                min_gap = float(gap)
                worst_y = float(y)

        return min_gap, worst_y, band_mins, samples

    # Pass 1: quick scan heights.
    q_min, q_worst, q_bands, q_samples = _measure(quick_ys)

    refined = False
    if mode == "heights_only":
        if q_min is None:
            return None
        return PairGapResult(
            min_gap=float(q_min),
            worst_y=q_worst,
            band_min_gaps=q_bands,
            sample_count=int(q_samples),
            refined=False,
        )

    if mode == "dense_only":
        ys = _frange(y_min, y_max, step=float(dense_step))
        d_min, d_worst, d_bands, d_samples = _measure(ys)
        if d_min is None:
            return None
        return PairGapResult(
            min_gap=float(d_min),
            worst_y=d_worst,
            band_min_gaps=d_bands,
            sample_count=int(d_samples),
            refined=True,
        )

    # two_pass
    if should_refine_two_pass(quick_min_gap=q_min, target_gap=float(target_gap), dense_step=float(dense_step)):
        ys = _frange(y_min, y_max, step=float(dense_step))
        d_min, d_worst, d_bands, d_samples = _measure(ys)
        if d_min is None:
            return None
        refined = True
        return PairGapResult(
            min_gap=float(d_min),
            worst_y=d_worst,
            band_min_gaps=d_bands,
            sample_count=int(d_samples),
            refined=True,
        )

    if q_min is None:
        return None
    return PairGapResult(
        min_gap=float(q_min),
        worst_y=q_worst,
        band_min_gaps=q_bands,
        sample_count=int(q_samples),
        refined=False,
    )


@dataclass(frozen=True)
class BumperSuggestion:
    bumper_delta: float
    recommended_exception: int


def compute_bumper_suggestion(
    *,
    kerning_value: float,
    measured_min_gap: float,
    target_gap: float,
    max_delta: int,
) -> BumperSuggestion:
    """Compute minimal loosening to reach target gap.

    The suggestion never tightens; it only increases the kerning value.
    """

    needed = max(0.0, float(target_gap) - float(measured_min_gap))
    clamped = min(float(needed), float(max_delta))
    recommended = float(kerning_value) + clamped

    # Kerning is integer font-units. For a collision guard we must not
    # accidentally under-apply due to rounding; use ceil to guarantee
    # recommended_exception >= recommended.
    recommended_int = int(math.ceil(float(recommended) - 1e-6))

    return BumperSuggestion(
        bumper_delta=float(clamped),
        recommended_exception=recommended_int,
    )


def glyph_unicode_char(glyph: Any) -> Optional[str]:
    """Return the single Unicode character for a glyph, if available."""

    uni = _safe_attr(glyph, "unicode")
    if not uni:
        return None
    try:
        return chr(int(str(uni), 16))
    except Exception:
        return None


def build_glyph_maps(glyphs: Iterable[Any]) -> Dict[str, Any]:
    """Build a set of fast glyph lookup maps from an iterable of glyph objects."""

    name_to_id: Dict[str, str] = {}
    id_to_name: Dict[str, str] = {}
    glyphname_to_unicode: Dict[str, str] = {}
    unicode_to_glyphname: Dict[str, str] = {}
    unicode_to_glyphname_fallback: Dict[str, str] = {}

    left_key_group_rep: Dict[str, str] = {}  # rightKerningGroup -> representative glyph name (@MMK_L_*)
    right_key_group_rep: Dict[str, str] = {}  # leftKerningGroup -> representative glyph name (@MMK_R_*)

    name_set: set[str] = set()

    for glyph in glyphs or []:
        name = str(_safe_attr(glyph, "name", "") or "")
        if not name:
            continue
        name_set.add(name)

        gid = _safe_attr(glyph, "id", None)
        if gid is not None:
            gid_s = str(gid)
            if gid_s and name not in name_to_id:
                name_to_id[name] = gid_s
            if gid_s and gid_s not in id_to_name:
                id_to_name[gid_s] = name

        # Unicode maps.
        ch = glyph_unicode_char(glyph)
        if ch:
            glyphname_to_unicode[name] = ch
            exported = bool(_safe_attr(glyph, "export", True))
            if exported and ch not in unicode_to_glyphname:
                unicode_to_glyphname[ch] = name
            if ch not in unicode_to_glyphname_fallback:
                unicode_to_glyphname_fallback[ch] = name

        # Group representatives.
        rgrp = _safe_attr(glyph, "rightKerningGroup", None)
        lgrp = _safe_attr(glyph, "leftKerningGroup", None)
        if rgrp:
            rgrp_s = str(rgrp)
            if rgrp_s and rgrp_s not in left_key_group_rep:
                left_key_group_rep[rgrp_s] = name
        if lgrp:
            lgrp_s = str(lgrp)
            if lgrp_s and lgrp_s not in right_key_group_rep:
                right_key_group_rep[lgrp_s] = name

    # Fallback for unicode mapping: use any glyph if no exported glyph was found.
    for ch, name in unicode_to_glyphname_fallback.items():
        if ch not in unicode_to_glyphname:
            unicode_to_glyphname[ch] = name

    return {
        "nameSet": name_set,
        "nameToId": name_to_id,
        "idToName": id_to_name,
        "glyphnameToUnicode": glyphname_to_unicode,
        "unicodeToGlyphname": unicode_to_glyphname,
        "leftKeyGroupRep": left_key_group_rep,
        "rightKeyGroupRep": right_key_group_rep,
    }


def kerning_key_to_glyph_name(
    *,
    key: str,
    is_left_key: bool,
    name_set: set[str],
    id_to_name: Dict[str, str],
    left_key_group_rep: Dict[str, str],
    right_key_group_rep: Dict[str, str],
) -> Optional[str]:
    """Convert a kerning dictionary key to a representative glyph name."""

    if not isinstance(key, str) or not key:
        return None

    if key.startswith("@MMK_L_"):
        group = key[len("@MMK_L_") :]
        rep = left_key_group_rep.get(group)
        if rep:
            return rep
        # As a last resort, treat group name as a glyph name.
        return group if group in name_set else None

    if key.startswith("@MMK_R_"):
        group = key[len("@MMK_R_") :]
        rep = right_key_group_rep.get(group)
        if rep:
            return rep
        return group if group in name_set else None

    if key in id_to_name:
        return id_to_name.get(key)

    return key if key in name_set else None


def build_candidate_pairs(
    *,
    dataset_pairs: Sequence[Tuple[str, str]],
    unicode_to_glyphname: Dict[str, str],
    relevant_limit: int,
    include_existing: bool,
    kerning_master: Dict[str, Dict[str, Any]] | Any,
    name_set: set[str],
    id_to_name: Dict[str, str],
    left_key_group_rep: Dict[str, str],
    right_key_group_rep: Dict[str, str],
    focus: Optional[set[str]] = None,
    pair_limit: int = 3000,
) -> Tuple[List[Tuple[str, str]], Dict[str, int]]:
    """Build an ordered, deduped list of glyph-name pairs to analyze."""

    focus = focus if focus else None
    cap = max(int(pair_limit or 0), 0) or 3000
    relevant_cap = max(int(relevant_limit or 0), 0)

    out: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()

    counts = {
        "pairsCandidate": 0,
        "pairsFromRelevant": 0,
        "pairsFromExisting": 0,
        "pairsSkippedNoGlyph": 0,
    }

    # 1) Relevant (Andre-Fuchs) pairs.
    for left_ch, right_ch in (dataset_pairs or [])[:relevant_cap]:
        left_name = unicode_to_glyphname.get(left_ch)
        right_name = unicode_to_glyphname.get(right_ch)
        if not left_name or not right_name:
            counts["pairsSkippedNoGlyph"] += 1
            continue
        if focus is not None and left_name not in focus and right_name not in focus:
            continue
        pair = (left_name, right_name)
        if pair in seen:
            continue
        out.append(pair)
        seen.add(pair)
        counts["pairsFromRelevant"] += 1
        if len(out) >= cap:
            return out, counts

    # 2) Existing explicit kerning pairs (representative glyphs).
    if include_existing:
        kerning_norm = _string_keys_kerning(kerning_master)
        for left_key, right_dict in kerning_norm.items():
            if not isinstance(right_dict, dict):
                continue
            left_name = kerning_key_to_glyph_name(
                key=str(left_key),
                is_left_key=True,
                name_set=name_set,
                id_to_name=id_to_name,
                left_key_group_rep=left_key_group_rep,
                right_key_group_rep=right_key_group_rep,
            )
            if not left_name:
                continue
            for right_key in right_dict.keys():
                right_name = kerning_key_to_glyph_name(
                    key=str(right_key),
                    is_left_key=False,
                    name_set=name_set,
                    id_to_name=id_to_name,
                    left_key_group_rep=left_key_group_rep,
                    right_key_group_rep=right_key_group_rep,
                )
                if not right_name:
                    continue
                if focus is not None and left_name not in focus and right_name not in focus:
                    continue
                pair = (left_name, right_name)
                if pair in seen:
                    continue
                out.append(pair)
                seen.add(pair)
                counts["pairsFromExisting"] += 1
                if len(out) >= cap:
                    return out, counts

    counts["pairsCandidate"] = len(out)
    return out, counts
