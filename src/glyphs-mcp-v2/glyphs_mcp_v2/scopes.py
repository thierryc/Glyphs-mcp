"""Pure, reusable selectors for bounded Glyphs MCP reads and reviews."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence


LAYER_ROLES = frozenset(
    {"master", "intermediate", "alternate", "backup", "smart", "color"}
)
KERNING_DIRECTIONS = frozenset({"ltr", "rtl", "vertical"})
KERNING_ENTRY_KINDS = frozenset({"pair", "context"})


def _strings(value: Any) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return set()
    return {str(item) for item in value if str(item)}


def _normalized_strings(value: Any) -> set[str]:
    return {item.lower() for item in _strings(value)}


def glyph_matches_scope(glyph: Mapping[str, Any], scope: Mapping[str, Any] | None) -> bool:
    """Return whether one canonical glyph satisfies a closed glyph scope."""

    selected = scope or {}
    names = _strings(selected.get("glyphNames"))
    if names and str(glyph.get("name") or "") not in names:
        return False
    exporting = selected.get("exporting")
    if exporting is not None and bool(glyph.get("export", True)) is not bool(exporting):
        return False
    categories = _normalized_strings(selected.get("categories"))
    if categories and str(glyph.get("category") or "").lower() not in categories:
        return False
    subcategories = _normalized_strings(selected.get("subCategories"))
    if subcategories and str(glyph.get("subCategory") or "").lower() not in subcategories:
        return False
    scripts = _normalized_strings(selected.get("scripts"))
    script = str(glyph.get("script") or "").lower()
    if scripts and script not in scripts:
        if script or not bool(selected.get("includeScriptless", False)):
            return False
    return True


def selected_glyph_names(
    glyphs: Mapping[str, Any], scope: Mapping[str, Any] | None
) -> tuple[str, ...]:
    return tuple(
        str(name)
        for name in sorted(glyphs)
        if isinstance(glyphs[name], Mapping)
        and glyph_matches_scope(glyphs[name], scope)
    )


def layer_matches_scope(
    glyph: Mapping[str, Any],
    layer: Mapping[str, Any],
    scope: Mapping[str, Any] | None,
) -> bool:
    selected = scope or {}
    if not glyph_matches_scope(glyph, selected.get("glyphs")):
        return False
    layer_ids = _strings(selected.get("layerIds"))
    if layer_ids and str(layer.get("id") or "") not in layer_ids:
        return False
    master_ids = _strings(selected.get("masterIds"))
    if master_ids and str(layer.get("masterId") or "") not in master_ids:
        return False
    roles = _normalized_strings(selected.get("roles"))
    unknown = roles - LAYER_ROLES
    if unknown:
        raise ValueError("unsupported layer roles: {}".format(", ".join(sorted(unknown))))
    layer_roles = _normalized_strings(layer.get("roles"))
    if bool(layer.get("isMasterLayer")):
        layer_roles.add("master")
    return not roles or bool(roles.intersection(layer_roles))


def validate_kerning_scope(scope: Mapping[str, Any] | None) -> None:
    selected = scope or {}
    directions = _normalized_strings(selected.get("directions"))
    unknown_directions = directions - KERNING_DIRECTIONS
    if unknown_directions:
        raise ValueError(
            "unsupported kerning directions: {}".format(
                ", ".join(sorted(unknown_directions))
            )
        )
    kinds = _normalized_strings(selected.get("entryKinds"))
    unknown_kinds = kinds - KERNING_ENTRY_KINDS
    if unknown_kinds:
        raise ValueError(
            "unsupported kerning entry kinds: {}".format(
                ", ".join(sorted(unknown_kinds))
            )
        )


def kerning_entry_matches_scope(
    entry: Mapping[str, Any], scope: Mapping[str, Any] | None
) -> bool:
    selected = scope or {}
    validate_kerning_scope(selected)
    master_ids = _strings(selected.get("masterIds"))
    if master_ids and str(entry.get("masterId") or "") not in master_ids:
        return False
    kinds = _normalized_strings(selected.get("entryKinds"))
    if kinds and str(entry.get("entryKind") or "").lower() not in kinds:
        return False
    directions = _normalized_strings(selected.get("directions"))
    if (
        directions
        and entry.get("entryKind") == "pair"
        and str(entry.get("direction") or "ltr").lower() not in directions
    ):
        return False
    left_keys = _strings(selected.get("leftKeys"))
    right_keys = _strings(selected.get("rightKeys"))
    left = entry.get("left") if isinstance(entry.get("left"), Mapping) else {}
    right = entry.get("right") if isinstance(entry.get("right"), Mapping) else {}
    if left_keys and not {str(left.get("id") or ""), str(left.get("name") or "")}.intersection(left_keys):
        return False
    if right_keys and not {str(right.get("id") or ""), str(right.get("name") or "")}.intersection(right_keys):
        return False
    return True


def scope_values(scope: Mapping[str, Any] | None, name: str) -> tuple[str, ...]:
    """Expose one normalized selector field without duplicating parsing."""

    return tuple(sorted(_strings((scope or {}).get(name))))


__all__ = [
    "KERNING_DIRECTIONS",
    "KERNING_ENTRY_KINDS",
    "LAYER_ROLES",
    "glyph_matches_scope",
    "kerning_entry_matches_scope",
    "layer_matches_scope",
    "scope_values",
    "selected_glyph_names",
    "validate_kerning_scope",
]
