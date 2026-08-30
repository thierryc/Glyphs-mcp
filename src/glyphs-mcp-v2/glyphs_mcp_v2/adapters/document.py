"""Glyphs 3.5/4 document snapshots, staged Python, recovery, and write-back."""

from __future__ import annotations

import builtins
import base64
import copy
import contextlib
import ctypes
import difflib
import gc
import hashlib
import io
import json
import os
import plistlib
import re
import sys
import time
import tempfile
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock, Thread
from typing import Any, Callable, Mapping, Optional, Sequence

from ..canonical_collections import (
    canonical_glyph_id,
    canonical_kerning_domain,
    collection_order,
    find_entity_index,
    indexed_entities,
    require_indexed_entities,
)
from ..canonical_tree import CanonicalSnapshot
from ..canonical_sources import (
    SerializedMappingSource,
    canonical_component,
    canonical_info_property,
    canonical_image_path,
    canonical_extension_value,
    canonical_layer_scalar,
    canonical_record_value,
    canonical_root_from_serialized_records,
)
from ..detached_python import NATIVE_CONSTRUCTOR_NAMES, build_detached_namespace
from ..exporting import inspect_destination, publish_staged_directory, resolve_destination
from ..ports import HostAccessError
from ..python_execution import (
    ObservedLivePythonError,
    PythonExecutionRequest,
)
from ..runtime_safety import (
    SafetyRepairReport,
    SafetySlotSnapshot,
    SourceSaveForbiddenError,
    StaleScriptingRuntimeIncidentError,
    ScriptingRuntimeUnavailableError,
    ScriptingSafetyStateMachine,
)
from ..mutation import (
    CANONICAL_LIFECYCLE_CAPABILITY,
    CanonicalImpact,
    LAYER_LIFECYCLE_CAPABILITY,
    MASTER_LIFECYCLE_CAPABILITY,
    MutationScope,
    is_structural_change_path,
    master_owns_layer_order_change,
    staged_lifecycle_capabilities,
    writable_subset,
)
from ..native_replay import NativeReplayEvidenceStore
from ..canonical_schema import (
    CANONICAL_FONT_SCALAR_FIELDS,
    CANONICAL_SCHEMA,
    FieldRole,
    deterministic_occurrence_id,
)
from ..canonical_views import (
    is_semantic_identity_path,
    layer_anchors as canonical_layer_anchors,
    layer_components as canonical_layer_components,
    layer_paths as canonical_layer_paths,
    layer_shapes as canonical_layer_shapes,
    semantic_identity_document,
)
from ..semantic import (
    ChangeSet,
    complete_models_equal,
    diff_models,
    fingerprint_model,
    rebase_canonical_model,
    semantic_value_at,
)
from ..saving import DocumentSaveError
from ..saved_source import SavedSourceReader
from ..source_bundle import (
    SourceBundleError,
    preflight_source_bundle as build_source_bundle_preflight,
    render_source_bundle,
)
from .glyphs import (
    GlyphsHostAdapter,
    _is_objc_proxy,
    _maybe_call,
    _native_property,
    _native_unsaved_changes,
    _safe_getattr,
    _sequence_values,
    _set_native_property,
)


_FONT_SCALARS = CANONICAL_FONT_SCALAR_FIELDS
_GLYPH_SCALARS = (
    "category",
    "subCategory",
    "unicode",
    "export",
    "leftKerningGroup",
    "rightKerningGroup",
    "topKerningGroup",
    "bottomKerningGroup",
    "script",
    "productionName",
    "sortName",
    "sortNameKeep",
    "note",
    "color",
    "locked",
    "direction",
    "case",
    "group",
    "groupIdx",
    "leftMetricsKey",
    "rightMetricsKey",
    "widthMetricsKey",
    "bottomMetricsKey",
    "topMetricsKey",
    "vertOriginMetricsKey",
    "vertWidthMetricsKey",
)
_GLYPH_METADATA_FIELDS = (
    "unicodes",
    "tags",
    "userData",
    "smartAxes",
    "partsSettings",
)
_GLYPH_DIRECT_METADATA_FIELDS = (
    "unicodes",
    *tuple(
        name
        for name in ("tags", "userData", "partsSettings")
        if name
        in CANONICAL_SCHEMA.canonical_fields_for(
            "definition.glyph",
            roles=(FieldRole.WRITABLE,),
            replays=("adapter",),
        )
    ),
)
_GLYPH_NATIVE_TEMPLATE_DEFAULTS = {
    name: CANONICAL_SCHEMA.default_for_canonical("definition.glyph", name)
    for name in CANONICAL_SCHEMA.canonical_fields_for(
        "definition.glyph", replays=("native_template_only",)
    )
}
_NATIVE_FIELD_MISSING = object()
_LAYER_SCALARS = (
    "width",
    "vertOrigin",
    "vertWidth",
    "leftMetricsKey",
    "rightMetricsKey",
    "widthMetricsKey",
    "bottomMetricsKey",
    "topMetricsKey",
    "vertOriginMetricsKey",
    "vertWidthMetricsKey",
    "active",
    "visible",
    "color",
)
_WRITABLE = (FieldRole.WRITABLE,)
_ANNOTATION_FIELDS = CANONICAL_SCHEMA.fields_for(
    "definition.annotation", roles=_WRITABLE
)
_GUIDE_FIELDS = CANONICAL_SCHEMA.fields_for(
    "definition.guide", roles=_WRITABLE
)
_HINT_FIELDS = CANONICAL_SCHEMA.fields_for(
    "definition.hint", roles=_WRITABLE
)
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


def _point_with_default(value: Any, default: tuple[float, float]) -> list[float]:
    if value is None:
        return [float(default[0]), float(default[1])]
    return _point(value)


def _mapping_keys(value: Any) -> list[str]:
    """Read keys only from proven Python/Foundation dictionary containers.

    Many rich PyObjC records advertise ``collections.abc.Mapping`` even
    though their protocol is implemented through unrelated Objective-C
    selectors. Calling ``keys()`` on such an object can therefore send
    ``-key`` to records such as ``GSAxis``. Canonical conversion recognizes
    concrete Python dictionaries and Foundation's explicit dictionary API;
    every other native object stays opaque.
    """

    if value is None:
        return []
    if isinstance(value, dict):
        # Glyphs' ObjectWrapper exposes some NSDictionary-backed values as a
        # ``dict`` subclass whose overridden ``keys`` method incorrectly
        # calls Foundation ``allKeys`` on the Python proxy. Bypass subclass
        # overrides at this adapter boundary while retaining normal dict
        # semantics for built-in mappings.
        return sorted((str(key) for key in dict.keys(value)), key=str)
    getter = _safe_getattr(value, "objectForKey_")
    if not callable(getter):
        return []
    key_provider = _safe_getattr(value, "allKeys")
    if key_provider is None:
        key_provider = _safe_getattr(value, "keys")
    raw_keys = _maybe_call(key_provider)
    keys = _native_property_list_sequence(raw_keys)
    if keys is None:
        return []
    return sorted((str(key) for key in keys), key=str)


def _mapping_get(value: Any, key: Any) -> Any:
    if isinstance(value, dict):
        try:
            return dict.__getitem__(value, key)
        except KeyError:
            return None
    getter = _safe_getattr(value, "objectForKey_")
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            return None
    try:
        return value[key]
    except Exception:
        return None


def _native_property_list_mapping_items(
    value: Any,
) -> list[tuple[str, Any]] | None:
    """Return items through an explicit Python/Foundation map boundary."""

    if isinstance(value, dict):
        keys = sorted(dict.keys(value), key=str)
        return [
            (str(key), dict.__getitem__(value, key))
            for key in keys
        ]
    getter = _safe_getattr(value, "objectForKey_")
    key_provider = _safe_getattr(value, "allKeys")
    if key_provider is None:
        key_provider = _safe_getattr(value, "keys")
    if not callable(getter) or key_provider is None:
        return None
    keys = _native_property_list_sequence(_maybe_call(key_provider))
    if keys is None:
        return None
    return [
        (str(key), getter(key))
        for key in sorted(keys, key=str)
    ]


def _is_component(value: Any) -> bool:
    return _safe_getattr(value, "componentName") is not None


def _is_path(value: Any) -> bool:
    return _safe_getattr(value, "nodes") is not None and not _is_component(value)


def _is_image(value: Any) -> bool:
    return any(
        _safe_getattr(value, name) is not None
        for name in ("imagePath", "imageURL", "crop")
    ) and not _is_path(value) and not _is_component(value)


def _is_shape_group(value: Any) -> bool:
    return _safe_getattr(value, "groupId") is not None and not any(
        (_is_path(value), _is_component(value), _is_image(value))
    )


def _layer_shapes(layer: Any) -> list[Any]:
    shapes = _sequence_values(_safe_getattr(layer, "shapes"))
    if shapes:
        return shapes
    # Compatibility for test doubles and older wrappers. Native v6 capture
    # uses GSLayer.shapes so the interleaved order is authoritative.
    return _layer_paths(layer) + _layer_components(layer)


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


def _native_layers(glyph: Any) -> list[Any]:
    layers = _safe_getattr(glyph, "layers")
    ordered = _sequence_values(layers)
    if ordered and all(
        _safe_getattr(layer, "layerId") is not None
        or _safe_getattr(layer, "id") is not None
        for layer in ordered
    ):
        # GlyphLayerProxy is Mapping-shaped, but integer access and iteration
        # implement Glyphs' authoritative presentation order: master layers
        # in font-master order followed by the native non-master layer array.
        # ``values()`` delegates to NSDictionary.allValues() and is unordered.
        return ordered
    if isinstance(layers, Mapping):
        return list(layers.values())
    return ordered


def _native_attributes(value: Any) -> dict[str, Any]:
    attributes = _safe_getattr(value, "attributes")
    if attributes is None:
        attributes = _safe_getattr(value, "attr")
    return {
        key: _plain_attribute_value(_mapping_get(attributes, key))
        for key in _mapping_keys(attributes)
    }


def _native_persistent_container(value: Any, name: str) -> Any:
    """Read a persistent container below a lossy ObjectWrapper projection."""

    native_methods = _safe_getattr(value, "pyobjc_instanceMethods")
    selector = _safe_getattr(native_methods, name)
    if callable(selector):
        try:
            return selector()
        except Exception:
            pass
    return _safe_getattr(value, name)


def _user_data_model(value: Any) -> dict[str, Any]:
    user_data = _native_persistent_container(value, "userData")
    return {
        key: _plain_attribute_value(_mapping_get(user_data, key))
        for key in _mapping_keys(user_data)
    }


def _path_model(path: Any) -> dict[str, Any]:
    nodes = []
    occurrences: dict[str, int] = {}
    for node in _sequence_values(_safe_getattr(path, "nodes")):
        precise_position = _maybe_call(_safe_getattr(node, "positionPrecise"))
        position = _point(
            precise_position
            if precise_position is not None
            else _safe_getattr(node, "position")
        )
        node_type = str(_safe_getattr(node, "type") or "line").lower()
        occurrence = occurrences.get(node_type, 0)
        occurrences[node_type] = occurrence + 1
        nodes.append(
            {
                "id": deterministic_occurrence_id("node", node_type, occurrence),
                "x": position[0],
                "y": position[1],
                "type": node_type,
                "smooth": bool(_safe_getattr(node, "smooth", False)),
                "name": _optional_text(_safe_getattr(node, "name")),
                "orientation": _plain_scalar(_safe_getattr(node, "orientation")),
                "locked": bool(_maybe_call(_safe_getattr(node, "locked", False))),
                "attributes": _native_attributes(node),
            }
        )
    return {
        "closed": bool(_safe_getattr(path, "closed", True)),
        "locked": bool(_maybe_call(_safe_getattr(path, "locked", False))),
        "attributes": _native_attributes(path),
        "nodes": nodes,
    }


def _anchor_model(layer: Any) -> list[dict[str, Any]]:
    anchors = _safe_getattr(layer, "anchors")
    result: list[dict[str, Any]] = []
    occurrences: dict[str, int] = {}
    for anchor in _sequence_values(anchors):
        name = str(_safe_getattr(anchor, "name") or "")
        occurrence = occurrences.get(name, 0)
        occurrences[name] = occurrence + 1
        result.append(
            {
                "id": deterministic_occurrence_id("anchor", name, occurrence),
                "name": name,
                "position": _point(_safe_getattr(anchor, "position")),
                "orientation": canonical_record_value(
                    "anchor",
                    "orientation",
                    _plain_scalar(_safe_getattr(anchor, "orientation")),
                ),
                "locked": bool(_maybe_call(_safe_getattr(anchor, "locked", False))),
                "attributes": _native_attributes(anchor),
                "userData": _user_data_model(anchor),
            }
        )
    if not result:
        for name in _mapping_keys(anchors):
            anchor = _mapping_get(anchors, name)
            if anchor is not None:
                occurrence = occurrences.get(name, 0)
                occurrences[name] = occurrence + 1
                result.append(
                    {
                        "id": deterministic_occurrence_id("anchor", name, occurrence),
                        "name": name,
                        "position": _point(_safe_getattr(anchor, "position")),
                        "orientation": canonical_record_value(
                            "anchor",
                            "orientation",
                            _plain_scalar(_safe_getattr(anchor, "orientation")),
                        ),
                        "locked": bool(_maybe_call(_safe_getattr(anchor, "locked", False))),
                        "attributes": _native_attributes(anchor),
                        "userData": _user_data_model(anchor),
                    }
                )
    return result


def _component_model(component: Any) -> dict[str, Any]:
    native = lambda name: CANONICAL_SCHEMA.native_field_for_canonical(
        "definition.component", name
    )
    value = lambda name, default=None: _maybe_call(
        _safe_getattr(component, native(name), default)
    )
    piece = _plain_attribute_value(value("piece"))
    return canonical_component(
        {
            "ref": value("name"),
            "pos": value("position"),
            "scale": value("scale"),
            "angle": value("angle"),
            "slant": value("slant"),
            "alignment": value("alignment"),
            "anchor": value("anchor"),
            "locked": value("locked", False),
            "masterId": value("masterId"),
            "orientation": value("orientation"),
            "keepWeight": value("keepWeight"),
            "traverseAnchors": value("traverseAnchors"),
            "attr": _plain_attribute_value(
                value("attributes") or {}
            ),
            # ``smartComponentValues`` is an official open mapping. Some
            # wrappers expose an absent placeholder whose description is the
            # string ``None``; that is not a valid document value.
            "piece": piece if isinstance(piece, Mapping) else {},
        }
    )


def _document_path_for_native(value: Any) -> Any:
    """Resolve one owning font path without retaining native objects."""

    current = value
    seen: set[int] = set()
    for _ in range(5):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        path = _maybe_call(_safe_getattr(current, "filepath"))
        if path:
            return path
        current = _maybe_call(_safe_getattr(current, "parent"))
    return None


def _image_model(image: Any, *, document_path: Any = None) -> dict[str, Any]:
    return {
        "imagePath": canonical_image_path(
            _maybe_call(_safe_getattr(image, "imagePath")), document_path
        ),
        "imageURL": _optional_text(_safe_getattr(image, "imageURL")),
        "position": _point(_safe_getattr(image, "position")),
        "scale": _point(_safe_getattr(image, "scale")),
        "crop": _plain_attribute_value(_safe_getattr(image, "crop")),
        "angle": _plain_scalar(_safe_getattr(image, "angle")),
        "slant": _plain_scalar(_safe_getattr(image, "slant")),
        "alpha": _plain_scalar(_safe_getattr(image, "alpha")),
        "locked": bool(_maybe_call(_safe_getattr(image, "locked", False))),
        "attributes": _native_attributes(image),
    }


def _shape_group_model(group: Any) -> dict[str, Any]:
    return {
        "groupId": str(_safe_getattr(group, "groupId") or ""),
        "attributes": _native_attributes(group),
    }


def _shape_models(layer: Any, *, document_path: Any = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    occurrences: dict[str, int] = {}
    for shape in _layer_shapes(layer):
        if _is_component(shape):
            kind, value = "component", _component_model(shape)
        elif _is_path(shape):
            kind, value = "path", _path_model(shape)
        elif _is_image(shape):
            kind, value = "image", _image_model(
                shape, document_path=document_path
            )
        elif _is_shape_group(shape):
            kind, value = "shape_group", _shape_group_model(shape)
        else:
            kind, value = "opaque", {
                "nativeClass": type(shape).__name__,
                "attributes": _native_attributes(shape),
            }
        occurrence = occurrences.get(kind, 0)
        occurrences[kind] = occurrence + 1
        result.append(
            {
                "id": deterministic_occurrence_id("shape", kind, occurrence),
                "kind": kind,
                "value": value,
            }
        )
    return result


def _plain_attribute_value(value: Any, *, _key: str | None = None) -> Any:
    value = _maybe_call(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return canonical_extension_value(value, _key=_key)
    mapping_items = _native_property_list_mapping_items(value)
    if mapping_items is not None:
        return {
            key: _plain_attribute_value(child, _key=key)
            for key, child in mapping_items
        }
    sequence = _native_property_list_sequence(value)
    if sequence is not None:
        return [_plain_attribute_value(item) for item in sequence]
    geometry = _native_geometry_pair(value)
    if geometry is not None:
        return [canonical_extension_value(item) for item in geometry]
    keys = _mapping_keys(value)
    if keys:
        return {
            key: _plain_attribute_value(_mapping_get(value, key), _key=key)
            for key in keys
        }
    return canonical_extension_value(str(value), _key=_key)


def _native_property_list_sequence(value: Any) -> list[Any] | None:
    """Bridge Python and Foundation array containers through one boundary."""

    if isinstance(value, (str, bytes, bytearray, dict)):
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    getter = _safe_getattr(value, "objectAtIndex_")
    count = _maybe_call(_safe_getattr(value, "count"))
    if not callable(getter):
        return None
    try:
        size = int(count)
    except (TypeError, ValueError):
        return None
    if size < 0:
        return None
    return [getter(index) for index in range(size)]


def _native_geometry_pair(value: Any) -> tuple[Any, Any] | None:
    """Return the semantic pair from CGPoint/CGSize-like native structs."""

    for first_name, second_name in (("x", "y"), ("width", "height")):
        first = _maybe_call(_safe_getattr(value, first_name))
        second = _maybe_call(_safe_getattr(value, second_name))
        if first is not None and second is not None:
            return first, second
    return None


def _persistent_property_list(value: Any, *, format_version: int = 4) -> Any:
    """Return Glyphs' documented persistent representation when available.

    Some public Glyphs properties expose rich native objects even though the
    same value is stored as an ordinary property-list tree.  Falling back to
    ``str(native_object)`` is not canonical: Objective-C descriptions may
    contain process-local addresses.  ``GSItemProtocol`` provides the exact
    serialization boundary used by the Glyphs file format, including the
    structured values of custom parameters such as ``TTFStems``.

    PyObjC returns Objective-C out parameters as a tuple ``(value, error)``.
    Test doubles and wrapper variants may return the value directly.  A
    missing or failed selector is deliberately represented by ``None`` so the
    caller can retain its existing compatibility fallback.
    """

    serializer = _safe_getattr(value, "propertyListValueFormat_error_")
    if not callable(serializer):
        return None
    try:
        result = serializer(int(format_version), None)
    except Exception:
        return None
    if isinstance(result, tuple):
        if not result:
            return None
        persistent = result[0]
        error = result[1] if len(result) > 1 else None
        if error is not None:
            return None
        return persistent
    return result


_NATIVE_PROPERTY_LIST_FLATTENER: Any = None
_NATIVE_PROPERTY_LIST_FLATTENER_LOCK = RLock()
_MISSING_PERSISTENT_FIELD = object()


_SAVED_SOURCE_READER = SavedSourceReader()


def _persistent_record_field(value: Any, name: str) -> Any:
    """Read one authoritative saved field from a native record, if exposed."""

    persistent = _persistent_property_list(value)
    if persistent is None or name not in _mapping_keys(persistent):
        return _MISSING_PERSISTENT_FIELD
    field = _mapping_get(persistent, name)
    plain, is_plain = _plain_property_list_value(field)
    if is_plain:
        return plain
    # GSItemProtocol property trees are intentionally shallow. Rich children
    # such as GSInfoValue and GSTTStem must pass through the same GlyphsCore
    # flattener as a complete document before they are canonical data.
    flattened = _native_serialized_property_tree(persistent)
    if isinstance(flattened, Mapping) and name in _mapping_keys(flattened):
        flattened_field = _mapping_get(flattened, name)
        plain, is_plain = _plain_property_list_value(flattened_field)
        return plain if is_plain else flattened_field
    return field


def _persistent_collection_records(
    owner: Any, name: str
) -> list[Mapping[str, Any]] | None:
    """Flatten one saved record collection without serializing the full font."""

    persistent = _persistent_property_list(owner)
    if persistent is None or name not in _mapping_keys(persistent):
        return None
    field = _mapping_get(persistent, name)
    flattened = _native_serialized_property_tree({name: field})
    if not isinstance(flattened, Mapping):
        return None
    plain, is_plain = _plain_property_list_value(
        _mapping_get(flattened, name)
    )
    if not is_plain or not isinstance(plain, list):
        return None
    if not all(isinstance(item, Mapping) for item in plain):
        return None
    return [dict(item) for item in plain]


_RECORD_ROOT_NATIVE_COLLECTIONS = {
    "axes": "axes",
    "masters": "masters",
    "instances": "instances",
    "metrics": "metrics",
    "stems": "stems",
    "numbers": "numbers",
    "features": "features",
    "classes": "classes",
    "featurePrefixes": "featurePrefixes",
}


def _persistent_item_records(
    owner: Any, collection_name: str
) -> list[dict[str, Any]] | None:
    """Serialize independent collection records without walking their owner."""

    result: list[dict[str, Any]] = []
    for item in _sequence_values(_safe_getattr(owner, collection_name)):
        persistent = _persistent_property_list(item)
        if persistent is None:
            return None
        flattened = _native_serialized_property_tree(persistent)
        plain, is_plain = _plain_property_list_value(flattened)
        if not is_plain or not isinstance(plain, Mapping):
            return None
        result.append(dict(plain))
    return result


def _persistent_canonical_record_root(
    font: Any,
    root: str,
    context: Mapping[str, Any],
) -> Any | None:
    collection_name = _RECORD_ROOT_NATIVE_COLLECTIONS.get(root)
    if collection_name is None:
        return None
    records = _persistent_item_records(font, collection_name)
    if records is None:
        return None
    return canonical_root_from_serialized_records(
        root,
        records,
        context=context,
    )


def _schedule_deferred_gc(callback: Callable[[], Any]) -> None:
    """Run one collection after the current MCP response can leave Python."""

    def run() -> None:
        time.sleep(1.0)
        callback()

    Thread(
        target=run,
        name="GlyphsMCPDeferredGC",
        daemon=True,
    ).start()


class _DeferredCyclicGC:
    """Keep Python GC outside verified main-thread transaction phases.

    Python 3.14 can schedule an incremental collection immediately after a
    locally disabled bulk capture. In an embedded PyObjC interpreter that
    traversal includes a large, long-lived host graph and can occupy Glyphs'
    main thread for minutes. This boundary nests across adjacent MCP calls and
    performs the young-generation cleanup only after an idle delay, on a
    daemon worker. A new transaction invalidates the pending cleanup and keeps
    GC disabled until the later transaction has also completed.
    """

    def __init__(
        self,
        *,
        scheduler: Callable[[Callable[[], Any]], Any] = _schedule_deferred_gc,
    ) -> None:
        self._scheduler = scheduler
        self._lock = RLock()
        self._depth = 0
        self._generation = 0
        self._restore_required = False

    def begin(self) -> None:
        with self._lock:
            self._generation += 1
            if self._depth == 0 and not self._restore_required and gc.isenabled():
                gc.disable()
                self._restore_required = True
            self._depth += 1

    def end(self) -> None:
        with self._lock:
            if self._depth <= 0:
                return
            self._depth -= 1
            if self._depth or not self._restore_required:
                return
            generation = self._generation
        self._scheduler(lambda: self._restore(generation))

    def _restore(self, generation: int) -> None:
        with self._lock:
            if (
                self._depth
                or generation != self._generation
                or not self._restore_required
            ):
                return
            try:
                gc.collect(0)
            finally:
                gc.enable()
                self._restore_required = False


_VERIFIED_TRANSACTION_GC = _DeferredCyclicGC()


@contextlib.contextmanager
def _suspend_cyclic_gc_for_bulk_capture():
    """Avoid repeated whole-heap scans while building one acyclic snapshot.

    JSON/font-tree containers are created in a large burst. Re-enabling the
    collector with that burst still in generation zero can immediately trigger
    an unpredictable full embedded-interpreter sweep on the next response
    allocation. Collect only generation zero while the boundary is controlled:
    this promotes or untracks the new acyclic containers without sweeping the
    older Glyphs/PyObjC generations. Global GC policy and thresholds remain
    untouched.
    """

    was_enabled = gc.isenabled()
    if was_enabled:
        gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.collect(0)
            gc.enable()


def _run_with_cyclic_gc_suspended(callback: Callable[[], Any]) -> Any:
    """Run one bounded native transaction without an arbitrary full sweep."""

    with _suspend_cyclic_gc_for_bulk_capture():
        return callback()


def _run_with_font_updates_suspended(font: Any, callback: Callable[[], Any]) -> Any:
    """Bracket one live native write with Glyphs' documented UI suspension."""

    disable = _safe_getattr(font, "disableUpdateInterface")
    enable = _safe_getattr(font, "enableUpdateInterface")
    suspended = callable(disable) and callable(enable)
    if suspended:
        disable()
    try:
        return callback()
    finally:
        if suspended:
            enable()


def _native_property_list_flattener() -> Callable[..., Any] | None:
    """Load GlyphsCore's property-tree flattener lazily.

    ``GSFont.propertyListValueFormat:error:`` intentionally returns a shallow
    tree: nested ``GSItemProtocol`` objects such as ``GSNode`` can remain native
    objects. Walking those objects through public properties one-by-one is
    prohibitively expensive for a complete font. GlyphsCore already provides
    the format-aware bulk flattener used by its document pipeline.

    Loading is lazy and adapter-local so headless tests and non-Glyphs hosts do
    not acquire an AppKit or PyObjC dependency.  Failure is cached; callers keep
    the existing authoritative manual-capture fallback.
    """

    global _NATIVE_PROPERTY_LIST_FLATTENER
    with _NATIVE_PROPERTY_LIST_FLATTENER_LOCK:
        if _NATIVE_PROPERTY_LIST_FLATTENER is False:
            return None
        if _NATIVE_PROPERTY_LIST_FLATTENER is not None:
            return _NATIVE_PROPERTY_LIST_FLATTENER
        try:
            import objc  # type: ignore[import-not-found]
            from Foundation import NSBundle  # type: ignore[import-not-found]

            bundle = NSBundle.bundleWithPath_(
                "/Applications/Glyphs 4.app/Contents/Frameworks/"
                "GlyphsCore.framework"
            )
            if bundle is None or not bundle.load():
                raise RuntimeError("GlyphsCore could not be loaded")
            functions: dict[str, Any] = {}
            objc.loadBundleFunctions(
                bundle,
                functions,
                [
                    ("GSFlattenDictionary", b"@@C^@"),
                ],
            )
            codec = functions["GSFlattenDictionary"]
        except Exception:
            _NATIVE_PROPERTY_LIST_FLATTENER = False
            return None
        _NATIVE_PROPERTY_LIST_FLATTENER = codec
        return codec


def _native_serialized_property_tree(
    persistent: Any, *, format_version: int = 4
) -> Mapping[str, Any] | None:
    """Flatten a shallow Glyphs property tree entirely inside GlyphsCore."""

    def result_value(result: Any) -> Any:
        if not isinstance(result, tuple):
            return result
        if not result:
            return None
        if len(result) > 1 and result[1] is not None:
            return None
        return result[0]

    flatten = _native_property_list_flattener()
    if flatten is None:
        return None
    try:
        flattened = result_value(
            flatten(persistent, int(format_version), None)
        )
        if isinstance(flattened, Mapping):
            try:
                from Foundation import (  # type: ignore[import-not-found]
                    NSJSONSerialization,
                )

                encoded = (
                    NSJSONSerialization.dataWithJSONObject_options_error_(
                        flattened,
                        0,
                        None,
                    )
                )
                error = (
                    encoded[1]
                    if isinstance(encoded, tuple) and len(encoded) > 1
                    else None
                )
                data = result_value(encoded)
                if error is not None and os.environ.get(
                    "GLYPHS_MCP_DEBUG_CAPTURE"
                ):
                    print(
                        "[Glyphs MCP][CanonicalCapture] native JSON bridge rejected: {}".format(
                            str(error)[:500]
                        )
                    )
                if data is not None:
                    raw = _native_data_bytes(data)
                    plain = json.loads(raw) if raw is not None else None
                    if isinstance(plain, Mapping):
                        return plain
            except Exception:
                pass
            try:
                from Foundation import (  # type: ignore[import-not-found]
                    NSPropertyListBinaryFormat_v1_0,
                    NSPropertyListSerialization,
                )

                encoded = (
                    NSPropertyListSerialization.dataWithPropertyList_format_options_error_(
                        flattened,
                        NSPropertyListBinaryFormat_v1_0,
                        0,
                        None,
                    )
                )
                error = (
                    encoded[1]
                    if isinstance(encoded, tuple) and len(encoded) > 1
                    else None
                )
                data = result_value(encoded)
                raw = _native_data_bytes(data) if data is not None else None
                if error is None and raw is not None:
                    plain = plistlib.loads(raw)
                    if isinstance(plain, Mapping):
                        return plain
            except Exception:
                pass
            # Never feed a bridged NSDictionary or a shallow built-in mapping
            # recursively through the canonical converter. Glyphs' native
            # flattener may return a Python ``dict`` whose descendants are
            # still PyObjC objects; protocol-based inspection of one such
            # object can invoke arbitrary Objective-C selectors. The bulk
            # optimization is available only after the complete tree crosses
            # the strict detached-property-list boundary.
            return (
                flattened
                if type(flattened) is dict
                and _is_strict_plain_property_list_value(flattened)
                else None
            )
    except Exception:
        return None
    return None


def _native_data_bytes(data: Any) -> bytes | None:
    """Copy one NSData-like value through a bounded native buffer bridge.

    ``bytes(NSData)`` can iterate one byte at a time on some PyObjC/Python
    combinations. Canonical font trees routinely exceed ten MiB, so that
    convenience conversion is not an acceptable main-thread boundary.
    """

    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, memoryview):
        return data.tobytes()
    try:
        return memoryview(data).tobytes()
    except Exception:
        pass
    try:
        length = int(_maybe_call(_safe_getattr(data, "length")) or 0)
        pointer = _maybe_call(_safe_getattr(data, "bytes"))
        as_buffer = _safe_getattr(pointer, "as_buffer")
        if callable(as_buffer):
            return memoryview(as_buffer(length)).tobytes()
    except Exception:
        pass
    try:
        length = int(_maybe_call(_safe_getattr(data, "length")) or 0)
        target = bytearray(length)
        copier = _safe_getattr(data, "getBytes_length_")
        if callable(copier):
            copier(target, length)
            return bytes(target)
    except Exception:
        pass
    return None


def _native_openstep_property_list(path: Path) -> Any:
    """Decode one saved Glyphs v4 mapping through the pinned OpenStep parser.

    Glyphs' flat and package files use the OpenStep property-list syntax.
    Python's ``plistlib`` does not parse that syntax, and Foundation's legacy
    collection convenience initializers reject valid modern Glyphs package
    records on some hosts. ``openstep_plist`` is the small parser used by the
    official Glyphs file-format tooling; it returns a detached Python tree and
    does not introduce a second canonicalization implementation.
    """

    try:
        from openstep_plist import load as load_openstep  # type: ignore[import-not-found]

        with path.open("r", encoding="utf-8") as stream:
            return load_openstep(stream, use_numbers=True)
    except Exception:
        # Keep the native bridge as a compatibility fallback for an incomplete
        # development environment. Release/runtime validation requires the
        # pinned parser, so a failed fallback merely disqualifies the saved
        # fast path and never weakens verification.
        pass

    try:
        from Foundation import (  # type: ignore[import-not-found]
            NSArray,
            NSDictionary,
            NSJSONSerialization,
        )
    except Exception:
        return None

    value = NSDictionary.dictionaryWithContentsOfFile_(str(path))
    if value is None:
        value = NSArray.arrayWithContentsOfFile_(str(path))
    if value is None:
        return None
    try:
        encoded = NSJSONSerialization.dataWithJSONObject_options_error_(
            value, 0, None
        )
        if isinstance(encoded, tuple):
            if len(encoded) > 1 and encoded[1] is not None:
                return None
            encoded = encoded[0] if encoded else None
        raw = _native_data_bytes(encoded) if encoded is not None else None
        return json.loads(raw) if raw is not None else None
    except Exception:
        return None


def _saved_package_mapping(
    package_path: Path,
    *,
    decoder: Callable[[Path], Any] = _native_openstep_property_list,
) -> Mapping[str, Any] | None:
    """Load a Glyphs package as one source-neutral serialized mapping."""

    fontinfo = decoder(package_path / "fontinfo.plist")
    order = decoder(package_path / "order.plist")
    kerning_path = package_path / "kerning.plist"
    kerning = decoder(kerning_path) if kerning_path.exists() else {}
    glyph_directory = package_path / "glyphs"
    if not isinstance(fontinfo, Mapping) or not isinstance(order, list):
        return None
    if not isinstance(kerning, Mapping) or not glyph_directory.is_dir():
        return None

    glyphs: dict[str, Any] = {}
    for path in sorted(glyph_directory.glob("*.glyph")):
        glyph = decoder(path)
        if not isinstance(glyph, Mapping):
            return None
        name = str(glyph.get("glyphname") or "")
        if not name or name in glyphs:
            return None
        glyphs[name] = glyph

    fontinfo_copy = copy.deepcopy(dict(fontinfo))
    feature_directory = package_path / "features"
    for collection_name in ("features", "classes", "featurePrefixes"):
        records = fontinfo_copy.get(collection_name)
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict) or record.get("code") is not None:
                continue
            file_name = str(record.get("file") or "")
            if not file_name:
                continue
            feature_path = feature_directory / file_name
            try:
                record["code"] = feature_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                return None

    mapping: dict[str, Any] = {
        "fontinfo.plist": fontinfo_copy,
        "order.plist": list(order),
        "kerning.plist": copy.deepcopy(dict(kerning)),
        "glyphs": glyphs,
    }
    note_path = package_path / "note.md"
    if note_path.exists():
        try:
            mapping["note.md"] = note_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return None
    return mapping


def _saved_source_canonical_model(
    path: Path,
    *,
    instance_ids: Optional[Sequence[str]] = None,
) -> Mapping[str, Any] | None:
    """Decode through the neutral stable reader without touching live objects."""

    result = _SAVED_SOURCE_READER.read(
        path,
        instance_ids=tuple(str(value) for value in (instance_ids or ())),
    )
    return result.snapshot.model if result.snapshot is not None else None


def _saved_document_canonical_model(
    font: Any,
    *,
    instance_ids: Optional[Sequence[str]] = None,
) -> Mapping[str, Any] | None:
    """Capture a clean saved document without materializing the live font."""

    def unavailable(reason: str) -> None:
        if os.environ.get("GLYPHS_MCP_DEBUG_CAPTURE"):
            print(
                "[Glyphs MCP][CanonicalCapture] saved mapping unavailable: {}".format(
                    reason
                ),
                flush=True,
            )

    path_value = _safe_getattr(font, "filepath")
    if not path_value:
        unavailable("document has no path")
        return None
    document = _maybe_call(_safe_getattr(font, "parent"))
    if _native_unsaved_changes(document) is not False:
        unavailable("document is not authoritatively clean")
        return None
    path = Path(str(path_value))
    if path.suffix.lower() not in {".glyphs", ".glyphspackage"}:
        unavailable("document path is not a supported Glyphs v4 source")
        return None
    model = _saved_source_canonical_model(path, instance_ids=instance_ids)
    if not isinstance(model, dict):
        unavailable("OpenStep source decoding or canonical conversion failed")
        return None
    glyph_models = model.get("glyphs")
    if not isinstance(glyph_models, Mapping):
        unavailable("canonical glyph root is not a mapping")
        return None
    native_glyphs = {
        str(_safe_getattr(glyph, "name") or ""): glyph
        for glyph in _sequence_values(_safe_getattr(font, "glyphs"))
        if str(_safe_getattr(glyph, "name") or "")
    }
    if set(native_glyphs) != set(glyph_models):
        unavailable(
            "glyph identity mismatch native={} saved={}".format(
                len(native_glyphs), len(glyph_models)
            )
        )
        return None
    if not all(isinstance(glyph_model, dict) for glyph_model in glyph_models.values()):
        unavailable("canonical glyph shard is not mutable during identity proof")
        return None
    if not _saved_model_matches_live_identity(native_glyphs, glyph_models):
        unavailable("live glyph identity proof disagrees with saved source")
        return None
    return model


def _saved_model_matches_live_identity(
    native_glyphs: Mapping[str, Any],
    saved_glyphs: Mapping[str, Any],
) -> bool:
    """Reject a falsely-clean restored window before trusting its disk tree."""

    for name, saved in saved_glyphs.items():
        if not isinstance(saved, Mapping):
            return False
        native = native_glyphs.get(str(name))
        if native is None:
            return False
        if bool(_maybe_call(_safe_getattr(native, "export", True))) != bool(
            saved.get("export", True)
        ):
            return False
        saved_unicode = saved.get("unicode")
        if saved_unicode is None:
            continue
        native_unicode = _maybe_call(_safe_getattr(native, "unicode"))
        if native_unicode in (None, ""):
            return False
        text = str(native_unicode).strip().upper()
        if text.startswith("U+"):
            text = text[2:]
        try:
            text = "{:04X}".format(int(text, 16))
        except ValueError:
            pass
        if text != str(saved_unicode):
            return False
    return True


def _debug_first_serialized_node(value: Any) -> str:
    """Return one bounded node representation for capture diagnostics."""

    pending = [value]
    visited = 0
    while pending and visited < 10_000:
        current = pending.pop()
        visited += 1
        if isinstance(current, Mapping):
            for key, child in current.items():
                if str(key) == "nodes":
                    values = list(child) if isinstance(child, Sequence) else []
                    first = values[0] if values else child
                    return "container={} firstType={} first={!r}".format(
                        type(child).__name__, type(first).__name__, first
                    )[:500]
                pending.append(child)
        elif isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            pending.extend(current)
    return "not_found"


def _persistent_custom_parameter_value(parameter: Any) -> Any:
    """Capture one custom-parameter value in official format-v4 form."""

    # The Python-facing ``value`` is not always the saved value. In particular,
    # GSFont.copy() can bridge structured parameters as an ordinary Objective-C
    # description string while GSItemProtocol still exposes the authoritative
    # property-list tree. Prefer that documented persistence boundary for every
    # parameter; the scalar/plain fast path is only a compatibility fallback.
    persistent_value = _persistent_record_field(parameter, "value")
    if persistent_value is not _MISSING_PERSISTENT_FIELD:
        return canonical_extension_value(
            _plain_attribute_value(persistent_value)
        )
    raw_value = _safe_getattr(parameter, "value")
    plain, is_plain = _plain_property_list_value(raw_value)
    if is_plain:
        return canonical_extension_value(plain)
    return canonical_extension_value(_plain_attribute_value(raw_value))


def _plain_property_list_value(value: Any) -> tuple[Any, bool]:
    """Fast-path values that are already ordinary persistent data.

    Most custom parameters contain a scalar or a Python property-list tree.
    Asking PyObjC whether every one of those objects implements the native
    serializer is needlessly expensive.  This bounded recursive probe avoids
    selector discovery for ordinary values while rejecting a collection as a
    whole when any child is a rich native object.  The caller can then invoke
    Glyphs' official serializer exactly once for that owning parameter.
    """

    value = _maybe_call(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value, True
    mapping_items = _native_property_list_mapping_items(value)
    if mapping_items is not None:
        result = {}
        for key, raw_child in mapping_items:
            child, is_plain = _plain_property_list_value(raw_child)
            if not is_plain:
                return None, False
            result[key] = child
        return result, True
    sequence = _native_property_list_sequence(value)
    if sequence is not None:
        result = []
        for item in sequence:
            child, is_plain = _plain_property_list_value(item)
            if not is_plain:
                return None, False
            result.append(child)
        return result, True
    geometry = _native_geometry_pair(value)
    if geometry is not None:
        return [canonical_extension_value(item) for item in geometry], True
    return None, False


def _strict_plain_property_list_value(value: Any) -> tuple[Any, bool]:
    """Validate a detached built-in property-list tree without host access.

    PyObjC objects can advertise Python mapping or sequence protocols while
    implementing them through Objective-C selectors. A validator must not
    invoke those protocols merely to decide whether native objects escaped a
    bulk flatten. Only exact built-in containers cross this boundary; every
    other object makes the optimization unavailable.
    """

    if value is None or type(value) in (bool, int, float, str):
        return value, True
    if type(value) is dict:
        result: dict[str, Any] = {}
        for key, child in value.items():
            if type(key) not in (str, int, float, bool):
                return None, False
            plain, is_plain = _strict_plain_property_list_value(child)
            if not is_plain:
                return None, False
            result[str(key)] = plain
        return result, True
    if type(value) in (list, tuple):
        result = []
        for child in value:
            plain, is_plain = _strict_plain_property_list_value(child)
            if not is_plain:
                return None, False
            result.append(plain)
        return result, True
    return None, False


def _is_strict_plain_property_list_value(value: Any) -> bool:
    """Prove the exact built-in property-list boundary without copying it."""

    pending = [value]
    while pending:
        current = pending.pop()
        if current is None or type(current) in (bool, int, float, str):
            continue
        if type(current) is dict:
            for key, child in current.items():
                if type(key) not in (str, int, float, bool):
                    return False
                pending.append(child)
            continue
        if type(current) in (list, tuple):
            pending.extend(current)
            continue
        return False
    return True


def _layer_attributes(layer: Any) -> dict[str, Any]:
    attributes = _safe_getattr(layer, "attributes")
    return {
        key: _plain_attribute_value(_mapping_get(attributes, key))
        for key in _mapping_keys(attributes)
    }


def _axis_tag_mapping(axis_tags: Optional[Mapping[str, str]]) -> dict[str, str]:
    return {str(key): str(value) for key, value in dict(axis_tags or {}).items()}


def _interpolation_model(
    attributes: Mapping[str, Any],
    *,
    axis_tags: Optional[Mapping[str, str]],
    is_intermediate: bool,
    is_alternate: bool,
) -> dict[str, Any] | None:
    tag_by_id = _axis_tag_mapping(axis_tags)
    coordinates = attributes.get("coordinates")
    if isinstance(coordinates, Mapping) or is_intermediate:
        values = coordinates if isinstance(coordinates, Mapping) else {}
        return {
            "kind": "intermediate",
            "coordinates": {
                tag_by_id.get(str(axis_id), str(axis_id)): _plain_attribute_value(value)
                for axis_id, value in sorted(values.items(), key=lambda item: str(item[0]))
            },
        }
    rules = attributes.get("axisRules")
    if isinstance(rules, Mapping) or is_alternate:
        values = rules if isinstance(rules, Mapping) else {}
        ranges: dict[str, dict[str, Any]] = {}
        for axis_id, rule in sorted(values.items(), key=lambda item: str(item[0])):
            source = rule if isinstance(rule, Mapping) else {}
            ranges[tag_by_id.get(str(axis_id), str(axis_id))] = {
                "min": _plain_attribute_value(source.get("min")),
                "max": _plain_attribute_value(source.get("max")),
            }
        return {"kind": "alternate", "ranges": ranges}
    return None


def _generic_record_model(
    value: Any, fields: Sequence[str], *, kind: str
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in fields:
        native_name = (
            "position"
            if name == "pos"
            else "attributes"
            if name == "attr"
            else name
        )
        native = _safe_getattr(value, native_name)
        plain = _plain_attribute_value(native)
        result[name] = canonical_record_value(kind, name, plain)
    return result


def _ordered_records(
    owner: Any,
    attribute: str,
    *,
    kind: str,
    fields: Sequence[str],
) -> list[dict[str, Any]]:
    result = []
    occurrences: dict[str, int] = {}
    for value in _sequence_values(_safe_getattr(owner, attribute)):
        semantic = str(
            _plain_scalar(_safe_getattr(value, "name"))
            or _plain_scalar(_safe_getattr(value, "type"))
            or kind
        )
        occurrence = occurrences.get(semantic, 0)
        occurrences[semantic] = occurrence + 1
        result.append(
            {
                "id": deterministic_occurrence_id(kind, semantic, occurrence),
                **_generic_record_model(value, fields, kind=kind),
            }
        )
    return result


def _background_model(
    background: Any, *, document_path: Any = None
) -> dict[str, Any] | None:
    if background is None:
        return None
    result = {
        "anchors": _anchor_model(background),
        "annotations": _ordered_records(
            background,
            "annotations",
            kind="annotation",
            fields=_ANNOTATION_FIELDS,
        ),
        "backgroundImage": (
            _image_model(
                _safe_getattr(background, "backgroundImage"),
                document_path=document_path,
            )
            if _safe_getattr(background, "backgroundImage") is not None
            else None
        ),
        "guides": _ordered_records(
            background,
            "guides",
            kind="guide",
            fields=_GUIDE_FIELDS,
        ),
        "hints": _ordered_records(
            background,
            "hints",
            kind="hint",
            fields=_HINT_FIELDS,
        ),
        "shapes": _shape_models(background, document_path=document_path),
    }
    return result if any(value not in (None, [], {}) for value in result.values()) else None


def _layer_roles(
    layer: Any,
    attributes: Mapping[str, Any],
    interpolation: Mapping[str, Any] | None,
) -> list[str]:
    if bool(_maybe_call(_safe_getattr(layer, "isMasterLayer", False))):
        return ["master"]
    roles: list[str] = []
    kind = str(interpolation.get("kind") or "") if interpolation else ""
    if kind == "intermediate":
        roles.append("intermediate")
    if kind == "alternate":
        roles.append("alternate")
    if bool(_maybe_call(_safe_getattr(layer, "isSmartComponentLayer", False))):
        roles.append("smart")
    if bool(_maybe_call(_safe_getattr(layer, "isColorPaletteLayer", False))) or any(
        key in attributes for key in ("colorPalette", "sbixSize", "svg")
    ):
        roles.append("color")
    # Backup is the fallback role, not an additive specialization. A copied
    # backup layer can retain a stale native flag briefly after interpolation
    # attributes are attached; the canonical role follows the authoritative
    # interpolation payload instead.
    if not roles and bool(
        _maybe_call(_safe_getattr(layer, "isBackupLayer", False))
    ):
        roles.append("backup")
    if not roles:
        roles.append("backup")
    return roles


def _layer_model(
    layer: Any,
    *,
    axis_tags: Optional[Mapping[str, str]] = None,
    document_path: Any = None,
) -> dict[str, Any]:
    if document_path in (None, ""):
        document_path = _document_path_for_native(layer)
    layer_id = str(_safe_getattr(layer, "layerId") or _safe_getattr(layer, "id") or "")
    master_id = str(_safe_getattr(layer, "associatedMasterId") or layer_id)
    attributes = _layer_attributes(layer)
    interpolation = _interpolation_model(
        attributes,
        axis_tags=axis_tags,
        is_intermediate=bool(
            _maybe_call(_safe_getattr(layer, "isBraceLayer", False))
        ),
        is_alternate=bool(
            _maybe_call(_safe_getattr(layer, "isBracketLayer", False))
        ),
    )
    canonical_attributes = {
        key: copy.deepcopy(value)
        for key, value in attributes.items()
        if key not in {"coordinates", "axisRules"}
    }
    roles = _layer_roles(layer, attributes, interpolation)
    values = {
        "id": layer_id,
        "masterId": master_id,
        "name": str(_safe_getattr(layer, "name") or ""),
        "roles": roles,
        "isMasterLayer": bool(_maybe_call(_safe_getattr(layer, "isMasterLayer", False))),
        "isSpecialLayer": bool(
            _maybe_call(_safe_getattr(layer, "isSpecialLayer", False))
        )
        or bool(set(roles) & {"intermediate", "alternate", "smart"}),
        "interpolation": interpolation,
        "attributes": canonical_attributes,
        "anchors": _anchor_model(layer),
        "annotations": _ordered_records(
            layer,
            "annotations",
            kind="annotation",
            fields=_ANNOTATION_FIELDS,
        ),
        "background": _background_model(
            _safe_getattr(layer, "background"), document_path=document_path
        ),
        "backgroundImage": (
            _image_model(
                _safe_getattr(layer, "backgroundImage"),
                document_path=document_path,
            )
            if _safe_getattr(layer, "backgroundImage") is not None
            else None
        ),
        "guides": _ordered_records(
            layer,
            "guides",
            kind="guide",
            fields=_GUIDE_FIELDS,
        ),
        "hints": _ordered_records(
            layer,
            "hints",
            kind="hint",
            fields=_HINT_FIELDS,
        ),
        "partSelection": _plain_attribute_value(
            _safe_getattr(layer, "partSelection")
        ),
        "shapes": _shape_models(layer, document_path=document_path),
        "userData": _user_data_model(layer),
    }
    for name in _LAYER_SCALARS:
        # A master layer inherits its visibility from the owning master. The
        # saved layer record has no independent visibility field, while the
        # live getter projects the master's value and GSFont.copy() does not.
        # Canonical ownership therefore remains with the master record.
        raw_value = (
            False
            if name == "visible" and values["isMasterLayer"]
            else _plain_scalar(_safe_getattr(layer, name))
        )
        values[name] = canonical_layer_scalar(name, raw_value)
    return values


def native_layer_to_model(
    layer: Any, *, axis_tags: Optional[Mapping[str, str]] = None
) -> dict[str, Any]:
    """Return one detached canonical layer for drawing-only consumers."""

    return _layer_model(layer, axis_tags=axis_tags)


class NativeLayerOverlayProjector:
    """Incrementally copy one layer's visual primitives on the host thread."""

    def __init__(self, layer: Any) -> None:
        layer_id = str(
            _safe_getattr(layer, "layerId") or _safe_getattr(layer, "id") or ""
        )
        self._result = {
            "id": layer_id,
            "masterId": str(_safe_getattr(layer, "associatedMasterId") or layer_id),
            "width": _plain_scalar(_safe_getattr(layer, "width")),
            "anchors": [],
            "shapes": [],
        }
        self._paths = tuple(
            shape for shape in _layer_shapes(layer) if _is_path(shape)
        )
        self._anchors = tuple(
            _sequence_values(_safe_getattr(layer, "anchors"))
        )
        self._path_index = 0
        self._node_index = 0
        self._active_path: dict[str, Any] | None = None
        self._active_nodes: tuple[Any, ...] = ()
        self._anchor_index = 0
        self._anchor_occurrences: dict[str, int] = {}
        self.complete = False

    def step(
        self,
        *,
        budget_seconds: float = 0.002,
        clock: Callable[[], float] = time.perf_counter,
    ) -> bool:
        """Copy at least one primitive and yield once the time budget expires."""

        if self.complete:
            return True
        deadline = clock() + max(0.0, float(budget_seconds))
        progressed = False
        while self._path_index < len(self._paths):
            native_path = self._paths[self._path_index]
            if self._active_path is None:
                self._active_path = {
                    "closed": bool(_safe_getattr(native_path, "closed", True)),
                    "nodes": [],
                }
                self._active_nodes = tuple(
                    _sequence_values(_safe_getattr(native_path, "nodes"))
                )
                self._node_index = 0
            while self._node_index < len(self._active_nodes):
                node = self._active_nodes[self._node_index]
                position = _point(_safe_getattr(node, "position"))
                self._active_path["nodes"].append(
                    {
                        "x": position[0],
                        "y": position[1],
                        "type": str(_safe_getattr(node, "type") or "line").lower(),
                    }
                )
                self._node_index += 1
                progressed = True
                if clock() >= deadline:
                    return False
            self._result["shapes"].append(
                {
                    "id": deterministic_occurrence_id(
                        "shape", "path", self._path_index
                    ),
                    "kind": "path",
                    "value": self._active_path,
                }
            )
            self._active_path = None
            self._active_nodes = ()
            self._path_index += 1
            if progressed and clock() >= deadline:
                return False

        while self._anchor_index < len(self._anchors):
            anchor = self._anchors[self._anchor_index]
            name = str(_safe_getattr(anchor, "name") or "")
            occurrence = self._anchor_occurrences.get(name, 0)
            self._anchor_occurrences[name] = occurrence + 1
            self._result["anchors"].append(
                {
                    "id": deterministic_occurrence_id(
                        "anchor", name, occurrence
                    ),
                    "name": name,
                    "position": _point(_safe_getattr(anchor, "position")),
                }
            )
            self._anchor_index += 1
            progressed = True
            if clock() >= deadline:
                return False
        self.complete = True
        return True

    def result(self) -> dict[str, Any]:
        if not self.complete:
            raise RuntimeError("layer overlay projection is incomplete")
        return self._result


def native_layer_overlay_state(layer: Any) -> dict[str, Any]:
    """Project only the native values consumed by the drawing-only Reporter."""

    projector = NativeLayerOverlayProjector(layer)
    while not projector.step(budget_seconds=float("inf")):
        pass
    return projector.result()


def _canonical_layer_projection(
    native_layers: Sequence[Mapping[str, Any]],
    reference_glyph: Mapping[str, Any] | None,
) -> list[Mapping[str, Any]]:
    """Keep root-owned master presentation out of nested layer history.

    Glyphs projects every glyph's master-layer prefix from the font master
    collection. Reordering masters therefore changes the native presentation
    of hundreds of layer dictionaries even though the canonical nested
    collection did not change. A verified transition uses its source/target
    glyph shard as the stable identity order for retained master layers.

    Newly attached master layers are inserted at their root-projected index;
    deleted layers simply disappear. Non-master order is always taken from the
    native glyph and is never normalized, so layer lifecycle changes and
    unexpected host effects remain observable.
    """

    layers = list(native_layers)
    if not isinstance(reference_glyph, Mapping):
        return layers
    reference_layers = reference_glyph.get("layers", ())
    if not isinstance(reference_layers, (list, tuple)):
        return layers
    native_indexed = indexed_entities(layers)
    reference_indexed = indexed_entities(reference_layers)
    if native_indexed is None or reference_indexed is None:
        return layers
    native_order, native_by_id = native_indexed
    reference_order, reference_by_id = reference_indexed
    native_master_order = [
        identity
        for identity in native_order
        if isinstance(native_by_id.get(identity), Mapping)
        and bool(native_by_id[identity].get("isMasterLayer"))
    ]
    reference_master_order = [
        identity
        for identity in reference_order
        if isinstance(reference_by_id.get(identity), Mapping)
        and bool(reference_by_id[identity].get("isMasterLayer"))
    ]
    native_master_ids = set(native_master_order)
    projected_master_order = [
        identity
        for identity in reference_master_order
        if identity in native_master_ids
    ]
    for native_index, identity in enumerate(native_master_order):
        if identity not in reference_by_id:
            projected_master_order.insert(
                min(native_index, len(projected_master_order)), identity
            )
    # If an identity changed role, retain it once in the native non-master
    # partition. Its modeled role field still makes the transition mismatch.
    native_non_master_order = [
        identity
        for identity in native_order
        if identity not in native_master_ids
    ]
    projected_order = projected_master_order + native_non_master_order
    if len(projected_order) != len(native_order) or set(projected_order) != set(
        native_order
    ):
        return layers
    return [native_by_id[identity] for identity in projected_order]


def _native_presence_value(value: Any, name: str) -> object:
    """Read an adapter-only explicit-presence flag when the host exposes it."""

    raw = _safe_getattr(value, name, _NATIVE_FIELD_MISSING)
    if raw is _NATIVE_FIELD_MISSING:
        return _NATIVE_FIELD_MISSING
    return _maybe_call(raw)


def _glyph_scalar_value(glyph: Any, field: str) -> Any:
    """Capture one glyph override without confusing it with its host default."""

    presence = CANONICAL_SCHEMA.native_presence_field_for_canonical(
        "definition.glyph", field
    )
    if presence is not None:
        stored = _native_presence_value(glyph, presence)
        if stored is not _NATIVE_FIELD_MISSING and not bool(stored):
            return None
    return _plain_scalar(_safe_getattr(glyph, field))


def _glyph_native_template_field_value(glyph: Any, field: str) -> Any:
    """Capture a serialized field that has no guaranteed live selector.

    Glyphs 4 preserves these values inside a native glyph copy/tombstone but
    may omit them from ObjectWrapper entirely. When a selector is absent, use
    the official canonical default. Non-default state remains protected by the
    native template and complete serialized/native verification boundaries.
    """

    if field not in _GLYPH_NATIVE_TEMPLATE_DEFAULTS:
        raise HostAccessError(
            "glyph field is not registered for native-template capture: {}".format(
                field
            )
        )
    raw = _safe_getattr(glyph, field, _NATIVE_FIELD_MISSING)
    if raw is not _NATIVE_FIELD_MISSING:
        plain = _plain_attribute_value(_maybe_call(raw))
        if plain is not None:
            return canonical_extension_value(plain)
    return copy.deepcopy(_GLYPH_NATIVE_TEMPLATE_DEFAULTS[field])


def _apply_glyph_scalar_updates(
    glyph: Any,
    current: Mapping[str, Any],
    target: Mapping[str, Any],
    *,
    whole_glyph: bool,
    changed_fields: set[str],
) -> None:
    """Replay glyph overrides and their native presence flags as one unit.

    A presence flag may own more than one canonical field (notably
    ``storeSortName``).  Decide each flag from the complete target glyph
    before assigning individual values so field order cannot erase a sibling
    override.  Hosts without these flags keep the legacy direct-property path.
    """

    selected = tuple(
        field
        for field in _GLYPH_SCALARS
        if field in target
        and (whole_glyph or field in changed_fields)
        and current.get(field) != target.get(field)
    )
    presence_groups: dict[str, list[str]] = {}
    for field in _GLYPH_SCALARS:
        if field not in target:
            continue
        presence = CANONICAL_SCHEMA.native_presence_field_for_canonical(
            "definition.glyph", field
        )
        if presence is not None:
            presence_groups.setdefault(presence, []).append(field)

    enabled_presence: dict[str, bool] = {}
    for presence in {
        CANONICAL_SCHEMA.native_presence_field_for_canonical(
            "definition.glyph", field
        )
        for field in selected
    }:
        if presence is None:
            continue
        if _native_presence_value(glyph, presence) is _NATIVE_FIELD_MISSING:
            continue
        enabled = any(
            target.get(field) is not None
            for field in presence_groups.get(presence, ())
        )
        _set_native_property(glyph, presence, enabled)
        enabled_presence[presence] = enabled

    for field in selected:
        presence = CANONICAL_SCHEMA.native_presence_field_for_canonical(
            "definition.glyph", field
        )
        target_value = target.get(field)
        if (
            presence is not None
            and presence in enabled_presence
            and not enabled_presence[presence]
            and target_value is None
        ):
            # Clearing the presence flag is the native representation of an
            # absent value. Integer-backed setters must never receive None.
            continue
        _set_native_property(glyph, field, target_value)
    if set(selected).intersection(
        {"leftMetricsKey", "rightMetricsKey", "widthMetricsKey"}
    ):
        for layer in _native_layers(glyph):
            sync_metrics = _safe_getattr(layer, "syncMetrics")
            if not callable(sync_metrics):
                raise HostAccessError(
                    "Glyphs did not expose GSLayer.syncMetrics for a glyph metrics-key update"
                )
            sync_metrics()


def _glyph_model(
    glyph: Any,
    *,
    axis_tags: Optional[Mapping[str, str]] = None,
    layer_order_reference: Mapping[str, Any] | None = None,
    document_path: Any = None,
) -> dict[str, Any]:
    name = str(_safe_getattr(glyph, "name") or "")
    layers: list[dict[str, Any]] = []
    for layer in _native_layers(glyph):
        model = _layer_model(
            layer, axis_tags=axis_tags, document_path=document_path
        )
        if model["id"]:
            layers.append(model)
    layers = list(_canonical_layer_projection(layers, layer_order_reference))
    if indexed_entities(layers) is None:
        raise HostAccessError("Glyphs returned duplicate or empty layer identities")
    result = {
        "name": name,
        # Native glyph UUIDs can be regenerated after deletion. The glyph map
        # is already name-keyed, so its canonical identity must be semantic.
        "id": canonical_glyph_id(name),
        "mastersCompatible": bool(_maybe_call(_safe_getattr(glyph, "mastersCompatible", False))),
        "layers": layers,
    }
    for scalar in _GLYPH_SCALARS:
        result[scalar] = _glyph_scalar_value(glyph, scalar)
    unicodes = _sequence_values(_safe_getattr(glyph, "unicodes"))
    if not unicodes:
        unicode_value = _safe_getattr(glyph, "unicode")
        unicodes = [unicode_value] if unicode_value not in (None, "") else []
    result.update(
        {
            "unicodes": [str(value) for value in unicodes],
            "tags": [str(value) for value in _sequence_values(_safe_getattr(glyph, "tags"))],
            "userData": _user_data_model(glyph),
            "smartAxes": _ordered_records(
                glyph,
                "axes",
                kind="smart_axis",
                fields=("name", "bottomValue", "topValue"),
            ),
            "partsSettings": _glyph_native_template_field_value(
                glyph, "partsSettings"
            ),
        }
    )
    return result


def _glyph_fragment_model(
    glyph: Any,
    base_glyph: Mapping[str, Any],
    paths: Sequence[Sequence[str]],
    *,
    axis_tags: Optional[Mapping[str, str]] = None,
    layer_order_reference: Mapping[str, Any] | None = None,
    document_path: Any = None,
) -> dict[str, Any]:
    """Materialize only glyph fields named by canonical semantic paths."""

    if any(len(path) <= 2 for path in paths):
        return _glyph_model(
            glyph,
            axis_tags=axis_tags,
            document_path=document_path,
            layer_order_reference=layer_order_reference or base_glyph,
        )
    result = dict(base_glyph)
    for path in paths:
        if len(path) == 3:
            field = str(path[2])
            if field == "mastersCompatible":
                result[field] = bool(
                    _maybe_call(
                        _safe_getattr(glyph, "mastersCompatible", False)
                    )
                )
            elif field in _GLYPH_SCALARS:
                result[field] = _glyph_scalar_value(glyph, field)
            elif field == "unicodes":
                values = _sequence_values(_safe_getattr(glyph, "unicodes"))
                result[field] = [str(value) for value in values]
            elif field == "tags":
                result[field] = [
                    str(value) for value in _sequence_values(_safe_getattr(glyph, "tags"))
                ]
            elif field == "userData":
                result[field] = _user_data_model(glyph)
            elif field == "smartAxes":
                result[field] = _ordered_records(
                    glyph,
                    "smartComponentAxes",
                    kind="smartAxis",
                    fields=("name", "bottomValue", "topValue"),
                )
            elif field == "partsSettings":
                result[field] = _glyph_native_template_field_value(glyph, field)
    layer_ids = tuple(
        dict.fromkeys(
            str(path[3])
            for path in paths
            if len(path) >= 4 and path[2] == "layers"
        )
    )
    if layer_ids:
        layers = list(base_glyph.get("layers", ()))
        for layer_id in layer_ids:
            native = _lookup_layer(glyph, layer_id)
            index = find_entity_index(layers, layer_id)
            if native is None:
                if index is not None:
                    del layers[index]
            else:
                layer = _layer_model(
                    native,
                    axis_tags=axis_tags,
                    document_path=document_path,
                )
                if index is None:
                    layers.append(layer)
                else:
                    layers[index] = layer
        native_order = [
            str(_safe_getattr(layer, "layerId") or _safe_getattr(layer, "id") or "")
            for layer in _native_layers(glyph)
        ]
        if set(native_order) == {str(layer.get("id") or "") for layer in layers}:
            by_id = {str(layer.get("id") or ""): layer for layer in layers}
            layers = [by_id[identity] for identity in native_order]
        layers = list(
            _canonical_layer_projection(
                layers,
                layer_order_reference or base_glyph,
            )
        )
        result["layers"] = layers
    return result


def _path_matches_model(path: Any, expected: Mapping[str, Any]) -> bool:
    if bool(_safe_getattr(path, "closed", True)) != bool(
        expected.get("closed", True)
    ):
        return False
    native_nodes = _sequence_values(_safe_getattr(path, "nodes"))
    expected_nodes = expected.get("nodes", ())
    if not isinstance(expected_nodes, (list, tuple)) or len(native_nodes) != len(
        expected_nodes
    ):
        return False
    for native, modeled in zip(native_nodes, expected_nodes):
        if not isinstance(modeled, Mapping):
            return False
        precise = _maybe_call(_safe_getattr(native, "positionPrecise"))
        position = _point(
            precise if precise is not None else _safe_getattr(native, "position")
        )
        if (
            position[0] != modeled.get("x")
            or position[1] != modeled.get("y")
            or str(_safe_getattr(native, "type") or "line").lower()
            != str(modeled.get("type") or "line")
            or bool(_safe_getattr(native, "smooth", False))
            != bool(modeled.get("smooth", False))
            or _optional_text(_safe_getattr(native, "name"))
            != modeled.get("name")
        ):
            return False
    return True


def _layer_matches_model(layer: Any, expected: Mapping[str, Any]) -> bool:
    layer_id = str(
        _safe_getattr(layer, "layerId") or _safe_getattr(layer, "id") or ""
    )
    master_id = str(_safe_getattr(layer, "associatedMasterId") or layer_id)
    if (
        layer_id != str(expected.get("id") or "")
        or master_id != str(expected.get("masterId") or "")
        or str(_safe_getattr(layer, "name") or "")
        != str(expected.get("name") or "")
        or bool(_maybe_call(_safe_getattr(layer, "isMasterLayer", False)))
        != bool(expected.get("isMasterLayer", False))
        or bool(_maybe_call(_safe_getattr(layer, "isSpecialLayer", False)))
        != bool(expected.get("isSpecialLayer", False))
    ):
        return False
    for name in _LAYER_SCALARS:
        if _plain_scalar(_safe_getattr(layer, name)) != expected.get(name):
            return False
    if tuple(_anchor_model(layer)) != canonical_layer_anchors(expected):
        return False
    native_paths = _layer_paths(layer)
    expected_paths = canonical_layer_paths(expected)
    if not isinstance(expected_paths, (list, tuple)) or len(native_paths) != len(
        expected_paths
    ):
        return False
    if any(
        not isinstance(modeled, Mapping)
        or not _path_matches_model(native, modeled)
        for native, modeled in zip(native_paths, expected_paths)
    ):
        return False
    components = _layer_components(layer)
    expected_components = canonical_layer_components(expected)
    if not isinstance(expected_components, (list, tuple)) or len(components) != len(
        expected_components
    ):
        return False
    for native, modeled in zip(components, expected_components):
        if not isinstance(modeled, Mapping) or _component_model(native) != modeled:
            return False
    return True


def _glyph_matches_model(glyph: Any, expected: Mapping[str, Any]) -> bool:
    name = str(_safe_getattr(glyph, "name") or "")
    if (
        name != str(expected.get("name") or "")
        or canonical_glyph_id(name) != str(expected.get("id") or "")
        or bool(_maybe_call(_safe_getattr(glyph, "mastersCompatible", False)))
        != bool(expected.get("mastersCompatible", False))
    ):
        return False
    for field_name in _GLYPH_SCALARS:
        if _glyph_scalar_value(glyph, field_name) != expected.get(field_name):
            return False
    expected_layers = expected.get("layers", ())
    indexed = indexed_entities(expected_layers)
    if indexed is None:
        return False
    expected_order, expected_by_id = indexed
    native_layers = _native_layer_index(glyph)
    native_order = [
        str(_safe_getattr(layer, "layerId") or _safe_getattr(layer, "id") or "")
        for layer in _native_layers(glyph)
    ]
    return native_order == expected_order and set(native_layers) == set(expected_by_id) and all(
        isinstance(expected_by_id[key], Mapping)
        and _layer_matches_model(layer, expected_by_id[key])
        for key, layer in native_layers.items()
    )


def _glyph_root_matches_model(glyph: Any, expected: Mapping[str, Any]) -> bool:
    """Compare authoritative glyph fields without traversing layer contents."""

    name = str(_safe_getattr(glyph, "name") or "")
    if (
        name != str(expected.get("name") or "")
        or canonical_glyph_id(name) != str(expected.get("id") or "")
        or bool(_maybe_call(_safe_getattr(glyph, "mastersCompatible", False)))
        != bool(expected.get("mastersCompatible", False))
    ):
        return False
    return all(
        _glyph_scalar_value(glyph, field_name) == expected.get(field_name)
        for field_name in _GLYPH_SCALARS
    )


def _glyph_root_revision_evidence(glyph: Any) -> dict[str, Any]:
    """Capture authoritative native evidence for one glyph root only.

    The evidence is intentionally source-neutral: it proves that fields not
    owned by the pending semantic patch stayed unchanged across the live
    transaction. It is never hashed into canonical content and never asks the
    source mapping and projected ObjectWrapper getters to share a spelling.
    """

    unicodes = _sequence_values(_safe_getattr(glyph, "unicodes"))
    if not unicodes:
        unicode_value = _safe_getattr(glyph, "unicode")
        unicodes = [unicode_value] if unicode_value not in (None, "") else []
    return {
        "name": str(_safe_getattr(glyph, "name") or ""),
        "id": str(_safe_getattr(glyph, "id") or ""),
        "mastersCompatible": bool(
            _maybe_call(_safe_getattr(glyph, "mastersCompatible", False))
        ),
        **{
            name: _glyph_scalar_value(glyph, name)
            for name in _GLYPH_SCALARS
        },
        "unicodes": tuple(str(value) for value in unicodes),
        "tags": tuple(
            str(value) for value in _sequence_values(_safe_getattr(glyph, "tags"))
        ),
        "userData": _user_data_model(glyph),
        "smartAxes": tuple(
            _ordered_records(
                glyph,
                "axes",
                kind="smart_axis",
                fields=("name", "bottomValue", "topValue"),
            )
        ),
        "partsSettings": _glyph_native_template_field_value(
            glyph, "partsSettings"
        ),
    }


def _native_layer_index(glyph: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for layer in _native_layers(glyph):
        layer_id = str(
            _safe_getattr(layer, "layerId") or _safe_getattr(layer, "id") or ""
        )
        if layer_id and layer_id not in result:
            result[layer_id] = layer
    return result


def _layer_revision_token(layer: Any) -> tuple[Any, ...] | None:
    """Return bounded native evidence covering one otherwise-reused layer.

    Glyphs 4's ``lastUpdate`` changes for outline, anchor, component, and metric
    edits. It is paired with canonical scalar, role, and attribute values so
    layer metadata that does not advance that clock is still visible. The
    token never traverses paths, components, or anchors; a clock mismatch
    causes the complete canonical layer to be materialized and compared.
    Hosts without this native clock retain the conservative full-layer path.
    """

    raw_last_update = _safe_getattr(layer, "lastUpdate")
    if raw_last_update is None:
        return None
    try:
        last_update = _plain_scalar(raw_last_update)
        if last_update is None:
            return None
    except Exception:
        return None
    is_master = bool(
        _maybe_call(_safe_getattr(layer, "isMasterLayer", False))
    )
    return (
        str(_safe_getattr(layer, "layerId") or _safe_getattr(layer, "id") or ""),
        str(_safe_getattr(layer, "associatedMasterId") or ""),
        str(_safe_getattr(layer, "name") or ""),
        is_master,
        bool(_maybe_call(_safe_getattr(layer, "isSpecialLayer", False))),
        bool(_maybe_call(_safe_getattr(layer, "isBraceLayer", False))),
        bool(_maybe_call(_safe_getattr(layer, "isBracketLayer", False))),
        bool(_maybe_call(_safe_getattr(layer, "isSmartComponentLayer", False))),
        bool(_maybe_call(_safe_getattr(layer, "isColorPaletteLayer", False))),
        bool(_maybe_call(_safe_getattr(layer, "isBackupLayer", False))),
        bool(_maybe_call(_safe_getattr(layer, "hasAlignedWidth", False))),
        # Master layers normally carry no interpolation attributes. Avoid an
        # Objective-C dictionary bridge for the dominant 5 x glyph-count
        # surface while retaining exact special-layer metadata evidence.
        "{}"
        if is_master
        else json.dumps(
            _layer_attributes(layer), sort_keys=True, separators=(",", ":")
        ),
        tuple(_plain_scalar(_safe_getattr(layer, name)) for name in _LAYER_SCALARS),
        last_update,
    )


def _layer_revision_index(glyph: Any) -> dict[str, tuple[Any, ...] | None]:
    return {
        key: _layer_revision_token(layer)
        for key, layer in _native_layer_index(glyph).items()
    }


def _verified_glyph_fragment_matches(
    glyph: Any,
    modeled: Mapping[str, Any],
    expected: Mapping[str, Any],
    paths: Sequence[Sequence[str]],
    *,
    before_root_evidence: Mapping[str, Any] | None = None,
    current_root_evidence: Mapping[str, Any] | None = None,
    before_layer_tokens: Mapping[str, tuple[Any, ...] | None] | None,
    current_layer_tokens: Mapping[str, tuple[Any, ...] | None],
) -> bool:
    """Prove a predicted glyph fragment without rescanning sibling outlines."""

    if modeled != expected:
        return False
    if before_root_evidence is not None and current_root_evidence is not None:
        root_is_replaced = any(len(path) <= 2 for path in paths)
        impacted_root_fields = {
            str(path[2])
            for path in paths
            if len(path) == 3 and path[2] != "layers"
        }
        if not root_is_replaced:
            for field in set(before_root_evidence) | set(current_root_evidence):
                if field in impacted_root_fields:
                    continue
                if before_root_evidence.get(field) != current_root_evidence.get(field):
                    return False
    elif not _glyph_root_matches_model(glyph, expected):
        # Compatibility path for hosts/tests that have not seeded lazy native
        # evidence. Production transactions always seed affected glyphs before
        # their one live apply.
        return False
    expected_layers = expected.get("layers", ())
    indexed = indexed_entities(expected_layers)
    if indexed is None:
        return False
    expected_order, expected_by_id = indexed
    if set(current_layer_tokens) != set(expected_order):
        return False
    # Master order belongs to the font's master collection. Glyphs may reorder
    # the corresponding native layer objects as a derived side effect, but the
    # canonical glyph shard must remain reusable. Non-master layer order is a
    # schema-v5 lifecycle field and must still match exactly.
    expected_master_ids = {
        identity
        for identity, layer in expected_by_id.items()
        if isinstance(layer, Mapping) and bool(layer.get("isMasterLayer"))
    }
    current_master_ids = {
        identity
        for identity, token in current_layer_tokens.items()
        if token is not None and len(token) > 3 and bool(token[3])
    }
    if current_master_ids != expected_master_ids:
        return False
    expected_non_master_order = tuple(
        identity for identity in expected_order if identity not in expected_master_ids
    )
    current_non_master_order = tuple(
        identity
        for identity, token in current_layer_tokens.items()
        if token is not None and len(token) > 3 and not bool(token[3])
    )
    if current_non_master_order != expected_non_master_order:
        return False
    impacted = {
        str(path[3])
        for path in paths
        if len(path) >= 4 and path[2] == "layers"
    }
    before_layer_tokens = before_layer_tokens or {}
    for layer_id, token in current_layer_tokens.items():
        if layer_id in impacted:
            continue
        before_token = before_layer_tokens.get(layer_id)
        if token is None or before_token is None or token != before_token:
            return False
    return True


def _custom_parameter_models(owner: Any) -> list[dict[str, Any]]:
    values = []
    occurrences: dict[str, int] = {}
    for parameter in _sequence_values(_safe_getattr(owner, "customParameters")):
        name = str(_safe_getattr(parameter, "name") or "")
        occurrence = occurrences.get(name, 0)
        occurrences[name] = occurrence + 1
        values.append(
            {
                "id": deterministic_occurrence_id("parameter", name, occurrence),
                "name": name,
                "value": _persistent_custom_parameter_value(parameter),
                "disabled": bool(
                    _native_property(parameter, "disabled", False, objc_boolean=True)
                ),
            }
        )
    return values


def _property_models(owner: Any) -> list[dict[str, Any]]:
    values = []
    occurrences: dict[str, int] = {}
    for property_value in _sequence_values(_safe_getattr(owner, "properties")):
        key = str(
            _safe_getattr(property_value, "key")
            or _safe_getattr(property_value, "name")
            or ""
        )
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        localized = []
        for item in _sequence_values(_safe_getattr(property_value, "values")):
            localized.append(
                {
                    "language": str(
                        _safe_getattr(item, "language")
                        or _safe_getattr(item, "languageTag")
                        or ""
                    ),
                    "value": _plain_attribute_value(_safe_getattr(item, "value")),
                }
            )
        values.append(
            {
                "id": deterministic_occurrence_id("property", key, occurrence),
                **canonical_info_property(
                    key,
                    _plain_attribute_value(
                        _safe_getattr(property_value, "value")
                    ),
                    localized,
                ),
            }
        )
    return values


def _metric_definition_bindings(
    font: Any, attribute: str
) -> list[tuple[str, dict[str, Any]]]:
    """Bind one canonical definition identity to its native Glyphs ID.

    Glyphs serializes master metric/stem/number values positionally, but its
    live API exposes ID-addressed dictionaries.  The canonical seam uses the
    semantic root-definition identity while this adapter-local binding keeps
    the process-specific native IDs out of fingerprints and public data.
    """

    result = []
    occurrences: dict[str, int] = {}
    for value in _sequence_values(_safe_getattr(font, attribute)):
        raw_type = _plain_scalar(_safe_getattr(value, "type"))
        if raw_type in (0, "0", "0.0", ""):
            # Glyphs uses zero as the live sentinel for the format-v4
            # omission used by named custom metrics, stems, and numbers.
            raw_type = None
        normalized = {
            "type": CANONICAL_SCHEMA.canonical_value_for_official(
                "definition.metric", "type", raw_type
            ),
            "name": str(_safe_getattr(value, "name") or ""),
            "horizontal": bool(
                _maybe_call(_safe_getattr(value, "horizontal", False))
            ),
            "filter": _optional_text(_safe_getattr(value, "filter")),
        }
        semantic = "{}:{}:{}:{}".format(
            normalized["type"],
            normalized["name"],
            normalized["horizontal"],
            normalized["filter"] or "",
        )
        occurrence = occurrences.get(semantic, 0)
        occurrences[semantic] = occurrence + 1
        canonical = {
            "id": deterministic_occurrence_id(
                attribute[:-1] or attribute, semantic, occurrence
            ),
            **normalized,
        }
        result.append(
            (str(_safe_getattr(value, "id") or ""), canonical)
        )
    return result


def _metric_models(font: Any, attribute: str) -> list[dict[str, Any]]:
    return [model for _native_id, model in _metric_definition_bindings(font, attribute)]


_MISSING_STORE_VALUE = object()


def _native_store_value(store: Any, native_id: str, index: int) -> Any:
    store = _maybe_call(store)
    if isinstance(store, Mapping):
        return store.get(native_id, _MISSING_STORE_VALUE)
    getter = _safe_getattr(store, "objectForKey_")
    if callable(getter):
        value = getter(native_id)
        return _MISSING_STORE_VALUE if value is None else value
    values = _sequence_values(store)
    return values[index] if index < len(values) else _MISSING_STORE_VALUE


def _native_metric_scalar(value: Any, primary: str, fallback: str) -> Any:
    raw = _maybe_call(_safe_getattr(value, primary))
    if raw is None:
        raw = _maybe_call(_safe_getattr(value, fallback))
    return 0 if raw is None else _plain_scalar(raw)


def _master_store_models(
    owner: Any,
    attribute: str,
    bindings: Sequence[tuple[str, Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    store = _safe_getattr(owner, attribute)
    values = []
    for index, (native_id, definition) in enumerate(bindings):
        value = _native_store_value(store, native_id, index)
        if value is _MISSING_STORE_VALUE:
            continue
        if attribute == "metricValues":
            values.append(
                {
                    "id": str(definition.get("id") or ""),
                    "pos": _native_metric_scalar(value, "position", "pos"),
                    "over": _native_metric_scalar(value, "overshoot", "over"),
                }
            )
            continue
        if isinstance(value, Mapping):
            scalar = value.get("value", value.get("width"))
        else:
            scalar = _maybe_call(_safe_getattr(value, "value"))
        if scalar is None and isinstance(value, (bool, int, float, str)):
            scalar = value
        values.append(
            {
                "id": str(definition.get("id") or ""),
                "value": 0 if scalar is None else _plain_scalar(scalar),
            }
        )
    return values


def _axis_models(font: Any) -> list[dict[str, Any]]:
    result = []
    native_axes = _sequence_values(_safe_getattr(font, "axes"))
    persistent_axes = _persistent_collection_records(font, "axes") or []
    for index, axis in enumerate(native_axes):
        tag = str(
            _safe_getattr(axis, "axisTag") or _safe_getattr(axis, "tag") or ""
        )
        if not tag:
            raise HostAccessError("Glyphs returned an axis without a tag")
        has_persistent_axis = index < len(persistent_axes)
        persistent_axis = persistent_axes[index] if has_persistent_axis else {}
        # Once the official record exists, omission is authoritative and maps
        # to the format schema's empty localized-name default. Falling back to
        # the editor wrapper would mix a second source into one canonical
        # record and can observe transient/mis-bound PyObjC proxy state during
        # structural read-back.
        persistent_names = (
            persistent_axis.get("names", [])
            if has_persistent_axis
            else _MISSING_PERSISTENT_FIELD
        )
        names = _plain_attribute_value(
            _safe_getattr(axis, "names")
            if persistent_names is _MISSING_PERSISTENT_FIELD
            else persistent_names
        )
        result.append(
            {
                "id": tag,
                "tag": tag,
                "name": str(_safe_getattr(axis, "name") or ""),
                "names": names if isinstance(names, (list, dict)) else [],
                "default": _plain_scalar(_safe_getattr(axis, "default")),
                "hidden": bool(_maybe_call(_safe_getattr(axis, "hidden", False))),
                "userData": _user_data_model(axis),
            }
        )
    return result


def _axis_coordinate_models(font: Any) -> list[dict[str, str]]:
    """Return only the stable tags needed to bind master/instance positions."""

    result = []
    for axis in _sequence_values(_safe_getattr(font, "axes")):
        tag = str(
            _safe_getattr(axis, "axisTag") or _safe_getattr(axis, "tag") or ""
        )
        if not tag:
            raise HostAccessError("Glyphs returned an axis without a tag")
        result.append({"tag": tag})
    return result


def _axis_revision_evidence(font: Any) -> list[dict[str, Any]]:
    """Capture bounded native proof without reading unsafe localized wrappers."""

    return [
        {
            "tag": axis["tag"],
            "name": str(_safe_getattr(native, "name") or ""),
            "default": _plain_scalar(_safe_getattr(native, "default")),
            "hidden": bool(_maybe_call(_safe_getattr(native, "hidden", False))),
        }
        for native, axis in zip(
            _sequence_values(_safe_getattr(font, "axes")),
            _axis_coordinate_models(font),
        )
    ]


def _axis_tag_by_native_id(font: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    for axis in _sequence_values(_safe_getattr(font, "axes")):
        tag = str(_safe_getattr(axis, "axisTag") or _safe_getattr(axis, "tag") or "")
        native_id = str(_safe_getattr(axis, "axisId") or _safe_getattr(axis, "id") or tag)
        if tag and native_id:
            result[native_id] = tag
    return result


def _master_models(font: Any) -> list[dict[str, Any]]:
    axes = _axis_coordinate_models(font)
    metric_bindings = _metric_definition_bindings(font, "metrics")
    stem_bindings = _metric_definition_bindings(font, "stems")
    number_bindings = _metric_definition_bindings(font, "numbers")
    result = []
    for master in _sequence_values(_safe_getattr(font, "masters")):
        positions = _sequence_values(_safe_getattr(master, "axes"))
        result.append(
            {
                "id": str(_safe_getattr(master, "id") or ""),
                "name": str(_safe_getattr(master, "name") or ""),
                "italicAngle": _plain_scalar(_safe_getattr(master, "italicAngle")),
                "active": bool(_maybe_call(_safe_getattr(master, "active", False))),
                "visible": bool(_maybe_call(_safe_getattr(master, "visible", True))),
                "iconName": _optional_text(_safe_getattr(master, "iconName")),
                "axes": [
                    {"tag": axis.get("tag"), "internal": _plain_scalar(positions[index]) if index < len(positions) else None}
                    for index, axis in enumerate(axes)
                ],
                "customParameters": _custom_parameter_models(master),
                "properties": _property_models(master),
                "guides": _ordered_records(
                    master,
                    "guides",
                    kind="guide",
                    fields=_GUIDE_FIELDS,
                ),
                "metricValues": _master_store_models(
                    master, "metricValues", metric_bindings
                ),
                "stemValues": _master_store_models(
                    master, "stemValues", stem_bindings
                ),
                "numberValues": _master_store_models(
                    master, "numberValues", number_bindings
                ),
                "userData": _user_data_model(master),
            }
        )
    return result


def _instance_models(
    font: Any, *, instance_ids: Optional[Sequence[str]] = None
) -> list[dict[str, Any]]:
    axes = _axis_coordinate_models(font)
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
        if not external_positions:
            # Glyphs File Format v4 defines axesValues as the effective
            # external coordinates too when no separate mapping exists.
            # Mirror that semantic rule in live capture so source seams
            # converge instead of manufacturing a reorder-only diff.
            external_positions = positions
        canonical_positions = [
            _plain_scalar(positions[axis_index])
            if axis_index < len(positions)
            else 0
            if is_variable
            else None
            for axis_index in range(len(axes))
        ]
        canonical_external_positions = []
        for axis_index, internal_position in enumerate(canonical_positions):
            external_position = (
                _plain_scalar(external_positions[axis_index])
                if axis_index < len(external_positions)
                else None
            )
            canonical_external_positions.append(
                internal_position if external_position is None else external_position
            )
        included_value = _safe_getattr(instance, "active")
        if included_value is None:
            included_value = _safe_getattr(instance, "exports", True)
        manual_interpolation = bool(
            _maybe_call(_safe_getattr(instance, "manualInterpolation", False))
        )
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
                "exports": bool(_maybe_call(_safe_getattr(instance, "exports", included_value))),
                "visible": bool(_maybe_call(_safe_getattr(instance, "visible", True))),
                "isBold": bool(_maybe_call(_safe_getattr(instance, "isBold", False))),
                "isItalic": bool(_maybe_call(_safe_getattr(instance, "isItalic", False))),
                "linkStyle": _optional_text(_safe_getattr(instance, "linkStyle")),
                "manualInterpolation": manual_interpolation,
                "weightClass": _plain_scalar(_safe_getattr(instance, "weightClass")),
                "widthClass": _plain_scalar(_safe_getattr(instance, "widthClass")),
                "instanceInterpolations": (
                    _plain_attribute_value(
                        _safe_getattr(instance, "instanceInterpolations")
                    )
                    if manual_interpolation
                    else {}
                ),
                "customParameters": _custom_parameter_models(instance),
                "properties": _property_models(instance),
                "userData": _user_data_model(instance),
                "axes": [
                    {
                        "tag": axis.get("tag"),
                        "internal": canonical_positions[axis_index],
                        "external": canonical_external_positions[axis_index],
                    }
                    for axis_index, axis in enumerate(axes)
                ],
            }
        )
    return result


def _code_collection(font: Any, attribute: str) -> list[dict[str, Any]]:
    return [
        {
            "id": str(
                _native_property(value, "name", "")
                or "{}_{}".format(attribute, index)
            ),
            "name": str(_native_property(value, "name", "") or ""),
            "tag": str(
                _native_property(value, "tag", "")
                or _native_property(value, "name", "")
                or ""
            ),
            "code": str(_native_property(value, "code", "") or ""),
            "automatic": bool(
                _native_property(value, "automatic", False, objc_boolean=True)
            ),
            "disabled": bool(
                _native_property(value, "disabled", False, objc_boolean=True)
            ),
            "notes": _optional_text(_native_property(value, "notes")),
            "labels": _feature_label_models(value) if attribute == "features" else [],
        }
        for index, value in enumerate(_sequence_values(_safe_getattr(font, attribute)))
    ]


def _feature_label_models(feature: Any) -> list[dict[str, Any]]:
    """Read official feature labels through either Glyphs host spelling."""

    native_label = _maybe_call(_safe_getattr(feature, "label"))
    if native_label is not None:
        return [
            {
                "language": str(
                    _safe_getattr(value, "language")
                    or _safe_getattr(value, "languageTag")
                    or "dflt"
                ),
                "value": str(_safe_getattr(value, "value") or ""),
            }
            for value in _sequence_values(_safe_getattr(native_label, "values"))
        ]
    legacy = _native_property(feature, "labels")
    return list(canonical_extension_value(legacy or []))


def _kerning_domain_model(
    font: Any, attribute: str
) -> dict[str, dict[str, dict[str, Any]]]:
    glyph_names: list[str] = []
    native_aliases: dict[str, str] = {}
    for glyph in _sequence_values(_safe_getattr(font, "glyphs")):
        name = str(_safe_getattr(glyph, "name") or "")
        if not name:
            continue
        glyph_names.append(name)
        canonical = canonical_glyph_id(name)
        native_id = str(_maybe_call(_safe_getattr(glyph, "id")) or "")
        if native_id:
            native_aliases[native_id] = canonical

    def normalize(raw_value: Any) -> Any:
        try:
            return float(raw_value)
        except Exception:
            return _plain_attribute_value(raw_value)

    # ObjectWrapper's kerning containers are NSDictionary-like proxies rather
    # than guaranteed Python ``Mapping`` instances. Read their three known
    # levels through the adapter boundary before applying the source-neutral
    # semantic key resolver. Converting the outer proxy generically can yield
    # an empty tree on a dirty GSFont even though its partitions are present.
    kerning = _safe_getattr(font, attribute)
    raw_domain: dict[str, dict[str, dict[str, Any]]] = {}
    for master_id in _mapping_keys(kerning):
        lefts = _mapping_get(kerning, master_id)
        for left in _mapping_keys(lefts):
            rights = _mapping_get(lefts, left)
            for right in _mapping_keys(rights):
                raw_domain.setdefault(master_id, {}).setdefault(left, {})[
                    right
                ] = _mapping_get(rights, right)
    return canonical_kerning_domain(
        raw_domain,
        glyph_names=glyph_names,
        native_aliases=native_aliases,
        normalize_value=normalize,
    )


def _kerning_model(font: Any) -> dict[str, Any]:
    return {
        "ltr": _kerning_domain_model(font, "kerning"),
        "rtl": _kerning_domain_model(font, "kerningRTL"),
        "vertical": _kerning_domain_model(font, "kerningVertical"),
        "context": _context_kerning_model(font),
    }


def _context_kerning_model(font: Any) -> dict[str, dict[str, Any]]:
    """Capture Glyphs 4's context-key -> master -> numeric value domain."""

    source = _maybe_call(_safe_getattr(font, "kerningContext"))
    result: dict[str, dict[str, Any]] = {}
    for context_key in _mapping_keys(source):
        master_values = _mapping_get(source, context_key)
        for master_id in _mapping_keys(master_values):
            raw_value = _mapping_get(master_values, master_id)
            try:
                value: Any = float(raw_value)
            except Exception:
                value = _plain_attribute_value(raw_value)
            result.setdefault(str(context_key), {})[str(master_id)] = value
    return result


def _settings_model(font: Any) -> dict[str, Any]:
    source = _safe_getattr(font, "settings")
    result = {
        key: _plain_attribute_value(_mapping_get(source, key))
        for key in _mapping_keys(source)
    }
    # Grid values have one canonical owner under ``font``. Some native builds
    # also project them through the settings dictionary.
    result.pop("gridLength", None)
    result.pop("gridSubDivision", None)
    aliases = {
        "disablesAutomaticAlignment": "disablesAutomaticAlignment",
        "disablesNiceNames": "disablesNiceNames",
        "keepAlternatesTogether": "keepAlternatesTogether",
        "keyboardIncrement": "keyboardIncrement",
        "keyboardIncrementBig": "keyboardIncrementBig",
        "keyboardIncrementHuge": "keyboardIncrementHuge",
        "previewRemoveOverlap": "previewRemoveOverlap",
        "snapToObjects": "snapToObjects",
        "fontType": "fontType",
    }
    for canonical, native in aliases.items():
        value = _safe_getattr(font, native)
        if value is not None:
            result[canonical] = _plain_attribute_value(value)
    result.setdefault("dependencies", {})
    return result


def _apply_settings_model(
    font: Any, current: Mapping[str, Any], target: Mapping[str, Any]
) -> None:
    aliases = {
        "disablesAutomaticAlignment": "disablesAutomaticAlignment",
        "disablesNiceNames": "disablesNiceNames",
        "keepAlternatesTogether": "keepAlternatesTogether",
        "keyboardIncrement": "keyboardIncrement",
        "keyboardIncrementBig": "keyboardIncrementBig",
        "keyboardIncrementHuge": "keyboardIncrementHuge",
        "previewRemoveOverlap": "previewRemoveOverlap",
        "snapToObjects": "snapToObjects",
        "fontType": "fontType",
    }
    for key, native in aliases.items():
        if current.get(key) != target.get(key):
            _set_native_property(font, native, copy.deepcopy(target.get(key)))
    mapping_target = {
        str(key): copy.deepcopy(value)
        for key, value in target.items()
        if str(key) not in aliases
    }
    current_mapping = {
        str(key): copy.deepcopy(value)
        for key, value in current.items()
        if str(key) not in aliases
    }
    if current_mapping == mapping_target:
        return
    # ``readSettingDict:`` is Glyphs' format-owned replay boundary. There is no
    # public ``font.settings`` property in Glyphs 4, and ObjectWrapper may
    # expose only individual documented settings. Replaying the complete saved
    # mapping here also preserves reviewed extension keys such as color-space
    # state without introducing one setter branch per key.
    reader = _safe_getattr(font, "readSettingDict_")
    if callable(reader):
        reader(mapping_target)
        return
    # Compatibility fallback for fakes and older wrappers that expose an
    # assignable mapping owner directly.
    try:
        _set_native_property(font, "settings", mapping_target)
        return
    except Exception:
        pass
    mapping = _safe_getattr(font, "settings")
    if mapping is None:
        raise HostAccessError("Glyphs did not expose writable font settings")
    _replace_mapping_values(mapping, mapping_target)


def _font_model_with_glyphs(
    font: Any,
    glyphs: Mapping[str, Any],
    *,
    masters: Optional[Sequence[Mapping[str, Any]]] = None,
    instance_ids: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    return {
        "font": {
            **{name: _plain_scalar(_safe_getattr(font, name)) for name in _FONT_SCALARS},
            "customParameters": _custom_parameter_models(font),
            "properties": _property_models(font),
            "userData": _user_data_model(font),
        },
        "axes": _axis_models(font),
        "masters": list(masters) if masters is not None else _master_models(font),
        "instances": _instance_models(font, instance_ids=instance_ids),
        "glyphs": dict(glyphs),
        "glyphOrder": [
            str(_safe_getattr(glyph, "name") or "")
            for glyph in _sequence_values(_safe_getattr(font, "glyphs"))
            if str(_safe_getattr(glyph, "name") or "")
        ],
        "kerning": _kerning_model(font),
        "features": _code_collection(font, "features"),
        "classes": _code_collection(font, "classes"),
        "featurePrefixes": _code_collection(font, "featurePrefixes"),
        "metrics": _metric_models(font, "metrics"),
        "stems": _metric_models(font, "stems"),
        "numbers": _metric_models(font, "numbers"),
        "settings": _settings_model(font),
    }


def native_font_to_model(
    font: Any,
    *,
    instance_ids: Optional[Sequence[str]] = None,
    layer_order_reference_model: Mapping[str, Any] | None = None,
    document_path: Any = None,
) -> dict[str, Any]:
    if document_path in (None, ""):
        document_path = _safe_getattr(font, "filepath")
    axis_tags = _axis_tag_by_native_id(font)
    reference_glyphs = (
        layer_order_reference_model.get("glyphs", {})
        if isinstance(layer_order_reference_model, Mapping)
        else {}
    )
    if not isinstance(reference_glyphs, Mapping):
        reference_glyphs = {}
    glyphs = {}
    for glyph in _sequence_values(_safe_getattr(font, "glyphs")):
        name = str(_safe_getattr(glyph, "name") or "")
        reference = reference_glyphs.get(name)
        model = _glyph_model(
            glyph,
            axis_tags=axis_tags,
            document_path=document_path,
            layer_order_reference=(
                reference if isinstance(reference, Mapping) else None
            ),
        )
        if model["name"]:
            glyphs[model["name"]] = model
    return _font_model_with_glyphs(font, glyphs, instance_ids=instance_ids)


def _native_persistent_font_model(
    font: Any,
    *,
    instance_ids: Optional[Sequence[str]] = None,
    document_path: Any = None,
) -> dict[str, Any] | None:
    """Capture a live font through Glyphs' official format-v4 mapping.

    Glyphs implements the file-format serialization in native code.  Reading
    that in-memory property-list tree once is both more authoritative and far
    cheaper than asking PyObjC for every node, hint, guide, image, and custom
    parameter separately.  ``SerializedMappingSource`` remains the sole
    mapping-to-canonical implementation, so live, flat, and package sources do
    not acquire separate schema rules.

    Editor-derived verdicts are intentionally left at their source-neutral
    defaults here. They are excluded from semantic document identity and are
    refreshed only for impacted glyphs or explicit analytical workflows; a
    bulk capture must not issue thousands of PyObjC diagnostic getters.
    """

    started = time.perf_counter()
    if document_path in (None, ""):
        document_path = _safe_getattr(font, "filepath")

    def stage(name: str) -> None:
        if os.environ.get("GLYPHS_MCP_DEBUG_CAPTURE"):
            print(
                "[Glyphs MCP][CanonicalCapture] persistent stage={} elapsedMs={:.1f}".format(
                    name, (time.perf_counter() - started) * 1000.0
                )
            )

    def unavailable(reason: str, error: Any = None) -> None:
        if os.environ.get("GLYPHS_MCP_DEBUG_CAPTURE"):
            suffix = "" if error is None else " error={!r}".format(error)
            print(
                "[Glyphs MCP][CanonicalCapture] persistent mapping unavailable: {}{}".format(
                    reason, suffix
                )
            )

    persistent = _persistent_property_list(font)
    stage("property_tree")
    if persistent is None:
        unavailable("native serializer returned no mapping")
        return None
    persistent_is_plain = bool(
        type(persistent) is dict
        and _is_strict_plain_property_list_value(persistent)
    )
    plain_persistent = persistent if persistent_is_plain else None
    already_canonical = bool(
        persistent_is_plain
        and isinstance(plain_persistent, Mapping)
        and "font" in plain_persistent
        and isinstance(plain_persistent.get("glyphs"), Mapping)
    )
    if already_canonical:
        try:
            model = dict(
                SerializedMappingSource(
                    plain_persistent,
                    document_path=document_path,
                ).capture()
            )
            stage("direct_canonical")
        except Exception as exc:
            unavailable("canonical mapping conversion failed", exc)
            return None
    else:
        flattened = _native_serialized_property_tree(persistent)
        stage("native_flattened")
        if flattened is None:
            unavailable("native format-v4 document encoding failed")
            return None
        try:
            model = dict(
                SerializedMappingSource(
                    flattened,
                    copy_source=False,
                    document_path=document_path,
                ).capture()
            )
            stage("flattened_canonical")
        except Exception as exc:
            if os.environ.get("GLYPHS_MCP_DEBUG_CAPTURE"):
                print(
                    "[Glyphs MCP][CanonicalCapture] flattened node shape: {}".format(
                        _debug_first_serialized_node(flattened)
                    )
                )
            unavailable("flattened mapping conversion failed", exc)
            return None
    model_is_plain = bool(
        type(model) is dict and _is_strict_plain_property_list_value(model)
    )
    if not model_is_plain:
        unavailable("canonical mapping retained a native object after flattening")
        return None
    glyph_models = model.get("glyphs")
    if not isinstance(glyph_models, Mapping):
        unavailable("canonical glyph root is not a mapping")
        return None

    native_glyph_values = _sequence_values(_safe_getattr(font, "glyphs"))
    native_glyph_pairs = [
        (str(_safe_getattr(glyph, "name") or ""), glyph)
        for glyph in native_glyph_values
        if str(_safe_getattr(glyph, "name") or "")
    ]
    native_glyphs = dict(native_glyph_pairs)
    stage("native_glyph_index")
    if set(native_glyphs) != set(glyph_models):
        unavailable(
            "glyph identity mismatch native={} persistent={}".format(
                len(native_glyphs), len(glyph_models)
            )
        )
        return None
    # The GSFont glyph proxy is an editor view, not the saved collection-order
    # owner: changing a scalar such as ``export`` can immediately regroup it.
    # Preserve the order emitted by the official format-v4 serializer so live,
    # flat, and package sources share one document-content identity.
    if not all(isinstance(glyph_model, dict) for glyph_model in glyph_models.values()):
        unavailable("glyph model is immutable or not a dictionary")
        return None
    stage("source_neutral_verdicts")

    identities = tuple(str(value) for value in (instance_ids or ()))
    instances = model.get("instances")
    if identities and isinstance(instances, list):
        if len(identities) != len(instances):
            unavailable("instance identity count mismatch")
            return None
        for index, instance in enumerate(instances):
            if not isinstance(instance, dict):
                unavailable("instance model is immutable or not a dictionary")
                return None
            instance["id"] = identities[index]
    stage("complete")
    return model


class _AuthoritativeGlyphShardResolver:
    """Resolve full glyph shards from the active canonical source.

    Interactive history is captured through the registry-driven live adapter.
    The bulk format-v4 projection is a separate, opt-in equivalence authority
    used by release audits. Keeping that choice request-local prevents a font
    from changing canonical spelling merely because it crossed Glyphs' clean /
    dirty editor boundary.
    """

    def __init__(
        self,
        font: Any,
        *,
        axis_tags: Optional[Mapping[str, str]] = None,
        instance_ids: Optional[Sequence[str]] = None,
        prefer_serialized_source: bool = False,
        document_path: Any = None,
    ) -> None:
        self._font = font
        self._axis_tags = axis_tags
        self._instance_ids = instance_ids
        self._document_path = document_path
        self._use_serialized_source = bool(
            prefer_serialized_source
            or _serialized_source_verification_enabled()
        )
        self._loaded = False
        self._persistent_model: Mapping[str, Any] | None = None

    def _load(self) -> Mapping[str, Any] | None:
        if not self._use_serialized_source:
            return None
        if not self._loaded:
            self._persistent_model = _native_persistent_font_model(
                self._font,
                instance_ids=self._instance_ids,
                document_path=self._document_path,
            )
            self._loaded = True
        return self._persistent_model

    def document_model(self) -> Mapping[str, Any] | None:
        """Return the one lazily captured authoritative document mapping."""

        return self._load()

    def capture(
        self,
        glyph: Any,
        *,
        layer_order_reference: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        complete = self._load()
        complete_glyphs = (
            complete.get("glyphs", {}) if isinstance(complete, Mapping) else {}
        )
        name = str(_safe_getattr(glyph, "name") or "")
        authoritative = (
            complete_glyphs.get(name)
            if isinstance(complete_glyphs, Mapping)
            else None
        )
        if isinstance(authoritative, Mapping):
            result = copy.deepcopy(dict(authoritative))
            result["layers"] = list(
                _canonical_layer_projection(
                    result.get("layers", ()), layer_order_reference
                )
            )
            return result
        return _glyph_model(
            glyph,
            axis_tags=self._axis_tags,
            document_path=self._document_path,
            layer_order_reference=layer_order_reference,
        )


def _serialized_source_verification_enabled() -> bool:
    """Return whether the exhaustive live/serialized equivalence gate is on.

    The native Glyphs format flattener is an independent audit source, not the
    interactive capture engine. On production-sized fonts it materializes the
    complete serialized tree and defeats immutable shard reuse. Ordinary MCP
    operations therefore use the registry-driven live adapter; release gates
    can opt into this slower cross-source proof explicitly.
    """

    return os.environ.get("GLYPHS_MCP_VERIFY_SERIALIZED_SOURCE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


_SERIALIZED_CANONICAL_SOURCES = frozenset(
    {"saved_format_v4_mapping", "glyphs_format_v4_mapping"}
)


def _uses_serialized_canonical_source(model: Mapping[str, Any]) -> bool:
    """Return whether a snapshot's spelling came from the format-v4 seam."""

    if not isinstance(model, CanonicalSnapshot):
        return False
    return str(model.native_revision_evidence.get("capture") or "") in (
        _SERIALIZED_CANONICAL_SOURCES
    )


def _canonical_document_path(model: Mapping[str, Any]) -> Any:
    if isinstance(model, CanonicalSnapshot):
        return model.native_revision_evidence.get("documentPath")
    return None


def _retain_canonical_model(model: Mapping[str, Any]) -> Mapping[str, Any]:
    """Retain immutable snapshots and detach ordinary adapter mappings."""

    return model if isinstance(model, CanonicalSnapshot) else copy.deepcopy(dict(model))


def _paths_require_source_neutral_glyph(
    paths: Sequence[Sequence[str]],
) -> bool:
    """Return whether paths replace membership or a complete nested entity.

    Scalar fragments have explicit normalizers and can be spliced into any
    canonical source. Collection order, membership, and complete layer/glyph
    entities must be recaptured through the baseline's source seam; otherwise
    ObjectWrapper defaults can masquerade as unrelated semantic changes.
    """

    return any(
        len(path) <= 2
        or (len(path) >= 3 and str(path[2]) == "layers")
        for path in paths
    )


def _project_persistent_layer_order(
    model: Mapping[str, Any],
    reference_model: Mapping[str, Any] | None,
) -> None:
    """Apply the one canonical layer-order projection to a captured mapping."""

    glyphs = model.get("glyphs", {})
    references = (
        reference_model.get("glyphs", {})
        if isinstance(reference_model, Mapping)
        else {}
    )
    if not isinstance(glyphs, Mapping) or not isinstance(references, Mapping):
        return
    for name, glyph in glyphs.items():
        if not isinstance(glyph, dict):
            continue
        reference = references.get(name)
        glyph["layers"] = list(
            _canonical_layer_projection(
                glyph.get("layers", ()),
                reference if isinstance(reference, Mapping) else None,
            )
        )


_PERSISTENT_VERIFICATION_GLYPH_THRESHOLD = 32


def _impact_prefers_persistent_verification(impact: CanonicalImpact) -> bool:
    """Select one complete native mapping when fragment proof is costlier.

    Large glyph batches and master/glyph collection operations can advance
    broad Glyphs revision evidence. Walking hundreds of PyObjC objects then
    costs more and proves less than one official format-v4 mapping. The result
    still enters the same canonical source and projection seams; this selects
    a capture strategy, not another model or mutation engine.
    """

    return bool(
        len(impact.glyph_names) > _PERSISTENT_VERIFICATION_GLYPH_THRESHOLD
        or "glyphOrder" in impact.roots
        or ("glyphs" in impact.roots and not impact.glyph_names)
    )


def _glyph_layer_structure(glyph: Any) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            str(_safe_getattr(layer, "layerId") or _safe_getattr(layer, "id") or ""),
            str(_safe_getattr(layer, "associatedMasterId") or ""),
        )
        for layer in _native_layers(glyph)
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


def _document_revision_token(
    font: Any,
    *,
    notification_generation: int | None = None,
) -> tuple[Any, ...] | None:
    """Return host-owned evidence that covers every document mutation.

    Glyphs' ``GSDocument`` inherits the NSDocument change counter and advances
    it for native user and plug-in edits. It is the only bounded evidence broad
    enough to reuse all canonical roots. Hosts that do not expose the counter
    use the documented update-notification generation when available.

    The token deliberately excludes Python object identity. PyObjC may vend a
    fresh proxy for the same native document on consecutive attribute reads;
    the surrounding cache is already scoped by the stable process-local
    ``documentId``. MCP writes also set explicit pending impact below, so this
    token can never bypass a transaction's required read-back.
    """

    document = _maybe_call(_safe_getattr(font, "parent"))
    if document is None:
        return None
    value = _maybe_call(_safe_getattr(document, "changeCount"))
    try:
        count = int(value)
    except (TypeError, ValueError):
        if notification_generation is None:
            return None
        return (
            "glyphs_update_interface",
            int(notification_generation),
            _native_unsaved_changes(document),
        )
    return ("native_change_count", count, _native_unsaved_changes(document))


class _GlyphsChangeGeneration:
    """Passive process-local revision evidence from documented Glyphs events.

    Glyphs 4 does not expose ``NSDocument.changeCount`` through PyObjC.  Its
    documented ``UPDATEINTERFACE`` callback is the host boundary used by
    plug-ins after document edits.  This listener performs no canonical work;
    it only increments a generation.  Explicit MCP mutations still invalidate
    semantic impact directly, and arbitrary live Python forces a fresh capture
    because it may omit the host notification.
    """

    def __init__(self, glyphs: Any, events: Sequence[Any]) -> None:
        self._glyphs = glyphs
        self._events = tuple(events)
        self._generation = 0
        self._lock = RLock()
        self._installed = False

    @classmethod
    def install(cls, app: Any) -> "_GlyphsChangeGeneration | None":
        try:
            from GlyphsApp import (  # type: ignore[import-not-found]
                DOCUMENTCLOSED,
                DOCUMENTOPENED,
                DOCUMENTWASSAVED,
                Glyphs,
                UPDATEINTERFACE,
            )
        except Exception:
            return None
        if app is not Glyphs:
            return None
        listener = cls(
            Glyphs,
            (UPDATEINTERFACE, DOCUMENTOPENED, DOCUMENTCLOSED, DOCUMENTWASSAVED),
        )
        registered = []
        for event in listener._events:
            try:
                Glyphs.addCallback(listener.changed_, event)
                registered.append(event)
            except Exception:
                pass
        listener._events = tuple(registered)
        listener._installed = bool(UPDATEINTERFACE in registered)
        return listener if listener._installed else None

    def changed_(self, _notification: Any = None) -> None:
        with self._lock:
            self._generation += 1

    def current(self) -> int:
        with self._lock:
            return self._generation

    def close(self) -> None:
        for event in self._events:
            try:
                self._glyphs.removeCallback(self.changed_, event)
            except Exception:
                try:
                    self._glyphs.removeCallback(self.changed_)
                except Exception:
                    pass
        self._events = ()
        self._installed = False


@dataclass(frozen=True)
class _PersistentCaptureDraft:
    """Detached bulk capture ready for worker-thread snapshot assembly."""

    document_id: str
    roots: Mapping[str, Any]
    glyphs: Mapping[str, Any]
    current_glyphs: Mapping[str, Mapping[str, Any]]
    previous_snapshot: CanonicalSnapshot | None
    expected: CanonicalSnapshot | None
    revision_at_start: tuple[Any, ...] | None
    revision_at_end: tuple[Any, ...] | None
    pending_roots: frozenset[str]
    pending_root_paths: Mapping[str, tuple[tuple[str, ...], ...]]
    pending_paths: Mapping[str, tuple[tuple[str, ...], ...]]
    capture_source: str
    root_evidence: Mapping[str, Any]
    document_path: Any


class _RevisionBoundGlyphModelCache:
    """Reuse detached glyph trees only while native revision evidence agrees.

    Paths and components dominate live canonical capture cost. Glyphs updates a
    glyph's ``lastChange`` when its own layers or derived metrics change; each
    glyph's own layer membership is included independently. Master order lives
    in the master root and cannot invalidate unrelated glyph shards.
    Agent-owned writes invalidate the document explicitly before verification.
    """

    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def invalidate(self, document_id: str) -> None:
        with self._lock:
            self._documents.pop(document_id, None)

    def invalidate_unscoped(self) -> None:
        """Require complete live proof without discarding canonical authority.

        Arbitrary open-world Python has no semantic impact boundary. Preserve
        each immutable snapshot as the source-neutral reference, mark every
        canonical root pending, and force Glyphs' complete format-v4 mapping
        on the next capture. Clearing the cache here is incorrect: after an
        exact MCP revert, Cocoa's native dirty bit can remain sticky, which
        disqualifies the saved-file fast path and would make a cold capture
        fall back to lossy editor getters.
        """

        with self._lock:
            for document in self._documents.values():
                snapshot = document.get("snapshot")
                if not isinstance(snapshot, CanonicalSnapshot):
                    continue
                pending_roots = document.setdefault("pendingRoots", set())
                pending_roots.update(str(root) for root in snapshot.root_shards)
                pending_roots.add("glyphs")
                document["forcePersistentVerification"] = True

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

    def invalidate_impact(
        self,
        document_id: str,
        impact: CanonicalImpact,
        *,
        font: Any | None = None,
    ) -> None:
        """Mark exact fragments stale and lazily seed native proof evidence.

        Cold capture remains a bulk canonical-source operation. Only the
        glyphs owned by a pending live mutation pay for detailed root/layer
        evidence, immediately before the native write occurs.
        """

        with self._lock:
            document = self._documents.get(document_id)
            if document is None:
                return
            roots = document.setdefault("pendingRoots", set())
            roots.update(str(root) for root in impact.roots)
            root_paths = document.setdefault("pendingRootPaths", {})
            for path in impact.paths:
                if not path or path[0] == "glyphs":
                    continue
                root = str(path[0])
                existing_root_paths = list(root_paths.get(root, ()))
                if path not in existing_root_paths:
                    existing_root_paths.append(path)
                root_paths[root] = tuple(existing_root_paths)
            pending = document.setdefault("pendingGlyphPaths", {})
            for name, paths in impact.glyph_paths.items():
                existing = list(pending.get(name, ()))
                for path in paths:
                    if path not in existing:
                        existing.append(path)
                pending[name] = tuple(existing)
            # Small impacts use lazy per-glyph native proof. Large batches and
            # root-only operations are cheaper and stronger through one
            # complete native format-v4 mapping than thousands of PyObjC
            # diagnostic getters.
            bulk_verification = _impact_prefers_persistent_verification(impact)
            if bulk_verification:
                document["forcePersistentVerification"] = True
            if font is not None and impact.glyph_names and not bulk_verification:
                native_glyphs = {
                    str(_safe_getattr(glyph, "name") or ""): glyph
                    for glyph in _sequence_values(_safe_getattr(font, "glyphs"))
                    if str(_safe_getattr(glyph, "name") or "")
                }
                glyphs = document.get("glyphs", {})
                for name in impact.glyph_names:
                    cached = glyphs.get(str(name))
                    native = native_glyphs.get(str(name))
                    if cached is None or native is None:
                        continue
                    cached["rootEvidence"] = _glyph_root_revision_evidence(native)
                    cached["layerTokens"] = _layer_revision_index(native)

    def finalize_persistent_capture(
        self, draft: _PersistentCaptureDraft
    ) -> CanonicalSnapshot:
        """Encode/hash a detached bulk capture away from Glyphs' main thread."""

        exact_fingerprint = None
        expected = draft.expected
        if expected is not None and all(
            draft.roots.get(name) == expected.root_shards.get(name)
            for name in set(draft.roots) | set(expected.root_shards)
        ) and draft.glyphs == expected.glyph_shards:
            exact_fingerprint = expected.document_fingerprint
        with _suspend_cyclic_gc_for_bulk_capture():
            snapshot = CanonicalSnapshot.from_shards(
                draft.roots,
                draft.glyphs,
                previous=draft.previous_snapshot,
                document_fingerprint=exact_fingerprint,
                native_revision_evidence={
                    "capture": draft.capture_source,
                    "documentPath": draft.document_path,
                    "document": draft.revision_at_start,
                    "glyphs": {
                        name: value["token"]
                        for name, value in draft.current_glyphs.items()
                    },
                    "layers": {
                        name: value["layerTokens"]
                        for name, value in draft.current_glyphs.items()
                        if value.get("layerTokens") is not None
                    },
                },
            )
        revision_is_stable = bool(
            draft.revision_at_start is not None
            and draft.revision_at_start == draft.revision_at_end
        )
        expected_mismatch = bool(
            expected is not None
            and snapshot.document_fingerprint != expected.document_fingerprint
        )
        with self._lock:
            self._documents[draft.document_id] = {
                "glyphs": dict(draft.current_glyphs),
                "snapshot": snapshot,
                "revisionToken": (
                    draft.revision_at_end if revision_is_stable else None
                ),
                "pendingRoots": (
                    set(draft.pending_roots) if expected_mismatch else set()
                ),
                "pendingRootPaths": (
                    dict(draft.pending_root_paths) if expected_mismatch else {}
                ),
                "pendingGlyphPaths": (
                    dict(draft.pending_paths) if expected_mismatch else {}
                ),
                # A stable read-back is an agreement between two observations
                # from one canonical source. Keep a bulk format-v4 proof source
                # selected for every expected-state read; an exact first result
                # is not yet an agreement and must not make the second read
                # fall through to the registry-live adapter. The next ordinary
                # capture (without ``expected``) releases this proof-source
                # preference after storing its result.
                "forcePersistentVerification": bool(
                    expected is not None
                    and draft.capture_source == "glyphs_format_v4_mapping"
                ),
                "rootEvidence": dict(draft.root_evidence),
            }
        return snapshot

    def capture_snapshot(
        self,
        document_id: str,
        font: Any,
        *,
        instance_ids: Optional[Sequence[str]] = None,
        expected: CanonicalSnapshot | None = None,
        revision_provider: Callable[[], tuple[Any, ...] | None] | None = None,
        defer_persistent_assembly: bool = False,
    ) -> CanonicalSnapshot | _PersistentCaptureDraft:
        capture_started = time.perf_counter()
        debug_capture = bool(os.environ.get("GLYPHS_MCP_DEBUG_CAPTURE"))

        def debug(stage: str, **values: Any) -> None:
            if not debug_capture:
                return
            fields = " ".join(
                "{}={}".format(name, value)
                for name, value in sorted(values.items())
            )
            print(
                "[Glyphs MCP][CanonicalCapture] document={} stage={} elapsedMs={:.1f} {}".format(
                    document_id,
                    stage,
                    (time.perf_counter() - capture_started) * 1000.0,
                    fields,
                ),
                flush=True,
            )

        revision_at_start = (
            revision_provider()
            if revision_provider is not None
            else _document_revision_token(font)
        )
        with self._lock:
            previous = self._documents.get(document_id)
            previous_snapshot = (
                previous.get("snapshot") if previous is not None else None
            )
            previous_glyphs = (
                previous.get("glyphs", {})
                if previous is not None
                else {}
            )
            pending_paths = dict(
                previous.get("pendingGlyphPaths", {})
                if previous is not None
                else {}
            )
            pending_roots = set(
                previous.get("pendingRoots", set())
                if previous is not None
                else set()
            )
            pending_root_paths = dict(
                previous.get("pendingRootPaths", {})
                if previous is not None
                else {}
            )
            previous_root_evidence = dict(
                previous.get("rootEvidence", {})
                if previous is not None
                else {}
            )
            force_persistent_verification = bool(
                previous.get("forcePersistentVerification", False)
                if previous is not None
                else False
            )
            streaming_capture = bool(
                previous_snapshot is not None
                and (pending_paths or pending_roots)
            )
            if (
                previous_snapshot is not None
                and revision_at_start is not None
                and revision_at_start == previous.get("revisionToken")
                and not pending_paths
                and not pending_roots
                and (
                    expected is None
                    or expected.document_fingerprint
                    == previous_snapshot.document_fingerprint
                )
            ):
                debug("snapshot_reused", revision=revision_at_start)
                return previous_snapshot

            passive_root_evidence: Mapping[str, Any] | None = None
            if (
                previous_snapshot is not None
                and not pending_paths
                and not pending_roots
                and not force_persistent_verification
            ):
                # A host notification is only revision evidence. Compare the
                # small native root surface against its previous native
                # spelling before touching canonical shards. This prevents a
                # notification emitted after a verified glyph edit from
                # rebuilding every saved-source root through ObjectWrapper.
                passive_root_evidence = _native_root_evidence(
                    font,
                    instance_ids=instance_ids,
                )
                pending_roots.update(
                    root
                    for root in _ROOT_EVIDENCE_NAMES
                    if passive_root_evidence.get(root)
                    != previous_root_evidence.get(root)
                )
                streaming_capture = True

            persistent_model = None
            capture_source = "registry_live_adapter"
            # Stable revision evidence reuses immutable shards above. Exact
            # MCP invalidations stay on the streaming branch below. An
            # unscoped revision refresh, however, must preserve the source
            # family that established the snapshot: mixing a format-v4
            # bootstrap with ObjectWrapper roots creates false changes in
            # default values and anonymous identities. Release audits also
            # force the complete format-v4 source on every capture.
            serialized_audit = _serialized_source_verification_enabled()
            source_neutral_revision_refresh = bool(
                previous_snapshot is not None
                and passive_root_evidence is not None
                and _uses_serialized_canonical_source(previous_snapshot)
            )
            if not serialized_audit and previous_snapshot is None:
                # A clean saved v4 document is already a detached immutable
                # source. Decode that source once, verify its glyph identities
                # against the open document, and then let all subsequent MCP
                # writes stream only their predicted live impact. This avoids
                # a multi-minute PyObjC traversal merely to rediscover bytes
                # Glyphs has already persisted. Dirty or pathless documents
                # fail this qualification and use the registry live adapter.
                persistent_model = _saved_document_canonical_model(
                    font,
                    instance_ids=instance_ids,
                )
                if persistent_model is not None:
                    capture_source = "saved_format_v4_mapping"
            if force_persistent_verification or source_neutral_revision_refresh or (
                serialized_audit
                and (
                    previous_snapshot is None
                    or (not pending_paths and not pending_roots)
                )
            ):
                with _suspend_cyclic_gc_for_bulk_capture():
                    persistent_model = _native_persistent_font_model(
                        font,
                        instance_ids=instance_ids,
                    )
                if persistent_model is not None:
                    capture_source = "glyphs_format_v4_mapping"
            if persistent_model is not None:
                persistent_glyphs = persistent_model.get("glyphs", {})
                reference_glyphs = (
                    expected.glyph_shards
                    if expected is not None
                    else previous_snapshot.glyph_shards
                    if previous_snapshot is not None
                    else {}
                )
                _project_persistent_layer_order(
                    persistent_model,
                    {"glyphs": reference_glyphs},
                )
                current_glyphs: dict[str, dict[str, Any]] = {}
                for native_glyph in _sequence_values(_safe_getattr(font, "glyphs")):
                    name = str(_safe_getattr(native_glyph, "name") or "")
                    glyph_model = persistent_glyphs.get(name)
                    if not name or not isinstance(glyph_model, dict):
                        continue
                    current_glyphs[name] = {
                        "token": _glyph_revision_token(native_glyph),
                        "model": glyph_model,
                        # Native root/layer proof is seeded lazily only for a
                        # glyph owned by a pending live mutation.
                        "rootEvidence": None,
                        "layerTokens": None,
                    }
                if set(current_glyphs) != set(persistent_glyphs):
                    raise HostAccessError(
                        "Glyphs persistent capture did not preserve every glyph identity"
                    )
                roots = {
                    name: value
                    for name, value in persistent_model.items()
                    if name != "glyphs"
                }
                if capture_source == "saved_format_v4_mapping":
                    root_evidence = _native_root_evidence(
                        font,
                        instance_ids=instance_ids,
                    )
                elif previous_snapshot is not None:
                    # A complete serialized read-back already proves every
                    # canonical shard. Preserve earlier source-local evidence
                    # and refresh only roots named by the actual transaction;
                    # a glyph-only bulk operation must never traverse every
                    # ObjectWrapper root merely to seed a later optimization.
                    root_evidence = dict(previous_root_evidence)
                    for root in pending_root_paths:
                        if root in {"glyphs", "glyphOrder"}:
                            continue
                        root_evidence[root] = _native_root_evidence_value(
                            font,
                            root,
                            instance_ids=instance_ids,
                        )
                else:
                    root_evidence = {}
                revision_at_end = (
                    revision_provider()
                    if revision_provider is not None
                    else _document_revision_token(font)
                )
                draft = _PersistentCaptureDraft(
                    document_id=document_id,
                    roots=roots,
                    glyphs=persistent_glyphs,
                    current_glyphs=current_glyphs,
                    previous_snapshot=previous_snapshot,
                    expected=expected,
                    revision_at_start=revision_at_start,
                    revision_at_end=revision_at_end,
                    pending_roots=frozenset(str(root) for root in pending_roots),
                    pending_root_paths={
                        str(name): tuple(tuple(path) for path in paths)
                        for name, paths in pending_root_paths.items()
                    },
                    pending_paths={
                        str(name): tuple(tuple(path) for path in paths)
                        for name, paths in pending_paths.items()
                    },
                    capture_source=capture_source,
                    root_evidence=root_evidence,
                    document_path=_safe_getattr(font, "filepath"),
                )
                if defer_persistent_assembly:
                    debug("persistent_draft_captured", glyphCount=len(current_glyphs))
                    return draft
                snapshot = self.finalize_persistent_capture(draft)
                debug(
                    "persistent_snapshot_stored",
                    fingerprint=snapshot.document_fingerprint,
                    glyphCount=len(current_glyphs),
                    revisionStart=revision_at_start,
                    revisionEnd=revision_at_end,
                )
                return snapshot

            masters = _master_models(font)
            debug("masters_captured", count=len(masters), revision=revision_at_start)
            axis_tags = _axis_tag_by_native_id(font)
            authoritative_glyphs = _AuthoritativeGlyphShardResolver(
                font,
                axis_tags=axis_tags,
                instance_ids=instance_ids,
                prefer_serialized_source=(
                    previous_snapshot is not None
                    and _uses_serialized_canonical_source(previous_snapshot)
                ),
                document_path=(
                    _canonical_document_path(previous_snapshot)
                    if previous_snapshot is not None
                    else _safe_getattr(font, "filepath")
                ),
            )
            current_glyphs: dict[str, dict[str, Any]] = {}
            result_glyphs: dict[str, Any] = {}
            for glyph in _sequence_values(_safe_getattr(font, "glyphs")):
                token = _glyph_revision_token(glyph)
                name = str(token[0])
                if not name:
                    continue
                cached = previous_glyphs.get(name)
                root_evidence = (
                    cached.get("rootEvidence") if cached is not None else None
                )
                if (
                    cached is not None
                    and cached.get("token") == token
                    and not pending_paths.get(name)
                ):
                    model = cached["model"]
                    layer_tokens = cached.get("layerTokens", {})
                elif (
                    cached is not None
                    and pending_paths.get(name)
                    and expected is not None
                ):
                    layer_tokens = _layer_revision_index(glyph)
                    root_evidence = _glyph_root_revision_evidence(glyph)
                    expected_glyph = expected.glyph_shards.get(name)
                    source_neutral_entity = bool(
                        _uses_serialized_canonical_source(previous_snapshot)
                        and _paths_require_source_neutral_glyph(
                            pending_paths[name]
                        )
                    )
                    if source_neutral_entity:
                        model = authoritative_glyphs.capture(
                            glyph,
                            layer_order_reference=(
                                expected_glyph
                                if isinstance(expected_glyph, Mapping)
                                else cached["model"]
                            ),
                        )
                    else:
                        model = _glyph_fragment_model(
                            glyph,
                            cached["model"],
                            pending_paths[name],
                            axis_tags=axis_tags,
                            document_path=_canonical_document_path(
                                previous_snapshot
                            ),
                            layer_order_reference=(
                                expected_glyph
                                if isinstance(expected_glyph, Mapping)
                                else cached["model"]
                            ),
                        )
                    if (
                        isinstance(expected_glyph, Mapping)
                        and not source_neutral_entity
                        and not _verified_glyph_fragment_matches(
                            glyph,
                            model,
                            expected_glyph,
                            pending_paths[name],
                            before_root_evidence=cached.get("rootEvidence"),
                            current_root_evidence=root_evidence,
                            before_layer_tokens=cached.get("layerTokens", {}),
                            current_layer_tokens=layer_tokens,
                        )
                    ):
                        if debug_capture:
                            fragment_diff = diff_models(
                                {"glyph": model},
                                {"glyph": expected_glyph},
                            )
                            debug(
                                "glyph_fragment_mismatch",
                                glyph=name,
                                predictedPaths=[
                                    list(path) for path in pending_paths[name][:12]
                                ],
                                fragmentDiffPaths=[
                                    list(change.path)
                                    for change in fragment_diff.changes[:12]
                                ],
                                fragmentDiffCount=len(fragment_diff.changes),
                            )
                        # A native side effect escaped the predicted paths.
                        # Materialize the complete mismatch so verification
                        # reports the real observed tree rather than accepting
                        # a stale sibling shard.
                        model = authoritative_glyphs.capture(
                            glyph,
                            layer_order_reference=expected_glyph,
                        )
                        if debug_capture:
                            complete_diff = diff_models(
                                {"glyph": model},
                                {"glyph": expected_glyph},
                            )
                            debug(
                                "glyph_complete_mismatch",
                                glyph=name,
                                diffPaths=[
                                    list(change.path)
                                    for change in complete_diff.changes[:12]
                                ],
                                diffCount=len(complete_diff.changes),
                            )
                elif cached is not None:
                    # Glyphs can advance a broad glyph revision marker for a
                    # master/root operation without changing a glyph field.
                    # Prove the unchanged canonical shard from bounded native
                    # layer evidence before falling back to a full rebuild.
                    layer_tokens = _layer_revision_index(glyph)
                    root_evidence = _glyph_root_revision_evidence(glyph)
                    model = cached["model"]
                    expected_glyph = (
                        expected.glyph_shards.get(name)
                        if expected is not None
                        else cached["model"]
                    )
                    if not (
                        isinstance(expected_glyph, Mapping)
                        and _verified_glyph_fragment_matches(
                            glyph,
                            cached["model"],
                            expected_glyph,
                            (),
                            before_root_evidence=cached.get("rootEvidence"),
                            current_root_evidence=root_evidence,
                            before_layer_tokens=cached.get("layerTokens", {}),
                            current_layer_tokens=layer_tokens,
                        )
                    ):
                        model = authoritative_glyphs.capture(
                            glyph,
                            layer_order_reference=(
                                expected_glyph
                                if isinstance(expected_glyph, Mapping)
                                else cached["model"]
                            ),
                        )
                else:
                    expected_glyph = (
                        expected.glyph_shards.get(name)
                        if expected is not None
                        else None
                    )
                    model = authoritative_glyphs.capture(
                        glyph,
                        layer_order_reference=(
                            expected_glyph
                            if isinstance(expected_glyph, Mapping)
                            else None
                        ),
                    )
                    layer_tokens = _layer_revision_index(glyph)
                    root_evidence = _glyph_root_revision_evidence(glyph)
                result_glyphs[name] = model
                current_glyphs[name] = {
                    "token": token,
                    "model": model,
                    "rootEvidence": root_evidence,
                    "layerTokens": layer_tokens,
                }
            debug("glyphs_captured", count=len(current_glyphs))
            if streaming_capture:
                # Warm verification owns a path-derived impact. Reuse every
                # unrelated immutable root shard and materialize only roots
                # explicitly invalidated by that impact. Glyph collection
                # order is always checked because it is cheap, authoritative,
                # and can expose an unexpected parent-collection side effect.
                roots = dict(previous_snapshot.root_shards)
                root_evidence = dict(previous_root_evidence)
                for root in sorted(set(pending_roots) - {"glyphs", "glyphOrder"}):
                    current_evidence = (
                        passive_root_evidence.get(root)
                        if passive_root_evidence is not None
                        else _native_root_evidence_value(
                            font,
                            root,
                            instance_ids=instance_ids,
                        )
                    )
                    candidate = current_evidence
                    root_change_paths = tuple(
                        tuple(path[1:])
                        for path in pending_root_paths.get(root, ())
                        if path and path[0] == root
                    )
                    if (
                        expected is not None
                        and root in previous_root_evidence
                        and root_change_paths
                    ):
                        verified, unexpected = _verified_root_evidence_transition(
                            root,
                            previous_root_evidence[root],
                            current_evidence,
                            expected.root_shards.get(root),
                            root_change_paths,
                        )
                        if (
                            not verified
                            and _uses_serialized_canonical_source(previous_snapshot)
                        ):
                            fallback_started = time.perf_counter()
                            persistent_root = _persistent_canonical_record_root(
                                font,
                                root,
                                expected,
                            )
                            verified = (
                                persistent_root
                                == expected.root_shards.get(root)
                            )
                            if debug_capture:
                                debug(
                                    "root_record_fallback",
                                    root=root,
                                    verified=verified,
                                    elapsedMs=round(
                                        (time.perf_counter() - fallback_started)
                                        * 1000.0,
                                        1,
                                    ),
                                )
                        if not verified:
                            raise HostAccessError(
                                "Native {} changes escaped the predicted canonical "
                                "impact (first paths: {})".format(
                                    root,
                                    [list(path) for path in unexpected[:12]],
                                )
                            )
                        candidate = expected.root_shards.get(root)
                    roots[root] = candidate
                    root_evidence[root] = current_evidence
                membership_changed = bool(
                    set(result_glyphs) != set(previous_snapshot.glyph_shards)
                )
                if "glyphOrder" in pending_roots or membership_changed:
                    persistent = authoritative_glyphs.document_model()
                    persistent_order = (
                        persistent.get("glyphOrder")
                        if isinstance(persistent, Mapping)
                        else [
                            str(_safe_getattr(glyph, "name") or "")
                            for glyph in _sequence_values(_safe_getattr(font, "glyphs"))
                            if str(_safe_getattr(glyph, "name") or "")
                        ]
                    )
                    if not isinstance(persistent_order, list):
                        raise HostAccessError(
                            "Glyphs did not provide authoritative glyph order"
                        )
                    roots["glyphOrder"] = list(persistent_order)
                debug(
                    "roots_streamed",
                    materialized=len(set(pending_roots) - {"glyphs"}),
                )
            else:
                model = _font_model_with_glyphs(
                    font,
                    result_glyphs,
                    masters=masters,
                    instance_ids=instance_ids,
                )
                debug("roots_captured", count=len(model) - 1)
                roots = {
                    name: value for name, value in model.items() if name != "glyphs"
                }
                root_evidence = {
                    name: value
                    for name, value in roots.items()
                    if name in _ROOT_EVIDENCE_NAMES
                }
            exact_fingerprint = None
            if expected is not None and all(
                roots.get(name) == expected.root_shards.get(name)
                for name in set(roots) | set(expected.root_shards)
            ) and result_glyphs == expected.glyph_shards:
                exact_fingerprint = expected.document_fingerprint
            snapshot = CanonicalSnapshot.from_shards(
                roots,
                result_glyphs,
                previous=previous_snapshot,
                document_fingerprint=exact_fingerprint,
                native_revision_evidence={
                    "capture": (
                        previous_snapshot.native_revision_evidence.get("capture")
                        if previous_snapshot is not None
                        else "registry_live_adapter"
                    ),
                    "documentPath": (
                        _canonical_document_path(previous_snapshot)
                        if previous_snapshot is not None
                        else _safe_getattr(font, "filepath")
                    ),
                    "glyphs": {
                        name: value["token"] for name, value in current_glyphs.items()
                    },
                    "layers": {
                        name: value["layerTokens"]
                        for name, value in current_glyphs.items()
                        if value["layerTokens"] is not None
                    },
                    "masters": tuple(
                        str(master.get("id") or "") for master in masters
                    ),
                    "document": revision_at_start,
                },
            )
            revision_at_end = (
                revision_provider()
                if revision_provider is not None
                else _document_revision_token(font)
            )
            revision_is_stable = bool(
                revision_at_start is not None
                and revision_at_start == revision_at_end
            )
            expected_mismatch = bool(
                expected is not None
                and snapshot.document_fingerprint
                != expected.document_fingerprint
            )
            self._documents[document_id] = {
                "glyphs": current_glyphs,
                "snapshot": snapshot,
                "revisionToken": (
                    revision_at_end if revision_is_stable else None
                ),
                "pendingRoots": (
                    set(pending_roots) if expected_mismatch else set()
                ),
                "pendingRootPaths": (
                    dict(pending_root_paths) if expected_mismatch else {}
                ),
                "pendingGlyphPaths": (
                    dict(pending_paths)
                    if expected_mismatch
                    else {}
                ),
                "forcePersistentVerification": False,
                "rootEvidence": root_evidence,
            }
            debug(
                "snapshot_stored",
                fingerprint=snapshot.document_fingerprint,
                revisionStart=revision_at_start,
                revisionEnd=revision_at_end,
            )
        return snapshot

    def capture(
        self,
        document_id: str,
        font: Any,
        *,
        instance_ids: Optional[Sequence[str]] = None,
    ) -> dict[str, Any]:
        return self.capture_snapshot(
            document_id,
            font,
            instance_ids=instance_ids,
        ).materialize()

    def capture_verified_snapshot(
        self,
        document_id: str,
        font: Any,
        expected: CanonicalSnapshot,
        *,
        instance_ids: Optional[Sequence[str]] = None,
    ) -> CanonicalSnapshot:
        return self.capture_snapshot(
            document_id,
            font,
            instance_ids=instance_ids,
            expected=expected,
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
    for layer in _native_layers(glyph):
        if key in {str(_safe_getattr(layer, "layerId") or ""), str(_safe_getattr(layer, "associatedMasterId") or "")}:
            return layer
    return None


def _edit_layer_for_glyph(
    font: Any, glyph: Any, master_id: Optional[str]
) -> Any:
    if master_id:
        return _lookup_layer(glyph, master_id)
    selected_master = _safe_getattr(font, "selectedFontMaster")
    selected_master_id = str(_safe_getattr(selected_master, "id") or "")
    if selected_master_id:
        layer = _lookup_layer(glyph, selected_master_id)
        if layer is not None:
            return layer
    for layer in _sequence_values(_safe_getattr(font, "selectedLayers")):
        if _safe_getattr(layer, "parent") is glyph:
            return layer
    layers = _native_layers(glyph)
    return layers[0] if layers else None


_ROOT_EVIDENCE_NAMES = (
    "font",
    "axes",
    "masters",
    "instances",
    "kerning",
    "features",
    "classes",
    "featurePrefixes",
    "metrics",
    "stems",
    "numbers",
    "settings",
)
_EVIDENCE_ONLY_ROOTS = frozenset({"axes"})


def _native_canonical_root(
    font: Any,
    root: str,
    *,
    instance_ids: Optional[Sequence[str]] = None,
) -> Any:
    """Capture one registered non-glyph root through its canonical adapter.

    Scoped verification must not rebuild a complete serialized font merely to
    read one changed root.  This dispatcher is the single root-level seam used
    by detached and live streaming verification; it deliberately delegates to
    the same canonical conversion helpers as a complete ObjectWrapper capture.
    """

    if root == "font":
        return {
            **{
                name: _plain_scalar(_safe_getattr(font, name))
                for name in _FONT_SCALARS
            },
            "customParameters": _custom_parameter_models(font),
            "properties": _property_models(font),
            "userData": _user_data_model(font),
        }
    if root == "axes":
        return _axis_models(font)
    if root == "masters":
        return _master_models(font)
    if root == "instances":
        return _instance_models(font, instance_ids=instance_ids)
    if root == "glyphOrder":
        return [
            str(_safe_getattr(glyph, "name") or "")
            for glyph in _sequence_values(_safe_getattr(font, "glyphs"))
            if str(_safe_getattr(glyph, "name") or "")
        ]
    if root == "kerning":
        return _kerning_model(font)
    if root in {"features", "classes", "featurePrefixes"}:
        return _code_collection(font, root)
    if root in {"metrics", "stems", "numbers"}:
        return _metric_models(font, root)
    if root == "settings":
        return _settings_model(font)
    raise HostAccessError("The canonical root is not registered: {}".format(root))


def _native_root_evidence(
    font: Any,
    *,
    instance_ids: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Capture source-local evidence for every small non-glyph root.

    Evidence is compared only with evidence captured through this same live
    adapter; it never enters the document fingerprint. A changed evidence
    shard nominates one canonical root for materialization, while unchanged
    roots retain their source-neutral saved-document representation.
    """

    return {
        root: _native_root_evidence_value(
            font,
            root,
            instance_ids=instance_ids,
        )
        for root in _ROOT_EVIDENCE_NAMES
    }


def _native_root_evidence_value(
    font: Any,
    root: str,
    *,
    instance_ids: Optional[Sequence[str]] = None,
) -> Any:
    """Capture one bounded root in the live adapter's own spelling."""

    return (
        _axis_revision_evidence(font)
        if root == "axes"
        else _native_canonical_root(
            font,
            root,
            instance_ids=instance_ids,
        )
    )


def _root_paths(
    impact: CanonicalImpact | None,
    root: str,
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(path[1:])
        for path in (impact.paths if impact is not None else ())
        if path and str(path[0]) == root
    )


def _evidence_path_is_predicted(
    actual: Sequence[str], predicted: Sequence[Sequence[str]]
) -> bool:
    actual_path = tuple(str(part) for part in actual)
    return any(
        actual_path[: len(path)] == tuple(str(part) for part in path)
        for path in predicted
    )


def _verified_root_evidence_transition(
    root: str,
    before_evidence: Any,
    current_evidence: Any,
    expected_root: Any,
    paths: Sequence[Sequence[str]],
) -> tuple[bool, tuple[tuple[str, ...], ...]]:
    """Prove one root transition without mixing canonical source spellings.

    Canonical snapshots may come from the saved format-v4 source while this
    evidence comes from ObjectWrapper. Their pre-existing representational
    differences are irrelevant. The native before/after delta must be fully
    owned by the predicted semantic paths, and every predicted after-value
    must agree with the expected canonical target. The caller may then reuse
    the expected immutable shard without serializing the complete font.
    """

    predicted = tuple(tuple(str(part) for part in path) for path in paths)
    if not predicted:
        return before_evidence == current_evidence, ()
    evidence_diff = diff_models(
        {root: before_evidence},
        {root: current_evidence},
    )
    actual = tuple(tuple(change.path[1:]) for change in evidence_diff.changes)
    unexpected_paths = []
    for path in actual:
        if _evidence_path_is_predicted(path, predicted):
            continue
        current_present, current_value = semantic_value_at(
            current_evidence, path
        )
        expected_present, expected_value = semantic_value_at(expected_root, path)
        # Detached clones and Glyphs collection setters can refresh a native
        # projected value that differed from the source-neutral snapshot. If
        # the final authoritative value converges exactly to the expected
        # canonical shard, no semantic side effect escaped the plan.
        if (
            current_present == expected_present
            and current_value == expected_value
        ):
            continue
        unexpected_paths.append(path)
    unexpected = tuple(unexpected_paths)
    if unexpected and os.environ.get("GLYPHS_MCP_DEBUG_CAPTURE"):
        for path in unexpected[:12]:
            current_present, current_value = semantic_value_at(
                current_evidence, path
            )
            expected_present, expected_value = semantic_value_at(
                expected_root, path
            )
            print(
                "[Glyphs MCP][RootEvidence] root={} path={} "
                "currentPresent={} current={!r} expectedPresent={} expected={!r}".format(
                    root,
                    list(path),
                    current_present,
                    current_value,
                    expected_present,
                    expected_value,
                )[:1600],
                flush=True,
            )
    if unexpected:
        return False, unexpected
    for path in predicted:
        current_present, current_value = semantic_value_at(
            current_evidence, path
        )
        expected_present, expected_value = semantic_value_at(expected_root, path)
        if (
            current_present != expected_present
            or current_value != expected_value
        ):
            return False, (path,)
    return True, ()


def _scoped_font_model(
    font: Any,
    base_model: Mapping[str, Any],
    scope: MutationScope,
    *,
    impact: CanonicalImpact | None = None,
    extra_glyph_names: Sequence[str] = (),
    instance_ids: Optional[Sequence[str]] = None,
    expected_model: Mapping[str, Any] | None = None,
    before_root_evidence: Mapping[str, Any] | None = None,
    current_root_evidence: Mapping[str, Any] | None = None,
    allow_observed_root_expansion: bool = False,
) -> Mapping[str, Any]:
    """Refresh one canonical tree from native state without rebuilding every glyph."""

    # Copy only the top-level maps that this capture may replace. Canonical
    # shards are detached and immutable by convention; unchanged glyph/layer
    # objects remain shared until a native fragment is materialized below.
    result = dict(base_model)
    axis_tags = _axis_tag_by_native_id(font)
    authoritative_glyphs = _AuthoritativeGlyphShardResolver(
        font,
        axis_tags=axis_tags,
        instance_ids=instance_ids,
        prefer_serialized_source=_uses_serialized_canonical_source(base_model),
        document_path=_canonical_document_path(base_model),
    )
    result["glyphs"] = dict(base_model.get("glyphs", {}))
    roots = set(impact.roots if impact is not None else scope.roots)
    for root in sorted(roots - {"glyphs", "glyphOrder"}):
        current_evidence = (
            current_root_evidence[root]
            if current_root_evidence is not None
            and root in current_root_evidence
            else _native_root_evidence_value(
                font,
                root,
                instance_ids=instance_ids,
            )
        )
        candidate = current_evidence
        if (
            expected_model is not None
            and _uses_serialized_canonical_source(base_model)
        ):
            previous_evidence = (
                before_root_evidence.get(root)
                if before_root_evidence is not None
                else current_evidence
            )
            verified, unexpected = _verified_root_evidence_transition(
                root,
                previous_evidence,
                current_evidence,
                expected_model.get(root),
                _root_paths(impact, root),
            )
            observed_root = None
            if not verified:
                persistent_root = _persistent_canonical_record_root(
                    font,
                    root,
                    expected_model,
                )
                verified = persistent_root == expected_model.get(root)
                if (
                    not verified
                    and allow_observed_root_expansion
                    and persistent_root is not None
                ):
                    # Detached planning is allowed to discover canonical host
                    # effects outside the requested path. They become part of
                    # the observed plan and must later be reproduced by the
                    # strict live read-back. This is not a verification escape
                    # hatch: only the bounded official-record source may
                    # expand a root, and required-target/revert simulations
                    # keep this mode disabled.
                    observed_root = persistent_root
                    verified = True
                if (
                    not verified
                    and os.environ.get("GLYPHS_MCP_DEBUG_CAPTURE")
                    and persistent_root is not None
                ):
                    persistent_diff = diff_models(
                        {root: persistent_root},
                        {root: expected_model.get(root)},
                    )
                    print(
                        "[Glyphs MCP][RootRecordFallback] root={} "
                        "changeCount={} firstPaths={}".format(
                            root,
                            len(persistent_diff.changes),
                            [
                                list(change.path[1:])
                                for change in persistent_diff.changes[:12]
                            ],
                        ),
                        flush=True,
                    )
            if not verified:
                raise HostAccessError(
                    "Native {} changes escaped the predicted canonical impact "
                    "(first paths: {})".format(
                        root,
                        [list(path) for path in unexpected[:12]],
                    )
                )
            candidate = (
                observed_root
                if observed_root is not None
                else expected_model.get(root)
            )
        previous = base_model.get(root)
        result[root] = previous if candidate == previous else candidate

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
    if "glyphOrder" in roots or removed or added:
        persistent = authoritative_glyphs.document_model()
        persistent_order = (
            persistent.get("glyphOrder")
            if isinstance(persistent, Mapping)
            else [
                str(_safe_getattr(glyph, "name") or "")
                for glyph in _sequence_values(_safe_getattr(font, "glyphs"))
                if str(_safe_getattr(glyph, "name") or "")
            ]
        )
        if not isinstance(persistent_order, list):
            raise HostAccessError("Glyphs did not provide authoritative glyph order")
        previous_order = base_model.get("glyphOrder")
        result["glyphOrder"] = (
            previous_order
            if list(persistent_order) == previous_order
            else list(persistent_order)
        )
    expected_glyphs = (
        expected_model.get("glyphs", {})
        if isinstance(expected_model, Mapping)
        else {}
    )
    if not isinstance(expected_glyphs, Mapping):
        expected_glyphs = {}
    for name in removed:
        base_glyphs.pop(name, None)
    for name in added:
        reference = expected_glyphs.get(name)
        base_glyphs[name] = authoritative_glyphs.capture(
            native_index[name],
            layer_order_reference=(
                reference if isinstance(reference, Mapping) else None
            ),
        )
    extra = {str(value) for value in extra_glyph_names}
    for name in sorted(set(scope.glyph_names) | extra):
        glyph = native_index.get(name)
        if glyph is None:
            # A collection insertion scopes the future identity before it
            # exists in either the canonical source or the detached clone.
            # Existing identities that disappeared are represented by
            # ``removed``. Request validation owns missing update/delete
            # targets; capture only reflects the native collection it sees.
            continue
        paths = impact.glyph_paths.get(name, ()) if impact is not None else ()
        base = base_glyphs.get(name)
        reference = expected_glyphs.get(name)
        if not isinstance(reference, Mapping):
            reference = base if isinstance(base, Mapping) else None
        if (
            isinstance(base, Mapping)
            and paths
            and not impact.requires_complete_glyph(name)
        ):
            if (
                _uses_serialized_canonical_source(base_model)
                and _paths_require_source_neutral_glyph(paths)
            ):
                base_glyphs[name] = authoritative_glyphs.capture(
                    glyph,
                    layer_order_reference=reference,
                )
            else:
                base_glyphs[name] = _glyph_fragment_model(
                    glyph,
                    base,
                    paths,
                    axis_tags=axis_tags,
                    document_path=_canonical_document_path(base_model),
                    layer_order_reference=reference,
                )
        else:
            base_glyphs[name] = authoritative_glyphs.capture(
                glyph,
                layer_order_reference=reference,
            )
    if isinstance(base_model, CanonicalSnapshot):
        return CanonicalSnapshot.from_shards(
            {name: value for name, value in result.items() if name != "glyphs"},
            result["glyphs"],
            previous=base_model,
            coverage=base_model.coverage,
        )
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


def _unproved_revision_glyphs(
    font: Any,
    base: Mapping[str, Any],
    target: Mapping[str, Any],
    impact: CanonicalImpact,
    changed_names: Sequence[str],
) -> tuple[str, ...]:
    """Return broad revision changes not covered by bounded native proof.

    Predicted glyph fragments are already captured by ``impact``. For a broad
    marker that changed outside that impact, compare the native glyph root,
    layer membership/order, canonical scalars, and lightweight layer revision
    tokens with the immutable source evidence. Only a mismatch materializes
    the complete glyph, preserving detection of unexpected host effects.
    """

    if not isinstance(base, CanonicalSnapshot):
        return tuple(str(name) for name in changed_names)
    evidence = base.native_revision_evidence.get("layers", {})
    if not isinstance(evidence, Mapping):
        return tuple(str(name) for name in changed_names)
    base_glyphs = base.get("glyphs", {})
    target_glyphs = target.get("glyphs", {})
    if not isinstance(base_glyphs, Mapping) or not isinstance(
        target_glyphs, Mapping
    ):
        return tuple(str(name) for name in changed_names)
    native = {
        str(_safe_getattr(glyph, "name") or ""): glyph
        for glyph in _sequence_values(_safe_getattr(font, "glyphs"))
        if str(_safe_getattr(glyph, "name") or "")
    }
    unproved: list[str] = []
    for raw_name in changed_names:
        name = str(raw_name)
        if name in impact.glyph_paths:
            continue
        glyph = native.get(name)
        modeled = base_glyphs.get(name)
        expected = target_glyphs.get(name)
        before_tokens = evidence.get(name)
        if not (
            glyph is not None
            and isinstance(modeled, Mapping)
            and isinstance(expected, Mapping)
            and isinstance(before_tokens, Mapping)
            and _verified_glyph_fragment_matches(
                glyph,
                modeled,
                expected,
                (),
                before_layer_tokens=before_tokens,
                current_layer_tokens=_layer_revision_index(glyph),
            )
        ):
            unproved.append(name)
    return tuple(unproved)


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
    layers = glyph.get("layers", ()) if isinstance(glyph, Mapping) else ()
    if isinstance(layers, Mapping):
        layers = list(layers.values())
    if isinstance(layers, (list, tuple)):
        for layer in layers:
            if not isinstance(layer, Mapping):
                continue
            identities = {
                str(layer.get("id") or ""),
                str(layer.get("masterId") or ""),
            }
            if identities & allowed_layers:
                allowed_layers.add(str(layer.get("id") or ""))
    violations: list[tuple[str, ...]] = []
    for change in changes.changes:
        path = change.path
        allowed = (
            len(path) >= 3
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


def _apply_native_constructor_fields(
    value: Any,
    spec: Mapping[str, Any],
    fields: Mapping[str, str] | Sequence[str],
) -> None:
    """Apply explicit non-null fields to one newly constructed native value.

    Canonical ``null`` represents the native constructor default for optional
    saved fields. Passing Python ``None`` through PyObjC is not equivalent:
    scalar Objective-C setters (notably ``char`` orientation fields) reject it,
    while some string setters persist the text ``"None"``. Fresh entity replay
    therefore leaves null fields at their native defaults and writes every
    explicit false/zero/empty collection normally.
    """

    aliases = dict(fields) if isinstance(fields, Mapping) else {
        str(field): str(field) for field in fields
    }
    for canonical, native in aliases.items():
        if canonical not in spec:
            continue
        target = spec.get(canonical)
        if target is None:
            continue
        _set_native_property(value, native, copy.deepcopy(target))


def _set_registered_native_field(
    value: Any,
    source: str,
    canonical_name: str,
    target: Any,
) -> None:
    """Replay one canonical leaf through its registry-owned native contract.

    Glyphs exposes some saved dictionaries as read-only Python properties over
    mutable native proxies (for example Smart Component values). Replacing the
    proxy contents is the authoritative write in that case; ordinary scalar
    and collection properties retain the shared Objective-C setter boundary.
    """

    field_spec = CANONICAL_SCHEMA.field_spec_for_canonical(source, canonical_name)
    native_name = CANONICAL_SCHEMA.native_field_for_canonical(source, canonical_name)
    if field_spec.replay == "info_value_label":
        if not callable(_safe_getattr(value, "setLabel_")):
            # Plain test doubles and older wrappers can still expose the
            # historical plural Python property. Real Glyphs 4 uses the
            # singular Objective-C info-value contract below.
            _set_native_field_value(
                value, "labels", copy.deepcopy(target or [])
            )
            return
        labels = list(target or [])
        native_label = _construct_info_property(
            {"key": "", "value": None, "values": labels}
        )
        _set_native_property(value, native_name, native_label)
        return
    _set_native_field_value(value, native_name, target)


def _set_native_field_value(
    value: Any,
    native_name: str,
    target: Any,
) -> None:
    """Write a scalar or replace the contents of a native mapping proxy."""

    current = _safe_getattr(value, native_name)
    if isinstance(target, Mapping) and current is not None:
        _replace_mapping_values(current, target)
        return
    try:
        _set_native_property(value, native_name, copy.deepcopy(target))
    except Exception as exc:
        raise HostAccessError(
            "native field replay failed for {}.{} from {}: {}".format(
                value.__class__.__name__,
                native_name,
                type(target).__name__,
                repr(target)[:160],
            )
        ) from exc


def _native_record_replay_value(
    kind: str,
    official_name: str,
    value: Any,
) -> Any:
    """Bridge official record values to their native SDK representation."""

    if official_name in {"pos", "scale", "size"} and isinstance(
        value, Sequence
    ) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) >= 2:
            try:
                from Foundation import NSMakePoint, NSMakeSize  # type: ignore[import-not-found]

                constructor = NSMakeSize if official_name == "size" else NSMakePoint
                return constructor(float(value[0]), float(value[1]))
            except Exception as exc:
                raise HostAccessError(
                    "Glyphs could not construct a native {} value".format(
                        official_name
                    )
                ) from exc

    if kind == "hint" and official_name in {
        "origin",
        "target",
        "other1",
        "other2",
    }:
        if value is None:
            return None
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            try:
                from Foundation import NSIndexPath  # type: ignore[import-not-found]

                indexes = tuple(int(item) for item in value)
                return NSIndexPath.indexPathWithIndexes_length_(
                    indexes, len(indexes)
                )
            except Exception as exc:
                raise HostAccessError(
                    "Glyphs could not construct a hint index path"
                ) from exc
    return copy.deepcopy(value)


def _new_anchor(spec: Mapping[str, Any]) -> Any:
    try:
        from GlyphsApp import GSAnchor  # type: ignore[import-not-found]
    except Exception as exc:
        raise HostAccessError("GSAnchor is unavailable") from exc
    name = str(spec.get("name") or "")
    position = spec.get("position") or (0, 0)
    try:
        anchor = GSAnchor(name, (float(position[0]), float(position[1])))
    except Exception:
        anchor = GSAnchor()
        _set_native_property(anchor, "name", name)
        _set_native_property(
            anchor, "position", (float(position[0]), float(position[1]))
        )
    _apply_native_constructor_fields(
        anchor,
        spec,
        ("orientation", "locked", "attributes", "userData"),
    )
    return anchor


def _replace_anchors(layer: Any, anchors: Any) -> None:
    collection = _safe_getattr(layer, "anchors")
    existing = _sequence_values(collection)
    for anchor in reversed(existing):
        try:
            collection.remove(anchor)
        except Exception:
            name = str(_safe_getattr(anchor, "name") or "")
            if name:
                try:
                    del collection[name]
                except Exception:
                    pass
    if isinstance(anchors, Mapping):
        specs = [
            {"name": str(name), "position": list(position)}
            for name, position in anchors.items()
        ]
    else:
        specs = [value for value in anchors or () if isinstance(value, Mapping)]
    for spec in specs:
        anchor = _new_anchor(spec)
        try:
            collection.append(anchor)
        except Exception:
            collection[str(spec.get("name") or "")] = anchor


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
        _apply_native_constructor_fields(
            node,
            node_spec,
            ("orientation", "locked", "attributes"),
        )
        nodes.append(node)
    _replace_collection(path.nodes, nodes)
    _set_native_property(path, "closed", bool(spec.get("closed", True)))
    _apply_native_constructor_fields(path, spec, ("locked", "attributes"))
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
        for field in ("orientation", "locked", "attributes"):
            if current_node.get(field) != target_node.get(field):
                _set_native_property(
                    native_node, field, copy.deepcopy(target_node.get(field))
                )
    for native_path, current_path, target_path in zip(
        native_paths, current_specs, target_specs
    ):
        for field in ("locked", "attributes"):
            if current_path.get(field) != target_path.get(field):
                _set_native_property(
                    native_path, field, copy.deepcopy(target_path.get(field))
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
    component_fields = (
            "position",
            "scale",
            "angle",
            "slant",
            "alignment",
            "anchor",
            "locked",
            "masterId",
            "orientation",
            "keepWeight",
            "traverseAnchors",
            "attributes",
            "piece",
        )
    for field in component_fields:
        if field in spec and spec.get(field) is not None:
            _set_registered_native_field(
                component,
                "definition.component",
                field,
                spec.get(field),
            )
    return component


def _new_image(
    spec: Mapping[str, Any], *, document_path: Any = None
) -> Any:
    try:
        from GlyphsApp import GSBackgroundImage  # type: ignore[import-not-found]
    except Exception as exc:
        raise HostAccessError("GSBackgroundImage is unavailable") from exc
    image = GSBackgroundImage()
    fields = dict(spec)
    image_path = fields.get("imagePath")
    if image_path not in (None, "") and document_path not in (None, ""):
        normalized = os.path.normpath(str(image_path))
        if not os.path.isabs(normalized):
            fields["imagePath"] = os.path.abspath(
                os.path.join(
                    os.path.dirname(os.path.abspath(str(document_path))),
                    normalized,
                )
            )
    aliases = {
        "imagePath": "imagePath",
        "imageURL": "imageURL",
        "position": "position",
        "scale": "scale",
        "crop": "crop",
        "angle": "angle",
        "slant": "slant",
        "alpha": "alpha",
        "locked": "locked",
        "attributes": "attributes",
    }
    _apply_native_constructor_fields(image, fields, aliases)
    return image


def _new_shape_group(spec: Mapping[str, Any]) -> Any:
    try:
        from GlyphsApp import GSShapeGroup  # type: ignore[import-not-found]
    except Exception as exc:
        raise HostAccessError("GSShapeGroup is unavailable") from exc
    group = GSShapeGroup()
    _set_native_property(group, "groupId", str(spec.get("groupId") or ""))
    _set_native_property(group, "attributes", copy.deepcopy(spec.get("attributes") or {}))
    return group


def _replace_shapes(layer: Any, specs: Sequence[Mapping[str, Any]]) -> None:
    """Replace one complete ordered shape collection.

    V6 owns cross-kind order. Native-only shape kinds require replay evidence;
    ordinary typed replay can construct paths and components directly.
    """

    shapes = []
    for shape in specs:
        kind = str(shape.get("kind") or "")
        value = shape.get("value")
        if not isinstance(value, Mapping):
            raise HostAccessError("canonical shape value must be an object")
        if kind == "path":
            shapes.append(_new_path(value))
        elif kind == "component":
            shapes.append(_new_component(value))
        elif kind == "image":
            shapes.append(
                _new_image(
                    value,
                    document_path=_document_path_for_native(layer),
                )
            )
        elif kind == "shape_group":
            shapes.append(_new_shape_group(value))
        else:
            raise HostAccessError(
                "canonical {} shape replay requires native evidence".format(
                    kind or "unknown"
                )
            )
    collection = _safe_getattr(layer, "shapes")
    if collection is None:
        raise HostAccessError("Glyphs did not expose the writable layer.shapes store")
    try:
        _set_native_property(layer, "shapes", shapes)
    except Exception:
        _replace_collection(collection, shapes)


def _update_shapes_in_place(
    layer: Any,
    current_shapes: Sequence[Mapping[str, Any]],
    target_shapes: Sequence[Mapping[str, Any]],
) -> bool:
    if len(current_shapes) != len(target_shapes):
        return False
    if [shape.get("kind") for shape in current_shapes] != [
        shape.get("kind") for shape in target_shapes
    ]:
        return False
    if [shape.get("id") for shape in current_shapes] != [
        shape.get("id") for shape in target_shapes
    ]:
        return False
    for kind in ("path", "component"):
        current = [
            shape.get("value")
            for shape in current_shapes
            if shape.get("kind") == kind and isinstance(shape.get("value"), Mapping)
        ]
        target = [
            shape.get("value")
            for shape in target_shapes
            if shape.get("kind") == kind and isinstance(shape.get("value"), Mapping)
        ]
        updater = _update_paths_in_place if kind == "path" else _update_components_in_place
        if current != target and not updater(layer, current, target):
            return False
    return not any(
        shape.get("kind") not in {"path", "component"}
        and shape != target_shapes[index]
        for index, shape in enumerate(current_shapes)
    )


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
    for native, current, target in zip(
        native_components, current_specs, target_specs
    ):
        current_name = str(current.get("name") or "")
        target_name = str(target.get("name") or "")
        native_name = str(_safe_getattr(native, "componentName") or "")
        if current_name != target_name or native_name != current_name:
            return False
        for field in (
            "position",
            "scale",
            "angle",
            "slant",
            "alignment",
            "anchor",
            "locked",
            "masterId",
            "orientation",
            "keepWeight",
            "traverseAnchors",
            "attributes",
            "piece",
        ):
            if current.get(field) != target.get(field):
                _set_registered_native_field(
                    native,
                    "definition.component",
                    field,
                    target.get(field),
                )
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


def _kerning_direction(kind: str) -> Any:
    try:
        from GlyphsApp import GSLTR, GSRTL, GSVERTICAL  # type: ignore[import-not-found]

        return {"ltr": GSLTR, "rtl": GSRTL, "vertical": GSVERTICAL}[kind]
    except Exception:
        return {"ltr": 0, "rtl": 1, "vertical": 2}[kind]


def _replace_kerning_domain(font: Any, kind: str, target_pairs: Any) -> None:
    attribute = {"ltr": "kerning", "rtl": "kerningRTL", "vertical": "kerningVertical"}[kind]
    current_model = _kerning_domain_model(font, attribute)
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
    direction = _kerning_direction(kind)
    for key in sorted(set(current) - set(target)):
        if callable(remove):
            arguments = (
                key[0],
                _native_kerning_key(font, key[1]),
                _native_kerning_key(font, key[2]),
            )
            try:
                remove(*arguments, direction)
            except TypeError:
                if kind != "ltr":
                    raise HostAccessError(
                        "Glyphs did not expose directional kerning removal"
                    )
                remove(*arguments)
    setter = _safe_getattr(font, "setKerningForPair")
    if not callable(setter):
        raise HostAccessError("Glyphs did not expose setKerningForPair")
    for key in sorted(target):
        if current.get(key) != target[key]:
            arguments = (
                key[0],
                _native_kerning_key(font, key[1]),
                _native_kerning_key(font, key[2]),
                float(target[key]),
            )
            try:
                setter(*arguments, direction)
            except TypeError:
                if kind != "ltr":
                    raise HostAccessError(
                        "Glyphs did not expose directional kerning assignment"
                    )
                setter(*arguments)


def _replace_kerning(font: Any, target: Any) -> None:
    domains = target if isinstance(target, Mapping) else {"ltr": target}
    if "context" in domains:
        _replace_context_kerning(
            font, domains.get("context", {}), validate_only=True
        )
    for kind in ("ltr", "rtl", "vertical"):
        _replace_kerning_domain(font, kind, domains.get(kind, {}))
    if "context" in domains:
        _replace_context_kerning(font, domains.get("context", {}))


def _replace_context_kerning(
    font: Any, target_contexts: Any, *, validate_only: bool = False
) -> None:
    current_model = _context_kerning_model(font)
    current = {
        (str(context_key), str(master_id)): value
        for context_key, master_values in current_model.items()
        if isinstance(master_values, Mapping)
        for master_id, value in master_values.items()
    }
    target = {
        (str(context_key), str(master_id)): value
        for context_key, master_values in (
            target_contexts.items()
            if isinstance(target_contexts, Mapping)
            else ()
        )
        if isinstance(master_values, Mapping)
        for master_id, value in master_values.items()
    }
    removed = sorted(set(current) - set(target))
    changed = sorted(
        key for key, value in target.items() if current.get(key) != value
    )
    remover = _safe_getattr(
        font, "removeContextKerningForKey_fontMasterID_"
    ) or _safe_getattr(font, "removeContextKerningForKey")
    setter = _safe_getattr(
        font, "setContextKerningForKey_fontMasterID_value_"
    ) or _safe_getattr(font, "setContextKerningForKey")
    if removed and not callable(remover):
        raise HostAccessError(
            "Glyphs did not expose contextual kerning removal"
        )
    if changed and not callable(setter):
        raise HostAccessError(
            "Glyphs did not expose contextual kerning assignment"
        )
    if validate_only:
        return
    for context_key, master_id in removed:
        remover(context_key, master_id)
    for context_key, master_id in changed:
        setter(context_key, master_id, float(target[(context_key, master_id)]))


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


def _replace_native_collection_order(
    collection: Any,
    values: Sequence[Any],
    *,
    identity_storage: Any = None,
    notification_owner: Any = None,
    notification_key: str | None = None,
) -> None:
    desired = list(values)
    current = _sequence_values(collection)
    if len(current) == len(desired) and all(
        before is after for before, after in zip(current, desired)
    ):
        return
    # Some Glyphs collection proxies implement their public whole-collection
    # setter by rebuilding every dependent native object. When the requested
    # change is only a permutation, preserve the existing identities and move
    # them in their authoritative mutable storage instead. The complete
    # detached and live read-back verification remains the correctness proof;
    # this path changes only the native replay primitive.
    storage_values = (
        _sequence_values(identity_storage)
        if identity_storage is not None
        else []
    )
    exchange = _safe_getattr(
        identity_storage, "exchangeObjectAtIndex_withObjectAtIndex_"
    )
    same_identity_permutation = (
        callable(exchange)
        and len(storage_values) == len(current) == len(desired)
        and all(
            stored is exposed
            for stored, exposed in zip(storage_values, current)
        )
        and {id(value) for value in storage_values}
        == {id(value) for value in desired}
    )
    if same_identity_permutation:
        will_change = _safe_getattr(
            notification_owner, "willChangeValueForKey_"
        )
        did_change = _safe_getattr(
            notification_owner, "didChangeValueForKey_"
        )
        notified = (
            bool(notification_key)
            and callable(will_change)
            and callable(did_change)
        )
        if notified:
            will_change(notification_key)
        try:
            working = list(storage_values)
            for target_index, target in enumerate(desired):
                if working[target_index] is target:
                    continue
                source_index = next(
                    index
                    for index in range(target_index + 1, len(working))
                    if working[index] is target
                )
                exchange(target_index, source_index)
                working[target_index], working[source_index] = (
                    working[source_index],
                    working[target_index],
                )
        finally:
            if notified:
                did_change(notification_key)
        return
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
    for index in reversed(range(len(current))):
        _remove_native_collection_item(collection, index, current[index])
    for value in desired:
        _append_native_collection_item(collection, value)


def _native_layer_identity(layer: Any) -> str:
    return str(_safe_getattr(layer, "layerId") or _safe_getattr(layer, "id") or "")


def _set_ordered_glyph_layers(glyph: Any, values: Sequence[Any]) -> None:
    """Assign one identity-preserving native layer collection atomically.

    ``GSGlyph.layers`` is backed by Glyphs' ``MGOrderedDictionary``. Building
    that exact type preserves insertion order while ``setLayers:`` retains the
    official ownership, undo, and notification boundary. A plain
    ``NSMutableDictionary`` is intentionally insufficient because its key
    order is undefined. Adapter fakes expose the same boundary as ``setter``.
    """

    desired = list(values)
    native_setter = _safe_getattr(glyph, "setLayers_")
    if callable(native_setter):
        try:
            from Foundation import NSClassFromString  # type: ignore[import-not-found]

            ordered_class = NSClassFromString("MGOrderedDictionary")
            if ordered_class is None:
                raise RuntimeError("MGOrderedDictionary is unavailable")
            ordered = ordered_class.alloc().initWithCapacity_(len(desired))
            insert = _safe_getattr(ordered, "setObject_forKey_")
            if not callable(insert):
                raise RuntimeError("MGOrderedDictionary insertion is unavailable")
            for layer in desired:
                identity = _native_layer_identity(layer)
                if not identity:
                    raise RuntimeError("layer identity is empty")
                insert(layer, identity)
            native_setter(ordered)
            return
        except Exception as exc:
            raise HostAccessError(
                "Glyphs could not atomically assign the ordered layer collection"
            ) from exc

    collection = _safe_getattr(glyph, "layers")
    atomic_setter = _safe_getattr(collection, "setter")
    if callable(atomic_setter):
        atomic_setter(desired)
        return
    raise HostAccessError("Glyphs does not expose an ordered layer setter")


def _replace_glyph_layer_order(glyph: Any, values: Sequence[Any]) -> None:
    """Replay the one order Glyphs actually owns for a glyph's layers.

    Glyphs projects master layers first according to the font master order.
    Only the remaining native layer array is user-orderable. The public
    ``GlyphLayerProxy.setter`` rebuilds an unordered NSDictionary and therefore
    cannot prove order. Exact-ID detach/reattach is also invalid here: the live
    glyph undo manager may restore the removed entry before reattachment even
    though a detached copy appears correct. Use one ordered native assignment.
    """

    _replace_glyph_layer_collection(
        glyph,
        values,
        allow_master_membership_change=False,
    )


def _replace_glyph_layer_collection(
    glyph: Any,
    values: Sequence[Any],
    *,
    allow_master_membership_change: bool,
) -> None:
    """Atomically replace canonical layer membership and order.

    Layer lifecycle may change only the non-master suffix. Master lifecycle
    opts into changing the master prefix, but both domains share the same
    ``setLayers:`` ownership boundary so Glyphs' undo manager cannot reinsert
    an exact-ID deletion under a fresh backup identity.
    """

    desired = list(values)
    current = _native_layers(glyph)
    desired_ids = [_native_layer_identity(layer) for layer in desired]
    current_ids = [_native_layer_identity(layer) for layer in current]
    if not all(desired_ids) or len(set(desired_ids)) != len(desired_ids):
        raise HostAccessError("Glyphs layer collection requires unique stable identities")

    def partition(layers: Sequence[Any]) -> tuple[list[Any], list[Any]]:
        masters: list[Any] = []
        non_masters: list[Any] = []
        reached_non_master = False
        for layer in layers:
            is_master = bool(_maybe_call(_safe_getattr(layer, "isMasterLayer", False)))
            if is_master and reached_non_master:
                raise HostAccessError("Glyphs master layers must form the canonical prefix")
            if is_master:
                masters.append(layer)
            else:
                reached_non_master = True
                non_masters.append(layer)
        return masters, non_masters

    current_masters, _ = partition(current)
    desired_masters, _ = partition(desired)
    if not allow_master_membership_change and [
        _native_layer_identity(layer) for layer in current_masters
    ] != [_native_layer_identity(layer) for layer in desired_masters]:
        raise HostAccessError("layer lifecycle cannot reorder master layers")
    if current_ids == desired_ids:
        return

    _set_ordered_glyph_layers(glyph, desired)

    actual_ids = [
        _native_layer_identity(layer) for layer in _native_layers(glyph)
    ]
    if actual_ids != desired_ids:
        raise HostAccessError(
            "Glyphs did not preserve the requested layer collection "
            "(expected {} {!r}; actual {} {!r})".format(
                len(desired_ids), desired_ids[:12],
                len(actual_ids), actual_ids[:12],
            )
        )


def _construct_native_entity(kind: str, name: str = "") -> Any:
    """Create one native entity behind a single testable SDK boundary."""

    try:
        import GlyphsApp  # type: ignore[import-not-found]
    except Exception as exc:
        raise HostAccessError("Glyphs native entity classes are unavailable") from exc
    class_names = {
        "glyph": "GSGlyph",
        "instance": "GSInstance",
        "features": "GSFeature",
        "classes": "GSClass",
        "featurePrefixes": "GSFeaturePrefix",
        "axis": "GSAxis",
        "customParameter": "GSCustomParameter",
        "property": "GSProperty",
        "metric": "GSMetric",
        "stem": "GSMetric",
        "number": "GSMetric",
        "guide": "GSGuide",
        "hint": "GSHint",
        "annotation": "GSAnnotation",
        "smartAxis": "GSSmartComponentAxis",
    }
    constructor = getattr(GlyphsApp, class_names.get(kind, ""), None)
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


def _exact_native_template_additions(
    current_entities: Mapping[str, Any],
    target_entities: Mapping[str, Any],
    templates: Mapping[str, Any] | None,
    *,
    reuse_native_templates: bool,
) -> frozenset[str]:
    """Identify additions backed by exact, already-qualified native evidence.

    Attaching such an object is the replay action. Replaying every canonical
    default from an empty synthetic baseline can change how Glyphs serializes
    an otherwise identical entity. Complete canonical and native read-back
    still proves the attachment, so no domain-specific default exceptions are
    needed.
    """

    del reuse_native_templates  # Detached copies are qualified evidence too.
    if not templates:
        return frozenset()
    available = {str(identity) for identity in templates}
    return frozenset(
        str(identity)
        for identity in target_entities
        if identity not in current_entities and str(identity) in available
    )


def _apply_ordered_record_collection(
    owner: Any,
    attribute: str,
    current: Sequence[Mapping[str, Any]],
    target: Sequence[Mapping[str, Any]],
    *,
    kind: str,
    fields: Mapping[str, str] | Sequence[str],
    templates: Mapping[str, Any] | None = None,
    reuse_native_templates: bool = False,
) -> None:
    collection = _safe_getattr(owner, attribute)
    if collection is None:
        if not current and not target:
            return
        raise HostAccessError("Glyphs did not expose {}".format(attribute))
    native_by_id = _sync_native_entities(
        collection,
        current,
        target,
        kind=kind,
        templates=templates,
        reuse_native_templates=reuse_native_templates,
        owner=owner,
    )
    _, current_entities = require_indexed_entities(current, attribute)
    target_order, target_entities = require_indexed_entities(target, attribute)
    exact_additions = _exact_native_template_additions(
        current_entities,
        target_entities,
        templates,
        reuse_native_templates=reuse_native_templates,
    )
    aliases = dict(fields) if isinstance(fields, Mapping) else {
        str(field): str(field) for field in fields
    }
    try:
        registered = {
            canonical: CANONICAL_SCHEMA.native_field_for_official(
                "definition.{}".format(kind), canonical
            )
            for canonical in aliases
        }
    except KeyError:
        registered = aliases
    default_entity = None
    for identity in target_order:
        native = native_by_id[identity]
        after = target_entities[identity]
        before = (
            after
            if identity in exact_additions
            else current_entities.get(identity, {})
        )
        for canonical, native_name in aliases.items():
            if before.get(canonical) != after.get(canonical):
                native_name = registered.get(canonical, native_name)
                target_value = after.get(canonical)
                if target_value is None:
                    if default_entity is None:
                        default_entity = _construct_native_entity(kind)
                    target_value = _safe_getattr(default_entity, native_name)
                _set_native_field_value(
                    native,
                    native_name,
                    _native_record_replay_value(
                        kind, canonical, target_value
                    ),
                )


def _construct_info_property(record: Mapping[str, Any]) -> Any:
    """Build one official Glyphs font-info property from canonical data.

    ``GSInfoValueLocalized.values`` is a collection of native
    ``GSInfoValue`` objects. Replaying canonical dictionaries directly works
    in Python fakes but fails in Glyphs and can desynchronize a parent
    convenience property such as ``GSInstance.name``.
    """

    try:
        from GlyphsApp import (  # type: ignore[import-not-found]
            GSInfoValue,
            GSInfoValueLocalized,
            GSInfoValueSingle,
        )
    except Exception as exc:
        raise HostAccessError(
            "Glyphs native font-info property classes are unavailable"
        ) from exc

    key = str(record.get("key") or "")
    localized = list(record.get("values") or [])
    if localized:
        native = GSInfoValueLocalized()
        _set_native_property(native, "key", key)
        native_values = []
        for item in localized:
            value = GSInfoValue()
            _set_native_property(
                value,
                "languageTag",
                str(item.get("language") or "dflt"),
            )
            _set_native_property(
                value, "value", copy.deepcopy(item.get("value"))
            )
            native_values.append(value)
        _set_native_property(native, "values", native_values)
        return native

    native = GSInfoValueSingle()
    _set_native_property(native, "key", key)
    _set_native_property(native, "value", copy.deepcopy(record.get("value")))
    return native


def _apply_property_collection(
    owner: Any,
    current: Sequence[Mapping[str, Any]],
    target: Sequence[Mapping[str, Any]],
    *,
    owner_is_new: bool,
) -> None:
    """Replay one ordered official property collection and verify it."""

    collection = _safe_getattr(owner, "properties")
    if collection is None:
        if not current and not target:
            return
        raise HostAccessError("Glyphs did not expose properties")
    observed = _property_models(owner)
    desired = [copy.deepcopy(dict(record)) for record in target]
    if observed == desired:
        return
    if not owner_is_new and observed != list(current):
        raise HostAccessError(
            "Glyphs property collection diverged before mutation "
            "(owner={} {!r}; native={} {!r}; expected={} {!r})".format(
                type(owner).__name__,
                str(_safe_getattr(owner, "id") or _safe_getattr(owner, "name") or ""),
                len(observed),
                [item.get("id") for item in observed[:12]],
                len(current),
                [item.get("id") for item in list(current)[:12]],
            )
        )
    native_values = [_construct_info_property(record) for record in desired]
    _replace_native_collection_order(collection, native_values)
    verified = _property_models(owner)
    if verified != desired:
        raise HostAccessError(
            "Glyphs did not preserve the requested property collection "
            "(expected {} {!r}; actual {} {!r})".format(
                len(desired), desired[:12], len(verified), verified[:12]
            )
        )


def _staged_native_types() -> dict[str, Any]:
    """Resolve the registry-owned constructors at the native adapter boundary."""

    try:
        import GlyphsApp  # type: ignore[import-not-found]
    except Exception:
        return {}
    return {
        name: constructor
        for name in NATIVE_CONSTRUCTOR_NAMES
        if (constructor := getattr(GlyphsApp, name, None)) is not None
    }


def _sync_native_entities(
    collection: Any,
    current: Sequence[Mapping[str, Any]],
    target: Sequence[Mapping[str, Any]],
    *,
    kind: str,
    templates: Mapping[str, Any] | None = None,
    reuse_native_templates: bool = False,
    owner: Any | None = None,
) -> dict[str, Any]:
    current_order, _ = require_indexed_entities(current, kind)
    target_order, target_entities = require_indexed_entities(target, kind)
    native_values = _sequence_values(collection)
    if len(native_values) != len(current_order):
        owner_type = type(owner).__name__ if owner is not None else "unknown"
        owner_identity = str(
            _safe_getattr(owner, "id")
            or _safe_getattr(owner, "name")
            or ""
        )
        native_names = [
            str(_safe_getattr(value, "name") or _safe_getattr(value, "key") or "")
            for value in native_values[:12]
        ]
        raise HostAccessError(
            "Glyphs {} collection diverged before mutation "
            "(owner={} {!r}; native={} {!r}; expected={} {!r})".format(
                kind,
                owner_type,
                owner_identity,
                len(native_values),
                native_names,
                len(current_order),
                current_order[:12],
            )
        )
    native_by_id = {
        identity: native_values[index]
        for index, identity in enumerate(current_order)
    }
    available_templates = dict(templates or {})
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
        template = available_templates.get(identity)
        value = (
            template
            if reuse_native_templates and template is not None
            else _copy_native_object(template, kind=kind)
            if template is not None
            # Instance names are owned by the official ``styleNames`` child
            # property. Constructing with the convenience name would eagerly
            # create that child before canonical replay owns it.
            else _construct_native_entity(
                kind, "" if kind == "instance" else entity_name
            )
        )
        if (
            kind != "instance"
            and str(_safe_getattr(value, "name") or "") != entity_name
        ):
            _set_native_property(value, "name", entity_name)
        native_by_id[identity] = value
        _append_native_collection_item(collection, value)
    _replace_native_collection_order(
        collection,
        [native_by_id[identity] for identity in target_order],
    )
    return native_by_id


def _apply_code_collection(
    font: Any,
    attribute: str,
    current: Sequence[Mapping[str, Any]],
    target: Sequence[Mapping[str, Any]],
    *,
    templates: Mapping[str, Any] | None = None,
    reuse_native_templates: bool = False,
) -> None:
    """Apply membership, order, and scalar fields through one collection path."""

    schema_source = {
        "features": "definition.feature",
        "classes": "definition.class",
        "featurePrefixes": "definition.featurePrefix",
    }.get(attribute)
    if schema_source is None:
        raise HostAccessError(
            "unregistered OpenType collection replay: {}".format(attribute)
        )
    schema_fields = frozenset(
        CANONICAL_SCHEMA.canonical_fields_for(
            schema_source,
            roles=(FieldRole.WRITABLE,),
            replays=("adapter", "info_value_label"),
        )
    )
    identity_field = CANONICAL_SCHEMA.object_for(schema_source).identity
    native_identity_field = CANONICAL_SCHEMA.native_field_for_canonical(
        schema_source, identity_field
    )

    collection = _safe_getattr(font, attribute)
    native_by_id = _sync_native_entities(
        collection,
        current,
        target,
        kind=attribute,
        templates=templates,
        reuse_native_templates=reuse_native_templates,
    )
    _, current_entities = require_indexed_entities(current, attribute)
    target_order, target_entities = require_indexed_entities(target, attribute)
    exact_additions = _exact_native_template_additions(
        current_entities,
        target_entities,
        templates,
        reuse_native_templates=reuse_native_templates,
    )
    for identity in target_order:
        native = native_by_id[identity]
        after = target_entities[identity]
        before = (
            after
            if identity in exact_additions
            else current_entities.get(identity, {})
        )
        target_identity = str(
            after.get(identity_field) or after.get("id") or ""
        )
        if str(_safe_getattr(native, native_identity_field) or "") != target_identity:
            _set_native_property(native, native_identity_field, target_identity)
        # Automatic mode is applied first. Custom code is legal only in the
        # resulting manual state, as enforced by the pure request builder.
        if before.get("automatic") != after.get("automatic"):
            _set_native_property(native, "automatic", bool(after.get("automatic")))
        if before.get("code") != after.get("code"):
            _set_native_property(native, "code", str(after.get("code") or ""))
        if before.get("disabled") != after.get("disabled"):
            _set_native_property(native, "disabled", bool(after.get("disabled")))
        for field in ("tag", "notes", "labels"):
            if field in schema_fields and before.get(field) != after.get(field):
                _set_registered_native_field(
                    native,
                    schema_source,
                    field,
                    copy.deepcopy(after.get(field)),
                )


def _apply_axis_collection(
    font: Any,
    current: Sequence[Mapping[str, Any]],
    target: Sequence[Mapping[str, Any]],
    *,
    templates: Mapping[str, Any] | None = None,
    reuse_native_templates: bool = False,
) -> None:
    _apply_ordered_record_collection(
        font,
        "axes",
        current,
        target,
        kind="axis",
        fields={
            "tag": "axisTag",
            "name": "name",
            "names": "names",
            "default": "default",
            "hidden": "hidden",
            "userData": "userData",
        },
        templates=templates,
        reuse_native_templates=reuse_native_templates,
    )


def _apply_font_record_roots(
    font: Any,
    current: Mapping[str, Any],
    target: Mapping[str, Any],
    *,
    native_templates: Mapping[tuple[str, ...], Any],
    reuse_native_templates: bool,
) -> None:
    for root, attribute, kind in (
        ("metrics", "metrics", "metric"),
        ("stems", "stems", "stem"),
        ("numbers", "numbers", "number"),
    ):
        if current.get(root) == target.get(root):
            continue
        _apply_ordered_record_collection(
            font,
            attribute,
            current.get(root, []),
            target.get(root, []),
            kind=kind,
            fields={
                "name": "name",
                "type": "type",
                "horizontal": "horizontal",
                "filter": "filter",
            },
            templates=_native_templates_for_root(native_templates, root),
            reuse_native_templates=reuse_native_templates,
        )


def _apply_owned_metadata(
    owner: Any,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> None:
    if before.get("customParameters") != after.get("customParameters"):
        native_records = _custom_parameter_models(owner)
        if native_records != list(after.get("customParameters", [])):
            # Parent setters and detached replay templates may eagerly
            # materialize the exact registered child collection. Accept that
            # convergence; a third state still reaches the strict collection
            # precondition below and fails closed.
            replay_before = (
                native_records
                # A newly constructed parent has no canonical before-entity.
                # Its SDK-provided child defaults are adapter state, so replay
                # starts from the observed native collection. Retained owners
                # keep the strict captured-before precondition.
                if not before
                else before.get("customParameters", [])
            )
            _apply_ordered_record_collection(
                owner,
                "customParameters",
                replay_before,
                after.get("customParameters", []),
                kind="customParameter",
                fields={"name": "name", "value": "value", "disabled": "disabled"},
            )
    if before.get("properties") != after.get("properties"):
        _apply_property_collection(
            owner,
            before.get("properties", []),
            after.get("properties", []),
            owner_is_new=not bool(before),
        )
    if before.get("userData") != after.get("userData"):
        _set_native_property(owner, "userData", copy.deepcopy(after.get("userData")))


def _apply_instance_collection(
    font: Any,
    current: Sequence[Mapping[str, Any]],
    target: Sequence[Mapping[str, Any]],
    *,
    templates: Mapping[str, Any] | None = None,
    reuse_native_templates: bool = False,
) -> None:
    collection = _safe_getattr(font, "instances")
    native_by_id = _sync_native_entities(
        collection,
        current,
        target,
        kind="instance",
        templates=templates,
        reuse_native_templates=reuse_native_templates,
    )
    _, current_entities = require_indexed_entities(current, "instances")
    target_order, target_entities = require_indexed_entities(target, "instances")
    exact_additions = _exact_native_template_additions(
        current_entities,
        target_entities,
        templates,
        reuse_native_templates=reuse_native_templates,
    )
    try:
        from GlyphsApp import INSTANCETYPEVARIABLE  # type: ignore[import-not-found]
    except Exception:
        INSTANCETYPEVARIABLE = 1
    for identity in target_order:
        native = native_by_id[identity]
        after = target_entities[identity]
        before = (
            after
            if identity in exact_additions
            else current_entities.get(identity, {})
        )
        # ``GSInstance.name`` is the host's convenience setter for the
        # official ``properties/styleNames`` record. Apply it first; the
        # shared metadata path then verifies convergence or atomically
        # replaces the complete registered property collection.
        if before.get("name") != after.get("name"):
            _set_native_property(native, "name", str(after.get("name") or ""))
        _apply_owned_metadata(native, before, after)
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
        for field in (
            "exports",
            "visible",
            "isBold",
            "isItalic",
            "linkStyle",
            "manualInterpolation",
            "weightClass",
            "widthClass",
            "instanceInterpolations",
        ):
            if before.get(field) != after.get(field):
                native_name = "exports" if field == "exports" else field
                _set_native_property(
                    native, native_name, copy.deepcopy(after.get(field))
                )


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


def _remove_glyph_layer(glyph: Any, layer_id: str, layer: Any) -> None:
    """Remove a layer by stable identity across Glyphs proxy variants."""

    layers = _safe_getattr(glyph, "layers")
    try:
        del layers[layer_id]
        return
    except Exception:
        pass
    remover = _safe_getattr(layers, "removeObjectForKey_")
    if callable(remover):
        remover(layer_id)
        return
    setter = _safe_getattr(glyph, "setLayer_forId_")
    if callable(setter):
        setter(None, layer_id)
        return
    values = _native_layers(glyph)
    try:
        index = values.index(layer)
    except ValueError as exc:
        raise HostAccessError("Glyphs layer identity is missing") from exc
    _remove_native_collection_item(layers, index, layer)


def _canonical_layer_collection(
    glyph: Mapping[str, Any],
) -> tuple[list[str], dict[str, Mapping[str, Any]]]:
    layers = glyph.get("layers", ())
    if isinstance(layers, Mapping):
        layers = [
            {
                "id": str(key),
                "masterId": str(value.get("masterId") or key),
                **dict(value),
            }
            for key, value in layers.items()
            if isinstance(value, Mapping)
        ]
    return require_indexed_entities(layers, "glyph layers")


def _set_mapping_value(mapping: Any, key: str, value: Any) -> None:
    try:
        mapping[key] = value
        return
    except Exception:
        setter = _safe_getattr(mapping, "setObject_forKey_")
        if callable(setter):
            setter(value, key)
            return
    raise HostAccessError("Glyphs could not update layer attribute {}".format(key))


def _remove_mapping_value(mapping: Any, key: str) -> None:
    if _mapping_get(mapping, key) is None:
        return
    try:
        del mapping[key]
        return
    except Exception:
        remover = _safe_getattr(mapping, "removeObjectForKey_")
        if callable(remover):
            remover(key)
            return
    raise HostAccessError("Glyphs could not remove layer attribute {}".format(key))


def _replace_mapping_values(
    mapping: Any,
    target: Mapping[str, Any],
    *,
    preserve: Sequence[str] = (),
) -> None:
    preserved = {str(key) for key in preserve}
    current_keys = {str(key) for key in _mapping_keys(mapping)}
    target_keys = {str(key) for key in target}
    for key in sorted(current_keys - target_keys - preserved):
        _remove_mapping_value(mapping, key)
    for key in sorted(target_keys):
        value = copy.deepcopy(target[key])
        if _plain_attribute_value(_mapping_get(mapping, key)) != value:
            _set_mapping_value(mapping, key, value)


def _axis_ids_by_tag(font: Any) -> dict[str, str]:
    return {tag: native_id for native_id, tag in _axis_tag_by_native_id(font).items()}


def _set_layer_interpolation(
    font: Any,
    layer: Any,
    interpolation: Mapping[str, Any] | None,
) -> None:
    attributes = _safe_getattr(layer, "attributes")
    if attributes is None:
        attributes = {}
        _set_native_property(layer, "attributes", attributes)
    _remove_mapping_value(attributes, "coordinates")
    _remove_mapping_value(attributes, "axisRules")
    if interpolation is None:
        return
    axis_ids = _axis_ids_by_tag(font)
    kind = str(interpolation.get("kind") or "")
    if kind == "intermediate":
        coordinates = interpolation.get("coordinates", {})
        _set_mapping_value(
            attributes,
            "coordinates",
            {
                axis_ids[str(tag)]: value
                for tag, value in dict(coordinates).items()
                if str(tag) in axis_ids
            },
        )
        return
    if kind == "alternate":
        ranges = interpolation.get("ranges", {})
        _set_mapping_value(
            attributes,
            "axisRules",
            {
                axis_ids[str(tag)]: {
                    key: value
                    for key, value in dict(rule).items()
                    if value is not None
                }
                for tag, rule in dict(ranges).items()
                if str(tag) in axis_ids and isinstance(rule, Mapping)
            },
        )
        return
    raise HostAccessError("canonical layer interpolation kind is unsupported")


def _apply_layer_collection(
    font: Any,
    glyph: Any,
    glyph_name: str,
    current: Mapping[str, Any],
    target: Mapping[str, Any],
    *,
    execution_context: Mapping[str, Any] | None = None,
    restore_templates: Mapping[str, Any] | None = None,
    reuse_native_templates: bool = False,
    replacement_roots: Sequence[Sequence[str]] = (),
    excluded_ids: Sequence[str] = (),
    allow_master_membership_change: bool = False,
    affected_ids: Sequence[str] | None = None,
) -> None:
    """Synchronize one ordered layer collection through native identity."""

    current_order, current_entities = _canonical_layer_collection(current)
    target_order, target_entities = _canonical_layer_collection(target)
    excluded = {str(identity) for identity in excluded_ids}
    affected = (
        None
        if affected_ids is None
        else {str(identity) for identity in affected_ids}
    )
    collection = _safe_getattr(glyph, "layers")
    native_values = _native_layers(glyph)
    native_by_id = {
        str(_safe_getattr(layer, "layerId") or _safe_getattr(layer, "id") or ""): layer
        for layer in native_values
        if str(_safe_getattr(layer, "layerId") or _safe_getattr(layer, "id") or "")
    }
    if set(native_by_id) != set(current_order) and len(native_values) == len(
        current_order
    ):
        # Sparse adapter unit fixtures predate stable layer IDs. The real
        # schema-v5 host never enters this branch because capture rejects an
        # empty identity before mutation.
        native_by_id = {
            identity: native_values[index]
            for index, identity in enumerate(current_order)
        }
    expected_native_ids = (set(current_order) - excluded) | (
        set(target_order) & excluded
    )
    if set(native_by_id) != expected_native_ids:
        native_ids = sorted(native_by_id)
        expected_ids = sorted(expected_native_ids)
        raise HostAccessError(
            "Glyphs layer collection diverged before mutation for {!r}: "
            "native={} {!r}; expected={} {!r}".format(
                glyph_name,
                len(native_ids),
                native_ids[:12],
                len(expected_ids),
                expected_ids[:12],
            )
        )
    context = dict(execution_context or {})
    source_map = {
        str(key): str(value)
        for key, value in dict(context.get("layerSources") or {}).items()
    }
    templates = dict(restore_templates or {})
    exact_additions = _exact_native_template_additions(
        current_entities,
        target_entities,
        templates,
        reuse_native_templates=reuse_native_templates,
    )

    for identity in target_order:
        if identity in native_by_id or identity in excluded:
            continue
        key = "{}/{}".format(glyph_name, identity)
        template = templates.get(key)
        reuse = bool(reuse_native_templates and template is not None)
        source_id = source_map.get(key)
        source = template if template is not None else native_by_id.get(source_id or "")
        if source is None:
            raise HostAccessError(
                "layer creation requires a verified native copy source for {}".format(key)
            )
        layer = source if reuse else _copy_native_object(source, kind="layer")
        after = target_entities[identity]
        if identity not in exact_additions:
            _set_native_scalar_if_changed(layer, "layerId", identity)
            _set_native_scalar_if_changed(
                layer, "associatedMasterId", str(after.get("masterId") or "")
            )
            _set_native_scalar_if_changed(
                layer, "name", str(after.get("name") or "")
            )
            _set_layer_interpolation(font, layer, after.get("interpolation"))
        # Native append is the archive-equivalent attachment boundary for a
        # new non-master layer. Deletion deliberately does not use its exact-ID
        # inverse below because Glyphs' undo machinery can reinsert a removed
        # object under a fresh identity; the complete assignment handles that.
        _append_native_collection_item(collection, layer)
        native_by_id[identity] = layer

    for identity in reversed(current_order):
        if identity in target_entities or identity in excluded:
            continue
        native_by_id.pop(identity)

    native_order = [
        identity
        for identity in (
            str(
                _safe_getattr(layer, "layerId")
                or _safe_getattr(layer, "id")
                or ""
            )
            for layer in _native_layers(glyph)
        )
        if identity
    ]
    canonical_collection_changed = current_order != target_order
    current_master_ids = {
        identity
        for identity in current_order
        if bool(current_entities[identity].get("isMasterLayer"))
    }
    target_master_ids = {
        identity
        for identity in target_order
        if bool(target_entities[identity].get("isMasterLayer"))
    }
    if (
        canonical_collection_changed
        and not allow_master_membership_change
        and current_master_ids != target_master_ids
    ):
        raise HostAccessError(
            "layer lifecycle cannot change master-layer membership"
        )
    if not canonical_collection_changed:
        # A scalar/entity-field replay does not own collection order. Glyphs
        # projects the master prefix from the root master collection, and that
        # host order may legitimately differ from the canonical source's
        # presentation order. Preserve it unless the semantic patch contains
        # an actual membership/order transition.
        complete_order = [
            identity for identity in native_order if identity in native_by_id
        ]
    else:
        # The root master collection owns the master-layer prefix. Glyphs may
        # project a different prefix order from the canonical reference both
        # during ordinary layer lifecycle and immediately after a master is
        # attached. Forcing that nested prefix back creates an impossible
        # fixed point. Keep the host-derived prefix while canonical layer
        # lifecycle owns only the independently orderable non-master suffix.
        host_master_order = [
            identity
            for identity in native_order
            if identity in target_entities
            and bool(target_entities[identity].get("isMasterLayer"))
        ]
        target_non_master_order = [
            identity
            for identity in target_order
            if identity in native_by_id
            and not bool(target_entities[identity].get("isMasterLayer"))
        ]
        complete_order = host_master_order + target_non_master_order
    if set(complete_order) != set(native_by_id):
        raise HostAccessError("canonical layer order omitted a native identity")
    if native_order != complete_order:
        _replace_glyph_layer_collection(
            glyph,
            [native_by_id[identity] for identity in complete_order],
            allow_master_membership_change=allow_master_membership_change,
        )

    for identity in target_order:
        if identity in excluded:
            continue
        if affected is not None and identity not in affected:
            continue
        native = native_by_id[identity]
        after = target_entities[identity]
        before = (
            after
            if identity in exact_additions
            else current_entities.get(identity, {})
        )
        _set_native_scalar_if_changed(native, "layerId", identity)
        _set_native_scalar_if_changed(
            native, "associatedMasterId", str(after.get("masterId") or "")
        )
        _set_native_scalar_if_changed(native, "name", str(after.get("name") or ""))
        if before.get("interpolation") != after.get("interpolation"):
            _set_layer_interpolation(font, native, after.get("interpolation"))
        # ``before`` and ``after`` come from the one official canonical source.
        # Re-capturing this layer through the ObjectWrapper projection would
        # introduce a second semantic model (and previously rewrote unrelated
        # anchors/defaults). Apply the proven delta once here; the outer
        # document transaction owns settled, source-consistent fixed-point
        # verification and any bounded reconciliation pass.
        if before != after:
            _apply_layer_canonical_pass(
                native,
                before,
                after,
                layer_root=("glyphs", glyph_name, "layers", identity),
                replacement_roots=replacement_roots,
            )


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
                "bottomMetricsKey",
                "topMetricsKey",
                "vertOriginMetricsKey",
                "vertWidthMetricsKey",
            )
        )
        for scalar in (
            "leftMetricsKey",
            "rightMetricsKey",
            "widthMetricsKey",
            "bottomMetricsKey",
            "topMetricsKey",
            "vertOriginMetricsKey",
            "vertWidthMetricsKey",
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
        for scalar in set(_LAYER_SCALARS) - {
            "width",
            "vertOrigin",
            "vertWidth",
            "leftMetricsKey",
            "rightMetricsKey",
            "widthMetricsKey",
            "bottomMetricsKey",
            "topMetricsKey",
            "vertOriginMetricsKey",
            "vertWidthMetricsKey",
        }:
            if current_layer.get(scalar) != target_layer.get(scalar):
                _set_native_property(layer, scalar, target_layer.get(scalar))
        if current_layer.get("anchors") != target_layer.get("anchors"):
            _replace_anchors(layer, target_layer.get("anchors", []))
        if current_layer.get("attributes") != target_layer.get("attributes"):
            attributes = _safe_getattr(layer, "attributes")
            if attributes is None:
                attributes = {}
                _set_native_property(layer, "attributes", attributes)
            _replace_mapping_values(
                attributes,
                target_layer.get("attributes") or {},
                preserve=("coordinates", "axisRules"),
            )
        for field, kind, aliases in (
            (
                "annotations",
                "annotation",
                {"angle": "angle", "pos": "position", "text": "text", "type": "type", "width": "width"},
            ),
            (
                "guides",
                "guide",
                {
                    "angle": "angle", "attr": "attributes", "filter": "filter",
                    "grid": "grid", "length": "length",
                    "lockAngle": "lockAngle", "locked": "locked", "name": "name",
                    "orientation": "orientation", "pos": "position",
                    "showMeasurement": "showMeasurement", "size": "size", "slope": "slope",
                    "type": "type",
                },
            ),
            (
                "hints",
                "hint",
                {
                    "horizontal": "horizontal", "name": "name", "options": "options",
                    "origin": "origin", "other1": "other1", "other2": "other2", "place": "place",
                    "scale": "scale", "settings": "settings", "stem": "stem", "target": "target",
                    "type": "type",
                },
            ),
        ):
            if current_layer.get(field) != target_layer.get(field):
                _apply_ordered_record_collection(
                    layer,
                    field,
                    current_layer.get(field, []),
                    target_layer.get(field, []),
                    kind=kind,
                    fields=aliases,
                )
        for field in ("partSelection", "userData"):
            if current_layer.get(field) != target_layer.get(field):
                _set_native_property(
                    layer, field, copy.deepcopy(target_layer.get(field))
                )
        if current_layer.get("backgroundImage") != target_layer.get("backgroundImage"):
            image = target_layer.get("backgroundImage")
            _set_native_property(
                layer,
                "backgroundImage",
                _new_image(
                    image,
                    document_path=_document_path_for_native(layer),
                )
                if isinstance(image, Mapping)
                else None,
            )
        if current_layer.get("background") != target_layer.get("background"):
            background = _safe_getattr(layer, "background")
            if background is None:
                raise HostAccessError("Glyphs did not expose the layer background")
            _apply_background_canonical_pass(
                background,
                current_layer.get("background"),
                target_layer.get("background"),
                layer_root=tuple(layer_root) + ("background",),
                replacement_roots=replacement_roots,
            )
        current_shapes = canonical_layer_shapes(current_layer)
        target_shapes = canonical_layer_shapes(target_layer)
        if current_shapes != target_shapes:
            collection_root = tuple(layer_root) + ("shapes",)
            if collection_root in replacement_set or not _update_shapes_in_place(
                layer, current_shapes, target_shapes
            ):
                _replace_shapes(layer, target_shapes)
        # Advance/origin metrics are stable last: bearings and absolute outline
        # replay can invalidate an earlier assignment on either axis.
        if current_layer.get("vertOrigin") != target_layer.get("vertOrigin"):
            _set_native_property(layer, "vertOrigin", target_layer.get("vertOrigin"))
        if current_layer.get("vertWidth") != target_layer.get("vertWidth"):
            _set_native_property(layer, "vertWidth", target_layer.get("vertWidth"))
        if current_layer.get("width") != target_layer.get("width"):
            _set_native_property(layer, "width", target_layer.get("width"))
    finally:
        if callable(end):
            end()


def _apply_background_canonical_pass(
    background: Any,
    current: Any,
    target: Any,
    *,
    layer_root: Sequence[str],
    replacement_roots: Sequence[Sequence[str]],
) -> None:
    before = current if isinstance(current, Mapping) else {
        "anchors": [], "annotations": [], "backgroundImage": None,
        "guides": [], "hints": [], "shapes": [],
    }
    after = target if isinstance(target, Mapping) else {
        "anchors": [], "annotations": [], "backgroundImage": None,
        "guides": [], "hints": [], "shapes": [],
    }
    synthetic_before = {
        **before,
        **{name: None for name in _LAYER_SCALARS},
        "attributes": {}, "background": None, "partSelection": None,
        "userData": {},
    }
    synthetic_after = {
        **after,
        **{name: None for name in _LAYER_SCALARS},
        "attributes": {}, "background": None, "partSelection": None,
        "userData": {},
    }
    _apply_layer_canonical_pass(
        background,
        synthetic_before,
        synthetic_after,
        layer_root=layer_root,
        replacement_roots=replacement_roots,
    )


def _reconcile_layer_to_canonical_target(
    layer: Any,
    current_layer: Mapping[str, Any],
    target_layer: Mapping[str, Any],
    *,
    layer_root: Sequence[str],
    replacement_roots: Sequence[Sequence[str]] = (),
    axis_tags: Optional[Mapping[str, str]] = None,
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
        updated = _layer_model(layer, axis_tags=axis_tags)
        if updated == state:
            return
        state = updated


def _apply_master_store_models(
    font: Any,
    master: Any,
    attribute: str,
    target_values: Sequence[Mapping[str, Any]],
) -> None:
    """Replay one ID-addressed Glyphs master value store.

    The file format writes these stores as arrays, while Glyphs exposes
    dictionaries keyed by private root-definition IDs. Capture and replay use
    the same adapter-local binding so dictionary enumeration order can never
    change canonical identity or assign a value to the wrong definition.
    """

    root = {
        "metricValues": "metrics",
        "stemValues": "stems",
        "numberValues": "numbers",
    }[attribute]
    bindings = _metric_definition_bindings(font, root)
    by_canonical_id = {
        str(definition.get("id") or ""): (index, native_id)
        for index, (native_id, definition) in enumerate(bindings)
    }
    target_by_id = {
        str(value.get("id") or ""): value for value in target_values
    }
    if len(target_by_id) != len(target_values) or not set(target_by_id).issubset(
        by_canonical_id
    ):
        raise HostAccessError(
            "{} values do not match their canonical root definitions".format(
                attribute
            )
        )
    store = _safe_getattr(master, attribute)
    for canonical_id, target in target_by_id.items():
        index, native_id = by_canonical_id[canonical_id]
        native_value = _native_store_value(store, native_id, index)
        if native_value is _MISSING_STORE_VALUE:
            raise HostAccessError(
                "{} is missing native value {}".format(attribute, canonical_id)
            )
        if attribute == "metricValues":
            _set_native_scalar_if_changed(
                native_value, "position", target.get("pos", 0)
            )
            _set_native_scalar_if_changed(
                native_value, "overshoot", target.get("over", 0)
            )
            continue
        scalar = target.get("value", 0)
        setter_name = {
            "stemValues": "setStemValueValue_forId_",
            "numberValues": "setNumberValueValue_forId_",
        }[attribute]
        setter = _safe_getattr(master, setter_name)
        current = _maybe_call(_safe_getattr(native_value, "value"))
        if current == scalar:
            continue
        if callable(setter):
            setter(scalar, native_id)
        else:
            _set_native_scalar_if_changed(native_value, "value", scalar)


def _apply_master_collection(
    font: Any,
    current: Sequence[Mapping[str, Any]],
    target: Sequence[Mapping[str, Any]],
    *,
    execution_context: Mapping[str, Any] | None = None,
    restore_templates: Mapping[str, Mapping[str, Any]] | None = None,
    reuse_native_templates: bool = False,
) -> None:
    """Replay master membership/order while preserving native-only state."""

    current_order, current_entities = require_indexed_entities(current, "masters")
    target_order, target_entities = require_indexed_entities(target, "masters")
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
    template_evidence_ids: set[str] = set()
    glyphs = {
        str(_safe_getattr(glyph, "name") or ""): glyph
        for glyph in _sequence_values(_safe_getattr(font, "glyphs"))
        if str(_safe_getattr(glyph, "name") or "")
    }

    # Additions happen before removals so one batch may duplicate a source and
    # then delete it without losing the native copy source.
    for identity in target_order:
        if identity in native_by_id:
            continue
        template = templates.get(identity)
        template_master = None
        template_layers: Mapping[str, Any] = {}
        if isinstance(template, Mapping):
            template_master = template.get(
                "nativeMaster" if reuse_native_templates else "master"
            )
            if template_master is None:
                # The generic path-keyed tombstone store has already selected
                # either its detached copy or exact native payload. Its
                # composite master evidence therefore uses the neutral
                # ``master``/``layers`` keys, while the legacy compatibility
                # view retains ``nativeMaster``/``nativeLayers``.
                template_master = template.get("master")
            template_layers = template.get(
                "nativeLayers" if reuse_native_templates else "layers"
            )
            if template_layers is None:
                template_layers = template.get("layers", {})
            if not isinstance(template_layers, Mapping):
                template_layers = {}
        reuse_template = bool(
            reuse_native_templates
            and template_master is not None
        )
        source_id = source_map.get(identity)
        source_master = (
            template_master
            if template_master is not None
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
        if template_master is not None:
            template_evidence_ids.add(identity)
        _set_native_scalar_if_changed(master, "id", identity)
        _append_native_collection_item(collection, master)
        native_by_id[identity] = master

        stored_layers = template_layers
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
            # A master layer's displayed name is derived from its associated
            # master. Persisting the same text on GSLayer creates a redundant
            # native ``name`` field and makes replay differ from a native
            # master duplication. Attachment below establishes the derived
            # value; special-layer names remain owned by layer lifecycle.
            _set_glyph_master_layer(glyph, identity, copied_layer)

    removed_master_ids = [
        identity for identity in current_order if identity not in target_entities
    ]
    # Master layers are owned by the master collection. Glyphs removes them as
    # one native lifecycle cascade when their master is deleted. Removing the
    # layers first is both redundant and incorrect: while the master still
    # exists Glyphs recreates its required layer membership. Keep that
    # ownership boundary in one place and let complete read-back verification
    # prove the resulting nested collection state.
    for identity in reversed(removed_master_ids):
        value = native_by_id.pop(identity)
        index = _sequence_values(collection).index(value)
        _remove_native_collection_item(collection, index, value)

    native_master_storage = _maybe_call(_safe_getattr(font, "fontMasters"))
    _replace_native_collection_order(
        collection,
        [native_by_id[identity] for identity in target_order],
        identity_storage=native_master_storage,
        notification_owner=font,
        notification_key="fontMasters",
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
        # Qualified native evidence—either a detached verifier copy or an
        # exact same-process tombstone—already represents the canonical target
        # entity. Its writable baseline is therefore the target. Only an
        # ordinary typed duplicate is based on another live source entity.
        # Replaying evidence from ``{}`` would try to add collections the
        # native template already owns and falsely report divergence.
        before = current_entities.get(identity)
        if before is None:
            before = (
                after
                if identity in template_evidence_ids
                else current_entities.get(source_map.get(identity, ""), {})
            )
        for field in ("active", "visible", "iconName"):
            if before.get(field) != after.get(field):
                _set_native_property(native, field, copy.deepcopy(after.get(field)))
        _apply_owned_metadata(native, before, after)
        if before.get("guides") != after.get("guides"):
            _apply_ordered_record_collection(
                native,
                "guides",
                before.get("guides", []),
                after.get("guides", []),
                kind="guide",
                fields={
                    "angle": "angle", "filter": "filter", "grid": "grid",
                    "attr": "attributes",
                    "length": "length", "lockAngle": "lockAngle", "locked": "locked",
                    "name": "name", "orientation": "orientation", "pos": "position",
                    "showMeasurement": "showMeasurement", "size": "size", "slope": "slope",
                    "type": "type",
                },
            )
        for field in ("metricValues", "stemValues", "numberValues"):
            if before.get(field) == after.get(field):
                continue
            _apply_master_store_models(
                font,
                native,
                field,
                after.get(field, []),
            )

    # Attachment can produce host-derived effects. Do not run a second eager
    # per-layer mutation engine here: the transaction's one settled streaming
    # read-back owns those effects, expands the observed diff, and restores the
    # pre-attempt snapshot atomically if the native result is unsupported.


def _apply_glyph_membership(
    font: Any,
    current: Mapping[str, Mapping[str, Any]],
    target: Mapping[str, Mapping[str, Any]],
    *,
    templates: Mapping[str, Any] | None = None,
    reuse_native_templates: bool = False,
) -> None:
    collection = _safe_getattr(font, "glyphs")
    native_by_name = {
        str(_safe_getattr(value, "name") or ""): value
        for value in _sequence_values(collection)
        if str(_safe_getattr(value, "name") or "")
    }
    if set(native_by_name) != set(current):
        raise HostAccessError("Glyphs glyph collection diverged before mutation")
    available_templates = dict(templates or {})
    for name in sorted(set(current) - set(target), reverse=True):
        value = native_by_name.pop(name)
        try:
            del collection[name]
        except Exception:
            index = _sequence_values(collection).index(value)
            _remove_native_collection_item(collection, index, value)
    for name in sorted(set(target) - set(current)):
        template = available_templates.get(name)
        value = (
            template
            if reuse_native_templates and template is not None
            else _copy_native_object(template, kind="glyph")
            if template is not None
            else _construct_native_entity("glyph", name)
        )
        if str(_safe_getattr(value, "name") or "") != name:
            _set_native_property(value, "name", name)
        _append_native_collection_item(collection, value)
        native_by_name[name] = value


def _apply_glyph_order(font: Any, order: Sequence[str]) -> None:
    collection = _safe_getattr(font, "glyphs")
    native_by_name = {
        str(_safe_getattr(value, "name") or ""): value
        for value in _sequence_values(collection)
        if str(_safe_getattr(value, "name") or "")
    }
    requested = [str(name) for name in order]
    if len(requested) != len(set(requested)) or set(requested) != set(native_by_name):
        raise HostAccessError("canonical glyph order must contain every glyph once")
    _replace_native_collection_order(
        collection,
        [native_by_name[name] for name in requested],
    )


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
        and change.path[4] == "shapes"
    }
    return tuple(sorted(replacements))


def _native_templates_for_root(
    templates: Mapping[tuple[str, ...], Any], root: str
) -> dict[str, Any]:
    return {
        path[1]: value
        for path, value in templates.items()
        if len(path) == 2 and path[0] == root
    }


def _native_layer_templates(
    templates: Mapping[tuple[str, ...], Any]
) -> dict[str, Any]:
    return {
        "{}/{}".format(path[1], path[3]): value
        for path, value in templates.items()
        if len(path) == 4 and path[0] == "glyphs" and path[2] == "layers"
    }


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
    layer_restore_templates: Mapping[str, Any] | None = None,
    reuse_native_master_templates: bool = False,
    reuse_native_layer_templates: bool = False,
) -> None:
    context = dict(execution_context or {})
    raw_templates = context.get("nativeReplayTemplates") or {}
    native_templates = {
        tuple(str(part) for part in path): value
        for path, value in dict(raw_templates).items()
        if isinstance(path, (tuple, list))
    }
    reuse_native_templates = bool(context.get("reuseNativeReplayTemplates"))
    contextual_master_templates = _native_templates_for_root(
        native_templates, "masters"
    )
    contextual_layer_templates = _native_layer_templates(native_templates)
    resolved_master_templates = {
        **contextual_master_templates,
        **dict(master_restore_templates or {}),
    }
    resolved_layer_templates = {
        **contextual_layer_templates,
        **dict(layer_restore_templates or {}),
    }
    replacement_roots = {tuple(str(part) for part in path) for path in replay_replacements}
    changed_roots = {change.path[0] for change in change_set.changes}
    affected_glyph_ids = change_set.affected_identities(("glyphs",))
    current_glyphs = current.get("glyphs", {})
    target_glyphs = target.get("glyphs", {})
    if "glyphs" in changed_roots and (
        not isinstance(current_glyphs, Mapping)
        or not isinstance(target_glyphs, Mapping)
    ):
        raise HostAccessError("canonical glyph collections must be keyed by name")

    # Resolve the parent glyph collection before master-owned layer
    # membership. This is the canonical ownership order in both directions:
    # removed glyphs are detached before Glyphs cascades a master deletion,
    # preserving their exact native tombstones; newly restored glyphs are
    # present when master replay attaches its one owned layer per glyph.
    # Scalar and nested-layer reconciliation remains below, after the master
    # collection has reached its target membership.
    if (
        "glyphs" in changed_roots
        and isinstance(current_glyphs, Mapping)
        and isinstance(target_glyphs, Mapping)
        and set(current_glyphs) != set(target_glyphs)
    ):
        _apply_glyph_membership(
            font,
            current_glyphs,
            target_glyphs,
            templates=_native_templates_for_root(native_templates, "glyphs"),
            reuse_native_templates=reuse_native_templates,
        )

    if "axes" in changed_roots:
        _apply_axis_collection(
            font,
            current.get("axes", []),
            target.get("axes", []),
            templates=_native_templates_for_root(native_templates, "axes"),
            reuse_native_templates=reuse_native_templates,
        )

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
            execution_context=context,
            restore_templates=resolved_master_templates,
            reuse_native_templates=(
                reuse_native_master_templates or reuse_native_templates
            ),
        )
    if "font" in changed_roots:
        font_changes = change_set.changes_under(("font",))
        whole_font = any(len(change.path) == 1 for change in font_changes)
        changed_font_fields = {
            change.path[1] for change in font_changes if len(change.path) > 1
        }
        for name in _FONT_SCALARS:
            if (
                (whole_font or name in changed_font_fields)
                and current.get("font", {}).get(name)
                != target.get("font", {}).get(name)
            ):
                _set_native_property(font, name, target.get("font", {}).get(name))
        if whole_font or changed_font_fields.intersection(
            {"customParameters", "properties", "userData"}
        ):
            _apply_owned_metadata(
                font,
                current.get("font", {}),
                target.get("font", {}),
            )
    if "glyphs" in changed_roots:
        if not isinstance(current_glyphs, Mapping) or not isinstance(
            target_glyphs, Mapping
        ):
            raise HostAccessError("canonical glyph collections must be keyed by name")
        replay_glyph_names = (
            sorted(target_glyphs)
            if affected_glyph_ids is None
            else sorted(
                name for name in affected_glyph_ids if name in target_glyphs
            )
        )
        for name in replay_glyph_names:
            glyph_changes = change_set.changes_under(("glyphs", name))
            whole_glyph = affected_glyph_ids is None or any(
                len(change.path) == 2 for change in glyph_changes
            )
            changed_glyph_fields = {
                change.path[2]
                for change in glyph_changes
                if len(change.path) > 2
            }
            glyph = _lookup_by_name(_safe_getattr(font, "glyphs"), name)
            if glyph is None:
                raise HostAccessError("Glyphs could not resolve glyph {}".format(name))
            current_glyph = current_glyphs.get(name)
            if not isinstance(current_glyph, Mapping):
                # A new glyph can gain host-created master layers when it is
                # inserted into the font. Capture those derived values before
                # applying any explicitly modeled content.
                current_glyph = _glyph_model(
                    glyph,
                    layer_order_reference=target_glyphs.get(name),
                )
            _apply_glyph_scalar_updates(
                glyph,
                current_glyph,
                target_glyphs[name],
                whole_glyph=whole_glyph,
                changed_fields=changed_glyph_fields,
            )
            for field in _GLYPH_DIRECT_METADATA_FIELDS:
                if (
                    field in target_glyphs[name]
                    and (whole_glyph or field in changed_glyph_fields)
                    and current_glyph.get(field) != target_glyphs[name].get(field)
                ):
                    _set_native_property(
                        glyph, field, copy.deepcopy(target_glyphs[name].get(field))
                    )
            if (
                "smartAxes" in target_glyphs[name]
                and (whole_glyph or "smartAxes" in changed_glyph_fields)
                and current_glyph.get("smartAxes")
                != target_glyphs[name].get("smartAxes")
            ):
                _apply_ordered_record_collection(
                    glyph,
                    "smartComponentAxes",
                    current_glyph.get("smartAxes", []),
                    target_glyphs[name].get("smartAxes", []),
                    kind="smartAxis",
                    fields=("name", "bottomValue", "topValue"),
                )
            if not (whole_glyph or "layers" in changed_glyph_fields):
                continue
            affected_layer_ids = (
                None
                if whole_glyph
                else change_set.affected_identities(
                    ("glyphs", name, "layers")
                )
            )
            raw_current_layers = current_glyph.get("layers", {})
            raw_target_layers = target_glyphs[name].get("layers", {})
            if isinstance(raw_current_layers, Mapping) and isinstance(
                raw_target_layers, Mapping
            ):
                # Internal schema-v4 sparse adapter fixtures retain their
                # field-level replay contract. Native schema-v5 capture never
                # emits this representation.
                if set(raw_current_layers) != set(raw_target_layers):
                    raise HostAccessError(
                        "schema-v4 layer membership cannot be replayed"
                    )
                layer_keys = (
                    sorted(raw_target_layers)
                    if affected_layer_ids is None
                    else sorted(
                        layer_id
                        for layer_id in affected_layer_ids
                        if layer_id in raw_target_layers
                    )
                )
                for layer_key in layer_keys:
                    if raw_current_layers[layer_key] == raw_target_layers[layer_key]:
                        continue
                    layer = _lookup_layer(glyph, layer_key)
                    if layer is None:
                        raise HostAccessError(
                            "Glyphs could not resolve layer {}".format(layer_key)
                        )
                    _reconcile_layer_to_canonical_target(
                        layer,
                        raw_current_layers[layer_key],
                        raw_target_layers[layer_key],
                        layer_root=("glyphs", name, "layers", layer_key),
                        replacement_roots=replacement_roots,
                    )
                continue
            current_order, _ = _canonical_layer_collection(current_glyph)
            target_order, _ = _canonical_layer_collection(target_glyphs[name])
            if name not in current_glyphs and not target_order:
                # Glyphs derives master layers for a newly attached glyph.
                continue
            membership_changed = set(current_order) != set(target_order)
            layer_lifecycle = LAYER_LIFECYCLE_CAPABILITY in capabilities
            if membership_changed and not (layer_lifecycle or master_structural_ids):
                raise HostAccessError(
                    "canonical layer collection membership changes require layer lifecycle"
                )
            _apply_layer_collection(
                font,
                glyph,
                name,
                current_glyph,
                target_glyphs[name],
                execution_context=context,
                restore_templates=resolved_layer_templates,
                reuse_native_templates=(
                    reuse_native_layer_templates or reuse_native_templates
                ),
                replacement_roots=replacement_roots,
                excluded_ids=master_structural_ids,
                allow_master_membership_change=bool(master_structural_ids),
                affected_ids=affected_layer_ids,
            )
    # Parent order has its own semantic patch. Nested entity writes must not
    # rewrite the complete collection; the streaming verifier checks order
    # independently and a real order delta is reconciled through this branch.
    if "glyphOrder" in changed_roots:
        _apply_glyph_order(font, target.get("glyphOrder", list(target_glyphs)))
    if "kerning" in changed_roots:
        _replace_kerning(font, target.get("kerning", []))
    if "instances" in changed_roots:
        _apply_instance_collection(
            font,
            current.get("instances", []),
            target.get("instances", []),
            templates=_native_templates_for_root(native_templates, "instances"),
            reuse_native_templates=reuse_native_templates,
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
                templates=_native_templates_for_root(native_templates, root),
                reuse_native_templates=reuse_native_templates,
            )
    if changed_roots.intersection({"metrics", "stems", "numbers"}):
        _apply_font_record_roots(
            font,
            current,
            target,
            native_templates=native_templates,
            reuse_native_templates=reuse_native_templates,
        )
    if "settings" in changed_roots:
        _apply_settings_model(
            font,
            current.get("settings", {}),
            target.get("settings", {}),
        )


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

    created = (
        path.is_dir() and (path / "fontinfo.plist").is_file()
        if path.suffix.lower() == ".glyphspackage"
        else path.is_file()
    )
    if not created:
        raise HostAccessError("Glyphs did not create the requested copy")


_NATIVE_ARCHIVE_UI_SESSION_PATHS = frozenset({"UIState.plist"})


def _serialized_font_archive(font: Any) -> bytes:
    """Serialize complete native evidence as a deterministic package manifest.

    Glyphs' flat writer is disproportionately expensive for large documents.
    Its package writer preserves the same native payload in independently
    addressable root and glyph files, matching the canonical tree's shard
    model while retaining every unsupported/private field for proof.
    """

    with tempfile.TemporaryDirectory(prefix="glyphs-mcp-v2-archive-") as root:
        path = Path(root) / "checkpoint.glyphspackage"
        _save_font_copy(font, path)
        replacements: dict[bytes, bytes] = {}
        for index, instance in enumerate(
            _sequence_values(_safe_getattr(font, "instances"))
        ):
            identifier = str(
                _plain_scalar(_safe_getattr(instance, "id")) or ""
            ).strip()
            if not _UUID_PATTERN.fullmatch(identifier):
                continue
            replacement = "__GLYPHS_MCP_INSTANCE_{:04d}__".format(index).encode(
                "ascii"
            )
            for spelling in (identifier, identifier.upper(), identifier.lower()):
                replacements[spelling.encode("ascii")] = replacement
        files = [
            {
                "path": item.relative_to(path).as_posix(),
                "value": _native_package_file_value(item, replacements),
            }
            for item in sorted(
                (
                    candidate
                    for candidate in path.rglob("*")
                    if candidate.is_file()
                    and candidate.relative_to(path).as_posix()
                    not in _NATIVE_ARCHIVE_UI_SESSION_PATHS
                ),
                key=lambda candidate: candidate.relative_to(path).as_posix(),
            )
        ]
        archive = json.dumps(
            {"format": "glyphspackage-v1", "files": files},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    return archive


def _native_package_file_value(
    path: Path, replacements: Mapping[bytes, bytes] | None = None
) -> Any:
    """Capture one package file without reparsing it through Glyphs/Cocoa.

    JSON is decoded for deterministic synthetic fixtures. Glyphs' production
    package files use OpenStep syntax; their exact bytes are the authoritative
    private-state evidence. Canonical state supplies field-level semantics,
    while native mismatches remain attributable to a stable package path.
    """

    data = path.read_bytes()
    if replacements:
        data = _ARCHIVE_UUID_BYTES.sub(
            lambda match: replacements.get(match.group(0), match.group(0)), data
        )
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return {"$data": base64.b64encode(data).decode("ascii")}


def _serialized_review_scope(
    font: Any, request: PythonExecutionRequest
) -> bytes:
    """Archive one clone-stable native scope for staged replay proof.

    NSKeyedArchiver output for an isolated glyph is not stable across two
    independent ``GSFont.copy()`` clones, even before either clone is changed.
    Comparing those archives therefore creates false native mismatches. The
    normalized serialized font archive is the smallest proven clone-stable
    evidence boundary. Staged context validation still constrains which
    objects Python may address; archive proof deliberately verifies more than
    that declared context so an unexpected native side effect cannot hide.
    """

    del request
    return _serialized_font_archive(font)


def _native_archive_fingerprint(archive: bytes) -> str:
    tree = _decoded_native_archive_tree(archive)
    if tree is not None:
        archive = json.dumps(
            _normalized_native_archive_tree(tree),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    digest = hashlib.sha256(archive).hexdigest()
    return "sha256:{}".format(digest)


def _serialized_font_fingerprint(font: Any) -> str:
    return _native_archive_fingerprint(_serialized_font_archive(font))


def _archive_delta(before: bytes, after: bytes) -> list[dict[str, Any]]:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    result: list[dict[str, Any]] = []
    # Glyph archives contain thousands of repeated structural lines. Disabling
    # SequenceMatcher's popular-line index makes a one-line insertion
    # quadratic on a production font. The heuristic cannot hide a difference:
    # opcodes still cover both complete sequences and every changed block is
    # hashed below. It only chooses anchors efficiently.
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=True)
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


_NATIVE_ARCHIVE_MISSING = object()


def _bounded_native_archive_value(value: Any) -> Any:
    """Return one bounded diagnostic value without exposing a native subtree."""

    if value is _NATIVE_ARCHIVE_MISSING:
        return {"missing": True}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 160 else value[:157] + "..."
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "type": "array" if isinstance(value, list) else "object",
        "size": len(value),
        "hash": hashlib.sha256(encoded).hexdigest(),
    }


def _decoded_native_package_data(value: Any) -> Any | None:
    """Decode one exact package byte wrapper for diagnostics only.

    Native archive equivalence remains strict except for registry-reviewed
    omission defaults. Decoding the OpenStep payload attributes a refusal to
    the field that differs and lets that one schema rule operate without
    weakening unknown/private fields.
    """

    if not isinstance(value, Mapping) or set(value) != {"$data"}:
        return None
    encoded = value.get("$data")
    if not isinstance(encoded, str):
        return None
    try:
        data = base64.b64decode(encoded, validate=True)
        text = data.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        from openstep_plist import loads as loads_openstep  # type: ignore[import-not-found]

        return loads_openstep(text, use_numbers=True)
    except Exception:
        return None


def _native_archive_tree_mismatches(
    direct: Any,
    replay: Any,
    *,
    limit: int,
    align_identity_collections: bool = True,
) -> tuple[list[dict[str, Any]], bool]:
    """Locate native proof differences by semantic plist path.

    Serialized Glyphs archives are canonical JSON trees at this boundary.
    Walking those trees makes a private-state refusal actionable without
    retaining or returning the complete native payload. Traversal stops after
    one item beyond the public bound; callers still know the result truncated.
    """

    maximum = max(0, min(100, int(limit)))
    found: list[dict[str, Any]] = []

    def record(path: tuple[str | int, ...], left: Any, right: Any) -> None:
        if len(found) > maximum:
            return
        found.append(
            {
                "path": list(path),
                "direct": _bounded_native_archive_value(left),
                "replay": _bounded_native_archive_value(right),
            }
        )

    def walk(path: tuple[str | int, ...], left: Any, right: Any) -> None:
        if len(found) > maximum or left == right:
            return
        if (left is _NATIVE_ARCHIVE_MISSING) != (
            right is _NATIVE_ARCHIVE_MISSING
        ):
            present = right if left is _NATIVE_ARCHIVE_MISSING else left
            has_default, default = CANONICAL_SCHEMA.serialized_default_for_archive_path(
                path
            )
            if has_default and present == default:
                return
        if isinstance(left, Mapping) and isinstance(right, Mapping):
            decoded_left = _decoded_native_package_data(left)
            decoded_right = _decoded_native_package_data(right)
            if decoded_left is not None and decoded_right is not None:
                if decoded_left == decoded_right:
                    # The semantic tree is byte-for-byte identical after
                    # parsing, so this is only an unexplained storage spelling
                    # difference and remains strict.
                    record(
                        path + ("$data",),
                        left.get("$data"),
                        right.get("$data"),
                    )
                    return
                walk(path + ("$decoded",), decoded_left, decoded_right)
                # A changed decoded tree may converge only through explicit
                # registry-owned omission defaults encountered by ``walk``.
                # Unknown fields and equal decoded trees never reach this
                # zero-mismatch case.
                return
            for key in sorted(set(left) | set(right), key=str):
                if len(found) > maximum:
                    return
                walk(
                    path + (str(key),),
                    left.get(key, _NATIVE_ARCHIVE_MISSING),
                    right.get(key, _NATIVE_ARCHIVE_MISSING),
                )
            return
        if isinstance(left, list) and isinstance(right, list):
            identity_key = _native_archive_collection_identity(left, right)
            if path == ("files",) and identity_key is None:
                identity_key = _native_archive_shared_identity(left, right, "path")
            if identity_key is not None:
                if not align_identity_collections:
                    found.append(
                        {
                            "path": list(path),
                            "identityKey": identity_key,
                            "directOrder": [
                                str(item[identity_key]) for item in left[:20]
                            ],
                            "replayOrder": [
                                str(item[identity_key]) for item in right[:20]
                            ],
                            "orderTruncated": len(left) > 20,
                        }
                    )
                    return
                left_by_identity = {
                    str(item[identity_key]): item for item in left
                }
                right_by_identity = {
                    str(item[identity_key]): item for item in right
                }
                for identity in sorted(left_by_identity):
                    if len(found) > maximum:
                        return
                    walk(
                        path + ("@{}={}".format(identity_key, identity),),
                        left_by_identity[identity],
                        right_by_identity[identity],
                    )
                return
            for index in range(max(len(left), len(right))):
                if len(found) > maximum:
                    return
                walk(
                    path + (index,),
                    left[index] if index < len(left) else _NATIVE_ARCHIVE_MISSING,
                    right[index] if index < len(right) else _NATIVE_ARCHIVE_MISSING,
                )
            return
        record(path, left, right)

    walk((), direct, replay)
    return found[:maximum], len(found) > maximum


def _native_archive_shared_identity(
    direct: list[Any], replay: list[Any], key: str
) -> str | None:
    """Return ``key`` when two arrays contain the same unique identities."""

    if len(direct) != len(replay) or not direct:
        return None
    if not all(isinstance(item, Mapping) for item in direct + replay):
        return None
    if not all(key in item and str(item[key]) for item in direct + replay):
        return None
    direct_ids = [str(item[key]) for item in direct]
    replay_ids = [str(item[key]) for item in replay]
    if len(set(direct_ids)) != len(direct_ids):
        return None
    if len(set(replay_ids)) != len(replay_ids):
        return None
    return key if set(direct_ids) == set(replay_ids) else None


def _native_archive_collection_identity(
    direct: list[Any], replay: list[Any]
) -> str | None:
    """Return a shared unique identity key only when list order diverges.

    Canonical schema v5 already verifies meaningful collection order. Native
    archive proof therefore aligns the same identity-addressed entities before
    checking private fields, while positional arrays (paths, nodes, coordinate
    tuples) remain strictly ordered.
    """

    if len(direct) != len(replay) or not direct:
        return None
    if not all(isinstance(item, Mapping) for item in direct + replay):
        return None
    for key in ("path", "glyphname", "layerId", "id", "name"):
        if not all(key in item and str(item[key]) for item in direct + replay):
            continue
        direct_ids = [str(item[key]) for item in direct]
        replay_ids = [str(item[key]) for item in replay]
        if direct_ids == replay_ids:
            return None
        if (
            len(set(direct_ids)) == len(direct_ids)
            and len(set(replay_ids)) == len(replay_ids)
            and set(direct_ids) == set(replay_ids)
        ):
            return key
    return None


def _native_archive_identity_key(values: list[Any]) -> str | None:
    """Return a unique native identity key for one unordered archive array."""

    if not values or not all(isinstance(item, Mapping) for item in values):
        return None
    for key in ("path", "glyphname", "layerId", "id", "name"):
        if not all(key in item and str(item[key]) for item in values):
            continue
        identities = [str(item[key]) for item in values]
        if len(set(identities)) == len(identities):
            return key
    return None


def _archive_tree_without_registered_defaults(
    value: Any,
    path: tuple[str | int, ...] = (),
) -> tuple[Any, bool]:
    """Omit only official defaults registered for exact archive proof.

    OpenStep package payloads remain byte-authoritative unless removing a
    reviewed omission default actually changes their decoded semantic tree.
    Thus formatting-only archive differences stay visible while an explicit
    public default converges with the official omitted spelling.
    """

    if isinstance(value, Mapping):
        decoded = _decoded_native_package_data(value)
        if decoded is not None:
            normalized, changed = _archive_tree_without_registered_defaults(
                decoded, path + ("$decoded",)
            )
            return ({"$decoded": normalized}, True) if changed else (value, False)
        result = {}
        changed = False
        for key, child in value.items():
            child_path = path + (str(key),)
            has_default, default = CANONICAL_SCHEMA.serialized_default_for_archive_path(
                child_path
            )
            if has_default and child == default:
                changed = True
                continue
            normalized, child_changed = _archive_tree_without_registered_defaults(
                child, child_path
            )
            result[str(key)] = normalized
            changed = changed or child_changed
        return result, changed
    if isinstance(value, list):
        result = []
        changed = False
        for index, child in enumerate(value):
            normalized, child_changed = _archive_tree_without_registered_defaults(
                child, path + (index,)
            )
            result.append(normalized)
            changed = changed or child_changed
        return result, changed
    return value, False


def _normalized_native_archive_storage_order(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalized_native_archive_storage_order(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list):
        normalized = [
            _normalized_native_archive_storage_order(child) for child in value
        ]
        identity_key = _native_archive_identity_key(normalized)
        if identity_key is not None:
            return sorted(normalized, key=lambda item: str(item[identity_key]))
        return normalized
    return value


def _normalized_native_archive_tree(value: Any) -> Any:
    """Normalize reviewed defaults and storage order proven by canonical IDs.

    Native package storage may reorder identity-addressed entities after an
    exact detach/reattach even though schema-v5 authoritative order is
    unchanged. Fingerprinting sorts only arrays whose members all expose one
    unique stable identity. Positional arrays such as paths, nodes,
    coordinates, and transforms remain order-sensitive.
    """

    without_defaults, _ = _archive_tree_without_registered_defaults(value)
    return _normalized_native_archive_storage_order(without_defaults)


def _decoded_native_archive_tree(archive: bytes) -> Any | None:
    try:
        return json.loads(archive.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


_ARCHIVE_UUID_BYTES = re.compile(
    rb"(?<![0-9A-Fa-f])[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[1-5][0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}(?![0-9A-Fa-f])"
)


def _normalize_independent_clone_archives(
    direct_before: bytes,
    direct_after: bytes,
    replay_before: bytes,
    replay_after: bytes,
) -> tuple[bytes, bytes, bytes, bytes, int]:
    """Normalize only UUID values proven volatile by untouched clone baselines.

    The two before archives are independent ``GSFont.copy()`` results of the
    same live font. UUIDs that differ at the same serialized occurrence are
    therefore clone-local native evidence, not document state. Build a
    review-local isomorphism from those untouched baselines and apply it to
    both before/after lineages. A value introduced or changed by either
    mutation is absent from the baseline map and remains visible to proof.
    """

    direct_values = _ARCHIVE_UUID_BYTES.findall(direct_before)
    replay_values = _ARCHIVE_UUID_BYTES.findall(replay_before)
    if len(direct_values) != len(replay_values):
        return (
            direct_before,
            direct_after,
            replay_before,
            replay_after,
            0,
        )
    direct_map: dict[bytes, bytes] = {}
    replay_map: dict[bytes, bytes] = {}
    for index, (direct_value, replay_value) in enumerate(
        zip(direct_values, replay_values)
    ):
        if direct_value == replay_value:
            continue
        existing_direct = direct_map.get(direct_value)
        existing_replay = replay_map.get(replay_value)
        if existing_direct is not None or existing_replay is not None:
            if existing_direct is None or existing_direct != existing_replay:
                return direct_before, direct_after, replay_before, replay_after, 0
            continue
        placeholder = "__GLYPHS_MCP_CLONE_UUID_{:06d}__".format(index).encode("ascii")
        direct_map[direct_value] = placeholder
        replay_map[replay_value] = placeholder

    def normalize(archive: bytes, replacements: Mapping[bytes, bytes]) -> bytes:
        if not replacements:
            return archive
        return _ARCHIVE_UUID_BYTES.sub(
            lambda match: replacements.get(match.group(0), match.group(0)),
            archive,
        )

    return (
        normalize(direct_before, direct_map),
        normalize(direct_after, direct_map),
        normalize(replay_before, replay_map),
        normalize(replay_after, replay_map),
        len(direct_map),
    )


def _compare_native_archive_deltas(
    direct_before: bytes,
    direct_after: bytes,
    replay_before: bytes,
    replay_after: bytes,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """Compare native archive effects, not unrelated identities of two clones."""

    (
        direct_before,
        direct_after,
        replay_before,
        replay_after,
        normalized_count,
    ) = _normalize_independent_clone_archives(
        direct_before,
        direct_after,
        replay_before,
        replay_after,
    )
    baseline_equivalent = direct_before == replay_before
    final_equivalent = direct_after == replay_after
    direct = _archive_delta(direct_before, direct_after)
    replay = _archive_delta(replay_before, replay_after)
    count = max(len(direct), len(replay))
    mismatches: list[dict[str, Any]] = []
    tree_truncated = False
    if not baseline_equivalent:
        direct_baseline_tree = _decoded_native_archive_tree(direct_before)
        replay_baseline_tree = _decoded_native_archive_tree(replay_before)
        if direct_baseline_tree is not None and replay_baseline_tree is not None:
            baseline_mismatches, baseline_truncated = _native_archive_tree_mismatches(
                direct_baseline_tree,
                replay_baseline_tree,
                limit=limit,
            )
            baseline_equivalent = not baseline_mismatches and not baseline_truncated
            tree_truncated = tree_truncated or baseline_truncated
            mismatches.extend(
                dict(item, phase="baseline") for item in baseline_mismatches
            )
        else:
            mismatches.append(
                {
                    "baseline": {
                        "directHash": hashlib.sha256(direct_before).hexdigest(),
                        "replayHash": hashlib.sha256(replay_before).hexdigest(),
                    }
                }
            )
    if not final_equivalent:
        direct_tree = _decoded_native_archive_tree(direct_after)
        replay_tree = _decoded_native_archive_tree(replay_after)
        if direct_tree is not None and replay_tree is not None:
            final_mismatches, final_truncated = _native_archive_tree_mismatches(
                direct_tree,
                replay_tree,
                limit=limit,
            )
            final_equivalent = not final_mismatches and not final_truncated
            tree_truncated = tree_truncated or final_truncated
            mismatches.extend(dict(item, phase="final") for item in final_mismatches)
        else:
            for index in range(count):
                direct_item = direct[index] if index < len(direct) else None
                replay_item = replay[index] if index < len(replay) else None
                if direct_item != replay_item:
                    mismatches.append({"direct": direct_item, "replay": replay_item})
    if not final_equivalent and not mismatches:
        mismatches.append(
            {
                "final": {
                    "directHash": hashlib.sha256(direct_after).hexdigest(),
                    "replayHash": hashlib.sha256(replay_after).hexdigest(),
                }
            }
        )
    bounded = mismatches[: max(0, min(100, int(limit)))]
    return {
        "equivalent": baseline_equivalent and final_equivalent,
        "mismatchCount": len(mismatches),
        "mismatchLocations": bounded,
        "truncated": tree_truncated or len(mismatches) > len(bounded),
        "directDeltaCount": len(direct),
        "replayDeltaCount": len(replay),
        "baselineEquivalent": baseline_equivalent,
        "finalEquivalent": final_equivalent,
        "normalizedCloneUuidCount": normalized_count,
    }


def _compare_native_archives(
    direct: bytes,
    replay: bytes,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """Compare two native states with the reviewed pairwise equivalence rules.

    An independent digest cannot encode an asymmetric storage spelling such
    as an omitted official default versus the same default written explicitly.
    Native restoration therefore uses the same bounded tree comparator as
    staged replay proof.  Unknown fields and formatting-only byte changes stay
    strict; only registered omission defaults and identity-addressed storage
    order may converge.
    """

    if direct == replay:
        return {
            "equivalent": True,
            "mismatchCount": 0,
            "mismatchLocations": [],
            "truncated": False,
        }
    direct_tree = _decoded_native_archive_tree(direct)
    replay_tree = _decoded_native_archive_tree(replay)
    if direct_tree is not None and replay_tree is not None:
        mismatches, truncated = _native_archive_tree_mismatches(
            direct_tree,
            replay_tree,
            limit=limit,
        )
        return {
            "equivalent": not mismatches and not truncated,
            "mismatchCount": len(mismatches),
            "mismatchLocations": mismatches,
            "truncated": truncated,
        }
    maximum = max(0, min(100, int(limit)))
    mismatch = {
        "directHash": hashlib.sha256(direct).hexdigest(),
        "replayHash": hashlib.sha256(replay).hexdigest(),
    }
    return {
        "equivalent": False,
        "mismatchCount": 1,
        "mismatchLocations": [mismatch] if maximum else [],
        "truncated": maximum == 0,
    }


def _native_archive_file_mapping(tree: Any, file_path: str) -> Mapping[str, Any] | None:
    if not isinstance(tree, Mapping):
        return None
    files = tree.get("files")
    if not isinstance(files, list):
        return None
    for entry in files:
        if not isinstance(entry, Mapping) or str(entry.get("path") or "") != file_path:
            continue
        value = entry.get("value")
        decoded = _decoded_native_package_data(value)
        if isinstance(decoded, Mapping):
            return decoded
        return value if isinstance(value, Mapping) else None
    return None


def _native_archive_mismatch_canonical_scope(
    mismatch: Mapping[str, Any],
    *,
    direct_tree: Any,
    replay_tree: Any,
) -> tuple[str, ...] | None:
    """Resolve one serialized mismatch to its narrow canonical owner.

    This is deliberately conservative.  A path is returned only when the
    package identity and nested entity identity are explicit.  An unresolved
    path remains private/unknown evidence and can never be normalized by a
    clone projection.
    """

    path = tuple(mismatch.get("path") or ())
    file_token = next(
        (
            str(part)[len("@path=") :]
            for part in path
            if str(part).startswith("@path=")
        ),
        "",
    )
    if not file_token:
        return None
    try:
        value_index = path.index("value")
    except ValueError:
        return None
    tail = list(path[value_index + 1 :])
    if tail and tail[0] == "$decoded":
        tail.pop(0)
    if not tail:
        return None
    direct = _native_archive_file_mapping(direct_tree, file_token)
    replay = _native_archive_file_mapping(replay_tree, file_token)
    serialized = direct or replay
    if serialized is None:
        return None

    if file_token == "fontinfo.plist":
        root = str(tail[0])
        aliases: Mapping[str, tuple[str, ...]] = {
            "settings": ("settings",),
            "fontMaster": ("masters",),
            "instances": ("instances",),
            "features": ("features",),
            "classes": ("classes",),
            "featurePrefixes": ("featurePrefixes",),
            "axes": ("axes",),
            "metrics": ("metrics",),
            "stems": ("stems",),
            "numbers": ("numbers",),
            "kerningLTR": ("kerning", "ltr"),
            "kerningRTL": ("kerning", "rtl"),
            "kerningVertical": ("kerning", "vertical"),
            "kerningContext": ("kerning", "context"),
        }
        canonical_root = aliases.get(root)
        if canonical_root is None:
            return None
        # Container-level loss (the observed ``settings`` copy artifact) is
        # intentionally a prefix scope. Nested collection identities require
        # a dedicated resolver before their private archive fields can pass.
        if len(tail) == 1:
            return canonical_root
        if root == "settings":
            return canonical_root + tuple(str(part) for part in tail[1:])
        return None

    if not file_token.startswith("glyphs/"):
        return None
    glyph_name = str(serialized.get("glyphname") or "")
    if not glyph_name:
        return None
    if str(tail[0]) != "layers":
        return ("glyphs", glyph_name) + tuple(str(part) for part in tail)
    if len(tail) < 2:
        return ("glyphs", glyph_name, "layers")
    layer_token = tail[1]
    layer_id = ""
    if str(layer_token).startswith("@layerId="):
        layer_id = str(layer_token).split("=", 1)[1]
    else:
        try:
            index = int(layer_token)
        except (TypeError, ValueError):
            return None
        layers = serialized.get("layers")
        if not isinstance(layers, list) or not 0 <= index < len(layers):
            return None
        layer = layers[index]
        if isinstance(layer, Mapping):
            layer_id = str(layer.get("layerId") or "")
    if not layer_id:
        return None
    return (
        "glyphs",
        glyph_name,
        "layers",
        layer_id,
    ) + tuple(str(part) for part in tail[2:])


def _classify_native_clone_archive_mismatches(
    mismatches: Sequence[Mapping[str, Any]],
    *,
    artifact_paths: Sequence[Sequence[str]],
    direct_tree: Any,
    replay_tree: Any,
) -> dict[str, Any]:
    """Join native mismatch scopes to exact canonical clone artifacts."""

    artifacts = tuple(tuple(str(part) for part in path) for path in artifact_paths)
    uncovered = []
    covered_count = 0
    for mismatch in mismatches:
        scope = _native_archive_mismatch_canonical_scope(
            mismatch,
            direct_tree=direct_tree,
            replay_tree=replay_tree,
        )
        covered = scope is not None and any(
            artifact[: len(scope)] == scope or scope[: len(artifact)] == artifact
            for artifact in artifacts
        )
        if covered:
            covered_count += 1
        else:
            uncovered.append(dict(mismatch))
    return {
        "complete": not uncovered,
        "coveredCount": covered_count,
        "uncoveredLocations": uncovered,
    }


def _staged_instance_identity(value: Any) -> str:
    native = str(_plain_scalar(_safe_getattr(value, "id")) or "")
    return native or "py:{}".format(id(value))


def _staged_instance_ids(
    before_instances: Sequence[Any],
    before_ids: Sequence[str],
    after_instances: Sequence[Any],
    *,
    code_hash: str,
) -> list[str]:
    if len(before_instances) != len(before_ids):
        raise HostAccessError("staged instance identity baseline is invalid")
    retained = {
        _staged_instance_identity(value): str(before_ids[index])
        for index, value in enumerate(before_instances)
    }
    used = set(retained.values())
    result: list[str] = []
    new_index = 0
    for value in after_instances:
        identity = retained.get(_staged_instance_identity(value))
        if identity is None:
            while True:
                identity = "instance_staged_{}_{:04d}".format(
                    code_hash[:12], new_index
                )
                new_index += 1
                if identity not in used:
                    break
        if identity in result:
            raise HostAccessError("staged instances produced a duplicate identity")
        used.add(identity)
        result.append(identity)
    return result


def _added_native_replay_templates(
    font: Any,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    changes: ChangeSet,
) -> dict[tuple[str, ...], Any]:
    """Copy only newly added native entities from the Python-modified clone."""

    additions = {
        change.path
        for change in changes.changes
        if not change.before_present and change.after_present
    }
    if not additions:
        return {}
    templates: dict[tuple[str, ...], Any] = {}
    added_master_ids = {
        path[1]
        for path in additions
        if len(path) == 2 and path[0] == "masters"
    }
    native_glyphs = {
        str(_safe_getattr(glyph, "name") or ""): glyph
        for glyph in _sequence_values(_safe_getattr(font, "glyphs"))
        if str(_safe_getattr(glyph, "name") or "")
    }

    for master_id in sorted(added_master_ids):
        master = _master_by_id(font, master_id)
        if master is None:
            raise HostAccessError("staged master template is unavailable")
        layers: dict[str, Any] = {}
        for glyph_name, glyph in native_glyphs.items():
            layer = _lookup_layer(glyph, master_id)
            if layer is None:
                raise HostAccessError(
                    "staged master layer template is unavailable for {}".format(
                        glyph_name
                    )
                )
            layers[glyph_name] = _copy_native_object(
                layer, kind="staged master layer"
            )
        templates[("masters", master_id)] = {
            "master": _copy_native_object(master, kind="staged master"),
            "layers": layers,
        }

    for path in sorted(additions):
        if len(path) == 2 and path[0] == "glyphs":
            glyph = native_glyphs.get(path[1])
            if glyph is None:
                raise HostAccessError("staged glyph template is unavailable")
            templates[path] = _copy_native_object(glyph, kind="staged glyph")
        elif (
            len(path) == 4
            and path[0] == "glyphs"
            and path[2] == "layers"
            and path[3] not in added_master_ids
        ):
            layer = _lookup_layer(native_glyphs.get(path[1]), path[3])
            if layer is None:
                raise HostAccessError("staged layer template is unavailable")
            templates[path] = _copy_native_object(layer, kind="staged layer")

    for root, attribute, kind in (
        ("instances", "instances", "instance"),
        ("features", "features", "feature"),
        ("classes", "classes", "class"),
        ("featurePrefixes", "featurePrefixes", "feature prefix"),
    ):
        target_order = collection_order(after.get(root, []))
        native_values = _sequence_values(_safe_getattr(font, attribute))
        if len(target_order) != len(native_values):
            raise HostAccessError("staged {} identity count is invalid".format(kind))
        native_by_id = {
            target_order[index]: value for index, value in enumerate(native_values)
        }
        for path in sorted(additions):
            if len(path) == 2 and path[0] == root:
                templates[path] = _copy_native_object(
                    native_by_id[path[1]], kind="staged {}".format(kind)
                )
    return templates


def _document_edited_state(font: Any) -> Optional[bool]:
    document = _maybe_call(_safe_getattr(font, "parent"))
    return _native_unsaved_changes(document)


def _source_file_state(path: Path) -> Mapping[str, Any] | None:
    """Return a private content-only fingerprint for an existing Glyphs source."""

    suffix = path.suffix.lower()
    if suffix not in {".glyphs", ".glyphspackage"}:
        return None
    kind = "glyphspackage" if suffix == ".glyphspackage" else "glyphs"
    if not path.exists():
        return {
            "kind": kind,
            "exists": False,
            "contentFingerprint": None,
        }
    digest = hashlib.sha256()
    try:
        if kind == "glyphs":
            if not path.is_file():
                return None
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        else:
            if not path.is_dir():
                return None
            for candidate in sorted(
                (item for item in path.rglob("*") if item.is_file()),
                key=lambda item: item.relative_to(path).as_posix(),
            ):
                relative = candidate.relative_to(path).as_posix().encode("utf-8")
                digest.update(len(relative).to_bytes(8, "big"))
                digest.update(relative)
                with candidate.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
    except OSError:
        return {
            "kind": kind,
            "exists": True,
            "contentFingerprint": None,
            "readable": False,
        }
    return {
        "kind": kind,
        "exists": True,
        "contentFingerprint": "sha256:{}".format(digest.hexdigest()),
        "readable": True,
    }


def _normalized_source_file_state(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix not in {".glyphs", ".glyphspackage"}:
        raise DocumentSaveError(
            "unsupported_source_format",
            "Glyphs document saves require a .glyphs or .glyphspackage path.",
        )
    if path.is_symlink():
        raise DocumentSaveError(
            "invalid_destination",
            "A Glyphs save path cannot be a symbolic link.",
        )
    kind = "glyphspackage" if suffix == ".glyphspackage" else "glyphs"
    if path.exists():
        if kind == "glyphs" and not path.is_file():
            raise DocumentSaveError(
                "destination_type_mismatch",
                "A .glyphs destination must be a regular file.",
            )
        if kind == "glyphspackage" and not path.is_dir():
            raise DocumentSaveError(
                "destination_type_mismatch",
                "A .glyphspackage destination must be a directory.",
            )
        if kind == "glyphspackage":
            for candidate in path.rglob("*"):
                if candidate.is_symlink():
                    raise DocumentSaveError(
                        "invalid_destination",
                        "A .glyphspackage destination cannot contain symbolic links.",
                    )
                if not candidate.is_dir() and not candidate.is_file():
                    raise DocumentSaveError(
                        "destination_type_mismatch",
                        "A .glyphspackage destination contains an unsupported filesystem object.",
                    )
    raw = _source_file_state(path)
    if raw is None:
        return {
            "kind": kind,
            "exists": path.exists(),
            "readable": False,
            "contentFingerprint": None,
        }
    return {
        "kind": kind,
        "exists": bool(raw.get("exists")),
        "readable": bool(raw.get("readable")),
        "contentFingerprint": raw.get("contentFingerprint"),
    }


def _same_save_path(left: Path | None, right: Path) -> bool:
    """Compare logical document URLs, not filesystem inode aliases."""

    if left is None:
        return False
    return left.resolve(strict=False) == right.resolve(strict=False)


def _same_save_object(left: Path | None, right: Path) -> bool:
    """Detect aliases when protecting another open document."""

    if left is None:
        return False
    try:
        if left.exists() and right.exists():
            return os.path.samefile(str(left), str(right))
    except OSError:
        pass
    return _same_save_path(left, right)


def _validated_save_destination(value: str) -> Path:
    """Resolve a save path without traversing links or nesting packages."""

    raw = Path(str(value or ""))
    if not raw.is_absolute():
        raise DocumentSaveError(
            "invalid_destination", "Save destinations must be explicit absolute paths."
        )
    if any(parent.suffix.lower() == ".glyphspackage" for parent in raw.parents):
        raise DocumentSaveError(
            "invalid_destination",
            "A save destination cannot be nested inside a .glyphspackage.",
        )
    # ``resolve_destination`` normalizes the stable macOS /tmp and /var root
    # aliases before rejecting arbitrary symlink ancestors. Performing a raw
    # symlink walk here would incorrectly reject ordinary /var/folders paths.
    try:
        target = resolve_destination(str(raw))
    except ValueError as exc:
        raise DocumentSaveError("invalid_destination", str(exc)) from exc
    if not target.parent.exists() or not target.parent.is_dir():
        raise DocumentSaveError(
            "destination_parent_unavailable",
            "The save destination parent directory does not exist.",
        )
    if not os.access(str(target.parent), os.W_OK):
        raise DocumentSaveError(
            "destination_parent_unwritable",
            "The save destination parent directory is not writable.",
        )
    return target


def _native_save_error(result: Any) -> str | None:
    success = result
    error = None
    if isinstance(result, tuple):
        success = result[0] if result else False
        error = result[1] if len(result) > 1 else None
    if bool(success) and error is None:
        return None
    for name in (
        "localizedRecoverySuggestion",
        "localizedFailureReason",
        "localizedDescription",
    ):
        value = _maybe_call(_safe_getattr(error, name)) if error is not None else None
        if value:
            return str(value)[:2048]
    return "Glyphs reported that the native document save failed."


_LIVE_SOURCE_SAVE_GUARD_LOCK = RLock()
_GuardSlotKey = tuple[int, int, int, bytes, bytes, bool]
_SOURCE_SAVE_REFLECTION_METHODS = frozenset(
    {
        "methodforselector",
        "performselector",
        "performselectorafterdelay",
        "performselectorinbackground",
        "performselectoronmainthread",
        "performselectoronthread",
        "performselectorwithobject",
        "performselectorwithobjectafterdelay",
        "performselectorwithobjectwithobject",
    }
)


@dataclass(frozen=True)
class _ObjectiveCMethodState:
    owner: Any
    python_name: str
    selector_name: bytes
    class_method: bool
    class_pointer: int
    method_pointer: int
    implementation_pointer: int
    type_encoding: bytes


@dataclass(frozen=True)
class _ObjectiveCMethodPatch:
    original_state: _ObjectiveCMethodState
    installed_implementation_pointer: int
    slot: _GuardSlotKey
    original_imp: Any
    trampoline: Any
    state: str = "residual_guard"
    repairable: bool = True


@dataclass(frozen=True)
class _PythonMethodPatch:
    owner: Any
    name: str
    original: Any
    installed: Any
    state: str = "residual_guard"
    repairable: bool = True


@dataclass(frozen=True)
class _ProfileHookPatch:
    original: Any
    installed: Any
    state: str
    repairable: bool


@dataclass
class _RuntimeDispatchController:
    original_imp: Any
    method_name: str
    reflection: bool
    active_guard: Any = None


class _ObjectiveCRuntime:
    """Minimal typed bridge to the Objective-C method runtime."""

    def __init__(self) -> None:
        library = ctypes.CDLL(None)
        pointer = ctypes.c_void_p
        library.objc_getClass.argtypes = [ctypes.c_char_p]
        library.objc_getClass.restype = pointer
        library.sel_registerName.argtypes = [ctypes.c_char_p]
        library.sel_registerName.restype = pointer
        library.object_getClass.argtypes = [pointer]
        library.object_getClass.restype = pointer
        library.class_getInstanceMethod.argtypes = [pointer, pointer]
        library.class_getInstanceMethod.restype = pointer
        library.class_getClassMethod.argtypes = [pointer, pointer]
        library.class_getClassMethod.restype = pointer
        library.class_copyMethodList.argtypes = [
            pointer,
            ctypes.POINTER(ctypes.c_uint),
        ]
        library.class_copyMethodList.restype = ctypes.POINTER(pointer)
        library.method_getImplementation.argtypes = [pointer]
        library.method_getImplementation.restype = pointer
        library.method_getTypeEncoding.argtypes = [pointer]
        library.method_getTypeEncoding.restype = ctypes.c_char_p
        library.method_setImplementation.argtypes = [pointer, pointer]
        library.method_setImplementation.restype = pointer
        library.free.argtypes = [pointer]
        library.free.restype = None
        self._library = library

    def capture(
        self,
        owner: Any,
        python_name: str,
        selector_name: bytes,
        *,
        class_method: bool,
        require_owned: bool = True,
    ) -> _ObjectiveCMethodState | None:
        owner_name = str(_safe_getattr(owner, "__name__") or "")
        if not owner_name:
            return None
        class_pointer = int(
            self._library.objc_getClass(owner_name.encode("utf-8")) or 0
        )
        selector_pointer = int(
            self._library.sel_registerName(bytes(selector_name)) or 0
        )
        if not class_pointer or not selector_pointer:
            return None
        if class_method:
            method_pointer = int(
                self._library.class_getClassMethod(
                    ctypes.c_void_p(class_pointer),
                    ctypes.c_void_p(selector_pointer),
                )
                or 0
            )
            list_owner = int(
                self._library.object_getClass(ctypes.c_void_p(class_pointer))
                or 0
            )
        else:
            method_pointer = int(
                self._library.class_getInstanceMethod(
                    ctypes.c_void_p(class_pointer),
                    ctypes.c_void_p(selector_pointer),
                )
                or 0
            )
            list_owner = class_pointer
        if not method_pointer or not list_owner:
            return None
        if require_owned:
            count = ctypes.c_uint(0)
            methods = self._library.class_copyMethodList(
                ctypes.c_void_p(list_owner), ctypes.byref(count)
            )
            try:
                owned = bool(methods) and any(
                    int(methods[index] or 0) == method_pointer
                    for index in range(int(count.value))
                )
            finally:
                if methods:
                    self._library.free(methods)
            if not owned:
                return None
        implementation_pointer = int(
            self._library.method_getImplementation(
                ctypes.c_void_p(method_pointer)
            )
            or 0
        )
        raw_encoding = self._library.method_getTypeEncoding(
            ctypes.c_void_p(method_pointer)
        )
        if not implementation_pointer or not raw_encoding:
            return None
        return _ObjectiveCMethodState(
            owner=owner,
            python_name=str(python_name),
            selector_name=bytes(selector_name),
            class_method=bool(class_method),
            class_pointer=class_pointer,
            method_pointer=method_pointer,
            implementation_pointer=implementation_pointer,
            type_encoding=bytes(raw_encoding),
        )

    def _matches(
        self,
        observed: _ObjectiveCMethodState | None,
        state: _ObjectiveCMethodState,
        implementation_pointer: int,
    ) -> bool:
        return bool(
            observed is not None
            and observed.class_pointer == state.class_pointer
            and observed.method_pointer == state.method_pointer
            and observed.implementation_pointer == implementation_pointer
            and observed.type_encoding == state.type_encoding
        )

    def swap_and_verify(
        self,
        state: _ObjectiveCMethodState,
        replacement_implementation_pointer: int,
        *,
        expected_current_implementation_pointer: int,
    ) -> tuple[bool, int | None]:
        """Atomically swap one IMP and prove both sides of the transition."""

        before = self.capture(
            state.owner,
            state.python_name,
            state.selector_name,
            class_method=state.class_method,
            require_owned=True,
        )
        if not self._matches(
            before, state, expected_current_implementation_pointer
        ):
            return False, None
        prior = int(
            self._library.method_setImplementation(
                ctypes.c_void_p(state.method_pointer),
                ctypes.c_void_p(replacement_implementation_pointer),
            )
            or 0
        )
        try:
            observed = self.capture(
                state.owner,
                state.python_name,
                state.selector_name,
                class_method=state.class_method,
                require_owned=True,
            )
        except BaseException:
            # The atomic exchange has already happened. Return its prior IMP
            # so the caller can restore it before failing closed.
            observed = None
        return (
            bool(
                prior == expected_current_implementation_pointer
                and self._matches(
                    observed, state, replacement_implementation_pointer
                )
            ),
            prior,
        )

    def set_and_verify(
        self,
        state: _ObjectiveCMethodState,
        implementation_pointer: int,
    ) -> bool:
        """Unconditionally restore an observed prior IMP after a failed swap."""

        self._library.method_setImplementation(
            ctypes.c_void_p(state.method_pointer),
            ctypes.c_void_p(implementation_pointer),
        )
        try:
            observed = self.capture(
                state.owner,
                state.python_name,
                state.selector_name,
                class_method=state.class_method,
                require_owned=True,
            )
        except BaseException:
            observed = None
        return self._matches(observed, state, implementation_pointer)

    def restore_and_verify(
        self,
        state: _ObjectiveCMethodState,
        *,
        expected_current_implementation_pointer: int | None = None,
    ) -> bool:
        expected = (
            state.implementation_pointer
            if expected_current_implementation_pointer is None
            else expected_current_implementation_pointer
        )
        verified, _prior = self.swap_and_verify(
            state,
            state.implementation_pointer,
            expected_current_implementation_pointer=expected,
        )
        if verified:
            return True
        # A failed transition can still end at the exact captured baseline.
        # Observe that final state before degrading the runtime. Never write
        # the baseline unconditionally here: a third party may have taken
        # ownership after the guard was installed.
        try:
            observed = self.capture(
                state.owner,
                state.python_name,
                state.selector_name,
                class_method=state.class_method,
                require_owned=True,
            )
        except BaseException:
            observed = None
        return self._matches(
            observed, state, state.implementation_pointer
        )


_OBJC_RUNTIME: _ObjectiveCRuntime | None = None
_OBJC_TRAMPOLINES: dict[_GuardSlotKey, Any] = {}
_OBJC_TRAMPOLINE_CLASS_SEQUENCE = 0


def _objective_c_runtime() -> _ObjectiveCRuntime:
    global _OBJC_RUNTIME
    if _OBJC_RUNTIME is None:
        _OBJC_RUNTIME = _ObjectiveCRuntime()
    return _OBJC_RUNTIME


class _WorkingSourceSaveGuardManager:
    """Own process-wide guard health, dispatch, and bounded native repair."""

    def __init__(self) -> None:
        self._lock = _LIVE_SOURCE_SAVE_GUARD_LOCK
        self._repair_lock = Lock()
        self._machine = ScriptingSafetyStateMachine()
        self._active_guard: Any = None
        self._controllers: dict[_GuardSlotKey, _RuntimeDispatchController] = {}
        self._objective_c_residuals: dict[
            _GuardSlotKey, _ObjectiveCMethodPatch
        ] = {}
        self._python_residuals: dict[
            tuple[Any, str], _PythonMethodPatch
        ] = {}
        self._profile_residual: _ProfileHookPatch | None = None

    def snapshot(self) -> Any:
        return self._machine.snapshot()

    def is_active_guard(self, guard: Any) -> bool:
        with self._lock:
            return self._active_guard is guard and self._machine.state == "active"

    def register_controller(
        self,
        slot: _GuardSlotKey,
        *,
        original_imp: Any,
        method_name: str,
        reflection: bool,
        guard: Any,
    ) -> None:
        with self._lock:
            controller = self._controllers.get(slot)
            if controller is None:
                controller = _RuntimeDispatchController(
                    original_imp=original_imp,
                    method_name=str(method_name),
                    reflection=bool(reflection),
                )
                self._controllers[slot] = controller
            else:
                controller.original_imp = original_imp
                controller.method_name = str(method_name)
                controller.reflection = bool(reflection)
            controller.active_guard = guard

    def deactivate_controller(self, slot: _GuardSlotKey, guard: Any) -> None:
        with self._lock:
            controller = self._controllers.get(slot)
            if controller is not None and controller.active_guard is guard:
                controller.active_guard = None

    def dispatch(self, slot: _GuardSlotKey, receiver: Any, *args: Any) -> Any:
        with self._lock:
            controller = self._controllers.get(slot)
            guard = controller.active_guard if controller is not None else None
            original_imp = controller.original_imp if controller is not None else None
        if controller is None or not callable(original_imp):
            raise SourceSaveForbiddenError(
                "working-source save guard dispatch state is unavailable"
            )
        if guard is not None and self.is_active_guard(guard):
            return guard._dispatch_objective_c(controller, receiver, *args)
        # A residual trampoline can remain reachable directly or through a
        # third-party swizzle. Outside an active lease it must behave exactly
        # like the captured implementation so normal Glyphs saves keep working.
        return original_imp(receiver, *args)

    def begin(self, guard: Any) -> None:
        with self._lock:
            if self._active_guard is not None:
                raise ScriptingRuntimeUnavailableError(
                    "working-source save guard is already active",
                    self._machine.snapshot(),
                )
        if self._machine.state != "healthy":
            self.repair(trigger="automatic_preflight")
        with self._lock:
            snapshot = self._machine.snapshot()
            if snapshot.state != "healthy":
                raise ScriptingRuntimeUnavailableError(
                    "strict scripting safety is unavailable; repair the current incident",
                    snapshot,
                )
            self._active_guard = guard
            self._machine.begin("guard_{}".format(id(guard)))

    def begin_recovery(self, guard: Any) -> None:
        with self._lock:
            if self._active_guard is guard:
                self._machine.begin_recovery(trigger="execution_teardown")

    @staticmethod
    def _objective_c_slot_snapshot(
        patch: _ObjectiveCMethodPatch,
        *,
        state: str | None = None,
        repairable: bool | None = None,
    ) -> SafetySlotSnapshot:
        owner = patch.original_state.owner
        selector = patch.original_state.selector_name.decode(
            "utf-8", errors="replace"
        )
        return SafetySlotSnapshot(
            slot_id="objc_{}_{}".format(
                patch.original_state.class_pointer,
                patch.original_state.method_pointer,
            ),
            owner_class=str(_safe_getattr(owner, "__name__") or type(owner).__name__),
            selector=selector,
            kind="objective_c",
            state=patch.state if state is None else state,
            repairable=(
                patch.repairable if repairable is None else repairable
            ),
        )

    @staticmethod
    def _python_slot_snapshot(
        patch: _PythonMethodPatch,
        *,
        state: str | None = None,
        repairable: bool | None = None,
    ) -> SafetySlotSnapshot:
        return SafetySlotSnapshot(
            slot_id="python_{}_{}".format(id(patch.owner), patch.name),
            owner_class=str(
                _safe_getattr(patch.owner, "__name__")
                or type(patch.owner).__name__
            ),
            selector=patch.name,
            kind="python_descriptor",
            state=patch.state if state is None else state,
            repairable=(
                patch.repairable if repairable is None else repairable
            ),
        )

    @staticmethod
    def _profile_slot_snapshot(patch: _ProfileHookPatch) -> SafetySlotSnapshot:
        return SafetySlotSnapshot(
            slot_id="profile_hook_main_thread",
            owner_class="PythonRuntime",
            selector="sys.setprofile",
            kind="profile_hook",
            state=patch.state,
            repairable=patch.repairable,
        )

    def finish(
        self,
        guard: Any,
        *,
        objective_c_residuals: Sequence[_ObjectiveCMethodPatch] = (),
        python_residuals: Sequence[_PythonMethodPatch] = (),
        profile_residual: _ProfileHookPatch | None = None,
        safety_failures: Sequence[str] = (),
    ) -> Any:
        with self._lock:
            for patch in objective_c_residuals:
                self._objective_c_residuals[patch.slot] = patch
                self.deactivate_controller(patch.slot, guard)
            for patch in python_residuals:
                self._python_residuals[(patch.owner, patch.name)] = patch
            if profile_residual is not None:
                self._profile_residual = profile_residual
            if self._active_guard is guard:
                self._active_guard = None
            affected = tuple(
                self._objective_c_slot_snapshot(patch)
                for patch in objective_c_residuals
            ) + tuple(
                self._python_slot_snapshot(patch)
                for patch in python_residuals
            )
            if profile_residual is not None:
                affected += (self._profile_slot_snapshot(profile_residual),)
            has_owned_residual = bool(
                any(
                    patch.state != "external_owner"
                    for patch in objective_c_residuals
                )
                or any(
                    patch.state != "external_owner"
                    for patch in python_residuals
                )
                or (
                    profile_residual is not None
                    and profile_residual.state != "external_owner"
                )
            )
            if affected:
                message = (
                    str(safety_failures[0])
                    if safety_failures
                    else "One or more save-guard slots did not restore exactly."
                )
                self._machine.mark_incident(
                    target_state=(
                        "recovery_required" if has_owned_residual else "degraded"
                    ),
                    phase="restore",
                    reason_code="guard_restoration_incomplete",
                    message=message,
                    affected_slots=affected,
                    trigger="execution_teardown",
                )
            elif safety_failures:
                self._machine.mark_incident(
                    target_state="degraded",
                    phase="restore",
                    reason_code="guard_verification_unavailable",
                    message=str(safety_failures[0]),
                    affected_slots=(),
                    trigger="execution_teardown",
                )
            else:
                self._machine.mark_healthy(trigger="execution_teardown")
            return self._machine.snapshot()

    def repair(
        self,
        *,
        trigger: str,
        expected_incident_id: str | None = None,
    ) -> SafetyRepairReport:
        """Serialize one bounded repair pass and convert native faults to state."""

        if not self._repair_lock.acquire(blocking=False):
            snapshot = self._machine.snapshot()
            report = SafetyRepairReport(
                trigger=str(trigger),
                attempted_at=datetime.now(timezone.utc).isoformat().replace(
                    "+00:00", "Z"
                ),
                result="busy",
                before_state=snapshot.state,
                after_state=snapshot.state,
                incident_id=(
                    snapshot.current_incident.incident_id
                    if snapshot.current_incident is not None
                    else None
                ),
                repaired_slot_count=0,
                remaining_slot_count=(
                    len(self._objective_c_residuals)
                    + len(self._python_residuals)
                    + (1 if self._profile_residual is not None else 0)
                ),
                message="Another scripting runtime repair is active.",
            )
            self._machine.record_repair(report)
            return report
        try:
            return self._repair_once(
                trigger=trigger,
                expected_incident_id=expected_incident_id,
            )
        except StaleScriptingRuntimeIncidentError:
            raise
        except BaseException as exc:
            with self._lock:
                before = self._machine.snapshot()
                affected = (
                    SafetySlotSnapshot(
                        slot_id="native_runtime_verification",
                        owner_class="ObjectiveCRuntime",
                        selector="method_getImplementation",
                        kind="objective_c",
                        state="unverifiable",
                        repairable=False,
                    ),
                )
                if before.state != "recovering":
                    self._machine.begin_recovery(trigger=str(trigger))
                self._machine.mark_incident(
                    target_state="recovery_required",
                    phase="repair",
                    reason_code="native_repair_unavailable",
                    message="Native scripting repair failed: {}".format(
                        type(exc).__name__
                    ),
                    affected_slots=affected,
                    trigger=str(trigger),
                )
                after = self._machine.snapshot()
                report = SafetyRepairReport(
                    trigger=str(trigger),
                    attempted_at=datetime.now(timezone.utc).isoformat().replace(
                        "+00:00", "Z"
                    ),
                    result="incomplete",
                    before_state=before.state,
                    after_state=after.state,
                    incident_id=(
                        after.current_incident.incident_id
                        if after.current_incident is not None
                        else None
                    ),
                    repaired_slot_count=0,
                    remaining_slot_count=1,
                    message="Native scripting runtime recovery is unavailable.",
                )
                self._machine.record_repair(report)
                return report
        finally:
            self._repair_lock.release()

    def _repair_once(
        self,
        *,
        trigger: str,
        expected_incident_id: str | None = None,
    ) -> SafetyRepairReport:
        with self._lock:
            before = self._machine.snapshot()
            current_id = (
                before.current_incident.incident_id
                if before.current_incident is not None
                else None
            )
            if expected_incident_id and expected_incident_id != current_id:
                raise StaleScriptingRuntimeIncidentError(
                    "stale scripting runtime incident: expected {} but current is {}".format(
                        expected_incident_id, current_id or "none"
                    )
                )
            if self._active_guard is not None:
                report = SafetyRepairReport(
                    trigger=str(trigger),
                    attempted_at=datetime.now(timezone.utc).isoformat().replace(
                        "+00:00", "Z"
                    ),
                    result="busy",
                    before_state=before.state,
                    after_state=before.state,
                    incident_id=current_id,
                    repaired_slot_count=0,
                    remaining_slot_count=(
                        len(self._objective_c_residuals)
                        + len(self._python_residuals)
                        + (1 if self._profile_residual is not None else 0)
                    ),
                    message="A live scripting guard is active.",
                )
                self._machine.record_repair(report)
                return report
            if (
                before.state == "healthy"
                and not self._objective_c_residuals
                and not self._python_residuals
                and self._profile_residual is None
            ):
                report = SafetyRepairReport(
                    trigger=str(trigger),
                    attempted_at=datetime.now(timezone.utc).isoformat().replace(
                        "+00:00", "Z"
                    ),
                    result="not_needed",
                    before_state="healthy",
                    after_state="healthy",
                    incident_id=None,
                    repaired_slot_count=0,
                    remaining_slot_count=0,
                    message="The strict scripting interlock is healthy.",
                )
                self._machine.record_repair(report)
                return report
            self._machine.begin_recovery(trigger=str(trigger))

        repaired = 0
        remaining_objc: dict[_GuardSlotKey, _ObjectiveCMethodPatch] = {}
        remaining_python: dict[tuple[Any, str], _PythonMethodPatch] = {}
        remaining_profile: _ProfileHookPatch | None = None
        affected: list[SafetySlotSnapshot] = []
        runtime = _objective_c_runtime()

        for slot, patch in tuple(self._objective_c_residuals.items()):
            state = patch.original_state
            try:
                observed = runtime.capture(
                    state.owner,
                    state.python_name,
                    state.selector_name,
                    class_method=state.class_method,
                    require_owned=True,
                )
            except BaseException:
                observed = None
            if runtime._matches(observed, state, state.implementation_pointer):
                repaired += 1
                self.deactivate_controller(slot, None)
                continue
            if runtime._matches(
                observed, state, patch.installed_implementation_pointer
            ):
                try:
                    restored = runtime.restore_and_verify(
                        state,
                        expected_current_implementation_pointer=(
                            patch.installed_implementation_pointer
                        ),
                    )
                except BaseException:
                    restored = False
                if restored:
                    repaired += 1
                    self.deactivate_controller(slot, None)
                    continue
                remaining_objc[slot] = patch
                affected.append(
                    self._objective_c_slot_snapshot(
                        patch, state="residual_guard", repairable=True
                    )
                )
                continue
            if observed is not None:
                # The public method is now owned by another implementation.
                # Do not overwrite it. The retained controller safely forwards
                # if that implementation still calls our old trampoline.
                repaired += 1
                self.deactivate_controller(slot, None)
                continue
            remaining_objc[slot] = patch
            affected.append(
                self._objective_c_slot_snapshot(
                    patch, state="unverifiable", repairable=False
                )
            )

        for key, patch in tuple(self._python_residuals.items()):
            try:
                current = vars(patch.owner).get(patch.name)
            except Exception:
                current = None
            if current is patch.original:
                repaired += 1
                continue
            if current is patch.installed:
                try:
                    restored = _WorkingSourceSaveRuntimeGuard._set_python_descriptor(
                        patch.owner, patch.name, patch.original
                    )
                except BaseException:
                    restored = False
                if restored:
                    repaired += 1
                    continue
                remaining_python[key] = patch
                affected.append(
                    self._python_slot_snapshot(
                        patch, state="residual_guard", repairable=True
                    )
                )
                continue
            if current is not None:
                repaired += 1
                continue
            remaining_python[key] = patch
            affected.append(
                self._python_slot_snapshot(
                    patch, state="unverifiable", repairable=False
                )
            )

        profile_patch = self._profile_residual
        if profile_patch is not None:
            try:
                current_profile = sys.getprofile()
                profile_verified = True
            except BaseException:
                current_profile = None
                profile_verified = False
            if not profile_verified:
                remaining_profile = _ProfileHookPatch(
                    original=profile_patch.original,
                    installed=profile_patch.installed,
                    state="unverifiable",
                    repairable=False,
                )
                affected.append(self._profile_slot_snapshot(remaining_profile))
            elif current_profile is profile_patch.original:
                repaired += 1
            elif current_profile is profile_patch.installed:
                try:
                    sys.setprofile(profile_patch.original)
                    restored = sys.getprofile() is profile_patch.original
                except BaseException:
                    restored = False
                if restored:
                    repaired += 1
                else:
                    remaining_profile = _ProfileHookPatch(
                        original=profile_patch.original,
                        installed=profile_patch.installed,
                        state="residual_guard",
                        repairable=True,
                    )
                    affected.append(
                        self._profile_slot_snapshot(remaining_profile)
                    )
            else:
                # An external profiler deliberately took ownership. Preserve
                # it and adopt it as the next lease's baseline.
                repaired += 1

        with self._lock:
            self._objective_c_residuals = remaining_objc
            self._python_residuals = remaining_python
            self._profile_residual = remaining_profile
            remaining = (
                len(remaining_objc)
                + len(remaining_python)
                + (1 if remaining_profile is not None else 0)
            )
            if remaining:
                self._machine.mark_incident(
                    target_state="recovery_required",
                    phase="repair",
                    reason_code="guard_repair_incomplete",
                    message="Strict scripting safety could not restore every owned slot.",
                    affected_slots=tuple(affected),
                    trigger=str(trigger),
                )
                result = "incomplete"
                message = "Scripting runtime repair remains incomplete."
            else:
                self._machine.mark_healthy(trigger=str(trigger))
                result = "repaired" if repaired else "revalidated"
                message = "The strict scripting interlock is healthy."
            after = self._machine.snapshot()
            report = SafetyRepairReport(
                trigger=str(trigger),
                attempted_at=datetime.now(timezone.utc).isoformat().replace(
                    "+00:00", "Z"
                ),
                result=result,
                before_state=before.state,
                after_state=after.state,
                incident_id=current_id,
                repaired_slot_count=repaired,
                remaining_slot_count=remaining,
                message=message,
            )
            self._machine.record_repair(report)
            return report


_LIVE_SOURCE_SAVE_GUARD_MANAGER = _WorkingSourceSaveGuardManager()


def _objective_c_trampoline(
    slot: _GuardSlotKey,
) -> Any:
    """Return one stable off-target PyObjC callback IMP for a guard slot.

    Installing a Python selector directly on a real host class mutates
    PyObjC's descriptor cache, which cannot be repaired by restoring only the
    Objective-C IMP. Trampolines therefore live on private helper classes and
    are reused across serialized guard executions; real host classes are
    touched only through ``method_setImplementation``.
    """

    global _OBJC_TRAMPOLINE_CLASS_SEQUENCE
    cached = _OBJC_TRAMPOLINES.get(slot)
    if cached is not None:
        return cached
    import objc  # type: ignore[import-not-found]

    _class_pointer, _method_pointer, _baseline_pointer, selector_name, signature, class_method = slot

    def dispatch(receiver: Any, *args: Any) -> Any:
        return _LIVE_SOURCE_SAVE_GUARD_MANAGER.dispatch(slot, receiver, *args)

    NSObject = objc.lookUpClass("NSObject")
    while True:
        _OBJC_TRAMPOLINE_CLASS_SEQUENCE += 1
        class_name = "GlyphsMCPSaveGuardIMP_{}_{}".format(
            os.getpid(), _OBJC_TRAMPOLINE_CLASS_SEQUENCE
        )
        try:
            objc.lookUpClass(class_name)
        except objc.nosuchclass_error:
            pass
        else:
            continue
        try:
            helper = type(class_name, (NSObject,), {})
        except Exception as exc:
            raise SourceSaveForbiddenError(
                "working-source save guard could not allocate its private "
                "Objective-C trampoline class"
            ) from exc
        break
    replacement_selector = objc.selector(
        dispatch,
        selector=selector_name,
        signature=signature,
        isClassMethod=class_method,
    )
    objc.classAddMethod(helper, selector_name, replacement_selector)
    state = _objective_c_runtime().capture(
        helper,
        "trampoline",
        selector_name,
        class_method=class_method,
        require_owned=True,
    )
    if state is None:
        raise SourceSaveForbiddenError(
            "working-source save guard could not create a verifiable "
            "Objective-C trampoline"
        )
    trampoline = {
        "owner": helper,
        "selector": replacement_selector,
        "state": state,
    }
    _OBJC_TRAMPOLINES[slot] = trampoline
    return trampoline


def _runtime_selector_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    selector = _safe_getattr(value, "selector")
    if isinstance(selector, bytes):
        return selector.decode("utf-8", errors="replace")
    if isinstance(selector, str):
        return selector
    return str(value or "")


def _runtime_method_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _runtime_selector_text(value).lower())


def _is_working_source_save_operation(value: Any) -> bool:
    """Recognize native/Python entry points that persist an open source.

    Deliberately exclude read-only save-panel/autosaved-URL accessors and
    ``saveDocumentToPDF:``. Open-world Python retains ordinary mutation and
    unrelated external-file behavior; only working-font persistence is gated.
    """

    key = _runtime_method_key(value)
    if not key:
        return False
    if key in {"save", "gsfontsave"} or key.endswith("gsfontsave"):
        return True
    if key.startswith("savedocumenttopdf"):
        return False
    return key.startswith(
        (
            "savedocument",
            "saveifnecessary",
            "savepresenteditemchanges",
            "savetofile",
            "savetopath",
            "savetourl",
            "writetofile",
            "writetopath",
            "writesafelytourl",
            "writetourl",
            "autosavedocument",
            "autosavewith",
        )
    )


def _is_source_save_reflection_method(value: Any) -> bool:
    key = _runtime_method_key(value)
    return key in _SOURCE_SAVE_REFLECTION_METHODS or key.startswith(
        "performselector"
    )


class _WorkingSourceSaveRuntimeGuard:
    """Temporarily interpose persistence selectors for the working document.

    This is a capability interlock, not a Python sandbox. Native selectors are
    replaced on their defining Objective-C classes and restored exactly in
    ``finally``. Wrappers forward calls for every non-protected receiver, which
    keeps other open-world mutation behavior intact. A process-local profile
    callback is defense in depth for Python convenience methods and selectors
    that a host class exposes dynamically rather than in its class dictionary.
    """

    def __init__(
        self,
        protected_objects: Sequence[Any],
        *,
        native_identity: Callable[[Any], Any],
    ) -> None:
        self._objects = tuple(
            value for value in protected_objects if value is not None
        )
        self._native_identity = native_identity
        self._protected_identities: set[Any] = set()
        for value in self._objects:
            try:
                self._protected_identities.add(native_identity(value))
            except Exception:
                self._protected_identities.add(("python", id(value)))
        self._patched: list[
            tuple[
                str,
                Any,
                str,
                Any,
                Any,
                _ObjectiveCMethodPatch | _PythonMethodPatch | None,
            ]
        ] = []
        self._patched_keys: set[tuple[Any, str]] = set()
        self._prior_profile: Any = None
        self._installed_profile: Any = None
        self._blocked_operation: str | None = None
        self._safety_failures: list[str] = []
        self._entered = False

    def _poison(self, message: str) -> None:
        """Record an incident for bounded recovery after teardown."""

        self._safety_failures.append(str(message))

    def _identity(self, value: Any) -> Any:
        try:
            identity = self._native_identity(value)
            hash(identity)
            return identity
        except Exception:
            return ("python", id(value))

    def _is_protected(self, value: Any) -> bool:
        if value is None:
            return False
        return self._identity(value) in self._protected_identities

    def _block(self, operation: Any) -> None:
        name = _runtime_selector_text(operation) or "source-save selector"
        self._blocked_operation = self._blocked_operation or name
        raise SourceSaveForbiddenError(
            "execute_python cannot invoke working-source save selector {!r}; "
            "use save_document".format(name)
        )

    def _replacement(
        self,
        original: Any,
        method_name: str,
        *,
        reflection: bool,
    ) -> Callable[..., Any]:
        guard = self

        def guarded_method(receiver: Any, *args: Any, **kwargs: Any) -> Any:
            if not _LIVE_SOURCE_SAVE_GUARD_MANAGER.is_active_guard(guard):
                return original(receiver, *args, **kwargs)
            if guard._is_protected(receiver):
                if not reflection:
                    guard._block(method_name)
                selector_value = args[0] if args else None
                if selector_value is None and kwargs:
                    selector_value = next(iter(kwargs.values()), None)
                if _is_working_source_save_operation(selector_value):
                    guard._block(selector_value)
            return original(receiver, *args, **kwargs)

        guarded_method.__name__ = str(method_name)
        guarded_method.__qualname__ = "working_source_save_guard.{}".format(
            method_name
        )
        return guarded_method

    @staticmethod
    def _set_python_descriptor(owner: Any, name: str, value: Any) -> bool:
        """Assign a Python method without promoting it to an ObjC selector.

        PyObjC's class metaclass turns a bare function assigned with
        ``setattr`` into an ``objc.python_selector``. Assigning the original
        function the same way during teardown therefore cannot restore the
        descriptor (and leaves a new Objective-C method behind). The
        ``python_method`` marker preserves Python-only methods as their exact
        original function objects across both sides of the interposition.
        """

        assignment = value
        if _is_objc_proxy(owner):
            try:
                import objc  # type: ignore[import-not-found]

                assignment = objc.python_method(value)
            except Exception as exc:
                raise RuntimeError(
                    "save-guard could not preserve a PyObjC Python method"
                ) from exc
        setattr(owner, name, assignment)
        try:
            return vars(owner).get(name) is value
        except Exception:
            return False

    def _dispatch_objective_c(
        self,
        controller: _RuntimeDispatchController,
        receiver: Any,
        *args: Any,
    ) -> Any:
        if self._is_protected(receiver):
            if not controller.reflection:
                self._block(controller.method_name)
            selector_value = args[0] if args else None
            if _is_working_source_save_operation(selector_value):
                self._block(selector_value)
        return controller.original_imp(receiver, *args)

    def _patch_method(
        self,
        owner: Any,
        name: str,
        original: Any,
        *,
        reflection: bool,
    ) -> None:
        key = (owner, name)
        if key in self._patched_keys or not callable(original):
            return
        selector_name = _safe_getattr(original, "selector")
        signature = _safe_getattr(original, "signature")
        if selector_name is not None and signature is not None:
            try:
                raw_selector = (
                    selector_name.encode("utf-8")
                    if isinstance(selector_name, str)
                    else bytes(selector_name)
                )
                raw_signature = (
                    signature.encode("utf-8")
                    if isinstance(signature, str)
                    else bytes(signature)
                )
                class_method = bool(
                    _safe_getattr(original, "isClassMethod")
                )
                runtime = _objective_c_runtime()
                original_state = runtime.capture(
                    owner,
                    name,
                    raw_selector,
                    class_method=class_method,
                    require_owned=True,
                )
                if original_state is None:
                    # The descriptor is inherited or lazily cached on this
                    # Python class. Its actual defining Objective-C class is
                    # visited separately through the MRO; never add a new
                    # override that cannot be removed safely.
                    return
                original_imp = (
                    owner.methodForSelector_(raw_selector)
                    if class_method
                    else owner.instanceMethodForSelector_(raw_selector)
                )
                slot: _GuardSlotKey = (
                    original_state.class_pointer,
                    original_state.method_pointer,
                    original_state.implementation_pointer,
                    raw_selector,
                    raw_signature,
                    class_method,
                )
                trampoline = _objective_c_trampoline(slot)
                installed_pointer = int(
                    trampoline["state"].implementation_pointer
                )
                if installed_pointer == original_state.implementation_pointer:
                    raise SourceSaveForbiddenError(
                        "working-source save guard trampoline unexpectedly "
                        "matches the host implementation"
                    )
                _LIVE_SOURCE_SAVE_GUARD_MANAGER.register_controller(
                    slot,
                    original_imp=original_imp,
                    method_name=name,
                    reflection=reflection,
                    guard=self,
                )
                objective_c_patch = _ObjectiveCMethodPatch(
                    original_state=original_state,
                    installed_implementation_pointer=installed_pointer,
                    slot=slot,
                    original_imp=original_imp,
                    trampoline=trampoline,
                )
                installed, prior = runtime.swap_and_verify(
                    original_state,
                    installed_pointer,
                    expected_current_implementation_pointer=(
                        original_state.implementation_pointer
                    ),
                )
                if not installed:
                    _LIVE_SOURCE_SAVE_GUARD_MANAGER.deactivate_controller(
                        slot, self
                    )
                    if prior is not None and not runtime.set_and_verify(
                        original_state, prior
                    ):
                        self._patched.append(
                            (
                                "objc",
                                owner,
                                name,
                                raw_selector,
                                original,
                                objective_c_patch,
                            )
                        )
                        self._patched_keys.add(key)
                        self._poison(
                            "Objective-C selector installation could not "
                            "restore the exact IMP observed by its atomic swap"
                        )
                    raise SourceSaveForbiddenError(
                        "working-source save guard could not verify its "
                        "Objective-C selector interposition"
                    )
                self._patched.append(
                    (
                        "objc",
                        owner,
                        name,
                        raw_selector,
                        original,
                        objective_c_patch,
                    )
                )
                self._patched_keys.add(key)
                return
            except SourceSaveForbiddenError:
                raise
            except Exception as exc:
                raise SourceSaveForbiddenError(
                    "working-source save guard could not install its "
                    "Objective-C selector interposition"
                ) from exc
        replacement = self._replacement(
            original, name, reflection=reflection
        )
        python_patch = _PythonMethodPatch(
            owner=owner,
            name=name,
            original=original,
            installed=replacement,
        )
        managed_owner = _is_objc_proxy(owner)
        try:
            installed = self._set_python_descriptor(
                owner, name, replacement
            )
        except Exception as exc:
            if managed_owner:
                try:
                    restored = self._set_python_descriptor(
                        owner, name, original
                    )
                except Exception:
                    restored = False
                if not restored:
                    self._patched.append(
                        ("python", owner, name, None, original, python_patch)
                    )
                    self._patched_keys.add(key)
                    self._poison(
                        "PyObjC Python-method installation could not restore "
                        "the exact original descriptor"
                    )
                raise SourceSaveForbiddenError(
                    "working-source save guard could not install its "
                    "PyObjC Python-method interposition"
                ) from exc
            raise SourceSaveForbiddenError(
                "working-source save guard could not install its Python "
                "method interposition"
            ) from exc
        if not installed:
            try:
                restored = self._set_python_descriptor(
                    owner, name, original
                )
            except Exception:
                restored = False
            if not restored:
                self._patched.append(
                    ("python", owner, name, None, original, python_patch)
                )
                self._patched_keys.add(key)
                self._poison(
                    "Python descriptor installation could not restore the "
                    "exact original method"
                )
            raise SourceSaveForbiddenError(
                "working-source save guard could not verify its Python "
                "method interposition"
            )
        self._patched.append(
            ("python", owner, name, None, original, python_patch)
        )
        self._patched_keys.add(key)

    def _install_class_interpositions(self) -> None:
        for target in self._objects:
            try:
                hierarchy = tuple(type(target).__mro__)
            except Exception:
                hierarchy = (type(target),)
            for owner in hierarchy:
                # PyObjC discovers native selectors lazily. ``dir`` populates
                # the class dictionary before we select defining methods only.
                try:
                    dir(owner)
                    own_items = tuple(vars(owner).items())
                except Exception:
                    continue
                for name, original in own_items:
                    reflection = _is_source_save_reflection_method(name)
                    if not reflection and not _is_working_source_save_operation(
                        name
                    ):
                        continue
                    self._patch_method(
                        owner,
                        str(name),
                        original,
                        reflection=reflection,
                    )

    def _profile(self, frame: Any, event: str, argument: Any) -> None:
        if not _LIVE_SOURCE_SAVE_GUARD_MANAGER.is_active_guard(self):
            prior = self._prior_profile
            if callable(prior):
                prior(frame, event, argument)
            return
        target = None
        name = ""
        if event == "call":
            name = str(_safe_getattr(frame.f_code, "co_name") or "")
            target = frame.f_locals.get("self")
        elif event == "c_call":
            name = str(_safe_getattr(argument, "__name__") or "")
            target = _safe_getattr(argument, "__self__")
        if (
            name
            and _is_working_source_save_operation(name)
            and self._is_protected(target)
        ):
            self._block(name)
        prior = self._prior_profile
        if callable(prior):
            prior(frame, event, argument)

    def __enter__(self) -> "_WorkingSourceSaveRuntimeGuard":
        _LIVE_SOURCE_SAVE_GUARD_MANAGER.begin(self)
        self._entered = True
        try:
            self._prior_profile = sys.getprofile()
            self._install_class_interpositions()
            self._installed_profile = self._profile
            sys.setprofile(self._installed_profile)
            if sys.getprofile() is not self._installed_profile:
                raise SourceSaveForbiddenError(
                    "working-source save guard could not verify its profile hook"
                )
        except BaseException as exc:
            # Installation failures do not become a permanent latch. They do
            # become an observable degraded incident so an agent can run one
            # native revalidation pass before retrying the interrupted call.
            if isinstance(exc, SourceSaveForbiddenError):
                self._poison(str(exc))
            self.__exit__(*sys.exc_info())
            raise
        return self

    def raise_if_blocked(self) -> None:
        if self._blocked_operation is not None:
            self._block(self._blocked_operation)

    def __exit__(self, *_error: Any) -> None:
        if not self._entered:
            return
        active_exception = bool(_error and _error[0] is not None)
        restoration_errors: list[BaseException] = []
        objective_c_residuals: list[_ObjectiveCMethodPatch] = []
        python_residuals: list[_PythonMethodPatch] = []
        profile_residual: _ProfileHookPatch | None = None
        _LIVE_SOURCE_SAVE_GUARD_MANAGER.begin_recovery(self)
        try:
            try:
                current_profile = sys.getprofile()
                if current_profile is self._installed_profile:
                    sys.setprofile(self._prior_profile)
                    if sys.getprofile() is not self._prior_profile:
                        profile_residual = _ProfileHookPatch(
                            original=self._prior_profile,
                            installed=self._installed_profile,
                            state="residual_guard",
                            repairable=True,
                        )
                        raise RuntimeError(
                            "save-guard profile restoration did not verify"
                        )
                elif current_profile is not self._prior_profile:
                    profile_residual = _ProfileHookPatch(
                        original=self._prior_profile,
                        installed=self._installed_profile,
                        state="external_owner",
                        repairable=True,
                    )
                    raise RuntimeError(
                        "save-guard profile hook ownership changed during execution"
                    )
            except BaseException as exc:
                if profile_residual is None:
                    profile_residual = _ProfileHookPatch(
                        original=self._prior_profile,
                        installed=self._installed_profile,
                        state="unverifiable",
                        repairable=False,
                    )
                restoration_errors.append(exc)
            for kind, owner, name, _selector_name, original, patch in reversed(
                self._patched
            ):
                try:
                    if kind == "objc":
                        if not isinstance(patch, _ObjectiveCMethodPatch):
                            raise RuntimeError(
                                "save-guard Objective-C restoration state is missing"
                            )
                        if not _objective_c_runtime().restore_and_verify(
                            patch.original_state,
                            expected_current_implementation_pointer=(
                                patch.installed_implementation_pointer
                            ),
                        ):
                            raise RuntimeError(
                                "save-guard Objective-C IMP restoration did not verify"
                            )
                    else:
                        if not isinstance(patch, _PythonMethodPatch):
                            raise RuntimeError(
                                "save-guard Python restoration state is missing"
                            )
                        try:
                            current = vars(owner).get(name)
                        except Exception:
                            current = None
                        if current is original:
                            restored = True
                        elif current is patch.installed:
                            restored = self._set_python_descriptor(
                                owner, name, original
                            )
                        else:
                            # Another owner replaced our wrapper. Do not
                            # overwrite it. Record external ownership so one
                            # native repair pass can adopt it as the next
                            # baseline while inactive wrappers forward safely.
                            external_patch = _PythonMethodPatch(
                                owner=patch.owner,
                                name=patch.name,
                                original=patch.original,
                                installed=patch.installed,
                                state="external_owner",
                                repairable=True,
                            )
                            python_residuals.append(external_patch)
                            restoration_errors.append(
                                RuntimeError(
                                    "save-guard descriptor ownership changed during execution"
                                )
                            )
                            continue
                        if not restored:
                            raise RuntimeError(
                                "save-guard descriptor restoration did not verify"
                            )
                except BaseException as exc:
                    if isinstance(patch, _ObjectiveCMethodPatch):
                        state = patch.original_state
                        try:
                            runtime = _objective_c_runtime()
                            observed = runtime.capture(
                                state.owner,
                                state.python_name,
                                state.selector_name,
                                class_method=state.class_method,
                                require_owned=True,
                            )
                        except BaseException:
                            observed = None
                        if observed is not None and runtime._matches(
                            observed, state, state.implementation_pointer
                        ):
                            _LIVE_SOURCE_SAVE_GUARD_MANAGER.deactivate_controller(
                                patch.slot, self
                            )
                            continue
                        if observed is not None and not runtime._matches(
                            observed,
                            state,
                            patch.installed_implementation_pointer,
                        ):
                            residual_patch = _ObjectiveCMethodPatch(
                                original_state=patch.original_state,
                                installed_implementation_pointer=(
                                    patch.installed_implementation_pointer
                                ),
                                slot=patch.slot,
                                original_imp=patch.original_imp,
                                trampoline=patch.trampoline,
                                state="external_owner",
                                repairable=True,
                            )
                        elif observed is None:
                            residual_patch = _ObjectiveCMethodPatch(
                                original_state=patch.original_state,
                                installed_implementation_pointer=(
                                    patch.installed_implementation_pointer
                                ),
                                slot=patch.slot,
                                original_imp=patch.original_imp,
                                trampoline=patch.trampoline,
                                state="unverifiable",
                                repairable=False,
                            )
                        else:
                            residual_patch = patch
                        restoration_errors.append(exc)
                        objective_c_residuals.append(residual_patch)
                    elif isinstance(patch, _PythonMethodPatch):
                        try:
                            current = vars(patch.owner).get(patch.name)
                        except Exception:
                            current = None
                        if current is patch.original:
                            continue
                        if current is not None and current is not patch.installed:
                            residual_patch = _PythonMethodPatch(
                                owner=patch.owner,
                                name=patch.name,
                                original=patch.original,
                                installed=patch.installed,
                                state="external_owner",
                                repairable=True,
                            )
                        elif current is None:
                            residual_patch = _PythonMethodPatch(
                                owner=patch.owner,
                                name=patch.name,
                                original=patch.original,
                                installed=patch.installed,
                                state="unverifiable",
                                repairable=False,
                            )
                        else:
                            residual_patch = patch
                        restoration_errors.append(exc)
                        python_residuals.append(residual_patch)
                    else:
                        restoration_errors.append(exc)
                    continue
                if isinstance(patch, _ObjectiveCMethodPatch):
                    _LIVE_SOURCE_SAVE_GUARD_MANAGER.deactivate_controller(
                        patch.slot, self
                    )
            if restoration_errors:
                self._poison(
                    "working-source save guard restoration failed: {}".format(
                        restoration_errors[0]
                    )
                )
        finally:
            self._patched = []
            self._patched_keys.clear()
            self._entered = False
            snapshot = _LIVE_SOURCE_SAVE_GUARD_MANAGER.finish(
                self,
                objective_c_residuals=objective_c_residuals,
                python_residuals=python_residuals,
                profile_residual=profile_residual,
                safety_failures=tuple(self._safety_failures),
            )
        if snapshot.state != "healthy" and not active_exception:
            raise ScriptingRuntimeUnavailableError(
                "working-source save guard restoration requires repair",
                snapshot,
            ) from (restoration_errors[0] if restoration_errors else None)


def _observed_layer_metrics(layer: Any) -> dict[str, Any]:
    def number(name: str) -> Any:
        value = _plain_scalar(_maybe_call(_safe_getattr(layer, name)))
        return value if isinstance(value, (int, float)) else None

    return {
        "width": number("width"),
        "leftBearing": number("LSB"),
        "rightBearing": number("RSB"),
        "verticalOrigin": number("vertOrigin"),
        "verticalAdvance": number("vertWidth"),
        "topBearing": number("TSB"),
        "bottomBearing": number("BSB"),
    }


def _observed_layer_bounds(layer: Any) -> Mapping[str, float] | None:
    if not (_layer_paths(layer) or _layer_components(layer)):
        return None
    bounds = _maybe_call(_safe_getattr(layer, "bounds"))
    if bounds is None:
        return None
    origin = _safe_getattr(bounds, "origin")
    size = _safe_getattr(bounds, "size")
    values = (
        _safe_getattr(origin, "x"),
        _safe_getattr(origin, "y"),
        _safe_getattr(size, "width"),
        _safe_getattr(size, "height"),
    )
    if not all(isinstance(value, (int, float)) for value in values):
        try:
            values = (bounds[0][0], bounds[0][1], bounds[1][0], bounds[1][1])
        except Exception:
            return None
    return {
        "x": float(values[0]),
        "y": float(values[1]),
        "width": float(values[2]),
        "height": float(values[3]),
    }


@dataclass(frozen=True)
class _DetachedCloneProjection:
    """Three-way projection for state changed only by ``GSFont.copy()``.

    The source and untouched clone establish the adapter-owned artifact set.
    Later clone captures project an artifact back to the source value only
    while its native value still equals that untouched-clone value. Explicit
    requested paths are protected. An unexpected third value is retained so
    verification observes it instead of silently normalizing a side effect.

    No native setter is called here. This is important because replaying an
    unrelated clone artifact can trigger Glyphs derivation, modal validation,
    or component realignment before the requested simulation even begins.
    """

    artifacts: ChangeSet

    @staticmethod
    def _overlaps(path: Sequence[str], protected: Sequence[str]) -> bool:
        left = tuple(str(part) for part in path)
        right = tuple(str(part) for part in protected)
        return (
            left[: len(right)] == right
            or right[: len(left)] == left
        )

    def normalize(
        self,
        observed: Mapping[str, Any],
        *,
        protected_paths: Sequence[Sequence[str]] = (),
    ) -> Mapping[str, Any]:
        corrections = []
        for artifact in self.artifacts.changes:
            if any(
                self._overlaps(artifact.path, protected)
                for protected in protected_paths
            ):
                continue
            present, value = semantic_value_at(observed, artifact.path)
            if present != artifact.before_present:
                continue
            if present and value != artifact.before:
                continue
            corrections.append(artifact)
        if not corrections:
            return observed
        patch = ChangeSet.project(observed, corrections)
        return patch.apply(observed)


class GlyphsDocumentHost(GlyphsHostAdapter):
    """Complete v2 host port; native objects remain inside this adapter."""

    observes_live_python_exceptions = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._canonical_model_cache = _RevisionBoundGlyphModelCache()
        self._glyphs_change_generation = _GlyphsChangeGeneration.install(self._app)
        self._instance_identity_maps: dict[str, dict[str, str]] = {}
        self._instance_identity_counters: dict[str, int] = {}
        self._master_lifecycle_tombstones: dict[str, Mapping[str, Any]] = {}
        self._layer_lifecycle_tombstones: dict[str, Mapping[str, Any]] = {}
        self._native_replay_evidence = NativeReplayEvidenceStore(
            max_records=32, max_records_per_document=8
        )
        self._native_lifecycle_tombstones: dict[str, Mapping[str, Any]] = {}
        self._verified_transaction_updates: dict[str, dict[str, Any]] = {}
        self._save_notification_correlations: dict[str, deque[str]] = {}
        self._detached_clone_projection_cache: dict[
            tuple[str, str], _DetachedCloneProjection
        ] = {}
        self._detached_clone_projection_order: list[tuple[str, str]] = []

    def release_staged_replay_evidence(self, evidence_id: str) -> None:
        self._native_replay_evidence.discard(str(evidence_id))

    def validate_staged_replay_evidence(
        self,
        document_id: str,
        execution_context: Mapping[str, Any],
        *,
        before_fingerprint: str,
        after_fingerprint: str,
        capabilities: Sequence[str],
    ) -> bool:
        evidence_id = str(execution_context.get("nativeReplayEvidenceId") or "")
        if not evidence_id:
            return True
        evidence = self._native_replay_evidence.resolve(
            evidence_id, document_id=document_id
        )
        return bool(
            evidence is not None
            and evidence.before_fingerprint == str(before_fingerprint)
            and evidence.after_fingerprint == str(after_fingerprint)
            and evidence.capabilities
            == tuple(sorted(set(str(value) for value in capabilities)))
        )

    def _resolved_replay_context(
        self,
        document_id: str,
        execution_context: Mapping[str, Any] | None,
        *,
        native_restore: bool = False,
    ) -> dict[str, Any]:
        context = dict(execution_context or {})
        evidence_id = str(context.get("nativeReplayEvidenceId") or "")
        if evidence_id:
            evidence = self._native_replay_evidence.resolve(
                evidence_id, document_id=document_id
            )
            if evidence is None:
                raise HostAccessError(
                    "staged structural replay evidence is missing or expired"
                )
            context["nativeReplayTemplates"] = evidence.templates
            # Evidence contains detached copies whose exact native payload was
            # qualified on the independent verifier clone. Attaching those
            # objects is the replay operation; copying them again can create
            # fresh Glyphs-private state, especially for composite masters.
            context["reuseNativeReplayTemplates"] = True
        if native_restore:
            context["reuseNativeReplayTemplates"] = True
        return context

    def runtime_snapshot(self):
        self._cleanup_all_recovery()
        return super().runtime_snapshot()

    def scripting_runtime_safety_status(self) -> Mapping[str, Any]:
        """Return a detached, thread-safe snapshot without probing native slots."""

        return _LIVE_SOURCE_SAVE_GUARD_MANAGER.snapshot().to_dict()

    def repair_scripting_runtime(
        self,
        *,
        expected_incident_id: str | None = None,
        trigger: str = "agent",
    ) -> Mapping[str, Any]:
        """Run one bounded native repair pass on Glyphs' main thread."""

        def repair() -> Mapping[str, Any]:
            report = _LIVE_SOURCE_SAVE_GUARD_MANAGER.repair(
                trigger=str(trigger),
                expected_incident_id=expected_incident_id,
            )
            return {
                "repair": report.to_dict(),
                "scriptingRuntimeSafety": (
                    _LIVE_SOURCE_SAVE_GUARD_MANAGER.snapshot().to_dict()
                ),
            }

        return self._executor.run(repair)

    def _font_for_document(self, document_id: str) -> Any:
        for font in self._collect_fonts():
            if self._identities.resolve(self._native_identity(font)) == document_id:
                return font
        raise HostAccessError("The Glyphs document is no longer open: {}".format(document_id))

    def document_id_for_font(self, font: Any) -> str:
        return self._identities.resolve(self._native_identity(font))

    def consume_save_notification_correlation(
        self, document_id: str
    ) -> str | None:
        """Return the opaque token owned by one native save notification."""

        key = str(document_id or "")
        pending = self._save_notification_correlations.get(key)
        if not pending:
            return None
        token = pending.popleft()
        if not pending:
            self._save_notification_correlations.pop(key, None)
        return token

    def clear_save_notification_correlation(self, document_id: str) -> None:
        self._save_notification_correlations.pop(str(document_id or ""), None)

    def native_font(self, document_id: str) -> Any:
        return self._font_for_document(document_id)

    def source_path_for_document(self, document_id: str) -> str | None:
        """Capture only the current source-path identifier on the host lane."""

        def capture() -> str | None:
            value = _safe_getattr(self._font_for_document(document_id), "filepath")
            return str(value) if value else None

        return self._executor.run(capture)

    def capture_source_file_state(
        self, document_id: str, *, include_model: bool = False
    ) -> Mapping[str, Any] | None:
        """Observe persistence evidence with filesystem work off the host lane."""

        def capture_identity() -> tuple[str, tuple[str, ...]] | None:
            font = self._font_for_document(document_id)
            path_value = _safe_getattr(font, "filepath")
            if not path_value:
                return None
            instance_ids = tuple(
                str(_safe_getattr(instance, "id") or "")
                for instance in _sequence_values(_safe_getattr(font, "instances"))
            )
            return str(path_value), instance_ids

        identity = self._executor.run(capture_identity)
        if identity is None:
            return None
        path_value, instance_ids = identity
        path = Path(path_value)
        if include_model:
            observed = _SAVED_SOURCE_READER.read(path, instance_ids=instance_ids)
            state = dict(observed.state)
            if observed.snapshot is not None:
                state["savedModel"] = observed.snapshot.model
                state["savedSnapshot"] = observed.snapshot
            return state
        raw = _source_file_state(path)
        return {**dict(raw), "filePath": str(path)} if raw is not None else None

    def rebase_verified_change_tracking(
        self,
        operation_id: str,
        *,
        document_id: str,
        baseline_fingerprint: str,
        final_fingerprint: str,
        keep_contribution: bool,
    ) -> None:
        """Rebase one pending MCP contribution after a native save boundary."""

        def rebase() -> None:
            pending = getattr(self, "_document_mcp_pending_reverts", {})
            attempt = pending.get(operation_id)
            self._reset_verified_change_tracking_main_thread(document_id)
            if not keep_contribution or not isinstance(attempt, Mapping):
                return
            rebuilt = dict(attempt)
            rebuilt.update(
                {
                    "documentId": document_id,
                    "kind": "apply",
                    "removedId": None,
                    "record": {"nativeDirtyBefore": False},
                    "nativeDirtyBefore": False,
                    "verifiedDirtyBefore": False,
                    "beforeFingerprint": baseline_fingerprint,
                    "afterFingerprint": final_fingerprint,
                }
            )
            refreshed = getattr(self, "_document_mcp_pending_reverts", {})
            refreshed[operation_id] = rebuilt
            self._document_mcp_pending_reverts = refreshed

        self._executor.run(rebase)

    def save_document(
        self,
        document_id: str,
        *,
        expected_document_fingerprint: str,
        destination: Any = None,
        expected_source_file_fingerprint: Any = None,
        overwrite_policy: str = "fail_if_exists",
        expected_destination_file_fingerprint: Any = None,
        notification_correlation_token: Any = None,
        expected_snapshot: CanonicalSnapshot | None = None,
    ) -> Mapping[str, Any]:
        """Invoke NSDocument on the host thread, then prove bytes off-thread."""

        if overwrite_policy not in {"fail_if_exists", "replace_if_match"}:
            raise DocumentSaveError(
                "invalid_request", "Unsupported save overwrite policy."
            )
        if not expected_document_fingerprint:
            raise DocumentSaveError(
                "invalid_request", "expectedDocumentFingerprint is required."
            )

        def native_preflight() -> Mapping[str, Any]:
            font = self._font_for_document(document_id)
            generation = (
                self._glyphs_change_generation.current()
                if self._glyphs_change_generation is not None
                else None
            )
            revision = _document_revision_token(
                font, notification_generation=generation
            )
            if expected_snapshot is not None:
                observed_fingerprint = expected_snapshot.document_fingerprint
                expected_revision = expected_snapshot.native_revision_evidence.get(
                    "document"
                )
                if expected_revision is not None and revision != expected_revision:
                    raise DocumentSaveError(
                        "stale_document",
                        "The Glyphs document changed before the native save fence.",
                    )
            else:
                snapshot = self._capture_cached_snapshot(document_id, font)
                observed_fingerprint = snapshot.document_fingerprint
            if observed_fingerprint != str(expected_document_fingerprint):
                raise DocumentSaveError(
                    "stale_document",
                    "The Glyphs document changed before the native save fence.",
                    details={
                        "expectedDocumentFingerprint": str(
                            expected_document_fingerprint
                        ),
                        "observedDocumentFingerprint": observed_fingerprint,
                    },
                )
            path_value = _safe_getattr(font, "filepath")
            return {
                "font": font,
                "path": str(path_value) if path_value else None,
                "dirty": _document_edited_state(font),
                "documentFingerprint": observed_fingerprint,
                "revision": revision,
                "instanceIds": tuple(
                    self._instance_ids_for_font(document_id, font)
                ),
                "openPaths": tuple(
                    (
                        self._identities.resolve(self._native_identity(candidate)),
                        str(_safe_getattr(candidate, "filepath") or ""),
                    )
                    for candidate in self._collect_fonts()
                ),
            }

        initial = self._executor.run(native_preflight)
        if initial.get("dirty") is None:
            raise DocumentSaveError(
                "document_dirty_state_unavailable",
                "Glyphs did not expose a reliable document dirty state.",
            )
        previous_path_value = str(initial["path"]) if initial.get("path") else None
        previous_path = (
            Path(previous_path_value).resolve(strict=False)
            if previous_path_value is not None
            else None
        )
        if destination in (None, ""):
            if previous_path is None:
                raise DocumentSaveError(
                    "document_path_required",
                    "A pathless document requires an explicit Save As destination.",
                )
            target = _validated_save_destination(previous_path_value or "")
        else:
            target = _validated_save_destination(str(destination))
        if target.suffix.lower() not in {".glyphs", ".glyphspackage"}:
            raise DocumentSaveError(
                "unsupported_source_format",
                "Save destinations must end in .glyphs or .glyphspackage.",
            )
        mode = "save" if _same_save_path(previous_path, target) else "save_as"
        if mode == "save" and (
            overwrite_policy != "fail_if_exists"
            or expected_destination_file_fingerprint not in (None, "")
        ):
            raise DocumentSaveError(
                "invalid_request",
                "Current-path saves use expectedSourceFileFingerprint, not a destination overwrite policy.",
            )

        def reject_open_destination(
            open_paths: Sequence[tuple[Any, Any]],
        ) -> None:
            for other_document_id, other_path_value in open_paths:
                if not other_path_value or str(other_document_id) == document_id:
                    continue
                other_path = Path(str(other_path_value)).resolve(strict=False)
                if _same_save_object(other_path, target):
                    raise DocumentSaveError(
                        "destination_open_in_glyphs",
                        "The Save As destination belongs to another open Glyphs document.",
                    )
                if other_path.suffix.lower() == ".glyphspackage":
                    try:
                        target.relative_to(other_path)
                    except ValueError:
                        pass
                    else:
                        raise DocumentSaveError(
                            "destination_open_in_glyphs",
                            "The Save As destination is inside another open Glyphs package.",
                        )
                if target.suffix.lower() == ".glyphspackage":
                    try:
                        other_path.relative_to(target)
                    except ValueError:
                        pass
                    else:
                        raise DocumentSaveError(
                            "destination_open_in_glyphs",
                            "The Save As package contains another open Glyphs document.",
                        )

        def reject_open_destination_by_path(
            open_paths: Sequence[tuple[Any, Any]],
        ) -> None:
            """Protect live ownership using identifier-only host-thread reads."""

            target_path = Path(os.path.abspath(str(target)))
            for other_document_id, other_path_value in open_paths:
                if not other_path_value or str(other_document_id) == document_id:
                    continue
                other_path = Path(os.path.abspath(str(other_path_value)))
                if os.path.normcase(str(other_path)) == os.path.normcase(
                    str(target_path)
                ):
                    raise DocumentSaveError(
                        "destination_open_in_glyphs",
                        "The Save As destination belongs to another open Glyphs document.",
                    )
                if other_path.suffix.lower() == ".glyphspackage":
                    try:
                        target_path.relative_to(other_path)
                    except ValueError:
                        pass
                    else:
                        raise DocumentSaveError(
                            "destination_open_in_glyphs",
                            "The Save As destination is inside another open Glyphs package.",
                        )
                if target_path.suffix.lower() == ".glyphspackage":
                    try:
                        other_path.relative_to(target_path)
                    except ValueError:
                        pass
                    else:
                        raise DocumentSaveError(
                            "destination_open_in_glyphs",
                            "The Save As package contains another open Glyphs document.",
                        )

        reject_open_destination(initial["openPaths"])
        if previous_path is not None and previous_path.suffix.lower() == ".glyphspackage":
            try:
                target.relative_to(previous_path)
            except ValueError:
                pass
            else:
                if not _same_save_path(previous_path, target):
                    raise DocumentSaveError(
                        "invalid_destination",
                        "The Save As destination cannot be inside the current Glyphs package.",
                    )

        previous_state = (
            _normalized_source_file_state(previous_path)
            if previous_path is not None
            else None
        )
        destination_before = _normalized_source_file_state(target)
        previous_fingerprint = (
            previous_state.get("contentFingerprint")
            if previous_state is not None
            else None
        )
        destination_before_fingerprint = destination_before.get(
            "contentFingerprint"
        )
        if mode == "save":
            if not previous_state or not previous_state.get("exists") or not previous_state.get("readable"):
                raise DocumentSaveError(
                    "source_file_unavailable",
                    "The current Glyphs source is missing or unreadable.",
                )
            if not expected_source_file_fingerprint:
                raise DocumentSaveError(
                    "invalid_request",
                    "expectedSourceFileFingerprint is required for a current-path save.",
                )
            if str(expected_source_file_fingerprint) != str(previous_fingerprint):
                raise DocumentSaveError(
                    "stale_source_file",
                    "The current source file changed after it was inspected.",
                    details={
                        "observedSourceFingerprint": previous_fingerprint,
                    },
                )
        else:
            if previous_path is None and expected_source_file_fingerprint not in (None, ""):
                raise DocumentSaveError(
                    "invalid_request",
                    "A pathless document has no expectedSourceFileFingerprint.",
                )
            if previous_state is not None:
                if (
                    not previous_state.get("exists")
                    or not previous_state.get("readable")
                    or not previous_fingerprint
                ):
                    raise DocumentSaveError(
                        "source_file_unavailable",
                        "The original Glyphs source is missing or unreadable.",
                    )
                if not expected_source_file_fingerprint:
                    raise DocumentSaveError(
                        "invalid_request",
                        "expectedSourceFileFingerprint is required when Save As has an existing original source.",
                    )
            if expected_source_file_fingerprint not in (None, "") and (
                previous_fingerprint != str(expected_source_file_fingerprint)
            ):
                raise DocumentSaveError(
                    "stale_source_file",
                    "The original source file changed after it was inspected.",
                    details={
                        "observedSourceFingerprint": previous_fingerprint,
                    },
                )
            if overwrite_policy == "fail_if_exists":
                if expected_destination_file_fingerprint not in (None, ""):
                    raise DocumentSaveError(
                        "invalid_request",
                        "expectedDestinationFileFingerprint requires replace_if_match.",
                    )
                if destination_before.get("exists"):
                    raise DocumentSaveError(
                        "destination_exists",
                        "The Save As destination already exists.",
                        details={"destinationState": destination_before},
                    )
            else:
                if not destination_before.get("exists"):
                    raise DocumentSaveError(
                        "destination_missing",
                        "replace_if_match requires an existing destination.",
                    )
                if not destination_before.get("readable"):
                    raise DocumentSaveError(
                        "source_file_unavailable",
                        "The replacement destination is unreadable.",
                    )
                if not expected_destination_file_fingerprint:
                    raise DocumentSaveError(
                        "invalid_request",
                        "expectedDestinationFileFingerprint is required for replace_if_match.",
                    )
                if str(expected_destination_file_fingerprint) != str(
                    destination_before_fingerprint
                ):
                    raise DocumentSaveError(
                        "stale_destination",
                        "The replacement destination fingerprint does not match.",
                        details={"destinationState": destination_before},
                    )

        # Re-read immediately before entering the non-cancellable native call.
        before_native = self._executor.run(native_preflight)
        if (
            before_native.get("revision") != initial.get("revision")
            or before_native.get("path") != initial.get("path")
            or before_native.get("documentFingerprint")
            != str(expected_document_fingerprint)
        ):
            raise DocumentSaveError(
                "stale_document",
                "The Glyphs document changed during save preflight.",
            )
        destination_now = _normalized_source_file_state(target)
        if destination_now != destination_before:
            raise DocumentSaveError(
                "stale_source_file" if mode == "save" else "stale_destination",
                (
                    "The current source file changed during save preflight."
                    if mode == "save"
                    else "The Save As destination changed during save preflight."
                ),
                details={
                    (
                        "observedSourceState"
                        if mode == "save"
                        else "destinationState"
                    ): destination_now
                },
            )
        if mode == "save_as" and previous_path is not None and previous_state is not None:
            original_now = _normalized_source_file_state(previous_path)
            if original_now != previous_state:
                raise DocumentSaveError(
                    "stale_source_file",
                    "The original source file changed immediately before Save As.",
                    details={"observedSourceState": original_now},
                )
        reject_open_destination(before_native["openPaths"])

        def native_save() -> Mapping[str, Any]:
            font = self._font_for_document(document_id)
            generation = (
                self._glyphs_change_generation.current()
                if self._glyphs_change_generation is not None
                else None
            )
            revision = _document_revision_token(
                font, notification_generation=generation
            )
            path_value = _safe_getattr(font, "filepath")
            current_path = str(path_value) if path_value else None
            if revision != before_native.get("revision") or current_path != before_native.get("path"):
                raise DocumentSaveError(
                    "stale_document",
                    "The Glyphs document changed before the native save began.",
                )
            reject_open_destination_by_path(
                tuple(
                    (
                        self._identities.resolve(
                            self._native_identity(candidate)
                        ),
                        str(_safe_getattr(candidate, "filepath") or ""),
                    )
                    for candidate in self._collect_fonts()
                )
            )
            document = _maybe_call(_safe_getattr(font, "parent"))
            selector = _safe_getattr(
                document, "saveToURL_ofType_forSaveOperation_error_"
            )
            if not callable(selector):
                raise DocumentSaveError(
                    "native_save_failed",
                    "Glyphs did not expose the synchronous NSDocument save selector.",
                )
            try:
                from Foundation import NSURL  # type: ignore[import-not-found]
                try:
                    from AppKit import (  # type: ignore[import-not-found]
                        NSSaveAsOperation,
                        NSSaveOperation,
                    )
                except Exception:
                    NSSaveOperation = 0
                    NSSaveAsOperation = 1
                type_name = (
                    "com.glyphsapp.glyphspackage"
                    if target.suffix.lower() == ".glyphspackage"
                    else "com.schriftgestaltung.glyphs"
                )
                operation = (
                    NSSaveOperation if mode == "save" else NSSaveAsOperation
                )
            except Exception as exc:
                raise DocumentSaveError(
                    "native_save_failed",
                    "Glyphs native save constants are unavailable.",
                    details={"exceptionType": type(exc).__name__},
                ) from exc

            correlation_token = str(notification_correlation_token or "")
            if correlation_token:
                pending = self._save_notification_correlations.setdefault(
                    document_id, deque(maxlen=8)
                )
                if correlation_token not in pending:
                    pending.append(correlation_token)

            native_error_message = None
            native_error_details: dict[str, Any] = {}
            try:
                result = selector(
                    NSURL.fileURLWithPath_(str(target)),
                    type_name,
                    operation,
                    None,
                )
            except Exception as exc:
                native_error_message = (
                    "Glyphs raised while performing the native document save."
                )
                native_error_details = {"exceptionType": type(exc).__name__}
            else:
                native_error_message = _native_save_error(result)
            final_path_value = _safe_getattr(font, "filepath")
            return {
                "path": str(final_path_value) if final_path_value else None,
                "dirty": _document_edited_state(font),
                "nativeSaveSucceeded": native_error_message is None,
                "nativeErrorMessage": native_error_message,
                "nativeErrorDetails": native_error_details,
            }

        native_after = self._executor.run(native_save)
        final_path = (
            Path(str(native_after.get("path"))).resolve(strict=False)
            if native_after.get("path")
            else None
        )
        path_changed = bool(
            final_path is not None
            and (previous_path is None or not _same_save_path(previous_path, final_path))
        )

        def observed_source_state(path: Path | None) -> Mapping[str, Any] | None:
            if path is None:
                return None
            try:
                return _normalized_source_file_state(path)
            except DocumentSaveError as exc:
                return {
                    "kind": (
                        "glyphspackage"
                        if path.suffix.lower() == ".glyphspackage"
                        else "glyphs"
                    ),
                    "exists": bool(path.exists()),
                    "readable": False,
                    "contentFingerprint": None,
                    "observationErrorCode": exc.code,
                }
            except Exception as exc:
                return {
                    "kind": (
                        "glyphspackage"
                        if path.suffix.lower() == ".glyphspackage"
                        else "glyphs"
                    ),
                    "exists": bool(path.exists()),
                    "readable": False,
                    "contentFingerprint": None,
                    "observationErrorType": type(exc).__name__,
                }

        saved_read = _SAVED_SOURCE_READER.read(
            target,
            instance_ids=tuple(initial.get("instanceIds") or ()),
        )
        saved_state = {
            key: value
            for key, value in dict(saved_read.state).items()
            if key != "filePath"
        }
        original_after = (
            observed_source_state(previous_path)
            if previous_path is not None
            else None
        )
        native_save_succeeded = native_after.get("nativeSaveSucceeded") is True
        destination_state_changed = saved_state != destination_before
        post_write_details = {
            "nativeSaveSucceeded": native_save_succeeded,
            "fontSaved": bool(
                native_save_succeeded or destination_state_changed
            ),
            "saveMode": mode,
            "expectedFilePath": str(target),
            "observedFilePath": str(final_path) if final_path else None,
            "pathChanged": path_changed,
            "dirtyAfter": native_after.get("dirty"),
            "destinationChanged": destination_state_changed,
            "destinationStateBefore": destination_before,
            "destinationStateAfter": saved_state,
            "originalSourceStateBefore": previous_state,
            "originalSourceStateAfter": original_after,
            **dict(native_after.get("nativeErrorDetails") or {}),
        }

        if not native_save_succeeded:
            raise DocumentSaveError(
                "save_verification_failed",
                str(
                    native_after.get("nativeErrorMessage")
                    or "The native save did not report verified success."
                ),
                recoverable=False,
                details=post_write_details,
                write_attempted=True,
            )

        def post_write(callback: Callable[[], Any]) -> Any:
            try:
                return callback()
            except DocumentSaveError as exc:
                raise DocumentSaveError(
                    "save_verification_failed",
                    exc.message,
                    recoverable=False,
                    details={
                        **post_write_details,
                        "verificationErrorCode": exc.code,
                        **dict(exc.details),
                    },
                    write_attempted=True,
                ) from exc
            except Exception as exc:
                raise DocumentSaveError(
                    "save_verification_failed",
                    "The native save succeeded, but post-save verification failed.",
                    recoverable=False,
                    details={
                        **post_write_details,
                        "exceptionType": type(exc).__name__,
                    },
                    write_attempted=True,
                ) from exc

        if final_path is None or not _same_save_path(final_path, target):
            raise DocumentSaveError(
                "save_verification_failed",
                "Glyphs did not retain the expected document path after saving.",
                recoverable=False,
                details=post_write_details,
                write_attempted=True,
            )
        if (
            not saved_state.get("exists")
            or not saved_state.get("readable")
            or not saved_state.get("contentFingerprint")
        ):
            raise DocumentSaveError(
                "save_verification_failed",
                "The saved Glyphs source is missing or unreadable.",
                recoverable=False,
                details=post_write_details,
                write_attempted=True,
            )
        original_source_unchanged: bool | None = None
        if mode == "save_as" and previous_path is not None and previous_state is not None:
            original_source_unchanged = original_after == previous_state
        saved_model = (
            saved_read.snapshot.model
            if saved_read.snapshot is not None
            else None
        )
        if not isinstance(saved_model, Mapping):
            raise DocumentSaveError(
                "save_verification_failed",
                "The saved source could not be decoded through the canonical source adapter.",
                recoverable=False,
                details=post_write_details,
                write_attempted=True,
            )

        def validate_native_save_state() -> None:
            font = self._font_for_document(document_id)
            if _document_edited_state(font) is not False:
                raise DocumentSaveError(
                    "save_verification_failed",
                    "Glyphs still reports unsaved document changes after saving.",
                    recoverable=False,
                    details={"nativeSaveSucceeded": True, "fontSaved": True},
                    write_attempted=True,
                )

        post_write(lambda: self._executor.run(validate_native_save_state))
        post_write(lambda: self._canonical_model_cache.invalidate(document_id))
        saved_fingerprint = saved_state.get("contentFingerprint")
        return {
            "saveMode": mode,
            "previousFilePath": str(previous_path) if previous_path else None,
            "filePath": str(target),
            "fileKind": saved_state["kind"],
            "overwritePolicy": overwrite_policy,
            "previousSourceFingerprint": previous_fingerprint,
            "destinationBeforeFingerprint": destination_before_fingerprint,
            "savedSourceFingerprint": saved_fingerprint,
            "replacedDestinationFingerprint": (
                destination_before_fingerprint
                if mode == "save_as" and overwrite_policy == "replace_if_match"
                else None
            ),
            "dirtyBefore": bool(initial.get("dirty")),
            "dirtyAfter": False,
            "pathChanged": path_changed,
            "originalSourceUnchanged": original_source_unchanged,
            "destinationChanged": (
                destination_before_fingerprint != saved_fingerprint
                or not destination_before.get("exists")
            ),
            "nativeSaveSucceeded": True,
            "savedModel": saved_model,
            "savedSnapshot": saved_read.snapshot,
        }

    def force_document_dirty(self, document_id: str) -> None:
        """Keep an observed but unverified live mutation visibly dirty."""

        def force() -> None:
            font = self._font_for_document(document_id)
            if _document_edited_state(font) is not True:
                self._native_change_count(font, _NS_CHANGE_DONE)
            overrides = getattr(self, "_document_dirty_overrides", {})
            overrides[document_id] = True
            self._document_dirty_overrides = overrides

        self._executor.run(force)

    def inspect_glyph_metadata(
        self,
        document_id: str,
        glyph_names: Sequence[str] = (),
    ) -> Mapping[str, Mapping[str, Any]]:
        """Read effective native GlyphData-backed values without canonicalizing them."""

        def inspect() -> Mapping[str, Mapping[str, Any]]:
            font = self._font_for_document(document_id)
            return self._inspect_glyph_metadata_in_font(font, glyph_names)

        return self._executor.run(inspect)

    @staticmethod
    def _inspect_glyph_metadata_in_font(
        font: Any,
        glyph_names: Sequence[str] = (),
    ) -> Mapping[str, Mapping[str, Any]]:
        """Collect effective GlyphData-backed values from any font instance."""

        requested = {str(name) for name in glyph_names if str(name)}
        result: dict[str, Mapping[str, Any]] = {}
        for glyph in _sequence_values(_safe_getattr(font, "glyphs")):
            name = str(_safe_getattr(glyph, "name") or "")
            if not name or (requested and name not in requested):
                continue
            result[name] = {
                "name": name,
                "export": bool(_maybe_call(_safe_getattr(glyph, "export", True))),
                "category": _plain_scalar(_safe_getattr(glyph, "category")),
                "subCategory": _plain_scalar(_safe_getattr(glyph, "subCategory")),
                "script": _plain_scalar(_safe_getattr(glyph, "script")),
            }
        return result

    def inspect_layers(
        self,
        document_id: str,
        glyph_names: Sequence[str] = (),
        *,
        include_metrics: bool = False,
        resolve_metrics: bool = False,
        include_geometry: bool = False,
    ) -> Mapping[tuple[str, str], Mapping[str, Any]]:
        """Read non-canonical layer observations from one detached font copy."""

        def inspect() -> Mapping[tuple[str, str], Mapping[str, Any]]:
            font = self._font_for_document(document_id)
            return self._inspect_layers_in_font(
                font,
                glyph_names,
                include_metrics=include_metrics,
                resolve_metrics=resolve_metrics,
                include_geometry=include_geometry,
            )

        return self._executor.run(inspect)

    def _inspect_layers_in_font(
        self,
        font: Any,
        glyph_names: Sequence[str] = (),
        *,
        include_metrics: bool = False,
        resolve_metrics: bool = False,
        include_geometry: bool = False,
    ) -> Mapping[tuple[str, str], Mapping[str, Any]]:
        """Collect the same observations from a live font or detached clone."""

        requested = {str(name) for name in glyph_names if str(name)}
        metrics_clone = None
        if resolve_metrics:
            copier = _safe_getattr(font, "copy")
            if not callable(copier):
                raise HostAccessError("Glyphs did not provide GSFont.copy()")
            metrics_clone = copier()
            if metrics_clone is None:
                raise HostAccessError("Glyphs returned no detached font copy")
        result: dict[tuple[str, str], Mapping[str, Any]] = {}
        for glyph in _sequence_values(_safe_getattr(font, "glyphs")):
            glyph_name = str(_safe_getattr(glyph, "name") or "")
            if not glyph_name or (requested and glyph_name not in requested):
                continue
            clone_glyph = (
                _lookup_by_name(_safe_getattr(metrics_clone, "glyphs"), glyph_name)
                if metrics_clone is not None
                else None
            )
            clone_layers = (
                _native_layer_index(clone_glyph) if clone_glyph is not None else {}
            )
            for layer_id, layer in _native_layer_index(glyph).items():
                observation: dict[str, Any] = {
                    "hasAlignedWidth": bool(
                        _maybe_call(_safe_getattr(layer, "hasAlignedWidth", False))
                    ),
                    "isAligned": bool(
                        _maybe_call(_safe_getattr(layer, "isAligned", False))
                    ),
                }
                if include_metrics or resolve_metrics:
                    observation["currentMetrics"] = _observed_layer_metrics(layer)
                if resolve_metrics:
                    detached_layer = clone_layers.get(layer_id)
                    if detached_layer is None:
                        raise HostAccessError(
                            "The detached font omitted layer {}/{}".format(
                                glyph_name, layer_id
                            )
                        )
                    sync = _safe_getattr(detached_layer, "syncMetrics")
                    if not callable(sync):
                        raise HostAccessError(
                            "Glyphs did not expose GSLayer.syncMetrics()"
                        )
                    sync()
                    observation["resolvedMetrics"] = _observed_layer_metrics(
                        detached_layer
                    )
                if include_geometry:
                    observation["bounds"] = _observed_layer_bounds(layer)
                result[(glyph_name, layer_id)] = observation
        return result

    def inspect_compilation_diagnostics(
        self, document_id: str
    ) -> Mapping[str, Any]:
        """Compile one detached font copy and report bounded diagnostics."""

        def inspect() -> Mapping[str, Any]:
            font = self._font_for_document(document_id)
            copier = _safe_getattr(font, "copy")
            if not callable(copier):
                raise HostAccessError("Glyphs did not provide GSFont.copy()")
            clone = copier()
            if clone is None:
                raise HostAccessError("Glyphs returned no detached font copy")
            return self._inspect_compilation_in_font(clone)

        return self._executor.run(inspect)

    @staticmethod
    def _inspect_compilation_in_font(font: Any) -> Mapping[str, Any]:
        """Compile the supplied detached font and return bounded diagnostics."""

        detached_compile = _safe_getattr(font, "compileFeatures")
        if not callable(detached_compile):
            raise HostAccessError("Glyphs did not provide GSFont.compileFeatures()")
        try:
            detached_compile()
        except Exception as error:
            return {
                "succeeded": False,
                "errorType": type(error).__name__,
                "errorMessage": str(error)[:1000],
                "detached": True,
                "liveAttempted": False,
            }
        return {
            "succeeded": True,
            "errorType": None,
            "errorMessage": None,
            "detached": True,
            "liveAttempted": False,
        }

    def _document_activation_state_on_main(
        self, document_id: str, font: Any
    ) -> Mapping[str, Any]:
        """Compare both public Glyphs active-document signals by native identity."""

        current_document = _maybe_call(
            _safe_getattr(self._app, "currentDocument")
        )
        current_font = _maybe_call(_safe_getattr(current_document, "font"))
        active_font = _maybe_call(_safe_getattr(self._app, "font"))

        def matches(candidate: Any) -> bool:
            if candidate is None:
                return False
            try:
                return self._native_identity(candidate) == self._native_identity(
                    font
                )
            except Exception:
                return candidate is font

        def resolved_document_id(candidate: Any) -> str | None:
            if candidate is None:
                return None
            try:
                return self._identities.resolve(self._native_identity(candidate))
            except Exception:
                return None

        current_document_id = resolved_document_id(current_font)
        active_font_document_id = resolved_document_id(active_font)
        current_matches = matches(current_font)
        active_font_matches = matches(active_font)
        return {
            "documentId": document_id,
            "active": current_matches and active_font_matches,
            "activeDocumentId": current_document_id,
            "activeFontDocumentId": active_font_document_id,
            "currentDocumentMatchesTarget": current_matches,
            "activeFontMatchesTarget": active_font_matches,
            "signalsAgree": current_document_id == active_font_document_id,
        }

    def document_activation_state(self, document_id: str) -> Mapping[str, Any]:
        """Read bounded active-document evidence on Glyphs' main thread."""

        def capture() -> Mapping[str, Any]:
            font = self._font_for_document(document_id)
            return self._document_activation_state_on_main(document_id, font)

        return self._executor.run(capture)

    @staticmethod
    def _activation_error(method: str, error: Exception) -> str:
        return "{} failed with {}: {}".format(
            method, type(error).__name__, str(error)[:500]
        )

    def _activate_font_window(self, font: Any) -> Mapping[str, Any]:
        """Bring one already-open font window forward without touching font data."""

        methods: list[str] = []
        errors: list[str] = []
        document = _maybe_call(_safe_getattr(font, "parent"))
        controller = _maybe_call(_safe_getattr(document, "windowController"))

        showed_window = False
        show_window = _safe_getattr(controller, "showWindow_")
        if callable(show_window):
            try:
                show_window(None)
                methods.append("document.windowController.showWindow_")
                showed_window = True
            except Exception as error:
                errors.append(
                    self._activation_error(
                        "document.windowController.showWindow_", error
                    )
                )

        if not showed_window:
            show_font = _safe_getattr(font, "show")
            if callable(show_font):
                try:
                    show_font()
                    methods.append("font.show")
                    showed_window = True
                except Exception as error:
                    errors.append(self._activation_error("font.show", error))

        window = _maybe_call(_safe_getattr(controller, "window"))
        make_key = _safe_getattr(window, "makeKeyAndOrderFront_")
        if callable(make_key):
            try:
                make_key(None)
                methods.append("window.makeKeyAndOrderFront_")
            except Exception as error:
                errors.append(
                    self._activation_error("window.makeKeyAndOrderFront_", error)
                )

        if not methods and not errors:
            errors.append(
                "Glyphs did not expose a document window activation method."
            )
        return {
            "activationAttempted": True,
            "activationMethods": methods,
            "activationErrors": errors,
        }

    def open_edit_tab(
        self,
        document_id: str,
        glyph_names: Sequence[str],
        *,
        master_id: Optional[str] = None,
        activate_document: bool = False,
    ) -> Mapping[str, Any]:
        """Resolve every target, open one Edit tab, and optionally activate it."""

        def open_tab() -> Mapping[str, Any]:
            font = self._font_for_document(document_id)
            if master_id and _master_by_id(font, master_id) is None:
                raise HostAccessError(
                    "The requested Glyphs master is no longer available."
                )
            resolved = []
            missing = []
            for name in glyph_names:
                glyph = _lookup_by_name(_safe_getattr(font, "glyphs"), name)
                layer = (
                    _edit_layer_for_glyph(font, glyph, master_id)
                    if glyph is not None
                    else None
                )
                if layer is None:
                    missing.append(name)
                else:
                    resolved.append(layer)
            if missing:
                raise HostAccessError(
                    "Glyphs target(s) disappeared before opening the tab: {}.".format(
                        ", ".join(missing)
                    )
                )
            opener = _safe_getattr(font, "newTab")
            if not callable(opener):
                raise HostAccessError("Glyphs did not provide GSFont.newTab().")
            opener(resolved)
            activation = (
                self._activate_font_window(font)
                if activate_document
                else {
                    "activationAttempted": False,
                    "activationMethods": [],
                    "activationErrors": [],
                }
            )
            return {
                "glyphNames": list(glyph_names),
                "masterId": master_id,
                **activation,
            }

        return self._executor.run(open_tab)

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
        return self._capture_cached_snapshot(document_id, font).materialize()

    def _capture_cached_snapshot(
        self,
        document_id: str,
        font: Any,
        *,
        expected: CanonicalSnapshot | None = None,
        defer_persistent_assembly: bool = False,
    ) -> CanonicalSnapshot | _PersistentCaptureDraft:
        def revision() -> tuple[Any, ...] | None:
            generation = self._glyphs_change_generation
            return _document_revision_token(
                font,
                notification_generation=(
                    generation.current() if generation is not None else None
                ),
            )

        return self._canonical_model_cache.capture_snapshot(
            document_id,
            font,
            instance_ids=self._instance_ids_for_font(document_id, font),
            expected=expected,
            revision_provider=revision,
            defer_persistent_assembly=defer_persistent_assembly,
        )

    def _capture_snapshot_coordinated(
        self,
        document_id: str,
        *,
        expected: CanonicalSnapshot | None = None,
    ) -> CanonicalSnapshot:
        """Keep native reads bounded on main; assemble detached trees on worker."""

        captured = self._executor.run(
            lambda: self._capture_cached_snapshot(
                document_id,
                self._font_for_document(document_id),
                expected=expected,
                defer_persistent_assembly=True,
            )
        )
        if isinstance(captured, _PersistentCaptureDraft):
            return self._canonical_model_cache.finalize_persistent_capture(captured)
        return captured

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

    def _capture_removed_layer_templates(
        self,
        font: Any,
        current: Mapping[str, Any],
        target: Mapping[str, Any],
    ) -> dict[str, Any]:
        current_glyphs = current.get("glyphs", {})
        target_glyphs = target.get("glyphs", {})
        if not isinstance(current_glyphs, Mapping) or not isinstance(
            target_glyphs, Mapping
        ):
            return {}
        native_glyphs = {
            str(_safe_getattr(glyph, "name") or ""): glyph
            for glyph in _sequence_values(_safe_getattr(font, "glyphs"))
            if str(_safe_getattr(glyph, "name") or "")
        }
        result: dict[str, Any] = {}
        for glyph_name in sorted(set(current_glyphs) & set(target_glyphs)):
            before_order, before_layers = _canonical_layer_collection(
                current_glyphs[glyph_name]
            )
            _, after_layers = _canonical_layer_collection(target_glyphs[glyph_name])
            for identity in before_order:
                if identity in after_layers or bool(
                    before_layers[identity].get("isMasterLayer")
                ):
                    continue
                native = _lookup_layer(native_glyphs.get(glyph_name), identity)
                if native is None:
                    raise HostAccessError(
                        "Glyphs could not snapshot removed layer {}/{}".format(
                            glyph_name, identity
                        )
                    )
                # The detached copy is safe for clone simulation; the exact
                # live object is retained separately so same-process revert
                # restores hints, backgrounds, images, guides, and private
                # native payload without canonical reconstruction.
                result["{}/{}".format(glyph_name, identity)] = {
                    "copy": _copy_native_object(native, kind="layer"),
                    "native": native,
                }
        return result

    def _layer_restore_templates(
        self,
        contribution_id: Optional[str],
        *,
        native: bool,
    ) -> Mapping[str, Any]:
        if not contribution_id:
            return {}
        record = self._layer_lifecycle_tombstones.get(str(contribution_id), {})
        templates = record.get("templates", {}) if isinstance(record, Mapping) else {}
        if not isinstance(templates, Mapping):
            return {}
        key = "native" if native else "copy"
        return {
            str(identity): value.get(key)
            for identity, value in templates.items()
            if isinstance(value, Mapping) and value.get(key) is not None
        }

    def _capture_removed_native_templates(
        self,
        font: Any,
        current: Mapping[str, Any],
        target: Mapping[str, Any],
    ) -> dict[tuple[str, ...], Mapping[str, Any]]:
        """Capture every removed registered entity through one path registry."""

        result: dict[tuple[str, ...], Mapping[str, Any]] = {}
        for master_id, value in self._capture_removed_master_templates(
            font, current, target
        ).items():
            result[("masters", master_id)] = {
                "copy": {
                    "master": value.get("master"),
                    "layers": value.get("layers", {}),
                },
                "native": {
                    "master": value.get("nativeMaster"),
                    "layers": value.get("nativeLayers", {}),
                },
            }
        for key, value in self._capture_removed_layer_templates(
            font, current, target
        ).items():
            glyph_name, layer_id = key.split("/", 1)
            result[("glyphs", glyph_name, "layers", layer_id)] = value

        current_glyphs = current.get("glyphs", {})
        target_glyphs = target.get("glyphs", {})
        if isinstance(current_glyphs, Mapping) and isinstance(
            target_glyphs, Mapping
        ):
            for glyph_name in sorted(set(current_glyphs) - set(target_glyphs)):
                glyph = _lookup_by_name(_safe_getattr(font, "glyphs"), glyph_name)
                if glyph is None:
                    raise HostAccessError(
                        "Glyphs could not snapshot removed glyph {}".format(
                            glyph_name
                        )
                    )
                result[("glyphs", glyph_name)] = {
                    "copy": _copy_native_object(glyph, kind="glyph"),
                    "native": glyph,
                }

        for root, attribute, kind in (
            ("instances", "instances", "instance"),
            ("features", "features", "feature"),
            ("classes", "classes", "class"),
            ("featurePrefixes", "featurePrefixes", "feature prefix"),
        ):
            current_order = collection_order(current.get(root, []))
            target_order = set(collection_order(target.get(root, [])))
            native_values = _sequence_values(_safe_getattr(font, attribute))
            if len(current_order) != len(native_values):
                raise HostAccessError(
                    "Glyphs {} collection diverged before tombstone capture".format(
                        kind
                    )
                )
            for index, identity in enumerate(current_order):
                if identity in target_order:
                    continue
                native = native_values[index]
                result[(root, identity)] = {
                    "copy": _copy_native_object(native, kind=kind),
                    "native": native,
                }
        return result

    def _native_restore_templates(
        self, contribution_id: Optional[str], *, native: bool
    ) -> dict[tuple[str, ...], Any]:
        if not contribution_id:
            return {}
        record = self._native_lifecycle_tombstones.get(
            str(contribution_id), {}
        )
        templates = record.get("templates", {}) if isinstance(record, Mapping) else {}
        key = "native" if native else "copy"
        return {
            tuple(path): value.get(key)
            for path, value in dict(templates).items()
            if isinstance(value, Mapping) and value.get(key) is not None
        }

    def _cached_open_models(self) -> dict[str, Mapping[str, Any]]:
        return {
            document_id: self._capture_cached_snapshot(document_id, font)
            for font in self._collect_fonts()
            for document_id in (
                self._identities.resolve(self._native_identity(font)),
            )
        }

    def _stable_open_models(self) -> dict[str, Mapping[str, Any]]:
        """Capture every open document after yielding the Cocoa main queue.

        Open-world Python executes in one bounded main-thread callback. Glyphs
        can enqueue derived document updates while that callback is running,
        so an after-model captured inside the same callback can describe an
        intermediate state. Resolve the document identities on the main
        thread, then use the ordinary stable-capture boundary from the MCP
        worker. Each read is consequently a separate main-queue turn and the
        canonical result must agree across two observations.
        """

        document_ids = self._executor.run(
            lambda: tuple(
                self._identities.resolve(self._native_identity(font))
                for font in self._collect_fonts()
            )
        )
        result: dict[str, Mapping[str, Any]] = {}
        for document_id in document_ids:
            try:
                result[document_id] = self.capture_stable_snapshot(document_id)
            except HostAccessError:
                # An open-world script may close a document. Its absence from
                # the after mapping is itself the observed scope change.
                continue
        return result

    def capture_model(self, document_id: str) -> Mapping[str, Any]:
        return self._capture_snapshot_coordinated(document_id).materialize()

    def capture_snapshot(self, document_id: str) -> CanonicalSnapshot:
        return self._capture_snapshot_coordinated(document_id)

    def capture_stable_model(self, document_id: str) -> Mapping[str, Any]:
        return self.capture_stable_snapshot(document_id).materialize()

    def capture_stable_snapshot(
        self,
        document_id: str,
        *,
        expected_snapshot: CanonicalSnapshot | None = None,
    ) -> CanonicalSnapshot:
        """Capture a canonical tree only after two host readbacks agree.

        Glyphs may resolve metrics and other derived layer state on a later
        application-loop turn after a setter returns. The pause happens on the
        MCP worker, never inside Reporter drawing or the main-thread callback.
        A transaction must fail rather than publish an unstable fingerprint.
        """

        def capture() -> CanonicalSnapshot:
            return self._capture_snapshot_coordinated(
                document_id,
                expected=expected_snapshot,
            )

        quiet_window_seconds = 0.100
        previous = capture()
        previous_fingerprint = fingerprint_model(previous)
        # The settlement budget measures change *after* the first complete
        # observation. A forced persistent capture can legitimately exceed
        # the quiet-window budget on a substantial font; starting the clock
        # before it would skip the confirming readback and make a still-open
        # document look as though it disappeared after live Python.
        deadline = time.monotonic() + 0.750
        while time.monotonic() + quiet_window_seconds <= deadline:
            time.sleep(quiet_window_seconds)
            current = capture()
            current_fingerprint = fingerprint_model(current)
            if current_fingerprint == previous_fingerprint:
                return current
            previous = current
            previous_fingerprint = current_fingerprint
        raise HostAccessError(
            "Glyphs canonical state did not settle across bounded readbacks"
        )

    @staticmethod
    def _capture_detached_model(
        font: Any,
        source: Mapping[str, Any],
        *,
        scope: MutationScope | None = None,
        impact: CanonicalImpact | None = None,
        instance_ids: Sequence[str] = (),
        document_path: Any = None,
    ) -> Mapping[str, Any]:
        """Capture a clone through the same canonical source boundary.

        A scoped capture still refreshes every non-glyph root, but materializes
        only the glyph fragments needed by the planned operation. Open-world
        staged execution passes no scope and receives the complete model.
        """

        if document_path in (None, ""):
            document_path = _canonical_document_path(source)
        if scope is None:
            complete = _native_persistent_font_model(
                font,
                instance_ids=instance_ids,
                document_path=document_path,
            )
            if complete is not None:
                _project_persistent_layer_order(complete, source)
                return complete
            return native_font_to_model(
                font,
                instance_ids=instance_ids,
                layer_order_reference_model=source,
                document_path=document_path,
            )
        return _scoped_font_model(
            font,
            source,
            scope,
            impact=impact,
            instance_ids=instance_ids,
            expected_model=source,
        )

    def _reconcile_detached_clone(
        self,
        font: Any,
        source: Mapping[str, Any],
        observed: Mapping[str, Any],
        *,
        document_id: str = "",
        instance_ids: Sequence[str] = (),
        allow_cached_projection: bool = True,
        observed_is_complete: bool = False,
    ) -> tuple[Mapping[str, Any], _DetachedCloneProjection]:
        """Project an untouched ``GSFont.copy()`` onto its canonical source.

        Glyphs can omit writable saved values while cloning (for example a
        special layer's explicit visibility), or synthesize default hint
        indexes. Record those values as a three-way projection instead of
        replaying unrelated setters into the clone. Collection membership,
        order loss, and unsupported/private changes remain hard failures.
        """

        source_fingerprint = fingerprint_model(source)
        cache_key = (str(document_id), source_fingerprint)
        cached_projection = (
            self._detached_clone_projection_cache.get(cache_key)
            if (
                allow_cached_projection
                and document_id
                and isinstance(source, CanonicalSnapshot)
            )
            else None
        )
        if cached_projection is not None:
            return source, cached_projection
        if isinstance(source, CanonicalSnapshot):
            if document_id and not observed_is_complete:
                # A scoped clone capture can share every unpredicted glyph
                # shard with ``source`` and therefore hide copy-only changes
                # until a later native revision happens to expose that glyph.
                # Learn the complete artifact set once for each exact document
                # state through Glyphs' native format-v4 serializer. Repeated
                # states (notably selective reverts) reuse the immutable
                # projection. A different third value is never normalized by
                # ``_DetachedCloneProjection``.
                complete_observed = _native_persistent_font_model(
                    font,
                    instance_ids=instance_ids,
                    document_path=_canonical_document_path(source),
                )
                if complete_observed is None:
                    complete_observed = native_font_to_model(
                        font,
                        instance_ids=instance_ids,
                        layer_order_reference_model=source,
                        document_path=_canonical_document_path(source),
                    )
                else:
                    _project_persistent_layer_order(complete_observed, source)
                observed = rebase_canonical_model(source, complete_observed)
            # Rebase the clone onto immutable source shards before diffing.
            # Unchanged glyphs then compare by identity and retain their cached
            # encodings instead of rebuilding a projected whole-font tree.
            forward = diff_models(source, observed)
            identity_changes = tuple(
                change
                for change in forward.changes
                if is_semantic_identity_path(change.path)
            )
            reconciliation = ChangeSet.from_changes(
                before_fingerprint=forward.after_fingerprint,
                after_fingerprint=forward.before_fingerprint,
                changes=(change.inverse() for change in identity_changes),
            )
        else:
            observed_fingerprint = fingerprint_model(observed)
            reconciliation = None
        if (
            (isinstance(source, CanonicalSnapshot) and not reconciliation.changes)
            or (
                not isinstance(source, CanonicalSnapshot)
                and observed_fingerprint == source_fingerprint
            )
        ):
            empty = ChangeSet.from_changes(
                before_fingerprint=source_fingerprint,
                after_fingerprint=source_fingerprint,
                changes=(),
            )
            return source, _DetachedCloneProjection(empty)

        if reconciliation is None:
            reconciliation = diff_models(
                semantic_identity_document(observed),
                semantic_identity_document(source),
            )
        if os.environ.get("GLYPHS_MCP_DEBUG_CAPTURE"):
            print(
                "[Glyphs MCP][DetachedSimulation] clone reconciliation "
                "changes={} firstPaths={}".format(
                    len(reconciliation.changes),
                    [list(change.path) for change in reconciliation.changes[:12]],
                ),
                flush=True,
            )
            for change in reconciliation.changes[:12]:
                print(
                    "[Glyphs MCP][DetachedSimulation] path={} before={!r} after={!r}".format(
                        list(change.path), change.before, change.after
                    )[:1200],
                    flush=True,
                )
        # Clone projection owns every nonstructural canonical field. Public
        # lifecycle capabilities still gate requested mutations, while this
        # structural check prevents normalization from inventing collection
        # membership or order evidence.
        normalization_capabilities = (
            CANONICAL_LIFECYCLE_CAPABILITY,
            MASTER_LIFECYCLE_CAPABILITY,
            LAYER_LIFECYCLE_CAPABILITY,
        )
        structural = [
            change.path
            for change in reconciliation.changes
            if is_structural_change_path(change.path)
        ]
        if structural or not self.supports_change_set(
            reconciliation,
            capabilities=normalization_capabilities,
        ):
            paths = structural or [
                change.path for change in reconciliation.changes
            ]
            raise HostAccessError(
                "Detached GSFont.copy() lost unsupported canonical state "
                "({} changes; first paths: {})".format(
                    len(reconciliation.changes),
                    [list(path) for path in paths[:12]],
                )
            )

        projection = _DetachedCloneProjection(reconciliation)
        if isinstance(source, CanonicalSnapshot):
            # ``diff_models`` proves the complete forward transition and an
            # inverse is exact by construction. Later clone captures still use
            # the projection's three-way checks so a requested or unexpected
            # third value can never be hidden.
            if document_id and allow_cached_projection:
                self._detached_clone_projection_cache[cache_key] = projection
                try:
                    self._detached_clone_projection_order.remove(cache_key)
                except ValueError:
                    pass
                self._detached_clone_projection_order.append(cache_key)
                while len(self._detached_clone_projection_order) > 16:
                    expired = self._detached_clone_projection_order.pop(0)
                    self._detached_clone_projection_cache.pop(expired, None)
            return source, projection
        normalized = projection.normalize(observed)
        if fingerprint_model(normalized) != source_fingerprint:
            residual = diff_models(normalized, source)
            raise HostAccessError(
                "Detached GSFont.copy() could not be projected onto its "
                "canonical source ({} residual changes; first paths: {})".format(
                    len(residual.changes),
                    [list(change.path) for change in residual.changes[:12]],
                )
            )
        return source, projection

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
            simulation_started = time.perf_counter()

            def debug_simulation(stage: str, **details: Any) -> None:
                if not os.environ.get("GLYPHS_MCP_DEBUG_CAPTURE"):
                    return
                suffix = " ".join(
                    "{}={}".format(name, value)
                    for name, value in sorted(details.items())
                )
                print(
                    "[Glyphs MCP][DetachedSimulation] document={} stage={} elapsedMs={:.1f} {}".format(
                        document_id,
                        stage,
                        (time.perf_counter() - simulation_started) * 1000.0,
                        suffix,
                    ),
                    flush=True,
                )

            if not self.supports_change_set(
                change_set, capabilities=capabilities
            ):
                raise HostAccessError("The change set contains unsupported native write paths")
            font = self._font_for_document(document_id)
            copier = _safe_getattr(font, "copy")
            if not callable(copier):
                raise HostAccessError("Glyphs did not provide GSFont.copy()")
            source = _retain_canonical_model(before_model)
            impact = CanonicalImpact.from_change_set(source, change_set)
            before_impact = CanonicalImpact.from_change_set(
                source,
                ChangeSet.from_changes(
                    before_fingerprint=change_set.before_fingerprint,
                    after_fingerprint=change_set.after_fingerprint,
                    changes=(
                        change
                        for change in change_set.changes
                        if change.before_present
                    ),
                ),
            )
            before_scope = MutationScope(
                before_impact.roots, before_impact.glyph_names
            )
            required = (
                _retain_canonical_model(required_after_model)
                if required_after_model is not None
                else None
            )
            source_instance_ids = collection_order(source.get("instances", []))
            restore_templates = self._master_restore_templates(
                removes_contribution_id
            )
            layer_restore_templates = self._layer_restore_templates(
                removes_contribution_id, native=False
            )
            resolved_context = dict(execution_context or {})
            native_restore_templates = self._native_restore_templates(
                removes_contribution_id, native=False
            )
            if native_restore_templates:
                resolved_context["nativeReplayTemplates"] = {
                    **dict(resolved_context.get("nativeReplayTemplates") or {}),
                    **native_restore_templates,
                }

            def requested_observations() -> Mapping[
                tuple[str, str], Mapping[str, Any]
            ]:
                request = resolved_context.get("constraintObservations")
                if not isinstance(request, Mapping) or not request.get("fields"):
                    return {}
                fields = {str(value) for value in request.get("fields") or ()}
                observations = dict(
                    self._inspect_layers_in_font(
                        clone,
                        tuple(str(value) for value in request.get("glyphNames") or ()),
                        include_metrics=bool(request.get("includeMetrics")),
                        resolve_metrics=bool(request.get("resolveMetrics")),
                        include_geometry=bool(request.get("includeGeometry")),
                    )
                ) if fields.intersection({
                    "alignment",
                    "bounds",
                    "inheritance.metrics",
                    "spacing.horizontal",
                    "spacing.vertical",
                }) else {}
                if "compilation.diagnostics" in fields:
                    observations[("__document__", "compilation.diagnostics")] = dict(
                        self._inspect_compilation_in_font(clone)
                    )
                return observations

            def requested_effective_metadata() -> Mapping[str, Mapping[str, Any]]:
                request = resolved_context.get("constraintObservations")
                if not isinstance(request, Mapping) or "metadata.effective" not in {
                    str(value) for value in request.get("fields") or ()
                }:
                    return {}
                return self._inspect_glyph_metadata_in_font(
                    clone,
                    tuple(str(value) for value in request.get("glyphNames") or ()),
                )

            timings = {
                "clone": 0.0,
                "detached_apply": 0.0,
                "verification": 0.0,
            }
            started = time.perf_counter_ns()
            clone = copier()
            timings["clone"] += (time.perf_counter_ns() - started) / 1_000_000
            debug_simulation("clone_created")

            def capture_root_evidence(
                current_impact: CanonicalImpact,
                model: Mapping[str, Any],
            ) -> dict[str, Any]:
                return {
                    root: _native_root_evidence_value(
                        clone,
                        root,
                        instance_ids=collection_order(
                            model.get("instances", [])
                        ),
                    )
                    for root in current_impact.roots
                    if root not in {"glyphs", "glyphOrder"}
                }

            clone_initial_root_evidence = capture_root_evidence(
                before_impact, source
            )

            clone_projection: _DetachedCloneProjection

            def capture_after(
                base: Mapping[str, Any],
                target: Mapping[str, Any],
                current_impact: CanonicalImpact,
                revisions_start: Mapping[str, tuple[Any, ...]],
                protected_paths: Sequence[Sequence[str]],
                root_evidence_start: Mapping[str, Any],
            ) -> tuple[
                Mapping[str, Any],
                Mapping[str, tuple[Any, ...]],
                Mapping[str, Any],
            ]:
                verification_started = time.perf_counter_ns()
                revisions_after = _glyph_revision_index(clone)
                root_evidence_after = capture_root_evidence(
                    current_impact, target
                )
                changed_glyphs = _changed_revision_glyphs(
                    revisions_start, revisions_after
                )
                unproved_glyphs = _unproved_revision_glyphs(
                    clone,
                    base,
                    target,
                    current_impact,
                    changed_glyphs,
                )
                current_scope = MutationScope(
                    current_impact.roots, current_impact.glyph_names
                )
                captured = None
                if _impact_prefers_persistent_verification(current_impact):
                    with _suspend_cyclic_gc_for_bulk_capture():
                        captured = _native_persistent_font_model(
                            clone,
                            instance_ids=collection_order(
                                target.get("instances", [])
                            ),
                            document_path=_canonical_document_path(target),
                        )
                    if captured is not None:
                        _project_persistent_layer_order(captured, target)
                if captured is None:
                    captured = _scoped_font_model(
                        clone,
                        base,
                        current_scope,
                        impact=current_impact,
                        extra_glyph_names=unproved_glyphs,
                        instance_ids=collection_order(target.get("instances", [])),
                        expected_model=target,
                        before_root_evidence=root_evidence_start,
                        current_root_evidence=root_evidence_after,
                        allow_observed_root_expansion=required is None,
                    )
                captured = clone_projection.normalize(
                    captured,
                    protected_paths=protected_paths,
                )
                captured = rebase_canonical_model(base, captured)
                timings["verification"] += (
                    time.perf_counter_ns() - verification_started
                ) / 1_000_000
                return captured, revisions_after, root_evidence_after

            verification_started = time.perf_counter_ns()
            clone_before_is_complete = False
            clone_before = None
            if _impact_prefers_persistent_verification(impact):
                with _suspend_cyclic_gc_for_bulk_capture():
                    clone_before = _native_persistent_font_model(
                        clone,
                        instance_ids=source_instance_ids,
                        document_path=_canonical_document_path(source),
                    )
                if clone_before is not None:
                    _project_persistent_layer_order(clone_before, source)
                    clone_before = rebase_canonical_model(source, clone_before)
                    clone_before_is_complete = True
            if clone_before is None:
                clone_before = _scoped_font_model(
                    clone,
                    source,
                    before_scope,
                    impact=before_impact,
                    instance_ids=source_instance_ids,
                    expected_model=source,
                    before_root_evidence=clone_initial_root_evidence,
                    current_root_evidence=clone_initial_root_evidence,
                )
            debug_simulation("clone_captured")
            clone_before, clone_projection = self._reconcile_detached_clone(
                clone,
                source,
                clone_before,
                document_id=document_id,
                instance_ids=source_instance_ids,
                observed_is_complete=clone_before_is_complete,
            )
            debug_simulation("clone_reconciled")
            if fingerprint_model(clone_before) != change_set.before_fingerprint:
                raise HostAccessError(
                    "Detached GSFont.copy() did not reproduce the canonical source"
                )
            # Clone normalization is a precondition, not part of the planned
            # mutation. All proof evidence starts only after it succeeds, so
            # copy/reconciliation artifacts cannot be misclassified as host
            # effects of the requested change.
            clone_root_evidence_before = capture_root_evidence(impact, source)
            revisions_before = _glyph_revision_index(clone)
            timings["verification"] += (
                time.perf_counter_ns() - verification_started
            ) / 1_000_000
            requested_target = change_set.apply(clone_before)
            target = required if required is not None else requested_target
            apply_started = time.perf_counter_ns()
            _apply_target_model(
                clone,
                clone_before,
                target,
                change_set,
                capabilities=capabilities,
                execution_context=resolved_context,
                master_restore_templates=restore_templates,
                layer_restore_templates=layer_restore_templates,
            )
            debug_simulation("requested_patch_applied")
            timings["detached_apply"] += (
                time.perf_counter_ns() - apply_started
            ) / 1_000_000
            preferred, revisions_after, root_evidence_after = capture_after(
                source,
                target,
                impact,
                revisions_before,
                tuple(change.path for change in change_set.changes),
                clone_root_evidence_before,
            )
            debug_simulation(
                "requested_patch_verified",
                requestedAfter=change_set.after_fingerprint,
                source=fingerprint_model(source),
                target=fingerprint_model(target),
                verified=fingerprint_model(preferred),
            )
            if (
                isinstance(source, CanonicalSnapshot)
                and complete_models_equal(preferred, target)
                and fingerprint_model(target) == change_set.after_fingerprint
            ):
                preferred = source.store_verified_transition(
                    preferred,
                    change_set,
                    native_revision_evidence={
                        **dict(source.native_revision_evidence),
                        "glyphs": revisions_after,
                    },
                )
            if required is None or fingerprint_model(preferred) == fingerprint_model(
                required
            ):
                return {
                    "afterModel": preferred,
                    "observations": requested_observations(),
                    "replayReplacements": [],
                    "stageTimings": timings,
                }

            replacements = _canonical_replacement_roots(
                source,
                required,
                preferred,
            )
            if not replacements:
                return {
                    "afterModel": preferred,
                    "observations": requested_observations(),
                    "replayReplacements": [],
                    "stageTimings": timings,
                }
            residual = diff_models(preferred, required)
            residual_impact = CanonicalImpact.from_change_set(preferred, residual)
            apply_started = time.perf_counter_ns()
            _apply_target_model(
                clone,
                preferred,
                required,
                residual,
                replay_replacements=replacements,
                capabilities=capabilities,
                execution_context=resolved_context,
                master_restore_templates=restore_templates,
                layer_restore_templates=layer_restore_templates,
            )
            timings["detached_apply"] += (
                time.perf_counter_ns() - apply_started
            ) / 1_000_000
            canonical, _, _ = capture_after(
                preferred,
                required,
                residual_impact,
                revisions_after,
                tuple(change.path for change in residual.changes),
                root_evidence_after,
            )
            return {
                "afterModel": canonical,
                "observations": requested_observations(),
                "effectiveMetadata": requested_effective_metadata(),
                "replayReplacements": [list(path) for path in replacements],
                "stageTimings": timings,
            }

        return self._executor.run(
            lambda: _run_with_cyclic_gc_suspended(simulate)
        )

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
        layer_lifecycle = LAYER_LIFECYCLE_CAPABILITY in capabilities
        canonical_lifecycle = CANONICAL_LIFECYCLE_CAPABILITY in capabilities
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
            if path[0] == "font" and len(path) >= 2 and path[1] in {
                "customParameters", "properties", "userData"
            }:
                continue
            if path[0] in {"axes", "metrics", "stems", "numbers", "glyphOrder", "settings"} and canonical_lifecycle:
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
                    "active",
                    "visible",
                    "iconName",
                    "customParameters",
                    "properties",
                    "guides",
                    "metricValues",
                    "stemValues",
                    "numberValues",
                    "userData",
                }:
                    continue
                return False
            if (
                path[0] in {"features", "classes", "featurePrefixes"}
                and (
                    len(path) == 2
                    or (
                        len(path) >= 3
                        and path[2] in {
                            "name", "tag", "code", "automatic", "disabled",
                            "notes", "labels",
                        }
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
                    "exports",
                    "visible",
                    "isBold",
                    "isItalic",
                    "linkStyle",
                    "manualInterpolation",
                    "weightClass",
                    "widthClass",
                    "instanceInterpolations",
                    "customParameters",
                    "properties",
                    "userData",
                }:
                    continue
                return False
            if path[0] == "glyphs" and len(path) == 2:
                continue
            if path[0] == "glyphs" and len(path) >= 3:
                if master_lifecycle and master_owns_layer_order_change(
                    change, change_set
                ):
                    continue
                if (
                    master_lifecycle
                    and len(path) >= 4
                    and path[2] == "layers"
                    and path[3] in structural_master_ids
                ):
                    continue
                if len(path) == 3 and path[2] in set(_GLYPH_SCALARS) | set(_GLYPH_METADATA_FIELDS):
                    if not change.before_present or not change.after_present:
                        return False
                    continue
                if layer_lifecycle and len(path) >= 4 and path[2] == "layers":
                    if len(path) == 4:
                        continue
                    if path[4] in {
                        "name",
                        "masterId",
                        "interpolation",
                        "roles",
                        "isSpecialLayer",
                    }:
                        continue
                if len(path) >= 5 and path[2] == "layers" and path[4] in set(_LAYER_SCALARS) | {
                    "anchors",
                    "shapes",
                    "attributes",
                    "annotations",
                    "background",
                    "backgroundImage",
                    "guides",
                    "hints",
                    "partSelection",
                    "userData",
                }:
                    if len(path) == 5 and path[4] in _LAYER_SCALARS and (
                        not change.before_present or not change.after_present
                    ):
                        return False
                    continue
            return False
        return True

    @staticmethod
    def detached_python_constructor_names() -> tuple[str, ...]:
        return tuple(sorted(_staged_native_types()))

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
        return build_detached_namespace(
            {
                "font": font,
                "glyph": glyph,
                "master": master,
                "layer": layer,
                "selectedLayers": [layer] if layer is not None else [],
            },
            constructors=_staged_native_types(),
        )

    def preview_python(self, request: PythonExecutionRequest, before_model: Mapping[str, Any]) -> Mapping[str, Any]:
        """Run staged Python in short native phases and compare off-main-thread."""

        timings: dict[str, float] = {}
        native_phase_timings: list[float] = []
        total_started = time.perf_counter_ns()
        native_state: dict[str, Any] = {}

        def notify(phase: str, message: str, *, cancellable: bool = True) -> None:
            callback = request.progress_callback
            if callable(callback):
                callback(phase, message, cancellable)

        def checkpoint() -> None:
            callback = request.checkpoint_callback
            if callable(callback):
                callback()

        def elapsed_ms(started: int) -> float:
            return (time.perf_counter_ns() - started) / 1_000_000.0

        def native_phase(name: str, callback: Any) -> Any:
            checkpoint()
            started = time.perf_counter_ns()
            try:
                return self._executor.run(callback)
            except BaseException as exc:
                timings[name] = elapsed_ms(started)
                native_phase_timings.append(timings[name])
                timings["totalMs"] = elapsed_ms(total_started)
                timings["maxNativePhaseMs"] = max(native_phase_timings, default=0.0)
                try:
                    setattr(exc, "stage_timings", dict(timings))
                except Exception:
                    pass
                raise
            finally:
                if name not in timings:
                    timings[name] = elapsed_ms(started)
                    native_phase_timings.append(timings[name])

        notify("stabilizing", "Capturing a stable live-document baseline")
        started = time.perf_counter_ns()
        live_before_models = self._stable_open_models()
        timings["stableBaselineMs"] = elapsed_ms(started)
        live_before = {
            document_id: fingerprint_model(model)
            for document_id, model in live_before_models.items()
        }

        notify("cloning", "Cloning and capturing detached documents")

        def clone_and_capture() -> None:
            font = self._font_for_document(request.document_id or "")
            copier = _safe_getattr(font, "copy")
            if not callable(copier):
                raise HostAccessError("Glyphs did not provide GSFont.copy()")
            before_instance_ids = collection_order(
                before_model.get("instances", [])
            )
            clone = copier()
            verifier = copier()
            normalization_scope = (
                MutationScope(("glyphs",), (request.glyph_name,))
                if request.glyph_name
                else None
            )
            clone_before_model = self._capture_detached_model(
                clone,
                before_model,
                scope=normalization_scope,
                instance_ids=before_instance_ids,
            )
            clone_before_model, clone_projection = self._reconcile_detached_clone(
                clone,
                before_model,
                clone_before_model,
                document_id=request.document_id or "",
                instance_ids=before_instance_ids,
                allow_cached_projection=False,
            )
            verifier_before_model = self._capture_detached_model(
                verifier,
                before_model,
                scope=normalization_scope,
                instance_ids=before_instance_ids,
            )
            verifier_before_model, verifier_projection = self._reconcile_detached_clone(
                verifier,
                before_model,
                verifier_before_model,
                document_id=request.document_id or "",
                instance_ids=before_instance_ids,
                allow_cached_projection=False,
            )
            direct_before_archive = _serialized_review_scope(clone, request)
            replay_before_archive = _serialized_review_scope(verifier, request)
            clone_revisions_before = _glyph_revision_index(clone)
            clone_instances_before = _sequence_values(
                _safe_getattr(clone, "instances")
            )
            native_state.update(
                {
                    "clone": clone,
                    "verifier": verifier,
                    "cloneProjection": clone_projection,
                    "verifierProjection": verifier_projection,
                    "beforeInstanceIds": before_instance_ids,
                    "cloneRevisionsBefore": clone_revisions_before,
                    "cloneInstancesBefore": clone_instances_before,
                    "directBeforeArchive": direct_before_archive,
                    "replayBeforeArchive": replay_before_archive,
                }
            )

        native_phase("cloneCaptureMs", clone_and_capture)
        notify("executing", "Running Python on the detached document")

        def execute_and_capture() -> Mapping[str, Any]:
            clone = native_state["clone"]
            namespace = self._context(clone, request)
            stdout, stderr = io.StringIO(), io.StringIO()
            protected = [clone, _maybe_call(_safe_getattr(clone, "parent"))]
            with _WorkingSourceSaveRuntimeGuard(
                protected,
                native_identity=self._native_identity,
            ) as save_guard, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(compile(request.code or "", "<glyphs-mcp-staged>", "exec"), namespace, namespace)
                save_guard.raise_if_blocked()
            after_instance_ids = _staged_instance_ids(
                native_state["cloneInstancesBefore"],
                native_state["beforeInstanceIds"],
                _sequence_values(_safe_getattr(clone, "instances")),
                code_hash=hashlib.sha256(
                    (request.code or "").encode("utf-8")
                ).hexdigest(),
            )
            if request.glyph_name:
                clone_revisions_after = _glyph_revision_index(clone)
                after_model = _scoped_font_model(
                    clone,
                    before_model,
                    MutationScope(("glyphs",), (request.glyph_name,)),
                    extra_glyph_names=_changed_revision_glyphs(
                        native_state["cloneRevisionsBefore"],
                        clone_revisions_after,
                    ),
                    instance_ids=after_instance_ids,
                    expected_model=before_model,
                )
            else:
                # Open-world staged requests retain the conservative full-tree
                # fallback because no smaller correctness boundary was declared.
                after_model = self._capture_detached_model(
                    clone,
                    before_model,
                    instance_ids=after_instance_ids,
                )
            return {
                "afterModel": after_model,
                "afterInstanceIds": after_instance_ids,
                "stdout": stdout.getvalue(),
                "stderr": stderr.getvalue(),
                "directAfterArchive": _serialized_review_scope(clone, request),
            }

        execution = native_phase("evaluationCaptureMs", execute_and_capture)
        notify("comparing", "Comparing canonical staged changes")
        checkpoint()
        started = time.perf_counter_ns()
        after_model = native_state["cloneProjection"].normalize(
            execution["afterModel"]
        )
        changes = diff_models(before_model, after_model)
        capabilities = staged_lifecycle_capabilities(
            before_model, after_model, changes
        )
        context_violations = _staged_context_violations(
            request,
            changes,
            model=before_model,
        )
        writable_changes = writable_subset(
            before_model, changes, capabilities=capabilities
        )
        writable_supported = self.supports_change_set(
            writable_changes, capabilities=capabilities
        )
        writable_target = (
            writable_changes.apply(before_model) if writable_supported else None
        )
        timings["canonicalCompareMs"] = elapsed_ms(started)

        archive_comparison = {
            "equivalent": True,
            "mismatchCount": 0,
            "mismatchLocations": [],
            "truncated": False,
            "directDeltaCount": 0,
            "replayDeltaCount": 0,
        }
        templates: dict[tuple[str, ...], Any] = {}
        retained_templates: dict[tuple[str, ...], Any] = {}
        verifier_model: Mapping[str, Any] | None = None
        replay_after_archive: bytes | None = None
        if writable_supported:
            notify("replaying", "Replaying the staged change on a verifier")

            def replay_and_capture() -> Mapping[str, Any]:
                clone = native_state["clone"]
                verifier = native_state["verifier"]
                local_templates = _added_native_replay_templates(
                    clone, before_model, after_model, changes
                )
                _apply_target_model(
                    verifier,
                    before_model,
                    writable_target,
                    writable_changes,
                    capabilities=capabilities,
                    execution_context={
                        "nativeReplayTemplates": local_templates,
                        "reuseNativeReplayTemplates": True,
                    },
                )
                captured_verifier_model = self._capture_detached_model(
                    verifier,
                    after_model,
                    instance_ids=execution["afterInstanceIds"],
                    document_path=_canonical_document_path(before_model),
                )
                local_retained_templates = _added_native_replay_templates(
                    clone, before_model, after_model, changes
                )
                return {
                    "templates": local_templates,
                    "retainedTemplates": local_retained_templates,
                    "verifierModel": captured_verifier_model,
                    "replayAfterArchive": _serialized_review_scope(
                        verifier, request
                    ),
                }

            replay = native_phase("replayCaptureMs", replay_and_capture)
            templates = replay["templates"]
            retained_templates = replay["retainedTemplates"]
            replay_after_archive = replay["replayAfterArchive"]
            verifier_model = native_state["verifierProjection"].normalize(
                replay["verifierModel"],
                protected_paths=tuple(
                    change.path for change in writable_changes.changes
                ),
            )

        notify("verifying", "Verifying canonical and native replay parity")
        checkpoint()
        started = time.perf_counter_ns()
        if verifier_model is not None:
            if fingerprint_model(verifier_model) != fingerprint_model(after_model):
                canonical_mismatch = diff_models(after_model, verifier_model)
                mismatch_locations = [
                    {
                        "path": list(change.path),
                        "expectedPresent": change.before_present,
                        "observedPresent": change.after_present,
                        "expected": repr(change.before)[:500],
                        "observed": repr(change.after)[:500],
                    }
                    for change in canonical_mismatch.changes[:100]
                ]
                archive_comparison = {
                    "equivalent": False,
                    "mismatchCount": len(canonical_mismatch.changes),
                    "mismatchLocations": mismatch_locations,
                    "truncated": len(canonical_mismatch.changes)
                    > len(mismatch_locations),
                    "directDeltaCount": 0,
                    "replayDeltaCount": 0,
                }
            elif not int(context_violations.get("count") or 0):
                archive_comparison = _compare_native_archive_deltas(
                    native_state["directBeforeArchive"],
                    execution["directAfterArchive"],
                    native_state["replayBeforeArchive"],
                    replay_after_archive or b"",
                    limit=100,
                )
        timings["replayCompareMs"] = elapsed_ms(started)

        notify("checking_scope", "Checking live documents for staged drift")
        checkpoint()
        started = time.perf_counter_ns()
        live_after_models = self._stable_open_models()
        timings["scopeVerificationMs"] = elapsed_ms(started)
        live_after = {
            document_id: fingerprint_model(model)
            for document_id, model in live_after_models.items()
        }
        observed_document_changes = [
            {
                "documentId": document_id,
                "beforeFingerprint": live_before.get(document_id),
                "afterFingerprint": live_after.get(document_id),
                "declared": document_id == request.document_id,
            }
            for document_id in sorted(set(live_before) | set(live_after))
            if live_before.get(document_id) != live_after.get(document_id)
        ]
        replay_context: dict[str, Any] = {}
        if (
            retained_templates
            and not observed_document_changes
            and not int(context_violations.get("count") or 0)
            and bool(archive_comparison.get("equivalent"))
        ):
            evidence = self._native_replay_evidence.create(
                document_id=request.document_id or "",
                before_fingerprint=fingerprint_model(before_model),
                after_fingerprint=fingerprint_model(after_model),
                capabilities=capabilities,
                templates=retained_templates,
                ttl_seconds=15 * 60,
            )
            replay_context = {"nativeReplayEvidenceId": evidence.evidence_id}
        timings["totalMs"] = elapsed_ms(total_started)
        timings["maxNativePhaseMs"] = max(native_phase_timings, default=0.0)
        return {
            "afterModel": after_model,
            "changeSet": changes,
            "writableChangeSet": writable_changes,
            "capabilities": capabilities,
            "executionContext": replay_context,
            "stdout": execution["stdout"],
            "stderr": execution["stderr"],
            "observedDocumentChanges": observed_document_changes,
            "contextViolations": context_violations,
            "nativeArchiveComparison": archive_comparison,
            "stageTimings": timings,
        }

    def run_live_python(self, request: PythonExecutionRequest) -> Mapping[str, Any]:
        live_before_models = self._stable_open_models()
        live_before = {
            document_id: fingerprint_model(model)
            for document_id, model in live_before_models.items()
        }

        def run() -> Mapping[str, Any]:
            font = self._font_for_document(request.document_id) if request.document_id else _safe_getattr(self._app, "font")
            active_document_id = (
                request.document_id
                or (
                    self._identities.resolve(self._native_identity(font))
                    if font is not None
                    else None
                )
            )
            before = live_before_models.get(active_document_id or "", {})
            namespace = self._context(font, request) if font is not None else {"font": None, "glyph": None, "master": None, "layer": None, "selectedLayers": []}
            namespace.update({"Glyphs": self._app, "__builtins__": builtins.__dict__})
            stdout, stderr = io.StringIO(), io.StringIO()
            execution_error: BaseException | None = None
            try:
                protected_objects: list[Any] = []
                for open_font in self._collect_fonts():
                    protected_objects.append(open_font)
                    protected_objects.append(
                        _maybe_call(_safe_getattr(open_font, "parent"))
                    )
                with _WorkingSourceSaveRuntimeGuard(
                    protected_objects,
                    native_identity=self._native_identity,
                ) as save_guard, contextlib.redirect_stdout(
                    stdout
                ), contextlib.redirect_stderr(stderr):
                    exec(
                        compile(
                            request.code or "",
                            "<glyphs-mcp-live>",
                            "exec",
                        ),
                        namespace,
                        namespace,
                    )
                    # A script can catch the immediate guard exception. The
                    # attempt remains a failed capability request and must not
                    # be reported as successful execution.
                    save_guard.raise_if_blocked()
            except BaseException as exc:
                execution_error = exc
            return {
                "activeDocumentId": active_document_id,
                "beforeModel": before,
                "stdout": stdout.getvalue(),
                "stderr": stderr.getvalue(),
                "executionError": execution_error,
            }

        execution = self._executor.run(run)
        # Open-world Python can mutate through APIs that do not post Glyphs'
        # normal UPDATEINTERFACE notification. Invalidate every cached shard,
        # yield the main queue, and require stable observations before claiming
        # the final scope or fingerprint. This boundary applies equally to
        # direct scripts and scripts that compose nested verified operations.
        self._canonical_model_cache.invalidate_unscoped()
        live_after_models = self._stable_open_models()
        active_document_id = str(execution.get("activeDocumentId") or "")
        after = live_after_models.get(active_document_id, {})
        live_after = {
            document_id: fingerprint_model(model)
            for document_id, model in live_after_models.items()
        }
        changed_documents = [
            document_id
            for document_id in sorted(set(live_before) | set(live_after))
            if live_before.get(document_id) != live_after.get(document_id)
        ]
        observed_document_changes = [
            {
                "documentId": document_id,
                "beforeFingerprint": live_before.get(document_id),
                "afterFingerprint": live_after.get(document_id),
                "declared": document_id == request.document_id,
            }
            for document_id in changed_documents
        ]
        result = {
            "beforeModel": execution.get("beforeModel", {}),
            "afterModel": after,
            "stdout": execution.get("stdout", ""),
            "stderr": execution.get("stderr", ""),
            "observedDocumentChanges": observed_document_changes,
        }
        execution_error = execution.get("executionError")
        if isinstance(execution_error, BaseException):
            raise ObservedLivePythonError(execution_error, result) from execution_error
        return result

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
        pending = getattr(self, "_document_mcp_pending_reverts", {})
        has_pending = any(
            str(record.get("documentId") or "") == document_id
            for record in pending.values()
        )
        overrides = getattr(self, "_document_dirty_overrides", {})
        baseline = getattr(self, "_document_mcp_baseline_dirty", {}).get(document_id)
        baseline_fingerprint = getattr(
            self, "_document_mcp_baseline_fingerprints", {}
        ).get(document_id)
        if (
            not has_pending
            and baseline_fingerprint
            and current_fingerprint == baseline_fingerprint
        ):
            # Two independently verified operations may compensate exactly
            # even when neither one is a formal revert of the other. Canonical
            # baseline equivalence proves their net document delta is empty,
            # so do not leave a phantom dirty state merely because both audit
            # contributions remain addressable in process-local history.
            overrides[document_id] = baseline
        elif active or has_pending:
            overrides[document_id] = True
        else:
            native = _document_edited_state(font)
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
        *,
        current_fingerprint: Optional[str] = None,
    ) -> Optional[bool]:
        """Revalidate a clean override before it can hide a later user edit."""

        overrides = getattr(self, "_document_dirty_overrides", {})
        if document_id not in overrides:
            return native_state
        override = overrides[document_id]
        baseline_fingerprint = getattr(
            self, "_document_mcp_baseline_fingerprints", {}
        ).get(document_id)
        if not baseline_fingerprint:
            return override
        pending = getattr(self, "_document_mcp_pending_reverts", {})
        has_pending = any(
            str(record.get("documentId") or "") == document_id
            for record in pending.values()
        )
        if has_pending:
            return True
        if current_fingerprint is None:
            current_fingerprint = fingerprint_model(
                self._capture_cached_model(document_id, font)
            )
        if current_fingerprint == baseline_fingerprint:
            baseline = getattr(self, "_document_mcp_baseline_dirty", {}).get(
                document_id
            )
            overrides[document_id] = baseline
            self._document_dirty_overrides = overrides
            return baseline
        if override is not False or native_state is False:
            return override
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
            resolved_context = self._resolved_replay_context(
                document_id, execution_context
            )
            native_restore_templates = self._native_restore_templates(
                removes_contribution_id, native=True
            )
            if native_restore_templates:
                existing = dict(
                    resolved_context.get("nativeReplayTemplates") or {}
                )
                resolved_context["nativeReplayTemplates"] = {
                    **existing,
                    **native_restore_templates,
                }
                resolved_context["reuseNativeReplayTemplates"] = True
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
            verified_dirty_before = self.resolve_verified_dirty_state(
                document_id,
                font,
                native_before,
                current_fingerprint=fingerprint_model(current),
            )
            removed_templates = self._capture_removed_native_templates(
                font, current, target
            )
            if removed_templates:
                self._native_lifecycle_tombstones[operation_id] = {
                    "documentId": document_id,
                    "templates": removed_templates,
                }
                # Keep the established private compatibility views while the
                # single path-keyed store owns the retained objects.
                master_templates = {}
                layer_templates = {}
                for path, retained in removed_templates.items():
                    if len(path) == 2 and path[0] == "masters":
                        copied = retained.get("copy", {})
                        native = retained.get("native", {})
                        master_templates[path[1]] = {
                            "master": copied.get("master"),
                            "layers": copied.get("layers", {}),
                            "nativeMaster": native.get("master"),
                            "nativeLayers": native.get("layers", {}),
                        }
                    elif len(path) == 4 and path[0] == "glyphs":
                        layer_templates["{}/{}".format(path[1], path[3])] = retained
                if master_templates:
                    self._master_lifecycle_tombstones[operation_id] = {
                        "documentId": document_id,
                        "templates": master_templates,
                    }
                if layer_templates:
                    self._layer_lifecycle_tombstones[operation_id] = {
                        "documentId": document_id,
                        "templates": layer_templates,
                    }
            self._canonical_model_cache.invalidate_impact(
                document_id,
                CanonicalImpact.from_change_set(current, change_set),
                font=font,
            )
            def apply_target() -> None:
                _apply_target_model(
                    font,
                    current,
                    target,
                    change_set,
                    replay_replacements=replay_replacements,
                    capabilities=capabilities,
                    execution_context=resolved_context,
                    master_restore_templates=self._master_restore_templates(
                        removes_contribution_id
                    ),
                    layer_restore_templates=self._layer_restore_templates(
                        removes_contribution_id, native=True
                    ),
                    reuse_native_master_templates=True,
                    reuse_native_layer_templates=True,
                )

            update_boundary = self._verified_transaction_updates.get(document_id)
            if update_boundary and update_boundary.get("font") is font:
                apply_target()
            else:
                # Preserve the adapter's standalone safety when a caller does
                # not use the complete TransactionKernel boundary.
                _run_with_font_updates_suspended(font, apply_target)
            if any(change.path[0] == "instances" for change in change_set.changes):
                self._bind_instance_ids(
                    document_id,
                    font,
                    collection_order(target.get("instances", [])),
                )
            if change_set.changes:
                pending[operation_id] = {
                    "documentId": document_id,
                    "kind": "revert" if removes_contribution_id else "apply",
                    "removedId": removes_contribution_id,
                    "record": (
                        active.get(removes_contribution_id)
                        if removes_contribution_id
                        else {"nativeDirtyBefore": native_before}
                    ),
                    "nativeDirtyBefore": native_before,
                    "verifiedDirtyBefore": verified_dirty_before,
                    "beforeFingerprint": change_set.before_fingerprint,
                    "afterFingerprint": change_set.after_fingerprint,
                }
            self._document_mcp_contributions = contributions
            self._document_mcp_baseline_dirty = baselines
            self._document_mcp_baseline_fingerprints = baseline_fingerprints
            self._document_mcp_pending_reverts = pending
            self._refresh_verified_dirty_override(
                document_id,
                font,
                current_fingerprint=change_set.after_fingerprint,
            )

        self._executor.run(lambda: _run_with_cyclic_gc_suspended(apply))

    def begin_verified_transaction(self, document_id: str) -> None:
        """Suspend Glyphs redraw until live verification or restore finishes.

        This is an adapter-owned transaction boundary, not a second mutation
        engine. Native setters, settled canonical read-back, and emergency
        restoration stay inside one balanced host UI suspension so expensive
        Font/Edit View rendering cannot interleave with correctness proof.
        """

        def begin() -> None:
            existing = self._verified_transaction_updates.get(document_id)
            if existing is not None:
                existing["depth"] = int(existing.get("depth", 1)) + 1
                return
            font = self._font_for_document(document_id)
            disable = _safe_getattr(font, "disableUpdateInterface")
            enable = _safe_getattr(font, "enableUpdateInterface")
            suspended = callable(disable) and callable(enable)
            if suspended:
                disable()
            self._verified_transaction_updates[document_id] = {
                "font": font,
                "depth": 1,
                "suspended": suspended,
            }

        _VERIFIED_TRANSACTION_GC.begin()
        try:
            self._executor.run(begin)
        except Exception:
            _VERIFIED_TRANSACTION_GC.end()
            raise

    def end_verified_transaction(self, document_id: str) -> None:
        """Balance :meth:`begin_verified_transaction` on the main thread."""

        def end() -> None:
            existing = self._verified_transaction_updates.get(document_id)
            if existing is None:
                return
            depth = int(existing.get("depth", 1)) - 1
            if depth > 0:
                existing["depth"] = depth
                return
            self._verified_transaction_updates.pop(document_id, None)
            if existing.get("suspended"):
                enable = _safe_getattr(existing.get("font"), "enableUpdateInterface")
                if callable(enable):
                    enable()

        try:
            self._executor.run(end)
        finally:
            _VERIFIED_TRANSACTION_GC.end()

    def reconcile_verified_state(
        self,
        document_id: str,
        actual_model: Mapping[str, Any],
        expected_model: Mapping[str, Any],
        *,
        capabilities: Sequence[str] = (),
        execution_context: Mapping[str, Any] | None = None,
    ) -> None:
        """Converge writable drift that Glyphs derives after one UI turn.

        This remains inside the original verified transaction: it owns no
        dirty contribution, operation, audit event, or history entry. The
        complete settled tree is compared with the detached canonical target,
        and any non-writable residual refuses the transaction atomically.
        """

        expected = _retain_canonical_model(expected_model)
        actual_fingerprint = fingerprint_model(actual_model)

        def reconcile() -> None:
            font = self._font_for_document(document_id)
            current = self._capture_cached_model(document_id, font)
            if fingerprint_model(current) != actual_fingerprint:
                raise HostAccessError(
                    "the document changed during post-settle reconciliation"
                )
            residual = diff_models(current, expected)
            if not residual.changes:
                return
            if os.environ.get("GLYPHS_MCP_DEBUG_CAPTURE"):
                print(
                    "[Glyphs MCP][VerifiedReconciliation] residualCount={} "
                    "changes={}".format(
                        len(residual.changes),
                        [
                            {
                                "path": list(change.path),
                                "before": repr(change.before)[:160],
                                "after": repr(change.after)[:160],
                            }
                            for change in residual.changes[:20]
                        ],
                    ),
                    flush=True,
                )
            writable = writable_subset(
                current,
                residual,
                capabilities=capabilities,
            )
            if fingerprint_model(writable.apply(current)) != fingerprint_model(
                expected
            ):
                writable_paths = {change.path for change in writable.changes}
                non_writable_paths = [
                    list(change.path)
                    for change in residual.changes
                    if change.path not in writable_paths
                ]
                raise HostAccessError(
                    "the settled canonical residual contains non-writable state "
                    "({} residual changes; first non-writable paths: {})".format(
                        len(residual.changes), non_writable_paths[:12]
                    )
                )
            self._canonical_model_cache.invalidate_impact(
                document_id,
                CanonicalImpact.from_change_set(current, writable),
                font=font,
            )
            resolved_context = self._resolved_replay_context(
                document_id, execution_context
            )
            _apply_target_model(
                font,
                current,
                expected,
                writable,
                capabilities=capabilities,
                execution_context=resolved_context,
            )
            if any(change.path[0] == "instances" for change in writable.changes):
                self._bind_instance_ids(
                    document_id,
                    font,
                    collection_order(expected.get("instances", [])),
                )

        self._executor.run(reconcile)

    def commit_verified_change(self, operation_id: str) -> None:
        """Commit one pending native dirty contribution after exact verification."""

        def commit() -> None:
            pending = getattr(self, "_document_mcp_pending_reverts", {})
            completed = pending.get(operation_id)
            if completed is None:
                return
            document_id = str(completed.get("documentId") or "")
            font = self._font_for_document(document_id)
            contributions = getattr(self, "_document_mcp_contributions", {})
            active = contributions.setdefault(document_id, {})
            baselines = getattr(self, "_document_mcp_baseline_dirty", {})
            baseline_fingerprints = getattr(
                self, "_document_mcp_baseline_fingerprints", {}
            )
            if completed.get("kind") == "revert":
                removed_id = str(completed.get("removedId") or "")
                if removed_id not in active:
                    raise HostAccessError(
                        "The reverted MCP dirty contribution disappeared before commit"
                    )
                active.pop(removed_id, None)
                self._native_change_count(font, _NS_CHANGE_UNDONE)
                for tombstones in (
                    self._master_lifecycle_tombstones,
                    self._layer_lifecycle_tombstones,
                    self._native_lifecycle_tombstones,
                ):
                    tombstones.pop(removed_id, None)
                    tombstones.pop(operation_id, None)
            else:
                if not active:
                    # Commit the effective pre-operation state, not a possibly
                    # sticky native edited bit observed after prior MCP work.
                    baselines[document_id] = completed.get(
                        "verifiedDirtyBefore"
                    )
                    baseline_fingerprints[document_id] = str(
                        completed.get("beforeFingerprint") or ""
                    )
                active[operation_id] = dict(completed.get("record") or {})
                self._native_change_count(font, _NS_CHANGE_DONE)
            pending.pop(operation_id, None)
            self._document_mcp_contributions = contributions
            self._document_mcp_baseline_dirty = baselines
            self._document_mcp_baseline_fingerprints = baseline_fingerprints
            self._document_mcp_pending_reverts = pending
            self._refresh_verified_dirty_override(
                document_id,
                font,
                current_fingerprint=str(completed.get("afterFingerprint") or ""),
            )

        self._executor.run(commit)

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
        """Restore only a failed attempt's content.

        Dirty accounting remains pending until the transaction kernel proves
        the exact canonical baseline and calls :meth:`finalize_verified_failure`.
        """

        def restore() -> None:
            font = self._font_for_document(document_id)
            current = self._capture_cached_model(document_id, font)
            restoration = diff_models(current, model)
            self._canonical_model_cache.invalidate_impact(
                document_id,
                CanonicalImpact.from_change_set(current, restoration),
                font=font,
            )
            restore_templates = self._master_restore_templates(operation_id)
            if not restore_templates:
                restore_templates = self._master_restore_templates(
                    removes_contribution_id
                )
            layer_restore_templates = self._layer_restore_templates(
                operation_id, native=True
            )
            if not layer_restore_templates:
                layer_restore_templates = self._layer_restore_templates(
                    removes_contribution_id, native=True
                )
            resolved_context = self._resolved_replay_context(
                document_id, execution_context, native_restore=True
            )
            native_restore_templates = self._native_restore_templates(
                operation_id, native=True
            )
            if not native_restore_templates:
                native_restore_templates = self._native_restore_templates(
                    removes_contribution_id, native=True
                )
            if native_restore_templates:
                resolved_context["nativeReplayTemplates"] = {
                    **dict(resolved_context.get("nativeReplayTemplates") or {}),
                    **native_restore_templates,
                }
            _apply_target_model(
                font,
                current,
                model,
                restoration,
                capabilities=capabilities,
                execution_context=resolved_context,
                master_restore_templates=restore_templates,
                layer_restore_templates=layer_restore_templates,
                reuse_native_master_templates=True,
                reuse_native_layer_templates=True,
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
                    self._canonical_model_cache.invalidate_impact(
                        document_id,
                        CanonicalImpact.from_change_set(preferred, residual),
                        font=font,
                    )
                    _apply_target_model(
                        font,
                        preferred,
                        model,
                        residual,
                        replay_replacements=replacements,
                        capabilities=capabilities,
                        execution_context=resolved_context,
                        master_restore_templates=restore_templates,
                        layer_restore_templates=layer_restore_templates,
                        reuse_native_master_templates=True,
                        reuse_native_layer_templates=True,
                    )
                    if any(
                        change.path[0] == "instances" for change in residual.changes
                    ):
                        self._bind_instance_ids(
                            document_id,
                            font,
                            collection_order(model.get("instances", [])),
                        )
        self._executor.run(restore)

    def finalize_verified_failure(
        self,
        operation_id: str,
        *,
        rollback_succeeded: bool,
        observed_fingerprint: str,
    ) -> None:
        """Resolve pending dirty state only after rollback verification."""

        def finalize() -> None:
            pending = getattr(self, "_document_mcp_pending_reverts", {})
            attempt = pending.pop(operation_id, None)
            if attempt is None:
                return
            document_id = str(attempt.get("documentId") or "")
            font = self._font_for_document(document_id)
            contributions = getattr(self, "_document_mcp_contributions", {})
            active = contributions.setdefault(document_id, {})
            overrides = getattr(self, "_document_dirty_overrides", {})
            if rollback_succeeded:
                # No native change-count contribution was committed, so exact
                # content restoration can now balance a native setter-owned
                # dirty bit and reinstate the proven effective baseline.
                baseline_dirty = attempt.get("verifiedDirtyBefore")
                if (
                    not active
                    and baseline_dirty is False
                    and _document_edited_state(font) is True
                ):
                    self._native_change_count(font, _NS_CHANGE_UNDONE)
                overrides[document_id] = (
                    True
                    if active
                    else baseline_dirty
                )
            else:
                # Unverified content or disk state must stay visibly dirty. A
                # failed forward operation owns a durable contribution; a
                # failed revert retains the original one it never removed.
                if attempt.get("kind") == "apply":
                    baselines = getattr(self, "_document_mcp_baseline_dirty", {})
                    baseline_fingerprints = getattr(
                        self, "_document_mcp_baseline_fingerprints", {}
                    )
                    if not active:
                        baselines[document_id] = attempt.get(
                            "verifiedDirtyBefore"
                        )
                        baseline_fingerprints[document_id] = str(
                            attempt.get("beforeFingerprint") or ""
                        )
                    active[operation_id] = {
                        **dict(attempt.get("record") or {}),
                        "failedVerification": True,
                        "observedFingerprint": observed_fingerprint,
                    }
                    self._document_mcp_baseline_dirty = baselines
                    self._document_mcp_baseline_fingerprints = baseline_fingerprints
                if _document_edited_state(font) is not True:
                    self._native_change_count(font, _NS_CHANGE_DONE)
                overrides[document_id] = True
            for tombstones in (
                self._master_lifecycle_tombstones,
                self._layer_lifecycle_tombstones,
                self._native_lifecycle_tombstones,
            ):
                tombstones.pop(operation_id, None)
            self._document_mcp_contributions = contributions
            self._document_mcp_pending_reverts = pending
            self._document_dirty_overrides = overrides

        self._executor.run(finalize)

    def reset_verified_change_tracking(self, document_id: str) -> None:
        """Clear save-bound state on the adapter's native serialization lane."""

        self._executor.run(
            lambda: self._reset_verified_change_tracking_main_thread(document_id)
        )

    def _reset_verified_change_tracking_main_thread(
        self, document_id: str
    ) -> None:
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
        layer_tombstones = getattr(self, "_layer_lifecycle_tombstones", {})
        self._layer_lifecycle_tombstones = {
            operation_id: record
            for operation_id, record in layer_tombstones.items()
            if str(record.get("documentId") or "") != document_id
        }
        native_tombstones = getattr(self, "_native_lifecycle_tombstones", {})
        self._native_lifecycle_tombstones = {
            operation_id: record
            for operation_id, record in native_tombstones.items()
            if str(record.get("documentId") or "") != document_id
        }
        replay_evidence = getattr(self, "_native_replay_evidence", None)
        if replay_evidence is not None:
            replay_evidence.clear_document(document_id)
        projection_cache = getattr(
            self, "_detached_clone_projection_cache", {}
        )
        projection_order = getattr(
            self, "_detached_clone_projection_order", []
        )
        self._detached_clone_projection_cache = {
            key: value
            for key, value in projection_cache.items()
            if key[0] != document_id
        }
        self._detached_clone_projection_order = [
            key for key in projection_order if key[0] != document_id
        ]

    def complete_observed_diff_covered(
        self, change_set: ChangeSet, execution_result: Mapping[str, Any]
    ) -> bool:
        # The canonical model deliberately excludes some open-world PyObjC and
        # application state. Live execution is therefore recovery-only until a
        # complete native archive comparison proves otherwise.
        return False

    def inspect_export_destination(self, destination: str) -> Mapping[str, Any]:
        return inspect_destination(destination)

    def preflight_source_bundle(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        document_id = str(payload.get("documentId") or "")
        model = payload.get("canonicalModel")
        if not isinstance(model, Mapping):
            raise SourceBundleError(
                "canonical_model_required",
                "Source-bundle preflight requires the captured canonical model.",
            )

        def preflight() -> Mapping[str, Any]:
            return build_source_bundle_preflight(
                font=self._font_for_document(document_id),
                model=model,
                compatibility_mode=str(
                    payload.get("compatibilityMode") or "component_preserving"
                ),
                document_fingerprint=str(payload.get("documentFingerprint") or ""),
                source_fingerprint=(
                    str(payload.get("sourceFingerprint"))
                    if payload.get("sourceFingerprint")
                    else None
                ),
                runtime_versions=dict(payload.get("runtimeVersions") or {}),
            )

        return self._executor.run(preflight)

    def export_source_bundle(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        document_id = str(payload.get("documentId") or "")
        destination = str(payload.get("destination") or "")
        expected_state = dict(payload.get("destinationState") or {})
        model = payload.get("canonicalModel")
        if not isinstance(model, Mapping):
            raise SourceBundleError(
                "canonical_model_required",
                "Confirmed source export requires a freshly captured canonical model.",
            )

        def produce(staged: Path) -> Mapping[str, Any]:
            result = render_source_bundle(
                font=self._font_for_document(document_id),
                model=model,
                destination=staged,
                compatibility_mode=str(
                    payload.get("compatibilityMode") or "component_preserving"
                ),
                document_fingerprint=str(payload.get("documentFingerprint") or ""),
                source_fingerprint=(
                    str(payload.get("sourceFingerprint"))
                    if payload.get("sourceFingerprint")
                    else None
                ),
                runtime_versions=dict(payload.get("runtimeVersions") or {}),
            )
            reviewed_values = {
                "bundleFingerprint": payload.get("reviewedBundleFingerprint"),
                "manifestTreeSha256": payload.get("reviewedManifestTreeSha256"),
                "manifestSha256": payload.get("reviewedManifestSha256"),
            }
            mismatches = {
                key: {"reviewed": expected, "regenerated": result.get(key)}
                for key, expected in reviewed_values.items()
                if not expected or result.get(key) != expected
            }
            if mismatches:
                raise SourceBundleError(
                    "review_regeneration_mismatch",
                    "Confirmed regeneration differs from the reviewed source bundle.",
                    target={"fingerprints": mismatches},
                )
            return result

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


__all__ = [
    "GlyphsDocumentHost",
    "NativeLayerOverlayProjector",
    "native_font_to_model",
    "native_layer_overlay_state",
    "native_layer_to_model",
]
