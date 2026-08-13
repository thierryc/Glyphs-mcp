"""Contract tests for the canonical outline skill."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
CANONICAL = REPO / "skills" / "glyphs-mcp-outlines-docs" / "SKILL.md"
PACKAGED = REPO / "plugins" / "glyphs-mcp" / "skills" / "glyphs-mcp-outlines-docs" / "SKILL.md"


class OutlinesSkillTests(unittest.TestCase):
    def test_trigger_description_names_curve_geometry_work(self) -> None:
        text = CANONICAL.read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        for phrase in ("cubic Bezier geometry", "Tunni balance", "signed curvature", "curve quality"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, frontmatter)

    def test_skill_contains_complete_curve_geometry_workflow(self) -> None:
        text = CANONICAL.read_text(encoding="utf-8")
        for phrase in (
            "## Curve geometry workflow",
            "review_tunni_geometry",
            "review_curve_quality",
            'set_curve_review_overlay(enabled=true, overlays=["curvature", "curve_events"])',
            "View > Show Glyphs MCP Curvature",
            "difference-only Candidate Reporter",
            "Warm golden yellow marks only the symmetric difference",
            "Identical geometry draws nothing over the glyph",
            "Curvature is reviewed separately",
            "Curvature is reviewed separately through **View > Show Glyphs MCP Curvature**",
            "dry-run `apply_tunni_balance`",
            "Stop for explicit approval before `confirm=true`",
            "position, type, connection",
            "only explicitly targeted fields may change",
            "update_glyph_node_positions",
            'grid_policy="font"',
            "complete verified read-back",
            "never assign `None` to a Glyphs",
            "Treat an unexpected",
            "font was not saved",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_skill_contains_joint_start_node_alignment_contract(self) -> None:
        text = CANONICAL.read_text(encoding="utf-8")
        self.assertEqual(text.count("## Start-node alignment"), 1)
        section = text.split("## Start-node alignment", 1)[1].split("\n## ", 1)[0]
        normalized = " ".join(section.split())

        required_phrases = (
            "one joint cyclic-alignment task",
            "one corresponding closed-path set at a time",
            "Never rotate open paths",
            "explicitly selected on-curve node",
            "explicitly designated reference master",
            "Do not use `correctPathDirection()` as the start-node oracle",
            "extremum or corner class",
            "normalized position",
            "neighboring segments",
            "tangents, and curvature",
            "Raw node indices and absolute coordinates are not matching evidence",
            "canonical cyclic node-type sequence",
            "choose one shared topology phase",
            "exactly one unambiguous matching candidate in every master",
            "no match, multiple matches, incompatible topology, or a conflicting semantic result",
            "obtain explicit approval before mutation",
            "Stop if the live snapshot is stale",
            "coordinates, all node fields, contour direction, path and shape order, open paths, and compatibility remain unchanged",
            "report the resulting start in every master",
            "Call `review_start_node_alignment`",
            "Call `apply_start_node_alignment` with `dry_run=true`",
            "Retain the exact `planFingerprint`",
            "Never substitute generated code",
        )
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, normalized)

        self.assertEqual(section.count("correctPathDirection()"), 1)
        for obsolete_phrase in (
            "run `correctPathDirection()` on a detached copy",
            "oracle-selected start node",
            "rerun the detached oracle",
            "resolve every master independently",
        ):
            with self.subTest(obsolete_phrase=obsolete_phrase):
                self.assertNotIn(obsolete_phrase, normalized)

        self.assertNotIn("execute_code_with_context", normalized)
        workflow = " ".join(text.split())
        self.assertIn(
            "use the typed joint-alignment workflow below",
            workflow,
        )

    def test_packaged_skill_matches_canonical(self) -> None:
        self.assertEqual(
            PACKAGED.read_text(encoding="utf-8"),
            CANONICAL.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
