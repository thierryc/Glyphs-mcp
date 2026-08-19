"""Detached planning for verified apply-first document mutations."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from .semantic import (
    ChangeSet,
    SemanticChange,
    diff_models,
    fingerprint_model,
    subset_change_set,
)


_FONT_WRITABLE = frozenset(
    {"familyName", "upm", "versionMajor", "versionMinor", "note", "grid", "gridSubDivision"}
)
_GLYPH_WRITABLE = frozenset(
    {"category", "subCategory", "unicode", "export", "leftKerningGroup", "rightKerningGroup"}
)
_LAYER_WRITABLE = frozenset(
    {
        "width",
        "LSB",
        "RSB",
        "leftMetricsKey",
        "rightMetricsKey",
        "widthMetricsKey",
        "anchors",
        "paths",
        "components",
    }
)
_OPENTYPE_ROOTS = frozenset({"features", "classes", "featurePrefixes"})
_OPENTYPE_WRITABLE = frozenset({"name", "code", "automatic", "disabled"})
_INSTANCE_WRITABLE = frozenset({"name", "type", "included", "axes"})
MASTER_LIFECYCLE_CAPABILITY = "master_lifecycle"


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
            and change.path[1] in added_ids
        )
    ]
    after_kerning = after.get("kerning", {})
    if isinstance(after_kerning, Mapping):
        for master_id in sorted(added_ids & set(after_kerning)):
            retained.append(
                SemanticChange(
                    path=("kerning", master_id),
                    after=copy.deepcopy(after_kerning[master_id]),
                    before_present=False,
                )
            )
    result = ChangeSet.from_changes(
        before_fingerprint=fingerprint_model(before),
        after_fingerprint=fingerprint_model(after),
        changes=retained,
    )
    result.apply(before)
    result.inverse().apply(after)
    return result


def classify_change_path(path: tuple[str, ...]) -> str:
    if not path:
        return "unsupported"
    if path[0] == "font" and len(path) == 2 and path[1] in _FONT_WRITABLE:
        return "writable"
    if path[0] == "kerning":
        return "writable"
    if (
        path[0] in _OPENTYPE_ROOTS
        and (
            len(path) == 2
            or (len(path) == 3 and path[2] in _OPENTYPE_WRITABLE)
        )
    ):
        return "writable"
    if path[0] == "instances":
        if len(path) == 2:
            return "writable"
        if len(path) >= 3 and path[2] in _INSTANCE_WRITABLE:
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
            if path[4] == "pathSignature":
                return "derived"
            if path[4] in _LAYER_WRITABLE:
                return "writable"
    if path[0] == "glyphs" and len(path) == 2:
        return "writable"
    return "unsupported"


def is_structural_change_path(path: tuple[str, ...]) -> bool:
    """Return whether a patch changes canonical collection membership/order."""

    return len(path) == 2 and path[0] in {
        "glyphs",
        "masters",
        "instances",
        "features",
        "classes",
        "featurePrefixes",
    }


def _master_structural_ids(change_set: ChangeSet) -> frozenset[str]:
    return frozenset(
        change.path[1]
        for change in change_set.changes
        if len(change.path) == 2
        and change.path[0] == "masters"
        and change.path[1] != "$order"
        and change.before_present != change.after_present
    )


def _change_classification(
    change: Any,
    change_set: ChangeSet,
    capabilities: Sequence[str],
) -> str:
    classification = classify_change_path(change.path)
    if classification != "unsupported":
        return classification
    if MASTER_LIFECYCLE_CAPABILITY not in capabilities:
        return classification
    structural_ids = _master_structural_ids(change_set)
    path = change.path
    if path[0] == "masters":
        if len(path) == 2:
            return "writable"
        if len(path) >= 3 and path[2] in {"name", "italicAngle", "axes"}:
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


def mutation_scope(
    model: Mapping[str, Any], change_set: ChangeSet
) -> MutationScope:
    """Resolve one conservative semantic scope without native Glyphs objects."""

    roots = {change.path[0] for change in change_set.changes if change.path}
    glyphs = model.get("glyphs", {})
    glyph_map = glyphs if isinstance(glyphs, Mapping) else {}
    known_names = {str(name) for name in glyph_map}
    direct = {
        change.path[1]
        for change in change_set.changes
        if len(change.path) >= 2 and change.path[0] == "glyphs"
    }
    if "masters" in roots:
        # A master owns one layer in every glyph. Even a scalar master rename
        # can change derived layer names, so the conservative semantic closure
        # is the complete glyph collection.
        direct = set(known_names)
    if "glyphs" in roots and not direct:
        direct = set(known_names)

    reverse_dependencies: dict[str, set[str]] = {}
    for dependent_name, glyph in glyph_map.items():
        if not isinstance(glyph, Mapping):
            continue
        references: set[str] = set()
        layers = glyph.get("layers", {})
        layer_values = layers.values() if isinstance(layers, Mapping) else ()
        for layer in layer_values:
            if not isinstance(layer, Mapping):
                continue
            components = layer.get("components", ())
            if isinstance(components, (list, tuple)):
                for component in components:
                    if isinstance(component, Mapping):
                        name = str(
                            component.get("name")
                            or component.get("componentName")
                            or ""
                        )
                        if name in known_names:
                            references.add(name)
            for field in (
                "leftMetricsKey",
                "rightMetricsKey",
                "widthMetricsKey",
            ):
                value = layer.get(field)
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

    resolved = set(str(name) for name in direct)
    pending = list(resolved)
    while pending:
        source = pending.pop()
        for dependent in reverse_dependencies.get(source, ()):
            if dependent not in resolved:
                resolved.add(dependent)
                pending.append(dependent)
    return MutationScope(tuple(sorted(roots)), tuple(sorted(resolved)))


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

    @property
    def before_fingerprint(self) -> str:
        return self.observed_change_set.before_fingerprint

    @property
    def after_fingerprint(self) -> str:
        return self.observed_change_set.after_fingerprint


class MutationPlanner:
    def __init__(self, host: MutationPlanningHost) -> None:
        self._host = host

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
    ) -> VerifiedMutationPlan:
        if not document_id:
            raise ValueError("document_id is required")
        if not operation_id:
            raise ValueError("operation_id is required")
        before = copy.deepcopy(
            dict(before_model)
            if before_model is not None
            else dict(self._host.capture_model(document_id))
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
        # clone anything. This also rejects duplicate/stale paths deterministically.
        requested_change_set.apply(before)
        replay_replacements: tuple[tuple[str, ...], ...] = ()
        normalized_capabilities = tuple(sorted(set(str(value) for value in capabilities)))
        normalized_context = copy.deepcopy(dict(execution_context or {}))
        verified_simulator = getattr(
            self._host, "simulate_verified_change_set", None
        )
        reconciler = getattr(self._host, "simulate_reconciliation", None)
        if callable(verified_simulator):
            simulation = verified_simulator(
                document_id,
                requested_change_set,
                copy.deepcopy(before),
                required_after_model=(
                    copy.deepcopy(dict(required_after_model))
                    if required_after_model is not None
                    else None
                ),
                capabilities=normalized_capabilities,
                execution_context=normalized_context,
                removes_contribution_id=removes_contribution_id,
            )
            if not isinstance(simulation, Mapping) or not isinstance(
                simulation.get("afterModel"), Mapping
            ):
                raise ValueError("verified canonical simulation returned an invalid result")
            expected_after = copy.deepcopy(dict(simulation["afterModel"]))
            replay_replacements = tuple(
                tuple(str(part) for part in path)
                for path in simulation.get("replayReplacements", ())
            )
        elif required_after_model is not None and callable(reconciler):
            simulation = reconciler(
                document_id,
                requested_change_set,
                copy.deepcopy(dict(required_after_model)),
                copy.deepcopy(before),
            )
            if not isinstance(simulation, Mapping) or not isinstance(
                simulation.get("afterModel"), Mapping
            ):
                raise ValueError("canonical reconciliation returned an invalid simulation")
            expected_after = copy.deepcopy(dict(simulation["afterModel"]))
            replay_replacements = tuple(
                tuple(str(part) for part in path)
                for path in simulation.get("replayReplacements", ())
            )
        else:
            scoped_simulator = getattr(
                self._host, "simulate_change_set_from_model", None
            )
            simulator = getattr(self._host, "simulate_change_set", None)
            if callable(scoped_simulator):
                expected_after = copy.deepcopy(
                    dict(
                        scoped_simulator(
                            document_id, requested_change_set, before
                        )
                    )
                )
            elif callable(simulator):
                expected_after = copy.deepcopy(
                    dict(simulator(document_id, requested_change_set))
                )
            else:
                expected_after = requested_change_set.apply(before)
        if (
            required_after_model is not None
            and fingerprint_model(expected_after)
            != fingerprint_model(required_after_model)
        ):
            raise CanonicalTargetMismatchError(
                required_after_model,
                expected_after,
            )
        observed = (
            master_lifecycle_diff(before, expected_after)
            if MASTER_LIFECYCLE_CAPABILITY in normalized_capabilities
            else diff_models(before, expected_after)
        )
        observed.apply(before)
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
        )


__all__ = [
    "CanonicalTargetMismatchError",
    "MutationScope",
    "MutationPlanner",
    "MutationPlanningHost",
    "MutationBuild",
    "MASTER_LIFECYCLE_CAPABILITY",
    "VerifiedMutationPlan",
    "classify_change_path",
    "is_structural_change_path",
    "mutation_scope",
    "master_lifecycle_diff",
    "normalize_mutation_build",
    "unsupported_change_diagnostics",
    "writable_subset",
]
