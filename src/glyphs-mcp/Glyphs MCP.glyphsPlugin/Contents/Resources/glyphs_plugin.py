# encoding: utf-8

from __future__ import division, print_function, unicode_literals
import objc
import threading
from GlyphsApp import Glyphs, EDIT_MENU # type: ignore[import-not-found]
from GlyphsApp.plugins import GeneralPlugin # type: ignore[import-not-found]
from AppKit import NSMenuItem
from starlette.middleware import Middleware

from mcp_tools import mcp
from security import OriginValidationMiddleware, StaticTokenAuthMiddleware
from utils import find_available_port, get_known_tools, get_tool_info


class MCPBridgePlugin(GeneralPlugin):

    @objc.python_method
    def settings(self):
        # Localized menu titles
        self.name_start = Glyphs.localize(
            {
                "en": "Start Glyphs MCP Server",
                "de": "Glyphs MCP-Server starten",
                "fr": "Démarrer le serveur MCP",
                "es": "Iniciar el servidor MCP",
                "pt": "Iniciar o servidor Glyphs MCP",
            }
        )
        self.name_running = Glyphs.localize(
            {
                "en": "Glyphs MCP Server is running",
                "de": "Glyphs MCP-Server läuft",
                "fr": "Le serveur MCP est en cours d'exécution",
                "es": "El servidor MCP está en ejecución",
                "pt": "O servidor MCP está em execução",
            }
        )
        # Configuration
        self.default_port = 9680
        self.max_port_attempts = 50

    @objc.python_method
    def _http_middleware(self):
        """Return security middleware for the embedded HTTP server."""
        middleware = [Middleware(OriginValidationMiddleware)]

        # Always include token middleware; it is a no-op unless the env token is set.
        middleware.append(Middleware(StaticTokenAuthMiddleware))
        return middleware

    @objc.python_method
    def start(self):
        newMenuItem = NSMenuItem.new()
        newMenuItem.setTitle_(self.name_start)
        # Keep a reference so we can update the label later
        self.menuItem = newMenuItem
        newMenuItem.setTarget_(self)
        newMenuItem.setAction_(self.StartStopServer_)
        Glyphs.menu[EDIT_MENU].append(newMenuItem)

    def StartStopServer_(self, sender):
        """Toggle the local FastMCP server running on localhost.

        Clicking the menu item starts the server (if stopped) or shows status if already running.
        """
        # Check if server is running and provide status
        if hasattr(self, "_server_thread") and self._server_thread.is_alive():
            self._show_server_status()
            return

        # Find available port
        port = find_available_port(self.default_port, self.max_port_attempts)
        if port is None:
            print(
                "No free port between {} and {}".format(
                    self.default_port, self.default_port + self.max_port_attempts - 1
                )
            )
            return

        try:
            # Start server in daemon thread
            self._server_thread = threading.Thread(
                target=mcp.run,
                kwargs=dict(
                    transport="http",
                    host="127.0.0.1",
                    port=port,
                    middleware=self._http_middleware(),
                ),
                daemon=True,
            )
            self._server_thread.start()
            self._port = port

            self._show_startup_message(port)

            # Update menu title to indicate the server is running
            try:
                sender.setTitle_(self.name_running)
            except Exception:
                # Fallback in case sender is not the menu item
                if hasattr(self, "menuItem"):
                    self.menuItem.setTitle_(self.name_running)

        except Exception as e:
            print("Failed to start server: {}".format(e))

    @objc.python_method
    def _show_server_status(self):
        """Show the current server status."""
        print(
            "Glyphs MCP Server is running on port {}.".format(getattr(self, '_port', '?'))
        )
        print(
            "  HTTP endpoint: http://127.0.0.1:{}".format(getattr(self, '_port', '?'))
        )
        
        # Try to get tools information safely
        try:
            # Try multiple possible attribute names for tools
            tools = None
            for attr_name in ["_tools", "tools", "_tool_registry", "tool_registry", "_handlers"]:
                tools = getattr(mcp, attr_name, None)
                if tools:
                    break
            if tools:
                print("  Available tools: {} tools".format(len(tools)))
                print("  Tools available:")
                for tool_name in sorted(tools.keys()):
                    brief_desc = get_tool_info(mcp, tool_name)
                    print("    - {}: {}".format(tool_name, brief_desc))
            else:
                # Fallback: list the tools we know we defined
                known_tools = get_known_tools()
                print("  Available tools: {} tools".format(len(known_tools)))
                print("  Tools available:")
                for tool_name in known_tools:
                    print("    - {}".format(tool_name))
        except Exception as e:
            print("  Tools information unavailable: {}".format(e))
        
        print(
            "  To stop: restart Glyphs or use Activity Monitor to kill the process."
        )

    @objc.python_method
    def _show_startup_message(self, port):
        """Show startup success message."""
        print("Glyphs MCP Server started successfully!")
        print("  Port: {}".format(port))
        print("  HTTP endpoint: http://127.0.0.1:{}".format(port))

        # Try to get tools information safely
        try:
            # Try multiple possible attribute names for tools
            tools = None
            for attr_name in ["_tools", "tools", "_tool_registry", "tool_registry", "_handlers"]:
                tools = getattr(mcp, attr_name, None)
                if tools:
                    break
            if tools:
                print("  Available tools: {} tools".format(len(tools)))
                print("  Tools available:")
                for tool_name in sorted(tools.keys()):
                    brief_desc = get_tool_info(mcp, tool_name)
                    print("    - {}: {}".format(tool_name, brief_desc))
            else:
                # Fallback: list the tools we know we defined
                known_tools = get_known_tools()
                print("  Available tools: {} tools".format(len(known_tools)))
                print("  Tools available:")
                for tool_name in known_tools:
                    print("    - {}".format(tool_name))
        except Exception as e:
            print("  Tools information unavailable: {}".format(e))

        print("  Server running in background (daemon thread)")

    @objc.python_method
    def __file__(self):
        """Please leave this method unchanged"""
        return __file__
