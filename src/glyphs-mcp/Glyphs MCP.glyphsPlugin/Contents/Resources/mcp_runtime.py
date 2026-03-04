# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Runtime registry for Glyphs MCP.

This module owns the FastMCP instance. Keeping it in a dedicated module makes it
easy to split tool implementations across multiple files while preserving the
public import contract: `from mcp_tools import mcp`.
"""

# Compatibility shim:
# Some installations may have an older `mcp` package where `mcp.types` does not
# export `Icon` or `AnyFunction`. Newer FastMCP versions import them at runtime.
# Define a minimal fallback so the plug-in can load, and rely on runtime usage
# to treat icons as plain strings.
try:
    import mcp.types as _mcp_types  # type: ignore

    if not hasattr(_mcp_types, "Icon"):
        _mcp_types.Icon = str  # type: ignore[attr-defined]
    if not hasattr(_mcp_types, "AnyFunction"):
        from typing import Any, Callable

        _mcp_types.AnyFunction = Callable[..., Any]  # type: ignore[attr-defined]
except Exception:
    pass

from fastmcp import FastMCP

from versioning import get_plugin_version


mcp = FastMCP(name="Glyphs MCP Server", version=get_plugin_version())

__all__ = ["mcp"]

