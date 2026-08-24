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

    def observe_model(self, document_id: str, model: Mapping[str, Any]) -> str:
        tree_hash = self._store_or_reuse(document_id, model)
        scope = _ACTIVE_SCOPE.get()
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
        before_tree_hash = self._store_or_reuse(
            document_id,
            before,
            scope.observed_tree_hash if scope is not None else None,
        )
        resolved_changes = change_set or diff_models(before, after)
        after_snapshot = self.history.trees.store_verified_transition(
            before_tree_hash,
            after,
            resolved_changes,
        )
        if scope is not None:
            scope.document_id = document_id
            scope.before_tree_hash = before_tree_hash
            scope.after_tree_hash = after_snapshot.tree_hash
            scope.change_set = resolved_changes
            scope.coverage = coverage or CanonicalCoverage.complete()
            scope.transaction_completed = True
        return before_tree_hash, after_snapshot.tree_hash

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
        before_tree_hash = self._store_or_reuse(
            document_id,
            before,
            scope.observed_tree_hash if scope is not None else None,
        )
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
        del before
        after_snapshot = self.history.trees.store_verified_transition(
            token.before_tree_hash,
            after,
            change_set,
        )
        if token.scope is not None:
            token.scope.document_id = document_id
            token.scope.before_tree_hash = token.before_tree_hash
            token.scope.after_tree_hash = after_snapshot.tree_hash
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
        finally:
            if scope.context_token is not None:
                _ACTIVE_SCOPE.reset(scope.context_token)


__all__ = ["ActionTraceCoordinator"]
