"""Thread-safe, UI-neutral progress state for one Glyphs MCP process.

The application publishes coarse phases. Native adapters decide whether those
phases belong in a palette, a transient capsule, debug logging, or nowhere.
Observer failures and presentation choices can never affect transaction logic.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, replace
from threading import RLock
import time
from typing import Callable, Optional
from uuid import uuid4


ACTIVE_STATES = frozenset(("running", "cancel_requested"))
TERMINAL_STATES = frozenset(("success", "error", "cancelled"))


class ActivityCancelled(RuntimeError):
    """Raised only at an explicit cooperative cancellation checkpoint."""


@dataclass(frozen=True)
class ActivityToken:
    activity_id: str
    operation_id: str
    document_id: Optional[str]
    session_generation: int
    command_generation: int
    invocation_lease: str


@dataclass(frozen=True)
class ActivitySnapshot:
    activity_id: str
    document_id: Optional[str]
    tool: str
    title: str
    phase: str
    message: str
    state: str
    cancellable: bool
    cancel_requested: bool
    started_at: float
    updated_at: float
    observed_at: float
    completed_at: Optional[float]
    sequence: int
    session_generation: int = 0
    command_generation: int = 0
    summary: Optional[str] = None
    operation_id: str = ""

    @property
    def active(self) -> bool:
        return self.state in ACTIVE_STATES

    @property
    def elapsed_seconds(self) -> float:
        end = self.completed_at if self.completed_at is not None else self.observed_at
        return max(0.0, float(end) - float(self.started_at))


def _idle_snapshot(document_id: Optional[str], now: float) -> ActivitySnapshot:
    return ActivitySnapshot(
        activity_id="",
        document_id=document_id,
        tool="",
        title="Glyphs MCP",
        phase="idle",
        message="Ready",
        state="idle",
        cancellable=False,
        cancel_requested=False,
        started_at=now,
        updated_at=now,
        observed_at=now,
        completed_at=now,
        sequence=0,
        session_generation=0,
        command_generation=0,
        summary=None,
        operation_id="",
    )


class OperationActivityStore:
    """Hold bounded current activity without importing a native UI framework."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        id_factory: Callable[[], str] = lambda: "activity_{}".format(uuid4().hex),
        max_records: int = 256,
    ) -> None:
        self._clock = clock
        self._id_factory = id_factory
        self._max_records = max(8, int(max_records))
        self._records: dict[str, ActivitySnapshot] = {}
        self._active_by_document: dict[Optional[str], list[str]] = {}
        self._foreground_by_document: dict[Optional[str], str] = {}
        self._terminal_by_document: dict[Optional[str], str] = {}
        self._lease_ids: dict[str, str] = {}
        self._lease_released_at: dict[str, Optional[float]] = {}
        self._subscribers: dict[int, Callable[[ActivitySnapshot], None]] = {}
        self._next_subscriber = 1
        self._next_sequence = 1
        self._session_generation = 1
        self._next_command_generation = 1
        self._lock = RLock()
        self._current_token: ContextVar[Optional[ActivityToken]] = ContextVar(
            "glyphs_mcp_v2_activity_token_{}".format(id(self)), default=None
        )

    def _sequence(self) -> int:
        value = self._next_sequence
        self._next_sequence += 1
        return value

    def _notify(self, snapshot: ActivitySnapshot) -> None:
        with self._lock:
            callbacks = tuple(self._subscribers.values())
        for callback in callbacks:
            try:
                callback(snapshot)
            except Exception:
                pass

    def _prune(self) -> None:
        if len(self._records) <= self._max_records:
            return
        protected = {
            activity_id
            for values in self._active_by_document.values()
            for activity_id in values
        } | set(self._terminal_by_document.values()) | set(
            self._foreground_by_document.values()
        )
        removable = sorted(
            (
                snapshot
                for snapshot in self._records.values()
                if snapshot.activity_id not in protected
            ),
            key=lambda item: item.sequence,
        )
        for snapshot in removable:
            if len(self._records) <= self._max_records:
                break
            self._records.pop(snapshot.activity_id, None)
            self._lease_ids.pop(snapshot.activity_id, None)
            self._lease_released_at.pop(snapshot.activity_id, None)

    def subscribe(
        self, callback: Callable[[ActivitySnapshot], None]
    ) -> Callable[[], None]:
        if not callable(callback):
            raise TypeError("activity callback must be callable")
        with self._lock:
            key = self._next_subscriber
            self._next_subscriber += 1
            self._subscribers[key] = callback

        def unsubscribe() -> None:
            with self._lock:
                self._subscribers.pop(key, None)

        return unsubscribe

    def begin(
        self,
        *,
        document_id: Optional[str],
        tool: str,
        title: str,
        cancellable: bool = False,
        operation_id: Optional[str] = None,
    ) -> ActivityToken:
        now = float(self._clock())
        activity_id = str(self._id_factory() or "activity_{}".format(uuid4().hex))
        with self._lock:
            self._reconcile_orphans_locked(now, grace_seconds=30.0)
            while activity_id in self._records:
                activity_id = "activity_{}".format(uuid4().hex)
            command_generation = self._next_command_generation
            self._next_command_generation += 1
            token = ActivityToken(
                activity_id=activity_id,
                operation_id=str(operation_id or ""),
                document_id=document_id,
                session_generation=self._session_generation,
                command_generation=command_generation,
                invocation_lease="lease_{}".format(uuid4().hex),
            )
            snapshot = ActivitySnapshot(
                activity_id=activity_id,
                document_id=document_id,
                tool=str(tool or "unknown"),
                title=str(title or tool or "Glyphs MCP"),
                phase="preparing",
                message="Preparing",
                state="running",
                cancellable=bool(cancellable),
                cancel_requested=False,
                started_at=now,
                updated_at=now,
                observed_at=now,
                completed_at=None,
                sequence=self._sequence(),
                session_generation=token.session_generation,
                command_generation=token.command_generation,
                operation_id=token.operation_id,
            )
            self._records[activity_id] = snapshot
            self._active_by_document.setdefault(document_id, []).append(activity_id)
            self._foreground_by_document[document_id] = activity_id
            self._terminal_by_document.pop(document_id, None)
            self._lease_ids[activity_id] = token.invocation_lease
            self._lease_released_at[activity_id] = None
            self._prune()
        self._current_token.set(token)
        self._notify(snapshot)
        return token

    def advance(
        self,
        token: ActivityToken,
        phase: str,
        message: str,
        *,
        cancellable: Optional[bool] = None,
    ) -> ActivitySnapshot:
        now = float(self._clock())
        with self._lock:
            current = self._records.get(token.activity_id)
            if current is None:
                raise KeyError("activity is unavailable")
            if (
                token.session_generation != self._session_generation
                or self._lease_ids.get(token.activity_id)
                != token.invocation_lease
            ):
                return current
            if not current.active:
                return current
            next_cancellable = (
                current.cancellable if cancellable is None else bool(cancellable)
            )
            if current.cancel_requested:
                next_cancellable = False
            snapshot = replace(
                current,
                phase=str(phase or current.phase),
                message=str(message or current.message),
                cancellable=next_cancellable,
                updated_at=now,
                observed_at=now,
                sequence=self._sequence(),
            )
            self._records[token.activity_id] = snapshot
            self._lease_released_at[token.activity_id] = None
            self._foreground_by_document[token.document_id] = token.activity_id
            self._terminal_by_document.pop(token.document_id, None)
        self._notify(snapshot)
        return snapshot

    def advance_current(
        self,
        phase: str,
        message: str,
        *,
        cancellable: Optional[bool] = None,
    ) -> Optional[ActivitySnapshot]:
        token = self._current_token.get()
        if token is None:
            return None
        return self.advance(token, phase, message, cancellable=cancellable)

    def request_cancel(self, activity_id: str) -> bool:
        now = float(self._clock())
        with self._lock:
            current = self._records.get(str(activity_id or ""))
            if current is None or not current.active or not current.cancellable:
                return False
            snapshot = replace(
                current,
                state="cancel_requested",
                message="Cancel requested",
                cancellable=False,
                cancel_requested=True,
                updated_at=now,
                observed_at=now,
                sequence=self._sequence(),
            )
            self._records[current.activity_id] = snapshot
            self._foreground_by_document[current.document_id] = current.activity_id
            self._terminal_by_document.pop(current.document_id, None)
        self._notify(snapshot)
        return True

    def checkpoint(self, token: ActivityToken) -> None:
        with self._lock:
            current = self._records.get(token.activity_id)
            cancelled = bool(
                current
                and token.session_generation == self._session_generation
                and self._lease_ids.get(token.activity_id)
                == token.invocation_lease
                and current.cancel_requested
            )
        if cancelled:
            raise ActivityCancelled("operation cancelled before live mutation")

    def checkpoint_current(self) -> None:
        token = self._current_token.get()
        if token is not None:
            self.checkpoint(token)

    def checkpoint_callback(self) -> Callable[[], None]:
        """Capture the current token for work that crosses thread contexts."""

        token = self._current_token.get()

        def checkpoint() -> None:
            if token is not None:
                self.checkpoint(token)

        return checkpoint

    def complete(
        self,
        token: ActivityToken,
        *,
        ok: bool,
        summary: str,
        cancelled: bool = False,
    ) -> ActivitySnapshot:
        now = float(self._clock())
        with self._lock:
            current = self._records.get(token.activity_id)
            if current is None:
                raise KeyError("activity is unavailable")
            if (
                token.session_generation != self._session_generation
                or self._lease_ids.get(token.activity_id)
                != token.invocation_lease
            ):
                return current
            if not current.active:
                return current
            state = "cancelled" if cancelled else "success" if ok else "error"
            snapshot = replace(
                current,
                phase=state,
                message=str(summary or state.title()),
                state=state,
                cancellable=False,
                completed_at=now,
                updated_at=now,
                observed_at=now,
                sequence=self._sequence(),
                summary=str(summary or "") or None,
            )
            self._records[token.activity_id] = snapshot
            active = self._active_by_document.get(token.document_id, [])
            self._active_by_document[token.document_id] = [
                value for value in active if value != token.activity_id
            ]
            if self._foreground_by_document.get(token.document_id) == token.activity_id:
                newer = self._newest_active_locked(
                    token.document_id,
                    newer_than=token.command_generation,
                )
                if newer is not None:
                    self._foreground_by_document[token.document_id] = newer.activity_id
                    self._terminal_by_document.pop(token.document_id, None)
                else:
                    self._foreground_by_document.pop(token.document_id, None)
                    self._terminal_by_document[token.document_id] = token.activity_id
            visible = self._current_locked(token.document_id, now)
            self._prune()
        if self._current_token.get() == token:
            self._current_token.set(None)
        self._notify(visible)
        return snapshot

    def release(self, token: ActivityToken) -> None:
        """Release one invocation lease without changing document state."""

        now = float(self._clock())
        with self._lock:
            if (
                token.session_generation == self._session_generation
                and self._lease_ids.get(token.activity_id)
                == token.invocation_lease
                and token.activity_id in self._lease_released_at
                and self._lease_released_at[token.activity_id] is None
            ):
                self._lease_released_at[token.activity_id] = now
        if self._current_token.get() == token:
            self._current_token.set(None)

    def _newest_active_locked(
        self,
        document_id: Optional[str],
        *,
        newer_than: int = -1,
    ) -> Optional[ActivitySnapshot]:
        candidates = (
            self._records.get(activity_id)
            for activity_id in self._active_by_document.get(document_id, ())
        )
        return max(
            (
                snapshot
                for snapshot in candidates
                if snapshot is not None
                and snapshot.active
                and snapshot.command_generation > newer_than
            ),
            key=lambda snapshot: snapshot.command_generation,
            default=None,
        )

    def _reconcile_orphans_locked(
        self, now: float, *, grace_seconds: float
    ) -> bool:
        changed = False
        grace = max(0.0, float(grace_seconds))
        for activity_id, released_at in tuple(self._lease_released_at.items()):
            if released_at is None or now - released_at < grace:
                continue
            snapshot = self._records.get(activity_id)
            if snapshot is None or not snapshot.active:
                continue
            diagnostic = replace(
                snapshot,
                phase="orphaned",
                message="Invocation ended without a terminal activity update",
                state="cancelled",
                cancellable=False,
                completed_at=released_at,
                updated_at=now,
                observed_at=now,
                sequence=self._sequence(),
                summary="Orphaned activity cleared",
            )
            self._records[activity_id] = diagnostic
            active = self._active_by_document.get(snapshot.document_id, [])
            self._active_by_document[snapshot.document_id] = [
                value for value in active if value != activity_id
            ]
            if self._foreground_by_document.get(snapshot.document_id) == activity_id:
                self._foreground_by_document.pop(snapshot.document_id, None)
                self._terminal_by_document.pop(snapshot.document_id, None)
            changed = True
        return changed

    def reconcile_orphans(
        self, *, grace_seconds: float = 30.0
    ) -> ActivitySnapshot:
        now = float(self._clock())
        with self._lock:
            changed = self._reconcile_orphans_locked(
                now, grace_seconds=grace_seconds
            )
            snapshot = self._current_locked(None, now)
            self._prune()
        if changed:
            self._notify(snapshot)
        return snapshot

    def reset_session(self) -> ActivitySnapshot:
        """Start a fresh server activity generation without replacing observers."""

        now = float(self._clock())
        with self._lock:
            self._session_generation += 1
            for activity_id, snapshot in tuple(self._records.items()):
                if snapshot.active:
                    self._records[activity_id] = replace(
                        snapshot,
                        phase="session_ended",
                        message="Server session ended",
                        state="cancelled",
                        cancellable=False,
                        completed_at=now,
                        updated_at=now,
                        observed_at=now,
                        sequence=self._sequence(),
                        summary="Server session ended",
                    )
            self._active_by_document.clear()
            self._foreground_by_document.clear()
            self._terminal_by_document.clear()
            self._lease_ids.clear()
            self._lease_released_at.clear()
            snapshot = _idle_snapshot(None, now)
            self._prune()
        self._current_token.set(None)
        self._notify(snapshot)
        return snapshot

    def _current_locked(
        self, document_id: Optional[str], now: float
    ) -> ActivitySnapshot:
        candidates: list[ActivitySnapshot] = []
        scopes = (document_id, None) if document_id is not None else (None,)
        for scope in scopes:
            foreground_id = self._foreground_by_document.get(scope)
            foreground = self._records.get(foreground_id or "")
            if foreground is not None and foreground.active:
                candidates.append(foreground)
            terminal_id = self._terminal_by_document.get(scope)
            terminal = self._records.get(terminal_id or "")
            if terminal is not None:
                candidates.append(terminal)
        if candidates:
            return replace(
                max(candidates, key=lambda item: item.command_generation),
                observed_at=now,
            )
        return _idle_snapshot(document_id, now)

    def current(self, document_id: Optional[str]) -> ActivitySnapshot:
        now = float(self._clock())
        with self._lock:
            return self._current_locked(document_id, now)

    @staticmethod
    def _public_summary(snapshot: ActivitySnapshot, now: float) -> dict:
        observed = replace(snapshot, observed_at=now)
        return {
            "activityId": observed.activity_id,
            "operationId": observed.operation_id or None,
            "documentId": observed.document_id,
            "tool": observed.tool,
            "phase": observed.phase,
            "state": observed.state,
            "cancellable": observed.cancellable,
            "cancelRequested": observed.cancel_requested,
            "elapsedMs": round(observed.elapsed_seconds * 1000, 3),
            "summary": observed.summary,
        }

    def operation_summaries(
        self,
        *,
        active_limit: int = 16,
        recent_limit: int = 16,
        exclude_operation_id: Optional[str] = None,
    ) -> dict:
        """Return bounded process state using only the activity-store lock."""

        now = float(self._clock())
        active_bound = max(0, min(int(active_limit), 64))
        recent_bound = max(0, min(int(recent_limit), 64))
        excluded = str(exclude_operation_id or "")
        with self._lock:
            active = sorted(
                (
                    value
                    for value in self._records.values()
                    if value.active and value.operation_id != excluded
                ),
                key=lambda value: value.sequence,
                reverse=True,
            )
            recent = sorted(
                (
                    value
                    for value in self._records.values()
                    if not value.active
                    and value.state in TERMINAL_STATES
                    and value.operation_id != excluded
                ),
                key=lambda value: value.sequence,
                reverse=True,
            )
        return {
            "activeCount": len(active),
            "active": [
                self._public_summary(value, now)
                for value in active[:active_bound]
            ],
            "activeTruncated": len(active) > active_bound,
            "recentCount": len(recent),
            "recent": [
                self._public_summary(value, now)
                for value in recent[:recent_bound]
            ],
            "recentTruncated": len(recent) > recent_bound,
        }

    def dismiss(self, document_id: Optional[str]) -> ActivitySnapshot:
        now = float(self._clock())
        with self._lock:
            self._terminal_by_document.pop(document_id, None)
            foreground_id = self._foreground_by_document.get(document_id)
            foreground = self._records.get(foreground_id or "")
            if foreground is None or not foreground.active:
                self._foreground_by_document.pop(document_id, None)
            snapshot = self._current_locked(document_id, now)
        self._notify(snapshot)
        return snapshot


_DEFAULT_ACTIVITY_STORE = OperationActivityStore()


def default_activity_store() -> OperationActivityStore:
    return _DEFAULT_ACTIVITY_STORE


__all__ = [
    "ACTIVE_STATES",
    "TERMINAL_STATES",
    "ActivityCancelled",
    "ActivitySnapshot",
    "ActivityToken",
    "OperationActivityStore",
    "default_activity_store",
]
