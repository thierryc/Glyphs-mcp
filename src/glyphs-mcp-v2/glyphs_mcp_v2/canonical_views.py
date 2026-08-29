"""Read-only projections over canonical layer collections.

Schema v7 stores anchors and shapes as ordered identity-aware collections.
Keeping these projections here prevents workflows, the Reporter, and native
replay from growing their own schema-specific interpretations.  The v5
fallbacks are intentionally read-only and exist only for process-local test
fixtures and stale-history diagnostics; v7 capture never emits them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


_GLYPH_DERIVED_IDENTITY_FIELDS = frozenset({"mastersCompatible", "lastChange"})
_LAYER_DERIVED_IDENTITY_FIELDS = frozenset({"pathSignature"})


def is_semantic_identity_path(path: Sequence[str]) -> bool:
    """Return whether a canonical path contributes to document identity."""

    parts = tuple(str(part) for part in path)
    if (
        len(parts) == 3
        and parts[0] == "glyphs"
        and parts[2] in _GLYPH_DERIVED_IDENTITY_FIELDS
    ):
        return False
    if (
        len(parts) == 5
        and parts[0] == "glyphs"
        and parts[2] == "layers"
        and parts[4] in _LAYER_DERIVED_IDENTITY_FIELDS
    ):
        return False
    return True


def semantic_identity_glyph(glyph: Mapping[str, Any]) -> Mapping[str, Any]:
    """Project one glyph shard to saved-document semantic identity.

    Editor verdicts remain available to analysis, observed diffs, and the
    Change Log, but they cannot make a saved document appear modified. The
    projection is detached and shallow except for the ordered layer records.
    """

    projected = {
        str(name): value
        for name, value in glyph.items()
        if str(name) not in _GLYPH_DERIVED_IDENTITY_FIELDS
    }
    layers = glyph.get("layers")
    if isinstance(layers, (list, tuple)):
        projected["layers"] = [
            {
                str(name): value
                for name, value in layer.items()
                if str(name) not in _LAYER_DERIVED_IDENTITY_FIELDS
            }
            if isinstance(layer, Mapping)
            else layer
            for layer in layers
        ]
    return projected


def semantic_identity_document(model: Any) -> Any:
    """Return the semantic-identity view of a complete canonical document."""

    if not isinstance(model, Mapping):
        return model
    glyphs = model.get("glyphs")
    if not isinstance(glyphs, Mapping):
        return model
    projected = dict(model)
    projected["glyphs"] = {
        str(name): semantic_identity_glyph(glyph)
        if isinstance(glyph, Mapping)
        else glyph
        for name, glyph in glyphs.items()
    }
    return projected


def derived_diagnostics_equal(left: Any, right: Any) -> bool:
    """Compare state intentionally excluded from document identity.

    The canonical fingerprint already proves every saved-document field. This
    bounded projection completes exact transaction verification without
    recursively comparing hundreds of unchanged outline trees.
    """

    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return left == right
    left_glyphs = left.get("glyphs")
    right_glyphs = right.get("glyphs")
    if not isinstance(left_glyphs, Mapping) or not isinstance(
        right_glyphs, Mapping
    ):
        return left == right
    if set(left_glyphs) != set(right_glyphs):
        return False
    for name, left_glyph in left_glyphs.items():
        right_glyph = right_glyphs.get(name)
        if not isinstance(left_glyph, Mapping) or not isinstance(
            right_glyph, Mapping
        ):
            if left_glyph != right_glyph:
                return False
            continue
        if any(
            left_glyph.get(field) != right_glyph.get(field)
            for field in _GLYPH_DERIVED_IDENTITY_FIELDS
        ):
            return False
        left_layers = left_glyph.get("layers")
        right_layers = right_glyph.get("layers")
        if not isinstance(left_layers, (list, tuple)) or not isinstance(
            right_layers, (list, tuple)
        ):
            if left_layers != right_layers:
                return False
            continue
        if len(left_layers) != len(right_layers):
            return False
        for left_layer, right_layer in zip(left_layers, right_layers):
            if not isinstance(left_layer, Mapping) or not isinstance(
                right_layer, Mapping
            ):
                if left_layer != right_layer:
                    return False
                continue
            if str(left_layer.get("id") or "") != str(
                right_layer.get("id") or ""
            ):
                return False
            if any(
                left_layer.get(field) != right_layer.get(field)
                for field in _LAYER_DERIVED_IDENTITY_FIELDS
            ):
                return False
    return True


def layer_shapes(layer: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    values = layer.get("shapes")
    if isinstance(values, (list, tuple)):
        return tuple(value for value in values if isinstance(value, Mapping))
    result: list[Mapping[str, Any]] = []
    for kind, key in (("path", "paths"), ("component", "components")):
        legacy = layer.get(key)
        if not isinstance(legacy, (list, tuple)):
            continue
        for index, value in enumerate(legacy):
            if isinstance(value, Mapping):
                result.append(
                    {"id": "{}:{}".format(kind, index), "kind": kind, "value": value}
                )
    return tuple(result)


def shapes_of_kind(
    layer: Mapping[str, Any], kind: str
) -> tuple[Mapping[str, Any], ...]:
    result = []
    for shape in layer_shapes(layer):
        if str(shape.get("kind") or "") != kind:
            continue
        value = shape.get("value")
        if isinstance(value, Mapping):
            result.append(value)
    return tuple(result)


def layer_paths(layer: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    return shapes_of_kind(layer, "path")


def layer_components(layer: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    return shapes_of_kind(layer, "component")


def layer_anchors(layer: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    values = layer.get("anchors")
    if isinstance(values, (list, tuple)):
        return tuple(value for value in values if isinstance(value, Mapping))
    if isinstance(values, Mapping):
        return tuple(
            {
                "id": "anchor:{}:0".format(name),
                "name": str(name),
                "position": list(position)
                if isinstance(position, Sequence)
                and not isinstance(position, (str, bytes, bytearray))
                else position,
            }
            for name, position in values.items()
        )
    return ()


def anchors_by_name(
    layer: Mapping[str, Any],
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    for anchor in layer_anchors(layer):
        result.setdefault(str(anchor.get("name") or ""), []).append(anchor)
    return {name: tuple(values) for name, values in result.items()}


def path_signature(layer: Mapping[str, Any]) -> tuple[int, ...]:
    return tuple(len(path.get("nodes") or ()) for path in layer_paths(layer))


def replace_shape_kind(
    layer: Mapping[str, Any], kind: str, values: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    """Return shapes with one kind replaced while preserving cross-kind order.

    Existing slots are reused first. Additional values are appended after the
    last slot of that kind; removing values removes only their old slots.
    """

    replacements = iter(values)
    result: list[Mapping[str, Any]] = []
    occurrence = 0
    last_kind_index: int | None = None
    for shape in layer_shapes(layer):
        if shape.get("kind") != kind:
            result.append(shape)
            continue
        try:
            value = next(replacements)
        except StopIteration:
            continue
        result.append(
            {"id": "shape:{}:{}".format(kind, occurrence), "kind": kind, "value": value}
        )
        occurrence += 1
        last_kind_index = len(result)
    additions = [
        {"id": "shape:{}:{}".format(kind, occurrence + index), "kind": kind, "value": value}
        for index, value in enumerate(replacements)
    ]
    insertion = last_kind_index if last_kind_index is not None else len(result)
    result[insertion:insertion] = additions
    return result
