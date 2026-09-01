"""Keep the authored expertise layer aligned with the hard-reset surface."""

from __future__ import annotations

import inspect
import json
import re
import subprocess
import sys
import typing
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.transport.fastmcp import ToolHandlers  # noqa: E402
from glyphs_mcp_v2.versions import SERVER_VERSION  # noqa: E402


RETIRED_TOOLS = {
    "list_open_fonts",
    "get_document_status",
    "list_glyphs",
    "list_masters",
    "list_layers",
    "list_instances",
    "list_kerning_pairs",
    "list_opentype_items",
    "review_spacing",
    "apply_spacing",
    "review_export",
    "export_source_bundle",
    "compile_opentype_features",
    "rollback_python_execution",
    "open_edit_tab",
    "get_scripting_runtime_status",
    "repair_scripting_runtime",
    "apply_glyph_updates",
    "apply_master_updates",
    "apply_layer_updates",
    "apply_instance_updates",
    "apply_kerning_updates",
    "apply_opentype_updates",
    "apply_metrics_updates",
    "apply_anchor_updates",
    "apply_compatibility_updates",
}


class V2SkillContractTests(unittest.TestCase):
    manifest = json.loads(
        (REPO / "skills" / "manifest.json").read_text(encoding="utf-8")
    )
    skills = tuple(item["name"] for item in manifest["managedSkills"])

    def _text(self, skill: str, *, packaged: bool = False) -> str:
        root = (
            REPO / "plugins" / "glyphs-mcp" / "skills"
            if packaged
            else REPO / "skills"
        )
        return (root / skill / "SKILL.md").read_text(encoding="utf-8")

    def _tree_text(self, skill: str) -> str:
        root = REPO / "skills" / skill
        return "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(root.rglob("*"))
            if path.is_file() and path.suffix in {".json", ".md", ".yaml", ".yml"}
        )

    def test_authored_skills_are_the_only_packaged_source(self) -> None:
        self.assertEqual(self.manifest["schemaVersion"], 1)
        self.assertEqual(len(self.skills), len(set(self.skills)))
        for skill in self.skills:
            with self.subTest(skill=skill):
                canonical = self._text(skill)
                self.assertIn("metadata:\n  surface: glyphs-mcp-v2", canonical)
                self.assertIn("`get_server_info`", canonical)
                self.assertIn("`data.apiMajor == 2`", canonical)
                self.assertEqual(canonical, self._text(skill, packaged=True))

        checked = subprocess.run(
            ["scripts/sync_codex_plugin_skills.sh", "--check"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_no_skill_or_supporting_reference_restores_retired_tools(self) -> None:
        violations: list[tuple[str, str]] = []
        for skill in self.skills:
            text = self._tree_text(skill)
            for tool in RETIRED_TOOLS:
                if re.search(r"\b{}\b".format(re.escape(tool)), text):
                    violations.append((skill, tool))
        self.assertEqual(violations, [])

    def test_geometry_skills_require_exact_fractional_geometry(self) -> None:
        precision_skills = {
            "glyphs",
            "glyphs-mcp-development",
            "glyphs-mcp-scripting",
            "glyphs-mcp-spacing",
            "glyphs-mcp-italic-first-pass",
            "glyphs-mcp-outlines-docs",
            "glyphs-mcp-master-compatibility",
        }
        for skill in precision_skills:
            text = self._text(skill).lower()
            normalized = " ".join(text.replace("automatic-", "automatic ").split())
            with self.subTest(skill=skill):
                self.assertIn("fraction", normalized)
                self.assertIn("grid", normalized)
                self.assertIn("automatic alignment", normalized)

        violations: list[tuple[str, str]] = []
        quantizer_grid = re.compile(
            r"`?quantizer`?\s*=\s*(?:[\"'])?grid\b", re.IGNORECASE
        )
        positive_snapping = re.compile(
            r"\b(?:choose|use|apply|prefer|require)\b[^.\n]{0,80}"
            r"\b(?:grid[- ](?:snap|quant)|snap[^.\n]{0,30}\bgrid)"
        )
        for skill in self.skills:
            text = self._tree_text(skill)
            if quantizer_grid.search(text) or positive_snapping.search(text):
                violations.append((skill, "conflicting snapping directive"))
        self.assertEqual(violations, [])

    def test_toolish_skill_references_exist_in_the_catalog(self) -> None:
        toolish = re.compile(
            r"^(?:apply|evaluate|execute|get|list|open|preview|repair|revert|save|search)_"
        )
        violations: list[tuple[str, str]] = []
        referenced: set[str] = set()
        for skill in self.skills:
            names = set(re.findall(r"`([a-z][a-z0-9_]+)`", self._text(skill)))
            referenced.update(names)
            violations.extend(
                (skill, name)
                for name in names
                if toolish.match(name) and name not in TOOL_CATALOG
            )
        self.assertEqual(violations, [])
        self.assertLessEqual(
            {
                "read_document",
                "search_knowledge",
                "get_knowledge",
                "preview_change",
                "apply_change",
                "execute_python",
                "revert_change",
                "save_document",
            },
            referenced,
        )

    def test_domain_skills_encode_knowledge_generic_and_python_routing(self) -> None:
        mutation_skills = {
            "glyphs",
            "glyphs-mcp-icon-font",
            "glyphs-mcp-italic-first-pass",
            "glyphs-mcp-kerning",
            "glyphs-mcp-litsquare-metadata",
            "glyphs-mcp-master-compatibility",
            "glyphs-mcp-opentype-features",
            "glyphs-mcp-outlines-docs",
            "glyphs-mcp-spacing",
        }
        for skill in mutation_skills:
            text = self._text(skill)
            with self.subTest(skill=skill):
                self.assertIn("`search_knowledge`", text)
                self.assertIn("`read_document`", text)
                self.assertIn("`apply_change`", text)
                self.assertIn("`execute_python", text)

        scripting = self._text("glyphs-mcp-scripting")
        for mode in ("read_only", "staged_document", "live_open_world"):
            self.assertIn("`{}`".format(mode), scripting)
        self.assertIn("never rerun the code", scripting)
        self.assertIn("data.registries.pythonExecution.detachedNamespace", scripting)
        self.assertIn("`staged_assertion_failed`", scripting)

        spacing = self._text("glyphs-mcp-spacing")
        self.assertIn("`inheritance.metrics` separates configured keys", spacing)
        self.assertIn("change or remove the key", spacing)
        self.assertIn("never make it", spacing)

    def test_python_and_generic_transport_have_no_legacy_arguments(self) -> None:
        execute = inspect.signature(ToolHandlers.execute_python).parameters
        preview = inspect.signature(ToolHandlers.preview_change).parameters
        self.assertNotIn("snippet_only", execute)
        self.assertNotIn("reviewId", execute)
        self.assertNotIn("dry_run", preview)
        mode_annotation = typing.get_type_hints(
            ToolHandlers.execute_python, include_extras=True
        )["mode"]
        self.assertEqual(
            {"read_only", "staged_document", "live_open_world"},
            set(typing.get_args(mode_annotation)),
        )

    def test_plugin_manifest_and_runtime_version_agree(self) -> None:
        manifest = json.loads(
            (
                REPO
                / "plugins"
                / "glyphs-mcp"
                / ".codex-plugin"
                / "plugin.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["version"], SERVER_VERSION)


if __name__ == "__main__":
    unittest.main()
