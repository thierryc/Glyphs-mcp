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

    def test_latest_active_operation_wins_without_losing_older_work(self) -> None:
        ids = iter(("activity_one", "activity_two"))
        store = OperationActivityStore(id_factory=lambda: next(ids))
        first = store.begin(document_id="doc_alpha", tool="one", title="One")
        second = store.begin(document_id="doc_alpha", tool="two", title="Two")

        self.assertEqual(store.current("doc_alpha").activity_id, second.activity_id)
        store.complete(second, ok=True, summary="Two done")
        self.assertEqual(store.current("doc_alpha").activity_id, first.activity_id)
        store.complete(first, ok=True, summary="One done")
        self.assertEqual(store.current("doc_alpha").state, "success")

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
        document_scope = source.split("def _document_id(self):", 1)[1].split(
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


if __name__ == "__main__":
    unittest.main()
