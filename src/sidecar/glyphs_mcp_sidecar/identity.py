"""Read packaged identity once, before accepting requests."""
from pathlib import Path
from glyphs_mcp_protocol.identity import component_identity

IDENTITY = component_identity(Path(__file__).resolve().parents[1])
VERSION = (IDENTITY["release"] or {}).get("version", "unknown")
RELEASE_VERSION = (IDENTITY["release"] or {}).get("releaseVersion", "unknown")
