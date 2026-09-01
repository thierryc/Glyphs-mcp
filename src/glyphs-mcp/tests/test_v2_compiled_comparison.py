"""Format-aware compiled-font comparison contracts."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.compiled_comparison import (  # noqa: E402
    compare_compiled_fonts,
)


def _common_tables(builder: FontBuilder) -> None:
    builder.setupHorizontalMetrics({".notdef": (600, 0), "A": (600, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupCharacterMap({0x41: "A"})
    builder.setupNameTable(
        {
            "familyName": "Comparison Fixture",
            "styleName": "Regular",
            "uniqueFontIdentifier": "Comparison Fixture Regular",
            "fullName": "Comparison Fixture Regular",
            "psName": "ComparisonFixture-Regular",
        }
    )
    builder.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        usWinAscent=800,
        usWinDescent=200,
    )
    builder.setupPost()


def _ttf(path: Path, *, extra_point: bool = False, advance: int = 600) -> None:
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "A"])
    glyphs = {}
    for name in (".notdef", "A"):
        pen = TTGlyphPen(None)
        if name == "A":
            pen.moveTo((0, 0))
            if extra_point:
                pen.lineTo((250, 0))
            pen.lineTo((500, 0))
            pen.lineTo((500, 700))
            pen.lineTo((0, 700))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    _common_tables(builder)
    builder.setupHorizontalMetrics(
        {".notdef": (600, 0), "A": (advance, 0)}
    )
    builder.setupMaxp()
    builder.save(path)


def _cff(path: Path, *, x_shift: int = 0) -> None:
    builder = FontBuilder(1000, isTTF=False)
    builder.setupGlyphOrder([".notdef", "A"])
    charstrings = {}
    for name in (".notdef", "A"):
        pen = T2CharStringPen(600, None)
        if name == "A":
            pen.moveTo((x_shift, 0))
            pen.lineTo((500 + x_shift, 0))
            pen.lineTo((500 + x_shift, 700))
            pen.lineTo((x_shift, 700))
            pen.closePath()
        charstrings[name] = pen.getCharString()
    builder.setupCFF(
        "ComparisonFixture-Regular",
        {
            "FullName": "Comparison Fixture Regular",
            "FamilyName": "Comparison Fixture",
            "Weight": "Regular",
        },
        charstrings,
        {},
    )
    _common_tables(builder)
    builder.setupMaxp()
    builder.save(path)


class CompiledComparisonTests(unittest.TestCase):
    def test_truetype_uses_topology_independent_outline_distance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected, observed = root / "expected.ttf", root / "observed.ttf"
            _ttf(expected)
            _ttf(observed, extra_point=True)

            result = compare_compiled_fonts(expected, observed)

        self.assertTrue(result["passed"], result)
        self.assertEqual(result["profile"]["name"], "truetype_behavioral")
        self.assertFalse(result["profile"]["topologyRequired"])
        self.assertEqual(result["topologyMismatchCount"], 1)
        self.assertEqual(result["observedMaxima"]["outlineDistance"], 0)

    def test_truetype_reports_metric_tolerance_and_observed_maximum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected, observed = root / "expected.ttf", root / "observed.ttf"
            _ttf(expected, advance=600)
            _ttf(observed, advance=604)

            failed = compare_compiled_fonts(expected, observed)
            accepted = compare_compiled_fonts(
                expected, observed, tolerances={"advanceWidth": 4}
            )

        self.assertFalse(failed["passed"])
        self.assertIn("advance_width_delta", failed["blockers"])
        self.assertEqual(failed["observedMaxima"]["advanceWidth"], 4)
        self.assertTrue(accepted["passed"], accepted)

    def test_cff_requires_contour_topology_and_reports_coordinate_delta(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected, observed = root / "expected.otf", root / "observed.otf"
            _cff(expected, x_shift=0)
            _cff(observed, x_shift=3)

            failed = compare_compiled_fonts(expected, observed)
            accepted = compare_compiled_fonts(
                expected, observed, tolerances={"coordinateDelta": 3}
            )

        self.assertEqual(failed["profile"]["name"], "cff_contour")
        self.assertTrue(failed["profile"]["topologyRequired"])
        self.assertEqual(failed["observedMaxima"]["coordinateDelta"], 3)
        self.assertIn("outline_delta", failed["blockers"])
        self.assertTrue(accepted["passed"], accepted)

    def test_outline_format_mismatch_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ttf, cff = root / "font.ttf", root / "font.otf"
            _ttf(ttf)
            _cff(cff)
            result = compare_compiled_fonts(ttf, cff)

        self.assertFalse(result["passed"])
        self.assertEqual(result["blockers"], ["outline_format_mismatch"])


if __name__ == "__main__":
    unittest.main()
