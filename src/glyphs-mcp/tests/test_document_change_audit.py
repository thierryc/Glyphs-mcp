"""Pure tests for the bounded one-document MCP change ledger."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import threading
import unittest


def _load_module():
    path = (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
        / "document_change_audit.py"
    )
    spec = importlib.util.spec_from_file_location("glyphs_mcp_test_document_change_audit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DocumentChangeAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_module()

    @staticmethod
    def _target(object_id=10, path=None):
        return {
            "objectId": object_id,
            "fontIndex": 0,
            "familyName": "Audit Sans",
            "filePath": path,
            "fileState": "Saved" if path else "Unsaved",
        }

    @staticmethod
    def _event(outcome="changed", tool="update_glyph_metrics"):
        return {
            "tool": tool,
            "title": "Update Glyph Metrics",
            "effect": "edit",
            "outcome": outcome,
            "target": {"glyphName": "a", "masterId": "M1"},
            "summary": "Changed width from 500 to 520.",
        }

    def test_idle_then_automatic_single_document_binding(self):
        ledger = self.module.DocumentChangeLedger()
        self.assertEqual(ledger.snapshot()["status"], "idle")

        self.assertTrue(ledger.record(self._target(), self._event()))
        snapshot = ledger.snapshot()
        self.assertEqual(snapshot["status"], "active")
        self.assertEqual(snapshot["target"]["familyName"], "Audit Sans")
        self.assertNotIn("objectId", snapshot["target"])
        self.assertEqual(snapshot["counts"]["changed"], 1)
        self.assertEqual(snapshot["entries"][0]["target"]["glyphName"], "a")

    def test_second_document_is_counted_but_not_recorded(self):
        ledger = self.module.DocumentChangeLedger()
        ledger.record(self._target(10), self._event())
        self.assertFalse(ledger.record(self._target(11), self._event(tool="delete_glyph")))
        snapshot = ledger.snapshot()
        self.assertEqual(len(snapshot["entries"]), 1)
        self.assertEqual(snapshot["crossDocumentAttemptCount"], 1)
        self.assertIn("another open document", snapshot["warnings"][0])

    def test_capacity_preserves_aggregate_counts(self):
        ledger = self.module.DocumentChangeLedger(capacity=2)
        for index in range(4):
            event = self._event(outcome="succeeded", tool="tool_{}".format(index))
            ledger.record(self._target(), event)
        snapshot = ledger.snapshot(limit=100)
        self.assertEqual(snapshot["counts"]["succeeded"], 4)
        self.assertEqual(snapshot["omittedEntryCount"], 2)
        self.assertEqual([event["tool"] for event in snapshot["entries"]], ["tool_2", "tool_3"])

    def test_save_updates_target_and_last_save(self):
        ledger = self.module.DocumentChangeLedger()
        ledger.record(self._target(), self._event())
        saved_target = self._target(path="/tmp/AuditSans.glyphs")
        ledger.record(
            saved_target,
            {
                "tool": "save_font",
                "title": "Save Font",
                "effect": "save",
                "outcome": "saved",
                "summary": "Saved the tracked document.",
            },
        )
        snapshot = ledger.snapshot()
        self.assertEqual(snapshot["target"]["filePath"], "/tmp/AuditSans.glyphs")
        self.assertEqual(snapshot["counts"]["saved"], 1)
        self.assertEqual(snapshot["lastSave"]["filePath"], "/tmp/AuditSans.glyphs")

    def test_unattributed_code_warning_does_not_start_session(self):
        ledger = self.module.DocumentChangeLedger()
        ledger.record_unattributed()
        snapshot = ledger.snapshot()
        self.assertEqual(snapshot["status"], "idle")
        self.assertEqual(snapshot["unattributedOperationCount"], 1)
        self.assertIn("could not be attributed", snapshot["warnings"][0])

    def test_reset_and_document_close_clear_only_audit_state(self):
        ledger = self.module.DocumentChangeLedger()
        ledger.record(self._target(), self._event())
        self.assertFalse(ledger.document_closed(99))
        self.assertEqual(ledger.snapshot()["status"], "active")
        self.assertTrue(ledger.document_closed(10))
        self.assertEqual(ledger.snapshot()["status"], "idle")

        ledger.record(self._target(), self._event())
        ledger.reset()
        self.assertEqual(ledger.snapshot()["counts"]["changed"], 0)

    def test_output_is_bounded_and_markdown_is_portable(self):
        ledger = self.module.DocumentChangeLedger()
        event = self._event()
        event["summary"] = "x" * 900
        event["warnings"] = ["warning-{}".format(index) for index in range(20)]
        ledger.record(self._target(), event)
        snapshot = ledger.snapshot(limit=500)
        self.assertEqual(len(snapshot["entries"][0]["summary"]), 500)
        self.assertEqual(len(snapshot["entries"][0]["warnings"]), 8)
        markdown = self.module.overview_markdown(snapshot)
        self.assertIn("# Glyphs MCP Changes", markdown)
        self.assertIn("Audit Sans", markdown)
        self.assertIn("Update Glyph Metrics", markdown)

    def test_limit_reports_retained_entries_not_returned(self):
        ledger = self.module.DocumentChangeLedger(capacity=10)
        for index in range(4):
            ledger.record(self._target(), self._event(tool="tool_{}".format(index)))
        snapshot = ledger.snapshot(limit=2)
        self.assertEqual([event["tool"] for event in snapshot["entries"]], ["tool_2", "tool_3"])
        self.assertEqual(snapshot["omittedEntryCount"], 2)
        without_entries = ledger.snapshot(include_entries=False)
        self.assertEqual(without_entries["omittedEntryCount"], 4)

    def test_return_limit_clamps_to_one_through_one_hundred(self):
        ledger = self.module.DocumentChangeLedger(capacity=150)
        for index in range(120):
            ledger.record(self._target(), self._event(tool="tool_{}".format(index)))
        self.assertEqual(len(ledger.snapshot(limit=1000)["entries"]), 100)
        self.assertEqual(len(ledger.snapshot(limit=0)["entries"]), 1)

    def test_concurrent_writers_preserve_counts_and_event_order(self):
        ledger = self.module.DocumentChangeLedger(capacity=256)

        def record_batch(batch):
            for index in range(100):
                ledger.record(
                    self._target(),
                    self._event(tool="batch_{}_{}".format(batch, index)),
                )

        threads = [threading.Thread(target=record_batch, args=(batch,)) for batch in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        snapshot = ledger.snapshot(limit=100)
        self.assertEqual(snapshot["counts"]["changed"], 400)
        self.assertEqual(snapshot["omittedEntryCount"], 300)
        event_numbers = [int(event["eventId"].split("-")[1]) for event in snapshot["entries"]]
        self.assertEqual(event_numbers, sorted(event_numbers))


if __name__ == "__main__":
    unittest.main()
