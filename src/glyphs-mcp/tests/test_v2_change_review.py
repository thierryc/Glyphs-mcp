"""Apply-first change-operation state and navigation tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))


def _operation(items, *, operation_id="op_review", document_id="doc_a"):
    return {
        "operationId": operation_id,
        "documentId": document_id,
        "tool": "apply_glyph_updates",
        "reason": "Test change",
        "status": "applied",
        "beforeFingerprint": "before",
        "afterFingerprint": "after",
        "items": list(items),
        "auditReceipt": {"auditId": "audit_1", "timestamp": "2026-08-17T00:00:00Z"},
    }


class _Layer:
    def __init__(self, layer_id, master_id):
        self.layerId = layer_id
        self.associatedMasterId = master_id


class _Glyph:
    def __init__(self, name, layers):
        self.name = name
        self.layers = list(layers)


class _Tab:
    def __init__(self, layers):
        self.layers = list(layers)
        self.tempData = {}


class _Font:
    def __init__(self, glyphs):
        self.glyphs = {glyph.name: glyph for glyph in glyphs}
        self.tabs = []
        self.currentTab = None
        self.new_tab_calls = 0

    def newTab(self, layers):
        self.new_tab_calls += 1
        tab = _Tab(layers)
        self.tabs.append(tab)
        self.currentTab = tab
        return tab


class ChangeReviewStoreTests(unittest.TestCase):
    def test_store_keeps_one_selected_operation_per_document(self) -> None:
        from glyphs_mcp_v2.change_review import ChangeOperation, ChangeReviewStore

        store = ChangeReviewStore(id_factory=lambda: "op_generated")
        first = store.register(ChangeOperation.from_mapping(_operation([])))
        second = store.register(
            ChangeOperation.from_mapping(_operation([], operation_id="op_two"))
        )

        self.assertEqual(store.list_operations("doc_a"), (first, second))
        self.assertIsNone(store.selected("doc_a"))
        store.select("doc_a", "op_review")
        self.assertEqual(store.selected("doc_a").operation_id, "op_review")
        store.select("doc_a", "op_two")
        self.assertEqual(store.selected("doc_a").operation_id, "op_two")
        self.assertEqual(store.selected_ids(), {"doc_a": "op_two"})

    def test_change_operation_deduplicates_glyph_targets_in_first_change_order(self) -> None:
        from glyphs_mcp_v2.change_review import ChangeOperation

        operation = ChangeOperation.from_mapping(
            _operation(
                [
                    {"glyphName": "b", "masterId": "m2", "layerId": "b.m2"},
                    {"glyphName": "a", "masterId": "m1", "layerId": "a.m1"},
                    {"glyphName": "b", "masterId": "m1", "layerId": "b.m1"},
                ]
            )
        )
        self.assertEqual(
            operation.glyph_targets(),
            (
                {"glyphName": "b", "masterId": "m2", "layerId": "b.m2"},
                {"glyphName": "a", "masterId": "m1", "layerId": "a.m1"},
            ),
        )

    def test_outline_overlay_is_current_stale_or_absent_from_one_pure_resolver(self) -> None:
        from glyphs_mcp_v2.change_review import ChangeOperation, resolve_outline_overlay
        from glyphs_mcp_v2.semantic import fingerprint_model

        before = [{"closed": True, "nodes": [{"x": 0, "y": 0, "type": "line"}]}]
        applied = [{"closed": True, "nodes": [{"x": 10, "y": 0, "type": "line"}]}]
        operation = ChangeOperation.from_mapping(
            _operation(
                [
                    {
                        "glyphName": "a",
                        "masterId": "m1",
                        "layerId": "a.m1",
                        "displayBefore": before,
                        "displayApplied": applied,
                        "displayAppliedFingerprint": fingerprint_model(applied),
                    }
                ]
            )
        )

        current = resolve_outline_overlay(
            operation,
            glyph_name="a",
            layer_id="a.m1",
            master_id="m1",
            live_paths=applied,
        )
        stale = resolve_outline_overlay(
            operation,
            glyph_name="a",
            layer_id="a.m1",
            master_id="m1",
            live_paths=[{"closed": True, "nodes": [{"x": 12, "y": 0, "type": "line"}]}],
        )

        self.assertFalse(current["stale"])
        self.assertTrue(stale["stale"])
        self.assertIsNone(
            resolve_outline_overlay(
                operation.with_status("rolled_back"),
                glyph_name="a",
                layer_id="a.m1",
                master_id="m1",
                live_paths=before,
            )
        )
        self.assertIsNone(
            resolve_outline_overlay(
                operation,
                glyph_name="b",
                layer_id="b.m1",
                master_id="m1",
                live_paths=applied,
            )
        )


class ChangeReviewNavigationTests(unittest.TestCase):
    @staticmethod
    def _items(count):
        return [
            {
                "glyphName": "g{:03d}".format(index),
                "masterId": "m1",
                "layerId": "g{:03d}.m1".format(index),
            }
            for index in range(count)
        ]

    def test_open_reuses_one_tagged_tab_and_exact_affected_layers(self) -> None:
        from glyphs_mcp_v2.change_review import ChangeOperation
        from glyphs_mcp_v2.change_review_navigation import open_changed_glyphs

        font = _Font(
            [
                _Glyph("a", [_Layer("a.m1", "m1"), _Layer("a.m2", "m2")]),
                _Glyph("b", [_Layer("b.m1", "m1"), _Layer("b.m2", "m2")]),
            ]
        )
        operation = ChangeOperation.from_mapping(
            _operation(
                [
                    {"glyphName": "b", "masterId": "m2", "layerId": "b.m2"},
                    {"glyphName": "a", "masterId": "m1", "layerId": "a.m1"},
                    {"glyphName": "b", "masterId": "m1", "layerId": "b.m1"},
                ]
            )
        )

        first = open_changed_glyphs(font, operation)
        second = open_changed_glyphs(font, operation)

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertFalse(first["reusedTab"])
        self.assertTrue(second["reusedTab"])
        self.assertEqual(font.new_tab_calls, 1)
        self.assertIs(font.currentTab, font.tabs[0])
        self.assertEqual([layer.layerId for layer in font.currentTab.layers], ["b.m2", "a.m1"])
        self.assertEqual(font.currentTab.tempData["glyphsMCPChangeOperationId"], "op_review")

    def test_target_limit_is_strict_and_never_opens_a_partial_tab(self) -> None:
        from glyphs_mcp_v2.change_review import ChangeOperation
        from glyphs_mcp_v2.change_review_navigation import open_changed_glyphs

        glyphs = [
            _Glyph("g{:03d}".format(index), [_Layer("g{:03d}.m1".format(index), "m1")])
            for index in range(501)
        ]
        font = _Font(glyphs)
        operation = ChangeOperation.from_mapping(_operation(self._items(501)))

        result = open_changed_glyphs(font, operation)

        self.assertFalse(result["ok"])
        self.assertEqual(result["errorCode"], "too_many_review_targets")
        self.assertEqual(font.new_tab_calls, 0)

    def test_supported_scale_counts_open_one_complete_tab(self) -> None:
        from glyphs_mcp_v2.change_review import ChangeOperation
        from glyphs_mcp_v2.change_review_navigation import open_changed_glyphs

        for count in (1, 2, 383, 500):
            with self.subTest(count=count):
                glyphs = [
                    _Glyph(
                        "g{:03d}".format(index),
                        [_Layer("g{:03d}.m1".format(index), "m1")],
                    )
                    for index in range(count)
                ]
                font = _Font(glyphs)
                operation = ChangeOperation.from_mapping(_operation(self._items(count)))

                result = open_changed_glyphs(font, operation)

                self.assertTrue(result["ok"])
                self.assertEqual(result["openedGlyphCount"], count)
                self.assertEqual(len(font.currentTab.layers), count)
                self.assertEqual(font.new_tab_calls, 1)

    def test_missing_targets_are_bounded_warnings_not_document_fallbacks(self) -> None:
        from glyphs_mcp_v2.change_review import ChangeOperation
        from glyphs_mcp_v2.change_review_navigation import open_changed_glyphs

        font = _Font([_Glyph("a", [_Layer("a.m1", "m1")])])
        operation = ChangeOperation.from_mapping(
            _operation(
                [
                    {"glyphName": "missing", "masterId": "m1", "layerId": "missing.m1"},
                    {"glyphName": "a", "masterId": "m1", "layerId": "a.m1"},
                ]
            )
        )

        result = open_changed_glyphs(font, operation)

        self.assertTrue(result["ok"])
        self.assertEqual(result["openedGlyphCount"], 1)
        self.assertEqual(result["missingGlyphCount"], 1)
        self.assertEqual(result["missingGlyphNames"], ["missing"])

    def test_missing_explicit_layer_is_skipped_instead_of_using_another_master(self) -> None:
        from glyphs_mcp_v2.change_review import ChangeOperation
        from glyphs_mcp_v2.change_review_navigation import open_changed_glyphs

        font = _Font([_Glyph("a", [_Layer("a.m1", "m1")])])
        operation = ChangeOperation.from_mapping(
            _operation(
                [{"glyphName": "a", "masterId": "m2", "layerId": "a.m2"}]
            )
        )

        result = open_changed_glyphs(font, operation)

        self.assertFalse(result["ok"])
        self.assertEqual(result["errorCode"], "review_targets_unavailable")
        self.assertEqual(font.new_tab_calls, 0)


class ChangeReviewUISourceTests(unittest.TestCase):
    def test_panel_double_click_and_button_share_one_handler(self) -> None:
        source = (
            V2_SOURCE / "glyphs_mcp_v2" / "change_review_panel.py"
        ).read_text(encoding="utf-8")
        self.assertIn("table.setDoubleAction_(self.OpenChangedGlyphs_)", source)
        self.assertIn("open_button.setAction_(self.OpenChangedGlyphs_)", source)
        self.assertEqual(source.count("def OpenChangedGlyphs_(self, sender):"), 1)

    def test_reporter_has_no_font_view_callbacks_or_document_writes(self) -> None:
        source = (
            V2_SOURCE / "glyphs_mcp_v2" / "change_review_reporter.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("drawForegroundForLayer", source)
        self.assertNotIn("drawBackgroundForLayer", source)
        self.assertNotIn("drawFontView", source)
        self.assertNotIn("save(", source)
        self.assertNotIn("userData", source)


if __name__ == "__main__":
    unittest.main()
