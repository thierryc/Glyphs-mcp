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
    def __init__(
        self,
        name: str,
        script: str = "",
        category: str = "",
        sub_category: str = "",
        unicode_value: str = "",
    ) -> None:
        self.name = name
        self.script = script
        self.category = category
        self.subCategory = sub_category
        self.unicode = unicode_value
        self.glyphInfo = None
        self.leftMetricsKey = ""
        self.rightMetricsKey = ""
        self.widthMetricsKey = ""
        self.layers = {}


class _Origin:
    def __init__(self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)


class _Size:
    def __init__(self, width: float, height: float) -> None:
        self.width = float(width)
        self.height = float(height)


class _Bounds:
    def __init__(self, x: float, y: float, width: float, height: float) -> None:
        self.origin = _Origin(x, y)
        self.size = _Size(width, height)


class _GeometryLayer:
    def __init__(self, width: float, height: float, edge_fn, lsb: float = 0, rsb: float = 0) -> None:
        self.width = float(width)
        self.leftSideBearing = float(lsb)
        self.rightSideBearing = float(rsb)
        self.bounds = _Bounds(0, 0, width, height)
        self.paths = [object()]
        self.components = []
        self.isAligned = False
        self.leftMetricsKey = ""
        self.rightMetricsKey = ""
        self.widthMetricsKey = ""
        self._edge_fn = edge_fn

    def intersectionsBetweenPoints(self, p1, p2, components=True):  # noqa: ARG002 - API parity
        y = float(p1[1])
        if y < 0 or y > self.bounds.size.height:
            return []
        left, right = self._edge_fn(y)
        return [_Pt(p1[0]), _Pt(left), _Pt(right), _Pt(p2[0])]


class _FakeFont:
    def __init__(self, glyphs, upm: int = 1000, fixed_pitch=None, family_name: str = "Synthetic") -> None:
        self.glyphs = {glyph.name: glyph for glyph in glyphs}
        self.upm = upm
        self.familyName = family_name
        self.customParameters = {}
        if fixed_pitch is not None:
            self.customParameters["isFixedPitch"] = fixed_pitch


class _FakeMaster:
    def __init__(self, master_id: str = "m1", x_height: float = 500, italic_angle: float = 0) -> None:
        self.id = master_id
        self.name = "Master"
        self.xHeight = x_height
        self.italicAngle = italic_angle


class _Pt:
    def __init__(self, x: float) -> None:
        self.x = float(x)


class _NegativeIndexProxy:
    def __init__(self, values) -> None:
        self._values = list(values)

    def __len__(self) -> int:
        return len(self._values)

    def __getitem__(self, index: int):
        if index < 0:
            raise IndexError("negative indexes are not supported")
        return self._values[index]

    def __iter__(self):
        return iter(self._values)


class _ProxyIntersectionLayer:
    def intersectionsBetweenPoints(self, p1, p2, components=True):  # noqa: ARG002 - API parity
        return _NegativeIndexProxy([_Pt(p1[0]), _Pt(10), _Pt(90), _Pt(p2[0])])


class SpacingEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources_dir()))
        global spacing_engine  # noqa: PLW0603 - simple test import
        import spacing_engine as spacing_engine  # type: ignore

    def _glyph_with_layer(
        self,
        name: str,
        *,
        category: str = "Letter",
        sub_category: str = "",
        unicode_value: str = "",
        width: float = 600,
        height: float = 700,
        edge_fn=None,
        lsb: float = 40,
        rsb: float = 40,
    ):
        glyph = _FakeGlyph(name, category=category, sub_category=sub_category, unicode_value=unicode_value)
        if edge_fn is None:
            edge_fn = lambda _y: (40.0, width - 40.0)
        glyph.layers["m1"] = _GeometryLayer(width, height, edge_fn, lsb=lsb, rsb=rsb)
        return glyph

    def _compute(self, font, glyph, *, reference="auto", tabular_mode=False, guards=None):
        master = _FakeMaster()
        defaults = dict(spacing_engine.DEFAULTS)
        defaults.update({"referenceGlyph": reference, "tabularMode": tabular_mode, "skipAutoAligned": False})
        return spacing_engine.compute_suggestion_for_layer(
            font=font,
            glyph=glyph,
            layer=glyph.layers["m1"],
            master=master,
            rules=[],
            defaults=defaults,
            master_params={
                "xHeight": 500,
                "italicAngle": 0,
                "area": defaults["area"],
                "depth": defaults["depth"],
                "over": defaults["over"],
                "frequency": 10,
            },
            guards=guards,
        )

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

    def test_round_half_away_from_zero(self) -> None:
        fn = spacing_engine._round_half_away_from_zero  # type: ignore[attr-defined]
        self.assertEqual(fn(0.5), 1)
        self.assertEqual(fn(1.4), 1)
        self.assertEqual(fn(1.5), 2)
        self.assertEqual(fn(-0.5), -1)
        self.assertEqual(fn(-1.4), -1)
        self.assertEqual(fn(-1.5), -2)

    def test_split_int_delta_sums_exactly(self) -> None:
        split = spacing_engine._split_int_delta  # type: ignore[attr-defined]
        self.assertEqual(sum(split(0)), 0)
        self.assertEqual(sum(split(1)), 1)
        self.assertEqual(sum(split(2)), 2)
        self.assertEqual(sum(split(-1)), -1)
        self.assertEqual(sum(split(-3)), -3)

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
        self.assertIsInstance(out["lsb"], int)
        self.assertIsInstance(out["rsb"], int)
        self.assertIn("clamped_lsb_delta", warnings)
        self.assertIn("clamped_rsb_delta", warnings)
        self.assertIn("clamped_rsb_min", warnings)

    def test_diagonize_left_limits_slope(self) -> None:
        xs = [0.0, 100.0, 300.0]
        out = spacing_engine._diagonize_left(xs, step=50.0)  # type: ignore[attr-defined]
        self.assertLessEqual(out[1] - out[0], 50.0)
        self.assertLessEqual(out[2] - out[1], 50.0)

    def test_measure_edges_materializes_glyphs4_intersection_proxy(self) -> None:
        left, right = spacing_engine._measure_edges_at_y(  # type: ignore[attr-defined]
            _ProxyIntersectionLayer(),
            y=50,
            include_components=True,
            start_x=-20,
            end_x=120,
        )

        self.assertEqual(left, 10.0)
        self.assertEqual(right, 90.0)

    def test_auto_reference_classifies_uppercase_without_subcategory(self) -> None:
        a = self._glyph_with_layer("A")
        h = self._glyph_with_layer("H")
        x = self._glyph_with_layer("x", sub_category="Lowercase", height=500)
        resolved = spacing_engine.resolve_reference(
            font=_FakeFont([a, h, x]),
            glyph=a,
            layer=a.layers["m1"],
            rule={},
            defaults={"referenceGlyph": "auto"},
        )
        self.assertEqual(spacing_engine.classify_glyph(a, a.layers["m1"])["glyphClass"], "uppercase")
        self.assertEqual(resolved["resolvedReferenceGlyph"], "H")

    def test_auto_reference_resolves_decimal_and_lowercase_classes(self) -> None:
        seven = self._glyph_with_layer("seven", category="Number", unicode_value="0037")
        one = self._glyph_with_layer("one", category="Number", unicode_value="0031")
        n = self._glyph_with_layer("n", sub_category="Lowercase", unicode_value="006E", height=500)
        x = self._glyph_with_layer("x", sub_category="Lowercase", unicode_value="0078", height=500)
        font = _FakeFont([seven, one, n, x])

        figure_ref = spacing_engine.resolve_reference(
            font=font, glyph=seven, layer=seven.layers["m1"], rule={}, defaults={"referenceGlyph": "auto"}
        )
        lower_ref = spacing_engine.resolve_reference(
            font=font, glyph=n, layer=n.layers["m1"], rule={}, defaults={"referenceGlyph": "auto"}
        )

        self.assertEqual(figure_ref["resolvedReferenceGlyph"], "one")
        self.assertEqual(lower_ref["resolvedReferenceGlyph"], "x")

    def test_explicit_x_remains_explicit(self) -> None:
        a = self._glyph_with_layer("A")
        h = self._glyph_with_layer("H")
        x = self._glyph_with_layer("x", height=500)
        resolved = spacing_engine.resolve_reference(
            font=_FakeFont([a, h, x]),
            glyph=a,
            layer=a.layers["m1"],
            rule={},
            defaults={"referenceGlyph": "x"},
        )
        self.assertEqual(resolved["referenceMode"], "explicit")
        self.assertEqual(resolved["resolvedReferenceGlyph"], "x")

    def test_missing_explicit_reference_is_not_reinterpreted_as_auto(self) -> None:
        a = self._glyph_with_layer("A")
        h = self._glyph_with_layer("H")
        x = self._glyph_with_layer("x", height=500)
        result = self._compute(_FakeFont([a, h, x]), a, reference="missing.reference")
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "explicit_reference_missing")
        self.assertEqual(result["referenceMode"], "explicit")
        self.assertIsNone(result["resolvedReferenceGlyph"])

    def test_missing_h_uses_deterministic_fallback_with_provenance(self) -> None:
        a = self._glyph_with_layer("A")
        x = self._glyph_with_layer("x", height=500)
        resolved = spacing_engine.resolve_reference(
            font=_FakeFont([a, x]),
            glyph=a,
            layer=a.layers["m1"],
            rule={},
            defaults={"referenceGlyph": "auto"},
        )
        self.assertEqual(resolved["resolvedReferenceGlyph"], "x")
        self.assertEqual(resolved["referenceFallback"]["reason"], "preferred_reference_missing")
        self.assertEqual(resolved["referenceFallback"]["preferredReferenceGlyph"], "H")
        result = self._compute(_FakeFont([a, x]), a)
        self.assertEqual(result["resolvedReferenceGlyph"], "x")
        self.assertIn("reference_fallback_used", result["warnings"])
        self.assertTrue(any(issue.get("code") == "reference_fallback_used" for issue in result["issues"]))

    def test_class_aware_reference_prevents_synthetic_diagonal_extremes(self) -> None:
        h = self._glyph_with_layer("H")
        x = self._glyph_with_layer("x", height=500)

        def diagonal_edges(y):
            fraction = min(1.0, max(0.0, y / 700.0))
            return (450.0 * (1.0 - fraction), 550.0 + 450.0 * fraction)

        for name in ("V", "W", "Y"):
            glyph = self._glyph_with_layer(name, width=1000, edge_fn=diagonal_edges, lsb=0, rsb=0)
            font = _FakeFont([glyph, h, x])
            old = self._compute(font, glyph, reference="x")
            automatic = self._compute(font, glyph, reference="auto")
            self.assertEqual(automatic["resolvedReferenceGlyph"], "H")
            self.assertLess(min(old["proposed"]["lsb"], old["proposed"]["rsb"]), -50)
            self.assertGreater(min(automatic["proposed"]["lsb"], automatic["proposed"]["rsb"]), -50)

    def test_legitimate_overhang_warns_without_zero_clamp(self) -> None:
        glyph = self._glyph_with_layer("J")
        classification = spacing_engine.classify_glyph(glyph, glyph.layers["m1"])
        proposed = {"width": 550, "lsb": 40, "rsb": -120}
        assessment = spacing_engine.assess_spacing_suggestion(
            glyph=glyph,
            layer=glyph.layers["m1"],
            current={"width": 600, "lsb": 40, "rsb": 20},
            proposed=proposed,
            measured={"lFullExtreme": 0, "rFullExtreme": 600, "distanceLeft": 0, "distanceRight": 140},
            classification=classification,
            upm=1000,
            italic_angle=0,
            guards=None,
        )
        self.assertEqual(proposed["rsb"], -120)
        self.assertNotEqual(assessment["negativeBearingAssessment"]["severity"], "blocked")
        self.assertTrue(assessment["negativeBearingAssessment"]["exempted"])

    def test_guard_blocks_normalized_uppercase_outliers_at_multiple_upms(self) -> None:
        glyph = self._glyph_with_layer("A")
        classification = spacing_engine.classify_glyph(glyph, glyph.layers["m1"])
        severities = []
        for upm, value in ((1000, -110), (2048, -225.28)):
            assessment = spacing_engine.assess_spacing_suggestion(
                glyph=glyph,
                layer=glyph.layers["m1"],
                current={"width": upm, "lsb": 0, "rsb": 0},
                proposed={"width": upm, "lsb": value, "rsb": 20},
                measured={"lFullExtreme": 0, "rFullExtreme": upm * 0.8, "distanceLeft": 0, "distanceRight": 0},
                classification=classification,
                upm=upm,
                italic_angle=0,
                guards=None,
            )
            severities.append(assessment["negativeBearingAssessment"]["severity"])
            self.assertAlmostEqual(assessment["normalizedMetrics"]["proposed"]["lsb"], -0.11)
            self.assertEqual(assessment["metricsTrustAssessment"]["status"], "untrusted")
        self.assertEqual(severities, ["blocked", "blocked"])

    def test_mark_zero_width_and_allow_list_exemptions_are_reported(self) -> None:
        mark = self._glyph_with_layer("acutecomb", category="Mark", width=0, lsb=-200, rsb=-200)
        mark_result = self._compute(_FakeFont([mark]), mark, guards=None)
        self.assertEqual(mark_result["reason"], "zero_width_glyph")
        self.assertTrue(mark_result["negativeBearingAssessment"]["exempted"])

        a = self._glyph_with_layer("A")
        assessment = spacing_engine.assess_spacing_suggestion(
            glyph=a,
            layer=a.layers["m1"],
            current={"width": 600, "lsb": 20, "rsb": 20},
            proposed={"width": 400, "lsb": -120, "rsb": -120},
            measured={"lFullExtreme": 0, "rFullExtreme": 600, "distanceLeft": 0, "distanceRight": 0},
            classification=spacing_engine.classify_glyph(a, a.layers["m1"]),
            upm=1000,
            italic_angle=0,
            guards={"allowGlyphs": ["A"]},
        )
        self.assertEqual(assessment["negativeBearingAssessment"]["severity"], "exempted")
        self.assertTrue(assessment["negativeBearingAssessment"]["exempted"])

    def test_tabular_detection_uses_fixed_pitch_and_equal_figure_evidence(self) -> None:
        master = _FakeMaster()
        fixed_figures = [self._glyph_with_layer(name, category="Number", width=600) for name in spacing_engine.DEFAULT_FIGURE_NAMES]
        fixed_font = _FakeFont(fixed_figures, fixed_pitch=True)
        fixed = spacing_engine.assess_tabular_mode(
            font=fixed_font,
            glyph=fixed_figures[1],
            layer=fixed_figures[1].layers["m1"],
            master=master,
            defaults={"tabularMode": "auto", "tabularToleranceEm": 0.005},
            classification={"glyphClass": "decimalFigure"},
        )
        self.assertTrue(fixed["detected"])
        self.assertEqual(fixed["reason"], "font_fixed_pitch_metadata")
        self.assertEqual(fixed["preservedWidth"], 600)
        fixed_result = self._compute(fixed_font, fixed_figures[7], tabular_mode="auto")
        self.assertEqual(fixed_result["proposed"]["width"], 600)

        equal_figures = [
            self._glyph_with_layer(name, category="Number", width=600 + (index % 2))
            for index, name in enumerate(spacing_engine.DEFAULT_FIGURE_NAMES)
        ]
        equal_font = _FakeFont(equal_figures)
        equal = spacing_engine.assess_tabular_mode(
            font=equal_font,
            glyph=equal_figures[7],
            layer=equal_figures[7].layers["m1"],
            master=master,
            defaults={"tabularMode": "auto", "tabularToleranceEm": 0.005},
            classification={"glyphClass": "decimalFigure"},
        )
        self.assertTrue(equal["detected"])
        self.assertEqual(equal["reason"], "default_figures_equal_width")
        equal_result = self._compute(equal_font, equal_figures[7], tabular_mode="auto")
        self.assertEqual(equal_result["proposed"]["width"], equal["preservedWidth"])

    def test_proportional_typewriter_style_is_not_forced_tabular(self) -> None:
        figures = [
            self._glyph_with_layer(name, category="Number", width=450 + index * 20)
            for index, name in enumerate(spacing_engine.DEFAULT_FIGURE_NAMES)
        ]
        font = _FakeFont(figures, family_name="Synthetic Typewriter Slab")
        assessed = spacing_engine.assess_tabular_mode(
            font=font,
            glyph=figures[7],
            layer=figures[7].layers["m1"],
            master=_FakeMaster(),
            defaults={"tabularMode": "auto", "tabularToleranceEm": 0.005},
            classification={"glyphClass": "decimalFigure"},
        )
        self.assertFalse(assessed["detected"])

    def test_narrow_punctuation_and_width_collapse_are_flagged(self) -> None:
        semicolon = self._glyph_with_layer("semicolon", category="Punctuation", width=300)
        resolved = spacing_engine.resolve_reference(
            font=_FakeFont([semicolon]),
            glyph=semicolon,
            layer=semicolon.layers["m1"],
            rule={},
            defaults={"referenceGlyph": "auto"},
        )
        self.assertEqual(resolved["referenceMode"], "auto")
        self.assertEqual(resolved["resolvedReferenceGlyph"], "semicolon")
        assessment = spacing_engine.assess_spacing_suggestion(
            glyph=semicolon,
            layer=semicolon.layers["m1"],
            current={"width": 300, "lsb": 40, "rsb": 40},
            proposed={"width": 0, "lsb": -20, "rsb": -20},
            measured={"lFullExtreme": 0, "rFullExtreme": 220, "distanceLeft": 0, "distanceRight": 0},
            classification=spacing_engine.classify_glyph(semicolon, semicolon.layers["m1"]),
            upm=1000,
            italic_angle=0,
            guards=None,
        )
        self.assertEqual(assessment["confidence"]["level"], "low")
        self.assertTrue(assessment["confidence"]["manualReviewRequired"])
        self.assertEqual(assessment["widthAssessment"]["severity"], "blocked")
        self.assertIn("manualReviewGlyphs", assessment["applicationAssessment"]["requiredOverrides"])


if __name__ == "__main__":
    unittest.main()
