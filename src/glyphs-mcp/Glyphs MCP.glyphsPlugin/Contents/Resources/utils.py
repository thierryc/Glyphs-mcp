# encoding: utf-8

from __future__ import division, print_function, unicode_literals
import sys
import socket

# Fix for Glyphs' console output compatibility
# Glyphs' console replaces sys.stdout / sys.stderr with GlyphsOut objects
# that miss the .isatty() method. Uvicorn's logging formatter expects it,
# so we add a stub returning False to avoid runtime errors.
def fix_glyphs_console():
    """Fix Glyphs console compatibility issues."""
    for _stream in (sys.stdout, sys.stderr):
        if not hasattr(_stream, "isatty"):
            setattr(_stream, "isatty", lambda: False)


def find_available_port(start_port=9680, max_attempts=50):
    """Find an available port in the given range.
    
    Args:
        start_port (int): Starting port number to check. Defaults to 9680.
        max_attempts (int): Maximum number of ports to try. Defaults to 50.
    
    Returns:
        int or None: Available port number, or None if no port is available.
    """
    for port in range(start_port, start_port + max_attempts):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind(("127.0.0.1", port))
                return port
            finally:
                s.close()
        except OSError:
            continue
    return None


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
        "execute_code",
        "execute_code_with_context",
        "save_font",
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
        tools = getattr(mcp_instance, "_tools", None) or getattr(mcp_instance, "tools", None)
        if tools and tool_name in tools:
            tool = tools[tool_name]
            doc = getattr(tool, "__doc__", None) or "No description available"
            # Extract first line of docstring for brief description
            return doc.split("\n")[0].strip() if doc else "No description"
        return "No description available"
    except:
        return "No description available"