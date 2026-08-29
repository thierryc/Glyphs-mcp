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
            "surface: glyphs-mcp-v2",
            "get_server_info",
            "data.apiMajor == 2",
            "search_knowledge",
            "get_knowledge",
            "list_documents",
            "read_document",
            "every interpolation-participating layer",
            "geometry counts",
            "alignment",
            'execute_python(mode="read_only")',
            "Classify the mismatch",
            "Start-node placement is a semantic decision",
            "explicit `move`, `set`, or `duplicate` mechanics",
            'execute_python(mode="staged_document")',
            "Preserve topology",
            "preview_change",
            "apply_change",
            "re-read all participating layers",
            "Never call `save_document` automatically",
        ):
            with self.subTest(required=required):
                self.assertIn(required, normalized)

        for removed_tool in (
            "review_master_compatibility",
            "apply_compatibility_updates",
            "list_glyphs",
            "list_layers",
            "review_start_node_alignment",
            "apply_start_node_alignment",
            "get_glyph_paths",
            "get_glyph_components",
        ):
            with self.subTest(removed_tool=removed_tool):
                self.assertNotIn(removed_tool, normalized)

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
