"""Thread-safe saved-source baselines for the drawing-only change Reporter."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class SavedBaselineSnapshot:
    path: str
    source_fingerprint: str
    model: Mapping[str, Any]


@dataclass(frozen=True)
class _CacheEntry:
    signature: tuple[Any, ...]
    source_fingerprint: str | None
    snapshot: SavedBaselineSnapshot | None


def normalize_source_path(value: Any) -> str | None:
    """Return one absolute supported Glyphs source path without reading it."""

    text = str(value or "").strip()
    if not text:
        return None
    path = os.path.abspath(os.path.expanduser(text))
    if Path(path).suffix.lower() not in {".glyphs", ".glyphspackage"}:
        return None
    return path


def saved_source_signature(path: Path) -> tuple[Any, ...]:
    """Return a cheap metadata signature used before content hashing.

    Package signatures inspect names and stat metadata but never read file
    contents. The content fingerprint remains the authority whenever this
    bounded change detector reports a possible update.
    """

    suffix = path.suffix.lower()
    kind = "glyphspackage" if suffix == ".glyphspackage" else "glyphs"
    try:
        if not path.exists():
            return (kind, False)
        if kind == "glyphs":
            if not path.is_file():
                return (kind, "invalid")
            stat = path.stat()
            return (
                kind,
                True,
                int(stat.st_ino),
                int(stat.st_size),
                int(stat.st_mtime_ns),
            )
        if not path.is_dir():
            return (kind, "invalid")
        records = []
        for candidate in sorted(
            (item for item in path.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(path).as_posix(),
        ):
            stat = candidate.stat()
            records.append(
                (
                    candidate.relative_to(path).as_posix(),
                    int(stat.st_ino),
                    int(stat.st_size),
                    int(stat.st_mtime_ns),
                )
            )
        return (kind, True, tuple(records))
    except OSError as error:
        return (kind, "unreadable", type(error).__name__)


def _source_state(path: Path) -> Mapping[str, Any] | None:
    from .adapters.document import _source_file_state

    return _source_file_state(path)


def _load_model(path: Path) -> Mapping[str, Any] | None:
    from .adapters.document import _saved_source_canonical_model

    return _saved_source_canonical_model(path)


class SavedBaselineCache:
    """Own immutable decoded disk snapshots; callers run ``refresh`` off-thread."""

    def __init__(
        self,
        *,
        signature: Callable[[Path], tuple[Any, ...]] = saved_source_signature,
        source_state: Callable[[Path], Mapping[str, Any] | None] = _source_state,
        load_model: Callable[[Path], Mapping[str, Any] | None] = _load_model,
    ) -> None:
        self._signature = signature
        self._source_state = source_state
        self._load_model = load_model
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = RLock()

    def snapshot(self, path: Any) -> SavedBaselineSnapshot | None:
        normalized = normalize_source_path(path)
        if normalized is None:
            return None
        with self._lock:
            entry = self._entries.get(normalized)
            return entry.snapshot if entry is not None else None

    def refresh(self, path: Any, *, force: bool = False) -> bool:
        """Refresh one path and return whether the published baseline changed."""

        normalized = normalize_source_path(path)
        if normalized is None:
            return False
        source_path = Path(normalized)
        signature = self._signature(source_path)
        with self._lock:
            previous = self._entries.get(normalized)
            if previous is not None and previous.signature == signature and not force:
                return False

        state = self._source_state(source_path)
        fingerprint = (
            str(state.get("contentFingerprint"))
            if isinstance(state, Mapping) and state.get("contentFingerprint")
            else None
        )
        readable = bool(
            isinstance(state, Mapping)
            and state.get("exists")
            and state.get("readable")
            and fingerprint
        )
        model: Mapping[str, Any] | None = None
        source_stable = True
        if readable:
            with self._lock:
                reusable = (
                    previous.snapshot
                    if previous is not None
                    and previous.source_fingerprint == fingerprint
                    and previous.snapshot is not None
                    else None
                )
            if reusable is not None:
                model = reusable.model
            else:
                model = self._load_model(source_path)
                verified_state = self._source_state(source_path)
                verified_fingerprint = (
                    str(verified_state.get("contentFingerprint"))
                    if isinstance(verified_state, Mapping)
                    and verified_state.get("contentFingerprint")
                    else None
                )
                source_stable = verified_fingerprint == fingerprint
        snapshot = (
            SavedBaselineSnapshot(
                path=normalized,
                source_fingerprint=fingerprint,
                model=model,
            )
            if fingerprint and source_stable and isinstance(model, Mapping)
            else None
        )
        replacement = _CacheEntry(
            signature=signature,
            source_fingerprint=fingerprint,
            snapshot=snapshot,
        )
        with self._lock:
            current = self._entries.get(normalized)
            self._entries[normalized] = replacement
        return (
            current.snapshot.source_fingerprint
            if current is not None and current.snapshot is not None
            else None
        ) != (
            replacement.snapshot.source_fingerprint
            if replacement.snapshot is not None
            else None
        )

    def retain_only(self, paths: set[str]) -> bool:
        normalized = {
            value
            for path in paths
            if (value := normalize_source_path(path)) is not None
        }
        with self._lock:
            removed = [path for path in self._entries if path not in normalized]
            for path in removed:
                self._entries.pop(path, None)
        return bool(removed)

    def clear(self) -> bool:
        with self._lock:
            changed = bool(self._entries)
            self._entries.clear()
            return changed


__all__ = [
    "SavedBaselineCache",
    "SavedBaselineSnapshot",
    "normalize_source_path",
    "saved_source_signature",
]
