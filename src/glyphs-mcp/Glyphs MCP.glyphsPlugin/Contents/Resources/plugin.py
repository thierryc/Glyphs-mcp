# encoding: utf-8

from __future__ import division, print_function, unicode_literals

# Import utility functions and apply fixes
from utils import fix_glyphs_console
fix_glyphs_console()

# Import MCP tools (this registers all the tools)
from mcp_tools import mcp

# Import code execution tools (this registers the execution tools)
import code_execution

# Import bundled documentation resources so they are registered with FastMCP
import documentation_resources  # noqa: F401

# Import and initialize the plugin
from glyphs_plugin import MCPBridgePlugin


