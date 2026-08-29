"""Save-tolerant lifecycle and persistence evidence for open documents."""

from __future__ import annotations

import copy
import time
from collections import deque
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable, Mapping, Optional
from uuid import uuid4

from .change_history import ChangeHistory
from .semantic import ChangeSet, diff_models, fingerprint_model, public_change_dict


_MAX_PENDING_SAVE_NOTIFICATIONS = 8
_MAX_SAVE_EVENTS = 64
_MAX_PUBLIC_RESIDUAL_CHANGES = 12


@dataclass(frozen=True)
class SaveEvent:
    epoch: int
    document_id: str
    origin: str
    correlation_token: str | None
    observed_at: float
    saved_document_fingerprint: str | None
    source_file_fingerprint: str | None
    source_path: str | None
    source_exists: bool | None
    source_readable: bool | None
    saved_model: Mapping[str, Any] | None = field(repr=False)
    evidence_completeness: str = "partial"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "origin": self.origin,
            "correlationToken": self.correlation_token,
            "observedAt": self.observed_at,
            "savedDocumentFingerprint": self.saved_document_fingerprint,
            "sourceFileFingerprint": self.source_file_fingerprint,
            "sourcePath": self.source_path,
            "sourceExists": self.source_exists,
            "sourceReadable": self.source_readable,
            "evidenceCompleteness": self.evidence_completeness,
        }


@dataclass(frozen=True)
class TransactionSaveToken:
    token: str
    document_id: str
    start_epoch: int


@dataclass(frozen=True)
class PersistenceReconciliation:
    relationship: str
    source_file_changed: bool
    save_events: tuple[SaveEvent, ...]
    baseline_model: Mapping[str, Any] | None
    residual_change_set: ChangeSet
    residual_change_count: int
    document_dirty_after: bool | None
    evidence_completeness: str
    source_before: Mapping[str, Any] | None
    source_after: Mapping[str, Any] | None

    @property
    def save_observed(self) -> bool:
        return any(
            event.origin in {"native", "tool"} for event in self.save_events
        )

    @property
    def revert_available(self) -> bool:
        return self.residual_change_count > 0

    def to_public_dict(self) -> dict[str, Any]:
        before = dict(self.source_before or {})
        after = dict(self.source_after or {})
        residual_changes = [
            public_change_dict(change)
            for change in self.residual_change_set.changes[
                :_MAX_PUBLIC_RESIDUAL_CHANGES
            ]
        ]
        return {
            "relationship": self.relationship,
            "saveObserved": self.save_observed,
            "saveEventCount": len(self.save_events),
            "saveEvents": [event.to_public_dict() for event in self.save_events],
            "sourceFileChanged": self.source_file_changed,
            "sourceFileFingerprintBefore": before.get("contentFingerprint"),
            "sourceFileFingerprintAfter": after.get("contentFingerprint"),
            "residualChangeCount": self.residual_change_count,
            "residualSemanticDiff": {
                "beforeFingerprint": self.residual_change_set.before_fingerprint,
                "afterFingerprint": self.residual_change_set.after_fingerprint,
                "changeCount": self.residual_change_count,
                "changes": residual_changes,
                "changesTruncated": (
                    self.residual_change_count > len(residual_changes)
                ),
            },
            "documentDirtyAfter": self.document_dirty_after,
            "provenance": {
                "liveDocument": "canonical-readback",
                "savedDocument": (
                    "decoded-source" if self.baseline_model is not None else "unavailable"
                ),
                "sourceFile": "filesystem-observation",
                "saveEvents": "native-or-tool-notification-ledger",
            },
            "evidenceCompleteness": self.evidence_completeness,
        }


class DocumentHistoryLifecycle:
    """Coordinate native saves without making them document-operation blockers."""

    def __init__(
        self,
        history: ChangeHistory,
        *,
        reset_tracking: Optional[Callable[[str], None]] = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._history = history
        self._reset_tracking = reset_tracking
        self._now = now
        self._inflight: dict[str, dict[str, object]] = {}
        self._pending_notifications: dict[str, deque[str]] = {}
        self._events: dict[str, deque[SaveEvent]] = {}
        self._epochs: dict[str, int] = {}
        self._active_transactions: dict[str, set[str]] = {}
        self._pending_source_notifications: dict[str, deque[str]] = {}
        self._last_saved_document_fingerprint: dict[str, str] = {}
        self._lock = RLock()

    def begin_transaction(self, document_id: str) -> TransactionSaveToken:
        if not document_id:
            raise ValueError("document_id is required")
        with self._lock:
            token = "txn_save_{}".format(uuid4().hex)
            self._active_transactions.setdefault(document_id, set()).add(token)
            return TransactionSaveToken(
                token=token,
                document_id=document_id,
                start_epoch=self._epochs.get(document_id, 0),
            )

    def _finish_transaction_token(self, token: TransactionSaveToken) -> None:
        with self._lock:
            active = self._active_transactions.get(token.document_id)
            if active is None:
                return
            active.discard(token.token)
            if not active:
                self._active_transactions.pop(token.document_id, None)

    def cancel_transaction(self, token: TransactionSaveToken) -> None:
        """Idempotently release a transaction fence after unexpected failure."""

        self._finish_transaction_token(token)

    @staticmethod
    def _source_state_changed(
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
    ) -> bool:
        if before is None:
            return after is not None
        if after is None:
            return True
        return any(
            before.get(key) != after.get(key)
            for key in ("kind", "exists", "contentFingerprint")
        )

    def _append_event(
        self,
        document_id: str,
        *,
        origin: str,
        correlation_token: str | None,
        source_state: Mapping[str, Any] | None,
        saved_model: Mapping[str, Any] | None,
    ) -> tuple[SaveEvent, bool]:
        state = dict(source_state or {})
        source_fingerprint = state.get("contentFingerprint")
        saved_fingerprint = None
        copied_model: Mapping[str, Any] | None = None
        if isinstance(saved_model, Mapping):
            copied_model = copy.deepcopy(dict(saved_model))
            try:
                saved_fingerprint = fingerprint_model(copied_model)
            except Exception:
                copied_model = None
        with self._lock:
            events = self._events.setdefault(
                document_id, deque(maxlen=_MAX_SAVE_EVENTS)
            )
            if correlation_token:
                duplicate = next(
                    (
                        event
                        for event in reversed(events)
                        if event.correlation_token == correlation_token
                    ),
                    None,
                )
                if duplicate is not None:
                    return duplicate, True
            epoch = self._epochs.get(document_id, 0) + 1
            self._epochs[document_id] = epoch
            event = SaveEvent(
                epoch=epoch,
                document_id=document_id,
                origin=str(origin or "native"),
                correlation_token=correlation_token,
                observed_at=float(self._now()),
                saved_document_fingerprint=saved_fingerprint,
                source_file_fingerprint=(
                    str(source_fingerprint) if source_fingerprint else None
                ),
                source_path=(
                    str(state.get("filePath")) if state.get("filePath") else None
                ),
                source_exists=(
                    bool(state.get("exists")) if "exists" in state else None
                ),
                source_readable=(
                    bool(state.get("readable")) if "readable" in state else None
                ),
                saved_model=copied_model,
                evidence_completeness=(
                    "complete"
                    if copied_model is not None and source_fingerprint
                    else "partial"
                ),
            )
            events.append(event)
            if saved_fingerprint:
                self._last_saved_document_fingerprint[document_id] = saved_fingerprint
            return event, False

    def persistence_state(
        self,
        document_id: str,
        *,
        live_model: Mapping[str, Any] | None = None,
        source_state: Mapping[str, Any] | None = None,
        dirty: bool | None = None,
    ) -> dict[str, Any]:
        state = dict(source_state or {})
        saved_model = state.pop("savedModel", None)
        if isinstance(saved_model, Mapping):
            try:
                saved_fingerprint = fingerprint_model(saved_model)
            except Exception:
                saved_fingerprint = None
            if saved_fingerprint:
                with self._lock:
                    self._last_saved_document_fingerprint.setdefault(
                        document_id, saved_fingerprint
                    )
        live_fingerprint = (
            fingerprint_model(live_model) if isinstance(live_model, Mapping) else None
        )
        with self._lock:
            return {
                "liveDocumentFingerprint": live_fingerprint,
                "lastSavedDocumentFingerprint": self._last_saved_document_fingerprint.get(
                    document_id
                ),
                "sourceFileFingerprint": state.get("contentFingerprint"),
                "sourcePath": state.get("filePath"),
                "sourceExists": state.get("exists"),
                "sourceReadable": state.get("readable"),
                "dirty": dirty,
                "saveEpoch": self._epochs.get(document_id, 0),
            }

    def reconcile_transaction(
        self,
        token: TransactionSaveToken,
        *,
        before_model: Mapping[str, Any],
        after_model: Mapping[str, Any],
        source_before: Mapping[str, Any] | None,
        source_after: Mapping[str, Any] | None,
        dirty_after: bool | None = None,
    ) -> PersistenceReconciliation:
        source_changed = self._source_state_changed(source_before, source_after)
        with self._lock:
            events = tuple(
                event
                for event in self._events.get(token.document_id, ())
                if event.epoch > token.start_epoch
            )
        if source_changed:
            after_state = dict(source_after or {})
            after_source_fingerprint = after_state.get("contentFingerprint")
            if not any(
                event.source_file_fingerprint == after_source_fingerprint
                for event in events
            ):
                saved_model = after_state.get("savedModel")
                event, _duplicate = self._append_event(
                    token.document_id,
                    origin="source_observation",
                    correlation_token=None,
                    source_state=after_state,
                    saved_model=(saved_model if isinstance(saved_model, Mapping) else None),
                )
                events = events + (event,)
                if event.source_file_fingerprint:
                    with self._lock:
                        pending = self._pending_source_notifications.setdefault(
                            token.document_id,
                            deque(maxlen=_MAX_PENDING_SAVE_NOTIFICATIONS),
                        )
                        pending.append(event.source_file_fingerprint)
        baseline_model = next(
            (
                event.saved_model
                for event in reversed(events)
                if isinstance(event.saved_model, Mapping)
            ),
            None,
        )
        before_fingerprint = fingerprint_model(before_model)
        after_fingerprint = fingerprint_model(after_model)
        baseline_fingerprint = (
            fingerprint_model(baseline_model)
            if isinstance(baseline_model, Mapping)
            else None
        )
        if not events and not source_changed:
            relationship = "unchanged"
        elif baseline_fingerprint == before_fingerprint:
            relationship = "saved_before"
        elif baseline_fingerprint == after_fingerprint:
            relationship = "saved_after"
        elif baseline_model is not None:
            relationship = "saved_intermediate"
        else:
            relationship = "source_changed_unclassified"
        residual_change_set = (
            diff_models(baseline_model, after_model)
            if isinstance(baseline_model, Mapping)
            else diff_models(before_model, after_model)
        )
        residual_count = len(residual_change_set.changes)
        completeness = (
            "complete"
            if (not source_changed and not events)
            or (
                baseline_model is not None
                and all(
                    event.evidence_completeness == "complete" for event in events
                )
            )
            else "partial"
        )
        if self._events_define_saved_baseline(events, baseline_model):
            # The active action trace has not been appended yet. Clear the old
            # saved session now; it will record only the residual transition.
            self._reset(token.document_id, include_tracking=False)
        self._finish_transaction_token(token)
        return PersistenceReconciliation(
            relationship=relationship,
            source_file_changed=source_changed,
            save_events=events,
            baseline_model=baseline_model,
            residual_change_set=residual_change_set,
            residual_change_count=residual_count,
            document_dirty_after=dirty_after,
            evidence_completeness=completeness,
            source_before=(dict(source_before) if source_before is not None else None),
            source_after=(dict(source_after) if source_after is not None else None),
        )

    @staticmethod
    def _events_define_saved_baseline(
        events: tuple[SaveEvent, ...],
        baseline_model: Mapping[str, Any] | None,
    ) -> bool:
        return bool(
            isinstance(baseline_model, Mapping)
            or any(event.origin in {"native", "tool"} for event in events)
        )

    def abort_transaction(
        self,
        token: TransactionSaveToken,
        *,
        before_model: Mapping[str, Any],
        restored_model: Mapping[str, Any],
        source_before: Mapping[str, Any] | None,
        source_after: Mapping[str, Any] | None,
        dirty_after: bool | None = None,
    ) -> PersistenceReconciliation:
        return self.reconcile_transaction(
            token,
            before_model=before_model,
            after_model=restored_model,
            source_before=source_before,
            source_after=source_after,
            dirty_after=dirty_after,
        )

    def begin_tool_save(self, document_id: str) -> str:
        if not document_id:
            raise ValueError("document_id is required")
        with self._lock:
            if document_id in self._inflight:
                raise RuntimeError("a document save is already in progress")
            token = "save_{}".format(uuid4().hex)
            self._inflight[document_id] = {
                "token": token,
                "notificationObserved": False,
                "completing": False,
            }
            return token

    def notification_observed(self, document_id: str, token: str) -> bool:
        with self._lock:
            state = self._inflight.get(document_id)
            return bool(
                state is not None
                and state.get("token") == token
                and state.get("notificationObserved")
            )

    def _reset(
        self, document_id: str, *, include_tracking: bool = True
    ) -> dict[str, bool]:
        tracking_reset = not include_tracking
        if include_tracking and self._reset_tracking is not None:
            try:
                self._reset_tracking(document_id)
                tracking_reset = True
            except Exception:
                tracking_reset = False
        elif include_tracking:
            tracking_reset = True
        history_reset = False
        if tracking_reset:
            try:
                self._history.reset_after_save(document_id)
                history_reset = True
            except Exception:
                history_reset = False
        return {
            "changeTrackingReset": tracking_reset,
            "historyReset": history_reset,
        }

    def complete_tool_save(
        self,
        document_id: str,
        token: str,
        *,
        verified: bool,
        expect_notification: bool = False,
        source_state: Mapping[str, Any] | None = None,
        saved_model: Mapping[str, Any] | None = None,
    ) -> dict[str, bool]:
        with self._lock:
            state = self._inflight.get(document_id)
            if state is None or state.get("token") != token:
                return {
                    "notificationObserved": False,
                    "changeTrackingReset": False,
                    "historyReset": False,
                }
            state["completing"] = True
        if verified:
            self._append_event(
                document_id,
                origin="tool",
                correlation_token=token,
                source_state=source_state,
                saved_model=saved_model,
            )
        with self._lock:
            transaction_active = bool(
                self._active_transactions.get(document_id)
            )
        reset = (
            self._reset(document_id)
            if verified and not transaction_active
            else {"changeTrackingReset": False, "historyReset": False}
        )
        with self._lock:
            state = self._inflight.get(document_id)
            if state is None or state.get("token") != token:
                return {"notificationObserved": False, **reset}
            notification_observed = bool(state.get("notificationObserved"))
            self._inflight.pop(document_id, None)
            if expect_notification and not notification_observed:
                pending = self._pending_notifications.setdefault(
                    document_id,
                    deque(maxlen=_MAX_PENDING_SAVE_NOTIFICATIONS),
                )
                if token not in pending:
                    pending.append(token)
        return {"notificationObserved": notification_observed, **reset}

    def document_was_saved(
        self,
        document_id: str,
        *,
        make_copy: bool = False,
        succeeded: bool = True,
        correlation_token: str | None = None,
        source_state: Mapping[str, Any] | None = None,
        saved_model: Mapping[str, Any] | None = None,
    ) -> bool:
        if not document_id or make_copy or not succeeded:
            return False
        _event, duplicate = self._append_event(
            document_id,
            origin="tool" if correlation_token else "native",
            correlation_token=correlation_token,
            source_state=source_state,
            saved_model=saved_model,
        )
        with self._lock:
            state = self._inflight.get(document_id)
            if (
                correlation_token
                and state is not None
                and state.get("token") == correlation_token
            ):
                state["notificationObserved"] = True
                return False
            pending = self._pending_notifications.get(document_id)
            if correlation_token and pending is not None:
                try:
                    pending.remove(correlation_token)
                except ValueError:
                    pass
                else:
                    if not pending:
                        self._pending_notifications.pop(document_id, None)
                    return False
            if correlation_token:
                return False
            pending_source = self._pending_source_notifications.get(document_id)
            if pending_source is not None and _event.source_file_fingerprint:
                try:
                    pending_source.remove(_event.source_file_fingerprint)
                except ValueError:
                    pass
                else:
                    if not pending_source:
                        self._pending_source_notifications.pop(document_id, None)
                    return False
            if self._active_transactions.get(document_id):
                return False
        if duplicate:
            return False
        reset = self._reset(document_id)
        return bool(reset["historyReset"])

    def document_was_closed(self, document_id: str) -> bool:
        if not document_id:
            return False
        with self._lock:
            self._inflight.pop(document_id, None)
            self._pending_notifications.pop(document_id, None)
            self._events.pop(document_id, None)
            self._epochs.pop(document_id, None)
            self._active_transactions.pop(document_id, None)
            self._pending_source_notifications.pop(document_id, None)
            self._last_saved_document_fingerprint.pop(document_id, None)
        return bool(self._reset(document_id)["historyReset"])


__all__ = [
    "DocumentHistoryLifecycle",
    "PersistenceReconciliation",
    "SaveEvent",
    "TransactionSaveToken",
]
