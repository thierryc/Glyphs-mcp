"""Saved-source copies and bounded file fingerprints for external artifacts."""
import hashlib
import shutil
from pathlib import Path
from glyphs_mcp_protocol.source_identity import SourceError, source_hash


def file_hash(path: Path) -> str:
    """Fingerprint exact file bytes without loading the complete file in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def font_source_hash(path: Path) -> str:
    """Fingerprint imported sources for Save As without making them job baselines."""
    suffix = path.suffix.lower()
    if suffix not in {".ufo", ".otf", ".ttf"}:
        return source_hash(path)
    if path.is_symlink():
        raise SourceError("the imported source contains a symbolic link")
    if suffix != ".ufo":
        if not path.is_file():
            raise SourceError("the imported source file is unavailable")
        return file_hash(path)
    if not path.is_dir():
        raise SourceError("the imported UFO source folder is unavailable")
    entries = list(path.rglob("*"))
    if any(item.is_symlink() or (not item.is_file() and not item.is_dir()) for item in entries):
        raise SourceError("the UFO contains unsafe filesystem entries")
    files = sorted((item for item in entries if item.is_file()), key=lambda item: item.relative_to(path).as_posix())
    if not files:
        raise SourceError("the imported UFO is empty")
    digest = hashlib.sha256()
    for item in files:
        name = item.relative_to(path).as_posix().encode()
        digest.update(len(name).to_bytes(8, "big")); digest.update(name)
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
