"""Tests for the kerning_resources registration helper."""

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

    resources_mod.DirectoryResource = _DummyResource
    resources_mod.FileResource = _DummyResource
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
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


class KerningResourcesTests(unittest.TestCase):
    def test_register_kerning_resources_registers_expected_uris(self) -> None:
        os.environ["GLYPHS_MCP_SKIP_AUTO_REGISTER"] = "1"
        _ensure_fake_fastmcp()
        _ensure_fake_mcp_tools()

        resources_dir = _resources_dir()
        sys.path.insert(0, str(resources_dir))

        module_path = resources_dir / "kerning_resources.py"
        module = _load_module("glyphs_mcp_kerning_resources", module_path)

        mcp_instance = sys.modules["mcp_tools"].mcp
        getattr(mcp_instance, "resources", []).clear()

        module.register_kerning_resources()

        uris = [getattr(r, "uri", None) for r in getattr(mcp_instance, "resources", [])]
        uris = [u for u in uris if isinstance(u, str)]

        self.assertIn("glyphs://glyphs-mcp/kerning", uris)
        self.assertIn("glyphs://glyphs-mcp/kerning/andre-fuchs/relevant_pairs.v1.json", uris)
        self.assertIn("glyphs://glyphs-mcp/kerning/andre-fuchs/ATTRIBUTION.md", uris)


if __name__ == "__main__":
    unittest.main()

