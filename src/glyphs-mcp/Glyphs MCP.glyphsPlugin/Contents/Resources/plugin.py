# encoding: utf-8

from __future__ import division, print_function, unicode_literals

# Ensure vendored dependencies are importable before anything else.
import os
import site
import sys


def _bootstrap_site_packages() -> None:
    """Add this bundle's vendored site-packages to sys.path."""
    bundle_dir = os.path.dirname(__file__)
    site_packages = os.path.join(bundle_dir, "site-packages")
    if os.path.isdir(site_packages) and site_packages not in sys.path:
        site.addsitedir(site_packages)


_bootstrap_site_packages()

# Import utility functions and apply fixes
from utils import fix_glyphs_console
fix_glyphs_console()

# Import MCP tools (this registers all the tools)
from mcp_tools import mcp

# Import code execution tools (this registers the execution tools)
import code_execution

# Import bundled documentation resources so they are registered with FastMCP
import documentation_resources  # noqa: F401
# Import prompt examples so they are registered
import prompt_examples  # noqa: F401

# Import and initialize the plugin
from glyphs_plugin import MCPBridgePlugin

