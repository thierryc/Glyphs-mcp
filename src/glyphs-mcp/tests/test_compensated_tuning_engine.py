"""Tests for compensated_tuning_engine pure helpers."""

from __future__ import annotations

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


class CompensatedTuningEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources_dir()))
        global compensated_tuning_engine  # noqa: PLW0603 - simple test import
        import compensated_tuning_engine as compensated_tuning_engine  # type: ignore

    def test_compute_q_geometric_is_one(self) -> None:
        q = compensated_tuning_engine.compute_q(scale=0.8, b=1.7, a=1.0)
        self.assertAlmostEqual(q, 1.0, places=9)

    def test_compute_q_full_compensation_matches_known_value(self) -> None:
        # a=0 => q = (1/s - b)/(1 - b)
        q = compensated_tuning_engine.compute_q(scale=0.8, b=1.7, a=0.0)
        self.assertAlmostEqual(q, 0.6428571428571429, places=9)

    def test_compute_q_scale_one_is_one(self) -> None:
        q = compensated_tuning_engine.compute_q(scale=1.0, b=1.7, a=0.3)
        self.assertAlmostEqual(q, 1.0, places=9)

    def test_compute_q_rejects_b_one(self) -> None:
        with self.assertRaises(ValueError):
            compensated_tuning_engine.compute_q(scale=0.9, b=1.0, a=0.0)

    def test_black_runs_from_intersections_pairs(self) -> None:
        runs = compensated_tuning_engine.black_runs_from_intersections([10, 30, 50, 70])
        self.assertEqual(runs, [20.0, 20.0])

    def test_black_runs_ignores_odd_tail(self) -> None:
        runs = compensated_tuning_engine.black_runs_from_intersections([10, 30, 50])
        self.assertEqual(runs, [20.0])

    def test_stem_thickness_from_scanlines_median_of_medians(self) -> None:
        scanlines = [
            [10, 30, 50, 70],  # runs 20,20 -> median 20
            [12, 32, 52, 72],  # runs 20,20 -> median 20
            [9, 29, 49, 69],  # runs 20,20 -> median 20
        ]
        stem = compensated_tuning_engine.stem_thickness_from_scanlines(scanlines_xs=scanlines, min_width=1.0, max_width=200.0)
        self.assertAlmostEqual(stem or 0.0, 20.0, places=9)

    def test_transform_point_matches_expected_italic_preservation(self) -> None:
        # When base==ref, q doesn't matter; formula becomes italic-preserving anisotropic scaling:
        # x = sx*(x - y*i) + (sy*y)*i
        shear = 0.2
        x, y = compensated_tuning_engine.transform_point(
            xr=100,
            yr=200,
            xb=100,
            yb=200,
            sx=0.8,
            sy=1.0,
            qx=0.5,
            qy=0.5,
            shear=shear,
            tx=0.0,
            ty=0.0,
        )
        self.assertAlmostEqual(y, 200.0, places=9)
        self.assertAlmostEqual(x, 88.0, places=9)


if __name__ == "__main__":
    unittest.main()

