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
    "glyphs-mcp-connect",
    "glyphs-mcp-features",
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

    def test_plugin_skill_copies_match_the_six_canonical_sources(self) -> None:
        plugin_names = tuple(sorted(path.name for path in (PLUGIN / "skills").iterdir() if path.is_dir()))
        self.assertEqual(plugin_names, tuple(sorted(SKILL_NAMES)))
        for name in SKILL_NAMES:
            self.assertEqual(_tree(CANONICAL_SKILLS / name), _tree(PLUGIN / "skills" / name), name)

    def test_canonical_skills_use_stable_urls_for_repository_references(self) -> None:
        for name in SKILL_NAMES:
            text = (CANONICAL_SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("../../", text, name)
            self.assertIn("https://github.com/thierryc/Glyphs-mcp/blob/main/", text, name)

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
