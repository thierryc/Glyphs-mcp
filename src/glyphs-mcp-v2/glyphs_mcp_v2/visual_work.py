"""Process-local arbitration for optional visual convenience work.

MCP operations and cooperative bundled scripts acquire short-lived leases.
Native presentation adapters subscribe to the immutable aggregate snapshot and
decide how to suspend their own work.  This module deliberately imports no
Glyphs or AppKit APIs.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock
from typing import Callable, Iterator
from uuid import uuid4


@dataclass(frozen=True)
class VisualWorkLease:
    """Opaque ownership token for one visual-work suspension reason."""

    lease_id: str
    reason: str
    gate_identity: int


@dataclass(frozen=True)
class VisualWorkSnapshot:
    """Immutable aggregate state safe to publish across runtime threads."""

    sequence: int
    active_lease_count: int
    reasons: tuple[str, ...]
    suspended: bool


class VisualWorkGate:
    """Reference-counted, observer-safe suspension state."""

    def __init__(
        self,
        *,
        id_factory: Callable[[], str] = lambda: "visual_{}".format(uuid4().hex),
    ) -> None:
        self._id_factory = id_factory
        self._leases: dict[str, str] = {}
        self._subscribers: dict[int, Callable[[VisualWorkSnapshot], None]] = {}
        self._next_subscriber = 1
        self._lock = RLock()
        self._snapshot = VisualWorkSnapshot(
            sequence=0,
            active_lease_count=0,
            reasons=(),
            suspended=False,
        )

    @staticmethod
    def _normalize_reason(reason: str) -> str:
        normalized = "_".join(str(reason or "").strip().lower().split())
        if not normalized:
            raise ValueError("visual-work suspension reason is required")
        return normalized

    def _next_snapshot_locked(self) -> VisualWorkSnapshot:
        reasons = tuple(sorted(set(self._leases.values())))
        self._snapshot = VisualWorkSnapshot(
            sequence=self._snapshot.sequence + 1,
            active_lease_count=len(self._leases),
            reasons=reasons,
            suspended=bool(self._leases),
        )
        return self._snapshot

    @staticmethod
    def _notify(
        callbacks: tuple[Callable[[VisualWorkSnapshot], None], ...],
        snapshot: VisualWorkSnapshot,
    ) -> None:
        for callback in callbacks:
            try:
                callback(snapshot)
            except Exception:
                pass

    def current(self) -> VisualWorkSnapshot:
        with self._lock:
            return self._snapshot

    def subscribe(
        self, callback: Callable[[VisualWorkSnapshot], None]
    ) -> Callable[[], None]:
        if not callable(callback):
            raise TypeError("visual-work callback must be callable")
        with self._lock:
            key = self._next_subscriber
            self._next_subscriber += 1
            self._subscribers[key] = callback

        def unsubscribe() -> None:
            with self._lock:
                self._subscribers.pop(key, None)

        return unsubscribe

    def acquire(self, reason: str) -> VisualWorkLease:
        normalized = self._normalize_reason(reason)
        lease_id = str(self._id_factory() or "visual_{}".format(uuid4().hex))
        with self._lock:
            while lease_id in self._leases:
                lease_id = "visual_{}".format(uuid4().hex)
            self._leases[lease_id] = normalized
            lease = VisualWorkLease(
                lease_id=lease_id,
                reason=normalized,
                gate_identity=id(self),
            )
            snapshot = self._next_snapshot_locked()
            callbacks = tuple(self._subscribers.values())
        self._notify(callbacks, snapshot)
        return lease

    def release(self, lease: VisualWorkLease) -> VisualWorkSnapshot:
        if not isinstance(lease, VisualWorkLease):
            raise TypeError("visual-work lease is required")
        with self._lock:
            if lease.gate_identity != id(self) or lease.lease_id not in self._leases:
                return self._snapshot
            self._leases.pop(lease.lease_id, None)
            snapshot = self._next_snapshot_locked()
            callbacks = tuple(self._subscribers.values())
        self._notify(callbacks, snapshot)
        return snapshot

    @contextmanager
    def hold(self, reason: str) -> Iterator[VisualWorkLease]:
        """Suspend optional visual work for one exception-safe scope."""

        lease = self.acquire(reason)
        try:
            yield lease
        finally:
            self.release(lease)


_DEFAULT_VISUAL_WORK_GATE = VisualWorkGate()


def default_visual_work_gate() -> VisualWorkGate:
    return _DEFAULT_VISUAL_WORK_GATE


__all__ = [
    "VisualWorkGate",
    "VisualWorkLease",
    "VisualWorkSnapshot",
    "default_visual_work_gate",
]
