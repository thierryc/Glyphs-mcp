"""Save lifecycle for the per-save change graph."""

from __future__ import annotations

from collections import deque
from threading import RLock
from typing import Callable, Optional
from uuid import uuid4

from .change_history import ChangeHistory


_MAX_PENDING_SAVE_NOTIFICATIONS = 8


class DocumentHistoryLifecycle:
    def __init__(
        self,
        history: ChangeHistory,
        *,
        reset_tracking: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._history = history
        self._reset_tracking = reset_tracking
        self._inflight: dict[str, dict[str, object]] = {}
        self._pending_notifications: dict[str, deque[str]] = {}
        self._lock = RLock()

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

    def _reset(self, document_id: str) -> dict[str, bool]:
        tracking_reset = True
        if self._reset_tracking is not None:
            try:
                self._reset_tracking(document_id)
            except Exception:
                tracking_reset = False
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
    ) -> dict[str, bool]:
        with self._lock:
            state = self._inflight.get(document_id)
            if state is None or state.get("token") != token:
                return {
                    "notificationObserved": False,
                    "changeTrackingReset": False,
                    "historyReset": False,
                }
            # Keep the document fenced until process-local cleanup completes.
            # Otherwise another save can begin and have its new history erased
            # by this save's delayed reset.
            state["completing"] = True
        reset = (
            self._reset(document_id)
            if verified
            else {"changeTrackingReset": False, "historyReset": False}
        )
        with self._lock:
            state = self._inflight.get(document_id)
            if state is None or state.get("token") != token:
                return {
                    "notificationObserved": False,
                    **reset,
                }
            notification_observed = bool(state.get("notificationObserved"))
            self._inflight.pop(document_id, None)
            if expect_notification and not notification_observed:
                # Native callbacks carry no operation identifier. The adapter
                # therefore correlates them in selector order. Keep a bounded
                # queue of tombstones: a missing callback cannot permanently
                # lock the document, while an old late callback still cannot
                # reset history created by a newer operation.
                pending = self._pending_notifications.setdefault(
                    document_id,
                    deque(maxlen=_MAX_PENDING_SAVE_NOTIFICATIONS),
                )
                if token not in pending:
                    pending.append(token)
        return {
            "notificationObserved": notification_observed,
            **reset,
        }

    def document_was_saved(
        self,
        document_id: str,
        *,
        make_copy: bool = False,
        succeeded: bool = True,
        correlation_token: str | None = None,
    ) -> bool:
        if not document_id or make_copy or not succeeded:
            return False
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
                # A token is issued only by the native save adapter. An unknown
                # or stale one must never reset unrelated diagnostic history.
                return False
        reset = self._reset(document_id)
        return bool(reset["historyReset"])

    def document_was_closed(self, document_id: str) -> bool:
        if not document_id:
            return False
        with self._lock:
            self._inflight.pop(document_id, None)
            self._pending_notifications.pop(document_id, None)
        return bool(self._reset(document_id)["historyReset"])


__all__ = ["DocumentHistoryLifecycle"]
