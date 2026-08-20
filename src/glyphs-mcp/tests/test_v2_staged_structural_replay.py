"""Milestone-9 contracts for staged-Python structural replay."""

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
from glyphs_mcp_v2.mutation import (  # noqa: E402
    LAYER_LIFECYCLE_CAPABILITY,
    MASTER_LIFECYCLE_CAPABILITY,
    StructuralReplayValidationError,
    staged_lifecycle_capabilities,
)
from glyphs_mcp_v2.native_replay import NativeReplayEvidenceStore  # noqa: E402
from glyphs_mcp_v2.operations import OperationStore  # noqa: E402
from glyphs_mcp_v2.python_execution import (  # noqa: E402
    PythonExecutionRequest,
    PythonExecutionService,
)
from glyphs_mcp_v2.semantic import diff_models, fingerprint_model  # noqa: E402
from glyphs_mcp_v2.transactions import TransactionKernel  # noqa: E402


def _layer(identity: str, master_id: str, *, master: bool) -> dict:
    return {
        "id": identity,
        "masterId": master_id,
        "name": identity,
        "roles": ["master"] if master else ["backup"],
        "isMasterLayer": master,
        "isSpecialLayer": False,
        "interpolation": None,
        "width": 500,
        "anchors": {},
        "paths": [],
        "components": [],
        "pathSignature": [],
    }


def _model() -> dict:
    return {
        "font": {"familyName": "Structural Replay"},
        "masters": [
            {
                "id": "m0",
                "name": "Regular",
                "italicAngle": 0,
                "axes": [{"tag": "wght", "internal": 100}],
            }
        ],
        "instances": [],
        "glyphs": {
            "A": {
                "id": "glyph_A",
                "name": "A",
                "mastersCompatible": True,
                "layers": [_layer("m0", "m0", master=True)],
            }
        },
        "kerning": {},
        "features": [],
        "classes": [],
        "featurePrefixes": [],
    }


class _Clock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value


class _StructuralPythonHost:
    def __init__(self) -> None:
        self.model = _model()
        self.preview_calls = 0
        self.applied_contexts: list[dict] = []
        self.released: list[str] = []

    def capture_model(self, document_id):
        return copy.deepcopy(self.model)

    def preview_python(self, request, before_model):
        self.preview_calls += 1
        after = copy.deepcopy(before_model)
        after["glyphs"]["B"] = {
            "id": "glyph_B",
            "name": "B",
            "mastersCompatible": True,
            "layers": [_layer("m0", "m0", master=True)],
        }
        changes = diff_models(before_model, after)
        return {
            "afterModel": after,
            "changeSet": changes,
            "writableChangeSet": changes,
            "capabilities": [],
            "executionContext": {
                "nativeReplayEvidenceId": "evidence_structural"
            },
            "nativeArchiveComparison": {
                "equivalent": True,
                "mismatchCount": 0,
                "mismatchLocations": [],
                "truncated": False,
            },
            "stdout": "preview only",
            "stderr": "",
            "scopeViolations": [],
        }

    def supports_change_set(self, change_set, *, capabilities=()):
        return True

    def apply_verified_change_set(
        self,
        document_id,
        change_set,
        *,
        operation_id,
        removes_contribution_id=None,
        replay_replacements=(),
        capabilities=(),
        execution_context=None,
    ):
        self.applied_contexts.append(dict(execution_context or {}))
        self.model = change_set.apply(self.model)

    def restore_verified_attempt(self, document_id, model, **kwargs):
        self.model = copy.deepcopy(model)

    def commit_verified_change(self, operation_id):
        return None

    def release_staged_replay_evidence(self, evidence_id):
        self.released.append(str(evidence_id))


class StagedStructuralReplayTests(unittest.TestCase):
    def test_native_evidence_is_bounded_expiring_and_document_bound(self) -> None:
        clock = _Clock()
        store = NativeReplayEvidenceStore(
            clock=clock,
            max_records=3,
            max_records_per_document=2,
        )
        first = store.create(
            document_id="doc_a",
            before_fingerprint="before",
            after_fingerprint="after-1",
            capabilities=(),
            templates={("glyphs", "A"): object()},
            ttl_seconds=10,
        )
        second = store.create(
            document_id="doc_a",
            before_fingerprint="before",
            after_fingerprint="after-2",
            capabilities=(),
            templates={("glyphs", "B"): object()},
            ttl_seconds=10,
        )
        third = store.create(
            document_id="doc_a",
            before_fingerprint="before",
            after_fingerprint="after-3",
            capabilities=(),
            templates={("glyphs", "C"): object()},
            ttl_seconds=10,
        )

        self.assertIsNone(store.resolve(first.evidence_id, document_id="doc_a"))
        self.assertIsNone(store.resolve(second.evidence_id, document_id="doc_b"))
        self.assertIsNotNone(store.resolve(second.evidence_id, document_id="doc_a"))
        self.assertEqual(store.record_count(), 2)
        clock.value += 11
        self.assertIsNone(store.resolve(third.evidence_id, document_id="doc_a"))
        self.assertEqual(store.record_count(), 0)

    def test_lifecycle_capabilities_are_composed_and_master_layers_are_owned(self) -> None:
        before = _model()
        after = copy.deepcopy(before)
        after["masters"].append(
            {
                "id": "m1",
                "name": "Bold",
                "italicAngle": 0,
                "axes": [{"tag": "wght", "internal": 200}],
            }
        )
        after["glyphs"]["A"]["layers"].extend(
            [
                _layer("m1", "m1", master=True),
                _layer("backup", "m0", master=False),
            ]
        )
        changes = diff_models(before, after)

        self.assertEqual(
            staged_lifecycle_capabilities(before, after, changes),
            (LAYER_LIFECYCLE_CAPABILITY, MASTER_LIFECYCLE_CAPABILITY),
        )

        orphaned = copy.deepcopy(before)
        orphaned["glyphs"]["A"]["layers"].append(
            _layer("orphan", "missing-master", master=True)
        )
        with self.assertRaises(StructuralReplayValidationError):
            staged_lifecycle_capabilities(
                before, orphaned, diff_models(before, orphaned)
            )

    def test_axis_lifecycle_is_not_smuggled_through_master_coordinates(self) -> None:
        before = _model()
        after = copy.deepcopy(before)
        after["masters"][0]["axes"].append(
            {"tag": "wdth", "internal": 100}
        )

        with self.assertRaises(StructuralReplayValidationError):
            staged_lifecycle_capabilities(before, after, diff_models(before, after))

    def test_structural_confirmation_reuses_review_id_and_never_reruns_code(self) -> None:
        host = _StructuralPythonHost()
        service = PythonExecutionService(
            host=host,
            transactions=TransactionKernel(host),
            reviews=OperationStore(),
            checkpoints=OperationStore(),
            audit=AuditLog(),
        )
        preview = service.execute(
            PythonExecutionRequest(
                code="# add glyph B on the detached clone",
                reason="structural replay contract",
                intended_effect="document_edit",
                document_id="doc_structural",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()

        self.assertEqual(preview["status"], "review_required")
        review_id = preview["data"]["reviewId"]
        confirmed = service.execute(
            PythonExecutionRequest(review_id=review_id, confirm=True)
        ).to_dict()

        self.assertTrue(confirmed["ok"])
        self.assertEqual(confirmed["operation"]["operationId"], review_id)
        self.assertEqual(host.preview_calls, 1)
        self.assertIn("B", host.model["glyphs"])
        self.assertEqual(
            host.applied_contexts,
            [{"nativeReplayEvidenceId": "evidence_structural"}],
        )
        self.assertEqual(host.released, ["evidence_structural"])


if __name__ == "__main__":
    unittest.main()
