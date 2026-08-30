"""Stable one-pass saved Glyphs source snapshots shared across v2 features."""

from __future__ import annotations

import copy
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping, Sequence

from .background_work import BackgroundWorkCoordinator, WorkContext
from .canonical_sources import SerializedMappingSource
from .canonical_tree import CanonicalSnapshot


SourceSignature = tuple[Any, ...]


def normalize_source_path(value: Any) -> str | None:
    """Return one absolute supported Glyphs source path without reading it."""

    text = str(value or "").strip()
    if not text:
        return None
    path = os.path.abspath(os.path.expanduser(text))
    if Path(path).suffix.lower() not in {".glyphs", ".glyphspackage"}:
        return None
    return path


def saved_source_signature(path: Path) -> SourceSignature:
    """Return a content-free metadata signature for a flat or package source."""

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


def source_state_changed(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    absent_before_is_change: bool = False,
) -> bool:
    """Compare the persistence identity fields used across v2 reconciliation."""

    if before is None:
        return bool(absent_before_is_change and after is not None)
    if after is None:
        return True
    return any(
        before.get(key) != after.get(key)
        for key in ("kind", "exists", "contentFingerprint")
    )


def _decode_openstep(data: bytes) -> Any:
    from openstep_plist import loads  # type: ignore[import-not-found]

    return loads(data.decode("utf-8"), use_numbers=True)


def _content_fingerprint(kind: str, files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    if kind == "glyphs":
        digest.update(files[""])
    else:
        for relative in sorted(files):
            encoded = relative.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            digest.update(files[relative])
    return "sha256:{}".format(digest.hexdigest())


def _package_mapping(
    files: Mapping[str, bytes], decoder: Callable[[bytes], Any]
) -> Mapping[str, Any] | None:
    def decoded(name: str, default: Any = None) -> Any:
        raw = files.get(name)
        return default if raw is None else decoder(raw)

    fontinfo = decoded("fontinfo.plist")
    order = decoded("order.plist")
    kerning = decoded("kerning.plist", {})
    if not isinstance(fontinfo, Mapping) or not isinstance(order, list):
        return None
    if not isinstance(kerning, Mapping):
        return None

    glyphs: dict[str, Any] = {}
    for name in sorted(
        value
        for value in files
        if value.startswith("glyphs/") and value.endswith(".glyph")
    ):
        glyph = decoded(name)
        if not isinstance(glyph, Mapping):
            return None
        glyph_name = str(glyph.get("glyphname") or "")
        if not glyph_name or glyph_name in glyphs:
            return None
        glyphs[glyph_name] = glyph

    fontinfo_copy = copy.deepcopy(dict(fontinfo))
    for collection_name in ("features", "classes", "featurePrefixes"):
        records = fontinfo_copy.get(collection_name)
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict) or record.get("code") is not None:
                continue
            file_name = str(record.get("file") or "")
            raw = files.get("features/{}".format(file_name)) if file_name else None
            if raw is None:
                continue
            try:
                record["code"] = raw.decode("utf-8")
            except UnicodeError:
                return None

    mapping: dict[str, Any] = {
        "fontinfo.plist": fontinfo_copy,
        "order.plist": list(order),
        "kerning.plist": copy.deepcopy(dict(kerning)),
        "glyphs": glyphs,
    }
    if "note.md" in files:
        try:
            mapping["note.md"] = files["note.md"].decode("utf-8")
        except UnicodeError:
            return None
    return mapping


@dataclass(frozen=True)
class SavedSourceSnapshot:
    path: str
    source_fingerprint: str
    signature: SourceSignature
    canonical: CanonicalSnapshot

    @property
    def model(self) -> CanonicalSnapshot:
        return self.canonical


@dataclass(frozen=True)
class SavedSourceRead:
    path: str
    state: Mapping[str, Any]
    snapshot: SavedSourceSnapshot | None
    error: str | None = None


class SavedSourceReader:
    """Read, hash, and decode one stable source without rereading its bytes."""

    def __init__(
        self,
        *,
        signature: Callable[[Path], SourceSignature] = saved_source_signature,
        read_bytes: Callable[[Path], bytes] | None = None,
        decoder: Callable[[bytes], Any] = _decode_openstep,
    ) -> None:
        self._signature = signature
        self._read_bytes = read_bytes or Path.read_bytes
        self._decoder = decoder

    def read(
        self,
        path: Any,
        *,
        instance_ids: Sequence[str] = (),
        cancelled: Callable[[], bool] | None = None,
    ) -> SavedSourceRead:
        normalized = normalize_source_path(path)
        if normalized is None:
            return SavedSourceRead(
                path=str(path or ""),
                state={"exists": False, "readable": False},
                snapshot=None,
                error="unsupported_source_format",
            )
        source = Path(normalized)
        before = self._signature(source)
        kind = str(before[0]) if before else (
            "glyphspackage" if source.suffix.lower() == ".glyphspackage" else "glyphs"
        )
        if len(before) < 2 or before[1] is not True:
            return SavedSourceRead(
                path=normalized,
                state={
                    "kind": kind,
                    "exists": bool(len(before) > 1 and before[1] is not False),
                    "readable": False,
                    "contentFingerprint": None,
                    "filePath": normalized,
                },
                snapshot=None,
                error="source_unavailable",
            )

        try:
            if kind == "glyphs":
                files = {"": self._read_bytes(source)}
            else:
                records = before[2] if len(before) > 2 else ()
                files = {}
                for record in records:
                    if cancelled is not None and cancelled():
                        return SavedSourceRead(
                            path=normalized,
                            state={
                                "kind": kind,
                                "exists": True,
                                "readable": False,
                                "contentFingerprint": None,
                                "filePath": normalized,
                            },
                            snapshot=None,
                            error="cancelled",
                        )
                    relative = str(record[0])
                    files[relative] = self._read_bytes(source / relative)
        except (OSError, UnicodeError):
            return SavedSourceRead(
                path=normalized,
                state={
                    "kind": kind,
                    "exists": True,
                    "readable": False,
                    "contentFingerprint": None,
                    "filePath": normalized,
                },
                snapshot=None,
                error="source_unreadable",
            )

        after = self._signature(source)
        if after != before:
            return SavedSourceRead(
                path=normalized,
                state={
                    "kind": kind,
                    "exists": True,
                    "readable": False,
                    "contentFingerprint": None,
                    "filePath": normalized,
                },
                snapshot=None,
                error="source_changed_during_read",
            )
        fingerprint = _content_fingerprint(kind, files)
        try:
            serialized = (
                self._decoder(files[""])
                if kind == "glyphs"
                else _package_mapping(files, self._decoder)
            )
            if not isinstance(serialized, Mapping):
                raise ValueError("saved source did not decode to a mapping")
            model = dict(
                SerializedMappingSource(
                    serialized,
                    copy_source=False,
                    document_path=source,
                ).capture()
            )
            identities = tuple(str(value) for value in instance_ids)
            instances = model.get("instances")
            if identities and isinstance(instances, list):
                if len(identities) != len(instances):
                    raise ValueError("saved instance identities do not match")
                for index, instance in enumerate(instances):
                    if not isinstance(instance, dict):
                        raise ValueError("saved instance is invalid")
                    instance["id"] = identities[index]
            canonical = CanonicalSnapshot.from_model(model)
        except Exception:
            return SavedSourceRead(
                path=normalized,
                state={
                    "kind": kind,
                    "exists": True,
                    "readable": True,
                    "contentFingerprint": fingerprint,
                    "filePath": normalized,
                },
                snapshot=None,
                error="source_decode_failed",
            )

        snapshot = SavedSourceSnapshot(
            path=normalized,
            source_fingerprint=fingerprint,
            signature=after,
            canonical=canonical,
        )
        return SavedSourceRead(
            path=normalized,
            state={
                "kind": kind,
                "exists": True,
                "readable": True,
                "contentFingerprint": fingerprint,
                "filePath": normalized,
            },
            snapshot=snapshot,
        )


@dataclass(frozen=True)
class SavedSourceRefresh:
    path: str
    changed: bool
    snapshot: SavedSourceSnapshot | None
    error: str | None


class SavedSourceStore:
    """Atomically publish immutable snapshots; foreground reads never lock."""

    def __init__(self, *, reader: SavedSourceReader | None = None) -> None:
        self.reader = reader or SavedSourceReader()
        self._published: dict[str, SavedSourceSnapshot] = {}
        self._states: dict[str, Mapping[str, Any]] = {}
        self._errors: dict[str, str] = {}
        self._content: dict[str, SavedSourceSnapshot] = {}
        self._publish_lock = RLock()

    def snapshot(self, path: Any) -> SavedSourceSnapshot | None:
        normalized = normalize_source_path(path)
        return self._published.get(normalized) if normalized is not None else None

    def state(self, path: Any) -> Mapping[str, Any] | None:
        normalized = normalize_source_path(path)
        return self._states.get(normalized) if normalized is not None else None

    def error(self, path: Any) -> str | None:
        normalized = normalize_source_path(path)
        return self._errors.get(normalized) if normalized is not None else None

    def paths(self) -> frozenset[str]:
        return frozenset(self._published)

    def publish(self, value: SavedSourceRead) -> SavedSourceRefresh:
        normalized = normalize_source_path(value.path)
        if normalized is None:
            return SavedSourceRefresh(value.path, False, None, value.error)
        with self._publish_lock:
            previous = self._published.get(normalized)
            snapshot = value.snapshot
            if snapshot is not None:
                reusable = self._content.get(snapshot.source_fingerprint)
                if reusable is not None:
                    snapshot = SavedSourceSnapshot(
                        path=normalized,
                        source_fingerprint=reusable.source_fingerprint,
                        signature=snapshot.signature,
                        canonical=reusable.canonical,
                    )
                self._content[snapshot.source_fingerprint] = snapshot
            published = dict(self._published)
            if snapshot is not None:
                published[normalized] = snapshot
            elif previous is not None:
                # A failed optional refresh must not discard the last usable
                # result.  Foreground consumers can keep drawing it while the
                # error state exposes that it may be stale.
                snapshot = previous
            states = dict(self._states)
            states[normalized] = dict(value.state)
            errors = dict(self._errors)
            if value.error:
                errors[normalized] = value.error
            else:
                errors.pop(normalized, None)
            self._published = published
            self._states = states
            self._errors = errors
        changed = (
            previous.source_fingerprint if previous is not None else None
        ) != (snapshot.source_fingerprint if snapshot is not None else None)
        return SavedSourceRefresh(normalized, changed, snapshot, value.error)

    def refresh(
        self,
        path: Any,
        *,
        instance_ids: Sequence[str] = (),
        cancelled: Callable[[], bool] | None = None,
    ) -> SavedSourceRefresh:
        return self.publish(
            self.reader.read(
                path,
                instance_ids=instance_ids,
                cancelled=cancelled,
            )
        )

    def retain_only(self, paths: set[str]) -> bool:
        normalized = {
            value
            for path in paths
            if (value := normalize_source_path(path)) is not None
        }
        previous = self._published
        published = {key: value for key, value in previous.items() if key in normalized}
        states = {key: value for key, value in self._states.items() if key in normalized}
        errors = {key: value for key, value in self._errors.items() if key in normalized}
        self._published = published
        self._states = states
        self._errors = errors
        retained_fingerprints = {value.source_fingerprint for value in published.values()}
        self._content = {
            key: value for key, value in self._content.items() if key in retained_fingerprints
        }
        return set(previous) != set(published)

    def clear(self) -> bool:
        changed = bool(self._published or self._states or self._errors)
        self._published = {}
        self._states = {}
        self._errors = {}
        self._content = {}
        return changed


class SavedSourceService:
    """Event-driven asynchronous facade shared by Reporter and MCP runtime."""

    def __init__(
        self,
        *,
        store: SavedSourceStore | None = None,
        coordinator: BackgroundWorkCoordinator | None = None,
    ) -> None:
        self.store = store or SavedSourceStore()
        self.coordinator = coordinator or BackgroundWorkCoordinator()
        self._listeners: tuple[Callable[[SavedSourceRefresh], None], ...] = ()

    def subscribe(
        self, listener: Callable[[SavedSourceRefresh], None]
    ) -> Callable[[], None]:
        self._listeners = self._listeners + (listener,)

        def unsubscribe() -> None:
            self._listeners = tuple(
                value for value in self._listeners if value is not listener
            )

        return unsubscribe

    def request_refresh(
        self,
        path: Any,
        *,
        force: bool = False,
        delay: float = 0.0,
        instance_ids: Sequence[str] = (),
    ) -> int | None:
        normalized = normalize_source_path(path)
        if normalized is None:
            return None

        def refresh(context: WorkContext) -> SavedSourceRefresh:
            current = self.store.snapshot(normalized)
            if not force and current is not None:
                signature = saved_source_signature(Path(normalized))
                if current.signature == signature:
                    return SavedSourceRefresh(normalized, False, current, None)
            return self.store.refresh(
                normalized,
                instance_ids=instance_ids,
                cancelled=context.cancelled,
            )

        def completed(result: SavedSourceRefresh) -> None:
            for listener in self._listeners:
                try:
                    listener(result)
                except Exception:
                    pass

        return self.coordinator.submit(
            "source",
            normalized,
            refresh,
            completed=completed,
            delay=delay,
        )

    def publish_verified(self, snapshot: SavedSourceSnapshot) -> SavedSourceRefresh:
        """Publish source proof already produced by save verification."""

        kind = (
            "glyphspackage"
            if Path(snapshot.path).suffix.lower() == ".glyphspackage"
            else "glyphs"
        )
        result = self.store.publish(
            SavedSourceRead(
                path=snapshot.path,
                state={
                    "kind": kind,
                    "exists": True,
                    "readable": True,
                    "contentFingerprint": snapshot.source_fingerprint,
                    "filePath": snapshot.path,
                },
                snapshot=snapshot,
            )
        )
        for listener in self._listeners:
            try:
                listener(result)
            except Exception:
                pass
        return result

    def pause_for_save(self, path: Any) -> None:
        normalized = normalize_source_path(path)
        if normalized is not None:
            self.coordinator.pause_for_save(normalized)

    def resume_after_save(self, path: Any) -> None:
        normalized = normalize_source_path(path)
        if normalized is not None:
            self.coordinator.resume_after_save(normalized, delay=0.25)
            self.request_refresh(normalized, force=True, delay=0.25)

    def retain_only(self, paths: set[str]) -> bool:
        normalized = {
            value
            for path in paths
            if (value := normalize_source_path(path)) is not None
        }
        for path in set(self.store._published) - normalized:
            self.coordinator.invalidate(path)
        return self.store.retain_only(normalized)

    def request_retain_only(
        self,
        paths: set[str],
        *,
        completed: Callable[[bool], None] | None = None,
    ) -> int | None:
        """Enqueue close/Save-As eviction without copying state on the caller."""

        normalized = frozenset(
            value
            for path in paths
            if (value := normalize_source_path(path)) is not None
        )

        def cleanup(_context: WorkContext) -> bool:
            for obsolete in self.store.paths() - normalized:
                self.coordinator.invalidate(obsolete)
            return self.store.retain_only(set(normalized))

        return self.coordinator.submit(
            "cleanup",
            "saved-source-paths",
            cleanup,
            completed=completed,
        )


_DEFAULT_SERVICE: SavedSourceService | None = None
_DEFAULT_SERVICE_LOCK = RLock()


def default_saved_source_service() -> SavedSourceService:
    global _DEFAULT_SERVICE
    with _DEFAULT_SERVICE_LOCK:
        if _DEFAULT_SERVICE is None:
            _DEFAULT_SERVICE = SavedSourceService()
        return _DEFAULT_SERVICE


__all__ = [
    "SavedSourceRead",
    "SavedSourceReader",
    "SavedSourceRefresh",
    "SavedSourceService",
    "SavedSourceSnapshot",
    "SavedSourceStore",
    "default_saved_source_service",
    "normalize_source_path",
    "saved_source_signature",
    "source_state_changed",
]
