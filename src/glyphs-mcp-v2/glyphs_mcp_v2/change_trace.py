"""Application/transaction bridge that records each document tool call once."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .change_history import ActionCommit, ChangeHistory
from .contracts import ToolResponse
from .semantic import ChangeSet, diff_models


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
    transaction_completed: bool = False
    commit: Optional[ActionCommit] = None
    context_token: Optional[Token] = None


@dataclass(frozen=True)
class _TransactionTrace:
    scope: Optional[_ActionScope]
    before_tree_hash: str


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

    def observe_model(self, document_id: str, model: Mapping[str, Any]) -> str:
        snapshot = self.history.trees.store_model(model)
        scope = _ACTIVE_SCOPE.get()
        if scope is not None:
            scope.document_id = document_id
            scope.observed_tree_hash = snapshot.tree_hash
        return snapshot.tree_hash

    def observe_transition(
        self,
        document_id: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        change_set: Optional[ChangeSet] = None,
    ) -> tuple[str, str]:
        """Record a detached before/after pair captured outside the mutation kernel."""

        before_snapshot = self.history.trees.store_model(before)
        after_snapshot = self.history.trees.store_model(after)
        scope = _ACTIVE_SCOPE.get()
        if scope is not None:
            scope.document_id = document_id
            scope.before_tree_hash = before_snapshot.tree_hash
            scope.after_tree_hash = after_snapshot.tree_hash
            scope.change_set = change_set or diff_models(before, after)
            scope.transaction_completed = True
        return before_snapshot.tree_hash, after_snapshot.tree_hash

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
        before_snapshot = self.history.trees.store_model(before)
        return _TransactionTrace(scope=scope, before_tree_hash=before_snapshot.tree_hash)

    def commit_transaction(
        self,
        token: _TransactionTrace,
        document_id: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        change_set: ChangeSet,
        writable_change_set: Optional[ChangeSet] = None,
    ) -> None:
        del before
        after_snapshot = self.history.trees.store_model(after)
        if token.scope is not None:
            token.scope.document_id = document_id
            token.scope.before_tree_hash = token.before_tree_hash
            token.scope.after_tree_hash = after_snapshot.tree_hash
            token.scope.change_set = change_set
            token.scope.writable_change_set = writable_change_set or change_set
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
                commit_id=response.metadata.operation_id,
            )
            return scope.commit
        finally:
            if scope.context_token is not None:
                _ACTIVE_SCOPE.reset(scope.context_token)


__all__ = ["ActionTraceCoordinator"]
