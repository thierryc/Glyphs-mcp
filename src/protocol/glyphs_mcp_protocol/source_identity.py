"""Streaming identity for saved Glyphs sources, shared by native restoration."""

from __future__ import annotations

import hashlib
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
