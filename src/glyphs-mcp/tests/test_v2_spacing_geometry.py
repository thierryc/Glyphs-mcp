"""Generic spacing projections and explicit physical write qualification."""

from __future__ import annotations

import asyncio
import copy
import math
import sys
import time
import unittest
from pathlib import Path
from threading import Event

from jsonschema import validate
from pydantic import ValidationError


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.activity import ActivityCancelled  # noqa: E402
from glyphs_mcp_v2.canonical_tree import CanonicalSnapshot  # noqa: E402
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.generic_tools import (  # noqa: E402
    build_change_set,
    project_reference,
    resolve_selector,
)
from glyphs_mcp_v2.semantic import fingerprint_model  # noqa: E402
from glyphs_mcp_v2.transport.fastmcp import ChangeOperation, ToolHandlers  # noqa: E402


def _path(*, locked: bool = False) -> dict:
    return {
        "id": "shape:path:0",
        "kind": "path",
        "value": {
            "closed": True,
            "locked": locked,
            "attributes": {},
            "nodes": [
                {"id": "node:0", "x": 50, "y": 0, "type": "line", "smooth": False, "locked": False, "attributes": {}},
                {"id": "node:1", "x": 450, "y": 700, "type": "line", "smooth": False, "locked": False, "attributes": {}},
            ],
        },
    }


def _component(*, alignment: int = -1, locked: bool = False) -> dict:
    return {
        "id": "shape:component:0",
        "kind": "component",
        "value": {
            "name": "H",
            "position": [20, 30],
            "scale": [1, 1],
            "angle": 0,
            "slant": [0, 0],
            "alignment": alignment,
            "locked": locked,
            "attributes": {},
        },
    }


def _layer(layer_id: str, master_id: str, *, width: float = 500) -> dict:
    return {
        "id": layer_id,
        "masterId": master_id,
        "name": "Regular",
        "roles": ["master"],
        "isMasterLayer": True,
        "isSpecialLayer": False,
        "locked": False,
        "attributes": {},
        "anchors": [
            {
                "id": "anchor:top:0",
                "name": "top",
                "position": [250, 700],
                "locked": False,
                "attributes": {},
            }
        ],
        "annotations": [],
        "guides": [],
        "hints": [],
        "shapes": [_path(), _component()],
        "userData": {},
        "width": width,
        "vertOrigin": 800,
        "vertWidth": 1000,
        "leftMetricsKey": None,
        "rightMetricsKey": None,
        "widthMetricsKey": None,
        "bottomMetricsKey": None,
        "topMetricsKey": None,
        "vertOriginMetricsKey": None,
        "vertWidthMetricsKey": None,
    }


def _glyph(name: str, *, category: str = "Letter") -> dict:
    return {
        "id": "glyph:{}".format(name),
        "name": name,
        "category": category,
        "subCategory": "Uppercase",
        "script": "latin",
        "export": True,
        "locked": False,
        "layers": [_layer("{}-master".format(name), "M1")],
    }


def _model(*, grid: float = 1, subdivision: float = 1) -> dict:
    return {
        "font": {
            "familyName": "Generic Spacing",
            "upm": 1000,
            "grid": grid,
            "gridSubDivision": subdivision,
        },
        "masters": [{"id": "M1", "name": "Regular", "axes": []}],
        "instances": [],
        "glyphs": {"A": _glyph("A"), "acutecomb": _glyph("acutecomb", category="Mark")},
        "kerning": {},
        "features": [],
        "classes": [],
        "featurePrefixes": [],
    }


def _black_y_model() -> dict:
    model = _model()
    layer = _layer("Y-black-condensed", "M1", width=1467)
    node_counts = (20, 19, 19)
    paths = []
    for path_index, node_count in enumerate(node_counts):
        nodes = []
        for node_index in range(node_count):
            x = 42 + round(1383 * node_index / max(1, node_count - 1))
            nodes.append(
                {
                    "id": "node:line:{}".format(node_index),
                    "x": x,
                    "y": path_index * 100 + node_index,
                    "type": "line",
                    "smooth": False,
                    "locked": False,
                    "attributes": {},
                }
            )
        paths.append(
            {
                "id": "shape:path:{}".format(path_index),
                "kind": "path",
                "value": {
                    "closed": True,
                    "locked": False,
                    "attributes": {},
                    "nodes": nodes,
                },
            }
        )
    layer["shapes"] = [*paths, _component(alignment=0)]
    layer["anchors"].append(
        {
            "id": "anchor:bottom:0",
            "name": "bottom",
            "position": [720, 0],
            "locked": False,
            "attributes": {},
        }
    )
    model["glyphs"] = {
        "Y": {
            **_glyph("Y"),
            "layers": [layer],
        }
    }
    return model


def _bounds(model: dict) -> dict:
    result = {}
    for name, glyph in model["glyphs"].items():
        for layer in glyph["layers"]:
            nodes = [
                node
                for shape in layer["shapes"]
                if shape["kind"] == "path"
                for node in shape["value"]["nodes"]
            ]
            xs = [node["x"] for node in nodes]
            ys = [node["y"] for node in nodes]
            result[(name, layer["id"])] = {
                "bounds": (
                    {
                        "x": min(xs),
                        "y": min(ys),
                        "width": max(xs) - min(xs),
                        "height": max(ys) - min(ys),
                    }
                    if nodes
                    else None
                ),
                "currentMetrics": {
                    "width": layer["width"],
                    "verticalOrigin": layer["vertOrigin"],
                    "verticalAdvance": layer["vertWidth"],
                },
                "resolvedMetrics": {
                    "width": layer["width"],
                    "verticalOrigin": layer["vertOrigin"],
                    "verticalAdvance": layer["vertWidth"],
                },
                "hasAlignedWidth": False,
                "isAligned": False,
            }
    return result


def _selector(name: str = "A") -> dict:
    return {
        "entity": "layer",
        "ids": ["{}-master".format(name)],
        "parent": {"glyphName": name},
    }


class _Host:
    def __init__(self, model: dict) -> None:
        self.model = copy.deepcopy(model)
        self.apply_calls = 0
        self.restore_calls = 0
        self.recovery_calls = []
        self.source_state = {
            "kind": "glyphs",
            "exists": True,
            "readable": True,
            "contentFingerprint": "sha256:source-before",
            "filePath": "/private/source/test.glyphs",
        }

    def capture_model(self, _document_id: str) -> dict:
        return copy.deepcopy(self.model)

    def apply_change_set(self, _document_id: str, change_set) -> None:
        self.apply_calls += 1
        self.model = change_set.apply(self.model)

    def restore_model(self, _document_id: str, model: dict) -> None:
        self.restore_calls += 1
        self.model = copy.deepcopy(model)

    def create_recovery_copy(self, document_id: str, execution_id: str) -> str:
        self.recovery_calls.append((document_id, execution_id))
        return "/private/recovery/{}.glyphs".format(execution_id)

    def capture_source_file_state(self, _document_id: str, include_model=False):
        return copy.deepcopy(self.source_state)

    def inspect_layers(self, _document_id, glyph_names=(), **_kwargs):
        names = set(glyph_names)
        return {
            key: value
            for key, value in _bounds(self.model).items()
            if not names or key[0] in names
        }

    def simulate_verified_change_set(
        self, _document_id, change_set, before_model, **_kwargs
    ):
        after = change_set.apply(before_model)
        return {"afterModel": after, "observations": _bounds(after)}


class _NativeRewriteHost(_Host):
    def simulate_verified_change_set(
        self, _document_id, change_set, before_model, **_kwargs
    ):
        after = change_set.apply(before_model)
        before_component = before_model["glyphs"]["A"]["layers"][0]["shapes"][1]["value"]
        after["glyphs"]["A"]["layers"][0]["shapes"][1]["value"]["position"] = copy.deepcopy(
            before_component["position"]
        )
        return {"afterModel": after, "observations": _bounds(after)}


class _NativeGridHost(_Host):
    @staticmethod
    def _snap(model: dict) -> dict:
        result = copy.deepcopy(model)
        layer = result["glyphs"]["A"]["layers"][0]
        for shape in layer["shapes"]:
            value = shape["value"]
            if shape["kind"] == "path":
                for node in value["nodes"]:
                    node["x"] = round(node["x"])
                    node["y"] = round(node["y"])
            elif shape["kind"] == "component":
                value["position"] = [round(value) for value in value["position"]]
        for anchor in layer["anchors"]:
            anchor["position"] = [round(value) for value in anchor["position"]]
        return result

    def simulate_verified_change_set(
        self, _document_id, change_set, before_model, **_kwargs
    ):
        after = self._snap(change_set.apply(before_model))
        return {"afterModel": after, "observations": _bounds(after)}

    def apply_change_set(self, _document_id: str, change_set) -> None:
        self.apply_calls += 1
        self.model = self._snap(change_set.apply(self.model))


def _aligned_inheritance_model() -> dict:
    model = _model()
    model["glyphs"]["H"] = _glyph("H")
    model["glyphs"]["H"]["layers"][0]["shapes"] = [_path()]
    aligned = model["glyphs"]["A"]["layers"][0]
    aligned["shapes"] = [_component(alignment=0)]
    aligned["width"] = 500
    return model


class _AlignedInheritanceHost(_Host):
    @staticmethod
    def _inherit(model: dict) -> dict:
        result = copy.deepcopy(model)
        result["glyphs"]["A"]["layers"][0]["width"] = result["glyphs"]["H"][
            "layers"
        ][0]["width"]
        return result

    def inspect_layers(self, document_id, glyph_names=(), **kwargs):
        observations = dict(
            super().inspect_layers(document_id, glyph_names, **kwargs)
        )
        key = ("A", "A-master")
        if key in observations:
            observations[key] = {
                **dict(observations[key]),
                "hasAlignedWidth": True,
                "isAligned": True,
            }
        return observations

    def simulate_verified_change_set(
        self, _document_id, change_set, before_model, **_kwargs
    ):
        after = self._inherit(change_set.apply(before_model))
        return {"afterModel": after, "observations": _bounds(after)}

    def apply_change_set(self, _document_id: str, change_set) -> None:
        self.apply_calls += 1
        self.model = self._inherit(change_set.apply(self.model))


class _AlignedLossHost(_AlignedInheritanceHost):
    def simulate_verified_change_set(
        self, _document_id, change_set, before_model, **_kwargs
    ):
        after = change_set.apply(before_model)
        after["glyphs"]["A"]["layers"][0]["shapes"][0]["value"][
            "alignment"
        ] = -1
        return {"afterModel": after, "observations": _bounds(after)}


class _AlignedPositionHost(_AlignedInheritanceHost):
    @staticmethod
    def _restore_position(model: dict, before_model: dict) -> dict:
        result = copy.deepcopy(model)
        result["glyphs"]["A"]["layers"][0]["shapes"][0]["value"][
            "position"
        ] = copy.deepcopy(
            before_model["glyphs"]["A"]["layers"][0]["shapes"][0]["value"][
                "position"
            ]
        )
        return result

    def simulate_verified_change_set(
        self, _document_id, change_set, before_model, **_kwargs
    ):
        after = self._restore_position(change_set.apply(before_model), before_model)
        return {"afterModel": after, "observations": _bounds(after)}

    def apply_change_set(self, _document_id: str, change_set) -> None:
        self.apply_calls += 1
        before = copy.deepcopy(self.model)
        self.model = self._restore_position(change_set.apply(self.model), before)


class _ObservationDriftHost(_Host):
    def inspect_layers(self, document_id, glyph_names=(), **kwargs):
        observations = dict(super().inspect_layers(document_id, glyph_names, **kwargs))
        if self.apply_calls:
            for key, value in list(observations.items()):
                value = dict(value)
                bounds = dict(value["bounds"])
                bounds["x"] += 1
                value["bounds"] = bounds
                observations[key] = value
                break
        return observations


class _RecoveryFailureHost(_Host):
    def __init__(self, model):
        super().__init__(model)
        self.opened_recovery = []

    def apply_change_set(self, document_id, change_set):
        super().apply_change_set(document_id, change_set)
        self.model["glyphs"]["A"]["layers"][0]["width"] += 1

    def restore_model(self, document_id, model):
        self.restore_calls += 1
        raise RuntimeError("restore failed")

    def open_recovery_copy(self, path):
        self.opened_recovery.append(path)


class _RichObservationHost(_Host):
    diagnostics = {
        "succeeded": True,
        "errorType": None,
        "errorMessage": None,
        "detached": True,
        "liveAttempted": False,
    }
    metadata = {
        "A": {
            "name": "A",
            "export": True,
            "category": "Letter",
            "subCategory": "Uppercase",
            "script": "latin",
        }
    }

    def simulate_verified_change_set(
        self, _document_id, change_set, before_model, **_kwargs
    ):
        after = change_set.apply(before_model)
        observations = dict(_bounds(after))
        observations[("__document__", "compilation.diagnostics")] = dict(
            self.diagnostics
        )
        return {
            "afterModel": after,
            "observations": observations,
            "effectiveMetadata": copy.deepcopy(self.metadata),
        }

    def inspect_compilation_diagnostics(self, _document_id):
        return dict(self.diagnostics)

    def inspect_glyph_metadata(self, _document_id, glyph_names=()):
        requested = set(glyph_names)
        return {
            name: copy.deepcopy(value)
            for name, value in self.metadata.items()
            if not requested or name in requested
        }


class _CancellablePreviewHost(_Host):
    def __init__(self, model):
        super().__init__(model)
        self.started = Event()

    def simulate_verified_change_set(
        self,
        _document_id,
        _change_set,
        _before_model,
        *,
        cancellation_checkpoint=None,
        **_kwargs,
    ):
        self.started.set()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if cancellation_checkpoint is not None:
                cancellation_checkpoint()
            time.sleep(0.002)
        raise RuntimeError("test cancellation did not reach detached work")


class V2SpacingGeometryTests(unittest.TestCase):
    def test_both_axes_are_generic_projections_with_provenance(self) -> None:
        model = _model()
        reference = resolve_selector(model, _selector())[0]
        result = project_reference(
            reference,
            {
                "fields": [
                    "width",
                    "vertOrigin",
                    "vertWidth",
                    "bounds",
                    "spacing.horizontal",
                    "spacing.vertical",
                    "geometry.counts",
                    "alignment",
                    "inheritance.metrics",
                    "ownership",
                ]
            },
            observations=_bounds(model),
        )

        self.assertEqual(
            result["values"]["spacing.horizontal"],
            {
                "advance": 500,
                "origin": None,
                "leadingBearing": 50,
                "trailingBearing": 50,
            },
        )
        self.assertEqual(
            result["values"]["spacing.vertical"],
            {
                "advance": 1000,
                "origin": 800,
                "leadingBearing": 100,
                "trailingBearing": 200,
            },
        )
        self.assertEqual(result["completeness"], "complete")
        self.assertEqual(result["values"]["ownership"]["glyphName"], "A")

    def test_explicit_horizontal_bearings_are_set_and_translate_operations(self) -> None:
        model = _model()
        build = build_change_set(
            model,
            [
                {
                    "op": "translate",
                    "target": _selector(),
                    "delta": {"x": -18, "y": 0},
                    "quantizer": "exact",
                },
                {
                    "op": "set",
                    "target": _selector(),
                    "field": "width",
                    "value": 457,
                    "quantizer": "exact",
                },
            ],
        )
        layer = build.change_set.apply(model)["glyphs"]["A"]["layers"][0]

        self.assertEqual(layer["width"], 457)
        self.assertEqual(layer["shapes"][0]["value"]["nodes"][0]["x"], 32)
        self.assertEqual(layer["shapes"][1]["value"]["position"], [2, 30])
        self.assertEqual(layer["anchors"][0]["position"], [232, 700])
        self.assertEqual(build.normalized_operations[0]["delta"], {"x": -18, "y": 0})
        self.assertEqual(build.normalized_operations[1]["value"], 457)

    def test_simultaneous_axes_translate_geometry_uniformly(self) -> None:
        model = _model()
        build = build_change_set(
            model,
            [
                {"op": "translate", "target": _selector(), "delta": {"x": 10, "y": 20}},
                {"op": "set", "target": _selector(), "field": "width", "value": 510},
                {"op": "set", "target": _selector(), "field": "vertOrigin", "value": 820},
                {"op": "set", "target": _selector(), "field": "vertWidth", "value": 950},
            ],
        )
        layer = build.change_set.apply(model)["glyphs"]["A"]["layers"][0]
        component = layer["shapes"][1]["value"]

        self.assertEqual(component["position"], [30, 50])
        self.assertEqual(component["scale"], [1, 1])
        self.assertEqual(layer["anchors"][0]["position"], [260, 720])
        self.assertEqual((layer["width"], layer["vertOrigin"], layer["vertWidth"]), (510, 820, 950))

        component_reference = resolve_selector(
            build.change_set.apply(model),
            {
                "entity": "shape",
                "ids": ["shape:component:0"],
                "parent": {"glyphName": "A", "layerId": "A-master"},
            },
        )[0]
        self.assertEqual(
            project_reference(
                component_reference, {"fields": ["geometry.transform"]}
            )["values"]["geometry.transform"][4:],
            [30.0, 50.0],
        )

    def test_translate_registry_supports_shape_node_and_anchor_targets(self) -> None:
        model = _model()
        model["glyphs"]["A"]["layers"][0]["shapes"].append(
            {
                "id": "shape:image:0",
                "kind": "image",
                "value": {
                    "imagePath": "proof.png",
                    "position": [5, 6],
                    "scale": [1, 1],
                    "angle": 0,
                    "slant": [0, 0],
                },
            }
        )
        operations = [
            {
                "op": "translate",
                "target": {
                    "entity": "node",
                    "ids": ["node:0"],
                    "parent": {
                        "glyphName": "A",
                        "layerId": "A-master",
                        "shapeId": "shape:path:0",
                    },
                },
                "delta": {"x": 5, "y": 7},
            },
            {
                "op": "translate",
                "target": {
                    "entity": "shape",
                    "ids": ["shape:component:0"],
                    "parent": {"glyphName": "A", "layerId": "A-master"},
                },
                "delta": {"x": -2, "y": 3},
            },
            {
                "op": "translate",
                "target": {
                    "entity": "anchor",
                    "ids": ["anchor:top:0"],
                    "parent": {"glyphName": "A", "layerId": "A-master"},
                },
                "delta": {"x": 1, "y": -4},
            },
            {
                "op": "translate",
                "target": {
                    "entity": "shape",
                    "ids": ["shape:image:0"],
                    "parent": {"glyphName": "A", "layerId": "A-master"},
                },
                "delta": {"x": 8, "y": 9},
            },
        ]
        after = build_change_set(model, operations).change_set.apply(model)
        layer = after["glyphs"]["A"]["layers"][0]
        self.assertEqual(layer["shapes"][0]["value"]["nodes"][0]["x"], 55)
        self.assertEqual(layer["shapes"][0]["value"]["nodes"][0]["y"], 7)
        self.assertEqual(layer["shapes"][1]["value"]["position"], [18, 33])
        self.assertEqual(layer["anchors"][0]["position"], [251, 696])
        self.assertEqual(layer["shapes"][2]["value"]["position"], [13, 15])

    def test_alignment_projection_separates_configuration_from_effective_state(self) -> None:
        for mode in (-1, 0, 1, 3):
            with self.subTest(mode=mode):
                model = _model()
                model["glyphs"]["A"]["layers"][0]["shapes"][1] = _component(
                    alignment=mode
                )
                reference = resolve_selector(model, _selector())[0]
                observations = _bounds(model)
                observations[("A", "A-master")]["isAligned"] = mode == 1
                alignment = project_reference(
                    reference,
                    {"fields": ["alignment"]},
                    observations=observations,
                )["values"]["alignment"]
                self.assertEqual(
                    alignment["configuredAutomaticComponentCount"],
                    0 if mode == -1 else 1,
                )
                self.assertEqual(alignment["modeCounts"][str(mode)], 1)
                self.assertEqual(alignment["effectiveLayerAlignment"], mode == 1)

    def test_component_only_and_font_wide_alignment_state_remain_observations(self) -> None:
        model = _model()
        model["settings"] = {"disablesAutomaticAlignment": True}
        layer = model["glyphs"]["A"]["layers"][0]
        layer["shapes"] = [_component(alignment=0)]
        reference = resolve_selector(model, _selector())[0]
        observations = {
            ("A", "A-master"): {
                "hasAlignedWidth": False,
                "isAligned": False,
            }
        }

        alignment = project_reference(
            reference,
            {"fields": ["alignment"]},
            observations=observations,
        )["values"]["alignment"]
        after = build_change_set(
            model,
            [{"op": "translate", "target": _selector(), "delta": {"x": 4, "y": 0}}],
        ).change_set.apply(model)

        self.assertEqual(alignment["configuredAutomaticComponentCount"], 1)
        self.assertFalse(alignment["effectiveLayerAlignment"])
        self.assertTrue(after["settings"]["disablesAutomaticAlignment"])
        self.assertEqual(
            after["glyphs"]["A"]["layers"][0]["shapes"][0]["value"]["alignment"],
            0,
        )

    def test_grid_quantizer_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "grid snapping is unsupported"):
            build_change_set(
                _model(grid=1, subdivision=2),
                [
                    {
                        "op": "translate",
                        "target": _selector(),
                        "delta": {"x": 0.25, "y": 0},
                        "quantizer": "grid",
                    }
                ],
            )

    def test_grid_projection_is_descriptive_not_a_quantization_step(self) -> None:
        model = _model(grid=1, subdivision=4)
        reference = resolve_selector(model, {"entity": "font"})[0]
        projected = project_reference(reference, {"fields": ["grid"]})

        self.assertEqual(
            projected["values"]["grid"],
            {"grid": 1, "subdivision": 4},
        )
        self.assertNotIn("step", projected["values"]["grid"])

    def test_no_category_or_negative_bearing_policy_is_embedded(self) -> None:
        model = _model()
        build = build_change_set(
            model,
            [
                {
                    "op": "translate",
                    "target": _selector("acutecomb"),
                    "delta": {"x": -80, "y": 0},
                }
            ],
        )
        layer = build.change_set.apply(model)["glyphs"]["acutecomb"]["layers"][0]
        self.assertEqual(layer["shapes"][0]["value"]["nodes"][0]["x"], -30)

    def test_affine_shear_uses_pivot_and_component_conjugation(self) -> None:
        model = _model()
        model["glyphs"]["A"]["layers"][0]["shapes"][1]["value"]["alignment"] = 0
        build = build_change_set(
            model,
            [
                {
                    "op": "transform",
                    "target": _selector(),
                    "matrix": [1, 0, 0.5, 1, 0, 0],
                    "origin": [0, 100],
                    "quantizer": "exact",
                    "include": ["paths", "anchors", "components"],
                    "componentComposition": "conjugate",
                    "alignmentPolicy": "explicit_noncommuting",
                }
            ],
        )
        layer = build.change_set.apply(model)["glyphs"]["A"]["layers"][0]

        self.assertEqual(layer["shapes"][0]["value"]["nodes"][1]["x"], 750)
        self.assertEqual(layer["anchors"][0]["position"], [550, 700])
        component = layer["shapes"][1]["value"]
        self.assertEqual(component["position"], [35, 30])
        self.assertEqual(component["alignment"], -1)
        self.assertEqual(build.normalized_operations[0]["origin"], [0, 100])

    def test_fractional_scale_and_recenter_preserve_all_geometry_fractions(self) -> None:
        model = _model()
        after = build_change_set(
            model,
            [
                {
                    "op": "transform",
                    "target": _selector(),
                    "matrix": [1.125, 0, 0, 0.875, 0.375, -0.625],
                    "origin": [12.25, -3.5],
                    "quantizer": "exact",
                    "include": ["paths", "anchors", "components"],
                    "componentComposition": "prepend",
                    "alignmentPolicy": "preserve",
                }
            ],
        ).change_set.apply(model)
        layer = after["glyphs"]["A"]["layers"][0]

        node = layer["shapes"][0]["value"]["nodes"][0]
        anchor = layer["anchors"][0]["position"]
        component = layer["shapes"][1]["value"]
        self.assertEqual((node["x"], node["y"]), (55.09375, -1.0625))
        self.assertEqual(anchor, [280.09375, 611.4375])
        self.assertEqual(component["position"], [21.34375, 25.1875])
        self.assertEqual(component["scale"], [1.125, 0.875])
        self.assertEqual(component["alignment"], -1)

    def test_affine_include_and_alignment_modes_are_explicit(self) -> None:
        model = _model()
        before_layer = copy.deepcopy(model["glyphs"]["A"]["layers"][0])
        after = build_change_set(
            model,
            [
                {
                    "op": "transform",
                    "target": _selector(),
                    "matrix": [1, 0, 0.25, 1, 0, 0],
                    "include": ["paths"],
                    "componentComposition": "unchanged",
                    "alignmentPolicy": "preserve",
                }
            ],
        ).change_set.apply(model)
        layer = after["glyphs"]["A"]["layers"][0]

        self.assertNotEqual(layer["shapes"][0], before_layer["shapes"][0])
        self.assertEqual(layer["shapes"][1], before_layer["shapes"][1])
        self.assertEqual(layer["anchors"], before_layer["anchors"])

    def test_affine_collection_skips_empty_members_and_reports_target_counts(self) -> None:
        model = _model()
        empty = _glyph("space")
        empty["layers"][0]["shapes"] = []
        empty["layers"][0]["anchors"] = []
        model["glyphs"]["space"] = empty
        operation = {
            "op": "transform",
            "target": {"entity": "layer", "parent": {"masterId": "M1"}},
            "matrix": [1, 0, 0.2, 1, 0, 0],
            "include": ["paths", "anchors", "components"],
        }

        build = build_change_set(model, [operation])
        evidence = build.normalized_operations[0]
        after = build.change_set.apply(model)

        self.assertEqual(evidence["resolvedTargetCount"], 3)
        self.assertEqual(evidence["changedTargetCount"], 2)
        self.assertEqual(evidence["skippedTargetCount"], 1)
        self.assertEqual(after["glyphs"]["space"], model["glyphs"]["space"])

        host = _Host(model)
        preview = GlyphsMCPApplication(host).invoke(
            "preview_change",
            {
                "documentId": "doc_empty_collection",
                "expectedDocumentFingerprint": fingerprint_model(model),
                "operations": [operation],
                "constraints": [],
            },
        ).to_dict()
        self.assertTrue(preview["ok"])
        self.assertEqual(preview["data"]["resolvedTargetCount"], 3)
        self.assertEqual(preview["data"]["changedTargetCount"], 2)
        self.assertEqual(preview["data"]["skippedTargetCount"], 1)
        validate(preview, TOOL_CATALOG["preview_change"].output_schema)

    def test_affine_all_empty_collection_is_a_no_op_error(self) -> None:
        model = _model()
        for glyph in model["glyphs"].values():
            glyph["layers"][0]["shapes"] = []
            glyph["layers"][0]["anchors"] = []

        with self.assertRaisesRegex(ValueError, "no geometry change"):
            build_change_set(
                model,
                [
                    {
                        "op": "transform",
                        "target": {
                            "entity": "layer",
                            "parent": {"masterId": "M1"},
                        },
                        "matrix": [1, 0, 0.2, 1, 0, 0],
                    }
                ],
            )

        with self.assertRaisesRegex(ValueError, "no geometry change"):
            build_change_set(
                _model(),
                [
                    {
                        "op": "transform",
                        "target": _selector(),
                        "matrix": [1, 0, 0, 1, 0, 0],
                    }
                ],
            )

    def test_normalized_target_counts_distinguish_noop_set_targets(self) -> None:
        build = build_change_set(
            _model(),
            [
                {
                    "op": "set",
                    "target": _selector(),
                    "field": "width",
                    "value": 500,
                }
            ],
        )
        evidence = build.normalized_operations[0]
        self.assertEqual(evidence["resolvedTargetCount"], 1)
        self.assertEqual(evidence["changedTargetCount"], 0)
        self.assertEqual(evidence["skippedTargetCount"], 1)

    def test_zero_translation_is_skipped_without_blocking_width_change(self) -> None:
        host = _Host(_model())
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {
                        "op": "translate",
                        "target": _selector(),
                        "delta": {"x": 0, "y": 0},
                    },
                    {
                        "op": "set",
                        "target": _selector(),
                        "field": "width",
                        "value": 510,
                    },
                ],
            },
        ).to_dict()

        self.assertTrue(preview["ok"])
        self.assertTrue(preview["data"]["applicable"])
        self.assertEqual(preview["data"]["changeSet"]["changeCount"], 1)
        self.assertEqual(preview["data"]["resolvedTargetCount"], 2)
        self.assertEqual(preview["data"]["changedTargetCount"], 1)
        self.assertEqual(preview["data"]["skippedTargetCount"], 1)
        operations = preview["data"]["normalizedOperations"]
        self.assertEqual(operations[0]["resolvedPaths"], [])
        self.assertEqual(operations[0]["changedTargetCount"], 0)
        self.assertEqual(operations[0]["skippedTargetCount"], 1)
        self.assertEqual(operations[1]["changedTargetCount"], 1)
        self.assertEqual(fingerprint_model(host.model), before)

        noop_preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {
                        "op": "translate",
                        "target": _selector(),
                        "delta": {"x": 0, "y": 0},
                    }
                ],
            },
        ).to_dict()
        self.assertTrue(noop_preview["ok"])
        self.assertTrue(noop_preview["data"]["applicable"])
        self.assertEqual(noop_preview["data"]["changeSet"]["changeCount"], 0)

    def test_fractional_translation_is_not_snapped_or_skipped(self) -> None:
        build = build_change_set(
            _model(grid=1, subdivision=1),
            [
                {
                    "op": "translate",
                    "target": _selector(),
                    "delta": {"x": 0.25, "y": 0},
                    "quantizer": "exact",
                }
            ],
        )

        evidence = build.normalized_operations[0]
        self.assertEqual(evidence["delta"], {"x": 0.25, "y": 0})
        self.assertEqual(evidence["changedTargetCount"], 1)
        self.assertEqual(evidence["skippedTargetCount"], 0)
        self.assertTrue(build.change_set.changes)
        after = build.change_set.apply(_model(grid=1, subdivision=1))
        self.assertEqual(
            after["glyphs"]["A"]["layers"][0]["shapes"][0]["value"]["nodes"][0]["x"],
            50.25,
        )

    def test_cancellation_checkpoints_cover_duplication_transform_and_comparison(self) -> None:
        model = _model()
        before = fingerprint_model(model)

        for name, operations, cancel_after in (
            (
                "duplication",
                [
                    {
                        "op": "duplicate",
                        "target": {"entity": "master", "ids": ["M1"]},
                        "newId": "M2",
                        "overrides": {"name": "Copy"},
                    }
                ],
                2,
            ),
            (
                "transform",
                [
                    {
                        "op": "transform",
                        "target": {
                            "entity": "layer",
                            "parent": {"masterId": "M1"},
                        },
                        "matrix": [1, 0, 0.2, 1, 0, 0],
                    }
                ],
                2,
            ),
        ):
            with self.subTest(phase=name):
                calls = 0

                def cancel() -> None:
                    nonlocal calls
                    calls += 1
                    if calls >= cancel_after:
                        raise ActivityCancelled("cancel {}".format(name))

                with self.assertRaises(ActivityCancelled):
                    build_change_set(
                        model,
                        operations,
                        cancellation_checkpoint=cancel,
                    )
                self.assertEqual(fingerprint_model(model), before)

    def test_transport_cancellation_receipt_and_health_are_bounded(self) -> None:
        host = _CancellablePreviewHost(_model())
        app = GlyphsMCPApplication(host)
        handlers = ToolHandlers(app)
        before = fingerprint_model(host.model)
        arguments = {
            "documentId": "doc_cancellable",
            "expectedDocumentFingerprint": before,
            "operations": [
                {
                    "op": "set",
                    "target": _selector(),
                    "field": "width",
                    "value": 510,
                }
            ],
        }

        async def exercise() -> None:
            task = asyncio.create_task(
                handlers._invoke("preview_change", arguments)
            )
            started = await asyncio.to_thread(host.started.wait, 1.0)
            self.assertTrue(started)
            active = app.activity.operation_summaries()["active"]
            operation_id = next(
                item["operationId"]
                for item in active
                if item["tool"] == "preview_change"
            )

            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

            health_started = time.perf_counter()
            health = await asyncio.wait_for(
                handlers.get_runtime_status(), timeout=1.0
            )
            self.assertLess(time.perf_counter() - health_started, 1.0)
            self.assertTrue(health.structured_content["ok"])

            deadline = time.monotonic() + 5.0
            while app._operations.get(operation_id) is None:
                self.assertLess(time.monotonic(), deadline)
                await asyncio.sleep(0.01)
            receipt = app.invoke(
                "get_operation", {"operationId": operation_id}
            ).to_dict()
            self.assertTrue(receipt["ok"])
            payload = receipt["data"]["payload"]
            self.assertEqual(payload["classification"], "cancelled")
            self.assertEqual(
                payload["response"]["operationId"], operation_id
            )
            self.assertIn("total", payload["stageTimings"])

        asyncio.run(exercise())
        self.assertEqual(fingerprint_model(host.model), before)
        self.assertEqual(host.apply_calls, 0)

    def test_affine_anchor_and_component_only_layers_are_not_empty(self) -> None:
        for include, shapes, anchors in (
            ("anchors", [], [_layer("tmp", "M1")["anchors"][0]]),
            ("components", [_component()], []),
        ):
            with self.subTest(include=include):
                model = _model()
                layer = model["glyphs"]["A"]["layers"][0]
                layer["shapes"] = shapes
                layer["anchors"] = anchors
                build = build_change_set(
                    model,
                    [
                        {
                            "op": "transform",
                            "target": _selector(),
                            "matrix": [1, 0, 0, 1, 5, 7],
                            "include": [include],
                        }
                    ],
                )
                evidence = build.normalized_operations[0]
                self.assertEqual(evidence["changedTargetCount"], 1)
                self.assertEqual(evidence["skippedTargetCount"], 0)

    def test_affine_unsupported_shape_and_invalid_matrix_remain_blocking(self) -> None:
        model = _model()
        model["glyphs"]["A"]["layers"][0]["shapes"].append(
            {
                "id": "shape:image:0",
                "kind": "image",
                "value": {"position": [0, 0]},
            }
        )
        target = {
            "entity": "shape",
            "ids": ["shape:image:0"],
            "parent": {"glyphName": "A", "layerId": "A-master"},
        }
        with self.assertRaisesRegex(ValueError, "only path and component"):
            build_change_set(
                model,
                [{"op": "transform", "target": target, "matrix": [1, 0, 0, 1, 1, 0]}],
            )
        with self.assertRaisesRegex(ValueError, "six finite numbers"):
            build_change_set(
                model,
                [{"op": "transform", "target": _selector(), "matrix": [1, 0, 0]}],
            )

    def test_affine_builder_retains_untouched_snapshot_glyph_shards(self) -> None:
        snapshot = CanonicalSnapshot.from_model(_model())
        source_x = snapshot["glyphs"]["A"]["layers"][0]["shapes"][0][
            "value"
        ]["nodes"][0]["x"]
        build = build_change_set(
            snapshot,
            [
                {
                    "op": "transform",
                    "target": _selector(),
                    "matrix": [1, 0, 0.2, 1, 0, 0],
                    "include": ["paths"],
                }
            ],
        )
        after = build.change_set.apply(snapshot)

        self.assertEqual(
            snapshot["glyphs"]["A"]["layers"][0]["shapes"][0]["value"][
                "nodes"
            ][0]["x"],
            source_x,
        )
        self.assertGreaterEqual(after.reused_glyph_count, 1)

    def test_affine_reflection_round_trips_and_singular_conjugation_refuses(self) -> None:
        model = _model()
        component = model["glyphs"]["A"]["layers"][0]["shapes"][1]["value"]
        component["scale"] = [-1, 2]
        transformed = build_change_set(
            model,
            [
                {
                    "op": "transform",
                    "target": {
                        "entity": "shape",
                        "ids": ["shape:component:0"],
                        "parent": {"glyphName": "A", "layerId": "A-master"},
                    },
                    "matrix": [1, 0, 0.2, 1, 3, 4],
                    "componentComposition": "prepend",
                }
            ],
        ).change_set.apply(model)
        reference = resolve_selector(
            transformed,
            {
                "entity": "shape",
                "ids": ["shape:component:0"],
                "parent": {"glyphName": "A", "layerId": "A-master"},
            },
        )[0]
        matrix = project_reference(
            reference, {"fields": ["geometry.transform"]}
        )["values"]["geometry.transform"]
        for observed, expected in zip(
            matrix, [-1.0, 0.0, 0.4, 2.0, 29.0, 34.0]
        ):
            self.assertAlmostEqual(observed, expected, places=12)

        with self.assertRaisesRegex(ValueError, "invertible"):
            build_change_set(
                model,
                [
                    {
                        "op": "transform",
                        "target": _selector(),
                        "matrix": [0, 0, 0, 1, 0, 0],
                        "componentComposition": "conjugate",
                    }
                ],
            )

    def test_collection_index_projection_reports_canonical_order(self) -> None:
        model = _model()
        model["masters"].append({"id": "M2", "name": "Bold", "axes": []})
        reference = resolve_selector(
            model, {"entity": "master", "ids": ["M2"]}
        )[0]
        projected = project_reference(
            reference, {"fields": ["collection.index", "axes"]}
        )
        self.assertEqual(projected["values"]["collection.index"], 1)
        self.assertEqual(projected["values"]["axes"], [])

    def test_locks_and_alignment_modes_are_preserved_metadata(self) -> None:
        model = _model()
        layer = model["glyphs"]["A"]["layers"][0]
        layer["locked"] = True
        layer["shapes"][0]["value"]["locked"] = True
        layer["shapes"][0]["value"]["nodes"][0]["locked"] = True
        layer["shapes"][1]["value"]["locked"] = True
        layer["shapes"][1]["value"]["alignment"] = 0
        layer["anchors"][0]["locked"] = True

        after = build_change_set(
            model,
            [{"op": "translate", "target": _selector(), "delta": {"x": 1, "y": 2}}],
        ).change_set.apply(model)
        translated = after["glyphs"]["A"]["layers"][0]

        self.assertTrue(translated["locked"])
        self.assertTrue(translated["shapes"][0]["value"]["locked"])
        self.assertTrue(translated["shapes"][0]["value"]["nodes"][0]["locked"])
        self.assertTrue(translated["shapes"][1]["value"]["locked"])
        self.assertEqual(translated["shapes"][1]["value"]["alignment"], 0)
        self.assertTrue(translated["anchors"][0]["locked"])
        self.assertEqual(translated["shapes"][0]["value"]["nodes"][0]["x"], 51)
        self.assertEqual(translated["shapes"][1]["value"]["position"], [21, 32])
        self.assertEqual(translated["anchors"][0]["position"], [251, 702])

    def test_each_locked_coordinate_entity_remains_directly_translatable(self) -> None:
        targets = (
            (
                "path",
                {"entity": "shape", "ids": ["shape:path:0"]},
                lambda layer: layer["shapes"][0]["value"].update(locked=True),
            ),
            (
                "component",
                {"entity": "shape", "ids": ["shape:component:0"]},
                lambda layer: layer["shapes"][1]["value"].update(locked=True),
            ),
            (
                "node",
                {
                    "entity": "node",
                    "ids": ["node:0"],
                    "parent": {"shapeId": "shape:path:0"},
                },
                lambda layer: layer["shapes"][0]["value"]["nodes"][0].update(
                    locked=True
                ),
            ),
            (
                "anchor",
                {"entity": "anchor", "ids": ["anchor:top:0"]},
                lambda layer: layer["anchors"][0].update(locked=True),
            ),
        )
        for name, target, lock in targets:
            with self.subTest(entity=name):
                model = _model()
                layer = model["glyphs"]["A"]["layers"][0]
                lock(layer)
                target["parent"] = {
                    "glyphName": "A",
                    "layerId": "A-master",
                    **dict(target.get("parent") or {}),
                }
                result = build_change_set(
                    model,
                    [{"op": "translate", "target": target, "delta": {"x": 1, "y": 0}}],
                )
                self.assertTrue(result.change_set.changes)

    def test_preview_exact_apply_readback_and_revert_are_atomic(self) -> None:
        host = _Host(_model())
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        constraints = [
            {
                "label": "assumed width",
                "phase": "before",
                "left": {"kind": "field", "selector": _selector(), "field": "width"},
                "operator": "eq",
                "right": {"kind": "literal", "value": 500},
            },
            {
                "label": "written width",
                "phase": "after",
                "left": {"kind": "field", "selector": _selector(), "field": "width"},
                "operator": "eq",
                "right": {"kind": "literal", "value": 457},
            },
        ]
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {"op": "translate", "target": _selector(), "delta": {"x": -18, "y": 0}},
                    {"op": "set", "target": _selector(), "field": "width", "value": 457},
                ],
                "constraints": constraints,
            },
        ).to_dict()

        self.assertTrue(preview["ok"])
        self.assertEqual(fingerprint_model(host.model), before)
        self.assertEqual(host.apply_calls, 0)
        validate(preview, TOOL_CATALOG["preview_change"].output_schema)

        applied = app.invoke(
            "apply_change",
            {
                "documentId": "doc_spacing",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before,
                "reason": "apply explicit spacing arithmetic",
            },
        ).to_dict()
        self.assertTrue(applied["ok"])
        self.assertEqual(host.apply_calls, 1)
        validate(applied, TOOL_CATALOG["apply_change"].output_schema)

        readback = app.invoke(
            "read_document",
            {
                "documentId": "doc_spacing",
                "selector": _selector(),
                "projection": {"fields": ["width", "bounds", "spacing.horizontal"]},
            },
        ).to_dict()
        self.assertEqual(readback["data"]["items"][0]["values"]["width"], 457)

        reverted = app.invoke(
            "revert_change",
            {
                "documentId": "doc_spacing",
                "operationId": applied["data"]["operationId"],
                "expectedDocumentFingerprint": fingerprint_model(host.model),
            },
        ).to_dict()
        self.assertTrue(reverted["ok"])
        self.assertEqual(fingerprint_model(host.model), before)

    def test_snapshot_backed_recovery_requires_confirmation_and_receipt(self) -> None:
        host = _Host(_model())
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {
                        "op": "set",
                        "target": _selector(),
                        "field": "width",
                        "value": 510,
                    }
                ],
                "transactionMode": "snapshot_backed_recovery",
            },
        ).to_dict()
        self.assertTrue(preview["ok"], preview)
        self.assertTrue(preview["data"]["recovery"]["requiredConfirmation"])

        refused = app.invoke(
            "apply_change",
            {
                "documentId": "doc_spacing",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before,
                "reason": "exercise bounded recovery",
            },
        ).to_dict()
        self.assertEqual(refused["error"]["code"], "confirmation_required")
        self.assertEqual(host.apply_calls, 0)

        applied = app.invoke(
            "apply_change",
            {
                "documentId": "doc_spacing",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before,
                "reason": "exercise bounded recovery",
                "confirmRecovery": True,
            },
        ).to_dict()
        self.assertTrue(applied["ok"], applied)
        self.assertEqual(len(host.recovery_calls), 1)
        self.assertTrue(applied["data"]["recovery"]["snapshotCreated"])
        self.assertNotIn("recoveryPath", applied["data"]["recovery"])
        self.assertEqual(host.apply_calls, 1)

    def test_snapshot_backed_recovery_refuses_stale_source_state(self) -> None:
        host = _Host(_model())
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {
                        "op": "set",
                        "target": _selector(),
                        "field": "width",
                        "value": 510,
                    }
                ],
                "transactionMode": "snapshot_backed_recovery",
            },
        ).to_dict()
        host.source_state["contentFingerprint"] = "sha256:source-after"

        applied = app.invoke(
            "apply_change",
            {
                "documentId": "doc_spacing",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before,
                "reason": "must bind source state",
                "confirmRecovery": True,
            },
        ).to_dict()

        self.assertFalse(applied["ok"])
        self.assertEqual(applied["error"]["code"], "stale_source")
        self.assertEqual(host.recovery_calls, [])
        self.assertEqual(host.apply_calls, 0)

    def test_snapshot_backed_failure_opens_one_recovery_and_quarantines(self) -> None:
        host = _RecoveryFailureHost(_model())
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {
                        "op": "set",
                        "target": _selector(),
                        "field": "width",
                        "value": 510,
                    }
                ],
                "transactionMode": "snapshot_backed_recovery",
            },
        ).to_dict()
        failed = app.invoke(
            "apply_change",
            {
                "documentId": "doc_spacing",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before,
                "reason": "exercise indeterminate recovery",
                "confirmRecovery": True,
            },
        ).to_dict()

        self.assertFalse(failed["ok"])
        self.assertEqual(failed["data"]["rollbackClassification"], "indeterminate")
        self.assertTrue(failed["data"]["recovery"]["recoveryAttempted"])
        self.assertTrue(failed["data"]["recovery"]["recoveryCopyOpened"])
        self.assertEqual(len(host.opened_recovery), 1)
        blocked = app.invoke(
            "apply_change",
            {
                "documentId": "doc_spacing",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": fingerprint_model(host.model),
                "reason": "must be quarantined",
                "confirmRecovery": True,
            },
        ).to_dict()
        self.assertEqual(blocked["error"]["code"], "document_quarantined")

    def test_black_condensed_y_spacing_is_previewed_applied_and_reverted(self) -> None:
        host = _Host(_black_y_model())
        app = GlyphsMCPApplication(host)
        before_model = copy.deepcopy(host.model)
        before_fingerprint = fingerprint_model(before_model)
        selector = {
            "entity": "layer",
            "ids": ["Y-black-condensed"],
            "parent": {"glyphName": "Y"},
        }
        constraints = [
            {
                "label": "source width",
                "phase": "before",
                "left": {"kind": "field", "selector": selector, "field": "width"},
                "operator": "eq",
                "right": {"kind": "literal", "value": 1467},
            },
            *[
                {
                    "label": label,
                    "phase": "after",
                    "left": {"kind": "field", "selector": selector, "field": field},
                    "operator": "eq",
                    "right": {"kind": "literal", "value": value},
                }
                for label, field, value in (
                    ("target width", "width", 1454),
                    ("target bounds", "observation.bounds.x", 30),
                    (
                        "target LSB",
                        "observation.spacing.horizontal.leadingBearing",
                        30,
                    ),
                    (
                        "target RSB",
                        "observation.spacing.horizontal.trailingBearing",
                        41,
                    ),
                    (
                        "alignment configuration",
                        "observation.alignment.configuredAutomaticComponentCount",
                        1,
                    ),
                )
            ],
        ]
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before_fingerprint,
                "operations": [
                    {"op": "translate", "target": selector, "delta": {"x": -12, "y": 0}},
                    {"op": "set", "target": selector, "field": "width", "value": 1454},
                ],
                "constraints": constraints,
            },
        ).to_dict()

        self.assertTrue(preview["ok"])
        self.assertTrue(preview["data"]["applicable"])
        self.assertEqual(fingerprint_model(host.model), before_fingerprint)
        applied = app.invoke(
            "apply_change",
            {
                "documentId": "doc_spacing",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before_fingerprint,
                "reason": "apply Black Condensed Y spacing",
            },
        ).to_dict()
        self.assertTrue(applied["ok"])
        layer = host.model["glyphs"]["Y"]["layers"][0]
        self.assertEqual(layer["width"], 1454)
        self.assertEqual(layer["shapes"][3]["value"]["alignment"], 0)
        self.assertEqual(len(layer["anchors"]), 2)
        self.assertEqual(sum(len(shape["value"]["nodes"]) for shape in layer["shapes"][:3]), 58)
        self.assertEqual(_bounds(host.model)[("Y", "Y-black-condensed")]["bounds"]["x"], 30)
        reverted = app.invoke(
            "revert_change",
            {
                "documentId": "doc_spacing",
                "operationId": applied["data"]["operationId"],
                "expectedDocumentFingerprint": fingerprint_model(host.model),
            },
        ).to_dict()
        self.assertTrue(reverted["ok"])
        self.assertEqual(host.model, before_model)

    def test_native_rewrite_cannot_replace_requested_geometry(self) -> None:
        host = _NativeRewriteHost(_model())
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {"op": "translate", "target": _selector(), "delta": {"x": 10, "y": 0}}
                ],
            },
        ).to_dict()

        self.assertTrue(preview["ok"])
        self.assertFalse(preview["data"]["applicable"])
        self.assertIsNotNone(preview["data"]["previewId"])
        self.assertEqual(preview["data"]["blockers"], ["requested_effect_mismatch"])
        self.assertEqual(fingerprint_model(host.model), before)

    def test_native_grid_rounding_blocks_exact_translation(self) -> None:
        host = _NativeGridHost(_model())
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {
                        "op": "translate",
                        "target": _selector(),
                        "delta": {"x": 10.49, "y": 0},
                        "quantizer": "exact",
                    }
                ],
            },
        ).to_dict()

        self.assertTrue(preview["ok"])
        self.assertFalse(preview["data"]["applicable"])
        self.assertEqual(preview["data"]["blockers"], ["requested_effect_mismatch"])
        self.assertEqual(fingerprint_model(host.model), before)
        self.assertEqual(host.apply_calls, 0)

    def test_native_grid_rounding_cannot_create_zero_change_preview(self) -> None:
        host = _NativeGridHost(_model())
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {
                        "op": "translate",
                        "target": _selector(),
                        "delta": {"x": 0.49, "y": 0},
                    }
                ],
            },
        ).to_dict()

        self.assertTrue(preview["ok"])
        self.assertFalse(preview["data"]["applicable"])
        self.assertEqual(preview["data"]["blockers"], ["requested_effect_mismatch"])
        self.assertIsNotNone(preview["data"]["previewId"])
        self.assertEqual(host.apply_calls, 0)

    def test_native_noop_is_an_applicable_zero_change_preview(self) -> None:
        host = _AlignedInheritanceHost(_aligned_inheritance_model())
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {
                        "op": "set",
                        "target": _selector("A"),
                        "field": "width",
                        "value": 700,
                    }
                ],
            },
        ).to_dict()

        self.assertTrue(preview["ok"])
        self.assertTrue(preview["data"]["applicable"])
        self.assertEqual(preview["data"]["changeSet"]["changeCount"], 0)
        evidence = preview["data"]["verification"]
        self.assertEqual(evidence["settlement"], "native")
        self.assertFalse(evidence["requestedTargetMatched"])

        applied = app.invoke(
            "apply_change",
            {
                "documentId": "doc_spacing",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before,
                "reason": "retain inherited aligned width",
            },
        ).to_dict()
        self.assertTrue(applied["ok"])
        self.assertEqual(host.apply_calls, 0)
        self.assertEqual(fingerprint_model(host.model), before)

    def test_base_and_aligned_composite_batch_applies_inherited_native_width(self) -> None:
        host = _AlignedInheritanceHost(_aligned_inheritance_model())
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {
                        "op": "set",
                        "target": _selector("H"),
                        "field": "width",
                        "value": 600,
                    },
                    {
                        "op": "set",
                        "target": _selector("A"),
                        "field": "width",
                        "value": 700,
                    },
                ],
            },
        ).to_dict()

        self.assertTrue(preview["data"]["applicable"])
        applied = app.invoke(
            "apply_change",
            {
                "documentId": "doc_spacing",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before,
                "reason": "space base and inherit aligned composite width",
            },
        ).to_dict()
        self.assertTrue(applied["ok"])
        self.assertEqual(host.model["glyphs"]["H"]["layers"][0]["width"], 600)
        self.assertEqual(host.model["glyphs"]["A"]["layers"][0]["width"], 600)
        self.assertEqual(
            host.model["glyphs"]["A"]["layers"][0]["shapes"][0]["value"][
                "alignment"
            ],
            0,
        )

    def test_aligned_component_position_rewrite_keeps_native_position(self) -> None:
        host = _AlignedPositionHost(_aligned_inheritance_model())
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {
                        "op": "translate",
                        "target": _selector("A"),
                        "delta": {"x": 10, "y": 0},
                    }
                ],
            },
        ).to_dict()

        self.assertTrue(preview["data"]["applicable"])
        self.assertEqual(preview["data"]["verification"]["settlement"], "native")
        applied = app.invoke(
            "apply_change",
            {
                "documentId": "doc_spacing",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before,
                "reason": "move authored anchors while preserving aligned components",
            },
        ).to_dict()
        self.assertTrue(applied["ok"])
        layer = host.model["glyphs"]["A"]["layers"][0]
        self.assertEqual(layer["shapes"][0]["value"]["position"], [20, 30])
        self.assertEqual(layer["anchors"][0]["position"], [260, 700])

    def test_independent_aligned_width_postcondition_remains_exact(self) -> None:
        host = _AlignedInheritanceHost(_aligned_inheritance_model())
        app = GlyphsMCPApplication(host)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": fingerprint_model(host.model),
                "operations": [
                    {
                        "op": "set",
                        "target": _selector("A"),
                        "field": "width",
                        "value": 700,
                    }
                ],
                "constraints": [
                    {
                        "phase": "after",
                        "left": {
                            "kind": "field",
                            "selector": _selector("A"),
                            "field": "width",
                        },
                        "operator": "eq",
                        "right": {"kind": "literal", "value": 700},
                    }
                ],
            },
        ).to_dict()

        self.assertFalse(preview["data"]["applicable"])
        self.assertEqual(preview["data"]["blockers"], ["postcondition_failed"])

    def test_explicit_transform_alignment_policy_is_allowed(self) -> None:
        host = _AlignedInheritanceHost(_aligned_inheritance_model())
        app = GlyphsMCPApplication(host)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": fingerprint_model(host.model),
                "operations": [
                    {
                        "op": "transform",
                        "target": _selector("A"),
                        "matrix": [1, 0, 0.25, 1, 0, 0],
                        "include": ["components"],
                        "alignmentPolicy": "explicit_noncommuting",
                    }
                ],
            },
        ).to_dict()

        self.assertTrue(preview["data"]["applicable"])
        expected = app._previews.get(preview["data"]["previewId"]).payload[
            "plan"
        ].expected_after_model
        self.assertEqual(
            expected["glyphs"]["A"]["layers"][0]["shapes"][0]["value"][
                "alignment"
            ],
            -1,
        )

    def test_font_wide_alignment_setting_is_protected(self) -> None:
        model = _aligned_inheritance_model()
        model["settings"] = {"disablesAutomaticAlignment": False}
        host = _AlignedInheritanceHost(model)
        app = GlyphsMCPApplication(host)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": fingerprint_model(host.model),
                "operations": [
                    {
                        "op": "set",
                        "target": {"entity": "document"},
                        "field": "settings.disablesAutomaticAlignment",
                        "value": True,
                    }
                ],
            },
        ).to_dict()

        self.assertFalse(preview["ok"])
        self.assertEqual(preview["error"]["code"], "invalid_request")
        self.assertIn("protected", preview["error"]["message"])

    def test_strict_archive_keeps_aligned_width_divergence_exact(self) -> None:
        host = _AlignedInheritanceHost(_aligned_inheritance_model())
        app = GlyphsMCPApplication(host)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": fingerprint_model(host.model),
                "verificationMode": "strict_archive",
                "operations": [
                    {
                        "op": "set",
                        "target": _selector("A"),
                        "field": "width",
                        "value": 700,
                    }
                ],
            },
        ).to_dict()

        self.assertFalse(preview["data"]["applicable"])
        self.assertEqual(preview["data"]["blockers"], ["strict_archive_mismatch"])

    def test_native_metadata_settlement_is_reviewable(self) -> None:
        host = _AlignedLossHost(_aligned_inheritance_model())
        app = GlyphsMCPApplication(host)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": fingerprint_model(host.model),
                "operations": [
                    {
                        "op": "set",
                        "target": _selector("A"),
                        "field": "width",
                        "value": 700,
                    }
                ],
            },
        ).to_dict()

        self.assertTrue(preview["data"]["applicable"])
        self.assertEqual(preview["data"]["blockers"], [])
        self.assertEqual(preview["data"]["verification"]["settlement"], "native")
        plan = app._previews.get(preview["data"]["previewId"]).payload["plan"]
        self.assertEqual(
            plan.expected_after_model["glyphs"]["A"]["layers"][0]["shapes"][0]
            ["value"]["alignment"],
            -1,
        )

    def test_apply_rolls_back_when_observation_evidence_drifts(self) -> None:
        host = _ObservationDriftHost(_model())
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        constraints = [
            {
                "phase": "after",
                "left": {
                    "kind": "field",
                    "selector": _selector(),
                    "field": "observation.bounds.x",
                },
                "operator": "eq",
                "right": {"kind": "literal", "value": 40},
            }
        ]
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {"op": "translate", "target": _selector(), "delta": {"x": -10, "y": 0}}
                ],
                "constraints": constraints,
            },
        ).to_dict()
        self.assertTrue(preview["data"]["applicable"])

        applied = app.invoke(
            "apply_change",
            {
                "documentId": "doc_spacing",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before,
                "reason": "exercise observation rollback",
            },
        ).to_dict()
        self.assertFalse(applied["ok"])
        self.assertEqual(applied["error"]["code"], "transaction_failed")
        self.assertEqual(fingerprint_model(host.model), before)

    def test_preview_and_apply_share_all_native_observation_sources(self) -> None:
        host = _RichObservationHost(_model())
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        constraints = [
            {
                "phase": "after",
                "left": {
                    "kind": "field",
                    "selector": _selector(),
                    "field": "observation.metadata.effective.category",
                },
                "operator": "eq",
                "right": {"kind": "literal", "value": "Letter"},
            },
            {
                "phase": "after",
                "left": {
                    "kind": "field",
                    "selector": _selector(),
                    "field": "observation.compilation.diagnostics.succeeded",
                },
                "operator": "eq",
                "right": {"kind": "literal", "value": True},
            },
        ]
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_spacing",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {
                        "op": "translate",
                        "target": _selector(),
                        "delta": {"x": 1, "y": 0},
                    }
                ],
                "constraints": constraints,
            },
        ).to_dict()

        self.assertTrue(preview["data"]["applicable"])
        applied = app.invoke(
            "apply_change",
            {
                "documentId": "doc_spacing",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before,
                "reason": "verify shared observation registry",
            },
        ).to_dict()
        self.assertTrue(applied["ok"])

    def test_transport_operation_shapes_are_closed_and_finite(self) -> None:
        with self.assertRaises(ValidationError):
            ChangeOperation.model_validate(
                {"op": "remove", "target": _selector(), "field": "width"}
            )
        with self.assertRaises(ValidationError):
            ChangeOperation.model_validate(
                {
                    "op": "translate",
                    "target": _selector(),
                    "delta": {"x": math.inf, "y": 0},
                }
            )


if __name__ == "__main__":
    unittest.main()
