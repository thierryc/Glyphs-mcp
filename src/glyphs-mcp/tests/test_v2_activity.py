"""Process-local activity contracts for the v2 Glyphs presentation adapter."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.activity import (  # noqa: E402
    ActivityCancelled,
    OperationActivityStore,
)
from glyphs_mcp_v2.versions import palette_display_name  # noqa: E402


class _Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


class OperationActivityStoreTests(unittest.TestCase):
    def test_activity_is_document_scoped_monotonic_and_event_driven(self) -> None:
        clock = _Clock()
        store = OperationActivityStore(clock=clock, id_factory=lambda: "activity_fixed")
        observed = []
        unsubscribe = store.subscribe(observed.append)

        token = store.begin(
            document_id="doc_alpha",
            tool="apply_glyph_updates",
            title="Apply Glyph Updates",
            cancellable=True,
        )
        clock.value += 2.5
        store.advance(token, "detached", "Running on detached document")
        clock.value += 1.0
        store.advance(token, "comparing", "Comparing changes")

        current = store.current("doc_alpha")
        self.assertEqual(current.activity_id, "activity_fixed")
        self.assertEqual(current.phase, "comparing")
        self.assertEqual(current.elapsed_seconds, 3.5)
        self.assertEqual(
            [item.phase for item in observed],
            ["preparing", "detached", "comparing"],
        )
        self.assertEqual(
            [item.sequence for item in observed],
            sorted(item.sequence for item in observed),
        )

        unsubscribe()
        store.complete(token, ok=True, summary="Applied")
        self.assertEqual(len(observed), 3)

    def test_cancel_is_cooperative_and_is_disabled_at_the_atomic_boundary(self) -> None:
        store = OperationActivityStore(id_factory=lambda: "activity_cancel")
        token = store.begin(
            document_id="doc_alpha",
            tool="execute_python",
            title="Execute Python",
            cancellable=True,
        )

        self.assertTrue(store.request_cancel(token.activity_id))
        with self.assertRaises(ActivityCancelled):
            store.checkpoint(token)

        second = store.begin(
            document_id="doc_alpha",
            tool="apply_glyph_updates",
            title="Apply Glyph Updates",
            cancellable=True,
        )
        store.advance(
            second,
            "applying",
            "Applying verified changes",
            cancellable=False,
        )
        self.assertFalse(store.request_cancel(second.activity_id))
        store.checkpoint(second)

    def test_observer_failure_never_changes_operation_state(self) -> None:
        store = OperationActivityStore(id_factory=lambda: "activity_observer")
        store.subscribe(lambda _snapshot: (_ for _ in ()).throw(RuntimeError("UI failed")))

        token = store.begin(
            document_id="doc_alpha",
            tool="list_glyphs",
            title="List Glyphs",
        )
        store.complete(token, ok=False, summary="Failed")

        current = store.current("doc_alpha")
        self.assertEqual(current.state, "error")
        self.assertEqual(current.summary, "Failed")

    def test_new_command_replaces_foreground_without_stale_resurrection(self) -> None:
        ids = iter(("activity_one", "activity_two"))
        store = OperationActivityStore(id_factory=lambda: next(ids))
        first = store.begin(document_id="doc_alpha", tool="one", title="One")
        second = store.begin(document_id="doc_alpha", tool="two", title="Two")

        self.assertEqual(store.current("doc_alpha").activity_id, second.activity_id)
        store.complete(second, ok=True, summary="Two done")
        store.release(second)
        self.assertEqual(store.current("doc_alpha").activity_id, second.activity_id)
        store.dismiss("doc_alpha")
        self.assertEqual(store.current("doc_alpha").state, "idle")
        store.complete(first, ok=True, summary="One done")
        store.release(first)
        self.assertEqual(store.current("doc_alpha").state, "idle")

    def test_progress_promotes_ongoing_work_but_old_completion_cannot_hide_newer_work(self) -> None:
        ids = iter(("activity_one", "activity_two"))
        store = OperationActivityStore(id_factory=lambda: next(ids))
        first = store.begin(document_id="doc_alpha", tool="one", title="One")
        second = store.begin(document_id="doc_alpha", tool="two", title="Two")

        store.advance(first, "verifying", "First made real progress")
        self.assertEqual(store.current("doc_alpha").activity_id, first.activity_id)
        store.complete(first, ok=True, summary="First done")
        store.release(first)
        self.assertEqual(store.current("doc_alpha").activity_id, second.activity_id)

    def test_valid_progress_refreshes_a_released_invocation_lease(self) -> None:
        clock = _Clock()
        store = OperationActivityStore(
            clock=clock, id_factory=lambda: "activity_progress"
        )
        token = store.begin(
            document_id="doc_alpha", tool="one", title="One"
        )
        store.release(token)
        clock.value += 20.0

        store.advance(token, "verifying", "Progress resumed")
        clock.value += 60.0
        store.reconcile_orphans(grace_seconds=30.0)

        self.assertEqual(
            store.current("doc_alpha").activity_id, token.activity_id
        )

    def test_completion_is_idempotent(self) -> None:
        store = OperationActivityStore(id_factory=lambda: "activity_once")
        token = store.begin(document_id="doc_alpha", tool="one", title="One")

        first = store.complete(token, ok=True, summary="Done")
        second = store.complete(token, ok=False, summary="Late error")

        self.assertEqual(first, second)
        self.assertEqual(store.current("doc_alpha").summary, "Done")

    def test_operation_summaries_are_bounded_and_link_public_identity(self) -> None:
        store = OperationActivityStore(id_factory=lambda: "activity_linked")
        token = store.begin(
            document_id="doc_alpha",
            tool="preview_change",
            title="Preview",
            cancellable=True,
            operation_id="op_linked",
        )

        active = store.operation_summaries(active_limit=1, recent_limit=1)
        self.assertEqual(active["activeCount"], 1)
        self.assertEqual(active["active"][0]["operationId"], "op_linked")
        store.complete(token, ok=True, summary="Done")
        recent = store.operation_summaries(active_limit=1, recent_limit=1)
        self.assertEqual(recent["recentCount"], 1)
        self.assertEqual(recent["recent"][0]["operationId"], "op_linked")

    def test_live_lease_never_expires_and_released_orphan_clears_at_thirty_seconds(self) -> None:
        clock = _Clock()
        ids = iter(("activity_live", "activity_orphan"))
        store = OperationActivityStore(
            clock=clock, id_factory=lambda: next(ids)
        )
        live = store.begin(
            document_id="doc_live", tool="live", title="Live"
        )
        clock.value += 300.0
        store.reconcile_orphans(grace_seconds=30.0)
        self.assertEqual(store.current("doc_live").activity_id, live.activity_id)

        orphan = store.begin(
            document_id="doc_orphan", tool="orphan", title="Orphan"
        )
        store.release(orphan)
        clock.value += 29.999
        store.reconcile_orphans(grace_seconds=30.0)
        self.assertEqual(
            store.current("doc_orphan").activity_id, orphan.activity_id
        )
        clock.value += 0.001
        store.reconcile_orphans(grace_seconds=30.0)
        self.assertEqual(store.current("doc_orphan").state, "idle")

    def test_server_session_reset_preserves_subscribers_and_rejects_stale_updates(self) -> None:
        ids = iter(("activity_old", "activity_new"))
        store = OperationActivityStore(id_factory=lambda: next(ids))
        observed = []
        store.subscribe(observed.append)
        old = store.begin(document_id="doc_alpha", tool="old", title="Old")

        store.reset_session()
        old_snapshot = store.advance(old, "late", "Late old update")
        self.assertEqual(old_snapshot.phase, "session_ended")
        self.assertEqual(store.current("doc_alpha").state, "idle")
        new = store.begin(document_id="doc_alpha", tool="new", title="New")

        self.assertGreater(new.session_generation, old.session_generation)
        self.assertEqual(observed[-1].activity_id, new.activity_id)

    def test_core_activity_module_has_no_native_ui_imports(self) -> None:
        source = (V2_SOURCE / "glyphs_mcp_v2" / "activity.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import AppKit", source)
        self.assertNotIn("from AppKit", source)
        self.assertNotIn("import GlyphsApp", source)
        self.assertNotIn("from GlyphsApp", source)

    def test_palette_document_scope_reuses_the_palette_font_binding(self) -> None:
        source = (V2_SOURCE / "glyphs_mcp_v2" / "inspector_palette.py").read_text(
            encoding="utf-8"
        )
        inspector_scope = source.split("class GlyphsMCPInspectorPalette", 1)[1]
        document_scope = inspector_scope.split("def _document_id(self):", 1)[1].split(
            "def _activity_changed", 1
        )[0]
        self.assertIn("font = self._font()", document_scope)
        self.assertNotIn("document.font()", document_scope)

    def test_capsule_anchors_to_the_palette_native_window(self) -> None:
        source = (V2_SOURCE / "glyphs_mcp_v2" / "inspector_palette.py").read_text(
            encoding="utf-8"
        )
        window_scope = source.split("def _document_window(self):", 1)[1].split(
            "def _show_capsule", 1
        )[0]
        self.assertIn("return self.dialog.window()", window_scope)
        self.assertNotIn("controller.window()", window_scope)

    def test_collapsed_palette_retains_its_document_presentation_binding(self) -> None:
        source = (V2_SOURCE / "glyphs_mcp_v2" / "inspector_palette.py").read_text(
            encoding="utf-8"
        )
        inspector_scope = source.split("class GlyphsMCPInspectorPalette", 1)[1]
        document_scope = inspector_scope.split("def _document_id(self):", 1)[1].split(
            "def _activity_changed", 1
        )[0]
        self.assertIn("self._activity_document_id = document_id", document_scope)
        self.assertIn("return self._activity_document_id", document_scope)
        self.assertIn("window = self.dialog.window()", document_scope)
        self.assertIn("if window is None:", document_scope)

    def test_cold_hidden_palette_resolves_font_from_its_native_window(self) -> None:
        source = (V2_SOURCE / "glyphs_mcp_v2" / "inspector_palette.py").read_text(
            encoding="utf-8"
        )
        inspector_scope = source.split("class GlyphsMCPInspectorPalette", 1)[1]
        document_scope = inspector_scope.split("def _document_id(self):", 1)[1].split(
            "def _activity_changed", 1
        )[0]
        self.assertIn("font = self._font() or _font_from_window(window)", document_scope)
        self.assertIn("def _font_from_window(window):", source)

    def test_unified_inspector_uses_the_compact_metadata_layout(self) -> None:
        source = (V2_SOURCE / "glyphs_mcp_v2" / "inspector_palette.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("COMPACT_METADATA_HEIGHT = 190", source)
        self.assertIn("STATUS_HEIGHT = 28", source)
        self.assertIn(
            "PALETTE_HEIGHT = COMPACT_METADATA_HEIGHT + STATUS_HEIGHT", source
        )
        self.assertIn("self.scrollView.setFrame_", source)
        self.assertNotIn("PALETTE_HEIGHT = METADATA_HEIGHT + STATUS_HEIGHT", source)

    def test_palette_header_discreetly_uses_the_runtime_version(self) -> None:
        source = (V2_SOURCE / "glyphs_mcp_v2" / "inspector_palette.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("from .versions import palette_display_name", source)
        self.assertIn(
            'objectForInfoDictionaryKey_("CFBundleVersion")',
            source,
        )
        self.assertNotIn("4004", source)

    def test_comparison_reference_is_a_separate_native_palette_section(self) -> None:
        source = (V2_SOURCE / "glyphs_mcp_v2" / "inspector_palette.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("class GlyphsMCPComparisonReferencePalette", source)
        self.assertIn('self.name = "Comparison Reference"', source)
        self.assertIn("REFERENCE_PALETTE_HEIGHT = 52", source)
        inspector_scope = source.split("class GlyphsMCPInspectorPalette", 1)[1]
        self.assertNotIn("_reference_", inspector_scope)

    def test_palette_header_normalizes_the_glyphs_build_number(self) -> None:
        self.assertEqual(
            palette_display_name(4004.0),
            "Glyphs MCP · 2.0.0 (4004)",
        )
        self.assertEqual(
            palette_display_name("4004.1"),
            "Glyphs MCP · 2.0.0 (4004.1)",
        )
        self.assertEqual(palette_display_name(None), "Glyphs MCP · 2.0.0")

    def test_terminal_errors_linger_briefly_then_return_to_ready(self) -> None:
        source = (V2_SOURCE / "glyphs_mcp_v2" / "inspector_palette.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ERROR_LINGER_SECONDS", source)
        self.assertIn(
            'snapshot.state in ("success", "cancelled", "error")', source
        )
        self.assertIn(
            'snapshot.state == "error"\n            and snapshot.completed_at is not None',
            source,
        )
        self.assertIn("ORPHAN_GRACE_SECONDS = 30.0", source)
        self.assertIn("self._activity_store.reconcile_orphans(", source)

    def test_palette_has_a_tiny_dot_without_growing_the_status_row(self) -> None:
        source = (V2_SOURCE / "glyphs_mcp_v2" / "inspector_palette.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("dot = NSView.alloc().initWithFrame_(", source)
        self.assertIn(
            "NSMakeRect(10, ((STATUS_HEIGHT - 7.0) / 2.0) + 1.5, 7.0, 7.0)",
            source,
        )
        self.assertIn("dot.setWantsLayer_(True)", source)
        self.assertIn("dot_layer.setCornerRadius_(3.5)", source)
        self.assertIn(
            "NSColor.secondaryLabelColor().CGColor()",
            source,
        )
        self.assertIn(
            "dot_layer.setBackgroundColor_(color.CGColor())",
            source,
        )
        self.assertNotIn('dot = _quiet_field(NSMakeRect(10, 5, 8, 16), "●", 7.0)', source)
        self.assertNotIn('dot.setStringValue_("●")', source)
        self.assertIn(
            'field = _quiet_field(NSMakeRect(22, 3, 178, 20), tr("palette.ready"), 10.5)',
            source,
        )
        self.assertIn("STATUS_HEIGHT = 28", source)
        self.assertIn("self._status_dot_view = dot", source)

    def test_palette_combines_connection_and_activity_on_the_main_thread(self) -> None:
        source = (V2_SOURCE / "glyphs_mcp_v2" / "inspector_palette.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("default_connection_status_store", source)
        self.assertIn("self._connection_store.subscribe(", source)
        self.assertIn("def _connection_changed(self, _snapshot):", source)
        self.assertIn("NSOperationQueue.mainQueue().addOperationWithBlock_", source)
        self.assertIn("indicator_presentation(", source)
        self.assertIn("connection.state in TRANSITIONAL_CONNECTION_STATES", source)
        self.assertIn("self._connection_unsubscribe = None", source)

    def test_palette_pulse_uses_the_window_cadence_and_cleans_up(self) -> None:
        source = (V2_SOURCE / "glyphs_mcp_v2" / "inspector_palette.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("STATUS_DOT_PULSE_SECONDS = 0.55", source)
        self.assertIn('"statusDotPulse:"', source)
        self.assertIn("dot.setAlphaValue_(0.35 if dim else 1.0)", source)
        self.assertIn("if not self._palette_is_visible():", source)
        self.assertIn("self._stop_status_dot_pulse()", source)
        self.assertIn('"magenta": ("systemPinkColor", "magentaColor")', source)


if __name__ == "__main__":
    unittest.main()
