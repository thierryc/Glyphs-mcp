"""Reproducible engine/geometry records shared by companion and skill bundles."""
from pathlib import Path
import hashlib
import json
from . import ENGINE_VERSION, SUPERTOOL_REVISION


def record(base):
    base = Path(base)
    files = {}
    for name in ("curve_repair", "curve_core"):
        for path in sorted((base / name).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo") and path.name != ".DS_Store":
                files[path.relative_to(base).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not files: raise ValueError("Repair engine source is missing")
    return {"schemaVersion": 1, "engineVersion": ENGINE_VERSION,
            "upstreamRevision": SUPERTOOL_REVISION, "files": files,
            "sourceDigest": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}


def validate(base, expected):
    observed = record(base)
    if observed != expected: raise ValueError("Repair engine bundles differ from the pinned source record")
    return observed
