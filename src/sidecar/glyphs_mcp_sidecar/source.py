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
