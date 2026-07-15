# encoding: utf-8

from __future__ import division, print_function, unicode_literals

from GlyphsApp import Glyphs, GSNode, GSPath  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import (
    _coerce_numeric,
    _font_resolution_error,
    _is_active_font,
    _replace_layer_paths_and_metrics,
    _resolve_font_by_index,
    _safe_json,
    _spacing_selected_glyph_names_for_font,
)

import compensated_tuning_engine
import stem_metrics_helpers


def _resolve_font_payload(font_index):
    font, fonts = _resolve_font_by_index(Glyphs, font_index)
    if not font:
        return None, _font_resolution_error(font_index, fonts, ok_key="ok")
    return font, None


def _stem_ratio_payload(
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
    return stem_metrics_helpers.stem_ratio_payload(
        font=font,
        base_master=base_master,
        ref_master=ref_master,
        reference_glyphs=reference_glyphs,
        samples=samples,
        band=band,
        min_width=min_width,
        max_width=max_width,
        include_components=include_components,
        stem_source=stem_source,
        mismatch_tolerance=mismatch_tolerance,
    )


def _measure_stem_ratio_impl(
    font_index: int = 0,
    base_master_id: str = None,
    ref_master_id: str = None,
    reference_glyphs: list = None,
    samples: int = 9,
    band: float = 0.2,
    min_width: float = 5.0,
    max_width: float = None,
    include_components: bool = True,
    stem_source: str = "auto",
    mismatch_tolerance: float = 0.2,
) -> str:
    """Measure the stem ratio `b` between two masters (ref/base).

    This helper estimates `b` (a vertical stem thickness ratio) used by the
    compensated tuning workflow.

    Safety:
      - Read-only (no mutation, no auto-save).

    Units:
      - Stem widths are measured in font units.
      - `band` is a fraction of a reference height used to choose scanline Y samples.

    Args:
      - base_master_id: The “base” master (denominator).
      - ref_master_id: The “reference” master (numerator).
      - stem_source:
          - "auto": prefer font stem metrics when they agree with measured intersections
          - "font_stems": use font/master stem metrics only (if present)
          - "intersections": measure from outline intersections only

    Returns:
      JSON payload. Notable keys:
        - ok (bool), error (str?)
        - b (float?)  # ratio ref/base
        - stemBase, stemRef (float?)
        - stemSource ("font_stems"|"intersections")
        - warnings (list[str])
    """
    try:
        font, error = _resolve_font_payload(font_index)
        if error:
            return _safe_json(error)
        if not base_master_id:
            return _safe_json({"ok": False, "error": "base_master_id is required"})
        if not ref_master_id:
            return _safe_json({"ok": False, "error": "ref_master_id is required"})

        base_master = next((m for m in (font.masters or []) if str(getattr(m, "id", "")) == str(base_master_id)), None)
        ref_master = next((m for m in (font.masters or []) if str(getattr(m, "id", "")) == str(ref_master_id)), None)
        if not base_master:
            return _safe_json({"ok": False, "error": "Base master not found", "base_master_id": base_master_id})
        if not ref_master:
            return _safe_json({"ok": False, "error": "Ref master not found", "ref_master_id": ref_master_id})

        payload = _stem_ratio_payload(
            font=font,
            base_master=base_master,
            ref_master=ref_master,
            reference_glyphs=reference_glyphs,
            samples=samples,
            band=band,
            min_width=min_width,
            max_width=max_width,
            include_components=bool(include_components),
            stem_source=stem_source,
            mismatch_tolerance=mismatch_tolerance,
        )
        return payload
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
async def measure_stem_ratio(
    font_index: int = 0,
    base_master_id: str = None,
    ref_master_id: str = None,
    reference_glyphs: list = None,
    samples: int = 9,
    band: float = 0.2,
    min_width: float = 5.0,
    max_width: float = None,
    include_components: bool = True,
    stem_source: str = "auto",
    mismatch_tolerance: float = 0.2,
) -> str:
    return _safe_json(
        _measure_stem_ratio_impl(
            font_index=font_index,
            base_master_id=base_master_id,
            ref_master_id=ref_master_id,
            reference_glyphs=reference_glyphs,
            samples=samples,
            band=band,
            min_width=min_width,
            max_width=max_width,
            include_components=include_components,
            stem_source=stem_source,
            mismatch_tolerance=mismatch_tolerance,
        )
    )


def _layer_has_components(layer) -> bool:
    try:
        comps = list(getattr(layer, "components", []) or [])
    except Exception:
        comps = []
    return bool(comps)


def _layers_compatible_for_tuning(layer_r, layer_b):
    paths_r = list(getattr(layer_r, "paths", []) or [])
    paths_b = list(getattr(layer_b, "paths", []) or [])
    if len(paths_r) != len(paths_b):
        return False, {"reason": "path_count_mismatch", "pathsBase": len(paths_r), "pathsRef": len(paths_b)}
    for p_i, (pr, pb) in enumerate(zip(paths_r, paths_b)):
        nodes_r = list(getattr(pr, "nodes", []) or [])
        nodes_b = list(getattr(pb, "nodes", []) or [])
        if len(nodes_r) != len(nodes_b):
            return False, {"reason": "node_count_mismatch", "pathIndex": p_i, "nodesBase": len(nodes_r), "nodesRef": len(nodes_b)}
        for n_i, (nr, nb) in enumerate(zip(nodes_r, nodes_b)):
            tr = getattr(nr, "type", None)
            tb = getattr(nb, "type", None)
            if tr != tb:
                return False, {"reason": "node_type_mismatch", "pathIndex": p_i, "nodeIndex": n_i, "typeBase": tr, "typeRef": tb}
    return True, None


def _review_compensated_tuning_impl(
    font_index: int = 0,
    glyph_name: str = None,
    base_master_id: str = None,
    ref_master_id: str = None,
    sx: float = 1.0,
    sy: float = 1.0,
    keep_stroke: float = 0.9,
    stroke_exponent_a: float = None,
    q_x: float = None,
    q_y: float = None,
    italic_angle: float = None,
    translate_x: float = 0.0,
    translate_y: float = 0.0,
    extrapolation: str = "clamp",
    round_units: bool = True,
    stem_ratio_b: float = None,
    stem_measure: dict = None,
) -> str:
    """Preview compensated tuning for one glyph (no mutation).

    This computes tuned outlines for `glyph_name` by combining corresponding
    nodes from `base_master_id` (R) and `ref_master_id` (B), using a
    compensated interpolation model.

    Safety:
      - Read-only (no mutation, no auto-save).
      - Refuses glyph layers that contain components (requires decomposed outlines).

    Units:
      - All geometric inputs/outputs are in font units.
      - `sx`/`sy` are unitless scale factors.
      - `q_x`/`q_y` are unitless compensation factors in the range [0..1] (may be clamped).

    Args:
      - extrapolation:
          - "clamp" (default): clamp q to [0..1] and emit warnings
          - "allow": allow q outside [0..1]
          - "error": fail if q is outside [0..1]
      - stem_ratio_b / stem_measure:
          - If `q_x`/`q_y` are not provided (and masters differ), `b` may be measured automatically.

    Returns:
      JSON in `set_glyph_paths` format (`paths`, `width`) plus a `gmcp` block with
      inputs, computed parameters, and warnings.
    """
    try:
        font, error = _resolve_font_payload(font_index)
        if error:
            return error
        if not glyph_name:
            return {"ok": False, "error": "glyph_name is required"}
        if not base_master_id:
            return {"ok": False, "error": "base_master_id is required"}
        if not ref_master_id:
            return {"ok": False, "error": "ref_master_id is required"}

        glyph = font.glyphs[glyph_name]
        if not glyph:
            return {"ok": False, "error": "Glyph not found", "glyph_name": glyph_name}

        base_master = next((m for m in (font.masters or []) if str(getattr(m, "id", "")) == str(base_master_id)), None)
        ref_master = next((m for m in (font.masters or []) if str(getattr(m, "id", "")) == str(ref_master_id)), None)
        if not base_master:
            return {"ok": False, "error": "Base master not found", "base_master_id": base_master_id}
        if not ref_master:
            return {"ok": False, "error": "Ref master not found", "ref_master_id": ref_master_id}

        same_master = str(base_master_id) == str(ref_master_id)

        layer_r = glyph.layers[str(base_master_id)]
        layer_b = glyph.layers[str(ref_master_id)]
        if not layer_r or not layer_b:
            return {"ok": False, "error": "Missing master layer(s) for glyph"}

        if _layer_has_components(layer_r) or _layer_has_components(layer_b):
            return {
                "ok": False,
                "error": "Glyph layers contain components; compensated tuning currently requires decomposed outlines.",
                "hint": "Decompose components before tuning, or tune base glyphs and rebuild components after.",
            }

        compat_ok, compat_info = _layers_compatible_for_tuning(layer_r, layer_b)
        if not compat_ok:
            return {"ok": False, "error": "Incompatible outlines between masters", "details": compat_info}

        sx_f = float(sx)
        sy_f = float(sy)
        if sx_f <= 0.0 or sy_f <= 0.0:
            return {"ok": False, "error": "sx and sy must be > 0"}

        warnings = []

        if stroke_exponent_a is None:
            a = compensated_tuning_engine.keep_stroke_to_exponent_a(float(keep_stroke))
        else:
            a = float(stroke_exponent_a)
        a = compensated_tuning_engine.clamp(a, 0.0, 1.0)

        b = None
        stem_info = None
        if stem_ratio_b is not None:
            b = float(stem_ratio_b)
        elif (q_x is None or q_y is None) and (not same_master):
            sm = stem_measure if isinstance(stem_measure, dict) else {}
            stem_info = _stem_ratio_payload(
                font=font,
                base_master=base_master,
                ref_master=ref_master,
                reference_glyphs=sm.get("reference_glyphs"),
                samples=sm.get("samples", 9),
                band=sm.get("band", 0.2),
                min_width=sm.get("min_width", 5.0),
                max_width=sm.get("max_width"),
                include_components=bool(sm.get("include_components", True)),
                stem_source=sm.get("stem_source", "auto"),
                mismatch_tolerance=sm.get("mismatch_tolerance", 0.2),
            )
            if not stem_info.get("ok"):
                return {"ok": False, "error": "Unable to measure stem ratio b", "stem": stem_info}
            b = float(stem_info.get("b"))

        if q_x is None:
            if same_master:
                qx = 1.0
                warnings.append("base_and_ref_same_using_geometric_qx")
            else:
                qx = compensated_tuning_engine.compute_q(scale=sx_f, b=float(b), a=a)
        else:
            qx = float(q_x)
        if q_y is None:
            if same_master:
                qy = 1.0
                warnings.append("base_and_ref_same_using_geometric_qy")
            else:
                qy = compensated_tuning_engine.compute_q(scale=sy_f, b=float(b), a=a)
        else:
            qy = float(q_y)

        mode = str(extrapolation or "clamp").strip().lower()
        if mode not in ("clamp", "allow", "error"):
            mode = "clamp"
        if mode == "clamp":
            qx0, qy0 = qx, qy
            qx = compensated_tuning_engine.clamp_q(qx)
            qy = compensated_tuning_engine.clamp_q(qy)
            if abs(qx0 - qx) > 1e-9:
                warnings.append("clamped_qx")
            if abs(qy0 - qy) > 1e-9:
                warnings.append("clamped_qy")
        elif mode == "error":
            if not (0.0 <= qx <= 1.0):
                return {"ok": False, "error": "qx out of range and extrapolation=error", "qx": qx}
            if not (0.0 <= qy <= 1.0):
                return {"ok": False, "error": "qy out of range and extrapolation=error", "qy": qy}

        if italic_angle is None:
            italic_angle = _coerce_numeric(getattr(base_master, "italicAngle", 0.0)) or 0.0
        shear = compensated_tuning_engine.italic_shear(float(italic_angle))

        paths_out = []
        paths_r = list(getattr(layer_r, "paths", []) or [])
        paths_b = list(getattr(layer_b, "paths", []) or [])
        for pr, pb in zip(paths_r, paths_b):
            nodes_r = list(getattr(pr, "nodes", []) or [])
            nodes_b = list(getattr(pb, "nodes", []) or [])
            nodes_out = []
            for nr, nb in zip(nodes_r, nodes_b):
                xr = _coerce_numeric(getattr(getattr(nr, "position", None), "x", None)) or 0.0
                yr = _coerce_numeric(getattr(getattr(nr, "position", None), "y", None)) or 0.0
                xb = _coerce_numeric(getattr(getattr(nb, "position", None), "x", None)) or 0.0
                yb = _coerce_numeric(getattr(getattr(nb, "position", None), "y", None)) or 0.0
                x, y = compensated_tuning_engine.transform_point(
                    xr=xr,
                    yr=yr,
                    xb=xb,
                    yb=yb,
                    sx=sx_f,
                    sy=sy_f,
                    qx=qx,
                    qy=qy,
                    shear=shear,
                    tx=float(translate_x),
                    ty=float(translate_y),
                )
                x_out = compensated_tuning_engine.units(x, round_units=bool(round_units))
                y_out = compensated_tuning_engine.units(y, round_units=bool(round_units))
                nodes_out.append(
                    {
                        "x": x_out,
                        "y": y_out,
                        "type": getattr(nr, "type", "line"),
                        "smooth": bool(getattr(nr, "smooth", False)),
                    }
                )

            paths_out.append({"nodes": nodes_out, "closed": bool(getattr(pr, "closed", True))})

        width_r = _coerce_numeric(getattr(layer_r, "width", None)) or 0.0
        width_b = _coerce_numeric(getattr(layer_b, "width", None)) or 0.0
        width_out = compensated_tuning_engine.interpolate_metric(mr=width_r, mb=width_b, s=sx_f, q=qx)
        width_out = compensated_tuning_engine.units(width_out, round_units=bool(round_units))

        out = {
            "paths": paths_out,
            "width": width_out,
            "gmcp": {
                "ok": True,
                "glyphName": glyph_name,
                "baseMasterId": str(base_master_id),
                "refMasterId": str(ref_master_id),
                "inputs": {
                    "sx": sx_f,
                    "sy": sy_f,
                    "keepStroke": keep_stroke,
                    "strokeExponentA": a,
                    "qX": q_x,
                    "qY": q_y,
                    "italicAngle": italic_angle,
                    "translateX": translate_x,
                    "translateY": translate_y,
                    "extrapolation": mode,
                    "roundUnits": bool(round_units),
                },
                "computed": {"b": b, "qX": qx, "qY": qy, "shear": shear, "width": width_out},
                "warnings": warnings,
                "stem": stem_info,
            },
        }
        return out
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
async def review_compensated_tuning(
    font_index: int = 0,
    glyph_name: str = None,
    base_master_id: str = None,
    ref_master_id: str = None,
    sx: float = 1.0,
    sy: float = 1.0,
    keep_stroke: float = 0.9,
    stroke_exponent_a: float = None,
    q_x: float = None,
    q_y: float = None,
    italic_angle: float = None,
    translate_x: float = 0.0,
    translate_y: float = 0.0,
    extrapolation: str = "clamp",
    round_units: bool = True,
    stem_ratio_b: float = None,
    stem_measure: dict = None,
) -> str:
    return _safe_json(
        _review_compensated_tuning_impl(
            font_index=font_index,
            glyph_name=glyph_name,
            base_master_id=base_master_id,
            ref_master_id=ref_master_id,
            sx=sx,
            sy=sy,
            keep_stroke=keep_stroke,
            stroke_exponent_a=stroke_exponent_a,
            q_x=q_x,
            q_y=q_y,
            italic_angle=italic_angle,
            translate_x=translate_x,
            translate_y=translate_y,
            extrapolation=extrapolation,
            round_units=round_units,
            stem_ratio_b=stem_ratio_b,
            stem_measure=stem_measure,
        )
    )


def _master_weight_coord(font, master):
    # Prefer wght axis if present; fall back to weightValue.
    axes = []
    try:
        axes = list(getattr(font, "axes", []) or [])
    except Exception:
        axes = []
    try:
        if axes:
            tag_list = []
            for a in axes:
                tag = getattr(a, "axisTag", None) or getattr(a, "name", "")
                tag_list.append(str(tag).lower())
            values = list(getattr(master, "axes", []) or [])
            for i, t in enumerate(tag_list):
                if t in {"wght", "weight"} and i < len(values):
                    v = _coerce_numeric(values[i])
                    if v is not None:
                        return float(v)
    except Exception:
        pass
    v = _coerce_numeric(getattr(master, "weightValue", None))
    return float(v) if v is not None else None


def _next_heavier_master(font, base_master):
    base_w = _master_weight_coord(font, base_master)
    if base_w is None:
        return None
    candidates = []
    for m in list(getattr(font, "masters", []) or []):
        if getattr(m, "id", None) == getattr(base_master, "id", None):
            continue
        w = _master_weight_coord(font, m)
        if w is None:
            continue
        if float(w) > float(base_w):
            candidates.append((float(w) - float(base_w), m))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]


def _apply_compensated_tuning_impl(
    font_index: int = 0,
    glyph_names: list = None,
    base_master_id: str = None,
    ref_master_id: str = None,
    output_master_id: str = None,
    sx: float = 1.0,
    sy: float = 1.0,
    keep_stroke: float = 0.9,
    stroke_exponent_a: float = None,
    q_x: float = None,
    q_y: float = None,
    italic_angle: float = None,
    translate_x: float = 0.0,
    translate_y: float = 0.0,
    extrapolation: str = "clamp",
    round_units: bool = True,
    stem_ratio_b: float = None,
    stem_measure: dict = None,
    confirm: bool = False,
    dry_run: bool = False,
    backup: bool = True,
    backup_layer_name: str = "GMCP Backup: CompTune",
    ref_fallback: str = "error",
) -> str:
    """Apply compensated tuning across glyphs (dry-run or confirm).

    Safety:
      - Refuses to mutate without `confirm=true` (unless `dry_run=true`).
      - Never auto-saves.
      - When applying (not dry-run), can create a backup layer per glyph.

    Units:
      - All geometry values are in font units; `sx`/`sy` are unitless.

    Behavior:
      - If `glyph_names` is omitted, uses the current Glyphs selection (active font only).
      - If `ref_master_id` is omitted, picks the next heavier master on the wght axis when possible.
      - If no heavier master exists:
          - `ref_fallback="error"` (default) fails
          - `ref_fallback="geometric"` uses base==ref (q=1) as a safe fallback

    Returns:
      JSON payload with `ok`, `dryRun`, `summary`, optional `stem` measurement data,
      and per-glyph `results`.
    """
    try:
        if not confirm and not dry_run:
            return {
                "ok": False,
                "error": "Refusing to apply without confirm=true.",
                "hint": "Run with dry_run=true to preview or confirm=true to apply.",
            }

        font, error = _resolve_font_payload(font_index)
        if error:
            return error

        if glyph_names:
            names = list(glyph_names)
        else:
            if not _is_active_font(Glyphs, font):
                return {"ok": False, "error": "No glyph_names provided and font_index is not the active font."}
            names = _spacing_selected_glyph_names_for_font(font)

        if not names:
            return {"ok": False, "error": "No glyphs to apply."}

        if base_master_id is None:
            base_master_id = getattr(getattr(font, "selectedFontMaster", None), "id", None) or getattr(font.masters[0], "id", None)
        if not base_master_id:
            return {"ok": False, "error": "Unable to determine base_master_id."}

        base_master = next((m for m in (font.masters or []) if str(getattr(m, "id", "")) == str(base_master_id)), None)
        if not base_master:
            return {"ok": False, "error": "Base master not found", "base_master_id": base_master_id}

        if ref_master_id is None:
            ref = _next_heavier_master(font, base_master)
            if ref is None:
                if str(ref_fallback or "error").strip().lower() == "geometric":
                    ref_master_id = str(base_master_id)
                else:
                    return {
                        "ok": False,
                        "error": "No heavier master found. Provide ref_master_id explicitly or set ref_fallback='geometric'.",
                        "base_master_id": base_master_id,
                    }
            else:
                ref_master_id = str(getattr(ref, "id", ""))

        if output_master_id is None:
            output_master_id = str(base_master_id)

        ref_master = next((m for m in (font.masters or []) if str(getattr(m, "id", "")) == str(ref_master_id)), None)
        if not ref_master:
            return {"ok": False, "error": "Ref master not found", "ref_master_id": ref_master_id}

        # Pre-measure b once if needed.
        stem_info = None
        b = None
        if stem_ratio_b is not None:
            b = float(stem_ratio_b)
        elif q_x is None or q_y is None:
            if str(ref_master_id) == str(base_master_id):
                b = None
            else:
                sm = stem_measure if isinstance(stem_measure, dict) else {}
                stem_info = _stem_ratio_payload(
                    font=font,
                    base_master=base_master,
                    ref_master=ref_master,
                    reference_glyphs=sm.get("reference_glyphs"),
                    samples=sm.get("samples", 9),
                    band=sm.get("band", 0.2),
                    min_width=sm.get("min_width", 5.0),
                    max_width=sm.get("max_width"),
                    include_components=bool(sm.get("include_components", True)),
                    stem_source=sm.get("stem_source", "auto"),
                    mismatch_tolerance=sm.get("mismatch_tolerance", 0.2),
                )
                if not stem_info.get("ok"):
                    return {"ok": False, "error": "Unable to measure stem ratio b", "stem": stem_info}
                b = float(stem_info.get("b"))

        results = []
        ok_count = 0
        skipped_count = 0
        error_count = 0
        backup_count = 0

        for name in names:
            glyph = font.glyphs[name]
            if not glyph:
                results.append({"glyphName": name, "status": "error", "reason": "glyph_not_found"})
                error_count += 1
                continue

            try:
                dest_layer = glyph.layers[str(output_master_id)]
            except Exception:
                dest_layer = None
            if not dest_layer:
                results.append({"glyphName": name, "status": "error", "reason": "dest_layer_missing", "outputMasterId": output_master_id})
                error_count += 1
                continue

            if _layer_has_components(dest_layer):
                results.append({"glyphName": name, "status": "skipped", "reason": "dest_has_components"})
                skipped_count += 1
                continue

            review_data = _review_compensated_tuning_impl(
                font_index=font_index,
                glyph_name=name,
                base_master_id=str(base_master_id),
                ref_master_id=str(ref_master_id),
                sx=sx,
                sy=sy,
                keep_stroke=keep_stroke,
                stroke_exponent_a=stroke_exponent_a,
                q_x=q_x,
                q_y=q_y,
                italic_angle=italic_angle,
                translate_x=translate_x,
                translate_y=translate_y,
                extrapolation=extrapolation,
                round_units=round_units,
                stem_ratio_b=b,
                stem_measure=stem_measure,
            )

            if not isinstance(review_data, dict) or not review_data.get("gmcp", {}).get("ok"):
                results.append({"glyphName": name, "status": "error", "reason": "review_failed", "details": review_data})
                error_count += 1
                continue

            if backup and not dry_run:
                try:
                    bl = dest_layer.copy()
                    bl.name = "{} (sx={} sy={} base={} ref={})".format(
                        backup_layer_name,
                        float(sx),
                        float(sy),
                        str(base_master_id),
                        str(ref_master_id),
                    )
                    try:
                        bl.associatedMasterId = str(output_master_id)
                    except Exception:
                        pass
                    glyph.layers.append(bl)
                    backup_count += 1
                except Exception:
                    results.append({"glyphName": name, "status": "error", "reason": "backup_failed"})
                    error_count += 1
                    continue

            if dry_run:
                results.append({"glyphName": name, "status": "ok", "action": "preview"})
                ok_count += 1
                continue

            # Apply: replace paths and width.
            new_paths = []
            for path_data in review_data.get("paths", []) or []:
                new_path = GSPath()
                for node_data in path_data.get("nodes", []) or []:
                    new_node = GSNode()
                    new_node.position = (
                        float(node_data.get("x", 0.0)),
                        float(node_data.get("y", 0.0)),
                    )
                    new_node.type = node_data.get("type", "line")
                    new_node.smooth = bool(node_data.get("smooth", False))
                    new_path.nodes.append(new_node)
                new_path.closed = bool(path_data.get("closed", True))
                new_paths.append(new_path)
            replace_result = _replace_layer_paths_and_metrics(
                dest_layer,
                new_paths,
                width=float(review_data["width"]) if "width" in review_data else None,
            )
            if not replace_result.get("ok"):
                results.append(
                    {
                        "glyphName": name,
                        "status": "error",
                        "reason": replace_result.get("error") or "path_write_failed",
                    }
                )
                error_count += 1
                continue

            results.append({"glyphName": name, "status": "ok", "action": "applied"})
            ok_count += 1

        return {
            "ok": True,
            "dryRun": bool(dry_run),
            "summary": {
                "glyphCount": len(names),
                "okCount": ok_count,
                "skippedCount": skipped_count,
                "errorCount": error_count,
                "backupCount": backup_count,
                "baseMasterId": str(base_master_id),
                "refMasterId": str(ref_master_id),
                "outputMasterId": str(output_master_id),
            },
            "stem": stem_info,
            "results": results,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
async def apply_compensated_tuning(
    font_index: int = 0,
    glyph_names: list = None,
    base_master_id: str = None,
    ref_master_id: str = None,
    output_master_id: str = None,
    sx: float = 1.0,
    sy: float = 1.0,
    keep_stroke: float = 0.9,
    stroke_exponent_a: float = None,
    q_x: float = None,
    q_y: float = None,
    italic_angle: float = None,
    translate_x: float = 0.0,
    translate_y: float = 0.0,
    extrapolation: str = "clamp",
    round_units: bool = True,
    stem_ratio_b: float = None,
    stem_measure: dict = None,
    confirm: bool = False,
    dry_run: bool = False,
    backup: bool = True,
    backup_layer_name: str = "GMCP Backup: CompTune",
    ref_fallback: str = "error",
) -> str:
    return _safe_json(
        _apply_compensated_tuning_impl(
            font_index=font_index,
            glyph_names=glyph_names,
            base_master_id=base_master_id,
            ref_master_id=ref_master_id,
            output_master_id=output_master_id,
            sx=sx,
            sy=sy,
            keep_stroke=keep_stroke,
            stroke_exponent_a=stroke_exponent_a,
            q_x=q_x,
            q_y=q_y,
            italic_angle=italic_angle,
            translate_x=translate_x,
            translate_y=translate_y,
            extrapolation=extrapolation,
            round_units=round_units,
            stem_ratio_b=stem_ratio_b,
            stem_measure=stem_measure,
            confirm=confirm,
            dry_run=dry_run,
            backup=backup,
            backup_layer_name=backup_layer_name,
            ref_fallback=ref_fallback,
        )
    )
