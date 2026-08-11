"""Guards against documentation drift for the MCP tool surface.

We avoid importing the tool modules because they import GlyphsApp (not present
in the normal unit test runner). Instead, we parse decorators from source.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


def _repo_root() -> Path:
    # .../src/glyphs-mcp/tests/test_*.py -> repo root is 3 parents up.
    return Path(__file__).resolve().parents[3]


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


if str(_resources_dir()) not in sys.path:
    sys.path.insert(0, str(_resources_dir()))

from tool_catalog import active_entries


def _active_tool_names() -> set[str]:
    return {entry.name for entry in active_entries()}


def _read_readme_command_set_section(readme_text: str) -> str:
    header = re.search(r"^##\s+Command Set\s+\(MCP server v[^\)]+\)\s*$", readme_text, re.M)
    if not header:
        raise AssertionError("README Command Set header not found.")

    # Find the next H2 heading after the command set header.
    rest = readme_text[header.end() :]
    next_header = re.search(r"^##\s+", rest, re.M)
    if next_header:
        return rest[: next_header.start()]
    return rest


class DocsSurfaceSyncTests(unittest.TestCase):
    def test_current_user_guidance_has_no_obsolete_tool_profiles(self) -> None:
        current_surfaces = (
            _repo_root() / "website" / "src" / "components" / "HomepageFeatures" / "index.tsx",
            _repo_root()
            / "macos-installer"
            / "GlyphsMCPInstaller"
            / "Core"
            / "StarterProjectCreator.swift",
            _repo_root()
            / "macos-installer"
            / "GlyphsMCPInstaller"
            / "Resources"
            / "Starter"
            / "AGENTS.md",
        )
        obsolete_phrases = ("tool profile", "read-only profile", "edit profile")

        for path in current_surfaces:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8", errors="replace").lower()
                for phrase in obsolete_phrases:
                    self.assertNotIn(phrase, text)

    def test_command_set_mdx_mentions_all_tools(self) -> None:
        tool_names = _active_tool_names()
        self.assertGreater(len(tool_names), 0, "Expected at least one tool name to be discovered.")

        command_set = _repo_root() / "content" / "reference" / "command-set.mdx"
        self.assertTrue(command_set.is_file(), f"Missing docs page: {command_set}")
        text = command_set.read_text(encoding="utf-8", errors="replace")

        missing = sorted([name for name in tool_names if name not in text])
        self.assertEqual(missing, [], f"command-set.mdx is missing tool names: {missing}")

    def test_readme_command_set_mentions_all_tools(self) -> None:
        readme = _repo_root() / "README.md"
        self.assertTrue(readme.is_file(), f"Missing README: {readme}")
        readme_text = readme.read_text(encoding="utf-8", errors="replace")
        section = _read_readme_command_set_section(readme_text)

        self.assertIn("76 active tools", section)
        self.assertIn("65 are model-visible", section)
        self.assertIn("11 are app-only", section)
        self.assertIn("authoritative list", section)
        self.assertNotIn("| Tool |", section)

    def test_italic_first_pass_docs_cite_primary_symbol_sources(self) -> None:
        page = _repo_root() / "content" / "italic-first-pass.md"
        text = page.read_text(encoding="utf-8", errors="replace")

        self.assertIn("### Sources and interpretation", text)
        for url in (
            "https://learn.microsoft.com/en-us/typography/develop/character-design-standards/math",
            "https://learn.microsoft.com/en-us/typography/opentype/spec/math",
            "https://www.unicode.org/reports/tr25/",
            "https://fonts.google.com/metadata/fonts",
            "https://fonttools.readthedocs.io/en/latest/pens/statisticsPen.html",
        ):
            self.assertIn(url, text)


if __name__ == "__main__":
    unittest.main()
