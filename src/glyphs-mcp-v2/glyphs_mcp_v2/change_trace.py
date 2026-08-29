"""Application/transaction bridge that records each document tool call once."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .change_history import ActionCommit, ChangeHistory
from .canonical_schema import CanonicalCoverage
from .contracts import ToolResponse
from .semantic import ChangeSet, diff_models, fingerprint_model


@dataclass
class _ActionScope:
    tool: str
    effect: str
    document_id: Optional[str]
    reason: Optional[str]
    observed_tree_hash: Optional[str] = None
    before_tree_hash: Optional[str] = None
    after_tree_hash: Optional[str] = None
    change_set: Optional[ChangeSet] = None
    writable_change_set: Optional[ChangeSet] = None
    coverage: CanonicalCoverage = CanonicalCoverage.complete()
    transaction_completed: bool = False
    history_recorded: bool = True
    history_warning: Optional[str] = None
    history_boundary: bool = False
    commit: Optional[ActionCommit] = None
    context_token: Optional[Token] = None


@dataclass(frozen=True)
class _TransactionTrace:
    scope: Optional[_ActionScope]
    before_tree_hash: Optional[str]


_ACTIVE_SCOPE: ContextVar[Optional[_ActionScope]] = ContextVar(
    "glyphs_mcp_v2_action_scope", default=None
)


class ActionTraceCoordinator:
    def __init__(self, history: ChangeHistory) -> None:
        self.history = history

    def start_action(self, tool: str, effect: str, arguments: Mapping[str, Any]) -> _ActionScope:
        document_id = str(arguments.get("documentId") or arguments.get("document_id") or "") or None
        reason = str(arguments.get("reason") or "") or None
        scope = _ActionScope(tool=tool, effect=effect, document_id=document_id, reason=reason)
        scope.context_token = _ACTIVE_SCOPE.set(scope)
        return scope

    def bind_document(self, document_id: str) -> None:
        scope = _ACTIVE_SCOPE.get()
        if scope is not None and document_id:
            scope.document_id = document_id

    def mark_history_boundary(self) -> None:
        scope = _ACTIVE_SCOPE.get()
        if scope is not None:
            scope.history_boundary = True

    @staticmethod
    def _mark_history_failure(
        scope: Optional[_ActionScope], error: BaseException
    ) -> None:
        if scope is None:
            return
        scope.history_recorded = False
        scope.history_warning = (
            "Change history persistence failed ({}); the tool result remains "
            "authoritative.".format(type(error).__name__)
        )

    def _matching_tree_hash(
        self,
        model: Mapping[str, Any],
        *candidates: Optional[str],
    ) -> Optional[str]:
        expected = fingerprint_model(model)
        seen = set()
        for tree_hash in candidates:
            if not tree_hash or tree_hash in seen:
                continue
            seen.add(tree_hash)
            try:
                descriptor = self.history.trees.descriptor(tree_hash)
            except (KeyError, ValueError):
                continue
            if str(descriptor.get("modelFingerprint") or "") == expected:
                return tree_hash
        return None

    def _store_or_reuse(
        self,
        document_id: str,
        model: Mapping[str, Any],
        *candidates: Optional[str],
    ) -> str:
        values = candidates + (self.history.head_tree_hash(document_id),)
        if not any(values):
            return self.history.trees.store_model(model).tree_hash
        matched = self._matching_tree_hash(model, *values)
        if matched:
            return matched
        return self.history.trees.store_model(model).tree_hash

    def _store_transition_with_fallback(
        self,
        before_tree_hash: str,
        after: Mapping[str, Any],
        change_set: ChangeSet,
        *,
        scope: Optional[_ActionScope],
    ) -> Optional[str]:
        """Persist an after-state without making history a mutation outcome.

        The incremental tree writer is an optimization. A valid complete
        after-model remains authoritative when that optimization rejects a
        transition. Even complete-tree persistence failure must not replace a
        successfully observed execution result with an unrelated exception.
        """

        try:
            snapshot = self.history.trees.store_verified_transition(
                before_tree_hash,
                after,
                change_set,
            )
        except Exception as incremental_error:
            try:
                snapshot = self.history.trees.store_model(after)
                if snapshot.model_fingerprint != change_set.after_fingerprint:
                    raise ValueError(
                        "complete after-model does not match the observed fingerprint"
                    )
            except Exception as fallback_error:
                if scope is not None:
                    scope.history_recorded = False
                    scope.history_warning = (
                        "Change history could not store the observed after-state "
                        "(incremental: {}; complete: {}).".format(
                            type(incremental_error).__name__,
                            type(fallback_error).__name__,
                        )
                    )
                return None
        return snapshot.tree_hash

    def observe_model(self, document_id: str, model: Mapping[str, Any]) -> str:
        scope = _ACTIVE_SCOPE.get()
        try:
            tree_hash = self._store_or_reuse(document_id, model)
        except Exception as error:
            self._mark_history_failure(scope, error)
            return ""
        if scope is not None:
            scope.document_id = document_id
            scope.observed_tree_hash = tree_hash
        return tree_hash

    def observe_transition(
        self,
        document_id: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        change_set: Optional[ChangeSet] = None,
        coverage: CanonicalCoverage | None = None,
    ) -> tuple[str, str]:
        """Record a detached before/after pair captured outside the mutation kernel."""

        scope = _ACTIVE_SCOPE.get()
        try:
            before_tree_hash = self._store_or_reuse(
                document_id,
                before,
                scope.observed_tree_hash if scope is not None else None,
            )
        except Exception as error:
            self._mark_history_failure(scope, error)
            return "", ""
        resolved_changes = change_set or diff_models(before, after)
        after_tree_hash = self._store_transition_with_fallback(
            before_tree_hash,
            after,
            resolved_changes,
            scope=scope,
        )
        if after_tree_hash is None:
            return before_tree_hash, before_tree_hash
        if scope is not None:
            scope.document_id = document_id
            scope.before_tree_hash = before_tree_hash
            scope.after_tree_hash = after_tree_hash
            scope.change_set = resolved_changes
            scope.coverage = coverage or CanonicalCoverage.complete()
            scope.transaction_completed = True
        return before_tree_hash, after_tree_hash

    @staticmethod
    def needs_initial_observation(scope: _ActionScope) -> bool:
        return bool(
            scope.document_id
            and not scope.transaction_completed
            and not scope.observed_tree_hash
        )

    def prepare_transaction(self, document_id: str, before: Mapping[str, Any]) -> _TransactionTrace:
        scope = _ACTIVE_SCOPE.get()
        if scope is not None:
            scope.document_id = document_id
        try:
            before_tree_hash = self._store_or_reuse(
                document_id,
                before,
                scope.observed_tree_hash if scope is not None else None,
            )
        except Exception as error:
            self._mark_history_failure(scope, error)
            before_tree_hash = None
        return _TransactionTrace(scope=scope, before_tree_hash=before_tree_hash)

    def commit_transaction(
        self,
        token: _TransactionTrace,
        document_id: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        change_set: ChangeSet,
        writable_change_set: Optional[ChangeSet] = None,
        coverage: Optional[CanonicalCoverage] = None,
    ) -> None:
        before_tree_hash = token.before_tree_hash
        if before_tree_hash is None:
            try:
                before_tree_hash = self._store_or_reuse(document_id, before)
                if token.scope is not None:
                    token.scope.history_recorded = True
                    token.scope.history_warning = None
            except Exception as error:
                self._mark_history_failure(token.scope, error)
                return
        after_tree_hash = self._store_transition_with_fallback(
            before_tree_hash,
            after,
            change_set,
            scope=token.scope,
        )
        if after_tree_hash is None:
            return
        if token.scope is not None:
            token.scope.document_id = document_id
            token.scope.before_tree_hash = before_tree_hash
            token.scope.after_tree_hash = after_tree_hash
            token.scope.change_set = change_set
            token.scope.writable_change_set = writable_change_set or change_set
            token.scope.coverage = coverage or CanonicalCoverage.complete()
            token.scope.transaction_completed = True

    def abort_transaction(self, token: _TransactionTrace) -> None:
        if token.scope is not None:
            token.scope.before_tree_hash = None
            token.scope.after_tree_hash = None
            token.scope.change_set = None
            token.scope.writable_change_set = None
            token.scope.transaction_completed = False

    def finish_action(self, scope: _ActionScope, response: ToolResponse) -> Optional[ActionCommit]:
        try:
            if not scope.history_recorded:
                return None
            if scope.history_boundary:
                return None
            document_id = scope.document_id
            if not document_id:
                return None
            if scope.transaction_completed:
                before_hash = scope.before_tree_hash
                after_hash = scope.after_tree_hash
            elif scope.observed_tree_hash:
                before_hash = scope.observed_tree_hash
                after_hash = scope.observed_tree_hash
            else:
                before_hash = self.history.head_tree_hash(document_id)
                after_hash = before_hash
            if not before_hash or not after_hash:
                return None
            scope.commit = self.history.record_action(
                document_id=document_id,
                tool=scope.tool,
                effect=scope.effect,
                status=response.status,
                run_id=response.metadata.run_id,
                before_tree_hash=before_hash,
                after_tree_hash=after_hash,
                reason=scope.reason,
                operation_id=response.metadata.operation_id,
                change_set=scope.change_set,
                writable_change_set=scope.writable_change_set,
                coverage=scope.coverage,
                commit_id=response.metadata.operation_id,
            )
            return scope.commit
        except Exception as error:
            scope.history_recorded = False
            scope.history_warning = (
                scope.history_warning
                or "Change history could not record this action ({}).".format(
                    type(error).__name__
                )
            )
            return None
        finally:
            if scope.context_token is not None:
                _ACTIVE_SCOPE.reset(scope.context_token)


__all__ = ["ActionTraceCoordinator"]
