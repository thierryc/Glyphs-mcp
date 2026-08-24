"""Regression tests for the coordinated release-version helper."""

from __future__ import annotations

import importlib.util
import json
import plistlib
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
        self.assertIn("releases/latest/download/Glyphs-MCP-latest.dmg", text)
        self.assertNotIn("GlyphsMCPInstaller.dmg", text)

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
            Path("content/getting-started/codex-chatgpt-plugin-ui.mdx"): (
                "Every host shares the same\n13 skills, localhost MCP configuration, and `1.6.0` package version.\n"
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
            [
                sys.executable,
                str(MODULE_PATH),
                "--dry-run",
                "--installer-build",
                "27",
                "1.6.1",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Dry run complete; repository files were not changed.", result.stdout)
        self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_target_aware_release_updates_v2_and_installer_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyphs-v2-version.") as temp_dir:
            root = Path(temp_dir)
            versions = root / "versions.py"
            pyproject = root / "pyproject.toml"
            project = root / "project.pbxproj"
            glyphs3 = root / "Glyphs3-Info.plist"
            glyphs3_manager = root / "Glyphs3-Manager-Info.plist"
            versions.write_text('SERVER_VERSION = "2.0.0.dev1"\n', encoding="utf-8")
            pyproject.write_text(
                '[project]\nname = "glyphs-mcp-v2"\nversion = "2.0.0.dev1"\n',
                encoding="utf-8",
            )
            project.write_text(
                "MARKETING_VERSION = 1.11.0;\nCURRENT_PROJECT_VERSION = 26;\n",
                encoding="utf-8",
            )
            for path in (glyphs3, glyphs3_manager):
                with path.open("wb") as stream:
                    plistlib.dump(
                        {
                            "CFBundleShortVersionString": "1.11.0",
                            "CFBundleVersion": "1.11.0",
                        },
                        stream,
                    )
            pinned_before = {path: path.read_bytes() for path in (glyphs3, glyphs3_manager)}

            bump_version.update_v2_source_version(versions, pyproject, "2.0.0")
            bump_version.update_installer_versions(project, "2.0.0", 27)

            self.assertIn('SERVER_VERSION = "2.0.0"', versions.read_text(encoding="utf-8"))
            self.assertIn('version = "2.0.0"', pyproject.read_text(encoding="utf-8"))
            project_text = project.read_text(encoding="utf-8")
            self.assertIn("MARKETING_VERSION = 2.0.0;", project_text)
            self.assertIn("CURRENT_PROJECT_VERSION = 27;", project_text)
            self.assertEqual(pinned_before, {path: path.read_bytes() for path in pinned_before})

    def test_cli_requires_explicit_installer_build_and_dry_run_omits_1x_plists(self) -> None:
        missing_build = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--dry-run", "2.0.0"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(missing_build.returncode, 2)
        self.assertIn("--installer-build", missing_build.stdout + missing_build.stderr)

        pinned_paths = (
            REPO_ROOT / "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Info.plist",
            REPO_ROOT / "plugin-manager/Glyphs MCP.glyphsPlugin/Contents/Info.plist",
        )
        before = {path: path.read_bytes() for path in pinned_paths}
        result = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--dry-run",
                "--installer-build",
                "27",
                "2.0.0",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Pinned Glyphs 3 surfaces unchanged", result.stdout)
        self.assertNotIn(str(pinned_paths[0]), result.stdout)
        self.assertNotIn(str(pinned_paths[1]), result.stdout)
        self.assertEqual(before, {path: path.read_bytes() for path in pinned_paths})


if __name__ == "__main__":
    unittest.main()
