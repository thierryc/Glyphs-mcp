"""Keep v2 skill instructions aligned with the callable runtime surface."""

from __future__ import annotations

import inspect
import json
import re
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.transport.fastmcp import ToolHandlers  # noqa: E402
from glyphs_mcp_v2.versions import SERVER_VERSION  # noqa: E402


class V2SkillContractTests(unittest.TestCase):
    skills = (
        "glyphs-mcp-scripting",
        "glyphs-mcp-spacing",
        "glyphs-mcp-opentype-features",
    )

    def _text(self, skill: str, *, packaged: bool = False) -> str:
        root = (
            REPO / "plugins" / "glyphs-mcp" / "skills"
            if packaged
            else REPO / "skills"
        )
        return (root / skill / "SKILL.md").read_text(encoding="utf-8")

    def test_v2_skills_are_marked_and_packaged_from_the_same_source(self) -> None:
        for skill in self.skills:
            with self.subTest(skill=skill):
                canonical = self._text(skill)
                self.assertIn("surface: glyphs-mcp-v2", canonical)
                self.assertEqual(canonical, self._text(skill, packaged=True))

    def test_removed_v1_arguments_and_tools_are_explicitly_forbidden(self) -> None:
        scripting = self._text("glyphs-mcp-scripting")
        spacing = self._text("glyphs-mcp-spacing")
        opentype = self._text("glyphs-mcp-opentype-features")
        self.assertIn("Do not send the removed snippet_only argument", scripting)
        self.assertNotIn("`snippet_only`", scripting)
        self.assertIn("Do not send the removed dry_run argument", spacing)
        self.assertNotIn("dry_run=true", spacing)
        self.assertIn("Do not use the removed glyphs-mcp-features", opentype)
        self.assertIn("list_style_sets workflow", opentype)
        self.assertNotIn("`list_style_sets`", opentype)

    def test_referenced_v2_tools_and_parameters_exist(self) -> None:
        referenced = set()
        for skill in self.skills:
            referenced.update(re.findall(r"`([a-z][a-z0-9_]+)`", self._text(skill)))
        toolish = {name for name in referenced if name in TOOL_CATALOG}
        self.assertIn("execute_python", toolish)
        self.assertIn("apply_spacing", toolish)
        self.assertIn("list_opentype_items", toolish)
        self.assertIn("compile_opentype_features", toolish)
        execute_parameters = inspect.signature(ToolHandlers.execute_python).parameters
        spacing_parameters = inspect.signature(ToolHandlers.apply_spacing).parameters
        self.assertNotIn("snippet_only", execute_parameters)
        self.assertNotIn("dry_run", spacing_parameters)

    def test_plugin_manifest_and_runtime_version_agree(self) -> None:
        manifest = json.loads(
            (REPO / "plugins" / "glyphs-mcp" / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["version"], SERVER_VERSION)


if __name__ == "__main__":
    unittest.main()
