"""Bounded process-local v2 audit events with source-code redaction."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, Mapping, Optional
from uuid import uuid4


_REDACTED_KEYS = frozenset({"code", "source", "sourceCode", "python", "snippet"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _redact(item)
            for key, item in value.items()
            if str(key) not in _REDACTED_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return copy.deepcopy(value)


@dataclass(frozen=True)
class AuditReceipt:
    audit_id: str
    timestamp: str

    def to_dict(self) -> dict[str, str]:
        return {"auditId": self.audit_id, "timestamp": self.timestamp}


@dataclass(frozen=True)
class AuditEvent:
    audit_id: str
    timestamp: str
    tool: str
    effect: str
    status: str
    document_id: Optional[str]
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "auditId": self.audit_id,
            "timestamp": self.timestamp,
            "tool": self.tool,
            "effect": self.effect,
            "status": self.status,
            "documentId": self.document_id,
            "details": copy.deepcopy(dict(self.details)),
        }


class AuditLog:
    def __init__(
        self,
        *,
        now: Callable[[], datetime] = _utc_now,
        id_factory: Optional[Callable[[], str]] = None,
        max_events: int = 4096,
    ) -> None:
        self._now = now
        self._id_factory = id_factory or (lambda: "audit_{}".format(uuid4().hex))
        self._max_events = max(1, int(max_events))
        self._events: list[AuditEvent] = []
        self._lock = RLock()

    def record(
        self,
        *,
        tool: str,
        effect: str,
        status: str,
        document_id: Optional[str],
        details: Mapping[str, Any],
    ) -> AuditReceipt:
        timestamp = _iso(self._now())
        audit_id = str(self._id_factory())
        event = AuditEvent(
            audit_id=audit_id,
            timestamp=timestamp,
            tool=tool,
            effect=effect,
            status=status,
            document_id=document_id,
            details=_redact(details),
        )
        with self._lock:
            self._events.append(event)
            if len(self._events) > self._max_events:
                del self._events[: len(self._events) - self._max_events]
        return AuditReceipt(audit_id=audit_id, timestamp=timestamp)

    def list_events(self, *, document_id: Optional[str] = None) -> tuple[AuditEvent, ...]:
        with self._lock:
            values = tuple(self._events)
        if document_id is not None:
            values = tuple(event for event in values if event.document_id == document_id)
        return values


__all__ = ["AuditEvent", "AuditLog", "AuditReceipt"]
