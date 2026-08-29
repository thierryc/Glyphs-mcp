"""Generic spacing projections and explicit physical write qualification."""

from __future__ import annotations

import copy
import math
import sys
import unittest
from pathlib import Path

from jsonschema import validate
from pydantic import ValidationError


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.generic_tools import (  # noqa: E402
    build_change_set,
    project_reference,
    resolve_selector,
)
from glyphs_mcp_v2.semantic import fingerprint_model  # noqa: E402
from glyphs_mcp_v2.transport.fastmcp import ChangeOperation  # noqa: E402


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
                "bounds": {
                    "x": min(xs),
                    "y": min(ys),
                    "width": max(xs) - min(xs),
                    "height": max(ys) - min(ys),
                },
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

    def capture_model(self, _document_id: str) -> dict:
        return copy.deepcopy(self.model)

    def apply_change_set(self, _document_id: str, change_set) -> None:
        self.apply_calls += 1
        self.model = change_set.apply(self.model)

    def restore_model(self, _document_id: str, model: dict) -> None:
        self.restore_calls += 1
        self.model = copy.deepcopy(model)

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

    def test_grid_quantization_is_explicit_and_visible(self) -> None:
        for requested, expected in ((0.25, 0.5), (-0.25, -0.5)):
            with self.subTest(requested=requested):
                build = build_change_set(
                    _model(grid=1, subdivision=2),
                    [
                        {
                            "op": "translate",
                            "target": _selector(),
                            "delta": {"x": requested, "y": 0},
                            "quantizer": "grid",
                        }
                    ],
                )
                self.assertEqual(build.normalized_operations[0]["delta"]["x"], expected)

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

    def test_native_rewrite_returns_an_immutable_non_applicable_preview(self) -> None:
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
        self.assertEqual(preview["data"]["diagnostics"]["mismatchCount"], 1)
        self.assertEqual(fingerprint_model(host.model), before)

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
