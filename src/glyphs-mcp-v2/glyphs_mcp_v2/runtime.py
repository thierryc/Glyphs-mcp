"""Composition root for the live Glyphs MCP 2.0 runtime."""

from __future__ import annotations

from fastmcp import FastMCP

from .adapters.document import GlyphsDocumentHost
from .application import GlyphsMCPApplication
from .canonical_tree import CanonicalFontTree, MemoryObjectStore
from .change_history import ChangeHistory
from .transport.fastmcp import create_server


_ACTIVE_HOST: GlyphsDocumentHost | None = None
_ACTIVE_APPLICATION: GlyphsMCPApplication | None = None


def active_host() -> GlyphsDocumentHost | None:
    return _ACTIVE_HOST


def active_application() -> GlyphsMCPApplication | None:
    return _ACTIVE_APPLICATION


def active_history() -> ChangeHistory | None:
    application = active_application()
    return application.history if application is not None else None


def create_glyphs_server() -> FastMCP:
    global _ACTIVE_APPLICATION, _ACTIVE_HOST
    host = GlyphsDocumentHost.from_running_glyphs()
    # Content-addressed objects live only for the unsaved app session. They are
    # detached Python bytes, structurally shared, and pruned on save; no disk IO
    # or hashing happens in Reporter callbacks.
    history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
    history.reset_for_schema_change(5, 6)
    application = GlyphsMCPApplication(host, history=history)
    _ACTIVE_HOST = host
    _ACTIVE_APPLICATION = application
    return create_server(application)


__all__ = ["active_application", "active_history", "active_host", "create_glyphs_server"]
