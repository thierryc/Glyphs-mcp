"""Thread-safe expiring process-local review and operation records."""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Dict, Mapping, Optional
from uuid import uuid4


@dataclass(frozen=True)
class OperationRecord:
    operation_id: str
    kind: str
    payload: Mapping[str, Any]
    created_at: float
    expires_at: float


class OperationStore:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        id_factory: Optional[Callable[[str], str]] = None,
        max_records: int = 2048,
    ) -> None:
        self._clock = clock
        self._id_factory = id_factory or (lambda prefix: prefix + uuid4().hex)
        self._max_records = max(1, int(max_records))
        self._records: Dict[str, OperationRecord] = {}
        self._lock = RLock()

    @staticmethod
    def _prefix(kind: str) -> str:
        if "review" in kind:
            return "review_"
        if "checkpoint" in kind:
            return "exec_"
        return "op_"

    def _purge_locked(self) -> None:
        now = self._clock()
        for operation_id in tuple(self._records):
            if self._records[operation_id].expires_at <= now:
                self._records.pop(operation_id, None)
        if len(self._records) > self._max_records:
            ordered = sorted(self._records.values(), key=lambda record: record.created_at)
            for record in ordered[: len(self._records) - self._max_records]:
                self._records.pop(record.operation_id, None)

    def create(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any],
        ttl_seconds: float,
        operation_id: Optional[str] = None,
    ) -> OperationRecord:
        if not kind:
            raise ValueError("kind is required")
        ttl = float(ttl_seconds)
        if ttl <= 0:
            raise ValueError("ttl_seconds must be positive")
        with self._lock:
            self._purge_locked()
            resolved_id = str(operation_id or self._id_factory(self._prefix(kind)))
            if resolved_id in self._records:
                raise RuntimeError("operation ID factory returned a duplicate")
            created = self._clock()
            record = OperationRecord(
                operation_id=resolved_id,
                kind=kind,
                payload=copy.deepcopy(dict(payload)),
                created_at=created,
                expires_at=created + ttl,
            )
            self._records[resolved_id] = record
            self._purge_locked()
            return record

    def get(self, operation_id: str) -> Optional[OperationRecord]:
        with self._lock:
            self._purge_locked()
            record = self._records.get(operation_id)
            if record is None:
                return None
            return OperationRecord(
                operation_id=record.operation_id,
                kind=record.kind,
                payload=copy.deepcopy(dict(record.payload)),
                created_at=record.created_at,
                expires_at=record.expires_at,
            )

    def consume(self, operation_id: str) -> Optional[OperationRecord]:
        with self._lock:
            self._purge_locked()
            record = self._records.pop(operation_id, None)
            if record is None:
                return None
            return OperationRecord(
                operation_id=record.operation_id,
                kind=record.kind,
                payload=copy.deepcopy(dict(record.payload)),
                created_at=record.created_at,
                expires_at=record.expires_at,
            )

    def discard(self, operation_id: str) -> bool:
        with self._lock:
            return self._records.pop(operation_id, None) is not None

    def list_records(self, *, kind: Optional[str] = None) -> tuple[OperationRecord, ...]:
        with self._lock:
            self._purge_locked()
            values = tuple(
                record
                for record in sorted(self._records.values(), key=lambda item: item.created_at)
                if kind is None or record.kind == kind
            )
        return tuple(
            OperationRecord(
                operation_id=record.operation_id,
                kind=record.kind,
                payload=copy.deepcopy(dict(record.payload)),
                created_at=record.created_at,
                expires_at=record.expires_at,
            )
            for record in values
        )


__all__ = ["OperationRecord", "OperationStore"]
