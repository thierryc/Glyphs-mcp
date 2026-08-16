"""Staged Python approval, exact apply, rollback, and open-world honesty."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.audit import AuditLog  # noqa: E402
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

    def capture_model(self, document_id):
        return copy.deepcopy(self.model)

    def preview_python(self, request, before_model):
        self.preview_calls += 1
        after = copy.deepcopy(before_model)
        if "Beta" in request.code:
            after["font"]["familyName"] = "Beta"
        if "unsupported" in request.code:
            after["unsupported"] = {"native": True}
        return {
            "afterModel": after,
            "stdout": "previewed",
            "stderr": "",
            "scopeViolations": [],
        }

    def run_live_python(self, request):
        self.live_calls += 1
        before = self.capture_model(request.document_id)
        after = copy.deepcopy(before)
        after["unsupported"] = {"native": True}
        self.model = after
        return {"beforeModel": before, "afterModel": after, "stdout": "live", "stderr": ""}

    def apply_change_set(self, document_id, change_set):
        self.model = change_set.apply(self.model)

    def restore_model(self, document_id, model):
        self.model = copy.deepcopy(model)

    def create_recovery_copy(self, document_id, execution_id):
        path = "/private/recovery/{}.glyphs".format(execution_id)
        self.recovery_paths.append(path)
        return path

    def open_recovery_copy(self, path):
        self.opened_recovery.append(path)


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


if __name__ == "__main__":
    unittest.main()
