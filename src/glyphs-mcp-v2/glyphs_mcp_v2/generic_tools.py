"""Generic canonical reads, constraints, and detached change construction.

This module deliberately contains no GlyphsApp, transport, or typographic
policy.  It turns closed selectors and mechanical operations into exact
canonical paths.  Skills and agents decide *what* a design should become;
the application and transaction kernel prove *what* will be written.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Optional, Sequence

from .affine import (
    clean_float as _clean_float,
    component_matrix as _affine_transform,
    decompose_component_matrix as _decompose_component_matrix,
    matrices_close as _matrices_close,
    matrix_about_origin as _matrix_about_origin,
    matrix_inverse as _matrix_inverse,
    matrix_multiply as _matrix_multiply,
)
from .canonical_collections import ORDER_TOKEN, entity_id, find_entity_index
from .canonical_views import layer_anchors, layer_components, layer_paths
from .mechanics_registry import (
    COMPUTED_PROJECTIONS,
    CONSTRAINT_OPERATORS,
    ENTITY_KINDS,
    OPERATION_DEFINITIONS,
    SCALAR_VALUE_FIELDS,
)
from .semantic import (
    ChangeSet,
    diff_models,
    rebase_canonical_model,
    semantic_value_at,
)


OPERATION_KINDS = frozenset(OPERATION_DEFINITIONS)

_ROOT_COLLECTIONS = {
    "axis": "axes",
    "master": "masters",
    "instance": "instances",
    "feature": "features",
    "class": "classes",
    "prefix": "featurePrefixes",
    "metric": "metrics",
    "stem": "stems",
    "number": "numbers",
}


@dataclass(frozen=True)
class EntityReference:
    kind: str
    identity: str
    path: tuple[str, ...]
    value: Any
    parent: Mapping[str, str]
    collection_index: Optional[int] = None

    def public_identity(self) -> dict[str, Any]:
        return {
            "entity": self.kind,
            "id": self.identity,
            "path": list(self.path),
            "parent": dict(self.parent),
        }


@dataclass(frozen=True)
class GenericMutationBuild:
    """Exact canonical intent plus bounded native lifecycle mechanics."""

    change_set: ChangeSet
    normalized_operations: tuple[Mapping[str, Any], ...]
    capabilities: tuple[str, ...] = ()
    execution_context: Mapping[str, Any] = field(default_factory=dict)


def _mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("{} must be an object".format(name))
    return value


def _finite_number(value: Any, *, name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("{} must be a finite number".format(name))
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("{} must be a finite number".format(name)) from exc
    if not number.is_finite():
        raise ValueError("{} must be a finite number".format(name))
    return number


def _public_number(value: Decimal) -> int | float:
    integral = value.to_integral_value()
    return int(integral) if value == integral else float(value)


def _nested_value(value: Any, field: str) -> tuple[bool, Any]:
    if field in {"", "*"}:
        return True, copy.deepcopy(value)
    current = value
    for part in str(field).split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
            continue
        if isinstance(current, (list, tuple)):
            try:
                current = current[int(part)]
                continue
            except (ValueError, IndexError):
                pass
        return False, None
    return True, copy.deepcopy(current)


def _matches_where(value: Any, where: Mapping[str, Any]) -> bool:
    if not isinstance(value, Mapping):
        return not where
    for field, expected in where.items():
        present, actual = _nested_value(value, str(field))
        if not present:
            return False
        if isinstance(expected, (list, tuple)):
            allowed = list(expected)
            if isinstance(actual, (list, tuple, set, frozenset)):
                if not any(item in allowed for item in actual):
                    return False
            elif actual not in allowed:
                return False
        elif actual != expected:
            return False
    return True


def _reference_field(reference: EntityReference, field: str) -> tuple[bool, Any]:
    name = str(field or "")
    if name in {"id", "identity"}:
        return True, reference.identity
    if name == "entity":
        return True, reference.kind
    if name.startswith("parent."):
        return _nested_value(reference.parent, name[len("parent.") :])
    if (
        SCALAR_VALUE_FIELDS.get(reference.kind) == name
        and not isinstance(reference.value, Mapping)
    ):
        return True, copy.deepcopy(reference.value)
    return _nested_value(reference.value, name)


def _predicate_matches(reference: EntityReference, predicate: Mapping[str, Any]) -> bool:
    source = _mapping(predicate, name="selector.predicate")
    operator = str(source.get("op") or "")
    if operator in {"and", "or"}:
        items = source.get("items")
        if not isinstance(items, (list, tuple)) or not items:
            raise ValueError("Boolean predicates require non-empty items")
        results = [
            _predicate_matches(reference, _mapping(item, name="predicate item"))
            for item in items
        ]
        return all(results) if operator == "and" else any(results)
    if operator == "not":
        item = source.get("item")
        return not _predicate_matches(
            reference, _mapping(item, name="predicate item")
        )
    field = str(source.get("field") or "")
    if not field:
        raise ValueError("predicate.field is required")
    present, actual = _reference_field(reference, field)
    if operator == "exists":
        return present is bool(source.get("exists", True))
    if operator not in {
        "eq",
        "ne",
        "lt",
        "lte",
        "gt",
        "gte",
        "in",
        "contains",
    }:
        raise ValueError("selector predicate operator is unsupported")
    if not present:
        return False
    expected = source.get("value")
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if operator in {"lt", "lte", "gt", "gte"}:
        left = _finite_number(actual, name="predicate field")
        right = _finite_number(expected, name="predicate value")
        return {
            "lt": left < right,
            "lte": left <= right,
            "gt": left > right,
            "gte": left >= right,
        }[operator]
    if operator == "in":
        if not isinstance(expected, (list, tuple)):
            raise ValueError("predicate in requires a list value")
        return actual in expected
    try:
        return expected in actual
    except TypeError:
        return False


def _identity(value: Any, fallback: Any = "") -> str:
    if isinstance(value, Mapping):
        return str(value.get("id") or value.get("name") or fallback)
    return str(fallback)


def _collection_items(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key), item
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield _identity(item, index), item


def _root_references(
    model: Mapping[str, Any], kind: str
) -> list[EntityReference]:
    if kind == "document":
        return [EntityReference(kind, "document", (), model, {})]
    if kind == "font":
        return [EntityReference(kind, "font", ("font",), model.get("font", {}), {})]
    if kind == "glyph":
        result = []
        for index, (name, glyph) in enumerate(_collection_items(model.get("glyphs", {}))):
            glyph_name = str(glyph.get("name") or name) if isinstance(glyph, Mapping) else name
            result.append(
                EntityReference(
                    kind, glyph_name, ("glyphs", name), glyph, {}, index
                )
            )
        return result
    root = _ROOT_COLLECTIONS.get(kind)
    if root is None:
        return []
    return [
        EntityReference(kind, identity, (root, identity), item, {}, index)
        for index, (identity, item) in enumerate(
            _collection_items(model.get(root, ()))
        )
    ]


def _layer_references(model: Mapping[str, Any]) -> list[EntityReference]:
    result: list[EntityReference] = []
    for glyph_ref in _root_references(model, "glyph"):
        glyph = glyph_ref.value
        if not isinstance(glyph, Mapping):
            continue
        for index, (layer_id, layer) in enumerate(
            _collection_items(glyph.get("layers", ()))
        ):
            parent = {
                "glyphName": glyph_ref.identity,
                "masterId": str(layer.get("masterId") or "")
                if isinstance(layer, Mapping)
                else "",
            }
            result.append(
                EntityReference(
                    "layer",
                    layer_id,
                    glyph_ref.path + ("layers", layer_id),
                    layer,
                    parent,
                    index,
                )
            )
    return result


def _nested_references(
    model: Mapping[str, Any], kind: str
) -> list[EntityReference]:
    result: list[EntityReference] = []
    for layer_ref in _layer_references(model):
        layer = layer_ref.value
        if not isinstance(layer, Mapping):
            continue
        if kind == "shape":
            source = layer.get("shapes", ())
        elif kind == "anchor":
            source = layer.get("anchors", ())
        elif kind == "node":
            for shape_id, shape in _collection_items(layer.get("shapes", ())):
                if not isinstance(shape, Mapping) or str(shape.get("kind") or "") != "path":
                    continue
                path = shape.get("value")
                if not isinstance(path, Mapping):
                    continue
                for index, (node_id, node) in enumerate(
                    _collection_items(path.get("nodes", ()))
                ):
                    result.append(
                        EntityReference(
                            "node",
                            node_id,
                            layer_ref.path
                            + ("shapes", shape_id, "value", "nodes", node_id),
                            node,
                            {
                                **dict(layer_ref.parent),
                                "layerId": layer_ref.identity,
                                "shapeId": shape_id,
                            },
                            index,
                        )
                    )
            continue
        else:
            continue
        for index, (identity, item) in enumerate(_collection_items(source)):
            result.append(
                EntityReference(
                    kind,
                    identity,
                    layer_ref.path + (("shapes" if kind == "shape" else "anchors"), identity),
                    item,
                    {
                        **dict(layer_ref.parent),
                        "layerId": layer_ref.identity,
                    },
                    index,
                )
            )
    return result


def _kerning_references(model: Mapping[str, Any]) -> list[EntityReference]:
    source = model.get("kerning", {})
    if not isinstance(source, Mapping):
        return []
    result: list[EntityReference] = []
    directional = any(key in source for key in ("ltr", "rtl", "vertical", "context"))
    if directional:
        for direction in ("ltr", "rtl", "vertical"):
            masters = source.get(direction, {})
            if not isinstance(masters, Mapping):
                continue
            for master_id, lefts in masters.items():
                if not isinstance(lefts, Mapping):
                    continue
                for left, rights in lefts.items():
                    if not isinstance(rights, Mapping):
                        continue
                    for right, value in rights.items():
                        identity = "/".join((direction, str(master_id), str(left), str(right)))
                        result.append(
                            EntityReference(
                                "kerning",
                                identity,
                                ("kerning", direction, str(master_id), str(left), str(right)),
                                value,
                                {
                                    "direction": direction,
                                    "masterId": str(master_id),
                                    "left": str(left),
                                    "right": str(right),
                                },
                            )
                        )
        contexts = source.get("context", {})
        if isinstance(contexts, Mapping):
            for key, masters in contexts.items():
                if not isinstance(masters, Mapping):
                    continue
                for master_id, value in masters.items():
                    identity = "/".join(("context", str(key), str(master_id)))
                    result.append(
                        EntityReference(
                            "kerning",
                            identity,
                            ("kerning", "context", str(key), str(master_id)),
                            value,
                            {
                                "direction": "context",
                                "contextKey": str(key),
                                "masterId": str(master_id),
                            },
                        )
                    )
        return result
    for master_id, lefts in source.items():
        if not isinstance(lefts, Mapping):
            continue
        for left, rights in lefts.items():
            if not isinstance(rights, Mapping):
                continue
            for right, value in rights.items():
                identity = "/".join(("ltr", str(master_id), str(left), str(right)))
                result.append(
                    EntityReference(
                        "kerning",
                        identity,
                        ("kerning", str(master_id), str(left), str(right)),
                        value,
                        {
                            "direction": "ltr",
                            "masterId": str(master_id),
                            "left": str(left),
                            "right": str(right),
                        },
                    )
                )
    return result


def resolve_selector(
    model: Mapping[str, Any], selector: Mapping[str, Any]
) -> tuple[EntityReference, ...]:
    """Resolve one closed selector deterministically against a snapshot."""

    source = _mapping(selector, name="selector")
    kind = str(source.get("entity") or "")
    if kind not in ENTITY_KINDS:
        raise ValueError("selector.entity is unsupported")
    if kind == "layer":
        values = _layer_references(model)
    elif kind in {"shape", "node", "anchor"}:
        values = _nested_references(model, kind)
    elif kind == "kerning":
        values = _kerning_references(model)
    else:
        values = _root_references(model, kind)
    ids_value = source.get("ids") or ()
    if not isinstance(ids_value, (list, tuple)):
        raise ValueError("selector.ids must be a list")
    ids = {str(item) for item in ids_value}
    parent = source.get("parent") or {}
    where = source.get("where") or {}
    if not isinstance(parent, Mapping) or not isinstance(where, Mapping):
        raise ValueError("selector.parent and selector.where must be objects")
    predicate = source.get("predicate")
    if predicate is not None and not isinstance(predicate, Mapping):
        raise ValueError("selector.predicate must be an object")
    selected = [
        ref
        for ref in values
        if (not ids or ref.identity in ids)
        and all(str(ref.parent.get(str(key), "")) == str(value) for key, value in parent.items())
        and _matches_where(ref.value, where)
        and (
            predicate is None
            or _predicate_matches(ref, predicate)
        )
    ]
    order_value = source.get("orderBy") or "identity"
    if isinstance(order_value, Mapping):
        order_by = str(order_value.get("field") or "identity")
        order_type = str(order_value.get("type") or "auto")
        reverse = bool(order_value.get("descending", False))
    else:
        order_by = str(order_value)
        order_type = "text"
        reverse = bool(source.get("descending", False))
    if order_by == "canonical":
        if reverse:
            selected.reverse()
    elif order_by == "identity":
        selected.sort(key=lambda ref: (ref.identity, ref.path), reverse=reverse)
    elif order_by:
        def order_key(ref: EntityReference) -> tuple[Any, ...]:
            present, value = _reference_field(ref, order_by)
            if order_type == "number" and present:
                try:
                    value = _finite_number(value, name="numeric order field")
                except ValueError:
                    present = False
                    value = Decimal(0)
            elif order_type == "auto" and present and isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                value = _finite_number(value, name="numeric order field")
            else:
                value = str(value) if present else ""
            return (not present, value, ref.identity)
        selected.sort(
            key=order_key,
            reverse=reverse,
        )
    return tuple(selected)


def reduce_references(
    references: Sequence[EntityReference],
    reducers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate deterministic generic reducers over a resolved selector."""

    result: dict[str, Any] = {}
    for index, raw in enumerate(reducers):
        reducer = _mapping(raw, name="projection.reducer")
        name = str(reducer.get("name") or "reducer-{}".format(index + 1))
        if name in result:
            raise ValueError("projection reducer names must be unique")
        operation = str(reducer.get("op") or "")
        field = str(reducer.get("field") or "")
        if operation == "count":
            result[name] = len(references)
            continue
        if operation not in {"min", "max", "sum", "average", "any", "all"}:
            raise ValueError("projection reducer operator is unsupported")
        if not field:
            raise ValueError("projection reducer field is required")
        values = [
            value
            for reference in references
            for present, value in [_reference_field(reference, field)]
            if present
        ]
        if operation in {"any", "all"}:
            result[name] = (
                any(bool(value) for value in values)
                if operation == "any"
                else all(bool(value) for value in values)
            )
            continue
        numbers = [
            _finite_number(value, name="reducer field") for value in values
        ]
        if not numbers:
            result[name] = None
        elif operation == "min":
            result[name] = _public_number(min(numbers))
        elif operation == "max":
            result[name] = _public_number(max(numbers))
        elif operation == "sum":
            result[name] = _public_number(sum(numbers, Decimal(0)))
        else:
            result[name] = _public_number(
                sum(numbers, Decimal(0)) / Decimal(len(numbers))
            )
    return result


def bind_relation_selector(
    parent_reference: EntityReference, selector: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind a nested selector to the exact identity of its parent entity."""

    bound = copy.deepcopy(dict(_mapping(selector, name="relation.selector")))
    child_kind = str(bound.get("entity") or "")
    implicit: dict[str, str] = {}
    if parent_reference.kind == "glyph" and child_kind in {
        "layer",
        "shape",
        "node",
        "anchor",
    }:
        implicit["glyphName"] = parent_reference.identity
    elif parent_reference.kind == "master" and child_kind in {"layer", "kerning"}:
        implicit["masterId"] = parent_reference.identity
    elif parent_reference.kind == "layer" and child_kind in {"shape", "node", "anchor"}:
        implicit.update(
            {
                "glyphName": str(parent_reference.parent.get("glyphName") or ""),
                "layerId": parent_reference.identity,
            }
        )
    elif parent_reference.kind == "shape" and child_kind == "node":
        implicit.update(
            {
                "glyphName": str(parent_reference.parent.get("glyphName") or ""),
                "layerId": str(parent_reference.parent.get("layerId") or ""),
                "shapeId": parent_reference.identity,
            }
        )
    requested_parent = bound.get("parent") or {}
    if not isinstance(requested_parent, Mapping):
        raise ValueError("relation selector parent must be an object")
    for key, value in implicit.items():
        if key in requested_parent and str(requested_parent[key]) != value:
            raise ValueError("relation selector conflicts with its parent identity")
    bound["parent"] = {**dict(requested_parent), **implicit}
    return bound


def _observation_for(
    observations: Mapping[tuple[str, str], Mapping[str, Any]],
    reference: EntityReference,
) -> Mapping[str, Any]:
    if reference.kind in {"document", "font"}:
        return observations.get(("__document__", "persistence"), {})
    if reference.kind != "layer":
        return {}
    return observations.get(
        (str(reference.parent.get("glyphName") or ""), reference.identity), {}
    )


def _spacing_projection(
    layer: Mapping[str, Any], observation: Mapping[str, Any], axis: str
) -> Optional[dict[str, Any]]:
    bounds = observation.get("bounds")
    metrics = observation.get("currentMetrics")
    metrics = metrics if isinstance(metrics, Mapping) else {}
    if axis == "horizontal":
        advance = metrics.get("width", layer.get("width"))
        origin = None
        leading = metrics.get("leftBearing")
        trailing = metrics.get("rightBearing")
        if isinstance(bounds, Mapping):
            x, width = bounds.get("x"), bounds.get("width")
            if leading is None and isinstance(x, (int, float)):
                leading = x
            if (
                trailing is None
                and isinstance(advance, (int, float))
                and isinstance(x, (int, float))
                and isinstance(width, (int, float))
            ):
                trailing = advance - x - width
    else:
        advance = metrics.get("verticalAdvance", metrics.get("vertWidth", layer.get("vertWidth")))
        origin = metrics.get("verticalOrigin", metrics.get("vertOrigin", layer.get("vertOrigin")))
        leading = metrics.get("topBearing")
        trailing = metrics.get("bottomBearing")
        if isinstance(bounds, Mapping):
            y, height = bounds.get("y"), bounds.get("height")
            if (
                leading is None
                and isinstance(origin, (int, float))
                and isinstance(y, (int, float))
                and isinstance(height, (int, float))
            ):
                leading = origin - y - height
            if (
                trailing is None
                and isinstance(advance, (int, float))
                and isinstance(origin, (int, float))
                and isinstance(y, (int, float))
            ):
                trailing = y - (origin - advance)
    return {
        "advance": advance,
        "origin": origin,
        "leadingBearing": leading,
        "trailingBearing": trailing,
    }


def project_reference(
    reference: EntityReference,
    projection: Mapping[str, Any],
    *,
    observations: Optional[Mapping[tuple[str, str], Mapping[str, Any]]] = None,
    effective_metadata: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    source = _mapping(projection, name="projection")
    scalar_value_field = SCALAR_VALUE_FIELDS.get(reference.kind)
    fields_value = source.get("fields") or (
        ["id", scalar_value_field]
        if scalar_value_field
        else ["id", "name"]
    )
    if not isinstance(fields_value, (list, tuple)) or not fields_value:
        raise ValueError("projection.fields must contain at least one field")
    fields = tuple(dict.fromkeys(str(field) for field in fields_value))
    observation = _observation_for(observations or {}, reference)
    values: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    missing: list[str] = []
    for field in fields:
        if field == "canonicalPath":
            values[field] = list(reference.path)
            provenance[field] = "canonical"
            continue
        if field == "collection.index":
            values[field] = reference.collection_index
            provenance[field] = (
                "canonical" if reference.collection_index is not None else "unavailable"
            )
            if reference.collection_index is None:
                missing.append(field)
            continue
        if field == "ownership":
            values[field] = dict(reference.parent)
            provenance[field] = "canonical"
            continue
        if field == "bounds":
            raw = observation.get("bounds") if isinstance(observation, Mapping) else None
            values[field] = copy.deepcopy(raw) if isinstance(raw, Mapping) else None
            provenance[field] = "native" if isinstance(raw, Mapping) else "unavailable"
            if raw is None:
                missing.append(field)
            continue
        if field == "compilation.diagnostics":
            diagnostics = (observations or {}).get(
                ("__document__", "compilation.diagnostics")
            )
            values[field] = (
                copy.deepcopy(diagnostics)
                if isinstance(diagnostics, Mapping)
                else None
            )
            provenance[field] = (
                "detached-native"
                if isinstance(diagnostics, Mapping)
                else "unavailable"
            )
            if diagnostics is None:
                missing.append(field)
            continue
        if field == "persistence":
            raw = (observations or {}).get(("__document__", "persistence"))
            values[field] = copy.deepcopy(raw) if isinstance(raw, Mapping) else None
            provenance[field] = "native+process" if isinstance(raw, Mapping) else "unavailable"
            if not isinstance(raw, Mapping):
                missing.append(field)
            continue
        if field in {"spacing.horizontal", "spacing.vertical"}:
            if reference.kind != "layer" or not isinstance(reference.value, Mapping):
                values[field] = None
                provenance[field] = "unavailable"
                missing.append(field)
                continue
            projected = _spacing_projection(
                reference.value,
                observation,
                "horizontal" if field.endswith("horizontal") else "vertical",
            )
            values[field] = projected
            provenance[field] = "derived"
            required_values = (
                ("advance", "leadingBearing", "trailingBearing")
                if field.endswith("horizontal")
                else ("advance", "origin", "leadingBearing", "trailingBearing")
            )
            if projected is None or any(
                projected.get(name) is None for name in required_values
            ):
                missing.append(field)
            continue
        if field == "geometry.counts":
            if reference.kind != "layer" or not isinstance(reference.value, Mapping):
                values[field] = None
                provenance[field] = "unavailable"
                missing.append(field)
            else:
                paths = layer_paths(reference.value)
                values[field] = {
                    "pathCount": len(paths),
                    "nodeCount": sum(len(path.get("nodes") or ()) for path in paths),
                    "componentCount": len(layer_components(reference.value)),
                    "anchorCount": len(layer_anchors(reference.value)),
                }
                provenance[field] = "derived"
            continue
        if field == "geometry.transform":
            shape = reference.value if reference.kind == "shape" else None
            value = shape.get("value") if isinstance(shape, Mapping) else None
            kind = str(shape.get("kind") or "") if isinstance(shape, Mapping) else ""
            transform = (
                _affine_transform(value)
                if kind in {"component", "image"} and isinstance(value, Mapping)
                else None
            )
            values[field] = transform
            provenance[field] = "derived" if transform is not None else "unavailable"
            if transform is None:
                missing.append(field)
            continue
        if field == "alignment":
            if reference.kind != "layer" or not isinstance(reference.value, Mapping):
                values[field] = None
                provenance[field] = "unavailable"
                missing.append(field)
            else:
                components = layer_components(reference.value)
                modes = [int(component.get("alignment", 0)) for component in components]
                values[field] = {
                    "hasAlignedWidth": observation.get("hasAlignedWidth"),
                    "effectiveLayerAlignment": observation.get("isAligned"),
                    "configuredAutomaticComponentCount": sum(
                        mode != -1 for mode in modes
                    ),
                    "modeCounts": {
                        str(mode): sum(value == mode for value in modes)
                        for mode in (-1, 0, 1, 3)
                    },
                    "componentCount": len(components),
                }
                provenance[field] = (
                    "native+derived"
                    if {"hasAlignedWidth", "isAligned"}.issubset(observation)
                    else "derived"
                )
                if not {"hasAlignedWidth", "isAligned"}.issubset(observation):
                    missing.append(field)
            continue
        if field == "inheritance.metrics":
            if reference.kind != "layer" or not isinstance(reference.value, Mapping):
                values[field] = None
                provenance[field] = "unavailable"
                missing.append(field)
            else:
                values[field] = {
                    "keys": {
                        "left": reference.value.get("leftMetricsKey"),
                        "right": reference.value.get("rightMetricsKey"),
                        "width": reference.value.get("widthMetricsKey"),
                        "top": reference.value.get("topMetricsKey"),
                        "bottom": reference.value.get("bottomMetricsKey"),
                        "verticalWidth": reference.value.get("vertWidthMetricsKey"),
                    },
                    "current": copy.deepcopy(observation.get("currentMetrics")),
                    "resolved": copy.deepcopy(observation.get("resolvedMetrics")),
                }
                provenance[field] = "canonical+native"
                if not isinstance(observation.get("resolvedMetrics"), Mapping):
                    missing.append(field)
            continue
        if field == "grid":
            if reference.kind not in {"font", "document"}:
                values[field] = None
                provenance[field] = "unavailable"
                missing.append(field)
            else:
                font = (
                    reference.value
                    if reference.kind == "font"
                    else reference.value.get("font", {})
                    if isinstance(reference.value, Mapping)
                    else {}
                )
                if not isinstance(font, Mapping):
                    font = {}
                values[field] = {
                    "grid": font.get("grid"),
                    "subdivision": font.get("gridSubDivision"),
                }
                provenance[field] = "derived"
            continue
        if field == "metadata.effective":
            glyph_name = (
                reference.identity
                if reference.kind == "glyph"
                else str(reference.parent.get("glyphName") or "")
            )
            metadata = (effective_metadata or {}).get(glyph_name)
            values[field] = copy.deepcopy(metadata) if isinstance(metadata, Mapping) else None
            provenance[field] = "native" if isinstance(metadata, Mapping) else "unavailable"
            if metadata is None:
                missing.append(field)
            continue
        present, value = _reference_field(reference, field)
        if not present and field == "id":
            present, value = True, reference.identity
        values[field] = value if present else None
        provenance[field] = "canonical" if present else "unavailable"
        if not present:
            missing.append(field)
    return {
        **reference.public_identity(),
        "values": values,
        "provenance": provenance if bool(source.get("includeProvenance", True)) else {},
        "completeness": "complete" if not missing else "partial",
        "missingFields": missing,
    }


def _observation_field(field: str) -> Optional[tuple[str, str]]:
    prefix = "observation."
    if not str(field).startswith(prefix):
        return None
    requested = str(field)[len(prefix) :]
    for projection in sorted(COMPUTED_PROJECTIONS, key=len, reverse=True):
        if requested == projection:
            return projection, ""
        if requested.startswith(projection + "."):
            return projection, requested[len(projection) + 1 :]
    raise ValueError("observation field uses an unsupported projection")


def constraint_observation_request(
    model: Mapping[str, Any],
    constraints: Sequence[Mapping[str, Any]],
    *,
    phase: str,
) -> dict[str, Any]:
    """Return the exact observation scope needed by one constraint phase."""

    fields: set[str] = set()
    glyph_names: set[str] = set()
    for raw in constraints:
        constraint = _mapping(raw, name="constraint")
        if str(constraint.get("phase") or "before") != phase:
            continue
        for side in ("left", "right"):
            operand = constraint.get(side)
            if not isinstance(operand, Mapping) or str(operand.get("kind") or "") != "field":
                continue
            observed = _observation_field(str(operand.get("field") or ""))
            if observed is None:
                continue
            fields.add(observed[0])
            selector = operand.get("selector")
            if not isinstance(selector, Mapping):
                continue
            for reference in resolve_selector(model, selector):
                glyph_name = (
                    reference.identity
                    if reference.kind == "glyph"
                    else str(reference.parent.get("glyphName") or "")
                )
                if glyph_name:
                    glyph_names.add(glyph_name)
    return {
        "fields": tuple(sorted(fields)),
        "glyphNames": tuple(sorted(glyph_names)),
        "includeGeometry": bool(
            fields.intersection({"bounds", "spacing.horizontal", "spacing.vertical"})
        ),
        "includeMetrics": bool(
            fields.intersection(
                {"spacing.horizontal", "spacing.vertical", "inheritance.metrics"}
            )
        ),
        "resolveMetrics": "inheritance.metrics" in fields,
    }


def _selector_operand(
    model: Mapping[str, Any],
    operand: Mapping[str, Any],
    *,
    observations: Mapping[tuple[str, str], Mapping[str, Any]],
    effective_metadata: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    kind = str(operand.get("kind") or "")
    if kind == "literal":
        return {
            "present": True,
            "value": copy.deepcopy(operand.get("value")),
            "target": None,
            "provenance": "literal",
            "completeness": "complete",
        }
    if kind == "reference":
        selector = operand.get("selector")
        if not isinstance(selector, Mapping):
            raise ValueError("reference operands require selector")
        references = resolve_selector(model, selector)
        if len(references) != 1:
            raise ValueError("reference operands must resolve exactly one entity")
        identity = references[0].public_identity()
        return {
            "present": True,
            "value": identity,
            "target": identity,
            "provenance": "canonical",
            "completeness": "complete",
        }
    if kind != "field":
        raise ValueError(
            "constraint operands require kind=literal, kind=field, or kind=reference"
        )
    selector = operand.get("selector")
    field = str(operand.get("field") or "")
    if not isinstance(selector, Mapping) or not field:
        raise ValueError("field operands require selector and field")
    references = resolve_selector(model, selector)
    if len(references) != 1:
        raise ValueError("field operands must resolve exactly one entity")
    reference = references[0]
    target = {**reference.public_identity(), "field": field}
    observed = _observation_field(field)
    if observed is None:
        present, value = _reference_field(reference, field)
        return {
            "present": present,
            "value": value,
            "target": target,
            "provenance": "canonical" if present else "unavailable",
            "completeness": "complete" if present else "unavailable",
        }
    projection, nested = observed
    item = project_reference(
        reference,
        {"fields": [projection], "includeProvenance": True},
        observations=observations,
        effective_metadata=effective_metadata,
    )
    projected = item.get("values", {}).get(projection)
    present, value = _nested_value(projected, nested)
    provenance = str(item.get("provenance", {}).get(projection) or "unavailable")
    return {
        "present": present and provenance != "unavailable" and value is not None,
        "value": value,
        "target": target,
        "provenance": provenance,
        "completeness": (
            "complete"
            if present and provenance != "unavailable" and value is not None
            else "unavailable"
        ),
    }


def _compare(left: Any, operator: str, right: Any, tolerance: Any) -> bool:
    if operator == "eq":
        return left == right
    if operator == "ne":
        return left != right
    if operator in {"lt", "lte", "gt", "gte", "within", "in_range"}:
        if operator == "in_range":
            if not isinstance(right, (list, tuple)) or len(right) != 2:
                raise ValueError("in_range requires a two-value literal operand")
            number = _finite_number(left, name="constraint left")
            return _finite_number(right[0], name="constraint minimum") <= number <= _finite_number(right[1], name="constraint maximum")
        left_number = _finite_number(left, name="constraint left")
        right_number = _finite_number(right, name="constraint right")
        if operator == "lt":
            return left_number < right_number
        if operator == "lte":
            return left_number <= right_number
        if operator == "gt":
            return left_number > right_number
        if operator == "gte":
            return left_number >= right_number
        return abs(left_number - right_number) <= _finite_number(
            0 if tolerance is None else tolerance, name="constraint tolerance"
        )
    raise ValueError("unsupported constraint operator")


def evaluate_constraints(
    model: Mapping[str, Any],
    constraints: Sequence[Mapping[str, Any]],
    *,
    phase: str,
    observations: Optional[Mapping[tuple[str, str], Mapping[str, Any]]] = None,
    effective_metadata: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(constraints):
        constraint = _mapping(raw, name="constraint")
        requested_phase = str(constraint.get("phase") or "before")
        if requested_phase != phase:
            continue
        operator = str(constraint.get("operator") or "")
        if operator not in CONSTRAINT_OPERATORS:
            raise ValueError("constraint.operator is unsupported")
        label = str(constraint.get("label") or "constraint-{}".format(index + 1))
        try:
            left_evidence = _selector_operand(
                model,
                _mapping(constraint.get("left"), name="constraint.left"),
                observations=observations or {},
                effective_metadata=effective_metadata or {},
            )
            right_evidence = _selector_operand(
                model,
                _mapping(constraint.get("right"), name="constraint.right"),
                observations=observations or {},
                effective_metadata=effective_metadata or {},
            )
            left_present = bool(left_evidence["present"])
            right_present = bool(right_evidence["present"])
            left = left_evidence["value"]
            right = right_evidence["value"]
            passed = bool(
                left_present
                and right_present
                and _compare(left, operator, right, constraint.get("tolerance"))
            )
            error = None
        except (TypeError, ValueError) as exc:
            left_present = right_present = False
            left = right = None
            left_evidence = right_evidence = {
                "target": None,
                "provenance": "unavailable",
                "completeness": "unavailable",
            }
            passed = False
            error = str(exc)
        items.append(
            {
                "label": label,
                "phase": phase,
                "operator": operator,
                "passed": passed,
                "leftPresent": left_present,
                "rightPresent": right_present,
                "left": copy.deepcopy(left),
                "right": copy.deepcopy(right),
                "leftTarget": left_evidence["target"],
                "rightTarget": right_evidence["target"],
                "leftProvenance": left_evidence["provenance"],
                "rightProvenance": right_evidence["provenance"],
                "leftCompleteness": left_evidence["completeness"],
                "rightCompleteness": right_evidence["completeness"],
                "error": error,
            }
        )
    failed = sum(not item["passed"] for item in items)
    return {
        "phase": phase,
        "constraintCount": len(items),
        "passedCount": len(items) - failed,
        "failedCount": failed,
        "passed": failed == 0,
        "items": items,
    }


def _container_at(model: MutableMapping[str, Any], path: Sequence[str]) -> tuple[Any, str]:
    if not path:
        raise ValueError("the document root cannot be replaced by an operation")
    current: Any = model
    for part in path[:-1]:
        if isinstance(current, MutableMapping):
            if part not in current:
                raise ValueError("canonical path is missing: {}".format("/".join(path)))
            current = current[part]
        elif isinstance(current, list):
            index = find_entity_index(current, part)
            if index is None:
                try:
                    index = int(part)
                except ValueError as exc:
                    raise ValueError("canonical entity is missing: {}".format(part)) from exc
            current = current[index]
        else:
            raise ValueError("canonical path traverses a scalar")
    return current, str(path[-1])


def _set_path(model: MutableMapping[str, Any], path: Sequence[str], value: Any) -> None:
    container, leaf = _container_at(model, path)
    if isinstance(container, MutableMapping):
        container[leaf] = copy.deepcopy(value)
        return
    if isinstance(container, list):
        index = find_entity_index(container, leaf)
        if index is None:
            try:
                index = int(leaf)
            except ValueError as exc:
                raise ValueError("canonical entity is missing: {}".format(leaf)) from exc
        container[index] = copy.deepcopy(value)
        return
    raise ValueError("canonical set target is not writable")


def _remove_path(model: MutableMapping[str, Any], path: Sequence[str]) -> None:
    container, leaf = _container_at(model, path)
    if isinstance(container, MutableMapping):
        if leaf not in container:
            raise ValueError("canonical target is missing")
        del container[leaf]
        return
    if isinstance(container, list):
        index = find_entity_index(container, leaf)
        if index is None:
            raise ValueError("canonical entity is missing")
        container.pop(index)
        return
    raise ValueError("canonical remove target is not writable")


def _quantize(value: Any, model: Mapping[str, Any], quantizer: str) -> Any:
    number = _finite_number(value, name="operation value")
    if quantizer != "exact":
        raise ValueError("quantizer must be exact; grid snapping is unsupported")
    return _public_number(number)


def _translate_node(
    node: MutableMapping[str, Any], x: Decimal, y: Decimal
) -> list[tuple[str, ...]]:
    touched: list[tuple[str, ...]] = []
    if x:
        node["x"] = _public_number(
            _finite_number(node.get("x"), name="node x") + x
        )
        touched.append(("x",))
    if y:
        node["y"] = _public_number(
            _finite_number(node.get("y"), name="node y") + y
        )
        touched.append(("y",))
    return touched


def _translate_position(
    value: MutableMapping[str, Any], x: Decimal, y: Decimal
) -> list[tuple[str, ...]]:
    position = list(value.get("position") or ())
    if len(position) != 2:
        raise ValueError("translation target position is incomplete")
    if x:
        position[0] = _public_number(
            _finite_number(position[0], name="position x") + x
        )
    if y:
        position[1] = _public_number(
            _finite_number(position[1], name="position y") + y
        )
    value["position"] = position
    return [("position",)]


def _translate_shape(
    shape: MutableMapping[str, Any], x: Decimal, y: Decimal
) -> list[tuple[str, ...]]:
    kind = str(shape.get("kind") or "")
    value = shape.get("value")
    if not isinstance(value, MutableMapping):
        raise ValueError("shape value must be a writable object")
    if kind == "path":
        touched: list[tuple[str, ...]] = []
        for node_id, node in _collection_items(value.get("nodes", ())):
            if not isinstance(node, MutableMapping):
                raise ValueError("path nodes must be writable objects")
            touched.extend(
                ("value", "nodes", node_id) + path
                for path in _translate_node(node, x, y)
            )
        return touched
    if kind in {"component", "image"}:
        return [("value",) + path for path in _translate_position(value, x, y)]
    return []


def _translate_anchor(
    anchor: MutableMapping[str, Any], x: Decimal, y: Decimal
) -> list[tuple[str, ...]]:
    return _translate_position(anchor, x, y)


def _translate_layer(
    layer: MutableMapping[str, Any], x: Decimal, y: Decimal
) -> list[tuple[str, ...]]:
    touched: list[tuple[str, ...]] = []
    for shape_id, shape in _collection_items(layer.get("shapes", ())):
        if not isinstance(shape, MutableMapping):
            raise ValueError("layer shapes must be writable objects")
        touched.extend(
            ("shapes", shape_id) + path
            for path in _translate_shape(shape, x, y)
        )
    for anchor_id, anchor in _collection_items(layer.get("anchors", ())):
        if not isinstance(anchor, MutableMapping):
            raise ValueError("layer anchors must be writable objects")
        touched.extend(
            ("anchors", anchor_id) + path
            for path in _translate_anchor(anchor, x, y)
        )
    return touched


_TRANSLATORS = {
    "layer": _translate_layer,
    "shape": _translate_shape,
    "node": _translate_node,
    "anchor": _translate_anchor,
}


def _translate_reference(
    reference: EntityReference, x: Decimal, y: Decimal
) -> list[tuple[str, ...]]:
    translator = _TRANSLATORS.get(reference.kind)
    if translator is None or not isinstance(reference.value, MutableMapping):
        raise ValueError("{} entities have no translatable coordinates".format(reference.kind))
    touched = translator(reference.value, x, y)
    if not touched:
        raise ValueError("translation target contains no coordinate-bearing geometry")
    return touched


def _matrix_values(value: Any, *, name: str = "transform matrix") -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != 6:
        raise ValueError("{} must contain six finite numbers".format(name))
    return tuple(float(_finite_number(item, name=name)) for item in value)


def _transform_xy(
    x_value: Any,
    y_value: Any,
    matrix: Sequence[float],
    model: Mapping[str, Any],
    quantizer: str,
) -> tuple[int | float, int | float]:
    x = float(_finite_number(x_value, name="transform x"))
    y = float(_finite_number(y_value, name="transform y"))
    a, b, c, d, tx, ty = matrix
    transformed_x = _quantize(a * x + c * y + tx, model, quantizer)
    transformed_y = _quantize(b * x + d * y + ty, model, quantizer)
    return transformed_x, transformed_y


def _transform_node(
    node: MutableMapping[str, Any],
    matrix: Sequence[float],
    model: Mapping[str, Any],
    quantizer: str,
) -> list[tuple[str, ...]]:
    before_x, before_y = node.get("x"), node.get("y")
    x, y = _transform_xy(node.get("x"), node.get("y"), matrix, model, quantizer)
    node["x"], node["y"] = x, y
    return [
        path
        for path, before, after in (
            (("x",), before_x, x),
            (("y",), before_y, y),
        )
        if before != after
    ]


def _transform_position(
    value: MutableMapping[str, Any],
    matrix: Sequence[float],
    model: Mapping[str, Any],
    quantizer: str,
) -> list[tuple[str, ...]]:
    position = value.get("position")
    if not isinstance(position, (list, tuple)) or len(position) != 2:
        raise ValueError("transform target position is incomplete")
    x, y = _transform_xy(position[0], position[1], matrix, model, quantizer)
    value["position"] = [x, y]
    return [("position",)] if tuple(position) != (x, y) else []


def _transform_component(
    value: MutableMapping[str, Any],
    matrix: Sequence[float],
    model: Mapping[str, Any],
    quantizer: str,
    composition: str,
    alignment_policy: str,
) -> list[tuple[str, ...]]:
    current = _affine_transform(value)
    if current is None:
        raise ValueError("component has no complete affine decomposition")
    if composition == "prepend":
        transformed = _matrix_multiply(matrix, current)
    elif composition == "append":
        transformed = _matrix_multiply(current, matrix)
    elif composition == "conjugate":
        transformed = _matrix_multiply(
            _matrix_multiply(matrix, current), _matrix_inverse(matrix)
        )
    elif composition == "unchanged":
        transformed = tuple(current)
    else:
        raise ValueError("componentComposition is unsupported")

    touched: list[tuple[str, ...]] = []
    if composition != "unchanged":
        decomposed = _decompose_component_matrix(transformed)
        position = decomposed["position"]
        position[0] = _quantize(position[0], model, quantizer)
        position[1] = _quantize(position[1], model, quantizer)
        for field_name in ("position", "scale", "angle", "slant"):
            field_value = decomposed[field_name]
            if value.get(field_name) != field_value:
                value[field_name] = field_value
                touched.append((field_name,))

    alignment = int(value.get("alignment", -1))
    make_explicit = alignment_policy == "explicit_all"
    if alignment_policy == "explicit_noncommuting":
        make_explicit = not _matrices_close(
            _matrix_multiply(matrix, current),
            _matrix_multiply(current, matrix),
        )
    elif alignment_policy not in {"preserve", "explicit_all"}:
        raise ValueError("alignmentPolicy is unsupported")
    if make_explicit and alignment != -1:
        value["alignment"] = -1
        touched.append(("alignment",))
    return touched


def _transform_shape(
    shape: MutableMapping[str, Any],
    matrix: Sequence[float],
    model: Mapping[str, Any],
    quantizer: str,
    composition: str,
    alignment_policy: str,
) -> list[tuple[str, ...]]:
    kind = str(shape.get("kind") or "")
    value = shape.get("value")
    if not isinstance(value, MutableMapping):
        raise ValueError("shape value must be a writable object")
    if kind == "path":
        touched: list[tuple[str, ...]] = []
        for node_id, node in _collection_items(value.get("nodes", ())):
            if not isinstance(node, MutableMapping):
                raise ValueError("path nodes must be writable objects")
            touched.extend(
                ("value", "nodes", node_id) + path
                for path in _transform_node(node, matrix, model, quantizer)
            )
        return touched
    if kind == "component":
        return [
            ("value",) + path
            for path in _transform_component(
                value,
                matrix,
                model,
                quantizer,
                composition,
                alignment_policy,
            )
        ]
    raise ValueError("transform supports only path and component shapes")


def _transform_layer(
    layer: MutableMapping[str, Any],
    matrix: Sequence[float],
    model: Mapping[str, Any],
    quantizer: str,
    include: Sequence[str],
    composition: str,
    alignment_policy: str,
) -> list[tuple[str, ...]]:
    requested = set(include)
    if not requested or not requested.issubset({"paths", "anchors", "components"}):
        raise ValueError("transform.include contains an unsupported geometry kind")
    touched: list[tuple[str, ...]] = []
    for shape_id, shape in _collection_items(layer.get("shapes", ())):
        if not isinstance(shape, MutableMapping):
            raise ValueError("layer shapes must be writable objects")
        kind = str(shape.get("kind") or "")
        if kind == "path" and "paths" in requested:
            touched.extend(
                ("shapes", shape_id) + path
                for path in _transform_shape(
                    shape, matrix, model, quantizer, composition, alignment_policy
                )
            )
        elif kind == "component" and "components" in requested:
            touched.extend(
                ("shapes", shape_id) + path
                for path in _transform_shape(
                    shape, matrix, model, quantizer, composition, alignment_policy
                )
            )
    if "anchors" in requested:
        for anchor_id, anchor in _collection_items(layer.get("anchors", ())):
            if not isinstance(anchor, MutableMapping):
                raise ValueError("layer anchors must be writable objects")
            touched.extend(
                ("anchors", anchor_id) + path
                for path in _transform_position(anchor, matrix, model, quantizer)
            )
    return touched


def _transform_reference(
    reference: EntityReference,
    matrix: Sequence[float],
    model: Mapping[str, Any],
    quantizer: str,
    include: Sequence[str],
    composition: str,
    alignment_policy: str,
) -> list[tuple[str, ...]]:
    if not isinstance(reference.value, MutableMapping):
        raise ValueError("transform target is not writable geometry")
    if reference.kind == "layer":
        touched = _transform_layer(
            reference.value,
            matrix,
            model,
            quantizer,
            include,
            composition,
            alignment_policy,
        )
    elif reference.kind == "shape":
        touched = _transform_shape(
            reference.value,
            matrix,
            model,
            quantizer,
            composition,
            alignment_policy,
        )
    elif reference.kind == "node":
        touched = _transform_node(reference.value, matrix, model, quantizer)
    elif reference.kind == "anchor":
        touched = _transform_position(reference.value, matrix, model, quantizer)
    else:
        raise ValueError("{} entities have no affine geometry".format(reference.kind))
    return touched


def _collection_for_insert(
    candidate: MutableMapping[str, Any], target: EntityReference, field: str
) -> Any:
    if not target.path:
        current: Any = candidate
        if field:
            current = candidate
            for part in field.split("."):
                if not isinstance(current, MutableMapping) or part not in current:
                    raise ValueError("insert target field is missing")
                current = current[part]
        if not isinstance(current, (MutableMapping, list)):
            raise ValueError("insert target is not a canonical collection")
        return current
    present, _value = semantic_value_at(candidate, target.path)
    if not present:
        raise ValueError("operation target disappeared")
    container, leaf = _container_at(candidate, target.path)
    current = container[leaf] if isinstance(container, Mapping) else container[find_entity_index(container, leaf)]
    if not isinstance(current, MutableMapping):
        if not isinstance(current, list):
            raise ValueError("insert target field must be a collection")
    if field:
        for part in field.split("."):
            if not isinstance(current, MutableMapping) or part not in current:
                raise ValueError("insert target field is missing")
            current = current[part]
    if not isinstance(current, (MutableMapping, list)):
        raise ValueError("insert target is not a canonical collection")
    return current


def _merge_execution_context(
    target: MutableMapping[str, Any], source: Mapping[str, Any]
) -> None:
    for key, value in source.items():
        if isinstance(value, Mapping):
            existing = target.setdefault(str(key), {})
            if not isinstance(existing, MutableMapping):
                raise ValueError("incompatible execution context")
            for nested_key, nested_value in value.items():
                if nested_key in existing and existing[nested_key] != nested_value:
                    raise ValueError("conflicting lifecycle source")
                existing[nested_key] = copy.deepcopy(nested_value)
        else:
            if key in target and target[key] != value:
                raise ValueError("conflicting execution context")
            target[str(key)] = copy.deepcopy(value)


def _copy_on_write_candidate(
    model: Mapping[str, Any], references: Sequence[EntityReference]
) -> MutableMapping[str, Any]:
    """Detach only roots/layers addressed by one direct generic operation."""

    if any(not reference.path for reference in references):
        return copy.deepcopy(dict(model))
    result: MutableMapping[str, Any] = dict(model)
    glyph_references = [
        reference
        for reference in references
        if reference.path and reference.path[0] == "glyphs"
    ]
    if glyph_references:
        source_glyphs = model.get("glyphs", {})
        if not isinstance(source_glyphs, Mapping):
            raise ValueError("glyphs must be a canonical mapping")
        glyphs: MutableMapping[str, Any] = dict(source_glyphs)
        result["glyphs"] = glyphs
        by_glyph: dict[str, list[EntityReference]] = {}
        for reference in glyph_references:
            if len(reference.path) < 2:
                raise ValueError("glyph operation path is incomplete")
            by_glyph.setdefault(str(reference.path[1]), []).append(reference)
        for glyph_name, scoped in by_glyph.items():
            source_glyph = source_glyphs.get(glyph_name)
            if not isinstance(source_glyph, Mapping):
                raise ValueError("glyph target disappeared")
            if any(reference.kind == "glyph" for reference in scoped):
                glyphs[glyph_name] = copy.deepcopy(dict(source_glyph))
                continue
            glyph = dict(source_glyph)
            source_layers = source_glyph.get("layers", ())
            layer_ids = {
                str(reference.path[3])
                for reference in scoped
                if len(reference.path) >= 4
                and reference.path[2] == "layers"
            }
            if isinstance(source_layers, Mapping):
                layers: Any = dict(source_layers)
                for layer_id in layer_ids:
                    if layer_id not in source_layers:
                        raise ValueError("layer target disappeared")
                    layers[layer_id] = copy.deepcopy(source_layers[layer_id])
            elif isinstance(source_layers, (list, tuple)):
                layers = list(source_layers)
                for layer_id in layer_ids:
                    index = find_entity_index(layers, layer_id)
                    if index is None:
                        raise ValueError("layer target disappeared")
                    layers[index] = copy.deepcopy(layers[index])
            else:
                raise ValueError("glyph layers must be a canonical collection")
            glyph["layers"] = layers
            glyphs[glyph_name] = glyph
    for root in {
        str(reference.path[0])
        for reference in references
        if reference.path and reference.path[0] != "glyphs"
    }:
        if root not in model:
            raise ValueError("operation root disappeared")
        result[root] = copy.deepcopy(model[root])
    return result


def _structural_lifecycle_build(
    candidate: Mapping[str, Any],
    operation: Mapping[str, Any],
    references: Sequence[EntityReference],
    cancellation_checkpoint: Optional[Callable[[], None]] = None,
) -> Optional[Any]:
    """Route ownership-sensitive operations through the structural registry."""

    kind = str(operation.get("op") or "")
    if len(references) != 1 or kind not in {"duplicate", "remove", "move"}:
        return None
    reference = references[0]
    if reference.kind == "master":
        from .structural_registry import build_master_updates

        update: dict[str, Any] = {
            "action": {"remove": "delete"}.get(kind, kind),
            "masterId": (
                str(operation.get("newId") or "")
                if kind == "duplicate"
                else reference.identity
            ),
        }
        if kind == "duplicate":
            update["sourceMasterId"] = reference.identity
            overrides = operation.get("overrides") or {}
            if not isinstance(overrides, Mapping):
                raise ValueError("duplicate.overrides must be an object")
            unsupported = set(overrides) - {"name", "italicAngle", "axes"}
            if unsupported:
                raise ValueError(
                    "master duplicate overrides are limited to name, italicAngle, and axes"
                )
            for name in ("name", "italicAngle", "axes"):
                if name in overrides:
                    update[name] = copy.deepcopy(overrides[name])
        if kind in {"duplicate", "move"} and operation.get("index") is not None:
            update["index"] = int(operation["index"])
        return build_master_updates(
            candidate,
            [update],
            cancellation_checkpoint=cancellation_checkpoint,
        )
    if reference.kind == "layer":
        from .structural_registry import build_layer_updates

        update = {
            "action": {"remove": "delete"}.get(kind, kind),
            "glyphName": str(reference.parent.get("glyphName") or ""),
            "layerId": (
                str(operation.get("newId") or "")
                if kind == "duplicate"
                else reference.identity
            ),
        }
        if kind == "duplicate":
            update["sourceLayerId"] = reference.identity
            overrides = operation.get("overrides") or {}
            if not isinstance(overrides, Mapping):
                raise ValueError("duplicate.overrides must be an object")
            unsupported = set(overrides) - {"name", "masterId", "interpolation"}
            if unsupported:
                raise ValueError(
                    "layer duplicate overrides are limited to name, masterId, and interpolation"
                )
            for name in ("name", "masterId", "interpolation"):
                if name in overrides:
                    update[name] = copy.deepcopy(overrides[name])
        if kind in {"duplicate", "move"} and operation.get("index") is not None:
            update["index"] = int(operation["index"])
        return build_layer_updates(candidate, [update])
    return None


def _numeric_value(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _batched_master_duplicates(
    candidate: Mapping[str, Any],
    operations: Sequence[Mapping[str, Any]],
    start: int,
    cancellation_checkpoint: Optional[Callable[[], None]] = None,
) -> tuple[Any, tuple[dict[str, Any], ...], int] | None:
    """Build one consecutive master-duplication run through one registry pass."""

    updates: list[dict[str, Any]] = []
    sources: list[tuple[Mapping[str, Any], EntityReference]] = []
    cursor = start
    while cursor < len(operations):
        operation = _mapping(operations[cursor], name="operation")
        if str(operation.get("op") or "") != "duplicate":
            break
        selector = _mapping(operation.get("target"), name="operation.target")
        references = resolve_selector(candidate, selector)
        if len(references) != 1 or references[0].kind != "master":
            break
        new_id = str(operation.get("newId") or "")
        if not new_id:
            raise ValueError("duplicate requires one source and newId")
        overrides = operation.get("overrides") or {}
        if not isinstance(overrides, Mapping):
            raise ValueError("duplicate.overrides must be an object")
        unsupported = set(overrides) - {"name", "italicAngle", "axes"}
        if unsupported:
            raise ValueError(
                "master duplicate overrides are limited to name, italicAngle, and axes"
            )
        update: dict[str, Any] = {
            "action": "duplicate",
            "sourceMasterId": references[0].identity,
            "masterId": new_id,
        }
        for name in ("name", "italicAngle", "axes"):
            if name in overrides:
                update[name] = copy.deepcopy(overrides[name])
        if operation.get("index") is not None:
            update["index"] = int(operation["index"])
        updates.append(update)
        sources.append((operation, references[0]))
        cursor += 1
    if len(updates) < 2:
        return None

    from .structural_registry import build_master_updates

    build = build_master_updates(
        candidate,
        updates,
        cancellation_checkpoint=cancellation_checkpoint,
    )
    normalized: list[dict[str, Any]] = []
    for offset, ((operation, source), update) in enumerate(zip(sources, updates)):
        new_id = str(update["masterId"])
        paths = [
            list(change.path)
            for change in build.change_set.changes
            if new_id in change.path or change.path == ("masters", ORDER_TOKEN)
        ]
        normalized.append(
            {
                "index": start + offset,
                "op": "duplicate",
                "target": copy.deepcopy(dict(operation["target"])),
                "resolvedPaths": paths,
                "resolvedTargetCount": 1,
                "changedTargetCount": 1,
                "skippedTargetCount": 0,
                "newId": new_id,
                "overrides": copy.deepcopy(dict(operation.get("overrides") or {})),
                **(
                    {"index": int(operation["index"])}
                    if operation.get("index") is not None
                    else {}
                ),
                "batchSize": len(updates),
            }
        )
    return build, tuple(normalized), cursor


def _batched_materializations(
    candidate: Mapping[str, Any],
    operations: Sequence[Mapping[str, Any]],
    start: int,
    cancellation_checkpoint: Optional[Callable[[], None]] = None,
) -> tuple[Any, tuple[dict[str, Any], ...], int] | None:
    """Build one adapter-prepared instance-to-master materialization run."""

    first = _mapping(operations[start], name="operation")
    if str(first.get("op") or "") != "materialize":
        return None
    prepared: list[Mapping[str, Any]] = []
    sources: list[tuple[Mapping[str, Any], EntityReference]] = []
    cursor = start
    while cursor < len(operations):
        operation = _mapping(operations[cursor], name="operation")
        if str(operation.get("op") or "") != "materialize":
            break
        if str(operation.get("destinationEntity") or "") != "master":
            raise ValueError("materialize currently supports destinationEntity=master")
        references = resolve_selector(
            candidate,
            _mapping(operation.get("target"), name="operation.target"),
        )
        if len(references) != 1 or references[0].kind != "instance":
            raise ValueError("materialize requires exactly one source instance")
        new_id = str(operation.get("newId") or "")
        if not new_id:
            raise ValueError("materialize requires newId")
        payload = operation.get("_materialized")
        if not isinstance(payload, Mapping):
            raise ValueError(
                "materialize requires detached-native preparation by the host adapter"
            )
        if str(payload.get("sourceInstanceId") or "") != references[0].identity:
            raise ValueError("materialized payload does not match its source instance")
        if str(dict(payload.get("master") or {}).get("id") or "") != new_id:
            raise ValueError("materialized payload does not match newId")
        prepared.append(payload)
        sources.append((operation, references[0]))
        cursor += 1

    from .structural_registry import build_materializations

    build = build_materializations(
        candidate,
        prepared,
        cancellation_checkpoint=cancellation_checkpoint,
    )
    normalized: list[dict[str, Any]] = []
    for offset, (operation, source) in enumerate(sources):
        new_id = str(operation["newId"])
        paths = [
            list(change.path)
            for change in build.change_set.changes
            if new_id in change.path or change.path == ("masters", ORDER_TOKEN)
        ]
        normalized.append(
            {
                "index": start + offset,
                "op": "materialize",
                "target": copy.deepcopy(dict(operation["target"])),
                "resolvedPaths": paths,
                "resolvedTargetCount": 1,
                "changedTargetCount": 1,
                "skippedTargetCount": 0,
                "destinationEntity": "master",
                "newId": new_id,
                "overrides": copy.deepcopy(dict(operation.get("overrides") or {})),
                **(
                    {"index": int(operation["index"])}
                    if operation.get("index") is not None
                    else {}
                ),
                "batchSize": len(prepared),
                "source": source.public_identity(),
            }
        )
    return build, tuple(normalized), cursor


def build_change_set(
    model: Mapping[str, Any],
    operations: Sequence[Mapping[str, Any]],
    *,
    cancellation_checkpoint: Optional[Callable[[], None]] = None,
) -> GenericMutationBuild:
    """Apply mechanical operations to a detached copy and return exact intent."""

    if not operations:
        raise ValueError("preview_change requires at least one operation")
    candidate: Mapping[str, Any] = model
    normalized: list[dict[str, Any]] = []
    capabilities: set[str] = set()
    execution_context: dict[str, Any] = {}
    index = 0
    while index < len(operations):
        if cancellation_checkpoint is not None:
            cancellation_checkpoint()
        raw = operations[index]
        operation = _mapping(raw, name="operation")
        kind = str(operation.get("op") or "")
        if kind not in OPERATION_KINDS:
            raise ValueError("operation.op is unsupported")
        selector = _mapping(operation.get("target"), name="operation.target")
        references = resolve_selector(candidate, selector)
        if kind == "insert":
            if len(references) != 1:
                raise ValueError("insert operations require exactly one parent target")
        elif not references:
            raise ValueError("operation target resolved no entities")
        if kind in {"move", "duplicate"} and len(references) != 1:
            raise ValueError("{} operations require exactly one target".format(kind))
        if (
            kind == "remove"
            and any(reference.kind in {"master", "layer"} for reference in references)
            and len(references) != 1
        ):
            raise ValueError(
                "master and layer removals require one exact target per operation"
            )

        materialized = _batched_materializations(
            candidate,
            operations,
            index,
            cancellation_checkpoint,
        )
        if materialized is not None:
            structural_batch, batch_normalized, next_index = materialized
            candidate = structural_batch.change_set.apply(candidate)
            capabilities.update(structural_batch.capabilities)
            _merge_execution_context(
                execution_context, structural_batch.execution_context
            )
            normalized.extend(batch_normalized)
            index = next_index
            continue

        batch = _batched_master_duplicates(
            candidate,
            operations,
            index,
            cancellation_checkpoint,
        )
        if batch is not None:
            structural_batch, batch_normalized, next_index = batch
            candidate = structural_batch.change_set.apply(candidate)
            capabilities.update(structural_batch.capabilities)
            _merge_execution_context(
                execution_context, structural_batch.execution_context
            )
            normalized.extend(batch_normalized)
            index = next_index
            continue
        resolved_paths: list[list[str]] = []
        normalized_values: dict[str, Any] = {}
        resolved_target_count = len(references)
        changed_target_count = resolved_target_count
        skipped_target_count = 0

        structural = _structural_lifecycle_build(
            candidate,
            operation,
            references,
            cancellation_checkpoint,
        )
        if structural is None:
            candidate = _copy_on_write_candidate(candidate, references)
            references = resolve_selector(candidate, selector)
        if structural is not None:
            candidate = structural.change_set.apply(candidate)
            capabilities.update(structural.capabilities)
            _merge_execution_context(execution_context, structural.execution_context)
            resolved_paths.extend(
                list(change.path) for change in structural.change_set.changes
            )
            normalized_values.update(
                {
                    key: copy.deepcopy(operation[key])
                    for key in ("index", "newId", "overrides")
                    if key in operation and operation[key] is not None
                }
            )
        elif kind == "set":
            field_name = str(operation.get("field") or "")
            if not field_name or field_name == "*":
                raise ValueError("set operations require one canonical field")
            quantizer = str(operation.get("quantizer") or "exact")
            if quantizer != "exact":
                raise ValueError(
                    "quantizer must be exact; grid snapping is unsupported"
                )
            raw_value = operation.get("value")
            value = (
                _quantize(raw_value, candidate, quantizer)
                if _numeric_value(raw_value)
                else copy.deepcopy(raw_value)
            )
            changed_target_count = 0
            skipped_target_count = 0
            for reference in references:
                path = (
                    reference.path
                    if SCALAR_VALUE_FIELDS.get(reference.kind) == field_name
                    and not isinstance(reference.value, Mapping)
                    else reference.path + tuple(field_name.split("."))
                )
                if path == ("settings", "disablesAutomaticAlignment"):
                    raise ValueError(
                        "the global automatic-alignment setting is protected"
                    )
                present, before_value = semantic_value_at(candidate, path)
                _set_path(candidate, path, value)
                if present and before_value == value:
                    skipped_target_count += 1
                else:
                    changed_target_count += 1
                    resolved_paths.append(list(path))
            normalized_values.update(
                {"field": field_name, "value": copy.deepcopy(value), "quantizer": quantizer}
            )
        elif kind == "translate":
            quantizer = str(operation.get("quantizer") or "exact")
            delta = _mapping(operation.get("delta") or {}, name="operation.delta")
            x = _quantize(delta.get("x", 0), candidate, quantizer)
            y = _quantize(delta.get("y", 0), candidate, quantizer)
            x_number = _finite_number(x, name="translation x")
            y_number = _finite_number(y, name="translation y")
            if not x_number and not y_number:
                changed_target_count = 0
                skipped_target_count = resolved_target_count
            else:
                for reference in references:
                    if not isinstance(reference.value, MutableMapping):
                        raise ValueError("translation target disappeared")
                    resolved_paths.extend(
                        list(reference.path + path)
                        for path in _translate_reference(
                            reference, x_number, y_number
                        )
                    )
            normalized_values.update(
                {"delta": {"x": x, "y": y}, "quantizer": quantizer}
            )
        elif kind == "transform":
            quantizer = str(operation.get("quantizer") or "exact")
            origin = operation.get("origin", [0, 0])
            matrix = _matrix_about_origin(
                _matrix_values(operation.get("matrix")),
                origin,
            )
            include_value = operation.get("include") or (
                "paths", "anchors", "components"
            )
            if not isinstance(include_value, (list, tuple)):
                raise ValueError("transform.include must be a list")
            include = tuple(dict.fromkeys(str(value) for value in include_value))
            composition = str(operation.get("componentComposition") or "prepend")
            alignment_policy = str(operation.get("alignmentPolicy") or "preserve")
            if composition == "conjugate":
                _matrix_inverse(matrix)
            changed_target_count = 0
            skipped_target_count = 0
            for reference in references:
                if cancellation_checkpoint is not None:
                    cancellation_checkpoint()
                touched = _transform_reference(
                    reference,
                    matrix,
                    candidate,
                    quantizer,
                    include,
                    composition,
                    alignment_policy,
                )
                if not touched:
                    skipped_target_count += 1
                    continue
                changed_target_count += 1
                resolved_paths.extend(
                    list(reference.path + path) for path in touched
                )
            if not changed_target_count:
                raise ValueError(
                    "transform target set produces no geometry change"
                )
            normalized_values.update(
                {
                    "matrix": [_clean_float(value) for value in matrix],
                    "origin": copy.deepcopy(list(origin))
                    if isinstance(origin, (list, tuple))
                    else [
                        copy.deepcopy(origin.get("x", 0)),
                        copy.deepcopy(origin.get("y", 0)),
                    ],
                    "quantizer": quantizer,
                    "include": list(include),
                    "componentComposition": composition,
                    "alignmentPolicy": alignment_policy,
                }
            )
        elif kind == "remove":
            for reference in sorted(references, key=lambda ref: ref.path, reverse=True):
                _remove_path(candidate, reference.path)
                resolved_paths.append(list(reference.path))
        elif kind == "move":
            position = int(operation.get("index"))
            for reference in references:
                container, leaf = _container_at(candidate, reference.path)
                if not isinstance(container, list):
                    raise ValueError("move operations require ordered entity collections")
                source_index = find_entity_index(container, leaf)
                if source_index is None:
                    raise ValueError("move target disappeared")
                item = container.pop(source_index)
                container.insert(max(0, min(position, len(container))), item)
                resolved_paths.append(list(reference.path[:-1] + (ORDER_TOKEN,)))
            normalized_values["index"] = position
        elif kind == "duplicate":
            new_id = str(operation.get("newId") or "")
            if not new_id or len(references) != 1:
                raise ValueError("duplicate requires one source and newId")
            reference = references[0]
            container, leaf = _container_at(candidate, reference.path)
            duplicate = copy.deepcopy(reference.value)
            overrides = operation.get("overrides") or {}
            if not isinstance(overrides, Mapping):
                raise ValueError("duplicate.overrides must be an object")
            if isinstance(duplicate, MutableMapping):
                duplicate["id"] = new_id
                duplicate.update(copy.deepcopy(dict(overrides)))
            if isinstance(container, list):
                if find_entity_index(container, new_id) is not None:
                    raise ValueError("duplicate identity already exists")
                source_index = find_entity_index(container, leaf)
                insert_at = int(
                    operation.get(
                        "index",
                        source_index + 1
                        if source_index is not None
                        else len(container),
                    )
                )
                container.insert(max(0, min(insert_at, len(container))), duplicate)
            elif isinstance(container, MutableMapping):
                if new_id in container:
                    raise ValueError("duplicate identity already exists")
                if reference.kind == "glyph" and isinstance(duplicate, MutableMapping):
                    duplicate["name"] = str(overrides.get("name") or new_id)
                container[new_id] = duplicate
            else:
                raise ValueError("duplicate target is not an entity")
            resolved_paths.append(list(reference.path[:-1] + (new_id,)))
            normalized_values.update(
                {
                    "newId": new_id,
                    "overrides": copy.deepcopy(dict(overrides)),
                    **(
                        {"index": int(operation["index"])}
                        if operation.get("index") is not None
                        else {}
                    ),
                }
            )
        elif kind == "insert":
            target = references[0]
            field_name = str(operation.get("field") or "")
            value = copy.deepcopy(operation.get("value"))
            collection = _collection_for_insert(candidate, target, field_name)
            identity = entity_id(value)
            if isinstance(collection, list):
                if not identity:
                    raise ValueError("inserted canonical entities require an id")
                if find_entity_index(collection, identity) is not None:
                    raise ValueError("inserted identity already exists")
                position = int(operation.get("index", len(collection)))
                collection.insert(max(0, min(position, len(collection))), value)
            else:
                key = str(operation.get("newId") or identity or "")
                if not key:
                    raise ValueError("mapping insertion requires newId")
                if key in collection:
                    raise ValueError("inserted identity already exists")
                collection[key] = value
                identity = key
            resolved_paths.append(
                list(
                    target.path
                    + (tuple(field_name.split(".")) if field_name else ())
                    + (str(identity),)
                )
            )
            normalized_values.update(
                {
                    "value": copy.deepcopy(value),
                    **({"field": field_name} if field_name else {}),
                    **(
                        {"newId": str(operation["newId"])}
                        if operation.get("newId") is not None
                        else {}
                    ),
                    **(
                        {"index": int(operation["index"])}
                        if operation.get("index") is not None
                        else {}
                    ),
                }
            )
        normalized.append(
            {
                "index": index,
                "op": kind,
                "target": copy.deepcopy(dict(selector)),
                "resolvedPaths": resolved_paths,
                "resolvedTargetCount": resolved_target_count,
                "changedTargetCount": changed_target_count,
                "skippedTargetCount": skipped_target_count,
                **normalized_values,
            }
        )
        index += 1
    candidate = rebase_canonical_model(model, candidate)
    if "master_lifecycle" in capabilities:
        from .mutation import master_lifecycle_diff

        final_change_set = master_lifecycle_diff(model, candidate)
    else:
        final_change_set = diff_models(model, candidate)
    return GenericMutationBuild(
        change_set=final_change_set,
        normalized_operations=tuple(normalized),
        capabilities=tuple(sorted(capabilities)),
        execution_context=execution_context,
    )


__all__ = [
    "COMPUTED_PROJECTIONS",
    "CONSTRAINT_OPERATORS",
    "ENTITY_KINDS",
    "EntityReference",
    "GenericMutationBuild",
    "OPERATION_KINDS",
    "build_change_set",
    "bind_relation_selector",
    "constraint_observation_request",
    "evaluate_constraints",
    "project_reference",
    "reduce_references",
    "resolve_selector",
]
