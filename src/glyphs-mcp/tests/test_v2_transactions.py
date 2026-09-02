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
from glyphs_mcp_v2.canonical_tree import CanonicalFontTree, MemoryObjectStore  # noqa: E402
from glyphs_mcp_v2.change_history import ChangeHistory  # noqa: E402
from glyphs_mcp_v2.change_lifecycle import DocumentHistoryLifecycle  # noqa: E402
from glyphs_mcp_v2.mutation import VerifiedMutationPlan  # noqa: E402
from glyphs_mcp_v2.transactions import (  # noqa: E402
    DocumentQuarantinedError,
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
        self.source_state = {
            "kind": "glyphs",
            "exists": True,
            "contentFingerprint": "sha256:before",
        }
        self.change_source_on_apply = False

    def capture_model(self, document_id):
        return copy.deepcopy(self.model)

    def apply_change_set(self, document_id, change_set):
        self.apply_calls += 1
        self.model = change_set.apply(self.model)
        if self.corrupt_apply:
            self.model["font"]["familyName"] = "Corrupt"
        if self.change_source_on_apply:
            self.source_state["contentFingerprint"] = "sha256:after"

    def restore_model(self, document_id, model):
        self.restore_calls += 1
        if self.fail_restore:
            raise RuntimeError("restore failed")
        self.model = copy.deepcopy(model)

    def capture_source_file_state(self, document_id, include_model=False):
        result = copy.deepcopy(self.source_state)
        if include_model and isinstance(result.get("savedModel"), dict):
            result["savedModel"] = copy.deepcopy(result["savedModel"])
        return result


class _SaveTimingAdapter(_DocumentAdapter):
    def __init__(self, model, lifecycle, mode) -> None:
        super().__init__(model)
        self.initial = copy.deepcopy(model)
        self.lifecycle = lifecycle
        self.mode = mode
        self.save_index = 0

    def _save(self, model):
        self.save_index += 1
        self.source_state = {
            "kind": "glyphs",
            "exists": True,
            "readable": True,
            "filePath": "/fonts/SaveTiming.glyphs",
            "contentFingerprint": "sha256:save-{}".format(self.save_index),
            "savedModel": copy.deepcopy(model),
        }
        self.lifecycle.document_was_saved(
            "doc_alpha",
            source_state=self.source_state,
            saved_model=model,
        )

    def apply_change_set(self, document_id, change_set):
        self.apply_calls += 1
        if self.mode in {"saved_before", "multiple"}:
            self._save(self.model)
        if self.mode == "saved_intermediate":
            middle = copy.deepcopy(self.model)
            middle["font"]["familyName"] = "Middle"
            self.model = middle
            self._save(middle)
        self.model = change_set.apply(
            self.model if self.mode != "saved_intermediate" else self.initial
        )
        if self.mode in {"saved_after", "multiple"}:
            self._save(self.model)
        if self.mode == "delayed":
            self.save_index += 1
            self.source_state = {
                "kind": "glyphs",
                "exists": True,
                "readable": True,
                "filePath": "/fonts/SaveTiming.glyphs",
                "contentFingerprint": "sha256:save-{}".format(self.save_index),
                "savedModel": copy.deepcopy(self.model),
            }
        if self.mode == "failure_after_save":
            self._save(self.model)
            self.model["font"]["familyName"] = "Corrupt"

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
        self.assertIn("settled_verification failed:", str(caught.exception))
        self.assertIn("['font', 'familyName']", str(caught.exception))
        self.assertIn("'actual': 'Corrupt'", str(caught.exception))
        self.assertIn("'expected': 'Beta'", str(caught.exception))
        self.assertEqual(adapter.model, self.before)
        self.assertEqual(adapter.restore_calls, 1)
        evidence = caught.exception.to_public_dict()["failureEvidence"]
        self.assertEqual(evidence["phase"], "settled_verification")
        self.assertEqual(evidence["causeType"], "RuntimeError")
        self.assertEqual(
            kernel.document_transaction_state("doc_alpha")["state"], "restored"
        )

    def test_live_apply_failure_names_its_transaction_phase(self) -> None:
        class FailingApplyAdapter(_DocumentAdapter):
            def apply_change_set(self, document_id, change_set):
                self.apply_calls += 1
                raise RuntimeError("native setter failed")

        adapter = FailingApplyAdapter(self.before)
        kernel = TransactionKernel(adapter)

        with self.assertRaises(TransactionVerificationError) as caught:
            kernel.apply(
                document_id="doc_alpha",
                expected_fingerprint=fingerprint_model(self.before),
                change_set=diff_models(self.before, self.after),
            )

        self.assertTrue(caught.exception.rollback_succeeded)
        self.assertIn(
            "live_apply failed: native setter failed", str(caught.exception)
        )
        diagnostic = kernel.diagnostic_failure_traceback()
        self.assertIn("native setter failed", diagnostic)
        self.assertIn("apply_change_set", diagnostic)

    def test_verification_failure_reports_the_restore_failure(self) -> None:
        adapter = _DocumentAdapter(self.before)
        adapter.corrupt_apply = True
        adapter.fail_restore = True
        kernel = TransactionKernel(adapter)

        with self.assertRaises(TransactionVerificationError) as caught:
            kernel.apply(
                document_id="doc_alpha",
                expected_fingerprint=fingerprint_model(self.before),
                change_set=diff_models(self.before, self.after),
            )

        self.assertFalse(caught.exception.rollback_succeeded)
        self.assertTrue(caught.exception.state_may_have_changed)
        self.assertEqual(caught.exception.observed_change_count, 1)
        self.assertEqual(
            caught.exception.observed_after_fingerprint,
            fingerprint_model(adapter.model),
        )
        self.assertIn("rollback failed: restore failed", str(caught.exception))
        self.assertEqual(adapter.restore_calls, 1)
        self.assertEqual(
            kernel.document_transaction_state("doc_alpha")["state"],
            "indeterminate",
        )
        with self.assertRaises(DocumentQuarantinedError):
            kernel.apply(
                document_id="doc_alpha",
                expected_fingerprint=fingerprint_model(adapter.model),
                change_set=diff_models(adapter.model, self.after),
            )
        self.assertEqual(adapter.apply_calls, 1)

    def test_failed_restore_that_proves_exact_after_is_classified_committed(self) -> None:
        class FailingObserver:
            def prepare_transaction(self, document_id, before):
                return "trace"

            def commit_transaction(self, *arguments, **keywords):
                raise RuntimeError("history write failed")

            def abort_transaction(self, token):
                pass

        adapter = _DocumentAdapter(self.before)
        adapter.fail_restore = True
        kernel = TransactionKernel(adapter, observer=FailingObserver())

        with self.assertRaises(TransactionVerificationError) as caught:
            kernel.apply(
                document_id="doc_alpha",
                expected_fingerprint=fingerprint_model(self.before),
                change_set=diff_models(self.before, self.after),
            )

        self.assertEqual(adapter.model, self.after)
        self.assertEqual(
            caught.exception.to_public_dict()["rollbackClassification"],
            "exact_committed",
        )
        self.assertEqual(
            kernel.document_transaction_state("doc_alpha")["state"],
            "committed",
        )

    def test_verified_mutation_observes_unchanged_source_content(self) -> None:
        adapter = _DocumentAdapter(self.before)

        result = TransactionKernel(adapter).apply(
            document_id="doc_alpha",
            expected_fingerprint=fingerprint_model(self.before),
            change_set=diff_models(self.before, self.after),
        )

        self.assertFalse(result.source_file_changed)
        self.assertEqual(
            adapter.source_state["contentFingerprint"], "sha256:before"
        )

    def test_source_change_is_reported_without_rolling_back_verified_live_state(self) -> None:
        adapter = _DocumentAdapter(self.before)
        adapter.change_source_on_apply = True

        result = TransactionKernel(adapter).apply(
            document_id="doc_alpha",
            expected_fingerprint=fingerprint_model(self.before),
            change_set=diff_models(self.before, self.after),
        )

        self.assertEqual(adapter.model, self.after)
        self.assertTrue(result.source_file_changed)
        self.assertEqual(
            result.persistence_reconciliation["relationship"],
            "source_changed_unclassified",
        )

    def test_unclassified_source_drift_does_not_erase_existing_history(self) -> None:
        history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        seed_after = copy.deepcopy(self.before)
        seed_after["font"]["designer"] = "Earlier"
        seed = history.record_action(
            document_id="doc_alpha",
            tool="apply_change",
            effect="edit",
            status="success",
            run_id="run_seed",
            before_model=self.before,
            after_model=seed_after,
        )
        lifecycle = DocumentHistoryLifecycle(history)
        adapter = _DocumentAdapter(self.before)
        adapter.change_source_on_apply = True

        result = TransactionKernel(
            adapter, persistence=lifecycle
        ).apply(
            document_id="doc_alpha",
            expected_fingerprint=fingerprint_model(self.before),
            change_set=diff_models(self.before, self.after),
        )

        self.assertEqual(
            result.persistence_reconciliation["relationship"],
            "source_changed_unclassified",
        )
        self.assertFalse(result.persistence_reconciliation["saveObserved"])
        self.assertEqual(
            [commit.commit_id for commit in history.list_commits("doc_alpha")],
            [seed.commit_id],
        )

    def _save_timing_transaction(self, mode, *, after=None):
        resets = []
        history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        lifecycle = DocumentHistoryLifecycle(
            history, reset_tracking=resets.append
        )
        adapter = _SaveTimingAdapter(self.before, lifecycle, mode)
        target = copy.deepcopy(after or self.after)
        result = TransactionKernel(
            adapter, persistence=lifecycle
        ).apply(
            document_id="doc_alpha",
            expected_fingerprint=fingerprint_model(self.before),
            change_set=diff_models(self.before, target),
        )
        return result, adapter, lifecycle, resets, target

    def test_save_before_mutation_keeps_the_complete_change_unsaved(self) -> None:
        result, adapter, _lifecycle, resets, target = (
            self._save_timing_transaction("saved_before")
        )

        self.assertEqual(adapter.model, target)
        self.assertEqual(
            result.persistence_reconciliation["relationship"], "saved_before"
        )
        self.assertEqual(result.history_change_count, 1)
        self.assertTrue(result.revert_available)
        self.assertEqual(resets, [])

    def test_save_after_mutation_audits_without_unsaved_history(self) -> None:
        result, adapter, _lifecycle, resets, target = (
            self._save_timing_transaction("saved_after")
        )

        self.assertEqual(adapter.model, target)
        self.assertEqual(
            result.persistence_reconciliation["relationship"], "saved_after"
        )
        self.assertEqual(result.history_change_count, 0)
        self.assertFalse(result.revert_available)
        self.assertEqual(resets, [])

    def test_intermediate_save_rebases_history_to_the_residual_change(self) -> None:
        target = copy.deepcopy(self.after)
        target["font"]["upm"] = 1200
        result, adapter, _lifecycle, _resets, target = (
            self._save_timing_transaction("saved_intermediate", after=target)
        )

        self.assertEqual(adapter.model, target)
        self.assertEqual(
            result.persistence_reconciliation["relationship"],
            "saved_intermediate",
        )
        self.assertEqual(result.history_change_count, 2)
        self.assertEqual(
            result.persistence_reconciliation["residualSemanticDiff"][
                "changeCount"
            ],
            2,
        )
        restored = result.inverse.apply(target)
        self.assertEqual(restored["font"]["familyName"], "Middle")
        self.assertEqual(restored["font"]["upm"], 1000)

    def test_multiple_saves_are_all_retained_and_latest_is_the_baseline(self) -> None:
        result, adapter, _lifecycle, _resets, target = (
            self._save_timing_transaction("multiple")
        )

        reconciliation = result.persistence_reconciliation
        self.assertEqual(adapter.model, target)
        self.assertEqual(reconciliation["saveEventCount"], 2)
        self.assertEqual(
            [event["epoch"] for event in reconciliation["saveEvents"]],
            [1, 2],
        )
        self.assertEqual(reconciliation["relationship"], "saved_after")
        self.assertFalse(result.revert_available)

    def test_delayed_callback_does_not_clear_reconciled_history(self) -> None:
        result, adapter, lifecycle, resets, target = (
            self._save_timing_transaction("delayed")
        )

        self.assertEqual(adapter.model, target)
        self.assertEqual(
            result.persistence_reconciliation["relationship"], "saved_after"
        )
        self.assertFalse(
            lifecycle.document_was_saved(
                "doc_alpha",
                source_state=adapter.source_state,
                saved_model=target,
            )
        )
        self.assertEqual(resets, [])

    def test_failed_verification_rolls_back_live_only_and_keeps_save_evidence(self) -> None:
        resets = []
        history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        lifecycle = DocumentHistoryLifecycle(
            history, reset_tracking=resets.append
        )
        adapter = _SaveTimingAdapter(
            self.before, lifecycle, "failure_after_save"
        )

        with self.assertRaises(TransactionVerificationError) as caught:
            TransactionKernel(adapter, persistence=lifecycle).apply(
                document_id="doc_alpha",
                expected_fingerprint=fingerprint_model(self.before),
                change_set=diff_models(self.before, self.after),
            )

        self.assertTrue(caught.exception.rollback_succeeded)
        self.assertEqual(adapter.model, self.before)
        reconciliation = caught.exception.persistence_reconciliation
        self.assertTrue(reconciliation["saveObserved"])
        self.assertEqual(reconciliation["relationship"], "saved_intermediate")
        self.assertTrue(reconciliation["sourceFileChanged"])
        self.assertEqual(reconciliation["residualChangeCount"], 1)
        self.assertEqual(resets, [])

    def test_unexpected_reconciliation_failure_never_leaves_a_save_fence(self) -> None:
        class BrokenReconciliation(DocumentHistoryLifecycle):
            def reconcile_transaction(self, *arguments, **keywords):
                raise RuntimeError("persistence decoder failed")

        resets = []
        history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        lifecycle = BrokenReconciliation(
            history, reset_tracking=resets.append
        )
        adapter = _DocumentAdapter(self.before)

        with self.assertRaises(TransactionVerificationError):
            TransactionKernel(adapter, persistence=lifecycle).apply(
                document_id="doc_alpha",
                expected_fingerprint=fingerprint_model(self.before),
                change_set=diff_models(self.before, self.after),
            )

        self.assertTrue(
            lifecycle.document_was_saved(
                "doc_alpha",
                source_state={
                    "kind": "glyphs",
                    "exists": True,
                    "readable": True,
                    "contentFingerprint": "sha256:later-save",
                },
                saved_model=self.before,
            )
        )
        self.assertEqual(resets, ["doc_alpha"])

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

    def test_live_interface_updates_resume_before_settled_verification(self) -> None:
        class SuspendingAdapter(_DocumentAdapter):
            def __init__(self, model) -> None:
                super().__init__(model)
                self.events = []

            def capture_model(self, document_id):
                self.events.append("capture")
                return super().capture_model(document_id)

            def begin_verified_transaction(self, document_id):
                self.events.append("begin")

            def apply_change_set(self, document_id, change_set):
                self.events.append("apply")
                return super().apply_change_set(document_id, change_set)

            def settle_verified_transaction(self, document_id):
                self.events.append("settle")

            def end_verified_transaction(self, document_id):
                self.events.append("end")

        adapter = SuspendingAdapter(self.before)
        TransactionKernel(adapter).apply(
            document_id="doc_alpha",
            expected_fingerprint=fingerprint_model(self.before),
            change_set=diff_models(self.before, self.after),
        )

        self.assertEqual(
            adapter.events,
            [
                "capture",
                "capture",
                "begin",
                "apply",
                "settle",
                "capture",
                "end",
            ],
        )

    def test_readback_observes_state_derived_when_native_batch_settles(self) -> None:
        class SettlingAdapter(_DocumentAdapter):
            def begin_verified_transaction(self, document_id):
                self.pending = None

            def apply_change_set(self, document_id, change_set):
                self.apply_calls += 1
                self.pending = change_set

            def settle_verified_transaction(self, document_id):
                self.model = self.pending.apply(self.model)

            def end_verified_transaction(self, document_id):
                pass

        result = TransactionKernel(SettlingAdapter(self.before)).apply(
            document_id="doc_alpha",
            expected_fingerprint=fingerprint_model(self.before),
            change_set=diff_models(self.before, self.after),
        )

        self.assertEqual(result.after_fingerprint, fingerprint_model(self.after))

    def test_live_interface_updates_resume_after_failed_verification_and_restore(self) -> None:
        class SuspendingAdapter(_DocumentAdapter):
            def __init__(self, model) -> None:
                super().__init__(model)
                self.events = []

            def capture_model(self, document_id):
                self.events.append("capture")
                return super().capture_model(document_id)

            def begin_verified_transaction(self, document_id):
                self.events.append("begin")

            def apply_change_set(self, document_id, change_set):
                self.events.append("apply")
                return super().apply_change_set(document_id, change_set)

            def restore_model(self, document_id, model):
                self.events.append("restore")
                return super().restore_model(document_id, model)

            def settle_verified_transaction(self, document_id):
                self.events.append("settle")

            def end_verified_transaction(self, document_id):
                self.events.append("end")

        adapter = SuspendingAdapter(self.before)
        adapter.corrupt_apply = True
        with self.assertRaises(TransactionVerificationError):
            TransactionKernel(adapter).apply(
                document_id="doc_alpha",
                expected_fingerprint=fingerprint_model(self.before),
                change_set=diff_models(self.before, self.after),
            )

        self.assertEqual(
            adapter.events,
            [
                "capture",
                "capture",
                "begin",
                "apply",
                "settle",
                "capture",
                "restore",
                "settle",
                "capture",
                "end",
            ],
        )

    def test_transaction_boundary_cleanup_failure_is_exactly_classified(self) -> None:
        class CleanupFailureAdapter(_DocumentAdapter):
            def begin_verified_transaction(self, document_id):
                pass

            def end_verified_transaction(self, document_id):
                raise RuntimeError("interface resume failed")

        adapter = CleanupFailureAdapter(self.before)
        kernel = TransactionKernel(adapter)

        with self.assertRaises(TransactionVerificationError) as caught:
            kernel.apply(
                document_id="doc_alpha",
                expected_fingerprint=fingerprint_model(self.before),
                change_set=diff_models(self.before, self.after),
            )

        self.assertEqual(adapter.model, self.after)
        self.assertEqual(
            caught.exception.to_public_dict()["rollbackClassification"],
            "exact_committed",
        )
        self.assertEqual(
            kernel.document_transaction_state("doc_alpha")["state"],
            "committed",
        )


if __name__ == "__main__":
    unittest.main()
