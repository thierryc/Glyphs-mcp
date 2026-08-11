"""Pure UI-model and native panel source tests for Glyphs MCP Changes."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


RESOURCES = (
    Path(__file__).resolve().parent.parent
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)


def _load_model():
    spec = importlib.util.spec_from_file_location(
        "glyphs_mcp_test_document_changes_panel_model",
        RESOURCES / "document_changes_panel_model.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DocumentChangesPanelModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = _load_model()

    @staticmethod
    def _snapshot(entries=None, omitted=0):
        return {
            "status": "active" if entries else "idle",
            "counts": {
                "changed": 2,
                "succeeded": 1,
                "failed": 1,
                "uncertain": 1,
                "saved": 1,
            },
            "entries": list(entries or []),
            "omittedEntryCount": omitted,
        }

    def test_empty_active_failed_and_uncertain_states(self):
        empty = self._snapshot()
        self.assertEqual(self.model.panel_rows(empty), [])
        self.assertIn("No document", self.model.header_text(empty))
        events = [
            {
                "eventId": "event-1",
                "timestamp": "2026-08-11T10:20:30Z",
                "tool": "delete_glyph",
                "title": "Delete Glyph",
                "outcome": "failed",
                "summary": "Glyph was protected.",
                "target": {"glyphName": "a"},
                "warnings": ["No changes were applied."],
            },
            {
                "eventId": "event-2",
                "timestamp": "2026-08-11T10:21:30Z",
                "tool": "execute_code_with_context",
                "outcome": "uncertain",
                "summary": "Opaque operation.",
                "opaque": True,
                "target": {"glyphNames": ["b", "c"]},
            },
        ]
        rows = self.model.panel_rows(self._snapshot(events, omitted=5))
        self.assertEqual([row["outcome"] for row in rows], ["Failed", "Uncertain"])
        self.assertEqual(rows[0]["time"], "10:20:30")
        self.assertEqual(rows[1]["target"], "b, c")
        self.assertIn("Warning:", self.model.detail_text(events[0]))
        self.assertIn("opaque", self.model.detail_text(events[1]).lower())
        global_warning = self.model.detail_text(
            None,
            overview_warnings=["One operation was unattributed."],
        )
        self.assertIn("One operation was unattributed.", global_warning)

        active = self._snapshot(events)
        active["target"] = {"familyName": "Audit Sans", "filePath": None}
        active["startedAt"] = "2026-08-11T10:20:00Z"
        self.assertEqual(
            self.model.header_text(active),
            "Audit Sans — Unsaved document",
        )
        self.assertIn("Started 2026-08-11 10:20:00", self.model.retention_text(active))

    def test_truncated_and_closed_document_states(self):
        truncated = self._snapshot(
            [{"eventId": "event-1", "outcome": "changed", "target": {}}],
            omitted=257,
        )
        self.assertIn("257 earlier event(s) omitted", self.model.retention_text(truncated))

        closed = {
            "status": "idle",
            "target": {},
            "entries": [],
            "counts": {},
            "omittedEntryCount": 0,
        }
        self.assertIn("No document", self.model.header_text(closed))
        self.assertEqual(self.model.panel_rows(closed), [])

    def test_counts_and_target_navigation_are_bounded(self):
        event = {
            "target": {
                "glyphName": "a",
                "glyphNames": ["a"] + ["g{}".format(index) for index in range(100)],
                "sourceGlyph": "source",
                "targetGlyph": "target",
            }
        }
        names = self.model.glyph_names_for_event(event)
        self.assertEqual(names[0], "a")
        self.assertEqual(len(names), 64)
        pair_names = self.model.glyph_names_for_event(
            {"target": {"left": "T", "right": "@MMK_R_V"}}
        )
        self.assertEqual(pair_names, ["T"])
        counts = self.model.counts_text(self._snapshot([event]))
        self.assertIn("Changed 2", counts)
        self.assertIn("Saves 1", counts)

    def test_panel_source_marshals_refreshes_to_main_thread(self):
        source = (RESOURCES / "document_changes_panel.py").read_text(encoding="utf-8")
        self.assertIn("NSThread.isMainThread()", source)
        self.assertIn("NSOperationQueue.mainQueue().addOperationWithBlock_(self.refresh)", source)
        self.assertIn("DOCUMENTCLOSED", source)
        self.assertIn("NSTimer.scheduledTimerWithTimeInterval", source)

    def test_milestone_ui_strings_cover_all_requested_locales(self):
        spec = importlib.util.spec_from_file_location(
            "glyphs_mcp_test_document_changes_i18n",
            RESOURCES / "i18n.py",
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        expected = {"en", "de", "fr", "es", "pt", "zh-Hans"}
        milestone = {
            key: translations
            for key, translations in module.STRINGS.items()
            if key == "menu.changes" or key.startswith("changes.")
        }
        self.assertTrue(milestone)
        for key, translations in milestone.items():
            with self.subTest(key=key):
                self.assertEqual(set(translations), expected)


if __name__ == "__main__":
    unittest.main()
