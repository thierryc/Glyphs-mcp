# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Aggregator for Glyphs MCP tool registration.

This module preserves the public import contract:

    from mcp_tools import mcp

Tool implementations live in `mcp_tools_*.py` modules and register themselves
via `@mcp.tool()` decorators at import time.
"""

from mcp_runtime import mcp

# Import tool modules for registration side effects.
import mcp_tools_components  # noqa: F401
import mcp_tools_compensated_tuning  # noqa: F401
import mcp_tools_export  # noqa: F401
import mcp_tools_font  # noqa: F401
import mcp_tools_glyph_ops  # noqa: F401
import mcp_tools_kerning  # noqa: F401
import mcp_tools_paths  # noqa: F401
import mcp_tools_selection  # noqa: F401
import mcp_tools_smoothness  # noqa: F401
import mcp_tools_spacing  # noqa: F401

__all__ = ["mcp"]

