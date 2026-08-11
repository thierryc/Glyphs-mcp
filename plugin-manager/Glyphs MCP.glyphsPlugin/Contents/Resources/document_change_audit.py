# encoding: utf-8

"""Thread-safe, process-local audit state for one open Glyphs document."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import threading
import uuid


AUDIT_SCHEMA_VERSION = 1
EVENT_CAPACITY = 256
RETURN_LIMIT_MAX = 100
OUTCOMES = ("changed", "no_change", "succeeded", "saved", "failed", "uncertain")


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _public_target(target):
    return {
        key: deepcopy(value)
        for key, value in dict(target or {}).items()
        if key != "objectId"
    }


class DocumentChangeLedger:
    """Keep one bounded in-memory session without retaining a live font object."""

    def __init__(self, capacity=EVENT_CAPACITY):
        self.capacity = max(1, int(capacity))
        self._lock = threading.RLock()
        self._reset_locked()

    def _reset_locked(self):
        self._session_id = None
        self._started_at = None
        self._target = None
        self._events = []
        self._counts = Counter({outcome: 0 for outcome in OUTCOMES})
        self._omitted_count = 0
        self._unattributed_count = 0
        self._cross_document_count = 0
        self._last_save = None
        self._sequence = 0

    def reset(self):
        with self._lock:
            self._reset_locked()

    def is_active(self):
        with self._lock:
            return self._session_id is not None

    def tracked_object_id(self):
        with self._lock:
            if not self._target:
                return None
            return self._target.get("objectId")

    def record_unattributed(self):
        with self._lock:
            self._unattributed_count += 1

    def record_cross_document(self):
        with self._lock:
            self._cross_document_count += 1

    def document_closed(self, object_id):
        with self._lock:
            if self._target and self._target.get("objectId") == object_id:
                self._reset_locked()
                return True
            return False

    def update_target(self, target):
        with self._lock:
            if not self._target or not target:
                return False
            if self._target.get("objectId") != target.get("objectId"):
                return False
            self._target.update(dict(target))
            return True

    def record(self, target, event):
        target = dict(target or {})
        event = dict(event or {})
        object_id = target.get("objectId")
        if object_id is None:
            self.record_unattributed()
            return False

        with self._lock:
            if self._target is None:
                self._session_id = uuid.uuid4().hex
                self._started_at = _utc_now()
                self._target = dict(target)
            elif self._target.get("objectId") != object_id:
                self._cross_document_count += 1
                return False
            else:
                self._target.update(target)

            outcome = str(event.get("outcome") or "uncertain")
            if outcome not in OUTCOMES:
                outcome = "uncertain"
            self._sequence += 1
            normalized = {
                "eventId": "event-{}".format(self._sequence),
                "timestamp": str(event.get("timestamp") or _utc_now()),
                "tool": str(event.get("tool") or "unknown"),
                "title": str(event.get("title") or event.get("tool") or "MCP mutation"),
                "effect": str(event.get("effect") or "edit"),
                "outcome": outcome,
                "target": deepcopy(event.get("target") or {}),
                "summary": str(event.get("summary") or "")[:500],
                "warnings": [str(value)[:300] for value in list(event.get("warnings") or [])[:8]],
                "opaque": bool(event.get("opaque", False)),
            }
            self._events.append(normalized)
            self._counts[outcome] += 1
            if outcome == "saved":
                self._last_save = {
                    "timestamp": normalized["timestamp"],
                    "filePath": target.get("filePath"),
                }
            if len(self._events) > self.capacity:
                del self._events[0]
                self._omitted_count += 1
            return True

    def snapshot(self, include_entries=True, limit=50):
        limit = max(1, min(int(limit), RETURN_LIMIT_MAX))
        with self._lock:
            warnings = []
            if self._unattributed_count:
                warnings.append(
                    "{} MCP code operation(s) could not be attributed to the tracked document.".format(
                        self._unattributed_count
                    )
                )
            if self._cross_document_count:
                warnings.append(
                    "{} MCP mutation attempt(s) targeted another open document and are not included.".format(
                        self._cross_document_count
                    )
                )
            events = deepcopy(self._events[-limit:]) if include_entries else []
            omitted_count = self._omitted_count + len(self._events) - len(events)
            return {
                "documentAuditSchemaVersion": AUDIT_SCHEMA_VERSION,
                "ok": True,
                "status": "active" if self._session_id else "idle",
                "sessionId": self._session_id,
                "startedAt": self._started_at,
                "target": _public_target(self._target),
                "counts": {outcome: int(self._counts[outcome]) for outcome in OUTCOMES},
                "entries": events,
                "omittedEntryCount": int(omitted_count),
                "unattributedOperationCount": int(self._unattributed_count),
                "crossDocumentAttemptCount": int(self._cross_document_count),
                "lastSave": deepcopy(self._last_save),
                "warnings": warnings,
                "error": None,
            }


def overview_markdown(snapshot):
    data = dict(snapshot or {})
    if data.get("status") != "active":
        return "# Glyphs MCP Changes\n\nNo document changes are being tracked."
    target = data.get("target") or {}
    counts = data.get("counts") or {}
    lines = [
        "# Glyphs MCP Changes",
        "",
        "- Document: {}".format(target.get("familyName") or "Untitled font"),
        "- File: {}".format(target.get("filePath") or "Unsaved"),
        "- Started: {}".format(data.get("startedAt") or "Unknown"),
        "- Changed: {}".format(counts.get("changed", 0)),
        "- Succeeded: {}".format(counts.get("succeeded", 0)),
        "- Failed: {}".format(counts.get("failed", 0)),
        "- Uncertain: {}".format(counts.get("uncertain", 0)),
        "- Saves: {}".format(counts.get("saved", 0)),
        "",
        "## Activity",
        "",
    ]
    for event in data.get("entries") or []:
        lines.append(
            "- {} — {} — {}: {}".format(
                event.get("timestamp") or "Unknown time",
                event.get("outcome") or "unknown",
                event.get("title") or event.get("tool") or "MCP mutation",
                event.get("summary") or "No summary returned",
            )
        )
    if not data.get("entries"):
        lines.append("- No retained events.")
    if data.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend("- {}".format(value) for value in data["warnings"])
    if data.get("omittedEntryCount"):
        lines.append("- {} earlier event(s) omitted by the bounded ledger.".format(data["omittedEntryCount"]))
    return "\n".join(lines)


DOCUMENT_CHANGE_LEDGER = DocumentChangeLedger()


__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "DOCUMENT_CHANGE_LEDGER",
    "DocumentChangeLedger",
    "EVENT_CAPACITY",
    "OUTCOMES",
    "RETURN_LIMIT_MAX",
    "overview_markdown",
]
