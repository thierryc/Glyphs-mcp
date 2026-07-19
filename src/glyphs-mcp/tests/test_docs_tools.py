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

    def test_glyphs_4_format_searches_return_official_source_metadata(self) -> None:
        for query in (
            "file format version 4",
            "shape group",
            "higher-order interpolation",
        ):
            payload = json.loads(
                asyncio.run(self.module.docs_search(query=query, max_results=10))
            )
            self.assertTrue(payload["ok"])
            official = [
                result
                for result in payload["results"]
                if result.get("formatVersion") == 4
                and str(result.get("sourceUrl") or "").startswith(
                    "https://github.com/schriftgestalt/GlyphsSDK/"
                )
            ]
            self.assertTrue(official, query)
            self.assertTrue(
                all(result.get("sourceKind") for result in official), query
            )

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
        self.assertIn("sourceKind", payload)
        self.assertIn("formatVersion", payload)
        self.assertIn("sourceUrl", payload)

        # Ensure the returned content matches the file prefix.
        docs_file = _resources_dir() / "MCP Documentation" / "docs" / doc_path
        expected_prefix = docs_file.read_text(encoding="utf-8", errors="replace")[: payload["returnedChars"]]
        self.assertEqual(payload["content"], expected_prefix)

    def test_docs_get_missing_args_errors(self) -> None:
        out = asyncio.run(self.module.docs_get())
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertIn("Missing doc_id or path", payload["error"])

    def test_docs_enable_page_resources_registers_pages(self) -> None:
        out = asyncio.run(self.module.docs_enable_page_resources())
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertGreater(payload["registeredPages"], 0)
        self.assertIn("Per-page resources", payload["note"])

    def test_index_covers_every_bundled_page_and_schemas_are_valid_json(self) -> None:
        bundle_root = _resources_dir() / "MCP Documentation"
        docs_root = bundle_root / "docs"
        index = json.loads((bundle_root / "index.json").read_text(encoding="utf-8"))
        documents = index.get("documents") or []
        indexed_paths = {entry["path"] for entry in documents}
        bundled_paths = {
            path.relative_to(docs_root).as_posix()
            for path in docs_root.rglob("*")
            if path.is_file()
        }

        self.assertEqual(indexed_paths, bundled_paths)
        self.assertEqual(index.get("sourceRevision"), "0f5422db727b78cb42abfb386f33ae0b382b0c4d")
        self.assertTrue(
            all(
                "sourceKind" in entry
                and "formatVersion" in entry
                and str(entry.get("sourceUrl") or "").startswith(
                    "https://github.com/schriftgestalt/GlyphsSDK/"
                )
                for entry in documents
            )
        )

        for schema_name in (
            "glyphs-3.schema.json",
            "glyphs-4.schema.json",
            "fontinfo-3.schema.json",
            "fontinfo-4.schema.json",
        ):
            schema_path = docs_root / "file-format" / "schemas" / schema_name
            parsed = json.loads(schema_path.read_text(encoding="utf-8"))
            self.assertIsInstance(parsed, dict)


if __name__ == "__main__":
    unittest.main()
