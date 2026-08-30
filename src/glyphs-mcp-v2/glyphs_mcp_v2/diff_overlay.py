"""Pure geometry-only saved-source diff plans with no Glyphs/AppKit imports."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional

from .canonical_collections import find_entity_index
from .canonical_views import layer_anchors, layer_paths
from .diff_geometry import (
    DifferenceBand,
    DifferenceTopologyError,
    PathSegment,
    difference_bands,
    path_segments,
)


def _visual_path(path: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            "closed": bool(path.get("closed")),
            "nodes": tuple(
                MappingProxyType(
                    {
                        "x": float(node.get("x", 0.0)),
                        "y": float(node.get("y", 0.0)),
                        "type": str(node.get("type") or "line"),
                    }
                )
                for node in path.get("nodes") or ()
                if isinstance(node, Mapping)
            ),
        }
    )


def _visual_json(paths, anchors, width):
    return {
        "paths": tuple(
            {
                "closed": bool(path.get("closed")),
                "nodes": tuple(
                    {
                        "x": float(node.get("x", 0.0)),
                        "y": float(node.get("y", 0.0)),
                        "type": str(node.get("type") or "line"),
                    }
                    for node in path.get("nodes") or ()
                ),
            }
            for path in paths
        ),
        "anchors": dict(anchors),
        "width": width,
    }


def _anchor_positions(layer: Mapping[str, Any]) -> Mapping[str, tuple[float, float]]:
    return MappingProxyType(
        {
            str(anchor.get("id") or "anchor:{}".format(index)): (
                float((anchor.get("position") or (0.0, 0.0))[0]),
                float((anchor.get("position") or (0.0, 0.0))[1]),
            )
            for index, anchor in enumerate(layer_anchors(layer))
        }
    )


@dataclass(frozen=True)
class LayerVisualState:
    paths: tuple[Mapping[str, Any], ...]
    anchors: Mapping[str, tuple[float, float]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    width: Optional[float] = None
    fingerprint: str = ""

    @classmethod
    def from_layer(cls, layer: Mapping[str, Any]) -> "LayerVisualState":
        paths = tuple(_visual_path(path) for path in layer_paths(layer))
        anchors = _anchor_positions(layer)
        width = float(layer["width"]) if layer.get("width") is not None else None
        encoded = json.dumps(
            _visual_json(paths, anchors, width),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            paths=paths,
            anchors=anchors,
            width=width,
            fingerprint="sha256:{}".format(hashlib.sha256(encoded).hexdigest()),
        )


@dataclass(frozen=True)
class LayerDiffPlan:
    visible: bool
    glyph_name: Optional[str] = None
    layer_key: Optional[str] = None
    baseline_paths: tuple[Mapping[str, Any], ...] = ()
    current_paths: tuple[Mapping[str, Any], ...] = ()
    baseline_anchors: Mapping[str, tuple[float, float]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    current_anchors: Mapping[str, tuple[float, float]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    baseline_width: Optional[float] = None
    current_width: Optional[float] = None
    baseline_segments: tuple[tuple[PathSegment, ...], ...] = ()
    bands: tuple[DifferenceBand, ...] = ()
    topology_compatible: bool = True
    live_fingerprint: str = ""


LayerOverlay = LayerDiffPlan


@dataclass(frozen=True)
class SavedLayerGeometry:
    state: LayerVisualState
    segments: tuple[tuple[PathSegment, ...], ...]


class SavedLayerGeometryCache:
    """Bounded content-addressed cache used only by background diff work."""

    def __init__(self, *, capacity: int = 128) -> None:
        self.capacity = max(1, int(capacity))
        self._values: "OrderedDict[tuple[str, str, str], SavedLayerGeometry]" = (
            OrderedDict()
        )

    def get_or_prepare(
        self,
        *,
        source_fingerprint: str,
        baseline_model: Optional[Mapping[str, Any]],
        glyph_name: str,
        layer_key: str,
    ) -> SavedLayerGeometry | None:
        key = (str(source_fingerprint), str(glyph_name), str(layer_key))
        cached = self._values.get(key)
        if cached is not None:
            self._values.move_to_end(key)
            return cached
        if not isinstance(baseline_model, Mapping):
            return None
        glyphs = baseline_model.get("glyphs")
        if not isinstance(glyphs, Mapping):
            return None
        layer = _layer(glyphs.get(glyph_name), layer_key)
        if layer is None:
            return None
        state = LayerVisualState.from_layer(layer)
        prepared = SavedLayerGeometry(
            state=state,
            segments=tuple(path_segments(path) for path in state.paths),
        )
        self._values[key] = prepared
        while len(self._values) > self.capacity:
            self._values.popitem(last=False)
        return prepared

    def clear(self) -> None:
        self._values.clear()


def _empty() -> LayerDiffPlan:
    return LayerDiffPlan(visible=False)


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


def build_layer_diff_plan(
    *,
    baseline_model: Optional[Mapping[str, Any]],
    glyph_name: str,
    layer_key: str,
    live_state: LayerVisualState,
    saved_geometry: SavedLayerGeometry | None = None,
) -> LayerDiffPlan:
    """Prepare every geometry comparison away from the drawing callback."""

    if not glyph_name or not layer_key:
        return _empty()
    if saved_geometry is None:
        if not isinstance(baseline_model, Mapping):
            return _empty()
        glyphs = baseline_model.get("glyphs")
        if not isinstance(glyphs, Mapping):
            return _empty()
        baseline_layer = _layer(glyphs.get(glyph_name), layer_key)
        if baseline_layer is None:
            return _empty()
        baseline = LayerVisualState.from_layer(baseline_layer)
        saved_segments = tuple(path_segments(path) for path in baseline.paths)
    else:
        baseline = saved_geometry.state
        saved_segments = saved_geometry.segments
    if (
        baseline.paths == live_state.paths
        and baseline.anchors == live_state.anchors
        and baseline.width == live_state.width
    ):
        return _empty()

    try:
        bands = difference_bands(baseline.paths, live_state.paths)
        topology_compatible = True
    except DifferenceTopologyError:
        bands = ()
        topology_compatible = False
    return LayerDiffPlan(
        visible=True,
        glyph_name=glyph_name,
        layer_key=layer_key,
        baseline_paths=baseline.paths,
        current_paths=live_state.paths,
        baseline_anchors=baseline.anchors,
        current_anchors=live_state.anchors,
        baseline_width=baseline.width,
        current_width=live_state.width,
        baseline_segments=saved_segments,
        bands=bands,
        topology_compatible=topology_compatible,
        live_fingerprint=live_state.fingerprint,
    )


def overlay_for_layer(
    *,
    baseline_model: Optional[Mapping[str, Any]],
    glyph_name: str,
    layer_key: str,
    live_layer: Mapping[str, Any],
) -> LayerDiffPlan:
    """Compatibility helper for pure callers and tests."""

    return build_layer_diff_plan(
        baseline_model=baseline_model,
        glyph_name=glyph_name,
        layer_key=layer_key,
        live_state=LayerVisualState.from_layer(live_layer),
    )


__all__ = [
    "LayerDiffPlan",
    "LayerOverlay",
    "LayerVisualState",
    "SavedLayerGeometry",
    "SavedLayerGeometryCache",
    "build_layer_diff_plan",
    "overlay_for_layer",
]
