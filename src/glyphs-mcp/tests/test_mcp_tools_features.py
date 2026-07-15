"""Regression tests for OpenType feature MCP tools."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


def _module_path() -> Path:
    return _resources_dir() / "mcp_tools_features.py"


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class McpToolsFeaturesTests(unittest.TestCase):
    def _load_module(self, font):
        resources = str(_resources_dir())
        if resources not in sys.path:
            sys.path.insert(0, resources)

        glyphs_module = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(fonts=[font], documents=[], currentDocument=None, font=font)
        )
        module_name = "glyphs_mcp_test_mcp_tools_features"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_module,
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module

    def _font(self):
        return types.SimpleNamespace(
            familyName="Feature Sans",
            filepath="/tmp/FeatureSans.glyphs",
            features=[
                types.SimpleNamespace(
                    name="ss01",
                    active=True,
                    automatic=False,
                    code="sub a by a.ss01;\nsub b by b.ss01;",
                    notes="Name: Round alternates",
                    labels=None,
                ),
                types.SimpleNamespace(
                    name="ss02",
                    active=False,
                    automatic=True,
                    code="sub c by c.ss02;",
                    notes="Square alternates",
                    labels=None,
                ),
                types.SimpleNamespace(
                    name="liga",
                    active=True,
                    automatic=False,
                    code="sub f i by fi;",
                    notes="",
                    labels=None,
                ),
            ],
        )

    def test_list_style_sets_filters_inactive_by_default_and_parses_substitutions(self) -> None:
        module = self._load_module(self._font())

        payload = json.loads(asyncio.run(module.list_style_sets(0)))

        self.assertEqual(payload["font"]["familyName"], "Feature Sans")
        self.assertEqual(payload["styleSetCount"], 1)
        style_set = payload["styleSets"][0]
        self.assertEqual(style_set["tag"], "ss01")
        self.assertEqual(style_set["name"], "Round alternates")
        self.assertEqual(style_set["sourceGlyphs"], ["a", "b"])
        self.assertEqual(style_set["replacementGlyphs"], ["a.ss01", "b.ss01"])
        self.assertEqual(style_set["substitutionCount"], 2)
        self.assertIn("showMarkdown", style_set)

    def test_list_style_sets_can_include_inactive_sets(self) -> None:
        module = self._load_module(self._font())

        payload = json.loads(asyncio.run(module.list_style_sets(0, include_inactive=True)))

        self.assertEqual([item["tag"] for item in payload["styleSets"]], ["ss01", "ss02"])
        self.assertFalse(payload["styleSets"][1]["active"])
        self.assertTrue(payload["styleSets"][1]["automatic"])

    def test_list_style_sets_invalid_font_index_is_structured(self) -> None:
        module = self._load_module(self._font())

        payload = json.loads(asyncio.run(module.list_style_sets(9)))

        self.assertIn("error", payload)
        self.assertEqual(payload["fontIndex"], 9)
        self.assertEqual(payload["availableFontCount"], 1)


if __name__ == "__main__":
    unittest.main()
