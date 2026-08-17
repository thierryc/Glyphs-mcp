"""One-shot verified document transactions with complete rollback checks."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol

from .semantic import ChangeSet, fingerprint_model


class TransactionAdapter(Protocol):
    def capture_model(self, document_id: str) -> Mapping[str, Any]:
        ...


class TransactionObserver(Protocol):
    def prepare_transaction(self, document_id: str, before: Mapping[str, Any]) -> Any:
        ...

    def commit_transaction(
        self,
        token: Any,
        document_id: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        change_set: ChangeSet,
    ) -> None:
        ...

    def abort_transaction(self, token: Any) -> None:
        ...

    def apply_change_set(self, document_id: str, change_set: ChangeSet) -> None:
        ...

    def restore_model(self, document_id: str, model: Mapping[str, Any]) -> None:
        ...


class StaleDocumentError(RuntimeError):
    pass


class TransactionVerificationError(RuntimeError):
    def __init__(self, message: str, *, rollback_succeeded: bool) -> None:
        super().__init__(message)
        self.rollback_succeeded = rollback_succeeded


@dataclass(frozen=True)
class TransactionResult:
    document_id: str
    before_fingerprint: str
    after_fingerprint: str
    change_count: int
    inverse: ChangeSet


class TransactionKernel:
    def __init__(
        self,
        adapter: TransactionAdapter,
        *,
        observer: Optional[TransactionObserver] = None,
    ) -> None:
        self._adapter = adapter
        self._observer = observer

    def apply(
        self,
        *,
        document_id: str,
        expected_fingerprint: str,
        change_set: ChangeSet,
    ) -> TransactionResult:
        if not document_id:
            raise ValueError("document_id is required")
        before = copy.deepcopy(dict(self._adapter.capture_model(document_id)))
        current_fingerprint = fingerprint_model(before)
        if current_fingerprint != expected_fingerprint:
            raise StaleDocumentError("document fingerprint changed before the transaction")
        if change_set.before_fingerprint != current_fingerprint:
            raise StaleDocumentError("change set was reviewed against another document state")
        expected_after = change_set.apply(before)
        trace_token = None
        if self._observer is not None:
            trace_token = self._observer.prepare_transaction(document_id, before)
        try:
            self._adapter.apply_change_set(document_id, change_set)
            actual_after = copy.deepcopy(dict(self._adapter.capture_model(document_id)))
            actual_fingerprint = fingerprint_model(actual_after)
            if actual_fingerprint != change_set.after_fingerprint or actual_after != expected_after:
                raise RuntimeError("document read-back did not match the reviewed change set")
            if self._observer is not None:
                self._observer.commit_transaction(
                    trace_token,
                    document_id,
                    before,
                    actual_after,
                    change_set,
                )
        except Exception as exc:
            rollback_succeeded = False
            try:
                self._adapter.restore_model(document_id, before)
                restored = self._adapter.capture_model(document_id)
                rollback_succeeded = fingerprint_model(restored) == current_fingerprint
            except Exception:
                rollback_succeeded = False
            if self._observer is not None:
                try:
                    self._observer.abort_transaction(trace_token)
                except Exception:
                    pass
            raise TransactionVerificationError(
                str(exc) or "document transaction verification failed",
                rollback_succeeded=rollback_succeeded,
            ) from exc
        return TransactionResult(
            document_id=document_id,
            before_fingerprint=current_fingerprint,
            after_fingerprint=change_set.after_fingerprint,
            change_count=len(change_set.changes),
            inverse=change_set.inverse(),
        )


__all__ = [
    "StaleDocumentError",
    "TransactionAdapter",
    "TransactionKernel",
    "TransactionObserver",
    "TransactionResult",
    "TransactionVerificationError",
]
