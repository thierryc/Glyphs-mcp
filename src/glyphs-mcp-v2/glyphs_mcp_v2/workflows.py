"""Detached, deterministic production reviews for Glyphs MCP 2.0."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping, Optional, Sequence

from .canonical_collections import (
    canonical_glyph_id,
    find_entity_index,
    indexed_entities,
    move_entity,
    require_indexed_entities,
)
from .canonical_views import (
    layer_anchors,
    layer_components,
    layer_paths,
    path_signature,
    replace_shape_kind,
)
from .canonical_schema import deterministic_occurrence_id
from .mutation import (
    LAYER_LIFECYCLE_CAPABILITY,
    MASTER_LIFECYCLE_CAPABILITY,
    MutationBuild,
    master_lifecycle_request_diff,
)
from .semantic import ChangeSet, diff_models


def _copy_on_write_model(
    model: Mapping[str, Any],
    *,
    roots: Iterable[str] = (),
    glyph_names: Iterable[str] = (),
    deep_glyphs: bool = True,
) -> dict[str, Any]:
    """Detach only mutation-owned canonical shards.

    The returned top-level mapping shares every undeclared root and glyph with
    ``model``. Requested roots are detached completely because their builders
    own the corresponding bounded collection. Requested glyphs are detached
    independently, preserving all unrelated glyph objects. This is the common
    builder-side counterpart to ``CanonicalSnapshot.store_verified_transition``.
    """

    after = dict(model)
    for root in dict.fromkeys(str(value) for value in roots):
        if root == "glyphs":
            raise ValueError("glyphs must be detached through glyph_names")
        if root in model:
            after[root] = copy.deepcopy(model[root])
    names = tuple(dict.fromkeys(str(value) for value in glyph_names))
    if names:
        source_glyphs = model.get("glyphs", {})
        if not isinstance(source_glyphs, Mapping):
            raise ValueError("glyph model must be keyed by name")
        glyphs = dict(source_glyphs)
        for name in names:
            if name not in source_glyphs:
                continue
            source = source_glyphs[name]
            glyphs[name] = (
                copy.deepcopy(dict(source))
                if deep_glyphs and isinstance(source, Mapping)
                else dict(source)
                if isinstance(source, Mapping)
                else copy.deepcopy(source)
            )
        after["glyphs"] = glyphs
    return after


def _items(value: Any, *, key_name: str = "id") -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        result = []
        for key, item in value.items():
            plain = copy.deepcopy(dict(item)) if isinstance(item, Mapping) else {"value": item}
            plain.setdefault(key_name, str(key))
            result.append(plain)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [copy.deepcopy(dict(item)) for item in value if isinstance(item, Mapping)]
    return []


def _canonical_layers(
    glyph: Any, *, copy_values: bool = True
) -> list[dict[str, Any]]:
    """Return the schema-v6 ordered layer entities for one glyph.

    A mapping is accepted only as a local schema-v4 migration fixture. Native
    capture and every schema-v6 builder return the ordered list form.
    """

    source = glyph.get("layers", ()) if isinstance(glyph, Mapping) else ()
    if isinstance(source, Mapping):
        source = list(source.values())
    if not isinstance(source, (list, tuple)):
        raise ValueError("glyph layers must be an ordered canonical collection")
    layers = [
        copy.deepcopy(dict(layer)) if copy_values else layer
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
    # Existing metrics/spacing APIs address master layers by master ID. Keep
    # that semantic lookup while schema v6 addresses lifecycle by layer ID.
    matches = [
        offset
        for offset, layer in enumerate(layers)
        if bool(layer.get("isMasterLayer"))
        and str(layer.get("masterId") or "") == identity
    ]
    return matches[0] if len(matches) == 1 else None


def _master_layer_prefix_length(layers: Sequence[Mapping[str, Any]]) -> int:
    """Return the immutable Glyphs master-layer prefix length."""

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


def _layer_for(glyph: Any, identity: str) -> dict[str, Any] | None:
    layers = _canonical_layers(glyph)
    index = _layer_index(layers, identity)
    return layers[index] if index is not None else None


def _finding_id(code: str, target: Mapping[str, Any]) -> str:
    payload = json.dumps([code, target], sort_keys=True, separators=(",", ":"))
    return "finding_{}".format(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16])


def _finding(code: str, severity: str, message: str, target: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _finding_id(code, target),
        "code": code,
        "severity": severity,
        "message": message,
        "target": dict(target),
    }


_GLYPH_LIST_FIELDS = frozenset(
    {
        "name",
        "id",
        "category",
        "subCategory",
        "unicode",
        "export",
        "leftKerningGroup",
        "rightKerningGroup",
        "mastersCompatible",
    }
)


def list_glyphs(
    model: Mapping[str, Any],
    *,
    fields: Optional[Sequence[str]] = None,
    include_links: bool = False,
) -> list[dict[str, Any]]:
    glyphs = _items(model.get("glyphs", {}), key_name="name")
    glyphs.sort(key=lambda glyph: str(glyph.get("name", "")))
    selected = set(fields or _GLYPH_LIST_FIELDS) | {"name"}
    unsupported = selected - _GLYPH_LIST_FIELDS
    if unsupported:
        raise ValueError("unsupported glyph list fields: {}".format(", ".join(sorted(unsupported))))
    result = [{key: value for key, value in glyph.items() if key in selected} for glyph in glyphs]
    if include_links:
        for glyph in result:
            glyph["glyphsLink"] = "glyphs://glyph/{}".format(str(glyph.get("name") or ""))
    return result


def list_instances(model: Mapping[str, Any]) -> list[dict[str, Any]]:
    instances = _items(model.get("instances", []))
    result: list[dict[str, Any]] = []
    for instance in instances:
        kind = str(instance.get("type") or "static").lower()
        axes = []
        for axis in _items(instance.get("axes", []), key_name="tag"):
            axes.append(
                {
                    "tag": str(axis.get("tag") or ""),
                    "internal": axis.get("internal"),
                    "external": axis.get("external"),
                }
            )
        result.append(
            {
                "id": str(instance.get("id") or instance.get("name") or ""),
                "name": str(instance.get("name") or ""),
                "type": "variable" if kind == "variable" else "static",
                "axes": axes,
                "included": bool(instance.get("included", True)),
                "inclusionReason": instance.get("inclusionReason"),
                "interpolationSupported": bool(
                    instance.get("interpolationSupported", kind != "variable")
                ),
            }
        )
    return result


def list_masters(model: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return ordered, bounded canonical master metadata."""

    masters = _items(model.get("masters", []))
    return [
        {
            "id": str(master.get("id") or ""),
            "name": str(master.get("name") or ""),
            "italicAngle": master.get("italicAngle"),
            "axes": [
                {
                    "tag": str(axis.get("tag") or ""),
                    "internal": axis.get("internal"),
                }
                for axis in _items(master.get("axes", []), key_name="tag")
            ],
        }
        for master in masters
    ]


_SIMPLE_OPENTYPE_SUBSTITUTION = re.compile(
    r"^sub\s+(\[[^\]]+\]|[^\s]+)\s+by\s+(\[[^\]]+\]|[^\s]+)$"
)


def _parse_opentype_glyphs(value: str) -> Optional[list[str]]:
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    elif any(character.isspace() for character in text):
        return None
    glyphs = [part for part in text.split() if part]
    if not glyphs or any(
        marker in glyph for glyph in glyphs for marker in ("'", "\\", "@")
    ):
        return None
    return glyphs


def _parse_stylistic_set_substitutions(code: Any) -> dict[str, Any]:
    clean = "\n".join(
        line.split("#", 1)[0] for line in str(code or "").splitlines()
    )
    substitutions = []
    unsupported = 0
    for statement in clean.split(";"):
        rule = " ".join(statement.strip().split())
        if not rule:
            continue
        match = _SIMPLE_OPENTYPE_SUBSTITUTION.match(rule)
        if not match or "'" in rule or " lookup " in rule or " from " in rule:
            unsupported += 1
            continue
        sources = _parse_opentype_glyphs(match.group(1))
        replacements = _parse_opentype_glyphs(match.group(2))
        if not sources or not replacements or len(sources) != len(replacements):
            unsupported += 1
            continue
        substitutions.extend(
            {"source": source, "replacement": replacement}
            for source, replacement in zip(sources, replacements)
        )
    return {
        "substitutions": substitutions,
        "unsupportedRuleCount": unsupported,
        "warnings": (
            [
                "{} unsupported or contextual feature rule(s) were skipped.".format(
                    unsupported
                )
            ]
            if unsupported
            else []
        ),
    }


def list_opentype_items(
    model: Mapping[str, Any],
    *,
    kinds: Optional[Sequence[str]] = None,
    tags: Optional[Sequence[str]] = None,
    include_disabled: bool = True,
) -> list[dict[str, Any]]:
    """Return ordered feature, class, and prefix source with parsed ssXX rules."""

    roots = (
        ("feature", "features"),
        ("class", "classes"),
        ("prefix", "featurePrefixes"),
    )
    requested_kinds = {str(kind) for kind in kinds or () if str(kind)}
    unknown = requested_kinds - {kind for kind, _root in roots}
    if unknown:
        raise ValueError(
            "unsupported OpenType kinds: {}".format(", ".join(sorted(unknown)))
        )
    requested_tags = {str(tag) for tag in tags or () if str(tag)}
    result = []
    order = 0
    for kind, root in roots:
        if requested_kinds and kind not in requested_kinds:
            continue
        for collection_order, item in enumerate(_items(model.get(root, []))):
            tag = str(item.get("tag") or item.get("name") or item.get("id") or "")
            if requested_tags and tag not in requested_tags:
                continue
            disabled = bool(item.get("disabled", False))
            if disabled and not include_disabled:
                continue
            parsed = (
                _parse_stylistic_set_substitutions(item.get("code"))
                if kind == "feature" and re.fullmatch(r"ss\d\d", tag)
                else {
                    "substitutions": [],
                    "unsupportedRuleCount": 0,
                    "warnings": [],
                }
            )
            result.append(
                {
                    "kind": kind,
                    "order": order,
                    "collectionOrder": collection_order,
                    "id": str(item.get("id") or tag),
                    "name": str(item.get("name") or tag),
                    "tag": tag,
                    "code": str(item.get("code") or ""),
                    "automatic": bool(item.get("automatic", False)),
                    "disabled": disabled,
                    "notes": item.get("notes"),
                    "labels": copy.deepcopy(item.get("labels") or []),
                    "stylisticSet": bool(
                        kind == "feature" and re.fullmatch(r"ss\d\d", tag)
                    ),
                    **parsed,
                }
            )
            order += 1
    return result


def list_layers(
    model: Mapping[str, Any],
    *,
    glyph_names: Optional[Sequence[str]] = None,
    roles: Optional[Sequence[str]] = None,
    detail: str = "summary",
    observations: Optional[Mapping[tuple[str, str], Mapping[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Return ordered layer identities and reviewable lifecycle metadata."""

    requested_glyphs = {str(name) for name in glyph_names or () if str(name)}
    requested_roles = {str(role).lower() for role in roles or () if str(role)}
    known_roles = {"master", "intermediate", "alternate", "backup", "smart", "color"}
    unknown = requested_roles - known_roles
    if unknown:
        raise ValueError("unsupported layer roles: {}".format(", ".join(sorted(unknown))))
    if detail not in {"summary", "metrics", "geometry", "full"}:
        raise ValueError("detail must be summary, metrics, geometry, or full")
    glyphs = model.get("glyphs", {})
    if not isinstance(glyphs, Mapping):
        raise ValueError("glyph model must be keyed by name")
    result: list[dict[str, Any]] = []
    for glyph_name in sorted(glyphs):
        if requested_glyphs and str(glyph_name) not in requested_glyphs:
            continue
        for order, layer in enumerate(_canonical_layers(glyphs[glyph_name])):
            layer_roles = [str(role) for role in layer.get("roles", ())]
            if requested_roles and not requested_roles.intersection(layer_roles):
                continue
            item = {
                    "glyphName": str(glyph_name),
                    "id": str(layer.get("id") or ""),
                    "masterId": str(layer.get("masterId") or ""),
                    "name": str(layer.get("name") or ""),
                    "order": order,
                    "roles": layer_roles,
                    "isMasterLayer": bool(layer.get("isMasterLayer")),
                    "isSpecialLayer": bool(layer.get("isSpecialLayer")),
                    "interpolation": copy.deepcopy(layer.get("interpolation")),
                    "width": layer.get("width"),
                    "pathCount": len(layer_paths(layer)),
                    "componentCount": len(layer_components(layer)),
                    "anchorCount": len(layer_anchors(layer)),
                }
            observation = dict(
                (observations or {}).get(
                    (str(glyph_name), str(layer.get("id") or "")),
                    {},
                )
            )
            if detail in {"metrics", "full"}:
                glyph = glyphs[glyph_name]
                glyph_keys = {
                    key: glyph.get(key)
                    for key in (
                        "leftMetricsKey",
                        "rightMetricsKey",
                        "widthMetricsKey",
                    )
                }
                layer_keys = {
                    key: layer.get(key)
                    for key in glyph_keys
                }
                effective = {
                    key: {
                        "value": (
                            layer_keys[key]
                            if layer_keys[key] is not None
                            else glyph_keys[key]
                        ),
                        "source": (
                            "layer"
                            if layer_keys[key] is not None
                            else "glyph"
                            if glyph_keys[key] is not None
                            else "none"
                        ),
                    }
                    for key in glyph_keys
                }
                current = {
                    "width": layer.get("width"),
                    "leftBearing": None,
                    "rightBearing": None,
                }
                resolved = dict(current)
                item.update(
                    {
                        "glyphMetricsKeys": glyph_keys,
                        "layerMetricsKeys": layer_keys,
                        "effectiveMetricsKeys": effective,
                        "currentMetrics": current,
                        "resolvedMetrics": resolved,
                        "delta": {
                            key: 0 if value is not None else None
                            for key, value in current.items()
                        },
                        "stale": False,
                        "hasAlignedWidth": bool(layer.get("hasAlignedWidth")),
                    }
                )
                item.update(
                    {
                        key: copy.deepcopy(value)
                        for key, value in observation.items()
                        if key
                        in {
                            "glyphMetricsKeys",
                            "layerMetricsKeys",
                            "effectiveMetricsKeys",
                            "currentMetrics",
                            "resolvedMetrics",
                            "delta",
                            "stale",
                            "hasAlignedWidth",
                        }
                    }
                )
            if detail in {"geometry", "full"}:
                item["bounds"] = copy.deepcopy(observation.get("bounds"))
                item["components"] = [
                    {
                        "name": str(component.get("name") or ""),
                        "transform": copy.deepcopy(component.get("transform")),
                        "automaticAlignment": bool(
                            component.get("automaticAlignment", False)
                        ),
                    }
                    for component in layer_components(layer)
                    if isinstance(component, Mapping)
                ]
            result.append(item)
    return result


def _kerning_key(value: Any, id_to_name: Optional[Mapping[str, str]] = None) -> dict[str, Any]:
    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "unresolved")
        return {
            "kind": kind if kind in {"glyph", "group", "unresolved"} else "unresolved",
            "id": str(value.get("id") or value.get("name") or ""),
            "name": value.get("name"),
            "provenance": value.get("provenance") or "source",
        }
    text = str(value)
    resolved_name = (id_to_name or {}).get(text)
    if text.startswith("@"):
        kind = "group"
    elif resolved_name:
        kind = "glyph"
    elif text.startswith("-") and text[1:].isdigit():
        kind = "unresolved"
    else:
        kind = "glyph"
    return {
        "kind": kind,
        "id": text,
        "name": resolved_name or (None if kind == "unresolved" else text),
        "provenance": "resolved_glyph_id" if resolved_name else "source",
    }


_KERNING_DIRECTIONS = ("ltr", "rtl", "vertical")
_KERNING_ENTRY_KINDS = {"pair", "context", "all"}


def _is_directional_kerning(value: Any) -> bool:
    return isinstance(value, Mapping) and any(
        domain in value for domain in (*_KERNING_DIRECTIONS, "context")
    )


def _parse_exact_context_key(
    value: Any, *, glyph_names: set[str]
) -> tuple[list[str], int] | None:
    """Parse the exact-glyph subset of Glyphs 4 ``kerningContext`` keys.

    Glyphs places ``*`` at the adjusted boundary. Bracket classes and AFDKO
    marked-run syntax remain lossless raw records, but are intentionally not
    normalized into the typed write contract.
    """

    tokens = str(value or "").split()
    if tokens.count("*") != 1:
        return None
    boundary_index = tokens.index("*")
    sequence = tokens[:boundary_index] + tokens[boundary_index + 1 :]
    if (
        len(sequence) < 3
        or not 1 <= boundary_index < len(sequence)
        or any(
            not token
            or token not in glyph_names
            or any(character in token for character in "[]*'")
            for token in sequence
        )
    ):
        return None
    return sequence, boundary_index


def _context_key(sequence: Sequence[str], boundary_index: int) -> str:
    return "{} * {}".format(
        " ".join(sequence[:boundary_index]),
        " ".join(sequence[boundary_index:]),
    )


def list_kerning_pairs(
    model: Mapping[str, Any], *, entry_kind: str = "pair"
) -> list[dict[str, Any]]:
    selected_kind = str(entry_kind or "pair").lower()
    if selected_kind not in _KERNING_ENTRY_KINDS:
        raise ValueError("entryKind must be pair, context, or all")
    pairs: list[dict[str, Any]] = []
    contexts: list[dict[str, Any]] = []
    glyphs = _items(model.get("glyphs", {}), key_name="name")
    id_to_name = {
        str(glyph.get("id")): str(glyph.get("name"))
        for glyph in glyphs
        if glyph.get("id") and glyph.get("name")
    }
    glyph_names = {
        str(glyph.get("name")) for glyph in glyphs if glyph.get("name")
    }
    source = model.get("kerning", [])

    def append_pair_domain(direction: str, domain: Any) -> None:
        if not isinstance(domain, Mapping):
            return
        for master_id, lefts in domain.items():
            if not isinstance(lefts, Mapping):
                continue
            for left, rights in lefts.items():
                if not isinstance(rights, Mapping):
                    continue
                for right, value in rights.items():
                    pairs.append(
                        {
                            "entryKind": "pair",
                            "direction": direction,
                            "masterId": str(master_id),
                            "left": _kerning_key(left, id_to_name),
                            "right": _kerning_key(right, id_to_name),
                            "value": value,
                            "provenance": "source",
                        }
                    )

    directional = _is_directional_kerning(source)
    if selected_kind in {"pair", "all"} and isinstance(source, Mapping):
        if directional:
            for direction in _KERNING_DIRECTIONS:
                append_pair_domain(direction, source.get(direction, {}))
        else:
            append_pair_domain("ltr", source)
    elif selected_kind in {"pair", "all"}:
        for pair in _items(source):
            pairs.append(
                {
                    "entryKind": "pair",
                    "direction": str(pair.get("direction") or "ltr"),
                    "masterId": str(pair.get("masterId") or ""),
                    "left": _kerning_key(pair.get("left"), id_to_name),
                    "right": _kerning_key(pair.get("right"), id_to_name),
                    "value": pair.get("value"),
                    "provenance": pair.get("provenance") or "source",
                }
            )

    if selected_kind in {"context", "all"} and directional:
        context_domain = source.get("context", {})
        if isinstance(context_domain, Mapping):
            for raw_context_key, master_values in context_domain.items():
                if not isinstance(master_values, Mapping):
                    continue
                parsed = _parse_exact_context_key(
                    raw_context_key, glyph_names=glyph_names
                )
                for master_id, value in master_values.items():
                    contexts.append(
                        {
                            "entryKind": "context",
                            "masterId": str(master_id),
                            "sequence": parsed[0] if parsed else None,
                            "boundaryIndex": parsed[1] if parsed else None,
                            "value": value,
                            "rawContextKey": str(raw_context_key),
                            "editable": parsed is not None,
                            "provenance": "source",
                        }
                    )

    direction_order = {
        direction: index for index, direction in enumerate(_KERNING_DIRECTIONS)
    }
    pairs.sort(
        key=lambda pair: (
            direction_order.get(str(pair["direction"]), len(direction_order)),
            pair["masterId"],
            pair["left"]["id"],
            pair["right"]["id"],
        )
    )
    contexts.sort(
        key=lambda item: (
            item["masterId"],
            item["rawContextKey"],
        )
    )
    return pairs + contexts


def _layer_roles(layer: Mapping[str, Any]) -> set[str]:
    roles = layer.get("roles", ())
    if not isinstance(roles, Sequence) or isinstance(
        roles, (str, bytes, bytearray)
    ):
        return set()
    return {str(role).lower() for role in roles if str(role)}


def _iter_all_layers(
    glyph: Mapping[str, Any],
) -> Iterable[tuple[str, Optional[str], Mapping[str, Any]]]:
    """Return every layer by layer identity without collapsing master links.

    The optional second tuple value is the collection key of a legacy
    mapping-shaped fixture. Schema-v6 canonical layers always use the ordered
    list form and carry their own unique, non-empty ``id``.
    """

    layers = glyph.get("layers", ())
    if isinstance(layers, Mapping):
        for key, layer in layers.items():
            if not isinstance(layer, Mapping):
                continue
            collection_key = str(key)
            layer_id = str(layer.get("id") or collection_key)
            if layer_id:
                yield layer_id, collection_key, layer
        return
    if not isinstance(layers, Sequence) or isinstance(
        layers, (str, bytes, bytearray)
    ):
        return
    for layer in layers:
        if not isinstance(layer, Mapping):
            continue
        layer_id = str(layer.get("id") or "")
        if layer_id:
            yield layer_id, None, layer


def _master_layer_map(
    glyph: Mapping[str, Any], master_ids: Sequence[str]
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[str, list[str]],
]:
    """Select true master layers without allowing associated layers to win.

    Explicit ``isMasterLayer`` flags are authoritative. A ``master`` role is a
    compatibility discriminator only when the boolean flag is absent. The
    mapping-key fallback exists solely for older minimal test fixtures that do
    not carry either discriminator.
    """

    declared_master_ids = {
        str(master_id) for master_id in master_ids if str(master_id)
    }
    candidates: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for layer_id, collection_key, layer in _iter_all_layers(glyph):
        is_master = layer.get("isMasterLayer")
        roles = _layer_roles(layer)
        master_id = ""
        if is_master is False:
            continue
        if is_master is True or "master" in roles:
            master_id = str(layer.get("masterId") or layer_id)
        elif collection_key is not None and not roles:
            if declared_master_ids and collection_key not in declared_master_ids:
                continue
            master_id = collection_key
        if master_id:
            candidates.setdefault(master_id, []).append((layer_id, layer))

    masters: dict[str, Mapping[str, Any]] = {}
    duplicates: dict[str, list[str]] = {}
    for master_id, layers in candidates.items():
        masters[master_id] = layers[0][1]
        if len(layers) > 1:
            duplicates[master_id] = [layer_id for layer_id, _layer in layers]
    return masters, duplicates


def _is_special_layer(layer: Mapping[str, Any]) -> bool:
    return bool(layer.get("isSpecialLayer")) or bool(
        _layer_roles(layer).intersection(
            {"intermediate", "alternate", "smart", "color"}
        )
    )


def _duplicate_master_findings(
    glyph_name: str, duplicates: Mapping[str, Sequence[str]]
) -> list[dict[str, Any]]:
    return [
        _finding(
            "duplicate_master_layer",
            "hard",
            "Multiple explicit master layers target the same master.",
            {
                "glyphName": glyph_name,
                "masterId": master_id,
                "layerIds": list(layer_ids),
            },
        )
        for master_id, layer_ids in sorted(duplicates.items())
    ]


def _component_names(layer: Mapping[str, Any]) -> list[str]:
    result = []
    for component in layer_components(layer):
        if isinstance(component, Mapping):
            result.append(str(component.get("name") or component.get("componentName") or ""))
    if not result and isinstance(layer.get("components"), Sequence):
        result.extend(
            str(component)
            for component in layer.get("components", ())
            if not isinstance(component, Mapping)
        )
    return result


def review_master_compatibility(
    model: Mapping[str, Any],
    *,
    mode: str = "component_preserving",
    include_nonexporting: bool = False,
) -> dict[str, Any]:
    if mode not in {"component_preserving", "decomposed_export"}:
        raise ValueError("unsupported compatibility mode")
    master_ids = [str(master.get("id") or "") for master in _items(model.get("masters", []))]
    glyph_map = {str(glyph.get("name")): glyph for glyph in _items(model.get("glyphs", {}), key_name="name")}
    findings: list[dict[str, Any]] = []
    graph: dict[str, set[str]] = {name: set() for name in glyph_map}
    special_layer_count = 0
    reviewed = 0
    for name, glyph in sorted(glyph_map.items()):
        if not include_nonexporting and not bool(glyph.get("export", True)):
            continue
        reviewed += 1
        target = {"glyphName": name}
        if glyph.get("mastersCompatible") is False:
            findings.append(_finding("host_incompatible", "hard", "Glyphs reports incompatible master layers.", target))
        all_layers = list(_iter_all_layers(glyph))
        layers, duplicate_masters = _master_layer_map(glyph, master_ids)
        findings.extend(_duplicate_master_findings(name, duplicate_masters))
        special_layers: list[tuple[str, Mapping[str, Any]]] = []
        for layer_id, _collection_key, layer in all_layers:
            if not _is_special_layer(layer):
                continue
            special_layer_count += 1
            special_layers.append((layer_id, layer))
            findings.append(
                _finding(
                    "special_layer_present",
                    "soft",
                    "A special layer participates in compatibility and export review.",
                    {"glyphName": name, "layerId": layer_id},
                )
            )

        dependency_layers: list[Mapping[str, Any]] = list(layers.values())
        dependency_layers.extend(layer for _layer_id, layer in special_layers)
        for layer in dependency_layers:
            for component_name in _component_names(layer):
                if component_name:
                    graph[name].add(component_name)
                    if component_name not in glyph_map:
                        findings.append(
                            _finding(
                                "missing_component",
                                "hard",
                                "A component target is missing from the font.",
                                {"glyphName": name, "componentName": component_name},
                            )
                        )
        missing_layers = [master_id for master_id in master_ids if master_id and master_id not in layers]
        if missing_layers:
            findings.append(
                _finding(
                    "missing_master_layer",
                    "hard",
                    "One or more master layers are missing.",
                    {"glyphName": name, "masterIds": missing_layers},
                )
            )
        reference_id = next((master_id for master_id in master_ids if master_id in layers), None)
        if reference_id is None and layers:
            reference_id = sorted(layers)[0]
        if reference_id is None:
            continue
        reference = layers[reference_id]
        reference_components = _component_names(reference)
        for master_id, layer in sorted(layers.items()):
            if master_id == reference_id:
                continue
            if mode == "component_preserving" and _component_names(layer) != reference_components:
                findings.append(
                    _finding(
                        "component_sequence_mismatch",
                        "hard",
                        "Component identities or order differ between masters.",
                        {"glyphName": name, "referenceMasterId": reference_id, "masterId": master_id},
                    )
                )
            if path_signature(layer) != path_signature(reference):
                findings.append(
                    _finding(
                        "path_topology_mismatch",
                        "hard",
                        "Path topology differs between masters.",
                        {"glyphName": name, "referenceMasterId": reference_id, "masterId": master_id},
                    )
                )
        for layer_id, layer in special_layers:
            associated_master_id = str(layer.get("masterId") or "")
            associated_master = layers.get(associated_master_id)
            if associated_master is None:
                continue
            special_target = {
                "glyphName": name,
                "layerId": layer_id,
                "associatedMasterId": associated_master_id,
            }
            if (
                mode == "component_preserving"
                and _component_names(layer) != _component_names(associated_master)
            ):
                findings.append(
                    _finding(
                        "special_layer_component_sequence_mismatch",
                        "hard",
                        "Component identities or order differ from the associated master.",
                        special_target,
                    )
                )
            if path_signature(layer) != path_signature(associated_master):
                findings.append(
                    _finding(
                        "special_layer_path_topology_mismatch",
                        "hard",
                        "Path topology differs from the associated master.",
                        special_target,
                    )
                )
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str, trail: list[str]) -> None:
        if name in visiting:
            cycle = trail[trail.index(name) :] + [name] if name in trail else trail + [name]
            findings.append(
                _finding("component_cycle", "hard", "The component graph contains a cycle.", {"cycle": cycle})
            )
            return
        if name in visited:
            return
        visiting.add(name)
        for child in sorted(graph.get(name, ())):
            if child in graph:
                visit(child, trail + [name])
        visiting.discard(name)
        visited.add(name)

    for glyph_name in sorted(graph):
        visit(glyph_name, [])
    dependencies = []
    for glyph_name in sorted(graph):
        direct = sorted(graph[glyph_name])
        if not direct:
            continue
        transitive: set[str] = set()
        pending = list(direct)
        while pending:
            child = pending.pop()
            if child in transitive:
                continue
            transitive.add(child)
            pending.extend(graph.get(child, ()))
        dependencies.append(
            {
                "glyphName": glyph_name,
                "direct": direct,
                "transitive": sorted(transitive),
            }
        )
    unique = {finding["id"]: finding for finding in findings}
    findings = sorted(unique.values(), key=lambda item: (item["severity"], item["code"], item["id"]))
    return {
        "mode": mode,
        "reviewedGlyphCount": reviewed,
        "specialLayerCount": special_layer_count,
        "componentDependencyCount": len(dependencies),
        "componentDependencies": dependencies,
        "findings": findings,
        "hasHardFailures": any(item["severity"] == "hard" for item in findings),
    }


def review_metrics_inheritance(
    model: Mapping[str, Any],
    *,
    glyph_names: Optional[Sequence[str]] = None,
    tolerance: float = 0.01,
    observations: Optional[Mapping[tuple[str, str], Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    if not math.isfinite(float(tolerance)) or float(tolerance) < 0:
        raise ValueError("tolerance must be a non-negative finite number")
    glyphs = {str(item.get("name")): item for item in _items(model.get("glyphs", {}), key_name="name")}
    requested = {str(name) for name in glyph_names or () if str(name)}
    missing = sorted(requested - set(glyphs))
    if missing:
        raise ValueError("unknown glyphNames: {}".format(", ".join(missing)))
    master_ids = [
        str(master.get("id") or "")
        for master in _items(model.get("masters", []))
    ]
    findings: list[dict[str, Any]] = []
    keys = ("leftMetricsKey", "rightMetricsKey", "widthMetricsKey")
    metrics: list[dict[str, Any]] = []
    for name, glyph in sorted(glyphs.items()):
        if requested and name not in requested:
            continue
        for key in keys:
            reference = glyph.get(key)
            if isinstance(reference, str) and reference.startswith("="):
                target = reference.lstrip("=|").split("+", 1)[0].strip()
                if target and target not in glyphs:
                    findings.append(
                        _finding(
                            "missing_metrics_reference",
                            "hard",
                            "A glyph metrics key references a missing glyph.",
                            {
                                "glyphName": name,
                                "scope": "glyph",
                                "field": key,
                                "reference": target,
                            },
                        )
                    )
        layers, duplicate_masters = _master_layer_map(glyph, master_ids)
        findings.extend(_duplicate_master_findings(name, duplicate_masters))
        for master_id, layer in sorted(layers.items()):
            observation = dict(
                (observations or {}).get(
                    (name, str(layer.get("id") or master_id)),
                    {},
                )
            )
            glyph_keys = {key: glyph.get(key) for key in keys}
            layer_keys = {key: layer.get(key) for key in keys}
            current = dict(
                observation.get("currentMetrics")
                or {
                    "width": layer.get("width"),
                    "leftBearing": None,
                    "rightBearing": None,
                }
            )
            resolved = dict(observation.get("resolvedMetrics") or current)
            delta = {}
            stale = False
            for metric in ("width", "leftBearing", "rightBearing"):
                left, right = current.get(metric), resolved.get(metric)
                value = (
                    float(right) - float(left)
                    if isinstance(left, (int, float))
                    and isinstance(right, (int, float))
                    else None
                )
                delta[metric] = value
                if value is not None and abs(value) > float(tolerance):
                    stale = True
            metrics.append(
                {
                    "glyphName": name,
                    "layerId": str(layer.get("id") or master_id),
                    "masterId": master_id,
                    "glyphMetricsKeys": glyph_keys,
                    "layerMetricsKeys": layer_keys,
                    "effectiveMetricsKeys": {
                        key: {
                            "value": (
                                layer_keys[key]
                                if layer_keys[key] is not None
                                else glyph_keys[key]
                            ),
                            "source": (
                                "layer"
                                if layer_keys[key] is not None
                                else "glyph"
                                if glyph_keys[key] is not None
                                else "none"
                            ),
                        }
                        for key in keys
                    },
                    "currentMetrics": current,
                    "resolvedMetrics": resolved,
                    "delta": delta,
                    "stale": stale,
                }
            )
            for key in keys:
                reference = layer.get(key)
                if isinstance(reference, str) and reference.startswith("="):
                    target = reference.lstrip("=|").split("+", 1)[0].strip()
                    if target and target not in glyphs:
                        findings.append(
                            _finding(
                                "missing_metrics_reference",
                                "hard",
                                "A metrics key references a missing glyph.",
                                {"glyphName": name, "masterId": master_id, "field": key, "reference": target},
                            )
                        )
            components = _component_names(layer)
            if components and any(
                layer.get(key) is not None or glyph.get(key) is not None
                for key in keys
            ):
                findings.append(
                    _finding(
                        "component_metrics_override",
                        "soft",
                        "A component layer also defines explicit metrics inheritance.",
                        {"glyphName": name, "masterId": master_id},
                    )
                )
    return {
        "reviewedGlyphCount": len(requested or glyphs),
        "reviewedLayerCount": len(metrics),
        "staleLayerCount": sum(bool(item["stale"]) for item in metrics),
        "tolerance": float(tolerance),
        "metrics": metrics,
        "findings": findings,
        "hasHardFailures": any(item["severity"] == "hard" for item in findings),
    }


def _anchor_names(layer: Mapping[str, Any]) -> list[str]:
    return [str(anchor.get("name") or "") for anchor in layer_anchors(layer)]


def review_anchor_consistency(model: Mapping[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    glyphs = _items(model.get("glyphs", {}), key_name="name")
    master_ids = [
        str(master.get("id") or "")
        for master in _items(model.get("masters", []))
    ]
    for glyph in glyphs:
        name = str(glyph.get("name") or "")
        layers, duplicate_masters = _master_layer_map(glyph, master_ids)
        findings.extend(_duplicate_master_findings(name, duplicate_masters))
        if not layers:
            continue
        reference_id = next(
            (master_id for master_id in master_ids if master_id in layers),
            sorted(layers)[0],
        )
        reference_names = _anchor_names(layers[reference_id])
        if len(reference_names) != len(set(reference_names)):
            findings.append(
                _finding("duplicate_anchor_name", "hard", "A layer contains duplicate anchor names.", {"glyphName": name, "masterId": reference_id})
            )
        reference_set = set(reference_names)
        for master_id, layer in sorted(layers.items()):
            names = _anchor_names(layer)
            if len(names) != len(set(names)):
                findings.append(
                    _finding("duplicate_anchor_name", "hard", "A layer contains duplicate anchor names.", {"glyphName": name, "masterId": master_id})
                )
            if set(names) != reference_set:
                findings.append(
                    _finding(
                        "anchor_set_difference",
                        "soft",
                        "Anchor names differ between master layers; verify whether this is intentional.",
                        {
                            "glyphName": name,
                            "referenceMasterId": reference_id,
                            "masterId": master_id,
                            "missing": sorted(reference_set - set(names)),
                            "extra": sorted(set(names) - reference_set),
                        },
                    )
                )
    unique = {finding["id"]: finding for finding in findings}
    ordered = sorted(unique.values(), key=lambda item: (item["code"], item["id"]))
    return {
        "reviewedGlyphCount": len(glyphs),
        "findings": ordered,
        "hasHardFailures": any(item["severity"] == "hard" for item in ordered),
    }


def simulate_spacing(
    items: Sequence[Mapping[str, Any]],
    *,
    max_iterations: int = 5,
    tolerance: float = 1.0,
) -> dict[str, Any]:
    iterations = max(1, min(int(max_iterations), 20))
    tolerance_value = max(0.0, float(tolerance))
    normalized: list[dict[str, Any]] = []
    widths: dict[tuple[str, str], float] = {}
    for source in items:
        item = copy.deepcopy(dict(source))
        name = str(item.get("glyphName") or item.get("name") or "")
        master_id = str(item.get("masterId") or "")
        key = (name, master_id)
        if not name or key in widths:
            raise ValueError("spacing items require unique explicit glyph/master targets")
        item["glyphName"], item["masterId"] = key
        item["beforeWidth"] = float(item.get("width") or 0)
        widths[key] = item["beforeWidth"]
        normalized.append(item)

    skipped: dict[tuple[str, str], str] = {}
    dependencies = []
    for item in normalized:
        key = (item["glyphName"], item["masterId"])
        if item["beforeWidth"] == 0 and str(item.get("category") or "").lower() == "mark":
            skipped[key] = "zero_width_mark"
            continue
        if bool(item.get("hostOwnsWidth")):
            skipped[key] = "automatic_alignment"
            continue
        reference_name = item.get("referenceGlyphName")
        if reference_name:
            reference = (
                str(reference_name),
                str(item.get("referenceMasterId") or item["masterId"]),
            )
            dependencies.append({"target": list(key), "source": list(reference)})
            if reference not in widths:
                skipped[key] = "missing_dependency"

    converged = False
    completed_iterations = 0
    for iteration in range(1, iterations + 1):
        proposals = dict(widths)
        maximum_delta = 0.0
        for item in normalized:
            key = (item["glyphName"], item["masterId"])
            if key in skipped:
                continue
            reference_name = item.get("referenceGlyphName")
            if reference_name:
                reference = (
                    str(reference_name),
                    str(item.get("referenceMasterId") or item["masterId"]),
                )
                target = widths[reference] + float(item.get("offset") or 0)
            else:
                target = float(item.get("targetWidth", widths[key]))
            proposals[key] = target
            maximum_delta = max(maximum_delta, abs(target - widths[key]))
        widths = proposals
        completed_iterations = iteration
        if maximum_delta <= tolerance_value:
            converged = True
            break

    results: list[dict[str, Any]] = []
    for item in normalized:
        key = (item["glyphName"], item["masterId"])
        if key in skipped:
            results.append(
                {
                    "glyphName": key[0],
                    "masterId": key[1],
                    "status": "skipped",
                    "reason": skipped[key],
                    "iterations": completed_iterations if skipped[key] == "missing_dependency" else 0,
                }
            )
            continue
        delta = widths[key] - item["beforeWidth"]
        results.append(
            {
                "glyphName": key[0],
                "masterId": key[1],
                "status": "ready" if abs(delta) > tolerance_value else "no_change",
                "reason": None,
                "iterations": completed_iterations,
                "beforeWidth": item["beforeWidth"],
                "proposedWidth": widths[key],
                "deltaWidth": delta,
            }
        )
    dependency_payload = json.dumps(dependencies, sort_keys=True, separators=(",", ":"))
    return {
        "maxIterations": iterations,
        "tolerance": tolerance_value,
        "completedIterations": completed_iterations,
        "converged": converged,
        "status": "converged" if converged else "iteration_limit",
        "dependencyCount": len(dependencies),
        "dependencyFingerprint": "sha256:{}".format(hashlib.sha256(dependency_payload.encode("utf-8")).hexdigest()),
        "items": results,
        "actionableCount": sum(item["status"] == "ready" for item in results),
    }


def review_kerning_coverage(
    model: Mapping[str, Any],
    *,
    mode: str,
    eligible_count: Optional[int] = None,
    measured_count: Optional[int] = None,
    skipped_count: int = 0,
) -> dict[str, Any]:
    modes = {
        "proof_families",
        "class_representatives",
        "class_cross_product",
        "glyph_expansion",
        "context_sequences",
    }
    if mode not in modes:
        raise ValueError("unsupported kerning coverage mode")
    entry_kind = "context" if mode == "context_sequences" else "pair"
    entries = list_kerning_pairs(model, entry_kind=entry_kind)
    eligible = len(entries) if eligible_count is None else max(0, int(eligible_count))
    measured = 0 if measured_count is None else max(0, int(measured_count))
    measured = min(eligible, measured)
    skipped = max(0, int(skipped_count))
    untested = max(0, eligible - measured - skipped)
    result = {
        "mode": mode,
        "entryKind": entry_kind,
        "eligibleCount": eligible,
        "measuredCount": measured,
        "skippedCount": skipped,
        "untestedCount": untested,
        "complete": untested == 0,
        "accountingComplete": eligible == measured + skipped + untested,
    }
    if entry_kind == "context":
        by_master: dict[str, dict[str, Any]] = {}
        for entry in entries:
            master_id = str(entry.get("masterId") or "")
            summary = by_master.setdefault(
                master_id,
                {
                    "masterId": master_id,
                    "entryCount": 0,
                    "editableCount": 0,
                    "rawOnlyCount": 0,
                },
            )
            summary["entryCount"] += 1
            summary[
                "editableCount" if entry.get("editable") else "rawOnlyCount"
            ] += 1
        editable_count = sum(bool(entry.get("editable")) for entry in entries)
        result.update(
            {
                "contextEntryCount": len(entries),
                "editableCount": editable_count,
                "rawOnlyCount": len(entries) - editable_count,
                "byMaster": [by_master[key] for key in sorted(by_master)],
            }
        )
    return result


def review_export(
    *,
    destination_state: Mapping[str, Any],
    compatibility: Mapping[str, Any],
    overwrite_policy: str = "fail_if_nonempty",
    expected_destination_fingerprint: Optional[str] = None,
    acknowledged_finding_ids: Sequence[str] = (),
) -> dict[str, Any]:
    if overwrite_policy not in {"fail_if_nonempty", "replace_if_match"}:
        raise ValueError("unsupported overwrite policy")
    blocking: list[str] = []
    exists = bool(destination_state.get("exists"))
    empty = bool(destination_state.get("empty", not exists))
    actual_fingerprint = destination_state.get("fingerprint")
    if exists and destination_state.get("kind") not in {None, "directory"}:
        blocking.append("destination_not_directory")
    if exists and not empty:
        if overwrite_policy == "fail_if_nonempty":
            blocking.append("destination_not_empty")
        elif not expected_destination_fingerprint or expected_destination_fingerprint != actual_fingerprint:
            blocking.append("destination_fingerprint_mismatch")
    hard_ids = {
        str(finding.get("id"))
        for finding in compatibility.get("findings", [])
        if isinstance(finding, Mapping) and finding.get("severity", "hard") == "hard"
    }
    if compatibility.get("hasHardFailures") and not hard_ids.issubset(set(acknowledged_finding_ids)):
        blocking.append("hard_compatibility_failure")
    return {
        "ready": not blocking,
        "overwritePolicy": overwrite_policy,
        "destinationFingerprint": actual_fingerprint,
        "blockingCodes": sorted(set(blocking)),
        "stagingRequired": True,
        "atomicPublishRequired": True,
        "includeBuildHelper": False,
    }


def build_glyph_updates(model: Mapping[str, Any], updates: Sequence[Mapping[str, Any]]) -> ChangeSet:
    """Build property and membership changes for the canonical glyph map."""

    target_names = [str(update.get("glyphName") or "") for update in updates]
    after = _copy_on_write_model(
        model,
        glyph_names=target_names,
        deep_glyphs=False,
    )
    glyphs = after.setdefault("glyphs", {})
    if not isinstance(glyphs, dict):
        raise ValueError("glyph model must be keyed by name for batch updates")
    seen: set[tuple[str, str]] = set()
    allowed = {"category", "subCategory", "unicode", "export", "leftKerningGroup", "rightKerningGroup"}
    for update in updates:
        name = str(update.get("glyphName") or "")
        action = str(update.get("action") or "update").lower()
        target = (action, name)
        if not name or target in seen:
            raise ValueError("glyph updates require unique explicit action/name targets")
        seen.add(target)
        if action == "create":
            if name in glyphs:
                raise ValueError("glyph already exists: {}".format(name))
            glyphs[name] = {
                "id": canonical_glyph_id(name),
                "name": name,
                "category": update.get("category"),
                "subCategory": update.get("subCategory"),
                "unicode": update.get("unicode"),
                "export": bool(update.get("export", True)),
                "leftKerningGroup": update.get("leftKerningGroup"),
                "rightKerningGroup": update.get("rightKerningGroup"),
                "layers": [],
            }
            continue
        if action == "delete":
            if name not in glyphs:
                raise ValueError("unknown glyph: {}".format(name))
            del glyphs[name]
            continue
        if action != "update":
            raise ValueError("glyph action must be create, update, or delete")
        if name not in glyphs or not isinstance(glyphs[name], dict):
            raise ValueError("unknown glyph: {}".format(name))
        supplied = allowed.intersection(update)
        if not supplied:
            raise ValueError("glyph updates require at least one writable property")
        for key, value in update.items():
            if key in allowed:
                glyphs[name][key] = copy.deepcopy(value)
    return diff_models(model, after)


# Internal compatibility name for existing pure callers. It is not a public
# MCP review token or registered capability.
review_glyph_updates = build_glyph_updates


def build_opentype_updates(
    model: Mapping[str, Any], updates: Sequence[Mapping[str, Any]]
) -> ChangeSet:
    """Build feature, class, and prefix membership/state changes."""

    roots = {
        "feature": "features",
        "class": "classes",
        "prefix": "featurePrefixes",
    }
    after = _copy_on_write_model(
        model,
        roots=(
            roots[str(update.get("kind") or "")]
            for update in updates
            if str(update.get("kind") or "") in roots
        ),
    )
    allowed = {"code", "automatic", "disabled"}
    seen: set[tuple[str, str, str]] = set()
    for update in updates:
        kind = str(update.get("kind") or "")
        root = roots.get(kind)
        name = str(update.get("name") or "")
        action = str(update.get("action") or "update").lower()
        target = (action, kind, name)
        if root is None:
            raise ValueError("OpenType update kind must be feature, class, or prefix")
        if not name or target in seen:
            raise ValueError("OpenType updates require unique action/kind/name targets")
        seen.add(target)
        collection = after.get(root)
        if not isinstance(collection, list):
            raise ValueError("{} must be an ordered canonical collection".format(root))
        require_indexed_entities(collection, root)
        index = find_entity_index(collection, name)
        if action == "create":
            if index is not None:
                raise ValueError("OpenType target already exists: {}/{}".format(kind, name))
            automatic = bool(update.get("automatic", False))
            code = str(update.get("code") or "")
            if automatic and code:
                raise ValueError("code updates require the resulting automatic false")
            collection.append(
                {
                    "id": name,
                    "name": name,
                    "code": code,
                    "automatic": automatic,
                    "disabled": bool(update.get("disabled", False)),
                }
            )
            if "index" in update:
                move_entity(collection, name, int(update["index"]))
            continue
        if index is None:
            raise ValueError("unknown OpenType target: {}/{}".format(kind, name))
        if action == "delete":
            del collection[index]
            continue
        if action == "move":
            if "index" not in update:
                raise ValueError("OpenType move requires index")
            move_entity(collection, name, int(update["index"]))
            continue
        if action != "update":
            raise ValueError("OpenType action must be create, update, move, or delete")
        item = collection[index]
        supplied = allowed.intersection(update)
        if not supplied:
            raise ValueError("OpenType updates require code, automatic, or disabled")
        resulting_automatic = bool(
            update.get("automatic")
            if "automatic" in update
            else item.get("automatic", False)
        )
        if "code" in supplied and resulting_automatic:
            raise ValueError("code updates require the resulting automatic false")
        if "automatic" in supplied:
            item["automatic"] = bool(update.get("automatic"))
        if "code" in supplied:
            item["code"] = str(update.get("code") or "")
        if "disabled" in supplied:
            item["disabled"] = bool(update.get("disabled"))
    return diff_models(model, after)


def build_instance_updates(
    model: Mapping[str, Any], updates: Sequence[Mapping[str, Any]]
) -> ChangeSet:
    """Build ordered instance membership and property changes."""

    after = _copy_on_write_model(model, roots=("instances",))
    collection = after.setdefault("instances", [])
    if not isinstance(collection, list):
        raise ValueError("instances must be an ordered canonical collection")
    require_indexed_entities(collection, "instances")
    seen: set[tuple[str, str]] = set()
    writable = {"name", "type", "included", "axes"}

    def synchronized_style_name(
        properties: Sequence[Mapping[str, Any]], name: str
    ) -> list[dict[str, Any]]:
        """Synchronize the convenience name with official v4 properties."""

        result = [copy.deepcopy(dict(item)) for item in properties]
        style_index = next(
            (
                index
                for index, item in enumerate(result)
                if str(item.get("key") or "") == "styleNames"
            ),
            None,
        )
        if style_index is None:
            result.append(
                {
                    "id": deterministic_occurrence_id(
                        "property", "styleNames", 0
                    ),
                    "key": "styleNames",
                    "value": None,
                    "values": [{"language": "dflt", "value": name}],
                }
            )
            return result
        record = result[style_index]
        localized = [
            copy.deepcopy(dict(item))
            for item in record.get("values", [])
            if isinstance(item, Mapping)
        ]
        default_index = next(
            (
                index
                for index, item in enumerate(localized)
                if str(item.get("language") or "") == "dflt"
            ),
            None,
        )
        if default_index is None:
            localized.append({"language": "dflt", "value": name})
        else:
            localized[default_index]["value"] = name
        record["value"] = None
        record["values"] = localized
        return result
    for update in updates:
        action = str(update.get("action") or "update").lower()
        identity = str(update.get("instanceId") or "")
        target = (action, identity)
        if not identity or target in seen:
            raise ValueError("instance updates require unique action/instanceId targets")
        seen.add(target)
        index = find_entity_index(collection, identity)
        if action == "create":
            if index is not None:
                raise ValueError("instance already exists: {}".format(identity))
            kind = str(update.get("type") or "static").lower()
            if kind not in {"static", "variable"}:
                raise ValueError("instance type must be static or variable")
            if not str(update.get("name") or ""):
                raise ValueError("instance creation requires name")
            name = str(update.get("name"))
            included = bool(update.get("included", True))
            collection.append(
                {
                    "id": identity,
                    "name": name,
                    "type": kind,
                    "included": included,
                    "inclusionReason": None,
                    "interpolationSupported": kind != "variable",
                    "exports": included,
                    "visible": True,
                    "isBold": False,
                    "isItalic": False,
                    "linkStyle": None,
                    "manualInterpolation": False,
                    "weightClass": 400,
                    "widthClass": 5,
                    "instanceInterpolations": {},
                    "customParameters": [],
                    "properties": synchronized_style_name([], name),
                    "userData": {},
                    "axes": copy.deepcopy(list(update.get("axes") or [])),
                }
            )
            if "index" in update:
                move_entity(collection, identity, int(update["index"]))
            continue
        if index is None:
            raise ValueError("unknown instance: {}".format(identity))
        if action == "delete":
            del collection[index]
            continue
        if action == "move":
            if "index" not in update:
                raise ValueError("instance move requires index")
            move_entity(collection, identity, int(update["index"]))
            continue
        if action != "update":
            raise ValueError("instance action must be create, update, move, or delete")
        supplied = writable.intersection(update)
        if not supplied:
            raise ValueError("instance updates require a writable property")
        item = collection[index]
        if "name" in supplied:
            name = str(update.get("name") or "")
            if not name:
                raise ValueError("instance name cannot be empty")
            item["name"] = name
            item["properties"] = synchronized_style_name(
                item.get("properties", []), name
            )
        if "type" in supplied:
            kind = str(update.get("type") or "").lower()
            if kind not in {"static", "variable"}:
                raise ValueError("instance type must be static or variable")
            item["type"] = kind
            item["interpolationSupported"] = kind != "variable"
        if "included" in supplied:
            item["included"] = bool(update.get("included"))
            item["exports"] = item["included"]
        if "axes" in supplied:
            item["axes"] = copy.deepcopy(list(update.get("axes") or []))
    return diff_models(model, after)


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


def build_master_updates(
    model: Mapping[str, Any], updates: Sequence[Mapping[str, Any]]
) -> MutationBuild:
    """Build one canonical master lifecycle patch.

    Duplicating or deleting a master owns the corresponding master layer in
    every glyph and the master's kerning partition. The canonical target is
    complete; the small execution context tells the native adapter which
    source master to copy so state outside the canonical schema is retained.
    """

    after = dict(model)
    source_masters = model.get("masters", [])
    if not isinstance(source_masters, (list, tuple)):
        raise ValueError("masters must be an ordered canonical collection")
    masters = [dict(master) for master in source_masters]
    after["masters"] = masters
    require_indexed_entities(masters, "masters")
    source_glyphs = model.get("glyphs", {})
    if not isinstance(source_glyphs, Mapping):
        raise ValueError("glyphs must be keyed by name")
    glyphs = dict(source_glyphs)
    after["glyphs"] = glyphs
    source_kerning = model.get("kerning", {})
    if not isinstance(source_kerning, Mapping):
        raise ValueError("kerning must be keyed by master ID")
    directional_kerning = any(
        domain in source_kerning for domain in ("ltr", "rtl", "vertical", "context")
    )
    kerning = (
        {
            domain: (
                {
                    str(context_key): dict(master_values)
                    if isinstance(master_values, Mapping)
                    else copy.deepcopy(master_values)
                    for context_key, master_values in source_kerning.get(
                        domain, {}
                    ).items()
                }
                if domain == "context"
                and isinstance(source_kerning.get(domain, {}), Mapping)
                else dict(source_kerning.get(domain, {}))
            )
            if isinstance(source_kerning.get(domain, {}), Mapping)
            else copy.deepcopy(source_kerning.get(domain))
            for domain in ("ltr", "rtl", "vertical", "context")
        }
        if directional_kerning
        else dict(source_kerning)
    )
    after["kerning"] = kerning
    source_map: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()

    for update in updates:
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
                raise ValueError(
                    "master duplication sources must predate the current batch"
                )
            if index is not None:
                raise ValueError("master already exists: {}".format(master_id))
            source = dict(masters[source_index])
            source["id"] = master_id
            source["name"] = str(update.get("name") or source.get("name") or "")
            if not source["name"]:
                raise ValueError("duplicated master name cannot be empty")
            if "italicAngle" in update:
                source["italicAngle"] = float(update["italicAngle"])
            if "axes" in update:
                expected_tags = [str(axis.get("tag") or "") for axis in source.get("axes", [])]
                source["axes"] = _master_axes(update["axes"], expected_tags=expected_tags)
            masters.append(source)
            if "index" in update:
                move_entity(masters, master_id, int(update["index"]))
            source_map[master_id] = source_id

            for glyph_name, glyph in glyphs.items():
                glyph_copy = dict(glyph) if isinstance(glyph, Mapping) else None
                layers = _canonical_layers(glyph, copy_values=False)
                source_layer_index = _layer_index(layers, source_id)
                source_layer = (
                    layers[source_layer_index]
                    if source_layer_index is not None
                    else None
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
                layer["id"] = master_id
                layer["masterId"] = master_id
                layer["name"] = source["name"]
                layer["isMasterLayer"] = True
                layer["isSpecialLayer"] = False
                # Glyphs owns master-layer attachment as the nested side of
                # master lifecycle. A master inserted before the end is
                # projected at the same position in every glyph's master
                # prefix; asking the layer writer to append it produces a
                # canonical target the host cannot preserve. Keep existing
                # master layers in place and insert only the new owned layer.
                master_position = find_entity_index(masters, master_id)
                if master_position is None:
                    raise ValueError(
                        "duplicated master is missing from the canonical order"
                    )
                prefix_length = _master_layer_prefix_length(layers)
                layers.insert(min(master_position, prefix_length), layer)
                glyph_copy["layers"] = layers
                glyphs[glyph_name] = glyph_copy
            if directional_kerning:
                for domain in ("ltr", "rtl", "vertical"):
                    partitions = kerning.get(domain, {})
                    if isinstance(partitions, dict) and source_id in partitions:
                        partitions[master_id] = copy.deepcopy(partitions[source_id])
                contexts = kerning.get("context", {})
                if isinstance(contexts, dict):
                    for master_values in contexts.values():
                        if (
                            isinstance(master_values, dict)
                            and source_id in master_values
                        ):
                            master_values[master_id] = copy.deepcopy(
                                master_values[source_id]
                            )
            elif source_id in kerning:
                kerning[master_id] = kerning[source_id]
            continue

        if index is None:
            raise ValueError("unknown master: {}".format(master_id))
        if action == "delete":
            if len(masters) <= 1:
                raise ValueError("the final master cannot be deleted")
            for glyph_name, glyph in glyphs.items():
                glyph_copy = dict(glyph) if isinstance(glyph, Mapping) else None
                layers = _canonical_layers(glyph, copy_values=False)
                master_layer_index = _layer_index(layers, master_id)
                if master_layer_index is None:
                    raise ValueError(
                        "glyph {} has no canonical master layer {}".format(
                            glyph_name, master_id
                        )
                    )
                for layer in layers:
                    if (
                        str(layer.get("id") or "") != master_id
                        and isinstance(layer, Mapping)
                        and str(layer.get("masterId") or "") == master_id
                        and bool(layer.get("isSpecialLayer"))
                    ):
                        raise ValueError(
                            "master {} has a dependent special layer in glyph {}".format(
                                master_id, glyph_name
                            )
                        )
                del layers[master_layer_index]
                glyph_copy["layers"] = layers
                glyphs[glyph_name] = glyph_copy
            del masters[index]
            if directional_kerning:
                for domain in ("ltr", "rtl", "vertical"):
                    partitions = kerning.get(domain, {})
                    if isinstance(partitions, dict):
                        partitions.pop(master_id, None)
                contexts = kerning.get("context", {})
                if isinstance(contexts, dict):
                    for context_key in list(contexts):
                        master_values = contexts.get(context_key)
                        if isinstance(master_values, dict):
                            master_values.pop(master_id, None)
                            if not master_values:
                                contexts.pop(context_key, None)
            else:
                kerning.pop(master_id, None)
            continue
        if action == "move":
            if "index" not in update:
                raise ValueError("master move requires index")
            move_entity(masters, master_id, int(update["index"]))
            continue
        if action != "update":
            raise ValueError("master action must be duplicate, update, move, or delete")

        item = masters[index]
        supplied = {"name", "italicAngle", "axes"}.intersection(update)
        if not supplied:
            raise ValueError("master updates require name, italicAngle, or axes")
        if "name" in supplied:
            name = str(update.get("name") or "")
            if not name:
                raise ValueError("master name cannot be empty")
            item["name"] = name
        if "italicAngle" in supplied:
            item["italicAngle"] = float(update["italicAngle"])
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
    value: Any,
    *,
    known_axis_tags: Sequence[str],
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("layer interpolation must be an object or null")
    kind = str(value.get("kind") or "").lower()
    known = set(str(tag) for tag in known_axis_tags)
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
        str(role)
        for role in layer.get("roles", ())
        if str(role) in {"smart", "color"}
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
    """Build one verified lifecycle patch for non-master layer entities."""

    after = dict(model)
    source_glyphs = model.get("glyphs", {})
    if not isinstance(source_glyphs, Mapping):
        raise ValueError("glyphs must be keyed by name")
    glyphs = dict(source_glyphs)
    after["glyphs"] = glyphs
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
        glyph_copy = dict(glyph)
        layers = _canonical_layers(glyph)
        master_prefix_length = _master_layer_prefix_length(layers)
        glyph_copy["layers"] = layers
        glyphs[glyph_name] = glyph_copy
        index = _layer_index(layers, layer_id)

        if action == "duplicate":
            if index is not None:
                raise ValueError("layer already exists: {}/{}".format(glyph_name, layer_id))
            source_id = str(update.get("sourceLayerId") or "")
            source_index = _layer_index(layers, source_id)
            if not source_id or source_index is None:
                raise ValueError("unknown source layer: {}/{}".format(glyph_name, source_id))
            source = copy.deepcopy(layers[source_index])
            source["id"] = layer_id
            source["isMasterLayer"] = False
            if "masterId" in update:
                source["masterId"] = str(update.get("masterId") or "")
            if str(source.get("masterId") or "") not in known_masters:
                raise ValueError("unknown associated master: {}".format(source.get("masterId")))
            if "name" in update:
                source["name"] = str(update.get("name") or "")
            interpolation = _normalized_interpolation(
                update.get("interpolation", source.get("interpolation")),
                known_axis_tags=known_axis_tags,
            )
            source["interpolation"] = interpolation
            source["roles"] = _project_layer_roles(source, interpolation)
            source["isSpecialLayer"] = bool(
                set(source["roles"]) & {"intermediate", "alternate", "smart"}
            )
            layers.append(source)
            if "index" in update:
                requested_index = int(update["index"])
                if requested_index < master_prefix_length:
                    raise ValueError(
                        "non-master layers cannot cross the master-layer prefix"
                    )
                move_entity(layers, layer_id, requested_index)
            source_map["{}/{}".format(glyph_name, layer_id)] = source_id
            continue

        if index is None:
            raise ValueError("unknown layer: {}/{}".format(glyph_name, layer_id))
        layer = layers[index]
        if bool(layer.get("isMasterLayer")):
            raise ValueError(
                "master layer mutations belong to apply_master_updates"
            )
        if action == "delete":
            del layers[index]
            continue
        if action == "move":
            if "index" not in update:
                raise ValueError("layer move requires index")
            requested_index = int(update["index"])
            if requested_index < master_prefix_length:
                raise ValueError(
                    "non-master layers cannot cross the master-layer prefix"
                )
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


def review_anchor_updates(model: Mapping[str, Any], updates: Sequence[Mapping[str, Any]]) -> ChangeSet:
    after = _copy_on_write_model(
        model,
        glyph_names=(str(update.get("glyphName") or "") for update in updates),
    )
    glyphs = after.setdefault("glyphs", {})
    seen = set()
    for update in updates:
        target = (str(update.get("glyphName") or ""), str(update.get("masterId") or ""), str(update.get("anchorName") or ""))
        if not all(target) or target in seen:
            raise ValueError("anchor updates require unique explicit targets")
        seen.add(target)
        glyph = glyphs.get(target[0]) if isinstance(glyphs, dict) else None
        if not isinstance(glyph, dict):
            raise ValueError("unknown glyph: {}".format(target[0]))
        layers = _canonical_layers(glyph)
        glyph["layers"] = layers
        layer_index = _layer_index(layers, target[1])
        layer = layers[layer_index] if layer_index is not None else None
        if not isinstance(layer, dict):
            raise ValueError("unknown master layer: {}".format(target[1]))
        anchors = layer.setdefault("anchors", {})
        if not isinstance(anchors, dict):
            raise ValueError("anchor model must be keyed by name")
        if bool(update.get("remove")):
            anchors.pop(target[2], None)
        else:
            anchors[target[2]] = [float(update["x"]), float(update["y"])]
    return diff_models(model, after)


def review_kerning_updates(model: Mapping[str, Any], updates: Sequence[Mapping[str, Any]]) -> ChangeSet:
    after = _copy_on_write_model(model, roots=("kerning",))
    glyphs = {
        str(glyph.get("name")): glyph
        for glyph in _items(model.get("glyphs", {}), key_name="name")
    }
    id_to_name = {
        str(glyph.get("id")): name
        for name, glyph in glyphs.items()
        if glyph.get("id")
    }

    def resolve(value: Any) -> str:
        if isinstance(value, Mapping):
            identifier = str(value.get("id") or "")
            name = str(value.get("name") or "")
            kind = str(value.get("kind") or "")
            if kind == "group" or identifier.startswith("@"):
                return identifier
            if identifier in id_to_name:
                return identifier
            if name in glyphs:
                return str(glyphs[name].get("id") or name)
            raise ValueError("unresolved kerning glyph identity: {}".format(identifier or name))
        text = str(value or "")
        if text.startswith("@"):
            return text
        if text in id_to_name:
            return text
        if text in glyphs:
            return str(glyphs[text].get("id") or text)
            raise ValueError("unresolved kerning glyph identity: {}".format(text))

    kerning = after.get("kerning", {})
    if not isinstance(kerning, dict):
        raise ValueError("kerning must be a canonical mapping")
    directional = _is_directional_kerning(kerning)
    if not directional and any(
        str(update.get("entryKind") or "pair").lower() == "context"
        for update in updates
    ):
        kerning = {
            "ltr": copy.deepcopy(kerning),
            "rtl": {},
            "vertical": {},
            "context": {},
        }
        after["kerning"] = kerning
        directional = True

    master_ids = {
        str(master.get("id") or "")
        for master in _items(model.get("masters", []))
        if master.get("id")
    }
    glyph_names = set(glyphs)
    seen: set[tuple[str, ...]] = set()
    for update in updates:
        entry_kind = str(update.get("entryKind") or "pair").lower()
        if entry_kind not in {"pair", "context"}:
            raise ValueError("kerning update entryKind must be pair or context")
        master_id = str(update.get("masterId") or "")
        if not master_id:
            raise ValueError("kerning updates require an explicit masterId")

        if entry_kind == "context":
            if master_id not in master_ids:
                raise ValueError(
                    "unknown contextual kerning master: {}".format(master_id)
                )
            raw_sequence = update.get("sequence")
            if not isinstance(raw_sequence, Sequence) or isinstance(
                raw_sequence, (str, bytes, bytearray)
            ):
                raise ValueError(
                    "context sequence must be an explicit glyph-name array"
                )
            sequence = [str(name or "") for name in raw_sequence]
            if len(sequence) < 3:
                raise ValueError("context sequences require at least three glyphs")
            invalid_names = [
                name
                for name in sequence
                if not name
                or name not in glyph_names
                or any(character in name for character in "[]*'")
                or any(character.isspace() for character in name)
            ]
            if invalid_names:
                raise ValueError(
                    "context sequences require known exact glyph names: {}".format(
                        ", ".join(invalid_names)
                    )
                )
            raw_boundary = update.get("boundaryIndex")
            if isinstance(raw_boundary, bool) or not isinstance(raw_boundary, int):
                raise ValueError("context boundaryIndex must be an integer")
            boundary_index = raw_boundary
            if not 1 <= boundary_index < len(sequence):
                raise ValueError(
                    "context boundaryIndex must identify an interior boundary"
                )
            raw_key = _context_key(sequence, boundary_index)
            target = ("context", master_id, raw_key)
            if target in seen:
                raise ValueError("kerning updates require unique explicit targets")
            seen.add(target)
            context_domain = kerning.setdefault("context", {})
            if not isinstance(context_domain, dict):
                raise ValueError(
                    "context kerning must be keyed by context sequence"
                )
            master_values = context_domain.get(raw_key, {})
            if not isinstance(master_values, Mapping):
                raise ValueError(
                    "context kerning values must be keyed by master ID"
                )
            master_values = dict(master_values)
            if update.get("value") is None:
                master_values.pop(master_id, None)
                if master_values:
                    context_domain[raw_key] = master_values
                else:
                    context_domain.pop(raw_key, None)
            else:
                value = float(update["value"])
                if not math.isfinite(value):
                    raise ValueError("context kerning values must be finite")
                master_values[master_id] = value
                context_domain[raw_key] = master_values
            continue

        direction = str(update.get("direction") or "ltr").lower()
        if direction not in _KERNING_DIRECTIONS:
            raise ValueError(
                "pair kerning direction must be ltr, rtl, or vertical"
            )
        if not directional and direction != "ltr":
            raise ValueError(
                "directional pair updates require a directional kerning model"
            )
        left = resolve(update.get("left"))
        right = resolve(update.get("right"))
        target = ("pair", direction, master_id, left, right)
        if target in seen:
            raise ValueError("kerning updates require unique explicit targets")
        seen.add(target)
        domain = kerning.setdefault(direction, {}) if directional else kerning
        if not isinstance(domain, dict):
            raise ValueError("pair kerning domain must be keyed by master ID")
        lefts = domain.get(master_id, {})
        if not isinstance(lefts, Mapping):
            raise ValueError(
                "pair kerning master partition must be keyed by left key"
            )
        lefts = copy.deepcopy(dict(lefts))
        rights = lefts.get(left, {})
        if not isinstance(rights, Mapping):
            raise ValueError(
                "pair kerning left partition must be keyed by right key"
            )
        rights = dict(rights)
        if update.get("value") is None:
            rights.pop(right, None)
            if rights:
                lefts[left] = rights
            else:
                lefts.pop(left, None)
            if lefts:
                domain[master_id] = lefts
            else:
                domain.pop(master_id, None)
        else:
            value = float(update["value"])
            if not math.isfinite(value):
                raise ValueError("pair kerning values must be finite")
            rights[right] = value
            lefts[left] = rights
            domain[master_id] = lefts
    return diff_models(model, after)


def review_metrics_updates(model: Mapping[str, Any], updates: Sequence[Mapping[str, Any]]) -> ChangeSet:
    after = _copy_on_write_model(
        model,
        glyph_names=(str(update.get("glyphName") or "") for update in updates),
    )
    glyphs = after.setdefault("glyphs", {})
    allowed = {"leftMetricsKey", "rightMetricsKey", "widthMetricsKey"}
    seen = set()
    for update in updates:
        if "masterId" in update:
            raise ValueError("masterId is not part of the v2 metrics update contract")
        scope = str(update.get("scope") or "")
        glyph_name = str(update.get("glyphName") or "")
        layer_id = str(update.get("layerId") or "")
        if scope not in {"glyph", "layer"} or not glyph_name:
            raise ValueError("metrics updates require explicit glyph or layer scope")
        if scope == "glyph" and "layerId" in update:
            raise ValueError("glyph-scoped metrics updates cannot include layerId")
        if scope == "layer" and not layer_id:
            raise ValueError("layer-scoped metrics updates require layerId")
        target = (scope, glyph_name, layer_id if scope == "layer" else "")
        if target in seen:
            raise ValueError("metrics updates require unique explicit targets")
        seen.add(target)
        glyph = glyphs.get(glyph_name) if isinstance(glyphs, dict) else None
        if not isinstance(glyph, dict):
            raise ValueError("unknown metrics glyph target: {}".format(glyph_name))
        supplied = allowed.intersection(update)
        if not supplied:
            raise ValueError("metrics updates require at least one inheritance key")
        if scope == "glyph":
            for field in supplied:
                value = update.get(field)
                glyph[field] = str(value) if value is not None else None
            continue
        layers = _canonical_layers(glyph) if isinstance(glyph, dict) else []
        if isinstance(glyph, dict):
            glyph["layers"] = layers
        layer_index = _layer_index(layers, layer_id)
        layer = layers[layer_index] if layer_index is not None else None
        if not isinstance(layer, dict):
            raise ValueError(
                "unknown metrics layer target: {}/{}".format(glyph_name, layer_id)
            )
        for field in supplied:
            value = update.get(field)
            layer[field] = str(value) if value is not None else None
    return diff_models(model, after)


def review_compatibility_updates(model: Mapping[str, Any], updates: Sequence[Mapping[str, Any]]) -> ChangeSet:
    after = _copy_on_write_model(
        model,
        glyph_names=(str(update.get("glyphName") or "") for update in updates),
    )
    glyphs = after.setdefault("glyphs", {})
    seen = set()
    for update in updates:
        target = (str(update.get("glyphName") or ""), str(update.get("masterId") or ""))
        if not all(target) or target in seen:
            raise ValueError("compatibility updates require unique explicit glyph/master targets")
        seen.add(target)
        glyph = glyphs.get(target[0]) if isinstance(glyphs, dict) else None
        layers = _canonical_layers(glyph) if isinstance(glyph, dict) else []
        if isinstance(glyph, dict):
            glyph["layers"] = layers
        layer_index = _layer_index(layers, target[1])
        layer = layers[layer_index] if layer_index is not None else None
        if not isinstance(layer, dict):
            raise ValueError("unknown compatibility target: {}/{}".format(*target))
        supplied = {"paths", "components"}.intersection(update)
        if not supplied:
            raise ValueError("compatibility updates require reviewed paths or components")
        for field in supplied:
            value = update.get(field)
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
                raise ValueError("{} must be an explicit sequence".format(field))
            kind = "path" if field == "paths" else "component"
            layer["shapes"] = replace_shape_kind(
                layer,
                kind,
                copy.deepcopy(list(value)),
            )
    return diff_models(model, after)


__all__ = [
    "build_layer_updates",
    "build_master_updates",
    "build_opentype_updates",
    "list_glyphs",
    "list_instances",
    "list_layers",
    "list_masters",
    "list_opentype_items",
    "list_kerning_pairs",
    "review_anchor_consistency",
    "review_anchor_updates",
    "review_export",
    "review_glyph_updates",
    "review_kerning_coverage",
    "review_kerning_updates",
    "review_metrics_updates",
    "review_compatibility_updates",
    "review_master_compatibility",
    "review_metrics_inheritance",
    "simulate_spacing",
]
