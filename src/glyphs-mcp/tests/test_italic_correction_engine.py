"""Tests for the pure balanced italic correction engine."""

from __future__ import annotations

import copy
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
if str(RESOURCES) not in sys.path:
    sys.path.insert(0, str(RESOURCES))

import italic_correction_engine as engine  # noqa: E402


def _path(points, node_type="line", closed=True):
    return {
        "closed": closed,
        "nodes": [
            {"x": float(x), "y": float(y), "type": node_type, "smooth": False}
            for x, y in points
        ],
    }


class ItalicCorrectionEngineTests(unittest.TestCase):
    def test_interpolation_endpoints_are_exact(self) -> None:
        raw = [_path([(0, 0), (10, 0), (10, 20), (0, 20)])]
        cursivy = [_path([(1, 2), (12, 3), (14, 24), (3, 25)])]
        self.assertEqual(engine.interpolate_paths(raw, cursivy, 0.0), raw)
        self.assertEqual(engine.interpolate_paths(raw, cursivy, 1.0), cursivy)

    def test_interpolation_preserves_topology(self) -> None:
        raw = [_path([(0, 0), (10, 0), (10, 20), (0, 20)])]
        cursivy = copy.deepcopy(raw)
        cursivy[0]["nodes"][0]["x"] = 4
        result = engine.interpolate_paths(raw, cursivy, 0.75)
        self.assertEqual(result[0]["nodes"][0]["x"], 3.0)
        self.assertEqual(engine.topology_signature(result), engine.topology_signature(raw))

    def test_incompatible_topology_is_rejected(self) -> None:
        raw = [_path([(0, 0), (10, 0), (10, 20), (0, 20)])]
        other = [_path([(0, 0), (10, 0), (0, 20)])]
        with self.assertRaises(ValueError):
            engine.interpolate_paths(raw, other, 0.5)

    def test_vertical_stem_width_is_restored(self) -> None:
        source = [_path([(0, 0), (100, 0), (100, 800), (0, 800)])]
        slanted = engine.shear_paths(source, angle=12, pivot_y=0)
        result = engine.compensate_stems(source, slanted, strength=1.0, upm=1000, stem_values=[100])
        self.assertEqual(result["diagnostics"]["compensatedPairCount"], 1)
        pair = result["diagnostics"]["compensatedPairs"][0]
        self.assertLess(abs(pair["afterWidth"] - pair["sourceWidth"]), 1e-9)
        self.assertGreater(abs(pair["beforeWidth"] - pair["sourceWidth"]), 0.1)

    def test_diagonal_stem_pair_is_detected(self) -> None:
        source = [_path([(0, 0), (200, 800), (280, 780), (80, -20)])]
        detection = engine.detect_stem_pairs(source, upm=1000, stem_values=[82])
        self.assertEqual(detection["acceptedCount"], 1)

    def test_curve_adjacent_segments_are_not_candidates(self) -> None:
        source = [_path([(0, 0), (100, 0), (100, 800), (0, 800)], node_type="curve")]
        detection = engine.detect_stem_pairs(source, upm=1000)
        self.assertEqual(detection["acceptedCount"], 0)

    def test_conflicting_pairs_are_ranked_without_reusing_nodes(self) -> None:
        source = [_path([(0, 0), (100, 0), (100, 100), (0, 100)])]
        detection = engine.detect_stem_pairs(source, upm=1000)
        self.assertGreaterEqual(detection["detectedCount"], 2)
        self.assertEqual(detection["acceptedCount"], 1)
        self.assertIn("node_conflict", [item["reason"] for item in detection["skipped"]])

    def test_unsafe_compensation_delta_is_skipped(self) -> None:
        source = [_path([(0, 0), (100, 0), (100, 800), (0, 800)])]
        candidate = [_path([(0, 0), (200, 0), (200, 800), (0, 800)])]
        result = engine.compensate_stems(source, candidate, strength=1.0, upm=1000)
        self.assertEqual(result["diagnostics"]["compensatedPairCount"], 0)
        self.assertIn("unsafe_width_delta", [item["reason"] for item in result["diagnostics"]["skippedPairs"]])

    def test_strength_validation_rejects_non_finite_and_out_of_range(self) -> None:
        for value in (-0.1, 1.1, math.inf, math.nan, "bad"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    engine.validate_unit_interval(value, "strength")


if __name__ == "__main__":
    unittest.main()
