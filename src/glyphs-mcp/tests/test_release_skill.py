"""Contract tests for the canonical release skill and packaged mirror."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
CANONICAL = REPO / "skills" / "glyphs-mcp-release"
PACKAGED = REPO / "plugins" / "glyphs-mcp" / "skills" / "glyphs-mcp-release"


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != ".DS_Store"
    }


class ReleaseSkillTests(unittest.TestCase):
    def test_skill_enforces_release_phase_boundaries(self) -> None:
        text = (CANONICAL / "SKILL.md").read_text(encoding="utf-8")
        for required in (
            "scripts/bump_version.py",
            "scripts/sync_codex_plugin_skills.sh",
            "MANAGED_SKILL_NAMES",
            "quick_validate.py",
            "Never save an open font automatically",
            "does not authorize committing",
            "annotated signed tag",
            "exact-tag confirmation",
            "Keep uploaded releases as drafts",
            "Never replace an already distributed asset",
        ):
            self.assertIn(required, text)
        self.assertLessEqual(len(text.splitlines()), 80)

    def test_reference_link_resolves_inside_skill_package(self) -> None:
        text = (CANONICAL / "SKILL.md").read_text(encoding="utf-8")
        match = re.search(r"\]\((references/release-gates\.md)\)", text)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertTrue((CANONICAL / match.group(1)).is_file())
        self.assertNotIn("../../", text)

    def test_reference_documents_required_release_gates(self) -> None:
        text = (CANONICAL / "references" / "release-gates.md").read_text(encoding="utf-8")
        for required in (
            "run_local_release_tests.sh",
            "release_security.py metadata",
            "quick_validate.py",
            "publish_release_assets.sh --tag vX.Y.Z --dry-run",
            "SKIP_NOTARIZATION=1",
            "Do not publish a standalone plug-in ZIP",
            "--confirm-publish vX.Y.Z",
            "Public publication is a fourth",
        ):
            self.assertIn(required, text)

    def test_packaged_skill_matches_canonical_tree(self) -> None:
        self.assertEqual(_tree(CANONICAL), _tree(PACKAGED))


if __name__ == "__main__":
    unittest.main()
