"""Generic canonical reads, constraints, and detached change construction.

This module deliberately contains no GlyphsApp, transport, or typographic
policy.  It turns closed selectors and mechanical operations into exact
canonical paths.  Skills and agents decide *what* a design should become;
the application and transaction kernel prove *what* will be written.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, MutableMapping, Optional, Sequence

from .canonical_collections import ORDER_TOKEN, entity_id, find_entity_index
from .canonical_views import layer_anchors, layer_components, layer_paths, layer_shapes
from .semantic import ChangeSet, diff_models, semantic_value_at


ENTITY_KINDS = frozenset(
    {
        "document",
        "font",
        "axis",
        "master",
        "instance",
        "glyph",
        "layer",
        "shape",
        "anchor",
        "kerning",
        "feature",
        "class",
        "prefix",
        "metric",
        "stem",
        "number",
    }
)
OPERATION_KINDS = frozenset(
    {"set", "translate", "insert", "remove", "move", "duplicate"}
)
CONSTRAINT_OPERATORS = frozenset(
    {"eq", "ne", "lt", "lte", "gt", "gte", "within", "in_range"}
)
COMPUTED_PROJECTIONS = frozenset(
    {
        "alignment",
        "bounds",
        "compilation.diagnostics",
        "geometry.counts",
        "grid",
        "inheritance.metrics",
        "metadata.effective",
        "ownership",
        "spacing.horizontal",
        "spacing.vertical",
    }
)

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
        for name, glyph in _collection_items(model.get("glyphs", {})):
            glyph_name = str(glyph.get("name") or name) if isinstance(glyph, Mapping) else name
            result.append(
                EntityReference(kind, glyph_name, ("glyphs", name), glyph, {})
            )
        return result
    root = _ROOT_COLLECTIONS.get(kind)
    if root is None:
        return []
    return [
        EntityReference(kind, identity, (root, identity), item, {})
        for identity, item in _collection_items(model.get(root, ()))
    ]


def _layer_references(model: Mapping[str, Any]) -> list[EntityReference]:
    result: list[EntityReference] = []
    for glyph_ref in _root_references(model, "glyph"):
        glyph = glyph_ref.value
        if not isinstance(glyph, Mapping):
            continue
        for layer_id, layer in _collection_items(glyph.get("layers", ())):
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
        else:
            continue
        for identity, item in _collection_items(source):
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
    elif kind in {"shape", "anchor"}:
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
    selected = [
        ref
        for ref in values
        if (not ids or ref.identity in ids)
        and all(str(ref.parent.get(str(key), "")) == str(value) for key, value in parent.items())
        and _matches_where(ref.value, where)
    ]
    order_by = str(source.get("orderBy") or "identity")
    reverse = bool(source.get("descending", False))
    if order_by == "canonical":
        if reverse:
            selected.reverse()
    elif order_by == "identity":
        selected.sort(key=lambda ref: (ref.identity, ref.path), reverse=reverse)
    elif order_by:
        selected.sort(
            key=lambda ref: (
                _nested_value(ref.value, order_by)[1] is None,
                str(_nested_value(ref.value, order_by)[1]),
                ref.identity,
            ),
            reverse=reverse,
        )
    return tuple(selected)


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
        "anchor",
    }:
        implicit["glyphName"] = parent_reference.identity
    elif parent_reference.kind == "master" and child_kind in {"layer", "kerning"}:
        implicit["masterId"] = parent_reference.identity
    elif parent_reference.kind == "layer" and child_kind in {"shape", "anchor"}:
        implicit.update(
            {
                "glyphName": str(parent_reference.parent.get("glyphName") or ""),
                "layerId": parent_reference.identity,
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
    fields_value = source.get("fields") or ["id", "name"]
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
        if field == "alignment":
            if reference.kind != "layer" or not isinstance(reference.value, Mapping):
                values[field] = None
                provenance[field] = "unavailable"
                missing.append(field)
            else:
                components = layer_components(reference.value)
                values[field] = {
                    "hasAlignedWidth": observation.get("hasAlignedWidth"),
                    "automaticComponentCount": sum(
                        bool(component.get("automaticAlignment"))
                        for component in components
                    ),
                    "componentCount": len(components),
                }
                provenance[field] = (
                    "native+derived"
                    if "hasAlignedWidth" in observation
                    else "derived"
                )
                if "hasAlignedWidth" not in observation:
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
                step = _grid_step({"font": font})
                values[field] = {
                    "grid": font.get("grid"),
                    "subdivision": font.get("gridSubDivision"),
                    "step": _public_number(step) if step is not None else None,
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
        present, value = _nested_value(reference.value, field)
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


def _selector_operand(
    model: Mapping[str, Any], operand: Mapping[str, Any]
) -> tuple[bool, Any, Optional[dict[str, Any]]]:
    kind = str(operand.get("kind") or "")
    if kind == "literal":
        return True, copy.deepcopy(operand.get("value")), None
    if kind == "reference":
        selector = operand.get("selector")
        if not isinstance(selector, Mapping):
            raise ValueError("reference operands require selector")
        references = resolve_selector(model, selector)
        if len(references) != 1:
            raise ValueError("reference operands must resolve exactly one entity")
        identity = references[0].public_identity()
        return True, identity, identity
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
    present, value = _nested_value(references[0].value, field)
    return present, value, references[0].public_identity()


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
    model: Mapping[str, Any], constraints: Sequence[Mapping[str, Any]], *, phase: str
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
            left_present, left, left_target = _selector_operand(
                model, _mapping(constraint.get("left"), name="constraint.left")
            )
            right_present, right, right_target = _selector_operand(
                model, _mapping(constraint.get("right"), name="constraint.right")
            )
            passed = bool(
                left_present
                and right_present
                and _compare(left, operator, right, constraint.get("tolerance"))
            )
            error = None
        except (TypeError, ValueError) as exc:
            left_present = right_present = False
            left = right = None
            left_target = right_target = None
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
                "leftTarget": left_target,
                "rightTarget": right_target,
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


def _grid_step(model: Mapping[str, Any]) -> Optional[Decimal]:
    font = model.get("font", {})
    if not isinstance(font, Mapping):
        return None
    grid = _finite_number(font.get("grid", 0), name="font grid")
    subdivision = _finite_number(font.get("gridSubDivision", 1), name="font grid subdivision")
    if grid <= 0:
        return None
    if subdivision <= 0:
        raise ValueError("font grid subdivision must be positive")
    return grid / subdivision


def _quantize(value: Any, model: Mapping[str, Any], quantizer: str) -> Any:
    number = _finite_number(value, name="operation value")
    if quantizer == "exact":
        return _public_number(number)
    if quantizer != "grid":
        raise ValueError("quantizer must be exact or grid")
    step = _grid_step(model)
    if step is None:
        return _public_number(number)
    return _public_number((number / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step)


def _assert_translatable(layer: Mapping[str, Any]) -> None:
    if bool(layer.get("locked")):
        raise ValueError("locked layer geometry cannot be translated")
    for shape in layer_shapes(layer):
        if bool(shape.get("locked")):
            raise ValueError("locked shape geometry cannot be translated")
        if str(shape.get("kind") or "") not in {"path", "component"}:
            raise ValueError("unsupported foreground shapes cannot be translated")
    for path in layer_paths(layer):
        for node in path.get("nodes") or ():
            if not isinstance(node, Mapping) or bool(node.get("locked")):
                raise ValueError("locked or unverifiable nodes cannot be translated")
    for component in layer_components(layer):
        if bool(component.get("locked")):
            raise ValueError("locked component geometry cannot be translated")
        if bool(component.get("automaticAlignment")):
            raise ValueError("automatic component alignment must be cleared explicitly")
    for anchor in layer_anchors(layer):
        if bool(anchor.get("locked")):
            raise ValueError("locked anchors cannot be translated")


def _translate_layer(layer: MutableMapping[str, Any], x: Any, y: Any) -> None:
    x_number = _finite_number(x, name="translation x")
    y_number = _finite_number(y, name="translation y")
    _assert_translatable(layer)
    for path in layer_paths(layer):
        for node in path.get("nodes") or ():
            if not isinstance(node, MutableMapping):
                raise ValueError("path nodes must be writable objects")
            node["x"] = _public_number(_finite_number(node.get("x"), name="node x") + x_number)
            node["y"] = _public_number(_finite_number(node.get("y"), name="node y") + y_number)
    for component in layer_components(layer):
        if not isinstance(component, MutableMapping):
            raise ValueError("components must be writable objects")
        position = list(component.get("position") or ())
        transform = list(component.get("transform") or ())
        if len(position) != 2 or len(transform) != 6:
            raise ValueError("component transform is incomplete")
        position[0] = _public_number(_finite_number(position[0], name="component x") + x_number)
        position[1] = _public_number(_finite_number(position[1], name="component y") + y_number)
        transform[4] = _public_number(_finite_number(transform[4], name="component transform x") + x_number)
        transform[5] = _public_number(_finite_number(transform[5], name="component transform y") + y_number)
        component["position"] = position
        component["transform"] = transform
    anchors = layer.get("anchors")
    for _identity_value, anchor in _collection_items(anchors):
        if isinstance(anchor, MutableMapping):
            position = list(anchor.get("position") or ())
            if len(position) != 2:
                raise ValueError("anchor position is incomplete")
            position[0] = _public_number(_finite_number(position[0], name="anchor x") + x_number)
            position[1] = _public_number(_finite_number(position[1], name="anchor y") + y_number)
            anchor["position"] = position
        elif isinstance(anchors, MutableMapping):
            position = list(anchor or ())
            if len(position) != 2:
                raise ValueError("anchor position is incomplete")
            position[0] = _public_number(_finite_number(position[0], name="anchor x") + x_number)
            position[1] = _public_number(_finite_number(position[1], name="anchor y") + y_number)
            anchors[_identity_value] = position


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


def _structural_lifecycle_build(
    candidate: Mapping[str, Any],
    operation: Mapping[str, Any],
    references: Sequence[EntityReference],
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
        return build_master_updates(candidate, [update])
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


def build_change_set(
    model: Mapping[str, Any], operations: Sequence[Mapping[str, Any]]
) -> GenericMutationBuild:
    """Apply mechanical operations to a detached copy and return exact intent."""

    if not operations:
        raise ValueError("preview_change requires at least one operation")
    candidate: MutableMapping[str, Any] = copy.deepcopy(dict(model))
    normalized: list[dict[str, Any]] = []
    capabilities: set[str] = set()
    execution_context: dict[str, Any] = {}
    for index, raw in enumerate(operations):
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
        resolved_paths: list[list[str]] = []
        normalized_values: dict[str, Any] = {}

        structural = _structural_lifecycle_build(candidate, operation, references)
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
            raw_value = operation.get("value")
            if quantizer == "grid" and not _numeric_value(raw_value):
                raise ValueError("grid quantization requires a numeric set value")
            value = (
                _quantize(raw_value, candidate, quantizer)
                if _numeric_value(raw_value)
                else copy.deepcopy(raw_value)
            )
            for reference in references:
                path = reference.path + tuple(field_name.split("."))
                _set_path(candidate, path, value)
                resolved_paths.append(list(path))
            normalized_values.update(
                {"field": field_name, "value": copy.deepcopy(value), "quantizer": quantizer}
            )
        elif kind == "translate":
            quantizer = str(operation.get("quantizer") or "exact")
            delta = _mapping(operation.get("delta") or {}, name="operation.delta")
            x = _quantize(delta.get("x", 0), candidate, quantizer)
            y = _quantize(delta.get("y", 0), candidate, quantizer)
            for reference in references:
                if reference.kind != "layer":
                    raise ValueError("translate operations target layers")
                refreshed = resolve_selector(
                    candidate,
                    {
                        "entity": "layer",
                        "ids": [reference.identity],
                        "parent": {
                            "glyphName": reference.parent.get("glyphName", "")
                        },
                    },
                )
                if len(refreshed) != 1 or not isinstance(
                    refreshed[0].value, MutableMapping
                ):
                    raise ValueError("translation target disappeared")
                _translate_layer(refreshed[0].value, x, y)
                resolved_paths.append(list(reference.path))
            normalized_values.update(
                {"delta": {"x": x, "y": y}, "quantizer": quantizer}
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
                **normalized_values,
            }
        )
    return GenericMutationBuild(
        change_set=diff_models(model, candidate),
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
    "evaluate_constraints",
    "project_reference",
    "resolve_selector",
]
