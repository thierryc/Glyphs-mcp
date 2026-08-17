"""Per-save Git-like action history derived from canonical font trees."""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable, Mapping, Optional
from uuid import uuid4

from .canonical_tree import CanonicalFontTree
from .semantic import ChangeSet


@dataclass(frozen=True)
class ActionCommit:
    commit_id: str
    parent_id: Optional[str]
    document_id: str
    tool: str
    effect: str
    status: str
    run_id: str
    source: str
    before_tree_hash: str
    after_tree_hash: str
    created_at: float
    reason: Optional[str]
    operation_id: Optional[str]
    change_set: ChangeSet

    @property
    def changed(self) -> bool:
        return self.before_tree_hash != self.after_tree_hash

    @property
    def changed_glyphs(self) -> tuple[str, ...]:
        result: list[str] = []
        seen = set()
        for change in self.change_set.changes:
            if len(change.path) >= 2 and change.path[0] == "glyphs":
                name = change.path[1]
                if name not in seen:
                    seen.add(name)
                    result.append(name)
        return tuple(result)


@dataclass(frozen=True)
class SessionDiff:
    document_id: str
    run_id: str
    before_tree_hash: str
    after_tree_hash: str
    commit_ids: tuple[str, ...]
    change_set: ChangeSet


@dataclass
class _DocumentState:
    commits: list[ActionCommit] = field(default_factory=list)
    head_tree_hash: Optional[str] = None
    baseline_tree_hash: Optional[str] = None
    latest_session: Optional[SessionDiff] = None


class ChangeHistory:
    """Thread-safe action graph whose visible refs reset after a document save."""

    def __init__(
        self,
        trees: CanonicalFontTree,
        *,
        now: Callable[[], float] = time.time,
        id_factory: Optional[Callable[[], str]] = None,
    ) -> None:
        self.trees = trees
        self._now = now
        self._id_factory = id_factory or (lambda: "change_{}".format(uuid4().hex))
        self._documents: dict[str, _DocumentState] = {}
        self._commits: dict[str, ActionCommit] = {}
        self._listeners: list[Callable[[str], None]] = []
        self._lock = RLock()

    def subscribe(self, listener: Callable[[str], None]) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def _notify(self, document_id: str) -> None:
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(document_id)
            except Exception:
                pass

    def _append(
        self,
        *,
        state: _DocumentState,
        document_id: str,
        tool: str,
        effect: str,
        status: str,
        run_id: str,
        source: str,
        before_tree_hash: str,
        after_tree_hash: str,
        reason: Optional[str],
        operation_id: Optional[str],
        change_set: Optional[ChangeSet] = None,
    ) -> ActionCommit:
        before_fingerprint = str(self.trees.descriptor(before_tree_hash)["modelFingerprint"])
        after_fingerprint = str(self.trees.descriptor(after_tree_hash)["modelFingerprint"])
        if change_set is not None:
            if (
                change_set.before_fingerprint != before_fingerprint
                or change_set.after_fingerprint != after_fingerprint
            ):
                raise ValueError("verified change set does not match its canonical trees")
        elif before_tree_hash == after_tree_hash:
            change_set = ChangeSet.from_changes(
                before_fingerprint=before_fingerprint,
                after_fingerprint=after_fingerprint,
                changes=(),
            )
        else:
            change_set = self.trees.diff(before_tree_hash, after_tree_hash)
        commit = ActionCommit(
            commit_id=str(self._id_factory()),
            parent_id=state.commits[-1].commit_id if state.commits else None,
            document_id=document_id,
            tool=tool,
            effect=effect,
            status=status,
            run_id=run_id,
            source=source,
            before_tree_hash=before_tree_hash,
            after_tree_hash=after_tree_hash,
            created_at=float(self._now()),
            reason=reason,
            operation_id=operation_id,
            change_set=change_set,
        )
        state.commits.append(commit)
        state.head_tree_hash = after_tree_hash
        self._commits[commit.commit_id] = commit
        if source == "external":
            state.latest_session = None
        elif commit.changed:
            previous = state.latest_session
            session_change_set = (
                commit.change_set
                if previous is None
                else self.trees.diff(previous.before_tree_hash, commit.after_tree_hash)
            )
            state.latest_session = SessionDiff(
                document_id=document_id,
                run_id=run_id,
                before_tree_hash=(
                    commit.before_tree_hash if previous is None else previous.before_tree_hash
                ),
                after_tree_hash=commit.after_tree_hash,
                commit_ids=(
                    (commit.commit_id,)
                    if previous is None
                    else previous.commit_ids + (commit.commit_id,)
                ),
                change_set=session_change_set,
            )
        return commit

    def record_action(
        self,
        *,
        document_id: str,
        tool: str,
        effect: str,
        status: str,
        run_id: str,
        before_model: Optional[Mapping[str, Any]] = None,
        after_model: Optional[Mapping[str, Any]] = None,
        before_tree_hash: Optional[str] = None,
        after_tree_hash: Optional[str] = None,
        reason: Optional[str] = None,
        operation_id: Optional[str] = None,
        source: str = "agent",
        change_set: Optional[ChangeSet] = None,
    ) -> ActionCommit:
        if not document_id:
            raise ValueError("document_id is required")
        if before_model is not None:
            before_tree_hash = self.trees.store_model(before_model).tree_hash
        if after_model is not None:
            after_tree_hash = self.trees.store_model(after_model).tree_hash

        with self._lock:
            state = self._documents.setdefault(document_id, _DocumentState())
            if before_tree_hash is None:
                before_tree_hash = state.head_tree_hash
            if after_tree_hash is None:
                after_tree_hash = before_tree_hash
            if before_tree_hash is None or after_tree_hash is None:
                raise ValueError("the first document action requires a canonical model")
            if state.baseline_tree_hash is None:
                state.baseline_tree_hash = before_tree_hash
            if state.head_tree_hash is not None and state.head_tree_hash != before_tree_hash:
                self._append(
                    state=state,
                    document_id=document_id,
                    tool="external_working_tree_change",
                    effect="edit",
                    status="observed",
                    run_id="external",
                    source="external",
                    before_tree_hash=state.head_tree_hash,
                    after_tree_hash=before_tree_hash,
                    reason=None,
                    operation_id=None,
                )
            commit = self._append(
                state=state,
                document_id=document_id,
                tool=tool,
                effect=effect,
                status=status,
                run_id=run_id,
                source=source,
                before_tree_hash=before_tree_hash,
                after_tree_hash=after_tree_hash,
                reason=reason,
                operation_id=operation_id,
                change_set=change_set,
            )
        self._notify(document_id)
        return commit

    def list_commits(self, document_id: str, *, include_external: bool = False) -> tuple[ActionCommit, ...]:
        with self._lock:
            values = tuple(self._documents.get(document_id, _DocumentState()).commits)
        if not include_external:
            values = tuple(value for value in values if value.source == "agent")
        return values

    def get_commit(self, commit_id: str) -> Optional[ActionCommit]:
        with self._lock:
            return self._commits.get(commit_id)

    def head_tree_hash(self, document_id: str) -> Optional[str]:
        with self._lock:
            state = self._documents.get(document_id)
            return state.head_tree_hash if state is not None else None

    def latest_session_diff(self, document_id: str) -> Optional[SessionDiff]:
        with self._lock:
            state = self._documents.get(document_id)
            return state.latest_session if state is not None else None

    def reset_after_save(self, document_id: str) -> None:
        with self._lock:
            state = self._documents.pop(document_id, None)
            if state is not None:
                for commit in state.commits:
                    self._commits.pop(commit.commit_id, None)
            retained = {
                tree_hash
                for other in self._documents.values()
                for commit in other.commits
                for tree_hash in (commit.before_tree_hash, commit.after_tree_hash)
            }
            retained.update(
                tree_hash
                for other in self._documents.values()
                for tree_hash in (other.head_tree_hash, other.baseline_tree_hash)
                if tree_hash
            )
        self.trees.prune(retained)
        self._notify(document_id)


__all__ = ["ActionCommit", "ChangeHistory", "SessionDiff"]
