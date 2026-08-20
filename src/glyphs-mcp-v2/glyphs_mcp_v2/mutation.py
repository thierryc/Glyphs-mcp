"""Detached planning for verified apply-first document mutations."""

from __future__ import annotations

import copy
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .canonical_tree import CanonicalSnapshot
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
                    after=after_kerning[master_id],
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
        before_layers = (
            before_glyph.get("layers", {})
            if isinstance(before_glyph, Mapping)
            else {}
        )
        after_layers = (
            after_glyph.get("layers", {})
            if isinstance(after_glyph, Mapping)
            else {}
        )
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

    before_kerning = before.get("kerning", {})
    after_kerning = after.get("kerning", {})
    if isinstance(before_kerning, Mapping) and isinstance(after_kerning, Mapping):
        for master_id in sorted(structural_ids):
            before_present = master_id in before_kerning
            after_present = master_id in after_kerning
            if before_present == after_present:
                continue
            changes.append(
                SemanticChange(
                    path=("kerning", master_id),
                    before=before_kerning.get(master_id),
                    after=after_kerning.get(master_id),
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
                    layers = (
                        glyph.get("layers", {})
                        if isinstance(glyph, Mapping)
                        else {}
                    )
                    if not isinstance(layers, Mapping):
                        continue
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

        pending = list(direct)
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
                if len(path) >= 4 and path[2] == "layers"
            )
        )

    def requires_complete_glyph(self, glyph_name: str) -> bool:
        return any(
            len(path) <= 2 for path in self.glyph_paths.get(glyph_name, ())
        )


def mutation_scope(
    model: Mapping[str, Any], change_set: ChangeSet
) -> MutationScope:
    """Compatibility view over the path-derived canonical impact."""

    impact = CanonicalImpact.from_change_set(model, change_set)
    return MutationScope(impact.roots, impact.glyph_names)


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
    stage_timings: Mapping[str, float] = field(
        default_factory=dict, compare=False, repr=False
    )

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
        initial_stage_timings: Mapping[str, float] | None = None,
    ) -> VerifiedMutationPlan:
        plan_started = time.perf_counter_ns()
        stage_timings = {
            "initial_capture": 0.0,
            "clone": 0.0,
            "detached_apply": 0.0,
            "verification": 0.0,
            **{
                str(name): float(value)
                for name, value in dict(initial_stage_timings or {}).items()
            },
        }
        if not document_id:
            raise ValueError("document_id is required")
        if not operation_id:
            raise ValueError("operation_id is required")
        capture_started = time.perf_counter_ns()
        captured = before_model
        if captured is None:
            snapshot_capture = getattr(self._host, "capture_snapshot", None)
            captured = (
                snapshot_capture(document_id)
                if callable(snapshot_capture)
                else self._host.capture_model(document_id)
            )
            stage_timings["initial_capture"] += (
                time.perf_counter_ns() - capture_started
            ) / 1_000_000
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
            simulation_started = time.perf_counter_ns()
            simulation = verified_simulator(
                document_id,
                requested_change_set,
                before,
                required_after_model=(
                    required_after_model
                    if isinstance(required_after_model, CanonicalSnapshot)
                    else copy.deepcopy(dict(required_after_model))
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
            provided_timings = simulation.get("stageTimings", {})
            if isinstance(provided_timings, Mapping):
                for name in ("clone", "detached_apply", "verification"):
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
            stage_timings=stage_timings,
        )


__all__ = [
    "CanonicalImpact",
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
    "master_lifecycle_request_diff",
    "normalize_mutation_build",
    "unsupported_change_diagnostics",
    "writable_subset",
]
