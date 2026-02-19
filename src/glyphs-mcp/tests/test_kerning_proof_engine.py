from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
import sys
import unittest


def _load_engine() -> ModuleType:
    resources_dir = (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )
    module_path = resources_dir / "kerning_proof_engine.py"
    spec = importlib.util.spec_from_file_location("kerning_proof_engine", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


class KerningProofEngineTests(unittest.TestCase):
    def test_hybrid_renders_unicode_when_available(self) -> None:
        engine = _load_engine()
        ProofGlyph = engine.ProofGlyph

        token, warnings = engine.render_token(
            [ProofGlyph("A", "A"), ProofGlyph("V", "V")],
            rendering="hybrid",
        )
        self.assertEqual(token, "AV")
        self.assertEqual(warnings, [])

    def test_hybrid_falls_back_to_slash_chain(self) -> None:
        engine = _load_engine()
        ProofGlyph = engine.ProofGlyph

        token, warnings = engine.render_token(
            [ProofGlyph("A.sc", None), ProofGlyph("V.sc", None)],
            rendering="hybrid",
        )
        self.assertEqual(token, "/A.sc/V.sc")
        self.assertNotIn(" ", token)
        self.assertEqual(warnings, [])

    def test_pack_tokens_respects_per_line(self) -> None:
        engine = _load_engine()
        packed = engine.pack_tokens(["AA", "BB", "CC"], per_line=2)
        self.assertEqual(packed, "AA BB\nCC")

    def test_assemble_tab_text_includes_headings(self) -> None:
        engine = _load_engine()
        ProofGlyph = engine.ProofGlyph

        text, _warnings = engine.assemble_tab_text(
            sections=[("TITLE", [[ProofGlyph("A", "A")]])],
            rendering="hybrid",
            per_line=12,
        )
        self.assertIn("TITLE", text)
        self.assertIn("A", text)


if __name__ == "__main__":
    unittest.main()
