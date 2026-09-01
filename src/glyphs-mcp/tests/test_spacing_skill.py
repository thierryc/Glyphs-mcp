"""Contract tests for the canonical spacing skill and its packaged mirror."""

from __future__ import annotations

import unittest
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class SpacingSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.canonical = _repo_root() / "skills" / "glyphs-mcp-spacing"
        self.packaged = _repo_root() / "plugins" / "glyphs-mcp" / "skills" / "glyphs-mcp-spacing"

    def test_skill_contains_generic_verified_workflow(self) -> None:
        text = (self.canonical / "SKILL.md").read_text(encoding="utf-8")
        for required in (
            "surface: glyphs-mcp-v2",
            "data.apiMajor == 2",
            "list_documents",
            "search_knowledge",
            "get_knowledge",
            "read_document",
            "spacing.horizontal",
            "spacing.vertical",
            "leadingBearing",
            "trailingBearing",
            "translation",
            "Layer translation moves paths and",
            "configuredAutomaticComponentCount",
            "effectiveLayerAlignment",
            "Metadata is not refusal",
            "Reviewable settlement and completion",
            "Native grid rounding",
            "Unregistered geometry deviation remains a",
            "If a preview has `applicable=false`, do not apply it",
            "open_document_view",
            "material deviation in spacing or geometry",
            "preview_change",
            "apply_change",
            "revert_change",
            "quantizer=\"exact\"",
            "floating-point geometry",
            "staged_document",
            "live_open_world",
            "Signed sidebearings are legal",
            "Never auto-save",
            "HHHOHH",
            "AVAYAW",
            "nonono",
        ):
            self.assertIn(required, text)
        for retired in (
            "review_spacing",
            "apply_spacing",
            "list_layers",
            "get_document_status",
            "quantizer=\"grid\"",
            "snap to the grid",
        ):
            self.assertNotIn(retired, text)
        self.assertLessEqual(len(text.splitlines()), 195)

    def test_obsolete_negative_sidebearing_reference_is_removed(self) -> None:
        text = (self.canonical / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("negative-sidebearings.md", text)
        self.assertFalse(
            (self.canonical / "references" / "negative-sidebearings.md").exists()
        )
        self.assertNotIn("CODEX.md", text)
        self.assertNotIn("../../", text)

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
