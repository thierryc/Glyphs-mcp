# encoding: utf-8
"""Bundle entry point. Runtime packages are copied here by the builder."""

from glyphs_mcp_bridge.plugin import GlyphsMCPBridgePlugin

from glyphs_mcp_bridge.server_panel import GlyphsMCPServerPlugin

__all__ = ["GlyphsMCPBridgePlugin", "GlyphsMCPServerPlugin"]
