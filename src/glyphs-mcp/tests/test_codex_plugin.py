"""Contract tests for the shared multi-host agent plugin package."""

from __future__ import annotations

import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
PLUGIN = REPO / "plugins" / "glyphs-mcp"
CANONICAL_SKILLS = REPO / "skills"
SKILL_NAMES = tuple(item['name'] for item in json.loads((CANONICAL_SKILLS/'manifest.json').read_text())['managedSkills'])
sys.path.insert(0, str(REPO / "scripts"))
from desktop_release_identity import load as release_identity
PLUGIN_VERSION = release_identity(REPO)["version"]
HOST_MANIFESTS = {
    "codex": PLUGIN / ".codex-plugin" / "plugin.json",
    "claude": PLUGIN / ".claude-plugin" / "plugin.json",
    "cursor": PLUGIN / ".cursor-plugin" / "plugin.json",
    "copilot": PLUGIN / ".github" / "plugin" / "plugin.json",
}
HOST_MARKETPLACES = {
    "codex": REPO / ".agents" / "plugins" / "marketplace.json",
    "claude": REPO / ".claude-plugin" / "marketplace.json",
    "cursor": REPO / ".cursor-plugin" / "marketplace.json",
    "copilot": REPO / ".github" / "plugin" / "marketplace.json",
}
HOST_DISCOVERY_PATHS = {
    "codex": (".codex-plugin/plugin.json", ".agents/plugins/marketplace.json"),
    "claude": (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"),
    "cursor": (".cursor-plugin/plugin.json", ".cursor-plugin/marketplace.json"),
    "copilot": (".github/plugin/plugin.json", ".github/plugin/marketplace.json"),
}
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CURSOR_MANIFEST_FIELDS = {
    "name",
    "displayName",
    "description",
    "version",
    "minClientVersions",
    "author",
    "publisher",
    "homepage",
    "repository",
    "license",
    "logo",
    "keywords",
    "category",
    "tags",
    "commands",
    "agents",
    "skills",
    "rules",
    "hooks",
    "mcpServers",
}
COPILOT_MANIFEST_FIELDS = {
    "name",
    "description",
    "version",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "category",
    "tags",
    "agents",
    "skills",
    "commands",
    "hooks",
    "extensions",
    "mcpServers",
    "lspServers",
}


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != ".DS_Store"
        and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo")
    }


class AgentPluginTests(unittest.TestCase):
    def test_host_native_discovery_paths_are_present(self) -> None:
        for host, (manifest_path, marketplace_path) in HOST_DISCOVERY_PATHS.items():
            with self.subTest(host=host):
                self.assertEqual(HOST_MANIFESTS[host], PLUGIN / manifest_path)
                self.assertEqual(HOST_MARKETPLACES[host], REPO / marketplace_path)
                self.assertTrue(HOST_MANIFESTS[host].is_file())
                self.assertTrue(HOST_MARKETPLACES[host].is_file())

    def test_host_manifests_share_version_skills_and_mcp_connection(self) -> None:
        mcp_config = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))

        for host, path in HOST_MANIFESTS.items():
            with self.subTest(host=host):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["name"], "glyphs-mcp")
                self.assertEqual(manifest["version"], PLUGIN_VERSION)
                self.assertRegex(manifest["version"], SEMVER_RE)
                self.assertIsInstance(manifest["description"], str)
                self.assertIsInstance(manifest["author"]["name"], str)
                self.assertEqual(manifest["skills"], "./skills/")
                self.assertEqual(manifest["mcpServers"], "./.mcp.json")
                self.assertTrue((PLUGIN / manifest["skills"]).is_dir())
                self.assertTrue((PLUGIN / manifest["mcpServers"]).is_file())

        codex_manifest = json.loads(HOST_MANIFESTS["codex"].read_text(encoding="utf-8"))
        self.assertNotIn("apps", codex_manifest)
        self.assertEqual(codex_manifest["interface"]["category"], "Creativity")
        self.assertEqual(codex_manifest["interface"]["capabilities"], ["Interactive", "Read", "Write"])
        self.assertEqual(len(codex_manifest["interface"]["defaultPrompt"]), 3)
        self.assertTrue((PLUGIN / codex_manifest["interface"]["composerIcon"]).is_file())
        self.assertEqual(
            mcp_config,
            {"mcpServers": {"glyphs-mcp-server": {"type": "http", "url": "http://127.0.0.1:9680/mcp/"}}},
        )
        runtime_text = (
            REPO
            / "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Resources/mcp_runtime.py"
        ).read_text(encoding="utf-8")
        self.assertIn('FastMCP(name="Glyphs MCP Server", version=get_plugin_version())', runtime_text)

    def test_host_specific_manifests_use_supported_fields(self) -> None:
        cursor = json.loads(HOST_MANIFESTS["cursor"].read_text(encoding="utf-8"))
        copilot = json.loads(HOST_MANIFESTS["copilot"].read_text(encoding="utf-8"))

        self.assertEqual(set(cursor) - CURSOR_MANIFEST_FIELDS, set())
        self.assertEqual(set(copilot) - COPILOT_MANIFEST_FIELDS, set())
        self.assertTrue((PLUGIN / cursor["logo"]).is_file())

    def test_repository_marketplaces_point_to_the_shared_plugin_without_versions(self) -> None:
        for host, path in HOST_MARKETPLACES.items():
            with self.subTest(host=host):
                marketplace = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(marketplace["name"], "glyphs-mcp")
                self.assertNotIn("version", marketplace)
                self.assertNotIn("version", marketplace.get("metadata", {}))
                self.assertEqual(len(marketplace["plugins"]), 1)
                entry = marketplace["plugins"][0]
                self.assertEqual(entry["name"], "glyphs-mcp")
                self.assertNotIn("version", entry)
                if host == "codex":
                    self.assertLessEqual(set(marketplace), {"name", "interface", "plugins"})
                    self.assertEqual(entry["source"], {"source": "local", "path": "./plugins/glyphs-mcp"})
                    self.assertEqual(
                        entry["policy"],
                        {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                    )
                    self.assertEqual(entry["category"], "Creativity")
                    source_path = entry["source"]["path"]
                else:
                    self.assertLessEqual(set(marketplace), {"name", "owner", "metadata", "plugins"})
                    self.assertIsInstance(marketplace["owner"]["name"], str)
                    self.assertEqual(entry["source"], "./plugins/glyphs-mcp")
                    self.assertLessEqual(set(entry), {"name", "source", "description"})
                    source_path = entry["source"]
                self.assertEqual((REPO / source_path.removeprefix("./")).resolve(), PLUGIN.resolve())

    def test_copilot_plugin_is_not_enabled_implicitly(self) -> None:
        self.assertFalse((REPO / ".github" / "copilot" / "settings.json").exists())

    def test_multi_host_documentation_keeps_plugins_optional(self) -> None:
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        guide = (REPO / "content/getting-started/use-agent-skills.mdx").read_text(encoding="utf-8")
        combined = readme + guide
        for host in ("Codex", "Claude Code", "Cursor", "GitHub Copilot CLI"):
            self.assertIn(host, combined)
        self.assertIn("matching local package", guide)
        for skill in json.loads((REPO / "skills/manifest.json").read_text())["managedSkills"]:
            self.assertIn("`" + skill["name"] + "`", guide)
        # Released marketplace instructions belong to the preserved v1 guide;
        # an unpublished candidate must not promise marketplace installation.
        legacy = (REPO / "website/versioned_docs/version-1.11.0/getting-started/use-agent-skills.mdx").read_text()
        for command in (
            "codex plugin marketplace add thierryc/Glyphs-mcp",
            "claude plugin marketplace add thierryc/Glyphs-mcp",
            "cursor-agent plugin marketplace add https://github.com/thierryc/Glyphs-mcp",
            "copilot plugin marketplace add thierryc/Glyphs-mcp",
            "copilot plugin install thierryc/Glyphs-mcp:plugins/glyphs-mcp",
            "/glyphs-mcp:glyphs",
            "/glyphs-mcp/glyphs",
        ):
            self.assertIn(command, legacy)
        self.assertIn("plugin is optional", combined.lower())
        self.assertIn("manual MCP", combined)

    def test_cursor_local_plugin_layout_smoke(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-cursor-plugin.") as temp_dir:
            installed = Path(temp_dir) / ".cursor" / "plugins" / "local" / "glyphs-mcp"
            shutil.copytree(PLUGIN, installed)
            manifest = json.loads((installed / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], PLUGIN_VERSION)
            self.assertTrue((installed / manifest["skills"]).is_dir())
            self.assertTrue((installed / manifest["mcpServers"]).is_file())

    def test_plugin_skill_copies_match_the_canonical_sources(self) -> None:
        self.assertEqual(len(SKILL_NAMES), len(set(SKILL_NAMES)))
        plugin_names = tuple(sorted(path.name for path in (PLUGIN / "skills").iterdir() if path.is_dir()))
        self.assertEqual(plugin_names, tuple(sorted(SKILL_NAMES)))
        for name in SKILL_NAMES:
            self.assertEqual(_tree(CANONICAL_SKILLS / name), _tree(PLUGIN / "skills" / name), name)

    def test_skills_inherit_the_package_version(self) -> None:
        for name in SKILL_NAMES:
            for root in (CANONICAL_SKILLS, PLUGIN / "skills"):
                text = (root / name / "SKILL.md").read_text(encoding="utf-8")
                frontmatter = text.split("---", 2)[1]
                self.assertNotRegex(frontmatter, r"(?m)^version\s*:", f"{root / name} has its own version")

    def test_canonical_skill_names_and_catalog_routing_stay_current(self) -> None:
        combined = []
        for name in SKILL_NAMES:
            text = (CANONICAL_SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            frontmatter = text.split("---", 2)[1]
            match = re.search(r"(?m)^name:\s*(\S+)\s*$", frontmatter)
            self.assertIsNotNone(match, name)
            self.assertEqual(match.group(1), name)
            combined.append(text)

        skill_text = "\n".join(combined)
        self.assertNotIn("tool profile", skill_text.lower())
        self.assertNotIn("Use Edit for this specialized workflow", skill_text)
        self.assertNotIn("Use Read-only for detached candidate preview", skill_text)
        for tool in ("get_status", "list_documents", "read_entities", "start_job", "get_job", "apply_job", "accept_job", "discard_job", "save_document"):
            self.assertIn("`" + tool + "`", skill_text)
        self.assertIn("Native Undo and Redo", skill_text)
        self.assertNotIn("execute_code_with_context", skill_text)
        self.assertNotIn("preview_italic_first_pass_candidate", skill_text)

    def test_shared_skill_sync_check_mode(self) -> None:
        result = subprocess.run(
            [str(REPO / "scripts" / "sync_codex_plugin_skills.sh"), "--check"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("shared agent plugin package", result.stdout)

    def test_canonical_skill_links_resolve_without_repository_dependencies(self) -> None:
        for name in SKILL_NAMES:
            base = CANONICAL_SKILLS / name
            for page in [base / "SKILL.md", *sorted((base / "references").glob("*.md"))]:
                for target in re.findall(r"\]\(([^)]+)\)", page.read_text(encoding="utf-8")):
                    if target.startswith(("https://", "http://", "#")):
                        continue
                    resolved = (page.parent / target.split("#", 1)[0]).resolve()
                    self.assertTrue(resolved.is_relative_to(CANONICAL_SKILLS.resolve()), (page, target))
                    self.assertTrue(resolved.is_file(), (page, target))

    def test_coding_routes_reach_installed_workflow_resources(self) -> None:
        # Check real routing edges instead of requiring obsolete stock wording.
        edges = {
            "glyphs/SKILL.md": ["../glyphs-mcp-development/SKILL.md"],
            "glyphs-mcp-scripting/SKILL.md": ["../glyphs-mcp-development/SKILL.md"],
            "glyphs-mcp-development/SKILL.md": ["../glyphs/SKILL.md", "references/development-docs.md",
                                               "references/native-iteration.md", "references/verification-and-recovery.md"],
        }
        for source, targets in edges.items():
            page = CANONICAL_SKILLS / source
            links = re.findall(r"\]\(([^)]+)\)", page.read_text(encoding="utf-8"))
            for target in targets:
                self.assertIn(target, links, source)
                self.assertTrue((page.parent / target).is_file(), (source, target))

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
            self.assertEqual(payload["version"], PLUGIN_VERSION)

    def test_plugin_validates_and_installs_in_an_isolated_claude_home(self) -> None:
        claude = shutil.which("claude")
        if not claude:
            self.skipTest("Claude Code CLI is unavailable")
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-claude-home.") as home:
            env = dict(os.environ, CLAUDE_CONFIG_DIR=home)
            for target in (PLUGIN, REPO):
                validated = subprocess.run(
                    [claude, "plugin", "validate", "--strict", str(target)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                    env=env,
                )
                self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)
            added_marketplace = subprocess.run(
                [claude, "plugin", "marketplace", "add", str(REPO), "--scope", "user"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=env,
            )
            self.assertEqual(
                added_marketplace.returncode,
                0,
                added_marketplace.stdout + added_marketplace.stderr,
            )
            installed = subprocess.run(
                [claude, "plugin", "install", "glyphs-mcp@glyphs-mcp", "--scope", "user"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=env,
            )
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            listed = subprocess.run(
                [claude, "plugin", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=env,
            )
            self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
            self.assertIn("glyphs-mcp", listed.stdout)
            installed_manifests = []
            for path in Path(home).rglob("plugin.json"):
                try:
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if manifest.get("name") == "glyphs-mcp":
                    installed_manifests.append(manifest)
            self.assertTrue(installed_manifests)
            self.assertTrue(any(item.get("version") == PLUGIN_VERSION for item in installed_manifests))

    def test_plugin_installs_in_an_isolated_copilot_home_when_available(self) -> None:
        copilot = shutil.which("copilot")
        if not copilot:
            self.skipTest("GitHub Copilot CLI is unavailable")
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-copilot-root.") as temp_dir:
            home = Path(temp_dir) / "home"
            cache = Path(temp_dir) / "cache"
            home.mkdir()
            cache.mkdir()
            env = dict(os.environ, COPILOT_HOME=str(home), COPILOT_CACHE_HOME=str(cache))
            added_marketplace = subprocess.run(
                [copilot, "plugin", "marketplace", "add", str(REPO)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=env,
            )
            self.assertEqual(
                added_marketplace.returncode,
                0,
                added_marketplace.stdout + added_marketplace.stderr,
            )
            installed = subprocess.run(
                [copilot, "plugin", "install", "glyphs-mcp@glyphs-mcp"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=env,
            )
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            listed = subprocess.run(
                [copilot, "plugin", "list"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=env,
            )
            self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
            self.assertIn("glyphs-mcp", listed.stdout)
            installed_manifests = []
            for path in home.rglob("plugin.json"):
                try:
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if manifest.get("name") == "glyphs-mcp":
                    installed_manifests.append(manifest)
            self.assertTrue(installed_manifests)
            self.assertTrue(any(item.get("version") == PLUGIN_VERSION for item in installed_manifests))


if __name__ == "__main__":
    unittest.main()
