# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json
import uuid
from datetime import datetime, timezone

from GlyphsApp import (  # type: ignore[import-not-found]
    ARROW,
    CIRCLE,
    MINUS,
    PLUS,
    TEXT,
    Glyphs,
    GSAnnotation,
)

from mcp_runtime import mcp
from mcp_tool_helpers import (
    _font_resolution_error,
    _get_layer_id,
    _glyphs_show_layer_link_fields,
    _layer_display_name,
    _resolve_font_by_index,
    _safe_json,
)


REGISTRY_KEY = "com.ap.cx.glyphs-mcp.agentAnnotations.v1"
REGISTRY_OWNER = "Glyphs MCP"
REGISTRY_KIND = "agentAnnotations"
REGISTRY_SCHEMA_VERSION = 1
REGISTRY_DO_NOT_EDIT = (
    "Managed by Glyphs MCP; safe to delete if you want to remove agent annotation metadata."
)

ANNOTATION_ID_PREFIX = "mcp-ann-"
GROUP_ID_PREFIX = "mcp-grp-"


TYPE_NAME_TO_CODE = {
    "TEXT": TEXT,
    "ARROW": ARROW,
    "CIRCLE": CIRCLE,
    "PLUS": PLUS,
    "MINUS": MINUS,
}

TYPE_CODE_TO_NAME = {
    TEXT: "TEXT",
    ARROW: "ARROW",
    CIRCLE: "CIRCLE",
    PLUS: "PLUS",
    MINUS: "MINUS",
}


def _now_timestamp():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_annotation_id():
    return ANNOTATION_ID_PREFIX + uuid.uuid4().hex[:12]


def _new_group_id():
    return GROUP_ID_PREFIX + uuid.uuid4().hex[:12]


def _plist_safe(value):
    if value is None:
        return ""
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_plist_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plist_safe(item) for key, item in value.items()}
    return str(value)


def _as_plain_dict(value):
    if isinstance(value, dict):
        return dict(value)
    try:
        return dict(value)
    except Exception:
        pass
    try:
        return {str(key): value[key] for key in value.keys()}
    except Exception:
        return {}


def _as_plain_list(value):
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, (str, bytes)):
        return []
    try:
        return [item for item in value]
    except Exception:
        pass
    try:
        return [value[index] for index in range(len(value))]
    except Exception:
        return []


def _read_user_data_value(user_data, key):
    if user_data is None:
        return None
    try:
        return user_data.get(key)
    except Exception:
        pass
    try:
        return user_data[key]
    except Exception:
        return None


def _set_user_data_value(layer, key, value):
    user_data = getattr(layer, "userData", None)
    if user_data is None:
        try:
            layer.userData = {key: value}
            return _read_user_data_value(getattr(layer, "userData", None), key) is not None
        except Exception:
            return False

    try:
        user_data[key] = value
        if _read_user_data_value(user_data, key) is not None:
            return True
    except Exception:
        pass

    for method_name in ("setObject_forKey_", "setValue_forKey_"):
        try:
            method = getattr(user_data, method_name, None)
            if callable(method):
                method(value, key)
                if _read_user_data_value(user_data, key) is not None:
                    return True
        except Exception:
            pass

    try:
        replacement = dict(user_data)
    except Exception:
        replacement = {}
    replacement[key] = value
    try:
        layer.userData = replacement
        return _read_user_data_value(getattr(layer, "userData", None), key) is not None
    except Exception:
        return False


def _delete_user_data_value(layer, key):
    user_data = getattr(layer, "userData", None)
    if user_data is None:
        return

    try:
        del user_data[key]
        if _read_user_data_value(user_data, key) is None:
            return
    except Exception:
        pass

    for method_name in ("removeObjectForKey_", "removeObject_forKey_"):
        try:
            method = getattr(user_data, method_name, None)
            if callable(method):
                method(key)
                if _read_user_data_value(user_data, key) is None:
                    return
        except Exception:
            pass

    try:
        replacement = dict(user_data)
        replacement.pop(key, None)
        layer.userData = replacement
    except Exception:
        pass


def _registry_from_raw(raw):
    registry = _as_plain_dict(raw)
    if not registry:
        return None

    items = _as_plain_list(registry.get("items", []))

    clean = _empty_registry()
    clean["items"] = []
    for item in items:
        plain_item = _as_plain_dict(item)
        if plain_item:
            clean["items"].append(plain_item)
    return clean


def _parent_glyph(layer):
    try:
        parent = getattr(layer, "parent", None)
        if callable(parent):
            return parent()
        return parent
    except Exception:
        return None


def _layer_registry_key(layer):
    layer_id = _get_layer_id(layer)
    if layer_id:
        return "{}.{}".format(REGISTRY_KEY, layer_id)
    return REGISTRY_KEY


def _target_registry_key(glyph, layer):
    glyph_name = str(getattr(glyph, "name", "") or "")
    layer_id = _get_layer_id(layer) or str(getattr(layer, "associatedMasterId", "") or "")
    if glyph_name or layer_id:
        return "{}.{}.{}".format(REGISTRY_KEY, glyph_name, layer_id)
    return REGISTRY_KEY


def _empty_registry():
    return {
        "owner": REGISTRY_OWNER,
        "kind": REGISTRY_KIND,
        "schemaVersion": REGISTRY_SCHEMA_VERSION,
        "doNotEdit": REGISTRY_DO_NOT_EDIT,
        "items": [],
    }


def _get_registry(font, glyph, layer):
    # Prefer font-level userData for MCP ownership metadata. In Glyphs 4, layer
    # and glyph proxy userData can appear writable while not surviving readback.
    font_user_data = getattr(font, "userData", None)
    registry = _registry_from_raw(_read_user_data_value(font_user_data, _target_registry_key(glyph, layer)))
    if registry:
        return registry

    user_data = getattr(layer, "userData", None)
    registry = _registry_from_raw(_read_user_data_value(user_data, REGISTRY_KEY))
    if registry and registry.get("items"):
        return registry

    if glyph is None:
        glyph = _parent_glyph(layer)
    glyph_user_data = getattr(glyph, "userData", None)
    registry = _registry_from_raw(_read_user_data_value(glyph_user_data, _target_registry_key(glyph, layer)))
    if registry:
        return registry

    registry = _registry_from_raw(_read_user_data_value(glyph_user_data, _layer_registry_key(layer)))
    if registry:
        return registry

    return _empty_registry()


def _write_registry(font, glyph, layer, registry):
    items = registry.get("items") or []
    target_key = _target_registry_key(glyph, layer)
    if not items:
        if font is not None:
            _delete_user_data_value(font, target_key)
        _delete_user_data_value(layer, REGISTRY_KEY)
        if glyph is not None:
            _delete_user_data_value(glyph, target_key)
            _delete_user_data_value(glyph, _layer_registry_key(layer))
        return

    clean = _empty_registry()
    clean["items"] = items
    wrote = False
    if font is not None:
        wrote = _set_user_data_value(font, target_key, _plist_safe(clean))
    if glyph is not None and not wrote:
        wrote = _set_user_data_value(glyph, target_key, _plist_safe(clean))
    if not wrote:
        # Layer userData is kept only as a last-resort fallback. Font userData
        # is public API and avoids Glyphs 4 proxy readback problems seen on layers.
        wrote = _set_user_data_value(layer, REGISTRY_KEY, _plist_safe(clean))
    if glyph is not None and not wrote:
        _set_user_data_value(glyph, _layer_registry_key(layer), _plist_safe(clean))


def _annotation_list(layer):
    try:
        return list(getattr(layer, "annotations", []) or [])
    except Exception:
        return []


def _annotation_xy(annotation):
    position = getattr(annotation, "position", None)
    x = getattr(position, "x", None)
    y = getattr(position, "y", None)
    if x is None or y is None:
        try:
            x = position[0]
            y = position[1]
        except Exception:
            x = 0.0 if x is None else x
            y = 0.0 if y is None else y
    return float(x or 0.0), float(y or 0.0)


def _round_visible(value):
    try:
        return round(float(value), 3)
    except Exception:
        return 0.0


def _type_name(type_code):
    try:
        return TYPE_CODE_TO_NAME.get(int(type_code), str(type_code))
    except Exception:
        return str(type_code)


def _resolve_annotation_type(value):
    if value is None or value == "":
        return TEXT, None

    if isinstance(value, str):
        text = value.strip()
        upper = text.upper()
        if upper in TYPE_NAME_TO_CODE:
            return TYPE_NAME_TO_CODE[upper], None
        try:
            value = int(text)
        except Exception:
            return None, "annotation_type must be one of TEXT, ARROW, CIRCLE, PLUS, MINUS"

    try:
        type_code = int(value)
    except Exception:
        return None, "annotation_type must be one of TEXT, ARROW, CIRCLE, PLUS, MINUS"

    if type_code not in TYPE_CODE_TO_NAME:
        return None, "annotation_type must be one of TEXT, ARROW, CIRCLE, PLUS, MINUS"
    return type_code, None


def _default_width_for_type(type_code, width):
    if width is not None:
        return float(width)
    if type_code == TEXT:
        return 160.0
    if type_code == CIRCLE:
        return 60.0
    return 0.0


def _annotation_fingerprint(annotation):
    x, y = _annotation_xy(annotation)
    type_code = getattr(annotation, "type", TEXT)
    try:
        type_code = int(type_code)
    except Exception:
        type_code = TEXT
    return {
        "type": _type_name(type_code),
        "typeCode": type_code,
        "x": _round_visible(x),
        "y": _round_visible(y),
        "text": str(getattr(annotation, "text", "") or ""),
        "angle": _round_visible(getattr(annotation, "angle", 0.0)),
        "width": _round_visible(getattr(annotation, "width", 0.0)),
    }


def _fingerprint_matches(stored, current):
    stored = _as_plain_dict(stored)
    if not stored or not current:
        return False

    stored_type = stored.get("type")
    stored_type_code = stored.get("typeCode")
    type_matches = stored_type == current.get("type")
    try:
        type_matches = type_matches or int(stored_type_code) == int(current.get("typeCode"))
    except Exception:
        pass

    return (
        type_matches
        and _round_visible(stored.get("x")) == current.get("x")
        and _round_visible(stored.get("y")) == current.get("y")
        and str(stored.get("text") or "") == current.get("text")
        and _round_visible(stored.get("angle")) == current.get("angle")
        and _round_visible(stored.get("width")) == current.get("width")
    )


def _resolve_target(font_index, glyph_name, master_id):
    font, fonts = _resolve_font_by_index(Glyphs, font_index)
    if not font:
        return None, None, None, _font_resolution_error(font_index, fonts)

    if not glyph_name:
        return None, None, None, {"error": "Glyph name is required"}

    glyph = font.glyphs[glyph_name]
    if not glyph:
        return None, None, None, {"error": "Glyph '{}' not found".format(glyph_name)}

    if master_id:
        layer = glyph.layers[master_id]
        if not layer:
            return None, None, None, {"error": "Master ID '{}' not found".format(master_id)}
    else:
        selected_master = getattr(font, "selectedFontMaster", None)
        if selected_master:
            layer = glyph.layers[getattr(selected_master, "id", None)]
        else:
            layer = glyph.layers[font.masters[0].id]

    if not layer:
        return None, None, None, {"error": "No valid layer found for glyph '{}'".format(glyph_name)}

    return font, glyph, layer, None


def _reconcile_registry(font, glyph, layer, persist=False):
    registry = _get_registry(font, glyph, layer)
    annotations = _annotation_list(layer)
    fingerprints = [_annotation_fingerprint(annotation) for annotation in annotations]
    used = set()
    changed = False

    for item in registry.get("items", []):
        stored_fingerprint = _as_plain_dict(item.get("fingerprint"))
        match_index = None
        try:
            last_index = int(item.get("lastIndex", -1))
        except Exception:
            last_index = -1

        if 0 <= last_index < len(fingerprints):
            if last_index not in used and _fingerprint_matches(stored_fingerprint, fingerprints[last_index]):
                match_index = last_index

        if match_index is None:
            for index, fingerprint in enumerate(fingerprints):
                if index in used:
                    continue
                if _fingerprint_matches(stored_fingerprint, fingerprint):
                    match_index = index
                    break

        if match_index is None:
            if not item.get("orphaned"):
                item["orphaned"] = True
                item["updatedAt"] = _now_timestamp()
                changed = True
            continue

        used.add(match_index)
        if item.get("lastIndex") != match_index:
            item["lastIndex"] = match_index
            changed = True
        if item.get("orphaned"):
            item["orphaned"] = False
            changed = True

    if persist and changed:
        _write_registry(font, glyph, layer, registry)

    return registry


def _managed_item_by_index(registry):
    result = {}
    for item in registry.get("items", []):
        if item.get("orphaned"):
            continue
        try:
            result[int(item.get("lastIndex"))] = item
        except Exception:
            continue
    return result


def _managed_item_by_id(registry, annotation_id):
    if not annotation_id:
        return None
    for item in registry.get("items", []):
        if item.get("annotationId") == annotation_id:
            return item
    return None


def _annotation_payload(annotation, index, item=None):
    x, y = _annotation_xy(annotation)
    type_code = getattr(annotation, "type", TEXT)
    try:
        type_code = int(type_code)
    except Exception:
        type_code = TEXT

    payload = {
        "index": index,
        "type": _type_name(type_code),
        "typeCode": type_code,
        "x": x,
        "y": y,
        "text": str(getattr(annotation, "text", "") or ""),
        "angle": float(getattr(annotation, "angle", 0.0) or 0.0),
        "width": float(getattr(annotation, "width", 0.0) or 0.0),
        "managedByMcp": bool(item),
    }
    if item:
        payload.update(
            {
                "annotationId": item.get("annotationId", ""),
                "groupId": item.get("groupId", ""),
                "role": item.get("role", ""),
                "comment": item.get("comment", ""),
                "createdAt": item.get("createdAt", ""),
                "updatedAt": item.get("updatedAt", ""),
            }
        )
    return payload


def _target_summary(font, glyph_name, layer):
    layer_id = _get_layer_id(layer)
    layer_name = _layer_display_name(font, layer)
    result = {
        "glyphName": glyph_name,
        "masterId": getattr(layer, "associatedMasterId", None),
        "masterName": layer_name,
        "layerId": layer_id,
        "registryKey": REGISTRY_KEY,
    }
    result.update(
        _glyphs_show_layer_link_fields(
            getattr(font, "filepath", None),
            glyph_name=glyph_name,
            layer_id=layer_id,
            label="Open {} {} in Glyphs".format(glyph_name, layer_name),
        )
    )
    return result


def _append_annotation(layer, registry, x, y, annotation_type, text="", angle=0.0, width=None, group_id="", role="", comment=""):
    type_code, error = _resolve_annotation_type(annotation_type)
    if error:
        return None, None, error

    annotation = GSAnnotation()
    annotation.position = (float(x), float(y))
    annotation.type = type_code
    annotation.text = str(text or "")
    annotation.angle = float(angle or 0.0)
    annotation.width = _default_width_for_type(type_code, width)

    before = _annotation_list(layer)
    try:
        layer.annotations.append(annotation)
    except Exception:
        if hasattr(layer, "addAnnotation_"):
            layer.addAnnotation_(annotation)
        else:
            raise

    annotations = _annotation_list(layer)
    if not any(existing is annotation for existing in annotations):
        try:
            layer.annotations = before + [annotation]
            annotations = _annotation_list(layer)
        except Exception:
            pass
    if not any(existing is annotation for existing in annotations):
        return None, None, "Glyphs did not accept the new annotation"

    index = max(len(annotations) - 1, 0)
    for candidate_index, existing in enumerate(annotations):
        if existing is annotation:
            index = candidate_index
            break
    timestamp = _now_timestamp()
    item = {
        "annotationId": _new_annotation_id(),
        "groupId": str(group_id or ""),
        "role": str(role or ""),
        "comment": str(comment or ""),
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "lastIndex": index,
        "orphaned": False,
        "fingerprint": _annotation_fingerprint(annotation),
    }
    registry.setdefault("items", []).append(item)
    return annotation, item, None


def _begin_layer_changes(layer):
    try:
        if hasattr(layer, "beginChanges"):
            layer.beginChanges()
            return True
    except Exception:
        return False
    return False


def _end_layer_changes(layer, changes_open):
    if not changes_open:
        return
    try:
        if hasattr(layer, "endChanges"):
            layer.endChanges()
    except Exception:
        pass


def _delete_annotation_at_index(layer, index):
    try:
        del layer.annotations[index]
        return
    except Exception:
        pass

    annotations = _annotation_list(layer)
    if index < 0 or index >= len(annotations):
        raise IndexError("annotation_index out of range")
    annotation = annotations[index]
    if hasattr(layer.annotations, "remove"):
        layer.annotations.remove(annotation)
        return
    raise IndexError("annotation_index out of range")


def _validate_annotation_spec(spec):
    spec = _as_plain_dict(spec)
    if "x" not in spec or "y" not in spec:
        return None, "Each annotation in annotations_json must include x and y"
    annotation_type = spec.get("annotation_type", spec.get("type", "TEXT"))
    type_code, error = _resolve_annotation_type(annotation_type)
    if error:
        return None, error
    try:
        x = float(spec.get("x"))
        y = float(spec.get("y"))
        angle = float(spec.get("angle", 0.0) or 0.0)
        width = spec.get("width", None)
        if width is not None:
            width = float(width)
    except Exception:
        return None, "Annotation x, y, angle, and width must be numbers"
    return {
        "x": x,
        "y": y,
        "annotation_type": type_code,
        "text": str(spec.get("text", "") or ""),
        "angle": angle,
        "width": width,
        "role": str(spec.get("role", "") or ""),
        "comment": str(spec.get("comment", "") or ""),
    }, None


@mcp.tool()
async def get_glyph_annotations(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    include_user_annotations: bool = True,
) -> str:
    """Return native Glyphs annotations for a glyph layer, including MCP ownership metadata when known."""
    try:
        font, glyph, layer, error = _resolve_target(font_index, glyph_name, master_id)
        if error:
            return json.dumps(error)

        registry = _reconcile_registry(font, glyph, layer, persist=False)
        managed_by_index = _managed_item_by_index(registry)
        annotations = []
        for index, annotation in enumerate(_annotation_list(layer)):
            item = managed_by_index.get(index)
            if not include_user_annotations and not item:
                continue
            annotations.append(_annotation_payload(annotation, index, item))

        result = _target_summary(font, glyph_name, layer)
        result.update(
            {
                "annotationCount": len(annotations),
                "managedCount": len([item for item in managed_by_index.values() if item]),
                "userCount": len([annotation for annotation in annotations if not annotation.get("managedByMcp")]),
                "orphanedRegistryCount": len([item for item in registry.get("items", []) if item.get("orphaned")]),
                "annotations": annotations,
            }
        )
        return _safe_json(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def add_glyph_annotation(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    x: float = None,
    y: float = None,
    annotation_type: str = "TEXT",
    text: str = "",
    angle: float = 0,
    width: float = None,
    group_id: str = None,
    role: str = None,
    comment: str = None,
) -> str:
    """Add a native Glyphs annotation and register it as managed by Glyphs MCP."""
    try:
        if x is None or y is None:
            return json.dumps({"error": "Both x and y coordinates are required"})

        font, glyph, layer, error = _resolve_target(font_index, glyph_name, master_id)
        if error:
            return json.dumps(error)

        type_code, type_error = _resolve_annotation_type(annotation_type)
        if type_error:
            return json.dumps({"error": type_error})

        changes_open = _begin_layer_changes(layer)
        try:
            registry = _reconcile_registry(font, glyph, layer, persist=True)
            annotation, item, append_error = _append_annotation(
                layer,
                registry,
                x,
                y,
                type_code,
                text=text,
                angle=angle,
                width=width,
                group_id=group_id,
                role=role,
                comment=comment,
            )
            if append_error:
                return json.dumps({"error": append_error})
            _write_registry(font, glyph, layer, registry)
        finally:
            _end_layer_changes(layer, changes_open)

        result = _target_summary(font, glyph_name, layer)
        result.update(
            {
                "success": True,
                "annotation": _annotation_payload(annotation, item.get("lastIndex"), item),
            }
        )
        return _safe_json(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def add_glyph_annotation_group(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    annotations_json: str = None,
    comment: str = None,
) -> str:
    """Add a linked group of native Glyphs annotations managed by Glyphs MCP."""
    try:
        if not annotations_json:
            return json.dumps({"error": "annotations_json is required"})

        try:
            payload = json.loads(annotations_json)
        except ValueError as e:
            return json.dumps({"error": "Invalid JSON in annotations_json: {}".format(str(e))})

        if isinstance(payload, dict):
            specs = payload.get("annotations", [])
        else:
            specs = payload
        if not isinstance(specs, list) or not specs:
            return json.dumps({"error": "annotations_json must be a non-empty list or an object with annotations"})

        validated_specs = []
        for spec in specs:
            validated, validation_error = _validate_annotation_spec(spec)
            if validation_error:
                return json.dumps({"error": validation_error})
            validated_specs.append(validated)

        font, glyph, layer, error = _resolve_target(font_index, glyph_name, master_id)
        if error:
            return json.dumps(error)

        group_id = _new_group_id()
        changes_open = _begin_layer_changes(layer)
        added = []
        try:
            registry = _reconcile_registry(font, glyph, layer, persist=True)
            for spec in validated_specs:
                annotation_comment = spec.get("comment") or comment or ""
                annotation, item, append_error = _append_annotation(
                    layer,
                    registry,
                    spec["x"],
                    spec["y"],
                    spec["annotation_type"],
                    text=spec["text"],
                    angle=spec["angle"],
                    width=spec["width"],
                    group_id=group_id,
                    role=spec["role"],
                    comment=annotation_comment,
                )
                if append_error:
                    return json.dumps({"error": append_error})
                added.append(_annotation_payload(annotation, item.get("lastIndex"), item))
            _write_registry(font, glyph, layer, registry)
        finally:
            _end_layer_changes(layer, changes_open)

        result = _target_summary(font, glyph_name, layer)
        result.update({"success": True, "groupId": group_id, "annotations": added})
        return _safe_json(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def update_glyph_annotation(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    annotation_id: str = None,
    annotation_index: int = None,
    x: float = None,
    y: float = None,
    annotation_type: str = None,
    text: str = None,
    angle: float = None,
    width: float = None,
    comment: str = None,
    group_id: str = None,
    role: str = None,
) -> str:
    """Update a native Glyphs annotation, preferring MCP annotation_id when available."""
    try:
        font, glyph, layer, error = _resolve_target(font_index, glyph_name, master_id)
        if error:
            return json.dumps(error)

        changes_open = _begin_layer_changes(layer)
        try:
            registry = _reconcile_registry(font, glyph, layer, persist=True)
            managed_by_index = _managed_item_by_index(registry)
            item = _managed_item_by_id(registry, annotation_id)
            if item and item.get("orphaned"):
                return json.dumps({"error": "annotation_id '{}' is orphaned".format(annotation_id)})

            if item:
                index = int(item.get("lastIndex"))
            elif annotation_index is not None:
                index = int(annotation_index)
            else:
                return json.dumps({"error": "annotation_id or annotation_index is required"})

            annotations = _annotation_list(layer)
            if index < 0 or index >= len(annotations):
                return json.dumps({"error": "annotation_index {} out of range".format(index)})

            annotation = annotations[index]
            if annotation_type is not None:
                type_code, type_error = _resolve_annotation_type(annotation_type)
                if type_error:
                    return json.dumps({"error": type_error})
                annotation.type = type_code
            if x is not None or y is not None:
                current_x, current_y = _annotation_xy(annotation)
                annotation.position = (
                    float(current_x if x is None else x),
                    float(current_y if y is None else y),
                )
            if text is not None:
                annotation.text = str(text)
            if angle is not None:
                annotation.angle = float(angle)
            if width is not None:
                annotation.width = float(width)

            if item is None:
                timestamp = _now_timestamp()
                item = {
                    "annotationId": _new_annotation_id(),
                    "groupId": "",
                    "role": "",
                    "comment": "",
                    "createdAt": timestamp,
                    "updatedAt": timestamp,
                    "lastIndex": index,
                    "orphaned": False,
                    "fingerprint": _annotation_fingerprint(annotation),
                }
                registry.setdefault("items", []).append(item)
            else:
                item["updatedAt"] = _now_timestamp()
                item["lastIndex"] = index
                item["orphaned"] = False
                item["fingerprint"] = _annotation_fingerprint(annotation)

            if comment is not None:
                item["comment"] = str(comment)
            if group_id is not None:
                item["groupId"] = str(group_id or "")
            if role is not None:
                item["role"] = str(role or "")

            _write_registry(font, glyph, layer, registry)
        finally:
            _end_layer_changes(layer, changes_open)

        result = _target_summary(font, glyph_name, layer)
        result.update(
            {
                "success": True,
                "annotation": _annotation_payload(annotation, index, item),
                "wasManagedBeforeUpdate": bool(managed_by_index.get(index)),
            }
        )
        return _safe_json(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def delete_glyph_annotation(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    annotation_id: str = None,
    annotation_index: int = None,
) -> str:
    """Delete one native Glyphs annotation by MCP annotation_id or explicit annotation_index."""
    try:
        font, glyph, layer, error = _resolve_target(font_index, glyph_name, master_id)
        if error:
            return json.dumps(error)

        changes_open = _begin_layer_changes(layer)
        try:
            registry = _reconcile_registry(font, glyph, layer, persist=True)
            item = _managed_item_by_id(registry, annotation_id)
            if item and item.get("orphaned"):
                registry["items"] = [
                    existing
                    for existing in registry.get("items", [])
                    if existing.get("annotationId") != annotation_id
                ]
                _write_registry(font, glyph, layer, registry)
                return _safe_json({"success": True, "deleted": False, "removedOrphanedRecord": True})

            if item:
                index = int(item.get("lastIndex"))
            elif annotation_index is not None:
                index = int(annotation_index)
            else:
                return json.dumps({"error": "annotation_id or annotation_index is required"})

            annotations = _annotation_list(layer)
            if index < 0 or index >= len(annotations):
                return json.dumps({"error": "annotation_index {} out of range".format(index)})

            managed_annotation_id = item.get("annotationId") if item else None
            _delete_annotation_at_index(layer, index)
            if managed_annotation_id:
                registry["items"] = [
                    existing
                    for existing in registry.get("items", [])
                    if existing.get("annotationId") != managed_annotation_id
                ]
                _write_registry(font, glyph, layer, registry)
            registry = _reconcile_registry(font, glyph, layer, persist=False)
            _write_registry(font, glyph, layer, registry)
        finally:
            _end_layer_changes(layer, changes_open)

        result = _target_summary(font, glyph_name, layer)
        result.update({"success": True, "deleted": True, "managedByMcp": bool(item)})
        return _safe_json(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def clear_glyph_annotations(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    scope: str = "mcp",
) -> str:
    """Clear MCP-managed annotations by default, or all annotations with scope='all'."""
    try:
        normalized_scope = str(scope or "mcp").strip().lower()
        if normalized_scope not in ("mcp", "all"):
            return json.dumps({"error": "scope must be 'mcp' or 'all'"})

        font, glyph, layer, error = _resolve_target(font_index, glyph_name, master_id)
        if error:
            return json.dumps(error)

        changes_open = _begin_layer_changes(layer)
        deleted_count = 0
        preserved_user_count = 0
        try:
            registry = _reconcile_registry(font, glyph, layer, persist=True)
            annotations = _annotation_list(layer)
            if normalized_scope == "all":
                indices = list(range(len(annotations)))
                registry["items"] = []
            else:
                managed_by_index = _managed_item_by_index(registry)
                indices = sorted(managed_by_index.keys())
                preserved_user_count = len(annotations) - len(indices)
                registry["items"] = []

            for index in sorted(indices, reverse=True):
                _delete_annotation_at_index(layer, index)
                deleted_count += 1
            _write_registry(font, glyph, layer, registry)
        finally:
            _end_layer_changes(layer, changes_open)

        result = _target_summary(font, glyph_name, layer)
        result.update(
            {
                "success": True,
                "scope": normalized_scope,
                "deletedCount": deleted_count,
                "preservedUserCount": preserved_user_count,
            }
        )
        return _safe_json(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_glyph_annotation_groups(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
) -> str:
    """Return MCP-managed annotation groups for a glyph layer."""
    try:
        font, glyph, layer, error = _resolve_target(font_index, glyph_name, master_id)
        if error:
            return json.dumps(error)

        registry = _reconcile_registry(font, glyph, layer, persist=False)
        annotations = _annotation_list(layer)
        groups = {}
        for item in registry.get("items", []):
            if item.get("orphaned"):
                continue
            group_id = item.get("groupId") or ""
            if not group_id:
                continue
            try:
                index = int(item.get("lastIndex"))
            except Exception:
                continue
            if index < 0 or index >= len(annotations):
                continue
            group = groups.setdefault(
                group_id,
                {
                    "groupId": group_id,
                    "comment": item.get("comment", ""),
                    "annotations": [],
                },
            )
            group["annotations"].append(_annotation_payload(annotations[index], index, item))

        result = _target_summary(font, glyph_name, layer)
        result.update({"groupCount": len(groups), "groups": list(groups.values())})
        return _safe_json(result)
    except Exception as e:
        return json.dumps({"error": str(e)})
