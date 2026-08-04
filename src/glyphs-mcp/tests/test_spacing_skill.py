"""Contract tests for the canonical spacing skill and its packaged mirror."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class SpacingSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.canonical = _repo_root() / "skills" / "glyphs-mcp-spacing"
        self.packaged = _repo_root() / "plugins" / "glyphs-mcp" / "skills" / "glyphs-mcp-spacing"

    def test_skill_contains_guarded_procedural_workflow(self) -> None:
        text = (self.canonical / "SKILL.md").read_text(encoding="utf-8")
        for required in (
            "glyphs-mcp-server",
            "list_open_fonts",
            "review_spacing",
            "resolvedReferenceGlyph",
            "apply_spacing",
            "dry_run=true",
            "current metrics are trusted or placeholders",
            "Current LSB/RSB",
            "calculated-minus-reference",
            "Never save the Glyphs document automatically",
            "HHHOHH",
            "AVAYAW",
            "nonono",
        ):
            self.assertIn(required, text)
        self.assertLessEqual(len(text.splitlines()), 90)

    def test_direct_reference_link_resolves_inside_skill_package(self) -> None:
        text = (self.canonical / "SKILL.md").read_text(encoding="utf-8")
        match = re.search(r"\]\((references/negative-sidebearings\.md)\)", text)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertTrue((self.canonical / match.group(1)).is_file())
        self.assertNotIn("CODEX.md", text)
        self.assertNotIn("../../", text)

    def test_negative_bearing_reference_records_required_policy(self) -> None:
        text = (self.canonical / "references" / "negative-sidebearings.md").read_text(encoding="utf-8")
        for required in (
            "signed OpenType metrics",
            "Negative values are legal",
            "`-0.05em`",
            "`-0.10em`",
            "overrides.blockedGlyphs",
            "True monospaced families",
            "Typewriter-styled proportional fonts",
            "`V`, `W`, or `Y`",
            "model failures",
        ):
            self.assertIn(required, text)

    def test_packaged_skill_matches_canonical_tree(self) -> None:
        def tree(root: Path) -> dict[str, bytes]:
            return {
                str(path.relative_to(root)): path.read_bytes()
                for path in sorted(root.rglob("*"))
                if path.is_file() and path.name != ".DS_Store"
            }

        self.assertEqual(tree(self.canonical), tree(self.packaged))


if __name__ == "__main__":
    unittest.main()
