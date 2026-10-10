"""Read packaged identity once, before accepting requests."""
from pathlib import Path
import json
from glyphs_mcp_protocol.identity import component_identity

IDENTITY = component_identity(Path(__file__).resolve().parents[1])
VERSION = (IDENTITY["release"] or {}).get("version", "unknown")
RELEASE_VERSION = (IDENTITY["release"] or {}).get("releaseVersion", "unknown")

try:
    AGENT_PACKAGE = json.loads((Path(__file__).resolve().parents[1] / 'glyphs-mcp-agent.json').read_text())
    if not isinstance(AGENT_PACKAGE, dict) or AGENT_PACKAGE.get('version') != VERSION:
        raise ValueError('Agent package does not match this sidecar')
except (OSError, ValueError, TypeError):
    AGENT_PACKAGE = None
