"""Pure presentation model for the passive Glyphs MCP Change Log."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from .change_history import ActionCommit, ChangeHistory


def _title(value: str) -> str:
    return " ".join(part.capitalize() for part in str(value or "change").split("_") if part)


def _value_text(value: Any, present: bool) -> str:
    if not present:
        return "∅"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        identity = value.get("id") or value.get("name")
        return "entity {} ({} fields)".format(identity or "value", len(value))
    if isinstance(value, (list, tuple)) and len(value) > 12:
        return "{} items".format(len(value))
    return str(value)


def _target_text(commit: ActionCommit) -> str:
    glyphs = commit.changed_glyphs
    count = len(commit.change_set.changes)
    change_text = "{} change{}".format(count, "" if count == 1 else "s")
    if glyphs:
        visible = ", ".join(glyphs[:3])
        if len(glyphs) > 3:
            visible += " +{}".format(len(glyphs) - 3)
        return "{} · {}".format(visible, change_text)
    if count:
        roots = []
        for change in commit.change_set.changes:
            if change.path[0] not in roots:
                roots.append(change.path[0])
        return "{} · {}".format(", ".join(roots[:3]), change_text)
    return "No document change"


def _human_path(path: tuple[str, ...]) -> str:
    values = list(path)
    if len(values) >= 3 and values[0] == "glyphs" and values[2] == "layers":
        values = [values[1]] + values[3:]
    return " / ".join(values)


@dataclass(frozen=True)
class ChangeLogRow:
    commit_id: str
    time: str
    status: str
    action: str
    targets: str


class ChangeLogModel:
    def __init__(self, history: ChangeHistory) -> None:
        self._history = history

    def rows(self, document_id: str) -> tuple[ChangeLogRow, ...]:
        result = []
        for commit in self._history.list_commits(document_id):
            try:
                time_text = datetime.fromtimestamp(commit.created_at).strftime("%H:%M:%S")
            except Exception:
                time_text = "—"
            result.append(
                ChangeLogRow(
                    commit_id=commit.commit_id,
                    time=time_text,
                    status=_title(commit.status),
                    action=_title(commit.tool),
                    targets=_target_text(commit),
                )
            )
        return tuple(result)

    def commit(self, commit_id: str) -> Optional[ActionCommit]:
        return self._history.get_commit(commit_id)

    def detail(self, commit_id: str, *, max_changes: int = 100) -> str:
        commit = self.commit(commit_id)
        if commit is None:
            return "Select a tool call to inspect its document changes."
        lines = [
            "{} · {}".format(_title(commit.tool), _title(commit.status)),
            "Operation: {}".format(commit.operation_id or commit.commit_id),
            "Changes: {}".format(len(commit.change_set.changes)),
        ]
        if commit.reason:
            lines.append("Reason: {}".format(commit.reason))
        for change in commit.change_set.changes[: max(0, int(max_changes))]:
            path = _human_path(change.path)
            before = _value_text(change.before, change.before_present)
            after = _value_text(change.after, change.after_present)
            lines.append("{}: {} → {}".format(path, before, after))
        remaining = len(commit.change_set.changes) - max(0, int(max_changes))
        if remaining > 0:
            lines.append("… {} more change(s)".format(remaining))
        return "\n".join(lines)


__all__ = ["ChangeLogModel", "ChangeLogRow"]
