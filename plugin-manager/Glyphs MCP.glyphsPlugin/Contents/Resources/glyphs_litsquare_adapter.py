# encoding: utf-8

"""Glyphs object adapter for LitSquare metadata inspection and guarded writes."""

from __future__ import annotations

import copy
from contextlib import contextmanager
from datetime import datetime, timezone

try:
    from Foundation import NSData, NSNotificationCenter  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - normal outside Glyphs
    NSData = None
    NSNotificationCenter = None

try:
    from GlyphsApp import Glyphs  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - normal outside Glyphs
    Glyphs = None

from litsquare_metadata import (
    ROLE_KEY,
    ROOT_KEY,
    SCHEMA_VERSION,
    aggregate_roles,
    effective_settings,
    from_json_projection,
    json_safe,
    merge_patch,
    native_inspection_projection,
    normalize_role,
    normalize_role_input,
    path_fingerprint,
    to_plain,
    validate_metadata,
)

try:
    from mcp_tool_helpers import _get_layer_id, _resolve_font_by_index, _run_on_main_thread
except Exception:  # pragma: no cover - pure test imports may stub these
    _get_layer_id = lambda layer: str(getattr(layer, "layerId", "") or getattr(layer, "layerID", ""))
    _run_on_main_thread = lambda callback: callback()

    def _resolve_font_by_index(app, font_index):
        fonts = list(getattr(app, "fonts", []) or [])
        try:
            return fonts[int(font_index)], fonts
        except Exception:
            return None, fonts


METADATA_CHANGED_NOTIFICATION = "com.litsquare.metadataDidChange"
INSPECTOR_NAME = "Glyphs MCP Metadata Inspector"


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _maybe_call(value):
    try:
        return value() if callable(value) else value
    except Exception:
        return None


def _sequence(value):
    if value is None:
        return []
    try:
        return [value[index] for index in range(len(value))]
    except Exception:
        try:
            return list(value)
        except Exception:
            return []


def _mapping_value(mapping, key):
    if mapping is None:
        return False, None
    try:
        if key in mapping:
            return True, mapping[key]
    except Exception:
        pass
    try:
        value = mapping.objectForKey_(key)
        if value is not None:
            return True, value
    except Exception:
        pass
    try:
        value = mapping[key]
        return value is not None, value
    except Exception:
        return False, None


def _mapping_set(owner, attribute_name, key, value):
    mapping = getattr(owner, attribute_name, None)
    native = _native_value(value)
    try:
        mapping[key] = native
        present, readback = _mapping_value(mapping, key)
        if present:
            return readback
    except Exception:
        pass
    try:
        replacement = dict(mapping or {})
    except Exception:
        replacement = {}
    replacement[key] = native
    setattr(owner, attribute_name, replacement)
    present, readback = _mapping_value(getattr(owner, attribute_name, None), key)
    if not present:
        raise RuntimeError("Glyphs did not retain {}[{}].".format(attribute_name, key))
    return readback


def _mapping_delete(owner, attribute_name, key):
    mapping = getattr(owner, attribute_name, None)
    try:
        del mapping[key]
        present, _ = _mapping_value(mapping, key)
        if not present:
            return
    except Exception:
        pass
    try:
        replacement = dict(mapping or {})
    except Exception:
        replacement = {}
    replacement.pop(key, None)
    setattr(owner, attribute_name, replacement)
    present, _ = _mapping_value(getattr(owner, attribute_name, None), key)
    if present:
        raise RuntimeError("Glyphs did not remove {}[{}].".format(attribute_name, key))


def _native_value(value):
    if isinstance(value, bytes) and NSData is not None:
        try:
            return NSData.dataWithBytes_length_(value, len(value))
        except Exception:
            return value
    if isinstance(value, dict):
        return {str(key): _native_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_native_value(item) for item in value]
    return value


def _glyph_by_name(font, glyph_name):
    if not glyph_name:
        return None
    glyphs = getattr(font, "glyphs", None)
    try:
        return glyphs[glyph_name]
    except Exception:
        pass
    for glyph in _sequence(glyphs):
        if str(getattr(glyph, "name", "") or "") == str(glyph_name):
            return glyph
    return None


def _layer_by_id(glyph, layer_id):
    if glyph is None or not layer_id:
        return None
    layers = getattr(glyph, "layers", None)
    try:
        return layers[layer_id]
    except Exception:
        pass
    for layer in _sequence(layers):
        if str(_get_layer_id(layer) or "") == str(layer_id):
            return layer
    return None


def _selected_layers(font):
    return _sequence(getattr(font, "selectedLayers", None))


def resolve_context(font_index=0, glyph_name=None, layer_id=None, app=None, font=None):
    if font is None:
        app = app or Glyphs
        if app is None:
            raise RuntimeError("GlyphsApp is unavailable.")
        font, fonts = _resolve_font_by_index(app, font_index)
        if font is None:
            raise ValueError("Font index {} is unavailable; {} font(s) are open.".format(font_index, len(fonts)))

    selected = _selected_layers(font)
    glyph = _glyph_by_name(font, glyph_name)
    if glyph is None and not glyph_name and len(selected) == 1:
        glyph = _maybe_call(getattr(selected[0], "parent", None))

    layer = _layer_by_id(glyph, layer_id)
    if layer is None and not layer_id and len(selected) == 1:
        selected_glyph = _maybe_call(getattr(selected[0], "parent", None))
        if glyph is None or selected_glyph is glyph:
            glyph = glyph or selected_glyph
            layer = selected[0]

    return {
        "font": font,
        "glyph": glyph,
        "layer": layer,
        "selectedLayerCount": len(selected),
        "target": {
            "fontIndex": int(font_index),
            "familyName": str(getattr(font, "familyName", "") or ""),
            "glyphName": str(getattr(glyph, "name", "") or "") if glyph is not None else None,
            "layerName": str(_maybe_call(getattr(layer, "name", None)) or "") if layer is not None else None,
            "layerId": str(_get_layer_id(layer) or "") if layer is not None else None,
        },
    }


def _metadata_result(owner):
    if owner is None:
        return {
            "state": "no_context",
            "label": "No context",
            "schemaVersion": None,
            "updatedAt": None,
            "value": None,
            "errors": [],
            "warnings": [],
        }
    present, raw = _mapping_value(getattr(owner, "userData", None), ROOT_KEY)
    return validate_metadata(raw, present=present)


def metadata_snapshot(font_index=0, glyph_name=None, layer_id=None, include_inherited=True, app=None, font=None):
    context = resolve_context(font_index, glyph_name, layer_id, app=app, font=font)
    scopes = {
        "font": _metadata_result(context["font"]),
        "glyph": _metadata_result(context["glyph"]),
        "layer": _metadata_result(context["layer"]),
    }
    data = {
        "ok": True,
        "target": context["target"],
        "summary": {
            "fontState": scopes["font"]["state"],
            "glyphState": scopes["glyph"]["state"],
            "layerState": scopes["layer"]["state"],
        },
        "scopes": json_safe(scopes),
        "selectedLayerCount": context["selectedLayerCount"],
        "fontSaved": False,
    }
    if include_inherited:
        data["effectiveSettings"] = json_safe(effective_settings(scopes))
    return data


def _selection_owners(font, scope):
    if scope == "font":
        return [(font, None, None)]
    selected = _selected_layers(font)
    if scope == "layer":
        owners = []
        seen = set()
        for layer in selected:
            if id(layer) in seen:
                continue
            seen.add(id(layer))
            owners.append((layer, _maybe_call(getattr(layer, "parent", None)), layer))
        return owners
    if scope == "glyph":
        owners = []
        seen = set()
        for layer in selected:
            glyph = _maybe_call(getattr(layer, "parent", None))
            if glyph is None or id(glyph) in seen:
                continue
            seen.add(id(glyph))
            owners.append((glyph, glyph, None))
        return owners
    raise ValueError("scope must be one of: font, glyph, layer")


def _metadata_target(scope, font_index, glyph, layer, result):
    return {
        "scope": scope,
        "fontIndex": int(font_index),
        "glyphName": str(getattr(glyph, "name", "") or "") if glyph is not None else None,
        "layerName": str(_maybe_call(getattr(layer, "name", None)) or "") if layer is not None else None,
        "layerId": str(_get_layer_id(layer) or "") if layer is not None else None,
        "expectedPresent": result["state"] != "missing",
        "expectedValue": json_safe(result.get("value")),
    }


def metadata_selection_snapshot(scope, font_index=0, app=None, font=None):
    """Read direct metadata for every selected owner in Palette selection order."""

    def transaction():
        context = resolve_context(font_index, app=app, font=font)
        owners = _selection_owners(context["font"], scope)
        entries = []
        identities = []
        for owner, glyph, layer in owners:
            result = _metadata_result(owner)
            target = _metadata_target(scope, font_index, glyph, layer, result)
            entries.append({"target": target, "result": json_safe(result)})
            identities.append((target["expectedPresent"], target["expectedValue"]))
        shared = bool(identities) and all(identity == identities[0] for identity in identities)
        shared_result = entries[0]["result"] if shared else None
        return {
            "ok": bool(entries),
            "target": dict(context["target"], scope=scope),
            "summary": {
                "targetCount": len(entries),
                "mixed": bool(entries) and not shared,
                "state": shared_result.get("state") if shared_result else ("mixed" if entries else "no_context"),
            },
            "entries": entries,
            "sharedResult": shared_result,
            "fontSaved": False,
        }

    return _run_on_main_thread(transaction)


def _node_record(node):
    position = _maybe_call(getattr(node, "position", None))
    x = getattr(position, "x", None)
    y = getattr(position, "y", None)
    if x is None:
        x = getattr(node, "x", 0)
    if y is None:
        y = getattr(node, "y", 0)
    return {
        "type": str(getattr(node, "type", "") or ""),
        "smooth": bool(getattr(node, "smooth", False)),
        "x": float(x or 0),
        "y": float(y or 0),
    }


def _path_record(path):
    return {
        "closed": bool(getattr(path, "closed", False)),
        "nodes": [_node_record(node) for node in _sequence(getattr(path, "nodes", None))],
    }


def _bounds(path):
    bounds = _maybe_call(getattr(path, "bounds", None))
    if bounds is None:
        return None
    origin = getattr(bounds, "origin", None)
    size = getattr(bounds, "size", None)
    try:
        return {
            "x": float(getattr(origin, "x", 0)),
            "y": float(getattr(origin, "y", 0)),
            "width": float(getattr(size, "width", 0)),
            "height": float(getattr(size, "height", 0)),
        }
    except Exception:
        return None


def _path_selected(path):
    if bool(getattr(path, "selected", False)):
        return True
    return any(bool(getattr(node, "selected", False)) for node in _sequence(getattr(path, "nodes", None)))


def _path_entry(glyph, layer, path, path_index):
    present, raw = _mapping_value(getattr(path, "attributes", None), ROLE_KEY)
    raw_errors = []
    plain_raw = to_plain(raw, path="$.role", errors=raw_errors) if present else None
    role = normalize_role(plain_raw, present)
    return {
        "glyphName": str(getattr(glyph, "name", "") or ""),
        "layerId": str(_get_layer_id(layer) or ""),
        "pathIndex": int(path_index),
        "pathFingerprint": path_fingerprint(_path_record(path)),
        "expectedRole": json_safe(plain_raw) if present else None,
        "rolePresent": present,
        "rawRole": json_safe(plain_raw) if present else None,
        "role": role.get("role"),
        "roleState": role["state"],
        "roleLabel": role["label"],
        "description": role["description"],
        "bounds": _bounds(path),
    }


def selected_path_snapshot(font_index=0, app=None, font=None):
    context = resolve_context(font_index, app=app, font=font)
    glyph = context["glyph"]
    layer = context["layer"]
    if glyph is None or layer is None:
        return {
            "ok": False,
            "target": context["target"],
            "summary": {"selectedPathCount": 0},
            "error": "Exactly one active glyph layer is required.",
        }
    entries = []
    for index, path in enumerate(_sequence(getattr(layer, "paths", None))):
        if _path_selected(path):
            entries.append(_path_entry(glyph, layer, path, index))
    aggregation = aggregate_roles(entries)
    return {
        "ok": True,
        "target": context["target"],
        "summary": {"selectedPathCount": len(entries), "roleState": aggregation["state"]},
        "paths": json_safe(entries),
        "aggregation": json_safe(aggregation),
        "fontSaved": False,
    }


def _inspection_target(font, glyph=None, layer=None, path_index=None):
    target = {
        "familyName": str(getattr(font, "familyName", "") or ""),
    }
    if glyph is not None:
        target["glyphName"] = str(getattr(glyph, "name", "") or "")
    if layer is not None:
        target["layerName"] = str(
            _maybe_call(getattr(layer, "name", None)) or ""
        )
        target["layerId"] = str(_get_layer_id(layer) or "")
    if path_index is not None:
        target["pathIndex"] = int(path_index)
    return target


def full_metadata_selection_snapshot(
    scope, font_index=0, app=None, font=None
):
    """Project complete selected native dictionaries for Palette inspection."""

    if scope not in {"font", "glyph", "layer", "paths"}:
        raise ValueError("scope must be one of: font, glyph, layer, paths")

    def transaction():
        context = resolve_context(font_index, app=app, font=font)
        resolved_font = context["font"]
        entries = []
        warnings = []

        def append_entry(target, storage_name, storage):
            projection = native_inspection_projection(
                storage if storage is not None else {}
            )
            entries.append(
                {
                    "target": target,
                    storage_name: projection["value"],
                }
            )
            for warning in projection["warnings"]:
                item = dict(warning)
                item["target"] = dict(target)
                item["storage"] = storage_name
                warnings.append(item)

        if scope == "paths":
            glyph = context["glyph"]
            layer = context["layer"]
            if glyph is not None and layer is not None:
                for path_index, path in enumerate(
                    _sequence(getattr(layer, "paths", None))
                ):
                    if not _path_selected(path):
                        continue
                    append_entry(
                        _inspection_target(
                            resolved_font,
                            glyph=glyph,
                            layer=layer,
                            path_index=path_index,
                        ),
                        "attributes",
                        getattr(path, "attributes", None),
                    )
        else:
            for owner, glyph, layer in _selection_owners(resolved_font, scope):
                append_entry(
                    _inspection_target(resolved_font, glyph=glyph, layer=layer),
                    "userData",
                    getattr(owner, "userData", None),
                )

        return {
            "ok": bool(entries),
            "scope": scope,
            "target": dict(context["target"], scope=scope),
            "summary": {
                "targetCount": len(entries),
                "warningCount": len(warnings),
            },
            "entries": entries,
            "warnings": warnings,
            "fontSaved": False,
        }

    return _run_on_main_thread(transaction)


def _owner_for_scope(context, scope):
    if scope == "font":
        return context["font"], None
    if scope == "glyph":
        if context["glyph"] is None:
            raise ValueError("A unique glyph target is required for glyph scope.")
        return context["glyph"], context["glyph"]
    if scope == "layer":
        if context["layer"] is None:
            raise ValueError("A unique layer target is required for layer scope.")
        return context["layer"], context["glyph"]
    raise ValueError("scope must be one of: font, glyph, layer")


def _undo_manager(font):
    document = _maybe_call(getattr(font, "parent", None))
    manager = _maybe_call(getattr(document, "undoManager", None)) if document is not None else None
    return manager


@contextmanager
def _undo_group(font):
    manager = _undo_manager(font)
    if manager is not None and callable(getattr(manager, "beginUndoGrouping", None)):
        manager.beginUndoGrouping()
        try:
            yield True, manager
        finally:
            manager.endUndoGrouping()
        return
    yield False, None


def _register_undo_handler(manager, target, handler):
    register = getattr(manager, "registerUndoWithTarget_handler_", None)
    if not callable(register):
        return False
    try:
        register(target, handler)
        return True
    except Exception:
        return False


def _register_root_inverse(manager, owner, value, present):
    restore_value = copy.deepcopy(value)

    def restore(target):
        current = _metadata_result(target)
        current_present = current["state"] != "missing"
        current_value = current.get("value")
        _register_root_inverse(
            manager, target, current_value if current_value is not None else {}, current_present
        )
        _write_root(target, restore_value, present=present)
        _post_change({"scope": "undo", "owner": target.__class__.__name__})

    return _register_undo_handler(manager, owner, restore)


def _register_roots_inverse(manager, font, originals):
    restore_values = [
        (owner, present, copy.deepcopy(value)) for owner, present, value in originals
    ]

    def restore(_target):
        current = []
        for owner, _present, _value in restore_values:
            result = _metadata_result(owner)
            value = result.get("value")
            current.append(
                (
                    owner,
                    result["state"] != "missing",
                    copy.deepcopy(value if value is not None else {}),
                )
            )
        _register_roots_inverse(manager, font, current)
        for owner, present, value in restore_values:
            _write_root(owner, value, present=present)
        _post_change({"scope": "undo", "ownerCount": len(restore_values)})

    return _register_undo_handler(manager, font, restore)


def _register_role_inverse(manager, font, originals):
    restore_values = [
        (layer, path, present, copy.deepcopy(raw)) for layer, path, present, raw in originals
    ]

    def restore(_target):
        current = []
        for layer, path, _present, _raw in restore_values:
            present, raw = _mapping_value(getattr(path, "attributes", None), ROLE_KEY)
            current.append((layer, path, present, raw))
        _register_role_inverse(manager, font, current)
        layers = []
        for layer, _path, _present, _raw in restore_values:
            if layer not in layers:
                layers.append(layer)
        opened = []
        try:
            for layer in layers:
                layer.beginChanges()
                opened.append(layer)
            for _layer, path, present, raw in restore_values:
                if present:
                    _mapping_set(path, "attributes", ROLE_KEY, raw)
                else:
                    _mapping_delete(path, "attributes", ROLE_KEY)
        finally:
            for layer in reversed(opened):
                layer.endChanges()
        _post_change({"fontIndex": None, "pathCount": len(restore_values), "undo": True})

    return _register_undo_handler(manager, font, restore)


def _post_change(target):
    if NSNotificationCenter is None:
        return
    try:
        NSNotificationCenter.defaultCenter().postNotificationName_object_userInfo_(
            METADATA_CHANGED_NOTIFICATION,
            None,
            target,
        )
    except Exception:
        pass


def _write_root(owner, value, present=None):
    should_store = bool(value) if present is None else bool(present)
    if should_store:
        readback = _mapping_set(owner, "userData", ROOT_KEY, value)
        result = validate_metadata(readback, present=True)
    else:
        _mapping_delete(owner, "userData", ROOT_KEY)
        result = validate_metadata(None, present=False)
    return result


def patch_metadata_transaction(
    scope,
    patch,
    font_index=0,
    glyph_name=None,
    layer_id=None,
    expected_updated_at=None,
    dry_run=True,
    confirm=False,
    app=None,
):
    if type(dry_run) is not bool or type(confirm) is not bool or dry_run == confirm:
        raise ValueError("Set exactly one of dry_run=true or confirm=true.")
    if not isinstance(patch, dict):
        raise ValueError("patch must be a JSON object.")
    if "schemaVersion" in patch:
        raise ValueError("schemaVersion changes require an explicit migration.")
    if "updatedAt" in patch:
        raise ValueError("updatedAt is managed by LitSquare tooling.")
    patch = from_json_projection(patch)

    def transaction():
        context = resolve_context(font_index, glyph_name, layer_id, app=app)
        owner, undo_glyph = _owner_for_scope(context, scope)
        current = _metadata_result(owner)
        if current["state"] == "unsupported_schema":
            raise ValueError("Unsupported LitSquare schema cannot be patched.")
        if current["state"] == "invalid":
            raise ValueError("Invalid LitSquare metadata must be repaired explicitly before patching.")
        current_updated_at = current.get("updatedAt")
        if expected_updated_at is not None and current_updated_at != expected_updated_at:
            raise ValueError("updatedAt changed since review; read the scope again.")

        original = copy.deepcopy(current.get("value") or {})
        original_present = current["state"] != "missing"
        proposed = merge_patch(original, patch)
        if proposed:
            proposed.setdefault("schemaVersion", SCHEMA_VERSION)
            proposed["updatedAt"] = utc_timestamp()
        validation = validate_metadata(proposed, present=bool(proposed))
        if validation["state"] not in {"valid", "valid_with_warnings", "missing", "empty"}:
            return {
                "ok": False,
                "target": dict(context["target"], scope=scope),
                "summary": {"changed": False},
                "error": {"code": "validation_failed", "message": "Proposed metadata is not valid v1 data.", "recoverable": True},
                "validation": json_safe(validation),
                "fontSaved": False,
            }
        changed = original != proposed
        payload = {
            "ok": True,
            "target": dict(context["target"], scope=scope),
            "summary": {"changed": changed},
            "before": json_safe(current),
            "proposed": json_safe(validation),
            "fontSaved": False,
            "undoGrouped": False,
            "undoRegistered": False,
        }
        if dry_run or not changed:
            return payload

        try:
            with _undo_group(context["font"]) as (grouped, manager):
                payload["undoGrouped"] = grouped
                if not grouped:
                    raise RuntimeError("Glyphs did not provide an undo context for this metadata change.")
                readback = _write_root(owner, proposed, present=bool(proposed))
                if readback["value"] != proposed:
                    raise RuntimeError("LitSquare metadata readback did not match the confirmed patch.")
                payload["undoRegistered"] = _register_root_inverse(
                    manager, owner, original, original_present
                )
                if not payload["undoRegistered"]:
                    raise RuntimeError("Glyphs did not accept the explicit metadata undo operation.")
                set_name = getattr(manager, "setActionName_", None)
                if callable(set_name):
                    set_name("Edit LitSquare Metadata")
        except Exception:
            try:
                _write_root(owner, original, present=original_present)
            except Exception:
                pass
            raise
        payload["after"] = json_safe(readback)
        _post_change(payload["target"])
        return payload

    return _run_on_main_thread(transaction)


def _metadata_owner_for_target(font, scope, target):
    if not isinstance(target, dict) or target.get("scope") != scope:
        raise ValueError("Metadata target does not match the requested scope.")
    if scope == "font":
        return font
    glyph = _glyph_by_name(font, target.get("glyphName"))
    if glyph is None:
        raise ValueError("Metadata target glyph no longer exists.")
    if scope == "glyph":
        return glyph
    layer = _layer_by_id(glyph, target.get("layerId"))
    if layer is None:
        raise ValueError("Metadata target layer no longer exists.")
    return layer


def replace_metadata_selection_transaction(
    scope,
    targets,
    value,
    font_index=0,
    app=None,
    font=None,
):
    """Atomically replace direct roots for Palette-selected owners."""

    if scope not in {"font", "glyph", "layer"}:
        raise ValueError("scope must be one of: font, glyph, layer")
    if not isinstance(targets, list) or not targets:
        raise ValueError("Metadata targets must be a non-empty selection snapshot.")
    proposed = copy.deepcopy(value)
    validation = validate_metadata(proposed, present=True)
    if validation["state"] not in {"empty", "valid", "valid_with_warnings"}:
        raise ValueError("Invalid input: metadata is not valid LitSquare data.")
    if proposed and proposed.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("Invalid input: schemaVersion must be 1.")

    def transaction():
        context = resolve_context(font_index, app=app, font=font)
        plans = []
        owner_ids = set()
        for target in targets:
            owner = _metadata_owner_for_target(context["font"], scope, target)
            if id(owner) in owner_ids:
                raise ValueError("Duplicate metadata targets are not allowed.")
            owner_ids.add(id(owner))
            current = _metadata_result(owner)
            current_present = current["state"] != "missing"
            expected_value = from_json_projection(target.get("expectedValue"))
            if current_present != bool(target.get("expectedPresent")) or current.get("value") != expected_value:
                raise ValueError("Metadata changed since it was displayed; refresh and try again.")
            plans.append((owner, current_present, copy.deepcopy(current.get("value"))))

        final_value = copy.deepcopy(proposed)
        if final_value:
            final_value["updatedAt"] = utc_timestamp()
        final_validation = validate_metadata(final_value, present=True)
        if final_validation["state"] not in {"empty", "valid", "valid_with_warnings"}:
            raise ValueError("Invalid input: metadata is not valid LitSquare data.")
        changed = [
            owner for owner, present, original in plans
            if not present or original != final_value
        ]
        payload = {
            "ok": True,
            "target": {
                "fontIndex": int(font_index),
                "scope": scope,
                "targetCount": len(plans),
            },
            "summary": {"changedTargetCount": len(changed), "reviewedTargetCount": len(plans)},
            "after": json_safe(final_validation),
            "fontSaved": False,
            "undoGrouped": False,
            "undoRegistered": False,
        }
        if not changed:
            return payload

        written = []
        try:
            with _undo_group(context["font"]) as (grouped, manager):
                payload["undoGrouped"] = grouped
                if not grouped:
                    raise RuntimeError("Glyphs did not provide one undo context for the metadata change.")
                for owner, original_present, original in plans:
                    readback = _write_root(owner, final_value, present=True)
                    written.append((owner, original_present, original))
                    if readback.get("value") != final_value:
                        raise RuntimeError("LitSquare metadata readback did not match the edited value.")
                originals = [
                    (
                        owner,
                        original_present,
                        original if original is not None else {},
                    )
                    for owner, original_present, original in plans
                ]
                payload["undoRegistered"] = _register_roots_inverse(
                    manager, context["font"], originals
                )
                if not payload["undoRegistered"]:
                    raise RuntimeError("Glyphs did not accept the explicit metadata undo operation.")
                set_name = getattr(manager, "setActionName_", None)
                if callable(set_name):
                    set_name("Edit LitSquare Metadata")
        except Exception:
            for owner, original_present, original in reversed(written):
                try:
                    _write_root(
                        owner,
                        original if original is not None else {},
                        present=original_present,
                    )
                except Exception:
                    pass
            raise
        _post_change(payload["target"])
        return payload

    return _run_on_main_thread(transaction)


def _target_path(context, target):
    glyph = _glyph_by_name(context["font"], target.get("glyphName"))
    layer = _layer_by_id(glyph, target.get("layerId"))
    if glyph is None or layer is None:
        raise ValueError("Path target glyph/layer no longer exists.")
    paths = _sequence(getattr(layer, "paths", None))
    try:
        index = int(target.get("pathIndex"))
        if index < 0:
            raise ValueError
        path = paths[index]
    except Exception:
        raise ValueError("Path target index no longer exists.")
    fingerprint = path_fingerprint(_path_record(path))
    if fingerprint != target.get("pathFingerprint"):
        raise ValueError("Path changed since review; read selected path roles again.")
    present, raw = _mapping_value(getattr(path, "attributes", None), ROLE_KEY)
    expected = target.get("expectedRole")
    raw_errors = []
    plain_raw = to_plain(raw, path="$.role", errors=raw_errors) if present else None
    current_expected = json_safe(plain_raw) if present else None
    if bool(present) != bool(target.get("rolePresent")) or current_expected != expected:
        raise ValueError("Path role changed since review; read selected path roles again.")
    return glyph, layer, path, present, raw


def set_path_roles_transaction(
    targets,
    role=None,
    font_index=0,
    dry_run=True,
    confirm=False,
    app=None,
    font=None,
):
    if type(dry_run) is not bool or type(confirm) is not bool or dry_run == confirm:
        raise ValueError("Set exactly one of dry_run=true or confirm=true.")
    if not isinstance(targets, list) or not targets:
        raise ValueError("targets must be a non-empty array returned by get_selected_litsquare_path_roles.")
    role = normalize_role_input(role)

    def transaction():
        context = resolve_context(font_index, app=app, font=font)
        plans = []
        target_keys = set()
        for target in targets:
            if not isinstance(target, dict):
                raise ValueError("Every path target must be an object.")
            target_key = (target.get("glyphName"), target.get("layerId"), target.get("pathIndex"))
            if target_key in target_keys:
                raise ValueError("Duplicate path targets are not allowed.")
            target_keys.add(target_key)
            glyph, layer, path, present, raw = _target_path(context, target)
            plans.append((target, glyph, layer, path, present, raw))
        replacements = [
            {
                "glyphName": target.get("glyphName"),
                "layerId": target.get("layerId"),
                "pathIndex": target.get("pathIndex"),
                "before": raw if present else None,
                "after": role,
            }
            for target, _glyph, _layer, _path, present, raw in plans
            if (raw if present else None) != role
        ]
        payload = {
            "ok": True,
            "target": {"fontIndex": int(font_index), "pathCount": len(plans)},
            "summary": {"changedPathCount": len(replacements), "reviewedPathCount": len(plans)},
            "replacements": replacements,
            "fontSaved": False,
            "undoGrouped": False,
            "undoRegistered": False,
        }
        if dry_run or not replacements:
            return payload

        originals = [
            (layer, path, present, raw)
            for _target, _glyph, layer, path, present, raw in plans
        ]
        layers = []
        for _target, _glyph, layer, _path, _present, _raw in plans:
            if layer not in layers:
                layers.append(layer)
        manager = _undo_manager(context["font"])
        opened_layers = []
        grouping_open = False
        try:
            if manager is not None and callable(getattr(manager, "beginUndoGrouping", None)):
                manager.beginUndoGrouping()
                grouping_open = True
                payload["undoGrouped"] = True
            else:
                raise RuntimeError("Glyphs did not provide one undo context for all targeted paths.")
            for layer in layers:
                begin = getattr(layer, "beginChanges", None)
                end = getattr(layer, "endChanges", None)
                if not callable(begin) or not callable(end):
                    raise RuntimeError("Confirmed path-role changes require layer.beginChanges/endChanges.")
                begin()
                opened_layers.append(layer)
            for _target, _glyph, _layer, path, _present, _raw in plans:
                if role is None:
                    _mapping_delete(path, "attributes", ROLE_KEY)
                else:
                    _mapping_set(path, "attributes", ROLE_KEY, role)
            for _target, _glyph, _layer, path, _present, _raw in plans:
                present, raw = _mapping_value(getattr(path, "attributes", None), ROLE_KEY)
                if (raw if present else None) != role:
                    raise RuntimeError("Path role readback did not match the confirmed assignment.")
            payload["undoRegistered"] = _register_role_inverse(
                manager, context["font"], originals
            )
            if not payload["undoRegistered"]:
                raise RuntimeError("Glyphs did not accept the explicit path-role undo operation.")
            set_name = getattr(manager, "setActionName_", None)
            if callable(set_name):
                set_name("Set LitSquare Path Roles")
        except Exception:
            for _layer, path, present, raw in originals:
                try:
                    if present:
                        _mapping_set(path, "attributes", ROLE_KEY, raw)
                    else:
                        _mapping_delete(path, "attributes", ROLE_KEY)
                except Exception:
                    pass
            raise
        finally:
            for layer in reversed(opened_layers):
                layer.endChanges()
            if manager is not None and grouping_open:
                manager.endUndoGrouping()
        _post_change(payload["target"])
        return payload

    return _run_on_main_thread(transaction)


__all__ = [
    "INSPECTOR_NAME",
    "METADATA_CHANGED_NOTIFICATION",
    "full_metadata_selection_snapshot",
    "metadata_selection_snapshot",
    "metadata_snapshot",
    "patch_metadata_transaction",
    "replace_metadata_selection_transaction",
    "resolve_context",
    "selected_path_snapshot",
    "set_path_roles_transaction",
    "utc_timestamp",
]
