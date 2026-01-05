# encoding: utf-8

from __future__ import division, print_function, unicode_literals
import objc
import threading
from GlyphsApp import Glyphs, EDIT_MENU # type: ignore[import-not-found]
from GlyphsApp.plugins import GeneralPlugin # type: ignore[import-not-found]
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSAlertSecondButtonReturn,
    NSMenuItem,
    NSPanel,
    NSButton,
    NSPasteboard,
    NSPasteboardTypeString,
    NSTextField,
    NSView,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskUtilityWindow,
    NSBackingStoreBuffered,
)
from Foundation import NSNumberFormatter
from starlette.middleware import Middleware

from mcp_tools import mcp
from security import (
    McpDiscoveryMiddleware,
    McpSessionIdMiddleware,
    OriginValidationMiddleware,
    StaticTokenAuthMiddleware,
)
from status_panel_helpers import endpoint_for, is_thread_running, status_text
from utils import get_known_tools, get_tool_info, is_port_available, notify_server_started


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
        self.name_status = Glyphs.localize(
            {
                "en": "Glyphs MCP Server Status…",
                "de": "Glyphs MCP-Server-Status…",
                "fr": "Statut du serveur MCP…",
                "es": "Estado del servidor MCP…",
                "pt": "Status do servidor MCP…",
            }
        )
        # Configuration
        self.default_port = 9680

    @objc.python_method
    def _http_middleware(self):
        """Return security middleware for the embedded HTTP server."""
        middleware = [
            Middleware(McpDiscoveryMiddleware),
            Middleware(McpSessionIdMiddleware),
            Middleware(OriginValidationMiddleware),
        ]

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

        status_item = NSMenuItem.new()
        status_item.setTitle_(self.name_status)
        status_item.setTarget_(self)
        status_item.setAction_(self.ShowStatusWindow_)
        Glyphs.menu[EDIT_MENU].append(status_item)
        self.statusMenuItem = status_item

    @objc.python_method
    def _start_server_on_port(self, port, sender):
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

        notify_server_started(port)
        self._show_startup_message(port)

        # Update menu title to indicate the server is running
        try:
            sender.setTitle_(self.name_running)
        except Exception:
            if hasattr(self, "menuItem"):
                self.menuItem.setTitle_(self.name_running)

        self._refresh_status_panel_if_visible()

    @objc.python_method
    def _prompt_when_default_port_busy(self):
        message = (
            'I can\'t start the MCP server on "9680". '
            "Wait a moment and retry, restart Glyphs, or enter a custom port below."
        )

        alert = NSAlert.alloc().init()
        alert.setMessageText_("Glyphs MCP Server")
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("Retry on 9680")
        alert.addButtonWithTitle_("Start on Custom Port")

        port_field = NSTextField.alloc().initWithFrame_(((0, 0), (220, 24)))
        port_field.setPlaceholderString_("Custom port (1–65535)")
        port_field.setStringValue_("9681")
        try:
            formatter = NSNumberFormatter.alloc().init()
            formatter.setAllowsFloats_(False)
            port_field.setFormatter_(formatter)
        except Exception:
            pass

        accessory = NSView.alloc().initWithFrame_(((0, 0), (220, 24)))
        accessory.addSubview_(port_field)
        alert.setAccessoryView_(accessory)

        response = alert.runModal()
        if response == NSAlertFirstButtonReturn:
            return ("retry", None)
        if response == NSAlertSecondButtonReturn:
            try:
                value = int(port_field.stringValue().strip())
            except Exception:
                return ("custom", None)
            return ("custom", value)
        return (None, None)

    @objc.python_method
    def _show_error(self, text):
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Glyphs MCP Server")
        alert.setInformativeText_(text)
        alert.addButtonWithTitle_("OK")
        try:
            alert.runModal()
        except Exception:
            print(text)

    def StartStopServer_(self, sender):
        """Toggle the local FastMCP server running on localhost.

        Clicking the menu item starts the server (if stopped) or shows status if already running.
        """
        # Check if server is running and provide status
        if hasattr(self, "_server_thread") and self._server_thread.is_alive():
            self._show_server_status()
            return

        while True:
            if is_port_available(self.default_port, host="127.0.0.1"):
                port = self.default_port
                break

            action, custom_port = self._prompt_when_default_port_busy()
            if action == "retry":
                continue
            if action == "custom":
                if custom_port is None:
                    self._show_error("Enter a valid port number (1–65535).")
                    continue
                if not (1 <= custom_port <= 65535):
                    self._show_error("Port must be between 1 and 65535.")
                    continue
                if not is_port_available(custom_port, host="127.0.0.1"):
                    self._show_error(
                        "Port {} is already in use. Choose another port or retry on 9680.".format(
                            custom_port
                        )
                    )
                    continue
                port = custom_port
                break
            return

        try:
            self._start_server_on_port(port, sender)
        except Exception as e:
            print("Failed to start server: {}".format(e))

    def ShowStatusWindow_(self, sender):
        """Open a small floating window with server status and endpoint."""
        try:
            self._ensure_status_panel()
            self._refresh_status_panel()
            self._status_panel.makeKeyAndOrderFront_(None)
        except Exception as e:
            self._show_error("Unable to open MCP status window: {}".format(e))

    @objc.python_method
    def _current_port(self):
        try:
            return int(getattr(self, "_port", self.default_port))
        except Exception:
            return int(self.default_port)

    @objc.python_method
    def _server_is_running(self):
        return is_thread_running(getattr(self, "_server_thread", None))

    @objc.python_method
    def _ensure_status_panel(self):
        if hasattr(self, "_status_panel") and self._status_panel is not None:
            return

        width = 420
        height = 140
        rect = ((0, 0), (width, height))
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskUtilityWindow
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        panel.setTitle_("Glyphs MCP Server")
        panel.setFloatingPanel_(True)

        content = panel.contentView()
        margin = 16
        row_h = 22
        label_w = 80
        value_w = width - margin * 2 - label_w
        y = height - margin - row_h

        status_label = NSTextField.alloc().initWithFrame_(((margin, y), (label_w, row_h)))
        status_label.setStringValue_("Status:")
        status_label.setEditable_(False)
        status_label.setSelectable_(False)
        status_label.setBordered_(False)
        status_label.setDrawsBackground_(False)
        content.addSubview_(status_label)

        status_value = NSTextField.alloc().initWithFrame_(((margin + label_w, y), (value_w, row_h)))
        status_value.setEditable_(False)
        status_value.setSelectable_(True)
        status_value.setBordered_(False)
        status_value.setDrawsBackground_(False)
        content.addSubview_(status_value)

        y -= (row_h + 10)

        endpoint_label = NSTextField.alloc().initWithFrame_(((margin, y), (label_w, row_h)))
        endpoint_label.setStringValue_("Endpoint:")
        endpoint_label.setEditable_(False)
        endpoint_label.setSelectable_(False)
        endpoint_label.setBordered_(False)
        endpoint_label.setDrawsBackground_(False)
        content.addSubview_(endpoint_label)

        endpoint_value = NSTextField.alloc().initWithFrame_(((margin + label_w, y), (value_w, row_h)))
        endpoint_value.setEditable_(False)
        endpoint_value.setSelectable_(True)
        endpoint_value.setBordered_(False)
        endpoint_value.setDrawsBackground_(False)
        content.addSubview_(endpoint_value)

        button_w = 120
        button_h = 28
        button_y = margin
        button_x = width - margin - button_w
        copy_button = NSButton.alloc().initWithFrame_(((button_x, button_y), (button_w, button_h)))
        copy_button.setTitle_("Copy Endpoint")
        copy_button.setTarget_(self)
        copy_button.setAction_(self.CopyEndpoint_)
        content.addSubview_(copy_button)

        self._status_panel = panel
        self._status_field = status_value
        self._endpoint_field = endpoint_value

    @objc.python_method
    def _refresh_status_panel_if_visible(self):
        panel = getattr(self, "_status_panel", None)
        if panel is None:
            return
        try:
            if panel.isVisible():
                self._refresh_status_panel()
        except Exception:
            return

    @objc.python_method
    def _refresh_status_panel(self):
        running = self._server_is_running()
        port = self._current_port()
        endpoint = endpoint_for(port)

        try:
            self._status_field.setStringValue_(status_text(running))
        except Exception:
            pass
        try:
            self._endpoint_field.setStringValue_(endpoint)
        except Exception:
            pass

    def CopyEndpoint_(self, sender):
        """Copy the current endpoint URL to the macOS clipboard."""
        endpoint = endpoint_for(self._current_port())
        try:
            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(endpoint, NSPasteboardTypeString)
        except Exception:
            print("Endpoint:", endpoint)

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
