# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import copy
import math

from GlyphsApp import Glyphs, GSGlyph  # type: ignore[import-not-found]

import italic_correction_engine
from mcp_runtime import mcp
from mcp_tool_helpers import (
    _append_font_glyph,
    _clear_layer_paths,
    _coerce_numeric,
    _component_transform_values,
    _get_left_sidebearing,
    _get_right_sidebearing,
    _new_glyph,
    _replace_layer_paths,
    _resolve_font_by_index,
    _safe_json,
    _set_layer_metrics,
)
from mcp_tools_stems import _review_master_stem_metrics_impl


DEFAULT_PROTECTED_GLYPHS = {
    "a",
    "e",
    "f",
    "g",
    "k",
    "v",
    "w",
    "x",
    "y",
    "ampersand",
    "question",
    "exclam",
    "parenleft",
    "parenright",
    "braceleft",
    "braceright",
    "bracketleft",
    "bracketright",
    "quoteleft",
    "quoteright",
    "quotedblleft",
    "quotedblright",
}


def _get_font(font_index):
    font, _fonts = _resolve_font_by_index(Glyphs, font_index)
    return font


def _master_by_id(font, master_id):
    if not master_id:
        return None
    for master in list(getattr(font, "masters", []) or []):
        if str(getattr(master, "id", "")) == str(master_id):
            return master
    return None


def _selected_master_id(font):
    master = getattr(font, "selectedFontMaster", None)
    if master:
        return getattr(master, "id", None)
    masters = list(getattr(font, "masters", []) or [])
    if masters:
        return getattr(masters[0], "id", None)
    return None


def _glyph_name(glyph):
    try:
        return str(glyph.name)
    except Exception:
        return None


def _glyphs_iter(font):
    glyphs = getattr(font, "glyphs", None)
    try:
        return list(glyphs or [])
    except Exception:
        return []


def _glyph_lookup(font, glyph_name):
    try:
        return font.glyphs[glyph_name]
    except Exception:
        return None


def _unique_names(names):
    out = []
    seen = set()
    for name in list(names or []):
        if name is None:
            continue
        value = str(name).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _resolve_glyph_names(source_font, scope, glyph_names):
    mode = str(scope or "selected_glyphs").strip().lower()
    if mode not in ("current_glyph", "selected_glyphs", "glyph_names", "all_glyphs"):
        mode = "selected_glyphs"

    if mode == "glyph_names":
        return _unique_names(glyph_names), mode

    if mode == "all_glyphs":
        return _unique_names([_glyph_name(g) for g in _glyphs_iter(source_font)]), mode

    selected_layers = list(getattr(source_font, "selectedLayers", []) or [])
    if mode == "current_glyph":
        if not selected_layers:
            return [], mode
        glyph = getattr(selected_layers[0], "parent", None)
        return _unique_names([_glyph_name(glyph)]), mode

    names = []
    for layer in selected_layers:
        glyph = getattr(layer, "parent", None)
        names.append(_glyph_name(glyph))
    return _unique_names(names), mode


def _copy_options(copy_options):
    opts = dict(copy_options or {})
    return {
        "paths": bool(opts.get("paths", True)),
        "components": bool(opts.get("components", True)),
        "anchors": bool(opts.get("anchors", True)),
        "metrics": bool(opts.get("metrics", True)),
    }


def _layer_for_glyph(glyph, master_id):
    try:
        return glyph.layers[str(master_id)]
    except Exception:
        return None


def _shape_signature(layer):
    if not layer:
        return None
    paths = []
    for path in list(getattr(layer, "paths", []) or []):
        nodes = list(getattr(path, "nodes", []) or [])
        paths.append([str(getattr(node, "type", "")) for node in nodes])
    components = []
    for component in list(getattr(layer, "components", []) or []):
        components.append(str(getattr(component, "componentName", getattr(component, "name", ""))))
    anchors = []
    for anchor in list(getattr(layer, "anchors", []) or []):
        anchors.append(str(getattr(anchor, "name", "")))
    return {"paths": paths, "components": components, "anchors": anchors}


def _compatible(source_layer, target_layer):
    return _shape_signature(source_layer) == _shape_signature(target_layer)


def _bounds(layer):
    b = getattr(layer, "bounds", None)
    if not b:
        return None
    origin = getattr(b, "origin", None)
    size = getattr(b, "size", None)
    ox = _coerce_numeric(getattr(origin, "x", None) if origin else None)
    oy = _coerce_numeric(getattr(origin, "y", None) if origin else None)
    sw = _coerce_numeric(getattr(size, "width", None) if size else None)
    sh = _coerce_numeric(getattr(size, "height", None) if size else None)
    if ox is None or oy is None or sw is None or sh is None:
        return None
    return {"minX": ox, "maxX": ox + sw, "minY": oy, "maxY": oy + sh, "width": sw, "height": sh}


def _copy_item(item):
    try:
        return item.copy()
    except Exception:
        pass
    try:
        return copy.deepcopy(item)
    except Exception:
        return item


def _signature_value(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    try:
        return tuple(_signature_value(item) for item in list(value))
    except Exception:
        pass
    point = []
    for attr in ("x", "y"):
        if hasattr(value, attr):
            point.append(_signature_value(getattr(value, attr)))
    if point:
        return tuple(point)
    return str(value)


def _component_signature_from_items(components):
    signature = []
    for component in list(components or []):
        signature.append(
            {
                "componentName": str(getattr(component, "componentName", getattr(component, "name", ""))),
                "componentMasterId": _signature_value(getattr(component, "componentMasterId", None)),
                "transform": _signature_value(getattr(component, "transform", None)),
                "position": _signature_value(getattr(component, "position", None)),
                "scale": _signature_value(getattr(component, "scale", None)),
                "rotation": _signature_value(getattr(component, "rotation", None)),
                "slant": _signature_value(getattr(component, "slant", None)),
            }
        )
    return signature


def _anchor_signature_from_items(anchors):
    signature = []
    for anchor in list(anchors or []):
        signature.append(
            {
                "name": str(getattr(anchor, "name", "")),
                "position": _signature_value(getattr(anchor, "position", None)),
            }
        )
    return signature


def _copied_collection(layer, attr_name):
    return [_copy_item(item) for item in list(getattr(layer, attr_name, []) or [])]


def _component_translation(component):
    position = getattr(component, "position", None)
    x_value = _coerce_numeric(getattr(position, "x", None) if position is not None else None)
    y_value = _coerce_numeric(getattr(position, "y", None) if position is not None else None)
    if x_value is not None and y_value is not None:
        return x_value, y_value
    transform = _component_transform_values(component)
    if len(transform) >= 6:
        return transform[4], transform[5]
    return None, None


def _set_component_x_translation(component, x_value):
    changed = False
    position = getattr(component, "position", None)
    if position is not None and hasattr(position, "x"):
        try:
            position.x = float(x_value)
            try:
                component.position = position
            except Exception:
                pass
            changed = True
        except Exception:
            pass

    transform = _component_transform_values(component)
    if len(transform) >= 6:
        transform[4] = float(x_value)
        try:
            component.transform = tuple(transform)
            changed = True
        except Exception:
            try:
                component.transform = transform
                changed = True
            except Exception:
                pass
    return changed


def _adjust_component_positions_for_slant(layer, angle):
    tangent = math.tan(math.radians(float(angle)))
    adjusted = 0
    skipped_baseline = 0
    unreadable = 0
    for component in list(getattr(layer, "components", []) or []):
        old_x, old_y = _component_translation(component)
        if old_x is None or old_y is None:
            unreadable += 1
            continue
        if old_y == 0:
            skipped_baseline += 1
            continue
        new_x = old_x + tangent * old_y
        if _set_component_x_translation(component, new_x):
            adjusted += 1
        else:
            unreadable += 1
    return {
        "angle": float(angle),
        "adjustedCount": adjusted,
        "baselineCount": skipped_baseline,
        "unreadableCount": unreadable,
    }


def _replace_paths(source_layer, target_layer):
    paths = [_copy_item(path) for path in list(getattr(source_layer, "paths", []) or [])]
    paths = [path for path in paths if path is not None]
    _replace_layer_paths(target_layer, paths)


def _set_collection(target, attr_name, values, setter_name=None):
    if setter_name and hasattr(target, setter_name):
        try:
            getattr(target, setter_name)(values)
            return True
        except Exception:
            pass
    try:
        setattr(target, attr_name, values)
        return True
    except Exception:
        pass
    if attr_name == "components" and hasattr(target, "shapes"):
        try:
            paths = [_copy_item(path) for path in list(getattr(target, "paths", []) or [])]
            target.shapes = paths + list(values or [])
            return True
        except Exception:
            pass
    try:
        collection = getattr(target, attr_name)
        try:
            collection.clear()
        except Exception:
            del collection[:]
        for value in values:
            collection.append(value)
        return True
    except Exception:
        return False


def _copy_layer_data(source_layer, target_layer, options):
    if options.get("paths"):
        _replace_paths(source_layer, target_layer)
    if options.get("components"):
        _set_collection(
            target_layer,
            "components",
            [_copy_item(component) for component in list(getattr(source_layer, "components", []) or [])],
            "setComponents_",
        )
    if options.get("anchors"):
        _set_collection(
            target_layer,
            "anchors",
            [_copy_item(anchor) for anchor in list(getattr(source_layer, "anchors", []) or [])],
        )
    if options.get("metrics"):
        lsb = _get_left_sidebearing(source_layer)
        rsb = _get_right_sidebearing(source_layer)
        try:
            width = float(getattr(source_layer, "width"))
        except Exception:
            width = None
        _set_layer_metrics(
            target_layer,
            width=width,
            left_sidebearing=float(lsb) if lsb is not None else None,
            right_sidebearing=float(rsb) if rsb is not None else None,
        )


def _ensure_target_glyph(source_glyph, target_font, glyph_name):
    target_glyph = _glyph_lookup(target_font, glyph_name)
    if target_glyph:
        return target_glyph, False
    new_glyph = _new_glyph(GSGlyph, glyph_name)
    for attr in ("unicode", "category", "subCategory", "export", "leftKerningGroup", "rightKerningGroup"):
        try:
            setattr(new_glyph, attr, getattr(source_glyph, attr))
        except Exception:
            pass
    verified_glyph = _append_font_glyph(target_font, new_glyph, glyph_name)
    if not verified_glyph:
        return None, False
    return verified_glyph, True


def _find_transformations_filter():
    for filter_obj in list(getattr(Glyphs, "filters", []) or []):
        class_name = filter_obj.__class__.__name__
        if class_name in ("GlyphsFilterTransformations", "GlyphsFilterTransform") or "Transformations" in class_name:
            return filter_obj
    return None


def _apply_transformations_filter(layer, angle, slant_mode, origin):
    filter_obj = _find_transformations_filter()
    if not filter_obj:
        return {"ok": False, "error": "Glyphs Transformations filter not found"}
    filter_method = getattr(filter_obj, "filter", None)
    if not callable(filter_method):
        return {
            "ok": False,
            "error": "Glyphs Transformations filter has no callable filter method",
            "filterClass": filter_obj.__class__.__name__,
        }
    args = {
        "Slant": float(angle),
        "SlantCorrection": 1 if str(slant_mode) == "cursivy" else 0,
        "Origin": int(origin),
    }
    try:
        filter_method(layer, False, args)
        return {"ok": True, "args": args, "backend": "glyphs_filter"}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "args": args}


def _origin_pivot_y(master, origin):
    origin_value = int(origin)
    cap_height = _coerce_numeric(getattr(master, "capHeight", None)) if master is not None else None
    x_height = _coerce_numeric(getattr(master, "xHeight", None)) if master is not None else None
    if origin_value == 0:
        return float(cap_height or 0.0)
    if origin_value == 1:
        return float(cap_height or 0.0) * 0.5
    if origin_value == 2:
        return float(x_height or 0.0)
    if origin_value == 3:
        return float(x_height or 0.0) * 0.5
    return 0.0


def _node_xy(node):
    position = getattr(node, "position", None)
    x_value = _coerce_numeric(getattr(position, "x", None) if position is not None else None)
    y_value = _coerce_numeric(getattr(position, "y", None) if position is not None else None)
    if x_value is None:
        x_value = _coerce_numeric(getattr(node, "x", None))
    if y_value is None:
        y_value = _coerce_numeric(getattr(node, "y", None))
    return float(x_value or 0.0), float(y_value or 0.0)


def _node_smooth(node):
    smooth = getattr(node, "smooth", None)
    if smooth is not None:
        return bool(smooth)
    return str(getattr(node, "connection", "") or "").strip().lower() == "smooth"


def _serialize_paths(layer):
    result = []
    for path in list(getattr(layer, "paths", []) or []):
        nodes = []
        for node in list(getattr(path, "nodes", []) or []):
            x_value, y_value = _node_xy(node)
            nodes.append(
                {
                    "x": x_value,
                    "y": y_value,
                    "type": str(getattr(node, "type", "")),
                    "smooth": _node_smooth(node),
                }
            )
        result.append({"closed": bool(getattr(path, "closed", True)), "nodes": nodes})
    return result


def _set_node_xy(node, x_value, y_value):
    position = getattr(node, "position", None)
    if position is not None and hasattr(position, "x") and hasattr(position, "y"):
        try:
            position.x = float(x_value)
            position.y = float(y_value)
            try:
                node.position = position
            except Exception:
                pass
            return True
        except Exception:
            pass
    try:
        node.position = (float(x_value), float(y_value))
        return True
    except Exception:
        pass
    changed = False
    for attr_name, value in (("x", x_value), ("y", y_value)):
        try:
            setattr(node, attr_name, float(value))
            changed = True
        except Exception:
            pass
    return changed


def _apply_serialized_paths(layer, serialized):
    paths = list(getattr(layer, "paths", []) or [])
    if len(paths) != len(serialized):
        return False
    for path_index, path in enumerate(paths):
        nodes = list(getattr(path, "nodes", []) or [])
        source_nodes = list(serialized[path_index].get("nodes") or [])
        if len(nodes) != len(source_nodes):
            return False
        for node_index, node in enumerate(nodes):
            record = source_nodes[node_index]
            if not _set_node_xy(node, record["x"], record["y"]):
                return False
    return True


def _shear_anchors(layer, angle, pivot_y):
    tangent = math.tan(math.radians(float(angle)))
    shifted = []
    for anchor in list(getattr(layer, "anchors", []) or []):
        position = getattr(anchor, "position", None)
        x_value = _coerce_numeric(getattr(position, "x", None) if position is not None else None)
        y_value = _coerce_numeric(getattr(position, "y", None) if position is not None else None)
        if x_value is None or y_value is None:
            shifted.append({"name": str(getattr(anchor, "name", "")), "status": "unreadable"})
            continue
        new_x = float(x_value) + tangent * (float(y_value) - float(pivot_y))
        if _set_node_xy(anchor, new_x, y_value):
            shifted.append(
                {
                    "name": str(getattr(anchor, "name", "")),
                    "beforeX": float(x_value),
                    "afterX": float(new_x),
                    "y": float(y_value),
                    "deltaX": float(new_x) - float(x_value),
                    "status": "shifted",
                }
            )
        else:
            shifted.append({"name": str(getattr(anchor, "name", "")), "status": "write_failed"})
    return {
        "pivotY": float(pivot_y),
        "shiftedCount": len([item for item in shifted if item.get("status") == "shifted"]),
        "anchors": shifted,
    }


def _component_master_mismatches(layer, target_master_id):
    mismatches = []
    for component in list(getattr(layer, "components", []) or []):
        component_master_id = getattr(component, "componentMasterId", None)
        if component_master_id in (None, "") or str(component_master_id) == str(target_master_id):
            continue
        mismatches.append(
            {
                "componentName": str(getattr(component, "componentName", getattr(component, "name", ""))),
                "componentMasterId": str(component_master_id),
                "targetMasterId": str(target_master_id),
            }
        )
    return mismatches


def _stem_values(stem_review, target_master_id):
    for master in list((stem_review or {}).get("masters") or []):
        if str(master.get("masterId")) != str(target_master_id):
            continue
        values = []
        for stem in list(master.get("stems") or []):
            value = _coerce_numeric(stem.get("value"))
            if value is not None and value > 0:
                values.append(float(value))
        return values
    return []


def _empty_stem_diagnostics():
    return {
        "detectedPairCount": 0,
        "acceptedPairCount": 0,
        "compensatedPairCount": 0,
        "compensatedPairs": [],
        "skippedPairs": [],
    }


def _fallback_cursivy_paths(source_paths, raw_paths, upm, stem_values):
    fallback = italic_correction_engine.compensate_stems(
        source_paths,
        raw_paths,
        strength=italic_correction_engine.CURSIVY_FALLBACK_STEM_STRENGTH,
        upm=upm,
        stem_values=stem_values,
    )
    return fallback["paths"], {
        "ok": True,
        "backend": "pure_stem_fallback",
        "warning": "glyphs_transformations_filter_unavailable",
        "stemStrength": italic_correction_engine.CURSIVY_FALLBACK_STEM_STRENGTH,
        "stemDiagnostics": fallback["diagnostics"],
    }


def _prepare_path_only_candidate(
    source_layer,
    target_layer,
    options,
    angle,
    slant_mode,
    origin,
    target_master=None,
    target_master_id=None,
    upm=1000.0,
    stem_values=None,
    curve_strength=0.75,
    stem_compensation=1.0,
):
    candidate = _copy_item(target_layer) if target_layer is not None else _copy_item(source_layer)
    if candidate is None:
        return {"ok": False, "reason": "candidate_layer_create_failed"}

    if target_layer is None:
        if not options.get("paths"):
            _clear_layer_paths(candidate)
        if not options.get("components"):
            _set_collection(candidate, "components", [], "setComponents_")
        if not options.get("anchors"):
            _set_collection(candidate, "anchors", [])

    _copy_layer_data(source_layer, candidate, options)
    component_positioning = (
        _adjust_component_positions_for_slant(candidate, angle)
        if options.get("components")
        else {"angle": float(angle), "adjustedCount": 0, "baselineCount": 0, "unreadableCount": 0}
    )
    preserved_components = _copied_collection(candidate, "components")
    preserved_component_signature = _component_signature_from_items(preserved_components)
    preserved_anchors = _copied_collection(candidate, "anchors")
    preserved_anchor_signature = _anchor_signature_from_items(preserved_anchors)
    component_mismatches = _component_master_mismatches(candidate, target_master_id)
    mode = str(slant_mode)
    pivot_y = _origin_pivot_y(target_master, origin)

    if mode == "balanced" and component_mismatches:
        return {
            "ok": False,
            "reason": "component_master_mismatch",
            "componentWarnings": component_mismatches,
            "componentTransformPolicy": "copy_components_preserve_unskewed",
        }

    if not options.get("paths"):
        anchor_positioning = (
            _shear_anchors(candidate, angle, pivot_y)
            if options.get("anchors") and mode == "balanced"
            else {"pivotY": pivot_y, "shiftedCount": 0, "anchors": []}
        )
        return {
            "ok": True,
            "candidateLayer": candidate,
            "transform": {"ok": True, "skipped": True, "reason": "copy_options_paths_false"},
            "componentsPreserved": True,
            "anchorsPreserved": True,
            "componentPositioning": component_positioning,
            "componentTransformPolicy": "copy_components_preserve_unskewed",
            "componentWarnings": component_mismatches,
            "anchorPositioning": anchor_positioning,
            "topologyPreserved": True,
            "stemDiagnostics": _empty_stem_diagnostics(),
            "curveStrength": float(curve_strength) if mode == "balanced" else (0.0 if mode == "raw" else 1.0),
            "stemCompensation": float(stem_compensation) if mode == "balanced" else 0.0,
            "pivotY": pivot_y,
        }

    source_paths = _serialize_paths(source_layer)
    raw_paths = italic_correction_engine.shear_paths(source_paths, angle=angle, pivot_y=pivot_y)

    cursivy_paths = None
    cursivy_transform = None
    if mode != "raw":
        filter_candidate = _copy_item(candidate)
        if filter_candidate is not None:
            if not _set_collection(filter_candidate, "components", [], "setComponents_"):
                filter_candidate = None
            elif not _set_collection(filter_candidate, "anchors", []):
                filter_candidate = None
        if filter_candidate is not None:
            filter_transform = _apply_transformations_filter(
                filter_candidate,
                angle=angle,
                slant_mode="cursivy",
                origin=origin,
            )
            if filter_transform.get("ok"):
                cursivy_paths = _serialize_paths(filter_candidate)
                cursivy_transform = filter_transform
        if cursivy_paths is None:
            cursivy_paths, cursivy_transform = _fallback_cursivy_paths(
                source_paths,
                raw_paths,
                upm=upm,
                stem_values=stem_values,
            )

        if not italic_correction_engine.topology_matches(raw_paths, cursivy_paths):
            return {
                "ok": False,
                "reason": "raw_cursivy_topology_mismatch",
                "transform": cursivy_transform,
                "componentTransformPolicy": "copy_components_preserve_unskewed",
            }

    stem_diagnostics = _empty_stem_diagnostics()
    if mode == "raw":
        final_paths = raw_paths
        transform = {"ok": True, "backend": "pure_affine", "angle": float(angle), "origin": int(origin)}
    elif mode == "cursivy":
        final_paths = cursivy_paths
        transform = cursivy_transform
    else:
        blended_paths = italic_correction_engine.interpolate_paths(raw_paths, cursivy_paths, curve_strength)
        compensated = italic_correction_engine.compensate_stems(
            source_paths,
            blended_paths,
            strength=stem_compensation,
            upm=upm,
            stem_values=stem_values,
        )
        final_paths = compensated["paths"]
        stem_diagnostics = compensated["diagnostics"]
        transform = {
            "ok": True,
            "backend": "balanced",
            "rawBackend": "pure_affine",
            "cursivyBackend": cursivy_transform.get("backend"),
            "cursivyWarning": cursivy_transform.get("warning"),
            "angle": float(angle),
            "origin": int(origin),
        }

    if not _apply_serialized_paths(candidate, final_paths):
        return {"ok": False, "reason": "candidate_path_write_failed", "transform": transform}
    if not _set_collection(
        candidate,
        "components",
        [_copy_item(component) for component in preserved_components],
        "setComponents_",
    ):
        return {"ok": False, "reason": "component_restore_failed", "transform": transform}
    if not _set_collection(candidate, "anchors", [_copy_item(anchor) for anchor in preserved_anchors]):
        return {"ok": False, "reason": "anchor_restore_failed", "transform": transform}

    anchor_positioning = (
        _shear_anchors(candidate, angle, pivot_y)
        if options.get("anchors") and mode == "balanced"
        else {"pivotY": pivot_y, "shiftedCount": 0, "anchors": []}
    )
    restored_component_signature = _component_signature_from_items(list(getattr(candidate, "components", []) or []))
    if restored_component_signature != preserved_component_signature:
        return {
            "ok": False,
            "reason": "component_preservation_failed",
            "transform": transform,
            "before": preserved_component_signature,
            "after": restored_component_signature,
        }
    restored_anchor_signature = _anchor_signature_from_items(list(getattr(candidate, "anchors", []) or []))
    if mode != "balanced" and restored_anchor_signature != preserved_anchor_signature:
        return {
            "ok": False,
            "reason": "anchor_preservation_failed",
            "transform": transform,
            "before": preserved_anchor_signature,
            "after": restored_anchor_signature,
        }

    return {
        "ok": True,
        "candidateLayer": candidate,
        "transform": transform,
        "componentsPreserved": True,
        "anchorsPreserved": True,
        "componentPositioning": component_positioning,
        "componentTransformPolicy": "copy_components_preserve_unskewed",
        "componentWarnings": component_mismatches,
        "anchorPositioning": anchor_positioning,
        "topologyPreserved": italic_correction_engine.topology_matches(source_paths, final_paths),
        "stemDiagnostics": stem_diagnostics,
        "curveStrength": float(curve_strength) if mode == "balanced" else (0.0 if mode == "raw" else 1.0),
        "stemCompensation": float(stem_compensation) if mode == "balanced" else 0.0,
        "pivotY": pivot_y,
    }


def _effective_slant_mode(slant_mode, stem_policy, stem_review):
    mode = str(slant_mode or "cursivy").strip().lower()
    if mode not in ("raw", "cursivy", "balanced"):
        mode = "cursivy"
    if mode == "cursivy" and not stem_review.get("readyForCursivy") and stem_policy == "skip_for_raw":
        return "raw"
    return mode


def _stem_review_for_policy(target_font_index, target_master_id, stem_policy):
    include_measurements = stem_policy == "measure_and_report"
    return _review_master_stem_metrics_impl(
        font_index=target_font_index,
        master_ids=[target_master_id],
        include_measurements=include_measurements,
    )


def _review_italic_first_pass_impl(
    font_index=0,
    source_font_index=None,
    target_font_index=None,
    source_master_id=None,
    target_master_id=None,
    scope="selected_glyphs",
    glyph_names=None,
    angle=12.0,
    slant_mode="cursivy",
    stem_policy="require_existing",
    compatibility_mode="preserve_if_possible",
    copy_options=None,
    protected_glyphs=None,
    skip_glyphs=None,
    origin=3,
    curve_strength=0.75,
    stem_compensation=1.0,
):
    try:
        curve_strength = italic_correction_engine.validate_unit_interval(curve_strength, "curve_strength")
        stem_compensation = italic_correction_engine.validate_unit_interval(
            stem_compensation,
            "stem_compensation",
        )
        source_index = font_index if source_font_index is None else source_font_index
        target_index = source_index if target_font_index is None else target_font_index
        source_font = _get_font(source_index)
        target_font = _get_font(target_index)
        if not source_font:
            return {"ok": False, "error": "Source font index out of range", "sourceFontIndex": source_index}
        if not target_font:
            return {"ok": False, "error": "Target font index out of range", "targetFontIndex": target_index}

        source_master_id = source_master_id or _selected_master_id(source_font)
        target_master_id = target_master_id or _selected_master_id(target_font)
        source_master = _master_by_id(source_font, source_master_id)
        target_master = _master_by_id(target_font, target_master_id)
        if not source_master:
            return {"ok": False, "error": "Source master not found", "sourceMasterId": source_master_id}
        if not target_master:
            return {"ok": False, "error": "Target master not found", "targetMasterId": target_master_id}

        names, resolved_scope = _resolve_glyph_names(source_font, scope, glyph_names)
        if not names:
            return {"ok": False, "error": "No glyphs resolved for scope", "scope": resolved_scope}

        options = _copy_options(copy_options)
        compatibility_mode = str(compatibility_mode or "preserve_if_possible").strip().lower()
        if compatibility_mode not in ("ignore", "preserve_if_possible", "strict"):
            compatibility_mode = "preserve_if_possible"

        stem_policy = str(stem_policy or "require_existing").strip().lower()
        if stem_policy not in ("require_existing", "copy_from_source", "measure_and_report", "skip_for_raw"):
            stem_policy = "require_existing"

        stem_review = _stem_review_for_policy(target_index, target_master_id, stem_policy)
        source_stem_review = None
        if stem_policy == "copy_from_source":
            source_stem_review = _review_master_stem_metrics_impl(
                font_index=source_index,
                master_ids=[source_master_id],
                include_measurements=False,
            )
        policy_warnings = []
        if (
            stem_policy == "copy_from_source"
            and source_stem_review
            and source_stem_review.get("readyForCursivy")
            and not stem_review.get("readyForCursivy")
        ):
            policy_warnings.append("source_stems_available_but_not_applied")
        effective_mode = _effective_slant_mode(slant_mode, stem_policy, stem_review)
        cursivy_blocked = effective_mode == "cursivy" and not stem_review.get("readyForCursivy")
        target_stem_values = _stem_values(stem_review, target_master_id)

        protected = set(protected_glyphs or DEFAULT_PROTECTED_GLYPHS)
        explicit_skip = set(skip_glyphs or [])

        results = []
        ok_count = 0
        blocked_count = 0
        skipped_count = 0
        error_count = 0

        for name in names:
            if name in explicit_skip:
                results.append({"glyphName": name, "status": "skipped", "reason": "explicit_skip"})
                skipped_count += 1
                continue

            source_glyph = _glyph_lookup(source_font, name)
            target_glyph = _glyph_lookup(target_font, name)
            if not source_glyph:
                results.append({"glyphName": name, "status": "error", "reason": "source_glyph_not_found"})
                error_count += 1
                continue
            source_layer = _layer_for_glyph(source_glyph, source_master_id)
            target_layer = _layer_for_glyph(target_glyph, target_master_id) if target_glyph else None
            if not source_layer:
                results.append({"glyphName": name, "status": "error", "reason": "source_layer_missing"})
                error_count += 1
                continue

            warnings = list(policy_warnings)
            if name in protected:
                warnings.append("protected_glyph_needs_manual_review")
            if target_glyph is None:
                warnings.append("target_glyph_will_be_created")

            compatible_before = _compatible(source_layer, target_layer) if target_layer else False
            compatible_after = bool(options.get("paths") and options.get("components") and options.get("anchors"))
            if compatibility_mode == "ignore":
                compatibility_status = "not_checked"
            elif compatibility_mode == "strict" and target_layer and not compatible_before:
                compatibility_status = "blocked"
            else:
                compatibility_status = "compatible_after_copy" if compatible_after else "may_diverge"

            blocked_reasons = []
            if cursivy_blocked:
                blocked_reasons.append("cursivy_requires_target_master_stems")
            if compatibility_status == "blocked":
                blocked_reasons.append("strict_compatibility_would_replace_incompatible_layer")

            candidate = None
            status = "blocked" if blocked_reasons else "ok"
            if status == "ok":
                candidate = _prepare_path_only_candidate(
                    source_layer,
                    target_layer,
                    options,
                    angle=angle,
                    slant_mode=effective_mode,
                    origin=origin,
                    target_master=target_master,
                    target_master_id=target_master_id,
                    upm=float(getattr(target_font, "upm", 1000) or 1000),
                    stem_values=target_stem_values,
                    curve_strength=curve_strength,
                    stem_compensation=stem_compensation,
                )
                if not candidate.get("ok"):
                    reason = candidate.get("reason", "candidate_prepare_failed")
                    if reason == "component_master_mismatch":
                        blocked_reasons.append(reason)
                        status = "blocked"
                    else:
                        status = "error"
                elif candidate.get("transform", {}).get("warning"):
                    warnings.append(candidate["transform"]["warning"])

            if status == "ok":
                ok_count += 1
            elif status == "blocked":
                blocked_count += 1
            else:
                error_count += 1

            current_metrics = None
            if target_layer:
                current_metrics = {
                    "width": getattr(target_layer, "width", None),
                    "leftSideBearing": _get_left_sidebearing(target_layer),
                    "rightSideBearing": _get_right_sidebearing(target_layer),
                }
            source_metrics = {
                "width": getattr(source_layer, "width", None),
                "leftSideBearing": _get_left_sidebearing(source_layer),
                "rightSideBearing": _get_right_sidebearing(source_layer),
            }
            candidate_layer = candidate.get("candidateLayer") if candidate and candidate.get("ok") else None
            candidate_metrics = None
            if candidate_layer is not None:
                candidate_metrics = {
                    "width": getattr(candidate_layer, "width", None),
                    "leftSideBearing": _get_left_sidebearing(candidate_layer),
                    "rightSideBearing": _get_right_sidebearing(candidate_layer),
                }

            results.append(
                {
                    "glyphName": name,
                    "status": status,
                    "blockedReasons": blocked_reasons,
                    "reason": candidate.get("reason") if candidate and not candidate.get("ok") else None,
                    "warnings": warnings,
                    "compatibility": {
                        "mode": compatibility_mode,
                        "before": compatible_before,
                        "after": compatible_after,
                        "status": compatibility_status,
                    },
                    "bounds": {
                        "source": _bounds(source_layer),
                        "target": _bounds(target_layer),
                        "candidate": _bounds(candidate_layer),
                    },
                    "metrics": {
                        "source": source_metrics,
                        "target": current_metrics,
                        "candidate": candidate_metrics,
                    },
                    "transform": candidate.get("transform") if candidate else None,
                    "topologyPreserved": candidate.get("topologyPreserved") if candidate else None,
                    "curveStrength": candidate.get("curveStrength") if candidate else None,
                    "stemCompensation": candidate.get("stemCompensation") if candidate else None,
                    "pivotY": candidate.get("pivotY") if candidate else _origin_pivot_y(target_master, origin),
                    "stemDiagnostics": candidate.get("stemDiagnostics") if candidate else _empty_stem_diagnostics(),
                    "anchorPositioning": candidate.get("anchorPositioning") if candidate else None,
                    "componentPositioning": candidate.get("componentPositioning") if candidate else None,
                    "componentWarnings": candidate.get("componentWarnings", []) if candidate else [],
                }
            )

        ready = blocked_count == 0 and error_count == 0
        return {
            "ok": True,
            "readyToApply": ready,
            "fontIndex": font_index,
            "sourceFontIndex": source_index,
            "targetFontIndex": target_index,
            "sourceMasterId": str(source_master_id),
            "targetMasterId": str(target_master_id),
            "scope": resolved_scope,
            "angle": float(angle),
            "origin": int(origin),
            "slantMode": str(slant_mode or "cursivy"),
            "effectiveSlantMode": effective_mode,
            "curveStrength": curve_strength,
            "stemCompensation": stem_compensation,
            "stemPolicy": stem_policy,
            "stemReview": stem_review,
            "sourceStemReview": source_stem_review,
            "policyWarnings": policy_warnings,
            "copyOptions": options,
            "summary": {
                "glyphCount": len(names),
                "okCount": ok_count,
                "blockedCount": blocked_count,
                "skippedCount": skipped_count,
                "errorCount": error_count,
            },
            "results": results,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _append_backup_layer(glyph, layer, target_master_id, backup_layer_name, angle):
    backup = layer.copy()
    backup.name = "{} angle={}".format(backup_layer_name, float(angle))
    try:
        backup.associatedMasterId = str(target_master_id)
    except Exception:
        pass
    glyph.layers.append(backup)


def _apply_italic_first_pass_impl(
    font_index=0,
    source_font_index=None,
    target_font_index=None,
    source_master_id=None,
    target_master_id=None,
    scope="selected_glyphs",
    glyph_names=None,
    angle=12.0,
    slant_mode="cursivy",
    stem_policy="require_existing",
    compatibility_mode="preserve_if_possible",
    copy_options=None,
    protected_glyphs=None,
    skip_glyphs=None,
    origin=3,
    curve_strength=0.75,
    stem_compensation=1.0,
    dry_run=False,
    confirm=False,
    backup=True,
    backup_layer_name="GMCP Backup: Italic First Pass",
):
    try:
        review = _review_italic_first_pass_impl(
            font_index=font_index,
            source_font_index=source_font_index,
            target_font_index=target_font_index,
            source_master_id=source_master_id,
            target_master_id=target_master_id,
            scope=scope,
            glyph_names=glyph_names,
            angle=angle,
            slant_mode=slant_mode,
            stem_policy=stem_policy,
            compatibility_mode=compatibility_mode,
            copy_options=copy_options,
            protected_glyphs=protected_glyphs,
            skip_glyphs=skip_glyphs,
            origin=origin,
            curve_strength=curve_strength,
            stem_compensation=stem_compensation,
        )
        if not review.get("ok"):
            return review
        if dry_run:
            review["dryRun"] = True
            return review
        if not confirm:
            return {"ok": False, "error": "Use dry_run=true first or confirm=true to mutate", "review": review}
        if not review.get("readyToApply"):
            return {"ok": False, "error": "Italic first pass is blocked; review results before applying", "review": review}

        source_font = _get_font(review["sourceFontIndex"])
        target_font = _get_font(review["targetFontIndex"])
        source_master_id = review["sourceMasterId"]
        target_master_id = review["targetMasterId"]
        options = review["copyOptions"]
        target_master = _master_by_id(target_font, target_master_id)
        target_stem_values = _stem_values(review.get("stemReview"), target_master_id)

        applied = []
        backup_count = 0
        created_count = 0
        error_count = 0

        for result in review.get("results", []):
            name = result.get("glyphName")
            if result.get("status") != "ok":
                applied.append({"glyphName": name, "status": result.get("status"), "reason": "not_ok_in_review"})
                continue

            source_glyph = _glyph_lookup(source_font, name)
            target_glyph = _glyph_lookup(target_font, name)
            source_layer = _layer_for_glyph(source_glyph, source_master_id)
            target_layer = _layer_for_glyph(target_glyph, target_master_id) if target_glyph else None
            if not source_layer:
                applied.append({"glyphName": name, "status": "error", "reason": "source_or_target_layer_missing"})
                error_count += 1
                continue

            candidate = _prepare_path_only_candidate(
                source_layer,
                target_layer,
                options,
                angle=angle,
                slant_mode=review["effectiveSlantMode"],
                origin=origin,
                target_master=target_master,
                target_master_id=target_master_id,
                upm=float(getattr(target_font, "upm", 1000) or 1000),
                stem_values=target_stem_values,
                curve_strength=review.get("curveStrength", curve_strength),
                stem_compensation=review.get("stemCompensation", stem_compensation),
            )
            if not candidate.get("ok"):
                applied.append(
                    {
                        "glyphName": name,
                        "status": "error",
                        "reason": candidate.get("reason", "candidate_prepare_failed"),
                        "transform": candidate.get("transform"),
                        "componentTransformPolicy": candidate.get(
                            "componentTransformPolicy",
                            "copy_components_preserve_unskewed",
                        ),
                    }
                )
                error_count += 1
                continue

            if not target_glyph:
                target_glyph, created = _ensure_target_glyph(source_glyph, target_font, name)
                if not target_glyph:
                    applied.append({"glyphName": name, "status": "error", "reason": "target_glyph_create_failed"})
                    error_count += 1
                    continue
                if created:
                    created_count += 1
                target_layer = _layer_for_glyph(target_glyph, target_master_id)

            if not target_layer:
                applied.append({"glyphName": name, "status": "error", "reason": "source_or_target_layer_missing"})
                error_count += 1
                continue

            changes_open = False
            try:
                if hasattr(target_layer, "beginChanges"):
                    target_layer.beginChanges()
                    changes_open = True
                if backup:
                    _append_backup_layer(target_glyph, target_layer, target_master_id, backup_layer_name, angle)
                    backup_count += 1
                _copy_layer_data(candidate["candidateLayer"], target_layer, options)
                applied.append(
                    {
                        "glyphName": name,
                        "status": "ok",
                        "action": "applied",
                        "transform": candidate["transform"],
                        "componentsPreserved": candidate["componentsPreserved"],
                        "componentPositioning": candidate["componentPositioning"],
                        "componentTransformPolicy": candidate["componentTransformPolicy"],
                        "componentWarnings": candidate.get("componentWarnings", []),
                        "anchorPositioning": candidate.get("anchorPositioning"),
                        "topologyPreserved": candidate.get("topologyPreserved"),
                        "curveStrength": candidate.get("curveStrength"),
                        "stemCompensation": candidate.get("stemCompensation"),
                        "stemDiagnostics": candidate.get("stemDiagnostics"),
                        "pivotY": candidate.get("pivotY"),
                    }
                )
            except Exception as exc:
                applied.append({"glyphName": name, "status": "error", "reason": str(exc)})
                error_count += 1
            finally:
                if changes_open and hasattr(target_layer, "endChanges"):
                    target_layer.endChanges()

        return {
            "ok": error_count == 0,
            "dryRun": False,
            "summary": {
                "glyphCount": len(applied),
                "appliedCount": len([item for item in applied if item.get("status") == "ok"]),
                "errorCount": error_count,
                "backupCount": backup_count,
                "createdGlyphCount": created_count,
            },
            "review": review,
            "results": applied,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
async def review_italic_first_pass(
    font_index: int = 0,
    source_font_index: int = None,
    target_font_index: int = None,
    source_master_id: str = None,
    target_master_id: str = None,
    scope: str = "selected_glyphs",
    glyph_names: list = None,
    angle: float = 12.0,
    slant_mode: str = "cursivy",
    stem_policy: str = "require_existing",
    compatibility_mode: str = "preserve_if_possible",
    copy_options: dict = None,
    protected_glyphs: list = None,
    skip_glyphs: list = None,
    origin: int = 3,
    curve_strength: float = 0.75,
    stem_compensation: float = 1.0,
) -> str:
    """Preview a roman-to-italic first-pass copy and slant workflow.

    The angle uses Glyphs' source/Transformations convention: positive values
    lean Latin outlines to the right. Default +12 maps to about -12 in exported
    OpenType/UFO post.italicAngle or slnt metadata.
    """
    return _safe_json(
        _review_italic_first_pass_impl(
            font_index=font_index,
            source_font_index=source_font_index,
            target_font_index=target_font_index,
            source_master_id=source_master_id,
            target_master_id=target_master_id,
            scope=scope,
            glyph_names=glyph_names,
            angle=angle,
            slant_mode=slant_mode,
            stem_policy=stem_policy,
            compatibility_mode=compatibility_mode,
            copy_options=copy_options,
            protected_glyphs=protected_glyphs,
            skip_glyphs=skip_glyphs,
            origin=origin,
            curve_strength=curve_strength,
            stem_compensation=stem_compensation,
        )
    )


@mcp.tool()
async def apply_italic_first_pass(
    font_index: int = 0,
    source_font_index: int = None,
    target_font_index: int = None,
    source_master_id: str = None,
    target_master_id: str = None,
    scope: str = "selected_glyphs",
    glyph_names: list = None,
    angle: float = 12.0,
    slant_mode: str = "cursivy",
    stem_policy: str = "require_existing",
    compatibility_mode: str = "preserve_if_possible",
    copy_options: dict = None,
    protected_glyphs: list = None,
    skip_glyphs: list = None,
    origin: int = 3,
    curve_strength: float = 0.75,
    stem_compensation: float = 1.0,
    dry_run: bool = False,
    confirm: bool = False,
    backup: bool = True,
    backup_layer_name: str = "GMCP Backup: Italic First Pass",
) -> str:
    """Apply a guarded roman-to-italic first pass after dry-run/confirmation.

    The angle uses Glyphs' source/Transformations convention: positive values
    lean Latin outlines to the right. Default +12 maps to about -12 in exported
    OpenType/UFO post.italicAngle or slnt metadata.
    """
    return _safe_json(
        _apply_italic_first_pass_impl(
            font_index=font_index,
            source_font_index=source_font_index,
            target_font_index=target_font_index,
            source_master_id=source_master_id,
            target_master_id=target_master_id,
            scope=scope,
            glyph_names=glyph_names,
            angle=angle,
            slant_mode=slant_mode,
            stem_policy=stem_policy,
            compatibility_mode=compatibility_mode,
            copy_options=copy_options,
            protected_glyphs=protected_glyphs,
            skip_glyphs=skip_glyphs,
            origin=origin,
            curve_strength=curve_strength,
            stem_compensation=stem_compensation,
            dry_run=dry_run,
            confirm=confirm,
            backup=backup,
            backup_layer_name=backup_layer_name,
        )
    )
