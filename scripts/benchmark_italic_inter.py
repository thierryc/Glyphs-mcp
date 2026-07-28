#!/usr/bin/env python3
"""Reproducible clean-room Inter benchmark for balanced italicification.

The script reads pinned Inter Glyphs packages with glyphsLib. It never modifies
or commits those sources. Generated evidence is written to an ignored cache by
default; the reviewed PNG may then be copied into contributor documentation.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

import glyphsLib
from PIL import Image, ImageChops, ImageDraw, ImageFont


INTER_COMMIT = "e3a3d4c57d5ecc01453a575621882a384c1995a3"
GLYPHS = [
    "H",
    "O",
    "A",
    "V",
    "W",
    "X",
    "n",
    "o",
    "p",
    "b",
    "d",
    "c",
    "e",
    "f",
    "s",
    "k",
    "v",
    "w",
    "x",
    "y",
    "zero",
    "eight",
    "parenleft",
    "ampersand",
    "adieresis",
    "iacute",
]
MODE_LABELS = [
    ("roman", "Inter Roman"),
    ("raw", "Current Raw"),
    ("cursivy", "Current Cursivy"),
    ("balanced", "New Balanced"),
    ("official", "Official Inter Italic"),
]
DIFF_COMPARISONS = [
    ("raw", "balanced", "Balanced vs Raw"),
    ("cursivy", "balanced", "Balanced vs Cursivy"),
    ("official", "balanced", "Balanced vs Official Italic"),
]
ANGLE = 9.4
ORIGIN = 3
CURVE_STRENGTH = 0.75
STEM_COMPENSATION = 1.0


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


RESOURCES = (
    _repo_root()
    / "src"
    / "glyphs-mcp"
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)
if str(RESOURCES) not in sys.path:
    sys.path.insert(0, str(RESOURCES))

import italic_correction_engine as engine  # noqa: E402


def _select_master(font: Any, expected_axes: dict[str, float]) -> Any:
    axis_tags = [
        str(getattr(axis, "axisTag", "") or getattr(axis, "tag", ""))
        for axis in font.axes
    ]
    missing_tags = sorted(set(expected_axes) - set(axis_tags))
    if missing_tags:
        raise RuntimeError(
            "Source is missing required axes: {}".format(", ".join(missing_tags))
        )
    matches = [
        master
        for master in font.masters
        if len(master.axes) >= len(axis_tags)
        and all(
            abs(float(master.axes[axis_tags.index(tag)]) - float(value)) < 1e-9
            for tag, value in expected_axes.items()
        )
    ]
    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one {} master; found {}".format(
                " ".join(
                    "{}={}".format(tag, value)
                    for tag, value in expected_axes.items()
                ),
                [(master.name, list(master.axes)) for master in matches],
            )
        )
    return matches[0]


def _serialize_layer_paths(layer: Any) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []
    for path in list(layer.paths or []):
        nodes = []
        for node in list(path.nodes or []):
            nodes.append(
                {
                    "x": float(node.position.x),
                    "y": float(node.position.y),
                    "type": str(node.type),
                    "smooth": bool(node.smooth),
                }
            )
        paths.append({"closed": bool(path.closed), "nodes": nodes})
    return paths


def _pivot_y(master: Any) -> float:
    if ORIGIN == 0:
        return float(master.capHeight)
    if ORIGIN == 1:
        return float(master.capHeight) * 0.5
    if ORIGIN == 2:
        return float(master.xHeight)
    if ORIGIN == 3:
        return float(master.xHeight) * 0.5
    return 0.0


def _anchors(
    layer: Any,
    mode: str,
    pivot_y: float,
    angle: float,
) -> list[dict[str, float | str]]:
    tangent = math.tan(math.radians(angle))
    result = []
    for anchor in list(layer.anchors or []):
        x_value = float(anchor.position.x)
        y_value = float(anchor.position.y)
        if mode == "balanced":
            x_value += tangent * (y_value - pivot_y)
        result.append({"name": str(anchor.name), "x": x_value, "y": y_value})
    return result


def _bounds(paths: list[dict[str, Any]]) -> dict[str, float] | None:
    points = [
        (float(node["x"]), float(node["y"]))
        for path in paths
        for node in list(path.get("nodes") or [])
    ]
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "minX": min(xs),
        "maxX": max(xs),
        "minY": min(ys),
        "maxY": max(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }


def _generate_glyph(
    layer: Any,
    master: Any,
    upm: float,
    stem_values: list[float],
    angle: float = ANGLE,
) -> dict[str, Any]:
    source = _serialize_layer_paths(layer)
    pivot_y = _pivot_y(master)
    raw = engine.shear_paths(source, angle=angle, pivot_y=pivot_y)
    cursivy_result = engine.compensate_stems(
        source,
        raw,
        strength=engine.CURSIVY_FALLBACK_STEM_STRENGTH,
        upm=upm,
        stem_values=stem_values,
    )
    cursivy = cursivy_result["paths"]
    blended = engine.interpolate_paths(raw, cursivy, CURVE_STRENGTH)
    balanced_result = engine.compensate_stems(
        source,
        blended,
        strength=STEM_COMPENSATION,
        upm=upm,
        stem_values=stem_values,
    )
    balanced = balanced_result["paths"]
    return {
        "source": source,
        "raw": raw,
        "cursivy": cursivy,
        "balanced": balanced,
        "balancedDiagnostics": balanced_result["diagnostics"],
        "anchors": {
            mode: _anchors(layer, mode, pivot_y, angle)
            for mode in ("roman", "raw", "cursivy", "balanced")
        },
        "width": float(layer.width),
        "topologyPreserved": all(
            engine.topology_matches(source, paths)
            for paths in (raw, cursivy, balanced)
        ),
        "bounds": {
            "roman": _bounds(source),
            "raw": _bounds(raw),
            "cursivy": _bounds(cursivy),
            "balanced": _bounds(balanced),
        },
    }


def _transform_tuple(
    component: Any,
    mode: str,
    angle: float,
) -> tuple[float, float, float, float, float, float]:
    values = tuple(float(value) for value in component.transform)
    if len(values) != 6:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    a, b, c, d, tx, ty = values
    if mode in ("raw", "cursivy", "balanced"):
        tx += math.tan(math.radians(angle)) * ty
    return (a, b, c, d, tx, ty)


def _compose(
    outer: tuple[float, float, float, float, float, float],
    inner: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    oa, ob, oc, od, otx, oty = outer
    ia, ib, ic, id_, itx, ity = inner
    return (
        oa * ia + oc * ib,
        ob * ia + od * ib,
        oa * ic + oc * id_,
        ob * ic + od * id_,
        oa * itx + oc * ity + otx,
        ob * itx + od * ity + oty,
    )


def _apply_transform(
    point: tuple[float, float],
    transform: tuple[float, float, float, float, float, float],
) -> tuple[float, float]:
    a, b, c, d, tx, ty = transform
    x_value, y_value = point
    return (a * x_value + c * y_value + tx, b * x_value + d * y_value + ty)


def _cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 12,
) -> list[tuple[float, float]]:
    result = []
    for index in range(1, steps + 1):
        t = index / steps
        mt = 1.0 - t
        result.append(
            (
                mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0],
                mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1],
            )
        )
    return result


def _sample_path(
    path: dict[str, Any],
    curve_steps: int = 12,
) -> list[tuple[float, float]]:
    nodes = list(path.get("nodes") or [])
    if not nodes:
        return []
    on_curve = [
        index
        for index, node in enumerate(nodes)
        if str(node.get("type", "")).lower() != "offcurve"
    ]
    if not on_curve:
        return []
    sampled = [(float(nodes[on_curve[0]]["x"]), float(nodes[on_curve[0]]["y"]))]
    count = len(nodes)
    for position, start_index in enumerate(on_curve):
        end_index = on_curve[(position + 1) % len(on_curve)]
        between = []
        index = (start_index + 1) % count
        while index != end_index:
            between.append(nodes[index])
            index = (index + 1) % count
        start = sampled[-1]
        end = (float(nodes[end_index]["x"]), float(nodes[end_index]["y"]))
        if str(nodes[end_index].get("type", "")).lower() == "curve" and len(between) == 2:
            control_1 = (float(between[0]["x"]), float(between[0]["y"]))
            control_2 = (float(between[1]["x"]), float(between[1]["y"]))
            sampled.extend(
                _cubic(
                    start,
                    control_1,
                    control_2,
                    end,
                    steps=max(4, int(curve_steps)),
                )
            )
        else:
            sampled.append(end)
        if not path.get("closed", True) and position == len(on_curve) - 2:
            break
    return sampled


def _component_name(component: Any) -> str:
    return str(getattr(component, "componentName", getattr(component, "name", "")))


def _glyph_contours(
    font: Any,
    master: Any,
    glyph_name: str,
    mode: str,
    generated: dict[str, Any] | None,
    angle: float,
    curve_steps: int = 12,
    transform: tuple[float, float, float, float, float, float] = (1, 0, 0, 1, 0, 0),
    stack: tuple[str, ...] = (),
) -> list[list[tuple[float, float]]]:
    if glyph_name in stack or len(stack) > 12:
        return []
    glyph = font.glyphs[glyph_name]
    if glyph is None:
        return []
    layer = glyph.layers[master.id]
    if layer is None:
        return []
    if generated is not None:
        if glyph_name not in generated:
            generated[glyph_name] = _generate_glyph(
                layer,
                master,
                float(font.upm),
                [float(value) for value in master.stems if float(value) > 0],
                angle=angle,
            )
        paths = generated[glyph_name]["source" if mode == "roman" else mode]
    else:
        paths = _serialize_layer_paths(layer)
    contours = []
    for path in paths:
        contour = [
            _apply_transform(point, transform)
            for point in _sample_path(path, curve_steps=curve_steps)
        ]
        if contour:
            contours.append(contour)
    for component in list(layer.components or []):
        component_transform = _transform_tuple(component, mode, angle)
        contours.extend(
            _glyph_contours(
                font,
                master,
                _component_name(component),
                mode,
                generated,
                angle,
                curve_steps=curve_steps,
                transform=_compose(transform, component_transform),
                stack=stack + (glyph_name,),
            )
        )
    return contours


def _label_font(pixel_size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", max(10, int(pixel_size)))
    except OSError:
        return ImageFont.load_default()


def _render_geometry(
    roman_font: Any,
    roman_master: Any,
    row_height: float,
    normalize_upm: bool,
) -> tuple[float, float]:
    if normalize_upm:
        outline_scale = 0.083 * 2048.0 / max(float(roman_font.upm), 1.0)
        descender = abs(float(getattr(roman_master, "descender", 0.0)))
        baseline_offset = row_height - max(
            12.0,
            descender * outline_scale + 8.0,
        )
        return outline_scale, baseline_offset
    return 0.083, 145.0


def _glyph_mode_geometry(
    *,
    roman_font: Any,
    roman_master: Any,
    italic_font: Any,
    italic_master: Any,
    generated: dict[str, Any],
    glyph_name: str,
    mode: str,
    angle: float,
    curve_steps: int,
) -> tuple[list[list[tuple[float, float]]], float]:
    if mode == "official":
        contours = _glyph_contours(
            italic_font,
            italic_master,
            glyph_name,
            mode,
            None,
            angle,
            curve_steps=curve_steps,
        )
        layer = italic_font.glyphs[glyph_name].layers[italic_master.id]
        return contours, float(layer.width)
    contours = _glyph_contours(
        roman_font,
        roman_master,
        glyph_name,
        mode,
        generated,
        angle,
        curve_steps=curve_steps,
    )
    layer = roman_font.glyphs[glyph_name].layers[roman_master.id]
    return contours, float(layer.width)


def _signed_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    return 0.5 * sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )


def _contours_to_mask(
    contours: list[list[tuple[float, float]]],
    *,
    size: tuple[int, int],
    origin_x: float,
    baseline_y: float,
    outline_scale: float,
) -> Image.Image:
    converted = [
        [
            (
                int(round(origin_x + x_value * outline_scale)),
                int(round(baseline_y - y_value * outline_scale)),
            )
            for x_value, y_value in contour
        ]
        for contour in contours
        if len(contour) >= 3
    ]
    converted = [contour for contour in converted if abs(_signed_area(contour)) > 0]
    mask = Image.new("L", size, 0)
    if not converted:
        return mask
    dominant = max(converted, key=lambda contour: abs(_signed_area(contour)))
    dominant_sign = 1.0 if _signed_area(dominant) >= 0 else -1.0
    draw = ImageDraw.Draw(mask)
    for contour in sorted(
        converted,
        key=lambda item: abs(_signed_area(item)),
        reverse=True,
    ):
        contour_sign = 1.0 if _signed_area(contour) >= 0 else -1.0
        draw.polygon(
            contour,
            fill=255 if contour_sign == dominant_sign else 0,
        )
    return mask


def _nonzero_pixel_count(mask: Image.Image) -> int:
    histogram = mask.histogram()
    return int(sum(histogram[1:]))


def _draw_contact_sheet(
    output_path: Path,
    roman_font: Any,
    roman_master: Any,
    italic_font: Any,
    italic_master: Any,
    generated: dict[str, Any],
    glyphs: list[str] = GLYPHS,
    angle: float = ANGLE,
    mode_labels: list[tuple[str, str]] = MODE_LABELS,
    normalize_upm: bool = False,
    render_scale: float = 1.0,
) -> None:
    pixel_ratio = max(1.0, min(4.0, float(render_scale)))
    cell_width = 410.0
    row_height = 185.0
    header_height = 60.0
    label_width = 100.0
    width = int(round((label_width + cell_width * len(mode_labels)) * pixel_ratio))
    height = int(round((header_height + row_height * len(glyphs)) * pixel_ratio))
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    header_font = _label_font(int(round(15 * pixel_ratio)))
    label_font = _label_font(int(round(13 * pixel_ratio)))
    line_width = max(1, int(round(pixel_ratio)))
    outline_width = max(2, int(round(2 * pixel_ratio)))
    for column, (_mode, label) in enumerate(mode_labels):
        x_value = (label_width + column * cell_width) * pixel_ratio
        draw.rectangle(
            (x_value, 0, x_value + cell_width * pixel_ratio, height),
            outline=(220, 220, 220),
            width=line_width,
        )
        draw.text(
            (x_value + 12 * pixel_ratio, 19 * pixel_ratio),
            label,
            fill=(20, 20, 20),
            font=header_font,
        )
    logical_outline_scale, baseline_offset = _render_geometry(
        roman_font,
        roman_master,
        row_height,
        normalize_upm,
    )
    outline_scale = logical_outline_scale * pixel_ratio
    curve_steps = max(12, int(round(12 * pixel_ratio)))
    for row, glyph_name in enumerate(glyphs):
        top = header_height + row * row_height
        draw.text(
            (12 * pixel_ratio, (top + 72) * pixel_ratio),
            glyph_name,
            fill=(20, 20, 20),
            font=label_font,
        )
        for column, (mode, _label) in enumerate(mode_labels):
            left = label_width + column * cell_width
            draw.line(
                (
                    left * pixel_ratio,
                    top * pixel_ratio,
                    (left + cell_width) * pixel_ratio,
                    top * pixel_ratio,
                ),
                fill=(230, 230, 230),
                width=line_width,
            )
            contours, advance = _glyph_mode_geometry(
                roman_font=roman_font,
                roman_master=roman_master,
                italic_font=italic_font,
                italic_master=italic_master,
                generated=generated,
                glyph_name=glyph_name,
                mode=mode,
                angle=angle,
                curve_steps=curve_steps,
            )
            origin_x = (
                left + (cell_width - advance * logical_outline_scale) * 0.5
            ) * pixel_ratio
            baseline_y = (top + baseline_offset) * pixel_ratio
            draw.line(
                (
                    origin_x,
                    baseline_y,
                    origin_x + advance * outline_scale,
                    baseline_y,
                ),
                fill=(205, 205, 205),
                width=line_width,
            )
            color = (20, 20, 20) if mode != "balanced" else (0, 91, 187)
            for contour in contours:
                screen = [
                    (
                        origin_x + x_value * outline_scale,
                        baseline_y - y_value * outline_scale,
                    )
                    for x_value, y_value in contour
                ]
                if len(screen) > 1:
                    draw.line(
                        screen,
                        fill=color,
                        width=outline_width,
                        joint="curve",
                    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        output_path,
        dpi=(72.0 * pixel_ratio, 72.0 * pixel_ratio),
        compress_level=6,
    )


def _draw_difference_sheet(
    output_path: Path,
    roman_font: Any,
    roman_master: Any,
    italic_font: Any,
    italic_master: Any,
    generated: dict[str, Any],
    *,
    glyphs: list[str],
    angle: float,
    normalize_upm: bool,
    render_scale: float,
    comparisons: list[tuple[str, str, str]] = DIFF_COMPARISONS,
) -> dict[str, Any]:
    pixel_ratio = max(1.0, min(4.0, float(render_scale)))
    cell_width = 520.0
    row_height = 185.0
    header_height = 82.0
    label_width = 110.0
    width = int(round((label_width + cell_width * len(comparisons)) * pixel_ratio))
    height = int(round((header_height + row_height * len(glyphs)) * pixel_ratio))
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    header_font = _label_font(int(round(15 * pixel_ratio)))
    label_font = _label_font(int(round(13 * pixel_ratio)))
    detail_font = _label_font(int(round(10 * pixel_ratio)))
    line_width = max(1, int(round(pixel_ratio)))
    curve_steps = max(12, int(round(12 * pixel_ratio)))
    logical_outline_scale, baseline_offset = _render_geometry(
        roman_font,
        roman_master,
        row_height,
        normalize_upm,
    )
    outline_scale = logical_outline_scale * pixel_ratio
    cell_size = (
        int(round(cell_width * pixel_ratio)),
        int(round(row_height * pixel_ratio)),
    )
    cell_origin_x = 110.0 * pixel_ratio
    cell_baseline_y = baseline_offset * pixel_ratio
    comparison_ratios: dict[str, list[float]] = {}
    glyph_results: list[dict[str, Any]] = []

    for column, (_reference, _candidate, label) in enumerate(comparisons):
        left = (label_width + column * cell_width) * pixel_ratio
        draw.rectangle(
            (left, 0, left + cell_width * pixel_ratio, height),
            outline=(220, 220, 220),
            width=line_width,
        )
        draw.text(
            (left + 12 * pixel_ratio, 14 * pixel_ratio),
            label,
            fill=(20, 20, 20),
            font=header_font,
        )
        draw.text(
            (left + 12 * pixel_ratio, 43 * pixel_ratio),
            "blue Balanced only  |  coral reference only  |  dark overlap",
            fill=(80, 80, 80),
            font=detail_font,
        )

    for row, glyph_name in enumerate(glyphs):
        top = header_height + row * row_height
        draw.text(
            (12 * pixel_ratio, (top + 72) * pixel_ratio),
            glyph_name,
            fill=(20, 20, 20),
            font=label_font,
        )
        glyph_result: dict[str, Any] = {
            "glyphName": glyph_name,
            "comparisons": {},
        }
        for column, (reference_mode, candidate_mode, _label) in enumerate(
            comparisons
        ):
            reference_contours, reference_advance = _glyph_mode_geometry(
                roman_font=roman_font,
                roman_master=roman_master,
                italic_font=italic_font,
                italic_master=italic_master,
                generated=generated,
                glyph_name=glyph_name,
                mode=reference_mode,
                angle=angle,
                curve_steps=curve_steps,
            )
            candidate_contours, candidate_advance = _glyph_mode_geometry(
                roman_font=roman_font,
                roman_master=roman_master,
                italic_font=italic_font,
                italic_master=italic_master,
                generated=generated,
                glyph_name=glyph_name,
                mode=candidate_mode,
                angle=angle,
                curve_steps=curve_steps,
            )
            reference_mask = _contours_to_mask(
                reference_contours,
                size=cell_size,
                origin_x=cell_origin_x,
                baseline_y=cell_baseline_y,
                outline_scale=outline_scale,
            )
            candidate_mask = _contours_to_mask(
                candidate_contours,
                size=cell_size,
                origin_x=cell_origin_x,
                baseline_y=cell_baseline_y,
                outline_scale=outline_scale,
            )
            shared = ImageChops.multiply(reference_mask, candidate_mask)
            reference_only = ImageChops.subtract(reference_mask, candidate_mask)
            candidate_only = ImageChops.subtract(candidate_mask, reference_mask)
            different = ImageChops.lighter(reference_only, candidate_only)
            union = ImageChops.lighter(reference_mask, candidate_mask)
            different_pixels = _nonzero_pixel_count(different)
            union_pixels = _nonzero_pixel_count(union)
            different_ratio = (
                float(different_pixels) / float(union_pixels)
                if union_pixels
                else 0.0
            )
            comparison_key = "{}Vs{}".format(
                candidate_mode,
                reference_mode[:1].upper() + reference_mode[1:],
            )
            comparison_ratios.setdefault(comparison_key, []).append(
                different_ratio
            )
            glyph_result["comparisons"][comparison_key] = {
                "candidate": candidate_mode,
                "reference": reference_mode,
                "differentPixelRatio": different_ratio,
                "differentPixelCount": different_pixels,
                "unionPixelCount": union_pixels,
                "candidateAdvanceWidth": candidate_advance,
                "referenceAdvanceWidth": reference_advance,
            }

            cell = Image.new("RGB", cell_size, "white")
            cell_draw = ImageDraw.Draw(cell)
            cell_draw.line(
                (
                    0,
                    cell_baseline_y,
                    cell_size[0],
                    cell_baseline_y,
                ),
                fill=(224, 224, 224),
                width=line_width,
            )
            cell_draw.line(
                (
                    cell_origin_x,
                    0,
                    cell_origin_x,
                    cell_size[1],
                ),
                fill=(235, 235, 235),
                width=line_width,
            )
            reference_advance_x = (
                cell_origin_x + reference_advance * outline_scale
            )
            candidate_advance_x = (
                cell_origin_x + candidate_advance * outline_scale
            )
            cell_draw.line(
                (
                    reference_advance_x,
                    0,
                    reference_advance_x,
                    cell_size[1],
                ),
                fill=(224, 84, 94),
                width=line_width,
            )
            cell_draw.line(
                (
                    candidate_advance_x,
                    0,
                    candidate_advance_x,
                    cell_size[1],
                ),
                fill=(0, 137, 207),
                width=line_width,
            )
            cell.paste((54, 58, 64), (0, 0), shared)
            cell.paste((224, 84, 94), (0, 0), reference_only)
            cell.paste((0, 137, 207), (0, 0), candidate_only)
            cell_draw.text(
                (12 * pixel_ratio, 10 * pixel_ratio),
                "diff {:.1%}".format(different_ratio),
                fill=(70, 70, 70),
                font=detail_font,
            )
            left = int(
                round((label_width + column * cell_width) * pixel_ratio)
            )
            image.paste(cell, (left, int(round(top * pixel_ratio))))
            draw.line(
                (
                    left,
                    top * pixel_ratio,
                    left + cell_size[0],
                    top * pixel_ratio,
                ),
                fill=(230, 230, 230),
                width=line_width,
            )
        glyph_results.append(glyph_result)

    summary = {}
    for comparison_key, ratios in comparison_ratios.items():
        summary[comparison_key] = {
            "glyphCount": len(ratios),
            "meanDifferentPixelRatio": (
                float(statistics.fmean(ratios)) if ratios else 0.0
            ),
            "medianDifferentPixelRatio": (
                float(statistics.median(ratios)) if ratios else 0.0
            ),
            "maxDifferentPixelRatio": max(ratios) if ratios else 0.0,
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        output_path,
        dpi=(72.0 * pixel_ratio, 72.0 * pixel_ratio),
        compress_level=6,
    )
    return {
        "legend": {
            "balancedOnly": "#0089CF",
            "referenceOnly": "#E0545E",
            "overlap": "#363A40",
        },
        "summary": summary,
        "glyphs": glyph_results,
    }


def benchmark_family(
    *,
    family_name: str,
    roman_path: Path,
    italic_path: Path,
    expected_axes: dict[str, float],
    glyphs: list[str],
    angle: float,
    png_path: Path,
    mode_labels: list[tuple[str, str]],
    normalize_upm: bool = False,
    render_scale: float = 1.0,
    diff_png_path: Path | None = None,
) -> dict[str, Any]:
    if not roman_path.is_dir() or not italic_path.is_dir():
        raise RuntimeError(
            "Pinned {} Roman and Italic glyphspackage sources were not found".format(
                family_name
            )
        )
    roman_font = glyphsLib.load(str(roman_path))
    italic_font = glyphsLib.load(str(italic_path))
    roman_master = _select_master(roman_font, expected_axes)
    italic_master = _select_master(italic_font, expected_axes)
    generated: dict[str, Any] = {}
    missing = [
        glyph_name
        for glyph_name in glyphs
        if roman_font.glyphs[glyph_name] is None or italic_font.glyphs[glyph_name] is None
    ]
    if missing:
        raise RuntimeError(
            "Benchmark glyphs missing from pinned {} sources: {}".format(
                family_name,
                missing,
            )
        )
    stem_values = [float(value) for value in roman_master.stems if float(value) > 0]
    raw_errors: list[float] = []
    cursivy_errors: list[float] = []
    balanced_errors: list[float] = []
    glyph_results = []
    anchor_errors = []
    compensated_pair_count = 0
    for glyph_name in glyphs:
        layer = roman_font.glyphs[glyph_name].layers[roman_master.id]
        record = _generate_glyph(
            layer,
            roman_master,
            float(roman_font.upm),
            stem_values,
            angle=angle,
        )
        generated[glyph_name] = record
        compensated_ids = {
            pair["pairId"]
            for pair in record["balancedDiagnostics"]["compensatedPairs"]
        }
        measurements = {
            mode: engine.measure_stem_widths(
                record["source"],
                record[mode],
                upm=float(roman_font.upm),
                stem_values=stem_values,
            )
            for mode in ("raw", "cursivy", "balanced")
        }
        by_mode = {
            mode: {
                item["pairId"]: item
                for item in measurements[mode]["measurements"]
            }
            for mode in measurements
        }
        for pair_id in sorted(compensated_ids):
            if all(pair_id in by_mode[mode] for mode in by_mode):
                raw_errors.append(by_mode["raw"][pair_id]["absoluteError"])
                cursivy_errors.append(by_mode["cursivy"][pair_id]["absoluteError"])
                balanced_errors.append(by_mode["balanced"][pair_id]["absoluteError"])
                compensated_pair_count += 1
        source_anchors = {item["name"]: item for item in record["anchors"]["roman"]}
        for anchor in record["anchors"]["balanced"]:
            source_anchor = source_anchors.get(anchor["name"])
            if source_anchor is None:
                continue
            expected_x = source_anchor["x"] + math.tan(math.radians(angle)) * (
                source_anchor["y"] - _pivot_y(roman_master)
            )
            anchor_errors.append(abs(float(anchor["x"]) - float(expected_x)))
        glyph_results.append(
            {
                "glyphName": glyph_name,
                "topologyPreserved": record["topologyPreserved"],
                "compensatedPairCount": len(compensated_ids),
                "bounds": record["bounds"],
                "advanceWidth": record["width"],
            }
        )

    def mean(values: list[float]) -> float:
        return float(statistics.fmean(values)) if values else 0.0

    summary = {
        "glyphCount": len(glyphs),
        "topologyPreservedCount": len([row for row in glyph_results if row["topologyPreserved"]]),
        "compensatedPairCount": compensated_pair_count,
        "meanAbsoluteStemWidthError": {
            "raw": mean(raw_errors),
            "cursivy": mean(cursivy_errors),
            "balanced": mean(balanced_errors),
        },
        "maxAnchorError": max(anchor_errors) if anchor_errors else 0.0,
    }
    raw_reference = max(summary["meanAbsoluteStemWidthError"]["raw"], 1e-9)
    cursivy_reference = max(summary["meanAbsoluteStemWidthError"]["cursivy"], 1e-9)
    summary["balancedImprovementVsRaw"] = 1.0 - summary["meanAbsoluteStemWidthError"]["balanced"] / raw_reference
    summary["balancedImprovementVsCursivy"] = (
        1.0 - summary["meanAbsoluteStemWidthError"]["balanced"] / cursivy_reference
    )
    acceptance = {
        "topologyPreserved": summary["topologyPreservedCount"] == len(glyphs),
        "atLeastSixCompensatedPairs": compensated_pair_count >= 6,
        "balancedAtLeast50PercentBetterThanRaw": summary["balancedImprovementVsRaw"] >= 0.5,
        "balancedAtLeast50PercentBetterThanCursivy": summary["balancedImprovementVsCursivy"] >= 0.5,
        "anchorErrorWithinPointZeroOne": summary["maxAnchorError"] <= 0.01,
    }
    result = {
        "source": {
            "romanMaster": {
                "id": roman_master.id,
                "name": roman_master.name,
                "axes": list(roman_master.axes),
            },
            "italicMaster": {
                "id": italic_master.id,
                "name": italic_master.name,
                "axes": list(italic_master.axes),
                "italicAngle": float(italic_master.italicAngle),
            },
        },
        "settings": {
            "angle": angle,
            "origin": ORIGIN,
            "curveStrength": CURVE_STRENGTH,
            "stemCompensation": STEM_COMPENSATION,
            "cursivyFallbackStemStrength": engine.CURSIVY_FALLBACK_STEM_STRENGTH,
            "glyphs": glyphs,
        },
        "summary": summary,
        "acceptance": acceptance,
        "glyphs": glyph_results,
    }
    _draw_contact_sheet(
        png_path,
        roman_font,
        roman_master,
        italic_font,
        italic_master,
        generated,
        glyphs=glyphs,
        angle=angle,
        mode_labels=mode_labels,
        normalize_upm=normalize_upm,
        render_scale=render_scale,
    )
    result["artifacts"] = {"png": str(png_path)}
    if diff_png_path is not None:
        result["imageDiff"] = _draw_difference_sheet(
            diff_png_path,
            roman_font,
            roman_master,
            italic_font,
            italic_master,
            generated,
            glyphs=glyphs,
            angle=angle,
            normalize_upm=normalize_upm,
            render_scale=render_scale,
        )
        result["artifacts"]["diffPng"] = str(diff_png_path)
    return result


def run(inter_root: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    family_result = benchmark_family(
        family_name="Inter",
        roman_path=inter_root / "src" / "Inter-Roman.glyphspackage",
        italic_path=inter_root / "src" / "Inter-Italic.glyphspackage",
        expected_axes={"opsz": 14, "wght": 400},
        glyphs=GLYPHS,
        angle=ANGLE,
        png_path=output_dir / "italic-balanced-inter-v4.1.png",
        mode_labels=MODE_LABELS,
    )
    result = {
        "inter": {
            "commit": INTER_COMMIT,
            **family_result["source"],
        },
        "settings": family_result["settings"],
        "legacyMcpBaseline": {
            "status": "failed",
            "reason": "component_detach_failed",
            "appliedCount": 0,
            "errorCount": len(GLYPHS),
            "note": "Observed before implementation on Glyphs 4; intended Raw/Cursivy geometry is reproduced here.",
        },
        "summary": family_result["summary"],
        "acceptance": family_result["acceptance"],
        "glyphs": family_result["glyphs"],
    }
    json_path = output_dir / "benchmark-results.json"
    json_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result["artifacts"] = {
        "json": str(json_path),
        "png": family_result["artifacts"]["png"],
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    default_inter = (
        _repo_root()
        / ".cache"
        / "italic-benchmark"
        / "inter-{}".format(INTER_COMMIT)
    )
    default_output = _repo_root() / ".cache" / "italic-benchmark" / "results"
    parser.add_argument("--inter-root", type=Path, default=default_inter)
    parser.add_argument("--output-dir", type=Path, default=default_output)
    args = parser.parse_args()
    result = run(args.inter_root.resolve(), args.output_dir.resolve())
    print(json.dumps({"summary": result["summary"], "acceptance": result["acceptance"], "artifacts": result["artifacts"]}, indent=2))
    return 0 if all(result["acceptance"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
