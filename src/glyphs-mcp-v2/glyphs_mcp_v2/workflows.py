"""Detached, deterministic production reviews for Glyphs MCP 2.0."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Iterable, Mapping, Optional, Sequence

from .canonical_collections import (
    canonical_glyph_id,
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
from .semantic import ChangeSet, diff_models


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
    """Return the schema-v5 ordered layer entities for one glyph.

    A mapping is accepted only as a local schema-v4 migration fixture. Native
    capture and every schema-v5 builder return the ordered list form.
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
    # that semantic lookup while schema v5 addresses lifecycle by layer ID.
    matches = [
        offset
        for offset, layer in enumerate(layers)
        if bool(layer.get("isMasterLayer"))
        and str(layer.get("masterId") or "") == identity
    ]
    return matches[0] if len(matches) == 1 else None


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


def list_layers(
    model: Mapping[str, Any],
    *,
    glyph_names: Optional[Sequence[str]] = None,
    roles: Optional[Sequence[str]] = None,
) -> list[dict[str, Any]]:
    """Return ordered layer identities and reviewable lifecycle metadata."""

    requested_glyphs = {str(name) for name in glyph_names or () if str(name)}
    requested_roles = {str(role).lower() for role in roles or () if str(role)}
    known_roles = {"master", "intermediate", "alternate", "backup", "smart", "color"}
    unknown = requested_roles - known_roles
    if unknown:
        raise ValueError("unsupported layer roles: {}".format(", ".join(sorted(unknown))))
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
            result.append(
                {
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
                    "pathCount": len(layer.get("paths") or ()),
                    "componentCount": len(layer.get("components") or ()),
                    "anchorCount": len(layer.get("anchors") or {}),
                }
            )
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


def list_kerning_pairs(model: Mapping[str, Any]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    glyphs = _items(model.get("glyphs", {}), key_name="name")
    id_to_name = {
        str(glyph.get("id")): str(glyph.get("name"))
        for glyph in glyphs
        if glyph.get("id") and glyph.get("name")
    }
    source = model.get("kerning", [])
    if isinstance(source, Mapping):
        for master_id, lefts in source.items():
            if not isinstance(lefts, Mapping):
                continue
            for left, rights in lefts.items():
                if not isinstance(rights, Mapping):
                    continue
                for right, value in rights.items():
                    pairs.append(
                        {
                            "masterId": str(master_id),
                            "left": _kerning_key(left, id_to_name),
                            "right": _kerning_key(right, id_to_name),
                            "value": value,
                            "provenance": "source",
                        }
                    )
    else:
        for pair in _items(source):
            pairs.append(
                {
                    "masterId": str(pair.get("masterId") or ""),
                    "left": _kerning_key(pair.get("left"), id_to_name),
                    "right": _kerning_key(pair.get("right"), id_to_name),
                    "value": pair.get("value"),
                    "provenance": pair.get("provenance") or "source",
                }
            )
    pairs.sort(key=lambda pair: (pair["masterId"], pair["left"]["id"], pair["right"]["id"]))
    return pairs


def _layer_map(glyph: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    layers = glyph.get("layers", {})
    if isinstance(layers, Mapping):
        return {str(key): value for key, value in layers.items() if isinstance(value, Mapping)}
    result = {}
    for layer in _items(layers):
        key = str(layer.get("masterId") or layer.get("id") or "")
        if key:
            result[key] = layer
    return result


def _component_names(layer: Mapping[str, Any]) -> list[str]:
    values = layer.get("components", [])
    result = []
    for component in values if isinstance(values, Sequence) else []:
        if isinstance(component, Mapping):
            result.append(str(component.get("name") or component.get("componentName") or ""))
        else:
            result.append(str(component))
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
        layers = _layer_map(glyph)
        for layer_id, layer in sorted(layers.items()):
            if bool(layer.get("isSpecialLayer")):
                special_layer_count += 1
                findings.append(
                    _finding(
                        "special_layer_present",
                        "soft",
                        "A special layer participates in compatibility and export review.",
                        {"glyphName": name, "layerId": layer.get("id") or layer_id},
                    )
                )
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
            if layer.get("pathSignature") != reference.get("pathSignature"):
                findings.append(
                    _finding(
                        "path_topology_mismatch",
                        "hard",
                        "Path topology differs between masters.",
                        {"glyphName": name, "referenceMasterId": reference_id, "masterId": master_id},
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


def review_metrics_inheritance(model: Mapping[str, Any]) -> dict[str, Any]:
    glyphs = {str(item.get("name")): item for item in _items(model.get("glyphs", {}), key_name="name")}
    findings: list[dict[str, Any]] = []
    keys = ("leftMetricsKey", "rightMetricsKey", "widthMetricsKey")
    for name, glyph in sorted(glyphs.items()):
        for master_id, layer in sorted(_layer_map(glyph).items()):
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
            if components and any(layer.get(key) for key in keys):
                findings.append(
                    _finding(
                        "component_metrics_override",
                        "soft",
                        "A component layer also defines explicit metrics inheritance.",
                        {"glyphName": name, "masterId": master_id},
                    )
                )
    return {
        "reviewedGlyphCount": len(glyphs),
        "findings": findings,
        "hasHardFailures": any(item["severity"] == "hard" for item in findings),
    }


def _anchor_names(layer: Mapping[str, Any]) -> list[str]:
    anchors = layer.get("anchors", {})
    if isinstance(anchors, Mapping):
        return [str(name) for name in anchors]
    return [str(anchor.get("name") or "") for anchor in _items(anchors, key_name="name")]


def review_anchor_consistency(model: Mapping[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    glyphs = _items(model.get("glyphs", {}), key_name="name")
    for glyph in glyphs:
        name = str(glyph.get("name") or "")
        layers = _layer_map(glyph)
        if not layers:
            continue
        reference_id = sorted(layers)[0]
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
    modes = {"proof_families", "class_representatives", "class_cross_product", "glyph_expansion"}
    if mode not in modes:
        raise ValueError("unsupported kerning coverage mode")
    pairs = list_kerning_pairs(model)
    eligible = len(pairs) if eligible_count is None else max(0, int(eligible_count))
    measured = 0 if measured_count is None else max(0, int(measured_count))
    measured = min(eligible, measured)
    skipped = max(0, int(skipped_count))
    untested = max(0, eligible - measured - skipped)
    return {
        "mode": mode,
        "eligibleCount": eligible,
        "measuredCount": measured,
        "skippedCount": skipped,
        "untestedCount": untested,
        "complete": untested == 0,
        "accountingComplete": eligible == measured + skipped + untested,
    }


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

    after = copy.deepcopy(dict(model))
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

    after = copy.deepcopy(dict(model))
    roots = {
        "feature": "features",
        "class": "classes",
        "prefix": "featurePrefixes",
    }
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

    after = copy.deepcopy(dict(model))
    collection = after.setdefault("instances", [])
    if not isinstance(collection, list):
        raise ValueError("instances must be an ordered canonical collection")
    require_indexed_entities(collection, "instances")
    seen: set[tuple[str, str]] = set()
    writable = {"name", "type", "included", "axes"}
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
            collection.append(
                {
                    "id": identity,
                    "name": str(update.get("name")),
                    "type": kind,
                    "included": bool(update.get("included", True)),
                    "inclusionReason": None,
                    "interpolationSupported": kind != "variable",
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
        if "type" in supplied:
            kind = str(update.get("type") or "").lower()
            if kind not in {"static", "variable"}:
                raise ValueError("instance type must be static or variable")
            item["type"] = kind
            item["interpolationSupported"] = kind != "variable"
        if "included" in supplied:
            item["included"] = bool(update.get("included"))
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
    kerning = dict(source_kerning)
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
                layers.append(layer)
                glyph_copy["layers"] = layers
                glyphs[glyph_name] = glyph_copy
            if source_id in kerning:
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
                move_entity(layers, layer_id, int(update["index"]))
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
            move_entity(layers, layer_id, int(update["index"]))
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
    after = copy.deepcopy(dict(model))
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
    after = copy.deepcopy(dict(model))
    pairs = list_kerning_pairs(after)
    keyed = {(pair["masterId"], pair["left"]["id"], pair["right"]["id"]): pair for pair in pairs}
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

    seen = set()
    for update in updates:
        target = (
            str(update.get("masterId") or ""),
            resolve(update.get("left")),
            resolve(update.get("right")),
        )
        if not all(target) or target in seen:
            raise ValueError("kerning updates require unique explicit targets")
        seen.add(target)
        if update.get("value") is None:
            keyed.pop(target, None)
        else:
            keyed[target] = {
                "masterId": target[0],
                "left": _kerning_key(target[1], id_to_name),
                "right": _kerning_key(target[2], id_to_name),
                "value": float(update["value"]),
                "provenance": "reviewed_update",
            }
    nested: dict[str, dict[str, dict[str, float]]] = {}
    for master_id, left, right in sorted(keyed):
        value = keyed[(master_id, left, right)].get("value")
        nested.setdefault(master_id, {}).setdefault(left, {})[right] = float(value)
    after["kerning"] = nested
    return diff_models(model, after)


def review_metrics_updates(model: Mapping[str, Any], updates: Sequence[Mapping[str, Any]]) -> ChangeSet:
    after = copy.deepcopy(dict(model))
    glyphs = after.setdefault("glyphs", {})
    allowed = {"leftMetricsKey", "rightMetricsKey", "widthMetricsKey"}
    seen = set()
    for update in updates:
        target = (str(update.get("glyphName") or ""), str(update.get("masterId") or ""))
        if not all(target) or target in seen:
            raise ValueError("metrics updates require unique explicit glyph/master targets")
        seen.add(target)
        glyph = glyphs.get(target[0]) if isinstance(glyphs, dict) else None
        layers = _canonical_layers(glyph) if isinstance(glyph, dict) else []
        if isinstance(glyph, dict):
            glyph["layers"] = layers
        layer_index = _layer_index(layers, target[1])
        layer = layers[layer_index] if layer_index is not None else None
        if not isinstance(layer, dict):
            raise ValueError("unknown metrics target: {}/{}".format(*target))
        supplied = allowed.intersection(update)
        if not supplied:
            raise ValueError("metrics updates require at least one inheritance key")
        for field in supplied:
            value = update.get(field)
            layer[field] = str(value) if value is not None else None
    return diff_models(model, after)


def review_compatibility_updates(model: Mapping[str, Any], updates: Sequence[Mapping[str, Any]]) -> ChangeSet:
    after = copy.deepcopy(dict(model))
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
            layer[field] = copy.deepcopy(list(value))
        if "paths" in supplied:
            layer["pathSignature"] = [
                len(path.get("nodes", [])) if isinstance(path, Mapping) else 0
                for path in layer["paths"]
            ]
    return diff_models(model, after)


__all__ = [
    "build_layer_updates",
    "build_master_updates",
    "build_opentype_updates",
    "list_glyphs",
    "list_instances",
    "list_layers",
    "list_masters",
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
