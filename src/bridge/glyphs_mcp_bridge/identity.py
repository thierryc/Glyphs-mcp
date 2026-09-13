"""Cached bundle fingerprint and native host evidence."""
from pathlib import Path
from glyphs_mcp_protocol.identity import component_identity

IDENTITY = component_identity(Path(__file__).resolve().parents[3])
VERSION = (IDENTITY["release"] or {}).get("version", "unknown")


def host_identity():
    try:
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        return {"identifier": bundle.bundleIdentifier(),
                "version": bundle.objectForInfoDictionaryKey_("CFBundleShortVersionString"),
                "build": bundle.objectForInfoDictionaryKey_("CFBundleVersion")}
    except Exception as exc:
        return {"identifier": None, "version": None, "build": None,
                "error": str(exc)}
