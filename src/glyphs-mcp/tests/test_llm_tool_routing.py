"""Deterministic routing and skill-reference contracts for the lean catalog."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RESOURCES = REPO_ROOT / "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Resources"
if str(RESOURCES) not in sys.path:
    sys.path.insert(0, str(RESOURCES))

from tool_catalog import ACTIVE, APP_ONLY, MODEL_AND_APP, TOOL_CATALOG as V1_TOOL_CATALOG

V2_SOURCE = REPO_ROOT / "src/glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.catalog import TOOL_CATALOG as V2_TOOL_CATALOG  # noqa: E402


SKILL_MANIFEST = json.loads(
    (REPO_ROOT / "skills" / "manifest.json").read_text(encoding="utf-8")
)
SKILL_SURFACES = {
    item["name"]: item["surface"] for item in SKILL_MANIFEST["managedSkills"]
}

TOOLISH = re.compile(
    r"^(?:accept|add|apply|clear|copy|create|delete|discard|docs|get|list|"
    r"materialize|open|preview|review|rollback|save|set|show|update|execute|export)_"
)
BACKTICK_IDENTIFIER = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
SKILL_ROUTING_FIELDS = {
    "id",
    "prompt",
    "expected_skill",
    "expected_action",
    "expected_tools",
    "approval",
    "review_required",
    "expected_result",
    "forbidden_skills",
    "forbidden_tools",
}
SKILL_ROUTING_ACTIONS = {
    "execute_read_only",
    "preview_mutation",
    "preview_external_effect",
    "return_snippet",
    "debug_live_script",
    "create_workspace_script",
    "create_workspace_plugin",
    "use_domain_workflow",
    "use_domain_fallback",
    "no_glyphs_skill",
}
SKILL_ROUTING_APPROVALS = {
    "not_required",
    "stop_before_execution",
    "domain_specific",
    "not_applicable",
}


class LLMToolRoutingTests(unittest.TestCase):
    @staticmethod
    def _is_model_tool(name: str) -> bool:
        if name in V2_TOOL_CATALOG:
            return True
        entry = V1_TOOL_CATALOG.get(name)
        return bool(entry and entry.state == ACTIVE and entry.visibility == MODEL_AND_APP)

    def test_routing_fixtures_use_catalog_visibility_and_safe_sequences(self) -> None:
        path = Path(__file__).resolve().parent / "fixtures/llm_tool_routing.json"
        fixtures = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(fixtures), 8)
        for fixture in fixtures:
            with self.subTest(intent=fixture["intent"]):
                route = [fixture["primary"], *fixture.get("followups", [])]
                surface = fixture["surface"]
                for name in route:
                    entry = V1_TOOL_CATALOG[name]
                    self.assertEqual(entry.state, ACTIVE)
                    expected_visibility = APP_ONLY if surface == "app" else MODEL_AND_APP
                    self.assertEqual(entry.visibility, expected_visibility)
                for name in fixture.get("forbidden", []):
                    entry = V1_TOOL_CATALOG.get(name)
                    self.assertTrue(
                        entry is None
                        or entry.state != ACTIVE
                        or (surface == "model" and entry.visibility == APP_ONLY)
                        or name not in route
                    )
                modes = fixture.get("modes")
                if modes:
                    self.assertEqual(len(modes), len(route))
                    if "confirmed" in modes:
                        self.assertIn("dry_run", modes[: modes.index("confirmed")])

    def test_skill_routing_prompts_define_complete_expected_results(self) -> None:
        path = Path(__file__).resolve().parent / "fixtures/llm_skill_routing.json"
        fixtures = json.loads(path.read_text(encoding="utf-8"))
        skill_names = {
            item.parent.name
            for item in (REPO_ROOT / "skills").glob("*/SKILL.md")
        }
        ids = [fixture["id"] for fixture in fixtures]
        prompts = [fixture["prompt"] for fixture in fixtures]

        self.assertGreaterEqual(len(fixtures), 12)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(prompts), len(set(prompts)))
        for fixture in fixtures:
            with self.subTest(case=fixture["id"]):
                self.assertEqual(set(fixture), SKILL_ROUTING_FIELDS)
                self.assertNotIn("$glyphs", fixture["prompt"])
                self.assertGreaterEqual(len(fixture["expected_result"]), 60)
                self.assertIn(fixture["expected_action"], SKILL_ROUTING_ACTIONS)
                self.assertIn(fixture["approval"], SKILL_ROUTING_APPROVALS)
                expected_skill = fixture["expected_skill"]
                if expected_skill is not None:
                    self.assertIn(expected_skill, skill_names)
                    self.assertNotIn(expected_skill, fixture["forbidden_skills"])
                    skill_text = (
                        REPO_ROOT / "skills" / expected_skill / "SKILL.md"
                    ).read_text(encoding="utf-8")
                    for name in fixture["expected_tools"]:
                        self.assertRegex(
                            skill_text,
                            r"`{}(?:`|\()".format(re.escape(name)),
                        )
                for name in fixture["forbidden_skills"]:
                    self.assertIn(name, skill_names)
                self.assertEqual(
                    len(fixture["expected_tools"]),
                    len(set(fixture["expected_tools"])),
                )
                self.assertEqual(
                    len(fixture["forbidden_tools"]),
                    len(set(fixture["forbidden_tools"])),
                )
                self.assertEqual(
                    set(fixture["expected_tools"]) & set(fixture["forbidden_tools"]),
                    set(),
                )
                for name in [*fixture["expected_tools"], *fixture["forbidden_tools"]]:
                    self.assertTrue(self._is_model_tool(name), name)

    def test_skill_routing_prompts_enforce_scripting_and_domain_boundaries(self) -> None:
        path = Path(__file__).resolve().parent / "fixtures/llm_skill_routing.json"
        fixtures = json.loads(path.read_text(encoding="utf-8"))
        by_id = {fixture["id"]: fixture for fixture in fixtures}
        required_cases = {
            "live-read-only-selection-report",
            "live-read-only-app-report",
            "live-mutation-preview",
            "live-external-side-effect-preview",
            "macro-panel-snippet-only",
            "debug-live-read-only-script",
            "reusable-script-menu-file",
            "reporter-plugin-bundle",
            "master-compatibility-domain-route",
            "outline-start-node-domain-route",
            "outline-specific-python-fallback",
            "italic-first-pass-domain-route",
            "spacing-domain-route",
            "context-kerning-domain-route",
            "generic-python-negative-route",
            "color-font-audit-route",
            "unicode-semantics-audit-route",
            "variable-font-audit-route",
            "export-validation-audit-route",
        }
        self.assertEqual(set(by_id), required_cases)

        live_actions = {
            "execute_read_only",
            "preview_mutation",
            "preview_external_effect",
            "return_snippet",
            "debug_live_script",
        }
        for fixture in fixtures:
            action = fixture["expected_action"]
            with self.subTest(case=fixture["id"]):
                if action in live_actions:
                    self.assertEqual(fixture["expected_skill"], "glyphs-mcp-scripting")
                    if action != "return_snippet":
                        self.assertIn("execute_python", fixture["expected_tools"])
                if action in {"preview_mutation", "preview_external_effect"}:
                    self.assertTrue(fixture["review_required"])
                    self.assertEqual(fixture["approval"], "stop_before_execution")
                    expected_token = (
                        "preview id"
                        if action == "preview_mutation"
                        else "approval id"
                    )
                    self.assertIn(expected_token, fixture["expected_result"].lower())
                if action in {"execute_read_only", "debug_live_script"}:
                    self.assertFalse(fixture["review_required"])
                    self.assertEqual(fixture["approval"], "not_required")
                if action == "return_snippet":
                    self.assertFalse(fixture["review_required"])
                    self.assertIn("do not call execute_python", fixture["expected_result"].lower())
                if action in {"create_workspace_script", "create_workspace_plugin"}:
                    self.assertEqual(fixture["expected_skill"], "glyphs-mcp-development")
                    self.assertIsNone(fixture["review_required"])
                    self.assertFalse(
                        {"execute_code", "execute_code_with_context"}
                        & set(fixture["expected_tools"])
                    )
                if action in {"use_domain_workflow", "use_domain_fallback"}:
                    self.assertNotEqual(fixture["expected_skill"], "glyphs-mcp-scripting")
                    self.assertEqual(fixture["approval"], "domain_specific")
                if action == "no_glyphs_skill":
                    self.assertIsNone(fixture["expected_skill"])
                    self.assertEqual(fixture["expected_tools"], [])
                    self.assertIsNone(fixture["review_required"])

        router = (REPO_ROOT / "skills/glyphs/SKILL.md").read_text(encoding="utf-8")
        scripting = (
            REPO_ROOT / "skills/glyphs-mcp-scripting/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Generic Python with no Glyphs app or font target", router)
        self.assertIn("staged_document", scripting)
        self.assertIn("approvalId", scripting)
        self.assertIn("never rerun the code for confirmation", scripting)

        focused_routes = {
            "color-font-audit-route": "glyphs-mcp-color-font",
            "unicode-semantics-audit-route": "glyphs-mcp-unicode-semantics",
            "variable-font-audit-route": "glyphs-mcp-variable-font",
            "export-validation-audit-route": "glyphs-mcp-export-validation",
        }
        for case, skill in focused_routes.items():
            fixture = by_id[case]
            self.assertEqual(fixture["expected_skill"], skill)
            self.assertIn("glyphs-mcp-production-audit", fixture["forbidden_skills"])
            self.assertFalse(fixture["review_required"])
            self.assertIn("save_document", fixture["forbidden_tools"])

        unicode_skill = (
            REPO_ROOT / "skills/glyphs-mcp-unicode-semantics/SKILL.md"
        ).read_text(encoding="utf-8")
        color_skill = (
            REPO_ROOT / "skills/glyphs-mcp-color-font/SKILL.md"
        ).read_text(encoding="utf-8")
        variable_skill = (
            REPO_ROOT / "skills/glyphs-mcp-variable-font/SKILL.md"
        ).read_text(encoding="utf-8")
        export_skill = (
            REPO_ROOT / "skills/glyphs-mcp-export-validation/SKILL.md"
        ).read_text(encoding="utf-8")
        production_skill = (
            REPO_ROOT / "skills/glyphs-mcp-production-audit/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Route icon PUA allocation", unicode_skill)
        self.assertIn("when the font intentionally contains color artwork", (
            REPO_ROOT / "skills/glyphs-mcp-color-font/references/color-font-audit.md"
        ).read_text(encoding="utf-8"))
        self.assertIn("Ordinary multiple-master static families", (
            REPO_ROOT / "skills/glyphs-mcp-variable-font/references/variable-font-audit.md"
        ).read_text(encoding="utf-8"))
        self.assertIn("existing binaries", export_skill)
        self.assertIn("`preview_export`", export_skill)
        self.assertIn("`apply_export` only when", export_skill)
        self.assertIn("color, variable", production_skill)
        self.assertNotIn("SOFT HYPHEN", production_skill)
        self.assertIn("COLR", color_skill)
        self.assertIn("fvar", variable_skill)

    def test_canonical_and_packaged_skills_route_only_to_model_tools(self) -> None:
        roots = [REPO_ROOT / "skills", REPO_ROOT / "plugins/glyphs-mcp/skills"]
        violations = []
        checked = 0
        for root in roots:
            self.assertEqual(
                {path.parent.name for path in root.glob("*/SKILL.md")},
                set(SKILL_SURFACES),
            )
            for path in sorted(root.glob("*/SKILL.md")):
                checked += 1
                text = path.read_text(encoding="utf-8")
                surface = SKILL_SURFACES[path.parent.name]
                for name in BACKTICK_IDENTIFIER.findall(text):
                    if not TOOLISH.match(name):
                        continue
                    available = (
                        name in V2_TOOL_CATALOG
                        if surface == "glyphs-mcp-v2"
                        else self._is_model_tool(name)
                    )
                    if not available:
                        violations.append((str(path.relative_to(REPO_ROOT)), name))
        self.assertEqual(checked, 2 * len(SKILL_SURFACES))
        self.assertEqual(violations, [])

    def test_removed_and_app_only_names_never_appear_in_skills(self) -> None:
        forbidden = {
            name
            for name, entry in V1_TOOL_CATALOG.items()
            if entry.state != ACTIVE or entry.visibility == APP_ONLY
        }
        violations = []
        for root in (REPO_ROOT / "skills", REPO_ROOT / "plugins/glyphs-mcp/skills"):
            for path in sorted(root.glob("*/SKILL.md")):
                names = set(BACKTICK_IDENTIFIER.findall(path.read_text(encoding="utf-8")))
                for name in sorted(names & forbidden):
                    violations.append((str(path.relative_to(REPO_ROOT)), name))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
