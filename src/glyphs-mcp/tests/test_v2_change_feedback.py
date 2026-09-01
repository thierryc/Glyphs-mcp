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
from glyphs_mcp_v2.diff_overlay import (  # noqa: E402
    SavedLayerGeometryCache,
    overlay_for_layer,
)
from glyphs_mcp_v2.projection_queue import ProjectionRequestQueue  # noqa: E402


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
        self.assertEqual(overlay.baseline_anchors["anchor:top:0"], (250, 700))
        self.assertEqual(overlay.current_anchors["anchor:top:0"], (260, 710))
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

    def test_added_and_removed_anchors_remain_explicit_in_the_plan(self) -> None:
        saved = copy.deepcopy(self.before)
        saved_layer = saved["glyphs"]["A"]["layers"]["m0"]
        saved_layer["anchors"] = {"old": [100, 200]}
        live = copy.deepcopy(saved_layer)
        live["anchors"] = {"new": [300, 400]}

        plan = overlay_for_layer(
            baseline_model=saved,
            glyph_name="A",
            layer_key="m0",
            live_layer=live,
        )

        self.assertEqual(set(plan.baseline_anchors), {"anchor:old:0"})
        self.assertEqual(set(plan.current_anchors), {"anchor:new:0"})

    def test_topology_mismatch_retains_saved_ghost_without_bands(self) -> None:
        live = copy.deepcopy(self.before["glyphs"]["A"]["layers"]["m0"])
        live["paths"][0]["nodes"].pop()

        plan = overlay_for_layer(
            baseline_model=self.before,
            glyph_name="A",
            layer_key="m0",
            live_layer=live,
        )

        self.assertTrue(plan.visible)
        self.assertFalse(plan.topology_compatible)
        self.assertFalse(plan.bands)
        self.assertTrue(plan.baseline_segments)

    def test_saved_segments_are_reused_by_source_glyph_and_layer(self) -> None:
        cache = SavedLayerGeometryCache()
        first = cache.get_or_prepare(
            source_fingerprint="sha256:saved",
            baseline_model=self.before,
            glyph_name="A",
            layer_key="m0",
        )
        second = cache.get_or_prepare(
            source_fingerprint="sha256:saved",
            baseline_model=self.before,
            glyph_name="A",
            layer_key="m0",
        )

        self.assertIsNotNone(first)
        self.assertIs(first, second)
        self.assertIs(first.segments, second.segments)

    def test_projection_requests_wait_for_the_latest_interface_quiet_window(self) -> None:
        now = [10.0]
        queue = ProjectionRequestQueue(
            delay_seconds=0.025,
            clock=lambda: now[0],
        )

        first_generation = queue.note_interface_change()
        queue.defer("A", version=("saved", first_generation), payload="old A")
        now[0] += 0.010
        remaining, ready = queue.drain_ready()
        self.assertAlmostEqual(remaining, 0.015)
        self.assertEqual(ready, ())

        second_generation = queue.note_interface_change()
        queue.defer("B", version=("saved", second_generation), payload="new B")
        now[0] += 0.025
        remaining, ready = queue.drain_ready()
        self.assertEqual(remaining, 0.0)
        self.assertEqual(ready, ("new B",))

    def test_projection_candidate_survives_additional_interface_notifications(self) -> None:
        now = [10.0]
        queue = ProjectionRequestQueue(
            delay_seconds=0.025,
            clock=lambda: now[0],
        )
        generation = queue.note_interface_change()
        queue.defer("A", version=("saved", generation), payload="current A")

        now[0] += 0.010
        queue.note_interface_change()
        now[0] += 0.025

        remaining, ready = queue.drain_ready()
        self.assertEqual(remaining, 0.0)
        self.assertEqual(ready, ("current A",))

    def test_projection_requests_coalesce_repeated_paints_for_one_layer(self) -> None:
        queue = ProjectionRequestQueue(delay_seconds=0.0, clock=lambda: 0.0)
        generation = queue.note_interface_change()
        version = ("saved", generation)

        self.assertTrue(queue.defer("A", version=version, payload="first"))
        self.assertFalse(queue.defer("A", version=version, payload="duplicate"))
        self.assertTrue(
            queue.defer(
                "A",
                version=("new saved", generation),
                payload="latest",
            )
        )

        _remaining, ready = queue.drain_ready()
        self.assertEqual(ready, ("latest",))

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
        self.assertIn("NativeLayerOverlayProjector", reporter_source)
        self.assertIn("self._saved_sources.store.snapshot", reporter_source)
        self.assertIn('self.menuName = "Changes Since Save"', reporter_source)
        self.assertIn("_draw_difference(plan.bands)", reporter_source)
        self.assertIn("_stroke_saved_segments", reporter_source)
        self.assertIn("_stroke_added_anchor(current, radius)", reporter_source)
        self.assertIn(".fill()", reporter_source)
        self.assertIn("PROJECTION_SETTLE_DELAY_SECONDS = 0.025", reporter_source)
        self.assertIn("ProjectionRequestQueue", reporter_source)
        self.assertIn("performSelector_withObject_afterDelay_", reporter_source)
        self.assertIn("self._projection_requests.remaining_delay()", reporter_source)
        self.assertNotIn("NSTimer", reporter_source)
        self.assertNotIn("pollSavedSources_", reporter_source)
        self.assertNotIn("TARGET_STALE_RGBA", reporter_source)
        foreground_source = reporter_source.split("def foreground(self, layer):", 1)[1]
        foreground_source = foreground_source.split("def _teardown", 1)[0]
        for forbidden in (
            ".refresh(",
            "_source_file_state",
            "_saved_source_canonical_model",
            "native_layer_overlay_state",
            "build_layer_diff_plan",
            "difference_bands",
            "path_segments",
            ".result(",
            ".join(",
        ):
            self.assertNotIn(forbidden, foreground_source)


if __name__ == "__main__":
    unittest.main()
