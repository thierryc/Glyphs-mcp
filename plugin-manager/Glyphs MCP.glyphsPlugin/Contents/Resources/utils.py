# encoding: utf-8

from __future__ import division, print_function, unicode_literals
import sys
import socket

try:
    from GlyphsApp import Message  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - Glyphs not available outside app
    Message = None

MCP_SERVER_URL = "http://127.0.0.1:9680/mcp/"
GITHUB_REPO_URL = "https://github.com/thierryc/glyphs-mcp"

# Fix for Glyphs' console output compatibility
# Glyphs' console replaces sys.stdout / sys.stderr with GlyphsOut objects
# that miss the .isatty() method. Uvicorn's logging formatter expects it,
# so we add a stub returning False to avoid runtime errors.
def fix_glyphs_console():
    """Fix Glyphs console compatibility issues."""
    for _stream in (sys.stdout, sys.stderr):
        if not hasattr(_stream, "isatty"):
            setattr(_stream, "isatty", lambda: False)


def is_port_available(port, host="127.0.0.1"):
    """Return True if we can bind to host:port."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, int(port)))
            return True
        finally:
            s.close()
    except Exception:
        return False


def notify_server_started(port, host="127.0.0.1"):
    """Display a lightweight dialog when the server starts (best effort)."""
    if not Message:
        return
    try:
        Message(
            "Glyphs MCP Server",
            "MCP server enabled on\nhttp://{0}:{1}/mcp/\n\nhttps://ap.cx/gmcp\v".format(
                host, int(port)
            ),
            "Go",
        )
    except Exception:
        return


def get_known_tools():
    """Return active names from the authoritative production tool catalog."""

    from tool_catalog import active_entries

    return [entry.name for entry in active_entries()]


def get_tool_info(mcp_instance, tool_name):
    """Get information about a specific tool.
    
    Args:
        mcp_instance: The FastMCP instance
        tool_name (str): Name of the tool
        
    Returns:
        str: Brief description of the tool
    """
    try:
        tools = get_mcp_tool_registry(mcp_instance)
        
        if tools and tool_name in tools:
            tool = tools[tool_name]
            doc = getattr(tool, "__doc__", None) or "No description available"
            # Extract first line of docstring for brief description
            return doc.split("\n")[0].strip() if doc else "No description"
        return "No description available"
    except:
        return "No description available"


def get_mcp_tool_registry(mcp_instance):
    """Return the internal FastMCP tool registry dict if discoverable."""
    if mcp_instance is None:
        return None

    # FastMCP has exposed the registry both directly on the server and through
    # a ToolManager. Prefer the manager because it is the authoritative source
    # for FastMCP 2.12 protocol list/call handling; keep direct layouts only as
    # compatibility fallbacks for older runtimes.
    containers = []
    for manager_name in ["_tool_manager", "tool_manager"]:
        try:
            manager = getattr(mcp_instance, manager_name, None)
        except Exception:
            manager = None
        if manager is not None and all(manager is not container for container in containers):
            containers.append(manager)
    containers.append(mcp_instance)

    for container in containers:
        for attr_name in ["_tools", "tools", "_tool_registry", "tool_registry", "_handlers"]:
            try:
                candidate = getattr(container, attr_name, None)
            except Exception:
                candidate = None
            if isinstance(candidate, dict):
                return candidate
    return None


def replace_tool_registry_in_place(registry_dict, new_tools):
    """Replace a tool registry dict in place, preserving references."""
    if registry_dict is None or not isinstance(registry_dict, dict):
        return
    if new_tools is None or not isinstance(new_tools, dict):
        new_tools = {}
    registry_dict.clear()
    registry_dict.update(new_tools)
