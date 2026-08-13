# encoding: utf-8

"""Glyphs adapter for fixed horizontal IconGrid centering."""

from __future__ import annotations

import copy

try:
    from Foundation import NSNotificationCenter  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - normal outside Glyphs
    NSNotificationCenter = None

try:
    from GlyphsApp import Glyphs  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - normal outside Glyphs
    Glyphs = None

from glyphs_litsquare_adapter import (
    _mapping_delete,
    _mapping_set,
    _mapping_value,
    _register_undo_handler,
    _sequence,
    _undo_group,
    resolve_context,
)
from icon_grid_centering import (
    CHANGED_NOTIFICATION,
    ROOT_KEY,
    IconGridCenteringError,
    center_candidates,
    propose_reset,
    propose_set,
    resolve_center,
    state_fingerprint,
    validate_policy_root,
)
from litsquare_metadata import json_safe, to_plain
from mcp_tool_helpers import _run_on_main_thread


def _plain_root(layer):
    present, raw = _mapping_value(getattr(layer, "userData", None), ROOT_KEY)
    if not present:
        return False, None
    errors = []
    value = to_plain(raw, path="$", errors=errors)
    if errors:
        return True, raw
    return True, value


def _write_root(layer, present, value):
    if present:
        _mapping_set(layer, "userData", ROOT_KEY, copy.deepcopy(value))
    else:
        _mapping_delete(layer, "userData", ROOT_KEY)
    read_present, read_value = _plain_root(layer)
    if read_present != bool(present):
        raise RuntimeError("IconGrid centering user data did not survive readback.")
    if present and read_value != value:
        raise RuntimeError("IconGrid centering user data readback did not match the write.")
    return validate_policy_root(read_value, read_present)


def _maybe_call(value):
    return value() if callable(value) else value


def _bounds(shape):
    bounds = _maybe_call(getattr(shape, "bounds", None))
    if bounds is None:
        return None
    origin = getattr(bounds, "origin", None)
    size = getattr(bounds, "size", None)
    try:
        return {
            "x": float(getattr(origin, "x")),
            "y": float(getattr(origin, "y")),
            "width": float(getattr(size, "width")),
            "height": float(getattr(size, "height")),
        }
    except Exception:
        return None


def _content_entries(context):
    layer = context["layer"]
    shapes = _sequence(getattr(layer, "shapes", None))
    if shapes:
        return [
            {"kind": "shape", "shapeIndex": index, "bounds": _bounds(shape)}
            for index, shape in enumerate(shapes)
        ]
    entries = [
        {"kind": "path", "shapeIndex": index, "bounds": _bounds(path)}
        for index, path in enumerate(_sequence(getattr(layer, "paths", None)))
    ]
    entries.extend(
        {
            "kind": "component",
            "shapeIndex": index,
            "bounds": _bounds(component),
        }
        for index, component in enumerate(
            _sequence(getattr(layer, "components", None))
        )
    )
    return entries


def _fingerprint_payload(context, root_present, root_value):
    return {
        "target": {
            "fontIndex": context["target"].get("fontIndex"),
            "glyphName": context["target"].get("glyphName"),
            "layerId": context["target"].get("layerId"),
        },
        "rootPresent": bool(root_present),
        "root": json_safe(root_value),
    }


def _snapshot_from_context(context):
    layer = context["layer"]
    if context["glyph"] is None or layer is None:
        return {
            "ok": False,
            "target": context["target"],
            "summary": {"state": "no_context"},
            "error": {
                "code": "icon_grid_context_required",
                "message": "Exactly one glyph layer is required.",
                "recoverable": True,
            },
            "fontSaved": False,
            "redrawn": False,
        }
    root_present, root_value = _plain_root(layer)
    policy = validate_policy_root(root_value, root_present)
    entries = _content_entries(context)
    center = resolve_center(getattr(layer, "width", None), policy)
    candidates = center_candidates(getattr(layer, "width", None), entries)
    fingerprint = state_fingerprint(
        _fingerprint_payload(context, root_present, root_value)
    )
    return {
        "ok": True,
        "target": context["target"],
        "summary": {
            "state": center["state"],
            "fallback": center["fallback"],
        },
        "policy": json_safe(policy),
        "center": json_safe(center),
        "candidates": json_safe(candidates),
        "stateFingerprint": fingerprint,
        "fontSaved": False,
        "redrawn": False,
    }


def icon_grid_snapshot(
    font_index=0,
    glyph_name=None,
    layer_id=None,
    app=None,
    font=None,
):
    def transaction():
        context = resolve_context(
            font_index,
            glyph_name,
            layer_id,
            app=app,
            font=font,
        )
        return _snapshot_from_context(context)

    return _run_on_main_thread(transaction)


def _post_change(target):
    if NSNotificationCenter is None:
        return
    try:
        NSNotificationCenter.defaultCenter().postNotificationName_object_userInfo_(
            CHANGED_NOTIFICATION,
            None,
            target,
        )
    except Exception:
        pass


def _redraw(app):
    owner = app or Glyphs
    method = getattr(owner, "redraw", None)
    if callable(method):
        method()
        return True
    return False


def _register_inverse(manager, font, layer, present, value, app):
    restore_present = bool(present)
    restore_value = copy.deepcopy(value)

    def restore(target):
        current_present, current_value = _plain_root(target)
        _register_inverse(
            manager,
            font,
            target,
            current_present,
            current_value,
            app,
        )
        _write_root(target, restore_present, restore_value)
        _post_change({"scope": "layer", "undo": True})
        _redraw(app)

    return _register_undo_handler(manager, layer, restore)


def _mutation(
    action,
    expected_state_fingerprint,
    font_index=0,
    glyph_name=None,
    layer_id=None,
    center_x=None,
    dry_run=True,
    confirm=False,
    app=None,
    font=None,
):
    if type(dry_run) is not bool or type(confirm) is not bool or dry_run == confirm:
        raise ValueError("Set exactly one of dry_run=true or confirm=true.")
    if not isinstance(expected_state_fingerprint, str) or not expected_state_fingerprint:
        raise ValueError("expected_state_fingerprint is required; read the layer first.")

    def transaction():
        context = resolve_context(
            font_index,
            glyph_name,
            layer_id,
            app=app,
            font=font,
        )
        before = _snapshot_from_context(context)
        if not before.get("ok"):
            return before
        if before["stateFingerprint"] != expected_state_fingerprint:
            raise ValueError("IconGrid centering state changed since review; read the layer again.")
        layer = context["layer"]
        before_present, before_value = _plain_root(layer)
        if action == "set":
            proposed_present = True
            proposed_value = propose_set(
                before_value,
                before_present,
                center_x,
            )
        elif action == "reset":
            proposed_present, proposed_value = propose_reset(before_value, before_present)
        else:  # pragma: no cover - private invariant
            raise ValueError("Unknown IconGrid mutation action.")
        changed = (
            before_present != proposed_present
            or before_value != proposed_value
        )
        proposed_policy = validate_policy_root(proposed_value, proposed_present)
        payload = {
            "ok": True,
            "target": context["target"],
            "summary": {
                "changed": changed,
                "action": action,
                "state": before["center"]["state"],
            },
            "before": before,
            "proposed": {
                "policy": json_safe(proposed_policy),
                "rootPresent": proposed_present,
                "root": json_safe(proposed_value),
            },
            "applied": False,
            "readback": before,
            "undoGrouped": False,
            "undoRegistered": False,
            "redrawn": False,
            "fontSaved": False,
        }
        if dry_run or not changed:
            return payload

        try:
            with _undo_group(context["font"]) as (grouped, manager):
                payload["undoGrouped"] = grouped
                if not grouped:
                    raise RuntimeError("Glyphs did not provide an undo context for IconGrid centering.")
                _write_root(layer, proposed_present, proposed_value)
                payload["undoRegistered"] = _register_inverse(
                    manager,
                    context["font"],
                    layer,
                    before_present,
                    before_value,
                    app,
                )
                if not payload["undoRegistered"]:
                    raise RuntimeError("Glyphs did not accept the explicit IconGrid undo operation.")
                set_name = getattr(manager, "setActionName_", None)
                if callable(set_name):
                    set_name(
                        "Center Icon Grid Horizontally"
                        if action == "set"
                        else "Reset Icon Grid Horizontal Center"
                    )
        except Exception:
            try:
                _write_root(layer, before_present, before_value)
            except Exception:
                pass
            raise
        payload["redrawn"] = _redraw(app)
        _post_change(dict(context["target"], action=action))
        payload["after"] = _snapshot_from_context(context)
        payload["after"]["redrawn"] = payload["redrawn"]
        payload["applied"] = True
        payload["readback"] = payload["after"]
        return payload

    return _run_on_main_thread(transaction)


def set_icon_grid_horizontal_center_transaction(
    expected_state_fingerprint,
    center_x,
    font_index=0,
    glyph_name=None,
    layer_id=None,
    dry_run=True,
    confirm=False,
    app=None,
    font=None,
):
    return _mutation(
        "set",
        expected_state_fingerprint,
        font_index=font_index,
        glyph_name=glyph_name,
        layer_id=layer_id,
        center_x=center_x,
        dry_run=dry_run,
        confirm=confirm,
        app=app,
        font=font,
    )


def reset_icon_grid_horizontal_center_transaction(
    expected_state_fingerprint,
    font_index=0,
    glyph_name=None,
    layer_id=None,
    dry_run=True,
    confirm=False,
    app=None,
    font=None,
):
    return _mutation(
        "reset",
        expected_state_fingerprint,
        font_index=font_index,
        glyph_name=glyph_name,
        layer_id=layer_id,
        dry_run=dry_run,
        confirm=confirm,
        app=app,
        font=font,
    )


__all__ = [
    "IconGridCenteringError",
    "icon_grid_snapshot",
    "reset_icon_grid_horizontal_center_transaction",
    "set_icon_grid_horizontal_center_transaction",
]
