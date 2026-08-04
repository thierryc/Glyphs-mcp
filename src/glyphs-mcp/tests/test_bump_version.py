"""Regression tests for the coordinated release-version helper."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "bump_version.py"
SPEC = importlib.util.spec_from_file_location("bump_version_test_module", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
bump_version = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bump_version
SPEC.loader.exec_module(bump_version)


class BumpVersionTests(unittest.TestCase):
    def _update(self, version_sentence: str) -> str:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "README.md"
            path.write_text(
                "\n".join(
                    [
                        "## Command Set (MCP server v1.5.4)",
                        version_sentence,
                        "https://github.com/thierryc/Glyphs-mcp/releases/latest/download/GlyphsMCPInstaller.dmg",
                        "https://github.com/thierryc/Glyphs-mcp/releases/latest",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            bump_version.update_readme(path, "1.6.0")
            return path.read_text(encoding="utf-8")

    def test_updates_current_generic_server_version_wording(self) -> None:
        text = self._update(
            "This table describes the tool surface exposed by the MCP server shipped in this repo (version `1.5.4`)."
        )
        self.assertIn("MCP server v1.6.0", text)
        self.assertIn("shipped in this repo (version `1.6.0`)", text)

    def test_retains_legacy_fastmcp_version_wording_support(self) -> None:
        text = self._update('The server uses FastMCP `version="1.5.4"`.')
        self.assertIn('FastMCP `version="1.6.0"`', text)

    def test_updates_agent_plugin_manifest_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plugin.json"
            path.write_text(
                json.dumps({"name": "glyphs-mcp", "version": "1.5.4", "skills": "./skills/"}),
                encoding="utf-8",
            )

            bump_version.update_json_version(path, "1.6.0")

            manifest = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], "1.6.0")
            self.assertEqual(manifest["skills"], "./skills/")

    def test_tracks_all_four_agent_plugin_manifests(self) -> None:
        self.assertEqual(
            bump_version.AGENT_PLUGIN_MANIFEST_PATHS,
            (
                Path("plugins/glyphs-mcp/.codex-plugin/plugin.json"),
                Path("plugins/glyphs-mcp/.claude-plugin/plugin.json"),
                Path("plugins/glyphs-mcp/.cursor-plugin/plugin.json"),
                Path("plugins/glyphs-mcp/.github/plugin/plugin.json"),
            ),
        )

    def test_updates_agent_plugin_documentation_versions(self) -> None:
        samples = {
            Path("README.md"): (
                "Glyphs MCP 1.6.0 provides one shared plugin package\n"
                "All host manifests use version `1.6.0`.\n"
            ),
            Path("plugins/glyphs-mcp/README.md"): (
                "Version 1.6.0 bundles the same general Glyphs launcher.\n"
            ),
            Path("content/getting-started/use-agent-skills.mdx"): (
                "All four manifests use version `1.6.0` and stay aligned.\n"
                "Use the release skill to prepare version 1.6.0 and stop before external publication.\n"
            ),
            Path("content/getting-started/installation.mdx"): (
                "Agent plugins are a separate, optional setup. Version 1.6.0 includes one shared package.\n"
            ),
            Path("content/contributor/release-qa-protocol.mdx"): (
                "Each host resolves version `1.6.0`, the same skills, and the same endpoint.\n"
            ),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for relative_path, text in samples.items():
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                bump_version.update_agent_plugin_doc(
                    path,
                    "1.6.1",
                    bump_version.AGENT_PLUGIN_DOC_REPLACEMENTS[relative_path],
                )
                updated = path.read_text(encoding="utf-8")
                self.assertIn("1.6.1", updated, relative_path)
                self.assertNotIn("1.6.0", updated, relative_path)

    def test_dry_run_does_not_change_release_surfaces(self) -> None:
        paths = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Info.plist",
            *(REPO_ROOT / path for path in bump_version.AGENT_PLUGIN_MANIFEST_PATHS),
            *(REPO_ROOT / path for path in bump_version.AGENT_PLUGIN_DOC_REPLACEMENTS),
        ]
        before = {path: path.read_bytes() for path in paths}

        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--dry-run", "1.6.1"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Dry run complete; repository files were not changed.", result.stdout)
        self.assertEqual(before, {path: path.read_bytes() for path in paths})


if __name__ == "__main__":
    unittest.main()
