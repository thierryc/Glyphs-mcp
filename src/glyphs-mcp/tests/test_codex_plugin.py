"""Contract tests for the repository Codex marketplace plug-in."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
PLUGIN = REPO / "plugins" / "glyphs-mcp"
CANONICAL_SKILLS = REPO / "skills"
SKILL_NAMES = (
    "glyphs",
    "glyphs-mcp-development",
    "glyphs-mcp-features",
    "glyphs-mcp-icon-font",
    "glyphs-mcp-italic-first-pass",
    "glyphs-mcp-kerning",
    "glyphs-mcp-outlines-docs",
    "glyphs-mcp-spacing",
)


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != ".DS_Store"
    }


class CodexPluginTests(unittest.TestCase):
    def test_manifest_and_mcp_connection(self) -> None:
        manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        mcp_config = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "glyphs-mcp")
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertEqual(manifest["mcpServers"], "./.mcp.json")
        self.assertNotIn("apps", manifest)
        self.assertEqual(manifest["interface"]["category"], "Creativity")
        self.assertEqual(manifest["interface"]["capabilities"], ["Interactive", "Read", "Write"])
        self.assertEqual(len(manifest["interface"]["defaultPrompt"]), 3)
        self.assertTrue((PLUGIN / manifest["interface"]["composerIcon"]).is_file())
        self.assertEqual(
            mcp_config,
            {"mcpServers": {"glyphs-mcp-server": {"type": "http", "url": "http://127.0.0.1:9680/mcp/"}}},
        )

    def test_repository_marketplace_points_to_the_plugin(self) -> None:
        marketplace = json.loads((REPO / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))

        self.assertEqual(marketplace["name"], "glyphs-mcp")
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "glyphs-mcp")
        self.assertEqual(entry["source"], {"source": "local", "path": "./plugins/glyphs-mcp"})
        self.assertEqual(entry["policy"], {"installation": "AVAILABLE", "authentication": "ON_INSTALL"})
        self.assertEqual(entry["category"], "Creativity")

    def test_plugin_skill_copies_match_the_eight_canonical_sources(self) -> None:
        plugin_names = tuple(sorted(path.name for path in (PLUGIN / "skills").iterdir() if path.is_dir()))
        self.assertEqual(plugin_names, tuple(sorted(SKILL_NAMES)))
        for name in SKILL_NAMES:
            self.assertEqual(_tree(CANONICAL_SKILLS / name), _tree(PLUGIN / "skills" / name), name)

    def test_canonical_skills_use_stable_urls_for_repository_references(self) -> None:
        for name in SKILL_NAMES:
            text = (CANONICAL_SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("../../", text, name)
            self.assertIn("https://github.com/thierryc/Glyphs-mcp/blob/main/", text, name)

    def test_generic_glyphs_skill_is_an_explicit_router(self) -> None:
        root = CANONICAL_SKILLS / "glyphs"
        files = {
            str(path.relative_to(root))
            for path in root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(files, {"SKILL.md", "agents/openai.yaml"})

        skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
        metadata_text = (root / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertLessEqual(len(skill_text.splitlines()), 55)
        self.assertIn("name: glyphs", skill_text)
        self.assertIn("get_server_info", skill_text)
        self.assertIn("list_open_fonts", skill_text)
        self.assertIn("glyphs-mcp-spacing", skill_text)
        self.assertIn("glyphs-mcp-kerning", skill_text)
        self.assertIn("glyphs-mcp-development", skill_text)
        self.assertIn('display_name: "Glyphs MCP"', metadata_text)
        self.assertIn("$glyphs", metadata_text)
        self.assertIn("allow_implicit_invocation: false", metadata_text)

    def test_development_skill_is_workspace_first_and_documented(self) -> None:
        root = CANONICAL_SKILLS / "glyphs-mcp-development"
        skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
        metadata_text = (root / "agents" / "openai.yaml").read_text(encoding="utf-8")

        self.assertIn("docs_search", skill_text)
        self.assertIn("docs_get", skill_text)
        self.assertIn("current workspace", skill_text)
        self.assertIn("Never install, execute, reload, restart Glyphs", skill_text)
        self.assertTrue((root / "scripts" / "scaffold.py").is_file())
        self.assertTrue((root / "assets" / "GlyphsSDK-LICENSE.txt").is_file())
        self.assertIn('display_name: "Glyphs MCP Development"', metadata_text)
        self.assertIn("$glyphs-mcp-development", metadata_text)
        self.assertIn("allow_implicit_invocation: true", metadata_text)

    def test_icon_font_skill_stays_narrow_and_domain_specific(self) -> None:
        root = CANONICAL_SKILLS / "glyphs-mcp-icon-font"
        files = {
            str(path.relative_to(root))
            for path in root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(files, {"SKILL.md", "agents/openai.yaml"})

        text = (root / "SKILL.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(text.splitlines()), 55)
        self.assertIn("specifically in an icon or symbol font", text)
        self.assertIn("not icon drawing or general PUA work", text)
        self.assertIn("require its previous map before allocation", text)
        self.assertIn("review_unicode_assignments", text)
        self.assertIn("apply_unicode_assignments", text)
        self.assertIn("glyphs-mcp-outlines-docs", text)
        self.assertIn("glyphs-mcp-spacing", text)

    def test_plugin_installs_from_the_marketplace_in_an_isolated_codex_home(self) -> None:
        codex = shutil.which("codex")
        if not codex:
            self.skipTest("Codex CLI is unavailable")
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-codex-home.") as home:
            env = dict(os.environ, CODEX_HOME=home)
            added_marketplace = subprocess.run(
                [codex, "plugin", "marketplace", "add", str(REPO), "--json"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                env=env,
            )
            self.assertEqual(added_marketplace.returncode, 0, added_marketplace.stdout + added_marketplace.stderr)
            installed = subprocess.run(
                [codex, "plugin", "add", "glyphs-mcp@glyphs-mcp", "--json"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                env=env,
            )
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            payload = json.loads(installed.stdout)
            self.assertEqual(payload["name"], "glyphs-mcp")
            self.assertEqual(payload["version"], "0.1.0")


if __name__ == "__main__":
    unittest.main()
