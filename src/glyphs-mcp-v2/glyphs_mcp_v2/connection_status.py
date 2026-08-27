"""Thread-safe server connection state and palette indicator decisions.

The general plug-in publishes its existing lifecycle classification here.  The
v2 inspector consumes the shared snapshot without importing GlyphsApp or
AppKit, and keeps visual policy testable outside Glyphs.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Callable, Optional


CONNECTION_STATES = frozenset(
    ("running", "starting", "waiting", "stopping", "error", "stopped")
)
TRANSITIONAL_CONNECTION_STATES = frozenset(("starting", "waiting", "stopping"))


@dataclass(frozen=True)
class ConnectionStatusSnapshot:
    state: str
    message: str
    sequence: int


@dataclass(frozen=True)
class IndicatorPresentation:
    tone: str
    pulsing: bool
    text_key: Optional[str]


class ConnectionStatusStore:
    """Hold one process-local connection snapshot and notify on real changes."""

    def __init__(self) -> None:
        self._snapshot = ConnectionStatusSnapshot(
            state="stopped",
            message="Stopped",
            sequence=0,
        )
        self._subscribers: dict[
            int, Callable[[ConnectionStatusSnapshot], None]
        ] = {}
        self._next_subscriber = 1
        self._lock = RLock()

    def current(self) -> ConnectionStatusSnapshot:
        with self._lock:
            return self._snapshot

    def subscribe(
        self, callback: Callable[[ConnectionStatusSnapshot], None]
    ) -> Callable[[], None]:
        if not callable(callback):
            raise TypeError("connection status callback must be callable")
        with self._lock:
            key = self._next_subscriber
            self._next_subscriber += 1
            self._subscribers[key] = callback

        def unsubscribe() -> None:
            with self._lock:
                self._subscribers.pop(key, None)

        return unsubscribe

    def publish(self, state: str, message: str = "") -> ConnectionStatusSnapshot:
        normalized_state = str(state or "").strip().lower()
        if normalized_state not in CONNECTION_STATES:
            raise ValueError("unsupported connection state: {}".format(state))
        normalized_message = str(message or "").strip()
        with self._lock:
            current = self._snapshot
            if (
                current.state == normalized_state
                and current.message == normalized_message
            ):
                return current
            snapshot = ConnectionStatusSnapshot(
                state=normalized_state,
                message=normalized_message,
                sequence=current.sequence + 1,
            )
            self._snapshot = snapshot
            callbacks = tuple(self._subscribers.values())
        for callback in callbacks:
            try:
                callback(snapshot)
            except Exception:
                pass
        return snapshot


def indicator_presentation(
    connection_state: str,
    activity_state: str,
    activity_elapsed_seconds: float,
    activity_active: bool,
    *,
    heavy_after_seconds: float = 2.0,
) -> IndicatorPresentation:
    """Resolve the tiny palette dot with connection transitions taking priority."""

    connection = str(connection_state or "stopped").strip().lower()
    if connection in ("starting", "waiting"):
        return IndicatorPresentation("blue", True, "palette.connecting")
    if connection == "stopping":
        return IndicatorPresentation("blue", True, "palette.disconnecting")
    if connection == "error":
        return IndicatorPresentation("red", False, "status.error")
    if connection != "running":
        return IndicatorPresentation("gray", False, "status.stopped")

    if str(activity_state or "").strip().lower() == "error":
        return IndicatorPresentation("red", False, None)
    if bool(activity_active):
        elapsed = max(0.0, float(activity_elapsed_seconds or 0.0))
        threshold = max(0.0, float(heavy_after_seconds))
        tone = "magenta" if elapsed >= threshold else "green"
        return IndicatorPresentation(tone, True, None)
    return IndicatorPresentation("green", False, None)


_DEFAULT_CONNECTION_STATUS_STORE = ConnectionStatusStore()


def default_connection_status_store() -> ConnectionStatusStore:
    return _DEFAULT_CONNECTION_STATUS_STORE


__all__ = [
    "CONNECTION_STATES",
    "TRANSITIONAL_CONNECTION_STATES",
    "ConnectionStatusSnapshot",
    "ConnectionStatusStore",
    "IndicatorPresentation",
    "default_connection_status_store",
    "indicator_presentation",
]
