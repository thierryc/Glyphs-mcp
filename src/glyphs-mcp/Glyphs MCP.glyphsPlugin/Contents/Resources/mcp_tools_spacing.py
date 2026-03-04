# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json
import math

from GlyphsApp import Glyphs, GSGuide  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import _custom_parameter, _safe_json, _spacing_selected_glyph_names_for_font

import spacing_engine

# AppKit is available inside Glyphs (PyObjC). Keep import optional so this file
# is still importable in environments where Glyphs isn't present.
try:
    from AppKit import NSPoint  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - only relevant outside Glyphs
    NSPoint = None


def _merge_spacing_defaults(user_defaults=None, debug=None):
    merged = dict(spacing_engine.DEFAULTS)
    if isinstance(user_defaults, dict):
        for k, v in user_defaults.items():
            if v is None:
                continue
            merged[k] = v
    if isinstance(debug, dict):
        # Allow debug.includeSamples without forcing payload bloat by default.
        if "includeSamples" in debug and debug["includeSamples"] is not None:
            merged["includeSamples"] = bool(debug["includeSamples"])
    return merged


def _effective_master_params_for_spacing(font, master, merged_defaults, explicit_defaults):
    explicit_defaults = explicit_defaults or {}

    def custom_dict(obj):
        out = {}
        if obj is None:
            return out
        for field in spacing_engine.SPACING_PARAM_FIELDS:
            for key_set in (
                spacing_engine.SPACING_PARAM_KEYS_CANONICAL,
                spacing_engine.SPACING_PARAM_KEYS_GMCP_LEGACY,
                spacing_engine.SPACING_PARAM_KEYS_PARAM_LEGACY,
            ):
                k = key_set.get(field)
                if not k:
                    continue
                val = _custom_parameter(obj, k, None)
                if val is not None:
                    out[k] = val
        return out

    master_custom = custom_dict(master)
    font_custom = custom_dict(font)

    def pick(field, fallback):
        return spacing_engine.resolve_param_precedence(
            field=field,
            per_call_defaults=explicit_defaults,
            master_custom=master_custom,
            font_custom=font_custom,
            fallback=fallback,
        )

    return {
        "xHeight": getattr(master, "xHeight", None),
        "italicAngle": getattr(master, "italicAngle", 0.0),
        "area": pick("area", merged_defaults.get("area")),
        "depth": pick("depth", merged_defaults.get("depth")),
        "over": pick("over", merged_defaults.get("over")),
        "frequency": pick("frequency", merged_defaults.get("frequency")),
    }


DEFAULT_SPACING_GUIDE_GLYPHS = [
    "n",
    "H",
    "zero",
    "o",
    "O",
    "period",
    "comma",
]


def _layer_bounds_ymin_ymax(layer):
    """Return (yMin, yMax) from layer.bounds, or (None, None) if unavailable."""
    try:
        b = getattr(layer, "bounds", None)
        if not b:
            return (None, None)
        origin = getattr(b, "origin", None)
        size = getattr(b, "size", None)
        if not origin or not size:
            return (None, None)
        y = float(getattr(origin, "y", 0.0))
        h = float(getattr(size, "height", 0.0))
        return (y, y + h)
    except Exception:
        return (None, None)


def _is_spacing_guide(guide):
    """Return True if the guide looks like one created by set_spacing_guides."""
    try:
        ud = getattr(guide, "userData", None)
        if ud and ud.get("cx.ap.spacingGuides") is True:
            return True
    except Exception:
        pass
    try:
        name = getattr(guide, "name", "") or ""
        name_s = str(name)
        if name_s.startswith("cx.ap.spacing."):
            return True
    except Exception:
        pass
    return False


def _clear_spacing_guides_from_layer(layer, *, dry_run: bool):
    removed = []
    try:
        guides = list(getattr(layer, "guides", []) or [])
    except Exception:
        guides = []

    # Remove from end to keep indices stable.
    for idx in range(len(guides) - 1, -1, -1):
        g = guides[idx]
        if not _is_spacing_guide(g):
            continue
        pos = getattr(g, "position", None)
        try:
            x = float(getattr(pos, "x", 0.0)) if pos is not None else None
        except Exception:
            x = None
        try:
            y = float(getattr(pos, "y", 0.0)) if pos is not None else None
        except Exception:
            y = None
        removed.append(
            {
                "index": idx,
                "name": getattr(g, "name", None),
                "position": {"x": x, "y": y},
            }
        )
        if not dry_run:
            try:
                del layer.guides[idx]
            except Exception:
                try:
                    layer.guides.remove(g)
                except Exception:
                    pass

    return removed


@mcp.tool()
async def set_spacing_guides(
    font_index: int = 0,
    glyph_names: list = None,
    master_scope: str = "current",
    master_id: str = None,
    mode: str = "add",
    reference_glyph: str = "x",
    style: str = "model",
    dry_run: bool = False,
) -> str:
    """Add or clear glyph-level guides that visualize the spacing measurement model.

    This tool is intended as a lightweight in-editor visualization aid. It writes guides
    into glyph layers (layer.guides) so they can be inspected in the Edit view.

    Args:
        font_index: Index of the font (0-based). Defaults to 0.
        glyph_names: List of glyph names. If omitted, uses currently selected glyphs in Glyphs (active font).
        master_scope: One of "current" (default), "all", or "master".
        master_id: Required when master_scope="master".
        mode: One of "add" (default) or "clear".
        reference_glyph: Glyph name used to derive the vertical band (defaults to "x").
                         Special value "*" means “use the glyph itself”.
        style: One of "band", "model" (default), or "full".
               - "band": two horizontal guides for yMin/yMax
               - "model": band + zone/depth/avg whitespace boundaries
               - "full": model + raw reference bounds + full extremes
        dry_run: If true, report changes without mutating.

    Returns:
        JSON payload with counts and per-layer actions (no auto-save).
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return _safe_json(
                {
                    "ok": False,
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts)),
                }
            )

        font = Glyphs.fonts[font_index]
        scope = (master_scope or "current").strip().lower()
        if scope not in ("current", "all", "master"):
            return _safe_json(
                {
                    "ok": False,
                    "error": "Invalid master_scope '{}'".format(master_scope),
                    "hint": "Use one of: current, all, master",
                }
            )

        mode_norm = (mode or "add").strip().lower()
        if mode_norm not in ("add", "clear"):
            return _safe_json(
                {
                    "ok": False,
                    "error": "Invalid mode '{}'".format(mode),
                    "hint": "Use one of: add, clear",
                }
            )

        style_norm = (style or "model").strip().lower()
        if style_norm not in ("band", "model", "full"):
            return _safe_json(
                {
                    "ok": False,
                    "error": "Invalid style '{}'".format(style),
                    "hint": "Use one of: band, model, full",
                }
            )

        # Determine masters
        masters = []
        if scope == "all":
            masters = list(font.masters or [])
        elif scope == "master":
            if not master_id:
                return _safe_json({"ok": False, "error": "master_id is required for master_scope=master"})
            wanted = str(master_id)
            found = None
            for m in font.masters:
                if getattr(m, "id", None) == wanted:
                    found = m
                    break
            if not found:
                return _safe_json({"ok": False, "error": "Master ID '{}' not found".format(master_id)})
            masters = [found]
        else:
            if getattr(font, "selectedFontMaster", None):
                masters = [font.selectedFontMaster]
            else:
                masters = [font.masters[0]] if font.masters else []

        if not masters:
            return _safe_json({"ok": False, "error": "No masters found"})

        # Determine glyphs
        names = glyph_names
        if not names:
            names = _spacing_selected_glyph_names_for_font(font)
        if not names:
            names = list(DEFAULT_SPACING_GUIDE_GLYPHS)
        if not names:
            return _safe_json({"ok": False, "error": "No glyph_names available"})

        ref_name = (reference_glyph or "x").strip()
        use_self_ref = ref_name == "*" or not ref_name

        merged_defaults = _merge_spacing_defaults(user_defaults=None, debug=None)
        explicit_defaults = {}  # do not treat per-call defaults as "stored settings" for guides

        def _ensure_user_data(guide_obj):
            try:
                ud = getattr(guide_obj, "userData", None)
                if ud is None:
                    guide_obj.userData = {}
                return guide_obj.userData
            except Exception:
                return None

        def _add_horizontal_guide(layer_obj, *, name: str, y: float):
            g = GSGuide()
            try:
                g.angle = 0.0
            except Exception:
                pass
            try:
                if NSPoint is not None:
                    g.position = NSPoint(0, float(y))
                else:
                    g.position = (0, float(y))
            except Exception:
                pass
            try:
                g.name = str(name)
            except Exception:
                pass
            try:
                g.locked = True
            except Exception:
                pass
            ud = _ensure_user_data(g)
            if ud is not None:
                ud["cx.ap.spacingGuides"] = True
                ud["cx.ap.spacingGuideName"] = str(name)
                ud["cx.ap.spacingGuideStyle"] = style_norm
            if not dry_run:
                try:
                    layer_obj.guides.append(g)
                except Exception:
                    pass
            return g

        def _add_xprime_guide(
            layer_obj,
            *,
            name: str,
            x_prime: float,
            y_min: float,
            y_max: float,
            x_height: float,
            italic_angle: float,
            italic_mode: str,
        ):
            g = GSGuide()

            # In "deslant" mode, x-prime boundaries are constant in a deslanted space:
            #   x' = x + tan(a) * (y - xHeight/2)
            # So to draw a constant-x' boundary in the original coordinates, draw the line:
            #   x(y) = x' - tan(a) * (y - xHeight/2)
            try:
                mode_s = str(italic_mode or "").strip().lower()
            except Exception:
                mode_s = "deslant"
            angle = float(italic_angle or 0.0)

            try:
                y1 = float(y_min)
                y2 = float(y_max)
            except Exception:
                y1, y2 = 0.0, 0.0

            if mode_s == "deslant" and abs(angle) > 1e-6 and abs(y2 - y1) > 1e-6:
                try:
                    t = math.tan(math.radians(angle))
                except Exception:
                    t = 0.0
                try:
                    xh = float(x_height or 0.0)
                except Exception:
                    xh = 0.0
                x1 = float(x_prime) - t * (y1 - xh / 2.0)
                x2 = float(x_prime) - t * (y2 - xh / 2.0)

                try:
                    if NSPoint is not None:
                        g.position = NSPoint(x1, y1)
                    else:
                        g.position = (x1, y1)
                except Exception:
                    pass

                try:
                    ang = math.degrees(math.atan2((y2 - y1), (x2 - x1)))
                    if ang < 0:
                        ang += 180.0
                    g.angle = float(ang)
                except Exception:
                    try:
                        g.angle = 90.0
                    except Exception:
                        pass
            else:
                # Upright (or "none" mode): constant x is a vertical guide.
                try:
                    if NSPoint is not None:
                        g.position = NSPoint(float(x_prime), 0.0)
                    else:
                        g.position = (float(x_prime), 0.0)
                except Exception:
                    pass
                try:
                    g.angle = 90.0
                except Exception:
                    pass

            try:
                g.name = str(name)
            except Exception:
                pass
            try:
                g.locked = True
            except Exception:
                pass

            ud = _ensure_user_data(g)
            if ud is not None:
                ud["cx.ap.spacingGuides"] = True
                ud["cx.ap.spacingGuideName"] = str(name)
                ud["cx.ap.spacingGuideStyle"] = style_norm
                ud["xPrime"] = float(x_prime)

            if not dry_run:
                try:
                    layer_obj.guides.append(g)
                except Exception:
                    pass
            return g

        results = []
        added_count = 0
        removed_count = 0
        skipped_count = 0

        for glyph_name in names:
            glyph = font.glyphs[glyph_name] if glyph_name else None
            if not glyph:
                skipped_count += 1
                results.append({"glyphName": glyph_name, "status": "skipped", "reason": "glyph_not_found"})
                continue

            for master in masters:
                mid = getattr(master, "id", None)
                try:
                    layer = glyph.layers[mid]
                except Exception:
                    layer = None

                if not layer:
                    skipped_count += 1
                    results.append(
                        {
                            "glyphName": glyph_name,
                            "masterId": mid,
                            "masterName": getattr(master, "name", None),
                            "status": "skipped",
                            "reason": "layer_not_found",
                        }
                    )
                    continue

                removed = _clear_spacing_guides_from_layer(layer, dry_run=bool(dry_run))
                removed_count += len(removed)

                if mode_norm == "clear":
                    results.append(
                        {
                            "glyphName": glyph_name,
                            "masterId": mid,
                            "masterName": getattr(master, "name", None),
                            "status": "ok",
                            "action": "cleared",
                            "removed": removed,
                        }
                    )
                    continue

                eff = _effective_master_params_for_spacing(font, master, merged_defaults, explicit_defaults)
                x_height = eff.get("xHeight") or getattr(master, "xHeight", None) or 0.0

                # Guides are visualization: do not let metrics keys / auto-aligned components prevent us from
                # computing the underlying model primitives when possible.
                guide_defaults = dict(merged_defaults)
                guide_defaults["referenceGlyph"] = ref_name if not use_self_ref else "*"
                guide_defaults["includeComponents"] = True
                guide_defaults["respectMetricsKeys"] = False
                guide_defaults["skipAutoAligned"] = False

                model = spacing_engine.compute_suggestion_for_layer(
                    font=font,
                    glyph=glyph,
                    layer=layer,
                    master=master,
                    rules=[],
                    defaults=guide_defaults,
                    master_params=eff,
                )

                # Preferred band source: engine reference band (already includes "over").
                y_min = None
                y_max = None
                ref_over_units = None
                try:
                    ref = model.get("reference") or {}
                    y_min = ref.get("yMin")
                    y_max = ref.get("yMax")
                    ref_over_units = ref.get("overUnits")
                except Exception:
                    y_min = None
                    y_max = None
                    ref_over_units = None

                # Fallback: compute band from reference bounds + stored over if engine couldn't.
                if y_min is None or y_max is None:
                    over_pct = eff.get("over", merged_defaults.get("over", 0.0)) or 0.0
                    try:
                        over_units = (float(over_pct) / 100.0) * float(x_height or 0.0)
                    except Exception:
                        over_units = 0.0

                    if use_self_ref:
                        ref_layer = layer
                    else:
                        ref_glyph = font.glyphs[ref_name]
                        ref_layer = None
                        try:
                            if ref_glyph:
                                ref_layer = ref_glyph.layers[mid]
                        except Exception:
                            ref_layer = None

                    y0, y1 = _layer_bounds_ymin_ymax(ref_layer) if ref_layer else (None, None)
                    if y0 is not None and y1 is not None:
                        y_min = float(y0) - float(over_units)
                        y_max = float(y1) + float(over_units)

                if y_min is None or y_max is None:
                    skipped_count += 1
                    results.append(
                        {
                            "glyphName": glyph_name,
                            "masterId": mid,
                            "masterName": getattr(master, "name", None),
                            "status": "skipped",
                            "reason": "reference_band_unavailable",
                            "referenceGlyph": ref_name if not use_self_ref else "*",
                            "modelStatus": model.get("status"),
                            "modelReason": model.get("reason"),
                        }
                    )
                    continue

                added = []

                # Always show the band in add mode, regardless of style.
                for kind, y in (("min", y_min), ("max", y_max)):
                    guide_name = "cx.ap.spacing.band:{}".format(kind)
                    g = _add_horizontal_guide(layer, name=guide_name, y=float(y))
                    try:
                        ud = _ensure_user_data(g)
                        if ud is not None:
                            ud["kind"] = kind
                            ud["referenceGlyph"] = ref_name if not use_self_ref else "*"
                            ud["y"] = float(y)
                    except Exception:
                        pass
                    added.append({"name": guide_name, "kind": kind, "y": float(y), "angle": getattr(g, "angle", None)})
                    added_count += 1

                # Band-only style stops here.
                if style_norm == "band":
                    results.append(
                        {
                            "glyphName": glyph_name,
                            "masterId": mid,
                            "masterName": getattr(master, "name", None),
                            "status": "ok",
                            "action": "added",
                            "style": style_norm,
                            "referenceGlyph": ref_name if not use_self_ref else "*",
                            "band": {"yMin": float(y_min), "yMax": float(y_max)},
                            "modelStatus": model.get("status"),
                            "modelReason": model.get("reason"),
                            "removed": removed,
                            "added": added,
                        }
                    )
                    continue

                # If the engine couldn't compute measured primitives, stop at the band.
                if model.get("status") != "ok":
                    skipped_count += 1
                    results.append(
                        {
                            "glyphName": glyph_name,
                            "masterId": mid,
                            "masterName": getattr(master, "name", None),
                            "status": "skipped",
                            "reason": "model_not_ok",
                            "style": style_norm,
                            "referenceGlyph": ref_name if not use_self_ref else "*",
                            "band": {"yMin": float(y_min), "yMax": float(y_max)},
                            "modelStatus": model.get("status"),
                            "modelReason": model.get("reason"),
                            "removed": removed,
                            "added": added,
                        }
                    )
                    continue

                measured = model.get("measured") or {}
                target = model.get("target") or {}
                params = model.get("params") or {}

                l_extreme = measured.get("lExtreme")
                r_extreme = measured.get("rExtreme")
                height = measured.get("height")
                left_area = measured.get("leftArea")
                right_area = measured.get("rightArea")
                target_avg = target.get("targetAvg")
                depth_pct = params.get("depth")
                italic_mode = params.get("italicMode")
                italic_angle = params.get("italicAngle")

                # Compute derived values (average whitespace is "area / height").
                try:
                    h = float(height)
                except Exception:
                    h = 0.0

                ok_for_model = (
                    l_extreme is not None
                    and r_extreme is not None
                    and left_area is not None
                    and right_area is not None
                    and target_avg is not None
                    and h > 1e-6
                )

                if ok_for_model:
                    l_extreme_f = float(l_extreme)
                    r_extreme_f = float(r_extreme)
                    avg_measured_left = float(left_area) / h
                    avg_measured_right = float(right_area) / h
                    avg_target = float(target_avg)

                    # Zone edges.
                    for side, x_p in (("L", l_extreme_f), ("R", r_extreme_f)):
                        guide_name = "cx.ap.spacing.zone:{}".format(side)
                        g = _add_xprime_guide(
                            layer,
                            name=guide_name,
                            x_prime=float(x_p),
                            y_min=float(y_min),
                            y_max=float(y_max),
                            x_height=float(x_height or 0.0),
                            italic_angle=float(italic_angle or 0.0),
                            italic_mode=str(italic_mode or "deslant"),
                        )
                        added.append({"name": guide_name, "xPrime": float(x_p), "angle": getattr(g, "angle", None)})
                        added_count += 1

                    # Depth clamp.
                    try:
                        depth_units = float(x_height or 0.0) * (float(depth_pct or 0.0) / 100.0)
                    except Exception:
                        depth_units = 0.0
                    for side, x_p in (("L", l_extreme_f + depth_units), ("R", r_extreme_f - depth_units)):
                        guide_name = "cx.ap.spacing.depth:{}".format(side)
                        g = _add_xprime_guide(
                            layer,
                            name=guide_name,
                            x_prime=float(x_p),
                            y_min=float(y_min),
                            y_max=float(y_max),
                            x_height=float(x_height or 0.0),
                            italic_angle=float(italic_angle or 0.0),
                            italic_mode=str(italic_mode or "deslant"),
                        )
                        added.append({"name": guide_name, "xPrime": float(x_p), "angle": getattr(g, "angle", None)})
                        added_count += 1

                    # Average whitespace: measured vs target.
                    avg_lines = [
                        ("avg.measured", "L", l_extreme_f + avg_measured_left),
                        ("avg.measured", "R", r_extreme_f - avg_measured_right),
                        ("avg.target", "L", l_extreme_f + avg_target),
                        ("avg.target", "R", r_extreme_f - avg_target),
                    ]
                    for group, side, x_p in avg_lines:
                        guide_name = "cx.ap.spacing.{}:{}".format(group, side)
                        g = _add_xprime_guide(
                            layer,
                            name=guide_name,
                            x_prime=float(x_p),
                            y_min=float(y_min),
                            y_max=float(y_max),
                            x_height=float(x_height or 0.0),
                            italic_angle=float(italic_angle or 0.0),
                            italic_mode=str(italic_mode or "deslant"),
                        )
                        added.append({"name": guide_name, "xPrime": float(x_p), "angle": getattr(g, "angle", None)})
                        added_count += 1

                # Full mode: add raw ref bounds (without over) + full extremes if available.
                if style_norm == "full":
                    try:
                        ou = float(ref_over_units or 0.0)
                    except Exception:
                        ou = 0.0
                    if ou and abs(ou) > 1e-6:
                        y_min_raw = float(y_min) + ou
                        y_max_raw = float(y_max) - ou
                        for kind, y in (("min", y_min_raw), ("max", y_max_raw)):
                            guide_name = "cx.ap.spacing.ref:{}".format(kind)
                            g = _add_horizontal_guide(layer, name=guide_name, y=float(y))
                            added.append({"name": guide_name, "kind": kind, "y": float(y), "angle": getattr(g, "angle", None)})
                            added_count += 1

                    try:
                        lf = measured.get("lFullExtreme")
                        rf = measured.get("rFullExtreme")
                        if lf is not None and rf is not None:
                            for side, x_p in (("L", float(lf)), ("R", float(rf))):
                                guide_name = "cx.ap.spacing.full:{}".format(side)
                                g = _add_xprime_guide(
                                    layer,
                                    name=guide_name,
                                    x_prime=float(x_p),
                                    y_min=float(y_min),
                                    y_max=float(y_max),
                                    x_height=float(x_height or 0.0),
                                    italic_angle=float(italic_angle or 0.0),
                                    italic_mode=str(italic_mode or "deslant"),
                                )
                                added.append({"name": guide_name, "xPrime": float(x_p), "angle": getattr(g, "angle", None)})
                                added_count += 1
                    except Exception:
                        pass

                results.append(
                    {
                        "glyphName": glyph_name,
                        "masterId": mid,
                        "masterName": getattr(master, "name", None),
                        "status": "ok",
                        "action": "added",
                        "style": style_norm,
                        "referenceGlyph": ref_name if not use_self_ref else "*",
                        "xHeight": x_height,
                        "band": {"yMin": float(y_min), "yMax": float(y_max)},
                        "modelStatus": model.get("status"),
                        "modelReason": model.get("reason"),
                        "removed": removed,
                        "added": added,
                    }
                )

        return _safe_json(
            {
                "ok": True,
                "dryRun": bool(dry_run),
                "mode": mode_norm,
                "masterScope": scope,
                "referenceGlyph": ref_name if not use_self_ref else "*",
                "style": style_norm,
                "summary": {
                    "glyphCount": len(names),
                    "masterCount": len(masters),
                    "addedCount": added_count,
                    "removedCount": removed_count,
                    "skippedCount": skipped_count,
                },
                "results": results,
            }
        )
    except Exception as e:
        return _safe_json({"ok": False, "error": str(e)})


@mcp.tool()
async def review_spacing(
    font_index: int = 0,
    glyph_names: list = None,
    master_id: str = None,
    rules: list = None,
    defaults: dict = None,
    debug: dict = None,
) -> str:
    """Review spacing and suggest sidebearings/width using a clean-room area-based model.

    This tool does not mutate the font.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return _safe_json(
                {
                    "ok": False,
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts)),
                    "results": [],
                }
            )

        font = Glyphs.fonts[font_index]

        merged_defaults = _merge_spacing_defaults(defaults, debug)
        explicit_defaults = defaults if isinstance(defaults, dict) else {}

        if glyph_names:
            names = list(glyph_names)
        else:
            # Prefer selection, but only when the referenced font is active.
            if not Glyphs.font or Glyphs.font != font:
                return _safe_json(
                    {
                        "ok": False,
                        "error": "No glyph_names provided and font_index is not the active font.",
                        "hint": "Provide glyph_names explicitly or activate the target font in Glyphs.",
                        "results": [],
                    }
                )
            names = _spacing_selected_glyph_names_for_font(font)

        if not names:
            return _safe_json(
                {
                    "ok": False,
                    "error": "No glyphs to review.",
                    "hint": "Select glyphs in Glyphs or pass glyph_names.",
                    "results": [],
                }
            )

        # Determine masters to evaluate.
        masters = []
        if master_id:
            wanted = str(master_id)
            masters = [m for m in font.masters if getattr(m, "id", None) == wanted]
            if not masters:
                return _safe_json(
                    {
                        "ok": False,
                        "error": "Master ID '{}' not found".format(master_id),
                        "results": [],
                    }
                )
        else:
            masters = list(font.masters or [])

        results = []
        ok_count = 0
        skipped_count = 0
        error_count = 0
        layer_count = 0

        for name in names:
            glyph = font.glyphs[name]
            if not glyph:
                results.append(
                    {
                        "glyphName": name,
                        "status": "error",
                        "reason": "glyph_not_found",
                    }
                )
                error_count += 1
                continue

            for master in masters:
                layer_count += 1
                mid = getattr(master, "id", None)
                try:
                    layer = glyph.layers[mid]
                except Exception:
                    layer = None

                if not layer:
                    results.append(
                        {
                            "glyphName": glyph.name,
                            "masterId": mid,
                            "masterName": getattr(master, "name", ""),
                            "status": "skipped",
                            "reason": "layer_missing",
                        }
                    )
                    skipped_count += 1
                    continue

                master_params = _effective_master_params_for_spacing(font, master, merged_defaults, explicit_defaults)
                try:
                    r = spacing_engine.compute_suggestion_for_layer(
                        font=font,
                        glyph=glyph,
                        layer=layer,
                        master=master,
                        rules=rules,
                        defaults=merged_defaults,
                        master_params=master_params,
                    )
                except Exception as exc:
                    results.append(
                        {
                            "glyphName": glyph.name,
                            "masterId": mid,
                            "masterName": getattr(master, "name", ""),
                            "status": "error",
                            "reason": "exception",
                            "error": str(exc),
                        }
                    )
                    error_count += 1
                    continue

                results.append(r)
                if r.get("status") == "ok":
                    ok_count += 1
                elif r.get("status") == "skipped":
                    skipped_count += 1
                else:
                    error_count += 1

        return _safe_json(
            {
                "ok": True,
                "summary": {
                    "glyphCount": len(names),
                    "layerCount": layer_count,
                    "okCount": ok_count,
                    "skippedCount": skipped_count,
                    "errorCount": error_count,
                    "rulesCount": len(rules or []),
                    "defaults": {
                        "area": merged_defaults.get("area"),
                        "depth": merged_defaults.get("depth"),
                        "over": merged_defaults.get("over"),
                        "frequency": merged_defaults.get("frequency"),
                        "referenceGlyph": merged_defaults.get("referenceGlyph"),
                        "italicMode": merged_defaults.get("italicMode"),
                    },
                },
                "results": results,
            }
        )
    except Exception as e:
        return _safe_json({"ok": False, "error": str(e), "results": []})


@mcp.tool()
async def apply_spacing(
    font_index: int = 0,
    glyph_names: list = None,
    master_id: str = None,
    rules: list = None,
    defaults: dict = None,
    clamp: dict = None,
    confirm: bool = False,
    dry_run: bool = False,
) -> str:
    """Apply suggested spacing (sidebearings/width) computed by review_spacing.

    Safety:
    - Set confirm=true to mutate.
    - Use dry_run=true to preview.
    """
    try:
        if not confirm and not dry_run:
            return _safe_json(
                {
                    "ok": False,
                    "error": "Refusing to apply spacing without confirm=true.",
                    "hint": "Run apply_spacing(..., dry_run=true) to preview or set confirm=true to apply.",
                }
            )

        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return _safe_json(
                {
                    "ok": False,
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts)),
                }
            )

        font = Glyphs.fonts[font_index]
        merged_defaults = _merge_spacing_defaults(defaults, debug=None)
        explicit_defaults = defaults if isinstance(defaults, dict) else {}

        effective_clamp = clamp or {"maxDeltaLSB": 150, "maxDeltaRSB": 150, "minLSB": -200, "minRSB": -200}

        if glyph_names:
            names = list(glyph_names)
        else:
            if not Glyphs.font or Glyphs.font != font:
                return _safe_json(
                    {
                        "ok": False,
                        "error": "No glyph_names provided and font_index is not the active font.",
                        "hint": "Provide glyph_names explicitly or activate the target font in Glyphs.",
                    }
                )
            names = _spacing_selected_glyph_names_for_font(font)

        if not names:
            return _safe_json(
                {
                    "ok": False,
                    "error": "No glyphs to apply.",
                    "hint": "Select glyphs in Glyphs or pass glyph_names.",
                }
            )

        masters = []
        if master_id:
            wanted = str(master_id)
            masters = [m for m in font.masters if getattr(m, "id", None) == wanted]
            if not masters:
                return _safe_json({"ok": False, "error": "Master ID '{}' not found".format(master_id)})
        else:
            masters = list(font.masters or [])

        results = []
        applied = []
        ok_count = 0
        skipped_count = 0
        error_count = 0
        applied_count = 0

        for name in names:
            glyph = font.glyphs[name]
            if not glyph:
                results.append({"glyphName": name, "status": "error", "reason": "glyph_not_found"})
                error_count += 1
                continue

            for master in masters:
                mid = getattr(master, "id", None)
                try:
                    layer = glyph.layers[mid]
                except Exception:
                    layer = None

                if not layer:
                    results.append(
                        {
                            "glyphName": glyph.name,
                            "masterId": mid,
                            "masterName": getattr(master, "name", ""),
                            "status": "skipped",
                            "reason": "layer_missing",
                        }
                    )
                    skipped_count += 1
                    continue

                master_params = _effective_master_params_for_spacing(font, master, merged_defaults, explicit_defaults)
                try:
                    r = spacing_engine.compute_suggestion_for_layer(
                        font=font,
                        glyph=glyph,
                        layer=layer,
                        master=master,
                        rules=rules,
                        defaults=merged_defaults,
                        master_params=master_params,
                    )
                except Exception as exc:
                    results.append(
                        {
                            "glyphName": glyph.name,
                            "masterId": mid,
                            "masterName": getattr(master, "name", ""),
                            "status": "error",
                            "reason": "exception",
                            "error": str(exc),
                        }
                    )
                    error_count += 1
                    continue

                if r.get("status") != "ok":
                    results.append(r)
                    if r.get("status") == "skipped":
                        skipped_count += 1
                    else:
                        error_count += 1
                    continue

                # Clamp suggestion (relative to current).
                cur = r.get("current") or {}
                sug = r.get("suggested") or {}
                clamped, clamp_warnings = spacing_engine.clamp_suggestion(current=cur, suggested=sug, clamp=effective_clamp)
                if clamp_warnings:
                    r.setdefault("warnings", []).extend(clamp_warnings)

                # Recompute width from measured shape if possible.
                try:
                    m = r.get("measured") or {}
                    width_shape = m.get("rFullExtreme") - m.get("lFullExtreme")

                    cl_l = _units_int(clamped.get("lsb"))
                    cl_r = _units_int(clamped.get("rsb"))
                    shape_int = _units_int(width_shape)

                    if shape_int is not None and cl_l is not None and cl_r is not None:
                        clamped["width"] = int(shape_int + cl_l + cl_r)

                    if sug.get("width") is not None and "tabular_width_preserved" in (r.get("warnings") or []):
                        clamped["width"] = _units_int(sug.get("width"))

                    clamped["lsb"] = cl_l
                    clamped["rsb"] = cl_r
                except Exception:
                    pass

                r["suggested"] = clamped
                try:
                    cur_w = _units_int(cur.get("width"))
                    cur_l = _units_int(cur.get("lsb"))
                    cur_r = _units_int(cur.get("rsb"))

                    cl_w = _units_int(clamped.get("width"))
                    cl_l = _units_int(clamped.get("lsb"))
                    cl_r = _units_int(clamped.get("rsb"))

                    r["delta"] = {
                        "width": (cl_w - cur_w) if (cl_w is not None and cur_w is not None) else None,
                        "lsb": (cl_l - cur_l) if (cl_l is not None and cur_l is not None) else None,
                        "rsb": (cl_r - cur_r) if (cl_r is not None and cur_r is not None) else None,
                    }
                except Exception:
                    pass

                results.append(r)
                ok_count += 1

                if dry_run or not confirm:
                    continue

                before_w = layer.width
                before_l = _get_left_sidebearing(layer)
                before_r = _get_right_sidebearing(layer)

                try:
                    new_lsb = clamped.get("lsb")
                    new_rsb = clamped.get("rsb")
                    if new_lsb is not None:
                        _set_sidebearing(layer, "leftSideBearing", "LSB", new_lsb)
                    if new_rsb is not None:
                        _set_sidebearing(layer, "rightSideBearing", "RSB", new_rsb)

                    # If tabular spacing is enabled, enforce the desired width explicitly.
                    if "tabular_width_preserved" in (r.get("warnings") or []) and clamped.get("width") is not None:
                        layer.width = int(round(float(clamped.get("width"))))

                    after_w = layer.width
                    after_l = _get_left_sidebearing(layer)
                    after_r = _get_right_sidebearing(layer)

                    applied.append(
                        {
                            "glyphName": glyph.name,
                            "masterId": mid,
                            "masterName": getattr(master, "name", ""),
                            "before": {"width": before_w, "lsb": before_l, "rsb": before_r},
                            "after": {"width": after_w, "lsb": after_l, "rsb": after_r},
                            "appliedSuggested": {"width": clamped.get("width"), "lsb": clamped.get("lsb"), "rsb": clamped.get("rsb")},
                        }
                    )
                    applied_count += 1
                except Exception as exc:
                    error_count += 1
                    results.append(
                        {
                            "glyphName": glyph.name,
                            "masterId": mid,
                            "masterName": getattr(master, "name", ""),
                            "status": "error",
                            "reason": "apply_failed",
                            "error": str(exc),
                        }
                    )

        return _safe_json(
            {
                "ok": True,
                "summary": {
                    "glyphCount": len(names),
                    "okCount": ok_count,
                    "skippedCount": skipped_count,
                    "errorCount": error_count,
                    "appliedCount": applied_count,
                    "dryRun": bool(dry_run),
                },
                "results": results,
                "applied": applied,
            }
        )
    except Exception as e:
        return _safe_json({"ok": False, "error": str(e)})


@mcp.tool()
async def set_spacing_params(
    font_index: int = 0,
    master_id: str = None,
    scope: str = "auto",
    params: dict = None,
    use_legacy_keys: bool = False,
    dry_run: bool = False,
) -> str:
    """Set spacing parameters as font/master Custom Parameters (no auto-save).

    Args:
        font_index: Index of the font (0-based). Defaults to 0.
        master_id: Master ID when targeting a specific master.
        scope: One of "auto" (default), "font", "master", or "all_masters".
        params: Dict with any of: area, depth, over, frequency. Values:
               - number -> set/update
               - null -> delete/unset
        use_legacy_keys: If true, use paramArea/paramDepth/paramOver/paramFreq.
                         Otherwise use cx.ap.spacingArea/Depth/Over/Freq.
        dry_run: If true, report changes without mutating.

    Returns:
        JSON payload with change list and read-back values.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return _safe_json(
                {
                    "ok": False,
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts)),
                }
            )

        font = Glyphs.fonts[font_index]
        params = params or {}
        if not isinstance(params, dict):
            return _safe_json({"ok": False, "error": "params must be an object/dict"})

        scope_norm = (scope or "auto").strip().lower()
        if scope_norm not in ("auto", "font", "master", "all_masters"):
            return _safe_json(
                {
                    "ok": False,
                    "error": "Invalid scope '{}'".format(scope),
                    "hint": "Use one of: auto, font, master, all_masters",
                }
            )

        # Resolve targets
        targets = []
        scope_applied = scope_norm
        if scope_norm == "auto":
            if master_id:
                scope_applied = "master"
            else:
                scope_applied = "font"

        if scope_applied == "font":
            targets = [("font", None, font)]
        elif scope_applied == "master":
            if not master_id:
                return _safe_json({"ok": False, "error": "master_id is required for scope=master"})
            wanted = str(master_id)
            found = None
            for m in font.masters:
                if getattr(m, "id", None) == wanted:
                    found = m
                    break
            if not found:
                return _safe_json({"ok": False, "error": "Master ID '{}' not found".format(master_id)})
            targets = [("master", wanted, found)]
        elif scope_applied == "all_masters":
            for m in font.masters:
                targets.append(("master", getattr(m, "id", None), m))

        key_map = spacing_engine.SPACING_PARAM_KEYS_PARAM_LEGACY if use_legacy_keys else spacing_engine.SPACING_PARAM_KEYS_CANONICAL

        changed = []
        effective_readback = []

        def _as_number(v):
            if v is None:
                return None
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str) and v.strip():
                try:
                    return float(v.strip())
                except Exception:
                    return None
            return None

        for kind, tid, obj in targets:
            target_label = {"type": kind}
            if kind == "master":
                target_label["masterId"] = tid
                target_label["masterName"] = getattr(obj, "name", None)

            # Apply changes field-by-field
            for field in spacing_engine.SPACING_PARAM_FIELDS:
                if field not in params:
                    continue
                key = key_map.get(field)
                if not key:
                    continue

                before = _custom_parameter(obj, key, None)
                requested = params.get(field)

                if requested is None:
                    action = "delete"
                    after = None
                    if not dry_run:
                        try:
                            del obj.customParameters[key]
                        except Exception:
                            pass
                else:
                    numeric = _as_number(requested)
                    if numeric is None:
                        return _safe_json(
                            {
                                "ok": False,
                                "error": "Param '{}' must be a number or null".format(field),
                                "value": requested,
                            }
                        )
                    action = "set"
                    after = numeric
                    if not dry_run:
                        obj.customParameters[key] = numeric

                changed.append(
                    {
                        "target": target_label,
                        "field": field,
                        "key": key,
                        "before": before,
                        "after": after,
                        "action": action,
                    }
                )

            # Readback (canonical + legacy, so callers can see what's present)
            rb = dict(target_label)
            rb["values"] = {}
            for field in spacing_engine.SPACING_PARAM_FIELDS:
                rb["values"][field] = {
                    "canonicalKey": spacing_engine.SPACING_PARAM_KEYS_CANONICAL.get(field),
                    "canonicalValue": _custom_parameter(obj, spacing_engine.SPACING_PARAM_KEYS_CANONICAL.get(field), None),
                    "gmcpLegacyKey": spacing_engine.SPACING_PARAM_KEYS_GMCP_LEGACY.get(field),
                    "gmcpLegacyValue": _custom_parameter(obj, spacing_engine.SPACING_PARAM_KEYS_GMCP_LEGACY.get(field), None),
                    "legacyKey": spacing_engine.SPACING_PARAM_KEYS_PARAM_LEGACY.get(field),
                    "legacyValue": _custom_parameter(obj, spacing_engine.SPACING_PARAM_KEYS_PARAM_LEGACY.get(field), None),
                }
            effective_readback.append(rb)

        return _safe_json(
            {
                "ok": True,
                "scopeApplied": scope_applied,
                "dryRun": bool(dry_run),
                "useLegacyKeys": bool(use_legacy_keys),
                "targets": [{"type": k, "masterId": tid} for k, tid, _obj in targets],
                "changed": changed,
                "effectiveReadback": effective_readback,
            }
        )
    except Exception as e:
        return _safe_json({"ok": False, "error": str(e)})
#+#+#+#+#+#+#+#+assistant to=functions.apply_patch>exit code: 0, success? Wait; we haven't provided patch content yet. We'll craft actual patch.
