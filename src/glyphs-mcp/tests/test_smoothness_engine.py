"""Tests for smoothness_engine pure helpers."""

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


class SmoothnessEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources_dir()))
        global smoothness_engine  # noqa: PLW0603 - simple test import
        import smoothness_engine as smoothness_engine  # type: ignore

    def test_perfect_collinear_handles_is_candidate(self) -> None:
        # Join at index 2: prev=1 offcurve, next=3 offcurve
        nodes = [
            {"x": 0, "y": 0, "type": "curve", "smooth": False},
            {"x": 50, "y": 0, "type": "offcurve"},
            {"x": 100, "y": 0, "type": "curve", "smooth": False},
            {"x": 150, "y": 0, "type": "offcurve"},
            {"x": 200, "y": 0, "type": "curve", "smooth": False},
        ]
        out = smoothness_engine.find_collinear_handle_nodes(
            nodes, closed=False, threshold_deg=3.0, min_handle_len=5.0, node_indices=[2]
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["nodeIndex"], 2)
        self.assertAlmostEqual(out[0]["angleDeg"], 0.0, places=6)

    def test_small_deviation_under_threshold_is_candidate(self) -> None:
        nodes = [
            {"x": 0, "y": 0, "type": "curve", "smooth": False},
            {"x": 50, "y": 0, "type": "offcurve"},
            {"x": 100, "y": 0, "type": "curve", "smooth": False},
            {"x": 150, "y": 2, "type": "offcurve"},  # ~2.29 degrees
            {"x": 200, "y": 0, "type": "curve", "smooth": False},
        ]
        out = smoothness_engine.find_collinear_handle_nodes(
            nodes, closed=False, threshold_deg=3.0, min_handle_len=5.0, node_indices=[2]
        )
        self.assertEqual(len(out), 1)
        self.assertLessEqual(out[0]["angleDeg"], 3.0)

    def test_deviation_over_threshold_is_not_candidate(self) -> None:
        nodes = [
            {"x": 0, "y": 0, "type": "curve", "smooth": False},
            {"x": 50, "y": 0, "type": "offcurve"},
            {"x": 100, "y": 0, "type": "curve", "smooth": False},
            {"x": 150, "y": 10, "type": "offcurve"},  # ~11 degrees
            {"x": 200, "y": 0, "type": "curve", "smooth": False},
        ]
        out = smoothness_engine.find_collinear_handle_nodes(
            nodes, closed=False, threshold_deg=3.0, min_handle_len=5.0, node_indices=[2]
        )
        self.assertEqual(out, [])

    def test_short_handles_are_skipped(self) -> None:
        nodes = [
            {"x": 0, "y": 0, "type": "curve", "smooth": False},
            {"x": 98, "y": 0, "type": "offcurve"},  # length 2
            {"x": 100, "y": 0, "type": "curve", "smooth": False},
            {"x": 150, "y": 0, "type": "offcurve"},
            {"x": 200, "y": 0, "type": "curve", "smooth": False},
        ]
        out = smoothness_engine.find_collinear_handle_nodes(
            nodes, closed=False, threshold_deg=3.0, min_handle_len=5.0, node_indices=[2]
        )
        self.assertEqual(out, [])

    def test_closed_path_wrap_neighbors(self) -> None:
        # Node 0 should see prev as last node (index 5)
        nodes = [
            {"x": 0, "y": 0, "type": "curve", "smooth": False},
            {"x": 50, "y": 0, "type": "offcurve"},
            {"x": 60, "y": 0, "type": "offcurve"},
            {"x": 100, "y": 0, "type": "curve", "smooth": False},
            {"x": 150, "y": 0, "type": "offcurve"},
            {"x": -50, "y": 0, "type": "offcurve"},  # prev handle for node 0
        ]
        out = smoothness_engine.find_collinear_handle_nodes(
            nodes, closed=True, threshold_deg=3.0, min_handle_len=5.0, node_indices=[0]
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["nodeIndex"], 0)

    def test_no_both_handles_is_skipped(self) -> None:
        nodes = [
            {"x": 0, "y": 0, "type": "curve", "smooth": False},
            {"x": 50, "y": 0, "type": "line"},  # not offcurve
            {"x": 100, "y": 0, "type": "curve", "smooth": False},
            {"x": 150, "y": 0, "type": "offcurve"},
            {"x": 200, "y": 0, "type": "curve", "smooth": False},
        ]
        out = smoothness_engine.find_collinear_handle_nodes(
            nodes, closed=False, threshold_deg=3.0, min_handle_len=5.0, node_indices=[2]
        )
        self.assertEqual(out, [])

