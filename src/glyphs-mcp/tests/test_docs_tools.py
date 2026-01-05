"""Tests for the docs_tools search/fetch helpers."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
import sys
import types
import unittest


def _ensure_fake_mcp_tools() -> None:
    if "mcp_tools" in sys.modules:
        return

    class _DummyMCP:
        def tool(self, *args, **kwargs):  # pragma: no cover - decorator stub
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


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


class DocsToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["GLYPHS_MCP_SKIP_AUTO_REGISTER"] = "1"
        _ensure_fake_mcp_tools()
        resources_dir = _resources_dir()
        sys.path.insert(0, str(resources_dir))
        cls.module = _load_module("glyphs_mcp_docs_tools", resources_dir / "docs_tools.py")

    def test_docs_search_finds_matches(self) -> None:
        out = asyncio.run(self.module.docs_search(query="GSApplication", max_results=5))
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertGreater(payload["count"], 0)
        self.assertIn("results", payload)
        self.assertTrue(any("GSApplication" in (r.get("title") or "") for r in payload["results"]))

    def test_docs_get_by_id_returns_content_slice(self) -> None:
        # Use a deterministic entry from the index.
        index_path = _resources_dir() / "MCP Documentation" / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        first = (index.get("documents") or [])[0]
        doc_id = first["id"]
        doc_path = first["path"]

        out = asyncio.run(self.module.docs_get(doc_id=doc_id, offset=0, max_chars=2000))
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["docId"], doc_id)
        self.assertEqual(payload["path"], doc_path)
        self.assertGreater(payload["returnedChars"], 0)
        self.assertIn("content", payload)

        # Ensure the returned content matches the file prefix.
        docs_file = _resources_dir() / "MCP Documentation" / "docs" / doc_path
        expected_prefix = docs_file.read_text(encoding="utf-8", errors="replace")[: payload["returnedChars"]]
        self.assertEqual(payload["content"], expected_prefix)

    def test_docs_get_missing_args_errors(self) -> None:
        out = asyncio.run(self.module.docs_get())
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertIn("Missing doc_id or path", payload["error"])


if __name__ == "__main__":
    unittest.main()

