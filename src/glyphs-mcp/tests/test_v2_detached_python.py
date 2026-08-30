"""Detached Python namespace, discovery, and structured failure contracts."""

from __future__ import annotations

import builtins
import contextlib
import copy
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.audit import AuditLog  # noqa: E402
from glyphs_mcp_v2.adapters.document import GlyphsDocumentHost  # noqa: E402
from glyphs_mcp_v2.detached_python import (  # noqa: E402
    DANGEROUS_IMPORT_ROOTS,
    DENIED_BUILTIN_NAMES,
    HOST_EFFECT_METHOD_NAMES,
    INTERNAL_BUILTIN_NAMES,
    build_detached_namespace,
    builtin_snapshot,
    detached_builtins,
    detached_python_registry,
    require_reviewed_builtin_snapshot,
)
from glyphs_mcp_v2.operations import OperationStore  # noqa: E402
from glyphs_mcp_v2.generic_tools import project_reference, resolve_selector  # noqa: E402
from glyphs_mcp_v2.python_execution import (  # noqa: E402
    PythonExecutionRequest,
    PythonExecutionService,
)
from glyphs_mcp_v2.semantic import fingerprint_model  # noqa: E402
from glyphs_mcp_v2.transactions import TransactionKernel  # noqa: E402


class _NamespaceHost:
    def __init__(self) -> None:
        self.model = {"font": {"familyName": "Detached"}, "glyphs": {}}
        self.dirty = False
        self.source_fingerprint = "sha256:file-a"
        self.force_host_assertion = False
        self.change_source_before_failure = False

    def capture_model(self, _document_id):
        return copy.deepcopy(self.model)

    def list_documents(self):
        return (SimpleNamespace(document_id="doc", has_unsaved_changes=self.dirty),)

    def capture_source_file_state(self, _document_id):
        return {
            "exists": True,
            "contentFingerprint": self.source_fingerprint,
        }

    def preview_python(self, request, before_model):
        if self.change_source_before_failure:
            self.source_fingerprint = "sha256:file-b"
        if self.force_host_assertion:
            error = AssertionError("host invariant")
            error.stage_timings = {"evaluationCaptureMs": 0.5}
            raise error
        stdout = io.StringIO()
        stderr = io.StringIO()
        namespace = build_detached_namespace(
            {
                "font": copy.deepcopy(before_model),
                "glyph": None,
                "master": None,
                "layer": None,
                "selectedLayers": [],
            }
        )
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(
                    compile(
                        request.code or "",
                        "<glyphs-mcp-staged>",
                        "exec",
                    ),
                    namespace,
                    namespace,
                )
        except BaseException as error:
            error.stage_timings = {"evaluationCaptureMs": 0.5}
            raise
        return {
            "afterModel": copy.deepcopy(before_model),
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "observedDocumentChanges": [],
            "nativeArchiveComparison": {
                "equivalent": True,
                "mismatchCount": 0,
                "mismatchLocations": [],
                "truncated": False,
            },
        }

    def apply_change_set(self, _document_id, change_set):
        self.model = change_set.apply(self.model)

    def restore_model(self, _document_id, model):
        self.model = copy.deepcopy(model)


class _Immediate:
    @staticmethod
    def run(callback):
        return callback()


class _MetricsLayer:
    def __init__(self, master_id, *, left, right=50, key=None) -> None:
        self.layerId = master_id
        self.associatedMasterId = master_id
        self.leftMetricsKey = key
        self.rightMetricsKey = None
        self.widthMetricsKey = None
        self.width = 500
        self.LSB = left
        self.RSB = right
        self.vertOrigin = None
        self.vertWidth = None
        self.TSB = None
        self.BSB = None
        self.paths = ()
        self.shapes = []
        self.parent = None

    def syncMetrics(self):
        key = self.leftMetricsKey or self.parent.leftMetricsKey
        if key not in {"=H", "==H+5", "=H/2"}:
            return
        font = self.parent.parent
        reference = next(glyph for glyph in font.glyphs if glyph.name == "H")
        layer = next(
            candidate
            for candidate in reference.layers
            if candidate.associatedMasterId == self.associatedMasterId
        )
        if key == "==H+5":
            self.LSB = layer.LSB + 5
        elif key == "=H/2":
            self.LSB = layer.LSB / 2
        else:
            self.LSB = layer.LSB


class _MetricsGlyph:
    def __init__(self, name, layers, *, left_key=None) -> None:
        self.name = name
        self.leftMetricsKey = left_key
        self.layers = list(layers)
        self.parent = None
        for layer in self.layers:
            layer.parent = self


class _MetricsFont:
    def __init__(self) -> None:
        self.familyName = "Metric Key Fixture"
        self.filepath = "/fonts/metric-key-fixture.glyphs"
        self.parent = None
        self.glyphs = [
            _MetricsGlyph(
                "H",
                [
                    _MetricsLayer("regular", left=40),
                    _MetricsLayer("bold", left=74),
                ],
            ),
            _MetricsGlyph(
                "target",
                [
                    _MetricsLayer("regular", left=12),
                    _MetricsLayer("bold", left=18),
                ],
                left_key="=H",
            ),
            _MetricsGlyph(
                "override",
                [
                    _MetricsLayer("regular", left=9, key="==H+5"),
                    _MetricsLayer("bold", left=11, key="=H/2"),
                ],
                left_key="=H",
            ),
        ]
        for glyph in self.glyphs:
            glyph.parent = self

    def copy(self):
        return copy.deepcopy(self)


class _MetricsApp:
    def __init__(self, font) -> None:
        self.font = font
        self.fonts = [font]
        self.documents = []


class V2DetachedPythonContractTests(unittest.TestCase):
    def service(self):
        host = _NamespaceHost()
        reviews = OperationStore()
        service = PythonExecutionService(
            host=host,
            transactions=TransactionKernel(host),
            reviews=reviews,
            checkpoints=OperationStore(),
            audit=AuditLog(),
        )
        return service, host, reviews

    @staticmethod
    def request(host, code, *, mode="read_only"):
        return PythonExecutionRequest(
            code=code,
            reason="detached namespace contract test",
            intended_effect="read" if mode == "read_only" else "document_edit",
            execution_mode=(
                "live_open_world" if mode == "read_only" else "staged_document"
            ),
            document_id="doc",
            expected_document_fingerprint=(
                fingerprint_model(host.model)
                if mode == "staged_document"
                else None
            ),
        )

    def test_registry_exactly_describes_the_runtime_namespace(self) -> None:
        registry = detached_python_registry()
        contract = registry["pythonExecution"]["detachedNamespace"]
        runtime = detached_builtins()

        self.assertEqual(
            contract["builtins"],
            sorted(set(runtime) - set(INTERNAL_BUILTIN_NAMES)),
        )
        self.assertEqual(
            contract["internalBuiltins"], sorted(INTERNAL_BUILTIN_NAMES)
        )
        self.assertEqual(
            registry["pythonModes"],
            ["read_only", "staged_document", "live_open_world"],
        )
        self.assertEqual(contract["appliesToModes"], ["read_only", "staged_document"])
        self.assertEqual(
            contract["internalGlobals"]["__name__"],
            "__glyphs_mcp_detached__",
        )
        self.assertFalse(contract["securitySandbox"])
        self.assertRegex(contract["contractFingerprint"], r"^sha256:[0-9a-f]{64}$")
        self.assertTrue(
            {
                "repr",
                "RuntimeError",
                "AssertionError",
                "type",
                "super",
            }.issubset(runtime)
        )
        self.assertTrue(DENIED_BUILTIN_NAMES.isdisjoint(contract["builtins"]))
        self.assertEqual(
            contract["deniedCapabilities"]["dangerousImportRoots"],
            sorted(DANGEROUS_IMPORT_ROOTS),
        )
        self.assertEqual(
            contract["deniedCapabilities"]["hostEffectMethods"],
            sorted(HOST_EFFECT_METHOD_NAMES),
        )

    @unittest.skipUnless(sys.version_info[:2] == (3, 14), "Python 3.14 contract gate")
    def test_python_314_snapshot_rejects_unreviewed_builtin_drift(self) -> None:
        self.assertTrue(builtin_snapshot()["reviewed"])
        with mock.patch.object(builtins, "contractDriftProbe", object(), create=True):
            with self.assertRaisesRegex(RuntimeError, "built-ins changed"):
                require_reviewed_builtin_snapshot()

    def test_near_standard_builtins_support_repr_runtime_error_and_classes(self) -> None:
        service, host, _reviews = self.service()
        result = service.execute(
            self.request(
                host,
                "class Result:\n"
                "    @classmethod\n"
                "    def value(cls):\n"
                "        return repr(cls.__name__)\n"
                "try:\n"
                "    raise RuntimeError(Result.value())\n"
                "except RuntimeError as error:\n"
                "    print(repr(error))",
            )
        ).to_dict()

        self.assertTrue(result["ok"])
        self.assertIn("RuntimeError", result["data"]["stdout"])
        self.assertFalse(result["data"]["liveDocumentChanged"])

    def test_targeted_failures_apply_to_both_detached_modes(self) -> None:
        cases = (
            ("import collections", "staged_import_unavailable"),
            ("help('detached')", "staged_symbol_unavailable"),
            ("assert False, 'candidate rejected'", "staged_assertion_failed"),
            ("raise AssertionError('candidate rejected')", "staged_assertion_failed"),
            ("repp('misspelled')", None),
        )
        for mode in ("read_only", "staged_document"):
            for code, targeted in cases:
                with self.subTest(mode=mode, code=code):
                    service, host, reviews = self.service()
                    result = service.execute(
                        self.request(host, code, mode=mode)
                    ).to_dict()

                    self.assertFalse(result["ok"])
                    expected = targeted or (
                        "python_execution_failed"
                        if mode == "read_only"
                        else "python_preview_failed"
                    )
                    self.assertEqual(result["error"]["code"], expected)
                    self.assertFalse(result["data"]["previewCreated"])
                    self.assertTrue(result["data"]["detachedCloneDiscarded"])
                    self.assertFalse(result["data"]["liveDocumentWasExecutionTarget"])
                    self.assertFalse(result["data"]["liveDocumentChanged"])
                    self.assertEqual(
                        result["data"]["baseDocumentFingerprint"],
                        result["data"]["liveAfterFingerprint"],
                    )
                    self.assertRegex(
                        result["data"]["codeHash"], r"^sha256:[0-9a-f]{64}$"
                    )
                    self.assertIn("line", result["error"]["details"])
                    self.assertEqual(
                        result["data"]["stageTimings"]["evaluationCaptureMs"],
                        0.5,
                    )
                    self.assertFalse(reviews.list_records())

    def test_dangerous_imports_and_calls_are_policy_violations_in_both_modes(
        self,
    ) -> None:
        cases = (
            "import os",
            "open('/tmp/detached-contract', 'w')",
            "input('detached')",
            "breakpoint()",
            "compile('1', '<value>', 'eval')",
            "eval('1')",
            "exec('value = 1')",
            "__import__('math')",
            "font.close()",
        )
        for mode in ("read_only", "staged_document"):
            for code in cases:
                with self.subTest(mode=mode, code=code):
                    service, host, reviews = self.service()
                    result = service.execute(
                        self.request(host, code, mode=mode)
                    ).to_dict()

                    self.assertFalse(result["ok"])
                    self.assertEqual(
                        result["error"]["code"], "staged_policy_violation"
                    )
                    self.assertFalse(reviews.list_records())

    def test_host_assertion_is_not_misclassified_as_script_validation(self) -> None:
        service, host, _reviews = self.service()
        host.force_host_assertion = True
        result = service.execute(
            self.request(host, "print('candidate')", mode="staged_document")
        ).to_dict()

        self.assertEqual(result["error"]["code"], "python_preview_failed")
        self.assertEqual(result["error"]["details"]["exceptionType"], "AssertionError")
        self.assertNotIn("assertionOrigin", result["error"]["details"])

    def test_concurrent_save_is_evidence_not_a_detached_failure_side_effect(self) -> None:
        service, host, _reviews = self.service()
        host.change_source_before_failure = True
        result = service.execute(
            self.request(host, "assert False, 'after save'", mode="staged_document")
        ).to_dict()

        self.assertEqual(result["error"]["code"], "staged_assertion_failed")
        self.assertTrue(result["data"]["sourceFileChanged"])
        self.assertFalse(result["data"]["liveDocumentChanged"])
        self.assertFalse(result["data"]["stateMayHaveChanged"])
        self.assertFalse(result["data"]["fontSaved"])

    def test_metrics_key_resolution_uses_the_associated_master_on_a_detached_copy(self) -> None:
        font = _MetricsFont()
        host = GlyphsDocumentHost(_MetricsApp(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id

        observations = host.inspect_layers(
            document_id,
            ("target", "override"),
            include_metrics=True,
            resolve_metrics=True,
        )

        self.assertEqual(
            observations[("target", "regular")]["currentMetrics"]["leftBearing"],
            12,
        )
        self.assertEqual(
            observations[("target", "regular")]["resolvedMetrics"]["leftBearing"],
            40,
        )
        self.assertEqual(
            observations[("target", "bold")]["currentMetrics"]["leftBearing"],
            18,
        )
        self.assertEqual(
            observations[("target", "bold")]["resolvedMetrics"]["leftBearing"],
            74,
        )
        self.assertEqual([layer.LSB for layer in font.glyphs[1].layers], [12, 18])
        self.assertEqual(
            observations[("override", "regular")]["resolvedMetrics"]["leftBearing"],
            45,
        )
        self.assertEqual(
            observations[("override", "bold")]["resolvedMetrics"]["leftBearing"],
            37,
        )
        self.assertEqual([layer.LSB for layer in font.glyphs[2].layers], [9, 11])

        model = {
            "glyphs": {
                "override": {
                    "name": "override",
                    "layers": [
                        {
                            "id": "bold",
                            "masterId": "bold",
                            "leftMetricsKey": "=H/2",
                        }
                    ],
                }
            }
        }
        reference = resolve_selector(
            model,
            {
                "entity": "layer",
                "ids": ["bold"],
                "parent": {"glyphName": "override"},
            },
        )[0]
        projected = project_reference(
            reference,
            {"fields": ["inheritance.metrics"]},
            observations=observations,
        )
        inheritance = projected["values"]["inheritance.metrics"]
        self.assertEqual(inheritance["keys"]["left"], "=H/2")
        self.assertEqual(inheritance["current"]["leftBearing"], 11)
        self.assertEqual(inheritance["resolved"]["leftBearing"], 37)
        self.assertEqual(
            projected["provenance"]["inheritance.metrics"],
            "canonical+native",
        )


if __name__ == "__main__":
    unittest.main()
