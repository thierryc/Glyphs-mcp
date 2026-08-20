"""Pure latest-session overlay projection with no Glyphs or AppKit imports."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from .canonical_tree import CanonicalFontTree
from .canonical_collections import find_entity_index
from .change_history import SessionDiff


@dataclass(frozen=True)
class LayerOverlay:
    visible: bool
    includes_later_edits: bool
    glyph_name: Optional[str] = None
    layer_key: Optional[str] = None
    baseline_paths: tuple[Mapping[str, Any], ...] = ()
    current_paths: tuple[Mapping[str, Any], ...] = ()
    baseline_anchors: Mapping[str, Any] = field(default_factory=dict)
    current_anchors: Mapping[str, Any] = field(default_factory=dict)
    baseline_width: Optional[float] = None
    current_width: Optional[float] = None


def _empty() -> LayerOverlay:
    return LayerOverlay(
        visible=False,
        includes_later_edits=False,
        baseline_anchors={},
        current_anchors={},
    )


def _layer(glyph: Any, layer_key: str) -> Optional[Mapping[str, Any]]:
    if not isinstance(glyph, Mapping):
        return None
    layers = glyph.get("layers")
    if isinstance(layers, Mapping):
        value = layers.get(layer_key)
    elif isinstance(layers, (list, tuple)):
        index = find_entity_index(layers, layer_key)
        value = layers[index] if index is not None else None
    else:
        value = None
    return value if isinstance(value, Mapping) else None


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
    recorded_visual_changed = any(
        before.get(field) != target.get(field)
        for field in ("paths", "anchors", "components", "width")
    )
    if not recorded_visual_changed:
        return _empty()
    visual_fields = ("paths", "anchors", "components", "width")
    live_visual_changed = any(before.get(field) != live_layer.get(field) for field in visual_fields)
    if not live_visual_changed:
        return _empty()
    includes_later_edits = any(target.get(field) != live_layer.get(field) for field in visual_fields)
    return LayerOverlay(
        visible=True,
        includes_later_edits=includes_later_edits,
        glyph_name=glyph_name,
        layer_key=layer_key,
        baseline_paths=tuple(copy.deepcopy(list(before.get("paths") or []))),
        current_paths=tuple(copy.deepcopy(list(live_layer.get("paths") or []))),
        baseline_anchors=copy.deepcopy(dict(before.get("anchors") or {})),
        current_anchors=copy.deepcopy(dict(live_layer.get("anchors") or {})),
        baseline_width=float(before["width"]) if before.get("width") is not None else None,
        current_width=float(live_layer["width"]) if live_layer.get("width") is not None else None,
    )


__all__ = ["LayerOverlay", "overlay_for_layer"]
