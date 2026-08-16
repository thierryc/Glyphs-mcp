"""Fingerprint-bound staging and publication for v2 source bundles."""

from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from typing import Any, Callable, Mapping


class ExportPublicationError(RuntimeError):
    """Raised before an unverified destination can be published."""


def resolve_destination(value: str) -> Path:
    raw = Path(str(value or ""))
    if not raw.is_absolute():
        raise ValueError("destination must be an explicit absolute path")
    if raw.is_symlink():
        raise ValueError("destination cannot be a symbolic link")
    resolved = raw.resolve(strict=False)
    if resolved == Path(resolved.anchor):
        raise ValueError("destination cannot be a filesystem root")
    return resolved


def _tree_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    entries = [path]
    if path.is_dir():
        entries.extend(sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()))
    for entry in entries:
        relative = "." if entry == path else entry.relative_to(path).as_posix()
        metadata = entry.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            kind = "symlink"
        elif stat.S_ISDIR(metadata.st_mode):
            kind = "directory"
        elif stat.S_ISREG(metadata.st_mode):
            kind = "file"
        else:
            raise ExportPublicationError("destination contains an unsupported filesystem object")
        digest.update(kind.encode("utf-8"))
        digest.update(b"\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if kind == "symlink":
            digest.update(os.readlink(entry).encode("utf-8"))
        elif kind == "file":
            with entry.open("rb") as handle:
                while True:
                    block = handle.read(1024 * 1024)
                    if not block:
                        break
                    digest.update(block)
        digest.update(b"\0")
    return "sha256:{}".format(digest.hexdigest())


def inspect_destination(value: str) -> dict[str, Any]:
    path = resolve_destination(value)
    if not path.exists():
        return {"exists": False, "empty": True, "kind": None, "fingerprint": None}
    kind = "directory" if path.is_dir() else "file" if path.is_file() else "unsupported"
    if kind == "unsupported":
        raise ValueError("destination must be a regular file or directory")
    empty = path.is_dir() and next(path.iterdir(), None) is None
    return {
        "exists": True,
        "empty": empty,
        "kind": kind,
        "fingerprint": _tree_fingerprint(path),
    }


def destination_matches(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    keys = ("exists", "empty", "kind", "fingerprint")
    return all(left.get(key) == right.get(key) for key in keys)


def _atomic_swap(left: Path, right: Path) -> None:
    if sys.platform != "darwin":
        raise ExportPublicationError("atomic directory replacement requires macOS renameatx_np")
    libc = ctypes.CDLL(None, use_errno=True)
    renameatx_np = getattr(libc, "renameatx_np", None)
    if renameatx_np is None:
        raise ExportPublicationError("macOS atomic swap is unavailable")
    renameatx_np.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameatx_np.restype = ctypes.c_int
    at_fdcwd = -2
    rename_swap = 0x00000002
    result = renameatx_np(
        at_fdcwd,
        os.fsencode(left),
        at_fdcwd,
        os.fsencode(right),
        rename_swap,
    )
    if result != 0:
        errno_value = ctypes.get_errno()
        raise ExportPublicationError(os.strerror(errno_value))


def publish_staged_directory(
    *,
    destination: str,
    expected_state: Mapping[str, Any],
    producer: Callable[[Path], Mapping[str, Any]],
) -> dict[str, Any]:
    """Build beside the destination, then publish only the reviewed state."""

    target = resolve_destination(destination)
    current = inspect_destination(str(target))
    if not destination_matches(current, expected_state):
        raise ExportPublicationError("destination changed after review")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".glyphs-mcp-v2-export-", dir=str(target.parent)))
    staged = staging_root / "bundle"
    swapped = False
    try:
        producer_result = dict(producer(staged))
        if not staged.is_dir():
            raise ExportPublicationError("export producer did not create a source-bundle directory")
        staged_fingerprint = _tree_fingerprint(staged)
        before_publish = inspect_destination(str(target))
        if not destination_matches(before_publish, expected_state):
            raise ExportPublicationError("destination changed while the bundle was staged")
        if before_publish["exists"]:
            _atomic_swap(staged, target)
            swapped = True
            displaced_state = inspect_destination(str(staged))
            if not destination_matches(displaced_state, expected_state):
                _atomic_swap(staged, target)
                swapped = False
                raise ExportPublicationError("destination changed during atomic publication")
        else:
            os.replace(staged, target)
        published_state = inspect_destination(str(target))
        if published_state["fingerprint"] != staged_fingerprint:
            if swapped:
                _atomic_swap(staged, target)
                swapped = False
            else:
                os.replace(target, staged)
            raise ExportPublicationError("published bundle failed fingerprint verification")
        return {
            **producer_result,
            "destination": str(target),
            "publishedFingerprint": published_state["fingerprint"],
            "replacedDestinationFingerprint": expected_state.get("fingerprint"),
            "atomicPublication": True,
        }
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


__all__ = [
    "ExportPublicationError",
    "destination_matches",
    "inspect_destination",
    "publish_staged_directory",
    "resolve_destination",
]
