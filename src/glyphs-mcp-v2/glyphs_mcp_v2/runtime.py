"""Composition root for the live Glyphs MCP 2.0 read-only slice."""

from __future__ import annotations

from fastmcp import FastMCP

from .adapters.glyphs import GlyphsHostAdapter
from .application import ReadOnlyApplication
from .transport.fastmcp import create_server


def create_glyphs_server() -> FastMCP:
    host = GlyphsHostAdapter.from_running_glyphs()
    application = ReadOnlyApplication(host)
    return create_server(application)


__all__ = ["create_glyphs_server"]
