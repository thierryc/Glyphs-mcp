"""Contract tests for curve-geometry discovery in the outline skill."""

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

    def test_packaged_skill_matches_canonical(self) -> None:
        self.assertEqual(
            PACKAGED.read_text(encoding="utf-8"),
            CANONICAL.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
