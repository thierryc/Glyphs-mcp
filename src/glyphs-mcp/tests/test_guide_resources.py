"""Tests for the guide_resources registration helper."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType
import sys
import types
import unittest


def _ensure_fake_fastmcp() -> None:
    if "fastmcp.resources" in sys.modules:
        return

    fastmcp_pkg = types.ModuleType("fastmcp")
    resources_mod = types.ModuleType("fastmcp.resources")

    class _DummyResource:  # noqa: D401 - simple placeholder
        def __init__(self, *args, **kwargs) -> None:
            self.uri = kwargs.get("uri")

    resources_mod.FileResource = _DummyResource
    resources_mod.DirectoryResource = _DummyResource
    fastmcp_pkg.resources = resources_mod

    sys.modules["fastmcp"] = fastmcp_pkg
    sys.modules["fastmcp.resources"] = resources_mod


def _ensure_fake_mcp_tools() -> None:
    if "mcp_tools" in sys.modules:
        return

    class _DummyMCP:
        def __init__(self) -> None:
            self.resources = []

        def add_resource(self, resource, *args, **kwargs) -> None:  # pragma: no cover
            self.resources.append(resource)

    stub = types.ModuleType("mcp_tools")
    stub.mcp = _DummyMCP()
    sys.modules["mcp_tools"] = stub


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


class GuideResourcesTests(unittest.TestCase):
    def test_guide_file_exists(self) -> None:
        guide_path = _resources_dir() / "MCP_GUIDE.md"
        self.assertTrue(guide_path.is_file(), f"Missing guide file at {guide_path}")
        self.assertGreater(len(guide_path.read_text(encoding="utf-8").strip()), 0)

    def test_register_guide_resource_registers_uri(self) -> None:
        os.environ["GLYPHS_MCP_SKIP_AUTO_REGISTER"] = "1"
        _ensure_fake_fastmcp()
        _ensure_fake_mcp_tools()

        resources_dir = _resources_dir()
        sys.path.insert(0, str(resources_dir))

        module_path = resources_dir / "guide_resources.py"
        module = _load_module("glyphs_mcp_guide_resources", module_path)

        mcp_instance = sys.modules["mcp_tools"].mcp
        getattr(mcp_instance, "resources", []).clear()

        module.register_guide_resource()

        uris = [getattr(r, "uri", None) for r in getattr(mcp_instance, "resources", [])]
        uris = [u for u in uris if isinstance(u, str)]

        self.assertIn(module._GUIDE_RESOURCE_URI, uris)
        self.assertEqual(len(uris), len(set(uris)))


if __name__ == "__main__":
    unittest.main()
