"""Unit tests for the pure Unicode assignment engine."""

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


sys.path.insert(0, str(_resources_dir()))
import unicode_assignment_engine as engine  # noqa: E402


def _glyph(name, unicodes=None, export=True):
    return {"name": name, "unicodes": list(unicodes or []), "export": export}


class UnicodeAssignmentEngineTests(unittest.TestCase):
    def test_codepoint_parsing_normalizes_bmp_and_supplementary_values(self) -> None:
        self.assertEqual(engine.normalize_codepoint("u+e042"), "E042")
        self.assertEqual(engine.normalize_codepoint("0x41"), "0041")
        self.assertEqual(engine.normalize_codepoint(0xF0000), "F0000")

    def test_codepoint_parsing_rejects_malformed_out_of_range_and_surrogates(self) -> None:
        for value in ("nope", -1, "110000", "D800", True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    engine.parse_codepoint(value)

    def test_noncharacters_are_valid_explicit_values_but_skipped_by_allocator(self) -> None:
        self.assertTrue(engine.is_noncharacter(engine.parse_codepoint("FDD0")))
        review = engine.review_assignments(
            [_glyph("privateCharacter")],
            ["privateCharacter"],
            allocate_unencoded=True,
            range_start="FDD0",
            range_end="FDF0",
        )
        self.assertEqual(review["proposedAssignments"][0]["unicodes"], ["FDF0"])

        preflight = engine.prepare_assignment_changes(
            [_glyph("privateCharacter")],
            [
                {
                    "glyphName": "privateCharacter",
                    "expectedUnicodes": [],
                    "unicodes": ["FDD0"],
                }
            ],
        )
        self.assertTrue(preflight["ok"])
        self.assertIn("noncharacter_assignment", {item["code"] for item in preflight["warnings"]})

    def test_allocation_is_deterministic_and_skips_occupied_and_reserved_values(self) -> None:
        glyphs = [
            _glyph("zTarget"),
            _glyph("occupied", ["E000"]),
            _glyph("aTarget"),
        ]
        review = engine.review_assignments(
            glyphs,
            ["zTarget", "aTarget"],
            allocate_unencoded=True,
            reserved_codepoints=["E001"],
        )
        self.assertEqual(
            [(item["glyphName"], item["unicodes"]) for item in review["proposedAssignments"]],
            [("aTarget", ["E002"]), ("zTarget", ["E003"])],
        )

        reordered = engine.review_assignments(
            list(reversed(glyphs)),
            ["aTarget", "zTarget"],
            allocate_unencoded=True,
            reserved_codepoints=["E001"],
        )
        self.assertEqual(reordered["proposedAssignments"], review["proposedAssignments"])

    def test_descending_and_supplementary_pua_allocation(self) -> None:
        review = engine.review_assignments(
            [_glyph("constructedCharacter")],
            ["constructedCharacter"],
            allocate_unencoded=True,
            range_start="F0000",
            range_end="F0002",
            direction="descending",
        )
        self.assertEqual(review["proposedAssignments"][0]["unicodes"], ["F0002"])
        self.assertEqual(
            review["proposedAssignments"][0]["classifications"],
            [{"codepoint": "F0002", "classification": "private_use"}],
        )
        self.assertTrue(review["range"]["privateUseOnly"])

    def test_pua_b_and_standard_values_are_classified_mechanically(self) -> None:
        review = engine.review_assignments(
            [
                _glyph("regularTextCharacter", ["0041"]),
                _glyph("institutionalCharacter", ["100000"]),
            ],
            ["regularTextCharacter", "institutionalCharacter"],
        )

        self.assertEqual(
            review["currentClassifications"]["regularTextCharacter"],
            [{"codepoint": "0041", "classification": "standard"}],
        )
        self.assertEqual(
            review["currentClassifications"]["institutionalCharacter"],
            [{"codepoint": "100000", "classification": "private_use"}],
        )
        self.assertEqual(review["fontCounts"]["standardUnicodeGlyphCount"], 1)
        self.assertEqual(review["fontCounts"]["privateUseGlyphCount"], 1)

    def test_range_exhaustion_does_not_return_partial_new_allocations(self) -> None:
        review = engine.review_assignments(
            [_glyph("a"), _glyph("b")],
            ["a", "b"],
            allocate_unencoded=True,
            range_start="E000",
            range_end="E000",
        )
        self.assertEqual(review["proposedAssignments"], [])
        self.assertIn("allocation_range_exhausted", {item["code"] for item in review["errors"]})

    def test_previous_map_restores_existing_identity_and_reserves_removed_values(self) -> None:
        review = engine.review_assignments(
            [_glyph("restored"), _glyph("newCharacter")],
            ["restored", "newCharacter"],
            allocate_unencoded=True,
            previous_map={
                "restored": ["E001"],
                "removedCharacter": ["E000"],
            },
        )
        proposals = {item["glyphName"]: item for item in review["proposedAssignments"]}
        self.assertEqual(proposals["restored"]["unicodes"], ["E001"])
        self.assertEqual(proposals["restored"]["source"], "previous_map")
        self.assertEqual(proposals["newCharacter"]["unicodes"], ["E002"])
        self.assertIn("previous_glyph_removed", {item["code"] for item in review["warnings"]})

    def test_previous_map_changes_are_reported_as_breaking_findings(self) -> None:
        review = engine.review_assignments(
            [_glyph("scholarlySign", ["E101"])],
            ["scholarlySign"],
            previous_map={"scholarlySign": ["E100"]},
        )
        self.assertIn("previous_mapping_changed", {item["code"] for item in review["errors"]})
        self.assertEqual(review["changes"]["changed"][0]["currentUnicodes"], ["E101"])

    def test_duplicate_exporting_assignments_are_errors(self) -> None:
        review = engine.review_assignments(
            [_glyph("one", ["E010"]), _glyph("two", ["E010"])],
            ["one"],
        )
        duplicate = [item for item in review["errors"] if item["code"] == "duplicate_unicode"]
        self.assertEqual(duplicate[0]["glyphNames"], ["one", "two"])

    def test_duplicate_involving_only_one_exporting_glyph_is_a_warning(self) -> None:
        review = engine.review_assignments(
            [_glyph("exported", ["E010"]), _glyph("sourceOnly", ["E010"], export=False)],
            ["exported"],
        )
        self.assertNotIn("duplicate_unicode", {item["code"] for item in review["errors"]})
        self.assertIn("duplicate_unicode", {item["code"] for item in review["warnings"]})

    def test_multiple_assignments_are_preserved(self) -> None:
        review = engine.review_assignments(
            [_glyph("legacyCharacter", ["E100", "F0000"])],
            ["legacyCharacter"],
        )
        self.assertEqual(review["currentMap"]["legacyCharacter"], ["E100", "F0000"])
        self.assertIn("multiple_unicode_assignments", {item["code"] for item in review["warnings"]})

    def test_non_private_allocation_requires_semantic_validation(self) -> None:
        review = engine.review_assignments(
            [_glyph("requestedCharacter")],
            ["requestedCharacter"],
            allocate_unencoded=True,
            range_start="0041",
            range_end="0042",
        )
        self.assertEqual(review["proposedAssignments"][0]["unicodes"], ["0041"])
        self.assertIn("semantic_validation_required", {item["code"] for item in review["warnings"]})

    def test_preflight_rejects_stale_state(self) -> None:
        preflight = engine.prepare_assignment_changes(
            [_glyph("gaiji", ["E100"])],
            [{"glyphName": "gaiji", "expectedUnicodes": [], "unicodes": ["E101"]}],
        )
        self.assertFalse(preflight["ok"])
        self.assertIn("stale_expected_state", {item["code"] for item in preflight["errors"]})

    def test_preflight_rejects_collisions_with_untargeted_glyphs(self) -> None:
        preflight = engine.prepare_assignment_changes(
            [_glyph("target"), _glyph("existing", ["E100"])],
            [{"glyphName": "target", "expectedUnicodes": [], "unicodes": ["E100"]}],
        )
        self.assertFalse(preflight["ok"])
        self.assertIn("unicode_collision", {item["code"] for item in preflight["errors"]})

    def test_preflight_accepts_multiple_unicode_values_without_reordering(self) -> None:
        preflight = engine.prepare_assignment_changes(
            [_glyph("phoneticCharacter", ["E200"])],
            [
                {
                    "glyphName": "phoneticCharacter",
                    "expectedUnicodes": ["E200"],
                    "unicodes": ["E200", "F0001"],
                }
            ],
        )
        self.assertTrue(preflight["ok"])
        self.assertEqual(preflight["actions"][0]["after"], ["E200", "F0001"])


if __name__ == "__main__":
    unittest.main()
