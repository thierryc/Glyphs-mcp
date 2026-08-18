"""Staged Python approval, exact apply, rollback, and open-world honesty."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.audit import AuditLog  # noqa: E402
from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.operations import OperationStore  # noqa: E402
from glyphs_mcp_v2.python_execution import (  # noqa: E402
    PythonExecutionRequest,
    PythonExecutionService,
    PythonPolicyError,
    validate_staged_code,
)
from glyphs_mcp_v2.semantic import diff_models, fingerprint_model  # noqa: E402
from glyphs_mcp_v2.transactions import TransactionKernel  # noqa: E402


class _PythonHost:
    def __init__(self) -> None:
        self.model = {"font": {"familyName": "Alpha"}, "glyphs": {}}
        self.preview_calls = 0
        self.live_calls = 0
        self.opened_recovery = []
        self.recovery_paths = []
        self.scope_violations = []
        self.stdout = "live"
        self.preview_scope_violations = []
        self.preview_context_violations = None
        self.corrupt_apply = False
        self.raise_live = False
        self.recovery_registry = {}
        self.native_archive_comparison = {
            "equivalent": True,
            "mismatchCount": 0,
            "mismatchLocations": [],
            "truncated": False,
        }

    def capture_model(self, document_id):
        return copy.deepcopy(self.model)

    def preview_python(self, request, before_model):
        self.preview_calls += 1
        after = copy.deepcopy(before_model)
        if "Beta" in request.code:
            after["font"]["familyName"] = "Beta"
        if "unsupported" in request.code:
            after["unsupported"] = {"native": True}
        if "bulk" in request.code:
            after["glyphs"] = {
                "g{:03d}".format(index): {"export": False}
                for index in range(225)
            }
        if "featureEdit" in request.code:
            after["features"][0]["code"] = "sub f f i by ffi;"
        result = {
            "afterModel": after,
            "stdout": "previewed",
            "stderr": "",
            "scopeViolations": list(self.preview_scope_violations),
            "nativeArchiveComparison": copy.deepcopy(
                self.native_archive_comparison
            ),
        }
        if self.preview_context_violations is not None:
            result["contextViolations"] = copy.deepcopy(
                self.preview_context_violations
            )
        return result

    def run_live_python(self, request):
        self.live_calls += 1
        before = self.capture_model(request.document_id)
        after = copy.deepcopy(before)
        after["unsupported"] = {"native": True}
        self.model = after
        if self.raise_live:
            raise RuntimeError("live failure")
        return {
            "beforeModel": before,
            "afterModel": after,
            "stdout": self.stdout,
            "stderr": "",
            "scopeViolations": list(self.scope_violations),
        }

    def apply_change_set(self, document_id, change_set):
        self.model = change_set.apply(self.model)
        if self.corrupt_apply:
            self.model["font"]["familyName"] = "Corrupt"

    def restore_model(self, document_id, model):
        self.model = copy.deepcopy(model)

    def create_recovery_copy(self, document_id, execution_id):
        path = "/private/recovery/{}.glyphs".format(execution_id)
        self.recovery_paths.append(path)
        return path

    def open_recovery_copy(self, path):
        self.opened_recovery.append(path)

    def register_recovery_checkpoint(self, execution_id, document_id, recovery_path, after_fingerprint):
        self.recovery_registry[execution_id] = {
            "executionId": execution_id,
            "documentId": document_id,
            "recoveryPath": recovery_path,
            "afterFingerprint": after_fingerprint,
        }

    def find_recovery_checkpoint(self, execution_id):
        return self.recovery_registry.get(execution_id)


class _PrecomputedPreviewHost(_PythonHost):
    def preview_python(self, request, before_model):
        result = super().preview_python(request, before_model)
        changes = diff_models(before_model, result["afterModel"])
        result["changeSet"] = changes
        result["writableChangeSet"] = changes
        return result


class _DriftingRollbackPythonHost(_PythonHost):
    """A writable inverse derives a state different from its checkpoint."""

    def __init__(self) -> None:
        super().__init__()
        self.model["glyphs"] = {"A": {"mastersCompatible": False}}

    def preview_python(self, request, before_model):
        self.preview_calls += 1
        after = copy.deepcopy(before_model)
        after["font"]["familyName"] = "Beta"
        after["glyphs"]["A"]["mastersCompatible"] = True
        return {
            "afterModel": after,
            "stdout": "previewed",
            "stderr": "",
            "scopeViolations": [],
            "nativeArchiveComparison": copy.deepcopy(
                self.native_archive_comparison
            ),
        }

    @staticmethod
    def _derive(model):
        result = copy.deepcopy(model)
        family = result["font"]["familyName"]
        result["glyphs"]["A"]["mastersCompatible"] = (
            True if family == "Beta" else None
        )
        return result

    def simulate_change_set(self, document_id, change_set):
        return self._derive(change_set.apply(self.model))

    def apply_change_set(self, document_id, change_set):
        self.model = self._derive(change_set.apply(self.model))


class _ReconcilingRollbackPythonHost(_DriftingRollbackPythonHost):
    def __init__(self) -> None:
        super().__init__()
        self.required_after = None
        self.reconciliation_calls = 0

    def simulate_reconciliation(
        self, document_id, change_set, required_after_model, before_model
    ):
        self.reconciliation_calls += 1
        self.required_after = copy.deepcopy(required_after_model)
        return {
            "afterModel": copy.deepcopy(required_after_model),
            "replayReplacements": [],
        }

    def apply_verified_change_set(
        self,
        document_id,
        change_set,
        *,
        operation_id,
        removes_contribution_id=None,
        replay_replacements=(),
    ):
        if operation_id.startswith("rollback_") and self.required_after is not None:
            self.model = copy.deepcopy(self.required_after)
            return
        self.model = self._derive(change_set.apply(self.model))


class _Clock:
    def __init__(self):
        self.value = 1_700_000_000.0

    def __call__(self):
        return self.value


class V2PythonExecutionTests(unittest.TestCase):
    def service(self):
        host = _PythonHost()
        operations = OperationStore()
        service = PythonExecutionService(
            host=host,
            transactions=TransactionKernel(host),
            reviews=operations,
            checkpoints=OperationStore(),
            audit=AuditLog(),
        )
        return service, host

    def test_staged_preview_does_not_mutate_and_confirmation_does_not_rerun_code(self) -> None:
        service, host = self.service()
        before = fingerprint_model(host.model)
        preview = service.execute(
            PythonExecutionRequest(
                code="font.familyName = 'Beta'",
                reason="rename the detached test font",
                intended_effect="document_edit",
                execution_mode="staged_document",
                document_id="doc_alpha",
                expected_document_fingerprint=before,
            )
        ).to_dict()

        self.assertEqual(preview["status"], "review_required")
        self.assertEqual(host.model["font"]["familyName"], "Alpha")
        self.assertEqual(host.preview_calls, 1)
        self.assertNotIn("font.familyName", repr(preview["auditReceipt"]))

        confirmed = service.execute(
            PythonExecutionRequest(review_id=preview["data"]["reviewId"], confirm=True)
        ).to_dict()
        self.assertTrue(confirmed["ok"])
        self.assertEqual(host.model["font"]["familyName"], "Beta")
        self.assertEqual(host.preview_calls, 1)
        self.assertEqual(confirmed["data"]["rollback"]["coverage"], "document_inverse")

    def test_staged_preview_reuses_the_host_verified_change_sets(self) -> None:
        host = _PrecomputedPreviewHost()
        service = PythonExecutionService(
            host=host,
            transactions=TransactionKernel(host),
            reviews=OperationStore(),
            checkpoints=OperationStore(),
            audit=AuditLog(),
        )

        with mock.patch(
            "glyphs_mcp_v2.python_execution.diff_models",
            side_effect=AssertionError("service recomputed host semantic diff"),
        ), mock.patch(
            "glyphs_mcp_v2.python_execution.writable_subset",
            side_effect=AssertionError("service recomputed host writable diff"),
        ):
            preview = service.execute(
                PythonExecutionRequest(
                    code="font.familyName = 'Beta'",
                    reason="reuse the host's verified staged plan",
                    intended_effect="document_edit",
                    execution_mode="staged_document",
                    document_id="doc_alpha",
                    expected_document_fingerprint=fingerprint_model(host.model),
                )
            ).to_dict()

        self.assertEqual(preview["status"], "review_required")
        self.assertEqual(host.preview_calls, 1)

    def test_staged_existing_feature_code_is_confirmable_and_reversible(self) -> None:
        service, host = self.service()
        host.model["features"] = [
            {
                "id": "liga",
                "name": "liga",
                "code": "sub f i by fi;",
                "automatic": False,
                "disabled": False,
            }
        ]
        baseline = copy.deepcopy(host.model)
        preview = service.execute(
            PythonExecutionRequest(
                code="# featureEdit",
                reason="update existing liga code",
                intended_effect="document_edit",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()

        self.assertEqual(preview["status"], "review_required")
        confirmed = service.execute(
            PythonExecutionRequest(review_id=preview["data"]["reviewId"], confirm=True)
        ).to_dict()
        self.assertTrue(confirmed["ok"])
        self.assertEqual(host.model["features"][0]["code"], "sub f f i by ffi;")

        rolled_back = service.rollback(
            execution_id=confirmed["data"]["executionId"],
            expected_after_fingerprint=confirmed["data"]["afterFingerprint"],
            confirm=True,
        ).to_dict()
        self.assertTrue(rolled_back["ok"])
        self.assertEqual(host.model, baseline)

    def test_rollback_is_fingerprint_bound_and_one_shot(self) -> None:
        service, host = self.service()
        preview = service.execute(
            PythonExecutionRequest(
                code="font.familyName = 'Beta'",
                reason="rename",
                intended_effect="document_edit",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()
        confirmed = service.execute(
            PythonExecutionRequest(review_id=preview["data"]["reviewId"], confirm=True)
        ).to_dict()

        rolled_back = service.rollback(
            execution_id=confirmed["data"]["executionId"],
            expected_after_fingerprint=confirmed["data"]["afterFingerprint"],
            confirm=True,
        ).to_dict()
        self.assertTrue(rolled_back["ok"])
        self.assertEqual(host.model["font"]["familyName"], "Alpha")

        repeated = service.rollback(
            execution_id=confirmed["data"]["executionId"],
            expected_after_fingerprint=confirmed["data"]["afterFingerprint"],
            confirm=True,
        ).to_dict()
        self.assertFalse(repeated["ok"])
        self.assertEqual(repeated["error"]["code"], "checkpoint_unavailable")

    def test_rollback_refuses_a_derived_state_that_misses_the_checkpoint_target(self) -> None:
        host = _DriftingRollbackPythonHost()
        service = PythonExecutionService(
            host=host,
            transactions=TransactionKernel(host),
            reviews=OperationStore(),
            checkpoints=OperationStore(),
            audit=AuditLog(),
        )
        baseline = copy.deepcopy(host.model)
        preview = service.execute(
            PythonExecutionRequest(
                code="font.familyName = 'Beta'",
                reason="exercise exact rollback planning",
                intended_effect="document_edit",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()
        confirmed = service.execute(
            PythonExecutionRequest(
                review_id=preview["data"]["reviewId"], confirm=True
            )
        ).to_dict()
        after = copy.deepcopy(host.model)

        rolled_back = service.rollback(
            execution_id=confirmed["data"]["executionId"],
            expected_after_fingerprint=confirmed["data"]["afterFingerprint"],
            confirm=True,
        ).to_dict()

        self.assertFalse(rolled_back["ok"])
        self.assertEqual(rolled_back["error"]["code"], "rollback_not_exact")
        self.assertEqual(host.model, after)
        self.assertNotEqual(fingerprint_model(host.model), fingerprint_model(baseline))

    def test_rollback_uses_the_same_canonical_reconciler_as_typed_revert(self) -> None:
        host = _ReconcilingRollbackPythonHost()
        service = PythonExecutionService(
            host=host,
            transactions=TransactionKernel(host),
            reviews=OperationStore(),
            checkpoints=OperationStore(),
            audit=AuditLog(),
        )
        baseline = copy.deepcopy(host.model)
        preview = service.execute(
            PythonExecutionRequest(
                code="font.familyName = 'Beta'",
                reason="exercise shared rollback reconciliation",
                intended_effect="document_edit",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()
        confirmed = service.execute(
            PythonExecutionRequest(
                review_id=preview["data"]["reviewId"], confirm=True
            )
        ).to_dict()

        rolled_back = service.rollback(
            execution_id=confirmed["data"]["executionId"],
            expected_after_fingerprint=confirmed["data"]["afterFingerprint"],
            confirm=True,
        ).to_dict()

        self.assertTrue(rolled_back["ok"])
        self.assertEqual(host.model, baseline)
        self.assertEqual(
            rolled_back["data"]["afterFingerprint"],
            fingerprint_model(baseline),
        )
        self.assertEqual(host.reconciliation_calls, 1)

    def test_later_edits_make_rollback_stale(self) -> None:
        service, host = self.service()
        preview = service.execute(
            PythonExecutionRequest(
                code="font.familyName = 'Beta'",
                reason="rename",
                intended_effect="document_edit",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()
        confirmed = service.execute(
            PythonExecutionRequest(review_id=preview["data"]["reviewId"], confirm=True)
        ).to_dict()
        host.model["font"]["familyName"] = "User Edit"

        result = service.rollback(
            execution_id=confirmed["data"]["executionId"],
            expected_after_fingerprint=confirmed["data"]["afterFingerprint"],
            confirm=True,
        ).to_dict()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "stale_document")
        self.assertEqual(host.model["font"]["familyName"], "User Edit")

    def test_live_open_world_is_previewed_and_never_claims_external_rollback(self) -> None:
        service, host = self.service()
        preview = service.execute(
            PythonExecutionRequest(
                code="open('/tmp/result', 'w')",
                reason="explicit external fallback",
                intended_effect="files_or_external",
                execution_mode="live_open_world",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()
        self.assertEqual(host.live_calls, 0)

        confirmed = service.execute(
            PythonExecutionRequest(review_id=preview["data"]["reviewId"], confirm=True)
        ).to_dict()
        self.assertEqual(host.live_calls, 1)
        self.assertFalse(confirmed["data"]["externalEffectsVerifiable"])
        self.assertEqual(confirmed["data"]["rollback"]["coverage"], "recovery_only")
        self.assertFalse(confirmed["data"]["transactional"])

        recovery = service.rollback(
            execution_id=confirmed["data"]["executionId"],
            expected_after_fingerprint=confirmed["data"]["afterFingerprint"],
            confirm=True,
            strategy="open_recovery_copy",
        ).to_dict()
        self.assertTrue(recovery["ok"])
        self.assertEqual(len(host.opened_recovery), 1)

    def test_staged_policy_rejects_open_world_constructs(self) -> None:
        validate_staged_code("font.familyName = 'Beta'")
        for code in (
            "import os",
            "from GlyphsApp import Glyphs",
            "open('/tmp/x', 'w')",
            "font.save('/tmp/x.glyphs')",
            "font.close()",
            "__import__('subprocess')",
        ):
            with self.subTest(code=code), self.assertRaises(PythonPolicyError):
                validate_staged_code(code)

    def test_confirmation_ignores_substitute_code_and_large_diff_is_paginated(self) -> None:
        service, host = self.service()
        preview = service.execute(
            PythonExecutionRequest(
                code="# bulk",
                reason="review a synthetic bulk change",
                intended_effect="document_edit",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()
        change_set = preview["data"]["changeSet"]
        self.assertEqual(change_set["changeCount"], 225)
        self.assertEqual(len(change_set["changes"]), 100)
        self.assertIsNotNone(change_set["page"]["nextCursor"])
        self.assertLess(
            len(json.dumps(preview, separators=(",", ":")).encode("utf-8")),
            64 * 1024,
        )

        application = GlyphsMCPApplication(host, operations=service._operations)
        second = application.get_operation(
            {
                "operationId": preview["data"]["operationId"],
                "cursor": change_set["page"]["nextCursor"],
                "pageSize": 100,
            }
        ).to_dict()
        self.assertEqual(len(second["data"]["payload"]["changes"]), 100)

        confirmed = service.execute(
            PythonExecutionRequest(
                review_id=preview["data"]["reviewId"],
                confirm=True,
                code="raise RuntimeError('substitute')",
            )
        ).to_dict()
        self.assertTrue(confirmed["ok"])
        self.assertEqual(host.preview_calls, 1)
        self.assertEqual(len(host.model["glyphs"]), 225)

    def test_staged_scope_and_unsupported_changes_are_refused(self) -> None:
        service, host = self.service()
        host.preview_scope_violations = ["doc_other"]
        scope = service.execute(
            PythonExecutionRequest(
                code="font.familyName = 'Beta'",
                reason="scope test",
                intended_effect="document_edit",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()
        self.assertEqual(scope["error"]["code"], "staged_scope_violation")
        self.assertEqual(host.model["font"]["familyName"], "Alpha")

        host.preview_scope_violations = []
        unsupported = service.execute(
            PythonExecutionRequest(
                code="# unsupported",
                reason="unsupported test",
                intended_effect="document_edit",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()
        self.assertEqual(unsupported["error"]["code"], "unsupported_staged_change")

    def test_staged_explicit_context_escape_is_refused_before_review(self) -> None:
        service, host = self.service()
        host.preview_context_violations = {
            "count": 2,
            "paths": [
                ["glyphs", "B", "layers", "m0", "paths"],
                ["font", "note"],
            ],
            "truncated": False,
        }

        result = service.execute(
            PythonExecutionRequest(
                code="layer.width = 500",
                reason="context boundary test",
                intended_effect="document_edit",
                document_id="doc_alpha",
                glyph_name="A",
                layer_id="m0",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()

        self.assertEqual(result["error"]["code"], "staged_context_violation")
        self.assertEqual(result["data"]["violationCount"], 2)
        self.assertEqual(host.model["font"]["familyName"], "Alpha")

    def test_native_archive_refusal_returns_structured_bounded_mismatch_locations(self) -> None:
        service, host = self.service()
        source_marker = "audit-secret-source-marker"
        host.native_archive_comparison = {
            "equivalent": False,
            "mismatchCount": 142,
            "mismatchLocations": [
                {
                    "direct": {"beforeStart": index, "afterStart": index},
                    "replay": {"beforeStart": index, "afterStart": index + 1},
                }
                for index in range(100)
            ],
            "truncated": True,
        }

        result = service.execute(
            PythonExecutionRequest(
                code="font.familyName = 'Beta'  # {}".format(source_marker),
                reason="archive mismatch diagnostics",
                intended_effect="document_edit",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()

        self.assertEqual(result["error"]["code"], "unsupported_staged_change")
        comparison = result["data"]["nativeArchiveMismatch"]
        self.assertEqual(comparison["mismatchCount"], 142)
        self.assertEqual(len(comparison["mismatchLocations"]), 100)
        self.assertTrue(comparison["truncated"])
        self.assertEqual(host.model["font"]["familyName"], "Alpha")

        self.assertIsNotNone(result["auditReceipt"])
        events = service._audit.list_events(document_id="doc_alpha")
        self.assertEqual(len(events), 1)
        event = events[0].to_dict()
        self.assertEqual(event["status"], "error")
        self.assertEqual(event["details"]["errorCode"], "unsupported_staged_change")
        self.assertEqual(event["details"]["reason"], "archive mismatch diagnostics")
        self.assertEqual(event["details"]["declaredEffect"], "document_edit")
        self.assertEqual(event["details"]["executionMode"], "staged_document")
        self.assertTrue(event["details"]["codeHash"].startswith("sha256:"))
        self.assertNotIn(source_marker, repr(event))
        self.assertNotIn(source_marker, repr(result["auditReceipt"]))

    def test_read_intent_mutation_scope_and_output_truncation_are_reported(self) -> None:
        service, host = self.service()
        host.scope_violations = ["doc_other"]
        host.stdout = "x" * 100
        result = service.execute(
            PythonExecutionRequest(
                code="print('read')",
                reason="read test",
                intended_effect="read",
                document_id="doc_alpha",
                max_output_chars=20,
            )
        ).to_dict()
        codes = {warning["code"] for warning in result["warnings"]}
        self.assertIn("read_intent_violated", codes)
        self.assertIn("undeclared_document_mutation", codes)
        self.assertIn("output truncated", result["data"]["stdout"])

    def test_obvious_external_effect_cannot_bypass_exact_review_as_read_intent(self) -> None:
        service, host = self.service()
        result = service.execute(
            PythonExecutionRequest(
                code="open('/tmp/not-created', 'w')",
                reason="misdeclared external effect",
                intended_effect="read",
                document_id="doc_alpha",
            )
        ).to_dict()
        self.assertEqual(result["error"]["code"], "effect_review_required")
        self.assertEqual(host.live_calls, 0)

    def test_live_exception_keeps_recovery_and_restart_is_recovery_only(self) -> None:
        service, host = self.service()
        preview = service.execute(
            PythonExecutionRequest(
                code="raise RuntimeError('boom')",
                reason="exception test",
                intended_effect="files_or_external",
                execution_mode="live_open_world",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()
        host.raise_live = True
        failed = service.execute(
            PythonExecutionRequest(review_id=preview["data"]["reviewId"], confirm=True)
        ).to_dict()
        self.assertEqual(failed["error"]["code"], "python_execution_failed")
        self.assertEqual(failed["data"]["rollback"]["coverage"], "recovery_only")

        restarted = PythonExecutionService(
            host=host,
            transactions=TransactionKernel(host),
            reviews=OperationStore(),
            checkpoints=OperationStore(),
            audit=AuditLog(),
        )
        recovered = restarted.rollback(
            execution_id=failed["data"]["executionId"],
            expected_after_fingerprint=failed["data"]["afterFingerprint"],
            confirm=True,
            strategy="open_recovery_copy",
        ).to_dict()
        self.assertTrue(recovered["ok"])
        self.assertFalse(recovered["data"]["workingDocumentReplaced"])

    def test_rollback_failure_restores_the_pre_attempt_after_state(self) -> None:
        service, host = self.service()
        preview = service.execute(
            PythonExecutionRequest(
                code="font.familyName = 'Beta'",
                reason="rollback verification test",
                intended_effect="document_edit",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()
        confirmed = service.execute(
            PythonExecutionRequest(review_id=preview["data"]["reviewId"], confirm=True)
        ).to_dict()
        host.corrupt_apply = True
        failed = service.rollback(
            execution_id=confirmed["data"]["executionId"],
            expected_after_fingerprint=confirmed["data"]["afterFingerprint"],
            confirm=True,
        ).to_dict()
        self.assertEqual(failed["error"]["code"], "rollback_failed")
        self.assertTrue(failed["data"]["afterStateRestored"])
        self.assertEqual(host.model["font"]["familyName"], "Beta")

    def test_reviews_and_automatic_rollback_expire(self) -> None:
        clock = _Clock()
        host = _PythonHost()
        reviews = OperationStore(clock=clock)
        checkpoints = OperationStore(clock=clock)
        service = PythonExecutionService(
            host=host,
            transactions=TransactionKernel(host),
            reviews=reviews,
            checkpoints=checkpoints,
            audit=AuditLog(),
        )
        preview = service.execute(
            PythonExecutionRequest(
                code="font.familyName = 'Beta'",
                reason="expiry test",
                intended_effect="document_edit",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()
        clock.value += 901
        expired_review = service.execute(
            PythonExecutionRequest(review_id=preview["data"]["reviewId"], confirm=True)
        ).to_dict()
        self.assertEqual(expired_review["error"]["code"], "review_unavailable")

        fresh = service.execute(
            PythonExecutionRequest(
                code="font.familyName = 'Beta'",
                reason="rollback expiry test",
                intended_effect="document_edit",
                document_id="doc_alpha",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()
        confirmed = service.execute(
            PythonExecutionRequest(review_id=fresh["data"]["reviewId"], confirm=True)
        ).to_dict()
        clock.value += 3601
        expired_rollback = service.rollback(
            execution_id=confirmed["data"]["executionId"],
            expected_after_fingerprint=confirmed["data"]["afterFingerprint"],
            confirm=True,
        ).to_dict()
        self.assertEqual(expired_rollback["error"]["code"], "checkpoint_unavailable")


if __name__ == "__main__":
    unittest.main()
