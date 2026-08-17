"""Application tracing, save reset, and safe semantic revert contracts."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.canonical_tree import CanonicalFontTree, MemoryObjectStore  # noqa: E402
from glyphs_mcp_v2.change_history import ChangeHistory  # noqa: E402
from glyphs_mcp_v2.change_lifecycle import DocumentHistoryLifecycle  # noqa: E402
from glyphs_mcp_v2.semantic import fingerprint_model  # noqa: E402


def _model() -> dict:
    return {
        "font": {"familyName": "History App", "upm": 1000},
        "masters": [{"id": "m0", "name": "Regular"}],
        "instances": [],
        "glyphs": {"A": {"name": "A", "id": "id_A", "export": True, "layers": {}}},
        "kerning": {}, "features": [], "classes": [], "featurePrefixes": [],
    }


class _Host:
    def __init__(self) -> None:
        self.model = _model()
        self.apply_calls = 0
        self.restore_calls = 0

    def capture_model(self, document_id):
        return copy.deepcopy(self.model)

    def apply_change_set(self, document_id, change_set):
        self.apply_calls += 1
        self.model = change_set.apply(self.model)

    def restore_model(self, document_id, model):
        self.restore_calls += 1
        self.model = copy.deepcopy(model)


class ChangeHistoryApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.host = _Host()
        self.history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        self.app = GlyphsMCPApplication(self.host, history=self.history)

    def _apply_export_toggle(self) -> dict:
        review = self.app.invoke(
            "review_glyph_updates",
            {"documentId": "doc_history", "updates": [{"glyphName": "A", "export": False}]},
        ).to_dict()
        return self.app.invoke(
            "apply_glyph_updates", {"reviewId": review["data"]["reviewId"], "confirm": True}
        ).to_dict()

    def test_review_and_apply_each_emit_one_linked_tool_call_commit(self) -> None:
        applied = self._apply_export_toggle()
        commits = self.history.list_commits("doc_history")

        self.assertTrue(applied["ok"])
        self.assertEqual([item.tool for item in commits], ["review_glyph_updates", "apply_glyph_updates"])
        self.assertFalse(commits[0].changed)
        self.assertTrue(commits[1].changed)
        self.assertEqual(commits[1].operation_id, applied["operationId"])
        self.assertEqual(self.host.apply_calls, 1)

    def test_generic_revert_preserves_unrelated_later_fields(self) -> None:
        self._apply_export_toggle()
        changed = [item for item in self.history.list_commits("doc_history") if item.changed][0]
        self.host.model["font"]["familyName"] = "Manually Renamed"

        reverted = self.app.invoke(
            "revert_change",
            {
                "documentId": "doc_history",
                "commitId": changed.commit_id,
                "expectedDocumentFingerprint": fingerprint_model(self.host.model),
            },
        ).to_dict()

        self.assertTrue(reverted["ok"])
        self.assertTrue(self.host.model["glyphs"]["A"]["export"])
        self.assertEqual(self.host.model["font"]["familyName"], "Manually Renamed")
        self.assertEqual(self.history.list_commits("doc_history")[-1].tool, "revert_change")

    def test_generic_revert_refuses_conflicting_later_edit(self) -> None:
        self._apply_export_toggle()
        changed = [item for item in self.history.list_commits("doc_history") if item.changed][0]
        self.host.model["glyphs"]["A"]["export"] = "manual-conflict"

        reverted = self.app.invoke(
            "revert_change",
            {
                "documentId": "doc_history",
                "commitId": changed.commit_id,
                "expectedDocumentFingerprint": fingerprint_model(self.host.model),
            },
        ).to_dict()

        self.assertFalse(reverted["ok"])
        self.assertEqual(reverted["error"]["code"], "revert_conflict")
        self.assertEqual(self.host.apply_calls, 1)

    def test_verified_save_event_resets_only_its_document_history(self) -> None:
        self._apply_export_toggle()
        other_before = _model()
        other_after = copy.deepcopy(other_before)
        other_after["font"]["familyName"] = "Other"
        self.history.record_action(
            document_id="doc_other", tool="edit", effect="edit", status="success", run_id="run_other",
            before_model=other_before, after_model=other_after,
        )
        lifecycle = DocumentHistoryLifecycle(self.history)
        lifecycle.document_was_saved("doc_history", make_copy=False, succeeded=True)

        self.assertEqual(self.history.list_commits("doc_history"), ())
        self.assertEqual(len(self.history.list_commits("doc_other")), 1)

    def test_save_copy_or_failed_save_does_not_reset_history(self) -> None:
        self._apply_export_toggle()
        lifecycle = DocumentHistoryLifecycle(self.history)
        lifecycle.document_was_saved("doc_history", make_copy=True, succeeded=True)
        lifecycle.document_was_saved("doc_history", make_copy=False, succeeded=False)
        self.assertEqual(len(self.history.list_commits("doc_history")), 2)


if __name__ == "__main__":
    unittest.main()
