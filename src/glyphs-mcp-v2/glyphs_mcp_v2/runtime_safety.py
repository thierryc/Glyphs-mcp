"""Pure process-local state for the recoverable scripting safety interlock."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Mapping, Sequence
from uuid import uuid4


SAFETY_STATES = (
    "healthy",
    "active",
    "recovering",
    "degraded",
    "recovery_required",
)
SLOT_STATES = (
    "baseline",
    "guard_installed",
    "external_owner",
    "residual_guard",
    "unverifiable",
)
NEXT_ACTIONS = ("none", "retry", "repair", "restart_glyphs")

_ALLOWED_TRANSITIONS = {
    "healthy": frozenset({"healthy", "active", "recovering", "degraded"}),
    "active": frozenset({"recovering"}),
    "recovering": frozenset(
        {"healthy", "degraded", "recovery_required", "recovering"}
    ),
    "degraded": frozenset(
        {"degraded", "recovering", "healthy", "recovery_required"}
    ),
    "recovery_required": frozenset(
        {"recovery_required", "recovering", "healthy", "degraded"}
    ),
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SourceSaveForbiddenError(RuntimeError):
    """Raised when live Python reaches a protected working-source save path."""


class ScriptingRuntimeUnavailableError(RuntimeError):
    """Raised when strict live-Python coverage cannot be established."""

    def __init__(self, message: str, snapshot: "ScriptingSafetySnapshot") -> None:
        super().__init__(message)
        self.snapshot = snapshot


class StaleScriptingRuntimeIncidentError(ValueError):
    """Raised when an agent tries to repair a superseded incident."""


@dataclass(frozen=True)
class SafetySlotSnapshot:
    slot_id: str
    owner_class: str
    selector: str
    kind: str
    state: str
    repairable: bool

    def __post_init__(self) -> None:
        if self.state not in SLOT_STATES:
            raise ValueError("unsupported scripting safety slot state: {}".format(self.state))

    def to_dict(self) -> dict[str, Any]:
        return {
            "slotId": self.slot_id,
            "ownerClass": self.owner_class,
            "selector": self.selector,
            "kind": self.kind,
            "state": self.state,
            "repairable": self.repairable,
        }


@dataclass(frozen=True)
class SafetyIncident:
    incident_id: str
    phase: str
    reason_code: str
    message: str
    first_observed_at: str
    last_observed_at: str
    affected_slots: tuple[SafetySlotSnapshot, ...] = ()
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "incidentId": self.incident_id,
            "phase": self.phase,
            "reasonCode": self.reason_code,
            "message": self.message,
            "firstObservedAt": self.first_observed_at,
            "lastObservedAt": self.last_observed_at,
            "affectedSlotCount": len(self.affected_slots),
            "affectedSlots": [slot.to_dict() for slot in self.affected_slots],
            "resolvedAt": self.resolved_at,
        }


@dataclass(frozen=True)
class SafetyTransition:
    timestamp: str
    before: str
    after: str
    trigger: str
    incident_id: str | None
    reason_code: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "before": self.before,
            "after": self.after,
            "trigger": self.trigger,
            "incidentId": self.incident_id,
            "reasonCode": self.reason_code,
        }


@dataclass(frozen=True)
class SafetyRepairReport:
    trigger: str
    attempted_at: str
    result: str
    before_state: str
    after_state: str
    incident_id: str | None
    repaired_slot_count: int
    remaining_slot_count: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger,
            "attemptedAt": self.attempted_at,
            "result": self.result,
            "beforeState": self.before_state,
            "afterState": self.after_state,
            "incidentId": self.incident_id,
            "repairedSlotCount": self.repaired_slot_count,
            "remainingSlotCount": self.remaining_slot_count,
            "message": self.message,
        }


@dataclass(frozen=True)
class ScriptingSafetySnapshot:
    state: str
    active_execution_id: str | None
    current_incident: SafetyIncident | None
    last_repair: SafetyRepairReport | None
    transitions: tuple[SafetyTransition, ...] = field(default_factory=tuple)

    @property
    def live_python_available(self) -> bool:
        return self.state == "healthy"

    @property
    def automatic_repair_available(self) -> bool:
        if self.state not in {"degraded", "recovery_required"}:
            return False
        incident = self.current_incident
        return not (
            incident is not None
            and incident.affected_slots
            and not any(slot.repairable for slot in incident.affected_slots)
        )

    @property
    def next_action(self) -> str:
        if self.state == "healthy":
            return "none"
        if self.state == "active":
            return "retry"
        if self.state in {"degraded", "recovery_required"}:
            incident = self.current_incident
            if incident is not None and incident.affected_slots and not any(
                slot.repairable for slot in incident.affected_slots
            ):
                return "restart_glyphs"
            if self.automatic_repair_available:
                return "repair"
        return "retry"

    def summary_dict(self) -> dict[str, Any]:
        incident = self.current_incident
        return {
            "state": self.state,
            "mode": "strict",
            "strictInterlockAvailable": self.state in {"healthy", "active"},
            "livePythonAvailable": self.live_python_available,
            "stagedPythonAvailable": True,
            "automaticRepairAvailable": self.automatic_repair_available,
            "incidentId": incident.incident_id if incident is not None else None,
            "affectedSlotCount": (
                len(incident.affected_slots) if incident is not None else 0
            ),
            "nextAction": self.next_action,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.summary_dict(),
            "activeExecutionId": self.active_execution_id,
            "currentIncident": (
                self.current_incident.to_dict()
                if self.current_incident is not None
                else None
            ),
            "lastRepair": (
                self.last_repair.to_dict() if self.last_repair is not None else None
            ),
            "recentTransitions": [item.to_dict() for item in self.transitions],
        }


class ScriptingSafetyStateMachine:
    """Thread-safe transition reducer with bounded incident history."""

    def __init__(
        self,
        *,
        max_incidents: int = 64,
        max_transitions: int = 256,
    ) -> None:
        self._lock = RLock()
        self._state = "healthy"
        self._active_execution_id: str | None = None
        self._current_incident: SafetyIncident | None = None
        self._last_repair: SafetyRepairReport | None = None
        self._repair_attempts: deque[SafetyRepairReport] = deque(maxlen=64)
        self._incidents: deque[SafetyIncident] = deque(maxlen=max(1, max_incidents))
        self._transitions: deque[SafetyTransition] = deque(
            maxlen=max(1, max_transitions)
        )

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def snapshot(self) -> ScriptingSafetySnapshot:
        with self._lock:
            return ScriptingSafetySnapshot(
                state=self._state,
                active_execution_id=self._active_execution_id,
                current_incident=self._current_incident,
                last_repair=self._last_repair,
                transitions=tuple(self._transitions)[-32:],
            )

    def incidents(self) -> tuple[SafetyIncident, ...]:
        with self._lock:
            return tuple(self._incidents)

    def transition_history(self) -> tuple[SafetyTransition, ...]:
        with self._lock:
            return tuple(self._transitions)

    def repair_attempts(self) -> tuple[SafetyRepairReport, ...]:
        with self._lock:
            return tuple(self._repair_attempts)

    def _transition(
        self,
        target: str,
        *,
        trigger: str,
        reason_code: str | None = None,
    ) -> None:
        self._validate_transition(target)
        before = self._state
        self._state = target
        self._transitions.append(
            SafetyTransition(
                timestamp=_iso_now(),
                before=before,
                after=target,
                trigger=str(trigger),
                incident_id=(
                    self._current_incident.incident_id
                    if self._current_incident is not None
                    else None
                ),
                reason_code=reason_code,
            )
        )

    def _validate_transition(self, target: str) -> None:
        if target not in SAFETY_STATES:
            raise ValueError("unsupported scripting safety state: {}".format(target))
        before = self._state
        if target not in _ALLOWED_TRANSITIONS[before]:
            raise ValueError(
                "illegal scripting safety transition: {} -> {}".format(
                    before, target
                )
            )

    def begin(self, execution_id: str) -> None:
        with self._lock:
            if self._state == "active":
                raise RuntimeError("scripting runtime is already active")
            if self._state != "healthy":
                raise RuntimeError(
                    "scripting runtime is not healthy: {}".format(self._state)
                )
            self._active_execution_id = str(execution_id)
            self._transition("active", trigger="execution_begin")

    def begin_recovery(self, *, trigger: str) -> None:
        with self._lock:
            if self._state == "active":
                self._active_execution_id = None
            self._transition("recovering", trigger=trigger)

    def mark_healthy(self, *, trigger: str, reason_code: str | None = None) -> None:
        with self._lock:
            self._validate_transition("healthy")
            self._active_execution_id = None
            if self._current_incident is not None:
                now = _iso_now()
                resolved = SafetyIncident(
                    incident_id=self._current_incident.incident_id,
                    phase=self._current_incident.phase,
                    reason_code=self._current_incident.reason_code,
                    message=self._current_incident.message,
                    first_observed_at=self._current_incident.first_observed_at,
                    last_observed_at=now,
                    affected_slots=self._current_incident.affected_slots,
                    resolved_at=now,
                )
                self._incidents.append(resolved)
                self._current_incident = None
            self._transition("healthy", trigger=trigger, reason_code=reason_code)

    def mark_incident(
        self,
        *,
        target_state: str,
        phase: str,
        reason_code: str,
        message: str,
        affected_slots: Sequence[SafetySlotSnapshot] = (),
        trigger: str,
    ) -> SafetyIncident:
        if target_state not in {"degraded", "recovery_required"}:
            raise ValueError("incidents require a degraded safety state")
        with self._lock:
            self._validate_transition(target_state)
            now = _iso_now()
            current = self._current_incident
            incident = SafetyIncident(
                incident_id=(
                    current.incident_id
                    if current is not None
                    else "incident_{}".format(uuid4().hex)
                ),
                phase=(current.phase if current is not None else str(phase)),
                reason_code=(
                    current.reason_code if current is not None else str(reason_code)
                ),
                message=(current.message if current is not None else str(message)),
                first_observed_at=(
                    current.first_observed_at if current is not None else now
                ),
                last_observed_at=now,
                affected_slots=tuple(affected_slots),
            )
            self._current_incident = incident
            self._active_execution_id = None
            self._transition(
                target_state, trigger=trigger, reason_code=str(reason_code)
            )
            return incident

    def record_repair(self, report: SafetyRepairReport) -> None:
        with self._lock:
            self._last_repair = report
            self._repair_attempts.append(report)


def agent_recovery_directive(snapshot: ScriptingSafetySnapshot) -> dict[str, Any] | None:
    incident = snapshot.current_incident
    if incident is None or not snapshot.automatic_repair_available:
        return None
    return {
        "tool": "repair_runtime",
        "arguments": {"expectedIncidentId": incident.incident_id},
        "verifyWith": "get_runtime_status",
        "retryOriginalCall": True,
        "maxRepairAttempts": 1,
    }


__all__ = [
    "NEXT_ACTIONS",
    "SAFETY_STATES",
    "SLOT_STATES",
    "SafetyIncident",
    "SafetyRepairReport",
    "SafetySlotSnapshot",
    "SafetyTransition",
    "SourceSaveForbiddenError",
    "ScriptingSafetySnapshot",
    "ScriptingSafetyStateMachine",
    "ScriptingRuntimeUnavailableError",
    "StaleScriptingRuntimeIncidentError",
    "agent_recovery_directive",
]
