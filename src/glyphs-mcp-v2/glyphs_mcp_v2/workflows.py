"""Detached, deterministic production reviews for Glyphs MCP 2.0."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Iterable, Mapping, Optional, Sequence

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


def review_glyph_updates(model: Mapping[str, Any], updates: Sequence[Mapping[str, Any]]) -> ChangeSet:
    after = copy.deepcopy(dict(model))
    glyphs = after.setdefault("glyphs", {})
    if not isinstance(glyphs, dict):
        raise ValueError("glyph model must be keyed by name for batch updates")
    seen = set()
    allowed = {"category", "subCategory", "unicode", "export", "leftKerningGroup", "rightKerningGroup"}
    for update in updates:
        name = str(update.get("glyphName") or "")
        if not name or name in seen:
            raise ValueError("glyph updates require unique explicit glyph names")
        seen.add(name)
        if name not in glyphs or not isinstance(glyphs[name], dict):
            raise ValueError("unknown glyph: {}".format(name))
        for key, value in update.items():
            if key in allowed:
                glyphs[name][key] = copy.deepcopy(value)
    return diff_models(model, after)


def build_opentype_updates(
    model: Mapping[str, Any], updates: Sequence[Mapping[str, Any]]
) -> ChangeSet:
    """Update existing feature, class, and prefix code through one contract."""

    after = copy.deepcopy(dict(model))
    roots = {
        "feature": "features",
        "class": "classes",
        "prefix": "featurePrefixes",
    }
    allowed = {"code", "automatic", "disabled"}
    seen: set[tuple[str, str]] = set()
    for update in updates:
        kind = str(update.get("kind") or "")
        root = roots.get(kind)
        name = str(update.get("name") or "")
        target = (kind, name)
        if root is None:
            raise ValueError("OpenType update kind must be feature, class, or prefix")
        if not name or target in seen:
            raise ValueError("OpenType updates require unique existing kind/name targets")
        seen.add(target)
        collection = after.get(root)
        if not isinstance(collection, list):
            raise ValueError("{} must be an ordered canonical collection".format(root))
        matches = [
            item
            for item in collection
            if isinstance(item, dict)
            and name in {str(item.get("id") or ""), str(item.get("name") or "")}
        ]
        if len(matches) != 1:
            raise ValueError("unknown or ambiguous OpenType target: {}/{}".format(kind, name))
        item = matches[0]
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
        layers = glyph.setdefault("layers", {})
        layer = layers.get(target[1]) if isinstance(layers, dict) else None
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
        layers = glyph.get("layers") if isinstance(glyph, dict) else None
        layer = layers.get(target[1]) if isinstance(layers, dict) else None
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
        layers = glyph.get("layers") if isinstance(glyph, dict) else None
        layer = layers.get(target[1]) if isinstance(layers, dict) else None
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
    "build_opentype_updates",
    "list_glyphs",
    "list_instances",
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
