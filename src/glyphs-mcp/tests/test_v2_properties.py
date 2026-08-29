"""Deterministic property tests for the generic v2 change algebra."""

from __future__ import annotations

import copy
import itertools
import random
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.generic_tools import (  # noqa: E402
    build_change_set,
    evaluate_constraints,
)
from glyphs_mcp_v2.semantic import diff_models, fingerprint_model  # noqa: E402


DOCUMENT_ID = "property-document"


def _layer(identity: str, width: int, x: int) -> dict:
    return {
        "id": identity,
        "masterId": "m0",
        "name": "Regular",
        "isMasterLayer": True,
        "isSpecialLayer": False,
        "roles": ["master"],
        "width": width,
        "anchors": [{"id": "top", "name": "top", "position": [x + 50, 700]}],
        "shapes": [
            {
                "id": "path-{}".format(identity),
                "kind": "path",
                "value": {
                    "closed": True,
                    "nodes": [
                        {"id": "n0", "x": x, "y": 0, "type": "line"},
                        {"id": "n1", "x": x + 100, "y": 700, "type": "line"},
                    ],
                },
            }
        ],
    }


def _model(glyph_count: int = 5) -> dict:
    return {
        "font": {
            "familyName": "Property Font",
            "upm": 1000,
            "grid": 1,
            "gridSubDivision": 1,
        },
        "masters": [{"id": "m0", "name": "Regular"}],
        "instances": [],
        "glyphs": {
            "g{}".format(index): {
                "id": "glyph-{}".format(index),
                "name": "g{}".format(index),
                "export": False,
                "layers": [_layer("l{}".format(index), 500 + index, index * 10)],
            }
            for index in range(glyph_count)
        },
        "kerning": {},
        "features": [],
        "classes": [],
        "featurePrefixes": [],
    }


class _Host:
    def __init__(self, model: dict) -> None:
        self.model = copy.deepcopy(model)
        self.apply_calls = 0

    def capture_model(self, _document_id: str) -> dict:
        return copy.deepcopy(self.model)

    def apply_change_set(self, _document_id: str, change_set) -> None:
        self.apply_calls += 1
        self.model = change_set.apply(self.model)

    def restore_model(self, _document_id: str, model: dict) -> None:
        self.model = copy.deepcopy(model)


class GenericChangeProperties(unittest.TestCase):
    def test_independent_operation_permutations_normalize_to_one_target(self) -> None:
        model = _model(4)
        operations = [
            {
                "op": "set",
                "target": {"entity": "glyph", "ids": ["g{}".format(index)]},
                "field": "export",
                "value": True,
            }
            for index in range(4)
        ]
        expected = None
        for permutation in itertools.permutations(operations):
            build = build_change_set(model, permutation)
            after = build.change_set.apply(model)
            if expected is None:
                expected = after
            self.assertEqual(after, expected)
            resolved = sorted(
                tuple(tuple(path) for path in item["resolvedPaths"])
                for item in build.normalized_operations
            )
            self.assertEqual(
                resolved,
                [(('glyphs', 'g0', 'export'),), (('glyphs', 'g1', 'export'),),
                 (('glyphs', 'g2', 'export'),), (('glyphs', 'g3', 'export'),)],
            )

    def test_constraint_comparisons_follow_numeric_boundaries(self) -> None:
        model = _model(1)
        selector = {"entity": "layer", "ids": ["l0"], "parent": {"glyphName": "g0"}}
        for delta in range(-20, 21):
            result = evaluate_constraints(
                model,
                [
                    {
                        "phase": "before",
                        "left": {"kind": "field", "selector": selector, "field": "width"},
                        "operator": "within",
                        "right": {"kind": "literal", "value": 500 + delta},
                        "tolerance": 10,
                    }
                ],
                phase="before",
            )
            self.assertEqual(result["passed"], abs(delta) <= 10)

    def test_random_semantic_patch_inversion_restores_exact_baseline(self) -> None:
        generator = random.Random(20260829)
        for _case in range(100):
            before = _model(3)
            after = copy.deepcopy(before)
            for index in range(3):
                glyph = after["glyphs"]["g{}".format(index)]
                glyph["export"] = bool(generator.getrandbits(1))
                layer = glyph["layers"][0]
                layer["width"] += generator.randint(-80, 80)
                layer["shapes"][0]["value"]["nodes"][0]["x"] += generator.randint(-20, 20)
            patch = diff_models(before, after)
            self.assertEqual(patch.apply(before), after)
            self.assertEqual(patch.inverse().apply(after), before)

    def test_preview_apply_equivalence_across_physical_changes(self) -> None:
        host = _Host(_model(1))
        application = GlyphsMCPApplication(host)
        for index in range(1, 31):
            before = fingerprint_model(host.model)
            operations = [
                {
                    "op": "set",
                    "target": {
                        "entity": "layer",
                        "ids": ["l0"],
                        "parent": {"glyphName": "g0"},
                    },
                    "field": "width",
                    "value": 500 + index,
                    "quantizer": "exact",
                },
                {
                    "op": "translate",
                    "target": {
                        "entity": "layer",
                        "ids": ["l0"],
                        "parent": {"glyphName": "g0"},
                    },
                    "delta": {"x": 1, "y": -1},
                    "quantizer": "exact",
                },
            ]
            preview = application.invoke(
                "preview_change",
                {
                    "documentId": DOCUMENT_ID,
                    "expectedDocumentFingerprint": before,
                    "operations": operations,
                    "constraints": [],
                },
            ).to_dict()
            self.assertTrue(preview["ok"], preview)
            proposed = preview["data"]["proposedFingerprint"]
            applied = application.invoke(
                "apply_change",
                {
                    "documentId": DOCUMENT_ID,
                    "previewId": preview["data"]["previewId"],
                    "expectedDocumentFingerprint": before,
                    "reason": "property-test exact preview replay",
                },
            ).to_dict()
            self.assertTrue(applied["ok"], applied)
            self.assertEqual(applied["data"]["afterFingerprint"], proposed)
            self.assertEqual(fingerprint_model(host.model), proposed)
        self.assertEqual(host.apply_calls, 30)


if __name__ == "__main__":
    unittest.main()
