"""Single descriptive registry for the public generic mechanics surface."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


ENTITY_KINDS = frozenset(
    {
        "document", "font", "axis", "master", "instance", "glyph", "layer",
        "shape", "node", "anchor", "kerning", "feature", "class", "prefix",
        "metric", "stem", "number",
    }
)
COMPUTED_PROJECTIONS = frozenset(
    {
        "alignment", "bounds", "collection.index", "compilation.diagnostics", "geometry.counts",
        "geometry.transform", "grid", "inheritance.metrics",
        "masterLayerCoverage", "metadata.effective", "ownership", "persistence",
        "spacing.horizontal", "spacing.vertical",
    }
)
OPERATION_DEFINITIONS: Mapping[str, Mapping[str, Any]] = {
    "set": {"required": ["target", "field", "value"], "optional": ["quantizer"]},
    "translate": {"required": ["target", "delta"], "optional": ["quantizer"]},
    "transform": {
        "required": ["target", "matrix"],
        "optional": [
            "origin", "quantizer", "include", "componentComposition",
            "alignmentPolicy",
        ],
    },
    "insert": {
        "required": ["target", "value"],
        "optional": ["field", "index", "newId"],
    },
    "remove": {"required": ["target"], "optional": []},
    "move": {"required": ["target", "index"], "optional": []},
    "duplicate": {
        "required": ["target", "newId"],
        "optional": ["overrides", "index"],
    },
    "materialize": {
        "required": ["target", "destinationEntity", "newId"],
        "optional": ["overrides", "index"],
    },
}
PREDICATE_OPERATORS = frozenset(
    {
        "and", "or", "not", "eq", "ne", "lt", "lte", "gt", "gte", "in",
        "contains", "exists",
    }
)
ORDER_TYPES = frozenset({"auto", "text", "number"})
REDUCER_KINDS = frozenset(
    {"count", "min", "max", "sum", "average", "any", "all"}
)
CONSTRAINT_OPERATORS = frozenset(
    {"eq", "ne", "lt", "lte", "gt", "gte", "within", "in_range"}
)
TRANSLATION_TARGETS = frozenset({"layer", "shape", "node", "anchor"})
TRANSFORM_TARGETS = frozenset({"layer", "shape", "node", "anchor"})
RELATION_DEFINITIONS: Mapping[str, tuple[str, ...]] = {
    "glyph": ("layer", "shape", "node", "anchor"),
    "master": ("layer", "kerning"),
    "layer": ("shape", "node", "anchor"),
    "shape": ("node",),
}
SCALAR_VALUE_FIELDS: Mapping[str, str] = {"kerning": "value"}


def _entity_capability(kind: str) -> dict[str, Any]:
    operations = {"set", "remove", "duplicate", "move"}
    if kind in {"document", "font", "glyph", "layer", "shape"}:
        operations.add("insert")
    if kind in TRANSLATION_TARGETS:
        operations.add("translate")
    if kind in TRANSFORM_TARGETS:
        operations.add("transform")
    if kind == "instance":
        operations.add("materialize")
    observations_by_kind = {
        "document": {
            "compilation.diagnostics", "masterLayerCoverage", "persistence"
        },
        "font": {"compilation.diagnostics", "persistence"},
        "glyph": {"metadata.effective", "ownership"},
        "layer": {
            "alignment", "bounds", "geometry.counts", "grid",
            "inheritance.metrics", "ownership", "spacing.horizontal",
            "spacing.vertical",
        },
        "shape": {"geometry.transform", "ownership"},
    }
    observations = sorted(observations_by_kind.get(kind, {"ownership"}))
    capability = {
        "operations": sorted(operations),
        "writableFields": "canonical-existing-fields",
        "observations": observations,
        "relations": list(RELATION_DEFINITIONS.get(kind, ())),
    }
    if kind in SCALAR_VALUE_FIELDS:
        capability["scalarValueField"] = SCALAR_VALUE_FIELDS[kind]
    return capability


def public_mechanics_registry() -> dict[str, Any]:
    return {
        "entities": sorted(ENTITY_KINDS),
        "computedProjections": sorted(COMPUTED_PROJECTIONS),
        "changeOperations": {
            name: deepcopy(dict(definition))
            for name, definition in sorted(OPERATION_DEFINITIONS.items())
        },
        "selectorPredicates": sorted(PREDICATE_OPERATORS),
        "orderTypes": sorted(ORDER_TYPES),
        "reducers": sorted(REDUCER_KINDS),
        "constraintOperators": sorted(CONSTRAINT_OPERATORS),
        "translationTargets": sorted(TRANSLATION_TARGETS),
        "transformTargets": sorted(TRANSFORM_TARGETS),
        "entityCapabilities": {
            kind: _entity_capability(kind) for kind in sorted(ENTITY_KINDS)
        },
        "relations": {
            kind: list(children)
            for kind, children in sorted(RELATION_DEFINITIONS.items())
        },
        "scalarValueFields": dict(sorted(SCALAR_VALUE_FIELDS.items())),
        "geometryExecution": {
            "coordinatePolicy": "floating_point",
            "quantizers": ["exact"],
            "nativeLayerRounding": "temporarily_disabled",
            "gridDuringTransformation": 0,
            "componentDependencyResolution": "transitive_before_grid_restore",
            "gridRestoration": "exact_entry_on_success_failure_cancellation_or_abort",
            "restoresGrid": True,
            "restoresGridSubDivision": True,
            "temporarySettingsOwnership": "tool",
            "temporarySettingsInRequestedChangeSet": False,
            "explicitGridChangeOrdering": "isolated_after_component_settlement",
            "preservesGlobalAutomaticAlignment": True,
        },
    }


__all__ = [
    "COMPUTED_PROJECTIONS",
    "CONSTRAINT_OPERATORS",
    "ENTITY_KINDS",
    "OPERATION_DEFINITIONS",
    "ORDER_TYPES",
    "PREDICATE_OPERATORS",
    "REDUCER_KINDS",
    "RELATION_DEFINITIONS",
    "SCALAR_VALUE_FIELDS",
    "TRANSLATION_TARGETS",
    "TRANSFORM_TARGETS",
    "public_mechanics_registry",
]
