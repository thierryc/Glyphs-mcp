"""Fingerprint-bound staging and publication for v2 source bundles."""

from __future__ import annotations

import ctypes
import errno
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
    if ".." in raw.parts:
        raise ValueError("destination cannot contain parent traversal")
    # macOS exposes these two stable root aliases as system symlinks. Resolve
    # them before applying the arbitrary-ancestor prohibition so ordinary
    # tempfile destinations remain usable without weakening user-path checks.
    if sys.platform == "darwin" and len(raw.parts) > 1 and raw.parts[1] in {
        "tmp",
        "var",
    }:
        raw = Path("/private") / Path(*raw.parts[1:])
    current = Path(raw.anchor)
    for part in raw.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError("destination and its ancestors cannot be symbolic links")
        if current.exists() and current != raw and not current.is_dir():
            raise ValueError("destination ancestors must be directories")
    resolved = raw.resolve(strict=False)
    if resolved == Path(resolved.anchor):
        raise ValueError("destination cannot be a filesystem root")
    if not resolved.parent.is_dir():
        raise ValueError("destination parent directory must already exist")
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
            raise ExportPublicationError(
                "destination trees cannot contain symbolic links"
            )
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
        if kind == "file":
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
    try:
        fingerprint = _tree_fingerprint(path)
    except ExportPublicationError as exc:
        raise ValueError(str(exc)) from exc
    return {
        "exists": True,
        "empty": empty,
        "kind": kind,
        "fingerprint": fingerprint,
    }


def _inspect_for_publication(value: str) -> dict[str, Any]:
    try:
        return inspect_destination(value)
    except ValueError as exc:
        raise ExportPublicationError(str(exc)) from exc


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
    rename_nofollow_any = 0x00000010
    result = renameatx_np(
        at_fdcwd,
        os.fsencode(left),
        at_fdcwd,
        os.fsencode(right),
        rename_swap | rename_nofollow_any,
    )
    if result != 0:
        errno_value = ctypes.get_errno()
        raise ExportPublicationError(os.strerror(errno_value))


def _atomic_publish_missing(staged: Path, target: Path) -> None:
    """Atomically publish ``staged`` only while ``target`` is still absent.

    A final stat followed by ``os.replace`` is not a no-clobber operation: a
    directory or symlink can appear in that gap and be silently replaced.  The
    v2 runtime is macOS-only, so use Darwin's kernel-enforced exclusive rename
    and reject the publication if any destination object appears.
    """

    if sys.platform != "darwin":
        raise ExportPublicationError(
            "atomic no-clobber directory publication requires macOS renameatx_np"
        )
    libc = ctypes.CDLL(None, use_errno=True)
    renameatx_np = getattr(libc, "renameatx_np", None)
    if renameatx_np is None:
        raise ExportPublicationError("macOS exclusive rename is unavailable")
    renameatx_np.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameatx_np.restype = ctypes.c_int
    at_fdcwd = -2
    rename_excl = 0x00000004
    rename_nofollow_any = 0x00000010
    ctypes.set_errno(0)
    result = renameatx_np(
        at_fdcwd,
        os.fsencode(staged),
        at_fdcwd,
        os.fsencode(target),
        rename_excl | rename_nofollow_any,
    )
    if result == 0:
        return
    errno_value = ctypes.get_errno()
    if errno_value in {errno.EEXIST, errno.ENOTEMPTY}:
        raise ExportPublicationError(
            "destination appeared during atomic publication"
        )
    raise ExportPublicationError(
        "exclusive destination publication failed: {}".format(
            os.strerror(errno_value)
        )
    )


def publish_staged_directory(
    *,
    destination: str,
    expected_state: Mapping[str, Any],
    producer: Callable[[Path], Mapping[str, Any]],
) -> dict[str, Any]:
    """Build beside the destination, then publish only the reviewed state."""

    target = resolve_destination(destination)
    current = _inspect_for_publication(str(target))
    if not destination_matches(current, expected_state):
        raise ExportPublicationError("destination changed after review")
    if resolve_destination(destination) != target:
        raise ExportPublicationError("destination path changed after review")
    staging_root = Path(tempfile.mkdtemp(prefix=".glyphs-mcp-v2-export-", dir=str(target.parent)))
    staged = staging_root / "bundle"
    swapped = False
    preserve_staging = False
    try:
        producer_result = dict(producer(staged))
        if not staged.is_dir():
            raise ExportPublicationError("export producer did not create a source-bundle directory")
        staged_fingerprint = _tree_fingerprint(staged)
        before_publish = _inspect_for_publication(str(target))
        if not destination_matches(before_publish, expected_state):
            raise ExportPublicationError("destination changed while the bundle was staged")
        if before_publish["exists"]:
            _atomic_swap(staged, target)
            swapped = True
        else:
            _atomic_publish_missing(staged, target)
        try:
            if swapped:
                displaced_state = _inspect_for_publication(str(staged))
                if not destination_matches(displaced_state, expected_state):
                    raise ExportPublicationError(
                        "destination changed during atomic publication"
                    )
            published_state = _inspect_for_publication(str(target))
            if published_state["fingerprint"] != staged_fingerprint:
                raise ExportPublicationError(
                    "published bundle failed fingerprint verification"
                )
        except Exception as verification_error:
            try:
                if swapped:
                    _atomic_swap(staged, target)
                    swapped = False
                else:
                    if not os.path.lexists(target):
                        raise ExportPublicationError(
                            "published destination disappeared before restoration"
                        )
                    os.replace(target, staged)
                restored_state = _inspect_for_publication(str(target))
                if not destination_matches(restored_state, expected_state):
                    raise ExportPublicationError(
                        "restored destination does not match the reviewed state"
                    )
            except Exception as restoration_error:
                preserve_staging = True
                raise ExportPublicationError(
                    "post-publication verification failed ({verification}); automatic "
                    "restoration also failed ({restoration}); recovery evidence is "
                    "preserved at {path}".format(
                        verification=verification_error,
                        restoration=restoration_error,
                        path=staging_root,
                    )
                ) from restoration_error
            raise ExportPublicationError(
                "post-publication verification failed; the reviewed destination was "
                "restored: {}".format(verification_error)
            ) from verification_error
        return {
            **producer_result,
            "destination": str(target),
            "publishedFingerprint": published_state["fingerprint"],
            "replacedDestinationFingerprint": expected_state.get("fingerprint"),
            "atomicPublication": True,
        }
    finally:
        if not preserve_staging:
            shutil.rmtree(staging_root, ignore_errors=True)


__all__ = [
    "ExportPublicationError",
    "destination_matches",
    "inspect_destination",
    "publish_staged_directory",
    "resolve_destination",
]
