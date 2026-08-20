"""One-shot verified document transactions with complete rollback checks."""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING, Any, Mapping, Optional, Protocol
from uuid import uuid4

from .canonical_tree import CanonicalSnapshot
from .semantic import ChangeSet, fingerprint_model

if TYPE_CHECKING:
    from .mutation import VerifiedMutationPlan


_LOGGER = logging.getLogger(__name__)


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


class StaleDocumentError(RuntimeError):
    pass


class TransactionVerificationError(RuntimeError):
    def __init__(self, message: str, *, rollback_succeeded: bool) -> None:
        super().__init__(message)
        self.rollback_succeeded = rollback_succeeded


@dataclass(frozen=True)
class TransactionResult:
    document_id: str
    operation_id: str
    before_fingerprint: str
    after_fingerprint: str
    requested_change_count: int
    observed_change_count: int
    inverse: ChangeSet

    @property
    def change_count(self) -> int:
        return self.observed_change_count


class TransactionKernel:
    _MAX_POST_SETTLE_RECONCILIATION_PASSES = 3
    stage_timing_names = (
        "initial_capture",
        "clone",
        "detached_apply",
        "verification",
        "live_apply",
        "settled_verification",
        "history",
        "total",
    )

    def __init__(
        self,
        adapter: TransactionAdapter,
        *,
        observer: Optional[TransactionObserver] = None,
    ) -> None:
        self._adapter = adapter
        self._observer = observer
        self._diagnostic_timings: dict[str, Mapping[str, float]] = {}
        self._timing_lock = RLock()

    def diagnostic_stage_timings(
        self, operation_id: str
    ) -> Mapping[str, float]:
        with self._timing_lock:
            return dict(self._diagnostic_timings.get(operation_id, {}))

    def _store_stage_timings(
        self, operation_id: str, values: Mapping[str, float]
    ) -> None:
        with self._timing_lock:
            self._diagnostic_timings[operation_id] = dict(values)
            while len(self._diagnostic_timings) > 100:
                self._diagnostic_timings.pop(next(iter(self._diagnostic_timings)))
        _LOGGER.debug(
            "verified mutation timings operation=%s stages=%s",
            operation_id,
            dict(values),
        )

    def _capture_verified_state(
        self,
        document_id: str,
        expected_snapshot: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Capture after Glyphs has had a chance to settle derived state.

        Host adapters that schedule derived updates after a native setter may
        provide ``capture_stable_model``. Pure/in-memory adapters retain the
        single-capture path.
        """

        stable_capture = getattr(self._adapter, "capture_stable_snapshot", None)
        if not callable(stable_capture):
            stable_capture = getattr(self._adapter, "capture_stable_model", None)
        if callable(stable_capture):
            if isinstance(expected_snapshot, CanonicalSnapshot):
                try:
                    return stable_capture(
                        document_id, expected_snapshot=expected_snapshot
                    )
                except TypeError:
                    pass
            return stable_capture(document_id)
        return self._capture_state(document_id)

    def _capture_state(self, document_id: str) -> Mapping[str, Any]:
        capture = getattr(self._adapter, "capture_snapshot", None)
        if callable(capture):
            return capture(document_id)
        return self._adapter.capture_model(document_id)

    @staticmethod
    def _retain_or_copy(model: Mapping[str, Any]) -> Mapping[str, Any]:
        if isinstance(model, CanonicalSnapshot):
            return model
        return copy.deepcopy(dict(model))

    def apply(
        self,
        *,
        document_id: str,
        expected_fingerprint: str,
        change_set: ChangeSet,
    ) -> TransactionResult:
        before = self._retain_or_copy(self._capture_state(document_id))
        current_fingerprint = fingerprint_model(before)
        if current_fingerprint != expected_fingerprint:
            raise StaleDocumentError("document fingerprint changed before the transaction")
        if change_set.before_fingerprint != current_fingerprint:
            raise StaleDocumentError("change set was reviewed against another document state")
        from .mutation import VerifiedMutationPlan

        expected_after = change_set.apply(before)
        plan = VerifiedMutationPlan(
            document_id=document_id,
            operation_id="op_transaction_{}".format(uuid4().hex),
            before_model=before,
            expected_after_model=expected_after,
            writable_change_set=change_set,
            observed_change_set=change_set,
        )
        return self.apply_plan(plan)

    def apply_plan(self, plan: "VerifiedMutationPlan") -> TransactionResult:
        transaction_started = time.perf_counter_ns()
        timings = {
            name: float(plan.stage_timings.get(name, 0.0))
            for name in self.stage_timing_names
        }
        document_id = plan.document_id
        if not document_id:
            raise ValueError("document_id is required")
        capture_started = time.perf_counter_ns()
        before = self._retain_or_copy(self._capture_state(document_id))
        timings["initial_capture"] += (
            time.perf_counter_ns() - capture_started
        ) / 1_000_000
        current_fingerprint = fingerprint_model(before)
        if current_fingerprint != plan.before_fingerprint:
            raise StaleDocumentError("document fingerprint changed before the transaction")
        if current_fingerprint != fingerprint_model(plan.before_model):
            raise StaleDocumentError("verified plan was built for another document state")
        expected_after = self._retain_or_copy(plan.expected_after_model)
        trace_token = None
        if self._observer is not None:
            history_started = time.perf_counter_ns()
            trace_token = self._observer.prepare_transaction(document_id, before)
            timings["history"] += (
                time.perf_counter_ns() - history_started
            ) / 1_000_000
        try:
            live_apply_started = time.perf_counter_ns()
            verified_apply = getattr(self._adapter, "apply_verified_change_set", None)
            if callable(verified_apply):
                apply_options = {
                    "operation_id": plan.operation_id,
                    "removes_contribution_id": plan.removes_contribution_id,
                    "replay_replacements": plan.replay_replacements,
                }
                if plan.capabilities or plan.execution_context:
                    apply_options.update(
                        capabilities=plan.capabilities,
                        execution_context=plan.execution_context,
                    )
                verified_apply(
                    document_id,
                    plan.writable_change_set,
                    **apply_options,
                )
            else:
                self._adapter.apply_change_set(document_id, plan.writable_change_set)
            timings["live_apply"] += (
                time.perf_counter_ns() - live_apply_started
            ) / 1_000_000
            settled_started = time.perf_counter_ns()
            actual_after = self._retain_or_copy(
                self._capture_verified_state(document_id, expected_after)
            )
            actual_fingerprint = fingerprint_model(actual_after)
            reconcile = getattr(self._adapter, "reconcile_verified_state", None)
            if (
                actual_fingerprint != plan.after_fingerprint
                and callable(reconcile)
                and fingerprint_model(expected_after) == plan.after_fingerprint
            ):
                for _ in range(self._MAX_POST_SETTLE_RECONCILIATION_PASSES):
                    reconcile(
                        document_id,
                        actual_after,
                        expected_after,
                        capabilities=plan.capabilities,
                        execution_context=plan.execution_context,
                    )
                    actual_after = self._retain_or_copy(
                        self._capture_verified_state(document_id, expected_after)
                    )
                    actual_fingerprint = fingerprint_model(actual_after)
                    if actual_fingerprint == plan.after_fingerprint:
                        break
            if (
                actual_fingerprint != plan.after_fingerprint
                or fingerprint_model(expected_after) != plan.after_fingerprint
            ):
                raise RuntimeError("document read-back did not match the detached verified plan")
            timings["settled_verification"] += (
                time.perf_counter_ns() - settled_started
            ) / 1_000_000
            if self._observer is not None:
                history_started = time.perf_counter_ns()
                commit = self._observer.commit_transaction
                if "writable_change_set" in getattr(commit, "__annotations__", {}):
                    commit(
                        trace_token,
                        document_id,
                        before,
                        actual_after,
                        plan.observed_change_set,
                        writable_change_set=plan.writable_change_set,
                    )
                else:
                    commit(
                        trace_token,
                        document_id,
                        before,
                        actual_after,
                        plan.observed_change_set,
                    )
                timings["history"] += (
                    time.perf_counter_ns() - history_started
                ) / 1_000_000
            verified_commit = getattr(self._adapter, "commit_verified_change", None)
            if callable(verified_commit):
                verified_commit(plan.operation_id)
        except Exception as exc:
            rollback_succeeded = False
            try:
                verified_restore = getattr(self._adapter, "restore_verified_attempt", None)
                if callable(verified_restore):
                    restore_options = {
                        "operation_id": plan.operation_id,
                        "removes_contribution_id": plan.removes_contribution_id,
                    }
                    if plan.capabilities or plan.execution_context:
                        restore_options.update(
                            capabilities=plan.capabilities,
                            execution_context=plan.execution_context,
                        )
                    verified_restore(
                        document_id,
                        before,
                        **restore_options,
                    )
                else:
                    self._adapter.restore_model(document_id, before)
                restored = self._capture_verified_state(document_id, before)
                rollback_succeeded = fingerprint_model(restored) == current_fingerprint
            except Exception:
                rollback_succeeded = False
            if self._observer is not None:
                try:
                    self._observer.abort_transaction(trace_token)
                except Exception:
                    pass
            timings["total"] = float(plan.stage_timings.get("total", 0.0)) + (
                time.perf_counter_ns() - transaction_started
            ) / 1_000_000
            self._store_stage_timings(plan.operation_id, timings)
            raise TransactionVerificationError(
                str(exc) or "document transaction verification failed",
                rollback_succeeded=rollback_succeeded,
            ) from exc
        from .mutation import writable_subset

        timings["total"] = float(plan.stage_timings.get("total", 0.0)) + (
            time.perf_counter_ns() - transaction_started
        ) / 1_000_000
        self._store_stage_timings(plan.operation_id, timings)

        return TransactionResult(
            document_id=document_id,
            operation_id=plan.operation_id,
            before_fingerprint=current_fingerprint,
            after_fingerprint=plan.after_fingerprint,
            requested_change_count=len(plan.writable_change_set.changes),
            observed_change_count=len(plan.observed_change_set.changes),
            # A rollback patch must start at the complete observed after-state,
            # not the writable-only intermediate target. Otherwise any Glyphs-
            # derived effect makes the inverse stale before it is ever used.
            inverse=writable_subset(
                actual_after,
                plan.observed_change_set.inverse(),
                capabilities=plan.capabilities,
            ),
        )


__all__ = [
    "StaleDocumentError",
    "TransactionAdapter",
    "TransactionKernel",
    "TransactionObserver",
    "TransactionResult",
    "TransactionVerificationError",
]
