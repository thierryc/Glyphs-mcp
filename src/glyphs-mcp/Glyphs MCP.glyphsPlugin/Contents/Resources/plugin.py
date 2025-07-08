# encoding: utf-8

from __future__ import division, print_function, unicode_literals
import objc
from GlyphsApp import Glyphs, EDIT_MENU
from GlyphsApp.plugins import GeneralPlugin
from AppKit import NSMenuItem
from fastmcp import FastMCP

import json
import socket
import threading

# -----------------------------------------------------------------------------
# Glyphs' console replaces sys.stdout / sys.stderr with GlyphsOut objects
# that miss the .isatty() method.  Uvicorn's logging formatter expects it,
# so we add a stub returning False to avoid runtime errors.
# -----------------------------------------------------------------------------
import sys
for _stream in (sys.stdout, sys.stderr):
    if not hasattr(_stream, "isatty"):
        setattr(_stream, "isatty", lambda: False)

# -----------------------------------------------------------------------------
# FastMCP server declaration + tools
# -----------------------------------------------------------------------------
mcp = FastMCP(name="Glyphs MCP Server", version="1.0.0")

@mcp.tool()
async def list_open_fonts() -> str:
    """Return information about all fonts currently open in Glyphs.

    Returns:
        str: A JSON-encoded list where each item contains:
            familyName (str): Font family name.
            filePath (str|None): Absolute path to the .glyphs file, or None if unsaved.
            masterCount (int): Number of masters in the font.
            instanceCount (int): Number of instances in the font.
            glyphCount (int): Number of glyphs in the font.
            unitsPerEm (int): Units per em (UPM) size.
            versionMajor (int): Font version major.
            versionMinor (int): Font version minor.
    """
    try:
        fonts_info = []
        for font in Glyphs.fonts:
            fonts_info.append({
                "familyName": font.familyName or "",
                "filePath": font.filepath,
                "masterCount": len(font.masters),
                "instanceCount": len(font.instances),
                "glyphCount": len(font.glyphs),
                "unitsPerEm": font.upm,
                "versionMajor": getattr(font, "versionMajor", 0),
                "versionMinor": getattr(font, "versionMinor", 0),
            })
        print(json.dumps(fonts_info))
        return json.dumps(fonts_info)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def get_font_glyphs(font_index: int = 0) -> str:
    """Get all glyphs in a specific font.
    
    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        
    Returns:
        str: JSON-encoded list of glyphs with their properties.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps({"error": f"Font index {font_index} out of range. Available fonts: {len(Glyphs.fonts)}"})
        
        font = Glyphs.fonts[font_index]
        glyphs_info = []
        for glyph in font.glyphs:
            glyphs_info.append({
                "name": glyph.name,
                "unicode": glyph.unicode,
                "category": glyph.category,
                "subCategory": glyph.subCategory,
                "layerCount": len(glyph.layers),
                "leftKerningGroup": glyph.leftKerningGroup,
                "rightKerningGroup": glyph.rightKerningGroup,
                "export": glyph.export
            })
        return json.dumps(glyphs_info)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def get_font_masters(font_index: int = 0) -> str:
    """Get master information for a specific font.
    
    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        
    Returns:
        str: JSON-encoded list of font masters with their properties.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps({"error": f"Font index {font_index} out of range. Available fonts: {len(Glyphs.fonts)}"})
        
        font = Glyphs.fonts[font_index]
        masters_info = []
        for master in font.masters:
            masters_info.append({
                "name": master.name,
                "id": master.id,
                "weight": master.customParameters.get("postscriptSlantAngle", 0),
                "width": master.customParameters.get("postscriptSlantAngle", 0),
                "customName": master.customName,
                "ascender": master.ascender,
                "capHeight": master.capHeight,
                "descender": master.descender,
                "xHeight": master.xHeight
            })
        return json.dumps(masters_info)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def get_font_instances(font_index: int = 0) -> str:
    """Get instance information for a specific font.
    
    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        
    Returns:
        str: JSON-encoded list of font instances with their properties.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps({"error": f"Font index {font_index} out of range. Available fonts: {len(Glyphs.fonts)}"})
        
        font = Glyphs.fonts[font_index]
        instances_info = []
        for instance in font.instances:
            instances_info.append({
                "name": instance.name,
                "weight": instance.weight,
                "width": instance.width,
                "customName": instance.customName,
                "interpolationWeight": instance.interpolationWeight,
                "interpolationWidth": instance.interpolationWidth,
                "active": instance.active,
                "export": instance.export
            })
        return json.dumps(instances_info)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def get_glyph_details(font_index: int = 0, glyph_name: str = "A") -> str:
    """Get detailed information about a specific glyph.
    
    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        glyph_name (str): Name of the glyph. Defaults to "A".
        
    Returns:
        str: JSON-encoded glyph details including layers and components.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps({"error": f"Font index {font_index} out of range. Available fonts: {len(Glyphs.fonts)}"})
        
        font = Glyphs.fonts[font_index]
        glyph = font.glyphs[glyph_name]
        
        if not glyph:
            return json.dumps({"error": f"Glyph '{glyph_name}' not found in font"})
        
        layers_info = []
        for layer in glyph.layers:
            layer_info = {
                "name": layer.name,
                "width": layer.width,
                "leftSideBearing": layer.leftSideBearing,
                "rightSideBearing": layer.rightSideBearing,
                "pathCount": len(layer.paths),
                "componentCount": len(layer.components),
                "anchorCount": len(layer.anchors)
            }
            
            # Add component details
            components = []
            for component in layer.components:
                components.append({
                    "name": component.componentName,
                    "transform": list(component.transform),
                    "automatic": component.automatic
                })
            layer_info["components"] = components
            
            layers_info.append(layer_info)
        
        glyph_details = {
            "name": glyph.name,
            "unicode": glyph.unicode,
            "category": glyph.category,
            "subCategory": glyph.subCategory,
            "script": glyph.script,
            "productionName": glyph.productionName,
            "layers": layers_info
        }
        
        return json.dumps(glyph_details)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def get_font_kerning(font_index: int = 0, master_id: str = None) -> str:
    """Get kerning information for a specific font and master.
    
    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        master_id (str): Master ID. If None, uses the first master.
        
    Returns:
        str: JSON-encoded kerning pairs and values.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps({"error": f"Font index {font_index} out of range. Available fonts: {len(Glyphs.fonts)}"})
        
        font = Glyphs.fonts[font_index]
        
        if master_id is None:
            master_id = font.masters[0].id
        
        kerning_info = []
        kerning = font.kerning.get(master_id, {})
        
        for left_group, right_dict in kerning.items():
            for right_group, value in right_dict.items():
                kerning_info.append({
                    "left": left_group,
                    "right": right_group,
                    "value": value
                })
        
        return json.dumps({
            "masterId": master_id,
            "kerningPairs": kerning_info,
            "pairCount": len(kerning_info)
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

class MCPBridgePlugin(GeneralPlugin):

    @objc.python_method
    def settings(self):
        self.name = Glyphs.localize({
            'en': 'Glyphs MCP Server',
            'de': 'Glyphs MCP Server',
            'fr': 'Glyphs MCP Server',
            'es': 'Glyphs MCP Server',
            'pt': 'Glyphs MCP Server',
        })
        # Configuration
        self.default_port = 9680
        self.max_port_attempts = 50

    @objc.python_method
    def start(self):
        newMenuItem = NSMenuItem.new()
        newMenuItem.setTitle_(self.name)
        newMenuItem.setTarget_(self)
        newMenuItem.setAction_(self.StartStopServer_)
        Glyphs.menu[EDIT_MENU].append(newMenuItem)

    @objc.python_method
    def _find_available_port(self, start_port=None, max_attempts=None):
        """Find an available port in the given range."""
        if start_port is None:
            start_port = self.default_port
        if max_attempts is None:
            max_attempts = self.max_port_attempts
            
        for port in range(start_port, start_port + max_attempts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('127.0.0.1', port))
                    return port
            except OSError:
                continue
        return None

    def StartStopServer_(self, sender):
        """Toggle the local FastMCP server running on localhost.

        Clicking the menu item starts the server (if stopped) or shows status if already running.
        """
        # Check if server is running and provide status
        if hasattr(self, "_server_thread") and self._server_thread.is_alive():
            print(f"✓ Glyphs MCP Server is running on port {getattr(self, '_port', '?')}.")
            print(f"  • SSE endpoint: http://127.0.0.1:{getattr(self, '_port', '?')}/sse")
            print(f"  • Available tools: {len(mcp._tools)} tools")
            print("  • Tools available:")
            for tool_name in sorted(mcp._tools.keys()):
                tool = mcp._tools[tool_name]
                doc = tool.__doc__ or "No description available"
                # Extract first line of docstring for brief description
                brief_desc = doc.split('\n')[0].strip() if doc else "No description"
                print(f"    - {tool_name}: {brief_desc}")
            print("  • To stop: restart Glyphs or use Activity Monitor to kill the process.")
            return

        # Find available port
        port = self._find_available_port()
        if port is None:
            print(f"✗ No free port between {self.default_port} and {self.default_port + self.max_port_attempts - 1}")
            return

        try:
            # Start server in daemon thread
            self._server_thread = threading.Thread(
                target=mcp.run,
                kwargs=dict(
                    transport="sse",
                    host="127.0.0.1",
                    port=port,
                ),
                daemon=True,
            )
            self._server_thread.start()
            self._port = port
            
            print(f"✓ Glyphs MCP Server started successfully!")
            print(f"  • Port: {port}")
            print(f"  • SSE endpoint: http://127.0.0.1:{port}/sse")
            
            # Try to get tools information safely
            try:
                tools = getattr(mcp, '_tools', None) or getattr(mcp, 'tools', None)
                if tools:
                    print(f"  • Available tools: {len(tools)} tools")
                    print("  • Tools available:")
                    for tool_name in sorted(tools.keys()):
                        tool = tools[tool_name]
                        doc = getattr(tool, '__doc__', None) or "No description available"
                        # Extract first line of docstring for brief description
                        brief_desc = doc.split('\n')[0].strip() if doc else "No description"
                        print(f"    - {tool_name}: {brief_desc}")
                else:
                    # Fallback: list the tools we know we defined
                    known_tools = [
                        "list_open_fonts",
                        "get_font_glyphs", 
                        "get_font_masters",
                        "get_font_instances",
                        "get_glyph_details",
                        "get_font_kerning"
                    ]
                    print(f"  • Available tools: {len(known_tools)} tools")
                    print("  • Tools available:")
                    for tool_name in known_tools:
                        print(f"    - {tool_name}")
            except Exception as e:
                print(f"  • Tools information unavailable: {e}")
                
            print("  • Server running in background (daemon thread)")
            
        except Exception as e:
            print(f"✗ Failed to start server: {e}")

    @objc.python_method
    def __file__(self):
        """Please leave this method unchanged"""
        return __file__