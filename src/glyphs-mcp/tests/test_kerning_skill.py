"""Contract tests for advanced pair and contextual kerning guidance."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
CANONICAL = REPO / "skills" / "glyphs-mcp-kerning"
PACKAGED = REPO / "plugins" / "glyphs-mcp" / "skills" / "glyphs-mcp-kerning"


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class KerningSkillTests(unittest.TestCase):
    def test_skill_routes_spacing_pairs_contexts_and_manual_feature_code(self) -> None:
        text = (CANONICAL / "SKILL.md").read_text(encoding="utf-8")

        for required in (
            "Spacing -> Kerning -> Context Kerning",
            'entryKind="pair"',
            'entryKind="context"',
            'mode="context_sequences"',
            "boundary `1`",
            "boundary `2`",
            "L’O",
            "l’A",
            "additional to ordinary kerning",
            "glyphs-mcp-spacing",
            "glyphs-mcp-opentype-features",
            "Never save the font automatically",
        ):
            self.assertIn(required, text)

    def test_advanced_reference_is_linked_and_source_grounded(self) -> None:
        skill = (CANONICAL / "SKILL.md").read_text(encoding="utf-8")
        match = re.search(r"\]\((references/context-kerning\.md)\)", skill)
        self.assertIsNotNone(match)
        reference = (CANONICAL / match.group(1)).read_text(encoding="utf-8")

        for required in (
            "L * quoteright A",
            "L quoteright * A",
            '"boundaryIndex": 1',
            "editable: false",
            "value: null",
            "value: 0",
            "contiguous subrun",
            "Text Preview/CoreText",
            "Microsoft OpenType GPOS specification",
            "Adobe OpenType feature-file syntax",
            "Apple TrueType `kerx` table",
            "Google Fonts testing guidance",
        ):
            self.assertIn(required, reference)

    def test_packaged_skill_matches_canonical_tree(self) -> None:
        self.assertEqual(_tree(CANONICAL), _tree(PACKAGED))


if __name__ == "__main__":
    unittest.main()
