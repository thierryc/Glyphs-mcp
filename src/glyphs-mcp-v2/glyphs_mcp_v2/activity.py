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
    document_id: Optional[str]


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
    summary: Optional[str] = None

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
        summary=None,
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
        self._terminal_by_document: dict[Optional[str], str] = {}
        self._subscribers: dict[int, Callable[[ActivitySnapshot], None]] = {}
        self._next_subscriber = 1
        self._next_sequence = 1
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
        } | set(self._terminal_by_document.values())
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
    ) -> ActivityToken:
        now = float(self._clock())
        activity_id = str(self._id_factory() or "activity_{}".format(uuid4().hex))
        token = ActivityToken(activity_id=activity_id, document_id=document_id)
        with self._lock:
            while activity_id in self._records:
                activity_id = "activity_{}".format(uuid4().hex)
                token = ActivityToken(activity_id=activity_id, document_id=document_id)
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
            )
            self._records[activity_id] = snapshot
            self._active_by_document.setdefault(document_id, []).append(activity_id)
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
        self._notify(snapshot)
        return True

    def checkpoint(self, token: ActivityToken) -> None:
        with self._lock:
            current = self._records.get(token.activity_id)
            cancelled = bool(current and current.cancel_requested)
        if cancelled:
            raise ActivityCancelled("operation cancelled before live mutation")

    def checkpoint_current(self) -> None:
        token = self._current_token.get()
        if token is not None:
            self.checkpoint(token)

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
            self._terminal_by_document[token.document_id] = token.activity_id
            visible = self._current_locked(token.document_id, now)
            self._prune()
        if self._current_token.get() == token:
            self._current_token.set(None)
        self._notify(visible)
        return snapshot

    def _current_locked(
        self, document_id: Optional[str], now: float
    ) -> ActivitySnapshot:
        for scope in (document_id, None) if document_id is not None else (None,):
            active = self._active_by_document.get(scope, [])
            for activity_id in reversed(active):
                snapshot = self._records.get(activity_id)
                if snapshot is not None and snapshot.active:
                    return replace(snapshot, observed_at=now)
            terminal_id = self._terminal_by_document.get(scope)
            terminal = self._records.get(terminal_id or "")
            if terminal is not None:
                return replace(terminal, observed_at=now)
        return _idle_snapshot(document_id, now)

    def current(self, document_id: Optional[str]) -> ActivitySnapshot:
        now = float(self._clock())
        with self._lock:
            return self._current_locked(document_id, now)

    def dismiss(self, document_id: Optional[str]) -> ActivitySnapshot:
        now = float(self._clock())
        with self._lock:
            self._terminal_by_document.pop(document_id, None)
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
