"""Compatibility import for shared typed preparation."""
import sys
from glyphs_mcp_protocol.preparation import outline as _implementation
sys.modules[__name__] = _implementation
