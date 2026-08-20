"""Static disposable-host guards for the Glyphs 4 live gate."""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.live_gates import (  # noqa: E402
    _StructuralGateSession,
    verify_copy_and_make_copy,
    verify_schema_v3_structural_kernel,
    verify_schema_v4_master_lifecycle,
    verify_schema_v5_layer_lifecycle,
)
from glyphs_mcp_v2.semantic import fingerprint_model  # noqa: E402


class _Document:
    def __init__(self):
        self.isDocumentEdited = True


class _Font:
    def __init__(self, family_name="Glyphs MCP V2 Disposable Test"):
        self.familyName = family_name
        self.filepath = "/disposable/source.glyphs"
        self.parent = _Document()
        self.upm = 1000
        self.versionMajor = 1
        self.versionMinor = 0
        self.note = None
        self.grid = 1
        self.gridSubDivision = 1
        self.axes = []
        self.masters = []
        self.instances = []
        self.glyphs = []
        self.kerning = {}
        self.features = []
        self.classes = []
        self.featurePrefixes = []

    def copy(self):
        return _Font(self.familyName)

    def save(self, path, formatVersion=3, makeCopy=False):
        Path(path).write_text("stable disposable archive", encoding="utf-8")


def _structural_model():
    return {
        "font": {"familyName": "Glyphs MCP V2 Disposable Gate", "upm": 1000},
        "masters": [
            {
                "id": "m0",
                "name": "Regular",
                "italicAngle": 0,
                "axes": [{"tag": "wght", "internal": 100}],
            }
        ],
        "instances": [
            {
                "id": "instance_regular",
                "name": "Regular",
                "type": "static",
                "included": True,
                "inclusionReason": None,
                "interpolationSupported": True,
                "axes": [],
            }
        ],
        "glyphs": {
            "A": {
                "id": "glyph_A",
                "name": "A",
                "category": "Letter",
                "subCategory": "Uppercase",
                "unicode": "0041",
                "export": True,
                "leftKerningGroup": "A",
                "rightKerningGroup": "A",
                "mastersCompatible": True,
                "layers": [
                    {
                        "id": "m0",
                        "masterId": "m0",
                        "name": "Regular",
                        "isMasterLayer": True,
                        "isSpecialLayer": False,
                        "hasAlignedWidth": False,
                        "width": 600,
                        "LSB": 50,
                        "RSB": 50,
                        "leftMetricsKey": None,
                        "rightMetricsKey": None,
                        "widthMetricsKey": None,
                        "anchors": {},
                        "paths": [],
                        "components": [],
                        "pathSignature": [],
                    }
                ],
            }
        },
        "kerning": {},
        "features": [
            {
                "id": "liga",
                "name": "liga",
                "code": "sub f i by fi;",
                "automatic": False,
                "disabled": False,
            }
        ],
        "classes": [],
        "featurePrefixes": [],
    }


class _StructuralHost:
    def __init__(self):
        self.model = _structural_model()
        self.apply_calls = 0
        self.restore_calls = 0

    def document_id_for_font(self, font):
        return "doc_structural_gate"

    def capture_model(self, document_id):
        if document_id != "doc_structural_gate":
            raise ValueError("wrong document")
        return copy.deepcopy(self.model)

    def simulate_change_set(self, document_id, change_set):
        return change_set.apply(self.model)

    def simulate_reconciliation(
        self, document_id, change_set, required_after_model, before_model
    ):
        return {
            "afterModel": copy.deepcopy(required_after_model),
            "replayReplacements": [],
        }

    def apply_change_set(self, document_id, change_set):
        self.apply_calls += 1
        self.model = change_set.apply(self.model)

    def restore_model(self, document_id, model):
        self.restore_calls += 1
        self.model = copy.deepcopy(model)


class V2LiveGateGuardTests(unittest.TestCase):
    def test_structural_gate_carries_verified_fingerprints_between_transactions(self) -> None:
        class Host:
            def capture_model(self, document_id):
                raise AssertionError("gate recaptured the complete model between operations")

        class Application:
            def __init__(self):
                self.expected = ["sha256:before", "sha256:after"]
                self.after = ["sha256:after", "sha256:before"]
                self.calls = 0

            def invoke(self, tool, arguments):
                index = self.calls
                self.calls += 1
                if arguments["expectedDocumentFingerprint"] != self.expected[index]:
                    raise AssertionError("gate did not carry the verified fingerprint")
                return {
                    "ok": True,
                    "operationId": "op_{}".format(index),
                    "auditReceipt": {"auditId": "audit_{}".format(index)},
                    "data": {
                        "operationId": "op_{}".format(index),
                        "transactionCount": 1,
                        "beforeFingerprint": self.expected[index],
                        "afterFingerprint": self.after[index],
                    },
                }

        application = Application()
        session = _StructuralGateSession(
            application,
            Host(),
            "doc_gate",
            "sha256:before",
        )
        session._require_change_log_commit = lambda operation_id, tool: None
        session._record_stage_timings = lambda operation_id: None

        operation_id = session.apply("apply_master_updates", [{"action": "move"}])
        session.revert(operation_id)

        self.assertEqual(application.calls, 2)
        self.assertEqual(session.current_fingerprint, "sha256:before")

    def test_gate_refuses_non_disposable_font(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                verify_copy_and_make_copy(_Font("Production Family"), str(Path(root) / "copy.glyphs"))

    def test_gate_preserves_path_and_dirty_state(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            font = _Font()
            result = verify_copy_and_make_copy(font, str(Path(root) / "copy.glyphs"))
            self.assertTrue(result["workingPathUnchanged"])
            self.assertTrue(result["dirtyStateUnchanged"])
            self.assertEqual(font.filepath, "/disposable/source.glyphs")
            self.assertTrue(font.parent.isDocumentEdited)

    def test_schema_v3_gate_refuses_non_disposable_font(self) -> None:
        host = _StructuralHost()
        app = GlyphsMCPApplication(host)

        with self.assertRaises(ValueError):
            verify_schema_v3_structural_kernel(
                _Font("Production Family"), application=app, host=host
            )

        self.assertEqual(host.apply_calls, 0)

    def test_schema_v3_gate_qualifies_all_structural_domains_and_restores_baseline(self) -> None:
        host = _StructuralHost()
        app = GlyphsMCPApplication(host)
        before = copy.deepcopy(host.model)

        result = verify_schema_v3_structural_kernel(
            _Font(), application=app, host=host
        )

        self.assertEqual(host.model, before)
        self.assertEqual(result["baselineFingerprint"], fingerprint_model(before))
        self.assertEqual(result["finalFingerprint"], fingerprint_model(before))
        self.assertEqual(result["qualifiedDomains"], [
            "glyphs",
            "opentype",
            "instances",
            "selective_revert",
            "atomic_refusal",
        ])
        self.assertEqual(result["successfulTransactionCount"], host.apply_calls)
        self.assertEqual(result["successfulTransactionCount"], 22)
        self.assertEqual(result["refusalCount"], 2)
        self.assertTrue(result["exactBaselineRestored"])
        self.assertTrue(result["singleTransactionResponses"])
        self.assertTrue(result["auditReceiptsPresent"])
        self.assertTrue(result["changeLogCommitsPresent"])

    def test_schema_v3_gate_leaves_no_partial_state_when_a_phase_fails(self) -> None:
        host = _StructuralHost()
        app = GlyphsMCPApplication(host)
        before = copy.deepcopy(host.model)
        original_invoke = app.invoke
        calls = 0

        def fail_during_opentype(tool, arguments=None):
            nonlocal calls
            calls += 1
            if calls == 8:
                raise RuntimeError("injected live-gate failure")
            return original_invoke(tool, arguments)

        app.invoke = fail_during_opentype

        with self.assertRaises(RuntimeError):
            verify_schema_v3_structural_kernel(
                _Font(), application=app, host=host
            )

        self.assertEqual(host.model, before)

    def test_schema_v4_master_gate_round_trips_one_composite_lifecycle(self) -> None:
        host = _StructuralHost()
        app = GlyphsMCPApplication(host)
        before = copy.deepcopy(host.model)
        model_reads = 0
        original_model = _StructuralGateSession.model

        def counted_model(session):
            nonlocal model_reads
            model_reads += 1
            return original_model(session)

        with mock.patch.object(_StructuralGateSession, "model", counted_model):
            result = verify_schema_v4_master_lifecycle(
                _Font(), application=app, host=host
            )

        self.assertEqual(host.model, before)
        self.assertEqual(result["baselineFingerprint"], fingerprint_model(before))
        self.assertEqual(result["finalFingerprint"], fingerprint_model(before))
        self.assertEqual(
            result["qualifiedDomains"],
            ["master_lifecycle", "atomic_refusal"],
        )
        self.assertEqual(result["successfulTransactionCount"], 8)
        self.assertEqual(result["refusalCount"], 2)
        self.assertTrue(result["exactBaselineRestored"])
        self.assertTrue(result["singleTransactionResponses"])
        self.assertTrue(result["auditReceiptsPresent"])
        self.assertTrue(result["changeLogCommitsPresent"])
        self.assertIn("stageTimingTotalsMs", result)
        self.assertIn("gateDurationMs", result)
        self.assertGreaterEqual(result["gateDurationMs"], 0)
        self.assertEqual(
            model_reads,
            1,
            "the gate must use verified commits for intermediate proof and recapture only the final baseline",
        )

    def test_schema_v4_master_gate_refuses_non_disposable_font(self) -> None:
        host = _StructuralHost()
        app = GlyphsMCPApplication(host)

        with self.assertRaises(ValueError):
            verify_schema_v4_master_lifecycle(
                _Font("Production Family"), application=app, host=host
            )

        self.assertEqual(host.apply_calls, 0)

    def test_schema_v5_layer_gate_round_trips_interpolation_and_membership(self) -> None:
        host = _StructuralHost()
        app = GlyphsMCPApplication(host)
        before = copy.deepcopy(host.model)
        model_reads = 0
        original_model = _StructuralGateSession.model

        def counted_model(session):
            nonlocal model_reads
            model_reads += 1
            return original_model(session)

        with mock.patch.object(_StructuralGateSession, "model", counted_model):
            result = verify_schema_v5_layer_lifecycle(
                _Font(), application=app, host=host
            )

        self.assertEqual(host.model, before)
        self.assertEqual(result["baselineFingerprint"], fingerprint_model(before))
        self.assertEqual(result["finalFingerprint"], fingerprint_model(before))
        self.assertEqual(
            result["qualifiedDomains"],
            ["layer_lifecycle", "interpolation_rules", "atomic_refusal"],
        )
        # Five forward lifecycle actions and their five exact reverts. A
        # second non-master layer is required because Glyphs master layers
        # form an immutable prefix and one trailing layer cannot be reordered.
        self.assertEqual(result["successfulTransactionCount"], 10)
        self.assertEqual(result["refusalCount"], 2)
        self.assertTrue(result["exactBaselineRestored"])
        self.assertTrue(result["singleTransactionResponses"])
        self.assertTrue(result["auditReceiptsPresent"])
        self.assertTrue(result["changeLogCommitsPresent"])
        self.assertEqual(model_reads, 1)

    def test_schema_v5_layer_gate_refuses_non_disposable_font(self) -> None:
        host = _StructuralHost()
        app = GlyphsMCPApplication(host)

        with self.assertRaises(ValueError):
            verify_schema_v5_layer_lifecycle(
                _Font("Production Family"), application=app, host=host
            )

        self.assertEqual(host.apply_calls, 0)


if __name__ == "__main__":
    unittest.main()
