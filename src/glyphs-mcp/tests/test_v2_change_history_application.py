"""Generic preview/apply/history/revert application qualification."""

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
from glyphs_mcp_v2.semantic import fingerprint_model  # noqa: E402


DOCUMENT_ID = "doc_history"


def _model() -> dict:
    return {
        "font": {"familyName": "History App", "upm": 1000},
        "masters": [{"id": "m0", "name": "Regular"}],
        "instances": [],
        "glyphs": {
            "A": {
                "id": "id_A",
                "name": "A",
                "export": True,
                "layers": [
                    {
                        "id": "layer_A_m0",
                        "masterId": "m0",
                        "isMasterLayer": True,
                        "isSpecialLayer": False,
                        "roles": ["master"],
                        "width": 500,
                        "shapes": [],
                        "anchors": [],
                    }
                ],
            }
        },
        "kerning": {},
        "features": [],
        "classes": [],
        "featurePrefixes": [],
    }


def _glyph_selector() -> dict:
    return {"entity": "glyph", "ids": ["A"]}


class _Host:
    def __init__(self) -> None:
        self.model = _model()
        self.apply_calls = 0
        self.restore_calls = 0

    def capture_model(self, _document_id: str) -> dict:
        return copy.deepcopy(self.model)

    def apply_change_set(self, _document_id: str, change_set) -> None:
        self.apply_calls += 1
        self.model = change_set.apply(self.model)

    def restore_model(self, _document_id: str, model: dict) -> None:
        self.restore_calls += 1
        self.model = copy.deepcopy(model)


class ChangeHistoryApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.host = _Host()
        self.history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        self.app = GlyphsMCPApplication(self.host, history=self.history)

    def _preview(self, value: bool) -> dict:
        return self.app.invoke(
            "preview_change",
            {
                "documentId": DOCUMENT_ID,
                "expectedDocumentFingerprint": fingerprint_model(self.host.model),
                "operations": [
                    {
                        "op": "set",
                        "target": _glyph_selector(),
                        "field": "export",
                        "value": value,
                    }
                ],
                "constraints": [],
            },
        ).to_dict()

    def _apply(self, value: bool) -> dict:
        before = fingerprint_model(self.host.model)
        preview = self._preview(value)
        self.assertTrue(preview["ok"], preview)
        return self.app.invoke(
            "apply_change",
            {
                "documentId": DOCUMENT_ID,
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before,
                "reason": "qualify generic history",
            },
        ).to_dict()

    def test_apply_records_one_public_history_entry_and_bounded_diff(self) -> None:
        applied = self._apply(False)
        self.assertTrue(applied["ok"], applied)
        self.assertEqual(self.host.apply_calls, 1)

        listed = self.app.invoke(
            "list_history", {"documentId": DOCUMENT_ID, "pageSize": 100}
        ).to_dict()
        self.assertTrue(listed["ok"], listed)
        changed = [item for item in listed["data"]["commits"] if item["changed"]]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]["tool"], "apply_change")
        self.assertEqual(changed[0]["operationId"], applied["data"]["operationId"])

        inspected = self.app.invoke(
            "get_operation",
            {"operationId": applied["data"]["operationId"], "pageSize": 100},
        ).to_dict()
        self.assertTrue(inspected["ok"], inspected)
        self.assertEqual(inspected["data"]["kind"], "mutation_diff")
        self.assertGreater(len(inspected["data"]["payload"]["changes"]), 0)

    def test_revert_preserves_unrelated_later_state(self) -> None:
        applied = self._apply(False)
        self.host.model["font"]["designer"] = "Unrelated"
        before_revert = fingerprint_model(self.host.model)

        reverted = self.app.invoke(
            "revert_change",
            {
                "documentId": DOCUMENT_ID,
                "operationId": applied["data"]["operationId"],
                "expectedDocumentFingerprint": before_revert,
            },
        ).to_dict()
        self.assertTrue(reverted["ok"], reverted)
        self.assertTrue(self.host.model["glyphs"]["A"]["export"])
        self.assertEqual(self.host.model["font"]["designer"], "Unrelated")

    def test_revert_refuses_an_overlapping_later_change(self) -> None:
        applied = self._apply(False)
        self.host.model["glyphs"]["A"]["export"] = "later-conflict"

        reverted = self.app.invoke(
            "revert_change",
            {
                "documentId": DOCUMENT_ID,
                "operationId": applied["data"]["operationId"],
                "expectedDocumentFingerprint": fingerprint_model(self.host.model),
            },
        ).to_dict()
        self.assertFalse(reverted["ok"])
        self.assertEqual(reverted["error"]["code"], "revert_conflict")
        self.assertEqual(self.host.model["glyphs"]["A"]["export"], "later-conflict")

    def test_noop_preview_applies_without_a_transaction_or_revert(self) -> None:
        applied = self._apply(True)
        self.assertTrue(applied["ok"], applied)
        self.assertEqual(applied["data"]["transactionCount"], 0)
        self.assertFalse(applied["data"]["revert"]["available"])
        self.assertEqual(self.host.apply_calls, 0)


if __name__ == "__main__":
    unittest.main()
