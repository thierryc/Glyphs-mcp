"""Pure fixed horizontal IconGrid centering contract tests."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


RESOURCES = (
    Path(__file__).resolve().parent.parent
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)
sys.path.insert(0, str(RESOURCES))

from icon_grid_centering import (  # noqa: E402
    IconGridCenteringError,
    center_candidates,
    content_union,
    propose_reset,
    propose_set,
    resolve_center,
    state_fingerprint,
    validate_policy_root,
)


class IconGridCenteringTests(unittest.TestCase):
    def test_missing_policy_uses_advance_center(self):
        policy = validate_policy_root(None, False)
        center = resolve_center(900, policy)
        self.assertEqual(center["state"], "default")
        self.assertEqual(center["resolvedX"], 450.0)
        self.assertFalse(center["fallback"])

    def test_valid_coordinate_is_fixed_and_accepts_any_finite_real(self):
        for coordinate in (-200, 0, 521.5, 1400):
            root = {"schemaVersion": 1, "centerX": {"mode": "coordinate", "x": coordinate}}
            policy = validate_policy_root(root, True)
            center = resolve_center(1000, policy)
            self.assertEqual(policy["storedX"], float(coordinate))
            self.assertEqual(center["resolvedX"], float(coordinate))
            self.assertFalse(center["fallback"])

    def test_validation_rejects_role_bounds_nonfinite_boolean_and_future_schema(self):
        invalid_values = (
            {"mode": "roleBounds", "role": "body"},
            {"mode": "coordinate", "x": math.nan},
            {"mode": "coordinate", "x": math.inf},
            {"mode": "coordinate", "x": True},
        )
        for center_x in invalid_values:
            malformed = validate_policy_root(
                {"schemaVersion": 1, "centerX": center_x}, True
            )
            self.assertEqual(malformed["state"], "invalid")
            self.assertTrue(resolve_center(1000, malformed)["fallback"])
        future = validate_policy_root({"schemaVersion": 2, "centerX": {}}, True)
        self.assertEqual(future["state"], "unsupported_schema")

    def test_content_union_and_candidates_cover_paths_and_components(self):
        entries = [
            {"kind": "path", "bounds": {"x": 100, "y": 20, "width": 200, "height": 300}},
            {"kind": "component", "bounds": {"x": 700, "y": -10, "width": -100, "height": 50}},
            {"kind": "path", "bounds": {"x": math.nan, "y": 0, "width": 20, "height": 20}},
        ]
        union = content_union(entries)
        self.assertEqual(union["shapeCount"], 3)
        self.assertEqual(union["validShapeCount"], 2)
        self.assertEqual(union["bounds"], {"x": 100.0, "y": -10.0, "width": 600.0, "height": 330.0})
        self.assertEqual(union["centerX"], 400.0)
        candidates = center_candidates(1043, entries)
        self.assertEqual(candidates["advance"]["x"], 521.5)
        self.assertEqual(candidates["layerContent"]["x"], 400.0)
        self.assertTrue(candidates["layerContent"]["available"])

    def test_empty_content_candidate_is_unavailable(self):
        candidates = center_candidates(1000, [])
        self.assertTrue(candidates["advance"]["available"])
        self.assertFalse(candidates["layerContent"]["available"])
        self.assertIsNone(candidates["layerContent"]["x"])

    def test_set_preserves_unknown_fields_and_replaces_obsolete_role_policy(self):
        proposed = propose_set(
            {
                "schemaVersion": 1,
                "future": {"keep": True},
                "centerX": {
                    "mode": "roleBounds",
                    "role": "body",
                    "futureOption": {"keep": True},
                },
            },
            True,
            321.25,
        )
        self.assertEqual(proposed["future"], {"keep": True})
        self.assertEqual(
            proposed["centerX"],
            {"mode": "coordinate", "x": 321.25, "futureOption": {"keep": True}},
        )

    def test_set_rejects_nonfinite_malformed_root_and_future_schema(self):
        for coordinate in (True, None, math.nan, math.inf):
            with self.assertRaises(IconGridCenteringError):
                propose_set(None, False, coordinate)
        with self.assertRaises(IconGridCenteringError):
            propose_set({"centerX": {}}, True, 200)
        with self.assertRaises(IconGridCenteringError):
            propose_set({"schemaVersion": 2, "centerX": {}}, True, 200)

    def test_reset_removes_only_center_and_preserves_unknown_fields(self):
        present, root = propose_reset(
            {
                "schemaVersion": 1,
                "centerX": {"mode": "coordinate", "x": 200},
                "future": {"keep": True},
            },
            True,
        )
        self.assertTrue(present)
        self.assertEqual(root, {"schemaVersion": 1, "future": {"keep": True}})
        present, root = propose_reset(
            {"schemaVersion": 1, "centerX": {"mode": "roleBounds", "role": "body"}},
            True,
        )
        self.assertFalse(present)
        self.assertIsNone(root)

    def test_fingerprint_is_stable_and_misspelled_domain_is_not_defined(self):
        self.assertEqual(state_fingerprint({"b": 2, "a": 1}), state_fingerprint({"a": 1, "b": 2}))
        source = (RESOURCES / "icon_grid_centering.py").read_text(encoding="utf-8")
        self.assertIn('ROOT_KEY = "com.litsquare.icongrid"', source)
        self.assertNotIn("com.leetsquare", source)


if __name__ == "__main__":
    unittest.main()
