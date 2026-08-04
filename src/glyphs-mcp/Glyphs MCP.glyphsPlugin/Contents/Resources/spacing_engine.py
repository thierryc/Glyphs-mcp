# encoding: utf-8

"""Clean-room auto-spacing engine based on an area-style spacing model.

This module purposefully avoids importing GlyphsApp at import-time so it can be
unit-tested outside of Glyphs. The MCP tools call into this module from within
Glyphs, passing real GSFont/GSGlyph/GSLayer objects.
"""

from __future__ import annotations

import math
import re
import statistics
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULTS: Dict[str, Any] = {
    # Area-style parameters (legacy master custom parameters are paramArea/paramDepth/paramOver).
    "area": 400.0,
    "depth": 15.0,  # percent of xHeight
    "over": 0.0,  # percent of xHeight
    "frequency": 5.0,
    "factor": 1.0,
    # Reference glyph used to define the vertical measurement range.
    # "auto" resolves by glyph class; "*" means "use glyph itself".
    "referenceGlyph": "auto",
    # Geometry / behavior toggles.
    "italicMode": "deslant",  # "deslant" | "none"
    "includeComponents": True,
    "respectMetricsKeys": True,
    "skipAutoAligned": True,
    "minCoverageRatio": 0.7,
    # Tabular handling.
    "tabularMode": "auto",
    "tabularWidth": None,  # int|None
    "tabularToleranceEm": 0.005,
    # Payload / debugging.
    "includeSamples": False,
}

DEFAULT_GUARDS: Dict[str, Any] = {
    "negativeBearingPolicy": "guarded",  # guarded | advisory | off
    "warnBelowEm": -0.05,
    "blockBelowEm": -0.10,
    "blockOnOutliers": True,
    "allowGlyphs": [],
    "allowItalicOverhangs": True,
    "allowMarks": True,
    "currentMetricsTrust": "auto",  # auto | trusted | untrusted
    "trustedMetricGlyphs": [],
    "untrustedMetricGlyphs": [],
}

DEFAULT_FIGURE_NAMES: Tuple[str, ...] = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
)

NARROW_PUNCTUATION_NAMES = frozenset(
    {
        "period",
        "comma",
        "colon",
        "semicolon",
        "exclam",
        "question",
        "quotesingle",
        "quotedbl",
        "quoteleft",
        "quoteright",
        "quotedblleft",
        "quotedblright",
        "guilsinglleft",
        "guilsinglright",
        "guillemotleft",
        "guillemotright",
        "ellipsis",
    }
)

OVERHANG_CANDIDATE_NAMES = frozenset({"J", "j", "f", "Q"})

SPACING_PARAM_FIELDS: Tuple[str, ...] = ("area", "depth", "over", "frequency")

SPACING_PARAM_KEYS_CANONICAL: Dict[str, str] = {
    "area": "cx.ap.spacingArea",
    "depth": "cx.ap.spacingDepth",
    "over": "cx.ap.spacingOver",
    "frequency": "cx.ap.spacingFreq",
}

SPACING_PARAM_KEYS_GMCP_LEGACY: Dict[str, str] = {
    "area": "gmcpSpacingArea",
    "depth": "gmcpSpacingDepth",
    "over": "gmcpSpacingOver",
    "frequency": "gmcpSpacingFreq",
}

SPACING_PARAM_KEYS_PARAM_LEGACY: Dict[str, str] = {
    "area": "paramArea",
    "depth": "paramDepth",
    "over": "paramOver",
    "frequency": "paramFreq",
}


def resolve_param_precedence(
    *,
    field: str,
    per_call_defaults: Optional[Dict[str, Any]],
    master_custom: Optional[Dict[str, Any]],
    font_custom: Optional[Dict[str, Any]],
    fallback: Any,
    canonical_keys: Dict[str, str] = SPACING_PARAM_KEYS_CANONICAL,
    legacy_key_sets: Sequence[Dict[str, str]] = (SPACING_PARAM_KEYS_GMCP_LEGACY, SPACING_PARAM_KEYS_PARAM_LEGACY),
) -> Any:
    """Resolve a spacing parameter with strict precedence.

    Precedence:
      1) per-call defaults
      2) master custom parameter (canonical)
      3) master custom parameter (legacy sets, in order)
      4) font custom parameter (canonical)
      5) font custom parameter (legacy sets, in order)
      6) fallback
    """
    if not field:
        return fallback

    per_call_defaults = per_call_defaults or {}
    if field in per_call_defaults and per_call_defaults.get(field) is not None:
        return per_call_defaults.get(field)

    master_custom = master_custom or {}
    font_custom = font_custom or {}

    ckey = canonical_keys.get(field)

    if ckey and ckey in master_custom and master_custom.get(ckey) is not None:
        return master_custom.get(ckey)

    for legacy_keys in legacy_key_sets:
        lkey = legacy_keys.get(field)
        if lkey and lkey in master_custom and master_custom.get(lkey) is not None:
            return master_custom.get(lkey)

    if ckey and ckey in font_custom and font_custom.get(ckey) is not None:
        return font_custom.get(ckey)

    for legacy_keys in legacy_key_sets:
        lkey = legacy_keys.get(field)
        if lkey and lkey in font_custom and font_custom.get(lkey) is not None:
            return font_custom.get(lkey)

    return fallback


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
    """Round to nearest int, with .5 values rounded away from zero.

    Python's built-in round() uses bankers rounding; font-unit metrics are
    typically expected to be integer units without .5 artifacts.
    """
    xf = float(x)
    if xf >= 0.0:
        return int(math.floor(xf + 0.5))
    return -int(math.floor(abs(xf) + 0.5))


def _units_int(value: Any) -> Optional[int]:
    """Coerce a numeric value to an integer font unit using half-away-from-zero rounding."""
    f = _coerce_float(value)
    if f is None:
        return None
    return _round_half_away_from_zero(f)


def _split_int_delta(diff_total: int) -> Tuple[int, int]:
    """Split an integer delta into two integers that sum exactly to diff_total.

    Used for tabular width preservation to avoid producing half-unit sidebearings.
    """
    left = diff_total // 2
    right = diff_total - left
    return left, right


def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        value = getattr(obj, name)
        return value() if callable(value) else value
    except Exception:
        return default


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


def _bounds_tuple(layer: Any) -> Optional[Tuple[float, float, float, float]]:
    """Return (min_x, max_x, min_y, max_y) for layer.bounds."""
    b = _safe_attr(layer, "bounds")
    if not b:
        return None
    ox = _coerce_float(_safe_attr(b, "origin").x if _safe_attr(b, "origin") else None)
    oy = _coerce_float(_safe_attr(b, "origin").y if _safe_attr(b, "origin") else None)
    sw = _coerce_float(_safe_attr(b, "size").width if _safe_attr(b, "size") else None)
    sh = _coerce_float(_safe_attr(b, "size").height if _safe_attr(b, "size") else None)
    if ox is None or oy is None or sw is None or sh is None:
        return None
    return (ox, ox + sw, oy, oy + sh)


def _frange(y_min: float, y_max: float, step: float) -> List[float]:
    if step <= 0:
        step = 1.0
    # Ensure stable iteration even when floats are involved.
    out: List[float] = []
    y = float(y_min)
    stop = float(y_max) + 1e-9
    while y <= stop:
        out.append(y)
        y += step
    return out


def _string_or_star(value: Any) -> str:
    s = (value or "").strip()
    return s if s else "*"


def _matches_token(rule_value: str, glyph_value: str) -> bool:
    if not rule_value or rule_value == "*":
        return True
    return rule_value == (glyph_value or "")


def _matches_name_filter(rule: Dict[str, Any], glyph_name: str) -> bool:
    if not glyph_name:
        return False

    if "nameRegex" in rule and rule["nameRegex"]:
        try:
            return re.search(str(rule["nameRegex"]), glyph_name) is not None
        except Exception:
            return False

    name_filter = rule.get("nameFilter")
    if not name_filter or str(name_filter).strip() in ("", "*"):
        return True
    return str(name_filter) in glyph_name


def _rule_score(rule: Dict[str, Any], glyph_meta: Dict[str, str]) -> Optional[int]:
    script = _string_or_star(rule.get("script", "*"))
    category = _string_or_star(rule.get("category", "*"))
    sub_category = _string_or_star(rule.get("subCategory", rule.get("subcategory", "*")))

    if not _matches_token(script, glyph_meta.get("script", "")):
        return None
    if not _matches_token(category, glyph_meta.get("category", "")):
        return None
    if not _matches_token(sub_category, glyph_meta.get("subCategory", "")):
        return None
    if not _matches_name_filter(rule, glyph_meta.get("name", "")):
        return None

    score = 0
    if script != "*":
        score += 8
    if category != "*":
        score += 4
    if sub_category != "*":
        score += 2
    if (rule.get("nameRegex") or rule.get("nameFilter")) and str(rule.get("nameRegex") or rule.get("nameFilter")).strip() not in ("", "*"):
        score += 1
    return score


def select_rule(glyph: Any, rules: Optional[Sequence[Dict[str, Any]]]) -> Dict[str, Any]:
    rules = list(rules or [])
    if not rules:
        return {}

    glyph_meta = {
        "name": str(_safe_attr(glyph, "name", "") or ""),
        "script": str(_safe_attr(glyph, "script", "") or ""),
        "category": str(_safe_attr(glyph, "category", "") or ""),
        "subCategory": str(_safe_attr(glyph, "subCategory", "") or ""),
    }

    best: Optional[Dict[str, Any]] = None
    best_score = -1
    best_index = -1
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        score = _rule_score(rule, glyph_meta)
        if score is None:
            continue
        if score > best_score or (score == best_score and idx > best_index):
            best = rule
            best_score = score
            best_index = idx

    return best or {}


def _font_glyph(font: Any, name: str) -> Any:
    try:
        return font.glyphs[name]
    except Exception:
        return None


def _glyph_unicode_character(glyph: Any) -> Optional[str]:
    raw = _safe_attr(glyph, "unicode", "")
    if not raw:
        info = _safe_attr(glyph, "glyphInfo")
        raw = _safe_attr(info, "unicode", "") if info is not None else ""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return chr(int(text, 16))
    except Exception:
        return None


def classify_glyph(glyph: Any, layer: Any = None) -> Dict[str, Any]:
    """Classify a glyph without depending on Glyphs subCategory alone."""
    name = str(_safe_attr(glyph, "name", "") or "")
    base_name = name.split(".", 1)[0]
    category = str(_safe_attr(glyph, "category", "") or "")
    sub_category = str(_safe_attr(glyph, "subCategory", "") or "")
    source = "glyph"

    info = _safe_attr(glyph, "glyphInfo")
    info_category = str(_safe_attr(info, "category", "") or "") if info is not None else ""
    info_sub_category = str(_safe_attr(info, "subCategory", "") or "") if info is not None else ""
    effective_category = category or info_category
    effective_sub_category = sub_category or info_sub_category
    if not category and info_category:
        source = "glyphInfo"

    width = _coerce_float(_safe_attr(layer, "width")) if layer is not None else None
    if width is not None and abs(width) <= 1e-6:
        return {
            "glyphClass": "zeroWidth",
            "source": "layerWidth",
            "category": effective_category or None,
            "subCategory": effective_sub_category or None,
        }

    cat_lower = effective_category.lower()
    sub_lower = effective_sub_category.lower()
    if cat_lower == "mark" or "nonspacing" in sub_lower or _detect_combining_mark(glyph):
        return {
            "glyphClass": "mark",
            "source": source,
            "category": effective_category or None,
            "subCategory": effective_sub_category or None,
        }
    if cat_lower == "letter" and sub_lower == "uppercase":
        glyph_class = "uppercase"
    elif cat_lower == "letter" and sub_lower == "lowercase":
        glyph_class = "lowercase"
    elif cat_lower in ("number", "decimal digit") and sub_lower in ("decimal digit", "decimal", "digit"):
        glyph_class = "decimalFigure"
    else:
        glyph_class = ""

    char = _glyph_unicode_character(glyph)
    unicode_category = None
    if not glyph_class and char:
        unicode_category = unicodedata.category(char)
        if unicode_category == "Lu" or char.isupper():
            glyph_class = "uppercase"
            source = "unicode"
        elif unicode_category == "Ll" or char.islower():
            glyph_class = "lowercase"
            source = "unicode"
        elif unicode_category == "Nd":
            glyph_class = "decimalFigure"
            source = "unicode"
        elif unicode_category.startswith("M"):
            glyph_class = "mark"
            source = "unicode"
        elif unicode_category.startswith("P"):
            glyph_class = "narrowPunctuation" if base_name in NARROW_PUNCTUATION_NAMES else "punctuation"
            source = "unicode"

    if not glyph_class:
        if len(base_name) == 1 and "A" <= base_name <= "Z":
            glyph_class = "uppercase"
            source = "glyphName"
        elif len(base_name) == 1 and "a" <= base_name <= "z":
            glyph_class = "lowercase"
            source = "glyphName"
        elif base_name in DEFAULT_FIGURE_NAMES:
            glyph_class = "decimalFigure"
            source = "glyphName"
        elif base_name in NARROW_PUNCTUATION_NAMES:
            glyph_class = "narrowPunctuation"
            source = "glyphName"
        elif cat_lower == "punctuation":
            glyph_class = "punctuation"
            source = source
        elif cat_lower == "number":
            # Non-decimal numbers should not automatically inherit the decimal model.
            glyph_class = "unclassified"
        else:
            glyph_class = "unclassified"

    return {
        "glyphClass": glyph_class,
        "source": source,
        "category": effective_category or None,
        "subCategory": effective_sub_category or None,
        "unicodeCategory": unicode_category,
    }


def resolve_reference(
    *,
    font: Any,
    glyph: Any,
    layer: Any,
    rule: Dict[str, Any],
    defaults: Dict[str, Any],
    classification: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve requested and effective spacing references with provenance."""
    classification = classification or classify_glyph(glyph, layer)
    glyph_class = classification.get("glyphClass") or "unclassified"

    if "referenceGlyph" in rule or "reference" in rule:
        requested = rule.get("referenceGlyph", rule.get("reference"))
    else:
        requested = defaults.get("referenceGlyph", "auto")
    requested = str(requested if requested is not None else "auto").strip() or "auto"

    if requested != "auto":
        if requested == "*":
            return {
                "referenceMode": "self",
                "requestedReferenceGlyph": "*",
                "resolvedReferenceGlyph": str(_safe_attr(glyph, "name", "") or "*"),
                "referenceFallback": None,
                "referenceGlyph": glyph,
            }
        explicit = _font_glyph(font, requested)
        return {
            "referenceMode": "explicit",
            "requestedReferenceGlyph": requested,
            "resolvedReferenceGlyph": requested if explicit else None,
            "referenceFallback": None,
            "referenceGlyph": explicit,
        }

    candidates: List[str]
    if glyph_class == "uppercase":
        candidates = ["H", "x", "*"]
    elif glyph_class == "lowercase":
        candidates = ["x", "n", "o", "*"]
    elif glyph_class == "decimalFigure":
        candidates = ["one", "zero", "x", "*"]
    elif glyph_class in ("mark", "zeroWidth", "narrowPunctuation"):
        candidates = ["*"]
    elif glyph_class == "punctuation":
        candidates = ["*", "x"]
    else:
        candidates = ["x", "*"]

    preferred = candidates[0]
    for candidate in candidates:
        if candidate == "*":
            resolved_name = str(_safe_attr(glyph, "name", "") or "*")
            ref_glyph = glyph
        else:
            resolved_name = candidate
            ref_glyph = _font_glyph(font, candidate)
        if ref_glyph:
            fallback = None
            if candidate != preferred:
                fallback = {
                    "preferredReferenceGlyph": preferred,
                    "resolvedReferenceGlyph": resolved_name,
                    "reason": "preferred_reference_missing",
                }
            return {
                "referenceMode": "auto",
                "requestedReferenceGlyph": "auto",
                "resolvedReferenceGlyph": resolved_name,
                "referenceFallback": fallback,
                "referenceGlyph": ref_glyph,
            }

    return {
        "referenceMode": "auto",
        "requestedReferenceGlyph": "auto",
        "resolvedReferenceGlyph": None,
        "referenceFallback": {
            "preferredReferenceGlyph": preferred,
            "resolvedReferenceGlyph": None,
            "reason": "no_reference_available",
        },
        "referenceGlyph": None,
    }


def resolve_reference_glyph_name(glyph: Any, rule: Dict[str, Any], defaults: Dict[str, Any]) -> str:
    """Compatibility helper returning the requested reference token."""
    if "referenceGlyph" in rule or "reference" in rule:
        ref = rule.get("referenceGlyph", rule.get("reference"))
    else:
        ref = defaults.get("referenceGlyph", "auto")
    return str(ref if ref is not None else "auto").strip() or "auto"


def resolve_factor(rule: Dict[str, Any], defaults: Dict[str, Any]) -> float:
    raw = rule.get("factor", rule.get("value", defaults.get("factor", 1.0)))
    return float(raw) if raw is not None else 1.0


def _detect_combining_mark(glyph: Any) -> bool:
    name = str(_safe_attr(glyph, "name", "") or "")
    sub = str(_safe_attr(glyph, "subCategory", "") or "").lower()
    if "nonspacing" in sub:
        return True
    if name.endswith("comb"):
        return True
    uni = str(_safe_attr(glyph, "unicode", "") or "").strip()
    if not uni:
        return False
    try:
        cp = int(uni, 16)
    except Exception:
        return False
    # Common combining mark blocks.
    return (0x0300 <= cp <= 0x036F) or (0x1AB0 <= cp <= 0x1AFF) or (0x1DC0 <= cp <= 0x1DFF) or (0x20D0 <= cp <= 0x20FF) or (0xFE20 <= cp <= 0xFE2F)


def _is_tabular_name(name: str) -> bool:
    return ".tf" in name or ".tosf" in name


def _coverage_ratio(glyph_bounds: Tuple[float, float, float, float], y_min: float, y_max: float) -> float:
    _, _, g_y_min, g_y_max = glyph_bounds
    denom = max(1e-6, float(y_max - y_min))
    overlap = max(0.0, min(y_max, g_y_max) - max(y_min, g_y_min))
    return overlap / denom


def _triangle(angle_deg: float, opp: float) -> float:
    return math.tan(math.radians(angle_deg)) * opp


def _deslant_x(x: float, y: float, x_height: float, italic_angle: float) -> float:
    # Shift x proportionally around half xHeight (helps in italic/slanted masters).
    return x + _triangle(italic_angle, y - x_height / 2.0)


def _measure_edges_at_y(
    layer: Any,
    y: float,
    include_components: bool,
    start_x: float,
    end_x: float,
) -> Tuple[Optional[float], Optional[float]]:
    try:
        intersections = layer.intersectionsBetweenPoints((start_x, y), (end_x, y), components=include_components)
    except Exception:
        return (None, None)

    try:
        points = list(intersections or [])
        n = len(points)
    except Exception:
        return (None, None)

    # Glyphs 4 proxy collections can reject negative indexes; use a real list.
    if n < 4:
        return (None, None)

    left = _point_x(points[1])
    right = _point_x(points[n - 2])
    return (left, right)


@dataclass(frozen=True)
class Measurement:
    ys: List[float]
    left_xs: List[Optional[float]]
    right_xs: List[Optional[float]]


def measure_layer_edges(
    layer: Any,
    y_min: float,
    y_max: float,
    step: float,
    include_components: bool,
) -> Optional[Measurement]:
    bounds = _bounds_tuple(layer)
    if not bounds:
        return None
    min_x, max_x, _, _ = bounds
    start_x = min_x - 1.0
    end_x = max_x + 1.0

    ys = _frange(y_min, y_max, step=step)
    left_xs: List[Optional[float]] = []
    right_xs: List[Optional[float]] = []
    for y in ys:
        l, r = _measure_edges_at_y(layer, y, include_components=include_components, start_x=start_x, end_x=end_x)
        left_xs.append(l)
        right_xs.append(r)
    return Measurement(ys=ys, left_xs=left_xs, right_xs=right_xs)


def _diagonize_left(xs: List[float], step: float) -> List[float]:
    if not xs:
        return xs
    out = list(xs)
    s = float(step)
    for i in range(len(out) - 1):
        out[i + 1] = min(out[i + 1], out[i] + s)
    for i in range(len(out) - 2, -1, -1):
        out[i] = min(out[i], out[i + 1] + s)
    return out


def _diagonize_right(xs: List[float], step: float) -> List[float]:
    if not xs:
        return xs
    out = list(xs)
    s = float(step)
    for i in range(len(out) - 1):
        out[i + 1] = max(out[i + 1], out[i] - s)
    for i in range(len(out) - 2, -1, -1):
        out[i] = max(out[i], out[i + 1] - s)
    return out


def _trapezoid_area(ys: List[float], indents: List[float]) -> float:
    if len(ys) < 2 or len(indents) < 2:
        return 0.0
    area = 0.0
    for i in range(len(ys) - 1):
        dy = float(ys[i + 1] - ys[i])
        area += (indents[i] + indents[i + 1]) * 0.5 * dy
    return area


def _first_last_non_none(values: List[Optional[float]]) -> Tuple[Optional[float], Optional[float]]:
    first = None
    last = None
    for v in values:
        if v is not None:
            first = v
            break
    for v in reversed(values):
        if v is not None:
            last = v
            break
    return first, last


def _min_max_non_none(values: List[Optional[float]]) -> Tuple[Optional[float], Optional[float]]:
    found: List[float] = [float(v) for v in values if v is not None]
    if not found:
        return None, None
    return min(found), max(found)


def _layer_has_metrics_keys(glyph: Any, layer: Any) -> Tuple[bool, bool]:
    # Metrics keys may exist on glyph or layer.
    g_left = str(_safe_attr(glyph, "leftMetricsKey", "") or "").strip()
    g_right = str(_safe_attr(glyph, "rightMetricsKey", "") or "").strip()
    l_left = str(_safe_attr(layer, "leftMetricsKey", "") or "").strip()
    l_right = str(_safe_attr(layer, "rightMetricsKey", "") or "").strip()
    return (bool(g_left or l_left), bool(g_right or l_right))


def _layer_width_metrics_key(glyph: Any, layer: Any) -> str:
    glyph_key = str(_safe_attr(glyph, "widthMetricsKey", "") or "").strip()
    layer_key = str(_safe_attr(layer, "widthMetricsKey", "") or "").strip()
    return layer_key or glyph_key


def _layer_is_auto_aligned(layer: Any) -> bool:
    return bool(_safe_attr(layer, "isAligned", False))


def _get_layer_metrics(layer: Any) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    width = _coerce_float(_safe_attr(layer, "width"))
    lsb = _coerce_float(_safe_attr(layer, "leftSideBearing", _safe_attr(layer, "LSB")))
    rsb = _coerce_float(_safe_attr(layer, "rightSideBearing", _safe_attr(layer, "RSB")))
    return width, lsb, rsb


def _custom_parameter_value(obj: Any, key: str) -> Any:
    params = _safe_attr(obj, "customParameters")
    if params is None:
        return None
    try:
        return params[key]
    except Exception:
        pass
    try:
        return params.get(key)
    except Exception:
        return None


def _master_layer(glyph: Any, master_id: str) -> Any:
    if glyph is None:
        return None
    try:
        return glyph.layers[master_id]
    except Exception:
        return None


def assess_tabular_mode(
    *,
    font: Any,
    glyph: Any,
    layer: Any,
    master: Any,
    defaults: Dict[str, Any],
    classification: Dict[str, Any],
) -> Dict[str, Any]:
    """Determine whether a width should be preserved and why."""
    mode = defaults.get("tabularMode", "auto")
    if isinstance(mode, str):
        mode_normalized: Any = mode.strip().lower() or "auto"
    else:
        mode_normalized = bool(mode)
    name = str(_safe_attr(glyph, "name", "") or "")
    current_width = _units_int(_safe_attr(layer, "width"))
    explicit_width = _units_int(defaults.get("tabularWidth"))
    upm = float(_safe_attr(font, "upm", 1000) or 1000)
    tolerance_em = _coerce_float(defaults.get("tabularToleranceEm"))
    if tolerance_em is None or tolerance_em < 0:
        tolerance_em = float(DEFAULTS["tabularToleranceEm"])
    tolerance_units = float(tolerance_em) * upm
    master_id = str(_safe_attr(master, "id", "") or "")

    result = {
        "mode": mode_normalized,
        "detected": False,
        "reason": "automatic_tabular_evidence_not_found",
        "preservedWidth": None,
        "toleranceEm": float(tolerance_em),
    }

    if mode_normalized is True:
        target = explicit_width if explicit_width is not None else current_width
        result.update(
            detected=target is not None,
            reason="explicit_tabular_mode" if explicit_width is None else "explicit_tabular_width",
            preservedWidth=target,
        )
        return result

    suffix_detected = _is_tabular_name(name)
    if mode_normalized is False:
        if suffix_detected:
            result.update(detected=current_width is not None, reason="tabular_glyph_name", preservedWidth=current_width)
        else:
            result["reason"] = "automatic_tabular_detection_disabled"
        return result

    if mode_normalized not in ("auto",):
        result["reason"] = "invalid_tabular_mode"
        return result

    if explicit_width is not None:
        result.update(detected=True, reason="explicit_tabular_width", preservedWidth=explicit_width)
        return result
    if suffix_detected:
        result.update(detected=current_width is not None, reason="tabular_glyph_name", preservedWidth=current_width)
        return result

    fixed_pitch = _custom_parameter_value(font, "isFixedPitch")
    if fixed_pitch is None:
        fixed_pitch = _safe_attr(font, "isFixedPitch")
    if bool(fixed_pitch):
        representative_widths: List[int] = []
        for candidate_name in DEFAULT_FIGURE_NAMES + ("H", "O", "n", "o", "space"):
            candidate = _font_glyph(font, candidate_name)
            candidate_layer = _master_layer(candidate, master_id)
            value = _units_int(_safe_attr(candidate_layer, "width"))
            if value is not None and value > 0:
                representative_widths.append(value)
        target = _round_half_away_from_zero(statistics.median(representative_widths)) if representative_widths else current_width
        result.update(detected=target is not None, reason="font_fixed_pitch_metadata", preservedWidth=target)
        return result

    if classification.get("glyphClass") != "decimalFigure":
        return result

    figure_widths: List[int] = []
    width_keys: List[str] = []
    all_figures_present = True
    for candidate_name in DEFAULT_FIGURE_NAMES:
        candidate = _font_glyph(font, candidate_name)
        candidate_layer = _master_layer(candidate, master_id)
        if candidate is None or candidate_layer is None:
            all_figures_present = False
            break
        value = _units_int(_safe_attr(candidate_layer, "width"))
        if value is None:
            all_figures_present = False
            break
        figure_widths.append(value)
        key = _layer_width_metrics_key(candidate, candidate_layer)
        if key:
            width_keys.append(key)

    if all_figures_present and len(figure_widths) == len(DEFAULT_FIGURE_NAMES):
        median_width = _round_half_away_from_zero(statistics.median(figure_widths))
        if max(figure_widths) - min(figure_widths) <= tolerance_units:
            result.update(
                detected=True,
                reason="default_figures_equal_width",
                preservedWidth=median_width,
                observedWidths=list(figure_widths),
            )
            return result
        if len(width_keys) == len(DEFAULT_FIGURE_NAMES) and len(set(width_keys)) == 1:
            result.update(
                detected=True,
                reason="default_figures_share_width_metrics_key",
                preservedWidth=median_width,
                widthMetricsKey=width_keys[0],
            )
            return result
    return result


def normalize_guards(guards: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(DEFAULT_GUARDS)
    if isinstance(guards, dict):
        for key, value in guards.items():
            if value is not None:
                out[key] = value
    policy = str(out.get("negativeBearingPolicy") or "guarded").strip().lower()
    if policy not in ("guarded", "advisory", "off"):
        policy = "guarded"
    out["negativeBearingPolicy"] = policy
    warn = _coerce_float(out.get("warnBelowEm"))
    block = _coerce_float(out.get("blockBelowEm"))
    out["warnBelowEm"] = float(DEFAULT_GUARDS["warnBelowEm"] if warn is None else warn)
    out["blockBelowEm"] = float(DEFAULT_GUARDS["blockBelowEm"] if block is None else block)
    if out["blockBelowEm"] > out["warnBelowEm"]:
        out["blockBelowEm"], out["warnBelowEm"] = out["warnBelowEm"], out["blockBelowEm"]
    for key in ("allowGlyphs", "trustedMetricGlyphs", "untrustedMetricGlyphs"):
        raw = out.get(key)
        out[key] = [str(value) for value in raw] if isinstance(raw, (list, tuple, set)) else []
    return out


def assess_metrics_trust(
    *,
    glyph: Any,
    layer: Any,
    current: Dict[str, Any],
    guards: Dict[str, Any],
) -> Dict[str, Any]:
    name = str(_safe_attr(glyph, "name", "") or "")
    if name in guards.get("untrustedMetricGlyphs", []):
        return {"status": "untrusted", "reason": "explicit_untrusted_glyph"}
    if name in guards.get("trustedMetricGlyphs", []):
        return {"status": "trusted", "reason": "explicit_trusted_glyph"}
    mode = str(guards.get("currentMetricsTrust") or "auto").strip().lower()
    if mode in ("trusted", "untrusted"):
        return {"status": mode, "reason": "explicit_scope_setting"}
    left_key, right_key = _layer_has_metrics_keys(glyph, layer)
    width_key = _layer_width_metrics_key(glyph, layer)
    if left_key or right_key or width_key:
        return {
            "status": "trusted",
            "reason": "established_metrics_relationship",
            "metricsKeys": {"left": left_key, "right": right_key, "width": width_key or None},
        }
    width = _coerce_float(current.get("width"))
    lsb = _coerce_float(current.get("lsb"))
    rsb = _coerce_float(current.get("rsb"))
    if width is not None and width <= 0:
        return {"status": "untrusted", "reason": "nonpositive_current_advance"}
    if lsb is not None and rsb is not None and abs(lsb) <= 1e-6 and abs(rsb) <= 1e-6:
        return {"status": "untrusted", "reason": "zero_sidebearing_placeholder_pattern"}
    return {"status": "unknown", "reason": "no_reliable_trust_evidence"}


def _normalized_metrics(metrics: Dict[str, Any], upm: float) -> Dict[str, Optional[float]]:
    denom = float(upm or 1000.0)
    return {
        key: (_coerce_float(metrics.get(key)) / denom if _coerce_float(metrics.get(key)) is not None else None)
        for key in ("width", "lsb", "rsb")
    }


def assess_spacing_suggestion(
    *,
    glyph: Any,
    layer: Any,
    current: Dict[str, Any],
    proposed: Dict[str, Any],
    measured: Dict[str, Any],
    classification: Dict[str, Any],
    upm: float,
    italic_angle: float,
    guards: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Assess raw spacing proposals without mutating or clamping them."""
    effective = normalize_guards(guards)
    name = str(_safe_attr(glyph, "name", "") or "")
    glyph_class = classification.get("glyphClass") or "unclassified"
    current_norm = _normalized_metrics(current, upm)
    proposed_norm = _normalized_metrics(proposed, upm)
    change_norm = {
        key: (
            proposed_norm[key] - current_norm[key]
            if proposed_norm.get(key) is not None and current_norm.get(key) is not None
            else None
        )
        for key in ("width", "lsb", "rsb")
    }
    trust = assess_metrics_trust(glyph=glyph, layer=layer, current=current, guards=effective)

    issues: List[Dict[str, Any]] = []
    exemptions: List[Dict[str, Any]] = []
    side_results: Dict[str, Any] = {}
    aggregate = "informational"
    policy = effective["negativeBearingPolicy"]
    ordinary_base = glyph_class in ("uppercase", "lowercase", "decimalFigure")
    allowed_by_name = name in effective.get("allowGlyphs", [])
    allow_mark = glyph_class in ("mark", "zeroWidth") and bool(effective.get("allowMarks"))

    for side, metric_key, distance_key in (
        ("left", "lsb", "distanceLeft"),
        ("right", "rsb", "distanceRight"),
    ):
        value_em = proposed_norm.get(metric_key)
        severity = "informational"
        reason = "Bearing is non-negative or within the advisory range"
        exempted = False
        evidence = _coerce_float(measured.get(distance_key)) or 0.0
        geometry_supports_overhang = evidence > max(1.0, float(upm) * 0.005)

        if value_em is not None and value_em < 0:
            if allowed_by_name:
                severity = "exempted"
                exempted = True
                reason = "Glyph is explicitly allow-listed"
            elif allow_mark:
                severity = "exempted"
                exempted = True
                reason = "Mark or zero-width glyph is exempt from ordinary bearing guards"
            elif name in OVERHANG_CANDIDATE_NAMES and geometry_supports_overhang:
                severity = "warning" if value_em <= effective["warnBelowEm"] else "informational"
                exempted = value_em <= effective["blockBelowEm"]
                reason = "Known overhang candidate has side-specific geometric support"
            elif (
                abs(float(italic_angle or 0.0)) > 1e-6
                and bool(effective.get("allowItalicOverhangs"))
                and geometry_supports_overhang
            ):
                severity = "exempted" if value_em <= effective["blockBelowEm"] else "warning"
                exempted = True
                reason = "Italic overhang has side-specific geometric support"
            elif policy != "off" and value_em <= effective["blockBelowEm"] and ordinary_base:
                if policy == "guarded" and bool(effective.get("blockOnOutliers")):
                    severity = "blocked"
                    reason = "Extreme negative bearing on an ordinary upright base glyph"
                else:
                    severity = "warning"
                    reason = "Extreme negative bearing reported in advisory mode"
            elif policy != "off" and value_em <= effective["warnBelowEm"]:
                severity = "warning"
                reason = "Negative bearing is below the normalized warning threshold"
            else:
                reason = "Negative bearing is within the configured advisory range"

        side_results[side] = {
            "em": value_em,
            "severity": severity,
            "reason": reason,
            "exempted": exempted,
            "geometrySupportsOverhang": geometry_supports_overhang,
        }
        if exempted:
            exemptions.append({"side": side, "reason": reason})
        if severity in ("warning", "blocked"):
            issues.append(
                {
                    "severity": severity,
                    "code": "negative_{}_bearing".format(side),
                    "message": reason,
                    "side": side,
                    "valueEm": value_em,
                }
            )
        if severity == "blocked":
            aggregate = "blocked"
        elif severity == "warning" and aggregate != "blocked":
            aggregate = "warning"
        elif severity == "exempted" and aggregate == "informational":
            aggregate = "exempted"

    left_em = proposed_norm.get("lsb")
    right_em = proposed_norm.get("rsb")
    if (
        policy != "off"
        and not any(value.get("exempted") for value in side_results.values())
        and ordinary_base
        and left_em is not None
        and right_em is not None
        and left_em <= effective["blockBelowEm"]
        and right_em <= effective["blockBelowEm"]
        and not allowed_by_name
    ):
        aggregate = "blocked" if policy == "guarded" and effective.get("blockOnOutliers") else "warning"
        issues.append(
            {
                "severity": aggregate,
                "code": "extreme_negative_bearings_both_sides",
                "message": "Large negative bearings on both sides of an ordinary base glyph",
            }
        )

    negative_aggregate = aggregate

    width_value = _coerce_float(proposed.get("width"))
    shape_width = None
    try:
        shape_width = float(measured.get("rFullExtreme")) - float(measured.get("lFullExtreme"))
    except Exception:
        shape_width = None
    width_severity = "informational"
    width_reason = "Advance width is plausible"
    if width_value is not None and width_value <= 0:
        width_severity = "blocked"
        width_reason = "Proposed advance width is nonpositive"
    elif width_value is not None and shape_width is not None and width_value < shape_width:
        width_severity = "warning"
        width_reason = "Proposed advance is narrower than the measured ink span"
    if width_severity in ("warning", "blocked"):
        issues.append(
            {
                "severity": width_severity,
                "code": "advance_width_collapse" if width_severity == "blocked" else "ink_exceeds_advance",
                "message": width_reason,
            }
        )
        if width_severity == "blocked":
            aggregate = "blocked"
        elif aggregate not in ("blocked",):
            aggregate = "warning"

    manual_review = glyph_class == "narrowPunctuation"
    confidence = {
        "level": "low" if manual_review else ("medium" if glyph_class in ("punctuation", "unclassified") else "high"),
        "manualReviewRequired": manual_review,
        "reason": (
            "Narrow punctuation depends on design rhythm and trusted visual references"
            if manual_review
            else "Classification and geometry support the ordinary spacing model"
        ),
    }
    if manual_review:
        issues.append(
            {
                "severity": "warning",
                "code": "narrow_punctuation_manual_review",
                "message": confidence["reason"],
            }
        )

    required_overrides: List[str] = []
    if aggregate == "blocked":
        required_overrides.append("blockedGlyphs")
    if manual_review:
        required_overrides.append("manualReviewGlyphs")
    disposition = "blocked" if aggregate == "blocked" else ("manual_review" if manual_review else "ready")
    return {
        "guards": effective,
        "normalizedMetrics": {"current": current_norm, "proposed": proposed_norm, "change": change_norm},
        "metricsTrustAssessment": trust,
        "negativeBearingAssessment": {
            "leftEm": left_em,
            "rightEm": right_em,
            "severity": negative_aggregate,
            "reason": next(
                (
                    value.get("reason")
                    for value in side_results.values()
                    if value.get("severity") == negative_aggregate
                ),
                "No suspicious negative bearing",
            ),
            "exempted": bool(exemptions),
            "exemptions": exemptions,
            "sides": side_results,
        },
        "widthAssessment": {
            "severity": width_severity,
            "reason": width_reason,
            "proposedWidthEm": proposed_norm.get("width"),
            "inkWidthEm": (shape_width / float(upm)) if shape_width is not None else None,
        },
        "confidence": confidence,
        "applicationAssessment": {
            "disposition": disposition,
            "eligible": not required_overrides,
            "requiredOverrides": required_overrides,
            "userOverride": None,
        },
        "issues": issues,
    }


def _scale_params(
    upm: float,
    x_height: float,
    area: float,
    factor: float,
) -> float:
    # Area scaling: areaUPM = area * ((upm/1000)^2); whiteArea = areaUPM * factor * 100
    return float(area) * ((float(upm) / 1000.0) ** 2) * float(factor) * 100.0


def _effective_default_reference(glyph: Any, font: Any) -> str:
    glyph_class = classify_glyph(glyph).get("glyphClass")
    if glyph_class == "uppercase":
        return "H"
    if glyph_class == "decimalFigure":
        return "one"
    if glyph_class in ("mark", "zeroWidth", "punctuation", "narrowPunctuation"):
        return "*"
    return "x"


def compute_suggestion_for_layer(
    *,
    font: Any,
    glyph: Any,
    layer: Any,
    master: Any,
    rules: Optional[Sequence[Dict[str, Any]]],
    defaults: Dict[str, Any],
    master_params: Dict[str, Any],
    guards: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    glyph_name = str(_safe_attr(glyph, "name", "") or "")
    master_id = str(_safe_attr(master, "id", "") or "")
    master_name = str(_safe_attr(master, "name", "") or "")

    warnings: List[str] = []
    issues: List[Dict[str, Any]] = []

    width, lsb, rsb = _get_layer_metrics(layer)
    current = {"width": _units_int(width), "lsb": _units_int(lsb), "rsb": _units_int(rsb)}
    classification = classify_glyph(glyph, layer)
    glyph_class = classification.get("glyphClass") or "unclassified"
    upm = float(_safe_attr(font, "upm", 1000) or 1000)
    italic_angle_early = float(master_params.get("italicAngle", _safe_attr(master, "italicAngle", 0.0) or 0.0))

    if glyph_class in ("mark", "zeroWidth"):
        proposed = dict(current)
        assessment = assess_spacing_suggestion(
            glyph=glyph,
            layer=layer,
            current=current,
            proposed=proposed,
            measured={},
            classification=classification,
            upm=upm,
            italic_angle=italic_angle_early,
            guards=guards,
        )
        return {
            "glyphName": glyph_name,
            "masterId": master_id,
            "masterName": master_name,
            "status": "skipped",
            "reason": "mark" if glyph_class == "mark" else "zero_width_glyph",
            "current": current,
            "proposed": proposed,
            "suggested": dict(proposed),
            "delta": {"width": 0, "lsb": 0, "rsb": 0},
            "glyphClass": glyph_class,
            "classification": classification,
            "referenceMode": "none",
            "requestedReferenceGlyph": str(defaults.get("referenceGlyph", "auto")),
            "resolvedReferenceGlyph": None,
            "referenceFallback": None,
            "tabularAssessment": {
                "mode": defaults.get("tabularMode", "auto"),
                "detected": False,
                "reason": "not_applicable_to_mark_or_zero_width_glyph",
                "preservedWidth": current.get("width"),
            },
            "warnings": warnings,
            **assessment,
        }

    bounds = _bounds_tuple(layer)
    if not bounds:
        return {
            "glyphName": glyph_name,
            "masterId": master_id,
            "masterName": master_name,
            "status": "skipped",
            "reason": "bounds_missing",
            "current": current,
            "warnings": warnings,
        }

    if _safe_attr(layer, "paths") is not None:
        try:
            has_paths = len(layer.paths) > 0
        except Exception:
            has_paths = False
    else:
        has_paths = False

    if _safe_attr(layer, "components") is not None:
        try:
            has_components = len(layer.components) > 0
        except Exception:
            has_components = False
    else:
        has_components = False

    if not has_paths and not has_components:
        return {
            "glyphName": glyph_name,
            "masterId": master_id,
            "masterName": master_name,
            "status": "skipped",
            "reason": "empty_layer",
            "current": current,
            "warnings": warnings,
        }

    if defaults.get("skipAutoAligned") and _layer_is_auto_aligned(layer):
        return {
            "glyphName": glyph_name,
            "masterId": master_id,
            "masterName": master_name,
            "status": "skipped",
            "reason": "auto_aligned_components",
            "current": current,
            "warnings": warnings,
        }

    left_key, right_key = _layer_has_metrics_keys(glyph, layer)
    if defaults.get("respectMetricsKeys") and left_key and right_key:
        return {
            "glyphName": glyph_name,
            "masterId": master_id,
            "masterName": master_name,
            "status": "skipped",
            "reason": "metrics_keys_both_sides",
            "current": current,
            "warnings": ["metrics_keys_left", "metrics_keys_right"],
        }

    rule = select_rule(glyph, rules)
    factor = resolve_factor(rule, defaults)
    reference_resolution = resolve_reference(
        font=font,
        glyph=glyph,
        layer=layer,
        rule=rule,
        defaults=defaults,
        classification=classification,
    )
    ref_glyph = reference_resolution.get("referenceGlyph")
    ref_name = reference_resolution.get("resolvedReferenceGlyph")
    reference_fallback = reference_resolution.get("referenceFallback")
    if reference_fallback:
        warnings.append("reference_fallback_used")
        issues.append(
            {
                "severity": "warning",
                "code": "reference_fallback_used",
                "message": "Preferred automatic reference was unavailable",
                "context": dict(reference_fallback),
            }
        )
    reference_fields = {
        "glyphClass": glyph_class,
        "classification": classification,
        "referenceMode": reference_resolution.get("referenceMode"),
        "requestedReferenceGlyph": reference_resolution.get("requestedReferenceGlyph"),
        "resolvedReferenceGlyph": reference_resolution.get("resolvedReferenceGlyph"),
        "referenceFallback": reference_fallback,
    }

    if not ref_glyph:
        missing_reason = "explicit_reference_missing" if reference_resolution.get("referenceMode") == "explicit" else "reference_glyph_missing"
        return {
            "glyphName": glyph_name,
            "masterId": master_id,
            "masterName": master_name,
            "status": "skipped",
            "reason": missing_reason,
            "current": current,
            "proposed": dict(current),
            "suggested": dict(current),
            **reference_fields,
            "reference": {"glyphName": None},
            "issues": issues,
            "warnings": warnings,
        }

    try:
        ref_layer = ref_glyph.layers[master_id]
    except Exception:
        ref_layer = None

    if not ref_layer:
        return {
            "glyphName": glyph_name,
            "masterId": master_id,
            "masterName": master_name,
            "status": "skipped",
            "reason": "reference_layer_missing",
            "current": current,
            "reference": {"glyphName": ref_name},
            **reference_fields,
            "warnings": warnings,
        }

    ref_bounds = _bounds_tuple(ref_layer)
    if not ref_bounds:
        return {
            "glyphName": glyph_name,
            "masterId": master_id,
            "masterName": master_name,
            "status": "skipped",
            "reason": "reference_bounds_missing",
            "current": current,
            "reference": {"glyphName": ref_name},
            **reference_fields,
            "warnings": warnings,
        }

    x_height = _coerce_float(master_params.get("xHeight"))
    if x_height is None:
        x_height = _coerce_float(_safe_attr(master, "xHeight"))
    if x_height is None or x_height <= 0:
        # Avoid division by zero; fall back to measured ref height.
        x_height = float(ref_bounds[3] - ref_bounds[2]) or 1.0

    area = float(master_params.get("area", defaults.get("area", DEFAULTS["area"])))
    depth_pct = float(master_params.get("depth", defaults.get("depth", DEFAULTS["depth"])))
    over_pct = float(master_params.get("over", defaults.get("over", DEFAULTS["over"])))
    freq = float(master_params.get("frequency", defaults.get("frequency", DEFAULTS["frequency"])))
    italic_angle = float(master_params.get("italicAngle", _safe_attr(master, "italicAngle", 0.0) or 0.0))

    overshoot = x_height * (over_pct / 100.0)
    depth_units = x_height * (depth_pct / 100.0)

    y_min_ref = float(ref_bounds[2] - overshoot)
    y_max_ref = float(ref_bounds[3] + overshoot)
    height = float(y_max_ref - y_min_ref)
    if height <= 0:
        return {
            "glyphName": glyph_name,
            "masterId": master_id,
            "masterName": master_name,
            "status": "skipped",
            "reason": "invalid_reference_height",
            "current": current,
            "reference": {"glyphName": ref_name},
            **reference_fields,
            "warnings": warnings,
        }

    coverage = _coverage_ratio(bounds, y_min_ref, y_max_ref)
    if coverage < float(defaults.get("minCoverageRatio", DEFAULTS["minCoverageRatio"])):
        return {
            "glyphName": glyph_name,
            "masterId": master_id,
            "masterName": master_name,
            "status": "skipped",
            "reason": "insufficient_vertical_coverage",
            "current": current,
            "reference": {"glyphName": ref_name, "yMin": y_min_ref, "yMax": y_max_ref, "coverageRatio": coverage},
            **reference_fields,
            "warnings": warnings,
        }

    include_components = bool(defaults.get("includeComponents", DEFAULTS["includeComponents"]))
    italic_mode = str(defaults.get("italicMode", DEFAULTS["italicMode"]) or "deslant").lower()
    if italic_mode in ("ht_approx", "tan"):
        italic_mode = "deslant"

    # Measure edges in full range for overshoot compensation.
    full_bounds = bounds
    full_measure = measure_layer_edges(layer, y_min=full_bounds[2], y_max=full_bounds[3], step=freq, include_components=include_components)
    zone_measure = measure_layer_edges(layer, y_min=y_min_ref, y_max=y_max_ref, step=freq, include_components=include_components)
    if not full_measure or not zone_measure:
        return {
            "glyphName": glyph_name,
            "masterId": master_id,
            "masterName": master_name,
            "status": "skipped",
            "reason": "measurement_failed",
            "current": current,
            "reference": {"glyphName": ref_name, "yMin": y_min_ref, "yMax": y_max_ref, "coverageRatio": coverage},
            **reference_fields,
            "warnings": warnings,
        }

    # Deslant if requested.
    def _maybe_deslant(xs: List[Optional[float]], ys: List[float]) -> List[Optional[float]]:
        if italic_mode != "deslant" or abs(italic_angle) < 1e-6:
            return xs
        out: List[Optional[float]] = []
        for x, y in zip(xs, ys):
            if x is None:
                out.append(None)
            else:
                out.append(_deslant_x(float(x), float(y), x_height=x_height, italic_angle=italic_angle))
        return out

    full_left = _maybe_deslant(full_measure.left_xs, full_measure.ys)
    full_right = _maybe_deslant(full_measure.right_xs, full_measure.ys)
    zone_left = _maybe_deslant(zone_measure.left_xs, zone_measure.ys)
    zone_right = _maybe_deslant(zone_measure.right_xs, zone_measure.ys)

    # Need at least one intersection inside zone.
    z_left_min, _ = _min_max_non_none(zone_left)
    _, z_right_max = _min_max_non_none(zone_right)
    if z_left_min is None or z_right_max is None:
        return {
            "glyphName": glyph_name,
            "masterId": master_id,
            "masterName": master_name,
            "status": "skipped",
            "reason": "no_intersections_in_zone",
            "current": current,
            "reference": {"glyphName": ref_name, "yMin": y_min_ref, "yMax": y_max_ref, "coverageRatio": coverage},
            **reference_fields,
            "warnings": warnings,
        }

    # Full extremes (overshoot compensation).
    f_left_min, _ = _min_max_non_none(full_left)
    _, f_right_max = _min_max_non_none(full_right)
    if f_left_min is None or f_right_max is None:
        return {
            "glyphName": glyph_name,
            "masterId": master_id,
            "masterName": master_name,
            "status": "skipped",
            "reason": "no_intersections_full_bounds",
            "current": current,
            "reference": {"glyphName": ref_name, "yMin": y_min_ref, "yMax": y_max_ref, "coverageRatio": coverage},
            **reference_fields,
            "warnings": warnings,
        }

    l_extreme = float(z_left_min)
    r_extreme = float(z_right_max)
    l_full_extreme = float(f_left_min)
    r_full_extreme = float(f_right_max)

    distance_l = float(math.ceil(l_extreme - l_full_extreme))
    distance_r = float(math.ceil(r_full_extreme - r_extreme))

    max_depth_l = l_extreme + depth_units
    min_depth_r = r_extreme - depth_units

    left_xs: List[float] = []
    right_xs: List[float] = []
    clamped_left = 0
    clamped_right = 0

    for x in zone_left:
        if x is None:
            xi = max_depth_l
            clamped_left += 1
        else:
            xi = max(l_extreme, min(float(x), max_depth_l))
            if xi != float(x):
                clamped_left += 1
        left_xs.append(xi)

    for x in zone_right:
        if x is None:
            xi = min_depth_r
            clamped_right += 1
        else:
            xi = min(r_extreme, max(float(x), min_depth_r))
            if xi != float(x):
                clamped_right += 1
        right_xs.append(xi)

    left_xs = _diagonize_left(left_xs, step=freq)
    right_xs = _diagonize_right(right_xs, step=freq)

    left_indents = [max(0.0, x - l_extreme) for x in left_xs]
    right_indents = [max(0.0, r_extreme - x) for x in right_xs]

    area_left = _trapezoid_area(zone_measure.ys, left_indents)
    area_right = _trapezoid_area(zone_measure.ys, right_indents)

    white_area = _scale_params(upm=upm, x_height=x_height, area=area, factor=factor)
    target_area = height * white_area / x_height

    sb_left = (target_area - area_left) / height
    sb_right = (target_area - area_right) / height

    suggested_lsb = float(math.ceil(0.0 - distance_l + sb_left))
    suggested_rsb = float(math.ceil(0.0 - distance_r + sb_right))

    width_shape = float(r_full_extreme - l_full_extreme)
    suggested_width = width_shape + suggested_lsb + suggested_rsb

    # Tabular: preserve width only when explicitly requested or reliably detected.
    tabular_assessment = assess_tabular_mode(
        font=font,
        glyph=glyph,
        layer=layer,
        master=master,
        defaults=defaults,
        classification=classification,
    )
    tabular_width = tabular_assessment.get("preservedWidth")
    if tabular_assessment.get("detected") and tabular_width is not None:
        # Preserve width using integer arithmetic to avoid half-unit sidebearings.
        target_w_int = _units_int(tabular_width)
        if target_w_int is not None:
            sug_l_int = _units_int(suggested_lsb)
            sug_r_int = _units_int(suggested_rsb)
            shape_int = _units_int(width_shape)
            if sug_l_int is not None and sug_r_int is not None and shape_int is not None:
                sug_w_int = shape_int + sug_l_int + sug_r_int
                diff_total = int(target_w_int - sug_w_int)
                dl, dr = _split_int_delta(diff_total)
                suggested_lsb = float(sug_l_int + dl)
                suggested_rsb = float(sug_r_int + dr)
                suggested_width = float(target_w_int)
                warnings.append("tabular_width_preserved")
            else:
                warnings.append("tabular_width_preserve_failed")
        else:
            warnings.append("tabular_width_preserve_failed")

    if defaults.get("respectMetricsKeys") and left_key:
        warnings.append("metrics_keys_left")
        suggested_lsb = float(current["lsb"]) if current.get("lsb") is not None else suggested_lsb
    if defaults.get("respectMetricsKeys") and right_key:
        warnings.append("metrics_keys_right")
        suggested_rsb = float(current["rsb"]) if current.get("rsb") is not None else suggested_rsb

    suggested_int = {
        "lsb": _units_int(suggested_lsb),
        "rsb": _units_int(suggested_rsb),
    }
    shape_int = _units_int(width_shape)
    if shape_int is not None and suggested_int["lsb"] is not None and suggested_int["rsb"] is not None:
        suggested_int["width"] = shape_int + int(suggested_int["lsb"]) + int(suggested_int["rsb"])
    else:
        suggested_int["width"] = _units_int(suggested_width)

    # If tabular preservation was requested, width must match the target exactly.
    if "tabular_width_preserved" in warnings and tabular_width is not None:
        target_w_int = _units_int(tabular_width)
        if target_w_int is not None:
            suggested_int["width"] = int(target_w_int)

    delta = {
        "width": (suggested_int["width"] - current["width"]) if (suggested_int.get("width") is not None and current.get("width") is not None) else None,
        "lsb": (suggested_int["lsb"] - current["lsb"]) if (suggested_int.get("lsb") is not None and current.get("lsb") is not None) else None,
        "rsb": (suggested_int["rsb"] - current["rsb"]) if (suggested_int.get("rsb") is not None and current.get("rsb") is not None) else None,
    }

    measured = {
        "height": height,
        "leftArea": area_left,
        "rightArea": area_right,
        "clampedLeftCount": clamped_left,
        "clampedRightCount": clamped_right,
        "lExtreme": l_extreme,
        "rExtreme": r_extreme,
        "lFullExtreme": l_full_extreme,
        "rFullExtreme": r_full_extreme,
        "distanceLeft": distance_l,
        "distanceRight": distance_r,
    }

    target = {
        "whiteArea": white_area,
        "targetArea": target_area,
        "targetAvg": target_area / height,
    }

    reference = {
        "glyphName": ref_name,
        "yMin": y_min_ref,
        "yMax": y_max_ref,
        "overUnits": overshoot,
        "coverageRatio": coverage,
    }
    params = {
        "area": area,
        "depth": depth_pct,
        "over": over_pct,
        "frequency": freq,
        "factor": factor,
        "italicMode": italic_mode,
        "italicAngle": italic_angle,
    }

    if clamped_left:
        warnings.append(f"depth_clamped_left_count={clamped_left}")
    if clamped_right:
        warnings.append(f"depth_clamped_right_count={clamped_right}")

    assessment = assess_spacing_suggestion(
        glyph=glyph,
        layer=layer,
        current=current,
        proposed=suggested_int,
        measured=measured,
        classification=classification,
        upm=upm,
        italic_angle=italic_angle,
        guards=guards,
    )
    issues.extend(assessment.pop("issues", []))

    result: Dict[str, Any] = {
        "glyphName": glyph_name,
        "masterId": master_id,
        "masterName": master_name,
        "status": "ok",
        "reason": None,
        "current": current,
        "proposed": dict(suggested_int),
        "reference": reference,
        "glyphClass": glyph_class,
        "classification": classification,
        "referenceMode": reference_resolution.get("referenceMode"),
        "requestedReferenceGlyph": reference_resolution.get("requestedReferenceGlyph"),
        "resolvedReferenceGlyph": reference_resolution.get("resolvedReferenceGlyph"),
        "referenceFallback": reference_fallback,
        "tabularAssessment": tabular_assessment,
        "params": params,
        "measured": measured,
        "target": target,
        "suggested": suggested_int,
        "delta": delta,
        "issues": issues,
        "warnings": warnings,
        **assessment,
    }

    if defaults.get("includeSamples"):
        result["samples"] = {
            "ys": list(zone_measure.ys),
            "leftXs": list(left_xs),
            "rightXs": list(right_xs),
        }
    return result


def clamp_suggestion(
    *,
    current: Dict[str, Any],
    suggested: Dict[str, Any],
    clamp: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[str]]:
    """Clamp suggested metrics relative to current, returning (new_suggested, warnings)."""
    clamp = clamp or {}
    warnings: List[str] = []

    max_delta_l = _coerce_float(clamp.get("maxDeltaLSB"))
    max_delta_r = _coerce_float(clamp.get("maxDeltaRSB"))
    min_lsb = _coerce_float(clamp.get("minLSB"))
    min_rsb = _coerce_float(clamp.get("minRSB"))

    out = dict(suggested)

    cur_l = _coerce_float(current.get("lsb"))
    cur_r = _coerce_float(current.get("rsb"))
    sug_l = _coerce_float(suggested.get("lsb"))
    sug_r = _coerce_float(suggested.get("rsb"))

    if cur_l is not None and sug_l is not None and max_delta_l is not None:
        dl = sug_l - cur_l
        if abs(dl) > max_delta_l:
            out["lsb"] = cur_l + max(-max_delta_l, min(max_delta_l, dl))
            warnings.append("clamped_lsb_delta")

    if cur_r is not None and sug_r is not None and max_delta_r is not None:
        dr = sug_r - cur_r
        if abs(dr) > max_delta_r:
            out["rsb"] = cur_r + max(-max_delta_r, min(max_delta_r, dr))
            warnings.append("clamped_rsb_delta")

    if min_lsb is not None and out.get("lsb") is not None:
        try:
            if float(out["lsb"]) < min_lsb:
                out["lsb"] = float(min_lsb)
                warnings.append("clamped_lsb_min")
        except Exception:
            pass

    if min_rsb is not None and out.get("rsb") is not None:
        try:
            if float(out["rsb"]) < min_rsb:
                out["rsb"] = float(min_rsb)
                warnings.append("clamped_rsb_min")
        except Exception:
            pass

    # Font-unit metrics should be integers; normalize here so apply_spacing and
    # review_spacing never return .5 sidebearings.
    out["lsb"] = _units_int(out.get("lsb"))
    out["rsb"] = _units_int(out.get("rsb"))

    return out, warnings
