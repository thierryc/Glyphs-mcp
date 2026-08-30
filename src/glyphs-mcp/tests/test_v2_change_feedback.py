"""Passive Change Log and independent saved-source overlay contracts."""

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
from glyphs_mcp_v2.diff_geometry import (  # noqa: E402
    DifferenceTopologyError,
    difference_bands,
)
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

    def test_overlay_compares_the_live_layer_with_the_saved_source(self) -> None:
        overlay = overlay_for_layer(
            baseline_model=self.before,
            glyph_name="A",
            layer_key="m0",
            live_layer=self.after["glyphs"]["A"]["layers"]["m0"],
        )

        self.assertTrue(overlay.visible)
        self.assertEqual(overlay.baseline_paths[0]["nodes"][0]["x"], 0)
        self.assertEqual(overlay.current_paths[0]["nodes"][0]["x"], 20)

    def test_manual_edit_updates_the_live_delta_from_disk(self) -> None:
        live = copy.deepcopy(self.after["glyphs"]["A"]["layers"]["m0"])
        live["paths"][0]["nodes"][0]["x"] = 35
        overlay = overlay_for_layer(
            baseline_model=self.before,
            glyph_name="A",
            layer_key="m0",
            live_layer=live,
        )
        self.assertTrue(overlay.visible)
        self.assertEqual(overlay.baseline_paths[0]["nodes"][0]["x"], 0)
        self.assertEqual(overlay.current_paths[0]["nodes"][0]["x"], 35)

    def test_unrelated_layer_metadata_draws_nothing(self) -> None:
        live = copy.deepcopy(self.before["glyphs"]["A"]["layers"]["m0"])
        live["name"] = "User label unrelated to visual geometry"
        overlay = overlay_for_layer(
            baseline_model=self.before,
            glyph_name="A",
            layer_key="m0",
            live_layer=live,
        )
        self.assertFalse(overlay.visible)

    def test_anchor_and_width_changes_are_projected(self) -> None:
        saved = copy.deepcopy(self.before)
        layer = saved["glyphs"]["A"]["layers"]["m0"]
        layer["anchors"] = {"top": [250, 700]}
        live = copy.deepcopy(layer)
        live["anchors"]["top"] = [260, 710]
        live["width"] = 540

        overlay = overlay_for_layer(
            baseline_model=saved,
            glyph_name="A",
            layer_key="m0",
            live_layer=live,
        )

        self.assertTrue(overlay.visible)
        self.assertEqual(overlay.baseline_anchors["anchor:top:0"], [250, 700])
        self.assertEqual(overlay.current_anchors["anchor:top:0"], [260, 710])
        self.assertEqual(overlay.baseline_width, 500)
        self.assertEqual(overlay.current_width, 540)

    def test_nonvisual_saved_anchor_fields_do_not_create_a_difference(self) -> None:
        saved = copy.deepcopy(self.before)
        saved_layer = saved["glyphs"]["A"]["layers"]["m0"]
        saved_layer["anchors"] = [
            {
                "id": "anchor:top:0",
                "name": "top",
                "position": [250, 700],
                "orientation": 0,
                "locked": False,
                "attributes": {},
                "userData": {},
            }
        ]
        live = copy.deepcopy(saved_layer)
        live["anchors"] = [
            {"id": "anchor:top:0", "name": "top", "position": [250, 700]}
        ]

        overlay = overlay_for_layer(
            baseline_model=saved,
            glyph_name="A",
            layer_key="m0",
            live_layer=live,
        )

        self.assertFalse(overlay.visible)

    def test_difference_geometry_builds_only_the_gap_between_old_and_live_paths(self) -> None:
        baseline = self.before["glyphs"]["A"]["layers"]["m0"]["paths"]
        live = copy.deepcopy(self.after["glyphs"]["A"]["layers"]["m0"]["paths"])
        live[0]["nodes"][0]["x"] = 35

        bands = difference_bands(baseline, live)

        self.assertEqual(len(bands), 1)
        self.assertTrue(bands[0].closed)
        self.assertEqual(bands[0].baseline_segments[0].points[0], (0.0, 0.0))
        self.assertEqual(bands[0].current_segments[0].points[0], (35.0, 0.0))
        self.assertEqual(difference_bands(baseline, baseline), ())

    def test_difference_geometry_refuses_an_ambiguous_topology_mapping(self) -> None:
        baseline = self.before["glyphs"]["A"]["layers"]["m0"]["paths"]
        incompatible = copy.deepcopy(baseline)
        incompatible[0]["nodes"].pop()

        with self.assertRaises(DifferenceTopologyError):
            difference_bands(baseline, incompatible)

    def test_unrelated_layer_draws_nothing(self) -> None:
        overlay = overlay_for_layer(
            baseline_model=self.before,
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
        for forbidden in (
            "native_font_to_model",
            "native_layer_to_model",
            "fingerprint_model",
            "diff_models",
            "capture_snapshot",
            "active_history",
            "active_host",
        ):
            self.assertNotIn(forbidden, reporter_source)
        self.assertIn("native_layer_overlay_state", reporter_source)
        self.assertIn("self._baseline_cache.snapshot", reporter_source)
        self.assertIn('self.menuName = "Changes Since Save"', reporter_source)
        self.assertIn("_draw_difference", reporter_source)
        self.assertIn("_stroke_saved_paths", reporter_source)
        self.assertIn(".fill()", reporter_source)
        self.assertNotIn("TARGET_STALE_RGBA", reporter_source)
        foreground_source = reporter_source.split("def foreground(self, layer):", 1)[1]
        foreground_source = foreground_source.split("def __file__", 1)[0]
        for forbidden in (".refresh(", "_source_file_state", "_saved_source_canonical_model"):
            self.assertNotIn(forbidden, foreground_source)


if __name__ == "__main__":
    unittest.main()
