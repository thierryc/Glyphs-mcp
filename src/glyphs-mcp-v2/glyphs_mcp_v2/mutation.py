"""Detached planning for verified apply-first document mutations."""

from __future__ import annotations

import copy
import inspect
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol, Sequence

from .canonical_tree import CanonicalSnapshot
from .canonical_schema import (
    CANONICAL_FONT_SCALAR_FIELDS,
    CANONICAL_SCHEMA,
    CanonicalCoverage,
    FieldRole,
)
from .canonical_views import layer_components
from .canonical_collections import (
    identity_order_change_required,
    indexed_entities,
    is_identity_collection_path,
)
from .semantic import (
    ChangeSet,
    SemanticChange,
    complete_models_equal,
    diff_models,
    fingerprint_model,
    rebase_canonical_model,
    semantic_value_at,
    subset_change_set,
)


_FONT_WRITABLE = frozenset(CANONICAL_FONT_SCALAR_FIELDS)
_GLYPH_WRITABLE = (
    frozenset(
        CANONICAL_SCHEMA.canonical_fields_for(
            "definition.glyph", roles=(FieldRole.WRITABLE,)
        )
    )
    # Glyph membership and layer lifecycle have their own capability owners;
    # a glyph rename remains conservative delete/add rather than a scalar edit.
    - {"name", "layers"}
    # The live API exposes both a primary ``unicode`` and its complete list.
    # Official v4 serializes the list through the same field, so this adapter
    # spelling intentionally supplements the registry-derived set.
    | {"unicodes"}
)
_LAYER_WRITABLE = frozenset(
    {
        "width",
        "leftMetricsKey",
        "rightMetricsKey",
        "widthMetricsKey",
        "bottomMetricsKey",
        "topMetricsKey",
        "vertOriginMetricsKey",
        "vertWidthMetricsKey",
        "vertOrigin",
        "vertWidth",
        "active",
        "visible",
        "color",
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
    }
)
_OPENTYPE_ROOTS = frozenset({"features", "classes", "featurePrefixes"})
_OPENTYPE_WRITABLE = frozenset().union(
    *(
        CANONICAL_SCHEMA.fields_for(source, roles=(FieldRole.WRITABLE,))
        for source in (
            "definition.feature",
            "definition.class",
            "definition.featurePrefix",
        )
    )
)
_INSTANCE_WRITABLE = frozenset({"name", "type", "included", "axes"})
MASTER_LIFECYCLE_CAPABILITY = "master_lifecycle"
LAYER_LIFECYCLE_CAPABILITY = "layer_lifecycle"
CANONICAL_LIFECYCLE_CAPABILITY = "canonical_lifecycle"
_CANONICAL_ROOT_COLLECTIONS = frozenset({"axes", "metrics", "stems", "numbers"})
SCOPED_NATIVE_VERIFICATION = "scoped_native"
COMPLETE_NATIVE_VERIFICATION = "complete_native"


def _layer_entities(glyph: Any) -> tuple[list[str], dict[str, Mapping[str, Any]]]:
    layers = glyph.get("layers", ()) if isinstance(glyph, Mapping) else ()
    indexed = indexed_entities(layers)
    if indexed is None:
        # Schema-v4 models are accepted only as an internal migration input;
        # every current native capture and public operation emits a list.
        if isinstance(layers, Mapping):
            order = [str(key) for key in layers]
            entities = {
                str(key): value
                for key, value in layers.items()
                if isinstance(value, Mapping)
            }
            return order, entities
    if indexed is None:
        return [], {}
    return indexed


@dataclass(frozen=True)
class MutationBuild:
    """Pure semantic patch plus bounded native replay information.

    Most mutations need only a :class:`ChangeSet`. Structural duplication is
    the exception: the canonical target says *what* the document must become,
    while ``execution_context`` identifies the native object that must be
    copied so Glyphs-only state is preserved. The context is process-local,
    never enters the canonical tree, audit ledger, or public response.
    """

    change_set: ChangeSet
    capabilities: tuple[str, ...] = ()
    execution_context: Mapping[str, Any] = field(default_factory=dict)
    result_context: Optional["MutationResultContext"] = None
    audit_details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MutationResultContext:
    """Bounded tool-specific evidence attached to a verified mutation.

    The result never enters the canonical tree or native replay context. The
    application stores the complete item list in the process-local operation
    store and returns only its first page with the common mutation envelope.
    """

    kind: str
    data_key: str
    item_key: str
    result: Mapping[str, Any]
    page_size: int = 100


class MutationRejected(ValueError):
    """Fail a detached mutation plan before any native transaction starts."""

    def __init__(
        self,
        *,
        code: str,
        summary: str,
        message: str,
        result_context: Optional[MutationResultContext] = None,
        audit_details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = str(code)
        self.summary = str(summary)
        self.message = str(message)
        self.result_context = result_context
        self.audit_details = dict(audit_details or {})


def normalize_mutation_build(value: ChangeSet | MutationBuild) -> MutationBuild:
    if isinstance(value, MutationBuild):
        return value
    if isinstance(value, ChangeSet):
        return MutationBuild(value)
    raise TypeError("mutation builders must return ChangeSet or MutationBuild")


def master_lifecycle_diff(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> ChangeSet:
    """Diff master-owned structures as independently reversible entities."""

    after = rebase_canonical_model(before, after)
    changes = diff_models(before, after)
    before_ids = {
        str(master.get("id") or "")
        for master in before.get("masters", [])
        if isinstance(master, Mapping)
    }
    after_ids = {
        str(master.get("id") or "")
        for master in after.get("masters", [])
        if isinstance(master, Mapping)
    }
    added_ids = after_ids - before_ids
    if not added_ids:
        return changes
    retained = [
        change
        for change in changes.changes
        if not (
            len(change.path) >= 2
            and change.path[0] == "kerning"
            and (
                (len(change.path) >= 3 and change.path[2] in added_ids)
                or (
                    len(change.path) >= 4
                    and change.path[1] == "context"
                    and change.path[3] in added_ids
                )
                or (len(change.path) == 2 and change.path[1] in added_ids)
            )
        )
    ]
    after_kerning = after.get("kerning", {})
    if isinstance(after_kerning, Mapping):
        directional = any(
            domain in after_kerning for domain in ("ltr", "rtl", "vertical", "context")
        )
        domains = ("ltr", "rtl", "vertical") if directional else (None,)
        for domain in domains:
            values = after_kerning.get(domain, {}) if domain else after_kerning
            if not isinstance(values, Mapping):
                continue
            for master_id in sorted(added_ids & set(values)):
                retained.append(
                    SemanticChange(
                        path=("kerning", domain, master_id) if domain else ("kerning", master_id),
                        after=values[master_id],
                        before_present=False,
                    )
                )
        if directional:
            contexts = after_kerning.get("context", {})
            if isinstance(contexts, Mapping):
                for context_key, master_values in contexts.items():
                    if not isinstance(master_values, Mapping):
                        continue
                    for master_id in sorted(added_ids & set(master_values)):
                        retained.append(
                            SemanticChange(
                                path=(
                                    "kerning",
                                    "context",
                                    str(context_key),
                                    master_id,
                                ),
                                after=master_values[master_id],
                                before_present=False,
                            )
                        )
    result = ChangeSet.from_changes(
        before_fingerprint=fingerprint_model(before),
        after_fingerprint=fingerprint_model(after),
        changes=retained,
    )
    result.apply(before)
    return result


def master_lifecycle_request_diff(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> ChangeSet:
    """Build the bounded writable master request without diffing every glyph."""

    after = rebase_canonical_model(before, after)
    before_masters = before.get("masters", [])
    after_masters = after.get("masters", [])
    master_changes = diff_models(
        {"masters": before_masters},
        {"masters": after_masters},
    ).changes
    before_ids = {
        str(master.get("id") or "")
        for master in before_masters
        if isinstance(master, Mapping)
    }
    after_ids = {
        str(master.get("id") or "")
        for master in after_masters
        if isinstance(master, Mapping)
    }
    structural_ids = before_ids ^ after_ids
    changes: list[SemanticChange] = list(master_changes)
    before_glyphs = before.get("glyphs", {})
    after_glyphs = after.get("glyphs", {})
    if not isinstance(before_glyphs, Mapping) or not isinstance(
        after_glyphs, Mapping
    ):
        raise ValueError("master lifecycle requires canonical glyph mappings")
    for glyph_name in sorted(set(before_glyphs) | set(after_glyphs)):
        before_glyph = before_glyphs.get(glyph_name, {})
        after_glyph = after_glyphs.get(glyph_name, {})
        before_order, before_layers = _layer_entities(before_glyph)
        after_order, after_layers = _layer_entities(after_glyph)
        for master_id in sorted(structural_ids):
            before_present = master_id in before_layers
            after_present = master_id in after_layers
            if before_present == after_present:
                continue
            changes.append(
                SemanticChange(
                    path=("glyphs", str(glyph_name), "layers", master_id),
                    before=before_layers.get(master_id),
                    after=after_layers.get(master_id),
                    before_present=before_present,
                    after_present=after_present,
                )
            )
        if identity_order_change_required(before_order, after_order):
            changes.append(
                SemanticChange(
                    path=("glyphs", str(glyph_name), "layers", "$order"),
                    before=before_order,
                    after=after_order,
                )
            )

    before_kerning = before.get("kerning", {})
    after_kerning = after.get("kerning", {})
    if isinstance(before_kerning, Mapping) and isinstance(after_kerning, Mapping):
        directional = any(
            domain in before_kerning or domain in after_kerning
            for domain in ("ltr", "rtl", "vertical", "context")
        )
        domains = ("ltr", "rtl", "vertical") if directional else (None,)
        for domain in domains:
            before_domain = before_kerning.get(domain, {}) if domain else before_kerning
            after_domain = after_kerning.get(domain, {}) if domain else after_kerning
            if not isinstance(before_domain, Mapping) or not isinstance(after_domain, Mapping):
                continue
            for master_id in sorted(structural_ids):
                before_present = master_id in before_domain
                after_present = master_id in after_domain
                if before_present == after_present:
                    continue
                changes.append(
                    SemanticChange(
                        path=("kerning", domain, master_id) if domain else ("kerning", master_id),
                        before=before_domain.get(master_id),
                        after=after_domain.get(master_id),
                        before_present=before_present,
                        after_present=after_present,
                    )
                )
        if directional:
            before_contexts = before_kerning.get("context", {})
            after_contexts = after_kerning.get("context", {})
            if isinstance(before_contexts, Mapping) and isinstance(
                after_contexts, Mapping
            ):
                for context_key in sorted(
                    set(before_contexts) | set(after_contexts), key=str
                ):
                    before_values = before_contexts.get(context_key)
                    after_values = after_contexts.get(context_key)
                    before_mapping = (
                        before_values if isinstance(before_values, Mapping) else {}
                    )
                    after_mapping = (
                        after_values if isinstance(after_values, Mapping) else {}
                    )
                    if context_key not in before_contexts:
                        changes.append(
                            SemanticChange(
                                path=("kerning", "context", str(context_key)),
                                after=after_values,
                                before_present=False,
                            )
                        )
                        continue
                    if context_key not in after_contexts:
                        changes.append(
                            SemanticChange(
                                path=("kerning", "context", str(context_key)),
                                before=before_values,
                                after_present=False,
                            )
                        )
                        continue
                    for master_id in sorted(structural_ids):
                        before_present = master_id in before_mapping
                        after_present = master_id in after_mapping
                        if before_present == after_present:
                            continue
                        changes.append(
                            SemanticChange(
                                path=(
                                    "kerning",
                                    "context",
                                    str(context_key),
                                    master_id,
                                ),
                                before=before_mapping.get(master_id),
                                after=after_mapping.get(master_id),
                                before_present=before_present,
                                after_present=after_present,
                            )
                        )
    result = ChangeSet.from_changes(
        before_fingerprint=fingerprint_model(before),
        after_fingerprint=fingerprint_model(after),
        changes=changes,
    )
    result.apply(before)
    return result


def classify_change_path(path: tuple[str, ...]) -> str:
    if not path:
        return "unsupported"
    if path[0] == "font" and len(path) == 2 and path[1] in _FONT_WRITABLE:
        return "writable"
    if path[0] == "font" and len(path) >= 2 and path[1] in {
        "customParameters", "properties", "userData"
    }:
        return "writable"
    if path[0] in _CANONICAL_ROOT_COLLECTIONS:
        return "writable"
    if path[0] in {"glyphOrder", "settings"}:
        return "writable"
    if path[0] == "kerning":
        return "writable"
    if (
        path[0] in _OPENTYPE_ROOTS
        and (
            len(path) == 2
            or (len(path) >= 3 and path[2] in _OPENTYPE_WRITABLE)
        )
    ):
        return "writable"
    if path[0] == "instances":
        if len(path) == 2:
            return "writable"
        if len(path) >= 3 and path[2] in _INSTANCE_WRITABLE | {
            "exports", "visible", "isBold", "isItalic", "linkStyle",
            "manualInterpolation", "weightClass", "widthClass",
            "instanceInterpolations", "customParameters", "properties", "userData",
        }:
            return "writable"
        if len(path) == 3 and path[2] in {
            "inclusionReason",
            "interpolationSupported",
        }:
            return "derived"
    if path[0] == "glyphs" and len(path) >= 3:
        if len(path) == 3 and path[2] == "mastersCompatible":
            return "derived"
        if len(path) == 3 and path[2] in _GLYPH_WRITABLE:
            return "writable"
        if len(path) >= 5 and path[2] == "layers":
            # Sidebearings are host projections of authoritative outline,
            # width, metrics-key, and master state. Their native setters are
            # mutation commands because they move geometry or resize width;
            # the projected getter values are not independently replayable
            # canonical leaves.
            if path[4] in {"LSB", "RSB"}:
                return "derived"
            if path[4] in _LAYER_WRITABLE:
                return "writable"
    if path[0] == "glyphs" and len(path) == 2:
        return "writable"
    return "unsupported"


def is_structural_change_path(path: tuple[str, ...]) -> bool:
    """Return whether a patch changes canonical collection membership/order."""

    if len(path) == 2 and path[0] == "glyphs":
        return True
    collection = path[:-1]
    return bool(path) and is_identity_collection_path(collection)


def _master_structural_ids(change_set: ChangeSet) -> frozenset[str]:
    return frozenset(
        change.path[1]
        for change in change_set.changes
        if len(change.path) == 2
        and change.path[0] == "masters"
        and change.path[1] != "$order"
        and change.before_present != change.after_present
    )


def master_owns_layer_order_change(change: Any, change_set: ChangeSet) -> bool:
    """Return whether master lifecycle completely explains one layer order.

    Master add/delete owns the corresponding master-layer membership in every
    glyph, including the position projected from the master collection. It
    does not grant permission to reorder any retained layer. Glyphs permits a
    glyph to lack retained master layers, so proof is local to the affected
    layer collection: the structural identities must have matching membership
    changes and every retained layer must keep its exact relative order.
    """

    path = tuple(str(part) for part in getattr(change, "path", ()))
    structural_ids = _master_structural_ids(change_set)
    if (
        len(path) != 4
        or path[0] != "glyphs"
        or path[2:] != ("layers", "$order")
        or not structural_ids
        or not getattr(change, "before_present", False)
        or not getattr(change, "after_present", False)
    ):
        return False
    def identities(value: Any) -> list[str] | None:
        if not isinstance(value, (list, tuple)):
            return None
        result = [str(identity) for identity in value]
        if not all(result) or len(result) != len(set(result)):
            return None
        return result

    layer_before = identities(change.before)
    layer_after = identities(change.after)
    if layer_before is None or layer_after is None:
        return False
    assert layer_before is not None
    assert layer_after is not None
    if set(layer_before) ^ set(layer_after) != set(structural_ids):
        return False
    glyph_name = path[1]
    for identity in structural_ids:
        master_change = next(
            (
                candidate
                for candidate in change_set.changes
                if candidate.path == ("masters", identity)
            ),
            None,
        )
        layer_change = next(
            (
                candidate
                for candidate in change_set.changes
                if candidate.path
                == ("glyphs", glyph_name, "layers", identity)
            ),
            None,
        )
        if (
            master_change is None
            or layer_change is None
            or master_change.before_present != layer_change.before_present
            or master_change.after_present != layer_change.after_present
        ):
            return False
    retained = (set(layer_before) | set(layer_after)) - set(structural_ids)
    if [identity for identity in layer_before if identity in retained] != [
        identity for identity in layer_after if identity in retained
    ]:
        return False

    master_order_change = next(
        (
            candidate
            for candidate in change_set.changes
            if candidate.path == ("masters", "$order")
            and candidate.after_present
        ),
        None,
    )
    added = {
        identity
        for identity in structural_ids
        if any(
            candidate.path == ("masters", identity)
            and not candidate.before_present
            and candidate.after_present
            for candidate in change_set.changes
        )
    }
    removed = set(structural_ids) - added
    expected = [identity for identity in layer_before if identity not in removed]
    if added:
        # An insertion index is owned by the font master order. When the
        # semantic diff contains no master order evidence we cannot prove
        # where a newly owned layer belongs, so fail closed instead of
        # accepting an arbitrary local reorder.
        if master_order_change is None:
            return False
        master_before = identities(master_order_change.before)
        master_after = identities(master_order_change.after)
        if master_before is None or master_after is None:
            return False
        master_ids = set(master_before) | set(master_after)
        for identity in master_after:
            if identity not in added:
                continue
            prefix_length = 0
            for current in expected:
                if current not in master_ids:
                    break
                prefix_length += 1
            expected.insert(
                min(master_after.index(identity), prefix_length), identity
            )
    return expected == layer_after


def _change_classification(
    change: Any,
    change_set: ChangeSet,
    capabilities: Sequence[str],
) -> str:
    classification = classify_change_path(change.path)
    if classification != "unsupported":
        return classification
    if LAYER_LIFECYCLE_CAPABILITY in capabilities:
        path = change.path
        if (
            len(path) >= 4
            and path[0] == "glyphs"
            and path[2] == "layers"
        ):
            if len(path) == 4 or path[3] == "$order":
                return "writable"
            if len(path) >= 5 and path[4] in {
                "name",
                "masterId",
                "interpolation",
                "roles",
                "isSpecialLayer",
            }:
                return "writable" if path[4] in {"name", "masterId", "interpolation"} else "derived"
    if CANONICAL_LIFECYCLE_CAPABILITY in capabilities and path[0] in {
        "axes", "metrics", "stems", "numbers", "glyphOrder", "settings"
    }:
        return "writable"
    if MASTER_LIFECYCLE_CAPABILITY not in capabilities:
        return classification
    structural_ids = _master_structural_ids(change_set)
    path = change.path
    if path[0] == "masters":
        if len(path) == 2:
            return "writable"
        if len(path) >= 3 and path[2] in {
            "name", "italicAngle", "axes", "active", "visible", "iconName",
            "customParameters", "properties", "guides", "metricValues",
            "stemValues", "numberValues", "userData",
        }:
            return "writable"
    if (
        len(path) >= 4
        and path[0] == "glyphs"
        and path[2] == "layers"
        and path[3] in structural_ids
    ):
        # Master-layer membership and its complete canonical payload are one
        # consequence of adding/removing the owning master. They are not a
        # general layer-mutation permission.
        return "writable"
    if master_owns_layer_order_change(change, change_set):
        return "writable"
    return classification


def writable_subset(
    before: Mapping[str, Any],
    observed: ChangeSet,
    *,
    capabilities: Sequence[str] = (),
) -> ChangeSet:
    return subset_change_set(
        before,
        observed,
        lambda change: _change_classification(change, observed, capabilities)
        == "writable",
    )


def unsupported_change_diagnostics(
    changes: ChangeSet,
    *,
    limit: int = 100,
    capabilities: Sequence[str] = (),
) -> dict[str, Any]:
    paths = [
        change.path
        for change in changes.changes
        if _change_classification(change, changes, capabilities) == "unsupported"
    ]
    roots: list[str] = []
    for path in paths:
        if path and path[0] not in roots:
            roots.append(path[0])
    bounded_limit = max(0, min(100, int(limit)))
    return {
        "unsupportedCount": len(paths),
        "changedRoots": roots,
        "unsupportedPaths": [list(path) for path in paths[:bounded_limit]],
        "truncated": len(paths) > bounded_limit,
    }


class MutationPlanningHost(Protocol):
    def capture_model(self, document_id: str) -> Mapping[str, Any]:
        ...


class CanonicalTargetMismatchError(ValueError):
    """Detached replay could not reproduce the required canonical tree."""

    def __init__(
        self,
        required_after_model: Mapping[str, Any],
        observed_after_model: Mapping[str, Any],
    ) -> None:
        self.required_after_model = copy.deepcopy(dict(required_after_model))
        self.observed_after_model = copy.deepcopy(dict(observed_after_model))
        self.mismatch = diff_models(
            self.required_after_model,
            self.observed_after_model,
        )
        super().__init__("detached replay did not reproduce the canonical target")


@dataclass(frozen=True)
class MutationScope:
    """Canonical roots and glyph dependency closure touched by one patch."""

    roots: tuple[str, ...]
    glyph_names: tuple[str, ...]


@dataclass(frozen=True)
class CanonicalImpact:
    """Exact canonical fragments that one semantic patch can affect."""

    roots: tuple[str, ...]
    paths: tuple[tuple[str, ...], ...]
    glyph_paths: Mapping[str, tuple[tuple[str, ...], ...]]

    @classmethod
    def from_change_set(
        cls, model: Mapping[str, Any], change_set: ChangeSet
    ) -> "CanonicalImpact":
        paths = [change.path for change in change_set.changes]
        renamed_master_ids = {
            change.path[1]
            for change in change_set.changes
            if len(change.path) == 3
            and change.path[0] == "masters"
            and change.path[2] == "name"
        }
        if renamed_master_ids:
            glyphs = model.get("glyphs", {})
            if isinstance(glyphs, Mapping):
                for glyph_name, glyph in glyphs.items():
                    _, layers = _layer_entities(glyph)
                    for master_id in renamed_master_ids & set(layers):
                        path = (
                            "glyphs",
                            str(glyph_name),
                            "layers",
                            str(master_id),
                            "name",
                        )
                        if path not in paths:
                            paths.append(path)
        return cls.from_paths(model, paths)

    @classmethod
    def from_paths(
        cls,
        model: Mapping[str, Any],
        paths: Iterable[Sequence[str]],
    ) -> "CanonicalImpact":
        paths = tuple(tuple(str(part) for part in path) for path in paths)
        roots = tuple(sorted({path[0] for path in paths if path}))
        direct: dict[str, list[tuple[str, ...]]] = {}
        for path in paths:
            if len(path) >= 2 and path[0] == "glyphs":
                direct.setdefault(str(path[1]), []).append(path)

        if not direct:
            return cls(roots=roots, paths=paths, glyph_paths={})

        glyphs = model.get("glyphs", {})
        glyph_map = glyphs if isinstance(glyphs, Mapping) else {}
        known_names = {str(name) for name in glyph_map}
        reverse_dependencies: dict[str, set[str]] = {}
        for dependent_name, glyph in glyph_map.items():
            if not isinstance(glyph, Mapping):
                continue
            references: set[str] = set()
            _, layer_map = _layer_entities(glyph)
            layer_values = layer_map.values()
            for layer in layer_values:
                if not isinstance(layer, Mapping):
                    continue
                for component in layer_components(layer):
                    name = str(
                        component.get("name")
                        or component.get("componentName")
                        or ""
                    )
                    if name in known_names:
                        references.add(name)
                for field_name in (
                    "leftMetricsKey",
                    "rightMetricsKey",
                    "widthMetricsKey",
                ):
                    value = layer.get(field_name)
                    if value:
                        references.update(
                            token
                            for token in re.findall(r"[\w.-]+", str(value))
                            if token in known_names
                        )
            for reference in references:
                reverse_dependencies.setdefault(reference, set()).add(
                    str(dependent_name)
                )

        def requires_dependency_closure(path: tuple[str, ...]) -> bool:
            if len(path) <= 2:
                return True
            if path[2] in {
                "leftMetricsKey",
                "rightMetricsKey",
                "widthMetricsKey",
                "bottomMetricsKey",
                "topMetricsKey",
                "vertOriginMetricsKey",
                "vertWidthMetricsKey",
                "smartAxes",
                "partsSettings",
            }:
                return True
            if path[2] != "layers":
                return False
            if len(path) <= 4:
                return True
            return path[4] in {
                "anchors",
                "shapes",
                "paths",
                "components",
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
            }

        pending = [
            name
            for name, changed_paths in direct.items()
            if any(requires_dependency_closure(path) for path in changed_paths)
        ]
        while pending:
            source = pending.pop()
            for dependent in reverse_dependencies.get(source, ()):
                if dependent not in direct:
                    direct[dependent] = [("glyphs", dependent)]
                    pending.append(dependent)
        return cls(
            roots=roots,
            paths=paths,
            glyph_paths={
                name: tuple(values) for name, values in sorted(direct.items())
            },
        )

    @property
    def glyph_names(self) -> tuple[str, ...]:
        return tuple(self.glyph_paths)

    def layer_ids(self, glyph_name: str) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                path[3]
                for path in self.glyph_paths.get(glyph_name, ())
                if len(path) >= 4 and path[2] == "layers" and path[3] != "$order"
            )
        )

    def requires_complete_glyph(self, glyph_name: str) -> bool:
        return any(
            len(path) <= 2 for path in self.glyph_paths.get(glyph_name, ())
        )


def select_verification_tier(
    *,
    execution_context: Mapping[str, Any] | None = None,
) -> str:
    """Use one native preview path, with full archives only when requested."""

    mode = str(dict(execution_context or {}).get("verificationMode") or "semantic")
    return (
        COMPLETE_NATIVE_VERIFICATION
        if mode == "strict_archive"
        else SCOPED_NATIVE_VERIFICATION
    )


def lifecycle_capabilities(
    change_set: ChangeSet, *, tool: str | None = None
) -> tuple[str, ...]:
    """Derive structural ownership from semantic paths for replay and revert."""

    capabilities: set[str] = set()
    paths = tuple(change.path for change in change_set.changes)
    if any(path and path[0] in _CANONICAL_ROOT_COLLECTIONS | {"glyphOrder", "settings"} for path in paths):
        capabilities.add(CANONICAL_LIFECYCLE_CAPABILITY)
    if any(path and path[0] == "masters" for path in paths):
        capabilities.add(MASTER_LIFECYCLE_CAPABILITY)
    structural_master_ids = _master_structural_ids(change_set)
    if any(
        len(path) == 4
        and path[0] == "glyphs"
        and path[2] == "layers"
        and path[3] not in structural_master_ids
        for path in paths
    ):
        capabilities.add(LAYER_LIFECYCLE_CAPABILITY)
    return tuple(sorted(capabilities))


class StructuralReplayValidationError(ValueError):
    """A staged structural change violates canonical lifecycle ownership."""


def _master_axis_tags(model: Mapping[str, Any]) -> tuple[str, ...]:
    tags: list[str] = []
    for master in model.get("masters", ()):
        if not isinstance(master, Mapping):
            continue
        current = tuple(
            str(axis.get("tag") or "")
            for axis in master.get("axes", ())
            if isinstance(axis, Mapping)
        )
        if current:
            if not tags:
                tags.extend(current)
            elif tuple(tags) != current:
                raise StructuralReplayValidationError(
                    "canonical masters disagree about the font axis order"
                )
    return tuple(tags)


def staged_lifecycle_capabilities(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    change_set: ChangeSet,
) -> tuple[str, ...]:
    """Validate staged collection ownership and return replay capabilities."""

    before_tags = _master_axis_tags(before)
    after_tags = _master_axis_tags(after)

    before_masters = {
        str(master.get("id") or "")
        for master in before.get("masters", ())
        if isinstance(master, Mapping) and str(master.get("id") or "")
    }
    after_masters = {
        str(master.get("id") or "")
        for master in after.get("masters", ())
        if isinstance(master, Mapping) and str(master.get("id") or "")
    }
    added_masters = after_masters - before_masters
    removed_masters = before_masters - after_masters
    capabilities = set(lifecycle_capabilities(change_set))
    if before_tags != after_tags or before.get("axes") != after.get("axes"):
        capabilities.add(CANONICAL_LIFECYCLE_CAPABILITY)

    before_glyphs = before.get("glyphs", {})
    after_glyphs = after.get("glyphs", {})
    before_glyphs = before_glyphs if isinstance(before_glyphs, Mapping) else {}
    after_glyphs = after_glyphs if isinstance(after_glyphs, Mapping) else {}
    for glyph_name in sorted(set(before_glyphs) | set(after_glyphs)):
        if glyph_name not in before_glyphs or glyph_name not in after_glyphs:
            # A glyph entity owns its complete layer collection. Its master
            # layers do not independently claim master lifecycle capability.
            continue
        _, old_layers = _layer_entities(before_glyphs.get(glyph_name, {}))
        _, new_layers = _layer_entities(after_glyphs.get(glyph_name, {}))
        for layer_id in sorted(set(old_layers) | set(new_layers)):
            old = old_layers.get(layer_id)
            new = new_layers.get(layer_id)
            if old is not None and new is not None:
                continue
            value = new if new is not None else old
            if not isinstance(value, Mapping):
                raise StructuralReplayValidationError(
                    "staged layer lifecycle produced an invalid entity"
                )
            master_id = str(value.get("masterId") or "")
            is_master = bool(value.get("isMasterLayer")) or "master" in set(
                str(role) for role in value.get("roles", ())
            )
            if is_master:
                expected = added_masters if new is not None else removed_masters
                if layer_id != master_id or layer_id not in expected:
                    raise StructuralReplayValidationError(
                        "master-layer membership belongs to master lifecycle"
                    )
                capabilities.add(MASTER_LIFECYCLE_CAPABILITY)
            else:
                capabilities.add(LAYER_LIFECYCLE_CAPABILITY)

    for glyph in after_glyphs.values():
        _, layers = _layer_entities(glyph)
        for layer_id, layer in layers.items():
            master_id = str(layer.get("masterId") or "")
            if not master_id or master_id not in after_masters:
                raise StructuralReplayValidationError(
                    "a staged layer references a missing master"
                )
            if bool(layer.get("isMasterLayer")) and layer_id != master_id:
                raise StructuralReplayValidationError(
                    "a master layer must use its owning master identity"
                )
    return tuple(sorted(capabilities))


@dataclass(frozen=True)
class VerifiedMutationPlan:
    """Writable intent plus the complete clone-observed result it must cause."""

    document_id: str
    operation_id: str
    before_model: Mapping[str, Any]
    expected_after_model: Mapping[str, Any]
    writable_change_set: ChangeSet
    observed_change_set: ChangeSet
    dirty_state_intent: str = "forward"
    removes_contribution_id: str | None = None
    replay_replacements: tuple[tuple[str, ...], ...] = ()
    capabilities: tuple[str, ...] = ()
    execution_context: Mapping[str, Any] = field(default_factory=dict)
    expected_observations: Mapping[tuple[str, str], Mapping[str, Any]] = field(
        default_factory=dict
    )
    expected_effective_metadata: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    verification_constraints: tuple[Mapping[str, Any], ...] = ()
    expected_constraint_evidence: Mapping[str, Any] = field(default_factory=dict)
    verification_evidence: Mapping[str, Any] = field(default_factory=dict)
    coverage: CanonicalCoverage = CanonicalCoverage.complete()
    stage_timings: Mapping[str, float] = field(
        default_factory=dict, compare=False, repr=False
    )
    impact: CanonicalImpact | None = field(default=None, compare=False, repr=False)
    verification_tier: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        impact = self.impact or CanonicalImpact.from_change_set(
            self.before_model, self.writable_change_set
        )
        tier = self.verification_tier or select_verification_tier(
            execution_context=self.execution_context,
        )
        object.__setattr__(self, "impact", impact)
        object.__setattr__(self, "verification_tier", tier)

    @property
    def before_fingerprint(self) -> str:
        return self.observed_change_set.before_fingerprint

    @property
    def after_fingerprint(self) -> str:
        return self.observed_change_set.after_fingerprint


class RequestedEffectMismatchError(ValueError):
    """Detached native execution did not preserve every requested effect."""

    def __init__(self, mismatches: Sequence[Mapping[str, Any]]) -> None:
        self.mismatches = tuple(copy.deepcopy(dict(item)) for item in mismatches)
        super().__init__(
            "detached native execution did not preserve {} requested effect(s)".format(
                len(self.mismatches)
            )
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "mismatchCount": len(self.mismatches),
            "mismatches": [
                copy.deepcopy(dict(item)) for item in self.mismatches[:12]
            ],
            "truncated": len(self.mismatches) > 12,
        }


class VerificationEquivalenceError(ValueError):
    """Strict archive verification found a native mismatch."""

    def __init__(self, evidence: Mapping[str, Any]) -> None:
        self.evidence = copy.deepcopy(dict(evidence))
        super().__init__("strict native-archive equivalence was not proved")

    def to_public_dict(self) -> dict[str, Any]:
        return copy.deepcopy(dict(self.evidence))


def _automatic_alignment_equivalent(
    model: Mapping[str, Any],
    path: tuple[str, ...],
    requested: Any,
    observed: Any,
    normalized: list[dict[str, Any]],
) -> bool:
    """Allow only the native geometry explicitly owned by auto alignment."""

    if len(path) >= 5 and path[:1] == ("glyphs",) and path[2] == "layers":
        layer_path = path[:4]
        present, layer = semantic_value_at(model, layer_path)
        if present and isinstance(layer, Mapping):
            automatic_components = [
                component
                for component in layer_components(layer)
                if int(component.get("alignment", -1)) != -1
            ]
            if path[-1] == "width" and automatic_components:
                normalized.append(
                    {
                        "path": list(path),
                        "direct": copy.deepcopy(requested),
                        "observed": copy.deepcopy(observed),
                        "rule": "automatic_alignment_derived_width",
                    }
                )
                return True
            if "shapes" in path and "position" in path:
                shape_index = path.index("shapes")
                if len(path) > shape_index + 1:
                    shape_path = path[: shape_index + 2]
                    shape_present, shape = semantic_value_at(model, shape_path)
                    component = (
                        shape.get("value")
                        if shape_present
                        and isinstance(shape, Mapping)
                        and shape.get("kind") == "component"
                        else None
                    )
                    if (
                        isinstance(component, Mapping)
                        and int(component.get("alignment", -1)) != -1
                    ):
                        normalized.append(
                            {
                                "path": list(path),
                                "direct": copy.deepcopy(requested),
                                "observed": copy.deepcopy(observed),
                                "rule": "automatic_alignment_derived_position",
                            }
                        )
                        return True
    return False


def _registered_canonical_equivalent(
    path: tuple[str, ...],
    requested: Any,
    observed: Any,
    normalized: list[dict[str, Any]],
) -> bool:
    if requested == observed:
        return True
    if isinstance(requested, Mapping) and isinstance(observed, Mapping):
        if set(requested) != set(observed):
            return False
        automatic_component = bool(
            "shapes" in path
            and "alignment" in requested
            and int(requested.get("alignment", -1)) != -1
        )
        for key in requested:
            child_path = path + (str(key),)
            if (
                automatic_component
                and key == "position"
                and requested[key] != observed[key]
            ):
                normalized.append(
                    {
                        "path": list(child_path),
                        "direct": copy.deepcopy(requested[key]),
                        "observed": copy.deepcopy(observed[key]),
                        "rule": "automatic_alignment_derived_position",
                    }
                )
                continue
            if not _registered_canonical_equivalent(
                child_path, requested[key], observed[key], normalized
            ):
                return False
        return True
    if isinstance(requested, (list, tuple)) and isinstance(
        observed, (list, tuple)
    ):
        return len(requested) == len(observed) and all(
            _registered_canonical_equivalent(
                path + (str(index),), left, right, normalized
            )
            for index, (left, right) in enumerate(zip(requested, observed))
        )
    if (
        isinstance(requested, (int, float))
        and not isinstance(requested, bool)
        and isinstance(observed, (int, float))
        and not isinstance(observed, bool)
        and "shapes" in path
        and set(path[-3:]).intersection(
            {"position", "scale", "angle", "slant"}
        )
    ):
        left, right = float(requested), float(observed)
        if math.isfinite(left) and math.isfinite(right):
            absolute_delta = abs(left - right)
            ulp = max(math.ulp(left), math.ulp(right), math.ulp(1.0))
            if absolute_delta <= max(1e-12, 16 * ulp):
                normalized.append(
                    {
                        "path": list(path),
                        "direct": left,
                        "observed": right,
                        "absoluteDelta": absolute_delta,
                        "maximumUlps": absolute_delta / ulp,
                        "rule": "component_decomposition_round_trip",
                    }
                )
                return True
    return False


def _requested_effect_mismatches(
    requested: ChangeSet,
    observed_after: Mapping[str, Any],
    *,
    semantic_equivalence: bool = False,
) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    mismatches: list[Mapping[str, Any]] = []
    normalized: list[Mapping[str, Any]] = []
    for change in requested.changes:
        present, value = semantic_value_at(observed_after, change.path)
        if present == change.after_present and (
            not present or value == change.after
        ):
            continue
        local_normalized: list[dict[str, Any]] = []
        if (
            semantic_equivalence
            and present
            and change.after_present
            and (
                _automatic_alignment_equivalent(
                    observed_after,
                    change.path,
                    change.after,
                    value,
                    local_normalized,
                )
                or _registered_canonical_equivalent(
                    change.path, change.after, value, local_normalized
                )
            )
        ):
            normalized.extend(local_normalized)
            continue
        mismatches.append(
            {
                "path": list(change.path),
                "requestedPresent": change.after_present,
                "observedPresent": present,
                "requested": copy.deepcopy(change.after)
                if change.after_present
                else "<missing>",
                "observed": copy.deepcopy(value) if present else "<missing>",
            }
        )
    return tuple(mismatches), tuple(normalized)


def _unicode_owners(model: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    """Return canonical Unicode ownership without consulting Glyphs UI state."""

    owners: dict[str, set[str]] = {}
    glyphs = model.get("glyphs", {})
    if not isinstance(glyphs, Mapping):
        return {}
    for key, glyph in glyphs.items():
        if not isinstance(glyph, Mapping):
            continue
        name = str(glyph.get("name") or key)
        values = glyph.get("unicodes")
        if values is None:
            values = (glyph.get("unicode"),)
        elif isinstance(values, str):
            values = (values,)
        elif not isinstance(values, Sequence):
            values = (values,)
        for value in values:
            codepoint = str(value or "").upper()
            if codepoint.startswith("U+"):
                codepoint = codepoint[2:]
            if codepoint:
                owners.setdefault(codepoint, set()).add(name)
    return {
        codepoint: frozenset(names)
        for codepoint, names in owners.items()
        if len(names) > 1
    }


def _reject_new_duplicate_unicodes(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> None:
    """Reject new Glyphs-invalid Unicode ownership, preserving legacy state."""

    existing = _unicode_owners(before)
    introduced = [
        (codepoint, owners)
        for codepoint, owners in sorted(_unicode_owners(after).items())
        if existing.get(codepoint) != owners
    ]
    if not introduced:
        return
    codepoint, owners = introduced[0]
    raise ValueError(
        "mutation introduces duplicate Unicode U+{} in glyphs {}".format(
            codepoint,
            ", ".join(sorted(owners)[:8]),
        )
    )


class MutationPlanner:
    def __init__(self, host: MutationPlanningHost, *, activity: Any = None) -> None:
        self._host = host
        self._activity = activity

    def plan(
        self,
        *,
        document_id: str,
        expected_document_fingerprint: str,
        requested_change_set: ChangeSet,
        operation_id: str,
        before_model: Mapping[str, Any] | None = None,
        dirty_state_intent: str = "forward",
        removes_contribution_id: str | None = None,
        required_after_model: Mapping[str, Any] | None = None,
        capabilities: Sequence[str] = (),
        execution_context: Mapping[str, Any] | None = None,
        coverage: CanonicalCoverage | None = None,
        initial_stage_timings: Mapping[str, float] | None = None,
    ) -> VerifiedMutationPlan:
        plan_started = time.perf_counter_ns()
        stage_timings = {
            "initial_capture": 0.0,
            "baseline_capture": 0.0,
            "clone": 0.0,
            "replay": 0.0,
            "canonical_comparison": 0.0,
            "native_comparison": 0.0,
            "detached_apply": 0.0,
            "verification": 0.0,
            "apply": 0.0,
            "readback": 0.0,
            "rollback": 0.0,
            "max_native_phase": 0.0,
            "native_phase_count": 0.0,
            **{
                str(name): float(value)
                for name, value in dict(initial_stage_timings or {}).items()
            },
        }
        if not document_id:
            raise ValueError("document_id is required")
        if not operation_id:
            raise ValueError("operation_id is required")
        if self._activity is not None:
            self._activity.advance_current(
                "capturing", "Reading the current document", cancellable=True
            )
            self._activity.checkpoint_current()
        capture_started = time.perf_counter_ns()
        captured = before_model
        if captured is None:
            snapshot_capture = getattr(self._host, "capture_snapshot", None)
            captured = (
                snapshot_capture(document_id)
                if callable(snapshot_capture)
                else self._host.capture_model(document_id)
            )
            capture_ms = (
                time.perf_counter_ns() - capture_started
            ) / 1_000_000
            stage_timings["initial_capture"] += capture_ms
            stage_timings["baseline_capture"] += capture_ms
        before = (
            captured
            if isinstance(captured, CanonicalSnapshot)
            else copy.deepcopy(dict(captured))
        )
        before_fingerprint = fingerprint_model(before)
        if before_fingerprint != expected_document_fingerprint:
            # Local import avoids coupling the semantic planning module back
            # into the transaction implementation at import time.
            from .transactions import StaleDocumentError

            raise StaleDocumentError("document fingerprint changed before detached simulation")
        if requested_change_set.before_fingerprint != before_fingerprint:
            from .transactions import StaleDocumentError

            raise StaleDocumentError("requested patch targets another document state")

        # Validate the writable patch independently before asking Glyphs to
        # clone anything. This also rejects duplicate/stale paths and new
        # document-integrity conflicts deterministically.
        requested_target = requested_change_set.apply(before)
        if dirty_state_intent == "forward":
            _reject_new_duplicate_unicodes(before, requested_target)
        replay_replacements: tuple[tuple[str, ...], ...] = ()
        simulation_observations: Mapping[tuple[str, str], Mapping[str, Any]] = {}
        simulation_effective_metadata: Mapping[str, Mapping[str, Any]] = {}
        normalized_context = copy.deepcopy(dict(execution_context or {}))
        verification_evidence: Mapping[str, Any] = {
            "mode": str(normalized_context.get("verificationMode") or "semantic"),
            "canonicalEquivalent": True,
            "equivalenceClass": "exact_canonical",
            "nativeArchiveEquivalent": None,
        }
        normalized_capabilities = tuple(sorted(set(str(value) for value in capabilities)))
        impact = CanonicalImpact.from_change_set(before, requested_change_set)
        verification_tier = select_verification_tier(
            execution_context=normalized_context,
        )
        verification_evidence = {
            **dict(verification_evidence),
            "tier": verification_tier,
        }
        verified_simulator = getattr(
            self._host, "simulate_verified_change_set", None
        )
        reconciler = getattr(self._host, "simulate_reconciliation", None)
        if callable(verified_simulator):
            if self._activity is not None:
                self._activity.advance_current(
                    "detached",
                    "Running on a detached document",
                    cancellable=True,
                )
                self._activity.checkpoint_current()
            simulation_started = time.perf_counter_ns()
            cancellation_checkpoint = (
                self._activity.checkpoint_callback()
                if self._activity is not None
                else None
            )
            simulation_options = {
                "required_after_model": (
                    required_after_model
                    if isinstance(required_after_model, CanonicalSnapshot)
                    else copy.deepcopy(dict(required_after_model))
                    if required_after_model is not None
                    else None
                ),
                "capabilities": normalized_capabilities,
                "execution_context": normalized_context,
                "removes_contribution_id": removes_contribution_id,
            }
            try:
                simulator_parameters = inspect.signature(
                    verified_simulator
                ).parameters.values()
            except (TypeError, ValueError):
                simulator_parameters = ()
            accepts_options = any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in simulator_parameters
            )
            parameter_names = {
                parameter.name for parameter in simulator_parameters
            }
            if accepts_options or "impact" in parameter_names:
                simulation_options["impact"] = impact
            if accepts_options or "verification_tier" in parameter_names:
                simulation_options["verification_tier"] = verification_tier
            if accepts_options or "cancellation_checkpoint" in parameter_names:
                simulation_options["cancellation_checkpoint"] = (
                    cancellation_checkpoint
                )
            simulation = verified_simulator(
                document_id,
                requested_change_set,
                before,
                **simulation_options,
            )
            if not isinstance(simulation, Mapping) or not isinstance(
                simulation.get("afterModel"), Mapping
            ):
                raise ValueError("verified canonical simulation returned an invalid result")
            provided_timings = simulation.get("stageTimings", {})
            if isinstance(provided_timings, Mapping):
                for name in (
                    "baseline_capture",
                    "clone",
                    "replay",
                    "canonical_comparison",
                    "native_comparison",
                    "detached_apply",
                    "verification",
                    "readback",
                    "max_native_phase",
                    "native_phase_count",
                ):
                    stage_timings[name] += float(provided_timings.get(name, 0.0))
            else:
                stage_timings["clone"] += (
                    time.perf_counter_ns() - simulation_started
                ) / 1_000_000
            simulated_after = simulation["afterModel"]
            expected_after = (
                simulated_after
                if isinstance(simulated_after, CanonicalSnapshot)
                else copy.deepcopy(dict(simulated_after))
            )
            replay_replacements = tuple(
                tuple(str(part) for part in path)
                for path in simulation.get("replayReplacements", ())
            )
            simulation_observations = copy.deepcopy(
                dict(simulation.get("observations") or {})
            )
            simulation_effective_metadata = copy.deepcopy(
                dict(simulation.get("effectiveMetadata") or {})
            )
            verification_evidence = copy.deepcopy(
                dict(simulation.get("verificationEvidence") or verification_evidence)
            )
            verification_evidence = {
                **dict(verification_evidence),
                "tier": verification_tier,
            }
        elif required_after_model is not None and callable(reconciler):
            simulation_started = time.perf_counter_ns()
            simulation = reconciler(
                document_id,
                requested_change_set,
                required_after_model
                if isinstance(required_after_model, CanonicalSnapshot)
                else copy.deepcopy(dict(required_after_model)),
                before,
            )
            if not isinstance(simulation, Mapping) or not isinstance(
                simulation.get("afterModel"), Mapping
            ):
                raise ValueError("canonical reconciliation returned an invalid simulation")
            stage_timings["clone"] += (
                time.perf_counter_ns() - simulation_started
            ) / 1_000_000
            simulated_after = simulation["afterModel"]
            expected_after = (
                simulated_after
                if isinstance(simulated_after, CanonicalSnapshot)
                else copy.deepcopy(dict(simulated_after))
            )
            replay_replacements = tuple(
                tuple(str(part) for part in path)
                for path in simulation.get("replayReplacements", ())
            )
            simulation_observations = copy.deepcopy(
                dict(simulation.get("observations") or {})
            )
            simulation_effective_metadata = copy.deepcopy(
                dict(simulation.get("effectiveMetadata") or {})
            )
        else:
            simulation_started = time.perf_counter_ns()
            scoped_simulator = getattr(
                self._host, "simulate_change_set_from_model", None
            )
            simulator = getattr(self._host, "simulate_change_set", None)
            if callable(scoped_simulator):
                simulated_after = scoped_simulator(
                    document_id, requested_change_set, before
                )
                expected_after = (
                    simulated_after
                    if isinstance(simulated_after, CanonicalSnapshot)
                    else copy.deepcopy(dict(simulated_after))
                )
            elif callable(simulator):
                expected_after = copy.deepcopy(
                    dict(simulator(document_id, requested_change_set))
                )
            else:
                expected_after = requested_change_set.apply(before)
            stage_timings["clone"] += (
                time.perf_counter_ns() - simulation_started
            ) / 1_000_000
        verification_started = time.perf_counter_ns()
        if self._activity is not None:
            self._activity.advance_current(
                "comparing", "Comparing changes", cancellable=True
            )
            self._activity.checkpoint_current()
        if required_after_model is not None and not complete_models_equal(
            expected_after, required_after_model
        ):
            raise CanonicalTargetMismatchError(
                required_after_model,
                expected_after,
            )
        semantic_mode = (
            str(normalized_context.get("verificationMode") or "semantic")
            == "semantic"
        )
        requested_mismatches, normalized_requested = (
            _requested_effect_mismatches(
                requested_change_set,
                expected_after,
                semantic_equivalence=True,
            )
            if semantic_mode
            else ((), ())
        )
        if requested_mismatches:
            raise RequestedEffectMismatchError(requested_mismatches)
        if normalized_requested:
            maximum_delta = max(
                (
                    float(item.get("absoluteDelta") or 0.0)
                    for item in normalized_requested
                ),
                default=0.0,
            )
            verification_evidence = {
                **dict(verification_evidence),
                "canonicalEquivalent": True,
                "equivalenceClass": "registered_normalization",
                "normalizedPaths": [
                    copy.deepcopy(dict(item))
                    for item in normalized_requested[:100]
                ],
                "normalizedPathCount": len(normalized_requested),
                "normalizedPathsTruncated": len(normalized_requested) > 100,
                "maximumAbsoluteDelta": maximum_delta,
            }
        requested_target_matched = complete_models_equal(
            requested_target, expected_after
        )
        if (
            str(normalized_context.get("verificationMode") or "semantic")
            == "strict_archive"
            and not requested_target_matched
        ):
            mismatch = diff_models(requested_target, expected_after)
            raise VerificationEquivalenceError(
                {
                    "mode": "strict_archive",
                    "canonicalEquivalent": False,
                    "mismatchCount": len(mismatch.changes),
                    "mismatchLocations": [
                        {"path": list(change.path)}
                        for change in mismatch.changes[:100]
                    ],
                    "truncated": len(mismatch.changes) > 100,
                }
            )
        verification_evidence = {
            **dict(verification_evidence),
            "requestedTargetMatched": requested_target_matched,
            "settlement": "exact" if requested_target_matched else "native",
        }
        if dirty_state_intent == "forward":
            _reject_new_duplicate_unicodes(before, expected_after)
        # The requested patch already proves the exact canonical target. When
        # detached read-back agrees completely, it is also the observed diff;
        # re-diffing hundreds of newly attached layers would only duplicate
        # their complete outline payloads. Host-derived effects retain the
        # complete fallback below.
        observed = (
            requested_change_set
            if complete_models_equal(requested_target, expected_after)
            else master_lifecycle_diff(before, expected_after)
            if MASTER_LIFECYCLE_CAPABILITY in normalized_capabilities
            else diff_models(before, expected_after)
        )
        observed.apply(before)
        if isinstance(before, CanonicalSnapshot) and not isinstance(
            expected_after, CanonicalSnapshot
        ):
            expected_after = before.store_verified_transition(
                expected_after,
                observed,
            )
        stage_timings["verification"] += (
            time.perf_counter_ns() - verification_started
        ) / 1_000_000
        stage_timings["total"] = (
            time.perf_counter_ns() - plan_started
        ) / 1_000_000
        return VerifiedMutationPlan(
            document_id=document_id,
            operation_id=operation_id,
            before_model=before,
            expected_after_model=expected_after,
            writable_change_set=requested_change_set,
            observed_change_set=observed,
            dirty_state_intent=dirty_state_intent,
            removes_contribution_id=removes_contribution_id,
            replay_replacements=replay_replacements,
            capabilities=normalized_capabilities,
            execution_context=normalized_context,
            expected_observations=simulation_observations,
            expected_effective_metadata=simulation_effective_metadata,
            verification_evidence=verification_evidence,
            coverage=coverage or CanonicalCoverage.complete(),
            stage_timings=stage_timings,
            impact=impact,
            verification_tier=verification_tier,
        )


__all__ = [
    "CanonicalImpact",
    "COMPLETE_NATIVE_VERIFICATION",
    "CanonicalTargetMismatchError",
    "MutationScope",
    "MutationPlanner",
    "MutationPlanningHost",
    "MutationBuild",
    "MutationRejected",
    "MutationResultContext",
    "RequestedEffectMismatchError",
    "SCOPED_NATIVE_VERIFICATION",
    "VerificationEquivalenceError",
    "CANONICAL_LIFECYCLE_CAPABILITY",
    "LAYER_LIFECYCLE_CAPABILITY",
    "lifecycle_capabilities",
    "MASTER_LIFECYCLE_CAPABILITY",
    "staged_lifecycle_capabilities",
    "StructuralReplayValidationError",
    "VerifiedMutationPlan",
    "classify_change_path",
    "is_structural_change_path",
    "master_lifecycle_diff",
    "master_owns_layer_order_change",
    "master_lifecycle_request_diff",
    "normalize_mutation_build",
    "select_verification_tier",
    "unsupported_change_diagnostics",
    "writable_subset",
]
