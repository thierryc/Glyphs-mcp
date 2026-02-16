"""Tests for spacing_engine pure helpers."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


class _FakeGlyph:
    def __init__(self, name: str, script: str = "", category: str = "", sub_category: str = "") -> None:
        self.name = name
        self.script = script
        self.category = category
        self.subCategory = sub_category
        self.unicode = ""
        self.leftMetricsKey = ""
        self.rightMetricsKey = ""


class SpacingEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources_dir()))
        global spacing_engine  # noqa: PLW0603 - simple test import
        import spacing_engine as spacing_engine  # type: ignore

    def test_select_rule_prefers_more_specific_match(self) -> None:
        g = _FakeGlyph(name="A", script="latin", category="Letter", sub_category="Uppercase")
        rules = [
            {"script": "*", "category": "*", "subCategory": "*", "factor": 1.0, "referenceGlyph": "x"},
            {"script": "*", "category": "Letter", "subCategory": "*", "factor": 2.0, "referenceGlyph": "H"},
            {
                "script": "latin",
                "category": "Letter",
                "subCategory": "Uppercase",
                "nameFilter": "A",
                "factor": 3.0,
                "referenceGlyph": "H",
            },
        ]
        picked = spacing_engine.select_rule(g, rules)
        self.assertEqual(picked.get("factor"), 3.0)

    def test_select_rule_tie_break_prefers_later_rule(self) -> None:
        g = _FakeGlyph(name="a", script="latin", category="Letter", sub_category="Lowercase")
        rules = [
            {"script": "latin", "category": "Letter", "subCategory": "Lowercase", "factor": 1.0},
            {"script": "latin", "category": "Letter", "subCategory": "Lowercase", "factor": 2.0},
        ]
        picked = spacing_engine.select_rule(g, rules)
        self.assertEqual(picked.get("factor"), 2.0)

    def test_scale_params_matches_ht_model(self) -> None:
        # areaUPM = area * (upm/1000)^2 ; whiteArea = areaUPM * factor * 100
        out = spacing_engine._scale_params(upm=1000, x_height=500, area=400, factor=1.0)  # type: ignore[attr-defined]
        self.assertEqual(out, 400.0 * 1.0 * 100.0)

    def test_resolve_param_precedence(self) -> None:
        # 1) per-call defaults wins
        val = spacing_engine.resolve_param_precedence(
            field="area",
            per_call_defaults={"area": 111},
            master_custom={"cx.ap.spacingArea": 200, "gmcpSpacingArea": 222, "paramArea": 333},
            font_custom={"cx.ap.spacingArea": 400, "gmcpSpacingArea": 444, "paramArea": 555},
            fallback=999,
        )
        self.assertEqual(val, 111)

        # 2) master canonical (cx.ap.*)
        val = spacing_engine.resolve_param_precedence(
            field="area",
            per_call_defaults={},
            master_custom={"cx.ap.spacingArea": 200, "gmcpSpacingArea": 222, "paramArea": 333},
            font_custom={"cx.ap.spacingArea": 400, "gmcpSpacingArea": 444, "paramArea": 555},
            fallback=999,
        )
        self.assertEqual(val, 200)

        # 3) master legacy (gmcpSpacing*)
        val = spacing_engine.resolve_param_precedence(
            field="area",
            per_call_defaults={},
            master_custom={"gmcpSpacingArea": 222, "paramArea": 333},
            font_custom={"cx.ap.spacingArea": 400, "gmcpSpacingArea": 444, "paramArea": 555},
            fallback=999,
        )
        self.assertEqual(val, 222)

        # 4) master legacy (param*)
        val = spacing_engine.resolve_param_precedence(
            field="area",
            per_call_defaults={},
            master_custom={"paramArea": 333},
            font_custom={"cx.ap.spacingArea": 400, "gmcpSpacingArea": 444, "paramArea": 555},
            fallback=999,
        )
        self.assertEqual(val, 333)

        # 5) font canonical (cx.ap.*)
        val = spacing_engine.resolve_param_precedence(
            field="area",
            per_call_defaults={},
            master_custom={},
            font_custom={"cx.ap.spacingArea": 400, "gmcpSpacingArea": 444, "paramArea": 555},
            fallback=999,
        )
        self.assertEqual(val, 400)

        # 6) font legacy (gmcpSpacing*)
        val = spacing_engine.resolve_param_precedence(
            field="area",
            per_call_defaults={},
            master_custom={},
            font_custom={"gmcpSpacingArea": 444, "paramArea": 555},
            fallback=999,
        )
        self.assertEqual(val, 444)

        # 7) font legacy (param*)
        val = spacing_engine.resolve_param_precedence(
            field="area",
            per_call_defaults={},
            master_custom={},
            font_custom={"paramArea": 555},
            fallback=999,
        )
        self.assertEqual(val, 555)

        # 8) fallback
        val = spacing_engine.resolve_param_precedence(
            field="area",
            per_call_defaults={},
            master_custom={},
            font_custom={},
            fallback=999,
        )
        self.assertEqual(val, 999)

    def test_clamp_suggestion_limits_deltas_and_mins(self) -> None:
        current = {"lsb": 0, "rsb": 0}
        suggested = {"lsb": 500, "rsb": -500}
        clamp = {"maxDeltaLSB": 150, "maxDeltaRSB": 150, "minLSB": -100, "minRSB": -100}
        out, warnings = spacing_engine.clamp_suggestion(current=current, suggested=suggested, clamp=clamp)
        self.assertEqual(out["lsb"], 150)
        # Suggested rsb delta is -500; clamp to -150, then minRSB keeps it at -100.
        self.assertEqual(out["rsb"], -100)
        self.assertIn("clamped_lsb_delta", warnings)
        self.assertIn("clamped_rsb_delta", warnings)
        self.assertIn("clamped_rsb_min", warnings)

    def test_diagonize_left_limits_slope(self) -> None:
        xs = [0.0, 100.0, 300.0]
        out = spacing_engine._diagonize_left(xs, step=50.0)  # type: ignore[attr-defined]
        self.assertLessEqual(out[1] - out[0], 50.0)
        self.assertLessEqual(out[2] - out[1], 50.0)


if __name__ == "__main__":
    unittest.main()
