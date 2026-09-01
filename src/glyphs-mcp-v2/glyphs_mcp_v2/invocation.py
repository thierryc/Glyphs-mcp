"""One bounded lifecycle context for a public Glyphs MCP invocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event, RLock
from typing import Any, Mapping, Optional

from .activity import ActivityCancelled, ActivityToken, OperationActivityStore
from .contracts import OperationMetadata


@dataclass
class InvocationContext:
    """Own identity, cooperative cancellation, timing, and terminal state."""

    tool: str
    document_id: Optional[str]
    metadata: OperationMetadata = field(default_factory=OperationMetadata.create)
    _cancelled: Event = field(default_factory=Event, init=False, repr=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _activity_store: Optional[OperationActivityStore] = field(
        default=None, init=False, repr=False
    )
    _activity_token: Optional[ActivityToken] = field(
        default=None, init=False, repr=False
    )
    _terminal_classification: Optional[str] = field(
        default=None, init=False
    )
    _terminal_stage: str = field(default="preparing", init=False)

    @property
    def operation_id(self) -> str:
        return self.metadata.operation_id

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def attach_activity(
        self, store: OperationActivityStore, token: ActivityToken
    ) -> None:
        with self._lock:
            self._activity_store = store
            self._activity_token = token
            cancelled = self._cancelled.is_set()
        if cancelled:
            store.request_cancel(token.activity_id)

    def request_cancel(self, *, classification: str = "cancelled") -> bool:
        if classification not in {"cancelled", "timeout"}:
            raise ValueError("cancellation classification is unsupported")
        with self._lock:
            store = self._activity_store
            token = self._activity_token
        if store is not None and token is not None:
            if not store.request_cancel(token.activity_id):
                return False
        self._cancelled.set()
        with self._lock:
            if self._terminal_classification is None:
                self._terminal_classification = classification
        return True

    def checkpoint(self) -> None:
        if self._cancelled.is_set():
            raise ActivityCancelled("operation cancelled before live mutation")
        with self._lock:
            store = self._activity_store
            token = self._activity_token
        if store is not None and token is not None:
            store.checkpoint(token)

    def finish(self, classification: str, *, stage: Optional[str] = None) -> None:
        with self._lock:
            if self._terminal_classification not in {"cancelled", "timeout"}:
                self._terminal_classification = str(classification)
            if stage:
                self._terminal_stage = str(stage)

    def evidence(self) -> Mapping[str, Any]:
        with self._lock:
            classification = self._terminal_classification
            stage = self._terminal_stage
        return {
            "operationId": self.operation_id,
            "classification": classification or "running",
            "terminalStage": stage,
            "cancelRequested": self._cancelled.is_set(),
        }


__all__ = ["InvocationContext"]
