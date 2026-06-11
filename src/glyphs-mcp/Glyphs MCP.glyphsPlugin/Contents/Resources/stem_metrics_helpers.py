# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Shared stem-metric helpers for Glyphs MCP tools.

The functions in this module avoid importing GlyphsApp so they can be used by
normal unit tests with lightweight fake Glyphs objects.
"""

from mcp_tool_helpers import _coerce_numeric, _safe_attr

import compensated_tuning_engine


DEFAULT_REFERENCE_GLYPHS = ["H", "n", "I", "o", "E"]


def bounds_tuple_for_layer(layer):
    b = _safe_attr(layer, "bounds")
    if not b:
        return None
    origin = _safe_attr(b, "origin")
    size = _safe_attr(b, "size")
    ox = _coerce_numeric(_safe_attr(origin, "x") if origin else None)
    oy = _coerce_numeric(_safe_attr(origin, "y") if origin else None)
    sw = _coerce_numeric(_safe_attr(size, "width") if size else None)
    sh = _coerce_numeric(_safe_attr(size, "height") if size else None)
    if ox is None or oy is None or sw is None or sh is None:
        return None
    return (float(ox), float(ox + sw), float(oy), float(oy + sh))


def point_x(pt):
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


def point_y(pt):
    if pt is None:
        return None
    try:
        return float(pt.y)
    except Exception:
        pass
    try:
        return float(pt[1])
    except Exception:
        return None


def sample_positions(center, extent, samples):
    n = int(samples)
    if n <= 1:
        return [float(center)]
    start = float(center) - float(extent) / 2.0
    end = float(center) + float(extent) / 2.0
    step = (end - start) / float(n - 1)
    return [start + i * step for i in range(n)]


def font_stem_definitions(font):
    definitions = []
    try:
        stems = list(getattr(font, "stems", []) or [])
    except Exception:
        stems = []

    for index, stem in enumerate(stems):
        name = getattr(stem, "name", None)
        if name is None or str(name).strip() == "":
            name = "stem{}".format(index + 1)
        try:
            horizontal = bool(getattr(stem, "horizontal", False))
        except Exception:
            horizontal = False
        definitions.append(
            {
                "name": str(name),
                "id": getattr(stem, "id", None),
                "index": index,
                "horizontal": horizontal,
                "orientation": "horizontal" if horizontal else "vertical",
                "stem": stem,
            }
        )
    return definitions


def stem_definitions_for_orientation(font, orientation):
    wanted_horizontal = str(orientation or "").lower().startswith("h")
    return [d for d in font_stem_definitions(font) if bool(d.get("horizontal")) == wanted_horizontal]


def pick_font_vertical_stem_name(font):
    stems = stem_definitions_for_orientation(font, "vertical")
    if not stems:
        return None
    return stems[0].get("name")


def _stem_value_from_collection(stems, stem_name=None, stem_id=None, stem_index=None):
    if stems is None:
        return None

    keys = []
    if stem_name is not None:
        keys.append(stem_name)
    if stem_id is not None:
        keys.append(stem_id)
    if stem_index is not None:
        keys.append(stem_index)

    for key in keys:
        try:
            value = stems[key]
            numeric = _coerce_numeric(value)
            if numeric is not None:
                return numeric
        except Exception:
            pass

    try:
        if isinstance(stems, dict):
            for key in keys:
                if key in stems:
                    numeric = _coerce_numeric(stems.get(key))
                    if numeric is not None:
                        return numeric
    except Exception:
        pass

    return None


def master_stem_value(master, stem_definition):
    stems = getattr(master, "stems", None)
    if stems is None:
        return None
    return _stem_value_from_collection(
        stems,
        stem_name=stem_definition.get("name"),
        stem_id=stem_definition.get("id"),
        stem_index=stem_definition.get("index"),
    )


def master_stem_value_by_name(master, stem_name):
    stems = getattr(master, "stems", None)
    return _stem_value_from_collection(stems, stem_name=stem_name)


def master_stem_report(font, master):
    entries = []
    for definition in font_stem_definitions(font):
        value = master_stem_value(master, definition)
        ok = value is not None and float(value) > 0.0
        entries.append(
            {
                "name": definition.get("name"),
                "index": definition.get("index"),
                "orientation": definition.get("orientation"),
                "horizontal": bool(definition.get("horizontal")),
                "value": value,
                "ok": bool(ok),
            }
        )
    return entries


def _center_height_for_name(master, font, name):
    upm = _coerce_numeric(getattr(font, "upm", None)) or 1000.0
    cap = _coerce_numeric(getattr(master, "capHeight", None))
    xh = _coerce_numeric(getattr(master, "xHeight", None))
    if len(name) == 1 and name.isalpha() and name.upper() == name and cap and cap > 0:
        return float(cap)
    if xh and xh > 0:
        return float(xh)
    if cap and cap > 0:
        return float(cap)
    return float(upm) * 0.5


def estimate_master_stem(
    *,
    font,
    master,
    orientation,
    reference_glyphs=None,
    samples=9,
    band=0.2,
    min_width=5.0,
    max_width=None,
    include_components=True,
):
    orientation = "horizontal" if str(orientation or "").lower().startswith("h") else "vertical"
    upm = _coerce_numeric(getattr(font, "upm", None)) or 1000.0
    glyph_names = list(reference_glyphs or DEFAULT_REFERENCE_GLYPHS)
    if not glyph_names:
        glyph_names = list(DEFAULT_REFERENCE_GLYPHS)

    values = []
    used_glyphs = []
    scanline_count = 0

    for glyph_name in glyph_names:
        try:
            glyph = font.glyphs[glyph_name]
        except Exception:
            glyph = None
        if not glyph:
            continue

        try:
            layer = glyph.layers[getattr(master, "id", None)]
        except Exception:
            layer = None
        if not layer:
            continue

        bounds = bounds_tuple_for_layer(layer)
        if not bounds:
            continue

        min_x, max_x, min_y, max_y = bounds
        margin = max(50.0, float(upm) * 0.1)
        scanlines = []

        if orientation == "vertical":
            height = _center_height_for_name(master, font, str(glyph_name))
            extent = max(1.0, float(height) * float(band))
            positions = sample_positions(center=float(height) * 0.5, extent=extent, samples=samples)
            start = float(min_x) - margin
            end = float(max_x) + margin
            for y in positions:
                try:
                    pts = layer.intersectionsBetweenPoints((start, y), (end, y), components=include_components)
                except Exception:
                    continue
                xs = [point_x(pt) for pt in list(pts or [])[1:-1]]
                xs = [x for x in xs if x is not None]
                if xs:
                    scanlines.append(xs)
        else:
            width = max(1.0, float(max_x) - float(min_x))
            extent = max(1.0, width * float(band))
            positions = sample_positions(center=(float(min_x) + float(max_x)) * 0.5, extent=extent, samples=samples)
            start = float(min_y) - margin
            end = float(max_y) + margin
            for x in positions:
                try:
                    pts = layer.intersectionsBetweenPoints((x, start), (x, end), components=include_components)
                except Exception:
                    continue
                ys = [point_y(pt) for pt in list(pts or [])[1:-1]]
                ys = [y for y in ys if y is not None]
                if ys:
                    scanlines.append(ys)

        scanline_count += len(scanlines)
        stem = compensated_tuning_engine.stem_thickness_from_scanlines(
            scanlines_xs=scanlines,
            min_width=min_width,
            max_width=max_width,
        )
        if stem is None or stem <= 0:
            continue
        values.append(float(stem))
        used_glyphs.append(str(glyph_name))

    value = compensated_tuning_engine._median(values)  # type: ignore[attr-defined]
    return {
        "ok": value is not None and float(value) > 0.0,
        "orientation": orientation,
        "value": value,
        "usedGlyphs": used_glyphs,
        "sampleCount": scanline_count,
        "dispersion": compensated_tuning_engine.iqr_ratio(values),
    }


def stem_ratio_payload(
    *,
    font,
    base_master,
    ref_master,
    reference_glyphs,
    samples,
    band,
    min_width,
    max_width,
    include_components,
    stem_source,
    mismatch_tolerance,
):
    stem_name = pick_font_vertical_stem_name(font)
    base_stem_font = master_stem_value_by_name(base_master, stem_name)
    ref_stem_font = master_stem_value_by_name(ref_master, stem_name)
    ratio_font = None
    if base_stem_font and ref_stem_font and base_stem_font > 0:
        ratio_font = float(ref_stem_font) / float(base_stem_font)

    base_estimate = estimate_master_stem(
        font=font,
        master=base_master,
        orientation="vertical",
        reference_glyphs=reference_glyphs,
        samples=samples,
        band=band,
        min_width=min_width,
        max_width=max_width,
        include_components=include_components,
    )
    ref_estimate = estimate_master_stem(
        font=font,
        master=ref_master,
        orientation="vertical",
        reference_glyphs=reference_glyphs,
        samples=samples,
        band=band,
        min_width=min_width,
        max_width=max_width,
        include_components=include_components,
    )

    stem_base_measured = base_estimate.get("value")
    stem_ref_measured = ref_estimate.get("value")
    ratio_measured = None
    if stem_base_measured and stem_ref_measured and stem_base_measured > 0:
        ratio_measured = float(stem_ref_measured) / float(stem_base_measured)

    used_glyphs = []
    for name in list(base_estimate.get("usedGlyphs") or []) + list(ref_estimate.get("usedGlyphs") or []):
        if name not in used_glyphs:
            used_glyphs.append(name)
    scanline_count = max(int(base_estimate.get("sampleCount") or 0), int(ref_estimate.get("sampleCount") or 0))
    dispersion = {
        "base": base_estimate.get("dispersion"),
        "ref": ref_estimate.get("dispersion"),
    }

    picked_source = stem_source or "auto"
    warnings = []

    if picked_source not in ("auto", "font_stems", "intersections"):
        picked_source = "auto"

    if picked_source == "font_stems":
        if ratio_font is None:
            return {
                "ok": False,
                "error": "No usable vertical font stem metrics found (font.stems/master.stems).",
                "stemBase": base_stem_font,
                "stemRef": ref_stem_font,
                "b": None,
                "usedGlyphs": [],
                "sampleCount": 0,
                "dispersion": None,
                "warnings": [],
                "stemSource": "font_stems",
            }
        return {
            "ok": True,
            "stemBase": base_stem_font,
            "stemRef": ref_stem_font,
            "b": ratio_font,
            "usedGlyphs": [],
            "sampleCount": 0,
            "dispersion": None,
            "warnings": [],
            "stemSource": "font_stems",
            "stemName": stem_name,
        }

    if picked_source == "intersections":
        if ratio_measured is None:
            return {
                "ok": False,
                "error": "Unable to measure stems from intersections. Provide stem_ratio_b or adjust reference_glyphs/settings.",
                "stemBase": stem_base_measured,
                "stemRef": stem_ref_measured,
                "b": None,
                "usedGlyphs": used_glyphs,
                "sampleCount": scanline_count,
                "dispersion": dispersion,
                "warnings": [],
                "stemSource": "intersections",
            }
        return {
            "ok": True,
            "stemBase": stem_base_measured,
            "stemRef": stem_ref_measured,
            "b": ratio_measured,
            "usedGlyphs": used_glyphs,
            "sampleCount": scanline_count,
            "dispersion": dispersion,
            "warnings": [],
            "stemSource": "intersections",
        }

    if ratio_font is not None and ratio_measured is not None:
        diff = abs(float(ratio_font) - float(ratio_measured)) / max(1e-6, float(ratio_measured))
        if diff <= float(mismatch_tolerance):
            return {
                "ok": True,
                "stemBase": base_stem_font,
                "stemRef": ref_stem_font,
                "b": ratio_font,
                "usedGlyphs": used_glyphs,
                "sampleCount": scanline_count,
                "dispersion": dispersion,
                "warnings": [],
                "stemSource": "font_stems",
                "stemName": stem_name,
                "measured": {
                    "stemBase": stem_base_measured,
                    "stemRef": stem_ref_measured,
                    "b": ratio_measured,
                },
            }
        warnings.append("font_stems_mismatch_using_intersections")

    if ratio_font is not None and ratio_measured is None:
        return {
            "ok": True,
            "stemBase": base_stem_font,
            "stemRef": ref_stem_font,
            "b": ratio_font,
            "usedGlyphs": [],
            "sampleCount": 0,
            "dispersion": None,
            "warnings": [],
            "stemSource": "font_stems",
            "stemName": stem_name,
        }

    if ratio_measured is None:
        return {
            "ok": False,
            "error": "Unable to compute stem ratio b (no usable font stems and intersection measurement failed).",
            "stemBase": stem_base_measured,
            "stemRef": stem_ref_measured,
            "b": None,
            "usedGlyphs": used_glyphs,
            "sampleCount": scanline_count,
            "dispersion": dispersion,
            "warnings": warnings,
            "stemSource": "intersections",
        }

    return {
        "ok": True,
        "stemBase": stem_base_measured,
        "stemRef": stem_ref_measured,
        "b": ratio_measured,
        "usedGlyphs": used_glyphs,
        "sampleCount": scanline_count,
        "dispersion": dispersion,
        "warnings": warnings,
        "stemSource": "intersections",
    }
