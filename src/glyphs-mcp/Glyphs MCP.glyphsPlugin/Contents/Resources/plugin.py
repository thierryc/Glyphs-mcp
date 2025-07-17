# encoding: utf-8

from __future__ import division, print_function, unicode_literals

# Import utility functions and apply fixes
from utils import fix_glyphs_console
fix_glyphs_console()

# Import MCP tools (this registers all the tools)
from mcp_tools import mcp

# Import code execution tools (this registers the execution tools)
import code_execution

# Import and initialize the plugin
from glyphs_plugin import MCPBridgePlugin


