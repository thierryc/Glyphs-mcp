"""Registry-backed mechanics for ownership-sensitive canonical structures.

Generic operations normally map directly to canonical paths. Masters and
layers are the bounded exception: Glyphs owns master layers with their master,
and non-master layers may not enter the master-layer prefix. This module
contains only those structural invariants. It contains no workflow, review,
typographic heuristic, transport, or host API policy.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Mapping, Optional, Sequence

from .canonical_collections import (
    find_entity_index,
    indexed_entities,
    move_entity,
    require_indexed_entities,
)
from .mutation import (
    LAYER_LIFECYCLE_CAPABILITY,
    MASTER_LIFECYCLE_CAPABILITY,
    MutationBuild,
    master_lifecycle_request_diff,
)
from .semantic import diff_models


def _items(value: Any, *, key_name: str = "id") -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        result: list[dict[str, Any]] = []
        for key, item in value.items():
            plain = copy.deepcopy(dict(item)) if isinstance(item, Mapping) else {"value": item}
            plain.setdefault(key_name, str(key))
            result.append(plain)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [copy.deepcopy(dict(item)) for item in value if isinstance(item, Mapping)]
    return []


def _canonical_layers(
    glyph: Any, *, deep: bool = True
) -> list[dict[str, Any]]:
    source = glyph.get("layers", ()) if isinstance(glyph, Mapping) else ()
    if isinstance(source, Mapping):
        source = list(source.values())
    if not isinstance(source, (list, tuple)):
        raise ValueError("glyph layers must be an ordered canonical collection")
    layers = [
        copy.deepcopy(dict(layer)) if deep else dict(layer)
        for layer in source
        if isinstance(layer, Mapping)
    ]
    if len(layers) != len(source) or indexed_entities(layers) is None:
        raise ValueError("glyph layers require unique non-empty layer IDs")
    return layers


def _layer_index(layers: Sequence[Mapping[str, Any]], identity: str) -> int | None:
    index = find_entity_index(layers, identity)
    if index is not None:
        return index
    matches = [
        offset
        for offset, layer in enumerate(layers)
        if bool(layer.get("isMasterLayer"))
        and str(layer.get("masterId") or "") == identity
    ]
    return matches[0] if len(matches) == 1 else None


def _master_layer_prefix_length(layers: Sequence[Mapping[str, Any]]) -> int:
    prefix = 0
    reached_non_master = False
    for layer in layers:
        is_master = bool(layer.get("isMasterLayer"))
        if is_master and reached_non_master:
            raise ValueError("canonical master layers must form the master-layer prefix")
        if is_master:
            prefix += 1
        else:
            reached_non_master = True
    return prefix


def _master_axes(value: Any, *, expected_tags: Sequence[str]) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("master axes must be an explicit sequence")
    axes = [copy.deepcopy(dict(axis)) for axis in value if isinstance(axis, Mapping)]
    tags = [str(axis.get("tag") or "") for axis in axes]
    if len(axes) != len(value) or not all(tags) or len(tags) != len(set(tags)):
        raise ValueError("master axes require unique non-empty tags")
    if tuple(tags) != tuple(expected_tags):
        raise ValueError("master axes must preserve the font axis tag order")
    for axis in axes:
        if axis.get("internal") is None:
            raise ValueError("master axis coordinates require internal values")
        axis["internal"] = float(axis["internal"])
    return axes


def _duplicate_kerning_partition(
    kerning: dict[str, Any], source_id: str, new_id: str
) -> None:
    directional = any(
        domain in kerning for domain in ("ltr", "rtl", "vertical", "context")
    )
    if not directional:
        if source_id in kerning:
            kerning[new_id] = copy.deepcopy(kerning[source_id])
        return
    for domain in ("ltr", "rtl", "vertical"):
        partitions = kerning.get(domain)
        if isinstance(partitions, dict) and source_id in partitions:
            partitions[new_id] = copy.deepcopy(partitions[source_id])
    contexts = kerning.get("context")
    if isinstance(contexts, dict):
        for master_values in contexts.values():
            if isinstance(master_values, dict) and source_id in master_values:
                master_values[new_id] = copy.deepcopy(master_values[source_id])


def _sync_italic_angle_metric(
    model: Mapping[str, Any], master: dict[str, Any], angle: float
) -> None:
    """Keep Glyphs' registered italic-angle metric and convenience scalar aligned."""

    metrics = _items(model.get("metrics", []))
    italic_ids = {
        str(metric.get("id") or "")
        for metric in metrics
        if metric.get("type") in {9, "9", "italic angle"}
    }
    italic_ids.discard("")
    if not italic_ids:
        return
    values = master.get("metricValues", [])
    if not isinstance(values, list):
        return
    for value in values:
        if isinstance(value, dict) and str(value.get("id") or "") in italic_ids:
            value["pos"] = float(angle)


def _remove_kerning_partition(kerning: dict[str, Any], master_id: str) -> None:
    directional = any(
        domain in kerning for domain in ("ltr", "rtl", "vertical", "context")
    )
    if not directional:
        kerning.pop(master_id, None)
        return
    for domain in ("ltr", "rtl", "vertical"):
        partitions = kerning.get(domain)
        if isinstance(partitions, dict):
            partitions.pop(master_id, None)
    contexts = kerning.get("context")
    if isinstance(contexts, dict):
        for context_key in list(contexts):
            master_values = contexts.get(context_key)
            if isinstance(master_values, dict):
                master_values.pop(master_id, None)
                if not master_values:
                    contexts.pop(context_key, None)


def _copy_materialized_kerning_partition(
    kerning: dict[str, Any], source: Mapping[str, Any], master_id: str
) -> None:
    """Copy only one captured native master partition into canonical kerning."""

    directional = any(
        domain in source for domain in ("ltr", "rtl", "vertical", "context")
    )
    if not directional:
        if master_id in source:
            kerning[master_id] = copy.deepcopy(source[master_id])
        return
    for domain in ("ltr", "rtl", "vertical"):
        values = source.get(domain)
        if not isinstance(values, Mapping) or master_id not in values:
            continue
        destination = kerning.setdefault(domain, {})
        if not isinstance(destination, dict):
            raise ValueError("canonical kerning domain must be a mapping")
        destination[master_id] = copy.deepcopy(values[master_id])
    contexts = source.get("context")
    if not isinstance(contexts, Mapping):
        return
    destination_contexts = kerning.setdefault("context", {})
    if not isinstance(destination_contexts, dict):
        raise ValueError("canonical contextual kerning must be a mapping")
    for context_key, values in contexts.items():
        if not isinstance(values, Mapping) or master_id not in values:
            continue
        destination = destination_contexts.setdefault(str(context_key), {})
        if not isinstance(destination, dict):
            raise ValueError("canonical contextual kerning partition must be a mapping")
        destination[master_id] = copy.deepcopy(values[master_id])


def build_materializations(
    model: Mapping[str, Any],
    materializations: Sequence[Mapping[str, Any]],
    *,
    cancellation_checkpoint: Optional[Callable[[], None]] = None,
) -> MutationBuild:
    """Attach exact detached-native entities captured for generic materialization.

    This registry never interpolates. The adapter prepares authoritative master
    and layer payloads on a detached Glyphs clone; this pure builder validates
    their ownership and turns them into the ordinary master-lifecycle patch.
    """

    if not materializations:
        raise ValueError("materialize requires at least one prepared target")
    source_masters = model.get("masters", [])
    if not isinstance(source_masters, (list, tuple)):
        raise ValueError("masters must be an ordered canonical collection")
    masters = [copy.deepcopy(dict(master)) for master in source_masters]
    current_order, current_by_id = require_indexed_entities(masters, "masters")
    source_glyphs = model.get("glyphs", {})
    if not isinstance(source_glyphs, Mapping):
        raise ValueError("glyphs must be keyed by name")
    glyphs = dict(source_glyphs)
    source_kerning = model.get("kerning", {})
    if not isinstance(source_kerning, Mapping):
        raise ValueError("kerning must be a canonical mapping")
    kerning = copy.deepcopy(dict(source_kerning))
    added: dict[str, dict[str, Any]] = {}
    layers_by_master: dict[str, Mapping[str, Any]] = {}
    final_order: list[str] | None = None

    for item in materializations:
        if cancellation_checkpoint is not None:
            cancellation_checkpoint()
        master = item.get("master")
        layers = item.get("layers")
        order = item.get("masterOrder")
        if not isinstance(master, Mapping) or not isinstance(layers, Mapping):
            raise ValueError("materialize requires an authoritative master and layers")
        master_id = str(master.get("id") or "")
        if not master_id or master_id in current_by_id or master_id in added:
            raise ValueError("materialize requires one unique new master identity")
        if not isinstance(order, Sequence) or isinstance(order, (str, bytes)):
            raise ValueError("materialize requires the authoritative master order")
        normalized_order = [str(identity) for identity in order]
        if final_order is None:
            final_order = normalized_order
        elif final_order != normalized_order:
            raise ValueError("materialized targets disagree on master order")
        added[master_id] = copy.deepcopy(dict(master))
        layers_by_master[master_id] = layers
        captured_kerning = item.get("kerning")
        if isinstance(captured_kerning, Mapping):
            _copy_materialized_kerning_partition(
                kerning, captured_kerning, master_id
            )

    target_ids = set(current_order) | set(added)
    if (
        final_order is None
        or set(final_order) != target_ids
        or len(final_order) != len(target_ids)
    ):
        raise ValueError("authoritative materialized master order is incomplete")
    masters_by_id = {**current_by_id, **added}
    masters = [copy.deepcopy(dict(masters_by_id[identity])) for identity in final_order]

    for glyph_name, glyph in source_glyphs.items():
        if cancellation_checkpoint is not None:
            cancellation_checkpoint()
        if not isinstance(glyph, Mapping):
            raise ValueError("glyph {} is not canonical".format(glyph_name))
        layers = _canonical_layers(glyph, deep=False)
        prefix_length = _master_layer_prefix_length(layers)
        existing_prefix = {
            str(layer.get("masterId") or layer.get("id") or ""): layer
            for layer in layers[:prefix_length]
        }
        for master_id, captured in layers_by_master.items():
            layer = captured.get(str(glyph_name))
            if not isinstance(layer, Mapping):
                raise ValueError(
                    "materialized master {} has no layer for glyph {}".format(
                        master_id, glyph_name
                    )
                )
            normalized = copy.deepcopy(dict(layer))
            if (
                str(normalized.get("id") or "") != master_id
                or str(normalized.get("masterId") or "") != master_id
                or not bool(normalized.get("isMasterLayer"))
            ):
                raise ValueError("materialized layers must be owned by their new master")
            existing_prefix[master_id] = normalized
        if set(existing_prefix) != target_ids:
            raise ValueError(
                "glyph {} does not contain one layer per target master".format(
                    glyph_name
                )
            )
        glyph_copy = dict(glyph)
        glyph_copy["layers"] = [
            existing_prefix[identity] for identity in final_order
        ] + layers[prefix_length:]
        glyphs[str(glyph_name)] = glyph_copy

    after = dict(model)
    after["masters"] = masters
    after["glyphs"] = glyphs
    after["kerning"] = kerning
    changes = master_lifecycle_request_diff(model, after)
    if not changes.changes:
        raise ValueError("materialize must produce a document change")
    return MutationBuild(
        change_set=changes,
        capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
        execution_context={"materializedMasterIds": tuple(added)},
    )


def build_master_updates(
    model: Mapping[str, Any],
    updates: Sequence[Mapping[str, Any]],
    *,
    cancellation_checkpoint: Optional[Callable[[], None]] = None,
) -> MutationBuild:
    """Build master operations plus their mechanically owned structures."""

    after = dict(model)
    source_masters = model.get("masters", [])
    if not isinstance(source_masters, (list, tuple)):
        raise ValueError("masters must be an ordered canonical collection")
    masters = [copy.deepcopy(dict(master)) for master in source_masters]
    after["masters"] = masters
    require_indexed_entities(masters, "masters")
    source_glyphs = model.get("glyphs", {})
    if not isinstance(source_glyphs, Mapping):
        raise ValueError("glyphs must be keyed by name")
    glyphs = dict(source_glyphs)
    after["glyphs"] = glyphs
    source_kerning = model.get("kerning", {})
    if not isinstance(source_kerning, Mapping):
        raise ValueError("kerning must be a canonical mapping")
    kerning = copy.deepcopy(dict(source_kerning))
    after["kerning"] = kerning
    source_map: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()

    for update in updates:
        if cancellation_checkpoint is not None:
            cancellation_checkpoint()
        action = str(update.get("action") or "update").lower()
        master_id = str(update.get("masterId") or "")
        target = (action, master_id)
        if not master_id or master_id == "$order" or target in seen:
            raise ValueError("master updates require unique explicit action/masterId targets")
        seen.add(target)
        index = find_entity_index(masters, master_id)

        if action == "duplicate":
            source_id = str(update.get("sourceMasterId") or "")
            source_index = find_entity_index(masters, source_id)
            if not source_id or source_index is None:
                raise ValueError("master duplication requires a known sourceMasterId")
            if source_id in source_map:
                raise ValueError("master duplication sources must predate the current batch")
            if index is not None:
                raise ValueError("master already exists: {}".format(master_id))
            duplicate = copy.deepcopy(masters[source_index])
            duplicate["id"] = master_id
            duplicate["name"] = str(update.get("name") or duplicate.get("name") or "")
            if not duplicate["name"]:
                raise ValueError("duplicated master name cannot be empty")
            if "italicAngle" in update:
                duplicate["italicAngle"] = float(update["italicAngle"])
                _sync_italic_angle_metric(
                    model, duplicate, float(update["italicAngle"])
                )
            if "axes" in update:
                expected_tags = [
                    str(axis.get("tag") or "") for axis in duplicate.get("axes", [])
                ]
                duplicate["axes"] = _master_axes(
                    update["axes"], expected_tags=expected_tags
                )
            masters.append(duplicate)
            if "index" in update:
                move_entity(masters, master_id, int(update["index"]))
            source_map[master_id] = source_id

            for glyph_name, glyph in list(glyphs.items()):
                if cancellation_checkpoint is not None:
                    cancellation_checkpoint()
                if not isinstance(glyph, Mapping):
                    raise ValueError("glyph {} is not canonical".format(glyph_name))
                layers = _canonical_layers(glyph, deep=False)
                source_layer_index = _layer_index(layers, source_id)
                source_layer = (
                    layers[source_layer_index] if source_layer_index is not None else None
                )
                if not isinstance(source_layer, Mapping) or not bool(
                    source_layer.get("isMasterLayer", True)
                ):
                    raise ValueError(
                        "glyph {} has no canonical source master layer {}".format(
                            glyph_name, source_id
                        )
                    )
                if _layer_index(layers, master_id) is not None:
                    raise ValueError(
                        "glyph {} already has layer {}".format(glyph_name, master_id)
                    )
                layer = dict(source_layer)
                layer.update(
                    {
                        "id": master_id,
                        "masterId": master_id,
                        "name": duplicate["name"],
                        "isMasterLayer": True,
                        "isSpecialLayer": False,
                    }
                )
                prefix_length = _master_layer_prefix_length(layers)
                master_position = find_entity_index(masters, master_id)
                layers.insert(min(master_position or 0, prefix_length), layer)
                glyph_copy = dict(glyph)
                glyph_copy["layers"] = layers
                glyphs[str(glyph_name)] = glyph_copy
            _duplicate_kerning_partition(kerning, source_id, master_id)
            continue

        if index is None:
            raise ValueError("unknown master: {}".format(master_id))
        if action == "delete":
            if len(masters) <= 1:
                raise ValueError("the final master cannot be deleted")
            for glyph_name, glyph in list(glyphs.items()):
                layers = _canonical_layers(glyph, deep=False)
                master_layer_index = _layer_index(layers, master_id)
                if master_layer_index is None:
                    raise ValueError(
                        "glyph {} has no canonical master layer {}".format(
                            glyph_name, master_id
                        )
                    )
                if any(
                    str(layer.get("id") or "") != master_id
                    and str(layer.get("masterId") or "") == master_id
                    and bool(layer.get("isSpecialLayer"))
                    for layer in layers
                ):
                    raise ValueError(
                        "master {} has a dependent special layer in glyph {}".format(
                            master_id, glyph_name
                        )
                    )
                del layers[master_layer_index]
                glyph_copy = dict(glyph)
                glyph_copy["layers"] = layers
                glyphs[str(glyph_name)] = glyph_copy
            del masters[index]
            _remove_kerning_partition(kerning, master_id)
            continue
        if action == "move":
            if "index" not in update:
                raise ValueError("master move requires index")
            move_entity(masters, master_id, int(update["index"]))
            continue
        if action != "update":
            raise ValueError("master action must be duplicate, update, move, or delete")

        supplied = {"name", "italicAngle", "axes"}.intersection(update)
        if not supplied:
            raise ValueError("master updates require name, italicAngle, or axes")
        item = masters[index]
        if "name" in supplied:
            name = str(update.get("name") or "")
            if not name:
                raise ValueError("master name cannot be empty")
            item["name"] = name
        if "italicAngle" in supplied:
            item["italicAngle"] = float(update["italicAngle"])
            _sync_italic_angle_metric(model, item, float(update["italicAngle"]))
        if "axes" in supplied:
            expected_tags = [str(axis.get("tag") or "") for axis in item.get("axes", [])]
            item["axes"] = _master_axes(update["axes"], expected_tags=expected_tags)

    changes = master_lifecycle_request_diff(model, after)
    if not changes.changes:
        raise ValueError("master updates must produce a document change")
    return MutationBuild(
        change_set=changes,
        capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
        execution_context={"masterSources": source_map},
    )


def _font_axis_tags(model: Mapping[str, Any]) -> tuple[str, ...]:
    tags: list[str] = []
    for master in _items(model.get("masters", [])):
        for axis in _items(master.get("axes", []), key_name="tag"):
            tag = str(axis.get("tag") or "")
            if tag and tag not in tags:
                tags.append(tag)
    return tuple(tags)


def _normalized_interpolation(
    value: Any, *, known_axis_tags: Sequence[str]
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("layer interpolation must be an object or null")
    kind = str(value.get("kind") or "").lower()
    known = set(known_axis_tags)
    if kind == "intermediate":
        coordinates = value.get("coordinates")
        if not isinstance(coordinates, Mapping) or not coordinates:
            raise ValueError("intermediate layers require axis coordinates")
        unknown = {str(tag) for tag in coordinates} - known
        if unknown:
            raise ValueError("unknown axis tag: {}".format(", ".join(sorted(unknown))))
        return {
            "kind": "intermediate",
            "coordinates": {
                str(tag): float(coordinates[tag]) for tag in sorted(coordinates, key=str)
            },
        }
    if kind == "alternate":
        ranges = value.get("ranges")
        if not isinstance(ranges, Mapping) or not ranges:
            raise ValueError("alternate layers require axis ranges")
        unknown = {str(tag) for tag in ranges} - known
        if unknown:
            raise ValueError("unknown axis tag: {}".format(", ".join(sorted(unknown))))
        normalized: dict[str, dict[str, float | None]] = {}
        for tag in sorted(ranges, key=str):
            rule = ranges[tag]
            if not isinstance(rule, Mapping):
                raise ValueError("alternate axis ranges require min/max objects")
            minimum = rule.get("min")
            maximum = rule.get("max")
            if minimum is None and maximum is None:
                raise ValueError("alternate axis ranges require a minimum or maximum")
            minimum = float(minimum) if minimum is not None else None
            maximum = float(maximum) if maximum is not None else None
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError("alternate range minimum cannot exceed maximum")
            normalized[str(tag)] = {"min": minimum, "max": maximum}
        return {"kind": "alternate", "ranges": normalized}
    raise ValueError("layer interpolation kind must be intermediate or alternate")


def _project_layer_roles(
    layer: Mapping[str, Any], interpolation: Mapping[str, Any] | None
) -> list[str]:
    retained = [
        str(role) for role in layer.get("roles", ()) if str(role) in {"smart", "color"}
    ]
    kind = str(interpolation.get("kind") or "") if interpolation else ""
    if kind:
        retained.insert(0, kind)
    if not retained:
        retained.append("backup")
    return list(dict.fromkeys(retained))


def build_layer_updates(
    model: Mapping[str, Any], updates: Sequence[Mapping[str, Any]]
) -> MutationBuild:
    """Build non-master layer operations while preserving the owned prefix."""

    after = copy.deepcopy(dict(model))
    glyphs = after.get("glyphs", {})
    if not isinstance(glyphs, dict):
        raise ValueError("glyphs must be keyed by name")
    known_masters = {
        str(master.get("id") or "")
        for master in _items(model.get("masters", []))
        if master.get("id")
    }
    known_axis_tags = _font_axis_tags(model)
    source_map: dict[str, str] = {}
    seen: set[tuple[str, str, str]] = set()

    for update in updates:
        action = str(update.get("action") or "update").lower()
        glyph_name = str(update.get("glyphName") or "")
        layer_id = str(update.get("layerId") or "")
        target = (action, glyph_name, layer_id)
        if not glyph_name or not layer_id or layer_id == "$order" or target in seen:
            raise ValueError(
                "layer updates require unique explicit action/glyphName/layerId targets"
            )
        seen.add(target)
        glyph = glyphs.get(glyph_name)
        if not isinstance(glyph, Mapping):
            raise ValueError("unknown glyph: {}".format(glyph_name))
        glyph_copy = copy.deepcopy(dict(glyph))
        layers = _canonical_layers(glyph)
        glyph_copy["layers"] = layers
        glyphs[glyph_name] = glyph_copy
        master_prefix_length = _master_layer_prefix_length(layers)
        index = _layer_index(layers, layer_id)

        if action == "duplicate":
            if index is not None:
                raise ValueError("layer already exists: {}/{}".format(glyph_name, layer_id))
            source_id = str(update.get("sourceLayerId") or "")
            source_index = _layer_index(layers, source_id)
            if not source_id or source_index is None:
                raise ValueError("unknown source layer: {}/{}".format(glyph_name, source_id))
            duplicate = copy.deepcopy(layers[source_index])
            duplicate["id"] = layer_id
            duplicate["isMasterLayer"] = False
            if "masterId" in update:
                duplicate["masterId"] = str(update.get("masterId") or "")
            if str(duplicate.get("masterId") or "") not in known_masters:
                raise ValueError("unknown associated master: {}".format(duplicate.get("masterId")))
            if "name" in update:
                duplicate["name"] = str(update.get("name") or "")
            interpolation = _normalized_interpolation(
                update.get("interpolation", duplicate.get("interpolation")),
                known_axis_tags=known_axis_tags,
            )
            duplicate["interpolation"] = interpolation
            duplicate["roles"] = _project_layer_roles(duplicate, interpolation)
            duplicate["isSpecialLayer"] = bool(
                set(duplicate["roles"]) & {"intermediate", "alternate", "smart"}
            )
            layers.append(duplicate)
            if "index" in update:
                requested_index = int(update["index"])
                if requested_index < master_prefix_length:
                    raise ValueError("non-master layers cannot cross the master-layer prefix")
                move_entity(layers, layer_id, requested_index)
            source_map["{}/{}".format(glyph_name, layer_id)] = source_id
            continue

        if index is None:
            raise ValueError("unknown layer: {}/{}".format(glyph_name, layer_id))
        layer = layers[index]
        if bool(layer.get("isMasterLayer")):
            raise ValueError("master layer mutations belong to master lifecycle")
        if action == "delete":
            del layers[index]
            continue
        if action == "move":
            if "index" not in update:
                raise ValueError("layer move requires index")
            requested_index = int(update["index"])
            if requested_index < master_prefix_length:
                raise ValueError("non-master layers cannot cross the master-layer prefix")
            move_entity(layers, layer_id, requested_index)
            continue
        if action != "update":
            raise ValueError("layer action must be duplicate, update, move, or delete")

        supplied = {"name", "masterId", "interpolation"}.intersection(update)
        if not supplied:
            raise ValueError("layer updates require name, masterId, or interpolation")
        if "name" in supplied:
            layer["name"] = str(update.get("name") or "")
        if "masterId" in supplied:
            master_id = str(update.get("masterId") or "")
            if master_id not in known_masters:
                raise ValueError("unknown associated master: {}".format(master_id))
            layer["masterId"] = master_id
        if "interpolation" in supplied:
            interpolation = _normalized_interpolation(
                update.get("interpolation"), known_axis_tags=known_axis_tags
            )
            layer["interpolation"] = interpolation
            layer["roles"] = _project_layer_roles(layer, interpolation)
            layer["isSpecialLayer"] = bool(
                set(layer["roles"]) & {"intermediate", "alternate", "smart"}
            )

    changes = diff_models(model, after)
    if not changes.changes:
        raise ValueError("layer updates must produce a document change")
    return MutationBuild(
        change_set=changes,
        capabilities=(LAYER_LIFECYCLE_CAPABILITY,),
        execution_context={"layerSources": source_map},
    )


__all__ = [
    "build_layer_updates",
    "build_master_updates",
    "build_materializations",
]
