"""Bounded adapter-owned evidence for exact native structural replay.

This module deliberately imports no Glyphs or AppKit symbols. Native objects
are opaque values owned by the adapter; application and operation stores see
only the generated evidence identifier.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from threading import RLock
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Sequence
from uuid import uuid4


@dataclass(frozen=True)
class NativeReplayEvidence:
    evidence_id: str
    document_id: str
    before_fingerprint: str
    after_fingerprint: str
    capabilities: tuple[str, ...]
    templates: Mapping[tuple[str, ...], Any]
    created_at: float
    expires_at: float

    @property
    def template_paths(self) -> tuple[tuple[str, ...], ...]:
        return tuple(self.templates)


class NativeReplayEvidenceStore:
    """Thread-safe native evidence registry with deterministic eviction."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        id_factory: Optional[Callable[[], str]] = None,
        max_records: int = 32,
        max_records_per_document: int = 8,
    ) -> None:
        self._clock = clock
        self._id_factory = id_factory or (
            lambda: "staged_replay_{}".format(uuid4().hex)
        )
        self._max_records = max(1, int(max_records))
        self._max_records_per_document = max(
            1, int(max_records_per_document)
        )
        self._records: dict[str, NativeReplayEvidence] = {}
        self._lock = RLock()

    def _purge_locked(self) -> None:
        now = self._clock()
        for evidence_id, record in tuple(self._records.items()):
            if record.expires_at <= now:
                self._records.pop(evidence_id, None)

    def _evict_oldest_locked(
        self, records: Sequence[NativeReplayEvidence], count: int
    ) -> None:
        for record in sorted(records, key=lambda value: value.created_at)[:count]:
            self._records.pop(record.evidence_id, None)

    def create(
        self,
        *,
        document_id: str,
        before_fingerprint: str,
        after_fingerprint: str,
        capabilities: Sequence[str],
        templates: Mapping[Sequence[str], Any],
        ttl_seconds: float,
    ) -> NativeReplayEvidence:
        if not document_id or not before_fingerprint:
            raise ValueError("native replay evidence requires a document baseline")
        ttl = float(ttl_seconds)
        if ttl <= 0:
            raise ValueError("ttl_seconds must be positive")
        normalized_templates = {
            tuple(str(part) for part in path): value
            for path, value in templates.items()
        }
        with self._lock:
            self._purge_locked()
            evidence_id = str(self._id_factory())
            if not evidence_id or evidence_id in self._records:
                raise RuntimeError("native replay evidence ID is invalid or duplicated")
            created = float(self._clock())
            record = NativeReplayEvidence(
                evidence_id=evidence_id,
                document_id=str(document_id),
                before_fingerprint=str(before_fingerprint),
                after_fingerprint=str(after_fingerprint),
                capabilities=tuple(sorted(set(str(value) for value in capabilities))),
                templates=MappingProxyType(normalized_templates),
                created_at=created,
                expires_at=created + ttl,
            )
            self._records[evidence_id] = record
            per_document = [
                value
                for value in self._records.values()
                if value.document_id == record.document_id
            ]
            overflow = len(per_document) - self._max_records_per_document
            if overflow > 0:
                self._evict_oldest_locked(per_document, overflow)
            overflow = len(self._records) - self._max_records
            if overflow > 0:
                self._evict_oldest_locked(tuple(self._records.values()), overflow)
            return record

    def bind(
        self,
        evidence_id: str,
        *,
        document_id: str,
        before_fingerprint: str,
        after_fingerprint: str,
        capabilities: Sequence[str],
    ) -> Optional[NativeReplayEvidence]:
        """Bind prepared templates to the immutable patch they will replay."""

        with self._lock:
            self._purge_locked()
            record = self._records.get(str(evidence_id))
            if (
                record is None
                or record.document_id != str(document_id)
                or record.before_fingerprint != str(before_fingerprint)
                or record.after_fingerprint
                or not after_fingerprint
            ):
                return None
            bound = replace(
                record,
                after_fingerprint=str(after_fingerprint),
                capabilities=tuple(
                    sorted(set(str(value) for value in capabilities))
                ),
            )
            self._records[bound.evidence_id] = bound
            return bound

    def resolve(
        self, evidence_id: str, *, document_id: str
    ) -> Optional[NativeReplayEvidence]:
        with self._lock:
            self._purge_locked()
            record = self._records.get(str(evidence_id))
            if record is None or record.document_id != str(document_id):
                return None
            return record

    def discard(self, evidence_id: str) -> bool:
        with self._lock:
            return self._records.pop(str(evidence_id), None) is not None

    def clear_document(self, document_id: str) -> None:
        with self._lock:
            for evidence_id, record in tuple(self._records.items()):
                if record.document_id == str(document_id):
                    self._records.pop(evidence_id, None)

    def record_count(self) -> int:
        with self._lock:
            self._purge_locked()
            return len(self._records)


__all__ = ["NativeReplayEvidence", "NativeReplayEvidenceStore"]
