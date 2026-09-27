"""Immutable copying for saved Glyphs sources."""
import shutil
from pathlib import Path
from glyphs_mcp_protocol.source_identity import SourceError, source_hash


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
