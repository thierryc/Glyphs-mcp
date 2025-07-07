# encoding: utf-8

from __future__ import division, print_function, unicode_literals
import objc
from GlyphsApp import Glyphs, EDIT_MENU
from GlyphsApp.plugins import GeneralPlugin
from AppKit import NSMenuItem
from fastmcp import FastMCP

import json

# -----------------------------------------------------------------------------
# Glyphs’ console replaces sys.stdout / sys.stderr with GlyphsOut objects
# that miss the .isatty() method.  Uvicorn’s logging formatter expects it,
# so we add a stub returning False to avoid runtime errors.
# -----------------------------------------------------------------------------
import sys
for _stream in (sys.stdout, sys.stderr):
    if not hasattr(_stream, "isatty"):
        setattr(_stream, "isatty", lambda: False)

# -----------------------------------------------------------------------------
# FastMCP server declaration + example tool
# -----------------------------------------------------------------------------
mcp = FastMCP(name="Glyphs MCP Server", version="1.0.0")

@mcp.tool()
async def tool_name(param1: str, param2: bool = True) -> str:
	"""Tool description for Claude.

	Args:
		param1: Description of parameter.
		param2: Optional parameter with default.
	"""
	result = {"param1": param1, "param2": param2}
	return json.dumps(result)


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

	@objc.python_method
	def start(self):
		if Glyphs.versionNumber >= 3.3:
			newMenuItem = NSMenuItem(self.name, callback=self.StartStopServer_, target=self)
		else:
			newMenuItem = NSMenuItem(self.name, self.StartStopServer_)
		Glyphs.menu[EDIT_MENU].append(newMenuItem)

	def StartStopServer_(self, sender):
		"""Toggle the local FastMCP server running on localhost.

		Clicking the menu item starts the server (if stopped) or notifies if already running.
		"""
		import threading

		# If no server thread exists or it has died, spin up a new one
		if not getattr(self, "_server_thread", None) or not self._server_thread.is_alive():
			start_port, max_attempts = 9680, 50
			for port in range(start_port, start_port + max_attempts):
				try:
					# FastMCP's canonical launcher is `run()`
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
					break
				except OSError:
					continue
			else:
				print(
					f"No free port between {start_port} and {start_port + max_attempts - 1}"
				)
				return

			print(f"Glyphs MCP server running via FastMCP on port {self._port}.")
			print(f"  • http://127.0.0.1:{self._port}/sse")
		else:
			print(
				f"Server already running on port {getattr(self, '_port', '?')}. "
				"Restart Glyphs to stop it."
			)

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
