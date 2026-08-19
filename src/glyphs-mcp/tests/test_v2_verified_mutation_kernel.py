"""Specification for the verified apply-first v2 mutation kernel."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.mutation import (  # noqa: E402
    MutationPlanner,
    VerifiedMutationPlan,
    mutation_scope,
)
from glyphs_mcp_v2.semantic import (  # noqa: E402
    canonical_json,
    diff_models,
    fingerprint_model,
)
from glyphs_mcp_v2 import semantic as semantic_module  # noqa: E402
from glyphs_mcp_v2.transactions import TransactionKernel  # noqa: E402
from glyphs_mcp_v2.transactions import StaleDocumentError  # noqa: E402
from glyphs_mcp_v2.transactions import TransactionVerificationError  # noqa: E402


def _model() -> dict:
    return {
        "font": {"familyName": "Kernel", "upm": 1000},
        "masters": [{"id": "m0", "name": "Regular"}],
        "instances": [],
        "glyphs": {
            "A": {
                "name": "A",
                "id": "id_A",
                "export": True,
                "layers": {
                    "m0": {"width": 500, "LSB": 40, "RSB": 60, "anchors": {}}
                },
            }
        },
        "kerning": {},
        "features": [],
        "classes": [],
        "featurePrefixes": [],
    }


class _DerivedHost:
    """A host where Glyphs derives RSB from width after writable updates."""

    def __init__(self) -> None:
        self.model = _model()
        self.clone_calls = 0
        self.apply_calls = 0
        self.restore_calls = 0

    @staticmethod
    def _derive(model: dict) -> dict:
        result = copy.deepcopy(model)
        layer = result["glyphs"]["A"]["layers"]["m0"]
        layer["RSB"] = layer["width"] - 440
        return result

    def capture_model(self, document_id):
        return copy.deepcopy(self.model)

    def simulate_change_set(self, document_id, change_set):
        self.clone_calls += 1
        return self._derive(change_set.apply(self.model))

    def apply_change_set(self, document_id, change_set):
        self.apply_calls += 1
        self.model = self._derive(change_set.apply(self.model))

    def restore_model(self, document_id, model):
        self.restore_calls += 1
        self.model = copy.deepcopy(model)


class _CanonicalReconciliationHost(_DerivedHost):
    def __init__(self) -> None:
        super().__init__()
        self.reconciliation_calls = 0
        self.required_after = None
        self.received_replacements = None

    def simulate_reconciliation(
        self, document_id, change_set, required_after_model, before_model
    ):
        self.reconciliation_calls += 1
        self.required_after = copy.deepcopy(required_after_model)
        return {
            "afterModel": copy.deepcopy(required_after_model),
            "replayReplacements": [
                ["glyphs", "A", "layers", "m0", "paths"]
            ],
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
        self.apply_calls += 1
        self.received_replacements = tuple(tuple(path) for path in replay_replacements)
        self.model = copy.deepcopy(self.required_after)


class _DriftingCanonicalReconciliationHost(_CanonicalReconciliationHost):
    def simulate_reconciliation(
        self, document_id, change_set, required_after_model, before_model
    ):
        self.reconciliation_calls += 1
        self.required_after = copy.deepcopy(required_after_model)
        drifted = copy.deepcopy(required_after_model)
        drifted["glyphs"]["A"]["layers"]["m0"]["RSB"] += 1
        return {"afterModel": drifted, "replayReplacements": []}


class _LateSettlingHost(_DerivedHost):
    """A host whose first readback precedes an asynchronous derived update."""

    def __init__(self) -> None:
        super().__init__()
        self._late_width = None

    def apply_change_set(self, document_id, change_set):
        super().apply_change_set(document_id, change_set)
        self._late_width = 500

    def capture_stable_model(self, document_id):
        immediate = self.capture_model(document_id)
        if self._late_width is not None:
            self.model["glyphs"]["A"]["layers"]["m0"]["width"] = self._late_width
            self.model = self._derive(self.model)
            self._late_width = None
        settled = self.capture_model(document_id)
        self.asserted_immediate_model = immediate
        return settled


class _PostSettleReconciliationHost(_LateSettlingHost):
    def __init__(self) -> None:
        super().__init__()
        self.reconciliation_calls = 0
        self.reconciliation_capabilities = None

    def reconcile_verified_state(
        self,
        document_id,
        actual_model,
        expected_model,
        *,
        capabilities=(),
        execution_context=None,
    ):
        self.reconciliation_calls += 1
        self.reconciliation_capabilities = tuple(capabilities)
        self.model = copy.deepcopy(expected_model)


class _NonConvergingPostSettleHost(_PostSettleReconciliationHost):
    def reconcile_verified_state(
        self,
        document_id,
        actual_model,
        expected_model,
        *,
        capabilities=(),
        execution_context=None,
    ):
        self.reconciliation_calls += 1


class VerifiedMutationKernelTests(unittest.TestCase):
    def test_mutation_scope_resolves_transitive_component_and_metrics_dependencies(self) -> None:
        before = _model()
        before["glyphs"].update(
            {
                "Aacute": {
                    "name": "Aacute",
                    "layers": {
                        "m0": {
                            "components": [{"name": "A"}],
                            "leftMetricsKey": "=A+10",
                        }
                    },
                },
                "Aacute.sc": {
                    "name": "Aacute.sc",
                    "layers": {
                        "m0": {"components": [{"name": "Aacute"}]}
                    },
                },
                "B": {"name": "B", "layers": {"m0": {}}},
            }
        )
        after = copy.deepcopy(before)
        after["glyphs"]["A"]["layers"]["m0"]["width"] = 520

        scope = mutation_scope(before, diff_models(before, after))

        self.assertEqual(scope.roots, ("glyphs",))
        self.assertEqual(scope.glyph_names, ("A", "Aacute", "Aacute.sc"))

    def test_canonical_numbers_normalize_negative_zero_and_integral_floats(self) -> None:
        integer = {"font": {"value": 0, "other": 12}}
        floating = {"font": {"value": -0.0, "other": 12.0}}

        self.assertEqual(canonical_json(integer), canonical_json(floating))
        self.assertEqual(fingerprint_model(integer), fingerprint_model(floating))
        self.assertEqual(diff_models(integer, floating).changes, ())

    def test_builtin_canonical_values_do_not_pay_abstract_mapping_checks(self) -> None:
        class ExplodingMappingMeta(type):
            def __instancecheck__(cls, instance):
                raise AssertionError(
                    "built-in canonical values must bypass Mapping ABC checks"
                )

        class ExplodingMapping(metaclass=ExplodingMappingMeta):
            pass

        value = {
            "font": {"upm": 1000, "note": None},
            "glyphs": {"A": {"paths": [[0, 1.0, -0.0, True, "line"]]}},
        }
        with mock.patch.object(semantic_module, "Mapping", ExplodingMapping):
            encoded = canonical_json(value)

        self.assertEqual(
            encoded,
            '{"font":{"note":null,"upm":1000},"glyphs":{"A":{"paths":[[0,1,0,true,"line"]]}}}',
        )

    def test_diff_models_self_verifies_type_sensitive_scalar_changes(self) -> None:
        before = {"font": {"value": 1.25}}
        after = {"font": {"value": 2}}
        changes = diff_models(before, after)

        self.assertEqual(changes.apply(before), after)
        self.assertEqual(changes.after_fingerprint, fingerprint_model(after))

    def test_plan_separates_requested_writes_from_complete_observed_diff(self) -> None:
        host = _DerivedHost()
        before = host.capture_model("doc_kernel")
        requested_after = copy.deepcopy(before)
        requested_after["glyphs"]["A"]["layers"]["m0"]["width"] = 520
        requested = diff_models(before, requested_after)

        plan = MutationPlanner(host).plan(
            document_id="doc_kernel",
            expected_document_fingerprint=fingerprint_model(before),
            requested_change_set=requested,
            operation_id="op_direct",
        )

        self.assertIsInstance(plan, VerifiedMutationPlan)
        self.assertEqual(len(plan.writable_change_set.changes), 1)
        self.assertEqual(len(plan.observed_change_set.changes), 2)
        self.assertEqual(
            {change.path[-1] for change in plan.observed_change_set.changes},
            {"width", "RSB"},
        )
        self.assertEqual(host.clone_calls, 1)

    def test_stale_fingerprint_rejects_before_detached_simulation(self) -> None:
        host = _DerivedHost()
        before = host.capture_model("doc_kernel")
        requested_after = copy.deepcopy(before)
        requested_after["glyphs"]["A"]["export"] = False

        with self.assertRaises(StaleDocumentError):
            MutationPlanner(host).plan(
                document_id="doc_kernel",
                expected_document_fingerprint="sha256:stale",
                requested_change_set=diff_models(before, requested_after),
                operation_id="op_stale",
            )

        self.assertEqual(host.clone_calls, 0)
        self.assertEqual(host.apply_calls, 0)

    def test_plan_applies_once_and_verifies_complete_derived_readback(self) -> None:
        host = _DerivedHost()
        before = host.capture_model("doc_kernel")
        requested_after = copy.deepcopy(before)
        requested_after["glyphs"]["A"]["layers"]["m0"]["width"] = 520
        plan = MutationPlanner(host).plan(
            document_id="doc_kernel",
            expected_document_fingerprint=fingerprint_model(before),
            requested_change_set=diff_models(before, requested_after),
            operation_id="op_direct",
        )

        result = TransactionKernel(host).apply_plan(plan)

        self.assertEqual(host.apply_calls, 1)
        self.assertEqual(result.requested_change_count, 1)
        self.assertEqual(result.observed_change_count, 2)
        self.assertEqual(result.operation_id, "op_direct")
        self.assertEqual(fingerprint_model(host.model), plan.after_fingerprint)
        self.assertEqual(result.inverse.before_fingerprint, plan.after_fingerprint)
        # The inverse contains authoritative writes only. The host recomputes
        # projected fields while applying it, just as Glyphs does natively.
        self.assertEqual(host._derive(result.inverse.apply(host.model)), before)

    def test_transaction_verifies_the_settled_host_state_not_the_first_readback(self) -> None:
        host = _LateSettlingHost()
        before = host.capture_model("doc_kernel")
        requested_after = copy.deepcopy(before)
        requested_after["glyphs"]["A"]["layers"]["m0"]["width"] = 520
        plan = MutationPlanner(host).plan(
            document_id="doc_kernel",
            expected_document_fingerprint=fingerprint_model(before),
            requested_change_set=diff_models(before, requested_after),
            operation_id="op_late_settle",
        )

        with self.assertRaises(TransactionVerificationError) as raised:
            TransactionKernel(host).apply_plan(plan)

        self.assertTrue(raised.exception.rollback_succeeded)
        self.assertEqual(host.model, before)
        self.assertEqual(host.apply_calls, 1)
        self.assertEqual(host.restore_calls, 1)

    def test_transaction_reconciles_writable_post_settle_drift_in_one_operation(self) -> None:
        host = _PostSettleReconciliationHost()
        before = host.capture_model("doc_kernel")
        requested_after = copy.deepcopy(before)
        requested_after["glyphs"]["A"]["layers"]["m0"]["width"] = 520
        plan = MutationPlanner(host).plan(
            document_id="doc_kernel",
            expected_document_fingerprint=fingerprint_model(before),
            requested_change_set=diff_models(before, requested_after),
            operation_id="op_post_settle",
            capabilities=("master_lifecycle",),
        )

        result = TransactionKernel(host).apply_plan(plan)

        self.assertEqual(result.after_fingerprint, plan.after_fingerprint)
        self.assertEqual(host.model, plan.expected_after_model)
        self.assertEqual(host.apply_calls, 1)
        self.assertEqual(host.reconciliation_calls, 1)
        self.assertEqual(host.reconciliation_capabilities, ("master_lifecycle",))
        self.assertEqual(host.restore_calls, 0)

    def test_nonconverging_post_settle_reconciliation_is_bounded_and_restored(self) -> None:
        host = _NonConvergingPostSettleHost()
        before = host.capture_model("doc_kernel")
        requested_after = copy.deepcopy(before)
        requested_after["glyphs"]["A"]["layers"]["m0"]["width"] = 520
        plan = MutationPlanner(host).plan(
            document_id="doc_kernel",
            expected_document_fingerprint=fingerprint_model(before),
            requested_change_set=diff_models(before, requested_after),
            operation_id="op_nonconverging_post_settle",
        )

        with self.assertRaises(TransactionVerificationError) as raised:
            TransactionKernel(host).apply_plan(plan)

        self.assertTrue(raised.exception.rollback_succeeded)
        self.assertEqual(host.apply_calls, 1)
        self.assertEqual(host.reconciliation_calls, 3)
        self.assertEqual(host.restore_calls, 1)
        self.assertEqual(host.model, before)

    def test_required_canonical_target_selects_and_replays_one_detached_strategy(self) -> None:
        host = _CanonicalReconciliationHost()
        before = host.capture_model("doc_kernel")
        required_after = copy.deepcopy(before)
        required_after["glyphs"]["A"]["layers"]["m0"]["width"] = 520
        requested = diff_models(before, required_after)

        plan = MutationPlanner(host).plan(
            document_id="doc_kernel",
            expected_document_fingerprint=fingerprint_model(before),
            requested_change_set=requested,
            operation_id="op_reconcile",
            required_after_model=required_after,
        )
        result = TransactionKernel(host).apply_plan(plan)

        expected_hint = (("glyphs", "A", "layers", "m0", "paths"),)
        self.assertEqual(host.reconciliation_calls, 1)
        self.assertEqual(plan.replay_replacements, expected_hint)
        self.assertEqual(host.received_replacements, expected_hint)
        self.assertEqual(result.after_fingerprint, fingerprint_model(required_after))

    def test_required_canonical_target_is_an_invariant_not_a_planner_hint(self) -> None:
        host = _DriftingCanonicalReconciliationHost()
        before = host.capture_model("doc_kernel")
        required_after = copy.deepcopy(before)
        required_after["glyphs"]["A"]["layers"]["m0"]["width"] = 520
        requested = diff_models(before, required_after)

        with self.assertRaisesRegex(ValueError, "canonical target"):
            MutationPlanner(host).plan(
                document_id="doc_kernel",
                expected_document_fingerprint=fingerprint_model(before),
                requested_change_set=requested,
                operation_id="op_reconcile_drift",
                required_after_model=required_after,
            )

        self.assertEqual(host.apply_calls, 0)


if __name__ == "__main__":
    unittest.main()
