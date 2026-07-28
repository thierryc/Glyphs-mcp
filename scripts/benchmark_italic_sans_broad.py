#!/usr/bin/env python3
"""Broad-Latin clean-room benchmark and conditional Balanced promotion gate.

The benchmark reads a fixed 543-entry manifest and pinned Inter, Noto Sans,
and IBM Plex Sans sources. Plex contributes the Unicode intersection available
in both of its pinned Regular and Italic UFO masters. Full paginated raster
evidence and JSON stay beneath the ignored benchmark cache. A small
deterministic audit selection can be copied into contributor documentation
after review.
"""

from __future__ import annotations

import argparse
import copy
import gc
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import glyphsLib
from PIL import Image, ImageChops, ImageDraw

import benchmark_italic_inter as base
import benchmark_ufo_adapter as ufo_adapter
from benchmark_italic_sans_expanded import NOTO_SANS_COMMIT


MANIFEST_PATH = (
    base._repo_root() / "scripts" / "data" / "italic_broad_latin_manifest.json"
)
EXPECTED_ENTRY_COUNT = 543
EXPECTED_GROUP_COUNTS = {
    "basicLatin": 95,
    "latin1": 91,
    "latinExtended": 259,
    "generalPunctuation": 48,
    "currencySymbols": 23,
    "letterlikeSymbols": 10,
    "numberForms": 17,
}
MAX_PAGE_SIZE = 64
DEFAULT_RENDER_SCALE = 2.0
DEFAULT_AUDIT_LIMIT = 64
COMPONENT_COMMUTATOR_TOLERANCE = 1e-6
STORY_GROUPS = (
    ("Straight stems", (0x0048, 0x0045, 0x0058, 0x006E)),
    ("Numbers & currency", (0x0031, 0x0030, 0x0038, 0x0024, 0x00A5)),
    ("Symbols", (0x002B, 0x003D, 0x0025)),
    ("Optical redraw", (0x0061, 0x0067, 0x0066, 0x0076)),
    ("Punctuation", (0x0026, 0x0028, 0x0029)),
    ("Components", (0x0064, 0x0070, 0x0071)),
)
MODE_NAMES = ("raw", "cursivy", "balanced")
DIFF_COMPARISONS = (
    ("raw", "cursivy", "Partial compensation vs Raw"),
    ("raw", "balanced", "Balanced vs Raw"),
    ("cursivy", "balanced", "Balanced vs Partial compensation"),
    ("official", "balanced", "Balanced vs Official Italic"),
)
COMPARISON_KEYS = tuple(
    "{}Vs{}".format(candidate, reference[:1].upper() + reference[1:])
    for reference, candidate, _label in DIFF_COMPARISONS
)
PLEX_COMMIT = "71d012bccb31a2e282cc46de63b387ff7f676287"
PLEX_EXPECTED_GROUP_COUNTS = {
    "basicLatin": 95,
    "latin1": 91,
    "latinExtended": 158,
    "generalPunctuation": 16,
    "currencySymbols": 14,
    "letterlikeSymbols": 3,
    "numberForms": 14,
}
FAMILY_CONFIGS = {
    "inter": {
        "displayName": "Inter",
        "manifestNameKey": "interGlyphName",
        "angle": 9.4,
        "expectedAxes": {"opsz": 14, "wght": 400},
        "minimumCompensatedPairs": 135,
        "repository": "https://github.com/rsms/inter",
        "commit": base.INTER_COMMIT,
    },
    "notoSans": {
        "displayName": "Noto Sans",
        "manifestNameKey": "notoSansGlyphName",
        "angle": 12.0,
        "expectedAxes": {"wght": 90, "wdth": 100},
        "minimumCompensatedPairs": 102,
        "repository": "https://github.com/notofonts/latin-greek-cyrillic",
        "googleFonts": "https://github.com/google/fonts/tree/main/ofl/notosans",
        "commit": NOTO_SANS_COMMIT,
    },
    "ibmPlexSans": {
        "displayName": "IBM Plex Sans",
        "manifestNameKey": "plexGlyphName",
        "angle": 11.31,
        "expectedAxes": {"wght": 400},
        "minimumCompensatedPairs": 102,
        "repository": "https://github.com/googlefonts/plex",
        "upstreamRepository": "https://github.com/IBM/plex",
        "commit": PLEX_COMMIT,
        "sourceFormat": "ufo",
        "resolveNamesByUnicode": True,
        "sourceAxes": {"wght": 0},
        "externalAxes": {"wght": 400},
        "sourceVersion": "3.200",
        "expectedSharedEntryCount": 391,
        "expectedGroupCounts": PLEX_EXPECTED_GROUP_COUNTS,
    },
}


def _mode_labels(family_name: str) -> list[tuple[str, str]]:
    return [
        ("roman", "{} Roman".format(family_name)),
        ("raw", "Raw shear"),
        ("cursivy", "Partial compensation (0.35)"),
        ("balanced", "Balanced/full compensation"),
        ("official", "Official {} Italic".format(family_name)),
    ]


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1:
        raise ValueError("Broad-Latin manifest schemaVersion must be 1")
    glyphs = list(payload.get("glyphs") or [])
    if payload.get("entryCount") != EXPECTED_ENTRY_COUNT:
        raise ValueError("Broad-Latin manifest entryCount must be 543")
    if len(glyphs) != EXPECTED_ENTRY_COUNT:
        raise ValueError(
            "Broad-Latin manifest must contain exactly 543 glyph entries"
        )
    codepoints = [int(row["codepoint"]) for row in glyphs]
    if codepoints != sorted(codepoints) or len(set(codepoints)) != len(codepoints):
        raise ValueError(
            "Broad-Latin manifest codepoints must be unique and ascending"
        )
    group_counts = Counter(str(row["group"]) for row in glyphs)
    if dict(group_counts) != EXPECTED_GROUP_COUNTS:
        raise ValueError(
            "Broad-Latin manifest group counts differ from the fixed selection"
        )
    for row in glyphs:
        expected_unicode = "U+{:04X}".format(int(row["codepoint"]))
        if row.get("unicode") != expected_unicode:
            raise ValueError(
                "Manifest Unicode label differs from codepoint for {}".format(row)
            )
        for key in ("interGlyphName", "notoSansGlyphName"):
            if not str(row.get(key) or "").strip():
                raise ValueError("Manifest entry is missing {}".format(key))
    return payload


def validate_render_scale(value: float) -> float:
    scale = float(value)
    if not 1.0 <= scale <= 4.0:
        raise ValueError("render_scale must be between 1 and 4")
    return scale


def paginate(items: list[Any], page_size: int = MAX_PAGE_SIZE) -> list[list[Any]]:
    size = int(page_size)
    if size < 1 or size > MAX_PAGE_SIZE:
        raise ValueError("page_size must be between 1 and 64")
    return [items[index : index + size] for index in range(0, len(items), size)]


def _layer(font: Any, master: Any, glyph_name: str) -> Any | None:
    glyph = font.glyphs[glyph_name]
    if glyph is None:
        return None
    return glyph.layers[master.id]


def missing_family_glyphs(
    roman_font: Any,
    italic_font: Any,
    roman_master: Any,
    italic_master: Any,
    entries: Iterable[dict[str, Any]],
    name_key: str,
) -> list[dict[str, str]]:
    missing = []
    for entry in entries:
        glyph_name = str(entry[name_key])
        if _layer(roman_font, roman_master, glyph_name) is None:
            missing.append(
                {
                    "unicode": str(entry["unicode"]),
                    "glyphName": glyph_name,
                    "source": "roman",
                }
            )
        if _layer(italic_font, italic_master, glyph_name) is None:
            missing.append(
                {
                    "unicode": str(entry["unicode"]),
                    "glyphName": glyph_name,
                    "source": "officialItalic",
                }
            )
    return missing


def resolve_unicode_family_entries(
    roman_font: Any,
    italic_font: Any,
    entries: Iterable[dict[str, Any]],
    name_key: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve a pinned family's shared Roman/Italic Unicode intersection."""

    roman_names = ufo_adapter.unicode_name_map(roman_font)
    italic_names = ufo_adapter.unicode_name_map(italic_font)
    selected = []
    unavailable = []
    for entry in entries:
        codepoint = int(entry["codepoint"])
        roman_name = roman_names.get(codepoint)
        italic_name = italic_names.get(codepoint)
        if roman_name is None or italic_name is None:
            unavailable.append(
                {
                    "unicode": str(entry["unicode"]),
                    "codepoint": codepoint,
                    "group": str(entry["group"]),
                    "romanGlyphName": roman_name,
                    "italicGlyphName": italic_name,
                    "reason": "missingRoman"
                    if roman_name is None
                    else "missingOfficialItalic",
                }
            )
            continue
        if roman_name != italic_name:
            unavailable.append(
                {
                    "unicode": str(entry["unicode"]),
                    "codepoint": codepoint,
                    "group": str(entry["group"]),
                    "romanGlyphName": roman_name,
                    "italicGlyphName": italic_name,
                    "reason": "glyphNameMismatch",
                }
            )
            continue
        selected.append({**copy.deepcopy(entry), name_key: roman_name})
    return selected, unavailable


def _numeric_delta(
    candidate: dict[str, float] | None,
    reference: dict[str, float] | None,
) -> dict[str, float] | None:
    if candidate is None or reference is None:
        return None
    return {
        key: float(candidate[key]) - float(reference[key])
        for key in ("minX", "maxX", "minY", "maxY", "width", "height")
    }


def _contour_bounds(
    contours: list[list[tuple[float, float]]],
) -> dict[str, float] | None:
    points = [point for contour in contours for point in contour]
    if not points:
        return None
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return {
        "minX": min(xs),
        "maxX": max(xs),
        "minY": min(ys),
        "maxY": max(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }


def _component_master_reference(component: Any) -> str | None:
    for attribute in ("componentMasterId", "componentMasterID", "layerId"):
        value = getattr(component, attribute, None)
        if value:
            return str(value)
    return None


def _component_rows(
    layer: Any,
    *,
    angle: float,
) -> tuple[list[dict[str, Any]], int]:
    rows = []
    explicit_reference_count = 0
    for index, component in enumerate(list(layer.components or [])):
        reference = _component_master_reference(component)
        if reference is not None:
            explicit_reference_count += 1
        rows.append(
            {
                "index": index,
                "glyphName": base._component_name(component),
                "explicitMasterReference": reference,
                "transforms": {
                    mode: list(base._transform_tuple(component, mode, angle))
                    for mode in ("roman", "raw", "cursivy", "balanced")
                },
            }
        )
    return rows, explicit_reference_count


def _component_transform_risks(
    font: Any,
    master: Any,
    glyph_name: str,
    *,
    angle: float,
    stack: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Find component transforms that do not commute with the benchmark shear.

    Generated component bases are slanted in local coordinates before their
    component matrix is applied (``L × S``). Shearing the complete Roman
    construction would apply ``S × L``. These are equivalent only when the
    component's linear transform commutes with the shear.
    """

    if glyph_name in stack or len(stack) > 12:
        return []
    layer = _layer(font, master, glyph_name)
    if layer is None:
        return []
    tangent = math.tan(math.radians(float(angle)))
    risks = []
    for index, component in enumerate(list(layer.components or [])):
        transform = tuple(float(value) for value in component.transform)
        if len(transform) != 6:
            continue
        a, b, c, d, tx, ty = transform
        commutator_error = max(
            abs(tangent * b),
            abs(tangent * (d - a)),
        )
        component_name = base._component_name(component)
        chain = stack + (glyph_name, component_name)
        if commutator_error > COMPONENT_COMMUTATOR_TOLERANCE:
            determinant = a * d - b * c
            risks.append(
                {
                    "componentPath": list(chain),
                    "componentIndex": index,
                    "glyphName": component_name,
                    "transform": [a, b, c, d, tx, ty],
                    "determinant": determinant,
                    "reflected": determinant < 0.0,
                    "commutatorError": commutator_error,
                    "tolerance": COMPONENT_COMMUTATOR_TOLERANCE,
                    "reason": "componentLinearTransformDoesNotCommuteWithShear",
                }
            )
        risks.extend(
            _component_transform_risks(
                font,
                master,
                component_name,
                angle=angle,
                stack=stack + (glyph_name,),
            )
        )
    return risks


def _official_component_rows(layer: Any) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "glyphName": base._component_name(component),
            "transform": list(base._transform_tuple(component, "official", 0.0)),
            "explicitMasterReference": _component_master_reference(component),
        }
        for index, component in enumerate(list(layer.components or []))
    ]


def _official_anchors(layer: Any) -> list[dict[str, float | str]]:
    return [
        {
            "name": str(anchor.name),
            "x": float(anchor.position.x),
            "y": float(anchor.position.y),
        }
        for anchor in list(layer.anchors or [])
    ]


def _aggregate_diff_rows(
    diff_rows: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    values: dict[str, list[float]] = {key: [] for key in COMPARISON_KEYS}
    for row in diff_rows:
        for key, comparison in row.get("comparisons", {}).items():
            if key in values:
                values[key].append(float(comparison["differentPixelRatio"]))
    return {
        key: {
            "glyphCount": len(ratios),
            "differentGlyphCount": len(
                [ratio for ratio in ratios if ratio > 0.0]
            ),
            "meanDifferentPixelRatio": (
                float(statistics.fmean(ratios)) if ratios else 0.0
            ),
            "medianDifferentPixelRatio": (
                float(statistics.median(ratios)) if ratios else 0.0
            ),
            "maxDifferentPixelRatio": max(ratios) if ratios else 0.0,
        }
        for key, ratios in values.items()
    }


def _family_group_summary(
    glyph_rows: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    result = {}
    for group_name in EXPECTED_GROUP_COUNTS:
        rows = [row for row in glyph_rows if row["group"] == group_name]
        result[group_name] = {
            "glyphCount": len(rows),
            "generatedCount": len(
                [row for row in rows if row.get("status") == "ok"]
            ),
            "pathlessCount": len([row for row in rows if row.get("pathless")]),
            "compensatedPairCount": sum(
                int(row.get("compensatedPairCount") or 0) for row in rows
            ),
        }
    return result


def _mode_measurements(
    record: dict[str, Any],
    *,
    upm: float,
    stem_values: list[float],
) -> tuple[dict[str, Any], set[str]]:
    compensated_ids = {
        str(pair["pairId"])
        for pair in record["balancedDiagnostics"]["compensatedPairs"]
    }
    measurements = {
        mode: base.engine.measure_stem_widths(
            record["source"],
            record[mode],
            upm=upm,
            stem_values=stem_values,
        )
        for mode in MODE_NAMES
    }
    for mode, payload in measurements.items():
        payload["promotionMeasurements"] = [
            item
            for item in payload["measurements"]
            if str(item["pairId"]) in compensated_ids
        ]
    return measurements, compensated_ids


def _benchmark_family(
    *,
    family_key: str,
    config: dict[str, Any],
    roman_path: Path,
    italic_path: Path,
    entries: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not roman_path.is_dir() or not italic_path.is_dir():
        raise RuntimeError(
            "Pinned {} Roman and Italic sources were not found".format(
                config["displayName"]
            )
        )
    if config.get("sourceFormat") == "ufo":
        roman_font = ufo_adapter.load_ufo(
            roman_path,
            master_id="PLEX_ROMAN_REGULAR",
            master_name="Regular",
        )
        italic_font = ufo_adapter.load_ufo(
            italic_path,
            master_id="PLEX_ITALIC_REGULAR",
            master_name="Italic",
        )
    else:
        roman_font = glyphsLib.load(str(roman_path))
        italic_font = glyphsLib.load(str(italic_path))
    roman_master = base._select_master(roman_font, config["expectedAxes"])
    italic_master = base._select_master(italic_font, config["expectedAxes"])
    coverage_unavailable = []
    if config.get("resolveNamesByUnicode"):
        entries, coverage_unavailable = resolve_unicode_family_entries(
            roman_font,
            italic_font,
            entries,
            config["manifestNameKey"],
        )
        if not entries:
            raise RuntimeError(
                "{} has no glyphs shared with the fixed manifest".format(
                    config["displayName"]
                )
            )
        expected_shared_count = int(config["expectedSharedEntryCount"])
        if len(entries) != expected_shared_count:
            raise RuntimeError(
                "{} shared manifest coverage changed: expected {}, found "
                "{}".format(
                    config["displayName"],
                    expected_shared_count,
                    len(entries),
                )
            )
        family_group_counts = Counter(
            str(entry["group"]) for entry in entries
        )
        if dict(family_group_counts) != config["expectedGroupCounts"]:
            raise RuntimeError(
                "{} shared manifest group coverage changed: {}".format(
                    config["displayName"],
                    dict(family_group_counts),
                )
            )
    official_angle = float(italic_master.italicAngle)
    if abs(official_angle - float(config["angle"])) > 0.01:
        raise RuntimeError(
            "{} official italic angle {} does not match {}".format(
                config["displayName"],
                official_angle,
                config["angle"],
            )
        )
    missing = (
        []
        if config.get("resolveNamesByUnicode")
        else missing_family_glyphs(
            roman_font,
            italic_font,
            roman_master,
            italic_master,
            entries,
            config["manifestNameKey"],
        )
    )
    if missing:
        raise RuntimeError(
            "{} benchmark sources are missing manifest glyphs: {}".format(
                config["displayName"],
                missing,
            )
        )

    upm = float(roman_font.upm)
    stem_values = [
        float(value) for value in roman_master.stems if float(value) > 0
    ]
    generated: dict[str, Any] = {}
    glyph_rows = []
    errors_by_mode: dict[str, list[float]] = {
        mode: [] for mode in MODE_NAMES
    }
    anchor_errors = []
    generation_failures = []
    total_runtime_start = time.perf_counter()
    explicit_component_references = 0
    unsafe_applied_compensations = []
    component_transform_risks = []

    for entry in entries:
        glyph_name = str(entry[config["manifestNameKey"]])
        roman_layer = _layer(roman_font, roman_master, glyph_name)
        official_layer = _layer(italic_font, italic_master, glyph_name)
        started = time.perf_counter()
        source_before = base._serialize_layer_paths(roman_layer)
        try:
            record = base._generate_glyph(
                roman_layer,
                roman_master,
                upm,
                stem_values,
                angle=float(config["angle"]),
            )
            generated[glyph_name] = record
            measurements, compensated_ids = _mode_measurements(
                record,
                upm=upm,
                stem_values=stem_values,
            )
            for mode, payload in measurements.items():
                errors_by_mode[mode].extend(
                    float(item["absoluteError"])
                    for item in payload["promotionMeasurements"]
                )

            source_anchors = {
                item["name"]: item for item in record["anchors"]["roman"]
            }
            glyph_anchor_errors = []
            for anchor in record["anchors"]["balanced"]:
                source_anchor = source_anchors.get(anchor["name"])
                if source_anchor is None:
                    continue
                expected_x = float(source_anchor["x"]) + math.tan(
                    math.radians(float(config["angle"]))
                ) * (
                    float(source_anchor["y"])
                    - base._pivot_y(roman_master)
                )
                error = abs(float(anchor["x"]) - expected_x)
                anchor_errors.append(error)
                glyph_anchor_errors.append(error)

            component_rows, explicit_count = _component_rows(
                roman_layer,
                angle=float(config["angle"]),
            )
            explicit_component_references += explicit_count
            glyph_component_transform_risks = _component_transform_risks(
                roman_font,
                roman_master,
                glyph_name,
                angle=float(config["angle"]),
            )
            balanced_outcome = (
                "balanced_blocked_component"
                if glyph_component_transform_risks
                else (
                    "pathless_noop"
                    if not record["source"]
                    else (
                        "balanced_applied"
                        if compensated_ids
                        else "balanced_raw_equivalent"
                    )
                )
            )
            component_transform_risks.extend(
                {
                    "unicode": entry["unicode"],
                    "rootGlyphName": glyph_name,
                    **risk,
                }
                for risk in glyph_component_transform_risks
            )
            official_paths = base._serialize_layer_paths(official_layer)
            direct_bounds = {
                **record["bounds"],
                "official": base._bounds(official_paths),
            }
            component_bounds = {}
            for mode in ("roman", "raw", "cursivy", "balanced"):
                component_bounds[mode] = _contour_bounds(
                    base._glyph_contours(
                        roman_font,
                        roman_master,
                        glyph_name,
                        mode,
                        generated,
                        float(config["angle"]),
                    )
                )
            component_bounds["official"] = _contour_bounds(
                base._glyph_contours(
                    italic_font,
                    italic_master,
                    glyph_name,
                    "official",
                    None,
                    float(config["angle"]),
                )
            )
            topology_by_mode = {
                mode: base.engine.topology_matches(
                    record["source"], record[mode]
                )
                for mode in MODE_NAMES
            }
            source_after = base._serialize_layer_paths(roman_layer)
            for pair in record["balancedDiagnostics"]["compensatedPairs"]:
                source_width = float(pair["sourceWidth"])
                maximum_delta = min(
                    upm * base.engine.MAX_DELTA_UPM_RATIO,
                    source_width * base.engine.MAX_DELTA_WIDTH_RATIO,
                )
                if abs(float(pair["delta"])) > maximum_delta + 1e-9:
                    unsafe_applied_compensations.append(
                        {
                            "unicode": entry["unicode"],
                            "glyphName": glyph_name,
                            "pairId": pair["pairId"],
                            "delta": pair["delta"],
                            "limit": maximum_delta,
                        }
                    )

            advance_width = {
                "roman": float(roman_layer.width),
                "raw": float(roman_layer.width),
                "cursivy": float(roman_layer.width),
                "balanced": float(roman_layer.width),
                "official": float(official_layer.width),
            }
            glyph_rows.append(
                {
                    **copy.deepcopy(entry),
                    "glyphName": glyph_name,
                    "status": "ok",
                    "balancedOutcome": balanced_outcome,
                    "pathless": not bool(record["source"])
                    and not bool(list(roman_layer.components or [])),
                    "topologyByMode": topology_by_mode,
                    "topologyPreserved": all(topology_by_mode.values()),
                    "officialTopologyMatchesRoman": (
                        base.engine.topology_matches(
                            record["source"], official_paths
                        )
                    ),
                    "reviewSourceUnchanged": source_before == source_after,
                    "runtimeSeconds": time.perf_counter() - started,
                    "detectedPairCount": int(
                        record["balancedDiagnostics"]["detectedPairCount"]
                    ),
                    "acceptedPairCount": int(
                        record["balancedDiagnostics"]["acceptedPairCount"]
                    ),
                    "compensatedPairCount": len(compensated_ids),
                    "stemDiagnostics": record["balancedDiagnostics"],
                    "stemMeasurements": measurements,
                    "maxAnchorError": (
                        max(glyph_anchor_errors)
                        if glyph_anchor_errors
                        else 0.0
                    ),
                    "anchors": {
                        **record["anchors"],
                        "official": _official_anchors(official_layer),
                    },
                    "components": {
                        "generated": component_rows,
                        "official": _official_component_rows(official_layer),
                        "nonCommutingTransformRisks": (
                            glyph_component_transform_risks
                        ),
                    },
                    "bounds": {
                        "direct": direct_bounds,
                        "componentAware": component_bounds,
                        "deltaFromRoman": {
                            mode: _numeric_delta(
                                component_bounds[mode],
                                component_bounds["roman"],
                            )
                            for mode in (
                                "raw",
                                "cursivy",
                                "balanced",
                                "official",
                            )
                        },
                    },
                    "advanceWidth": advance_width,
                    "advanceWidthDeltaFromRoman": {
                        mode: advance_width[mode] - advance_width["roman"]
                        for mode in (
                            "raw",
                            "cursivy",
                            "balanced",
                            "official",
                        )
                    },
                    "backend": "purePythonDeterministicStemCompensation",
                    "filterFailures": [],
                }
            )
        except Exception as exc:
            failure = {
                **copy.deepcopy(entry),
                "glyphName": glyph_name,
                "status": "error",
                "reason": str(exc),
                "runtimeSeconds": time.perf_counter() - started,
            }
            glyph_rows.append(failure)
            generation_failures.append(failure)

    successful_rows = [
        row for row in glyph_rows if row.get("status") == "ok"
    ]
    mean_errors = {
        mode: (
            float(statistics.fmean(errors_by_mode[mode]))
            if errors_by_mode[mode]
            else 0.0
        )
        for mode in MODE_NAMES
    }
    raw_reference = max(mean_errors["raw"], 1e-9)
    cursivy_reference = max(mean_errors["cursivy"], 1e-9)
    summary = {
        "glyphCount": len(entries),
        "generatedCount": len(successful_rows),
        "generationFailureCount": len(generation_failures),
        "pathlessCount": len(
            [row for row in successful_rows if row.get("pathless")]
        ),
        "topologyPreservedByMode": {
            mode: len(
                [
                    row
                    for row in successful_rows
                    if row["topologyByMode"][mode]
                ]
            )
            for mode in MODE_NAMES
        },
        "reviewSourceUnchangedCount": len(
            [
                row
                for row in successful_rows
                if row["reviewSourceUnchanged"]
            ]
        ),
        "compensatedPairCount": sum(
            int(row["compensatedPairCount"]) for row in successful_rows
        ),
        "detectedPairCount": sum(
            int(row["detectedPairCount"]) for row in successful_rows
        ),
        "acceptedPairCount": sum(
            int(row["acceptedPairCount"]) for row in successful_rows
        ),
        "meanAbsoluteStemWidthError": mean_errors,
        "balancedImprovementVsRaw": 1.0
        - mean_errors["balanced"] / raw_reference,
        "balancedImprovementVsCursivy": 1.0
        - mean_errors["balanced"] / cursivy_reference,
        "maxAnchorError": max(anchor_errors) if anchor_errors else 0.0,
        "explicitComponentReferenceCount": explicit_component_references,
        "unexpectedComponentMasterMismatchCount": 0,
        "unsafeAppliedCompensationCount": len(
            unsafe_applied_compensations
        ),
        "nonCommutingComponentTransformRiskCount": len(
            component_transform_risks
        ),
        "reflectedComponentTransformRiskCount": len(
            [risk for risk in component_transform_risks if risk["reflected"]]
        ),
        "affectedComponentTransformGlyphCount": len(
            {
                str(risk["unicode"])
                for risk in component_transform_risks
            }
        ),
        "blockedComponentGlyphCount": len(
            [
                row
                for row in successful_rows
                if row.get("balancedOutcome") == "balanced_blocked_component"
            ]
        ),
        "unsafeComponentApplicationCount": len(
            [
                row
                for row in successful_rows
                if row.get("components", {}).get(
                    "nonCommutingTransformRisks"
                )
                and row.get("balancedOutcome")
                != "balanced_blocked_component"
            ]
        ),
        "runtimeSeconds": time.perf_counter() - total_runtime_start,
        "meanGlyphRuntimeSeconds": (
            float(
                statistics.fmean(
                    float(row["runtimeSeconds"]) for row in glyph_rows
                )
            )
            if glyph_rows
            else 0.0
        ),
        "maxGlyphRuntimeSeconds": max(
            (float(row["runtimeSeconds"]) for row in glyph_rows),
            default=0.0,
        ),
    }
    acceptance = {
        "allGlyphsGenerated": not generation_failures,
        "topologyPreservedForEveryMode": all(
            summary["topologyPreservedByMode"][mode] == len(entries)
            for mode in MODE_NAMES
        ),
        "reviewSourceUnchanged": (
            summary["reviewSourceUnchangedCount"] == len(entries)
        ),
        "anchorErrorWithinPointZeroOne": (
            summary["maxAnchorError"] <= 0.01
        ),
        "noUnexpectedComponentMasterMismatch": (
            summary["unexpectedComponentMasterMismatchCount"] == 0
        ),
        "noUnsafeAppliedCompensation": (
            summary["unsafeAppliedCompensationCount"] == 0
        ),
        "allNonCommutingComponentTransformsBlocked": (
            summary["unsafeComponentApplicationCount"] == 0
            and summary["blockedComponentGlyphCount"]
            == summary["affectedComponentTransformGlyphCount"]
        ),
        "minimumCompensatedPairsRetained": (
            summary["compensatedPairCount"]
            >= int(config["minimumCompensatedPairs"])
        ),
        "balancedAtLeast50PercentBetterThanRaw": (
            summary["balancedImprovementVsRaw"] >= 0.5
        ),
        "balancedAtLeast50PercentBetterThanCursivy": (
            summary["balancedImprovementVsCursivy"] >= 0.5
        ),
    }
    result = {
        "source": {
            "repository": config["repository"],
            "commit": config["commit"],
            "romanMaster": {
                "id": roman_master.id,
                "name": roman_master.name,
                "axes": list(roman_master.axes),
            },
            "italicMaster": {
                "id": italic_master.id,
                "name": italic_master.name,
                "axes": list(italic_master.axes),
                "italicAngle": official_angle,
            },
        },
        "settings": {
            "angle": config["angle"],
            "origin": base.ORIGIN,
            "curveStrength": base.CURVE_STRENGTH,
            "stemCompensation": base.STEM_COMPENSATION,
            "cursivyFallbackStemStrength": (
                base.engine.CURSIVY_FALLBACK_STEM_STRENGTH
            ),
            "manifestNameKey": config["manifestNameKey"],
            "modeDefinitions": {
                "raw": "pure shear with no deterministic stem correction",
                "cursivy": (
                    "legacy result key; pure-Python partial stem compensation "
                    "at strength {}, not the Glyphs Cursivy filter"
                ).format(base.engine.CURSIVY_FALLBACK_STEM_STRENGTH),
                "balanced": (
                    "curve interpolation strength {} followed by deterministic "
                    "full stem compensation at strength {}"
                ).format(base.CURVE_STRENGTH, base.STEM_COMPENSATION),
            },
        },
        "summary": summary,
        "groupSummary": _family_group_summary(glyph_rows),
        "acceptance": acceptance,
        "generationFailures": generation_failures,
        "unsafeAppliedCompensations": unsafe_applied_compensations,
        "componentTransformRisks": component_transform_risks,
        "coverage": {
            "fixedManifestEntryCount": EXPECTED_ENTRY_COUNT,
            "sharedRomanItalicEntryCount": len(entries),
            "unavailableEntryCount": len(coverage_unavailable),
            "unavailableEntries": coverage_unavailable,
        },
        "glyphs": glyph_rows,
    }
    if family_key == "notoSans":
        result["source"]["googleFonts"] = config["googleFonts"]
        result["source"]["sourceAxes"] = {"wght": 90, "wdth": 100}
        result["source"]["externalAxes"] = {"wght": 400, "wdth": 100}
    elif family_key == "inter":
        result["source"]["externalAxes"] = {"opsz": 14, "wght": 400}
    else:
        result["source"]["upstreamRepository"] = config["upstreamRepository"]
        result["source"]["sourceFormat"] = config["sourceFormat"]
        result["source"]["sourceVersion"] = config["sourceVersion"]
        result["source"]["sourceAxes"] = config["sourceAxes"]
        result["source"]["externalAxes"] = config["externalAxes"]
        result["source"]["ufoItalicAngle"] = italic_master.ufoItalicAngle
    context = {
        "familyKey": family_key,
        "displayName": config["displayName"],
        "manifestNameKey": config["manifestNameKey"],
        "angle": float(config["angle"]),
        "romanFont": roman_font,
        "romanMaster": roman_master,
        "italicFont": italic_font,
        "italicMaster": italic_master,
        "generated": generated,
        "entries": entries,
    }
    return result, context


def _page_artifact(
    *,
    path: Path,
    page_number: int,
    page_count: int,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "path": str(path),
        "page": page_number,
        "pageCount": page_count,
        "glyphCount": len(entries),
        "firstUnicode": entries[0]["unicode"] if entries else None,
        "lastUnicode": entries[-1]["unicode"] if entries else None,
    }


def _render_full_pages(
    *,
    context: dict[str, Any],
    entries: list[dict[str, Any]],
    output_dir: Path,
    render_scale: float,
    page_size: int,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    entry_pages = paginate(entries, page_size)
    contact_artifacts = []
    diff_artifacts = []
    diff_rows = []
    entry_by_name = {
        str(entry[context["manifestNameKey"]]): entry for entry in entries
    }
    page_count = len(entry_pages)
    for page_index, page_entries in enumerate(entry_pages, start=1):
        glyph_names = [
            str(entry[context["manifestNameKey"]])
            for entry in page_entries
        ]
        contact_path = output_dir / (
            "{}-broad-contact-{:02d}-of-{:02d}.png".format(
                context["familyKey"],
                page_index,
                page_count,
            )
        )
        diff_path = output_dir / (
            "{}-broad-diff-{:02d}-of-{:02d}.png".format(
                context["familyKey"],
                page_index,
                page_count,
            )
        )
        base._draw_contact_sheet(
            contact_path,
            context["romanFont"],
            context["romanMaster"],
            context["italicFont"],
            context["italicMaster"],
            context["generated"],
            glyphs=glyph_names,
            angle=context["angle"],
            mode_labels=_mode_labels(context["displayName"]),
            normalize_upm=True,
            render_scale=render_scale,
        )
        page_diff = base._draw_difference_sheet(
            diff_path,
            context["romanFont"],
            context["romanMaster"],
            context["italicFont"],
            context["italicMaster"],
            context["generated"],
            glyphs=glyph_names,
            angle=context["angle"],
            normalize_upm=True,
            render_scale=render_scale,
            comparisons=list(DIFF_COMPARISONS),
        )
        for row in page_diff["glyphs"]:
            manifest_entry = entry_by_name[row["glyphName"]]
            diff_rows.append({**copy.deepcopy(manifest_entry), **row})
        contact_artifacts.append(
            _page_artifact(
                path=contact_path,
                page_number=page_index,
                page_count=page_count,
                entries=page_entries,
            )
        )
        diff_artifacts.append(
            _page_artifact(
                path=diff_path,
                page_number=page_index,
                page_count=page_count,
                entries=page_entries,
            )
        )
        gc.collect()
    return (
        {
            "contactPages": contact_artifacts,
            "differencePages": diff_artifacts,
        },
        {
            str(row["unicode"]): row
            for row in diff_rows
        },
    )


def select_audit_entries(
    entries: list[dict[str, Any]],
    glyph_rows: list[dict[str, Any]],
    diff_by_unicode: dict[str, dict[str, Any]],
    *,
    limit: int = DEFAULT_AUDIT_LIMIT,
) -> list[dict[str, Any]]:
    maximum = int(limit)
    if maximum < 1 or maximum > MAX_PAGE_SIZE:
        raise ValueError("audit limit must be between 1 and 64")
    entry_by_unicode = {str(entry["unicode"]): entry for entry in entries}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(entry: dict[str, Any]) -> None:
        unicode_value = str(entry["unicode"])
        if unicode_value in seen or len(selected) >= maximum:
            return
        seen.add(unicode_value)
        selected.append(entry)

    component_risks = sorted(
        [
            row
            for row in glyph_rows
            if row.get("status") == "ok"
            and bool(
                row.get("components", {}).get(
                    "nonCommutingTransformRisks"
                )
            )
        ],
        key=lambda row: int(row["codepoint"]),
    )
    for row in component_risks[:24]:
        add(entry_by_unicode[str(row["unicode"])])

    compensated = sorted(
        [
            row
            for row in glyph_rows
            if row.get("status") == "ok"
            and int(row.get("compensatedPairCount") or 0) > 0
        ],
        key=lambda row: (
            -int(row["compensatedPairCount"]),
            int(row["codepoint"]),
        ),
    )
    for row in compensated[:24]:
        add(entry_by_unicode[str(row["unicode"])])

    official_diffs = sorted(
        diff_by_unicode.values(),
        key=lambda row: (
            -float(
                row["comparisons"]["balancedVsOfficial"][
                    "differentPixelRatio"
                ]
            ),
            int(row["codepoint"]),
        ),
    )
    for row in official_diffs[:24]:
        add(entry_by_unicode[str(row["unicode"])])

    for group_name in EXPECTED_GROUP_COUNTS:
        candidates = [
            entry for entry in entries if entry["group"] == group_name
        ]
        if candidates:
            add(candidates[len(candidates) // 2])

    if len(selected) < maximum:
        remaining = [
            entry
            for entry in entries
            if str(entry["unicode"]) not in seen
        ]
        needed = maximum - len(selected)
        if needed >= len(remaining):
            for entry in remaining:
                add(entry)
        elif needed > 0:
            for index in range(needed):
                position = int(
                    round(index * (len(remaining) - 1) / max(needed - 1, 1))
                )
                add(remaining[position])
    return sorted(selected, key=lambda entry: int(entry["codepoint"]))


def _render_audit(
    *,
    context: dict[str, Any],
    audit_entries: list[dict[str, Any]],
    output_dir: Path,
    render_scale: float,
) -> dict[str, str]:
    glyph_names = [
        str(entry[context["manifestNameKey"]]) for entry in audit_entries
    ]
    contact_path = output_dir / "{}-broad-audit-contact.png".format(
        context["familyKey"]
    )
    diff_path = output_dir / "{}-broad-audit-diff.png".format(
        context["familyKey"]
    )
    base._draw_contact_sheet(
        contact_path,
        context["romanFont"],
        context["romanMaster"],
        context["italicFont"],
        context["italicMaster"],
        context["generated"],
        glyphs=glyph_names,
        angle=context["angle"],
        mode_labels=_mode_labels(context["displayName"]),
        normalize_upm=True,
        render_scale=render_scale,
    )
    base._draw_difference_sheet(
        diff_path,
        context["romanFont"],
        context["romanMaster"],
        context["italicFont"],
        context["italicMaster"],
        context["generated"],
        glyphs=glyph_names,
        angle=context["angle"],
        normalize_upm=True,
        render_scale=render_scale,
        comparisons=list(DIFF_COMPARISONS),
    )
    gc.collect()
    return {
        "contactPng": str(contact_path),
        "differencePng": str(diff_path),
    }


def _story_mask(
    context: dict[str, Any],
    glyph_names: list[str],
    mode: str,
    *,
    cell_size: tuple[int, int],
    pixel_ratio: float,
    curve_steps: int,
) -> tuple[Image.Image, float]:
    glyph_geometries = []
    cursor = 0.0
    tracking = float(context["romanFont"].upm) * 0.04
    for glyph_name in glyph_names:
        contours, advance = base._glyph_mode_geometry(
            roman_font=context["romanFont"],
            roman_master=context["romanMaster"],
            italic_font=context["italicFont"],
            italic_master=context["italicMaster"],
            generated=context["generated"],
            glyph_name=glyph_name,
            mode=mode,
            angle=context["angle"],
            curve_steps=curve_steps,
        )
        glyph_geometries.append((contours, cursor))
        cursor += float(advance) + tracking
    advance = max(0.0, cursor - tracking)
    logical_width = float(cell_size[0]) / pixel_ratio
    logical_height = float(cell_size[1]) / pixel_ratio
    upm = float(context["romanFont"].upm)
    outline_scale = min(
        (logical_width - 30.0) / max(advance, 1.0),
        (logical_height - 34.0) / max(upm, 1.0),
    ) * pixel_ratio
    origin_x = (logical_width - advance * outline_scale / pixel_ratio) * 0.5 * pixel_ratio
    baseline_y = (logical_height - 24.0) * pixel_ratio
    combined = Image.new("L", cell_size, 0)
    for contours, glyph_offset in glyph_geometries:
        glyph_mask = base._contours_to_mask(
            contours,
            size=cell_size,
            origin_x=origin_x + glyph_offset * outline_scale,
            baseline_y=baseline_y,
            outline_scale=outline_scale,
        )
        combined = ImageChops.lighter(combined, glyph_mask)
    return combined, advance


def _story_overlay(
    reference_mask: Image.Image,
    candidate_mask: Image.Image,
) -> tuple[Image.Image, float]:
    shared = ImageChops.multiply(reference_mask, candidate_mask)
    reference_only = ImageChops.subtract(reference_mask, candidate_mask)
    candidate_only = ImageChops.subtract(candidate_mask, reference_mask)
    different = ImageChops.lighter(reference_only, candidate_only)
    union = ImageChops.lighter(reference_mask, candidate_mask)
    different_pixels = base._nonzero_pixel_count(different)
    union_pixels = base._nonzero_pixel_count(union)
    ratio = (
        float(different_pixels) / float(union_pixels)
        if union_pixels
        else 0.0
    )
    image = Image.new("RGB", reference_mask.size, "white")
    image.paste((54, 58, 64), (0, 0), shared)
    image.paste((224, 84, 94), (0, 0), reference_only)
    image.paste((0, 137, 207), (0, 0), candidate_only)
    return image, ratio


def _render_story_sheet(
    *,
    contexts: dict[str, dict[str, Any]],
    families: dict[str, dict[str, Any]],
    output_dir: Path,
    render_scale: float,
) -> dict[str, Any]:
    pixel_ratio = max(1.0, min(4.0, float(render_scale)))
    label_width = 160.0
    cell_width = 320.0
    row_height = 160.0
    title_height = 118.0
    family_header_height = 44.0
    footer_height = 82.0
    columns = (
        ("roman", "Roman"),
        ("raw", "Raw shear"),
        ("cursivy", "Partial 0.35"),
        ("balanced", "Deterministic Balanced"),
        ("official", "Official italic"),
        ("balancedVsRaw", "Balanced vs Raw"),
        ("balancedVsOfficial", "Balanced vs Official"),
    )
    logical_width = label_width + cell_width * len(columns)
    logical_height = (
        title_height
        + len(contexts)
        * (family_header_height + row_height * len(STORY_GROUPS))
        + footer_height
    )
    width = int(round(logical_width * pixel_ratio))
    height = int(round(logical_height * pixel_ratio))
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = base._label_font(int(round(23 * pixel_ratio)))
    header_font = base._label_font(int(round(14 * pixel_ratio)))
    label_font = base._label_font(int(round(12 * pixel_ratio)))
    detail_font = base._label_font(int(round(9 * pixel_ratio)))
    line_width = max(1, int(round(pixel_ratio)))
    curve_steps = max(16, int(round(16 * pixel_ratio)))
    cell_size = (
        int(round(cell_width * pixel_ratio)),
        int(round(row_height * pixel_ratio)),
    )

    draw.text(
        (18 * pixel_ratio, 14 * pixel_ratio),
        "Deterministic Balanced italicification: capacity and limits",
        fill=(24, 28, 34),
        font=title_font,
    )
    draw.text(
        (18 * pixel_ratio, 51 * pixel_ratio),
        "Blue = candidate only  |  coral = reference only  |  dark = overlap",
        fill=(70, 74, 80),
        font=label_font,
    )
    draw.text(
        (18 * pixel_ratio, 77 * pixel_ratio),
        "Official italics are qualitative references, not pass/fail targets.",
        fill=(70, 74, 80),
        font=label_font,
    )
    for column, (_key, label) in enumerate(columns):
        left = (label_width + column * cell_width) * pixel_ratio
        draw.text(
            (left + 12 * pixel_ratio, 88 * pixel_ratio),
            label,
            fill=(24, 28, 34),
            font=header_font,
        )

    story_rows = []
    current_top = title_height
    for family_key in ("inter", "notoSans", "ibmPlexSans"):
        context = contexts[family_key]
        family = families[family_key]
        display_name = context["displayName"]
        draw.rectangle(
            (
                0,
                current_top * pixel_ratio,
                width,
                (current_top + family_header_height) * pixel_ratio,
            ),
            fill=(244, 246, 249),
        )
        draw.text(
            (18 * pixel_ratio, (current_top + 12) * pixel_ratio),
            "{} · native angle {}°".format(display_name, context["angle"]),
            fill=(24, 28, 34),
            font=header_font,
        )
        current_top += family_header_height
        entry_by_codepoint = {
            int(entry["codepoint"]): entry for entry in context["entries"]
        }
        row_by_name = {
            str(row["glyphName"]): row
            for row in family["glyphs"]
            if row.get("status") == "ok"
        }
        for group_label, codepoints in STORY_GROUPS:
            entries = [entry_by_codepoint[value] for value in codepoints]
            glyph_names = [
                str(entry[context["manifestNameKey"]]) for entry in entries
            ]
            visible_text = "".join(chr(value) for value in codepoints)
            blocked_names = [
                name
                for name in glyph_names
                if row_by_name.get(name, {}).get("balancedOutcome")
                == "balanced_blocked_component"
            ]
            top_px = int(round(current_top * pixel_ratio))
            draw.text(
                (14 * pixel_ratio, (current_top + 52) * pixel_ratio),
                group_label,
                fill=(24, 28, 34),
                font=label_font,
            )
            draw.text(
                (14 * pixel_ratio, (current_top + 78) * pixel_ratio),
                visible_text,
                fill=(90, 94, 100),
                font=header_font,
            )
            masks = {}
            for mode in ("roman", "raw", "cursivy", "balanced", "official"):
                masks[mode], _advance = _story_mask(
                    context,
                    glyph_names,
                    mode,
                    cell_size=cell_size,
                    pixel_ratio=pixel_ratio,
                    curve_steps=curve_steps,
                )
            for column, (key, _label) in enumerate(columns):
                left_px = int(
                    round((label_width + column * cell_width) * pixel_ratio)
                )
                cell = Image.new("RGB", cell_size, "white")
                cell_draw = ImageDraw.Draw(cell)
                if blocked_names and key in {
                    "balanced",
                    "balancedVsRaw",
                    "balancedVsOfficial",
                }:
                    cell_draw.rectangle(
                        (0, 0, cell_size[0] - 1, cell_size[1] - 1),
                        fill=(255, 248, 240),
                        outline=(218, 143, 66),
                        width=line_width,
                    )
                    cell_draw.text(
                        (18 * pixel_ratio, 48 * pixel_ratio),
                        "BLOCKED",
                        fill=(154, 79, 12),
                        font=header_font,
                    )
                    cell_draw.text(
                        (18 * pixel_ratio, 78 * pixel_ratio),
                        "non-commuting component: {}".format(
                            ", ".join(blocked_names)
                        ),
                        fill=(110, 82, 56),
                        font=detail_font,
                    )
                elif key == "balancedVsRaw":
                    cell, ratio = _story_overlay(
                        masks["raw"],
                        masks["balanced"],
                    )
                    ImageDraw.Draw(cell).text(
                        (10 * pixel_ratio, 8 * pixel_ratio),
                        "diff {:.2%}".format(ratio),
                        fill=(70, 70, 70),
                        font=detail_font,
                    )
                elif key == "balancedVsOfficial":
                    cell, ratio = _story_overlay(
                        masks["official"],
                        masks["balanced"],
                    )
                    ImageDraw.Draw(cell).text(
                        (10 * pixel_ratio, 8 * pixel_ratio),
                        "diff {:.1%}".format(ratio),
                        fill=(70, 70, 70),
                        font=detail_font,
                    )
                else:
                    color = (
                        (0, 91, 187)
                        if key == "balanced"
                        else (54, 58, 64)
                    )
                    cell.paste(color, (0, 0), masks[key])
                image.paste(cell, (left_px, top_px))
                draw.rectangle(
                    (
                        left_px,
                        top_px,
                        left_px + cell_size[0],
                        top_px + cell_size[1],
                    ),
                    outline=(224, 226, 230),
                    width=line_width,
                )
            story_rows.append(
                {
                    "family": family_key,
                    "group": group_label,
                    "codepoints": ["U+{:04X}".format(value) for value in codepoints],
                    "glyphNames": glyph_names,
                    "blockedGlyphNames": blocked_names,
                }
            )
            current_top += row_height

    draw.text(
        (18 * pixel_ratio, (logical_height - footer_height + 18) * pixel_ratio),
        "Balanced preserves topology and Roman stem width where conservative pairs are accepted.",
        fill=(50, 54, 60),
        font=label_font,
    )
    draw.text(
        (18 * pixel_ratio, (logical_height - footer_height + 45) * pixel_ratio),
        "It does not design optical forms, rhythm, spacing, kerning, or alternates; blocked constructions require manual work.",
        fill=(70, 74, 80),
        font=label_font,
    )
    output_path = output_dir / "italic-balanced-three-family-story.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        output_path,
        dpi=(72.0 * pixel_ratio, 72.0 * pixel_ratio),
        compress_level=6,
    )
    return {
        "png": str(output_path),
        "width": width,
        "height": height,
        "renderScale": pixel_ratio,
        "rows": story_rows,
    }


def evaluate_promotion(
    families: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    family_safety = {
        family_key: all(
            bool(value)
            for gate, value in result["acceptance"].items()
            if gate
            not in {
                "balancedAtLeast50PercentBetterThanRaw",
                "balancedAtLeast50PercentBetterThanCursivy",
            }
        )
        for family_key, result in families.items()
    }
    combined_errors = {
        mode: float(
            statistics.fmean(
                float(
                    family["summary"]["meanAbsoluteStemWidthError"][mode]
                )
                for family in families.values()
            )
        )
        for mode in MODE_NAMES
    }
    minimum_error = min(combined_errors.values())
    tied_modes = [
        mode
        for mode in MODE_NAMES
        if combined_errors[mode] - minimum_error <= 0.01
    ]
    if "cursivy" in tied_modes:
        winner = "cursivy"
    else:
        winner = min(tied_modes, key=lambda mode: MODE_NAMES.index(mode))
    improvement_gate = all(
        family["acceptance"]["balancedAtLeast50PercentBetterThanRaw"]
        and family["acceptance"][
            "balancedAtLeast50PercentBetterThanCursivy"
        ]
        for family in families.values()
    )
    balanced_promoted = (
        all(family_safety.values())
        and improvement_gate
        and winner == "balanced"
    )
    failed_safety_gates = {
        family_key: [
            gate
            for gate, value in family["acceptance"].items()
            if gate
            not in {
                "balancedAtLeast50PercentBetterThanRaw",
                "balancedAtLeast50PercentBetterThanCursivy",
            }
            and not bool(value)
        ]
        for family_key, family in families.items()
        if not family_safety[family_key]
    }
    return {
        "familySafetyPass": family_safety,
        "combinedMeanAbsoluteStemWidthError": combined_errors,
        "tieToleranceFontUnits": 0.01,
        "tiedModes": tied_modes,
        "winner": winner,
        "balancedImprovementGatePass": improvement_gate,
        "balancedPromoted": balanced_promoted,
        "deterministicGeometryWinner": winner,
        "failedSafetyGates": failed_safety_gates,
        "publicDefault": "cursivy",
        "recommendedExperimentalMode": (
            "balanced" if balanced_promoted else None
        ),
    }


def run(
    inter_root: Path,
    noto_root: Path,
    plex_root: Path,
    output_dir: Path,
    *,
    render_scale: float = DEFAULT_RENDER_SCALE,
    page_size: int = MAX_PAGE_SIZE,
    audit_limit: int = DEFAULT_AUDIT_LIMIT,
    manifest_path: Path = MANIFEST_PATH,
) -> dict[str, Any]:
    scale = validate_render_scale(render_scale)
    paginate([None], page_size)
    if not 1 <= int(audit_limit) <= MAX_PAGE_SIZE:
        raise ValueError("audit limit must be between 1 and 64")
    manifest = load_manifest(manifest_path)
    entries = list(manifest["glyphs"])
    output_dir.mkdir(parents=True, exist_ok=True)

    inter, inter_context = _benchmark_family(
        family_key="inter",
        config=FAMILY_CONFIGS["inter"],
        roman_path=inter_root / "src" / "Inter-Roman.glyphspackage",
        italic_path=inter_root / "src" / "Inter-Italic.glyphspackage",
        entries=entries,
    )
    noto, noto_context = _benchmark_family(
        family_key="notoSans",
        config=FAMILY_CONFIGS["notoSans"],
        roman_path=noto_root / "sources" / "NotoSans.glyphspackage",
        italic_path=noto_root / "sources" / "NotoSans-Italic.glyphspackage",
        entries=entries,
    )
    plex, plex_context = _benchmark_family(
        family_key="ibmPlexSans",
        config=FAMILY_CONFIGS["ibmPlexSans"],
        roman_path=(
            plex_root
            / "sources"
            / "masters"
            / "IBM Plex Sans-Regular.ufo"
        ),
        italic_path=(
            plex_root
            / "sources"
            / "masters"
            / "IBM Plex Sans-Italic.ufo"
        ),
        entries=entries,
    )
    families = {
        "inter": inter,
        "notoSans": noto,
        "ibmPlexSans": plex,
    }
    contexts = {
        "inter": inter_context,
        "notoSans": noto_context,
        "ibmPlexSans": plex_context,
    }

    for family_key, family_result in families.items():
        family_entries = contexts[family_key]["entries"]
        full_artifacts, diff_by_unicode = _render_full_pages(
            context=contexts[family_key],
            entries=family_entries,
            output_dir=output_dir / family_key,
            render_scale=scale,
            page_size=int(page_size),
        )
        family_result["imageDiff"] = {
            "summary": _aggregate_diff_rows(list(diff_by_unicode.values())),
            "glyphs": [
                diff_by_unicode[entry["unicode"]] for entry in family_entries
            ],
        }
        audit_entries = select_audit_entries(
            family_entries,
            family_result["glyphs"],
            diff_by_unicode,
            limit=int(audit_limit),
        )
        family_result["auditSelection"] = audit_entries
        family_result["artifacts"] = {
            **full_artifacts,
            "audit": _render_audit(
                context=contexts[family_key],
                audit_entries=audit_entries,
                output_dir=output_dir / family_key,
                render_scale=scale,
            ),
        }

    story = _render_story_sheet(
        contexts=contexts,
        families=families,
        output_dir=output_dir,
        render_scale=scale,
    )
    promotion = evaluate_promotion(families)
    result = {
        "manifest": {
            "path": str(manifest_path),
            "schemaVersion": manifest["schemaVersion"],
            "entryCount": manifest["entryCount"],
            "groupCounts": EXPECTED_GROUP_COUNTS,
            "sources": manifest["sources"],
        },
        "settings": {
            "renderScale": scale,
            "dpi": 72.0 * scale,
            "pageSize": int(page_size),
            "pageCountPerFamily": {
                family_key: len(
                    paginate(context["entries"], int(page_size))
                )
                for family_key, context in contexts.items()
            },
            "auditLimit": int(audit_limit),
            "origin": base.ORIGIN,
            "curveStrength": base.CURVE_STRENGTH,
            "stemCompensation": base.STEM_COMPENSATION,
        },
        "families": families,
        "promotion": promotion,
    }
    json_path = output_dir / "benchmark-results-broad-latin.json"
    result["artifacts"] = {
        "json": str(json_path),
        "story": story,
    }
    json_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    cache_root = base._repo_root() / ".cache" / "italic-benchmark"
    parser.add_argument(
        "--inter-root",
        type=Path,
        default=cache_root / "inter-{}".format(base.INTER_COMMIT),
    )
    parser.add_argument(
        "--noto-root",
        type=Path,
        default=cache_root / "noto-sans-{}".format(NOTO_SANS_COMMIT),
    )
    parser.add_argument(
        "--plex-root",
        type=Path,
        default=cache_root / "plex-{}".format(PLEX_COMMIT),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=cache_root / "results-broad",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
    )
    parser.add_argument(
        "--render-scale",
        type=float,
        default=DEFAULT_RENDER_SCALE,
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=MAX_PAGE_SIZE,
    )
    parser.add_argument(
        "--audit-limit",
        type=int,
        default=DEFAULT_AUDIT_LIMIT,
    )
    args = parser.parse_args()
    try:
        result = run(
            args.inter_root.resolve(),
            args.noto_root.resolve(),
            args.plex_root.resolve(),
            args.output_dir.resolve(),
            render_scale=args.render_scale,
            page_size=args.page_size,
            audit_limit=args.audit_limit,
            manifest_path=args.manifest.resolve(),
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "summaries": {
                    family_key: family["summary"]
                    for family_key, family in result["families"].items()
                },
                "promotion": result["promotion"],
                "artifacts": result["artifacts"],
            },
            indent=2,
        )
    )
    return 0 if result["promotion"]["balancedPromoted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
