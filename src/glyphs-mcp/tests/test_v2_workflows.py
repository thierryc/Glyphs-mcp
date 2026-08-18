"""Pure production review workflows and scale-sensitive result behavior."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.workflows import (  # noqa: E402
    list_instances,
    list_kerning_pairs,
    review_anchor_consistency,
    review_export,
    review_compatibility_updates,
    review_kerning_coverage,
    review_master_compatibility,
    review_metrics_updates,
    build_opentype_updates,
    simulate_spacing,
)


class V2WorkflowTests(unittest.TestCase):
    def test_opentype_updates_share_one_existing_collection_contract(self) -> None:
        model = {
            "features": [
                {
                    "id": "liga",
                    "name": "liga",
                    "code": "sub f i by fi;",
                    "automatic": False,
                    "disabled": False,
                }
            ],
            "classes": [
                {
                    "id": "Uppercase",
                    "name": "Uppercase",
                    "code": "A B",
                    "automatic": False,
                    "disabled": False,
                }
            ],
            "featurePrefixes": [
                {
                    "id": "Languagesystems",
                    "name": "Languagesystems",
                    "code": "languagesystem DFLT dflt;",
                    "automatic": False,
                    "disabled": False,
                }
            ],
        }

        changes = build_opentype_updates(
            model,
            [
                {"kind": "feature", "name": "liga", "code": "sub f f i by ffi;"},
                {"kind": "class", "name": "Uppercase", "disabled": True},
                {"kind": "prefix", "name": "Languagesystems", "automatic": True},
            ],
        )
        after = changes.apply(model)

        self.assertEqual(after["features"][0]["code"], "sub f f i by ffi;")
        self.assertTrue(after["classes"][0]["disabled"])
        self.assertTrue(after["featurePrefixes"][0]["automatic"])
        self.assertEqual(len(changes.changes), 3)

        with self.assertRaisesRegex(ValueError, "automatic false"):
            build_opentype_updates(
                model,
                [{"kind": "feature", "name": "liga", "automatic": True, "code": "sub a by b;"}],
            )

    def test_compatibility_explains_host_and_component_mismatches(self) -> None:
        model = {
            "masters": [{"id": "m1"}, {"id": "m2"}],
            "glyphs": {
                "A": {
                    "export": True,
                    "mastersCompatible": False,
                    "layers": {
                        "m1": {"components": ["A.base"], "pathSignature": [4]},
                        "m2": {"components": ["A.alt"], "pathSignature": [4]},
                    },
                }
            },
        }

        result = review_master_compatibility(model, mode="component_preserving")
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("host_incompatible", codes)
        self.assertIn("component_sequence_mismatch", codes)
        self.assertTrue(result["hasHardFailures"])

    def test_anchor_review_preserves_outliers_as_soft_findings(self) -> None:
        model = {
            "masters": [{"id": "m1"}, {"id": "m2"}],
            "glyphs": {
                "acutecomb": {
                    "layers": {
                        "m1": {"anchors": {"_top": [0, 500], "top": [0, 700]}},
                        "m2": {"anchors": {"_top": [0, 510]}},
                    }
                }
            },
        }
        result = review_anchor_consistency(model)
        self.assertEqual(result["findings"][0]["severity"], "soft")
        self.assertEqual(result["findings"][0]["code"], "anchor_set_difference")

    def test_zero_width_mark_is_a_valid_spacing_skip(self) -> None:
        result = simulate_spacing(
            [{"glyphName": "strokeshortcomb", "width": 0, "category": "Mark"}],
            max_iterations=5,
            tolerance=1,
        )
        item = result["items"][0]
        self.assertEqual(item["status"], "skipped")
        self.assertEqual(item["reason"], "zero_width_mark")
        self.assertNotIn("blocked", repr(item))

    def test_automatically_aligned_width_is_a_host_owned_spacing_skip(self) -> None:
        result = simulate_spacing(
            [
                {
                    "glyphName": "j",
                    "masterId": "m1",
                    "width": 265,
                    "targetWidth": 267,
                    "hostOwnsWidth": True,
                }
            ],
            max_iterations=5,
            tolerance=1,
        )

        item = result["items"][0]
        self.assertEqual(item["status"], "skipped")
        self.assertEqual(item["reason"], "automatic_alignment")
        self.assertEqual(result["actionableCount"], 0)

    def test_spacing_revalidates_dependencies_in_a_bounded_fixed_point(self) -> None:
        result = simulate_spacing(
            [
                {"glyphName": "A", "masterId": "m1", "width": 500, "targetWidth": 600},
                {
                    "glyphName": "Aacute",
                    "masterId": "m1",
                    "width": 500,
                    "referenceGlyphName": "A",
                    "offset": 10,
                },
            ],
            max_iterations=5,
            tolerance=1,
        )
        by_name = {item["glyphName"]: item for item in result["items"]}
        self.assertTrue(result["converged"])
        self.assertLessEqual(result["completedIterations"], 5)
        self.assertEqual(by_name["Aacute"]["proposedWidth"], 610)
        self.assertEqual(result["dependencyCount"], 1)

    def test_kerning_keys_and_instance_axes_are_typed(self) -> None:
        model = {
            "kerning": [
                {
                    "masterId": "m1",
                    "left": {"kind": "group", "id": "@MMK_L_A", "name": "A"},
                    "right": {"kind": "glyph", "id": "-841259840", "name": None},
                    "value": -20,
                }
            ],
            "instances": [
                {
                    "id": "i1",
                    "name": "Variable",
                    "type": "variable",
                    "axes": [{"tag": "wght", "internal": 400, "external": 90}],
                    "included": True,
                    "interpolationSupported": False,
                }
            ],
        }
        pairs = list_kerning_pairs(model)
        self.assertEqual(pairs[0]["right"]["id"], "-841259840")
        self.assertIsNone(pairs[0]["right"]["name"])
        instances = list_instances(model)
        self.assertEqual(instances[0]["axes"][0]["external"], 90)
        self.assertFalse(instances[0]["interpolationSupported"])
        coverage = review_kerning_coverage(model, mode="glyph_expansion")
        self.assertEqual(coverage["eligibleCount"], 1)
        self.assertEqual(coverage["measuredCount"], 0)
        self.assertEqual(coverage["untestedCount"], 1)
        self.assertTrue(coverage["accountingComplete"])
        self.assertFalse(coverage["complete"])

    def test_export_blocks_hard_findings_and_nonempty_destinations(self) -> None:
        compatibility = {"hasHardFailures": True, "findings": [{"id": "f1"}]}
        blocked = review_export(
            destination_state={"exists": True, "empty": False, "fingerprint": "dest_a"},
            compatibility=compatibility,
            overwrite_policy="fail_if_nonempty",
        )
        self.assertFalse(blocked["ready"])
        self.assertIn("destination_not_empty", blocked["blockingCodes"])
        self.assertIn("hard_compatibility_failure", blocked["blockingCodes"])

    def test_metrics_and_compatibility_batches_are_explicit_semantic_patches(self) -> None:
        model = {
            "glyphs": {
                "A": {
                    "layers": {
                        "m1": {
                            "leftMetricsKey": None,
                            "rightMetricsKey": None,
                            "widthMetricsKey": None,
                            "paths": [],
                            "components": [],
                            "pathSignature": [],
                        }
                    }
                }
            }
        }
        metrics = review_metrics_updates(
            model,
            [{"glyphName": "A", "masterId": "m1", "leftMetricsKey": "=H"}],
        )
        self.assertEqual(metrics.apply(model)["glyphs"]["A"]["layers"]["m1"]["leftMetricsKey"], "=H")

        compatibility = review_compatibility_updates(
            model,
            [
                {
                    "glyphName": "A",
                    "masterId": "m1",
                    "components": [{"name": "A.base", "transform": [1, 0, 0, 1, 0, 0]}],
                }
            ],
        )
        self.assertEqual(
            compatibility.apply(model)["glyphs"]["A"]["layers"]["m1"]["components"][0]["name"],
            "A.base",
        )


if __name__ == "__main__":
    unittest.main()
