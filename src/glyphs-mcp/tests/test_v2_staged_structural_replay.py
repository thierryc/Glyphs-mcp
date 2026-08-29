"""Milestone-9 contracts for staged-Python structural replay."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.audit import AuditLog  # noqa: E402
from glyphs_mcp_v2.adapters import document as document_adapter  # noqa: E402
from glyphs_mcp_v2.adapters.document import (  # noqa: E402
    GlyphsDocumentHost,
    native_font_to_model,
)
from glyphs_mcp_v2.mutation import (  # noqa: E402
    CANONICAL_LIFECYCLE_CAPABILITY,
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
    def test_detached_context_exposes_only_allowlisted_native_constructors(self) -> None:
        glyphs_app = ModuleType("GlyphsApp")
        for name in (
            "GSClass",
            "GSFeature",
            "GSFeaturePrefix",
            "GSFontMaster",
            "GSGlyph",
            "GSInstance",
            "GSLayer",
            "MGOrderedDictionary",
        ):
            setattr(glyphs_app, name, type(name, (), {}))

        with mock.patch.dict(sys.modules, {"GlyphsApp": glyphs_app}):
            constructors = document_adapter._staged_native_types()

        self.assertEqual(
            set(constructors),
            {
                "GSClass",
                "GSFeature",
                "GSFeaturePrefix",
                "GSFontMaster",
                "GSGlyph",
                "GSInstance",
                "GSLayer",
                "MGOrderedDictionary",
            },
        )
        self.assertNotIn("Glyphs", constructors)

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

    def test_resolved_evidence_reuses_the_exact_detached_native_templates(self) -> None:
        store = NativeReplayEvidenceStore()
        native_template = object()
        evidence = store.create(
            document_id="doc_a",
            before_fingerprint="before",
            after_fingerprint="after",
            capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
            templates={("masters", "m1"): native_template},
            ttl_seconds=60,
        )
        host = object.__new__(GlyphsDocumentHost)
        host._native_replay_evidence = store

        context = host._resolved_replay_context(
            "doc_a", {"nativeReplayEvidenceId": evidence.evidence_id}
        )

        self.assertIs(
            context["nativeReplayTemplates"][("masters", "m1")],
            native_template,
        )
        self.assertTrue(context["reuseNativeReplayTemplates"])

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

    def test_axis_lifecycle_is_owned_by_the_v6_replay_capability(self) -> None:
        before = _model()
        after = copy.deepcopy(before)
        after["masters"][0]["axes"].append(
            {"tag": "wdth", "internal": 100}
        )

        capabilities = staged_lifecycle_capabilities(
            before, after, diff_models(before, after)
        )
        self.assertIn(CANONICAL_LIFECYCLE_CAPABILITY, capabilities)

    def test_structural_apply_reuses_preview_patch_and_never_reruns_code(self) -> None:
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

        self.assertEqual(preview["status"], "success")
        self.assertEqual(
            preview["data"]["canonicalCoverage"]["status"],
            "complete_with_opaque_preservation",
        )
        self.assertGreater(
            preview["data"]["canonicalCoverage"]["opaqueChangeCount"], 0
        )
        preview_id = preview["data"]["previewId"]
        record = service._reviews.get(preview_id)
        self.assertIsNotNone(record)
        confirmed = service.apply_staged_preview(
            record,
            operation_id="op_structural",
            reason="apply exact staged structural patch",
        ).to_dict()

        self.assertTrue(confirmed["ok"])
        self.assertEqual(confirmed["operationId"], "op_structural")
        self.assertEqual(confirmed["data"]["transactionCount"], 1)
        self.assertFalse(confirmed["data"]["fontSaved"])
        self.assertEqual(
            confirmed["data"]["canonicalCoverage"]["status"],
            "complete_with_opaque_preservation",
        )
        self.assertEqual(host.preview_calls, 1)
        self.assertIn("B", host.model["glyphs"])
        self.assertEqual(
            host.applied_contexts,
            [{"nativeReplayEvidenceId": "evidence_structural"}],
        )
        self.assertEqual(host.released, ["evidence_structural"])

    def test_generic_native_template_preserves_added_and_deleted_feature_payload(self) -> None:
        original = SimpleNamespace(
            name="liga",
            code="sub f i by fi;",
            automatic=False,
            disabled=False,
            nativeOnly="private-feature-payload",
        )
        font = SimpleNamespace(
            familyName="Native Evidence",
            upm=1000,
            versionMajor=1,
            versionMinor=0,
            note=None,
            grid=1,
            gridSubDivision=1,
            masters=[],
            instances=[],
            glyphs=[],
            kerning={},
            features=[original],
            classes=[],
            featurePrefixes=[],
        )
        before = native_font_to_model(font)
        empty = copy.deepcopy(before)
        empty["features"] = []
        removal = diff_models(before, empty)
        host = object.__new__(GlyphsDocumentHost)
        retained = host._capture_removed_native_templates(font, before, empty)

        document_adapter._apply_target_model(font, before, empty, removal)
        self.assertEqual(font.features, [])
        restoration = diff_models(empty, before)
        document_adapter._apply_target_model(
            font,
            empty,
            before,
            restoration,
            execution_context={
                "nativeReplayTemplates": {
                    path: value["native"] for path, value in retained.items()
                },
                "reuseNativeReplayTemplates": True,
            },
        )

        self.assertIs(font.features[0], original)
        self.assertEqual(
            font.features[0].nativeOnly, "private-feature-payload"
        )

    def test_review_store_contains_only_the_opaque_evidence_identifier(self) -> None:
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
                code="# add glyph B",
                reason="opaque native evidence",
                intended_effect="document_edit",
                document_id="doc_structural",
                expected_document_fingerprint=fingerprint_model(host.model),
            )
        ).to_dict()
        record = service._reviews.get(preview["data"]["previewId"])

        self.assertEqual(
            record.payload["executionContext"],
            {"nativeReplayEvidenceId": "evidence_structural"},
        )
        self.assertNotIn("nativeReplayTemplates", repr(record.payload))


if __name__ == "__main__":
    unittest.main()
