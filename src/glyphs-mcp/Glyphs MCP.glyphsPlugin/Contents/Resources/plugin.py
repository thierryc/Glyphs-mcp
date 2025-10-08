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

    original_sys_path = list(sys.path)

    # Load vendored dependencies (and their .pth files).
    site.addsitedir(site_packages)

    # Promote any new entries (including the bundle path itself) ahead of existing ones.
    new_entries = [entry for entry in sys.path if entry not in original_sys_path]
    merged_entries = new_entries + original_sys_path

    seen: set[str] = set()
    sys.path[:] = [entry for entry in merged_entries if not (entry in seen or seen.add(entry))]


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
