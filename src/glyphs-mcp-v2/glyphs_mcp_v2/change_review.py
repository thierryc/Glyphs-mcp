"""Pure process-local state for apply-first change review.

This module deliberately has no GlyphsApp or AppKit imports. Application
services publish verified operations here; the native panel and Reporter only
read/select them.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, replace
from threading import RLock
from typing import Any, Callable, Mapping, Optional, Sequence
from uuid import uuid4

from .semantic import fingerprint_model


CHANGE_OPERATION_STATUSES = frozenset(
    {
        "applied",
        "partially_rolled_back",
        "rolled_back",
        "stale",
        "expired",
        "recovery_only",
    }
)


def _plain_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(value))


@dataclass(frozen=True)
class ChangeOperation:
    operation_id: str
    document_id: str
    tool: str
    reason: Optional[str]
    status: str
    before_fingerprint: str
    after_fingerprint: str
    items: tuple[Mapping[str, Any], ...]
    audit_receipt: Optional[Mapping[str, Any]] = None
    created_at: float = 0.0
    expires_at: float = 0.0
    rollback_token: Optional[str] = None
    rollback_coverage: str = "complete"

    def __post_init__(self) -> None:
        if not self.operation_id:
            raise ValueError("operationId is required")
        if not self.document_id:
            raise ValueError("documentId is required")
        if not self.tool:
            raise ValueError("tool is required")
        if self.status not in CHANGE_OPERATION_STATUSES:
            raise ValueError("unsupported change operation status: {}".format(self.status))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ChangeOperation":
        return cls(
            operation_id=str(value.get("operationId") or ""),
            document_id=str(value.get("documentId") or ""),
            tool=str(value.get("tool") or ""),
            reason=str(value["reason"]) if value.get("reason") is not None else None,
            status=str(value.get("status") or "applied"),
            before_fingerprint=str(value.get("beforeFingerprint") or ""),
            after_fingerprint=str(value.get("afterFingerprint") or ""),
            items=tuple(_plain_mapping(item) for item in value.get("items") or ()),
            audit_receipt=_plain_mapping(value["auditReceipt"])
            if isinstance(value.get("auditReceipt"), Mapping)
            else None,
            created_at=float(value.get("createdAt") or 0.0),
            expires_at=float(value.get("expiresAt") or 0.0),
            rollback_token=str(value["rollbackToken"])
            if value.get("rollbackToken") is not None
            else None,
            rollback_coverage=str(value.get("rollbackCoverage") or "complete"),
        )

    def to_mapping(self, *, include_items: bool = True) -> dict[str, Any]:
        value: dict[str, Any] = {
            "operationId": self.operation_id,
            "documentId": self.document_id,
            "tool": self.tool,
            "reason": self.reason,
            "status": self.status,
            "beforeFingerprint": self.before_fingerprint,
            "afterFingerprint": self.after_fingerprint,
            "changeCount": len(self.items),
            "affectedGlyphCount": len(self.glyph_targets()),
            "visualizableGlyphCount": len(
                {str(item.get("glyphName")) for item in self.items if item.get("displayBefore") and item.get("displayApplied")}
            ),
            "rollbackCoverage": self.rollback_coverage,
            "rollbackToken": self.rollback_token,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "auditReceipt": _plain_mapping(self.audit_receipt) if self.audit_receipt else None,
        }
        if include_items:
            value["items"] = [_plain_mapping(item) for item in self.items]
        return value

    def glyph_targets(self) -> tuple[dict[str, Any], ...]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in self.items:
            name = str(item.get("glyphName") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            result.append(
                {
                    "glyphName": name,
                    "masterId": item.get("masterId"),
                    "layerId": item.get("layerId"),
                }
            )
        return tuple(result)

    @property
    def reviewable(self) -> bool:
        if self.status not in {"applied", "stale", "partially_rolled_back"}:
            return False
        return not self.expires_at or self.expires_at > time.time()

    def with_status(self, status: str) -> "ChangeOperation":
        if status not in CHANGE_OPERATION_STATUSES:
            raise ValueError("unsupported change operation status: {}".format(status))
        return replace(self, status=status)


class ChangeReviewStore:
    def __init__(
        self,
        *,
        id_factory: Optional[Callable[[], str]] = None,
        max_operations_per_document: int = 256,
    ) -> None:
        self._id_factory = id_factory or (lambda: "op_{}".format(uuid4().hex))
        self._max_operations = max(1, int(max_operations_per_document))
        self._by_id: dict[str, ChangeOperation] = {}
        self._by_document: dict[str, list[str]] = {}
        self._selected: dict[str, str] = {}
        self._listeners: list[Callable[[], Any]] = []
        self._lock = RLock()

    def reset(self) -> None:
        with self._lock:
            self._by_id.clear()
            self._by_document.clear()
            self._selected.clear()
            self._listeners.clear()

    def add_listener(self, callback: Callable[[], Any]) -> None:
        if not callable(callback):
            return
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def _notify(self) -> None:
        with self._lock:
            listeners = tuple(self._listeners)
        for callback in listeners:
            try:
                callback()
            except Exception:
                continue

    def _expire_locked(self) -> None:
        now = time.time()
        for operation_id, operation in tuple(self._by_id.items()):
            if (
                operation.expires_at
                and operation.expires_at <= now
                and operation.status in {"applied", "stale", "partially_rolled_back"}
            ):
                self._by_id[operation_id] = operation.with_status("expired")

    def register(self, operation: ChangeOperation | Mapping[str, Any]) -> ChangeOperation:
        value = operation if isinstance(operation, ChangeOperation) else ChangeOperation.from_mapping(operation)
        if not value.operation_id:
            value = replace(value, operation_id=str(self._id_factory()))
        with self._lock:
            self._expire_locked()
            previous = self._by_id.get(value.operation_id)
            if previous is not None and previous.document_id != value.document_id:
                raise ValueError("operationId belongs to another document")
            document_ids = self._by_document.setdefault(value.document_id, [])
            if value.operation_id not in document_ids:
                document_ids.append(value.operation_id)
            self._by_id[value.operation_id] = value
            while len(document_ids) > self._max_operations:
                evicted = document_ids.pop(0)
                self._by_id.pop(evicted, None)
                if self._selected.get(value.document_id) == evicted:
                    self._selected.pop(value.document_id, None)
        self._notify()
        return value

    def get(self, operation_id: str) -> Optional[ChangeOperation]:
        with self._lock:
            self._expire_locked()
            return self._by_id.get(str(operation_id))

    def list_operations(self, document_id: str) -> tuple[ChangeOperation, ...]:
        with self._lock:
            self._expire_locked()
            return tuple(
                self._by_id[operation_id]
                for operation_id in self._by_document.get(str(document_id), ())
                if operation_id in self._by_id
            )

    def select(self, document_id: str, operation_id: Optional[str]) -> Optional[ChangeOperation]:
        document = str(document_id)
        with self._lock:
            self._expire_locked()
            if operation_id is None:
                self._selected.pop(document, None)
                value = None
            else:
                value = self._by_id.get(str(operation_id))
                if value is None or value.document_id != document:
                    raise KeyError("change operation is unavailable for this document")
                self._selected[document] = value.operation_id
        self._notify()
        return value

    def selected(self, document_id: str) -> Optional[ChangeOperation]:
        with self._lock:
            self._expire_locked()
            operation_id = self._selected.get(str(document_id))
            return self._by_id.get(operation_id) if operation_id else None

    def selected_ids(self) -> dict[str, str]:
        with self._lock:
            return dict(self._selected)

    def update_status(self, operation_id: str, status: str) -> Optional[ChangeOperation]:
        with self._lock:
            current = self._by_id.get(str(operation_id))
            if current is None:
                return None
            updated = current.with_status(status)
            self._by_id[updated.operation_id] = updated
        self._notify()
        return updated

    def clear_document(self, document_id: str) -> None:
        document = str(document_id)
        with self._lock:
            for operation_id in self._by_document.pop(document, ()):
                self._by_id.pop(operation_id, None)
            self._selected.pop(document, None)
        self._notify()


CHANGE_REVIEW_STORE = ChangeReviewStore()


def resolve_outline_overlay(
    operation: ChangeOperation,
    *,
    glyph_name: str,
    layer_id: str,
    master_id: str,
    live_paths: Sequence[Mapping[str, Any]],
) -> Optional[dict[str, Any]]:
    """Return detached overlay state for one Edit View layer, or ``None``."""
    if not operation.reviewable:
        return None
    item = next(
        (
            value
            for value in operation.items
            if str(value.get("glyphName") or "") == str(glyph_name)
            and str(value.get("layerId") or "") in {str(layer_id), ""}
            and str(value.get("masterId") or "") in {str(master_id), ""}
            and value.get("displayBefore") is not None
            and value.get("displayApplied") is not None
        ),
        None,
    )
    if item is None:
        return None
    before = copy.deepcopy(list(item.get("displayBefore") or []))
    applied = copy.deepcopy(list(item.get("displayApplied") or []))
    if [len(path.get("nodes") or []) for path in before] != [
        len(path.get("nodes") or []) for path in applied
    ]:
        return None
    expected = str(item.get("displayAppliedFingerprint") or fingerprint_model(applied))
    return {
        "operationId": operation.operation_id,
        "glyphName": str(glyph_name),
        "layerId": str(layer_id),
        "beforePaths": before,
        "appliedPaths": applied,
        "stale": fingerprint_model(list(live_paths)) != expected,
    }


__all__ = [
    "CHANGE_OPERATION_STATUSES",
    "CHANGE_REVIEW_STORE",
    "ChangeOperation",
    "ChangeReviewStore",
    "resolve_outline_overlay",
]
