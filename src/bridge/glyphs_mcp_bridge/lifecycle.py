"""One bridge per Glyphs process, shared by every document's palette."""

from __future__ import annotations

import os
from threading import Thread

from glyphs_mcp_companions import attach_registry, detach_registry
from glyphs_mcp_protocol import load_or_create_token

from .core import BridgeCore
from .glyphs_adapter import GlyphsAdapter
from .http_server import BridgeHTTPServer
from .main_thread import CocoaMainThread
from .identity import VERSION


BRIDGE_VERSION = VERSION
DEFAULT_PORT = 9681


class BridgeLifecycle:
    def __init__(self) -> None:
        self.server = None
        self.core = None
        self.adapter = None
        self.startup_error = None
        self.port = None
        self.callback_registered = False
        self.palettes = None
        self.menu_item = None
        # Cocoa menu targets are not retained. Keep the application-wide
        # settings controller alive even without a document window.
        self.menu_target = None
        self.stopped = False

    @property
    def ready(self) -> bool:
        return bool(
            self.server is not None
            and self.server.thread is not None
            and self.server.thread.is_alive()
        )

    def start(self, glyphs, update_event) -> None:
        self.stopped = False
        if not self.ready:
            self._shutdown(glyphs)
            try:
                token = load_or_create_token()
                port = int(os.environ.get("GLYPHS_MCP_BRIDGE_PORT", str(DEFAULT_PORT)))
                main = CocoaMainThread()
                self.adapter = GlyphsAdapter(glyphs)
                self.core = BridgeCore(self.adapter, main.schedule)
                self.server = BridgeHTTPServer(self.core, main, token=token, port=port)
                self.server.start()
                self.port = self.server.address[1]
                glyphs.addCallback(self.adapter.note_change, update_event)
                self.callback_registered = True
                attach_registry(self.core.companions)
                self.startup_error = None
            except Exception as exc:
                self.startup_error = str(exc) or exc.__class__.__name__
                self._shutdown(glyphs)
                print("[Glyphs MCP Bridge] Unavailable: " + self.startup_error)
        self.refresh()

    def refresh(self):
        for palette in self.palettes.allObjects() if self.palettes is not None else ():
            palette._refresh_palette()

    def stop(self, glyphs):
        if self.core is not None:
            if self.core.status()["activeOperations"]:
                raise RuntimeError("Wait for the current font operation to finish, then stop the server.")
            self.core.paused = True
        self.stopped = True
        self.startup_error = None
        self._shutdown(glyphs)
        self.refresh()

    def _shutdown(self, glyphs) -> None:
        if self.callback_registered:
            glyphs.removeCallback(self.adapter.note_change)
        self.callback_registered = False
        if self.core is not None:
            detach_registry(self.core.companions)
        server = self.server
        self.server = None
        self.port = None
        if server is not None:
            if server.thread is not None and server.thread.is_alive():
                Thread(target=server.stop, name="glyphs-bridge-stop", daemon=True).start()
            else:
                server.server.server_close()
        self.core = None
        self.adapter = None


# PalettePlugin.start runs for each palette instance. The imported package
# module, unlike a palette, lives for the application's lifetime.
bridge_lifecycle = BridgeLifecycle()
