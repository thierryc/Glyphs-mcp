# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import os
import plistlib
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


def get_plugin_version():
    """Return the plug-in version from Info.plist.

    Source of truth: CFBundleShortVersionString in the plug-in bundle.
    """
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


def get_docs_url_latest():
    """Return the "latest docs" URL (env override + default)."""
    url = os.environ.get("GLYPHS_MCP_DOCS_URL", "").strip()
    return url or DEFAULT_DOCS_URL
