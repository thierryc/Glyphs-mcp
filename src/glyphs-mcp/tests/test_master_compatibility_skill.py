"""Contract tests for the master compatibility skill and playbook."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
CANONICAL = REPO / "skills" / "glyphs-mcp-master-compatibility"
PACKAGED = REPO / "plugins" / "glyphs-mcp" / "skills" / "glyphs-mcp-master-compatibility"


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != ".DS_Store"
    }


class MasterCompatibilitySkillTests(unittest.TestCase):
    def test_skill_is_diagnostic_first_and_has_a_strict_completion_gate(self) -> None:
        text = (CANONICAL / "SKILL.md").read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        for required in (
            "Diagnose before editing",
            "review_master_compatibility",
            "get_operation",
            "review_start_node_alignment",
            "apply_start_node_alignment",
            "apply_compatibility_updates",
            "execute_python",
            "staged_document",
            "Before adding an off-curve node",
            "mastersCompatible == true",
            "never claim the glyph is compatible",
            "Never auto-save the font",
            "Show Master Compatibility",
        ):
            with self.subTest(required=required):
                self.assertIn(required, normalized)

    def test_playbook_covers_safe_near_and_manual_outcomes(self) -> None:
        text = (CANONICAL / "references" / "compatibility-playbook.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(text.split())
        for required in (
            "### Order or phase only",
            "### Nearly compatible",
            "### Ambiguous or manual",
            "semantic first node",
            "Never rotate open paths",
            "localized on-curve count difference",
            "new off-curve node",
            "explicit permission",
            "Make Node First",
            "Filter > Shape Order",
            "Path > Correct Path Direction",
            "mastersCompatible == true",
            "return `unresolved`",
            "host flag confirms technical structure, not interpolation quality",
        ):
            with self.subTest(required=required):
                self.assertIn(required, normalized)

    def test_metadata_keeps_implicit_invocation_enabled(self) -> None:
        text = (CANONICAL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "Glyphs Master Compatibility"', text)
        self.assertIn("$glyphs-mcp-master-compatibility", text)
        self.assertIn("allow_implicit_invocation: true", text)

    def test_packaged_skill_matches_canonical_tree(self) -> None:
        self.assertEqual(_tree(CANONICAL), _tree(PACKAGED))


if __name__ == "__main__":
    unittest.main()
