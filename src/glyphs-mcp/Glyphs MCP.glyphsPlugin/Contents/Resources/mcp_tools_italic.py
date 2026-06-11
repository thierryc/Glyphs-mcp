# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import copy

from GlyphsApp import Glyphs, GSGlyph  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import (
    _clear_layer_paths,
    _coerce_numeric,
    _get_left_sidebearing,
    _get_right_sidebearing,
    _safe_json,
    _set_sidebearing,
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
    if font_index >= len(Glyphs.fonts) or font_index < 0:
        return None
    return Glyphs.fonts[font_index]


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


def _replace_paths(source_layer, target_layer):
    _clear_layer_paths(target_layer)
    for path in list(getattr(source_layer, "paths", []) or []):
        new_path = _copy_item(path)
        try:
            target_layer.paths.append(new_path)
        except Exception:
            if hasattr(target_layer, "addPath_"):
                target_layer.addPath_(new_path)


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
        try:
            target_layer.width = float(getattr(source_layer, "width"))
        except Exception:
            pass
        lsb = _get_left_sidebearing(source_layer)
        rsb = _get_right_sidebearing(source_layer)
        if lsb is not None:
            _set_sidebearing(target_layer, "leftSideBearing", "LSB", float(lsb))
        if rsb is not None:
            _set_sidebearing(target_layer, "rightSideBearing", "RSB", float(rsb))


def _ensure_target_glyph(source_glyph, target_font, glyph_name):
    target_glyph = _glyph_lookup(target_font, glyph_name)
    if target_glyph:
        return target_glyph, False
    new_glyph = GSGlyph(glyph_name)
    for attr in ("unicode", "category", "subCategory", "export", "leftKerningGroup", "rightKerningGroup"):
        try:
            setattr(new_glyph, attr, getattr(source_glyph, attr))
        except Exception:
            pass
    try:
        target_font.glyphs.append(new_glyph)
    except Exception:
        try:
            target_font.glyphs[glyph_name] = new_glyph
        except Exception:
            return None, False
    return new_glyph, True


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
    args = {
        "Slant": float(angle),
        "SlantCorrection": 1 if str(slant_mode) == "cursivy" else 0,
        "Origin": int(origin),
    }
    try:
        filter_obj.filter(layer, False, args)
        return {"ok": True, "args": args}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "args": args}


def _effective_slant_mode(slant_mode, stem_policy, stem_review):
    mode = str(slant_mode or "cursivy").strip().lower()
    if mode not in ("raw", "cursivy"):
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
):
    try:
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
        if not _master_by_id(source_font, source_master_id):
            return {"ok": False, "error": "Source master not found", "sourceMasterId": source_master_id}
        if not _master_by_id(target_font, target_master_id):
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
        effective_mode = _effective_slant_mode(slant_mode, stem_policy, stem_review)
        cursivy_blocked = effective_mode == "cursivy" and not stem_review.get("readyForCursivy")

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

            warnings = []
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

            status = "blocked" if blocked_reasons else "ok"
            if status == "ok":
                ok_count += 1
            else:
                blocked_count += 1

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

            results.append(
                {
                    "glyphName": name,
                    "status": status,
                    "blockedReasons": blocked_reasons,
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
                    },
                    "metrics": {
                        "source": source_metrics,
                        "target": current_metrics,
                    },
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
            "stemPolicy": stem_policy,
            "stemReview": stem_review,
            "sourceStemReview": source_stem_review,
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
            target_glyph, created = _ensure_target_glyph(source_glyph, target_font, name)
            if not target_glyph:
                applied.append({"glyphName": name, "status": "error", "reason": "target_glyph_create_failed"})
                error_count += 1
                continue
            if created:
                created_count += 1

            source_layer = _layer_for_glyph(source_glyph, source_master_id)
            target_layer = _layer_for_glyph(target_glyph, target_master_id)
            if not source_layer or not target_layer:
                applied.append({"glyphName": name, "status": "error", "reason": "source_or_target_layer_missing"})
                error_count += 1
                continue

            undo_open = False
            try:
                if hasattr(target_glyph, "beginUndo"):
                    target_glyph.beginUndo()
                    undo_open = True
                if backup:
                    _append_backup_layer(target_glyph, target_layer, target_master_id, backup_layer_name, angle)
                    backup_count += 1
                _copy_layer_data(source_layer, target_layer, options)
                transform = _apply_transformations_filter(
                    target_layer,
                    angle=angle,
                    slant_mode=review["effectiveSlantMode"],
                    origin=origin,
                )
                if not transform.get("ok"):
                    applied.append({"glyphName": name, "status": "error", "reason": "transform_failed", "transform": transform})
                    error_count += 1
                    continue
                applied.append({"glyphName": name, "status": "ok", "action": "applied", "transform": transform})
            except Exception as exc:
                applied.append({"glyphName": name, "status": "error", "reason": str(exc)})
                error_count += 1
            finally:
                if undo_open and hasattr(target_glyph, "endUndo"):
                    target_glyph.endUndo()

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
            dry_run=dry_run,
            confirm=confirm,
            backup=backup,
            backup_layer_name=backup_layer_name,
        )
    )
