"""Immutable host snapshots and ports used by v2 application services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol, Sequence, TypeVar


T = TypeVar("T")


class HostAccessError(RuntimeError):
    """A normalized, recoverable host access failure."""


class MainThreadExecutor(Protocol):
    def run(self, callback: Callable[[], T]) -> T:
        ...


@dataclass(frozen=True)
class HostRuntimeSnapshot:
    application: str
    application_version: str
    build_number: str
    python_version: str
    open_document_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "application": self.application,
            "applicationVersion": self.application_version,
            "buildNumber": self.build_number,
            "pythonVersion": self.python_version,
            "openDocumentCount": self.open_document_count,
        }


@dataclass(frozen=True)
class FontSnapshot:
    document_id: str
    legacy_index: int
    family_name: str
    file_path: Optional[str]
    active: bool
    master_count: int
    instance_count: int
    glyph_count: int
    units_per_em: int
    version_major: int
    version_minor: int
    format_version: Optional[int]
    last_saved_app_version: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "documentId": self.document_id,
            "legacyIndex": self.legacy_index,
            "familyName": self.family_name,
            "filePath": self.file_path,
            "saved": bool(self.file_path),
            "active": self.active,
            "masterCount": self.master_count,
            "instanceCount": self.instance_count,
            "glyphCount": self.glyph_count,
            "unitsPerEm": self.units_per_em,
            "versionMajor": self.version_major,
            "versionMinor": self.version_minor,
            "formatVersion": self.format_version,
            "lastSavedAppVersion": self.last_saved_app_version,
        }


class ReadOnlyHost(Protocol):
    def runtime_snapshot(self) -> HostRuntimeSnapshot:
        ...

    def list_documents(self) -> Sequence[FontSnapshot]:
        ...


__all__ = [
    "FontSnapshot",
    "HostAccessError",
    "HostRuntimeSnapshot",
    "MainThreadExecutor",
    "ReadOnlyHost",
]
