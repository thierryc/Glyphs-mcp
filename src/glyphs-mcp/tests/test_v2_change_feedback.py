"""Passive Change Log and independent saved-source overlay contracts."""

from __future__ import annotations

import copy
import ast
import sys
import unittest
from types import SimpleNamespace
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.canonical_tree import CanonicalFontTree, MemoryObjectStore  # noqa: E402
from glyphs_mcp_v2.change_history import ChangeHistory  # noqa: E402
from glyphs_mcp_v2.change_log_model import ChangeLogModel  # noqa: E402
from glyphs_mcp_v2.diff_geometry import (  # noqa: E402
    DiffPreparationCancelled,
    DifferenceTopologyError,
    difference_bands,
)
from glyphs_mcp_v2.diff_overlay import (  # noqa: E402
    SavedLayerGeometryCache,
    overlay_for_layer,
)
from glyphs_mcp_v2.projection_queue import (  # noqa: E402
    PlanVersion,
    PreparedPlan,
    PreparedPlanCache,
    ProjectionRequestQueue,
    ViewStamp,
)


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


def _stamp(controller, key, *, scale=1.0, cursor=0, viewport=(0, 0, 100, 100)):
    return ViewStamp.create(
        controller_identity=controller,
        active_layer_key=key,
        layer_cursor=cursor,
        scale=scale,
        viewport=viewport,
        bounds=(0, 0, 100, 100),
        selected_layer_origin=(0, 0),
    )


def _ready_token(queue, now, controller, key, source="saved"):
    queue.note_interface_change(
        controller,
        active_key=key,
        reference_fingerprint=source,
    )
    now[0] += queue.delay_seconds
    first = queue.sample_capture(controller, _stamp(controller, key))
    assert first.status == "waiting"
    now[0] += queue.stability_interval_seconds
    second = queue.sample_capture(controller, _stamp(controller, key))
    assert second.status == "ready" and second.token is not None
    return second.token


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

    def test_saved_geometry_cache_is_lru_bounded(self) -> None:
        cache = SavedLayerGeometryCache(capacity=2)
        for index in range(3):
            model = _model(float(index))
            cache.get_or_prepare(
                source_fingerprint="sha256:saved-{}".format(index),
                baseline_model=model,
                glyph_name="A",
                layer_key="m0",
            )
        self.assertEqual(len(cache._values), 2)

    def test_rapid_navigation_waits_for_the_latest_quiet_and_stable_window(self) -> None:
        now = [10.0]
        queue = ProjectionRequestQueue(
            delay_seconds=0.025,
            stability_interval_seconds=0.016,
            clock=lambda: now[0],
        )
        keys = tuple(("/font.glyphs", name, "m0") for name in "ABC")

        queue.note_interface_change(
            "view", active_key=keys[0], reference_fingerprint="saved"
        )
        now[0] += 0.010
        queue.note_interface_change(
            "view", active_key=keys[1], reference_fingerprint="saved"
        )
        now[0] += 0.010
        queue.note_interface_change(
            "view", active_key=keys[2], reference_fingerprint="saved"
        )

        now[0] += 0.024
        self.assertAlmostEqual(queue.remaining_delay("view"), 0.001)
        self.assertEqual(
            queue.sample_capture("view", _stamp("view", keys[2])).status,
            "waiting",
        )
        now[0] += 0.0011
        self.assertEqual(
            queue.sample_capture("view", _stamp("view", keys[2])).status,
            "waiting",
        )
        now[0] += 0.0161
        ready = queue.sample_capture("view", _stamp("view", keys[2]))
        self.assertEqual(ready.status, "ready")
        self.assertEqual(ready.token.active_key, keys[2])

    def test_view_stamp_normalizes_floating_state_to_six_decimals(self) -> None:
        key = ("/font.glyphs", "A", "m0")
        first = _stamp(
            "view",
            key,
            scale=1.12345641,
            viewport=(0.00000041, 2.0, 100.0, 100.0),
        )
        second = _stamp(
            "view",
            key,
            scale=1.12345644,
            viewport=(0.00000044, 2.0, 100.0, 100.0),
        )
        self.assertEqual(first, second)

    def test_stability_retry_is_bounded_to_four_samples(self) -> None:
        now = [10.0]
        queue = ProjectionRequestQueue(
            delay_seconds=0.0,
            stability_interval_seconds=0.016,
            maximum_stability_samples=4,
            clock=lambda: now[0],
        )
        key = ("/font.glyphs", "A", "m0")
        queue.note_interface_change(
            "view", active_key=key, reference_fingerprint="saved"
        )
        decisions = []
        for scale in (1.0, 1.1, 1.2, 1.3):
            decisions.append(
                queue.sample_capture("view", _stamp("view", key, scale=scale))
            )
            now[0] += 0.016
        self.assertEqual([item.status for item in decisions], [
            "waiting", "waiting", "waiting", "abandoned"
        ])
        self.assertIsNone(queue.remaining_delay("view"))

    def test_stale_job_token_is_rejected_after_navigation(self) -> None:
        now = [0.0]
        queue = ProjectionRequestQueue(delay_seconds=0.0, clock=lambda: now[0])
        key_a = ("/font.glyphs", "A", "m0")
        key_b = ("/font.glyphs", "B", "m0")
        token = _ready_token(queue, now, "view", key_a)
        self.assertTrue(queue.is_current(token))
        queue.note_interface_change(
            "view", active_key=key_b, reference_fingerprint="saved"
        )
        self.assertFalse(queue.is_current(token))

    def test_navigation_never_exposes_the_previous_glyph_plan(self) -> None:
        now = [0.0]
        queue = ProjectionRequestQueue(delay_seconds=0.0, clock=lambda: now[0])
        key_a = ("/font.glyphs", "A", "m0")
        key_b = ("/font.glyphs", "B", "m0")
        token = _ready_token(queue, now, "view", key_a)
        visible = PreparedPlan(
            PlanVersion(key_a, "saved", "live-a"),
            SimpleNamespace(visible=True),
        )
        self.assertTrue(queue.publish(token, visible))
        self.assertIs(queue.published_for("view", key_a), visible)

        queue.note_interface_change(
            "view", active_key=key_b, reference_fingerprint="saved"
        )
        self.assertIsNone(queue.published_for("view", key_b))
        self.assertTrue(queue.session("view").invalidation_pending)

    def test_frame_only_events_do_not_create_diff_work(self) -> None:
        queue = ProjectionRequestQueue(delay_seconds=0.025, clock=lambda: 0.0)
        queue.ensure_session("view")
        session, cancelled = queue.note_view_frame("view")
        self.assertIsNotNone(session)
        self.assertIsNone(cancelled)
        self.assertFalse(session.capture_requested)
        self.assertIsNone(queue.remaining_delay("view"))

    def test_frame_event_rearms_only_an_existing_content_capture(self) -> None:
        now = [0.0]
        queue = ProjectionRequestQueue(delay_seconds=0.0, clock=lambda: now[0])
        key = ("/font.glyphs", "A", "m0")
        token = _ready_token(queue, now, "view", key)
        session, cancelled = queue.note_view_frame("view")
        self.assertEqual(cancelled, token)
        self.assertTrue(session.capture_requested)
        self.assertFalse(queue.is_current(token))

    def test_suspend_cancels_work_and_reenable_gets_a_new_epoch(self) -> None:
        now = [0.0]
        queue = ProjectionRequestQueue(delay_seconds=0.0, clock=lambda: now[0])
        key = ("/font.glyphs", "A", "m0")
        token = _ready_token(queue, now, "view", key)
        suspension = queue.suspend(clear_published=True)
        self.assertEqual(suspension.cancelled_tokens, (token,))
        self.assertEqual(suspension.invalidated_controllers, ())
        self.assertFalse(queue.is_current(token))
        new_token = _ready_token(queue, now, "view", key)
        self.assertGreater(new_token.content_epoch, token.content_epoch)

    def test_suspend_reports_visible_controllers_for_targeted_redraw(self) -> None:
        now = [0.0]
        queue = ProjectionRequestQueue(delay_seconds=0.0, clock=lambda: now[0])
        key = ("/font.glyphs", "A", "m0")
        token = _ready_token(queue, now, "view", key)
        visible = PreparedPlan(
            PlanVersion(key, "saved", "live"),
            SimpleNamespace(visible=True),
        )
        queue.publish(token, visible)
        pending = _ready_token(queue, now, "view", key)

        suspension = queue.suspend(clear_published=True)

        self.assertEqual(suspension.cancelled_tokens, (pending,))
        self.assertEqual(suspension.invalidated_controllers, ("view",))
        self.assertIsNone(queue.published_for("view", key))

    def test_each_interface_request_can_choose_its_own_settle_delay(self) -> None:
        now = [1.0]
        queue = ProjectionRequestQueue(
            delay_seconds=0.025, clock=lambda: now[0]
        )
        key = ("/font.glyphs", "A", "m0")
        queue.note_interface_change(
            "view",
            active_key=key,
            reference_fingerprint="saved",
            delay_seconds=0.100,
        )
        self.assertAlmostEqual(queue.remaining_delay("view"), 0.100)

    def test_sessions_are_independent_between_tabs(self) -> None:
        now = [0.0]
        queue = ProjectionRequestQueue(delay_seconds=0.0, clock=lambda: now[0])
        key_a = ("/font.glyphs", "A", "m0")
        key_b = ("/font.glyphs", "B", "m0")
        token_a = _ready_token(queue, now, "view-a", key_a)
        token_b = _ready_token(queue, now, "view-b", key_b)
        self.assertTrue(queue.is_current(token_a))
        self.assertTrue(queue.is_current(token_b))
        queue.note_interface_change(
            "view-a", active_key=key_b, reference_fingerprint="saved"
        )
        self.assertFalse(queue.is_current(token_a))
        self.assertTrue(queue.is_current(token_b))

    def test_render_signature_transitions_coalesce_targeted_invalidation(self) -> None:
        now = [0.0]
        queue = ProjectionRequestQueue(delay_seconds=0.0, clock=lambda: now[0])
        key = ("/font.glyphs", "A", "m0")

        invisible_token = _ready_token(queue, now, "view", key)
        invisible = PreparedPlan(
            PlanVersion(key, "saved", "live-0"),
            SimpleNamespace(visible=False),
        )
        self.assertFalse(queue.publish(invisible_token, invisible))
        self.assertFalse(queue.session("view").invalidation_pending)

        visible_token = _ready_token(queue, now, "view", key)
        visible = PreparedPlan(
            PlanVersion(key, "saved", "live-1"),
            SimpleNamespace(visible=True),
        )
        self.assertTrue(queue.publish(visible_token, visible))
        self.assertTrue(queue.session("view").invalidation_pending)
        self.assertEqual(
            queue.sample_invalidation("view", _stamp("view", key)).status,
            "waiting",
        )
        now[0] += 0.016
        self.assertEqual(
            queue.sample_invalidation("view", _stamp("view", key)).status,
            "ready",
        )

        same_token = _ready_token(queue, now, "view", key)
        self.assertFalse(queue.publish(same_token, visible))
        changed_token = _ready_token(queue, now, "view", key)
        changed = PreparedPlan(
            PlanVersion(key, "saved", "live-2"),
            SimpleNamespace(visible=True),
        )
        self.assertTrue(queue.publish(changed_token, changed))
        self.assertTrue(queue.session("view").invalidation_pending)

        disappeared_token = _ready_token(queue, now, "view", key)
        disappeared = PreparedPlan(
            PlanVersion(key, "saved", "live-3"),
            SimpleNamespace(visible=False),
        )
        self.assertTrue(queue.publish(disappeared_token, disappeared))
        self.assertTrue(queue.session("view").invalidation_pending)

    def test_content_addressed_plan_cache_reuses_and_evicts_lru(self) -> None:
        cache = PreparedPlanCache(capacity=2)
        key = ("/font.glyphs", "A", "m0")
        plans = [
            PreparedPlan(
                PlanVersion(key, "saved", "live-{}".format(index)),
                SimpleNamespace(visible=bool(index)),
            )
            for index in range(3)
        ]
        self.assertIs(cache.put(plans[0]), plans[0])
        self.assertIs(cache.get(plans[0].version), plans[0])
        cache.put(plans[1])
        cache.get(plans[0].version)
        cache.put(plans[2])
        self.assertEqual(len(cache), 2)
        self.assertIsNone(cache.get(plans[1].version))
        self.assertEqual(cache.versions(), (plans[0].version, plans[2].version))

    def test_source_save_invalidates_token_and_visible_publication(self) -> None:
        now = [0.0]
        queue = ProjectionRequestQueue(delay_seconds=0.0, clock=lambda: now[0])
        key = ("/font.glyphs", "A", "m0")
        token = _ready_token(queue, now, "view", key)
        visible = PreparedPlan(
            PlanVersion(key, "saved", "live"),
            SimpleNamespace(visible=True),
        )
        self.assertTrue(queue.publish(token, visible))
        next_token = _ready_token(queue, now, "view", key)
        cancelled = queue.invalidate_content(
            "view", clear_published=True, request_invalidation=True
        )
        self.assertEqual(cancelled, next_token)
        self.assertFalse(queue.is_current(next_token))
        self.assertIsNone(queue.published_for("view", key))

    def test_teardown_clear_removes_all_session_state(self) -> None:
        queue = ProjectionRequestQueue(delay_seconds=0.0, clock=lambda: 0.0)
        queue.ensure_session("view-a")
        queue.ensure_session("view-b")
        self.assertEqual(len(queue.clear()), 2)
        self.assertEqual(queue.sessions(), ())

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

    def test_cancelled_geometry_never_enters_the_saved_cache(self) -> None:
        cache = SavedLayerGeometryCache()
        checkpoints = [0]

        def cancelled() -> bool:
            checkpoints[0] += 1
            return checkpoints[0] >= 3

        with self.assertRaises(DiffPreparationCancelled):
            cache.get_or_prepare(
                source_fingerprint="sha256:cancelled",
                baseline_model=self.before,
                glyph_name="A",
                layer_key="m0",
                cancelled=cancelled,
            )
        self.assertEqual(len(cache._values), 0)

    def test_difference_band_construction_checks_cancellation_between_nodes(self) -> None:
        baseline = self.before["glyphs"]["A"]["layers"]["m0"]["paths"]
        live = copy.deepcopy(baseline)
        live[0]["nodes"][0]["x"] = 20
        checkpoints = [0]

        def cancelled() -> bool:
            checkpoints[0] += 1
            return checkpoints[0] >= 4

        with self.assertRaises(DiffPreparationCancelled):
            difference_bands(baseline, live, cancelled=cancelled)

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
        self.assertIn("self._references.snapshot_for_source", reporter_source)
        self.assertIn(
            'self.menuName = "Changes Against Reference"', reporter_source
        )
        self.assertIn("_draw_difference(plan.bands)", reporter_source)
        self.assertIn("_stroke_saved_segments", reporter_source)
        self.assertIn("_stroke_added_anchor(current, radius)", reporter_source)
        self.assertIn(".fill()", reporter_source)
        self.assertIn("PROJECTION_SETTLE_DELAY_SECONDS = 0.025", reporter_source)
        self.assertIn("VIEW_STABILITY_INTERVAL_SECONDS = 0.016", reporter_source)
        self.assertIn("MAXIMUM_STABILITY_SAMPLES = 4", reporter_source)
        self.assertIn('SAVED_HEX = "#3FE2A6"', reporter_source)
        self.assertIn('DIFFERENCE_HEX = "#3FD1E2"', reporter_source)
        self.assertIn('METRIC_HEX = "#3FDAC4"', reporter_source)
        self.assertIn(
            "SAVED_RGBA = (63.0 / 255.0, 226.0 / 255.0, 166.0 / 255.0, 0.78)",
            reporter_source,
        )
        self.assertIn(
            "DIFFERENCE_RGBA = (63.0 / 255.0, 209.0 / 255.0, 226.0 / 255.0, 0.26)",
            reporter_source,
        )
        self.assertIn(
            "METRIC_RGBA = (63.0 / 255.0, 218.0 / 255.0, 196.0 / 255.0, 0.18)",
            reporter_source,
        )
        self.assertIn("ProjectionRequestQueue", reporter_source)
        self.assertIn("performSelector_withObject_afterDelay_", reporter_source)
        self.assertIn("UPDATEEDITVIEWFRAME", reporter_source)
        self.assertIn("Glyphs, \"activeReporters\"", reporter_source)
        self.assertIn("CAPTURE_SLICE_BUDGET_SECONDS", reporter_source)
        self.assertIn("CAPTURE_SLICE_INTERVAL_SECONDS = 0.016", reporter_source)
        self.assertIn("POST_MCP_RESUME_DELAY_SECONDS = 0.250", reporter_source)
        self.assertIn("RAPID_SETTLE_DELAY_SECONDS = 0.100", reporter_source)
        self.assertIn('"advanceProjectionCapture:"', reporter_source)
        self.assertIn('"resumeVisualWork:"', reporter_source)
        self.assertIn("default_visual_work_gate()", reporter_source)
        self.assertNotIn("capture_plain_layer", reporter_source)
        self.assertNotIn('"currentlyPaused"', reporter_source)
        for performance_key in (
            '"mcpPauseEnabled"',
            '"overlayHiddenWhilePaused"',
            '"resumeDelayMs"',
            '"captureSliceBudgetMs"',
            '"captureSliceCadenceMs"',
            '"overBudgetThresholdMs"',
            '"suspensions"',
            '"resumes"',
            '"activityCancellations"',
            '"foregroundSkips"',
            '"captureSlices"',
            '"overBudgetSlices"',
            '"rapidSettleDeferrals"',
            '"captures"',
            '"cacheHits"',
            '"publications"',
            '"completedSuspension"',
            '"lastCapture"',
            '"maximumCapture"',
            '"lastPreparation"',
            '"maximumPreparation"',
            '"maximumSlice"',
        ):
            self.assertIn(performance_key, reporter_source)
        suspension_source = reporter_source.split(
            "def _suspend_projection_work(self, *, activity):", 1
        )[1].split("def DocumentWillSave_", 1)[0]
        self.assertIn("self._capture_jobs.clear()", suspension_source)
        self.assertIn("self._projection_state.suspend", suspension_source)
        self.assertIn("coordinator.invalidate", suspension_source)
        self.assertIn("self._invalidate_controller", suspension_source)
        capture_source = reporter_source.split(
            "def advanceProjectionCapture_(self, sender):", 1
        )[1].split("def _submit_projection_preparation", 1)[0]
        self.assertIn("CAPTURE_SLICE_INTERVAL_SECONDS", capture_source)
        publish_source = reporter_source.split(
            "def _submit_projection_preparation", 1
        )[1].split("def _invalidate_controller", 1)[0]
        self.assertLess(
            publish_source.rindex("if context.cancelled():"),
            publish_source.index("self._prepared_plan_cache.put"),
        )
        self.assertLess(
            publish_source.index("self._visual_suspended"),
            publish_source.index("self._projection_state.publish"),
        )
        resume_source = reporter_source.split(
            "def resumeVisualWork_(self, sender):", 1
        )[1].split("def _suspend_projection_work", 1)[0]
        self.assertEqual(resume_source.count("self._reconcile_current_view()"), 1)
        self.assertLess(
            resume_source.index("if not self._reporter_is_active()"),
            resume_source.index("self._reconcile_current_view()"),
        )
        self.assertIn('getattr(controller, "redraw", None)', reporter_source)
        self.assertEqual(reporter_source.count("Glyphs.redraw()"), 1)
        self.assertIn('self._diagnostics["globalFallbacks"] += 1', reporter_source)
        self.assertNotIn("NSTimer", reporter_source)
        self.assertNotIn("pollSavedSources_", reporter_source)
        self.assertNotIn("TARGET_STALE_RGBA", reporter_source)
        self.assertNotIn("_suppressed_plan_key", reporter_source)
        self.assertNotIn("_redraw_scheduled", reporter_source)
        flush_source = reporter_source.split(
            "def flushProjectionState_(self, sender):", 1
        )[1].split("def _validate_job", 1)[0]
        validation_source = reporter_source.split(
            "def _validate_job(self, token, *, require_stable_stamp):", 1
        )[1].split("def _cancel_projection", 1)[0]
        self.assertIn(
            "self._controllers.get(controller_identity)", flush_source
        )
        self.assertNotIn(
            "\n        controller = self._current_controller()", flush_source
        )
        self.assertIn(
            "self._controllers.get(session.controller_identity)",
            validation_source,
        )
        foreground_source = reporter_source.split("def foreground(self, layer):", 1)[1]
        foreground_source = foreground_source.split("def _teardown", 1)[0]
        self.assertLess(
            foreground_source.index("self._visual_suspended"),
            foreground_source.index("NSGraphicsContext.currentContext()"),
        )
        self.assertLess(
            foreground_source.index("self._visual_suspended"),
            foreground_source.index("self._callback_controller()"),
        )
        self.assertIn("self._callback_controller()", foreground_source)
        self.assertNotIn("self._current_controller()", foreground_source)
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
            "_saved_sources",
            "_references",
            "_reference_snapshot",
            "_arm_state_flush",
            "_begin_projection",
            "coordinator",
            ".submit(",
            ".put(",
            "addOperationWithBlock_",
            "performSelector_withObject_afterDelay_",
            ".redraw(",
        ):
            self.assertNotIn(forbidden, foreground_source)

        tree = ast.parse(reporter_source)
        reporter_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "GlyphsMCPChangeDiffReporter"
        )
        foreground = next(
            node
            for node in reporter_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "foreground"
        )
        called_names = {
            node.func.attr
            for node in ast.walk(foreground)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertFalse(
            called_names
            & {
                "snapshot",
                "submit",
                "put",
                "clear",
                "redraw",
                "addOperationWithBlock_",
                "performSelector_withObject_afterDelay_",
            }
        )


if __name__ == "__main__":
    unittest.main()
