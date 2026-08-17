"""Glyphs 3.5/4 document snapshots, staged Python, recovery, and write-back."""

from __future__ import annotations

import builtins
import contextlib
import hashlib
import io
import json
import os
import re
import time
import tempfile
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from ..exporting import inspect_destination, publish_staged_directory
from ..ports import HostAccessError
from ..python_execution import PythonExecutionRequest
from ..semantic import ChangeSet, diff_models, fingerprint_model
from .glyphs import (
    GlyphsHostAdapter,
    _maybe_call,
    _native_unsaved_changes,
    _safe_getattr,
    _sequence_values,
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
        position = _point(_safe_getattr(node, "position"))
        nodes.append(
            {
                "x": position[0],
                "y": position[1],
                "type": str(_safe_getattr(node, "type") or "line").lower(),
                "smooth": bool(_safe_getattr(node, "smooth", False)),
                "name": _plain_scalar(_safe_getattr(node, "name")),
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
        "anchors": _anchor_model(layer),
        "paths": [_path_model(path) for path in _layer_paths(layer)],
        "components": [
            {"name": str(_safe_getattr(component, "componentName") or ""), "transform": _component_transform(component)}
            for component in _layer_components(layer)
        ],
    }
    values["pathSignature"] = [len(path["nodes"]) for path in values["paths"]]
    for name in _LAYER_SCALARS:
        values[name] = _plain_scalar(_safe_getattr(layer, name))
    return values


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
        "id": str(_safe_getattr(glyph, "id") or ""),
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


def _instance_models(font: Any) -> list[dict[str, Any]]:
    axes = _axis_models(font)
    result = []
    for index, instance in enumerate(_sequence_values(_safe_getattr(font, "instances"))):
        raw_type = _plain_scalar(_safe_getattr(instance, "type"))
        is_variable = str(raw_type).lower() in {"variable", "1", "gsinstancetypevariable"}
        positions = _sequence_values(_safe_getattr(instance, "axes"))
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
                "id": "instance_{}".format(index),
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
            "automatic": bool(_safe_getattr(value, "automatic", False)),
            "disabled": bool(_safe_getattr(value, "disabled", False)),
        }
        for index, value in enumerate(_sequence_values(_safe_getattr(font, attribute)))
    ]


def _kerning_model(font: Any) -> dict[str, dict[str, dict[str, float]]]:
    result: dict[str, dict[str, dict[str, float]]] = {}
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
                result.setdefault(master_id, {}).setdefault(left, {})[right] = numeric
    return result


def native_font_to_model(font: Any) -> dict[str, Any]:
    glyphs = {}
    for glyph in _sequence_values(_safe_getattr(font, "glyphs")):
        model = _glyph_model(glyph)
        if model["name"]:
            glyphs[model["name"]] = model
    return {
        "font": {name: _plain_scalar(_safe_getattr(font, name)) for name in _FONT_SCALARS},
        "masters": _master_models(font),
        "instances": _instance_models(font),
        "glyphs": glyphs,
        "kerning": _kerning_model(font),
        "features": _code_collection(font, "features"),
        "classes": _code_collection(font, "classes"),
        "featurePrefixes": _code_collection(font, "featurePrefixes"),
    }


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


def _new_anchor(name: str, position: Sequence[float]) -> Any:
    try:
        from GlyphsApp import GSAnchor  # type: ignore[import-not-found]
    except Exception as exc:
        raise HostAccessError("GSAnchor is unavailable") from exc
    try:
        return GSAnchor(name, (float(position[0]), float(position[1])))
    except Exception:
        anchor = GSAnchor()
        anchor.name = name
        anchor.position = (float(position[0]), float(position[1]))
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
            node.position = (float(node_spec.get("x", 0)), float(node_spec.get("y", 0)))
            node.type = node_type
        try:
            node.smooth = bool(node_spec.get("smooth", False))
            node.name = node_spec.get("name")
        except Exception:
            pass
        nodes.append(node)
    _replace_collection(path.nodes, nodes)
    path.closed = bool(spec.get("closed", True))
    return path


def _replace_paths(layer: Any, specs: Sequence[Mapping[str, Any]]) -> None:
    paths = [_new_path(spec) for spec in specs]
    collection = _safe_getattr(layer, "paths")
    if collection is not None:
        _replace_collection(collection, paths)
        return
    shapes = _sequence_values(_safe_getattr(layer, "shapes"))
    setattr(layer, "shapes", paths + [shape for shape in shapes if not _is_path(shape)])


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
        component.componentName = name
    transform = spec.get("transform")
    if isinstance(transform, Sequence) and len(transform) == 6:
        component.transform = tuple(float(value) for value in transform)
    return component


def _replace_components(layer: Any, specs: Sequence[Mapping[str, Any]]) -> None:
    components = [_new_component(spec) for spec in specs]
    collection = _safe_getattr(layer, "components")
    if collection is not None:
        _replace_collection(collection, components)
        return
    shapes = _sequence_values(_safe_getattr(layer, "shapes"))
    setattr(layer, "shapes", [shape for shape in shapes if not _is_component(shape)] + components)


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
        if str(_safe_getattr(glyph, "id") or "") == value:
            name = str(_safe_getattr(glyph, "name") or "")
            if name:
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


def _apply_target_model(font: Any, current: Mapping[str, Any], target: Mapping[str, Any], change_set: ChangeSet) -> None:
    changed_roots = {change.path[0] for change in change_set.changes}
    if "font" in changed_roots:
        for name in _FONT_SCALARS:
            if current.get("font", {}).get(name) != target.get("font", {}).get(name):
                setattr(font, name, target.get("font", {}).get(name))
    if "glyphs" in changed_roots:
        current_glyphs = current.get("glyphs", {})
        target_glyphs = target.get("glyphs", {})
        if set(current_glyphs) != set(target_glyphs):
            raise HostAccessError("staged Python cannot add or delete glyphs in this v2 milestone")
        for name in sorted(target_glyphs):
            if current_glyphs.get(name) == target_glyphs.get(name):
                continue
            glyph = _lookup_by_name(_safe_getattr(font, "glyphs"), name)
            if glyph is None:
                raise HostAccessError("Glyphs could not resolve glyph {}".format(name))
            for scalar in _GLYPH_SCALARS:
                if current_glyphs[name].get(scalar) != target_glyphs[name].get(scalar):
                    setattr(glyph, scalar, target_glyphs[name].get(scalar))
            current_layers = current_glyphs[name].get("layers", {})
            target_layers = target_glyphs[name].get("layers", {})
            if set(current_layers) != set(target_layers):
                raise HostAccessError("staged Python cannot add or delete layers in this v2 milestone")
            for layer_key in sorted(target_layers):
                if current_layers.get(layer_key) == target_layers.get(layer_key):
                    continue
                layer = _lookup_layer(glyph, layer_key)
                if layer is None:
                    raise HostAccessError("Glyphs could not resolve layer {}".format(layer_key))
                begin = _safe_getattr(layer, "beginChanges")
                end = _safe_getattr(layer, "endChanges")
                if callable(begin):
                    begin()
                try:
                    for scalar in _LAYER_SCALARS:
                        if current_layers[layer_key].get(scalar) != target_layers[layer_key].get(scalar):
                            setattr(layer, scalar, target_layers[layer_key].get(scalar))
                    if current_layers[layer_key].get("anchors") != target_layers[layer_key].get("anchors"):
                        _replace_anchors(layer, target_layers[layer_key].get("anchors", {}))
                    if current_layers[layer_key].get("paths") != target_layers[layer_key].get("paths"):
                        _replace_paths(layer, target_layers[layer_key].get("paths", []))
                    if current_layers[layer_key].get("components") != target_layers[layer_key].get("components"):
                        _replace_components(layer, target_layers[layer_key].get("components", []))
                finally:
                    if callable(end):
                        end()
    if "kerning" in changed_roots:
        _replace_kerning(font, target.get("kerning", []))


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


def _serialized_font_fingerprint(font: Any) -> str:
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
        digest = hashlib.sha256(archive).hexdigest()
    return "sha256:{}".format(digest)


def _document_edited_state(font: Any) -> Optional[bool]:
    document = _maybe_call(_safe_getattr(font, "parent"))
    return _native_unsaved_changes(document)


class GlyphsDocumentHost(GlyphsHostAdapter):
    """Complete v2 host port; native objects remain inside this adapter."""

    def runtime_snapshot(self):
        self._cleanup_all_recovery()
        return super().runtime_snapshot()

    def _font_for_document(self, document_id: str) -> Any:
        for font in self._collect_fonts():
            if self._identities.resolve(self._native_identity(font)) == document_id:
                return font
        raise HostAccessError("The Glyphs document is no longer open: {}".format(document_id))

    def capture_model(self, document_id: str) -> Mapping[str, Any]:
        return self._executor.run(lambda: native_font_to_model(self._font_for_document(document_id)))

    def supports_change_set(self, change_set: ChangeSet) -> bool:
        for change in change_set.changes:
            path = change.path
            if path[0] == "font" and len(path) == 2 and path[1] in _FONT_SCALARS:
                continue
            if path[0] == "kerning":
                continue
            if path[0] == "glyphs" and len(path) >= 3:
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
            live_before = {self._identities.resolve(self._native_identity(font)): fingerprint_model(native_font_to_model(font)) for font in self._collect_fonts()}
            font = self._font_for_document(request.document_id or "")
            copier = _safe_getattr(font, "copy")
            if not callable(copier):
                raise HostAccessError("Glyphs did not provide GSFont.copy()")
            clone = copier()
            namespace = self._context(clone, request)
            namespace["__builtins__"] = _STAGED_BUILTINS
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(compile(request.code or "", "<glyphs-mcp-staged>", "exec"), namespace, namespace)
            after_model = native_font_to_model(clone)
            changes = diff_models(before_model, after_model)
            unsupported_native_change = False
            if self.supports_change_set(changes):
                verifier = copier()
                _apply_target_model(verifier, before_model, after_model, changes)
                unsupported_native_change = (
                    _serialized_font_fingerprint(verifier)
                    != _serialized_font_fingerprint(clone)
                )
            live_after = {self._identities.resolve(self._native_identity(font)): fingerprint_model(native_font_to_model(font)) for font in self._collect_fonts()}
            violations = [document_id for document_id in sorted(set(live_before) | set(live_after)) if live_before.get(document_id) != live_after.get(document_id)]
            return {
                "afterModel": after_model,
                "stdout": stdout.getvalue(),
                "stderr": stderr.getvalue(),
                "scopeViolations": violations,
                "unsupportedNativeChange": unsupported_native_change,
            }
        return self._executor.run(run)

    def run_live_python(self, request: PythonExecutionRequest) -> Mapping[str, Any]:
        def run() -> Mapping[str, Any]:
            live_before = {
                self._identities.resolve(self._native_identity(item)): fingerprint_model(native_font_to_model(item))
                for item in self._collect_fonts()
            }
            font = self._font_for_document(request.document_id) if request.document_id else _safe_getattr(self._app, "font")
            before = native_font_to_model(font) if font is not None else {}
            namespace = self._context(font, request) if font is not None else {"font": None, "glyph": None, "master": None, "layer": None, "selectedLayers": []}
            namespace.update({"Glyphs": self._app, "__builtins__": builtins.__dict__})
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(compile(request.code or "", "<glyphs-mcp-live>", "exec"), namespace, namespace)
            after = native_font_to_model(font) if font is not None else {}
            live_after = {
                self._identities.resolve(self._native_identity(item)): fingerprint_model(native_font_to_model(item))
                for item in self._collect_fonts()
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

    def _apply_and_track_dirty_state(
        self,
        document_id: str,
        font: Any,
        current: Mapping[str, Any],
        target: Mapping[str, Any],
        change_set: ChangeSet,
        *,
        restoring: bool = False,
    ) -> None:
        current_fingerprint = fingerprint_model(current)
        target_fingerprint = fingerprint_model(target)
        transitions = getattr(self, "_document_dirty_transitions", {})
        stack = transitions.setdefault(document_id, [])
        pending_reversals = getattr(self, "_document_dirty_pending_reversals", {})
        pending = pending_reversals.get(document_id) if restoring else None
        if not restoring:
            # A successful reversal remains pending only long enough for the
            # transaction kernel to restore its pre-attempt state on failure.
            pending_reversals.pop(document_id, None)
        restoring_reversal = bool(
            pending and pending["afterFingerprint"] == target_fingerprint
        )
        reversal = bool(
            stack
            and stack[-1]["beforeFingerprint"] == target_fingerprint
            and (
                stack[-1]["afterFingerprint"] == current_fingerprint
                or restoring
            )
        )
        native_dirty_before = _document_edited_state(font)
        _apply_target_model(font, current, target, change_set)
        if not change_set.changes:
            return

        document = _maybe_call(_safe_getattr(font, "parent"))
        updater = _safe_getattr(document, "updateChangeCount_") if document is not None else None
        update_succeeded = False
        change_count_action = None
        if restoring_reversal:
            change_count_action = _NS_CHANGE_DONE
        elif reversal:
            change_count_action = _NS_CHANGE_UNDONE
        elif not restoring:
            change_count_action = _NS_CHANGE_DONE
        if callable(updater) and change_count_action is not None:
            try:
                # Balance only the MCP transaction's change-count contribution;
                # never clear the document's complete native dirty history.
                updater(change_count_action)
                update_succeeded = True
            except Exception:
                update_succeeded = False

        overrides = getattr(self, "_document_dirty_overrides", {})
        if restoring_reversal:
            stack.append(pending)
            pending_reversals.pop(document_id, None)
            if update_succeeded:
                overrides.pop(document_id, None)
            else:
                overrides[document_id] = True
        elif reversal:
            transition = stack.pop()
            if not restoring:
                pending_reversals[document_id] = transition
            if update_succeeded:
                overrides.pop(document_id, None)
            elif stack:
                overrides[document_id] = True
            else:
                overrides[document_id] = transition["nativeDirtyBefore"]
        elif restoring:
            # No MCP change-count contribution was recorded for a partial
            # application failure, so restoration must not invent one.
            pass
        else:
            stack.append(
                {
                    "beforeFingerprint": current_fingerprint,
                    "afterFingerprint": target_fingerprint,
                    "nativeDirtyBefore": native_dirty_before,
                }
            )
            if update_succeeded:
                overrides.pop(document_id, None)
            else:
                # Even if the host cannot update its window dirty indicator,
                # this process knows the verified document model is unsaved.
                overrides[document_id] = True
        self._document_dirty_transitions = transitions
        self._document_dirty_pending_reversals = pending_reversals
        self._document_dirty_overrides = overrides

    def apply_change_set(self, document_id: str, change_set: ChangeSet) -> None:
        if not self.supports_change_set(change_set):
            raise HostAccessError("The change set contains unsupported native write paths")
        def apply() -> None:
            font = self._font_for_document(document_id)
            current = native_font_to_model(font)
            target = change_set.apply(current)
            self._apply_and_track_dirty_state(
                document_id, font, current, target, change_set
            )
        self._executor.run(apply)

    def complete_observed_diff_covered(
        self, change_set: ChangeSet, execution_result: Mapping[str, Any]
    ) -> bool:
        # The canonical model deliberately excludes some open-world PyObjC and
        # application state. Live execution is therefore recovery-only until a
        # complete native archive comparison proves otherwise.
        return False

    def restore_model(self, document_id: str, model: Mapping[str, Any]) -> None:
        def restore() -> None:
            font = self._font_for_document(document_id)
            current = native_font_to_model(font)
            change_set = diff_models(current, model)
            if not self.supports_change_set(change_set):
                raise HostAccessError("The rollback model contains unsupported native write paths")
            self._apply_and_track_dirty_state(
                document_id, font, current, model, change_set, restoring=True
            )
        self._executor.run(restore)

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


__all__ = ["GlyphsDocumentHost", "native_font_to_model"]
