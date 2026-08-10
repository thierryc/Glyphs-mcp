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
sys.path.insert(0, str(RESOURCES))

import candidate_difference_model as model  # noqa: E402


def path(points, kinds, closed=False):
    return {
        "closed": closed,
        "nodes": [
            {"x": float(x), "y": float(y), "type": kind}
            for (x, y), kind in zip(points, kinds)
        ],
    }


class CandidateDifferenceModelTests(unittest.TestCase):
    def test_identical_geometry_has_no_visible_difference(self):
        source = [path([(0, 0), (20, 0), (80, 100), (100, 100)], ["line", "offcurve", "offcurve", "curve"])]

        result = model.analyze_difference(source, copy.deepcopy(source))

        self.assertFalse(result["geometryDifferencePresent"])
        self.assertEqual(result["changedPathCount"], 0)
        self.assertEqual(result["maxOutlineDisplacement"], 0.0)
        self.assertFalse(result["samplingTruncated"])

    def test_tunni_fixture_reports_actual_outline_displacement(self):
        source = [
            path(
                [(1615, 1264), (1606, 1145), (1600, 1039), (1630, 895)],
                ["line", "offcurve", "offcurve", "curve"],
            )
        ]
        candidate = copy.deepcopy(source)
        candidate[0]["nodes"][1].update({"x": 1603.0, "y": 1103.0})
        candidate[0]["nodes"][2].update({"x": 1607.0, "y": 1006.0})

        result = model.analyze_difference(source, candidate, samples_per_curve=257)

        self.assertTrue(result["geometryDifferencePresent"])
        self.assertEqual(result["changedPathCount"], 1)
        self.assertAlmostEqual(result["maxNodeMovement"], math.hypot(3.0, 42.0), places=6)
        self.assertAlmostEqual(result["maxOutlineDisplacement"], 28.2545, places=3)

    def test_open_line_and_cubic_paths_are_measured(self):
        source = [
            path([(0, 0), (100, 0)], ["line", "line"]),
            path([(0, 0), (20, 0), (80, 100), (100, 100)], ["line", "offcurve", "offcurve", "curve"]),
        ]
        candidate = copy.deepcopy(source)
        candidate[0]["nodes"][1]["y"] = 10.0
        candidate[1]["nodes"][1]["y"] = 8.0

        result = model.analyze_difference(source, candidate)

        self.assertEqual(result["changedPathCount"], 2)
        self.assertEqual(result["maxNodeMovement"], 10.0)
        self.assertGreater(result["maxOutlineDisplacement"], 9.9)

    def test_topology_mismatch_is_visible_but_not_measured(self):
        source = [path([(0, 0), (100, 0)], ["line", "line"])]
        candidate = [path([(0, 0), (50, 20), (100, 0)], ["line", "line", "line"])]

        result = model.analyze_difference(source, candidate)

        self.assertTrue(result["geometryDifferencePresent"])
        self.assertFalse(result["topologyCompatible"])
        self.assertIsNone(result["maxOutlineDisplacement"])
        self.assertIsNone(result["maxNodeMovement"])

    def test_component_expanded_path_count_change_is_visible(self):
        source = [path([(0, 0), (100, 0), (100, 100)], ["line", "line", "line"], closed=True)]
        candidate = source + [path([(200, 0), (300, 0), (300, 100)], ["line", "line", "line"], closed=True)]

        result = model.analyze_difference(source, candidate)

        self.assertTrue(result["geometryDifferencePresent"])
        self.assertEqual(result["changedPathCount"], 1)
        self.assertFalse(result["topologyCompatible"])

    def test_sampling_is_odd_clamped_and_bounded(self):
        source = [path([(0, 0), (20, 0), (80, 100), (100, 100)], ["line", "offcurve", "offcurve", "curve"])]
        candidate = copy.deepcopy(source)
        candidate[0]["nodes"][1]["x"] = 30.0

        result = model.analyze_difference(source, candidate, samples_per_curve=8, max_samples=5)

        self.assertEqual(result["samplesPerCurve"], 9)
        self.assertEqual(result["sampleCount"], 5)
        self.assertTrue(result["samplingTruncated"])

    def test_nonfinite_coordinates_are_rejected(self):
        source = [path([(0, 0), (100, 0)], ["line", "line"])]
        candidate = copy.deepcopy(source)
        candidate[0]["nodes"][1]["x"] = float("nan")

        with self.assertRaisesRegex(ValueError, "nonfinite_coordinate"):
            model.analyze_difference(source, candidate)


if __name__ == "__main__":
    unittest.main()
