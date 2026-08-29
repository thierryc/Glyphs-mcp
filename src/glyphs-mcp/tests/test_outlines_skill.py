"""Contract tests for the canonical outline skill."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
CANONICAL = REPO / "skills" / "glyphs-mcp-outlines-docs" / "SKILL.md"
PACKAGED = REPO / "plugins" / "glyphs-mcp" / "skills" / "glyphs-mcp-outlines-docs" / "SKILL.md"


class OutlinesSkillTests(unittest.TestCase):
    def test_trigger_description_names_curve_geometry_work(self) -> None:
        text = CANONICAL.read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        for phrase in (
            "outlines",
            "components",
            "anchors",
            "selected nodes",
            "cubic geometry",
            "curvature",
            "surface: glyphs-mcp-v2",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, frontmatter)

    def test_skill_contains_coherent_v2_outline_workflow(self) -> None:
        text = CANONICAL.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        for phrase in (
            "# Glyphs MCP outlines and anchors",
            "get_server_info",
            "data.apiMajor == 2",
            "list_documents",
            "search_knowledge",
            "get_knowledge",
            "read_document",
            "exact glyph, layer, shape, and anchor identities",
            "geometry.counts",
            'execute_python(mode="read_only")',
            "Generic `translate`",
            "Generic `insert`, `set`, `move`, and `remove`",
            'execute_python(mode="staged_document")',
            "preview_change",
            "apply_change",
            "Never call `save_document` automatically",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, normalized)

        for removed_v1_tool in (
            "review_tunni_geometry",
            "review_curve_quality",
            "set_curve_review_overlay",
            "apply_tunni_balance",
            "update_glyph_node_positions",
            "review_start_node_alignment",
            "apply_start_node_alignment",
            "get_glyph_paths",
            "get_glyph_components",
            "docs_search",
            "docs_get",
        ):
            with self.subTest(removed_v1_tool=removed_v1_tool):
                self.assertNotIn(removed_v1_tool, text)

    def test_curve_diagnostics_use_bounded_read_then_staged_edit(self) -> None:
        text = CANONICAL.read_text(encoding="utf-8")
        normalized = " ".join(text.split())

        for invariant in (
            "Use measurements as evidence, not artistic scores",
            "exact glyph, layer, shape, and anchor identities",
            'execute_python(mode="read_only")',
            "Bound inspection to named entities and reject observed mutation",
            "Preserve topology, node types, smooth flags, winding, component identity",
            "inspect the immutable `preview_change` or staged Python preview",
            "Re-read exact affected entities",
            "Never call `save_document` automatically",
        ):
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, normalized)

    def test_start_node_work_uses_the_v2_staged_fallback(self) -> None:
        text = CANONICAL.read_text(encoding="utf-8")
        normalized = " ".join(text.split())

        required_phrases = (
            "Never rotate an open path or guess an ambiguous match",
            "Node-level and other unsupported edits use",
            'execute_python(mode="staged_document")',
            "Always add physical before/after constraints",
            "immutable `preview_change` or staged Python preview",
            "apply it only through `apply_change`",
            "Re-read exact affected entities",
        )
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, normalized)

        for removed_contract in (
            "review_start_node_alignment",
            "apply_start_node_alignment",
            "planFingerprint",
            "execute_code_with_context",
            "executionMode=staged_document",
        ):
            with self.subTest(removed_contract=removed_contract):
                self.assertNotIn(removed_contract, normalized)

    def test_packaged_skill_matches_canonical(self) -> None:
        self.assertEqual(
            PACKAGED.read_text(encoding="utf-8"),
            CANONICAL.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
