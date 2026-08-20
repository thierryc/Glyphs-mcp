"""Identity-aware operations for ordered canonical entity collections.

The canonical wire model deliberately remains ordinary JSON lists.  This
module supplies the missing semantic layer: entities are addressed by stable
``id`` values while order is represented independently.  Native adapters and
domain workflows can therefore share one collection model without importing
Glyphs or teaching the generic diff engine about individual domains.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping, MutableSequence, Sequence


IDENTITY_COLLECTION_ROOTS = frozenset(
    {"masters", "instances", "features", "classes", "featurePrefixes"}
)
IDENTITY_COLLECTION_PATHS = (
    *((root,) for root in sorted(IDENTITY_COLLECTION_ROOTS)),
    ("glyphs", "*", "layers"),
)
ORDER_TOKEN = "$order"


def _path_matches(pattern: Sequence[str], path: Sequence[str]) -> bool:
    return len(pattern) == len(path) and all(
        expected == "*" or expected == actual
        for expected, actual in zip(pattern, path)
    )


def is_identity_collection_path(path: Sequence[str]) -> bool:
    """Return whether ``path`` names a registered ordered entity collection.

    Registrations, rather than domain branches in the diff engine, are the
    extension point. A schema may therefore add another nested collection by
    declaring its path shape here while retaining the same semantic patch,
    composition, selective-revert, and order rules.
    """

    normalized = tuple(str(part) for part in path)
    return any(_path_matches(pattern, normalized) for pattern in IDENTITY_COLLECTION_PATHS)


def identity_collection_ancestor(path: Sequence[str]) -> tuple[str, ...] | None:
    """Return the registered collection prefix containing ``path``."""

    normalized = tuple(str(part) for part in path)
    matches = [
        normalized[: len(pattern)]
        for pattern in IDENTITY_COLLECTION_PATHS
        if len(normalized) >= len(pattern)
        and _path_matches(pattern, normalized[: len(pattern)])
    ]
    return max(matches, key=len) if matches else None


def identity_collection_paths(paths: Iterable[Sequence[str]]) -> tuple[tuple[str, ...], ...]:
    """Return every concrete registered collection referenced by paths."""

    values = {
        collection
        for path in paths
        if (collection := identity_collection_ancestor(path)) is not None
    }
    return tuple(sorted(values))


def identity_order_change_required(
    before_order: Sequence[str], after_order: Sequence[str]
) -> bool:
    """Return whether minimal sorted membership replay needs an order patch."""

    before = [str(identity) for identity in before_order]
    after = [str(identity) for identity in after_order]
    before_set = set(before)
    after_set = set(after)
    replayed = [identity for identity in before if identity in after_set] + sorted(
        after_set - before_set
    )
    inverse_replayed = [identity for identity in after if identity in before_set] + sorted(
        before_set - after_set
    )
    return replayed != after or inverse_replayed != before


def canonical_glyph_id(name: str) -> str:
    """Return the stable semantic ID for one name-keyed glyph entity."""

    return "glyph_{}".format(str(name))


def entity_id(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    return str(value.get("id") or "")


def indexed_entities(value: Any) -> tuple[list[str], dict[str, Mapping[str, Any]]] | None:
    """Return validated order and entities, or ``None`` for a positional list."""

    if not isinstance(value, (list, tuple)):
        return None
    order: list[str] = []
    entities: dict[str, Mapping[str, Any]] = {}
    for item in value:
        identity = entity_id(item)
        if not identity or identity == ORDER_TOKEN or identity in entities:
            return None
        order.append(identity)
        entities[identity] = item
    return order, entities


def require_indexed_entities(value: Any, root: str) -> tuple[list[str], dict[str, Mapping[str, Any]]]:
    indexed = indexed_entities(value)
    if indexed is None:
        raise ValueError("{} requires unique non-empty canonical entity IDs".format(root))
    return indexed


def find_entity_index(collection: Sequence[Any], identity: str) -> int | None:
    for index, item in enumerate(collection):
        if entity_id(item) == identity:
            return index
    return None


def collection_order(collection: Sequence[Any]) -> list[str]:
    indexed = indexed_entities(collection)
    if indexed is None:
        raise ValueError("ordered canonical collection has invalid entity IDs")
    return indexed[0]


def replace_entity(
    collection: MutableSequence[Any], identity: str, value: Any, *, present: bool
) -> None:
    index = find_entity_index(collection, identity)
    if present:
        replacement = copy.deepcopy(value)
        if entity_id(replacement) != identity:
            raise ValueError("canonical entity identity does not match its change path")
        if index is None:
            collection.append(replacement)
        else:
            collection[index] = replacement
    elif index is not None:
        del collection[index]


def reorder_entities(collection: MutableSequence[Any], order: Sequence[str]) -> None:
    current_order, entities = require_indexed_entities(collection, "collection")
    requested = [str(value) for value in order]
    if len(requested) != len(set(requested)) or set(requested) != set(current_order):
        raise ValueError("canonical collection order must contain every entity exactly once")
    collection[:] = [copy.deepcopy(entities[identity]) for identity in requested]


def move_entity(collection: MutableSequence[Any], identity: str, index: int) -> None:
    current = find_entity_index(collection, identity)
    if current is None:
        raise ValueError("unknown canonical entity: {}".format(identity))
    bounded = int(index)
    if bounded < 0 or bounded >= len(collection):
        raise ValueError("collection index is out of range")
    item = collection.pop(current)
    collection.insert(bounded, item)


__all__ = [
    "IDENTITY_COLLECTION_PATHS",
    "IDENTITY_COLLECTION_ROOTS",
    "ORDER_TOKEN",
    "canonical_glyph_id",
    "collection_order",
    "entity_id",
    "find_entity_index",
    "identity_collection_ancestor",
    "identity_collection_paths",
    "identity_order_change_required",
    "indexed_entities",
    "is_identity_collection_path",
    "move_entity",
    "reorder_entities",
    "replace_entity",
    "require_indexed_entities",
]
