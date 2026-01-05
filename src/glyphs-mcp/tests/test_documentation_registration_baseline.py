"""Tests for documentation resource registration defaults.

The plugin always registers the documentation directory listing + index file.
Per-page registrations are optional (and disabled by default) to avoid flooding
clients with hundreds of resources.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
import sys
import types
import unittest


def _ensure_fake_fastmcp() -> None:
    """Provide a minimal stub for fastmcp.resources used by the plugin."""

    if "fastmcp.resources" in sys.modules:
        return

    fastmcp_pkg = types.ModuleType("fastmcp")
    resources_mod = types.ModuleType("fastmcp.resources")

    class _DummyResource:  # noqa: D401 - simple placeholder
        def __init__(self, *args, **kwargs) -> None:
            # The docs module relies on a `uri` kwarg; keep it for assertions.
            self.uri = kwargs.get("uri")

    resources_mod.DirectoryResource = _DummyResource
    resources_mod.FileResource = _DummyResource
    fastmcp_pkg.resources = resources_mod

    sys.modules["fastmcp"] = fastmcp_pkg
    sys.modules["fastmcp.resources"] = resources_mod


def _ensure_fake_mcp_tools() -> None:
    """Provide a stub mcp_tools.mcp that records added resources."""

    if "mcp_tools" in sys.modules:
        return

    class _DummyMCP:
        def __init__(self) -> None:
            self.resources = []

        def add_resource(self, resource, *args, **kwargs) -> None:  # pragma: no cover - trivial
            self.resources.append(resource)

        def tool(self, *args, **kwargs):  # pragma: no cover - decorator stub
            def _decorator(func):
                return func

            return _decorator

        def prompt(self, *args, **kwargs):  # pragma: no cover - decorator stub
            def _decorator(func):
                return func

            return _decorator

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


def _load_docs_module() -> ModuleType:
    os.environ["GLYPHS_MCP_SKIP_AUTO_REGISTER"] = "1"
    _ensure_fake_fastmcp()
    _ensure_fake_mcp_tools()

    resources_dir = _resources_dir()
    module_path = resources_dir / "documentation_resources.py"
    sys.path.insert(0, str(resources_dir))
    spec = importlib.util.spec_from_file_location("glyphs_mcp_docs", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


class DocumentationRegistrationBaselineTests(unittest.TestCase):
    def test_index_matches_docs_folder(self) -> None:
        resources_dir = _resources_dir()
        index_path = resources_dir / "MCP Documentation" / "index.json"
        docs_dir = resources_dir / "MCP Documentation" / "docs"

        self.assertTrue(index_path.is_file(), f"Missing index.json at {index_path}")
        self.assertTrue(docs_dir.is_dir(), f"Missing docs directory at {docs_dir}")

        index = json.loads(index_path.read_text(encoding="utf-8"))
        documents = index.get("documents") or []
        self.assertGreater(len(documents), 0, "index.json contains no documents")

        missing = []
        for entry in documents:
            path = entry.get("path")
            if not path:
                continue
            if not (docs_dir / path).is_file():
                missing.append(path)

        self.assertEqual(missing, [], f"Missing docs referenced by index.json: {missing[:10]}")

    def test_register_documentation_resources_default_registers_listing_only(self) -> None:
        module = _load_docs_module()
        mcp_instance = sys.modules["mcp_tools"].mcp

        # Ensure a clean slate regardless of test ordering.
        getattr(mcp_instance, "resources", []).clear()
        os.environ.pop("GLYPHS_MCP_REGISTER_DOC_PAGES", None)
        module.register_documentation_resources()

        uris = [getattr(r, "uri", None) for r in getattr(mcp_instance, "resources", [])]
        uris = [u for u in uris if isinstance(u, str)]

        # Expect: directory listing + index + one resource per doc page.
        self.assertIn(module._DIRECTORY_RESOURCE_URI, uris)
        self.assertIn(module._INDEX_RESOURCE_URI, uris)

        page_uris = [u for u in uris if u.startswith(module._RESOURCE_PREFIX)]
        self.assertEqual(page_uris, [module._INDEX_RESOURCE_URI])

        # No duplicates.
        self.assertEqual(len(uris), len(set(uris)))

    def test_register_documentation_resources_can_enable_per_page(self) -> None:
        module = _load_docs_module()
        mcp_instance = sys.modules["mcp_tools"].mcp

        resources_dir = _resources_dir()
        index_path = resources_dir / "MCP Documentation" / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        documents = index.get("documents") or []
        expected_pages = len([d for d in documents if d.get("path")])

        # Ensure a clean slate regardless of test ordering.
        getattr(mcp_instance, "resources", []).clear()
        os.environ["GLYPHS_MCP_REGISTER_DOC_PAGES"] = "1"
        module.register_documentation_resources()

        uris = [getattr(r, "uri", None) for r in getattr(mcp_instance, "resources", [])]
        uris = [u for u in uris if isinstance(u, str)]

        self.assertIn(module._DIRECTORY_RESOURCE_URI, uris)
        self.assertIn(module._INDEX_RESOURCE_URI, uris)

        page_uris = [
            u
            for u in uris
            if u.startswith(module._RESOURCE_PREFIX) and u != module._INDEX_RESOURCE_URI
        ]
        self.assertEqual(len(page_uris), expected_pages)
        self.assertEqual(len(uris), len(set(uris)))


if __name__ == "__main__":
    unittest.main()
