"""Initialization-time file fingerprints; no claim about in-memory code."""

import hashlib
import json
import os
from pathlib import Path

RELEASE_FILE = "glyphs-mcp-release.json"
RELEASE_FIELDS = ("version", "releaseVersion", "channel", "betaNumber", "installerBuild")


def payload_hash(root):
    """Same framed relative paths as the installer; exclude generated caches."""
    root = Path(root)
    if not root.is_dir():
        raise OSError("Component directory unavailable")
    files = []
    def failed(error):
        raise error
    for directory, dirs, names in os.walk(root, onerror=failed):
        dirs[:] = sorted(name for name in dirs if name != "__pycache__")
        for name in names:
            if name.endswith((".pyc", ".pyo")) or name == ".DS_Store":
                continue
            path = Path(directory) / name
            if path.is_symlink():
                raise OSError("Symlink in component fingerprint")
            files.append(path)
        if any((Path(directory) / name).is_symlink() for name in dirs):
            raise OSError("Symlink directory in component fingerprint")
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def component_identity(root):
    result = {"release": None, "runtimeId": None, "codeHash": None,
              "identityEvidence": "unavailable"}
    try:
        release = json.loads((Path(root) / RELEASE_FILE).read_text(encoding="utf-8"))
        if not all(key in release for key in RELEASE_FIELDS):
            raise ValueError("Incomplete release metadata")
        if not all(isinstance(release[key], str) and release[key] for key in
                   ("version", "releaseVersion", "channel")):
            raise ValueError("Invalid release metadata")
        if any(type(release[key]) is not int or release[key] < 0 for key in
               ("betaNumber", "installerBuild")):
            raise ValueError("Invalid release build")
        result["release"] = {key: release[key] for key in RELEASE_FIELDS}
        code_hash = payload_hash(root)
        result.update(codeHash=code_hash,
                      runtimeId=release["releaseVersion"] + "+" + code_hash[7:19],
                      identityEvidence="initialization-time file fingerprint")
    except (OSError, ValueError, TypeError) as exc:
        result["identityError"] = str(exc)
    return result
