"""Tests for the fixed Broad-Latin italic benchmark and promotion gate."""

from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import benchmark_italic_sans_broad as broad  # noqa: E402


class _FakeMaster:
    id = "MASTER"
    capHeight = 700
    xHeight = 500


class _FakeLayer:
    def __init__(self, components: list | None = None) -> None:
        self.paths = []
        self.anchors = []
        self.components = list(components or [])
        self.width = 500


class _FakeGlyph:
    def __init__(self, layer: _FakeLayer) -> None:
        self.layers = {_FakeMaster.id: layer}


class _FakeGlyphProxy:
    def __init__(self, mapping: dict[str, _FakeGlyph]) -> None:
        self.mapping = mapping

    def __getitem__(self, key: str) -> _FakeGlyph | None:
        return self.mapping.get(key)


class _FakeFont:
    def __init__(self, mapping: dict[str, _FakeGlyph]) -> None:
        self.glyphs = _FakeGlyphProxy(mapping)


class _FakeComponent:
    def __init__(
        self,
        name: str,
        transform: tuple[float, float, float, float, float, float],
    ) -> None:
        self.componentName = name
        self.transform = transform


class _FakeUnicodeGlyph:
    def __init__(self, name: str, unicodes: tuple[int, ...]) -> None:
        self.name = name
        self.unicodes = unicodes


class _FakeUnicodeGlyphProxy:
    def __init__(self, glyphs: list[_FakeUnicodeGlyph]) -> None:
        self.glyphs = glyphs

    def __iter__(self):
        return iter(self.glyphs)


class _FakeUnicodeFont:
    def __init__(self, glyphs: list[_FakeUnicodeGlyph]) -> None:
        self.glyphs = _FakeUnicodeGlyphProxy(glyphs)


def _family_result(
    *,
    raw_error: float,
    cursivy_error: float,
    balanced_error: float,
    accepted: bool = True,
) -> dict:
    return {
        "acceptance": {
            "allGlyphsGenerated": accepted,
            "topologyPreservedForEveryMode": accepted,
            "reviewSourceUnchanged": accepted,
            "anchorErrorWithinPointZeroOne": accepted,
            "noUnexpectedComponentMasterMismatch": accepted,
            "noUnsafeAppliedCompensation": accepted,
            "noNonCommutingComponentTransforms": accepted,
            "minimumCompensatedPairsRetained": accepted,
            "balancedAtLeast50PercentBetterThanRaw": (
                balanced_error <= raw_error * 0.5
            ),
            "balancedAtLeast50PercentBetterThanCursivy": (
                balanced_error <= cursivy_error * 0.5
            ),
        },
        "summary": {
            "meanAbsoluteStemWidthError": {
                "raw": raw_error,
                "cursivy": cursivy_error,
                "balanced": balanced_error,
            }
        },
    }


class BroadItalicBenchmarkTests(unittest.TestCase):
    def test_fixed_manifest_has_expected_coverage(self) -> None:
        manifest = broad.load_manifest()
        glyphs = manifest["glyphs"]
        self.assertEqual(len(glyphs), 543)
        self.assertEqual(
            Counter(row["group"] for row in glyphs),
            Counter(broad.EXPECTED_GROUP_COUNTS),
        )
        self.assertEqual(len({row["codepoint"] for row in glyphs}), 543)
        self.assertEqual(
            [row["codepoint"] for row in glyphs],
            sorted(row["codepoint"] for row in glyphs),
        )
        self.assertEqual(glyphs[0]["unicode"], "U+0020")
        self.assertEqual(glyphs[-1]["unicode"], "U+2189")
        self.assertEqual(
            manifest["sources"]["ibmPlexSansCommit"],
            broad.PLEX_COMMIT,
        )

    def test_manifest_resolves_two_source_naming_mismatches_by_unicode(
        self,
    ) -> None:
        glyphs = broad.load_manifest()["glyphs"]
        overrides = {
            row["unicode"]: (
                row["interGlyphName"],
                row["notoSansGlyphName"],
            )
            for row in glyphs
            if row["interGlyphName"] != row["notoSansGlyphName"]
        }
        self.assertEqual(
            overrides,
            {
                "U+0162": ("Tcommaaccent", "Tcedilla"),
                "U+0196": ("Iota", "Iota-latin"),
            },
        )

    def test_pagination_is_bounded_and_complete(self) -> None:
        values = list(range(543))
        pages = broad.paginate(values, 64)
        self.assertEqual(len(pages), 9)
        self.assertTrue(all(1 <= len(page) <= 64 for page in pages))
        self.assertEqual([item for page in pages for item in page], values)
        with self.assertRaisesRegex(ValueError, "between 1 and 64"):
            broad.paginate(values, 0)
        with self.assertRaisesRegex(ValueError, "between 1 and 64"):
            broad.paginate(values, 65)

    def test_render_scale_validation(self) -> None:
        self.assertEqual(broad.validate_render_scale(1), 1.0)
        self.assertEqual(broad.validate_render_scale(4), 4.0)
        for invalid in (0.99, 4.01):
            with self.assertRaisesRegex(ValueError, "between 1 and 4"):
                broad.validate_render_scale(invalid)

    def test_pathless_layer_preserves_topology(self) -> None:
        generated = broad.base._generate_glyph(
            _FakeLayer(),
            _FakeMaster(),
            1000,
            [],
            angle=12,
        )
        self.assertTrue(generated["topologyPreserved"])
        self.assertEqual(generated["source"], [])
        self.assertEqual(generated["raw"], [])
        self.assertEqual(generated["cursivy"], [])
        self.assertEqual(generated["balanced"], [])
        self.assertEqual(
            generated["balancedDiagnostics"]["compensatedPairCount"],
            0,
        )

    def test_missing_glyphs_report_source(self) -> None:
        layer = _FakeLayer()
        roman = _FakeFont({"space": _FakeGlyph(layer)})
        italic = _FakeFont({})
        missing = broad.missing_family_glyphs(
            roman,
            italic,
            _FakeMaster(),
            _FakeMaster(),
            [
                {
                    "unicode": "U+0020",
                    "interGlyphName": "space",
                }
            ],
            "interGlyphName",
        )
        self.assertEqual(
            missing,
            [
                {
                    "unicode": "U+0020",
                    "glyphName": "space",
                    "source": "officialItalic",
                }
            ],
        )

    def test_audit_selection_is_deterministic_and_bounded(self) -> None:
        entries = broad.load_manifest()["glyphs"]
        glyph_rows = [
            {
                **row,
                "status": "ok",
                "compensatedPairCount": (
                    2 if index % 13 == 0 else 0
                ),
            }
            for index, row in enumerate(entries)
        ]
        diff_by_unicode = {
            row["unicode"]: {
                **row,
                "comparisons": {
                    "balancedVsOfficial": {
                        "differentPixelRatio": (
                            (len(entries) - index) / len(entries)
                        )
                    }
                },
            }
            for index, row in enumerate(entries)
        }
        first = broad.select_audit_entries(
            entries,
            glyph_rows,
            diff_by_unicode,
            limit=64,
        )
        second = broad.select_audit_entries(
            entries,
            glyph_rows,
            diff_by_unicode,
            limit=64,
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertEqual(
            len({row["unicode"] for row in first}),
            len(first),
        )
        self.assertEqual(
            [row["codepoint"] for row in first],
            sorted(row["codepoint"] for row in first),
        )
        self.assertTrue(
            set(broad.EXPECTED_GROUP_COUNTS)
            <= {row["group"] for row in first}
        )

    def test_audit_selection_prioritizes_component_direction_risks(
        self,
    ) -> None:
        entries = broad.load_manifest()["glyphs"][:3]
        glyph_rows = [
            {
                **row,
                "status": "ok",
                "compensatedPairCount": 0,
                "components": {
                    "nonCommutingTransformRisks": (
                        [{"reason": "test"}] if index == 2 else []
                    )
                },
            }
            for index, row in enumerate(entries)
        ]
        diff_by_unicode = {
            row["unicode"]: {
                **row,
                "comparisons": {
                    "balancedVsOfficial": {"differentPixelRatio": 0.0}
                },
            }
            for row in entries
        }
        selected = broad.select_audit_entries(
            entries,
            glyph_rows,
            diff_by_unicode,
            limit=1,
        )
        self.assertEqual(selected, [entries[2]])

    def test_all_visual_comparison_columns_are_declared(self) -> None:
        self.assertEqual(
            tuple(
                "{}Vs{}".format(
                    candidate,
                    reference[:1].upper() + reference[1:],
                )
                for reference, candidate, _label in broad.DIFF_COMPARISONS
            ),
            broad.COMPARISON_KEYS,
        )
        self.assertEqual(
            broad.COMPARISON_KEYS,
            (
                "cursivyVsRaw",
                "balancedVsRaw",
                "balancedVsCursivy",
                "balancedVsOfficial",
            ),
        )
        self.assertEqual(
            [mode for mode, _label in broad._mode_labels("Test")],
            ["roman", "raw", "cursivy", "balanced", "official"],
        )
        self.assertIn(
            "Partial compensation",
            dict(broad._mode_labels("Test"))["cursivy"],
        )

    def test_plex_is_pinned_as_a_regular_italic_ufo_pair(self) -> None:
        config = broad.FAMILY_CONFIGS["ibmPlexSans"]
        self.assertEqual(config["commit"], broad.PLEX_COMMIT)
        self.assertEqual(config["sourceFormat"], "ufo")
        self.assertEqual(config["expectedAxes"], {"wght": 400})
        self.assertEqual(config["angle"], 11.31)
        self.assertEqual(config["expectedSharedEntryCount"], 391)
        self.assertEqual(
            sum(config["expectedGroupCounts"].values()),
            391,
        )

    def test_unicode_family_selection_records_missing_and_mismatched_names(
        self,
    ) -> None:
        roman = _FakeUnicodeFont(
            [
                _FakeUnicodeGlyph("space", (0x20,)),
                _FakeUnicodeGlyph("A", (0x41,)),
                _FakeUnicodeGlyph("romanB", (0x42,)),
            ]
        )
        italic = _FakeUnicodeFont(
            [
                _FakeUnicodeGlyph("space", (0x20,)),
                _FakeUnicodeGlyph("italicB", (0x42,)),
            ]
        )
        entries = [
            {"unicode": "U+0020", "codepoint": 0x20, "group": "basicLatin"},
            {"unicode": "U+0041", "codepoint": 0x41, "group": "basicLatin"},
            {"unicode": "U+0042", "codepoint": 0x42, "group": "basicLatin"},
        ]
        selected, unavailable = broad.resolve_unicode_family_entries(
            roman,
            italic,
            entries,
            "plexGlyphName",
        )
        self.assertEqual(selected[0]["plexGlyphName"], "space")
        self.assertEqual(
            [row["reason"] for row in unavailable],
            ["missingOfficialItalic", "glyphNameMismatch"],
        )

    def test_component_transform_gate_detects_reflection_not_translation(
        self,
    ) -> None:
        leaf = _FakeGlyph(_FakeLayer())
        translated = _FakeGlyph(
            _FakeLayer(
                [_FakeComponent("leaf", (1, 0, 0, 1, 120, 50))]
            )
        )
        reflected = _FakeGlyph(
            _FakeLayer(
                [_FakeComponent("leaf", (-1, 0, 0, 1, 500, 0))]
            )
        )
        font = _FakeFont(
            {
                "leaf": leaf,
                "translated": translated,
                "reflected": reflected,
            }
        )
        self.assertEqual(
            broad._component_transform_risks(
                font,
                _FakeMaster(),
                "translated",
                angle=12,
            ),
            [],
        )
        risks = broad._component_transform_risks(
            font,
            _FakeMaster(),
            "reflected",
            angle=12,
        )
        self.assertEqual(len(risks), 1)
        self.assertTrue(risks[0]["reflected"])
        self.assertGreater(risks[0]["commutatorError"], 0)

    def test_balanced_wins_only_when_every_family_passes(self) -> None:
        families = {
            "inter": _family_result(
                raw_error=2.0,
                cursivy_error=1.3,
                balanced_error=0.0,
            ),
            "notoSans": _family_result(
                raw_error=2.1,
                cursivy_error=1.4,
                balanced_error=0.0,
            ),
        }
        promotion = broad.evaluate_promotion(families)
        self.assertEqual(promotion["winner"], "balanced")
        self.assertEqual(
            promotion["deterministicGeometryWinner"], "balanced"
        )
        self.assertTrue(promotion["balancedPromoted"])
        families["notoSans"]["acceptance"]["reviewSourceUnchanged"] = False
        self.assertFalse(
            broad.evaluate_promotion(families)["balancedPromoted"]
        )
        self.assertIsNone(
            broad.evaluate_promotion(families)[
                "recommendedExperimentalMode"
            ]
        )

    def test_cursivy_wins_ties_within_point_zero_one(self) -> None:
        families = {
            "inter": _family_result(
                raw_error=0.5,
                cursivy_error=0.005,
                balanced_error=0.0,
            ),
            "notoSans": _family_result(
                raw_error=0.5,
                cursivy_error=0.005,
                balanced_error=0.0,
            ),
        }
        promotion = broad.evaluate_promotion(families)
        self.assertEqual(promotion["winner"], "cursivy")
        self.assertFalse(promotion["balancedPromoted"])


if __name__ == "__main__":
    unittest.main()
