"""Contract tests for the canonical release skill and packaged mirror."""

from __future__ import annotations

import json
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
            "skills/manifest.json",
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
            "requirements-dev.txt",
            "fontmake",
            "release_security.py candidate",
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

    def test_release_qa_documents_the_asymmetric_v2_matrix(self) -> None:
        protocol = (REPO / "content/contributor/release-qa-protocol.mdx").read_text(
            encoding="utf-8"
        )
        for required in (
            "Glyphs 3.5 -> pinned v1.11",
            "Glyphs 4 -> v2.0",
            "Catalog equality is not an acceptance criterion",
            "must not mutate a document",
            "exact canonical and native baseline",
            "No live installation is replaced",
            "development symlink and its generated target",
            "Stop rather than qualifying a `dev` build",
            "`save_document` Save As",
            "`saveMode=save_as`",
            "`overwritePolicy=fail_if_exists`",
        ):
            self.assertIn(required, protocol)
        self.assertIn("verify_copy_and_make_copy", protocol)
        self.assertNotIn("makeCopy=True", protocol)

        foundation = (REPO / "content/contributor/glyphs-mcp-2-foundation.mdx").read_text(
            encoding="utf-8"
        )
        self.assertIn("## Frozen public surface", foundation)
        self.assertIn("Disposable Glyphs 4 live gates remain a release", foundation)

    def test_milestone_12_closure_records_current_unsigned_evidence(self) -> None:
        foundation = (REPO / "content/contributor/glyphs-mcp-2-foundation.mdx").read_text(
            encoding="utf-8"
        )
        build_notes = (REPO / "content/contributor/release-build-notes.mdx").read_text(
            encoding="utf-8"
        )
        compact_build_notes = " ".join(build_notes.split())
        checkpoint = (REPO / "build/milestone-12-session-checkpoint.md").read_text(
            encoding="utf-8"
        )
        changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn("Qualification: automated v2 schema", foundation)
        self.assertIn("must not be inferred from source-level tests", foundation)
        self.assertIn("1,357 Python tests with two expected skips", compact_build_notes)
        self.assertIn("112 Xcode test methods passed", compact_build_notes)
        self.assertIn(
            "sha256:9de0d412f2395920340b7910e79b2853bf94dad912d40e7757d63c032062ea1d",
            build_notes,
        )
        self.assertIn(
            "sha256:e12de192ebc7bf025147b20f0e1d6f8a85ce8f8c72348712617641c787a681c0",
            build_notes,
        )
        self.assertIn("Milestone 12 is complete locally", checkpoint)
        self.assertIn("Signing: not performed", checkpoint)
        self.assertIn("Publication: not performed", checkpoint)
        self.assertNotIn("schema-v6 automated and disposable-host\nclosure must pass", changelog)
        self.assertIn("Schema-v6 automated and disposable-host closure passed", changelog)

    def test_v2_release_notes_cover_host_and_rollback_boundaries(self) -> None:
        notes_path = REPO / "content/contributor/release-2-0-0-notes.mdx"
        notes = notes_path.read_text(encoding="utf-8")
        for required in (
            "Glyphs 4",
            "Glyphs 3",
            "schema v6",
            "18 generic tools",
            "Knowledge supplies pinned cited facts",
            "`EntitySelector`, `Projection`, `Constraint`, and `ChangeOperation`",
            "`preview_change`",
            "`apply_change`",
            "permanent Python fallback",
            "network calls, subprocesses",
            "`save_document`",
            "`apply_export`",
            "conflict-aware revert",
            "no implicit save",
            "Source-level tests do not substitute",
        ):
            self.assertIn(required, notes)
        self.assertNotIn("arbitrary-action Git history", notes)
        self.assertNotIn("byte-for-byte whole-font history", notes)

    def test_release_preflight_requires_exact_source_build_dependency(self) -> None:
        runner = (REPO / "scripts/run_local_release_tests.sh").read_text(
            encoding="utf-8"
        )
        dependency_check = '"$python_bin" scripts/check_release_dependencies.py'
        complete_suite = "GLYPHS_MCP_FULL_PYTHON_MATRIX=1"
        self.assertIn(dependency_check, runner)
        self.assertIn("--requirements requirements-dev.txt", runner)
        self.assertIn("fontmake uharfbuzz", runner)
        self.assertLess(runner.index(dependency_check), runner.index(complete_suite))

    def test_changelog_managed_skill_count_matches_manifest(self) -> None:
        manifest = json.loads((REPO / "skills/manifest.json").read_text(encoding="utf-8"))
        changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
        current = changelog.split("## 2.0.0", 1)[1].split("\n## ", 1)[0]
        expected = len(manifest["managedSkills"])

        self.assertEqual(expected, 18)
        self.assertIn("{} managed skills".format(expected), current)
        self.assertNotRegex(current, r"\b13 managed(?: v2)? skills\b")


if __name__ == "__main__":
    unittest.main()
