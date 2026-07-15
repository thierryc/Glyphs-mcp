"""Regression tests for server health/runtime identity MCP tools."""

from __future__ import annotations

import asyncio
import importlib.util
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
        / "mcp_tools_server.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class McpToolsServerTests(unittest.TestCase):
    def _load_module(self):
        font = types.SimpleNamespace(familyName="Runtime Test", filepath="/tmp/Runtime.glyphs")
        glyphs = types.SimpleNamespace(versionNumber=4.0, fonts=[font])
        helpers = types.SimpleNamespace(
            _font_summary=lambda font, i=None: {
                "fontIndex": i,
                "familyName": getattr(font, "familyName", ""),
                "filePath": getattr(font, "filepath", None),
            },
            _open_fonts_from_glyphs=lambda _glyphs: list(getattr(_glyphs, "fonts", [])),
            _safe_json=lambda payload: json.dumps(payload),
        )
        versioning = types.SimpleNamespace(
            get_runtime_info=lambda: {
                "version": "9.8.7",
                "runtimeId": "9.8.7+abcdef123456",
                "codeHash": "abcdef123456" * 5 + "abcd",
                "resourcesPath": "/tmp/resources",
                "infoPlistPath": "/tmp/Info.plist",
                "pythonVersion": "3.14.0",
            }
        )

        module_name = "glyphs_mcp_test_mcp_tools_server"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": types.SimpleNamespace(Glyphs=glyphs),
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": helpers,
                "versioning": versioning,
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module

    def test_get_server_info_reports_runtime_identity_and_font_count(self) -> None:
        module = self._load_module()

        payload = json.loads(asyncio.run(module.get_server_info()))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["version"], "9.8.7")
        self.assertEqual(payload["runtimeId"], "9.8.7+abcdef123456")
        self.assertEqual(payload["glyphsVersion"], 4.0)
        self.assertEqual(payload["openFontCount"], 1)
        self.assertEqual(payload["availableFonts"][0]["familyName"], "Runtime Test")
