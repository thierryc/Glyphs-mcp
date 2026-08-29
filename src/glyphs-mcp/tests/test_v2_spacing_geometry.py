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


def _component(*, automatic: bool = False, locked: bool = False) -> dict:
    return {
        "id": "shape:component:0",
        "kind": "component",
        "value": {
            "name": "H",
            "position": [20, 30],
            "scale": [1, 1],
            "angle": 0,
            "slant": [0, 0],
            "transform": [1, 0, 0, 1, 20, 30],
            "automaticAlignment": automatic,
            "alignment": -1 if not automatic else 0,
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
        "hasAlignedWidth": False,
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


def _bounds(model: dict) -> dict:
    return {
        (name, layer["id"]): {
            "bounds": {"x": 50, "y": 0, "width": 400, "height": 700},
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
        }
        for name, glyph in model["glyphs"].items()
        for layer in glyph["layers"]
    }


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
        self.assertEqual(component["transform"], [1, 0, 0, 1, 30, 50])
        self.assertEqual(component["scale"], [1, 1])
        self.assertEqual(layer["anchors"][0]["position"], [260, 720])
        self.assertEqual((layer["width"], layer["vertOrigin"], layer["vertWidth"]), (510, 820, 950))

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

    def test_locks_and_automatic_alignment_are_structural_failures(self) -> None:
        for mutation, message in (("locked", "locked"), ("automatic", "automatic")):
            with self.subTest(mutation=mutation):
                model = _model()
                shape = model["glyphs"]["A"]["layers"][0]["shapes"][1]["value"]
                shape["locked" if mutation == "locked" else "automaticAlignment"] = True
                with self.assertRaisesRegex(ValueError, message):
                    build_change_set(
                        model,
                        [{"op": "translate", "target": _selector(), "delta": {"x": 1, "y": 0}}],
                    )

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
