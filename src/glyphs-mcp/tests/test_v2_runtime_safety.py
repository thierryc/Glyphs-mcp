"""Pure and process-local tests for recoverable live-Python safety."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.adapters import document as document_adapter  # noqa: E402
from glyphs_mcp_v2.runtime_safety import (  # noqa: E402
    SAFETY_STATES,
    SafetySlotSnapshot,
    ScriptingRuntimeUnavailableError,
    ScriptingSafetyStateMachine,
    StaleScriptingRuntimeIncidentError,
    agent_recovery_directive,
)


class ScriptingSafetyStateMachineTests(unittest.TestCase):
    @staticmethod
    def _slot(state: str = "residual_guard", repairable: bool = True):
        return SafetySlotSnapshot(
            slot_id="python_fixture_save",
            owner_class="Fixture",
            selector="save",
            kind="python_descriptor",
            state=state,
            repairable=repairable,
        )

    def test_legal_recovery_preserves_first_cause_and_incident_identity(self):
        machine = ScriptingSafetyStateMachine()
        machine.begin("execution_1")
        machine.begin_recovery(trigger="execution_teardown")
        first = machine.mark_incident(
            target_state="recovery_required",
            phase="restore",
            reason_code="first_failure",
            message="first cause",
            affected_slots=(self._slot(),),
            trigger="execution_teardown",
        )
        machine.begin_recovery(trigger="agent")
        repeated = machine.mark_incident(
            target_state="recovery_required",
            phase="repair",
            reason_code="later_failure",
            message="later cause",
            affected_slots=(self._slot(),),
            trigger="agent",
        )

        self.assertEqual(repeated.incident_id, first.incident_id)
        self.assertEqual(repeated.phase, "restore")
        self.assertEqual(repeated.reason_code, "first_failure")
        self.assertEqual(repeated.message, "first cause")
        directive = agent_recovery_directive(machine.snapshot())
        self.assertEqual(
            directive["arguments"], {"expectedIncidentId": first.incident_id}
        )
        self.assertEqual(directive["maxRepairAttempts"], 1)

        machine.begin_recovery(trigger="agent")
        machine.mark_healthy(trigger="agent")
        self.assertEqual(machine.snapshot().state, "healthy")
        self.assertEqual(machine.incidents()[-1].incident_id, first.incident_id)
        self.assertIsNotNone(machine.incidents()[-1].resolved_at)

    def test_illegal_transition_is_rejected_and_no_poison_state_exists(self):
        machine = ScriptingSafetyStateMachine()
        machine.begin("execution_1")
        with self.assertRaisesRegex(ValueError, "active -> healthy"):
            machine.mark_healthy(trigger="illegal")
        self.assertNotIn("poisoned", SAFETY_STATES)
        self.assertEqual(machine.snapshot().state, "active")

    def test_incident_and_transition_journals_are_bounded(self):
        machine = ScriptingSafetyStateMachine(
            max_incidents=64, max_transitions=256
        )
        for index in range(90):
            machine.begin_recovery(trigger="test_{}".format(index))
            machine.mark_incident(
                target_state="degraded",
                phase="test",
                reason_code="failure_{}".format(index),
                message="failure {}".format(index),
                trigger="test",
            )
            machine.begin_recovery(trigger="test")
            machine.mark_healthy(trigger="test")

        self.assertEqual(len(machine.incidents()), 64)
        self.assertEqual(len(machine.transition_history()), 256)
        self.assertLessEqual(len(machine.snapshot().transitions), 32)

    def test_unrepairable_slot_recommends_restart_only_when_proven(self):
        machine = ScriptingSafetyStateMachine()
        machine.begin_recovery(trigger="test")
        machine.mark_incident(
            target_state="recovery_required",
            phase="repair",
            reason_code="unverifiable",
            message="native slot cannot be inspected",
            affected_slots=(self._slot("unverifiable", False),),
            trigger="test",
        )
        self.assertEqual(machine.snapshot().next_action, "restart_glyphs")
        self.assertFalse(machine.snapshot().automatic_repair_available)


class NativeGuardManagerTests(unittest.TestCase):
    def test_one_hundred_clean_cycles_never_latch_unhealthy(self):
        class SaveDocument:
            def saveDocument_(self, sender):
                return sender

        manager = document_adapter._WorkingSourceSaveGuardManager()
        document = SaveDocument()
        original = vars(SaveDocument)["saveDocument_"]
        with mock.patch.object(
            document_adapter, "_LIVE_SOURCE_SAVE_GUARD_MANAGER", manager
        ):
            for _index in range(100):
                with document_adapter._WorkingSourceSaveRuntimeGuard(
                    [document],
                    native_identity=lambda value: ("python", id(value)),
                ):
                    pass
                self.assertEqual(manager.snapshot().state, "healthy")
                self.assertIs(vars(SaveDocument)["saveDocument_"], original)

        self.assertEqual(document.saveDocument_("native save"), "native save")

    def test_public_repair_runs_through_the_host_main_thread_executor(self):
        class RecordingExecutor:
            def __init__(self):
                self.calls = 0

            def run(self, callback):
                self.calls += 1
                return callback()

        manager = document_adapter._WorkingSourceSaveGuardManager()
        executor = RecordingExecutor()
        host = document_adapter.GlyphsDocumentHost(object(), executor=executor)
        with mock.patch.object(
            document_adapter, "_LIVE_SOURCE_SAVE_GUARD_MANAGER", manager
        ):
            result = host.repair_scripting_runtime(trigger="agent")

        self.assertEqual(executor.calls, 1)
        self.assertEqual(result["repair"]["result"], "not_needed")
        self.assertEqual(result["scriptingRuntimeSafety"]["state"], "healthy")

    def test_nested_execution_is_busy_and_first_lease_recovers(self):
        manager = document_adapter._WorkingSourceSaveGuardManager()
        first = object()
        manager.begin(first)
        with self.assertRaises(ScriptingRuntimeUnavailableError) as busy:
            manager.begin(object())
        self.assertEqual(busy.exception.snapshot.state, "active")

        manager.begin_recovery(first)
        manager.finish(first)
        self.assertEqual(manager.snapshot().state, "healthy")

    def test_unexpected_native_repair_fault_becomes_restart_evidence(self):
        manager = document_adapter._WorkingSourceSaveGuardManager()
        manager._machine.begin_recovery(trigger="test")
        incident = manager._machine.mark_incident(
            target_state="degraded",
            phase="test",
            reason_code="transient",
            message="transient verification failure",
            trigger="test",
        )

        with mock.patch.object(
            manager, "_repair_once", side_effect=RuntimeError("native fault")
        ):
            report = manager.repair(
                trigger="agent", expected_incident_id=incident.incident_id
            )

        self.assertEqual(report.result, "incomplete")
        self.assertEqual(manager.snapshot().state, "recovery_required")
        self.assertEqual(manager.snapshot().next_action, "restart_glyphs")
        self.assertFalse(
            manager.snapshot().current_incident.affected_slots[0].repairable
        )

    def test_inactive_dispatch_forwards_the_captured_original(self):
        manager = document_adapter._WorkingSourceSaveGuardManager()
        guard = object()
        slot = (1, 2, 3, b"save:", b"v@:@", False)
        calls = []

        def original(receiver, value):
            calls.append((receiver, value))
            return "forwarded"

        manager.register_controller(
            slot,
            original_imp=original,
            method_name="save_",
            reflection=False,
            guard=guard,
        )
        manager.deactivate_controller(slot, guard)

        receiver = object()
        self.assertEqual(manager.dispatch(slot, receiver, 7), "forwarded")
        self.assertEqual(calls, [(receiver, 7)])

    def test_residual_python_wrapper_forwards_then_agent_repair_restores(self):
        class RefuseFirstRestore(type):
            writes = 0

            def __setattr__(owner, name, value):
                if name == "saveDocument_":
                    writes = type.__getattribute__(owner, "writes")
                    type.__setattr__(owner, "writes", writes + 1)
                    if writes >= 1:
                        raise RuntimeError("restoration refused")
                type.__setattr__(owner, name, value)

        class SaveDocument(metaclass=RefuseFirstRestore):
            def saveDocument_(self, sender):
                return sender

        manager = document_adapter._WorkingSourceSaveGuardManager()
        document = SaveDocument()
        original = vars(SaveDocument)["saveDocument_"]
        with mock.patch.object(
            document_adapter, "_LIVE_SOURCE_SAVE_GUARD_MANAGER", manager
        ):
            guard = document_adapter._WorkingSourceSaveRuntimeGuard(
                [document], native_identity=lambda value: ("python", id(value))
            )
            with self.assertRaises(ScriptingRuntimeUnavailableError):
                with guard:
                    pass

            incident = manager.snapshot().current_incident
            self.assertEqual(manager.snapshot().state, "recovery_required")
            self.assertIsNotNone(incident)
            self.assertIsNot(vars(SaveDocument)["saveDocument_"], original)
            self.assertEqual(document.saveDocument_("safe forwarding"), "safe forwarding")

            with self.assertRaises(StaleScriptingRuntimeIncidentError):
                manager.repair(
                    trigger="agent", expected_incident_id="incident_stale"
                )

            type.__setattr__(SaveDocument, "writes", 0)
            report = manager.repair(
                trigger="agent", expected_incident_id=incident.incident_id
            )
            self.assertEqual(report.result, "repaired")
            self.assertEqual(manager.snapshot().state, "healthy")
            self.assertIs(vars(SaveDocument)["saveDocument_"], original)
            self.assertEqual(len(manager._machine.repair_attempts()), 1)

    def test_external_descriptor_owner_is_never_overwritten_and_is_rebaselined(self):
        class SaveDocument:
            def saveDocument_(self, sender):
                return "original:{}".format(sender)

        def external(self, sender):
            return "external:{}".format(sender)

        manager = document_adapter._WorkingSourceSaveGuardManager()
        document = SaveDocument()
        with mock.patch.object(
            document_adapter, "_LIVE_SOURCE_SAVE_GUARD_MANAGER", manager
        ):
            with self.assertRaises(ScriptingRuntimeUnavailableError):
                with document_adapter._WorkingSourceSaveRuntimeGuard(
                    [document],
                    native_identity=lambda value: ("python", id(value)),
                ):
                    type.__setattr__(SaveDocument, "saveDocument_", external)

            self.assertIs(vars(SaveDocument)["saveDocument_"], external)
            self.assertEqual(document.saveDocument_("x"), "external:x")
            status = manager.snapshot()
            self.assertEqual(status.state, "degraded")
            self.assertEqual(
                status.current_incident.affected_slots[0].state,
                "external_owner",
            )
            manager.repair(
                trigger="agent",
                expected_incident_id=status.current_incident.incident_id,
            )
            self.assertEqual(manager.snapshot().state, "healthy")

            with document_adapter._WorkingSourceSaveRuntimeGuard(
                [document], native_identity=lambda value: ("python", id(value))
            ):
                pass
            self.assertIs(vars(SaveDocument)["saveDocument_"], external)

    def test_external_profiler_is_preserved_then_adopted_by_repair(self):
        class PlainDocument:
            pass

        manager = document_adapter._WorkingSourceSaveGuardManager()
        document = PlainDocument()
        prior = sys.getprofile()

        def external_profile(_frame, _event, _argument):
            return None

        try:
            with mock.patch.object(
                document_adapter, "_LIVE_SOURCE_SAVE_GUARD_MANAGER", manager
            ):
                with self.assertRaises(ScriptingRuntimeUnavailableError):
                    with document_adapter._WorkingSourceSaveRuntimeGuard(
                        [document],
                        native_identity=lambda value: ("python", id(value)),
                    ):
                        sys.setprofile(external_profile)

                status = manager.snapshot()
                self.assertEqual(status.state, "degraded")
                self.assertIs(sys.getprofile(), external_profile)
                self.assertEqual(
                    status.current_incident.affected_slots[0].state,
                    "external_owner",
                )

                report = manager.repair(
                    trigger="agent",
                    expected_incident_id=status.current_incident.incident_id,
                )
                self.assertEqual(report.after_state, "healthy")
                self.assertIs(sys.getprofile(), external_profile)

                with document_adapter._WorkingSourceSaveRuntimeGuard(
                    [document],
                    native_identity=lambda value: ("python", id(value)),
                ):
                    pass
                self.assertIs(sys.getprofile(), external_profile)
        finally:
            sys.setprofile(prior)

    def test_false_negative_restore_accepts_exact_final_baseline(self):
        runtime = document_adapter._ObjectiveCRuntime.__new__(
            document_adapter._ObjectiveCRuntime
        )
        state = mock.Mock(implementation_pointer=17)
        observed = object()
        runtime.swap_and_verify = mock.Mock(return_value=(False, None))
        runtime.capture = mock.Mock(return_value=observed)
        runtime._matches = mock.Mock(return_value=True)

        restored = runtime.restore_and_verify(
            state, expected_current_implementation_pointer=99
        )

        self.assertTrue(restored)
        runtime._matches.assert_called_with(observed, state, 17)

    def test_objective_c_third_party_owner_is_adopted_without_a_write(self):
        class Owner:
            pass

        manager = document_adapter._WorkingSourceSaveGuardManager()
        state = document_adapter._ObjectiveCMethodState(
            owner=Owner,
            python_name="saveDocument_",
            selector_name=b"saveDocument:",
            class_method=False,
            class_pointer=101,
            method_pointer=202,
            implementation_pointer=303,
            type_encoding=b"v@:@",
        )
        slot = (101, 202, 303, b"saveDocument:", b"v@:@", False)
        patch = document_adapter._ObjectiveCMethodPatch(
            original_state=state,
            installed_implementation_pointer=404,
            slot=slot,
            original_imp=lambda *_args: None,
            trampoline=object(),
            state="external_owner",
            repairable=True,
        )
        observed = document_adapter._ObjectiveCMethodState(
            owner=Owner,
            python_name="saveDocument_",
            selector_name=b"saveDocument:",
            class_method=False,
            class_pointer=101,
            method_pointer=202,
            implementation_pointer=505,
            type_encoding=b"v@:@",
        )
        runtime = mock.Mock()
        runtime.capture.return_value = observed
        runtime._matches.side_effect = (
            lambda candidate, baseline, implementation: bool(
                candidate is not None
                and candidate.class_pointer == baseline.class_pointer
                and candidate.method_pointer == baseline.method_pointer
                and candidate.implementation_pointer == implementation
            )
        )
        manager._objective_c_residuals[slot] = patch
        manager._machine.begin_recovery(trigger="test")
        incident = manager._machine.mark_incident(
            target_state="degraded",
            phase="restore",
            reason_code="external_owner",
            message="third-party swizzle owns the selector",
            affected_slots=(manager._objective_c_slot_snapshot(patch),),
            trigger="test",
        )

        with mock.patch.object(
            document_adapter, "_objective_c_runtime", return_value=runtime
        ):
            report = manager.repair(
                trigger="agent", expected_incident_id=incident.incident_id
            )

        self.assertEqual(report.after_state, "healthy")
        runtime.restore_and_verify.assert_not_called()
        self.assertEqual(manager._objective_c_residuals, {})


if __name__ == "__main__":
    unittest.main()
