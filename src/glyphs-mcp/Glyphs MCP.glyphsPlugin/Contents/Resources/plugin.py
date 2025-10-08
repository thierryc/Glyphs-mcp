# encoding: utf-8

from __future__ import division, print_function, unicode_literals

# Ensure vendored dependencies are importable before anything else.
import os
import site
import sys


def _bootstrap_site_packages() -> None:
    """Add this bundle's vendored site-packages to sys.path."""
    bundle_dir = os.path.dirname(__file__)
    site_packages = os.path.realpath(os.path.join(bundle_dir, "site-packages"))
    if not os.path.isdir(site_packages):
        return

    # Load vendored dependencies (and their .pth files), then ensure they win precedence.
    site.addsitedir(site_packages)

    vendor_entries: list[str] = []
    other_entries: list[str] = []
    seen: set[str] = set()

    for path_entry in sys.path:
        if path_entry in seen:
            continue
        seen.add(path_entry)
        if os.path.realpath(path_entry) == site_packages:
            vendor_entries.append(path_entry)
        else:
            other_entries.append(path_entry)

    sys.path[:] = vendor_entries + other_entries


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
