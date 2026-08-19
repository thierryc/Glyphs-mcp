"""Glyphs 3.5/4 document snapshots, staged Python, recovery, and write-back."""

from __future__ import annotations

import ast
import builtins
import copy
import contextlib
import difflib
import hashlib
import io
import json
import os
import re
import time
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Optional, Sequence

from ..canonical_collections import (
    canonical_glyph_id,
    collection_order,
    require_indexed_entities,
)
from ..exporting import inspect_destination, publish_staged_directory
from ..ports import HostAccessError
from ..python_execution import PythonExecutionRequest
from ..mutation import (
    MASTER_LIFECYCLE_CAPABILITY,
    MutationScope,
    mutation_scope,
    writable_subset,
)
from ..semantic import ChangeSet, diff_models, fingerprint_model
from .glyphs import (
    GlyphsHostAdapter,
    _maybe_call,
    _native_property,
    _native_unsaved_changes,
    _safe_getattr,
    _sequence_values,
    _set_native_property,
)


_FONT_SCALARS = ("familyName", "upm", "versionMajor", "versionMinor", "note", "grid", "gridSubDivision")
_GLYPH_SCALARS = ("category", "subCategory", "unicode", "export", "leftKerningGroup", "rightKerningGroup")
_LAYER_SCALARS = ("width", "LSB", "RSB", "leftMetricsKey", "rightMetricsKey", "widthMetricsKey")
_UUID_PATTERN = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
_NS_CHANGE_DONE = 0
_NS_CHANGE_UNDONE = 1


def _plain_scalar(value: Any) -> Any:
    value = _maybe_call(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _optional_text(value: Any) -> Optional[str]:
    """Canonicalize native absent-string spellings to one semantic value."""

    plain = _plain_scalar(value)
    if plain is None or plain == "":
        return None
    return str(plain)


def _point(value: Any) -> list[float]:
    try:
        return [float(value.x), float(value.y)]
    except Exception:
        try:
            return [float(value[0]), float(value[1])]
        except Exception:
            return [0.0, 0.0]


def _mapping_keys(value: Any) -> list[str]:
    if value is None:
        return []
    try:
        return sorted(str(key) for key in value.keys())
    except Exception:
        return []


def _mapping_get(value: Any, key: Any) -> Any:
    try:
        return value[key]
    except Exception:
        try:
            return value.objectForKey_(key)
        except Exception:
            return None


def _component_transform(component: Any) -> list[float]:
    transform = _safe_getattr(component, "transform")
    if transform is None:
        return [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    for names in (("m11", "m12", "m21", "m22", "tX", "tY"), ("a", "b", "c", "d", "tx", "ty")):
        values = [_safe_getattr(transform, name) for name in names]
        if all(value is not None for value in values):
            try:
                return [float(value) for value in values]
            except Exception:
                pass
    try:
        return [float(transform[index]) for index in range(6)]
    except Exception:
        return [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]


def _is_component(value: Any) -> bool:
    return _safe_getattr(value, "componentName") is not None


def _is_path(value: Any) -> bool:
    return _safe_getattr(value, "nodes") is not None and not _is_component(value)


def _layer_paths(layer: Any) -> list[Any]:
    paths = _sequence_values(_safe_getattr(layer, "paths"))
    if paths:
        return paths
    return [shape for shape in _sequence_values(_safe_getattr(layer, "shapes")) if _is_path(shape)]


def _layer_components(layer: Any) -> list[Any]:
    components = [shape for shape in _sequence_values(_safe_getattr(layer, "shapes")) if _is_component(shape)]
    if components:
        return components
    return [value for value in _sequence_values(_safe_getattr(layer, "components")) if _is_component(value)]


def _path_model(path: Any) -> dict[str, Any]:
    nodes = []
    for node in _sequence_values(_safe_getattr(path, "nodes")):
        precise_position = _maybe_call(_safe_getattr(node, "positionPrecise"))
        position = _point(
            precise_position
            if precise_position is not None
            else _safe_getattr(node, "position")
        )
        nodes.append(
            {
                "x": position[0],
                "y": position[1],
                "type": str(_safe_getattr(node, "type") or "line").lower(),
                "smooth": bool(_safe_getattr(node, "smooth", False)),
                "name": _optional_text(_safe_getattr(node, "name")),
            }
        )
    return {"closed": bool(_safe_getattr(path, "closed", True)), "nodes": nodes}


def _anchor_model(layer: Any) -> dict[str, list[float]]:
    anchors = _safe_getattr(layer, "anchors")
    result: dict[str, list[float]] = {}
    for anchor in _sequence_values(anchors):
        name = str(_safe_getattr(anchor, "name") or "")
        if name:
            result[name] = _point(_safe_getattr(anchor, "position"))
    if not result:
        for name in _mapping_keys(anchors):
            anchor = _mapping_get(anchors, name)
            if anchor is not None:
                result[name] = _point(_safe_getattr(anchor, "position"))
    return result


def _layer_model(layer: Any) -> dict[str, Any]:
    layer_id = str(_safe_getattr(layer, "layerId") or _safe_getattr(layer, "id") or "")
    master_id = str(_safe_getattr(layer, "associatedMasterId") or layer_id)
    values = {
        "id": layer_id,
        "masterId": master_id,
        "name": str(_safe_getattr(layer, "name") or ""),
        "isMasterLayer": bool(_maybe_call(_safe_getattr(layer, "isMasterLayer", False))),
        "isSpecialLayer": bool(_maybe_call(_safe_getattr(layer, "isSpecialLayer", False))),
        "hasAlignedWidth": bool(
            _maybe_call(_safe_getattr(layer, "hasAlignedWidth", False))
        ),
        "anchors": _anchor_model(layer),
        "paths": [_path_model(path) for path in _layer_paths(layer)],
        "components": [
            {
                "name": str(_safe_getattr(component, "componentName") or ""),
                "transform": _component_transform(component),
                "automaticAlignment": bool(
                    _maybe_call(
                        _safe_getattr(component, "automaticAlignment", False)
                    )
                ),
            }
            for component in _layer_components(layer)
        ],
    }
    values["pathSignature"] = [len(path["nodes"]) for path in values["paths"]]
    for name in _LAYER_SCALARS:
        values[name] = _plain_scalar(_safe_getattr(layer, name))
    return values


def native_layer_to_model(layer: Any) -> dict[str, Any]:
    """Return one detached canonical layer for drawing-only consumers."""

    return _layer_model(layer)


def _glyph_model(glyph: Any) -> dict[str, Any]:
    name = str(_safe_getattr(glyph, "name") or "")
    layers: dict[str, Any] = {}
    for layer in _sequence_values(_safe_getattr(glyph, "layers")):
        model = _layer_model(layer)
        key = model["masterId"] or model["id"]
        if key:
            if key in layers:
                key = model["id"] or "{}#{}".format(key, len(layers))
            layers[key] = model
    result = {
        "name": name,
        # Native glyph UUIDs can be regenerated after deletion. The glyph map
        # is already name-keyed, so its canonical identity must be semantic.
        "id": canonical_glyph_id(name),
        "mastersCompatible": bool(_maybe_call(_safe_getattr(glyph, "mastersCompatible", False))),
        "layers": layers,
    }
    for scalar in _GLYPH_SCALARS:
        result[scalar] = _plain_scalar(_safe_getattr(glyph, scalar))
    return result


def _axis_models(font: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": str(_safe_getattr(axis, "axisId") or _safe_getattr(axis, "id") or ""),
            "name": str(_safe_getattr(axis, "name") or ""),
            "tag": str(_safe_getattr(axis, "axisTag") or _safe_getattr(axis, "tag") or ""),
        }
        for axis in _sequence_values(_safe_getattr(font, "axes"))
    ]


def _master_models(font: Any) -> list[dict[str, Any]]:
    axes = _axis_models(font)
    result = []
    for master in _sequence_values(_safe_getattr(font, "masters")):
        positions = _sequence_values(_safe_getattr(master, "axes"))
        result.append(
            {
                "id": str(_safe_getattr(master, "id") or ""),
                "name": str(_safe_getattr(master, "name") or ""),
                "italicAngle": _plain_scalar(_safe_getattr(master, "italicAngle")),
                "axes": [
                    {"tag": axis.get("tag"), "internal": _plain_scalar(positions[index]) if index < len(positions) else None}
                    for index, axis in enumerate(axes)
                ],
            }
        )
    return result


def _instance_models(
    font: Any, *, instance_ids: Optional[Sequence[str]] = None
) -> list[dict[str, Any]]:
    axes = _axis_models(font)
    result = []
    native_instances = _sequence_values(_safe_getattr(font, "instances"))
    if instance_ids is not None and len(instance_ids) != len(native_instances):
        raise HostAccessError("canonical instance identity count does not match Glyphs")
    for index, instance in enumerate(native_instances):
        raw_type = _plain_scalar(_safe_getattr(instance, "type"))
        is_variable = str(raw_type).lower() in {"variable", "1", "gsinstancetypevariable"}
        positions = _sequence_values(_safe_getattr(instance, "internalAxesValues"))
        if not positions:
            positions = _sequence_values(_safe_getattr(instance, "axes"))
        external_positions = _sequence_values(
            _safe_getattr(instance, "externalAxesValues")
        )
        if not external_positions:
            external_positions = _sequence_values(_safe_getattr(instance, "externalAxes"))
        if not external_positions:
            external_positions = _sequence_values(
                _safe_getattr(instance, "externalAxisCoordinates")
            )
        included_value = _safe_getattr(instance, "active")
        if included_value is None:
            included_value = _safe_getattr(instance, "exports", True)
        result.append(
            {
                # Glyphs 4 regenerates native GSInstance UUIDs in GSFont.copy().
                # Use the ordered collection identity in the canonical model so
                # a detached clone does not manufacture a semantic change.
                "id": str(instance_ids[index])
                if instance_ids is not None
                else "instance_{}".format(index),
                "name": str(_safe_getattr(instance, "name") or ""),
                "type": "variable" if is_variable else "static",
                "included": bool(_maybe_call(included_value)),
                "inclusionReason": None,
                "interpolationSupported": not is_variable,
                "axes": [
                    {
                        "tag": axis.get("tag"),
                        "internal": _plain_scalar(positions[axis_index]) if axis_index < len(positions) else None,
                        "external": _plain_scalar(external_positions[axis_index])
                        if axis_index < len(external_positions)
                        else None,
                    }
                    for axis_index, axis in enumerate(axes)
                ],
            }
        )
    return result


def _code_collection(font: Any, attribute: str) -> list[dict[str, Any]]:
    return [
        {
            "id": str(_safe_getattr(value, "name") or "{}_{}".format(attribute, index)),
            "name": str(_safe_getattr(value, "name") or ""),
            "code": str(_safe_getattr(value, "code") or ""),
            "automatic": bool(
                _native_property(value, "automatic", False, objc_boolean=True)
            ),
            "disabled": bool(
                _native_property(value, "disabled", False, objc_boolean=True)
            ),
        }
        for index, value in enumerate(_sequence_values(_safe_getattr(font, attribute)))
    ]


def _kerning_model(font: Any) -> dict[str, dict[str, dict[str, float]]]:
    result: dict[str, dict[str, dict[str, float]]] = {}
    canonical_keys: dict[str, str] = {}
    for glyph in _sequence_values(_safe_getattr(font, "glyphs")):
        name = str(_safe_getattr(glyph, "name") or "")
        if not name:
            continue
        canonical = canonical_glyph_id(name)
        canonical_keys[name] = canonical
        native_id = str(_maybe_call(_safe_getattr(glyph, "id")) or "")
        if native_id:
            canonical_keys[native_id] = canonical
    kerning = _safe_getattr(font, "kerning")
    for master_id in _mapping_keys(kerning):
        lefts = _mapping_get(kerning, master_id)
        for left in _mapping_keys(lefts):
            rights = _mapping_get(lefts, left)
            for right in _mapping_keys(rights):
                try:
                    numeric = float(_mapping_get(rights, right))
                except Exception:
                    continue
                canonical_left = canonical_keys.get(left, left)
                canonical_right = canonical_keys.get(right, right)
                result.setdefault(master_id, {}).setdefault(canonical_left, {})[
                    canonical_right
                ] = numeric
    return result


def _font_model_with_glyphs(
    font: Any,
    glyphs: Mapping[str, Any],
    *,
    masters: Optional[Sequence[Mapping[str, Any]]] = None,
    instance_ids: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    return {
        "font": {name: _plain_scalar(_safe_getattr(font, name)) for name in _FONT_SCALARS},
        "masters": list(masters) if masters is not None else _master_models(font),
        "instances": _instance_models(font, instance_ids=instance_ids),
        "glyphs": dict(glyphs),
        "kerning": _kerning_model(font),
        "features": _code_collection(font, "features"),
        "classes": _code_collection(font, "classes"),
        "featurePrefixes": _code_collection(font, "featurePrefixes"),
    }


def native_font_to_model(
    font: Any, *, instance_ids: Optional[Sequence[str]] = None
) -> dict[str, Any]:
    glyphs = {}
    for glyph in _sequence_values(_safe_getattr(font, "glyphs")):
        model = _glyph_model(glyph)
        if model["name"]:
            glyphs[model["name"]] = model
    return _font_model_with_glyphs(font, glyphs, instance_ids=instance_ids)


def _glyph_layer_structure(glyph: Any) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            str(_safe_getattr(layer, "layerId") or _safe_getattr(layer, "id") or ""),
            str(_safe_getattr(layer, "associatedMasterId") or ""),
        )
        for layer in _sequence_values(_safe_getattr(glyph, "layers"))
    )


def _glyph_revision_token(glyph: Any) -> tuple[Any, ...]:
    return (
        str(_safe_getattr(glyph, "name") or ""),
        str(_safe_getattr(glyph, "id") or ""),
        str(_plain_scalar(_safe_getattr(glyph, "lastChange")) or ""),
        _plain_scalar(_maybe_call(_safe_getattr(glyph, "changeCount"))),
        _glyph_layer_structure(glyph),
    )


def _glyph_revision_index(font: Any) -> dict[str, tuple[Any, ...]]:
    result: dict[str, tuple[Any, ...]] = {}
    for glyph in _sequence_values(_safe_getattr(font, "glyphs")):
        token = _glyph_revision_token(glyph)
        if token[0]:
            result[str(token[0])] = token
    return result


class _RevisionBoundGlyphModelCache:
    """Reuse detached glyph trees only while native revision evidence agrees.

    Paths and components dominate live canonical capture cost. Glyphs updates a
    glyph's ``lastChange`` when its own layers or derived metrics change; layer
    membership and the ordered master identity are included independently so a
    structural collection change cannot reuse an incompatible glyph tree.
    Agent-owned writes invalidate the document explicitly before verification.
    """

    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def invalidate(self, document_id: str) -> None:
        with self._lock:
            self._documents.pop(document_id, None)

    def invalidate_glyphs(
        self, document_id: str, glyph_names: Sequence[str]
    ) -> None:
        with self._lock:
            document = self._documents.get(document_id)
            if document is None:
                return
            glyphs = document.get("glyphs", {})
            for name in glyph_names:
                glyphs.pop(str(name), None)

    def capture(
        self,
        document_id: str,
        font: Any,
        *,
        instance_ids: Optional[Sequence[str]] = None,
    ) -> dict[str, Any]:
        masters = _master_models(font)
        master_structure = tuple(str(master.get("id") or "") for master in masters)
        with self._lock:
            previous = self._documents.get(document_id)
            previous_glyphs = (
                previous.get("glyphs", {})
                if previous is not None
                and previous.get("masterStructure") == master_structure
                else {}
            )
            current_glyphs: dict[str, dict[str, Any]] = {}
            result_glyphs: dict[str, Any] = {}
            for glyph in _sequence_values(_safe_getattr(font, "glyphs")):
                token = _glyph_revision_token(glyph)
                name = str(token[0])
                if not name:
                    continue
                cached = previous_glyphs.get(name)
                if cached is not None and cached.get("token") == token:
                    model = copy.deepcopy(cached["model"])
                else:
                    model = _glyph_model(glyph)
                result_glyphs[name] = model
                current_glyphs[name] = {
                    "token": token,
                    "model": copy.deepcopy(model),
                }
            self._documents[document_id] = {
                "masterStructure": master_structure,
                "glyphs": current_glyphs,
            }
        return _font_model_with_glyphs(
            font,
            result_glyphs,
            masters=masters,
            instance_ids=instance_ids,
        )


def _lookup_by_name(collection: Any, name: str) -> Any:
    value = _mapping_get(collection, name)
    if value is not None:
        return value
    for item in _sequence_values(collection):
        if str(_safe_getattr(item, "name") or "") == name:
            return item
    return None


def _lookup_layer(glyph: Any, key: str) -> Any:
    layers = _safe_getattr(glyph, "layers")
    value = _mapping_get(layers, key)
    if value is not None:
        return value
    for layer in _sequence_values(layers):
        if key in {str(_safe_getattr(layer, "layerId") or ""), str(_safe_getattr(layer, "associatedMasterId") or "")}:
            return layer
    return None


def _scoped_font_model(
    font: Any,
    base_model: Mapping[str, Any],
    scope: MutationScope,
    *,
    extra_glyph_names: Sequence[str] = (),
    instance_ids: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Refresh one canonical tree from native state without rebuilding every glyph."""

    result = copy.deepcopy(dict(base_model))
    non_glyph = _font_model_with_glyphs(font, {}, instance_ids=instance_ids)
    for root, value in non_glyph.items():
        if root != "glyphs":
            result[root] = value

    base_glyphs = result.get("glyphs", {})
    if not isinstance(base_glyphs, dict):
        raise HostAccessError("The canonical glyph model is not keyed by name")
    native_index = {
        str(_safe_getattr(glyph, "name") or ""): glyph
        for glyph in _sequence_values(_safe_getattr(font, "glyphs"))
        if str(_safe_getattr(glyph, "name") or "")
    }
    removed = set(base_glyphs) - set(native_index)
    added = set(native_index) - set(base_glyphs)
    for name in removed:
        base_glyphs.pop(name, None)
    for name in added:
        base_glyphs[name] = _glyph_model(native_index[name])
    for name in sorted(set(scope.glyph_names) | {str(value) for value in extra_glyph_names}):
        glyph = native_index.get(name)
        if glyph is None:
            # A collection insertion scopes the future identity before it
            # exists in either the canonical source or the detached clone.
            # Existing identities that disappeared are represented by
            # ``removed``. Request validation owns missing update/delete
            # targets; capture only reflects the native collection it sees.
            continue
        base_glyphs[name] = _glyph_model(glyph)
    return result


def _changed_revision_glyphs(
    before: Mapping[str, tuple[Any, ...]],
    after: Mapping[str, tuple[Any, ...]],
) -> tuple[str, ...]:
    return tuple(
        name
        for name in sorted(set(before) | set(after))
        if before.get(name) != after.get(name)
    )


def _staged_context_violations(
    request: PythonExecutionRequest,
    changes: ChangeSet,
    *,
    model: Optional[Mapping[str, Any]] = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Bound changes that escaped an explicitly injected glyph/layer context."""

    if not request.glyph_name:
        return {"count": 0, "paths": [], "truncated": False}

    allowed_layers = {
        value for value in (request.layer_id, request.master_id) if value
    }
    glyphs = model.get("glyphs", {}) if isinstance(model, Mapping) else {}
    glyph = glyphs.get(request.glyph_name, {}) if isinstance(glyphs, Mapping) else {}
    layers = glyph.get("layers", {}) if isinstance(glyph, Mapping) else {}
    if isinstance(layers, Mapping):
        for key, layer in layers.items():
            if not isinstance(layer, Mapping):
                continue
            identities = {
                str(key),
                str(layer.get("id") or ""),
                str(layer.get("masterId") or ""),
            }
            if identities & allowed_layers:
                allowed_layers.add(str(key))
    violations: list[tuple[str, ...]] = []
    for change in changes.changes:
        path = change.path
        allowed = (
            len(path) >= 2
            and path[0] == "glyphs"
            and path[1] == request.glyph_name
        )
        if allowed and allowed_layers:
            # mastersCompatible is a host-derived consequence of a layer edit.
            allowed = (
                len(path) == 3 and path[2] == "mastersCompatible"
            ) or (
                len(path) >= 4
                and path[2] == "layers"
                and path[3] in allowed_layers
            )
        if not allowed:
            violations.append(path)

    bounded_limit = max(0, min(100, int(limit)))
    return {
        "count": len(violations),
        "paths": [list(path) for path in violations[:bounded_limit]],
        "truncated": len(violations) > bounded_limit,
    }


def _replace_collection(collection: Any, values: Sequence[Any]) -> None:
    try:
        collection[:] = list(values)
        return
    except Exception:
        pass
    try:
        while len(collection):
            del collection[len(collection) - 1]
        for value in values:
            collection.append(value)
    except Exception as exc:
        raise HostAccessError("Glyphs rejected collection replacement") from exc


def _replace_layer_shape_kind(
    layer: Any,
    values: Sequence[Any],
    *,
    matches: Any,
    kind: str,
) -> None:
    """Replace one canonical shape kind through GSLayer.shapes.

    Glyphs 3/4 exposes ``paths`` and ``components`` as read-only iteration
    proxies. ``shapes`` is the authoritative ordered mutable collection. The
    current canonical schema records the order inside each kind, but not a new
    cross-kind order, so collection replay may replace existing slots only.
    """

    collection = _safe_getattr(layer, "shapes")
    if collection is None:
        raise HostAccessError("Glyphs did not expose the writable layer.shapes store")
    shapes = _sequence_values(collection)
    indices = [index for index, shape in enumerate(shapes) if matches(shape)]
    if len(indices) != len(values):
        raise HostAccessError(
            "Canonical {} replay cannot change shape membership without an ordered shape model".format(
                kind
            )
        )
    for index, value in zip(indices, values):
        shapes[index] = value
    try:
        _set_native_property(layer, "shapes", list(shapes))
    except Exception:
        _replace_collection(collection, shapes)


def _new_anchor(name: str, position: Sequence[float]) -> Any:
    try:
        from GlyphsApp import GSAnchor  # type: ignore[import-not-found]
    except Exception as exc:
        raise HostAccessError("GSAnchor is unavailable") from exc
    try:
        return GSAnchor(name, (float(position[0]), float(position[1])))
    except Exception:
        anchor = GSAnchor()
        _set_native_property(anchor, "name", name)
        _set_native_property(
            anchor, "position", (float(position[0]), float(position[1]))
        )
        return anchor


def _replace_anchors(layer: Any, anchors: Mapping[str, Sequence[float]]) -> None:
    collection = _safe_getattr(layer, "anchors")
    for name in _mapping_keys(collection):
        try:
            del collection[name]
        except Exception:
            existing = _mapping_get(collection, name)
            try:
                collection.remove(existing)
            except Exception:
                pass
    for name in sorted(anchors):
        anchor = _new_anchor(name, anchors[name])
        try:
            collection.append(anchor)
        except Exception:
            collection[name] = anchor


def _new_path(spec: Mapping[str, Any]) -> Any:
    try:
        from GlyphsApp import CURVE, LINE, OFFCURVE, QCURVE, GSNode, GSPath  # type: ignore[import-not-found]
    except Exception as exc:
        raise HostAccessError("Glyphs path classes are unavailable") from exc
    types = {"curve": CURVE, "line": LINE, "offcurve": OFFCURVE, "qcurve": QCURVE}
    path = GSPath()
    nodes = []
    for node_spec in spec.get("nodes", []):
        node_type = types.get(str(node_spec.get("type") or "line").lower(), LINE)
        try:
            node = GSNode((float(node_spec.get("x", 0)), float(node_spec.get("y", 0))), node_type)
        except Exception:
            node = GSNode()
            _set_native_property(
                node,
                "position",
                (float(node_spec.get("x", 0)), float(node_spec.get("y", 0))),
            )
            _set_native_property(node, "type", node_type)
        try:
            _set_native_property(node, "smooth", bool(node_spec.get("smooth", False)))
        except Exception:
            pass
        # GSNode.name is not a normal nullable NSString bridge: assigning
        # Python None stores the literal text "None". Preserve the native
        # unnamed default and assign only a real canonical name.
        node_name = _optional_text(node_spec.get("name"))
        if node_name is not None:
            try:
                _set_native_property(node, "name", node_name)
            except Exception:
                pass
        nodes.append(node)
    _replace_collection(path.nodes, nodes)
    _set_native_property(path, "closed", bool(spec.get("closed", True)))
    return path


def _update_paths_in_place(
    layer: Any,
    current_specs: Sequence[Mapping[str, Any]],
    target_specs: Sequence[Mapping[str, Any]],
) -> bool:
    """Apply topology-compatible node changes without replacing native shapes."""

    native_paths = _layer_paths(layer)
    if len(native_paths) != len(current_specs) or len(current_specs) != len(target_specs):
        return False

    updates: list[tuple[Any, Mapping[str, Any], Mapping[str, Any]]] = []
    for native_path, current_path, target_path in zip(native_paths, current_specs, target_specs):
        if bool(current_path.get("closed", True)) != bool(target_path.get("closed", True)):
            return False
        if bool(_safe_getattr(native_path, "closed", True)) != bool(current_path.get("closed", True)):
            return False
        native_nodes = _sequence_values(_safe_getattr(native_path, "nodes"))
        current_nodes = current_path.get("nodes", [])
        target_nodes = target_path.get("nodes", [])
        if len(native_nodes) != len(current_nodes) or len(current_nodes) != len(target_nodes):
            return False
        for native_node, current_node, target_node in zip(native_nodes, current_nodes, target_nodes):
            current_type = str(current_node.get("type") or "line").lower()
            target_type = str(target_node.get("type") or "line").lower()
            native_type = str(_safe_getattr(native_node, "type") or "line").lower()
            if current_type != target_type or native_type != current_type:
                return False
            updates.append((native_node, current_node, target_node))

    for native_node, current_node, target_node in updates:
        current_position = (
            float(current_node.get("x", 0)),
            float(current_node.get("y", 0)),
        )
        target_position = (
            float(target_node.get("x", 0)),
            float(target_node.get("y", 0)),
        )
        if current_position != target_position:
            _set_native_property(native_node, "position", target_position)
        if bool(current_node.get("smooth", False)) != bool(target_node.get("smooth", False)):
            _set_native_property(
                native_node, "smooth", bool(target_node.get("smooth", False))
            )
        if current_node.get("name") != target_node.get("name"):
            _set_native_property(
                native_node, "name", str(target_node.get("name") or "")
            )
    return True


def _replace_paths(layer: Any, specs: Sequence[Mapping[str, Any]]) -> None:
    paths = [_new_path(spec) for spec in specs]
    _replace_layer_shape_kind(
        layer,
        paths,
        matches=_is_path,
        kind="path",
    )


def _new_component(spec: Mapping[str, Any]) -> Any:
    try:
        from GlyphsApp import GSComponent  # type: ignore[import-not-found]
    except Exception as exc:
        raise HostAccessError("GSComponent is unavailable") from exc
    name = str(spec.get("name") or "")
    try:
        component = GSComponent(name)
    except Exception:
        component = GSComponent()
        _set_native_property(component, "componentName", name)
    transform = spec.get("transform")
    if isinstance(transform, Sequence) and len(transform) == 6:
        _set_native_property(
            component, "transform", tuple(float(value) for value in transform)
        )
    if "automaticAlignment" in spec:
        _set_native_property(
            component,
            "automaticAlignment",
            bool(spec.get("automaticAlignment")),
        )
    return component


def _update_components_in_place(
    layer: Any,
    current_specs: Sequence[Mapping[str, Any]],
    target_specs: Sequence[Mapping[str, Any]],
) -> bool:
    """Update topology-compatible components without replacing Glyphs proxies."""

    native_components = _layer_components(layer)
    if (
        len(native_components) != len(current_specs)
        or len(current_specs) != len(target_specs)
    ):
        return False
    updates: list[tuple[Any, tuple[float, ...], Optional[bool]]] = []
    for native, current, target in zip(
        native_components, current_specs, target_specs
    ):
        current_name = str(current.get("name") or "")
        target_name = str(target.get("name") or "")
        native_name = str(_safe_getattr(native, "componentName") or "")
        if current_name != target_name or native_name != current_name:
            return False
        transform = target.get("transform")
        if not isinstance(transform, Sequence) or len(transform) != 6:
            return False
        try:
            alignment = (
                bool(target.get("automaticAlignment"))
                if "automaticAlignment" in target
                else None
            )
            updates.append(
                (native, tuple(float(value) for value in transform), alignment)
            )
        except (TypeError, ValueError):
            return False
    for native, transform, alignment in updates:
        if tuple(_component_transform(native)) != transform:
            _set_native_property(native, "transform", transform)
        if alignment is not None and bool(
            _maybe_call(_safe_getattr(native, "automaticAlignment", False))
        ) != alignment:
            _set_native_property(native, "automaticAlignment", alignment)
    return True


def _replace_components(layer: Any, specs: Sequence[Mapping[str, Any]]) -> None:
    components = [_new_component(spec) for spec in specs]
    _replace_layer_shape_kind(
        layer,
        components,
        matches=_is_component,
        kind="component",
    )


def _kerning_key(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("id") or value.get("name") or "")
    return str(value)


def _native_kerning_key(font: Any, value: str) -> str:
    if value.startswith("@"):
        return value
    glyphs = _safe_getattr(font, "glyphs")
    by_name = _lookup_by_name(glyphs, value)
    if by_name is not None:
        return value
    for glyph in _sequence_values(glyphs):
        name = str(_safe_getattr(glyph, "name") or "")
        native_id = str(_maybe_call(_safe_getattr(glyph, "id")) or "")
        if name and value in {canonical_glyph_id(name), native_id}:
            return name
    raise HostAccessError("Kerning key could not be resolved to a glyph name: {}".format(value))


def _replace_kerning(font: Any, target_pairs: Any) -> None:
    current_model = _kerning_model(font)
    current = {
        (master_id, left, right): value
        for master_id, lefts in current_model.items()
        for left, rights in lefts.items()
        for right, value in rights.items()
    }
    if isinstance(target_pairs, Mapping):
        target = {
            (str(master_id), str(left), str(right)): value
            for master_id, lefts in target_pairs.items()
            if isinstance(lefts, Mapping)
            for left, rights in lefts.items()
            if isinstance(rights, Mapping)
            for right, value in rights.items()
        }
    else:
        target = {
            (str(pair.get("masterId") or ""), _kerning_key(pair.get("left")), _kerning_key(pair.get("right"))): pair.get("value")
            for pair in target_pairs
        }
    remove = _safe_getattr(font, "removeKerningForPair")
    for key in sorted(set(current) - set(target)):
        if callable(remove):
            remove(
                key[0],
                _native_kerning_key(font, key[1]),
                _native_kerning_key(font, key[2]),
            )
    setter = _safe_getattr(font, "setKerningForPair")
    if not callable(setter):
        raise HostAccessError("Glyphs did not expose setKerningForPair")
    for key in sorted(target):
        if current.get(key) != target[key]:
            setter(
                key[0],
                _native_kerning_key(font, key[1]),
                _native_kerning_key(font, key[2]),
                float(target[key]),
            )


def _remove_native_collection_item(collection: Any, index: int, value: Any) -> None:
    try:
        del collection[index]
        return
    except Exception:
        pass
    remover = _safe_getattr(collection, "removeObjectAtIndex_")
    if callable(remover):
        remover(index)
        return
    remover = _safe_getattr(collection, "remove")
    if callable(remover):
        remover(value)
        return
    raise HostAccessError("Glyphs collection does not support removal")


def _append_native_collection_item(collection: Any, value: Any) -> None:
    appender = _safe_getattr(collection, "append")
    if callable(appender):
        appender(value)
        return
    appender = _safe_getattr(collection, "addObject_")
    if callable(appender):
        appender(value)
        return
    raise HostAccessError("Glyphs collection does not support append")


def _replace_native_collection_order(collection: Any, values: Sequence[Any]) -> None:
    desired = list(values)
    # Glyphs list proxies expose one whole-collection setter backed by the
    # native ``set…_`` contract. Prefer it over slice assignment: ListProxy
    # implements slices as repeated member replacement, which can detach and
    # reattach live objects and thereby recompute unrelated derived state.
    atomic_setter = _safe_getattr(collection, "setter")
    if callable(atomic_setter):
        atomic_setter(desired)
        return
    try:
        collection[:] = desired
        return
    except Exception:
        pass
    current = _sequence_values(collection)
    for index in reversed(range(len(current))):
        _remove_native_collection_item(collection, index, current[index])
    for value in desired:
        _append_native_collection_item(collection, value)


def _construct_native_entity(kind: str, name: str = "") -> Any:
    """Create one native entity behind a single testable SDK boundary."""

    try:
        from GlyphsApp import (  # type: ignore[import-not-found]
            GSClass,
            GSFeature,
            GSFeaturePrefix,
            GSGlyph,
            GSInstance,
        )
    except Exception as exc:
        raise HostAccessError("Glyphs native entity classes are unavailable") from exc
    classes = {
        "glyph": GSGlyph,
        "instance": GSInstance,
        "features": GSFeature,
        "classes": GSClass,
        "featurePrefixes": GSFeaturePrefix,
    }
    constructor = classes.get(kind)
    if constructor is None:
        raise HostAccessError("unsupported native entity kind: {}".format(kind))
    for arguments in ((name,), ()):
        try:
            value = constructor(*arguments)
            break
        except Exception:
            value = None
    if value is None:
        raise HostAccessError("Glyphs could not create a native {}".format(kind))
    if name and str(_safe_getattr(value, "name") or "") != name:
        _set_native_property(value, "name", name)
    return value


def _sync_native_entities(
    collection: Any,
    current: Sequence[Mapping[str, Any]],
    target: Sequence[Mapping[str, Any]],
    *,
    kind: str,
) -> dict[str, Any]:
    current_order, _ = require_indexed_entities(current, kind)
    target_order, target_entities = require_indexed_entities(target, kind)
    native_values = _sequence_values(collection)
    if len(native_values) != len(current_order):
        raise HostAccessError("Glyphs {} collection diverged before mutation".format(kind))
    native_by_id = {
        identity: native_values[index]
        for index, identity in enumerate(current_order)
    }
    for identity in reversed(current_order):
        if identity in target_entities:
            continue
        value = native_by_id.pop(identity)
        index = _sequence_values(collection).index(value)
        _remove_native_collection_item(collection, index, value)
    for identity in target_order:
        if identity in native_by_id:
            continue
        entity = target_entities[identity]
        entity_name = str(entity.get("name") or identity)
        value = _construct_native_entity(kind, entity_name)
        if str(_safe_getattr(value, "name") or "") != entity_name:
            _set_native_property(value, "name", entity_name)
        native_by_id[identity] = value
        _append_native_collection_item(collection, value)
    _replace_native_collection_order(
        collection, [native_by_id[identity] for identity in target_order]
    )
    return native_by_id


def _apply_code_collection(
    font: Any,
    attribute: str,
    current: Sequence[Mapping[str, Any]],
    target: Sequence[Mapping[str, Any]],
) -> None:
    """Apply membership, order, and scalar fields through one collection path."""

    collection = _safe_getattr(font, attribute)
    native_by_id = _sync_native_entities(
        collection, current, target, kind=attribute
    )
    _, current_entities = require_indexed_entities(current, attribute)
    target_order, target_entities = require_indexed_entities(target, attribute)
    for identity in target_order:
        native = native_by_id[identity]
        before = current_entities.get(identity, {})
        after = target_entities[identity]
        if str(_safe_getattr(native, "name") or "") != str(after.get("name") or ""):
            _set_native_property(native, "name", str(after.get("name") or ""))
        # Automatic mode is applied first. Custom code is legal only in the
        # resulting manual state, as enforced by the pure request builder.
        if before.get("automatic") != after.get("automatic"):
            _set_native_property(native, "automatic", bool(after.get("automatic")))
        if before.get("code") != after.get("code"):
            _set_native_property(native, "code", str(after.get("code") or ""))
        if before.get("disabled") != after.get("disabled"):
            _set_native_property(native, "disabled", bool(after.get("disabled")))


def _apply_instance_collection(
    font: Any,
    current: Sequence[Mapping[str, Any]],
    target: Sequence[Mapping[str, Any]],
) -> None:
    collection = _safe_getattr(font, "instances")
    native_by_id = _sync_native_entities(
        collection, current, target, kind="instance"
    )
    _, current_entities = require_indexed_entities(current, "instances")
    target_order, target_entities = require_indexed_entities(target, "instances")
    try:
        from GlyphsApp import INSTANCETYPEVARIABLE  # type: ignore[import-not-found]
    except Exception:
        INSTANCETYPEVARIABLE = 1
    for identity in target_order:
        native = native_by_id[identity]
        before = current_entities.get(identity, {})
        after = target_entities[identity]
        if before.get("name") != after.get("name"):
            _set_native_property(native, "name", str(after.get("name") or ""))
        if before.get("type") != after.get("type"):
            _set_native_property(
                native,
                "type",
                INSTANCETYPEVARIABLE if after.get("type") == "variable" else 0,
            )
        if before.get("included") != after.get("included"):
            if _safe_getattr(native, "active") is not None:
                _set_native_property(native, "active", bool(after.get("included")))
            else:
                _set_native_property(native, "exports", bool(after.get("included")))
        if before.get("axes") != after.get("axes"):
            axes = list(after.get("axes") or [])
            internal = [axis.get("internal") for axis in axes]
            if _safe_getattr(native, "internalAxesValues") is not None:
                _set_native_property(native, "internalAxesValues", internal)
            else:
                _set_native_property(native, "axes", internal)
            external = [axis.get("external") for axis in axes]
            if any(value is not None for value in external):
                if _safe_getattr(native, "externalAxesValues") is not None:
                    _set_native_property(native, "externalAxesValues", external)
                elif _safe_getattr(native, "externalAxes") is not None:
                    _set_native_property(native, "externalAxes", external)
                elif _safe_getattr(native, "externalAxisCoordinates") is not None:
                    _set_native_property(native, "externalAxisCoordinates", external)


def _copy_native_object(value: Any, *, kind: str) -> Any:
    copier = _safe_getattr(value, "copy")
    if callable(copier):
        copied = copier()
        if copied is not None:
            return copied
    try:
        return copy.copy(value)
    except Exception as exc:
        raise HostAccessError("Glyphs could not copy native {} state".format(kind)) from exc


def _set_native_scalar_if_changed(value: Any, name: str, target: Any) -> bool:
    """Write a canonical scalar only when the native value actually differs.

    Objective-C setters are not guaranteed to be inert when assigned their
    current value. Structural replay therefore compares the retained native
    object itself instead of assuming that a newly added canonical entity has
    no pre-existing state.
    """

    if _plain_scalar(_safe_getattr(value, name)) == _plain_scalar(target):
        return False
    _set_native_property(value, name, target)
    return True


def _master_by_id(font: Any, master_id: str) -> Any:
    for master in _sequence_values(_safe_getattr(font, "masters")):
        if str(_safe_getattr(master, "id") or "") == str(master_id):
            return master
    return None


def _set_glyph_master_layer(glyph: Any, master_id: str, layer: Any) -> None:
    _set_native_scalar_if_changed(layer, "associatedMasterId", master_id)
    _set_native_scalar_if_changed(layer, "layerId", master_id)
    layers = _safe_getattr(glyph, "layers")
    try:
        layers[master_id] = layer
        return
    except Exception:
        pass
    setter = _safe_getattr(glyph, "setLayer_forId_")
    if callable(setter):
        setter(layer, master_id)
        return
    raise HostAccessError("Glyphs could not assign a master layer")


def _apply_layer_canonical_pass(
    layer: Any,
    current_layer: Mapping[str, Any],
    target_layer: Mapping[str, Any],
    *,
    layer_root: Sequence[str],
    replacement_roots: Sequence[Sequence[str]] = (),
) -> None:
    replacement_set = {
        tuple(str(part) for part in path) for path in replacement_roots
    }
    begin = _safe_getattr(layer, "beginChanges")
    end = _safe_getattr(layer, "endChanges")
    if callable(begin):
        begin()
    try:
        metrics_key_changed = any(
            current_layer.get(field) != target_layer.get(field)
            for field in (
                "leftMetricsKey",
                "rightMetricsKey",
                "widthMetricsKey",
            )
        )
        for scalar in (
            "leftMetricsKey",
            "rightMetricsKey",
            "widthMetricsKey",
        ):
            if current_layer.get(scalar) != target_layer.get(scalar):
                _set_native_property(layer, scalar, target_layer.get(scalar))
        if metrics_key_changed:
            sync_metrics = _safe_getattr(layer, "syncMetrics")
            if not callable(sync_metrics):
                raise HostAccessError(
                    "Glyphs did not expose GSLayer.syncMetrics for a metrics-key update"
                )
            sync_metrics()
        shape_geometry_changed = any(
            current_layer.get(field) != target_layer.get(field)
            for field in ("paths", "components")
        )
        # LSB/RSB setters move or resize native geometry. When the semantic
        # patch carries explicit shapes, those shapes remain authoritative.
        if not shape_geometry_changed:
            for scalar in ("LSB", "RSB"):
                if current_layer.get(scalar) != target_layer.get(scalar):
                    _set_native_property(layer, scalar, target_layer.get(scalar))
        if current_layer.get("anchors") != target_layer.get("anchors"):
            _replace_anchors(layer, target_layer.get("anchors", {}))
        if current_layer.get("paths") != target_layer.get("paths"):
            current_paths = current_layer.get("paths", [])
            target_paths = target_layer.get("paths", [])
            collection_root = tuple(layer_root) + ("paths",)
            if collection_root in replacement_set:
                _replace_paths(layer, target_paths)
            elif not _update_paths_in_place(layer, current_paths, target_paths):
                _replace_paths(layer, target_paths)
        if current_layer.get("components") != target_layer.get("components"):
            current_components = current_layer.get("components", [])
            target_components = target_layer.get("components", [])
            collection_root = tuple(layer_root) + ("components",)
            if collection_root in replacement_set:
                _replace_components(layer, target_components)
            elif not _update_components_in_place(
                layer, current_components, target_components
            ):
                _replace_components(layer, target_components)
        # Width is stable last: bearings and absolute outline replay can both
        # invalidate an earlier assignment.
        if current_layer.get("width") != target_layer.get("width"):
            _set_native_property(layer, "width", target_layer.get("width"))
    finally:
        if callable(end):
            end()


def _reconcile_layer_to_canonical_target(
    layer: Any,
    current_layer: Mapping[str, Any],
    target_layer: Mapping[str, Any],
    *,
    layer_root: Sequence[str],
    replacement_roots: Sequence[Sequence[str]] = (),
    max_passes: int = 1,
) -> None:
    """Converge one native layer through a bounded canonical fixed point.

    Glyphs may derive metrics after geometry or attachment changes. Structural
    creation and ordinary field updates therefore share the same local
    read/apply boundary. The outer document transaction remains responsible
    for rejecting any layer that does not converge to its complete target.
    """

    state = copy.deepcopy(dict(current_layer))
    target = copy.deepcopy(dict(target_layer))
    seen: set[str] = set()
    for _ in range(max(1, min(3, int(max_passes)))):
        if state == target:
            return
        state_fingerprint = fingerprint_model(state)
        if state_fingerprint in seen:
            return
        seen.add(state_fingerprint)
        _apply_layer_canonical_pass(
            layer,
            state,
            target,
            layer_root=layer_root,
            replacement_roots=replacement_roots,
        )
        updated = _layer_model(layer)
        if updated == state:
            return
        state = updated


def _apply_master_collection(
    font: Any,
    current: Sequence[Mapping[str, Any]],
    target: Sequence[Mapping[str, Any]],
    *,
    target_glyphs: Mapping[str, Any] | None = None,
    execution_context: Mapping[str, Any] | None = None,
    restore_templates: Mapping[str, Mapping[str, Any]] | None = None,
    reuse_native_templates: bool = False,
) -> None:
    """Replay master membership/order while preserving native-only state."""

    current_order, current_entities = require_indexed_entities(current, "masters")
    target_order, target_entities = require_indexed_entities(target, "masters")
    added_ids = set(target_entities) - set(current_entities)
    collection = _safe_getattr(font, "masters")
    native_values = _sequence_values(collection)
    if len(native_values) != len(current_order):
        raise HostAccessError("Glyphs master collection diverged before mutation")
    native_by_id = {
        identity: native_values[index]
        for index, identity in enumerate(current_order)
    }
    context = dict(execution_context or {})
    source_map = {
        str(key): str(value)
        for key, value in dict(context.get("masterSources") or {}).items()
    }
    templates = dict(restore_templates or {})
    glyphs = {
        str(_safe_getattr(glyph, "name") or ""): glyph
        for glyph in _sequence_values(_safe_getattr(font, "glyphs"))
        if str(_safe_getattr(glyph, "name") or "")
    }
    canonical_glyphs = dict(target_glyphs or {})

    # Additions happen before removals so one batch may duplicate a source and
    # then delete it without losing the native copy source.
    for identity in target_order:
        if identity in native_by_id:
            continue
        template = templates.get(identity)
        reuse_template = bool(
            reuse_native_templates
            and isinstance(template, Mapping)
            and template.get("nativeMaster") is not None
        )
        source_id = source_map.get(identity)
        source_master = (
            template.get("nativeMaster" if reuse_template else "master")
            if isinstance(template, Mapping)
            else native_by_id.get(source_id or "")
        )
        if source_master is None:
            raise HostAccessError(
                "master creation requires a verified native copy source"
            )
        master = (
            source_master
            if reuse_template
            else _copy_native_object(source_master, kind="master")
        )
        _set_native_scalar_if_changed(master, "id", identity)
        _append_native_collection_item(collection, master)
        native_by_id[identity] = master

        stored_layers = (
            template.get("nativeLayers" if reuse_template else "layers", {})
            if isinstance(template, Mapping)
            else {}
        )
        for glyph_name, glyph in glyphs.items():
            source_layer = (
                stored_layers.get(glyph_name)
                if isinstance(stored_layers, Mapping)
                else None
            )
            if source_layer is None and source_id:
                source_glyph = glyphs.get(glyph_name)
                source_layer = (
                    _lookup_layer(source_glyph, source_id)
                    if source_glyph is not None
                    else None
                )
            if source_layer is None:
                raise HostAccessError(
                    "master copy source layer is missing for glyph {}".format(
                        glyph_name
                    )
                )
            copied_layer = (
                source_layer
                if reuse_template
                else _copy_native_object(source_layer, kind="master layer")
            )
            canonical_glyph = canonical_glyphs.get(glyph_name, {})
            canonical_layers = (
                canonical_glyph.get("layers", {})
                if isinstance(canonical_glyph, Mapping)
                else {}
            )
            canonical_layer = (
                canonical_layers.get(identity)
                if isinstance(canonical_layers, Mapping)
                else None
            )
            if isinstance(canonical_layer, Mapping) and "name" in canonical_layer:
                _set_native_scalar_if_changed(
                    copied_layer,
                    "name",
                    str(canonical_layer.get("name") or ""),
                )
            _set_glyph_master_layer(glyph, identity, copied_layer)

    for identity in reversed(current_order):
        if identity in target_entities:
            continue
        value = native_by_id.pop(identity)
        index = _sequence_values(collection).index(value)
        _remove_native_collection_item(collection, index, value)

    _replace_native_collection_order(
        collection, [native_by_id[identity] for identity in target_order]
    )
    for identity in target_order:
        native = native_by_id[identity]
        after = target_entities[identity]
        _set_native_scalar_if_changed(
            native,
            "name",
            str(after.get("name") or ""),
        )
        _set_native_scalar_if_changed(
            native,
            "italicAngle",
            float(after.get("italicAngle") or 0),
        )
        positions = [axis.get("internal") for axis in after.get("axes", [])]
        native_positions = [
            _plain_scalar(position)
            for position in _sequence_values(_safe_getattr(native, "axes"))
        ]
        if native_positions != positions:
            if _safe_getattr(native, "internalAxesValues") is not None:
                _set_native_property(native, "internalAxesValues", positions)
            else:
                _set_native_property(native, "axes", positions)

    # Copying preserves native-only state, but attachment may recalculate
    # canonical metrics. Re-read each added layer and converge it through the
    # same writer used by every ordinary layer mutation.
    for identity in target_order:
        if identity not in added_ids:
            continue
        for glyph_name, glyph in glyphs.items():
            canonical_glyph = canonical_glyphs.get(glyph_name, {})
            canonical_layers = (
                canonical_glyph.get("layers", {})
                if isinstance(canonical_glyph, Mapping)
                else {}
            )
            target_layer = (
                canonical_layers.get(identity)
                if isinstance(canonical_layers, Mapping)
                else None
            )
            layer = _lookup_layer(glyph, identity)
            if not isinstance(target_layer, Mapping) or layer is None:
                raise HostAccessError(
                    "canonical restored layer is missing for {}/{}".format(
                        glyph_name, identity
                    )
                )
            current_layer = _layer_model(layer)
            if current_layer != target_layer:
                _reconcile_layer_to_canonical_target(
                    layer,
                    current_layer,
                    target_layer,
                    layer_root=("glyphs", glyph_name, "layers", identity),
                    max_passes=3,
                )


def _apply_glyph_membership(
    font: Any,
    current: Mapping[str, Mapping[str, Any]],
    target: Mapping[str, Mapping[str, Any]],
) -> None:
    collection = _safe_getattr(font, "glyphs")
    native_by_name = {
        str(_safe_getattr(value, "name") or ""): value
        for value in _sequence_values(collection)
        if str(_safe_getattr(value, "name") or "")
    }
    if set(native_by_name) != set(current):
        raise HostAccessError("Glyphs glyph collection diverged before mutation")
    for name in sorted(set(current) - set(target), reverse=True):
        value = native_by_name.pop(name)
        try:
            del collection[name]
        except Exception:
            index = _sequence_values(collection).index(value)
            _remove_native_collection_item(collection, index, value)
    for name in sorted(set(target) - set(current)):
        value = _construct_native_entity("glyph", name)
        if str(_safe_getattr(value, "name") or "") != name:
            _set_native_property(value, "name", name)
        _append_native_collection_item(collection, value)
        native_by_name[name] = value


def _canonical_replacement_roots(
    before: Mapping[str, Any],
    target: Mapping[str, Any],
    observed: Mapping[str, Any],
) -> tuple[tuple[str, ...], ...]:
    """Return changed canonical collections that can resolve a remaining diff.

    The decision is based only on the three canonical trees. It deliberately
    has no knowledge of the originating tool or setter that caused the drift.
    """

    remaining = diff_models(observed, target)
    del before  # The replay decision is entirely the remaining target diff.
    replacements = {
        change.path[:5]
        for change in remaining.changes
        if len(change.path) >= 5
        and change.path[0] == "glyphs"
        and change.path[2] == "layers"
        and change.path[4] in {"paths", "components"}
    }
    return tuple(sorted(replacements))


def _apply_target_model(
    font: Any,
    current: Mapping[str, Any],
    target: Mapping[str, Any],
    change_set: ChangeSet,
    *,
    replay_replacements: Sequence[Sequence[str]] = (),
    capabilities: Sequence[str] = (),
    execution_context: Mapping[str, Any] | None = None,
    master_restore_templates: Mapping[str, Mapping[str, Any]] | None = None,
    reuse_native_master_templates: bool = False,
) -> None:
    replacement_roots = {tuple(str(part) for part in path) for path in replay_replacements}
    changed_roots = {change.path[0] for change in change_set.changes}
    master_structural_ids: set[str] = set()
    if "masters" in changed_roots:
        current_master_ids = {
            str(master.get("id") or "")
            for master in current.get("masters", [])
            if isinstance(master, Mapping)
        }
        target_master_ids = {
            str(master.get("id") or "")
            for master in target.get("masters", [])
            if isinstance(master, Mapping)
        }
        master_structural_ids = current_master_ids.symmetric_difference(
            target_master_ids
        )
        _apply_master_collection(
            font,
            current.get("masters", []),
            target.get("masters", []),
            target_glyphs=target.get("glyphs", {}),
            execution_context=execution_context,
            restore_templates=master_restore_templates,
            reuse_native_templates=reuse_native_master_templates,
        )
    if "font" in changed_roots:
        for name in _FONT_SCALARS:
            if current.get("font", {}).get(name) != target.get("font", {}).get(name):
                _set_native_property(font, name, target.get("font", {}).get(name))
    if "glyphs" in changed_roots:
        current_glyphs = current.get("glyphs", {})
        target_glyphs = target.get("glyphs", {})
        if not isinstance(current_glyphs, Mapping) or not isinstance(
            target_glyphs, Mapping
        ):
            raise HostAccessError("canonical glyph collections must be keyed by name")
        if set(current_glyphs) != set(target_glyphs):
            _apply_glyph_membership(font, current_glyphs, target_glyphs)
        for name in sorted(target_glyphs):
            if current_glyphs.get(name) == target_glyphs.get(name):
                continue
            glyph = _lookup_by_name(_safe_getattr(font, "glyphs"), name)
            if glyph is None:
                raise HostAccessError("Glyphs could not resolve glyph {}".format(name))
            current_glyph = current_glyphs.get(name)
            if not isinstance(current_glyph, Mapping):
                # A new glyph can gain host-created master layers when it is
                # inserted into the font. Capture those derived values before
                # applying any explicitly modeled content.
                current_glyph = _glyph_model(glyph)
            for scalar in _GLYPH_SCALARS:
                if current_glyph.get(scalar) != target_glyphs[name].get(scalar):
                    _set_native_property(glyph, scalar, target_glyphs[name].get(scalar))
            current_layers = current_glyph.get("layers", {})
            target_layers = target_glyphs[name].get("layers", {})
            if master_structural_ids:
                # Master lifecycle replay above owns these layers as complete
                # native copies. The generic layer writer must not replay the
                # same structural consequence field-by-field.
                current_layers = {
                    key: value
                    for key, value in current_layers.items()
                    if key not in master_structural_ids
                }
                target_layers = {
                    key: value
                    for key, value in target_layers.items()
                    if key not in master_structural_ids
                }
            if set(current_layers) != set(target_layers):
                # Layer collection mutation remains a separate structural
                # boundary. Empty requested layers on a newly created glyph
                # mean "accept Glyphs' derived master layers".
                if name not in current_glyphs and not target_layers:
                    target_layers = current_layers
                else:
                    raise HostAccessError(
                        "canonical layer collection membership changes are not supported"
                    )
            for layer_key in sorted(target_layers):
                if current_layers.get(layer_key) == target_layers.get(layer_key):
                    continue
                layer = _lookup_layer(glyph, layer_key)
                if layer is None:
                    raise HostAccessError("Glyphs could not resolve layer {}".format(layer_key))
                _reconcile_layer_to_canonical_target(
                    layer,
                    current_layers[layer_key],
                    target_layers[layer_key],
                    layer_root=("glyphs", name, "layers", layer_key),
                    replacement_roots=replacement_roots,
                )
    if "kerning" in changed_roots:
        _replace_kerning(font, target.get("kerning", []))
    if "instances" in changed_roots:
        _apply_instance_collection(
            font,
            current.get("instances", []),
            target.get("instances", []),
        )
    for root, attribute in (
        ("features", "features"),
        ("classes", "classes"),
        ("featurePrefixes", "featurePrefixes"),
    ):
        if root in changed_roots:
            _apply_code_collection(
                font,
                attribute,
                current.get(root, []),
                target.get(root, []),
            )


def _safe_import(name: str, globals_value: Any = None, locals_value: Any = None, fromlist: Any = (), level: int = 0) -> Any:
    if name.split(".", 1)[0] not in {"math", "re", "json", "statistics", "itertools", "functools"}:
        raise ImportError("staged Python cannot import {}".format(name))
    return builtins.__import__(name, globals_value, locals_value, fromlist, level)


_STAGED_BUILTINS = {
    "__import__": _safe_import, "abs": abs, "all": all, "any": any, "bool": bool,
    "dict": dict, "enumerate": enumerate, "float": float, "getattr": getattr,
    "hasattr": hasattr, "int": int, "isinstance": isinstance, "len": len, "list": list,
    "max": max, "min": min, "print": print, "range": range, "round": round,
    "set": set, "setattr": setattr, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "zip": zip, "Exception": Exception, "ValueError": ValueError,
}


def _save_font_copy(font: Any, destination: Path) -> None:
    """Save a copy without changing the live document path or leaked tempData.

    Glyphs 4.0.1's Python wrapper calls the removed
    ``saveToURL_type_format_error_`` selector. Fall back to the current native
    selector while restoring the transient filePath value on every exit path.
    """

    path = Path(destination)
    saver = _safe_getattr(font, "save")
    if not callable(saver):
        raise HostAccessError("Glyphs did not provide GSFont.save(makeCopy=True)")
    try:
        format_version = int(_plain_scalar(_safe_getattr(font, "formatVersion")) or 3)
    except (TypeError, ValueError):
        format_version = 3
    temp_data = _safe_getattr(font, "tempData")
    previous_temp_path = _mapping_get(temp_data, "filePath") if temp_data is not None else None

    def restore_temp_path() -> None:
        if temp_data is None:
            return
        try:
            temp_data["filePath"] = previous_temp_path
        except Exception:
            pass

    try:
        try:
            saver(str(path), formatVersion=format_version, makeCopy=True)
        except AttributeError as wrapper_error:
            restore_temp_path()
            native_saver = _safe_getattr(font, "saveToURL_type_format_context_error_")
            if not callable(native_saver):
                raise HostAccessError(
                    "Glyphs make-copy wrapper and native fallback are unavailable"
                ) from wrapper_error
            try:
                from Foundation import NSURL  # type: ignore[import-not-found]
            except Exception as exc:
                raise HostAccessError("Glyphs file URL support is unavailable") from exc
            suffix = path.suffix.lower()
            if suffix == ".glyphs":
                type_id = 1  # GSPackageFlatFile
            elif suffix == ".glyphspackage":
                type_id = 2  # GSPackageBundle
            else:
                raise HostAccessError("Recovery copies require .glyphs or .glyphspackage")
            if temp_data is not None:
                temp_data["filePath"] = str(path)
            native_saver(
                NSURL.fileURLWithPath_(str(path)),
                type_id,
                format_version,
                None,
                None,
            )
    finally:
        restore_temp_path()

    if not path.is_file():
        raise HostAccessError("Glyphs did not create the requested copy")


def _serialized_font_archive(font: Any) -> bytes:
    with tempfile.TemporaryDirectory(prefix="glyphs-mcp-v2-archive-") as root:
        path = Path(root) / "checkpoint.glyphs"
        _save_font_copy(font, path)
        archive = path.read_bytes()
        # GSFont.copy() in Glyphs 4 assigns fresh UUIDs to GSInstance objects.
        # Replace only those exact native UUID values, by ordered instance, so
        # archive comparison still detects every other non-canonical field.
        for index, instance in enumerate(_sequence_values(_safe_getattr(font, "instances"))):
            identifier = str(_plain_scalar(_safe_getattr(instance, "id")) or "").strip()
            if not _UUID_PATTERN.fullmatch(identifier):
                continue
            replacement = "__GLYPHS_MCP_INSTANCE_{:04d}__".format(index).encode("ascii")
            for spelling in (identifier, identifier.upper(), identifier.lower()):
                archive = archive.replace(spelling.encode("ascii"), replacement)
    return archive


def _serialized_review_scope(
    font: Any, request: PythonExecutionRequest
) -> bytes:
    """Archive a safe declared native scope, retaining a full-font fallback."""

    target = font
    if request.glyph_name:
        glyph = _lookup_by_name(_safe_getattr(font, "glyphs"), request.glyph_name)
        if glyph is None:
            raise HostAccessError(
                "The staged archive glyph no longer exists: {}".format(
                    request.glyph_name
                )
            )
        target = glyph
        try:
            tree = ast.parse(request.code or "", mode="exec")
        except SyntaxError as exc:
            raise HostAccessError("The staged Python source is invalid") from exc
        broad_names = {"font", "master"}
        if any(
            (isinstance(node, ast.Name) and node.id in broad_names)
            or (isinstance(node, ast.Attribute) and node.attr in {"font", "parent"})
            for node in ast.walk(tree)
        ):
            target = font
    if target is font:
        return _serialized_font_archive(font)
    try:
        from Foundation import NSKeyedArchiver  # type: ignore[import-not-found]

        data = NSKeyedArchiver.archivedDataWithRootObject_(target)
        return bytes(data)
    except Exception as exc:
        raise HostAccessError(
            "Glyphs could not archive the declared staged review scope"
        ) from exc


def _serialized_font_fingerprint(font: Any) -> str:
    digest = hashlib.sha256(_serialized_font_archive(font)).hexdigest()
    return "sha256:{}".format(digest)


def _archive_delta(before: bytes, after: bytes) -> list[dict[str, Any]]:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    result: list[dict[str, Any]] = []
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
    for tag, before_start, before_end, after_start, after_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        before_block = b"\n".join(before_lines[before_start:before_end])
        after_block = b"\n".join(after_lines[after_start:after_end])
        result.append(
            {
                "tag": tag,
                "beforeStart": before_start,
                "beforeEnd": before_end,
                "afterStart": after_start,
                "afterEnd": after_end,
                "beforeHash": hashlib.sha256(before_block).hexdigest(),
                "afterHash": hashlib.sha256(after_block).hexdigest(),
            }
        )
    return result


def _compare_native_archive_deltas(
    direct_before: bytes,
    direct_after: bytes,
    replay_before: bytes,
    replay_after: bytes,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """Compare native archive effects, not unrelated identities of two clones."""

    direct = _archive_delta(direct_before, direct_after)
    replay = _archive_delta(replay_before, replay_after)
    count = max(len(direct), len(replay))
    mismatches: list[dict[str, Any]] = []
    for index in range(count):
        direct_item = direct[index] if index < len(direct) else None
        replay_item = replay[index] if index < len(replay) else None
        if direct_item != replay_item:
            mismatches.append({"direct": direct_item, "replay": replay_item})
    bounded = mismatches[: max(0, min(100, int(limit)))]
    return {
        "equivalent": not mismatches,
        "mismatchCount": len(mismatches),
        "mismatchLocations": bounded,
        "truncated": len(mismatches) > len(bounded),
        "directDeltaCount": len(direct),
        "replayDeltaCount": len(replay),
    }


def _document_edited_state(font: Any) -> Optional[bool]:
    document = _maybe_call(_safe_getattr(font, "parent"))
    return _native_unsaved_changes(document)


class GlyphsDocumentHost(GlyphsHostAdapter):
    """Complete v2 host port; native objects remain inside this adapter."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._canonical_model_cache = _RevisionBoundGlyphModelCache()
        self._instance_identity_maps: dict[str, dict[str, str]] = {}
        self._instance_identity_counters: dict[str, int] = {}
        self._master_lifecycle_tombstones: dict[str, Mapping[str, Any]] = {}

    def runtime_snapshot(self):
        self._cleanup_all_recovery()
        return super().runtime_snapshot()

    def _font_for_document(self, document_id: str) -> Any:
        for font in self._collect_fonts():
            if self._identities.resolve(self._native_identity(font)) == document_id:
                return font
        raise HostAccessError("The Glyphs document is no longer open: {}".format(document_id))

    def document_id_for_font(self, font: Any) -> str:
        return self._identities.resolve(self._native_identity(font))

    def native_font(self, document_id: str) -> Any:
        return self._font_for_document(document_id)

    @staticmethod
    def _native_instance_key(instance: Any) -> str:
        # ``GSInstance.id`` is not a stable identity read in Glyphs 4: a fresh
        # collection proxy can expose a newly allocated UUID. PyObjC's native
        # object pointer identifies the live member without consulting font
        # data and remains stable across fresh Python proxies.
        try:
            import objc  # type: ignore[import-not-found]

            native_pointer = objc.pyobjc_id(instance)
            if native_pointer:
                return "objc:{}".format(native_pointer)
        except Exception:
            pass
        return "native:{}".format(id(instance))

    def _instance_ids_for_font(self, document_id: str, font: Any) -> list[str]:
        mapping = self._instance_identity_maps.setdefault(document_id, {})
        counter = self._instance_identity_counters.get(document_id, 0)
        used = set(mapping.values())
        result: list[str] = []
        for instance in _sequence_values(_safe_getattr(font, "instances")):
            key = self._native_instance_key(instance)
            identity = mapping.get(key)
            if identity is None:
                while "instance_{}".format(counter) in used:
                    counter += 1
                identity = "instance_{}".format(counter)
                counter += 1
                mapping[key] = identity
                used.add(identity)
            result.append(identity)
        live_keys = {
            self._native_instance_key(instance)
            for instance in _sequence_values(_safe_getattr(font, "instances"))
        }
        self._instance_identity_maps[document_id] = {
            key: value for key, value in mapping.items() if key in live_keys
        }
        self._instance_identity_counters[document_id] = counter
        return result

    def _bind_instance_ids(
        self, document_id: str, font: Any, identities: Sequence[str]
    ) -> None:
        native = _sequence_values(_safe_getattr(font, "instances"))
        if len(native) != len(identities):
            raise HostAccessError("Glyphs instance membership did not match the canonical target")
        self._instance_identity_maps[document_id] = {
            self._native_instance_key(instance): str(identities[index])
            for index, instance in enumerate(native)
        }

    def _capture_cached_model(self, document_id: str, font: Any) -> dict[str, Any]:
        return self._canonical_model_cache.capture(
            document_id,
            font,
            instance_ids=self._instance_ids_for_font(document_id, font),
        )

    def _capture_removed_master_templates(
        self,
        font: Any,
        current: Mapping[str, Any],
        target: Mapping[str, Any],
    ) -> dict[str, Mapping[str, Any]]:
        current_ids = {
            str(master.get("id") or "")
            for master in current.get("masters", [])
            if isinstance(master, Mapping)
        }
        target_ids = {
            str(master.get("id") or "")
            for master in target.get("masters", [])
            if isinstance(master, Mapping)
        }
        removed = current_ids - target_ids
        if not removed:
            return {}
        glyphs = _sequence_values(_safe_getattr(font, "glyphs"))
        result: dict[str, Mapping[str, Any]] = {}
        for master_id in sorted(removed):
            master = _master_by_id(font, master_id)
            if master is None:
                raise HostAccessError(
                    "Glyphs could not snapshot removed master {}".format(master_id)
                )
            layers: dict[str, Any] = {}
            native_layers: dict[str, Any] = {}
            for glyph in glyphs:
                glyph_name = str(_safe_getattr(glyph, "name") or "")
                layer = _lookup_layer(glyph, master_id)
                if not glyph_name or layer is None:
                    raise HostAccessError(
                        "Glyphs could not snapshot master layer {}/{}".format(
                            glyph_name or "<unnamed>", master_id
                        )
                    )
                native_layers[glyph_name] = layer
                layers[glyph_name] = _copy_native_object(layer, kind="master layer")
            result[master_id] = {
                "master": _copy_native_object(master, kind="master"),
                "layers": layers,
                # Exact detached objects are retained only for same-process
                # live rollback. Detached simulation uses the copies above so
                # no object ever crosses from the working font into a clone.
                "nativeMaster": master,
                "nativeLayers": native_layers,
            }
        return result

    def _master_restore_templates(
        self, contribution_id: Optional[str]
    ) -> Mapping[str, Mapping[str, Any]]:
        if not contribution_id:
            return {}
        record = self._master_lifecycle_tombstones.get(str(contribution_id), {})
        templates = record.get("templates", {}) if isinstance(record, Mapping) else {}
        return templates if isinstance(templates, Mapping) else {}

    def _cached_open_models(self) -> dict[str, dict[str, Any]]:
        return {
            document_id: self._capture_cached_model(document_id, font)
            for font in self._collect_fonts()
            for document_id in (
                self._identities.resolve(self._native_identity(font)),
            )
        }

    def capture_model(self, document_id: str) -> Mapping[str, Any]:
        return self._executor.run(
            lambda: self._capture_cached_model(
                document_id, self._font_for_document(document_id)
            )
        )

    def capture_stable_model(self, document_id: str) -> Mapping[str, Any]:
        """Capture a canonical tree only after two host readbacks agree.

        Glyphs may resolve metrics and other derived layer state on a later
        application-loop turn after a setter returns. The pause happens on the
        MCP worker, never inside Reporter drawing or the main-thread callback.
        A transaction must fail rather than publish an unstable fingerprint.
        """

        previous = copy.deepcopy(dict(self.capture_model(document_id)))
        previous_fingerprint = fingerprint_model(previous)
        for _ in range(3):
            time.sleep(0.02)
            current = copy.deepcopy(dict(self.capture_model(document_id)))
            current_fingerprint = fingerprint_model(current)
            if current_fingerprint == previous_fingerprint:
                return current
            previous = current
            previous_fingerprint = current_fingerprint
        raise HostAccessError(
            "Glyphs canonical state did not settle across bounded readbacks"
        )

    def simulate_change_set(
        self, document_id: str, change_set: ChangeSet
    ) -> Mapping[str, Any]:
        """Apply writable intent to one detached font and recapture host effects."""

        before = self.capture_model(document_id)
        return self.simulate_change_set_from_model(
            document_id, change_set, before
        )

    def simulate_change_set_from_model(
        self,
        document_id: str,
        change_set: ChangeSet,
        before_model: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Simulate one patch while recapturing only its semantic dependency scope."""

        return self._simulate_canonical_change(
            document_id,
            change_set,
            before_model,
        )["afterModel"]

    def _simulate_canonical_change(
        self,
        document_id: str,
        change_set: ChangeSet,
        before_model: Mapping[str, Any],
        *,
        required_after_model: Optional[Mapping[str, Any]] = None,
        capabilities: Sequence[str] = (),
        execution_context: Mapping[str, Any] | None = None,
        removes_contribution_id: Optional[str] = None,
    ) -> Mapping[str, Any]:
        """Replay one canonical patch on a clone using one bounded verifier.

        Forward planning and inverse reconciliation share this path. A complete
        result tree is assembled from the already-verified source plus fresh
        native captures for the semantic dependency closure and every glyph
        whose revision evidence changed unexpectedly. This preserves exact
        document fingerprints without rebuilding all unchanged glyph trees.
        """

        def simulate() -> Mapping[str, Any]:
            if not self.supports_change_set(
                change_set, capabilities=capabilities
            ):
                raise HostAccessError("The change set contains unsupported native write paths")
            font = self._font_for_document(document_id)
            copier = _safe_getattr(font, "copy")
            if not callable(copier):
                raise HostAccessError("Glyphs did not provide GSFont.copy()")
            source = copy.deepcopy(dict(before_model))
            scope = mutation_scope(source, change_set)
            required = (
                copy.deepcopy(dict(required_after_model))
                if required_after_model is not None
                else None
            )
            source_instance_ids = collection_order(source.get("instances", []))
            restore_templates = self._master_restore_templates(
                removes_contribution_id
            )

            def attempt(replacements: Sequence[Sequence[str]]) -> Mapping[str, Any]:
                clone = copier()
                revisions_before = _glyph_revision_index(clone)
                clone_before = _scoped_font_model(
                    clone,
                    source,
                    scope,
                    instance_ids=source_instance_ids,
                )
                if fingerprint_model(clone_before) != change_set.before_fingerprint:
                    raise HostAccessError(
                        "Detached GSFont.copy() did not reproduce the canonical source"
                    )
                requested_target = change_set.apply(clone_before)
                target = required if required is not None else requested_target
                _apply_target_model(
                    clone,
                    clone_before,
                    target,
                    change_set,
                    replay_replacements=replacements,
                    capabilities=capabilities,
                    execution_context=execution_context,
                    master_restore_templates=restore_templates,
                )
                revisions_after = _glyph_revision_index(clone)
                changed_glyphs = _changed_revision_glyphs(
                    revisions_before, revisions_after
                )
                return _scoped_font_model(
                    clone,
                    source,
                    scope,
                    extra_glyph_names=changed_glyphs,
                    instance_ids=collection_order(target.get("instances", [])),
                )

            preferred = attempt(())
            if required is None or fingerprint_model(preferred) == fingerprint_model(
                required
            ):
                return {"afterModel": preferred, "replayReplacements": []}

            replacements = _canonical_replacement_roots(
                source,
                required,
                preferred,
            )
            if not replacements:
                return {"afterModel": preferred, "replayReplacements": []}
            canonical = attempt(replacements)
            return {
                "afterModel": canonical,
                "replayReplacements": [list(path) for path in replacements],
            }

        return self._executor.run(simulate)

    def simulate_verified_change_set(
        self,
        document_id: str,
        change_set: ChangeSet,
        before_model: Mapping[str, Any],
        *,
        required_after_model: Optional[Mapping[str, Any]] = None,
        capabilities: Sequence[str] = (),
        execution_context: Mapping[str, Any] | None = None,
        removes_contribution_id: Optional[str] = None,
    ) -> Mapping[str, Any]:
        """One capability-aware detached simulation entry point."""

        return self._simulate_canonical_change(
            document_id,
            change_set,
            before_model,
            required_after_model=required_after_model,
            capabilities=capabilities,
            execution_context=execution_context,
            removes_contribution_id=removes_contribution_id,
        )

    def simulate_reconciliation(
        self,
        document_id: str,
        change_set: ChangeSet,
        required_after_model: Mapping[str, Any],
        before_model: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Select a cause-independent replay that reproduces a canonical tree."""

        return self._simulate_canonical_change(
            document_id,
            change_set,
            before_model,
            required_after_model=required_after_model,
        )

    def supports_change_set(
        self, change_set: ChangeSet, *, capabilities: Sequence[str] = ()
    ) -> bool:
        master_lifecycle = MASTER_LIFECYCLE_CAPABILITY in capabilities
        structural_master_ids = {
            change.path[1]
            for change in change_set.changes
            if len(change.path) == 2
            and change.path[0] == "masters"
            and change.path[1] != "$order"
            and change.before_present != change.after_present
        }
        for change in change_set.changes:
            path = change.path
            if path[0] == "font" and len(path) == 2 and path[1] in _FONT_SCALARS:
                continue
            if path[0] == "kerning":
                continue
            if path[0] == "masters" and master_lifecycle:
                if len(path) == 2:
                    continue
                if len(path) >= 3 and path[2] in {
                    "name",
                    "italicAngle",
                    "axes",
                }:
                    continue
                return False
            if (
                path[0] in {"features", "classes", "featurePrefixes"}
                and (
                    len(path) == 2
                    or (
                        len(path) == 3
                        and path[2] in {"name", "code", "automatic", "disabled"}
                    )
                )
            ):
                continue
            if path[0] == "instances":
                if len(path) == 2:
                    continue
                if len(path) >= 3 and path[2] in {
                    "name",
                    "type",
                    "included",
                    "axes",
                }:
                    continue
                return False
            if path[0] == "glyphs" and len(path) == 2:
                continue
            if path[0] == "glyphs" and len(path) >= 3:
                if (
                    master_lifecycle
                    and len(path) >= 4
                    and path[2] == "layers"
                    and path[3] in structural_master_ids
                ):
                    continue
                if len(path) == 3 and path[2] in _GLYPH_SCALARS:
                    if not change.before_present or not change.after_present:
                        return False
                    continue
                if len(path) >= 5 and path[2] == "layers" and path[4] in set(_LAYER_SCALARS) | {"anchors", "paths", "components", "pathSignature"}:
                    if len(path) == 5 and path[4] in _LAYER_SCALARS and (
                        not change.before_present or not change.after_present
                    ):
                        return False
                    continue
            return False
        return True

    def _context(self, font: Any, request: PythonExecutionRequest) -> dict[str, Any]:
        glyph = _lookup_by_name(_safe_getattr(font, "glyphs"), request.glyph_name) if request.glyph_name else None
        if request.glyph_name and glyph is None:
            raise HostAccessError("The Python glyph does not exist: {}".format(request.glyph_name))
        master = None
        if request.master_id:
            master = next((item for item in _sequence_values(_safe_getattr(font, "masters")) if str(_safe_getattr(item, "id") or "") == request.master_id), None)
            if master is None:
                raise HostAccessError("The Python master does not exist: {}".format(request.master_id))
        layer = _lookup_layer(glyph, request.layer_id or request.master_id or "") if glyph is not None and (request.layer_id or request.master_id) else None
        if glyph is not None and (request.layer_id or request.master_id) and layer is None:
            raise HostAccessError("The Python layer does not exist")
        return {"font": font, "glyph": glyph, "master": master, "layer": layer, "selectedLayers": [layer] if layer is not None else []}

    def preview_python(self, request: PythonExecutionRequest, before_model: Mapping[str, Any]) -> Mapping[str, Any]:
        def run() -> Mapping[str, Any]:
            live_before_models = self._cached_open_models()
            live_before = {
                document_id: fingerprint_model(model)
                for document_id, model in live_before_models.items()
            }
            font = self._font_for_document(request.document_id or "")
            copier = _safe_getattr(font, "copy")
            if not callable(copier):
                raise HostAccessError("Glyphs did not provide GSFont.copy()")
            clone = copier()
            verifier = copier()
            direct_before_archive = _serialized_review_scope(clone, request)
            replay_before_archive = _serialized_review_scope(verifier, request)
            clone_revisions_before = _glyph_revision_index(clone)
            namespace = self._context(clone, request)
            namespace["__builtins__"] = _STAGED_BUILTINS
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(compile(request.code or "", "<glyphs-mcp-staged>", "exec"), namespace, namespace)
            if request.glyph_name:
                clone_revisions_after = _glyph_revision_index(clone)
                after_model = _scoped_font_model(
                    clone,
                    before_model,
                    MutationScope(("glyphs",), (request.glyph_name,)),
                    extra_glyph_names=_changed_revision_glyphs(
                        clone_revisions_before,
                        clone_revisions_after,
                    ),
                    instance_ids=collection_order(before_model.get("instances", [])),
                )
            else:
                # Open-world staged requests retain the conservative full-tree
                # fallback because no smaller correctness boundary was declared.
                after_model = native_font_to_model(
                    clone,
                    instance_ids=collection_order(before_model.get("instances", [])),
                )
            changes = diff_models(before_model, after_model)
            context_violations = _staged_context_violations(
                request,
                changes,
                model=before_model,
            )
            writable_changes = writable_subset(before_model, changes)
            archive_comparison = {
                "equivalent": True,
                "mismatchCount": 0,
                "mismatchLocations": [],
                "truncated": False,
                "directDeltaCount": 0,
                "replayDeltaCount": 0,
            }
            if self.supports_change_set(writable_changes):
                writable_target = writable_changes.apply(before_model)
                _apply_target_model(
                    verifier,
                    before_model,
                    writable_target,
                    writable_changes,
                )
                archive_comparison = _compare_native_archive_deltas(
                    direct_before_archive,
                    _serialized_review_scope(clone, request),
                    replay_before_archive,
                    _serialized_review_scope(verifier, request),
                    limit=100,
                )
            live_after_models = self._cached_open_models()
            live_after = {
                document_id: fingerprint_model(model)
                for document_id, model in live_after_models.items()
            }
            violations = [document_id for document_id in sorted(set(live_before) | set(live_after)) if live_before.get(document_id) != live_after.get(document_id)]
            return {
                "afterModel": after_model,
                "changeSet": changes,
                "writableChangeSet": writable_changes,
                "stdout": stdout.getvalue(),
                "stderr": stderr.getvalue(),
                "scopeViolations": violations,
                "contextViolations": context_violations,
                "nativeArchiveComparison": archive_comparison,
            }
        return self._executor.run(run)

    def run_live_python(self, request: PythonExecutionRequest) -> Mapping[str, Any]:
        def run() -> Mapping[str, Any]:
            live_before_models = self._cached_open_models()
            live_before = {
                document_id: fingerprint_model(model)
                for document_id, model in live_before_models.items()
            }
            font = self._font_for_document(request.document_id) if request.document_id else _safe_getattr(self._app, "font")
            active_document_id = (
                request.document_id
                or (
                    self._identities.resolve(self._native_identity(font))
                    if font is not None
                    else None
                )
            )
            before = copy.deepcopy(
                live_before_models.get(active_document_id or "", {})
            )
            namespace = self._context(font, request) if font is not None else {"font": None, "glyph": None, "master": None, "layer": None, "selectedLayers": []}
            namespace.update({"Glyphs": self._app, "__builtins__": builtins.__dict__})
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(compile(request.code or "", "<glyphs-mcp-live>", "exec"), namespace, namespace)
            live_after_models = self._cached_open_models()
            after = copy.deepcopy(
                live_after_models.get(active_document_id or "", {})
            )
            live_after = {
                document_id: fingerprint_model(model)
                for document_id, model in live_after_models.items()
            }
            changed_documents = [
                document_id
                for document_id in sorted(set(live_before) | set(live_after))
                if live_before.get(document_id) != live_after.get(document_id)
            ]
            scope_violations = [
                document_id for document_id in changed_documents if document_id != request.document_id
            ]
            return {
                "beforeModel": before,
                "afterModel": after,
                "stdout": stdout.getvalue(),
                "stderr": stderr.getvalue(),
                "scopeViolations": scope_violations,
            }
        return self._executor.run(run)

    @staticmethod
    def _native_change_count(font: Any, action: int) -> None:
        document = _maybe_call(_safe_getattr(font, "parent"))
        updater = _safe_getattr(document, "updateChangeCount_") if document is not None else None
        if callable(updater):
            try:
                updater(action)
            except Exception:
                pass

    def _refresh_verified_dirty_override(
        self,
        document_id: str,
        font: Any,
        *,
        current_fingerprint: Optional[str] = None,
    ) -> None:
        contributions = getattr(self, "_document_mcp_contributions", {})
        active = contributions.get(document_id, {})
        overrides = getattr(self, "_document_dirty_overrides", {})
        if active:
            overrides[document_id] = True
        else:
            native = _document_edited_state(font)
            baseline = getattr(self, "_document_mcp_baseline_dirty", {}).get(document_id)
            baseline_fingerprint = getattr(
                self, "_document_mcp_baseline_fingerprints", {}
            ).get(document_id)
            if (
                baseline_fingerprint
                and current_fingerprint == baseline_fingerprint
            ):
                # Reversing native setters may leave Glyphs' edited bit sticky.
                # Canonical equivalence proves the MCP-owned document delta is
                # gone, so expose the pre-MCP dirty state without clearing the
                # document's native history.
                overrides[document_id] = baseline
            else:
                overrides[document_id] = native if native is not None else True
        self._document_dirty_overrides = overrides

    def resolve_verified_dirty_state(
        self,
        document_id: str,
        font: Any,
        native_state: Optional[bool],
    ) -> Optional[bool]:
        """Revalidate a clean override before it can hide a later user edit."""

        overrides = getattr(self, "_document_dirty_overrides", {})
        if document_id not in overrides:
            return native_state
        override = overrides[document_id]
        if override is not False or native_state is False:
            return override
        baseline_fingerprint = getattr(
            self, "_document_mcp_baseline_fingerprints", {}
        ).get(document_id)
        if not baseline_fingerprint:
            return native_state
        current_fingerprint = fingerprint_model(
            self._capture_cached_model(document_id, font)
        )
        if current_fingerprint == baseline_fingerprint:
            return False
        # The document diverged after the verified clean equivalence. Stop
        # overriding Glyphs so a later manual edit remains visibly dirty.
        overrides[document_id] = True
        self._document_dirty_overrides = overrides
        return True

    def apply_verified_change_set(
        self,
        document_id: str,
        change_set: ChangeSet,
        *,
        operation_id: str,
        removes_contribution_id: Optional[str] = None,
        replay_replacements: Sequence[Sequence[str]] = (),
        capabilities: Sequence[str] = (),
        execution_context: Mapping[str, Any] | None = None,
    ) -> None:
        """Apply content and one operation-owned native dirty contribution."""

        if not operation_id:
            raise ValueError("operation_id is required")
        if not self.supports_change_set(
            change_set, capabilities=capabilities
        ):
            raise HostAccessError("The change set contains unsupported native write paths")

        def apply() -> None:
            font = self._font_for_document(document_id)
            current = self._capture_cached_model(document_id, font)
            target = change_set.apply(current)
            scope = mutation_scope(current, change_set)
            contributions = getattr(self, "_document_mcp_contributions", {})
            active = contributions.setdefault(document_id, {})
            baselines = getattr(self, "_document_mcp_baseline_dirty", {})
            baseline_fingerprints = getattr(
                self, "_document_mcp_baseline_fingerprints", {}
            )
            pending = getattr(self, "_document_mcp_pending_reverts", {})
            if operation_id in active or operation_id in pending:
                raise HostAccessError("The MCP operation already owns a dirty contribution")
            if removes_contribution_id and removes_contribution_id not in active:
                raise HostAccessError("The reverted MCP dirty contribution is unavailable")
            native_before = _document_edited_state(font)
            master_templates = self._capture_removed_master_templates(
                font, current, target
            )
            if master_templates:
                self._master_lifecycle_tombstones[operation_id] = {
                    "documentId": document_id,
                    "templates": master_templates,
                }
            self._canonical_model_cache.invalidate_glyphs(
                document_id, scope.glyph_names
            )
            _apply_target_model(
                font,
                current,
                target,
                change_set,
                replay_replacements=replay_replacements,
                capabilities=capabilities,
                execution_context=execution_context,
                master_restore_templates=self._master_restore_templates(
                    removes_contribution_id
                ),
                reuse_native_master_templates=True,
            )
            if any(change.path[0] == "instances" for change in change_set.changes):
                self._bind_instance_ids(
                    document_id,
                    font,
                    collection_order(target.get("instances", [])),
                )
            if change_set.changes:
                if removes_contribution_id:
                    removed = active.pop(removes_contribution_id)
                    pending[operation_id] = {
                        "documentId": document_id,
                        "removedId": removes_contribution_id,
                        "record": removed,
                    }
                    self._native_change_count(font, _NS_CHANGE_UNDONE)
                else:
                    if not active:
                        baselines[document_id] = native_before
                        baseline_fingerprints[document_id] = (
                            change_set.before_fingerprint
                        )
                    active[operation_id] = {"nativeDirtyBefore": native_before}
                    self._native_change_count(font, _NS_CHANGE_DONE)
            self._document_mcp_contributions = contributions
            self._document_mcp_baseline_dirty = baselines
            self._document_mcp_baseline_fingerprints = baseline_fingerprints
            self._document_mcp_pending_reverts = pending
            self._refresh_verified_dirty_override(
                document_id,
                font,
                current_fingerprint=change_set.after_fingerprint,
            )

        self._executor.run(apply)

    def commit_verified_change(self, operation_id: str) -> None:
        pending = getattr(self, "_document_mcp_pending_reverts", {})
        completed_revert = pending.pop(operation_id, None)
        if completed_revert is not None:
            self._master_lifecycle_tombstones.pop(
                str(completed_revert.get("removedId") or ""), None
            )
            self._master_lifecycle_tombstones.pop(operation_id, None)
        self._document_mcp_pending_reverts = pending

    def restore_verified_attempt(
        self,
        document_id: str,
        model: Mapping[str, Any],
        *,
        operation_id: str,
        removes_contribution_id: Optional[str] = None,
        capabilities: Sequence[str] = (),
        execution_context: Mapping[str, Any] | None = None,
    ) -> None:
        """Restore a failed attempt's content and its exact dirty contribution."""

        def restore() -> None:
            font = self._font_for_document(document_id)
            current = self._capture_cached_model(document_id, font)
            restoration = diff_models(current, model)
            restoration_scope = mutation_scope(current, restoration)
            self._canonical_model_cache.invalidate_glyphs(
                document_id, restoration_scope.glyph_names
            )
            restore_templates = self._master_restore_templates(operation_id)
            if not restore_templates:
                restore_templates = self._master_restore_templates(
                    removes_contribution_id
                )
            _apply_target_model(
                font,
                current,
                model,
                restoration,
                capabilities=capabilities,
                execution_context=execution_context,
                master_restore_templates=restore_templates,
                reuse_native_master_templates=True,
            )
            if any(change.path[0] == "instances" for change in restoration.changes):
                self._bind_instance_ids(
                    document_id,
                    font,
                    collection_order(model.get("instances", [])),
                )
            preferred = self._capture_cached_model(document_id, font)
            if fingerprint_model(preferred) != fingerprint_model(model):
                replacements = _canonical_replacement_roots(
                    current, model, preferred
                )
                if replacements:
                    residual = diff_models(preferred, model)
                    residual_scope = mutation_scope(preferred, residual)
                    self._canonical_model_cache.invalidate_glyphs(
                        document_id, residual_scope.glyph_names
                    )
                    _apply_target_model(
                        font,
                        preferred,
                        model,
                        residual,
                        replay_replacements=replacements,
                        capabilities=capabilities,
                        execution_context=execution_context,
                        master_restore_templates=restore_templates,
                        reuse_native_master_templates=True,
                    )
                    if any(
                        change.path[0] == "instances" for change in residual.changes
                    ):
                        self._bind_instance_ids(
                            document_id,
                            font,
                            collection_order(model.get("instances", [])),
                        )
            contributions = getattr(self, "_document_mcp_contributions", {})
            active = contributions.setdefault(document_id, {})
            pending = getattr(self, "_document_mcp_pending_reverts", {})
            pending_revert = pending.pop(operation_id, None)
            if pending_revert is not None:
                active[pending_revert["removedId"]] = pending_revert["record"]
                self._native_change_count(font, _NS_CHANGE_DONE)
            elif operation_id in active:
                active.pop(operation_id, None)
                self._native_change_count(font, _NS_CHANGE_UNDONE)
            self._master_lifecycle_tombstones.pop(operation_id, None)
            self._document_mcp_contributions = contributions
            self._document_mcp_pending_reverts = pending
            self._refresh_verified_dirty_override(
                document_id,
                font,
                current_fingerprint=fingerprint_model(model),
            )

        self._executor.run(restore)

    def reset_verified_change_tracking(self, document_id: str) -> None:
        for attribute in (
            "_document_mcp_contributions",
            "_document_mcp_baseline_dirty",
            "_document_mcp_baseline_fingerprints",
        ):
            values = getattr(self, attribute, {})
            values.pop(document_id, None)
            setattr(self, attribute, values)
        pending = getattr(self, "_document_mcp_pending_reverts", {})
        self._document_mcp_pending_reverts = {
            key: value
            for key, value in pending.items()
            if value.get("documentId") != document_id
        }
        overrides = getattr(self, "_document_dirty_overrides", {})
        overrides.pop(document_id, None)
        self._document_dirty_overrides = overrides
        self._master_lifecycle_tombstones = {
            operation_id: record
            for operation_id, record in self._master_lifecycle_tombstones.items()
            if str(record.get("documentId") or "") != document_id
        }

    def complete_observed_diff_covered(
        self, change_set: ChangeSet, execution_result: Mapping[str, Any]
    ) -> bool:
        # The canonical model deliberately excludes some open-world PyObjC and
        # application state. Live execution is therefore recovery-only until a
        # complete native archive comparison proves otherwise.
        return False

    def inspect_export_destination(self, destination: str) -> Mapping[str, Any]:
        return inspect_destination(destination)

    def export_source_bundle(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        document_id = str(payload.get("documentId") or "")
        destination = str(payload.get("destination") or "")
        expected_state = dict(payload.get("destinationState") or {})

        def produce(staged: Path) -> Mapping[str, Any]:
            try:
                from export_designspace_ufo import (  # type: ignore[import-not-found]
                    ExportDesignspaceAndUFO,
                    ExportOptions,
                )
            except Exception as exc:
                raise HostAccessError("The reviewed source exporter is unavailable") from exc
            font = self._font_for_document(document_id)
            options = ExportOptions(
                include_variable=True,
                include_static=True,
                include_build_script=False,
                output_directory=str(staged),
                open_destination=False,
            )
            result = ExportDesignspaceAndUFO(font, options=options).run()

            def relative(paths: Sequence[str]) -> list[str]:
                values = []
                for value in paths:
                    try:
                        values.append(str(Path(value).relative_to(staged)))
                    except ValueError:
                        raise HostAccessError("The exporter reported a path outside its staging directory")
                return values

            return {
                "designspaceFiles": relative(result.designspace_files),
                "masterUFOs": relative(result.master_ufos),
                "braceUFOs": relative(result.brace_ufos),
                "supportFiles": relative(result.support_files),
                "buildHelperIncluded": False,
            }

        return self._executor.run(
            lambda: publish_staged_directory(
                destination=destination,
                expected_state=expected_state,
                producer=produce,
            )
        )

    @staticmethod
    def _recovery_root() -> Path:
        return Path.home() / "Library" / "Caches" / "com.thierryc.GlyphsMCP" / "v2" / "python-recovery"

    def _cleanup_recovery(self, root: Path, document_id: str) -> None:
        cutoff = time.time() - 24 * 60 * 60
        candidates = sorted(root.glob("{}-*.glyphs".format(document_id)), key=lambda path: path.stat().st_mtime, reverse=True)
        for index, path in enumerate(candidates):
            try:
                if index >= 10 or path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass

    def _cleanup_all_recovery(self) -> None:
        root = self._recovery_root()
        if not root.is_dir():
            return
        cutoff = time.time() - 24 * 60 * 60
        for path in root.glob("*"):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass

    def create_recovery_copy(self, document_id: str, execution_id: str) -> str:
        def save() -> str:
            font = self._font_for_document(document_id)
            root = self._recovery_root()
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._cleanup_all_recovery()
            try:
                os.chmod(root, 0o700)
            except OSError:
                pass
            safe_execution = "".join(character for character in execution_id if character.isalnum() or character in "_-")
            path = root / "{}-{}.glyphs".format(document_id, safe_execution)
            copier = _safe_getattr(font, "copy")
            if not callable(copier):
                raise HostAccessError("Glyphs did not provide GSFont.copy()")
            clone = copier()
            if clone is None:
                raise HostAccessError("Glyphs returned no full document clone")
            _save_font_copy(font, path)
            os.chmod(path, 0o600)
            clones = getattr(self, "_live_recovery_clones", {})
            clones[str(path)] = {"createdAt": time.time(), "documentId": document_id, "font": clone}
            self._live_recovery_clones = {
                key: value
                for key, value in sorted(
                    clones.items(), key=lambda item: float(item[1]["createdAt"]), reverse=True
                )[:10]
                if time.time() - float(value["createdAt"]) < 60 * 60
            }
            self._cleanup_recovery(root, document_id)
            return str(path)
        return self._executor.run(save)

    def open_recovery_copy(self, path: str) -> None:
        resolved, root = Path(path).resolve(), self._recovery_root().resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise HostAccessError("Recovery paths must remain in the private v2 cache") from exc
        if not resolved.is_file():
            raise HostAccessError("The recovery copy no longer exists")
        def open_copy() -> None:
            opener = _safe_getattr(self._app, "open")
            if not callable(opener):
                raise HostAccessError("Glyphs did not provide Glyphs.open()")
            opener(str(resolved), showInterface=True)
        self._executor.run(open_copy)

    def register_recovery_checkpoint(
        self,
        execution_id: str,
        document_id: str,
        recovery_path: str,
        after_fingerprint: str,
    ) -> None:
        root = self._recovery_root()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        safe_execution = "".join(
            character for character in execution_id if character.isalnum() or character in "_-"
        )
        if not safe_execution or safe_execution != execution_id:
            raise HostAccessError("The recovery execution ID is invalid")
        manifest = root / "{}.checkpoint.json".format(safe_execution)
        temporary = root / "{}.{}.{}.checkpoint.tmp".format(
            safe_execution, os.getpid(), time.time_ns()
        )
        payload = json.dumps(
            {
                "executionId": execution_id,
                "documentId": document_id,
                "recoveryPath": recovery_path,
                "afterFingerprint": after_fingerprint,
                "createdAt": time.time(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, manifest)
            os.chmod(manifest, 0o600)
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass

    def find_recovery_checkpoint(self, execution_id: str) -> Optional[Mapping[str, Any]]:
        self._cleanup_all_recovery()
        safe_execution = "".join(
            character for character in execution_id if character.isalnum() or character in "_-"
        )
        if not safe_execution or safe_execution != execution_id:
            return None
        manifest = self._recovery_root() / "{}.checkpoint.json".format(safe_execution)
        try:
            if time.time() - manifest.stat().st_mtime > 24 * 60 * 60:
                return None
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            recovery = Path(str(payload.get("recoveryPath") or ""))
            if not recovery.is_file():
                return None
            return payload
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None


__all__ = ["GlyphsDocumentHost", "native_font_to_model", "native_layer_to_model"]
