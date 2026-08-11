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

from tool_catalog import ACTIVE, APP_ONLY, MODEL_AND_APP, TOOL_CATALOG


TOOLISH = re.compile(
    r"^(?:accept|add|apply|clear|copy|create|delete|discard|docs|get|list|"
    r"materialize|open|preview|review|save|set|show|update|execute|export)_"
)
BACKTICK_IDENTIFIER = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


class LLMToolRoutingTests(unittest.TestCase):
    def test_routing_fixtures_use_catalog_visibility_and_safe_sequences(self) -> None:
        path = Path(__file__).resolve().parent / "fixtures/llm_tool_routing.json"
        fixtures = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(fixtures), 8)
        for fixture in fixtures:
            with self.subTest(intent=fixture["intent"]):
                route = [fixture["primary"], *fixture.get("followups", [])]
                surface = fixture["surface"]
                for name in route:
                    entry = TOOL_CATALOG[name]
                    self.assertEqual(entry.state, ACTIVE)
                    expected_visibility = APP_ONLY if surface == "app" else MODEL_AND_APP
                    self.assertEqual(entry.visibility, expected_visibility)
                for name in fixture.get("forbidden", []):
                    entry = TOOL_CATALOG.get(name)
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

    def test_canonical_and_packaged_skills_route_only_to_model_tools(self) -> None:
        roots = [REPO_ROOT / "skills", REPO_ROOT / "plugins/glyphs-mcp/skills"]
        violations = []
        checked = 0
        for root in roots:
            for path in sorted(root.glob("*/SKILL.md")):
                checked += 1
                text = path.read_text(encoding="utf-8")
                for name in BACKTICK_IDENTIFIER.findall(text):
                    if not TOOLISH.match(name):
                        continue
                    entry = TOOL_CATALOG.get(name)
                    if entry is None or entry.state != ACTIVE or entry.visibility != MODEL_AND_APP:
                        violations.append((str(path.relative_to(REPO_ROOT)), name))
        self.assertGreaterEqual(checked, 18)
        self.assertEqual(violations, [])

    def test_removed_and_app_only_names_never_appear_in_skills(self) -> None:
        forbidden = {
            name
            for name, entry in TOOL_CATALOG.items()
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
