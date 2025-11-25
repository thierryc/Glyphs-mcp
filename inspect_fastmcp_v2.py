
import sys
import site
import os
from pathlib import Path

# Add likely site-packages to path
sys.path.append(site.getusersitepackages())
# Add Glyphs scripts site-packages if it exists (standard location)
glyphs_site = Path.home() / "Library" / "Application Support" / "Glyphs 3" / "Scripts" / "site-packages"
if glyphs_site.exists():
    sys.path.append(str(glyphs_site))

try:
    from fastmcp import FastMCP
    print(f"FastMCP found: {FastMCP}")
    
    mcp = FastMCP("Test")
    
    # Check for configuration options related to paths
    print("Dir(mcp):", dir(mcp))
    
    # Check if run method signature has path options
    import inspect
    print("Run signature:", inspect.signature(mcp.run))
    
    # Check if it has an asgi_app property or method
    if hasattr(mcp, 'asgi_app'):
        print("Has asgi_app")
    
    # Check defaults
    if hasattr(mcp, 'settings'):
        print("Settings:", mcp.settings)

except ImportError:
    print("FastMCP not found in likely locations")
except Exception as e:
    print(f"Error: {e}")
