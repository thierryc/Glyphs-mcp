"""Pure saved-source overlay projection with no Glyphs or AppKit imports."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from .canonical_collections import find_entity_index
from .canonical_views import layer_anchors, layer_paths


@dataclass(frozen=True)
class LayerOverlay:
    visible: bool
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


def _anchor_positions(layer: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(anchor.get("id") or "anchor:{}".format(index)): copy.deepcopy(
            anchor.get("position")
        )
        for index, anchor in enumerate(layer_anchors(layer))
    }


def overlay_for_layer(
    *,
    baseline_model: Optional[Mapping[str, Any]],
    glyph_name: str,
    layer_key: str,
    live_layer: Mapping[str, Any],
) -> LayerOverlay:
    """Compare one live layer directly with the decoded source on disk."""

    if not isinstance(baseline_model, Mapping) or not glyph_name or not layer_key:
        return _empty()
    glyphs = baseline_model.get("glyphs")
    if not isinstance(glyphs, Mapping):
        return _empty()
    baseline = _layer(glyphs.get(glyph_name), layer_key)
    if baseline is None:
        return _empty()

    baseline_paths = tuple(layer_paths(baseline))
    current_paths = tuple(layer_paths(live_layer))
    baseline_anchors = _anchor_positions(baseline)
    current_anchors = _anchor_positions(live_layer)
    if (
        baseline_paths == current_paths
        and baseline_anchors == current_anchors
        and baseline.get("width") == live_layer.get("width")
    ):
        return _empty()

    return LayerOverlay(
        visible=True,
        glyph_name=glyph_name,
        layer_key=layer_key,
        baseline_paths=tuple(copy.deepcopy(list(baseline_paths))),
        current_paths=tuple(copy.deepcopy(list(current_paths))),
        baseline_anchors=baseline_anchors,
        current_anchors=current_anchors,
        baseline_width=(
            float(baseline["width"]) if baseline.get("width") is not None else None
        ),
        current_width=(
            float(live_layer["width"])
            if live_layer.get("width") is not None
            else None
        ),
    )


__all__ = ["LayerOverlay", "overlay_for_layer"]
