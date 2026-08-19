"""Canonical detached document models and deterministic semantic patches."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence, Tuple

from .canonical_collections import (
    IDENTITY_COLLECTION_ROOTS,
    ORDER_TOKEN,
    collection_order,
    entity_id,
    find_entity_index,
    indexed_entities,
    reorder_entities,
    replace_entity,
)


MISSING = object()
SUPPORTED_DOCUMENT_ROOTS = frozenset(
    {
        "font",
        "masters",
        "instances",
        "glyphs",
        "kerning",
        "features",
        "classes",
        "featurePrefixes",
    }
)


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
    raise TypeError("document models must contain JSON-safe detached values")


def canonical_json(value: Any) -> str:
    return json.dumps(
        _plain(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def fingerprint_model(value: Any) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return "sha256:{}".format(digest)


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
            "pathCount": len(value.get("paths") or ()),
            "componentCount": len(value.get("components") or ()),
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


def _value_at(model: Any, path: Sequence[str]) -> Any:
    current = model
    for part in path:
        if isinstance(current, Mapping):
            if part not in current:
                return MISSING
            current = current[part]
        elif isinstance(current, (list, tuple)):
            if part == ORDER_TOKEN:
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
    return current


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


def _missing_changes(value: Any, path: Tuple[str, ...], *, addition: bool) -> list[SemanticChange]:
    if isinstance(value, Mapping) and value:
        changes: list[SemanticChange] = []
        for key in sorted(value, key=str):
            changes.extend(_missing_changes(value[key], path + (str(key),), addition=addition))
        return changes
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

    def apply(self, model: Mapping[str, Any], *, verify_before: bool = True) -> dict[str, Any]:
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
                if change.before_present and current is MISSING:
                    raise ValueError("change path is missing: {}".format("/".join(change.path)))
                if not change.before_present and current is not MISSING:
                    raise ValueError("change path unexpectedly exists: {}".format("/".join(change.path)))
                if (
                    change.path[-1] == ORDER_TOKEN
                    and change.after_present
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
                    change.path[-1] != ORDER_TOKEN
                    and change.before_present
                    and current != change.before
                ):
                    raise ValueError("change path has stale content: {}".format("/".join(change.path)))
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
        if len(path) == 1 and path[0] in IDENTITY_COLLECTION_ROOTS:
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
                replayed_order = [
                    identity for identity in before_order if identity in after_entities
                ] + [
                    identity
                    for identity in sorted(after_entities)
                    if identity not in before_entities
                ]
                inverse_replayed_order = [
                    identity for identity in after_order if identity in before_entities
                ] + [
                    identity
                    for identity in sorted(before_entities)
                    if identity not in after_entities
                ]
                if (
                    replayed_order != after_order
                    or inverse_replayed_order != before_order
                ):
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
    before_plain = _plain(before)
    after_plain = _plain(after)
    change_set = ChangeSet.from_changes(
        before_fingerprint=fingerprint_model(before_plain),
        after_fingerprint=fingerprint_model(after_plain),
        changes=_diff(before_plain, after_plain, ()),
    )
    reproduced = change_set.apply(before_plain)
    if fingerprint_model(reproduced) != change_set.after_fingerprint:
        raise ValueError("generated semantic diff does not reproduce its after fingerprint")
    return change_set


def subset_change_set(
    before: Mapping[str, Any],
    source: ChangeSet,
    predicate: Any,
) -> ChangeSet:
    """Project a verified change set while preserving a reproducible target."""

    before_plain = _plain(before)
    if fingerprint_model(before_plain) != source.before_fingerprint:
        raise ValueError("source change set does not match the supplied before state")
    target = copy.deepcopy(before_plain)
    selected = [change for change in source.changes if predicate(change)]
    selected.sort(key=lambda change: (change.path[-1] == ORDER_TOKEN, change.path))
    for change in selected:
        current = _value_at(target, change.path)
        if (
            change.path[-1] == ORDER_TOKEN
            and change.after_present
            and (
                not isinstance(current, (list, tuple))
                or set(current) != set(change.after)
            )
        ):
            raise ValueError(
                "projected collection membership is stale: {}".format(
                    "/".join(change.path)
                )
            )
        if (
            change.path[-1] != ORDER_TOKEN
            and change.before_present
            and current != change.before
        ):
            raise ValueError("projected change path has stale content: {}".format("/".join(change.path)))
        _set_at(target, change.path, change.after, change.after_present)
    return diff_models(before_plain, target)


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

    current_plain = _plain(current)
    conflicts: list[Tuple[str, ...]] = []
    pending: list[SemanticChange] = []
    order_changes: list[SemanticChange] = []
    for change in original.changes:
        if change.path[-1] == ORDER_TOKEN:
            order_changes.append(change)
            continue
        value = _value_at(current_plain, change.path)
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
            pending.append(change)
        elif not matches_before:
            conflicts.append(change.path)
    if conflicts:
        return None, tuple(conflicts)
    target = copy.deepcopy(current_plain)
    for change in pending:
        _set_at(target, change.path, change.before, change.before_present)
    for change in order_changes:
        live_value = _value_at(current_plain, change.path)
        target_value = _value_at(target, change.path)
        if live_value is MISSING or target_value is MISSING:
            conflicts.append(change.path)
            continue
        live_order = [str(identity) for identity in live_value]
        target_order = [str(identity) for identity in target_value]
        before_order = [str(identity) for identity in change.before]
        after_order = [str(identity) for identity in change.after]
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
        _set_at(target, change.path, rebased_order, True)
    if conflicts:
        return None, tuple(conflicts)
    return diff_models(current_plain, target), ()


__all__ = [
    "ChangeSet",
    "SUPPORTED_DOCUMENT_ROOTS",
    "SemanticChange",
    "canonical_json",
    "diff_models",
    "fingerprint_model",
    "public_change_dict",
    "revert_change_set_onto",
    "subset_change_set",
]
