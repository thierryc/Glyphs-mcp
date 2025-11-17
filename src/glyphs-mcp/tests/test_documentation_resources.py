"""Tests for the documentation_resources metadata helpers."""

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
            pass

    resources_mod.DirectoryResource = _DummyResource
    resources_mod.FileResource = _DummyResource
    fastmcp_pkg.resources = resources_mod

    sys.modules["fastmcp"] = fastmcp_pkg
    sys.modules["fastmcp.resources"] = resources_mod


def _ensure_fake_mcp_tools() -> None:
    if "mcp_tools" in sys.modules:
        return

    class _DummyMCP:
        def add_resource(self, *args, **kwargs) -> None:  # pragma: no cover - noop stub
            pass

        def tool(self, *args, **kwargs):  # pragma: no cover - decorator stub
            def _decorator(func):
                return func

            return _decorator

    stub = types.ModuleType("mcp_tools")
    stub.mcp = _DummyMCP()
    sys.modules["mcp_tools"] = stub


def _load_module() -> ModuleType:
    os.environ["GLYPHS_MCP_SKIP_AUTO_REGISTER"] = "1"
    _ensure_fake_fastmcp()
    _ensure_fake_mcp_tools()
    resources_dir = (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )
    module_path = resources_dir / "documentation_resources.py"
    sys.path.insert(0, str(resources_dir))
    spec = importlib.util.spec_from_file_location("glyphs_mcp_docs", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


class DocumentationResourcesTests(unittest.TestCase):
    def test_extract_doc_entries_prefers_structured_documents(self) -> None:
        module = _load_module()
        index_data = {
            "documents": [
                {
                    "path": "foo.rst",
                    "title": "Foo Title",
                    "summary": "Concise description",
                }
            ]
        }

        entries = module._extract_doc_entries(index_data)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["path"], "foo.rst")
        self.assertEqual(entries[0]["title"], "Foo Title")
        self.assertEqual(entries[0]["summary"], "Concise description")

    def test_extract_doc_entries_handles_legacy_lists(self) -> None:
        module = _load_module()
        index_data = {
            "docnames": ["bar"],
            "titles": {"bar": "Bar Title"},
        }

        entries = module._extract_doc_entries(index_data)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["path"], "bar")
        self.assertEqual(entries[0]["title"], "Bar Title")


if __name__ == "__main__":
    unittest.main()
