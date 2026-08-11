"""Pure regression tests for the independent cubic geometry engine."""

from __future__ import annotations

import importlib.util
import json
import math
import unittest
from pathlib import Path
from unittest import mock


def _module_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
        / "outline_geometry_engine.py"
    )


def _load_engine():
    spec = importlib.util.spec_from_file_location("glyphs_mcp_test_outline_geometry_engine", _module_path())
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _node(x, y, node_type, smooth=False):
    return {"x": float(x), "y": float(y), "type": node_type, "smooth": bool(smooth)}


def _cubic_nodes(p0, p1, p2, p3, *, smooth_end=False):
    return [
        _node(*p0, "line"),
        _node(*p1, "offcurve"),
        _node(*p2, "offcurve"),
        _node(*p3, "curve", smooth=smooth_end),
    ]


def _rotate_point(point, angle_radians):
    cosine = math.cos(angle_radians)
    sine = math.sin(angle_radians)
    return (
        point[0] * cosine - point[1] * sine,
        point[0] * sine + point[1] * cosine,
    )


def _split_cubic(points, t):
    def interpolate(a, b):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    q0 = interpolate(points[0], points[1])
    q1 = interpolate(points[1], points[2])
    q2 = interpolate(points[2], points[3])
    r0 = interpolate(q0, q1)
    r1 = interpolate(q1, q2)
    split = interpolate(r0, r1)
    return (points[0], q0, r0, split), (split, r1, q2, points[3])


class OutlineGeometryEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = _load_engine()

    def test_balanced_tunni_curve_is_below_threshold(self) -> None:
        nodes = _cubic_nodes((0, 0), (30, 0), (100, 70), (100, 100))
        result = self.engine.analyze_tunni_segment(
            nodes,
            3,
            closed=False,
            upm=1000,
            imbalance_threshold=0.05,
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], "below_imbalance_threshold")
        self.assertAlmostEqual(result["ratios"]["start"], 0.3)
        self.assertAlmostEqual(result["ratios"]["end"], 0.3)
        self.assertAlmostEqual(result["tunniPoint"]["x"], 100.0)
        self.assertAlmostEqual(result["tunniPoint"]["y"], 0.0)

    def test_imbalanced_tunni_curve_proposes_arithmetic_mean(self) -> None:
        nodes = _cubic_nodes((0, 0), (20, 0), (100, 60), (100, 100))
        result = self.engine.analyze_tunni_segment(nodes, 3, closed=False, upm=1000)

        self.assertTrue(result["eligible"])
        self.assertAlmostEqual(result["targetRatio"], 0.3)
        self.assertEqual(result["nodeIndices"], {"start": 0, "handle1": 1, "handle2": 2, "end": 3})
        self.assertAlmostEqual(result["proposed"]["handle1"]["x"], 30.0)
        self.assertAlmostEqual(result["proposed"]["handle1"]["y"], 0.0)
        self.assertAlmostEqual(result["proposed"]["handle2"]["x"], 100.0)
        self.assertAlmostEqual(result["proposed"]["handle2"]["y"], 70.0)

    def test_tunni_handle_floor_cannot_be_lowered(self) -> None:
        nodes = _cubic_nodes((0, 0), (0.5, 0), (100, 60), (100, 100))

        result = self.engine.analyze_tunni_segment(
            nodes,
            3,
            closed=False,
            upm=1000,
            min_handle_length=0.0,
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["eligible"])
        self.assertEqual(result["segmentEndNodeIndex"], 3)
        self.assertEqual(result["reason"], "handle_too_short")

    def test_oblique_tunni_geometry_matches_exact_construction(self) -> None:
        # Both handle lines were constructed to meet at T=(210, 120), with
        # endpoint ratios 1/5 and 3/5. This exercises the cross-product solve
        # without relying on horizontal or vertical special cases.
        nodes = _cubic_nodes((10, 20), (50, 40), (198, 168), (180, 240))
        result = self.engine.analyze_tunni_segment(nodes, 3, closed=False, upm=1000)

        self.assertTrue(result["eligible"])
        self.assertAlmostEqual(result["tunniPoint"]["x"], 210.0, places=12)
        self.assertAlmostEqual(result["tunniPoint"]["y"], 120.0, places=12)
        self.assertAlmostEqual(result["ratios"]["start"], 0.2, places=12)
        self.assertAlmostEqual(result["ratios"]["end"], 0.6, places=12)
        self.assertAlmostEqual(result["relativeImbalance"], 2.0 / 3.0, places=12)
        self.assertAlmostEqual(result["targetRatio"], 0.4, places=12)
        self.assertAlmostEqual(result["proposed"]["handle1"]["x"], 90.0, places=12)
        self.assertAlmostEqual(result["proposed"]["handle1"]["y"], 60.0, places=12)
        self.assertAlmostEqual(result["proposed"]["handle2"]["x"], 192.0, places=12)
        self.assertAlmostEqual(result["proposed"]["handle2"]["y"], 192.0, places=12)

    def test_grid_safe_tunni_reports_ideal_and_authoritative_grid_candidate(self) -> None:
        nodes = _cubic_nodes((0, 0), (20, 0), (100, 60), (100, 100))
        for step in (1.0, 0.5, 2.0):
            with self.subTest(step=step):
                result = self.engine.analyze_tunni_segment(
                    nodes, 3, closed=False, upm=1000, grid_step=step
                )
                self.assertTrue(result["eligible"])
                self.assertEqual(result["grid"]["policy"], "font")
                self.assertTrue(result["grid"]["onGrid"])
                self.assertLessEqual(result["grid"]["postRelativeImbalance"], 0.05)
                self.assertLessEqual(result["grid"]["tangentDeviationDeg"]["maximum"], 0.25)
                self.assertEqual(result["idealProposed"]["handle1"]["x"], 30.000000000000004)
                for role in ("handle1", "handle2"):
                    for axis in ("x", "y"):
                        self.assertAlmostEqual(result["proposed"][role][axis] / step, round(result["proposed"][role][axis] / step))

    def test_integral_grid_serializes_coordinates_as_json_integers(self) -> None:
        result = self.engine.analyze_tunni_segment(
            _cubic_nodes((0, 0), (20, 0), (100, 60), (100, 100)),
            3,
            closed=False,
            upm=1000,
            grid_step=1,
        )

        self.assertIs(type(result["proposed"]["handle1"]["x"]), int)
        self.assertIs(type(result["proposed"]["handle2"]["y"]), int)
        self.assertIs(type(result["proposed"]["deltas"]["handle1"]["x"]), int)

    def test_negative_half_grid_and_proportional_grid_scaling(self) -> None:
        nodes = _cubic_nodes((-100, -100), (-80, -100), (0, -40), (0, 0))
        result = self.engine.analyze_tunni_segment(nodes, 3, closed=False, upm=1000, grid_step=0.5)
        scaled = [
            {**node, "x": node["x"] * 2.0, "y": node["y"] * 2.0}
            for node in nodes
        ]
        scaled_result = self.engine.analyze_tunni_segment(
            scaled, 3, closed=False, upm=2000, grid_step=1.0
        )

        self.assertTrue(result["eligible"])
        self.assertTrue(scaled_result["eligible"])
        for role in ("handle1", "handle2"):
            self.assertAlmostEqual(scaled_result["proposed"][role]["x"], result["proposed"][role]["x"] * 2.0)
            self.assertAlmostEqual(scaled_result["proposed"][role]["y"], result["proposed"][role]["y"] * 2.0)

    def test_grid_search_has_stable_impossible_candidate_reason(self) -> None:
        nodes = _cubic_nodes((0, 0), (20, 0), (100, 60), (100, 100))
        result = self.engine.analyze_tunni_segment(
            nodes, 3, closed=False, upm=1000, grid_step=3.0
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], "no_safe_grid_candidate")
        self.assertFalse(result["grid"]["onGrid"])

    def test_continuous_policy_remains_explicit_and_fractional(self) -> None:
        nodes = _cubic_nodes((0, 0), (20, 0), (100, 60), (100, 100))
        result = self.engine.analyze_tunni_segment(nodes, 3, closed=False, upm=1000, grid_step=None)

        self.assertTrue(result["eligible"])
        self.assertEqual(result["grid"], {"policy": "continuous", "onGrid": None})
        self.assertIsInstance(result["proposed"]["handle1"]["x"], float)

    def test_grid_candidate_is_stable_under_grid_translation_reflection_and_reversal(self) -> None:
        points = ((0, 0), (20, 0), (100, 60), (100, 100))
        translated = tuple((x + 12, y - 8) for x, y in points)
        reflected = tuple((-x, y) for x, y in points)
        reversed_points = tuple(reversed(points))
        base = self.engine.analyze_tunni_segment(
            _cubic_nodes(*points), 3, closed=False, upm=1000, grid_step=2
        )
        moved = self.engine.analyze_tunni_segment(
            _cubic_nodes(*translated), 3, closed=False, upm=1000, grid_step=2
        )
        mirrored = self.engine.analyze_tunni_segment(
            _cubic_nodes(*reflected), 3, closed=False, upm=1000, grid_step=2
        )
        reversed_result = self.engine.analyze_tunni_segment(
            _cubic_nodes(*reversed_points), 3, closed=False, upm=1000, grid_step=2
        )

        self.assertEqual(moved["proposed"]["handle1"]["x"], base["proposed"]["handle1"]["x"] + 12)
        self.assertEqual(moved["proposed"]["handle2"]["y"], base["proposed"]["handle2"]["y"] - 8)
        self.assertEqual(mirrored["proposed"]["handle1"]["x"], -base["proposed"]["handle1"]["x"])
        self.assertEqual(mirrored["proposed"]["handle2"]["x"], -base["proposed"]["handle2"]["x"])
        self.assertEqual(reversed_result["proposed"]["handle1"], base["proposed"]["handle2"])
        self.assertEqual(reversed_result["proposed"]["handle2"], base["proposed"]["handle1"])

    def test_tunni_ratios_are_translation_and_scale_invariant(self) -> None:
        base = _cubic_nodes((0, 0), (20, 0), (100, 60), (100, 100))
        transformed = [
            {**node, "x": node["x"] * 2.5 + 17.0, "y": node["y"] * 2.5 - 23.0}
            for node in base
        ]
        a = self.engine.analyze_tunni_segment(base, 3, closed=False, upm=1000)
        b = self.engine.analyze_tunni_segment(transformed, 3, closed=False, upm=2500)

        self.assertAlmostEqual(a["ratios"]["start"], b["ratios"]["start"])
        self.assertAlmostEqual(a["ratios"]["end"], b["ratios"]["end"])
        self.assertAlmostEqual(a["relativeImbalance"], b["relativeImbalance"])

    def test_tunni_ratios_are_rotation_and_reversal_invariant(self) -> None:
        points = ((0, 0), (20, 0), (100, 60), (100, 100))
        rotated = tuple(_rotate_point(point, math.radians(37.0)) for point in points)
        reversed_points = tuple(reversed(points))

        original = self.engine.analyze_tunni_segment(_cubic_nodes(*points), 3, closed=False, upm=1000)
        rotated_result = self.engine.analyze_tunni_segment(
            _cubic_nodes(*rotated), 3, closed=False, upm=1000
        )
        reversed_result = self.engine.analyze_tunni_segment(
            _cubic_nodes(*reversed_points), 3, closed=False, upm=1000
        )

        self.assertAlmostEqual(original["ratios"]["start"], rotated_result["ratios"]["start"], places=13)
        self.assertAlmostEqual(original["ratios"]["end"], rotated_result["ratios"]["end"], places=13)
        self.assertAlmostEqual(original["relativeImbalance"], rotated_result["relativeImbalance"], places=13)
        self.assertAlmostEqual(original["ratios"]["start"], reversed_result["ratios"]["end"], places=13)
        self.assertAlmostEqual(original["ratios"]["end"], reversed_result["ratios"]["start"], places=13)
        self.assertAlmostEqual(original["relativeImbalance"], reversed_result["relativeImbalance"], places=13)

    def test_closed_path_wrap_extracts_cubic(self) -> None:
        nodes = [
            _node(100, 60, "offcurve"),
            _node(100, 100, "curve"),
            _node(0, 0, "line"),
            _node(20, 0, "offcurve"),
        ]
        segment = self.engine.extract_cubic_segment(nodes, 1, closed=True)

        self.assertTrue(segment["ok"])
        self.assertEqual(segment["nodeIndices"], {"start": 2, "handle1": 3, "handle2": 0, "end": 1})
        self.assertEqual(self.engine.extract_cubic_segment(nodes, 1, closed=False)["reason"], "open_path_boundary")

    def test_closed_path_start_rotation_preserves_extracted_cubic(self) -> None:
        nodes = [
            _node(100, 60, "offcurve"),
            _node(100, 100, "curve"),
            _node(0, 0, "line"),
            _node(20, 0, "offcurve"),
        ]
        rotated_nodes = nodes[1:] + nodes[:1]

        original = self.engine.extract_cubic_segment(nodes, 1, closed=True)
        rotated = self.engine.extract_cubic_segment(rotated_nodes, 0, closed=True)

        self.assertTrue(original["ok"])
        self.assertTrue(rotated["ok"])
        self.assertEqual(original["points"], rotated["points"])

    def test_closed_path_with_too_few_nodes_is_rejected(self) -> None:
        nodes = [_node(0, 0, "offcurve"), _node(10, 10, "curve"), _node(20, 0, "offcurve")]
        result = self.engine.extract_cubic_segment(nodes, 1, closed=True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "insufficient_nodes")

    def test_tunni_rejection_reasons_are_stable(self) -> None:
        parallel = _cubic_nodes((0, 0), (30, 0), (70, 100), (100, 100))
        zero = _cubic_nodes((0, 0), (0, 0), (100, 60), (100, 100))
        excessive = _cubic_nodes((0, 0), (20, 0), (2000, 20), (2000, 2000))
        nonfinite = _cubic_nodes((0, 0), (math.inf, 0), (100, 60), (100, 100))

        self.assertEqual(
            self.engine.analyze_tunni_segment(parallel, 3, closed=False, upm=1000)["reason"],
            "parallel_handle_lines",
        )
        self.assertEqual(
            self.engine.analyze_tunni_segment(zero, 3, closed=False, upm=1000)["reason"],
            "handle_too_short",
        )
        self.assertEqual(
            self.engine.analyze_tunni_segment(excessive, 3, closed=False, upm=1000)["reason"],
            "proposed_movement_too_large",
        )
        self.assertEqual(
            self.engine.analyze_tunni_segment(nonfinite, 3, closed=False, upm=1000)["reason"],
            "nonfinite_coordinate",
        )

    def test_tunni_unsafe_intersections_and_ratio_bounds_are_rejected(self) -> None:
        cases = {
            "intersection_behind_endpoint": _cubic_nodes((0, 0), (20, 0), (0, 50), (100, 100)),
            "intersection_too_distant": _cubic_nodes((0, 0), (90, 0), (900, 900), (0, 1000)),
            "ratio_too_low": _cubic_nodes((0, 0), (5, 0), (200, 800), (0, 1000)),
            "ratio_too_high": _cubic_nodes((0, 0), (100, 0), (50, 50), (0, 100)),
        }

        for name, nodes in cases.items():
            with self.subTest(case=name):
                result = self.engine.analyze_tunni_segment(nodes, 3, closed=False, upm=1000)
                self.assertTrue(result["ok"])
                self.assertFalse(result["eligible"])
                self.assertEqual(result["segmentEndNodeIndex"], 3)
                expected = "ratio_out_of_bounds" if name.startswith("ratio_") else name
                self.assertEqual(result["reason"], expected)

    def test_malformed_segments_have_stable_rejection_schema(self) -> None:
        malformed = {
            "end_node_not_curve": _cubic_nodes((0, 0), (20, 0), (100, 60), (100, 100)),
            "missing_cubic_handles": _cubic_nodes((0, 0), (20, 0), (100, 60), (100, 100)),
            "missing_start_oncurve": _cubic_nodes((0, 0), (20, 0), (100, 60), (100, 100)),
        }
        malformed["end_node_not_curve"][3]["type"] = "line"
        malformed["missing_cubic_handles"][1]["type"] = "line"
        malformed["missing_start_oncurve"][0]["type"] = "offcurve"

        for expected_reason, nodes in malformed.items():
            with self.subTest(reason=expected_reason):
                result = self.engine.extract_cubic_segment(nodes, 3, closed=False)
                self.assertEqual(
                    {key: result[key] for key in ("ok", "eligible", "segmentEndNodeIndex", "reason")},
                    {
                        "ok": False,
                        "eligible": False,
                        "segmentEndNodeIndex": 3,
                        "reason": expected_reason,
                    },
                )

        invalid_index = self.engine.extract_cubic_segment([], "not-an-index", closed=False)
        self.assertEqual(invalid_index["segmentEndNodeIndex"], None)
        self.assertFalse(invalid_index["eligible"])
        self.assertEqual(invalid_index["reason"], "invalid_segment_index")

        invalid_coordinate = _cubic_nodes((0, 0), (20, 0), (100, 60), (100, 100))
        invalid_coordinate[1]["x"] = "not-a-coordinate"
        rejected_coordinate = self.engine.extract_cubic_segment(invalid_coordinate, 3, closed=False)
        self.assertFalse(rejected_coordinate["eligible"])
        self.assertEqual(rejected_coordinate["segmentEndNodeIndex"], 3)
        self.assertEqual(rejected_coordinate["reason"], "nonfinite_coordinate")

    def test_engine_indices_are_strict_and_path_analysis_preserves_rejections(self) -> None:
        nodes = _cubic_nodes((0, 0), (20, 0), (100, 60), (100, 100))
        invalid_indices = [True, 3.0, "3"]

        for value in invalid_indices:
            with self.subTest(extraction=value):
                result = self.engine.extract_cubic_segment(nodes, value, closed=False)
                self.assertFalse(result["ok"])
                self.assertFalse(result["eligible"])
                self.assertIsNone(result["segmentEndNodeIndex"])
                self.assertEqual(result["reason"], "invalid_segment_index")

        requested = invalid_indices + [3]
        tunni = self.engine.analyze_tunni_path(
            nodes,
            closed=False,
            upm=1000,
            segment_end_node_indices=requested,
        )
        self.assertEqual(len(tunni), len(requested))
        for rejected in tunni[:3]:
            self.assertFalse(rejected["ok"])
            self.assertFalse(rejected["eligible"])
            self.assertIsNone(rejected["segmentEndNodeIndex"])
            self.assertEqual(rejected["reason"], "invalid_segment_index")
        self.assertTrue(tunni[3]["ok"])
        self.assertEqual(tunni[3]["segmentEndNodeIndex"], 3)

        quality = self.engine.analyze_curve_quality_path(
            nodes,
            closed=False,
            upm=1000,
            segment_end_node_indices=requested,
        )
        self.assertEqual(quality["summary"]["requestedSegmentCount"], len(requested))
        self.assertEqual(len(quality["segments"]), len(requested))
        for rejected in quality["segments"][:3]:
            self.assertFalse(rejected["ok"])
            self.assertFalse(rejected["eligible"])
            self.assertIsNone(rejected["segmentEndNodeIndex"])
            self.assertEqual(rejected["reason"], "invalid_segment_index")
        self.assertTrue(quality["segments"][3]["ok"])
        self.assertEqual(quality["segments"][3]["segmentEndNodeIndex"], 3)

    def test_engine_rejects_nonfinite_thresholds_with_reason_codes(self) -> None:
        nodes = _cubic_nodes((0, 0), (20, 0), (100, 60), (100, 100))
        tunni_cases = (
            ({"upm": math.nan}, "invalid_upm"),
            ({"imbalance_threshold": math.inf}, "invalid_imbalance_threshold"),
            ({"min_handle_length": math.nan}, "invalid_min_handle_length"),
        )
        for kwargs, expected_reason in tunni_cases:
            with self.subTest(reason=expected_reason):
                result = self.engine.analyze_tunni_segment(nodes, 3, closed=False, **kwargs)
                self.assertFalse(result["ok"])
                self.assertFalse(result["eligible"])
                self.assertEqual(result["reason"], expected_reason)

        curve_cases = (
            ({"upm": math.inf}, "invalid_upm"),
            ({"upm": 1000, "discontinuity_threshold": math.nan}, "invalid_discontinuity_threshold"),
            ({"upm": 1000, "spike_ratio_threshold": math.inf}, "invalid_spike_ratio_threshold"),
        )
        for kwargs, expected_reason in curve_cases:
            with self.subTest(reason=expected_reason):
                result = self.engine.analyze_curve_quality_path(nodes, closed=False, **kwargs)
                self.assertFalse(result["ok"])
                self.assertEqual(result["reason"], expected_reason)

    def test_sample_count_is_odd_and_bounded(self) -> None:
        self.assertEqual(self.engine.clamp_samples_per_curve(2), 9)
        self.assertEqual(self.engine.clamp_samples_per_curve(50), 51)
        self.assertEqual(self.engine.clamp_samples_per_curve(999), 257)

    def test_line_cubic_has_zero_curvature(self) -> None:
        nodes = _cubic_nodes((0, 0), (100, 0), (200, 0), (300, 0))
        review = self.engine.analyze_curve_quality_path(nodes, closed=False, upm=1000)
        metrics = review["segments"][0]["curvature"]

        self.assertEqual(metrics["maxAbs"], 0.0)
        self.assertEqual(metrics["normalizedMaxAbs"], 0.0)
        self.assertEqual(metrics["spikeRatio"], 0.0)
        self.assertFalse(metrics["spikeRatioInfinite"])
        self.assertEqual(review["segments"][0]["inflectionSignChanges"], 0)

    def test_quarter_circle_has_nearly_constant_positive_curvature(self) -> None:
        k = 4.0 * (math.sqrt(2.0) - 1.0) / 3.0
        points = ((1.0, 0.0), (1.0, k), (k, 1.0), (0.0, 1.0))
        samples = self.engine.curvature_comb_samples(points, sample_count=51)
        curvatures = [sample["curvature"] for sample in samples]

        self.assertTrue(all(value is not None and value > 0 for value in curvatures))
        self.assertLess(max(curvatures) - min(curvatures), 0.03)

    def test_cubic_parabola_matches_analytic_position_derivatives_and_curvature(self) -> None:
        # These control points represent B(t)=(t,t^2) exactly. Therefore
        # B'=(1,2t), B''=(0,2), and k=2/(1+4t^2)^(3/2).
        points = ((0.0, 0.0), (1.0 / 3.0, 0.0), (2.0 / 3.0, 1.0 / 3.0), (1.0, 1.0))
        for t in (0.0, 0.125, 0.25, 0.5, 0.75, 1.0):
            with self.subTest(t=t):
                sample = self.engine.cubic_sample(points, t)
                expected_curvature = 2.0 / math.pow(1.0 + 4.0 * t * t, 1.5)
                self.assertAlmostEqual(sample["point"][0], t, places=14)
                self.assertAlmostEqual(sample["point"][1], t * t, places=14)
                self.assertAlmostEqual(sample["derivative"][0], 1.0, places=14)
                self.assertAlmostEqual(sample["derivative"][1], 2.0 * t, places=14)
                self.assertAlmostEqual(sample["secondDerivative"][0], 0.0, places=14)
                self.assertAlmostEqual(sample["secondDerivative"][1], 2.0, places=14)
                self.assertAlmostEqual(sample["curvature"], expected_curvature, places=13)

    def test_normalized_curvature_is_scale_invariant(self) -> None:
        points = ((0.0, 0.0), (40.0, 120.0), (170.0, -80.0), (250.0, 30.0))
        scale = 3.75
        scaled = tuple((x * scale, y * scale) for x, y in points)

        for t in (0.0, 0.2, 0.5, 0.8, 1.0):
            with self.subTest(t=t):
                base = self.engine.cubic_sample(points, t)["curvature"]
                transformed = self.engine.cubic_sample(scaled, t)["curvature"]
                self.assertIsNotNone(base)
                self.assertIsNotNone(transformed)
                self.assertAlmostEqual(transformed * scale, base, places=13)

        base_nodes = _cubic_nodes(*points)
        scaled_nodes = _cubic_nodes(*scaled)
        base_review = self.engine.analyze_curve_quality_path(base_nodes, closed=False, upm=1000)
        scaled_review = self.engine.analyze_curve_quality_path(
            scaled_nodes,
            closed=False,
            upm=1000 * scale,
        )
        self.assertAlmostEqual(
            base_review["segments"][0]["curvature"]["normalizedMaxAbs"],
            scaled_review["segments"][0]["curvature"]["normalizedMaxAbs"],
            places=12,
        )

    def test_reflection_reverses_signed_curvature_and_preserves_magnitude(self) -> None:
        points = ((0.0, 0.0), (40.0, 120.0), (170.0, -80.0), (250.0, 30.0))
        reflected = tuple((x, -y) for x, y in points)

        for t in (0.0, 0.2, 0.5, 0.8, 1.0):
            with self.subTest(t=t):
                original = self.engine.cubic_sample(points, t)["curvature"]
                mirrored = self.engine.cubic_sample(reflected, t)["curvature"]
                self.assertIsNotNone(original)
                self.assertIsNotNone(mirrored)
                self.assertAlmostEqual(mirrored, -original, places=13)
                self.assertAlmostEqual(abs(mirrored), abs(original), places=13)

    def test_curvature_is_rotation_invariant_and_reversal_changes_sign(self) -> None:
        points = ((0.0, 0.0), (40.0, 120.0), (170.0, -80.0), (250.0, 30.0))
        rotated = tuple(_rotate_point(point, math.radians(-23.0)) for point in points)
        reversed_points = tuple(reversed(points))

        for t in (0.0, 0.2, 0.5, 0.8, 1.0):
            with self.subTest(t=t):
                original = self.engine.cubic_sample(points, t)["curvature"]
                rotated_value = self.engine.cubic_sample(rotated, t)["curvature"]
                reversed_value = self.engine.cubic_sample(reversed_points, 1.0 - t)["curvature"]
                self.assertIsNotNone(original)
                self.assertIsNotNone(rotated_value)
                self.assertIsNotNone(reversed_value)
                self.assertAlmostEqual(rotated_value, original, places=13)
                self.assertAlmostEqual(reversed_value, -original, places=13)

    def test_curvature_is_invariant_under_de_casteljau_subdivision(self) -> None:
        points = ((0.0, 0.0), (40.0, 120.0), (170.0, -80.0), (250.0, 30.0))
        split_t = 0.37
        left, right = _split_cubic(points, split_t)

        for local_t in (0.0, 0.25, 0.6, 1.0):
            with self.subTest(side="left", local_t=local_t):
                original = self.engine.cubic_sample(points, split_t * local_t)["curvature"]
                subdivided = self.engine.cubic_sample(left, local_t)["curvature"]
                self.assertIsNotNone(original)
                self.assertIsNotNone(subdivided)
                self.assertAlmostEqual(subdivided, original, places=12)
            with self.subTest(side="right", local_t=local_t):
                original = self.engine.cubic_sample(
                    points, split_t + (1.0 - split_t) * local_t
                )["curvature"]
                subdivided = self.engine.cubic_sample(right, local_t)["curvature"]
                self.assertIsNotNone(original)
                self.assertIsNotNone(subdivided)
                self.assertAlmostEqual(subdivided, original, places=12)

    def test_inflection_and_degenerate_tangent_are_reported(self) -> None:
        inflection = _cubic_nodes((0, 0), (100, 100), (200, -100), (300, 0))
        cusp = _cubic_nodes((0, 0), (0, 0), (200, 100), (300, 0))

        inflection_review = self.engine.analyze_curve_quality_path(inflection, closed=False, upm=1000)
        cusp_review = self.engine.analyze_curve_quality_path(cusp, closed=False, upm=1000)

        self.assertGreaterEqual(inflection_review["segments"][0]["inflectionSignChanges"], 1)
        self.assertIn(0.0, cusp_review["segments"][0]["degenerateTangents"])
        self.assertIn("degenerate_tangent", [w["code"] for w in cusp_review["segments"][0]["warnings"]])

    def test_smooth_join_curvature_discontinuity_is_flagged(self) -> None:
        nodes = [
            _node(0, 0, "line"),
            _node(50, 0, "offcurve"),
            _node(100, 50, "offcurve"),
            _node(100, 100, "curve", smooth=True),
            _node(100, 150, "offcurve"),
            _node(100, 200, "offcurve"),
            _node(100, 250, "curve"),
        ]
        review = self.engine.analyze_curve_quality_path(
            nodes,
            closed=False,
            upm=1000,
            discontinuity_threshold=0.25,
        )

        self.assertEqual(len(review["joins"]), 1)
        self.assertEqual(review["joins"][0]["warning"]["code"], "curvature_discontinuity")

    def test_exact_parabola_join_is_continuous_without_warning(self) -> None:
        nodes = [
            _node(0, 0, "line"),
            _node(1.0 / 3.0, 0, "offcurve"),
            _node(2.0 / 3.0, 1.0 / 3.0, "offcurve"),
            _node(1, 1, "curve", smooth=True),
            _node(4.0 / 3.0, 5.0 / 3.0, "offcurve"),
            _node(5.0 / 3.0, 8.0 / 3.0, "offcurve"),
            _node(2, 4, "curve"),
        ]

        review = self.engine.analyze_curve_quality_path(nodes, closed=False, upm=1000)

        self.assertEqual(len(review["joins"]), 1)
        self.assertAlmostEqual(review["joins"][0]["relativeDiscontinuity"], 0.0, places=13)
        self.assertIsNone(review["joins"][0]["warning"])

    def test_spike_ratio_uses_exact_median_and_strict_threshold(self) -> None:
        nodes = _cubic_nodes((0, 0), (40, 200), (160, -80), (200, 0))
        segment = self.engine.extract_cubic_segment(nodes, 3, closed=False)
        probe = self.engine.analyze_curve_segment(
            segment,
            upm=1000,
            samples_per_curve=51,
            spike_ratio_threshold=1.0e12,
            include_samples=False,
        )
        ratio = probe["curvature"]["spikeRatio"]
        self.assertIsInstance(ratio, float)
        self.assertGreater(ratio, 1.0)
        self.assertAlmostEqual(
            ratio,
            probe["curvature"]["maxAbs"] / probe["curvature"]["medianAbs"],
            places=13,
        )

        at_boundary = self.engine.analyze_curve_segment(
            segment,
            upm=1000,
            samples_per_curve=51,
            spike_ratio_threshold=ratio,
            include_samples=False,
        )
        below_boundary = self.engine.analyze_curve_segment(
            segment,
            upm=1000,
            samples_per_curve=51,
            spike_ratio_threshold=math.nextafter(ratio, 0.0),
            include_samples=False,
        )
        self.assertNotIn("curvature_spike", [warning["code"] for warning in at_boundary["warnings"]])
        self.assertIn("curvature_spike", [warning["code"] for warning in below_boundary["warnings"]])

    def test_zero_median_nonzero_max_uses_json_safe_infinite_marker(self) -> None:
        nodes = _cubic_nodes((0, 0), (20, 0), (100, 60), (100, 100))
        segment = self.engine.extract_cubic_segment(nodes, 3, closed=False)
        curvatures = [0.0] * 8 + [1.0]
        samples = [
            {
                "t": index / 8.0,
                "point": (float(index), 0.0),
                "derivative": (1.0, 0.0),
                "secondDerivative": (0.0, 0.0),
                "speed": 1.0,
                "curvature": curvature,
            }
            for index, curvature in enumerate(curvatures)
        ]

        with mock.patch.object(self.engine, "curvature_comb_samples", return_value=samples):
            result = self.engine.analyze_curve_segment(
                segment,
                upm=1000,
                samples_per_curve=9,
                spike_ratio_threshold=4.0,
                include_samples=False,
            )

        self.assertIsNone(result["curvature"]["spikeRatio"])
        self.assertTrue(result["curvature"]["spikeRatioInfinite"])
        spike_warning = next(warning for warning in result["warnings"] if warning["code"] == "curvature_spike")
        self.assertIsNone(spike_warning["ratio"])
        self.assertTrue(spike_warning["ratioInfinite"])
        encoded = json.dumps(result, allow_nan=False)
        self.assertNotIn("Infinity", encoded)
        self.assertNotIn("NaN", encoded)

    def test_adaptive_arc_length_matches_line_and_quarter_circle(self) -> None:
        line = ((0.0, 0.0), (100.0 / 3.0, 0.0), (200.0 / 3.0, 0.0), (100.0, 0.0))
        kappa = 4.0 * (math.sqrt(2.0) - 1.0) / 3.0
        circle = ((100.0, 0.0), (100.0, 100.0 * kappa), (100.0 * kappa, 100.0), (0.0, 100.0))

        self.assertAlmostEqual(self.engine.cubic_arc_length(line), 100.0, places=10)
        self.assertAlmostEqual(
            self.engine.cubic_arc_length(circle),
            math.pi * 50.0,
            delta=0.03,
        )

    def test_adaptive_events_have_bounded_parameters_and_known_locations(self) -> None:
        arch = ((0.0, 0.0), (0.0, 100.0), (100.0, 100.0), (100.0, 0.0))
        inflection = ((0.0, 0.0), (100.0, 150.0), (100.0, -150.0), (200.0, 0.0))

        arch_events = self.engine.analyze_curve_events(arch, upm=1000)
        y_extremum = next(event for event in arch_events["extrema"] if event["axis"] == "y")
        self.assertAlmostEqual(y_extremum["t"], 0.5, places=12)
        self.assertAlmostEqual(y_extremum["point"]["y"], 75.0, places=10)

        inflection_events = self.engine.analyze_curve_events(inflection, upm=1000)
        self.assertEqual(len(inflection_events["inflections"]), 1)
        self.assertAlmostEqual(inflection_events["inflections"][0]["t"], 0.5, places=12)
        for collection in ("extrema", "inflections", "stationaryPoints", "cusps"):
            self.assertTrue(
                all(0.0 <= event["t"] <= 1.0 for event in inflection_events[collection])
            )

    def test_stationary_reversal_and_loop_self_intersection_are_reported(self) -> None:
        stationary = ((0.0, 0.0), (100.0, 0.0), (-100.0, 0.0), (0.0, 0.0))
        loop = ((0.0, 0.0), (200.0, 200.0), (-100.0, 200.0), (100.0, 0.0))

        stationary_events = self.engine.analyze_curve_events(stationary, upm=1000)
        loop_events = self.engine.analyze_curve_events(loop, upm=1000)

        self.assertEqual(len(stationary_events["stationaryPoints"]), 2)
        self.assertEqual(len(stationary_events["cusps"]), 2)
        self.assertEqual(len(loop_events["selfIntersections"]), 1)
        crossing = loop_events["selfIntersections"][0]
        self.assertLess(crossing["t1"], crossing["t2"])
        self.assertAlmostEqual(crossing["point"]["x"], 50.0, delta=0.1)

    def test_adaptive_curve_line_join_reports_g0_g1_and_g2(self) -> None:
        nodes = [
            _node(0, 0, "line"),
            _node(100.0 / 3.0, 0, "offcurve"),
            _node(200.0 / 3.0, 0, "offcurve"),
            _node(100, 0, "curve", smooth=True),
            _node(200, 0, "line"),
        ]

        review = self.engine.analyze_curve_quality_path(
            nodes, closed=False, upm=1000, analysis_mode="adaptive"
        )

        self.assertEqual(review["geometryDataVersion"], 2)
        self.assertEqual(review["analysisMode"], "adaptive")
        self.assertEqual(len(review["joins"]), 1)
        join = review["joins"][0]
        self.assertEqual(join["kind"], "curve_line")
        self.assertTrue(join["g0Continuous"])
        self.assertTrue(join["g1Continuous"])
        self.assertTrue(join["g2Continuous"])
        self.assertEqual(join["warnings"], [])

    def test_declared_smooth_mismatch_is_a_warning_not_a_verdict(self) -> None:
        nodes = [
            _node(0, 0, "line"),
            _node(30, 0, "offcurve"),
            _node(70, 0, "offcurve"),
            _node(100, 0, "curve", smooth=True),
            _node(100, 100, "line"),
        ]

        review = self.engine.analyze_curve_quality_path(nodes, closed=False, upm=1000)
        join = review["joins"][0]
        self.assertFalse(join["g1Continuous"])
        self.assertIn(
            "declared_geometric_smooth_mismatch",
            [warning["code"] for warning in join["warnings"]],
        )

    def test_adaptive_arc_length_is_translation_rotation_and_subdivision_invariant(self) -> None:
        points = ((0.0, 0.0), (40.0, 120.0), (170.0, -80.0), (250.0, 30.0))
        translated = tuple((x + 700.0, y - 300.0) for x, y in points)
        rotated = tuple(_rotate_point(point, math.radians(41.0)) for point in points)
        left, right = _split_cubic(points, 0.37)
        length = self.engine.cubic_arc_length(points)

        self.assertAlmostEqual(self.engine.cubic_arc_length(translated), length, places=8)
        self.assertAlmostEqual(self.engine.cubic_arc_length(rotated), length, places=8)
        self.assertAlmostEqual(
            self.engine.cubic_arc_length(left) + self.engine.cubic_arc_length(right),
            length,
            places=6,
        )

    def test_engine_has_no_glyphs_or_objc_imports(self) -> None:
        text = _module_path().read_text(encoding="utf-8")
        self.assertNotIn("import GlyphsApp", text)
        self.assertNotIn("import AppKit", text)
        self.assertNotIn("import objc", text)


if __name__ == "__main__":
    unittest.main()
