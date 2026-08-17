"""Pure latest-session overlay projection with no Glyphs or AppKit imports."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from .canonical_tree import CanonicalFontTree
from .change_history import SessionDiff


@dataclass(frozen=True)
class LayerOverlay:
    visible: bool
    stale: bool
    glyph_name: Optional[str] = None
    layer_key: Optional[str] = None
    before_paths: tuple[Mapping[str, Any], ...] = ()
    target_paths: tuple[Mapping[str, Any], ...] = ()
    before_anchors: Mapping[str, Any] = field(default_factory=dict)
    target_anchors: Mapping[str, Any] = field(default_factory=dict)
    before_width: Optional[float] = None
    target_width: Optional[float] = None


def _empty() -> LayerOverlay:
    return LayerOverlay(visible=False, stale=False, before_anchors={}, target_anchors={})


def _layer(glyph: Any, layer_key: str) -> Optional[Mapping[str, Any]]:
    if not isinstance(glyph, Mapping):
        return None
    layers = glyph.get("layers")
    if not isinstance(layers, Mapping):
        return None
    value = layers.get(layer_key)
    return value if isinstance(value, Mapping) else None


def _value_at(value: Any, path: tuple[str, ...]) -> tuple[bool, Any]:
    current = value
    for part in path:
        if isinstance(current, Mapping):
            if part not in current:
                return False, None
            current = current[part]
        elif isinstance(current, (list, tuple)):
            try:
                index = int(part)
            except (TypeError, ValueError):
                return False, None
            if index < 0 or index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def overlay_for_layer(
    *,
    trees: CanonicalFontTree,
    session: Optional[SessionDiff],
    glyph_name: str,
    layer_key: str,
    live_layer: Mapping[str, Any],
) -> LayerOverlay:
    if session is None or not glyph_name or not layer_key:
        return _empty()
    relevant = tuple(
        change
        for change in session.change_set.changes
        if len(change.path) >= 4
        and change.path[0] == "glyphs"
        and change.path[1] == glyph_name
        and change.path[2] == "layers"
        and change.path[3] == layer_key
    )
    affected = bool(relevant)
    if not affected:
        return _empty()
    before = _layer(trees.glyph(session.before_tree_hash, glyph_name), layer_key)
    target = _layer(trees.glyph(session.after_tree_hash, glyph_name), layer_key)
    if before is None or target is None:
        return _empty()
    visual_changed = any(
        before.get(field) != target.get(field)
        for field in ("paths", "anchors", "components", "width", "LSB", "RSB")
    )
    if not visual_changed:
        return _empty()
    stale = False
    for change in relevant:
        present, value = _value_at(live_layer, tuple(change.path[4:]))
        if present != change.after_present or (present and value != change.after):
            stale = True
            break
    return LayerOverlay(
        visible=True,
        stale=stale,
        glyph_name=glyph_name,
        layer_key=layer_key,
        before_paths=tuple(copy.deepcopy(list(before.get("paths") or []))),
        target_paths=tuple(copy.deepcopy(list(target.get("paths") or []))),
        before_anchors=copy.deepcopy(dict(before.get("anchors") or {})),
        target_anchors=copy.deepcopy(dict(target.get("anchors") or {})),
        before_width=float(before["width"]) if before.get("width") is not None else None,
        target_width=float(target["width"]) if target.get("width") is not None else None,
    )


__all__ = ["LayerOverlay", "overlay_for_layer"]
