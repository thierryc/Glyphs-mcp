"""Pure presentation and form state for the comparison-reference palette.

This module deliberately has no AppKit dependency.  The native Palette and
sheet adapters consume these immutable values, while Git and source decoding
remain in :mod:`comparison_reference`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlparse

from .comparison_reference import (
    ComparisonReferenceError,
    ComparisonReferenceSpec,
)


REFERENCE_KINDS = ("last_saved", "local_git", "github")
REFERENCE_LABELS = {
    "last_saved": "Last Saved",
    "local_git": "Local Git",
    "github": "Public GitHub",
}
SOURCE_ORIGINS = {
    "agent": "Agent",
    "sidebar": "Sidebar",
    "restored": "Restored from cache",
    "default": "Default",
}


@dataclass(frozen=True)
class ReferencePresentation:
    kind: str
    primary: str
    secondary: str
    tooltip: str
    accessibility_description: str
    resolved_commit: str | None
    show_refresh: bool
    show_copy: bool


@dataclass(frozen=True)
class ReferenceFormPresentation:
    kind: str
    sheet_height: float
    action_title: str
    action_enabled: bool
    show_repository: bool
    repository_label: str
    repository_placeholder: str
    show_revision: bool
    revision_placeholder: str
    show_advanced: bool
    show_font_path: bool
    explanation: str
    validation_message: str


def _text(value: Any) -> str:
    return str(value or "").strip()


def _repository_name(kind: str, repository: str) -> str:
    value = _text(repository).rstrip("/")
    if not value:
        return REFERENCE_LABELS.get(kind, "Reference")
    if kind == "github":
        parsed = urlparse(value)
        path = parsed.path.strip("/") if parsed.scheme else value.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2:
            return "/".join(parts[-2:])
    name = PurePosixPath(value.replace("\\", "/")).name
    return name[:-4] if name.endswith(".git") else (name or value)


def _format_timestamp(value: Any) -> str:
    if value is None:
        return ""
    try:
        stamp = datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return ""
    return stamp.strftime("%Y-%m-%d %H:%M UTC")


def _plain_tooltip(
    *,
    kind: str,
    primary: str,
    state: str,
    spec: Mapping[str, Any],
    resolved: Mapping[str, Any],
    origin: str,
    error_message: str,
) -> str:
    if kind == "last_saved":
        lines = ["Compares with the current document's last saved state."]
        if error_message:
            lines.append("Status: {}".format(error_message))
        return "\n".join(lines)

    repository = _text(
        resolved.get("repository")
        or spec.get("repositoryPath")
        or spec.get("repositoryUrl")
    )
    revision = _text(resolved.get("requestedRevision") or spec.get("revision"))
    commit = _text(resolved.get("resolvedCommit"))
    font_path = _text(resolved.get("fontPath") or spec.get("fontPath"))
    cache_state = _text(resolved.get("cacheState"))
    fetched_at = _format_timestamp(resolved.get("fetchedAt"))
    lines = ["Reference: {}".format(primary), "Status: {}".format(state)]
    if repository:
        lines.append("Repository: {}".format(repository))
    if revision:
        lines.append("Revision: {}".format(revision))
    if commit:
        lines.append("Commit: {}".format(commit))
    if font_path:
        lines.append("Font: {}".format(font_path))
    if cache_state:
        lines.append("Cache: {}".format(cache_state.replace("_", " ")))
    if fetched_at:
        lines.append("Fetched: {}".format(fetched_at))
    if origin:
        lines.append("Configured by: {}".format(SOURCE_ORIGINS.get(origin, origin)))
    if error_message:
        lines.append("Error: {}".format(error_message))
    return "\n".join(lines)


def reference_presentation(
    status: Mapping[str, Any],
    *,
    ui_error: str | None = None,
) -> ReferencePresentation:
    spec = dict(status.get("reference") or {"kind": "last_saved"})
    resolved = dict(status.get("resolved") or {})
    kind = _text(spec.get("kind")) or "last_saved"
    state = _text(status.get("state")) or "unavailable"
    commit = _text(resolved.get("resolvedCommit"))
    revision = _text(resolved.get("requestedRevision") or spec.get("revision"))
    font_path = _text(resolved.get("fontPath") or spec.get("fontPath"))
    repository = _text(
        resolved.get("repository")
        or spec.get("repositoryPath")
        or spec.get("repositoryUrl")
    )
    error = status.get("error")
    error_message = _text(ui_error)
    if not error_message and isinstance(error, Mapping):
        error_message = _text(error.get("message"))

    if kind == "last_saved":
        primary = "Last Saved"
    elif kind == "local_git":
        repository_name = _repository_name(kind, repository)
        primary = (
            "Local Git"
            if repository_name == REFERENCE_LABELS["local_git"]
            else "Local · {}".format(repository_name)
        )
    else:
        primary = _repository_name(kind, repository)

    if error_message:
        secondary = (
            "Cached · refresh failed"
            if bool(status.get("stale")) or state == "stale_cached"
            else "Couldn’t update reference"
        )
    elif state in {"resolving", "refreshing"}:
        secondary = "Refreshing…" if state == "refreshing" else "Resolving…"
    elif kind == "last_saved":
        secondary = ""
    else:
        identity = ""
        if revision and commit:
            identity = "{} @ {}".format(revision, commit[:8])
        elif commit:
            identity = commit[:8]
        elif revision:
            identity = revision
        if bool(status.get("stale")) or state == "stale_cached":
            identity = "Cached · {}".format(identity or "offline")
        secondary = identity
        if font_path:
            secondary = "{} · {}".format(identity, font_path) if identity else font_path

    tooltip = _plain_tooltip(
        kind=kind,
        primary=primary,
        state=state.replace("_", " "),
        spec=spec,
        resolved=resolved,
        origin=_text(status.get("origin")),
        error_message=error_message,
    )
    accessibility = primary if not secondary else "{}. {}".format(primary, secondary)
    return ReferencePresentation(
        kind=kind,
        primary=primary,
        secondary=secondary,
        tooltip=tooltip,
        accessibility_description=accessibility,
        resolved_commit=commit or None,
        show_refresh=kind in {"local_git", "github"} and state not in {"resolving", "refreshing"},
        show_copy=bool(commit),
    )


def unavailable_reference_presentation(message: str) -> ReferencePresentation:
    detail = _text(message) or "Reference unavailable"
    return ReferencePresentation(
        kind="unavailable",
        primary="Reference Unavailable",
        secondary=detail,
        tooltip=detail,
        accessibility_description="Reference unavailable. {}".format(detail),
        resolved_commit=None,
        show_refresh=False,
        show_copy=False,
    )


def initial_reference_drafts(spec: Mapping[str, Any] | None) -> dict[str, dict[str, str]]:
    current = dict(spec or {})
    kind = _text(current.get("kind")) or "last_saved"
    drafts = {
        "last_saved": {},
        "local_git": {"repository": "", "revision": "HEAD", "fontPath": ""},
        "github": {"repository": "", "revision": "", "fontPath": ""},
    }
    if kind in {"local_git", "github"}:
        drafts[kind] = {
            "repository": _text(
                current.get("repositoryPath") or current.get("repositoryUrl")
            ),
            "revision": _text(current.get("revision")) or (
                "HEAD" if kind == "local_git" else ""
            ),
            "fontPath": _text(current.get("fontPath")),
        }
    return drafts


def _draft_spec(kind: str, draft: Mapping[str, Any]) -> dict[str, str]:
    if kind == "last_saved":
        return {"kind": "last_saved"}
    result = {
        "kind": kind,
        "revision": _text(draft.get("revision")),
    }
    repository = _text(draft.get("repository"))
    if kind == "local_git":
        if repository:
            result["repositoryPath"] = repository
    else:
        result["repositoryUrl"] = repository
    font_path = _text(draft.get("fontPath"))
    if font_path:
        result["fontPath"] = font_path
    return result


def reference_form_presentation(
    kind: str,
    draft: Mapping[str, Any],
    *,
    advanced: bool,
) -> ReferenceFormPresentation:
    selected = kind if kind in REFERENCE_KINDS else "last_saved"
    validation_message = ""
    enabled = True
    try:
        ComparisonReferenceSpec.from_mapping(_draft_spec(selected, draft))
    except ComparisonReferenceError as error:
        enabled = False
        validation_message = error.message

    is_git = selected in {"local_git", "github"}
    return ReferenceFormPresentation(
        kind=selected,
        sheet_height=266.0 if is_git and advanced else (224.0 if is_git else 146.0),
        action_title="Use Last Saved" if selected == "last_saved" else "Set Reference",
        action_enabled=enabled,
        show_repository=is_git,
        repository_label="Repository",
        repository_placeholder=(
            "Repository containing this font (optional)"
            if selected == "local_git"
            else "owner/repository"
        ),
        show_revision=is_git,
        revision_placeholder=(
            "HEAD, branch, tag, or commit"
            if selected == "local_git"
            else "branch, tag, or commit"
        ),
        show_advanced=is_git,
        show_font_path=is_git and advanced,
        explanation=(
            "Compare with the current document's last saved state."
            if selected == "last_saved"
            else "Branches and tags remain pinned until you refresh them."
        ),
        validation_message=validation_message,
    )


def reference_spec_from_draft(kind: str, draft: Mapping[str, Any]) -> dict[str, Any]:
    value = _draft_spec(kind, draft)
    return ComparisonReferenceSpec.from_mapping(value).to_dict()


__all__ = [
    "REFERENCE_KINDS",
    "REFERENCE_LABELS",
    "ReferenceFormPresentation",
    "ReferencePresentation",
    "initial_reference_drafts",
    "reference_form_presentation",
    "reference_presentation",
    "reference_spec_from_draft",
    "unavailable_reference_presentation",
]
