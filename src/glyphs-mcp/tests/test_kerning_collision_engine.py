"""Tests for kerning_collision_engine pure helpers."""

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


class _Pt:
    def __init__(self, x: float) -> None:
        self.x = float(x)


class _Origin:
    def __init__(self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)


class _Size:
    def __init__(self, width: float, height: float) -> None:
        self.width = float(width)
        self.height = float(height)


class _Bounds:
    def __init__(self, min_x: float, max_x: float, min_y: float, max_y: float) -> None:
        self.origin = _Origin(min_x, min_y)
        self.size = _Size(max_x - min_x, max_y - min_y)


class _FakeLayer:
    def __init__(self, *, width: float, bounds: _Bounds, left_fn, right_fn) -> None:
        self.width = float(width)
        self.bounds = bounds
        self._left_fn = left_fn
        self._right_fn = right_fn

    def intersectionsBetweenPoints(self, p1, p2, components=True):  # noqa: ARG002 - API parity
        # p1/p2 are (x,y) tuples in Glyphs.
        y = float(p1[1])
        left = self._left_fn(y)
        right = self._right_fn(y)
        if left is None or right is None:
            return []
        return [_Pt(float(p1[0])), _Pt(float(left)), _Pt(float(right)), _Pt(float(p2[0]))]


class KerningCollisionEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources_dir()))
        global kerning_collision_engine  # noqa: PLW0603 - simple test import
        import kerning_collision_engine as kerning_collision_engine  # type: ignore

    def test_resolve_explicit_kerning_precedence_prefers_glyph_exception(self) -> None:
        kerning_master = {
            "@MMK_L_A": {"@MMK_R_V": -100},
            "idA": {"idV": -80},
        }
        val, src = kerning_collision_engine.resolve_explicit_kerning_value(
            kerning_master=kerning_master,
            left_glyph_id="idA",
            left_glyph_name="A",
            left_class_key="@MMK_L_A",
            right_glyph_id="idV",
            right_glyph_name="V",
            right_class_key="@MMK_R_V",
        )
        self.assertEqual(val, -80.0)
        self.assertEqual(src.left_key, "idA")
        self.assertEqual(src.right_key, "idV")

    def test_compute_bumper_suggestion_uses_ceil_for_safety(self) -> None:
        sug = kerning_collision_engine.compute_bumper_suggestion(
            kerning_value=-80.0,
            measured_min_gap=-12.3,
            target_gap=5.0,
            max_delta=200,
        )
        # needed = 17.3; recommended float = -62.7; ceil -> -62
        self.assertAlmostEqual(sug.bumper_delta, 17.3, places=5)
        self.assertEqual(sug.recommended_exception, -62)

    def test_two_pass_refines_when_near_threshold_and_finds_hidden_collision(self) -> None:
        bounds = _Bounds(-50, 650, 0, 100)

        left_layer = _FakeLayer(
            width=600,
            bounds=bounds,
            left_fn=lambda y: 100.0,
            right_fn=lambda y: 500.0,
        )

        def right_left_edge(y: float) -> float:
            return -20.0 if abs(y - 50.0) < 1e-9 else 0.0

        right_layer = _FakeLayer(
            width=600,
            bounds=bounds,
            left_fn=right_left_edge,
            right_fn=lambda y: 200.0,
        )

        out = kerning_collision_engine.measure_pair_min_gap(
            left_layer=left_layer,
            right_layer=right_layer,
            kerning_value=-88.0,  # shift = 512 => quick gap 12, dense finds -8 at y=50
            scan_mode="two_pass",
            scan_heights=None,
            dense_step=10.0,
            bands=8,
            include_components=True,
            target_gap=5.0,
        )

        self.assertIsNotNone(out)
        assert out is not None
        self.assertTrue(out.refined)
        self.assertAlmostEqual(out.min_gap, -8.0, places=5)
        self.assertEqual(len(out.band_min_gaps), 8)
        # y=50 is in band index floor(0.5*8)=4
        self.assertAlmostEqual(out.band_min_gaps[4], -8.0, places=5)


if __name__ == "__main__":
    unittest.main()

