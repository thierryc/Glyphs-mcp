"""Compatibility import for shared typed preparation."""
import sys
from glyphs_mcp_protocol.preparation import dimensions as _implementation
sys.modules[__name__] = _implementation
