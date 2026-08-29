"""Exact loaded-code identity for source tests and installed Glyphs runtimes."""

from __future__ import annotations

import hashlib
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from .versions import SERVER_VERSION


@lru_cache(maxsize=1)
def _package_code_hash() -> str:
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".json"}:
            continue
        if "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def loaded_runtime_identity() -> Mapping[str, Any]:
    """Return the plug-in-wide hash when available, otherwise this package hash."""

    try:
        from versioning import get_runtime_info

        installed = get_runtime_info()
        expected_resources = Path(__file__).resolve().parent.parent
        if (
            isinstance(installed, Mapping)
            and installed.get("version") == SERVER_VERSION
            and installed.get("codeHash")
            and Path(str(installed.get("resourcesPath") or "")).resolve()
            == expected_resources
        ):
            return dict(installed)
    except Exception:
        pass
    code_hash = _package_code_hash()
    return {
        "version": SERVER_VERSION,
        "runtimeId": "{}+{}".format(SERVER_VERSION, code_hash[:12]),
        "codeHash": code_hash,
        "resourcesPath": str(Path(__file__).resolve().parent),
        "infoPlistPath": None,
        "pythonVersion": sys.version.split()[0],
    }


__all__ = ["loaded_runtime_identity"]
