# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import os
import plistlib
import hashlib
import sys
from pathlib import Path


DEFAULT_DOCS_URL = "https://thierryc.github.io/Glyphs-mcp/docs/"


def _find_info_plist_path():
    here = Path(__file__).resolve()
    candidates = [
        # Expected layout: .../Contents/Resources/versioning.py
        here.parents[1] / "Info.plist",
        # Fallback layout if resources are relocated.
        here.parents[2] / "Contents" / "Info.plist",
    ]
    for path in candidates:
        try:
            if path.exists():
                return path
        except Exception:
            continue
    return candidates[0]


def _read_plugin_version():
    info_plist = _find_info_plist_path()
    try:
        with info_plist.open("rb") as f:
            data = plistlib.load(f)
        version = data.get("CFBundleShortVersionString")
        if version:
            return str(version)
    except Exception:
        pass
    return "dev"


def _runtime_source_files():
    resources = Path(__file__).resolve().parent
    try:
        for path in sorted(resources.rglob("*.py")):
            try:
                rel = path.relative_to(resources)
            except Exception:
                continue
            if "__pycache__" in rel.parts or "vendor" in rel.parts:
                continue
            yield rel.as_posix(), path
    except Exception:
        return

    info_plist = _find_info_plist_path()
    try:
        yield "../Info.plist", info_plist
    except Exception:
        return


def _compute_runtime_code_hash():
    digest = hashlib.sha256()
    found = False
    for rel, path in _runtime_source_files() or []:
        try:
            data = path.read_bytes()
        except Exception:
            continue
        found = True
        digest.update(rel.encode("utf-8", "replace"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    if not found:
        return "unknown"
    return digest.hexdigest()


_PLUGIN_VERSION = _read_plugin_version()
_RUNTIME_CODE_HASH = _compute_runtime_code_hash()
_RUNTIME_CODE_HASH_SHORT = _RUNTIME_CODE_HASH[:12] if _RUNTIME_CODE_HASH != "unknown" else "unknown"
_RUNTIME_ID = "{}+{}".format(_PLUGIN_VERSION, _RUNTIME_CODE_HASH_SHORT)


def get_plugin_version():
    """Return the plug-in version loaded with this Python module."""
    return _PLUGIN_VERSION


def get_runtime_info():
    """Return import-time identity for the code currently loaded in Glyphs."""
    return {
        "version": _PLUGIN_VERSION,
        "runtimeId": _RUNTIME_ID,
        "codeHash": _RUNTIME_CODE_HASH,
        "resourcesPath": str(Path(__file__).resolve().parent),
        "infoPlistPath": str(_find_info_plist_path()),
        "pythonVersion": sys.version.split()[0],
    }


def get_runtime_label():
    return _RUNTIME_ID


def get_docs_url_latest():
    """Return the "latest docs" URL (env override + default)."""
    url = os.environ.get("GLYPHS_MCP_DOCS_URL", "").strip()
    return url or DEFAULT_DOCS_URL
