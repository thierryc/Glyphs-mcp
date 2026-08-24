"""Identity-aware operations for ordered canonical entity collections.

The canonical wire model deliberately remains ordinary JSON lists.  This
module supplies the missing semantic layer: entities are addressed by stable
``id`` values while order is represented independently.  Native adapters and
domain workflows can therefore share one collection model without importing
Glyphs or teaching the generic diff engine about individual domains.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Iterable, Mapping, MutableSequence, Sequence


IDENTITY_COLLECTION_ROOTS = frozenset(
    {
        "axes", "masters", "instances", "features", "classes",
        "featurePrefixes", "metrics", "stems", "numbers",
    }
)
IDENTITY_COLLECTION_PATHS = (
    *((root,) for root in sorted(IDENTITY_COLLECTION_ROOTS)),
    ("font", "customParameters"),
    ("font", "properties"),
    ("masters", "*", "customParameters"),
    ("masters", "*", "properties"),
    ("masters", "*", "guides"),
    ("masters", "*", "metricValues"),
    ("masters", "*", "stemValues"),
    ("masters", "*", "numberValues"),
    ("instances", "*", "customParameters"),
    ("instances", "*", "properties"),
    ("glyphs", "*", "layers"),
    ("glyphs", "*", "smartAxes"),
    ("glyphs", "*", "layers", "*", "anchors"),
    ("glyphs", "*", "layers", "*", "annotations"),
    ("glyphs", "*", "layers", "*", "guides"),
    ("glyphs", "*", "layers", "*", "hints"),
    ("glyphs", "*", "layers", "*", "shapes"),
    ("glyphs", "*", "layers", "*", "background", "anchors"),
    ("glyphs", "*", "layers", "*", "background", "annotations"),
    ("glyphs", "*", "layers", "*", "background", "guides"),
    ("glyphs", "*", "layers", "*", "background", "hints"),
    ("glyphs", "*", "layers", "*", "background", "shapes"),
    ("glyphs", "*", "layers", "*", "shapes", "*", "value", "nodes"),
)
IDENTITY_SEQUENCE_PATHS = (
    ("glyphOrder",),
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


def is_identity_sequence_path(path: Sequence[str]) -> bool:
    """Return whether ``path`` stores order and membership as identity tokens.

    Most canonical collections store entity records and expose their order
    through ``$order``. A small number of format fields are themselves an
    ordered identity sequence. Registering those paths keeps diff, replay and
    selective revert generic without pretending their tokens are entities.
    """

    normalized = tuple(str(part) for part in path)
    return any(_path_matches(pattern, normalized) for pattern in IDENTITY_SEQUENCE_PATHS)


def identity_sequence(value: Any) -> list[str] | None:
    """Return a validated ordered identity sequence, or ``None``."""

    if not isinstance(value, (list, tuple)):
        return None
    result = [str(identity) for identity in value]
    if (
        any(not identity or identity == ORDER_TOKEN for identity in result)
        or len(result) != len(set(result))
    ):
        return None
    return result


def revert_identity_sequence_onto(
    current: Sequence[Any], before: Sequence[Any], after: Sequence[Any]
) -> list[str] | None:
    """Rebase one ordered-membership inverse without overwriting later IDs.

    Identities outside the original before/after universe belong to later
    operations and retain both their slots and relative order. Original
    additions are removed, original removals are restored, and retained
    identities return to their prior order. A third ordering of retained
    identities is a real overlap and is refused conservatively.
    """

    live = identity_sequence(current)
    original_before = identity_sequence(before)
    original_after = identity_sequence(after)
    if live is None or original_before is None or original_after is None:
        return None

    universe = set(original_before) | set(original_after)
    live_related = [identity for identity in live if identity in universe]
    live_related_set = set(live_related)
    projected_before = [
        identity for identity in original_before if identity in live_related_set
    ]
    projected_after = [
        identity for identity in original_after if identity in live_related_set
    ]
    if live_related not in (projected_before, projected_after):
        return None

    added = set(original_after) - set(original_before)
    removed = set(original_before) - set(original_after)
    target = [identity for identity in live if identity not in added]

    # Restore missing original identities relative to the nearest surviving
    # original successor. If no successor survives, append after the nearest
    # predecessor; with no surviving anchor, use the original leading slot.
    for identity in original_before:
        if identity not in removed or identity in target:
            continue
        original_index = original_before.index(identity)
        successor = next(
            (
                candidate
                for candidate in original_before[original_index + 1 :]
                if candidate in target
            ),
            None,
        )
        if successor is not None:
            target.insert(target.index(successor), identity)
            continue
        predecessor = next(
            (
                candidate
                for candidate in reversed(original_before[:original_index])
                if candidate in target
            ),
            None,
        )
        if predecessor is not None:
            target.insert(target.index(predecessor) + 1, identity)
        else:
            target.insert(min(original_index, len(target)), identity)

    target_related_set = universe & set(target)
    desired = [
        identity for identity in original_before if identity in target_related_set
    ]
    replacement = iter(desired)
    return [
        next(replacement) if identity in target_related_set else identity
        for identity in target
    ]


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


def canonical_kerning_domain(
    value: Any,
    *,
    glyph_names: Iterable[str],
    native_aliases: Mapping[str, str] | None = None,
    normalize_value: Callable[[Any], Any] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Normalize a directional kerning tree to semantic glyph identities.

    Glyphs serializes glyph kerning keys as names, while live dictionaries may
    expose native object IDs. Group/class keys and unresolved references remain
    unchanged. Exact glyph names deliberately win over native aliases because
    serialized documents are the source-neutral authority at this boundary.
    """

    names = {
        str(name): canonical_glyph_id(str(name))
        for name in glyph_names
        if str(name)
    }
    aliases = {
        str(key): str(identity)
        for key, identity in (native_aliases or {}).items()
        if str(key) and str(identity)
    }

    def resolve(raw: Any) -> str:
        key = str(raw)
        if key.startswith("@"):
            return key
        return names.get(key, aliases.get(key, key))

    normalize = normalize_value or (lambda item: item)
    result: dict[str, dict[str, dict[str, Any]]] = {}
    if not isinstance(value, Mapping):
        return result
    for raw_master, raw_lefts in value.items():
        if not isinstance(raw_lefts, Mapping):
            continue
        master_id = str(raw_master)
        for raw_left, raw_rights in raw_lefts.items():
            if not isinstance(raw_rights, Mapping):
                continue
            left = resolve(raw_left)
            for raw_right, raw_value in raw_rights.items():
                result.setdefault(master_id, {}).setdefault(left, {})[
                    resolve(raw_right)
                ] = normalize(raw_value)
    return result


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
    "IDENTITY_SEQUENCE_PATHS",
    "ORDER_TOKEN",
    "canonical_glyph_id",
    "collection_order",
    "entity_id",
    "find_entity_index",
    "identity_collection_ancestor",
    "identity_collection_paths",
    "identity_order_change_required",
    "identity_sequence",
    "indexed_entities",
    "is_identity_collection_path",
    "is_identity_sequence_path",
    "move_entity",
    "reorder_entities",
    "replace_entity",
    "revert_identity_sequence_onto",
    "require_indexed_entities",
]
