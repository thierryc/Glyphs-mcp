"""Host-light navigation helpers for the v2 Changes panel."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from .change_review import ChangeOperation


MAX_REVIEW_GLYPHS = 500
TAB_DOCUMENT_KEY = "glyphsMCPChangeDocumentId"
TAB_OPERATION_KEY = "glyphsMCPChangeOperationId"


def _values(collection: Any) -> list[Any]:
    if collection is None:
        return []
    if isinstance(collection, Mapping):
        return list(collection.values())
    try:
        return list(collection)
    except Exception:
        return []


def _lookup_glyph(font: Any, name: str) -> Any:
    glyphs = getattr(font, "glyphs", None)
    try:
        glyph = glyphs[name]
        if glyph is not None:
            return glyph
    except Exception:
        pass
    for glyph in _values(glyphs):
        if str(getattr(glyph, "name", "") or "") == name:
            return glyph
    return None


def _lookup_layer(glyph: Any, *, layer_id: Optional[str], master_id: Optional[str]) -> Any:
    layers = getattr(glyph, "layers", None)
    for key in (layer_id, master_id):
        if not key:
            continue
        try:
            layer = layers[key]
            if layer is not None:
                return layer
        except Exception:
            pass
    for layer in _values(layers):
        native_layer_id = str(getattr(layer, "layerId", getattr(layer, "id", "")) or "")
        native_master_id = str(getattr(layer, "associatedMasterId", "") or native_layer_id)
        if layer_id and native_layer_id == str(layer_id):
            return layer
        if master_id and native_master_id == str(master_id):
            return layer
    if layer_id or master_id:
        return None
    values = _values(layers)
    return values[0] if values else None


def _tab_data(tab: Any) -> Any:
    data = getattr(tab, "tempData", None)
    if data is None:
        data = {}
        try:
            tab.tempData = data
        except Exception:
            pass
    return data


def _data_get(data: Any, key: str) -> Any:
    try:
        return data[key]
    except Exception:
        try:
            return data.objectForKey_(key)
        except Exception:
            return None


def _data_set(data: Any, key: str, value: Any) -> None:
    try:
        data[key] = value
    except Exception:
        try:
            data.setObject_forKey_(value, key)
        except Exception:
            pass


def open_changed_glyphs(font: Any, operation: ChangeOperation | Mapping[str, Any]) -> dict[str, Any]:
    value = operation if isinstance(operation, ChangeOperation) else ChangeOperation.from_mapping(operation)
    targets = value.glyph_targets()
    if not targets:
        return {"ok": False, "errorCode": "no_glyph_targets", "targetCount": 0}
    if len(targets) > MAX_REVIEW_GLYPHS:
        return {
            "ok": False,
            "errorCode": "too_many_review_targets",
            "targetCount": len(targets),
            "maximumTargetCount": MAX_REVIEW_GLYPHS,
        }

    layers = []
    missing = []
    for target in targets:
        name = str(target.get("glyphName") or "")
        glyph = _lookup_glyph(font, name)
        if glyph is None:
            missing.append(name)
            continue
        layer = _lookup_layer(
            glyph,
            layer_id=str(target.get("layerId") or "") or None,
            master_id=str(target.get("masterId") or "") or None,
        )
        if layer is None:
            missing.append(name)
            continue
        layers.append(layer)
    if not layers:
        return {
            "ok": False,
            "errorCode": "review_targets_unavailable",
            "targetCount": len(targets),
            "missingGlyphCount": len(missing),
            "missingGlyphNames": missing[:64],
        }

    tab = None
    for possible in _values(getattr(font, "tabs", None)):
        data = _tab_data(possible)
        if str(_data_get(data, TAB_DOCUMENT_KEY) or "") == value.document_id:
            tab = possible
            break
    reused_tab = tab is not None
    if tab is None:
        tab = font.newTab(layers)
    else:
        tab.layers = list(layers)
    data = _tab_data(tab)
    _data_set(data, TAB_DOCUMENT_KEY, value.document_id)
    _data_set(data, TAB_OPERATION_KEY, value.operation_id)
    font.currentTab = tab
    return {
        "ok": True,
        "operationId": value.operation_id,
        "openedGlyphCount": len(layers),
        "missingGlyphCount": len(missing),
        "missingGlyphNames": missing[:64],
        "reusedTab": reused_tab,
    }


__all__ = [
    "MAX_REVIEW_GLYPHS",
    "TAB_DOCUMENT_KEY",
    "TAB_OPERATION_KEY",
    "open_changed_glyphs",
]
