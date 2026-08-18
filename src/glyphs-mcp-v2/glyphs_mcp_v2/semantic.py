"""Canonical detached document models and deterministic semantic patches."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence, Tuple


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
    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
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


def _value_at(model: Any, path: Sequence[str]) -> Any:
    current = model
    for part in path:
        if isinstance(current, Mapping):
            if part not in current:
                return MISSING
            current = current[part]
        elif isinstance(current, (list, tuple)):
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
            current = current[int(part)]
        else:
            raise ValueError("change path traverses a scalar: {}".format("/".join(path)))
    leaf = path[-1]
    if isinstance(current, list):
        index = int(leaf)
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
        for change in self.changes:
            current = _value_at(result, change.path)
            if verify_before:
                if change.before_present and current is MISSING:
                    raise ValueError("change path is missing: {}".format("/".join(change.path)))
                if not change.before_present and current is not MISSING:
                    raise ValueError("change path unexpectedly exists: {}".format("/".join(change.path)))
                if change.before_present and current != change.before:
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
    for change in source.changes:
        if not predicate(change):
            continue
        current = _value_at(target, change.path)
        if change.before_present and current != change.before:
            raise ValueError("projected change path has stale content: {}".format("/".join(change.path)))
        _set_at(target, change.path, change.after, change.after_present)
    return diff_models(before_plain, target)


def revert_change_set_onto(
    current: Mapping[str, Any],
    original: ChangeSet,
) -> tuple[ChangeSet | None, tuple[Tuple[str, ...], ...]]:
    """Build a non-overwriting inverse of ``original`` on ``current``.

    A path is safe only while it still contains the value written by the
    original change. Unrelated later fields are preserved; overlapping later
    edits are returned as conflicts and no partial patch is produced.
    """

    current_plain = _plain(current)
    conflicts: list[Tuple[str, ...]] = []
    for change in original.changes:
        value = _value_at(current_plain, change.path)
        if change.after_present:
            if value is MISSING or value != change.after:
                conflicts.append(change.path)
        elif value is not MISSING:
            conflicts.append(change.path)
    if conflicts:
        return None, tuple(conflicts)
    target = copy.deepcopy(current_plain)
    for change in original.changes:
        _set_at(target, change.path, change.before, change.before_present)
    return diff_models(current_plain, target), ()


__all__ = [
    "ChangeSet",
    "SUPPORTED_DOCUMENT_ROOTS",
    "SemanticChange",
    "canonical_json",
    "diff_models",
    "fingerprint_model",
    "revert_change_set_onto",
    "subset_change_set",
]
