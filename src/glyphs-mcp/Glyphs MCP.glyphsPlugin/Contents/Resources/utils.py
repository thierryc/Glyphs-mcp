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
    """Get a list of known MCP tools defined in the plugin.
    
    Returns:
        list: List of tool names.
    """
    return [
        "list_open_fonts",
        "get_font_glyphs",
        "get_font_masters",
        "get_font_instances",
        "get_glyph_details",
        "get_font_kerning",
        "create_glyph",
        "delete_glyph",
        "update_glyph_properties",
        "copy_glyph",
        "update_glyph_metrics",
        "get_glyph_components",
        "add_component_to_glyph",
        "add_anchor_to_glyph",
        "set_kerning_pair",
        "get_selected_glyphs",
        "get_selected_font_and_master",
        "get_glyph_paths",
        "set_glyph_paths",
        "execute_code",
        "execute_code_with_context",
        "save_font",
        "review_spacing",
        "apply_spacing",
        "set_spacing_params",
        "set_spacing_guides",
        "ExportDesignspaceAndUFO",
        "docs_search",
        "docs_get",
    ]


def get_tool_info(mcp_instance, tool_name):
    """Get information about a specific tool.
    
    Args:
        mcp_instance: The FastMCP instance
        tool_name (str): Name of the tool
        
    Returns:
        str: Brief description of the tool
    """
    try:
        # Try multiple possible attribute names for tools
        tools = None
        for attr_name in ["_tools", "tools", "_tool_registry", "tool_registry", "_handlers"]:
            tools = getattr(mcp_instance, attr_name, None)
            if tools:
                break
        
        if tools and tool_name in tools:
            tool = tools[tool_name]
            doc = getattr(tool, "__doc__", None) or "No description available"
            # Extract first line of docstring for brief description
            return doc.split("\n")[0].strip() if doc else "No description"
        return "No description available"
    except:
        return "No description available"
