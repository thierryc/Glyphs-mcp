"""Passive Change Log and independent latest-session overlay contracts."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.canonical_tree import CanonicalFontTree, MemoryObjectStore  # noqa: E402
from glyphs_mcp_v2.change_history import ChangeHistory  # noqa: E402
from glyphs_mcp_v2.change_log_model import ChangeLogModel  # noqa: E402
from glyphs_mcp_v2.diff_overlay import overlay_for_layer  # noqa: E402


def _model(x: float = 0.0) -> dict:
    return {
        "font": {"familyName": "Feedback", "upm": 1000},
        "masters": [{"id": "m0", "name": "Regular"}],
        "instances": [],
        "glyphs": {
            "A": {
                "name": "A", "id": "id_A", "export": True,
                "layers": {
                    "m0": {
                        "id": "m0", "masterId": "m0", "name": "Regular",
                        "width": 500, "anchors": {}, "components": [], "pathSignature": [3],
                        "paths": [{"closed": True, "nodes": [
                            {"x": x, "y": 0, "type": "line", "smooth": False, "name": None},
                            {"x": 250, "y": 700, "type": "line", "smooth": False, "name": None},
                            {"x": 500, "y": 0, "type": "line", "smooth": False, "name": None},
                        ]}],
                    }
                },
            }
        },
        "kerning": {}, "features": [], "classes": [], "featurePrefixes": [],
    }


class ChangeFeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trees = CanonicalFontTree(MemoryObjectStore())
        self.history = ChangeHistory(self.trees, id_factory=iter(("commit_a", "commit_b")).__next__)
        self.before = _model(0)
        self.after = _model(20)
        self.commit = self.history.record_action(
            document_id="doc_feedback", tool="update_glyph_node_positions", effect="edit",
            status="success", run_id="run_latest", reason="Optical correction",
            before_model=self.before, after_model=self.after,
        )

    def test_change_log_lists_tool_call_and_semantic_targets(self) -> None:
        model = ChangeLogModel(self.history)
        rows = model.rows("doc_feedback")
        detail = model.detail(rows[0].commit_id)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].action, "Update Glyph Node Positions")
        self.assertEqual(rows[0].targets, "A · 1 change")
        self.assertIn("A / m0 / paths / 0 / nodes / 0 / x", detail)
        self.assertIn("0 → 20", detail)

    def test_overlay_uses_latest_session_not_change_log_selection(self) -> None:
        session = self.history.latest_session_diff("doc_feedback")
        overlay = overlay_for_layer(
            trees=self.trees,
            session=session,
            glyph_name="A",
            layer_key="m0",
            live_layer=self.after["glyphs"]["A"]["layers"]["m0"],
        )

        self.assertTrue(overlay.visible)
        self.assertFalse(overlay.stale)
        self.assertEqual(overlay.before_paths[0]["nodes"][0]["x"], 0)
        self.assertEqual(overlay.target_paths[0]["nodes"][0]["x"], 20)

    def test_later_relevant_edit_marks_overlay_stale(self) -> None:
        live = copy.deepcopy(self.after["glyphs"]["A"]["layers"]["m0"])
        live["paths"][0]["nodes"][0]["x"] = 35
        overlay = overlay_for_layer(
            trees=self.trees,
            session=self.history.latest_session_diff("doc_feedback"),
            glyph_name="A",
            layer_key="m0",
            live_layer=live,
        )
        self.assertTrue(overlay.visible)
        self.assertTrue(overlay.stale)

    def test_unrelated_layer_draws_nothing(self) -> None:
        overlay = overlay_for_layer(
            trees=self.trees,
            session=self.history.latest_session_diff("doc_feedback"),
            glyph_name="B",
            layer_key="m0",
            live_layer={},
        )
        self.assertFalse(overlay.visible)

    def test_appkit_panel_is_passive_and_reporter_has_no_font_view_callback(self) -> None:
        panel_source = (V2_SOURCE / "glyphs_mcp_v2" / "change_log_panel.py").read_text(encoding="utf-8")
        reporter_source = (V2_SOURCE / "glyphs_mcp_v2" / "change_diff_reporter.py").read_text(encoding="utf-8")
        for forbidden in ("currentTab", "newTab", "activateReporter", "selectedFontMaster", "tab.layers"):
            self.assertNotIn(forbidden, panel_source)
        for forbidden in ("drawForegroundForLayer", "drawBackgroundForLayer", "fontView"):
            self.assertNotIn(forbidden, reporter_source)


if __name__ == "__main__":
    unittest.main()
