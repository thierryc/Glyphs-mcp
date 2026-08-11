"""Pure tests for the native curvature overlay model."""

from __future__ import annotations

import importlib
import math
import sys
import unittest
from pathlib import Path


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


def _node(x, y, node_type):
    return {"x": float(x), "y": float(y), "type": node_type}


def _path(points, direction=None):
    p0, p1, p2, p3 = points
    result = {
        "closed": False,
        "nodes": [
            _node(*p0, "line"),
            _node(*p1, "offcurve"),
            _node(*p2, "offcurve"),
            _node(*p3, "curve"),
        ],
    }
    if direction is not None:
        result["direction"] = direction
    return result


class CurveOverlayModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources_dir()))
        cls.model = importlib.import_module("curve_overlay_model")

    def test_native_defaults_match_png_density_but_keep_shorter_comb(self) -> None:
        path = _path(((0, 0), (20, 0), (100, 60), (100, 100)))
        result = self.model.build_curve_overlay([path], upm=1000)

        self.assertEqual(self.model.DEFAULT_SAMPLES_PER_CURVE, 51)
        self.assertEqual(result["samplesPerCurve"], 51)
        self.assertEqual(result["lengthScale"], 0.010)
        self.assertEqual(result["combLengthClampEm"], 0.12)
        self.assertEqual(result["hardCombLengthClampEm"], 0.25)
        self.assertEqual(result["strokeLimit"], 2000)

    def test_positive_and_negative_curves_have_signed_teeth_and_envelopes(self) -> None:
        positive = _path(((0, 0), (20, 0), (100, 60), (100, 100)))
        negative = _path(((0, 300), (20, 300), (100, 240), (100, 200)))
        result = self.model.build_curve_overlay([positive, negative], samples_per_curve=9)

        signs = {stroke["sign"] for stroke in result["strokes"]}
        envelope_signs = {envelope["sign"] for envelope in result["envelopes"]}
        self.assertEqual(signs, {"positive", "negative"})
        self.assertEqual(envelope_signs, {"positive", "negative"})
        self.assertEqual(result["segmentCount"], 2)
        self.assertEqual(result["strokeCount"], 18)
        self.assertEqual(self.model.OVERLAY_ALPHA, 0.65)
        self.assertTrue(
            all(entry["rgba"][-1] == 0.65 for entry in result["legend"]["entries"])
        )

        # Placement is outside ink, along the path's right normal, while sign
        # remains available for color. Both fixtures start with a rightward
        # tangent, so their first teeth must point downward.
        first_by_sign = {}
        for stroke in result["strokes"]:
            first_by_sign.setdefault(stroke["sign"], stroke)
        self.assertLess(first_by_sign["positive"]["end"][1], first_by_sign["positive"]["start"][1])
        self.assertLess(first_by_sign["negative"]["end"][1], first_by_sign["negative"]["start"][1])
        self.assertIn("right normal", result["legend"]["normalConvention"])
        self.assertIn("correctly wound counters", result["legend"]["pathDirectionRule"])

    def test_straight_cubic_draws_no_comb(self) -> None:
        straight = _path(((0, 0), (30, 0), (70, 0), (100, 0)))
        result = self.model.build_curve_overlay([straight], samples_per_curve=9)

        self.assertEqual(result["strokeCount"], 0)
        self.assertEqual(result["envelopes"], [])
        self.assertEqual(result["zeroCurvatureSampleCount"], 9)

    def test_inflection_splits_envelope_at_sign_change(self) -> None:
        inflection = _path(((0, 0), (100, 150), (100, -150), (200, 0)))
        result = self.model.build_curve_overlay([inflection], samples_per_curve=17)

        self.assertEqual({stroke["sign"] for stroke in result["strokes"]}, {"positive", "negative"})
        self.assertGreaterEqual(len(result["envelopes"]), 2)
        for envelope in result["envelopes"]:
            self.assertGreaterEqual(len(envelope["points"]), 2)

    def test_reflection_flips_sign_and_preserves_comb_lengths(self) -> None:
        path = _path(((0, 0), (20, 0), (100, 60), (100, 100)))
        reflected = {
            "closed": False,
            "nodes": [{**node, "y": -node["y"]} for node in path["nodes"]],
        }
        original = self.model.build_curve_overlay([path], samples_per_curve=9)
        mirrored = self.model.build_curve_overlay([reflected], samples_per_curve=9)

        self.assertTrue(all(stroke["sign"] == "positive" for stroke in original["strokes"]))
        self.assertTrue(all(stroke["sign"] == "negative" for stroke in mirrored["strokes"]))
        for first, second in zip(original["strokes"], mirrored["strokes"]):
            first_length = math.dist(first["start"], first["end"])
            second_length = math.dist(second["start"], second["end"])
            self.assertAlmostEqual(first_length, second_length, places=12)

    def test_reversing_path_flips_right_normal_placement_and_signed_color(self) -> None:
        points = ((0, 0), (20, 0), (100, 60), (100, 100))
        clockwise = _path(points, direction=1)
        counterclockwise = _path(tuple(reversed(points)), direction=-1)

        forward = self.model.build_curve_overlay([clockwise], samples_per_curve=9)
        reverse = self.model.build_curve_overlay([counterclockwise], samples_per_curve=9)

        self.assertEqual(forward["strokeCount"], reverse["strokeCount"])
        self.assertIn("reversing path direction", forward["legend"]["pathDirectionRule"])
        for first, second in zip(forward["strokes"], reversed(reverse["strokes"])):
            self.assertAlmostEqual(first["start"][0], second["start"][0], places=10)
            self.assertAlmostEqual(first["start"][1], second["start"][1], places=10)
            first_vector = (
                first["end"][0] - first["start"][0],
                first["end"][1] - first["start"][1],
            )
            second_vector = (
                second["end"][0] - second["start"][0],
                second["end"][1] - second["start"][1],
            )
            self.assertAlmostEqual(math.hypot(*first_vector), math.hypot(*second_vector), places=10)
            self.assertAlmostEqual(first_vector[0], -second_vector[0], places=10)
            self.assertAlmostEqual(first_vector[1], -second_vector[1], places=10)
            self.assertAlmostEqual(first["curvature"], -second["curvature"], places=12)
            self.assertNotEqual(first["sign"], second["sign"])

        self.assertEqual(
            [point for envelope in forward["envelopes"] for point in envelope["points"]],
            [stroke["end"] for stroke in forward["strokes"]],
        )
        self.assertEqual(
            [point for envelope in reverse["envelopes"] for point in envelope["points"]],
            [stroke["end"] for stroke in reverse["strokes"]],
        )

    def test_proportional_coordinate_and_upm_scaling_scales_comb(self) -> None:
        path = _path(((0, 0), (20, 0), (100, 60), (100, 100)))
        scaled = {
            "closed": False,
            "nodes": [
                {**node, "x": node["x"] * 2.0, "y": node["y"] * 2.0}
                for node in path["nodes"]
            ],
        }
        first = self.model.build_curve_overlay([path], upm=1000, samples_per_curve=9)
        second = self.model.build_curve_overlay([scaled], upm=2000, samples_per_curve=9)

        for a, b in zip(first["strokes"], second["strokes"]):
            self.assertAlmostEqual(b["start"][0], a["start"][0] * 2.0, places=12)
            self.assertAlmostEqual(b["start"][1], a["start"][1] * 2.0, places=12)
            self.assertAlmostEqual(b["end"][0], a["end"][0] * 2.0, places=12)
            self.assertAlmostEqual(b["end"][1], a["end"][1] * 2.0, places=12)

    def test_sampling_reduction_and_hard_stroke_cap_are_deterministic(self) -> None:
        paths = [_path(((0, 0), (20, 0), (100, 60), (100, 100))) for _ in range(4)]
        first = self.model.build_curve_overlay(paths, samples_per_curve=51, stroke_limit=35)
        second = self.model.build_curve_overlay(paths, samples_per_curve=51, stroke_limit=35)

        self.assertEqual(first, second)
        self.assertEqual(first["samplesPerCurve"], 9)
        self.assertEqual(first["strokeCount"], 35)
        self.assertTrue(first["strokeCapReached"])
        self.assertIn("sampling_reduced", [warning["code"] for warning in first["warnings"]])
        self.assertIn("stroke_cap_reached", [warning["code"] for warning in first["warnings"]])

    def test_length_clamp_and_component_omission_are_reported(self) -> None:
        tight = _path(((0, 0), (0.01, 0), (0.01, 0.01), (0, 0.01)))
        result = self.model.build_curve_overlay(
            [tight],
            upm=1000,
            samples_per_curve=9,
            max_length_em=1.0,
            component_count_omitted=2,
        )

        self.assertEqual(result["combLengthClampEm"], self.model.HARD_MAX_LENGTH_EM)
        self.assertGreater(result["clampedStrokeCount"], 0)
        self.assertEqual(result["componentCountOmitted"], 2)
        codes = [warning["code"] for warning in result["warnings"]]
        self.assertIn("comb_length_clamped", codes)
        self.assertIn("components_omitted", codes)

    def test_malformed_path_is_bounded_and_safe(self) -> None:
        malformed = {"closed": False, "nodes": [_node(0, 0, "line"), _node(10, 0, "offcurve")]}
        result = self.model.build_curve_overlay([malformed])

        self.assertEqual(result["segmentCount"], 0)
        self.assertEqual(result["strokeCount"], 0)
        self.assertEqual(result["warnings"], [])

    def test_curve_events_report_extrema_inflection_and_join_warnings(self) -> None:
        inflection = _path(((0, 0), (100, 150), (100, -150), (200, 0)))
        result = self.model.build_curve_events_overlay([inflection], upm=1000)

        kinds = {marker["kind"] for marker in result["markers"]}
        self.assertIn("inflection", kinds)
        self.assertIn("extremum", kinds)
        self.assertLessEqual(result["markerCount"], result["markerLimit"])

    def test_curve_event_marker_cap_is_deterministic(self) -> None:
        paths = [_path(((0, 0), (100, 150), (100, -150), (200, 0))) for _ in range(5)]
        first = self.model.build_curve_events_overlay(paths, marker_limit=3)
        second = self.model.build_curve_events_overlay(paths, marker_limit=3)

        self.assertEqual(first, second)
        self.assertEqual(first["markerCount"], 3)
        self.assertTrue(first["markerCapReached"])
        self.assertEqual(first["warnings"][0]["code"], "event_marker_cap_reached")


if __name__ == "__main__":
    unittest.main()
