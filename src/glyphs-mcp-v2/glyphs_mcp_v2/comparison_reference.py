"""Immutable Git-backed comparison references for the Glyphs Edit view.

This module deliberately has no AppKit dependency. Git, cache, preference, and
source decoding work happens on a dedicated background coordinator; Reporter
drawing callbacks only read already-published immutable snapshots.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import stat
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from threading import Event, RLock
from typing import Any, Callable, Mapping, MutableMapping, Sequence
from urllib.parse import urlparse

from .background_work import BackgroundWorkCoordinator, WorkContext
from .saved_source import (
    SavedSourceReader,
    SavedSourceRefresh,
    SavedSourceService,
    SavedSourceSnapshot,
    default_saved_source_service,
    normalize_source_path,
)


PREFERENCES_KEY = "com.thierryc.GlyphsMCP.v2.comparisonReferences"
PREFERENCES_SCHEMA_VERSION = 1
CACHE_SCHEMA_VERSION = 1
CACHE_SOFT_LIMIT_BYTES = 1024 * 1024 * 1024
MAXIMUM_SOURCE_BYTES = 256 * 1024 * 1024
MAXIMUM_PACKAGE_FILES = 20_000
DEFAULT_TIMEOUT_SECONDS = 60.0
MINIMUM_TIMEOUT_SECONDS = 5.0
MAXIMUM_TIMEOUT_SECONDS = 120.0
REFERENCE_CACHE_CAPACITY = 128
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"
REPORTER_CLASS_NAME = "GlyphsMCPChangeDiffReporter"


class ComparisonReferenceError(RuntimeError):
    """A stable, user-facing reference resolution failure."""

    def __init__(self, code: str, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.recoverable = bool(recoverable)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def native_font_identity(font: Any) -> str | None:
    """Return one process-local identity shared by host and Reporter adapters."""

    if font is None:
        return None
    try:
        return "native:{}".format(int(hash(font)))
    except Exception:
        return "native:{}".format(id(font))


def _normalized_live_path(value: Any) -> str | None:
    return normalize_source_path(value)


def _preference_identity(source_path: str | None) -> str | None:
    normalized = _normalized_live_path(source_path)
    return None if normalized is None else "font:" + _sha256_text(normalized)


def _normalize_font_path(value: Any) -> str | None:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return None
    if "\x00" in text or text.startswith("/"):
        raise ComparisonReferenceError(
            "invalid_font_path",
            "fontPath must be a repository-relative Glyphs source path.",
        )
    normalized = posixpath.normpath(text)
    parts = PurePosixPath(normalized).parts
    if normalized in {".", ".."} or ".." in parts:
        raise ComparisonReferenceError(
            "invalid_font_path",
            "fontPath must not escape the repository.",
        )
    suffix = PurePosixPath(normalized).suffix.lower()
    if suffix not in {".glyphs", ".glyphspackage"}:
        raise ComparisonReferenceError(
            "unsupported_source_format",
            "fontPath must end in .glyphs or .glyphspackage.",
        )
    return PurePosixPath(normalized).as_posix()


def canonical_github_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ComparisonReferenceError(
            "github_url_required", "A public GitHub repository URL is required."
        )
    if "://" not in text and text.count("/") == 1:
        text = "https://github.com/{}".format(text)
    parsed = urlparse(text)
    try:
        port = parsed.port
    except ValueError as error:
        raise ComparisonReferenceError(
            "unsupported_repository_url", "The GitHub repository URL is invalid."
        ) from error
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != "github.com"
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.params
    ):
        raise ComparisonReferenceError(
            "unsupported_repository_url",
            "Only credential-free public https://github.com repositories are supported.",
        )
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) != 2 or not all(parts):
        raise ComparisonReferenceError(
            "unsupported_repository_url",
            "The GitHub URL must identify one owner and repository.",
        )
    owner, repository = parts
    if (
        re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", owner) is None
        or re.fullmatch(r"[A-Za-z0-9._-]+", repository) is None
        or repository in {".", ".."}
    ):
        raise ComparisonReferenceError(
            "unsupported_repository_url", "The GitHub repository URL is invalid."
        )
    return "https://github.com/{}/{}.git".format(owner, repository)


@dataclass(frozen=True)
class ComparisonReferenceSpec:
    kind: str
    revision: str | None = None
    repository_path: str | None = None
    repository_url: str | None = None
    font_path: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ComparisonReferenceSpec":
        kind = str(value.get("kind") or "").strip().lower()
        if kind == "last_saved":
            return cls(kind=kind)
        if kind not in {"local_git", "github"}:
            raise ComparisonReferenceError(
                "unsupported_reference_kind",
                "comparisonReference.kind must be last_saved, local_git, or github.",
            )
        revision = str(value.get("revision") or "").strip()
        if not revision or revision.startswith("-") or "\x00" in revision:
            raise ComparisonReferenceError(
                "invalid_revision", "A non-empty Git branch, tag, or commit is required."
            )
        font_path = _normalize_font_path(value.get("fontPath"))
        if kind == "local_git":
            repository_path = str(value.get("repositoryPath") or "").strip() or None
            if repository_path is not None:
                repository_path = os.path.realpath(os.path.expanduser(repository_path))
            return cls(
                kind=kind,
                revision=revision,
                repository_path=repository_path,
                font_path=font_path,
            )
        return cls(
            kind=kind,
            revision=revision,
            repository_url=canonical_github_url(value.get("repositoryUrl")),
            font_path=font_path,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"kind": self.kind}
        if self.revision is not None:
            data["revision"] = self.revision
        if self.repository_path is not None:
            data["repositoryPath"] = self.repository_path
        if self.repository_url is not None:
            data["repositoryUrl"] = self.repository_url
        if self.font_path is not None:
            data["fontPath"] = self.font_path
        return data


@dataclass(frozen=True)
class ResolvedReference:
    kind: str
    repository: str | None
    requested_revision: str | None
    resolved_commit: str | None
    font_path: str | None
    cache_state: str
    fetched_at: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "repository": self.repository,
            "requestedRevision": self.requested_revision,
            "resolvedCommit": self.resolved_commit,
            "fontPath": self.font_path,
            "cacheState": self.cache_state,
            "fetchedAt": self.fetched_at,
        }


@dataclass(frozen=True)
class ReferenceSnapshot:
    resolved: ResolvedReference
    source: SavedSourceSnapshot

    @property
    def source_fingerprint(self) -> str:
        return self.source.source_fingerprint

    @property
    def model(self):
        return self.source.model


@dataclass(frozen=True)
class ReferenceStatus:
    state: str
    spec: ComparisonReferenceSpec
    resolved: ResolvedReference | None = None
    source_fingerprint: str | None = None
    stale: bool = False
    error_code: str | None = None
    error_message: str | None = None
    origin: str = "default"

    @property
    def ready(self) -> bool:
        return self.state in {"ready", "stale_cached"}

    @property
    def offline_status(self) -> str:
        """Describe offline usability without performing a network probe."""

        if self.spec.kind != "github":
            return "not_applicable"
        if self.source_fingerprint and self.ready:
            return "cache_ready"
        if self.state == "cache_miss":
            return "cache_missing"
        if self.state in {"resolving", "refreshing"}:
            return "checking"
        if self.error_code in {"github_fetch_failed", "reference_timeout", "offline"}:
            return "network_unavailable"
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "ready": self.ready,
            "reference": self.spec.to_dict(),
            "resolved": self.resolved.to_dict() if self.resolved is not None else None,
            "sourceFingerprint": self.source_fingerprint,
            "stale": self.stale,
            "offlineStatus": self.offline_status,
            "error": (
                {"code": self.error_code, "message": self.error_message}
                if self.error_code
                else None
            ),
            "origin": self.origin,
        }


@dataclass(frozen=True)
class ReferenceUpdate:
    session_key: str
    document_id: str | None
    source_path: str | None
    status: ReferenceStatus


@dataclass
class _ReferenceSession:
    session_key: str
    document_id: str | None
    source_path: str | None
    spec: ComparisonReferenceSpec = field(
        default_factory=lambda: ComparisonReferenceSpec(kind="last_saved")
    )
    resolved: ResolvedReference | None = None
    snapshot: ReferenceSnapshot | None = None
    state: str = "ready"
    stale: bool = False
    error_code: str | None = None
    error_message: str | None = None
    origin: str = "default"
    restore_requested: bool = False
    pending_new_reference: bool = False
    pending_spec: ComparisonReferenceSpec | None = None

    def status(self) -> ReferenceStatus:
        hide_previous = self.pending_new_reference
        return ReferenceStatus(
            state=self.state,
            spec=self.pending_spec or self.spec,
            resolved=None if hide_previous else self.resolved,
            source_fingerprint=(
                self.snapshot.source_fingerprint
                if self.snapshot is not None and not hide_previous
                else None
            ),
            stale=self.stale,
            error_code=self.error_code,
            error_message=self.error_message,
            origin=self.origin,
        )


class ComparisonReferencePreferences:
    """Versioned local preferences; no state is written into a font file."""

    def __init__(self, values: MutableMapping[str, Any] | None = None) -> None:
        self._values = values if values is not None else {}
        self._lock = RLock()

    def _document(self) -> dict[str, Any]:
        raw = self._values.get(PREFERENCES_KEY)
        if not raw:
            return {"schemaVersion": PREFERENCES_SCHEMA_VERSION, "entries": {}}
        try:
            value = json.loads(str(raw))
        except Exception:
            return {"schemaVersion": PREFERENCES_SCHEMA_VERSION, "entries": {}}
        if (
            not isinstance(value, dict)
            or value.get("schemaVersion") != PREFERENCES_SCHEMA_VERSION
            or not isinstance(value.get("entries"), dict)
        ):
            return {"schemaVersion": PREFERENCES_SCHEMA_VERSION, "entries": {}}
        return value

    def load(self, source_path: str | None) -> Mapping[str, Any] | None:
        identity = _preference_identity(source_path)
        if identity is None:
            return None
        with self._lock:
            value = self._document()["entries"].get(identity)
            return dict(value) if isinstance(value, dict) else None

    def save(
        self,
        source_path: str | None,
        spec: ComparisonReferenceSpec,
        resolved: ResolvedReference | None,
    ) -> None:
        identity = _preference_identity(source_path)
        if identity is None:
            return
        with self._lock:
            document = self._document()
            entries = dict(document["entries"])
            if spec.kind == "last_saved":
                entries.pop(identity, None)
            else:
                entries[identity] = {
                    "spec": spec.to_dict(),
                    "resolved": resolved.to_dict() if resolved is not None else None,
                    "updatedAt": time.time(),
                }
            if len(entries) > 256:
                ordered = sorted(
                    entries.items(),
                    key=lambda item: float(item[1].get("updatedAt") or 0.0),
                )
                entries = dict(ordered[-256:])
            self._values[PREFERENCES_KEY] = json.dumps(
                {"schemaVersion": PREFERENCES_SCHEMA_VERSION, "entries": entries},
                sort_keys=True,
                separators=(",", ":"),
            )

    def migrate(self, before_path: str | None, after_path: str | None) -> None:
        before = _preference_identity(before_path)
        after = _preference_identity(after_path)
        if before is None or after is None or before == after:
            return
        with self._lock:
            document = self._document()
            entries = dict(document["entries"])
            value = entries.pop(before, None)
            if value is not None:
                entries[after] = value
                self._values[PREFERENCES_KEY] = json.dumps(
                    {"schemaVersion": PREFERENCES_SCHEMA_VERSION, "entries": entries},
                    sort_keys=True,
                    separators=(",", ":"),
                )


class GitReferenceCache:
    """Persistent bare GitHub cache with bounded LRU eviction metadata."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        clock: Callable[[], float] = time.time,
        soft_limit_bytes: int = CACHE_SOFT_LIMIT_BYTES,
    ) -> None:
        self.root = root or (
            Path.home()
            / "Library"
            / "Caches"
            / "com.thierryc.GlyphsMCP"
            / "v2"
            / "comparison-references"
        )
        self.repositories = self.root / "repositories"
        self.index_path = self.root / "index.json"
        self.clock = clock
        self.soft_limit_bytes = max(1, int(soft_limit_bytes))
        self._lock = RLock()

    def repository_path(self, canonical_url: str) -> Path:
        return self.repositories / ("{}.git".format(_sha256_text(canonical_url)))

    def _load_index(self) -> dict[str, Any]:
        try:
            value = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {"schemaVersion": CACHE_SCHEMA_VERSION, "repositories": {}}
        if (
            not isinstance(value, dict)
            or value.get("schemaVersion") != CACHE_SCHEMA_VERSION
            or not isinstance(value.get("repositories"), dict)
        ):
            return {"schemaVersion": CACHE_SCHEMA_VERSION, "repositories": {}}
        return value

    def _write_index(self, value: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.index_path.with_name("index.json.tmp")
        temporary.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, self.index_path)

    @staticmethod
    def _directory_size(path: Path) -> int:
        total = 0
        try:
            for candidate in path.rglob("*"):
                if candidate.is_file() and not candidate.is_symlink():
                    total += candidate.stat().st_size
        except OSError:
            return total
        return total

    def touch(
        self,
        canonical_url: str,
        *,
        requested_revision: str | None,
        resolved_commit: str | None,
    ) -> None:
        identity = _sha256_text(canonical_url)
        path = self.repository_path(canonical_url)
        with self._lock:
            index = self._load_index()
            repositories = dict(index["repositories"])
            previous = repositories.get(identity)
            resolved_refs = (
                dict(previous.get("resolvedRefs") or {})
                if isinstance(previous, Mapping)
                else {}
            )
            if requested_revision and resolved_commit:
                resolved_refs[str(requested_revision)] = str(resolved_commit)
            repositories[identity] = {
                "url": canonical_url,
                "path": path.name,
                "lastAccess": self.clock(),
                "size": self._directory_size(path),
                "resolvedCommit": resolved_commit,
                "resolvedRefs": resolved_refs,
                "validationState": "valid",
            }
            self._write_index(
                {"schemaVersion": CACHE_SCHEMA_VERSION, "repositories": repositories}
            )

    def quarantine(self, canonical_url: str) -> Path | None:
        """Move an unreadable bare cache aside without deleting evidence."""

        identity = _sha256_text(canonical_url)
        source = self.repository_path(canonical_url)
        with self._lock:
            if not source.exists():
                return None
            destination_root = self.root / "quarantine"
            destination_root.mkdir(parents=True, exist_ok=True)
            timestamp = int(self.clock())
            destination = destination_root / "{}-{}-corrupt.git".format(
                identity, timestamp
            )
            suffix = 1
            while destination.exists():
                destination = destination_root / "{}-{}-{}-corrupt.git".format(
                    identity, timestamp, suffix
                )
                suffix += 1
            os.replace(source, destination)
            index = self._load_index()
            repositories = dict(index["repositories"])
            repositories.pop(identity, None)
            self._write_index(
                {"schemaVersion": CACHE_SCHEMA_VERSION, "repositories": repositories}
            )
            return destination

    def evict(self, *, protected_urls: Sequence[str] = ()) -> tuple[str, ...]:
        protected = {_sha256_text(value) for value in protected_urls}
        removed: list[str] = []
        with self._lock:
            index = self._load_index()
            repositories = dict(index["repositories"])
            total = sum(int(value.get("size") or 0) for value in repositories.values())
            ordered = sorted(
                repositories.items(),
                key=lambda item: float(item[1].get("lastAccess") or 0.0),
            )
            for identity, record in ordered:
                if total <= self.soft_limit_bytes or identity in protected:
                    continue
                path = self.repositories / str(record.get("path") or "")
                try:
                    if path.is_dir() and path.parent == self.repositories:
                        import shutil

                        shutil.rmtree(path)
                except OSError:
                    continue
                total -= int(record.get("size") or 0)
                repositories.pop(identity, None)
                removed.append(identity)
            self._write_index(
                {"schemaVersion": CACHE_SCHEMA_VERSION, "repositories": repositories}
            )
        return tuple(removed)


@dataclass(frozen=True)
class _ResolvedSnapshot:
    resolved: ResolvedReference
    snapshot: SavedSourceSnapshot


class DulwichGitReferenceResolver:
    """Read local Git objects or fetch one public GitHub ref into a bare cache."""

    def __init__(
        self,
        *,
        cache: GitReferenceCache | None = None,
        reader: SavedSourceReader | None = None,
        clock: Callable[[], float] = time.time,
        maximum_source_bytes: int = MAXIMUM_SOURCE_BYTES,
        maximum_package_files: int = MAXIMUM_PACKAGE_FILES,
        http_client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.cache = cache or GitReferenceCache(clock=clock)
        self.reader = reader or SavedSourceReader()
        self.clock = clock
        self.maximum_source_bytes = max(1, int(maximum_source_bytes))
        self.maximum_package_files = max(1, int(maximum_package_files))
        self.http_client_factory = http_client_factory
        self._decoded: "OrderedDict[tuple[str, str, str], _ResolvedSnapshot]" = (
            OrderedDict()
        )
        self._decoded_lock = RLock()

    @staticmethod
    def _dulwich():
        try:
            from dulwich.client import Urllib3HttpGitClient
            from dulwich.objects import Blob, Commit, Tag
            from dulwich.repo import Repo
        except ImportError as error:
            raise ComparisonReferenceError(
                "git_runtime_unavailable",
                "The bundled Dulwich Git runtime is unavailable.",
                recoverable=False,
            ) from error
        return Repo, Urllib3HttpGitClient, Blob, Commit, Tag

    @staticmethod
    def _peel_commit(repo, sha: bytes, commit_type, tag_type) -> bytes:
        seen: set[bytes] = set()
        current = sha
        while current not in seen:
            seen.add(current)
            try:
                value = repo[current]
            except Exception as error:
                raise ComparisonReferenceError(
                    "revision_not_found", "The requested Git object is unavailable."
                ) from error
            if isinstance(value, commit_type):
                return current
            if isinstance(value, tag_type):
                current = value.object[1]
                continue
            break
        raise ComparisonReferenceError(
            "revision_not_commit", "The requested Git revision does not resolve to a commit."
        )

    def _resolve_local_revision(self, repo, revision: str) -> bytes:
        _Repo, _Client, _Blob, Commit, Tag = self._dulwich()
        encoded = revision.encode("utf-8")
        if 7 <= len(revision) <= 64 and all(
            character in "0123456789abcdefABCDEF" for character in revision
        ):
            matches = tuple(repo.object_store.iter_prefix(encoded.lower()))
            if len(matches) > 1:
                raise ComparisonReferenceError(
                    "revision_ambiguous", "The abbreviated commit identifies multiple objects."
                )
            if len(matches) == 1:
                return self._peel_commit(repo, matches[0], Commit, Tag)
        refs = repo.refs.as_dict()
        names = (
            encoded,
            b"refs/heads/" + encoded,
            b"refs/tags/" + encoded,
            b"refs/remotes/origin/" + encoded,
        )
        commits: dict[bytes, bytes] = {}
        for name in names:
            sha = refs.get(name)
            if sha is None:
                continue
            commits[name] = self._peel_commit(repo, sha, Commit, Tag)
        unique = set(commits.values())
        if not unique:
            raise ComparisonReferenceError(
                "revision_not_found", "The branch, tag, or commit was not found."
            )
        if len(unique) > 1:
            raise ComparisonReferenceError(
                "revision_ambiguous",
                "The revision name resolves to different branch or tag commits.",
            )
        return next(iter(unique))

    def _resolve_remote_revision(self, refs: Mapping[bytes, bytes], revision: str) -> bytes:
        encoded = revision.encode("utf-8")
        if len(revision) in {40, 64} and all(
            character in "0123456789abcdefABCDEF" for character in revision
        ):
            return encoded.lower()
        names = (
            encoded,
            b"refs/heads/" + encoded,
            b"refs/tags/" + encoded + b"^{}",
            b"refs/tags/" + encoded,
        )
        values = {refs[name] for name in names if name in refs}
        if not values:
            raise ComparisonReferenceError(
                "revision_not_found", "The GitHub branch, tag, or commit was not found."
            )
        if len(values) > 1:
            tag_value = refs.get(b"refs/tags/" + encoded + b"^{}")
            plain_tag = refs.get(b"refs/tags/" + encoded)
            branch = refs.get(b"refs/heads/" + encoded)
            if tag_value is not None and branch is None:
                return tag_value
            if plain_tag is not None and branch is None and tag_value is None:
                return plain_tag
            raise ComparisonReferenceError(
                "revision_ambiguous",
                "The revision name identifies different GitHub branch or tag commits.",
            )
        return next(iter(values))

    @staticmethod
    def _tree_path(value: bytes) -> str:
        try:
            path = value.decode("utf-8")
        except UnicodeError as error:
            raise ComparisonReferenceError(
                "invalid_git_tree", "The Git tree contains a non-UTF-8 path."
            ) from error
        parts = PurePosixPath(path).parts
        if (
            not path
            or "\x00" in path
            or path.startswith("/")
            or ".." in parts
            or posixpath.normpath(path) != path
        ):
            raise ComparisonReferenceError(
                "invalid_git_tree", "The Git tree contains an unsafe path."
            )
        return path

    @staticmethod
    def _supported_sources(repo, commit) -> tuple[str, ...]:
        from dulwich.object_store import iter_tree_contents

        sources: set[str] = set()
        for entry in iter_tree_contents(repo.object_store, commit.tree):
            path = DulwichGitReferenceResolver._tree_path(entry.path)
            components = PurePosixPath(path).parts
            package = next(
                (
                    PurePosixPath(*components[: index + 1]).as_posix()
                    for index, component in enumerate(components)
                    if component.lower().endswith(".glyphspackage")
                ),
                None,
            )
            if package is not None:
                sources.add(package)
            elif path.lower().endswith(".glyphs"):
                sources.add(path)
        return tuple(sorted(sources))

    def _select_font_path(
        self,
        repo,
        commit,
        *,
        explicit: str | None,
        live_source_path: str | None,
        local_repository_root: str | None,
    ) -> str:
        sources = self._supported_sources(repo, commit)
        if explicit is not None:
            if explicit not in sources:
                raise ComparisonReferenceError(
                    "font_source_missing",
                    "The requested Glyphs source path does not exist at this commit.",
                )
            return explicit
        normalized_live = _normalized_live_path(live_source_path)
        if normalized_live and local_repository_root:
            try:
                relative = Path(normalized_live).resolve().relative_to(
                    Path(local_repository_root).resolve()
                ).as_posix()
                if relative in sources:
                    return relative
            except ValueError:
                pass
        if normalized_live:
            basename = Path(normalized_live).name
            matches = tuple(path for path in sources if PurePosixPath(path).name == basename)
            if len(matches) == 1:
                return matches[0]
        if len(sources) == 1:
            return sources[0]
        if not sources:
            raise ComparisonReferenceError(
                "font_source_missing", "No .glyphs or .glyphspackage source exists at this commit."
            )
        raise ComparisonReferenceError(
            "font_path_required",
            "The repository contains multiple Glyphs sources; provide fontPath.",
        )

    def _source_files(self, repo, commit, font_path: str) -> tuple[str, Mapping[str, bytes]]:
        from dulwich.object_store import iter_tree_contents

        _Repo, _Client, Blob, _Commit, _Tag = self._dulwich()
        entries = tuple(iter_tree_contents(repo.object_store, commit.tree))
        suffix = PurePosixPath(font_path).suffix.lower()
        files: dict[str, bytes] = {}
        total = 0
        prefix = font_path.rstrip("/") + "/"
        for entry in entries:
            path = self._tree_path(entry.path)
            selected = path == font_path if suffix == ".glyphs" else path.startswith(prefix)
            if not selected:
                continue
            mode = int(entry.mode or 0)
            if mode in {0o120000, 0o160000} or not stat.S_ISREG(mode):
                raise ComparisonReferenceError(
                    "unsupported_git_entry",
                    "Symlinks and submodules are not supported inside a comparison source.",
                )
            value = repo.object_store[entry.sha]
            if not isinstance(value, Blob):
                raise ComparisonReferenceError(
                    "invalid_git_tree", "The selected source contains a non-blob entry."
                )
            data = bytes(value.data)
            if data.startswith(LFS_POINTER_PREFIX):
                raise ComparisonReferenceError(
                    "git_lfs_unsupported",
                    "The selected source uses Git LFS, which is not supported.",
                )
            relative = "" if suffix == ".glyphs" else path[len(prefix) :]
            if not relative and suffix != ".glyphs":
                continue
            total += len(data)
            if total > self.maximum_source_bytes:
                raise ComparisonReferenceError(
                    "source_too_large", "The selected source exceeds the 256 MiB limit."
                )
            files[relative] = data
            if len(files) > self.maximum_package_files:
                raise ComparisonReferenceError(
                    "source_file_limit",
                    "The selected package exceeds the 20,000-file limit.",
                )
        if suffix == ".glyphs" and set(files) != {""}:
            raise ComparisonReferenceError(
                "font_source_missing", "The requested .glyphs blob is unavailable."
            )
        if suffix == ".glyphspackage" and not files:
            raise ComparisonReferenceError(
                "font_source_missing", "The requested .glyphspackage tree is unavailable."
            )
        return ("glyphs" if suffix == ".glyphs" else "glyphspackage"), files

    def _decode(
        self,
        repo,
        commit_sha: bytes,
        *,
        spec: ComparisonReferenceSpec,
        repository: str,
        cache_state: str,
        fetched_at: float | None,
        live_source_path: str | None,
        local_repository_root: str | None,
    ) -> _ResolvedSnapshot:
        _Repo, _Client, _Blob, Commit, Tag = self._dulwich()
        commit_sha = self._peel_commit(repo, commit_sha, Commit, Tag)
        commit = repo[commit_sha]
        font_path = self._select_font_path(
            repo,
            commit,
            explicit=spec.font_path,
            live_source_path=live_source_path,
            local_repository_root=local_repository_root,
        )
        kind, files = self._source_files(repo, commit, font_path)
        virtual_path = "/git-reference/{}".format(PurePosixPath(font_path).name)
        commit_text = commit_sha.decode("ascii")
        cache_key = (repository, commit_text, font_path)
        with self._decoded_lock:
            cached = self._decoded.get(cache_key)
            if cached is not None:
                self._decoded.move_to_end(cache_key)
                resolved = ResolvedReference(
                    kind=spec.kind,
                    repository=repository,
                    requested_revision=spec.revision,
                    resolved_commit=commit_text,
                    font_path=font_path,
                    cache_state=cache_state,
                    fetched_at=fetched_at,
                )
                return _ResolvedSnapshot(resolved=resolved, snapshot=cached.snapshot)
        decoded = self.reader.decode_files(
            path=virtual_path,
            kind=kind,
            files=files,
            signature=("git", repository, commit_text, font_path),
        )
        if decoded.snapshot is None:
            raise ComparisonReferenceError(
                decoded.error or "source_decode_failed",
                "The referenced Glyphs source could not be decoded.",
            )
        resolved = ResolvedReference(
            kind=spec.kind,
            repository=repository,
            requested_revision=spec.revision,
            resolved_commit=commit_text,
            font_path=font_path,
            cache_state=cache_state,
            fetched_at=fetched_at,
        )
        result = _ResolvedSnapshot(resolved=resolved, snapshot=decoded.snapshot)
        with self._decoded_lock:
            self._decoded[cache_key] = result
            self._decoded.move_to_end(cache_key)
            while len(self._decoded) > REFERENCE_CACHE_CAPACITY:
                self._decoded.popitem(last=False)
        return result

    def resolve(
        self,
        spec: ComparisonReferenceSpec,
        *,
        live_source_path: str | None,
        cached_only: bool = False,
        resolved_hint: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        cancelled: Callable[[], bool] | None = None,
        protected_urls: Sequence[str] = (),
    ) -> _ResolvedSnapshot:
        if spec.kind == "last_saved":
            raise ComparisonReferenceError(
                "invalid_reference_operation", "Last Saved does not require Git resolution."
            )
        Repo, HttpClient, _Blob, Commit, Tag = self._dulwich()
        if cancelled is not None and cancelled():
            raise ComparisonReferenceError("cancelled", "Reference resolution was cancelled.")
        if spec.kind == "local_git":
            start = spec.repository_path or live_source_path
            if not start:
                raise ComparisonReferenceError(
                    "repository_path_required",
                    "repositoryPath is required when the font is not inside a local repository.",
                )
            try:
                repo = Repo.discover(start)
            except Exception as error:
                raise ComparisonReferenceError(
                    "repository_unavailable", "The local Git repository could not be opened."
                ) from error
            try:
                commit_sha = (
                    self._resolve_local_revision(repo, resolved_hint)
                    if cached_only and resolved_hint
                    else self._resolve_local_revision(repo, str(spec.revision))
                )
                return self._decode(
                    repo,
                    commit_sha,
                    spec=spec,
                    repository=os.path.realpath(str(repo.path)),
                    cache_state="local",
                    fetched_at=None,
                    live_source_path=live_source_path,
                    local_repository_root=str(repo.path),
                )
            finally:
                repo.close()

        canonical_url = canonical_github_url(spec.repository_url)
        cache_path = self.cache.repository_path(canonical_url)
        cache_existed = cache_path.is_dir()
        if not cache_existed:
            if cached_only:
                raise ComparisonReferenceError(
                    "cache_miss", "The persisted GitHub reference is not available offline."
                )
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            repo = Repo.init_bare(cache_path, mkdir=True)
        else:
            try:
                repo = Repo(cache_path)
            except Exception as error:
                self.cache.quarantine(canonical_url)
                if cached_only:
                    raise ComparisonReferenceError(
                        "cache_corrupt", "The cached GitHub repository is unreadable."
                    ) from error
                repo = Repo.init_bare(cache_path, mkdir=True)
                cache_existed = False
        fetched_at: float | None = None
        try:
            commit_sha: bytes | None = None
            if resolved_hint:
                try:
                    commit_sha = self._peel_commit(
                        repo, resolved_hint.encode("ascii"), Commit, Tag
                    )
                except (ComparisonReferenceError, UnicodeError):
                    commit_sha = None
            if commit_sha is None and cached_only:
                raise ComparisonReferenceError(
                    "cache_miss", "The pinned commit is missing from the local cache."
                )
            if commit_sha is None:
                if cancelled is not None and cancelled():
                    raise ComparisonReferenceError(
                        "cancelled", "Reference resolution was cancelled."
                    )
                client_factory = self.http_client_factory or HttpClient
                client = client_factory(
                    canonical_url,
                    timeout=max(MINIMUM_TIMEOUT_SECONDS, min(30.0, timeout_seconds)),
                    username=None,
                    password=None,
                    auth_callback=lambda *_args: None,
                    quiet=True,
                    include_tags=True,
                )
                try:
                    remote_result = client.get_refs(b"")
                    remote_refs = dict(getattr(remote_result, "refs", remote_result))
                    wanted = self._resolve_remote_revision(
                        remote_refs, str(spec.revision)
                    )

                    def determine_wants(_refs, depth=None):
                        del depth
                        return [] if wanted in repo.object_store else [wanted]

                    client.fetch(
                        b"",
                        repo,
                        determine_wants=determine_wants,
                        depth=1,
                    )
                    commit_sha = self._peel_commit(repo, wanted, Commit, Tag)
                    repo.refs[
                        b"refs/glyphs-mcp/pins/" + commit_sha
                    ] = commit_sha
                    fetched_at = self.clock()
                except ComparisonReferenceError:
                    raise
                except Exception as error:
                    raise ComparisonReferenceError(
                        "github_fetch_failed",
                        "The public GitHub reference could not be fetched.",
                    ) from error
                finally:
                    client.close()
            result = self._decode(
                repo,
                commit_sha,
                spec=spec,
                repository=canonical_url,
                cache_state="warm" if cache_existed else "cold",
                fetched_at=fetched_at,
                live_source_path=live_source_path,
                local_repository_root=None,
            )
            self.cache.touch(
                canonical_url,
                requested_revision=spec.revision,
                resolved_commit=result.resolved.resolved_commit,
            )
            self.cache.evict(
                protected_urls=tuple(protected_urls) + (canonical_url,)
            )
            return result
        finally:
            repo.close()


class ComparisonReferenceService:
    """Per-document reference state with latest-wins background resolution."""

    def __init__(
        self,
        *,
        saved_sources: SavedSourceService | None = None,
        resolver: DulwichGitReferenceResolver | None = None,
        preferences: ComparisonReferencePreferences | None = None,
        coordinator: BackgroundWorkCoordinator | None = None,
    ) -> None:
        self.saved_sources = saved_sources or default_saved_source_service()
        self.resolver = resolver or DulwichGitReferenceResolver()
        self.preferences = preferences or ComparisonReferencePreferences(
            _default_preferences_values()
        )
        self.coordinator = coordinator or BackgroundWorkCoordinator(
            capacity=8, thread_name="glyphs-mcp-git-reference"
        )
        self._lock = RLock()
        self._sessions: dict[str, _ReferenceSession] = {}
        self._documents: dict[str, str] = {}
        self._sources: dict[str, str] = {}
        self._listeners: tuple[Callable[[ReferenceUpdate], None], ...] = ()
        self._diagnostics = {
            "referenceResolutions": 0,
            "fetches": 0,
            "cacheHits": 0,
            "timeouts": 0,
            "cancellations": 0,
            "publications": 0,
        }
        self._unsubscribe_saved_sources = self.saved_sources.subscribe(
            self._saved_source_updated
        )

    def _saved_source_updated(self, result: SavedSourceRefresh) -> None:
        with self._lock:
            sessions = tuple(
                session
                for session in self._sessions.values()
                if session.spec.kind == "last_saved"
                and session.source_path == result.path
            )
        for session in sessions:
            self._notify(session)

    def subscribe(
        self, listener: Callable[[ReferenceUpdate], None]
    ) -> Callable[[], None]:
        with self._lock:
            self._listeners = self._listeners + (listener,)

        def unsubscribe() -> None:
            with self._lock:
                self._listeners = tuple(
                    value for value in self._listeners if value is not listener
                )

        return unsubscribe

    def notify_sessions(self) -> None:
        """Refresh passive UI consumers without changing reference state."""

        with self._lock:
            sessions = tuple(self._sessions.values())
        for session in sessions:
            self._notify(session)

    def _notify(self, session: _ReferenceSession) -> None:
        update = ReferenceUpdate(
            session_key=session.session_key,
            document_id=session.document_id,
            source_path=session.source_path,
            status=self._status(session),
        )
        with self._lock:
            listeners = self._listeners
        for listener in listeners:
            try:
                listener(update)
            except Exception:
                pass

    def _record_resolution(self, result: _ResolvedSnapshot) -> None:
        with self._lock:
            self._diagnostics["fetches"] += int(
                result.resolved.fetched_at is not None
            )
            self._diagnostics["cacheHits"] += int(
                result.resolved.cache_state == "warm"
            )
            self._diagnostics["publications"] += 1

    def _diagnostics_snapshot(self) -> Mapping[str, int]:
        with self._lock:
            return dict(self._diagnostics)

    def _status(self, session: _ReferenceSession) -> ReferenceStatus:
        if session.spec.kind != "last_saved":
            return session.status()
        snapshot = (
            self.saved_sources.store.snapshot(session.source_path)
            if session.source_path
            else None
        )
        return ReferenceStatus(
            state="ready" if snapshot is not None else "unavailable",
            spec=session.spec,
            resolved=ResolvedReference(
                kind="last_saved",
                repository=None,
                requested_revision=None,
                resolved_commit=None,
                font_path=session.source_path,
                cache_state="not_applicable",
                fetched_at=None,
            ),
            source_fingerprint=(
                snapshot.source_fingerprint if snapshot is not None else None
            ),
            error_code=(
                session.error_code
                or (None if snapshot is not None else "saved_source_unavailable")
            ),
            error_message=(
                session.error_message
                or (
                    None
                    if snapshot is not None
                    else "Save the document once before comparing with Last Saved."
                )
            ),
            origin=session.origin,
        )

    def _load_persisted(self, session: _ReferenceSession) -> None:
        persisted = self.preferences.load(session.source_path)
        if not isinstance(persisted, Mapping):
            return
        spec_value = persisted.get("spec")
        if not isinstance(spec_value, Mapping):
            return
        try:
            spec = ComparisonReferenceSpec.from_mapping(spec_value)
        except ComparisonReferenceError:
            return
        if spec.kind == "last_saved":
            return
        resolved_value = persisted.get("resolved")
        resolved = None
        if isinstance(resolved_value, Mapping):
            resolved = ResolvedReference(
                kind=spec.kind,
                repository=str(resolved_value.get("repository") or "") or None,
                requested_revision=str(
                    resolved_value.get("requestedRevision") or spec.revision or ""
                )
                or None,
                resolved_commit=str(resolved_value.get("resolvedCommit") or "") or None,
                font_path=str(resolved_value.get("fontPath") or "") or spec.font_path,
                cache_state="cache_miss",
                fetched_at=(
                    float(resolved_value["fetchedAt"])
                    if resolved_value.get("fetchedAt") is not None
                    else None
                ),
            )
        session.spec = spec
        session.resolved = resolved
        session.state = "cache_miss"
        session.origin = "restored"

    def bind_document(
        self,
        document_id: str,
        *,
        source_path: str | None,
        native_identity: str | None = None,
    ) -> str:
        normalized = _normalized_live_path(source_path)
        session_key = native_identity or (
            "path:" + normalized if normalized else "document:" + str(document_id)
        )
        with self._lock:
            existing_key = self._documents.get(str(document_id))
            session = self._sessions.get(existing_key or session_key)
            if session is None:
                session = _ReferenceSession(
                    session_key=session_key,
                    document_id=str(document_id),
                    source_path=normalized,
                )
                self._load_persisted(session)
                self._sessions[session_key] = session
            elif session.session_key != session_key:
                self._sessions.pop(session.session_key, None)
                session.session_key = session_key
                self._sessions[session_key] = session
            previous_path = session.source_path
            session.document_id = str(document_id)
            session.source_path = normalized
            self._documents[str(document_id)] = session_key
            if previous_path and self._sources.get(previous_path) == session_key:
                self._sources.pop(previous_path, None)
            if normalized:
                self._sources[normalized] = session_key
        if previous_path != normalized:
            self.preferences.migrate(previous_path, normalized)
            if previous_path is None and normalized and session.spec.kind != "last_saved":
                self.preferences.save(normalized, session.spec, session.resolved)
        self._request_restore(session)
        return session_key

    def ensure_source(
        self, source_path: str | None, *, native_identity: str | None = None
    ) -> str | None:
        normalized = _normalized_live_path(source_path)
        if normalized is None and native_identity is None:
            return None
        with self._lock:
            session_key = native_identity or self._sources.get(normalized) or (
                "path:" + str(normalized)
            )
            session = self._sessions.get(session_key)
            if session is None:
                session = _ReferenceSession(
                    session_key=session_key,
                    document_id=None,
                    source_path=normalized,
                )
                self._load_persisted(session)
                self._sessions[session_key] = session
            if normalized:
                self._sources[normalized] = session_key
        self._request_restore(session)
        return session_key

    def _request_restore(self, session: _ReferenceSession) -> None:
        with self._lock:
            if (
                session.spec.kind == "last_saved"
                or session.snapshot is not None
                or session.restore_requested
                or session.resolved is None
                or not session.resolved.resolved_commit
            ):
                return
            session.restore_requested = True
            spec = session.spec
            resolved_commit = session.resolved.resolved_commit
            source_path = session.source_path
            session_key = session.session_key

        def restore(context: WorkContext):
            with self._lock:
                self._diagnostics["referenceResolutions"] += 1
            return self.resolver.resolve(
                spec,
                live_source_path=source_path,
                cached_only=True,
                resolved_hint=resolved_commit,
                cancelled=context.cancelled,
                protected_urls=self._protected_github_urls(),
            )

        def completed(result: _ResolvedSnapshot) -> None:
            with self._lock:
                current = self._sessions.get(session_key)
                if current is None or current.spec != spec:
                    return
                current.restore_requested = False
                current.resolved = result.resolved
                current.snapshot = ReferenceSnapshot(result.resolved, result.snapshot)
                current.state = "ready"
                current.error_code = None
                current.error_message = None
            self._record_resolution(result)
            self._notify(current)

        def failed(error: Exception) -> None:
            with self._lock:
                current = self._sessions.get(session_key)
                if current is None or current.spec != spec:
                    return
                current.restore_requested = False
                current.state = "cache_miss"
                current.error_code = getattr(error, "code", "cache_miss")
                current.error_message = str(error)
            self._notify(current)

        self.coordinator.submit(
            "source",
            (session_key, "restore"),
            restore,
            completed=completed,
            failed=failed,
        )

    def session_key_for_document(self, document_id: str) -> str | None:
        with self._lock:
            return self._documents.get(str(document_id))

    def status_for_document(self, document_id: str) -> ReferenceStatus | None:
        with self._lock:
            key = self._documents.get(str(document_id))
            session = self._sessions.get(key) if key else None
        return self._status(session) if session is not None else None

    def status_for_source(
        self, source_path: str | None, *, native_identity: str | None = None
    ) -> ReferenceStatus | None:
        key = self.ensure_source(source_path, native_identity=native_identity)
        with self._lock:
            session = self._sessions.get(key) if key else None
        return self._status(session) if session is not None else None

    def snapshot_for_source(
        self, source_path: str | None, *, native_identity: str | None = None
    ) -> ReferenceSnapshot | None:
        key = self.ensure_source(source_path, native_identity=native_identity)
        with self._lock:
            session = self._sessions.get(key) if key else None
            if session is None:
                return None
            if session.spec.kind != "last_saved":
                return None if session.pending_new_reference else session.snapshot
            path = session.source_path
        saved = self.saved_sources.store.snapshot(path) if path else None
        if saved is None:
            return None
        resolved = ResolvedReference(
            kind="last_saved",
            repository=None,
            requested_revision=None,
            resolved_commit=None,
            font_path=path,
            cache_state="not_applicable",
            fetched_at=None,
        )
        return ReferenceSnapshot(resolved=resolved, source=saved)

    def _session_for_document(self, document_id: str) -> _ReferenceSession:
        with self._lock:
            key = self._documents.get(str(document_id))
            session = self._sessions.get(key) if key else None
        if session is None:
            raise ComparisonReferenceError(
                "document_unbound", "The document reference session is unavailable."
            )
        return session

    def _protected_github_urls(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(
                session.spec.repository_url
                for session in self._sessions.values()
                if session.document_id is not None
                and session.spec.kind == "github"
                and session.spec.repository_url is not None
            )

    def configure_wait(
        self,
        document_id: str,
        spec: ComparisonReferenceSpec,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        origin: str = "agent",
    ) -> ReferenceStatus:
        timeout = max(
            MINIMUM_TIMEOUT_SECONDS,
            min(MAXIMUM_TIMEOUT_SECONDS, float(timeout_seconds)),
        )
        session = self._session_for_document(document_id)
        if spec.kind == "last_saved":
            with self._lock:
                self.coordinator.invalidate(session.session_key)
                session.spec = spec
                session.resolved = None
                session.snapshot = None
                session.state = "ready"
                session.stale = False
                session.error_code = None
                session.error_message = None
                session.origin = origin
                session.pending_new_reference = False
                session.pending_spec = None
            self.preferences.save(session.source_path, spec, None)
            self._notify(session)
            return self._status(session)

        return self._resolve_wait(
            document_id,
            spec,
            timeout_seconds=timeout,
            origin=origin,
            refresh=False,
        )

    def _resolve_wait(
        self,
        document_id: str,
        spec: ComparisonReferenceSpec,
        *,
        timeout_seconds: float,
        origin: str,
        refresh: bool,
    ) -> ReferenceStatus:
        timeout = max(
            MINIMUM_TIMEOUT_SECONDS,
            min(MAXIMUM_TIMEOUT_SECONDS, float(timeout_seconds)),
        )
        session = self._session_for_document(document_id)
        session_key = session.session_key
        source_path = session.source_path
        work_key = (session_key, "refresh" if refresh else "configure")

        done = Event()
        result_holder: dict[str, Any] = {}
        with self._lock:
            previous = (
                session.spec,
                session.resolved,
                session.snapshot,
                session.state,
                session.stale,
                session.origin,
                session.error_code,
                session.error_message,
            )
            session.state = "refreshing" if refresh else "resolving"
            session.error_code = None
            session.error_message = None
            session.pending_new_reference = not refresh
            session.pending_spec = spec
        self._notify(session)

        def resolve(context: WorkContext):
            with self._lock:
                self._diagnostics["referenceResolutions"] += 1
            return self.resolver.resolve(
                spec,
                live_source_path=source_path,
                timeout_seconds=timeout,
                cancelled=context.cancelled,
                protected_urls=self._protected_github_urls(),
            )

        def completed(result: _ResolvedSnapshot) -> None:
            with self._lock:
                if done.is_set():
                    return
                current = self._sessions.get(session_key)
                if current is None or current.pending_spec != spec:
                    return
                current.spec = ComparisonReferenceSpec(
                    kind=spec.kind,
                    revision=spec.revision,
                    repository_path=spec.repository_path,
                    repository_url=spec.repository_url,
                    font_path=result.resolved.font_path,
                )
                current.resolved = result.resolved
                current.snapshot = ReferenceSnapshot(result.resolved, result.snapshot)
                current.state = "ready"
                current.stale = False
                current.error_code = None
                current.error_message = None
                current.origin = origin
                current.pending_new_reference = False
                current.pending_spec = None
                result_holder["status"] = current.status()
            self._record_resolution(result)
            self.preferences.save(current.source_path, current.spec, current.resolved)
            self._notify(current)
            done.set()

        def failed(error: Exception) -> None:
            with self._lock:
                if done.is_set():
                    return
                current = self._sessions.get(session_key)
                if current is None or current.pending_spec != spec:
                    return
                (
                    current.spec,
                    current.resolved,
                    current.snapshot,
                    current.state,
                    current.stale,
                    current.origin,
                    current.error_code,
                    current.error_message,
                ) = previous
                current.pending_new_reference = False
                current.pending_spec = None
                current.error_code = getattr(error, "code", "reference_resolution_failed")
                current.error_message = str(error)
                if refresh and current.snapshot is not None:
                    current.state = "stale_cached"
                    current.stale = True
                code = str(getattr(error, "code", ""))
                self._diagnostics["timeouts"] += int(code == "reference_timeout")
                self._diagnostics["cancellations"] += int(code == "cancelled")
                result_holder["error"] = error
            self._notify(current)
            done.set()

        generation = self.coordinator.submit(
            "source",
            work_key,
            resolve,
            completed=completed,
            failed=failed,
        )
        if generation is None:
            failed(
                ComparisonReferenceError(
                    "reference_service_unavailable",
                    "The comparison reference service is unavailable.",
                )
            )
        if not done.wait(timeout):
            self.coordinator.invalidate(work_key, kind="source")
            failed(
                ComparisonReferenceError(
                    "reference_timeout",
                    "Reference resolution exceeded {:.0f} seconds.".format(timeout),
                )
            )
        error = result_holder.get("error")
        if isinstance(error, ComparisonReferenceError):
            raise error
        if isinstance(error, Exception):
            raise ComparisonReferenceError(
                "reference_resolution_failed", str(error)
            ) from error
        status = result_holder.get("status")
        if not isinstance(status, ReferenceStatus):
            raise ComparisonReferenceError(
                "reference_resolution_failed", "The reference did not publish a result."
            )
        return status

    def refresh_wait(
        self,
        document_id: str,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        origin: str = "agent",
    ) -> ReferenceStatus:
        session = self._session_for_document(document_id)
        if session.spec.kind == "last_saved":
            return self._status(session)
        return self._resolve_wait(
            document_id,
            session.spec,
            timeout_seconds=timeout_seconds,
            origin=origin,
            refresh=True,
        )

    def document_was_closed(self, document_id: str) -> None:
        with self._lock:
            key = self._documents.pop(str(document_id), None)
            session = self._sessions.get(key) if key else None
            if session is not None:
                session.document_id = None
            self.coordinator.invalidate(key) if key else None

    def close(self) -> None:
        self.coordinator.close(wait=False)
        unsubscribe = self._unsubscribe_saved_sources
        self._unsubscribe_saved_sources = None
        if callable(unsubscribe):
            unsubscribe()
        with self._lock:
            self._listeners = ()
            self._sessions.clear()
            self._documents.clear()
            self._sources.clear()


_FALLBACK_PREFERENCES: dict[str, Any] = {}


class _JsonPreferenceValues(MutableMapping[str, Any]):
    """Small atomic mapping for Glyphs MCP-owned local preferences."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = RLock()
        self._values: dict[str, Any] = {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                self._values = value
        except (OSError, ValueError, TypeError):
            pass

    def __getitem__(self, key: str) -> Any:
        with self._lock:
            return self._values[key]

    def __setitem__(self, key: str, value: Any) -> None:
        with self._lock:
            self._values[key] = value
            self._write()

    def __delitem__(self, key: str) -> None:
        with self._lock:
            del self._values[key]
            self._write()

    def __iter__(self):
        with self._lock:
            return iter(tuple(self._values))

    def __len__(self) -> int:
        with self._lock:
            return len(self._values)

    def _write(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(self._values, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError:
            # A read-only or unavailable preferences directory must not make the
            # Reporter unavailable for the current Glyphs session.
            return


_DEFAULT_PREFERENCE_VALUES: MutableMapping[str, Any] | None = None


def _default_preferences_values() -> MutableMapping[str, Any]:
    global _DEFAULT_PREFERENCE_VALUES
    if _DEFAULT_PREFERENCE_VALUES is None:
        try:
            path = (
                Path.home()
                / "Library"
                / "Application Support"
                / "com.thierryc.GlyphsMCP"
                / "v2"
                / "comparison-references.json"
            )
            _DEFAULT_PREFERENCE_VALUES = _JsonPreferenceValues(path)
        except Exception:
            _DEFAULT_PREFERENCE_VALUES = _FALLBACK_PREFERENCES
    return _DEFAULT_PREFERENCE_VALUES


_DEFAULT_SERVICE: ComparisonReferenceService | None = None
_DEFAULT_SERVICE_LOCK = RLock()


def default_comparison_reference_service() -> ComparisonReferenceService:
    global _DEFAULT_SERVICE
    with _DEFAULT_SERVICE_LOCK:
        if _DEFAULT_SERVICE is None:
            _DEFAULT_SERVICE = ComparisonReferenceService()
        return _DEFAULT_SERVICE


__all__ = [
    "CACHE_SOFT_LIMIT_BYTES",
    "ComparisonReferenceError",
    "ComparisonReferencePreferences",
    "ComparisonReferenceService",
    "ComparisonReferenceSpec",
    "DulwichGitReferenceResolver",
    "GitReferenceCache",
    "ReferenceSnapshot",
    "ReferenceStatus",
    "ReferenceUpdate",
    "ResolvedReference",
    "canonical_github_url",
    "default_comparison_reference_service",
    "native_font_identity",
]
