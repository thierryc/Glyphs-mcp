"""Canonical detached document models and deterministic semantic patches."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence, Tuple

from .canonical_collections import (
    ORDER_TOKEN,
    collection_order,
    entity_id,
    find_entity_index,
    identity_collection_paths,
    identity_order_change_required,
    identity_sequence,
    indexed_entities,
    is_identity_collection_path,
    is_identity_sequence_path,
    reorder_entities,
    replace_entity,
    revert_identity_sequence_onto,
)
from .canonical_views import (
    derived_diagnostics_equal,
    layer_components,
    layer_paths,
    semantic_identity_document,
)


MISSING = object()
_CACHED_FINGERPRINT_ACCESS = object()
SUPPORTED_DOCUMENT_ROOTS = frozenset(
    {
        "font",
        "axes",
        "masters",
        "instances",
        "glyphs",
        "glyphOrder",
        "kerning",
        "features",
        "classes",
        "featurePrefixes",
        "metrics",
        "stems",
        "numbers",
        "settings",
    }
)


class ChangeCompositionError(ValueError):
    """Raised when adjacent patches omit the order context needed to compose."""


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("document model numbers must be finite")
        # Glyphs and PyObjC routinely alternate between NSNumber integers and
        # floats. Integral floats and signed zero therefore have one canonical
        # representation, so a generated patch can always reproduce its hash.
        if value == 0 or value.is_integer():
            return int(value)
        return value
    # Native capture emits built-in JSON containers. Keep their recursive hot
    # path on CPython's direct type checks; a collections.abc Mapping check for
    # every scalar and node is disproportionately expensive in Glyphs' Python
    # 3.14/PyObjC runtime. Retain the abstract fallback for external adapters.
    if isinstance(value, dict):
        return {str(key): _plain(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value, key=str)}
    raise TypeError(
        "document models must contain JSON-safe detached values; found {}".format(
            type(value).__name__
        )
    )


def canonical_json(value: Any) -> str:
    return json.dumps(
        _plain(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def fingerprint_model(value: Any) -> str:
    provider = getattr(value, "_verified_canonical_fingerprint", None)
    cached = (
        provider(_CACHED_FINGERPRINT_ACCESS) if callable(provider) else None
    )
    if (
        isinstance(cached, str)
        and cached.startswith("sha256:")
        and len(cached) == 71
    ):
        return cached
    digest = hashlib.sha256(
        canonical_json(semantic_identity_document(value)).encode("utf-8")
    ).hexdigest()
    return "sha256:{}".format(digest)


def complete_models_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Compare complete observed state independently from document identity.

    The document fingerprint intentionally excludes derived diagnostics such
    as compatibility verdicts and last-change timestamps. Exact transaction
    verification and rollback must still prove those observed fields against
    the detached target. Comparing through the Mapping surface ignores cache
    and native revision evidence while immutable shared shards make the usual
    equal case bounded.
    """

    return (
        fingerprint_model(left) == fingerprint_model(right)
        and derived_diagnostics_equal(left, right)
    )


def rebase_canonical_model(
    base: Mapping[str, Any], candidate: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Retain the immutable shards of ``base`` in a copy-on-write candidate.

    Mutation builders intentionally operate on ordinary detached containers.
    When their source is an immutable canonical snapshot, this seam turns the
    resulting mapping back into a snapshot before any fingerprint or semantic
    proof is computed. Domain code therefore never needs to know how snapshots
    are sharded, and no builder can accidentally re-hash a complete font.
    """

    if callable(getattr(candidate, "_verified_canonical_fingerprint", None)):
        return candidate
    rebase = getattr(base, "_rebase_shared_model", None)
    return rebase(candidate) if callable(rebase) else candidate


@dataclass(frozen=True)
class SemanticChange:
    path: Tuple[str, ...]
    before: Any = None
    after: Any = None
    before_present: bool = True
    after_present: bool = True

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("semantic change paths cannot be empty")

    def inverse(self) -> "SemanticChange":
        return SemanticChange(
            path=self.path,
            before=copy.deepcopy(self.after),
            after=copy.deepcopy(self.before),
            before_present=self.after_present,
            after_present=self.before_present,
        )

    def to_dict(self) -> dict[str, Any]:
        value = {
            "path": list(self.path),
            "beforePresent": self.before_present,
            "afterPresent": self.after_present,
        }
        if self.before_present:
            value["before"] = copy.deepcopy(self.before)
        if self.after_present:
            value["after"] = copy.deepcopy(self.after)
        return value


def _change_from_mapping(value: Mapping[str, Any]) -> SemanticChange:
    return SemanticChange(
        path=tuple(str(part) for part in value["path"]),
        before=copy.deepcopy(value.get("before")),
        after=copy.deepcopy(value.get("after")),
        before_present=bool(value.get("beforePresent", "before" in value)),
        after_present=bool(value.get("afterPresent", "after" in value)),
    )


def _public_change_value(path: Sequence[str], value: Any) -> Any:
    if (
        len(path) == 2
        and path[0]
        in {"glyphs", "masters", "instances", "features", "classes", "featurePrefixes"}
        and isinstance(value, Mapping)
    ):
        identity = str(value.get("id") or path[1])
        summary = {
            key: copy.deepcopy(value[key])
            for key in ("name", "type", "category", "subCategory", "unicode", "export")
            if key in value
        }
        return {
            "kind": "canonical_entity",
            "id": identity,
            "fieldCount": len(value),
            "fingerprint": fingerprint_model(value),
            **summary,
        }
    if (
        len(path) == 4
        and path[0] == "glyphs"
        and path[2] == "layers"
        and isinstance(value, Mapping)
    ):
        return {
            "kind": "canonical_layer_entity",
            "id": str(value.get("id") or path[3]),
            "masterId": str(value.get("masterId") or ""),
            "name": str(value.get("name") or ""),
            "pathCount": len(layer_paths(value)),
            "componentCount": len(layer_components(value)),
            "fieldCount": len(value),
            "fingerprint": fingerprint_model(value),
        }
    if len(path) == 2 and path[0] == "kerning" and isinstance(value, Mapping):
        pair_count = sum(
            len(rights)
            for rights in value.values()
            if isinstance(rights, Mapping)
        )
        return {
            "kind": "canonical_kerning_partition",
            "masterId": path[1],
            "pairCount": pair_count,
            "fingerprint": fingerprint_model(value),
        }
    if path and path[-1] == ORDER_TOKEN and isinstance(value, (list, tuple)):
        bounded = [str(identity) for identity in value[:100]]
        return {
            "kind": "entity_order",
            "count": len(value),
            "ids": bounded,
            "truncated": len(value) > len(bounded),
        }
    return copy.deepcopy(value)


def public_change_dict(change: SemanticChange) -> dict[str, Any]:
    """Return a bounded display/result form without weakening stored rollback."""

    value: dict[str, Any] = {
        "path": list(change.path),
        "beforePresent": change.before_present,
        "afterPresent": change.after_present,
    }
    if change.before_present:
        value["before"] = _public_change_value(change.path, change.before)
    if change.after_present:
        value["after"] = _public_change_value(change.path, change.after)
    return value


def _value_at(
    model: Any, path: Sequence[str], *, prefix: Sequence[str] = ()
) -> Any:
    current = model
    traversed: list[str] = [str(part) for part in prefix]
    for part in path:
        if isinstance(current, Mapping):
            if part not in current:
                return MISSING
            current = current[part]
        elif isinstance(current, (list, tuple)):
            if part == ORDER_TOKEN:
                if is_identity_sequence_path(traversed):
                    current = identity_sequence(current)
                    if current is None:
                        return MISSING
                else:
                    try:
                        current = collection_order(current)
                    except ValueError:
                        return MISSING
            else:
                index = find_entity_index(current, part)
                if index is not None:
                    current = current[index]
                else:
                    try:
                        current = current[int(part)]
                    except (ValueError, IndexError):
                        return MISSING
        else:
            return MISSING
        traversed.append(str(part))
    return current


def semantic_value_at(
    model: Any, path: Sequence[str]
) -> tuple[bool, Any]:
    """Read one identity-aware canonical path without exposing a sentinel.

    Adapters use this at source boundaries to distinguish an absent saved
    field from an explicit null value. Collection identity and order lookup
    remains owned by the semantic patch kernel rather than being reimplemented
    by each native adapter.
    """

    value = _value_at(model, path)
    return value is not MISSING, None if value is MISSING else value


def _set_at(model: dict[str, Any], path: Sequence[str], value: Any, present: bool) -> None:
    current: Any = model
    for part in path[:-1]:
        if isinstance(current, dict):
            child = current.get(part)
            if not isinstance(child, (dict, list)):
                child = {}
                current[part] = child
            current = child
        elif isinstance(current, list):
            index = find_entity_index(current, part)
            if index is not None:
                current = current[index]
            else:
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    raise ValueError(
                        "change path is missing: {}".format("/".join(path))
                    )
        else:
            raise ValueError("change path traverses a scalar: {}".format("/".join(path)))
    leaf = path[-1]
    if isinstance(current, list):
        if leaf == ORDER_TOKEN:
            if not present:
                raise ValueError("canonical collection order cannot be removed")
            if is_identity_sequence_path(path[:-1]):
                replacement = identity_sequence(value)
                if replacement is None:
                    raise ValueError("canonical identity sequence is invalid")
                current[:] = replacement
            else:
                reorder_entities(current, value)
        else:
            identity_index = find_entity_index(current, leaf)
            is_entity_value = present and entity_id(value) == leaf
            if identity_index is not None or is_entity_value:
                replace_entity(current, leaf, value, present=present)
            else:
                try:
                    index = int(leaf)
                except ValueError:
                    replace_entity(current, leaf, value, present=present)
                    return
                if not present:
                    raise ValueError("list entries cannot be removed by an indexed semantic change")
                current[index] = copy.deepcopy(value)
    elif present:
        current[leaf] = copy.deepcopy(value)
    else:
        current.pop(leaf, None)


def _require_change_before(
    current: Any,
    change: SemanticChange,
    *,
    prefix: Sequence[str] = (),
) -> None:
    absolute_path = tuple(str(part) for part in prefix) + change.path
    if change.before_present and current is MISSING:
        raise ValueError("change path is missing: {}".format("/".join(change.path)))
    if not change.before_present and current is not MISSING:
        raise ValueError(
            "change path unexpectedly exists: {}".format("/".join(change.path))
        )
    if (
        change.path[-1] == ORDER_TOKEN
        and change.after_present
        and not is_identity_sequence_path(absolute_path[:-1])
        and (
            not isinstance(current, (list, tuple))
            or set(current) != set(change.after)
        )
    ):
        raise ValueError(
            "canonical collection membership is stale: {}".format(
                "/".join(change.path)
            )
        )
    if (
        change.path[-1] == ORDER_TOKEN
        and is_identity_sequence_path(absolute_path[:-1])
        and change.before_present
        and current != change.before
    ):
        raise ValueError(
            "canonical identity sequence has stale content: {}".format(
                "/".join(change.path)
            )
        )
    if (
        change.path[-1] != ORDER_TOKEN
        and change.before_present
        and current != change.before
    ):
        raise ValueError(
            "change path has stale content: {}".format("/".join(change.path))
        )


def _missing_changes(value: Any, path: Tuple[str, ...], *, addition: bool) -> list[SemanticChange]:
    # Presence belongs to the missing subtree root. Decomposing a newly added
    # mapping into leaf writes loses whether its ancestor existed; a later
    # inverse would then leave empty dictionaries and could not reproduce the
    # original fingerprint. Treating the subtree atomically is the same
    # identity/presence rule already used for collection entities.
    if addition:
        return [SemanticChange(path=path, after=copy.deepcopy(value), before_present=False)]
    return [SemanticChange(path=path, before=copy.deepcopy(value), after_present=False)]


@dataclass(frozen=True)
class ChangeSet:
    before_fingerprint: str
    after_fingerprint: str
    changes: Tuple[SemanticChange, ...]

    @classmethod
    def from_changes(
        cls,
        *,
        before_fingerprint: str,
        after_fingerprint: str,
        changes: Iterable[SemanticChange | Mapping[str, Any]],
    ) -> "ChangeSet":
        normalized = tuple(
            change if isinstance(change, SemanticChange) else _change_from_mapping(change)
            for change in changes
        )
        paths = [change.path for change in normalized]
        if len(paths) != len(set(paths)):
            raise ValueError("a semantic change set cannot contain duplicate paths")
        return cls(
            before_fingerprint=before_fingerprint,
            after_fingerprint=after_fingerprint,
            changes=tuple(sorted(normalized, key=lambda item: item.path)),
        )

    @classmethod
    def project(
        cls,
        before: Mapping[str, Any],
        changes: Iterable[SemanticChange | Mapping[str, Any]],
    ) -> "ChangeSet":
        """Build one verified copy-on-write projection from semantic paths.

        Selective revert and writable-path projection operate on already
        verified changes. Expanding their complete font into a mutable copy is
        both unnecessary and especially expensive inside Glyphs. This generic
        constructor applies only the supplied paths, asks an immutable
        snapshot to rebase the changed shards when available, and derives the
        exact target fingerprint from that shared tree.
        """

        normalized = tuple(
            change if isinstance(change, SemanticChange) else _change_from_mapping(change)
            for change in changes
        )
        before_fingerprint = fingerprint_model(before)
        result: Mapping[str, Any] = before
        for change in sorted(
            normalized,
            key=lambda item: (item.path[-1] == ORDER_TOKEN, item.path),
        ):
            _require_change_before(_value_at(result, change.path), change)
            result = _persistent_set_at(
                result,
                change.path,
                change.after,
                change.after_present,
            )
        rebase = getattr(before, "_rebase_shared_model", None)
        if callable(rebase):
            result = rebase(result)
            projected = cls.from_changes(
                before_fingerprint=before_fingerprint,
                after_fingerprint=fingerprint_model(result),
                changes=normalized,
            )
            # The snapshot transition verifies every changed shard and the
            # exact streamed document fingerprint without materializing the
            # complete font.
            projected.apply(before)
            return projected
        return diff_models(before, result)

    @property
    def supported(self) -> bool:
        return all(change.path[0] in SUPPORTED_DOCUMENT_ROOTS for change in self.changes)

    @property
    def unsupported_paths(self) -> Tuple[Tuple[str, ...], ...]:
        return tuple(
            change.path
            for change in self.changes
            if change.path[0] not in SUPPORTED_DOCUMENT_ROOTS
        )

    def changes_under(
        self, prefix: Sequence[str]
    ) -> Tuple[SemanticChange, ...]:
        """Return changes contained by one canonical subtree.

        Replay and impact analysis consume the semantic patch as their one
        routing index. Keeping prefix selection here prevents every native
        domain adapter from independently rescanning or comparing complete
        canonical trees.
        """

        normalized = tuple(str(part) for part in prefix)
        return tuple(
            change
            for change in self.changes
            if len(change.path) >= len(normalized)
            and change.path[: len(normalized)] == normalized
        )

    def affected_identities(
        self, collection_path: Sequence[str]
    ) -> Tuple[str, ...] | None:
        """Return identities touched below an identity-addressed collection.

        ``None`` means the collection or one of its ancestors is replaced, so
        callers must conservatively handle every identity. An empty tuple
        means the collection is untouched (or only its independent order
        token changed). Otherwise identities preserve semantic change order.
        """

        prefix = tuple(str(part) for part in collection_path)
        identities: list[str] = []
        seen: set[str] = set()
        for change in self.changes:
            path = change.path
            if len(path) <= len(prefix) and prefix[: len(path)] == path:
                return None
            if len(path) <= len(prefix) or path[: len(prefix)] != prefix:
                continue
            identity = path[len(prefix)]
            if identity == ORDER_TOKEN or identity in seen:
                continue
            seen.add(identity)
            identities.append(identity)
        return tuple(identities)

    def apply(
        self, model: Mapping[str, Any], *, verify_before: bool = True
    ) -> Mapping[str, Any]:
        snapshot_apply = getattr(model, "_apply_verified_change_set", None)
        if callable(snapshot_apply):
            return snapshot_apply(self, verify_before=verify_before)
        if verify_before and fingerprint_model(model) != self.before_fingerprint:
            raise ValueError("change set does not match the supplied before state")
        result = copy.deepcopy(_plain(model))
        # Membership and field changes must exist before the independent order
        # projection is applied.  Keeping this rule in one place lets every
        # identity-aware domain use the same patch representation.
        ordered_changes = sorted(
            self.changes,
            key=lambda change: (change.path[-1] == ORDER_TOKEN, change.path),
        )
        for change in ordered_changes:
            current = _value_at(result, change.path)
            if verify_before:
                _require_change_before(current, change)
            _set_at(result, change.path, change.after, change.after_present)
        if fingerprint_model(result) != self.after_fingerprint:
            raise ValueError("change set did not produce its declared after fingerprint")
        return result

    def inverse(self) -> "ChangeSet":
        return ChangeSet.from_changes(
            before_fingerprint=self.after_fingerprint,
            after_fingerprint=self.before_fingerprint,
            changes=(change.inverse() for change in self.changes),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "beforeFingerprint": self.before_fingerprint,
            "afterFingerprint": self.after_fingerprint,
            "changeCount": len(self.changes),
            "supported": self.supported,
            "changes": [change.to_dict() for change in self.changes],
        }


def _diff(before: Any, after: Any, path: Tuple[str, ...]) -> list[SemanticChange]:
    # Copy-on-write mutation builders retain every untouched canonical shard
    # by identity. That identity is stronger than recursive equality and lets
    # a one-glyph edit avoid walking the other hundreds of glyph trees.
    if before is after:
        return []
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        changes: list[SemanticChange] = []
        for key in sorted(set(before) | set(after), key=str):
            key_text = str(key)
            before_present = key in before
            after_present = key in after
            if not before_present:
                if path == ("glyphs",) or (
                    len(path) == 3
                    and path[0] == "glyphs"
                    and path[2] == "layers"
                ):
                    changes.append(
                        SemanticChange(
                            path=path + (key_text,),
                            after=copy.deepcopy(after[key]),
                            before_present=False,
                        )
                    )
                else:
                    changes.extend(_missing_changes(after[key], path + (key_text,), addition=True))
            elif not after_present:
                changes.append(
                    SemanticChange(
                        path=path + (key_text,),
                        before=copy.deepcopy(before[key]),
                        after_present=False,
                    )
                )
            else:
                changes.extend(_diff(before[key], after[key], path + (key_text,)))
        return changes
    if isinstance(before, (list, tuple)) and isinstance(after, (list, tuple)):
        if is_identity_sequence_path(path):
            before_sequence = identity_sequence(before)
            after_sequence = identity_sequence(after)
            if before_sequence is not None and after_sequence is not None:
                if before_sequence == after_sequence:
                    return []
                return [
                    SemanticChange(
                        path=path + (ORDER_TOKEN,),
                        before=before_sequence,
                        after=after_sequence,
                    )
                ]
        if is_identity_collection_path(path):
            before_indexed = indexed_entities(before)
            after_indexed = indexed_entities(after)
            if before_indexed is not None and after_indexed is not None:
                before_order, before_entities = before_indexed
                after_order, after_entities = after_indexed
                changes: list[SemanticChange] = []
                for identity in before_order:
                    if identity not in after_entities:
                        changes.append(
                            SemanticChange(
                                path=path + (identity,),
                                before=copy.deepcopy(before_entities[identity]),
                                after_present=False,
                            )
                        )
                for identity in after_order:
                    if identity not in before_entities:
                        changes.append(
                            SemanticChange(
                                path=path + (identity,),
                                after=copy.deepcopy(after_entities[identity]),
                                before_present=False,
                            )
                        )
                    else:
                        changes.extend(
                            _diff(
                                before_entities[identity],
                                after_entities[identity],
                                path + (identity,),
                            )
                        )
                # ChangeSet normalization sorts entity paths, so simultaneous
                # additions replay in identity order rather than construction
                # order. Emit an order patch only when that normalized minimal
                # membership replay cannot reproduce the target.
                if identity_order_change_required(before_order, after_order):
                    changes.append(
                        SemanticChange(
                            path=path + (ORDER_TOKEN,),
                            before=before_order,
                            after=after_order,
                        )
                    )
                return changes
        if len(before) != len(after):
            return [
                SemanticChange(
                    path=path,
                    before=copy.deepcopy(list(before)),
                    after=copy.deepcopy(list(after)),
                )
            ]
        changes = []
        for index, (before_item, after_item) in enumerate(zip(before, after)):
            changes.extend(_diff(before_item, after_item, path + (str(index),)))
        return changes
    if before != after:
        return [
            SemanticChange(
                path=path,
                before=copy.deepcopy(before),
                after=copy.deepcopy(after),
            )
        ]
    return []


def diff_models(before: Mapping[str, Any], after: Mapping[str, Any]) -> ChangeSet:
    # Immutable canonical snapshots carry fingerprints issued through the
    # private verification token above. Equality at that boundary proves an
    # empty semantic transition, so expanding hundreds of shared glyph shards
    # and recursively comparing them would add no evidence. Plain mappings
    # retain the same canonical-hash guarantee because ``fingerprint_model``
    # normalizes their complete JSON-safe content before this check.
    before_fingerprint = fingerprint_model(before)
    # Builders return copy-on-write mappings. Rebase those mappings onto the
    # immutable source before hashing so only changed shards are encoded and
    # the resulting SHA remains byte-identical to canonical whole-document
    # JSON.
    after_for_diff = rebase_canonical_model(before, after)
    after_fingerprint = fingerprint_model(after_for_diff)
    if before_fingerprint == after_fingerprint:
        return ChangeSet.from_changes(
            before_fingerprint=before_fingerprint,
            after_fingerprint=after_fingerprint,
            changes=(),
        )
    change_set = ChangeSet.from_changes(
        before_fingerprint=before_fingerprint,
        after_fingerprint=after_fingerprint,
        changes=_diff(before, after_for_diff, ()),
    )
    # CanonicalSnapshot applies this patch through its persistent tree editor;
    # plain mappings retain the existing detached-copy implementation. There
    # is no reason to materialize both complete documents merely to prove the
    # generated delta.
    reproduced = change_set.apply(before)
    if fingerprint_model(reproduced) != change_set.after_fingerprint:
        raise ValueError("generated semantic diff does not reproduce its after fingerprint")
    return change_set


def _is_path_prefix(prefix: Sequence[str], path: Sequence[str]) -> bool:
    return len(prefix) <= len(path) and tuple(path[: len(prefix)]) == tuple(prefix)


def _compose_paths(first: ChangeSet, second: ChangeSet) -> tuple[Tuple[str, ...], ...]:
    candidates: list[Tuple[str, ...]] = []
    for path in sorted(
        {change.path for change in first.changes + second.changes},
        key=lambda value: (len(value), value),
    ):
        if not any(_is_path_prefix(candidate, path) for candidate in candidates):
            candidates.append(path)
    return tuple(candidates)


def _apply_descendant_changes(
    value: Any,
    candidate: Sequence[str],
    changes: Sequence[SemanticChange],
    *,
    inverse: bool = False,
) -> Any:
    result = value
    projected: list[SemanticChange] = []
    for original in changes:
        change = (
            SemanticChange(
                path=original.path,
                before=original.after,
                after=original.before,
                before_present=original.after_present,
                after_present=original.before_present,
            )
            if inverse
            else original
        )
        relative = change.path[len(candidate) :]
        if not relative:
            raise ValueError("an exact change cannot be applied as a descendant")
        projected.append(
            SemanticChange(
                path=tuple(relative),
                before=change.before,
                after=change.after,
                before_present=change.before_present,
                after_present=change.after_present,
            )
        )
    for change in sorted(
        projected,
        key=lambda item: (item.path[-1] == ORDER_TOKEN, item.path),
    ):
        current = _value_at(result, change.path, prefix=candidate)
        _require_change_before(current, change, prefix=candidate)
        result = _persistent_set_at(
            result,
            change.path,
            change.after,
            change.after_present,
            prefix=candidate,
        )
    return result


def _persistent_set_at(
    current: Any,
    path: Sequence[str],
    value: Any,
    present: bool,
    *,
    prefix: Sequence[str] = (),
) -> Any:
    """Return one copy-on-write update while sharing every untouched branch."""

    part = path[0]
    leaf = len(path) == 1
    if isinstance(current, Mapping):
        result = dict(current)
        if leaf:
            if present:
                result[part] = value
            else:
                result.pop(part, None)
            return result
        child = current.get(part, {})
        result[part] = _persistent_set_at(
            child,
            path[1:],
            value,
            present,
            prefix=tuple(prefix) + (str(part),),
        )
        return result
    if isinstance(current, (list, tuple)):
        result = list(current)
        if part == ORDER_TOKEN:
            if not leaf or not present:
                raise ValueError("canonical collection order cannot be removed")
            if is_identity_sequence_path(prefix):
                replacement = identity_sequence(value)
                if replacement is None:
                    raise ValueError("canonical identity sequence is invalid")
                return replacement
            identities = {entity_id(item): item for item in result}
            requested = [str(identity) for identity in value]
            if set(requested) != set(identities) or len(requested) != len(identities):
                raise ValueError("canonical collection membership is stale")
            return [identities[identity] for identity in requested]
        index = find_entity_index(result, part)
        if index is None:
            try:
                index = int(part)
            except ValueError:
                index = None
        if leaf:
            if index is None:
                if present and entity_id(value) == part:
                    result.append(value)
                elif present:
                    raise ValueError("change path is missing: {}".format("/".join(path)))
            elif present:
                result[index] = value
            else:
                del result[index]
            return result
        if index is None:
            raise ValueError("change path is missing: {}".format("/".join(path)))
        result[index] = _persistent_set_at(
            result[index],
            path[1:],
            value,
            present,
            prefix=tuple(prefix) + (str(part),),
        )
        return result
    raise ValueError("change path traverses a scalar: {}".format("/".join(path)))


def _composed_fragment_changes(
    path: Tuple[str, ...],
    before: Any,
    after: Any,
    *,
    before_present: bool,
    after_present: bool,
) -> list[SemanticChange]:
    if before_present == after_present and (
        not before_present or before == after
    ):
        return []
    if not before_present or not after_present:
        return [
            SemanticChange(
                path=path,
                before=before,
                after=after,
                before_present=before_present,
                after_present=after_present,
            )
        ]
    if path[-1] == ORDER_TOKEN:
        return [SemanticChange(path=path, before=before, after=after)]
    return _diff(before, after, path)


def _replay_identity_membership(
    order: Sequence[str],
    changes: Sequence[SemanticChange],
    *,
    inverse: bool = False,
) -> list[str]:
    result = [str(identity) for identity in order]
    for original in sorted(changes, key=lambda item: item.path):
        before_present = original.after_present if inverse else original.before_present
        after_present = original.before_present if inverse else original.after_present
        identity = original.path[-1]
        if before_present and not after_present:
            if identity in result:
                result.remove(identity)
        elif not before_present and after_present and identity not in result:
            result.append(identity)
    return result


def _normalize_composed_orders(
    changes: Sequence[SemanticChange],
    first: ChangeSet,
    second: ChangeSet,
) -> list[SemanticChange]:
    result = list(changes)
    collection_paths = identity_collection_paths(
        change.path for change in (*first.changes, *second.changes, *result)
    )
    for collection_path in collection_paths:
        order_path = collection_path + (ORDER_TOKEN,)
        member_length = len(collection_path) + 1
        first_membership = tuple(
            change
            for change in first.changes
            if len(change.path) == member_length
            and change.path[: len(collection_path)] == collection_path
            and change.path[-1] != ORDER_TOKEN
        )
        second_membership = tuple(
            change
            for change in second.changes
            if len(change.path) == member_length
            and change.path[: len(collection_path)] == collection_path
            and change.path[-1] != ORDER_TOKEN
        )
        order = next((change for change in result if change.path == order_path), None)
        membership = tuple(
            change
            for change in result
            if len(change.path) == member_length
            and change.path[: len(collection_path)] == collection_path
            and change.path[-1] != ORDER_TOKEN
        )
        if order is None:
            if first_membership and second_membership and membership:
                raise ChangeCompositionError(
                    "identity membership changes require canonical order context"
                )
            continue

        additions = {
            change.path[-1]
            for change in membership
            if not change.before_present and change.after_present
        }
        deletions = {
            change.path[-1]
            for change in membership
            if change.before_present and not change.after_present
        }
        before = [str(identity) for identity in order.before]
        after = [str(identity) for identity in order.after]
        before = [identity for identity in before if identity not in additions]
        after = [identity for identity in after if identity not in deletions]
        before_only = set(before) - set(after)
        after_only = set(after) - set(before)
        before = [
            identity
            for identity in before
            if identity not in before_only or identity in deletions
        ]
        after = [
            identity
            for identity in after
            if identity not in after_only or identity in additions
        ]
        result = [change for change in result if change.path != order_path]
        if (
            _replay_identity_membership(before, membership) != after
            or _replay_identity_membership(after, membership, inverse=True) != before
        ):
            result.append(SemanticChange(path=order_path, before=before, after=after))
    return result


def compose_change_sets(first: ChangeSet, second: ChangeSet) -> ChangeSet:
    """Compose two verified semantic patches without reopening their trees.

    This is the canonical equivalent of composing adjacent Git deltas. Parent
    replacements absorb later child edits, child edits are reconstructed when
    a parent is subsequently removed, and exact reversals cancel. The bridge
    fingerprint and every overlapping before-value are checked before a
    composed patch is returned.
    """

    if first.after_fingerprint != second.before_fingerprint:
        raise ValueError("change sets are not adjacent")
    changes: list[SemanticChange] = []
    for candidate in _compose_paths(first, second):
        first_related = tuple(
            change
            for change in first.changes
            if _is_path_prefix(candidate, change.path)
        )
        second_related = tuple(
            change
            for change in second.changes
            if _is_path_prefix(candidate, change.path)
        )
        first_exact = next(
            (change for change in first_related if change.path == candidate),
            None,
        )
        second_exact = next(
            (change for change in second_related if change.path == candidate),
            None,
        )

        if not second_related:
            changes.extend(first_related)
            continue
        if not first_related:
            changes.extend(second_related)
            continue

        if first_exact is not None:
            before_present = first_exact.before_present
            before = first_exact.before
            middle_present = first_exact.after_present
            middle = first_exact.after
            if second_exact is not None:
                if (
                    middle_present != second_exact.before_present
                    or (middle_present and middle != second_exact.before)
                ):
                    raise ValueError("overlapping change sets have a stale bridge")
                after_present = second_exact.after_present
                after = second_exact.after
            else:
                after_present = middle_present
                after = (
                    _apply_descendant_changes(
                        middle,
                        candidate,
                        second_related,
                    )
                    if second_related
                    else middle
                )
        elif second_exact is not None:
            middle_present = second_exact.before_present
            middle = second_exact.before
            after_present = second_exact.after_present
            after = second_exact.after
            before_present = middle_present
            before = (
                _apply_descendant_changes(
                    middle,
                    candidate,
                    first_related,
                    inverse=True,
                )
                if first_related
                else middle
            )
        else:  # pragma: no cover - every candidate originates from one exact path
            raise ValueError("composition candidate has no exact change")

        changes.extend(
            _composed_fragment_changes(
                candidate,
                before,
                after,
                before_present=before_present,
                after_present=after_present,
            )
        )

    changes = _normalize_composed_orders(changes, first, second)
    result = ChangeSet.from_changes(
        before_fingerprint=first.before_fingerprint,
        after_fingerprint=second.after_fingerprint,
        changes=changes,
    )
    if not result.changes and result.before_fingerprint != result.after_fingerprint:
        raise ValueError("composed changes omitted a fingerprint delta")
    return result


def subset_change_set(
    before: Mapping[str, Any],
    source: ChangeSet,
    predicate: Any,
) -> ChangeSet:
    """Project a verified change set while preserving a reproducible target."""

    selected = [change for change in source.changes if predicate(change)]
    if len(selected) == len(source.changes):
        if fingerprint_model(before) != source.before_fingerprint:
            raise ValueError("source change set does not match the supplied before state")
        return source

    if fingerprint_model(before) != source.before_fingerprint:
        raise ValueError("source change set does not match the supplied before state")
    return ChangeSet.project(before, selected)


def revert_change_set_onto(
    current: Mapping[str, Any],
    original: ChangeSet,
) -> tuple[ChangeSet | None, tuple[Tuple[str, ...], ...]]:
    """Build a non-overwriting inverse of ``original`` on ``current``.

    A path is safe while it contains either the value written by the original
    change or the original value. The latter is already reverted and needs no
    write. Unrelated later fields are preserved; a third value is an
    overlapping edit and no partial patch is produced.
    """

    conflicts: list[Tuple[str, ...]] = []
    pending: list[SemanticChange] = []
    order_changes: list[SemanticChange] = []
    for change in original.changes:
        if change.path[-1] == ORDER_TOKEN:
            order_changes.append(change)
            continue
        value = _value_at(current, change.path)
        matches_after = (
            value is not MISSING and value == change.after
            if change.after_present
            else value is MISSING
        )
        matches_before = (
            value is not MISSING and value == change.before
            if change.before_present
            else value is MISSING
        )
        if matches_after:
            pending.append(change.inverse())
        elif not matches_before:
            conflicts.append(change.path)
    if conflicts:
        return None, tuple(conflicts)
    partial = ChangeSet.project(current, pending).apply(current) if pending else current
    projected = list(pending)
    for change in order_changes:
        live_value = _value_at(current, change.path)
        target_value = _value_at(partial, change.path)
        if live_value is MISSING or target_value is MISSING:
            conflicts.append(change.path)
            continue
        live_order = [str(identity) for identity in live_value]
        target_order = [str(identity) for identity in target_value]
        before_order = [str(identity) for identity in change.before]
        after_order = [str(identity) for identity in change.after]
        if is_identity_sequence_path(change.path[:-1]):
            rebased_order = revert_identity_sequence_onto(
                live_order, before_order, after_order
            )
            if rebased_order is None:
                conflicts.append(change.path)
                continue
            if target_order != rebased_order:
                projected.append(
                    SemanticChange(
                        path=change.path,
                        before=live_value,
                        after=rebased_order,
                    )
                )
            continue
        universe = set(before_order) | set(after_order)
        live_surviving = {identity for identity in universe if identity in live_order}
        projected_live = [
            identity for identity in live_order if identity in live_surviving
        ]
        projected_before = [
            identity for identity in before_order if identity in live_surviving
        ]
        projected_after = [
            identity for identity in after_order if identity in live_surviving
        ]
        if projected_live not in (projected_before, projected_after):
            conflicts.append(change.path)
            continue
        # Membership inverses above may have restored deleted entities or
        # removed added ones. Reorder that target projection to the original
        # before order while leaving later unrelated identities in their exact
        # slots and relative order.
        target_surviving = {
            identity for identity in universe if identity in target_order
        }
        desired = [
            identity for identity in before_order if identity in target_surviving
        ]
        replacement = iter(desired)
        rebased_order = [
            next(replacement) if identity in target_surviving else identity
            for identity in target_order
        ]
        if target_order != rebased_order:
            projected.append(
                SemanticChange(
                    path=change.path,
                    before=live_value,
                    after=rebased_order,
                )
            )
    if conflicts:
        return None, tuple(conflicts)
    return ChangeSet.project(current, projected), ()


__all__ = [
    "ChangeCompositionError",
    "ChangeSet",
    "SUPPORTED_DOCUMENT_ROOTS",
    "SemanticChange",
    "canonical_json",
    "complete_models_equal",
    "compose_change_sets",
    "diff_models",
    "fingerprint_model",
    "public_change_dict",
    "revert_change_set_onto",
    "semantic_value_at",
    "subset_change_set",
]
