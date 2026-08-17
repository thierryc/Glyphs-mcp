"""Composition root for the live Glyphs MCP 2.0 runtime."""

from __future__ import annotations

from fastmcp import FastMCP

from .adapters.document import GlyphsDocumentHost
from .application import GlyphsMCPApplication
from .transport.fastmcp import create_server


_ACTIVE_HOST: GlyphsDocumentHost | None = None


def active_host() -> GlyphsDocumentHost | None:
    return _ACTIVE_HOST


def create_glyphs_server() -> FastMCP:
    global _ACTIVE_HOST
    host = GlyphsDocumentHost.from_running_glyphs()
    _ACTIVE_HOST = host
    application = GlyphsMCPApplication(host)
    return create_server(application)


__all__ = ["active_host", "create_glyphs_server"]
