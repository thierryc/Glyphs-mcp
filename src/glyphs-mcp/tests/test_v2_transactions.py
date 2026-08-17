"""Verified semantic transaction and rollback coverage for v2."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.semantic import ChangeSet, diff_models, fingerprint_model  # noqa: E402
from glyphs_mcp_v2.transactions import (  # noqa: E402
    StaleDocumentError,
    TransactionKernel,
    TransactionVerificationError,
)


class _DocumentAdapter:
    def __init__(self, model) -> None:
        self.model = copy.deepcopy(model)
        self.apply_calls = 0
        self.restore_calls = 0
        self.corrupt_apply = False
        self.fail_restore = False

    def capture_model(self, document_id):
        return copy.deepcopy(self.model)

    def apply_change_set(self, document_id, change_set):
        self.apply_calls += 1
        self.model = change_set.apply(self.model)
        if self.corrupt_apply:
            self.model["font"]["familyName"] = "Corrupt"

    def restore_model(self, document_id, model):
        self.restore_calls += 1
        if self.fail_restore:
            raise RuntimeError("restore failed")
        self.model = copy.deepcopy(model)


class V2TransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.before = {
            "font": {"familyName": "Alpha", "upm": 1000},
            "glyphs": {"A": {"export": True}},
        }
        self.after = copy.deepcopy(self.before)
        self.after["font"]["familyName"] = "Beta"

    def test_one_apply_and_exact_readback(self) -> None:
        adapter = _DocumentAdapter(self.before)
        kernel = TransactionKernel(adapter)
        changes = diff_models(self.before, self.after)

        result = kernel.apply(
            document_id="doc_alpha",
            expected_fingerprint=fingerprint_model(self.before),
            change_set=changes,
        )

        self.assertEqual(adapter.apply_calls, 1)
        self.assertEqual(adapter.model, self.after)
        self.assertEqual(result.after_fingerprint, fingerprint_model(self.after))
        self.assertEqual(result.inverse.apply(self.after), self.before)

    def test_stale_state_is_rejected_without_writes(self) -> None:
        adapter = _DocumentAdapter(self.before)
        kernel = TransactionKernel(adapter)

        with self.assertRaises(StaleDocumentError):
            kernel.apply(
                document_id="doc_alpha",
                expected_fingerprint="sha256:stale",
                change_set=diff_models(self.before, self.after),
            )
        self.assertEqual(adapter.apply_calls, 0)

    def test_verification_failure_restores_the_complete_before_state(self) -> None:
        adapter = _DocumentAdapter(self.before)
        adapter.corrupt_apply = True
        kernel = TransactionKernel(adapter)

        with self.assertRaises(TransactionVerificationError) as caught:
            kernel.apply(
                document_id="doc_alpha",
                expected_fingerprint=fingerprint_model(self.before),
                change_set=diff_models(self.before, self.after),
            )

        self.assertTrue(caught.exception.rollback_succeeded)
        self.assertEqual(adapter.model, self.before)
        self.assertEqual(adapter.restore_calls, 1)

    def test_duplicate_paths_are_invalid(self) -> None:
        with self.assertRaises(ValueError):
            ChangeSet.from_changes(
                before_fingerprint=fingerprint_model(self.before),
                after_fingerprint=fingerprint_model(self.after),
                changes=[
                    {"path": ["font", "familyName"], "before": "Alpha", "after": "Beta"},
                    {"path": ["font", "familyName"], "before": "Alpha", "after": "Gamma"},
                ],
            )

    def test_observer_reuses_transaction_snapshots_without_extra_capture(self) -> None:
        class Observer:
            def __init__(self):
                self.prepared = []
                self.committed = []

            def prepare_transaction(self, document_id, before):
                self.prepared.append((document_id, copy.deepcopy(before)))
                return "trace_token"

            def commit_transaction(self, token, document_id, before, after, change_set):
                self.committed.append((token, document_id, copy.deepcopy(before), copy.deepcopy(after), change_set))

            def abort_transaction(self, token):
                raise AssertionError("successful transaction must not abort its trace")

        adapter = _DocumentAdapter(self.before)
        observer = Observer()
        kernel = TransactionKernel(adapter, observer=observer)
        result = kernel.apply(
            document_id="doc_alpha",
            expected_fingerprint=fingerprint_model(self.before),
            change_set=diff_models(self.before, self.after),
        )

        self.assertEqual(result.after_fingerprint, fingerprint_model(self.after))
        self.assertEqual(len(observer.prepared), 1)
        self.assertEqual(len(observer.committed), 1)
        self.assertEqual(observer.committed[0][2], self.before)
        self.assertEqual(observer.committed[0][3], self.after)
        self.assertEqual(adapter.apply_calls, 1)


if __name__ == "__main__":
    unittest.main()
