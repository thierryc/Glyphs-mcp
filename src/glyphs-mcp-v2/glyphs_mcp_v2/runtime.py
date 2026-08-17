"""Composition root for the live Glyphs MCP 2.0 runtime."""

from __future__ import annotations

from fastmcp import FastMCP

from .adapters.document import GlyphsDocumentHost
from .application import GlyphsMCPApplication
from .transport.fastmcp import create_server


def create_glyphs_server() -> FastMCP:
    host = GlyphsDocumentHost.from_running_glyphs()
    application = GlyphsMCPApplication(host)
    return create_server(application)


__all__ = ["create_glyphs_server"]
