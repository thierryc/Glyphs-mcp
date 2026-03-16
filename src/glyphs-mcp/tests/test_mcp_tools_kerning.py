"""Regression tests for MCP kerning tools."""

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
        / "mcp_tools_kerning.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _GlyphCollection:
    def __init__(self, glyphs) -> None:
        self._glyphs = {glyph.name: glyph for glyph in glyphs}

    def __iter__(self):
        return iter(self._glyphs.values())

    def __getitem__(self, key):
        return self._glyphs.get(key)


class _FakeGlyph:
    def __init__(
        self,
        name: str,
        char: str | None = None,
        *,
        export: bool = True,
        left_group: str | None = None,
        right_group: str | None = None,
    ) -> None:
        self.name = name
        self.char = char
        self.export = export
        self.leftKerningGroup = left_group
        self.rightKerningGroup = right_group
        self.layers = {}


class _ProofGlyph:
    def __init__(self, name: str, char: str | None) -> None:
        self.name = name
        self.char = char


class McpToolsKerningTests(unittest.TestCase):
    def _load_module(self):
        glyphs = [
            _FakeGlyph("A", "A"),
            _FakeGlyph("V", "V"),
            _FakeGlyph("H", "H"),
            _FakeGlyph("O", "O"),
        ]
        font = types.SimpleNamespace(
            glyphs=_GlyphCollection(glyphs),
            masters=[types.SimpleNamespace(id="m1")],
            kerning={"m1": {"A": {"V": -80}}},
        )
        glyphs_module = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(fonts=[font]),
        )
        helpers_module = types.SimpleNamespace(
            _coerce_numeric=lambda value: None if value is None else float(value),
            _glyph_unicode_char=lambda glyph: getattr(glyph, "char", None),
            _load_andre_fuchs_relevant_pairs=lambda: ({"id": "test_pairs", "pairCount": 1}, [("A", "V")], []),
            _open_tab_on_main_thread=lambda font_obj, text: object(),
            _safe_json=lambda payload: json.dumps(payload),
            _set_kerning_pairs_on_main_thread=lambda *args, **kwargs: None,
        )
        proof_module = types.SimpleNamespace(
            ProofGlyph=_ProofGlyph,
            assemble_tab_text=lambda sections, rendering, per_line: ("proof", []),
        )
        module_name = "glyphs_mcp_test_mcp_tools_kerning"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_module,
                "kerning_collision_engine": types.SimpleNamespace(),
                "kerning_proof_engine": proof_module,
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": helpers_module,
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module

    def test_generate_kerning_tab_handles_numeric_kerning_values(self) -> None:
        module = self._load_module()

        payload = json.loads(
            asyncio.run(
                module.generate_kerning_tab(
                    font_index=0,
                    master_id="m1",
                    relevant_limit=1,
                    missing_limit=1,
                    audit_limit=1,
                    per_line=4,
                    glyph_names=["A", "V"],
                )
            )
        )

        self.assertTrue(payload["success"])
        self.assertTrue(payload["openedTab"])
        self.assertEqual(payload["dataset"]["id"], "test_pairs")
        self.assertEqual(payload["counts"]["existingTightIncluded"], 1)
        self.assertEqual(payload["counts"]["existingWideIncluded"], 1)
        self.assertEqual(payload["text"], "proof")


if __name__ == "__main__":
    unittest.main()
