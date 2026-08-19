"""One-shot verified document transactions with complete rollback checks."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, Optional, Protocol
from uuid import uuid4

from .semantic import ChangeSet, fingerprint_model

if TYPE_CHECKING:
    from .mutation import VerifiedMutationPlan


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

    def __init__(
        self,
        adapter: TransactionAdapter,
        *,
        observer: Optional[TransactionObserver] = None,
    ) -> None:
        self._adapter = adapter
        self._observer = observer

    def _capture_verified_state(self, document_id: str) -> Mapping[str, Any]:
        """Capture after Glyphs has had a chance to settle derived state.

        Host adapters that schedule derived updates after a native setter may
        provide ``capture_stable_model``. Pure/in-memory adapters retain the
        single-capture path.
        """

        stable_capture = getattr(self._adapter, "capture_stable_model", None)
        if callable(stable_capture):
            return stable_capture(document_id)
        return self._adapter.capture_model(document_id)

    def apply(
        self,
        *,
        document_id: str,
        expected_fingerprint: str,
        change_set: ChangeSet,
    ) -> TransactionResult:
        before = copy.deepcopy(dict(self._adapter.capture_model(document_id)))
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
        document_id = plan.document_id
        if not document_id:
            raise ValueError("document_id is required")
        before = copy.deepcopy(dict(self._adapter.capture_model(document_id)))
        current_fingerprint = fingerprint_model(before)
        if current_fingerprint != plan.before_fingerprint:
            raise StaleDocumentError("document fingerprint changed before the transaction")
        if current_fingerprint != fingerprint_model(plan.before_model):
            raise StaleDocumentError("verified plan was built for another document state")
        expected_after = copy.deepcopy(dict(plan.expected_after_model))
        trace_token = None
        if self._observer is not None:
            trace_token = self._observer.prepare_transaction(document_id, before)
        try:
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
            actual_after = copy.deepcopy(dict(self._capture_verified_state(document_id)))
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
                    actual_after = copy.deepcopy(
                        dict(self._capture_verified_state(document_id))
                    )
                    actual_fingerprint = fingerprint_model(actual_after)
                    if actual_fingerprint == plan.after_fingerprint:
                        break
            if (
                actual_fingerprint != plan.after_fingerprint
                or fingerprint_model(expected_after) != plan.after_fingerprint
            ):
                raise RuntimeError("document read-back did not match the detached verified plan")
            if self._observer is not None:
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
                restored = self._capture_verified_state(document_id)
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
        from .mutation import writable_subset

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
