"""Authoritative catalog, registration, visibility, and budget tests."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _resources() -> Path:
    return Path(__file__).resolve().parent.parent / "Glyphs MCP.glyphsPlugin" / "Contents" / "Resources"


def _load(name: str):
    path = _resources() / (name + ".py")
    spec = importlib.util.spec_from_file_location("glyphs_mcp_test_" + name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ToolCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources()))
        cls.catalog = _load("tool_catalog")
        cls.schemas = _load("tool_result_schemas")

    def test_exact_active_model_app_and_removed_counts(self) -> None:
        self.assertEqual(len(self.catalog.TOOL_CATALOG), 86)
        self.assertEqual(len(self.catalog.active_entries()), 78)
        self.assertEqual(len(self.catalog.model_entries()), 67)
        self.assertEqual(len(self.catalog.app_only_entries()), 11)
        self.assertEqual(
            {entry.name for entry in self.catalog.app_only_entries()},
            {
                "show_glyphs_status",
                "show_font_feedback",
                "show_glyph_feedback",
                "show_opentype_features",
                "preview_spacing_feedback",
                "preview_kerning_feedback",
                "preview_handle_smoothing_feedback",
                "apply_feedback_plan",
                "open_feedback_target",
                "get_curve_review_overlay_state",
                "generate_kerning_tab",
            },
        )
        self.assertEqual(
            {entry.name for entry in self.catalog.TOOL_CATALOG.values() if entry.state == "removed"},
            {
                "render_glyph_review_image",
                "docs_enable_page_resources",
                "measure_stem_ratio",
                "review_collinear_handles",
                "review_italic_first_pass",
                "apply_italic_first_pass",
                "review_compensated_tuning",
                "apply_compensated_tuning",
            },
        )

    def test_every_catalog_entry_is_concise_typed_and_annotated(self) -> None:
        for entry in self.catalog.TOOL_CATALOG.values():
            with self.subTest(tool=entry.name):
                self.assertLessEqual(len(entry.title), 60)
                self.assertLessEqual(len(entry.description), 220)
                self.assertTrue(entry.description.endswith("."))
                self.assertIn(entry.visibility, {"model+app", "app-only"})
                self.assertIn(entry.state, {"active", "removed"})
                self.assertTrue(entry.category)
                self.assertTrue(entry.tags)
                self.assertEqual(
                    set(entry.annotations),
                    {"title", "readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"},
                )
                self.assertEqual(entry.annotations["title"], entry.title)
                for hint in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
                    self.assertIs(type(entry.annotations[hint]), bool)
                if entry.output_schema:
                    self.assertIsNotNone(self.schemas.schema_for(entry.output_schema))

    def test_removed_replacements_are_active_and_never_registered(self) -> None:
        active = {entry.name for entry in self.catalog.active_entries()}
        for entry in self.catalog.TOOL_CATALOG.values():
            if entry.state == "removed":
                self.assertIn(entry.replacement, active)

        decorated = self._decorated_names()
        self.assertEqual(decorated, active)
        self.assertTrue(decorated.isdisjoint(
            {entry.name for entry in self.catalog.TOOL_CATALOG.values() if entry.state == "removed"}
        ))

    def test_tool_modules_use_only_catalog_registration_helper(self) -> None:
        violations = []
        for path in _resources().glob("*.py"):
            if path.name == "tool_registration.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "mcp" and node.func.attr == "tool":
                        violations.append(path.name)
        self.assertEqual(violations, [])

    def test_catalog_metadata_budget_is_bounded(self) -> None:
        payload = []
        for entry in self.catalog.model_entries():
            payload.append(
                {
                    "name": entry.name,
                    "title": entry.title,
                    "description": entry.description,
                    "tags": entry.tags,
                    "annotations": entry.annotations,
                    "outputSchema": self.schemas.schema_for(entry.output_schema),
                }
            )
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertLess(len(encoded), 160 * 1024)

    def test_fastmcp_registration_uses_catalog_metadata_and_structured_result(self) -> None:
        isolated_names = {"tool_registration", "tool_result_schemas"}
        saved_modules = {
            name: module
            for name, module in sys.modules.items()
            if name in isolated_names or name == "fastmcp" or name.startswith("fastmcp.")
        }
        for name in saved_modules:
            sys.modules.pop(name, None)
        try:
            from fastmcp import FastMCP

            server = FastMCP("catalog registration test")
            spec = importlib.util.spec_from_file_location(
                "glyphs_mcp_test_tool_registration", _resources() / "tool_registration.py"
            )
            assert spec is not None and spec.loader is not None
            registration = importlib.util.module_from_spec(spec)
            with mock.patch.dict(sys.modules, {"mcp_runtime": types.SimpleNamespace(mcp=server)}):
                spec.loader.exec_module(registration)

            def broken_observer(**_kwargs):
                raise RuntimeError("observer failed")

            registration.register_tool_result_observer(broken_observer)

            @registration.glyphs_tool()
            async def review_curve_quality(glyph_name: str = "a"):
                return json.dumps({"ok": True, "target": {"glyphName": "a"}, "summary": {"count": 1}})

            tool = asyncio.run(server.get_tools())["review_curve_quality"]
            entry = self.catalog.TOOL_CATALOG["review_curve_quality"]
            self.assertEqual(tool.title, entry.title)
            self.assertEqual(tool.description, entry.description)
            self.assertEqual(tool.tags, set(entry.tags))
            self.assertEqual(tool.meta["ui"]["visibility"], ["model", "app"])
            self.assertIsNotNone(tool.output_schema)
            with mock.patch.object(registration.logger, "exception") as log_exception:
                result = asyncio.run(tool.run({}))
            log_exception.assert_called_once()
            self.assertEqual(result.structured_content["resultSchemaVersion"], 1)
            self.assertEqual(result.structured_content["tool"], "review_curve_quality")
            self.assertIn('"ok": true', result.content[0].text.lower())
        finally:
            for name in list(sys.modules):
                if name == "fastmcp" or name.startswith("fastmcp."):
                    sys.modules.pop(name, None)
            sys.modules.update(saved_modules)

    @staticmethod
    def _decorated_names():
        names = set()
        for path in _resources().glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
                        if decorator.func.id == "glyphs_tool":
                            names.add(node.name)
        return names


if __name__ == "__main__":
    unittest.main()
