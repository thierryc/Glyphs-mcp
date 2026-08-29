"""Contract tests for the shared multi-host agent plugin package."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
PLUGIN = REPO / "plugins" / "glyphs-mcp"
CANONICAL_SKILLS = REPO / "skills"
SKILL_MANIFEST = json.loads(
    (CANONICAL_SKILLS / "manifest.json").read_text(encoding="utf-8")
)
SKILL_NAMES = tuple(item["name"] for item in SKILL_MANIFEST["managedSkills"])
version_tree = ast.parse(
    (REPO / "src/glyphs-mcp-v2/glyphs_mcp_v2/versions.py").read_text(encoding="utf-8")
)
PLUGIN_VERSION = next(
    ast.literal_eval(node.value)
    for node in version_tree.body
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == "SERVER_VERSION" for target in node.targets)
)
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
        for command in (
            "codex plugin marketplace add thierryc/Glyphs-mcp",
            "claude plugin marketplace add thierryc/Glyphs-mcp",
            "cursor-agent plugin marketplace add https://github.com/thierryc/Glyphs-mcp",
            "copilot plugin marketplace add thierryc/Glyphs-mcp",
            "copilot plugin install thierryc/Glyphs-mcp:plugins/glyphs-mcp",
            "/glyphs-mcp:glyphs",
            "/glyphs-mcp/glyphs",
        ):
            self.assertIn(command, combined)
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
        self.assertEqual(len(SKILL_NAMES), 18)
        self.assertEqual(SKILL_MANIFEST["schemaVersion"], 1)
        self.assertEqual(
            {item["surface"] for item in SKILL_MANIFEST["managedSkills"]},
            {"glyphs-mcp-v2"},
        )
        self.assertEqual(
            CANONICAL_SKILLS.joinpath("manifest.json").read_bytes(),
            PLUGIN.joinpath("skills", "manifest.json").read_bytes(),
        )
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
        for public_tool in (
            "read_document",
            "preview_change",
            "apply_change",
            "search_knowledge",
            "execute_python",
        ):
            self.assertIn(public_tool, skill_text)
        for retired_contract in (
            "TOOL_CATALOG",
            "apply_opentype_updates",
            "preview_italic_first_pass_candidate",
            "accept_outline_candidate_session",
            "dry_run=true",
            "confirm=true",
        ):
            self.assertNotIn(retired_contract, skill_text)

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

    def test_canonical_skills_use_stable_urls_for_repository_references(self) -> None:
        for name in SKILL_NAMES:
            text = (CANONICAL_SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("../../", text, name)
            for url in re.findall(r"https://github\.com/thierryc/Glyphs-mcp/[^)\s]+", text):
                self.assertIn("/blob/main/", url, name)

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
        self.assertIn("list_documents", skill_text)
        self.assertIn("read_document", skill_text)
        self.assertIn("search_knowledge", skill_text)
        self.assertIn("preview_change", skill_text)
        self.assertIn("apply_change", skill_text)
        self.assertIn("execute_python", skill_text)
        self.assertIn("glyphs-mcp-spacing", skill_text)
        self.assertIn("glyphs-mcp-kerning", skill_text)
        self.assertIn("glyphs-mcp-development", skill_text)
        self.assertIn("glyphs-mcp-scripting", skill_text)
        self.assertIn("glyphs-mcp-master-compatibility", skill_text)
        self.assertIn("corresponding audit skill", skill_text)
        self.assertIn("Generic Python with no Glyphs app or font target", skill_text)
        self.assertNotIn("list_open_fonts", skill_text)
        self.assertIn('display_name: "Glyphs MCP"', metadata_text)
        self.assertIn("$glyphs", metadata_text)
        self.assertIn("allow_implicit_invocation: false", metadata_text)

    def test_focused_audit_skills_are_discoverable_and_read_only(self) -> None:
        expectations = {
            "glyphs-mcp-color-font": ("COLR", "compiled binary", "read_document"),
            "glyphs-mcp-unicode-semantics": ("U+00AD", "nonzero advance", "read_document"),
            "glyphs-mcp-variable-font": ("fvar", "glyphs-mcp-master-compatibility", "preview_export"),
            "glyphs-mcp-export-validation": ("source readiness", "SKIP", "preview_export"),
        }
        for name, required in expectations.items():
            with self.subTest(skill=name):
                root = CANONICAL_SKILLS / name
                skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
                metadata_text = (root / "agents/openai.yaml").read_text(encoding="utf-8")
                files = {
                    str(path.relative_to(root))
                    for path in root.rglob("*")
                    if path.is_file()
                }
                self.assertEqual(len(files), 3)
                self.assertEqual(len([item for item in files if item.startswith("references/")]), 1)
                self.assertIn("without", skill_text.lower())
                self.assertIn("fingerprint", skill_text)
                self.assertIn("search_knowledge", skill_text)
                self.assertIn(f"${name}", metadata_text)
                self.assertIn("allow_implicit_invocation: true", metadata_text)
                for value in required:
                    self.assertIn(value, skill_text)

    def test_development_skill_is_workspace_first_and_documented(self) -> None:
        root = CANONICAL_SKILLS / "glyphs-mcp-development"
        skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
        metadata_text = (root / "agents" / "openai.yaml").read_text(encoding="utf-8")

        self.assertIn("search_knowledge", skill_text)
        self.assertIn("get_knowledge", skill_text)
        self.assertIn("pinned local SDK", skill_text)
        self.assertIn("Create workspace artifacts", skill_text)
        self.assertIn("Create files in the workspace", skill_text)
        self.assertIn("Never install, reload, restart Glyphs, run the artifact", skill_text)
        self.assertTrue((root / "scripts" / "scaffold.py").is_file())
        self.assertTrue((root / "assets" / "GlyphsSDK-LICENSE.txt").is_file())
        self.assertIn('display_name: "Glyphs MCP Development"', metadata_text)
        self.assertIn("$glyphs-mcp-development", metadata_text)
        self.assertIn("allow_implicit_invocation: true", metadata_text)

    def test_scripting_skill_gates_live_code_and_preserves_domain_routing(self) -> None:
        root = CANONICAL_SKILLS / "glyphs-mcp-scripting"
        files = {
            str(path.relative_to(root))
            for path in root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(files, {"SKILL.md", "agents/openai.yaml"})

        skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
        metadata_text = (root / "agents" / "openai.yaml").read_text(encoding="utf-8")
        normalized = " ".join(skill_text.split())
        self.assertLessEqual(len(skill_text.splitlines()), 110)
        for required in (
            "execute_python",
            "read_only",
            "staged_document",
            "live_open_world",
            "search_knowledge",
            "get_knowledge",
            "get_runtime_status",
            "repair_runtime",
            "approvalId",
            "apply_change",
            "open_document_view",
            "save_document",
        ):
            self.assertIn(required, skill_text)
        # The scripting skill is a v2-surface skill. It must not route agents to
        # documentation tools that are absent from the v2 catalog.
        self.assertNotIn("docs_search", skill_text)
        self.assertNotIn("docs_get", skill_text)
        self.assertIn("Never call `exit()`, `quit()`, or `sys.exit()`", normalized)
        self.assertIn("never rerun the code for confirmation", skill_text)
        self.assertIn("permanent architectural capability", skill_text)
        self.assertNotIn("rollback_python_execution", skill_text)
        self.assertNotIn("confirm=true", skill_text)
        self.assertIn('display_name: "Glyphs MCP Scripting"', metadata_text)
        self.assertIn('short_description: "Run and recover staged or open-world Glyphs Python."', metadata_text)
        self.assertIn("$glyphs-mcp-scripting", metadata_text)
        self.assertIn("allow_implicit_invocation: true", metadata_text)

    def test_coding_prompt_routing_contract(self) -> None:
        router = (CANONICAL_SKILLS / "glyphs" / "SKILL.md").read_text(encoding="utf-8")
        scripting = (CANONICAL_SKILLS / "glyphs-mcp-scripting" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        development = (CANONICAL_SKILLS / "glyphs-mcp-development" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        outlines = (CANONICAL_SKILLS / "glyphs-mcp-outlines-docs" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        normalized_router = " ".join(router.split())
        normalized_scripting = " ".join(scripting.split())
        normalized_development = " ".join(development.split())

        # Python is a permanent fallback with distinct inspection, staged, and
        # open-world semantics.
        self.assertIn("permanent `execute_python` fallback", normalized_router)
        self.assertIn("`read_only`: bounded inspection", normalized_scripting)
        self.assertIn("immutable `previewId`", normalized_scripting)
        self.assertIn("never rerun the code for confirmation", normalized_scripting)
        self.assertIn("exact `approvalId`", normalized_scripting)
        # Reusable scripts and every supported plug-in type remain development artifacts.
        self.assertIn("Reusable scripts and plug-ins", normalized_router)
        self.assertIn("script versus general, reporter, filter, palette", normalized_development)
        self.assertIn("reporter", development)
        # Outline fallback stays with the existing domain skill.
        self.assertIn('execute_python(mode="read_only")', outlines)
        self.assertIn('execute_python(mode="staged_document")', outlines)
        # Generic Python must not claim a Glyphs workflow.
        self.assertIn("Generic Python with no Glyphs app or font target", router)

    def test_icon_font_skill_stays_narrow_and_domain_specific(self) -> None:
        root = CANONICAL_SKILLS / "glyphs-mcp-icon-font"
        files = {
            str(path.relative_to(root))
            for path in root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(files, {"SKILL.md", "agents/openai.yaml"})

        text = (root / "SKILL.md").read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        self.assertLessEqual(len(text.splitlines()), 55)
        self.assertIn("encoding stability, not icon drawing", normalized)
        self.assertIn("require the previous mapping before allocating", normalized)
        self.assertIn("read_document", text)
        self.assertIn("search_knowledge", text)
        self.assertIn("preview_change", text)
        self.assertIn("apply_change", text)
        self.assertIn('execute_python(mode="read_only")', text)
        self.assertNotIn("list_glyphs", text)
        self.assertNotIn("apply_glyph_updates", text)

    def test_italic_first_pass_skill_exposes_guarded_slant_construction(self) -> None:
        text = (CANONICAL_SKILLS / "glyphs-mcp-italic-first-pass" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(text.split())

        self.assertIn("A mechanical construction is a draft", text)
        self.assertIn("search_knowledge", text)
        self.assertIn("read_document", text)
        self.assertIn("`slnt`", text)
        self.assertIn("`post.italicAngle`", text)
        self.assertIn("opposite sign", text)
        self.assertIn('execute_python(mode="staged_document")', text)
        self.assertIn("apply_change", text)
        self.assertIn("Never call `save_document` automatically", normalized)

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
