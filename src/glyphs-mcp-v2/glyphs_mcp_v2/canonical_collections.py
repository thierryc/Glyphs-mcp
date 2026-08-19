"""Identity-aware operations for ordered canonical entity collections.

The canonical wire model deliberately remains ordinary JSON lists.  This
module supplies the missing semantic layer: entities are addressed by stable
``id`` values while order is represented independently.  Native adapters and
domain workflows can therefore share one collection model without importing
Glyphs or teaching the generic diff engine about individual domains.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, MutableSequence, Sequence


IDENTITY_COLLECTION_ROOTS = frozenset(
    {"masters", "instances", "features", "classes", "featurePrefixes"}
)
ORDER_TOKEN = "$order"


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
    "IDENTITY_COLLECTION_ROOTS",
    "ORDER_TOKEN",
    "collection_order",
    "entity_id",
    "find_entity_index",
    "indexed_entities",
    "move_entity",
    "reorder_entities",
    "replace_entity",
    "require_indexed_entities",
]
