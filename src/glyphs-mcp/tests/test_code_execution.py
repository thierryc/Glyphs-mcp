"""Regression tests for execute_code helpers."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _module_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
        / "code_execution.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class CodeExecutionTests(unittest.TestCase):
    def _load_module(self):
        fake_layer = types.SimpleNamespace(name="Regular")
        fake_master = types.SimpleNamespace(id="m1")
        fake_glyph = types.SimpleNamespace(name="A", layers={"m1": fake_layer})
        fake_font = types.SimpleNamespace(
            familyName="Unit Test Sans",
            glyphs={"A": fake_glyph},
            selectedFontMaster=fake_master,
            masters=[fake_master],
        )
        glyphs_app = types.ModuleType("GlyphsApp")
        glyphs_app.Glyphs = types.SimpleNamespace(fonts=[fake_font])
        glyphs_app.GSGlyph = type("GSGlyph", (), {})
        glyphs_app.GSLayer = type("GSLayer", (), {})
        glyphs_app.GSPath = type("GSPath", (), {})
        glyphs_app.GSNode = type("GSNode", (), {})
        glyphs_app.GSComponent = type("GSComponent", (), {})
        glyphs_app.GSAnchor = type("GSAnchor", (), {})

        module_name = "glyphs_mcp_test_code_execution"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_app,
                "mcp_tools": types.SimpleNamespace(mcp=_FakeMCP()),
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module

    def test_execute_code_terminal_expression_runs_once(self) -> None:
        module = self._load_module()
        out = asyncio.run(module.execute_code("x = []\n(x.append(1), len(x))[1]"))
        payload = json.loads(out)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["result"], "1")

    def test_execute_code_with_context_terminal_expression_runs_once(self) -> None:
        module = self._load_module()
        out = asyncio.run(module.execute_code_with_context("x = []\n(x.append(glyph.name), len(x))[1]", glyph_name="A"))
        payload = json.loads(out)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["result"], "1")
        self.assertEqual(payload["context"]["font"], "Unit Test Sans")
        self.assertEqual(payload["context"]["glyph"], "A")
        self.assertEqual(payload["context"]["layer"], "Regular")

    def test_execute_code_signatures_no_longer_expose_timeout(self) -> None:
        module = self._load_module()
        self.assertNotIn("timeout", inspect.signature(module.execute_code).parameters)
        self.assertNotIn("timeout", inspect.signature(module.execute_code_with_context).parameters)


if __name__ == "__main__":
    unittest.main()
