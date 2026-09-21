"""Streaming identity and immutable copying for saved Glyphs sources."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


class SourceError(RuntimeError):
    pass


def _files(path: Path) -> list[Path]:
    if path.suffix.lower() == ".glyphs":
        if not path.is_file() or path.is_symlink():
            raise SourceError("the saved .glyphs source is unavailable or unsafe")
        return [path]
    if path.suffix.lower() != ".glyphspackage" or not path.is_dir() or path.is_symlink():
        raise SourceError("bulk jobs require a saved .glyphs or .glyphspackage source")
    entries = list(path.rglob("*"))
    if any(item.is_symlink() for item in entries):
        raise SourceError("the .glyphspackage is empty or contains symbolic links")
    files = sorted(
        (item for item in entries if item.is_file()),
        key=lambda item: item.relative_to(path).as_posix(),
    )
    if not files:
        raise SourceError("the .glyphspackage is empty or contains symbolic links")
    return files


def source_hash(path: Path | str) -> str:
    source = Path(path)
    digest = hashlib.sha256()
    for item in _files(source):
        if source.is_dir():
            relative = item.relative_to(source).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
        with item.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def snapshot_source(source: Path | str, job_root: Path) -> tuple[Path, str]:
    original = Path(source)
    before = source_hash(original)
    destination = job_root / ("source" + original.suffix.lower())
    if original.is_dir():
        shutil.copytree(original, destination)
    else:
        shutil.copy2(original, destination)
    copied = source_hash(destination)
    after = source_hash(original)
    if before != copied or before != after:
        if destination.is_dir():
            shutil.rmtree(destination, ignore_errors=True)
        else:
            destination.unlink(missing_ok=True)
        raise SourceError("the saved source changed while it was copied")
    return destination, before
