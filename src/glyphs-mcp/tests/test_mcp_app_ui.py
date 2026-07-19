"""Tests for the bundled MCP App feedback resource and static UI contract."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import shutil
import subprocess
import json
import sys
import types
import unittest
from unittest import mock


def _resources_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "Glyphs MCP.glyphsPlugin" / "Contents" / "Resources"


class _FakeMCP:
    def __init__(self):
        self.resources = []

    def add_resource(self, resource):
        self.resources.append(resource)
        return resource


class _TextResourceStub:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    async def read(self):
        return self.text


class MCPAppResourceTests(unittest.TestCase):
    def _load_module(self):
        fake_mcp = _FakeMCP()
        module_name = "glyphs_mcp_test_mcp_app_ui"
        spec = importlib.util.spec_from_file_location(module_name, _resources_dir() / "mcp_app_ui.py")
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        fastmcp_resources = types.ModuleType("fastmcp.resources")
        fastmcp_resources.TextResource = _TextResourceStub
        with mock.patch.dict(
            sys.modules,
            {
                "fastmcp.resources": fastmcp_resources,
                "mcp_runtime": types.SimpleNamespace(mcp=fake_mcp),
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, fake_mcp

    def test_registers_exact_versioned_mcp_app_resource_once(self) -> None:
        module, fake_mcp = self._load_module()

        self.assertEqual(len(fake_mcp.resources), 1)
        resource = fake_mcp.resources[0]
        self.assertEqual(str(resource.uri), "ui://glyphs-mcp/feedback-v1.html")
        self.assertEqual(resource.mime_type, "text/html;profile=mcp-app")
        self.assertEqual(resource.meta["ui"]["csp"]["connectDomains"], [])
        self.assertEqual(resource.meta["ui"]["csp"]["resourceDomains"], [])
        self.assertFalse(module.register_feedback_resource())
        self.assertEqual(len(fake_mcp.resources), 1)

    def test_fastmcp_212_accepts_the_profile_through_the_narrow_subclass(self) -> None:
        code = """
import importlib.util, json, sys, types
from pathlib import Path

resources = Path(sys.argv[1])
captured = []
runtime = types.SimpleNamespace(mcp=types.SimpleNamespace(add_resource=lambda resource: captured.append(resource)))
sys.modules['mcp_runtime'] = runtime
spec = importlib.util.spec_from_file_location('isolated_mcp_app_ui', resources / 'mcp_app_ui.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps({'uri': str(captured[0].uri), 'mime': captured[0].mime_type, 'count': len(captured)}))
"""
        completed = subprocess.run(
            [sys.executable, "-c", code, str(_resources_dir())],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload, {"uri": "ui://glyphs-mcp/feedback-v1.html", "mime": "text/html;profile=mcp-app", "count": 1})

    def test_resource_read_returns_the_bundled_self_contained_html(self) -> None:
        _module, fake_mcp = self._load_module()

        html = asyncio.run(fake_mcp.resources[0].read())

        self.assertIn("ui/initialize", html)
        self.assertIn("ui/notifications/tool-result", html)
        self.assertIn("ui/notifications/tool-input", html)
        self.assertIn("ui/notifications/host-context-changed", html)
        self.assertIn("tools/call", html)
        self.assertIn("bridge_unavailable", html)
        self.assertIn("5000", html)
        self.assertIn("aria-live", html)
        self.assertIn("Show more", html)

    def test_html_has_no_editor_or_external_dependency_surface(self) -> None:
        html = (_resources_dir() / "feedback_ui_v1.html").read_text(encoding="utf-8")
        lower = html.lower()

        for forbidden in (
            "<input",
            "<textarea",
            "<select",
            "contenteditable",
            "<iframe",
            "<script src=",
            "<link rel=",
            "http://",
            "https://",
            "role=\"tab\"",
            "role='tab'",
        ):
            self.assertNotIn(forbidden, lower)
        self.assertNotIn("overflow-y: auto", lower)
        self.assertNotIn("overflow-y:auto", lower)
        self.assertIn("slice(0, 2)", html)

    def test_mock_mcp_apps_host_exercises_bridge_actions_theme_and_errors(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is unavailable for the MCP Apps bridge fixture")
        fixture = Path(__file__).resolve().parent / "fixtures" / "mock_mcp_apps_host.js"
        completed = subprocess.run(
            [node, str(fixture), str(_resources_dir() / "feedback_ui_v1.html")],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
