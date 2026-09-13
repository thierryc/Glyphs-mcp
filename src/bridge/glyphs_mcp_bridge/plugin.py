"""Minimal fixed-height Glyphs palette for the lean bridge."""

from __future__ import annotations

import AppKit as AK
import objc  # type: ignore[import-not-found]
from GlyphsApp import Glyphs, UPDATEINTERFACE  # type: ignore[import-not-found]
from GlyphsApp.plugins import PalettePlugin  # type: ignore[import-not-found]
from Foundation import NSHashTable  # type: ignore[import-not-found]

from glyphs_mcp_bridge import PROJECT_VERSION
from glyphs_mcp_bridge.lifecycle import BRIDGE_VERSION, bridge_lifecycle


PALETTE_HEIGHT = 30


def _label(frame, *, size=12.0):
    field = AK.NSTextField.labelWithString_("")
    field.setFrame_(frame)
    field.setSelectable_(True)
    field.setFont_(AK.NSFont.systemFontOfSize_(size))
    field.setAutoresizingMask_(AK.NSViewWidthSizable)
    return field


class GlyphsMCPBridgePlugin(PalettePlugin):
    @objc.python_method
    def settings(self) -> None:
        self.name = "Glyphs MCP Bridge {} ({})".format(PROJECT_VERSION, BRIDGE_VERSION)
        self.min = PALETTE_HEIGHT
        self.max = PALETTE_HEIGHT
        if bridge_lifecycle.palettes is None:
            bridge_lifecycle.palettes = NSHashTable.weakObjectsHashTable()
        bridge_lifecycle.palettes.addObject_(self)

        self.dialog = AK.NSView.alloc().initWithFrame_(AK.NSMakeRect(0, 0, 220, PALETTE_HEIGHT))
        self._indicator = _label(AK.NSMakeRect(10, 6, 14, 18), size=13.0)
        self._state = _label(AK.NSMakeRect(28, 6, 156, 18), size=13.0)
        self.dialog.addSubview_(self._indicator)
        self.dialog.addSubview_(self._state)
        self._heart = AK.NSButton.alloc().initWithFrame_(AK.NSMakeRect(188, 4, 24, 22))
        self._heart.setImage_(AK.NSImage.imageWithSystemSymbolName_accessibilityDescription_("heart.circle", "Welcome & Support"))
        self._heart.setBordered_(False)
        self._heart.setToolTip_("Welcome & Support")
        self._heart.setAccessibilityLabel_("Welcome & Support")
        self._heart.setAutoresizingMask_(AK.NSViewMinXMargin)
        self._heart.setTarget_(self)
        self._heart.setAction_(self.showWelcome_)
        self.dialog.addSubview_(self._heart)
        self._refresh_palette()

    def showWelcome_(self, sender):
        if bridge_lifecycle.menu_target is not None:
            bridge_lifecycle.menu_target.showWelcome_(sender)

    def currentHeight(self):
        return PALETTE_HEIGHT

    @objc.python_method
    def start(self) -> None:
        if not bridge_lifecycle.stopped:
            bridge_lifecycle.start(Glyphs, UPDATEINTERFACE)

    @objc.python_method
    def _refresh_palette(self) -> None:
        ready = bridge_lifecycle.ready
        self._indicator.setStringValue_("●")
        self._indicator.setTextColor_(AK.NSColor.systemGreenColor() if ready else AK.NSColor.systemRedColor())
        self._state.setStringValue_("Ready" if ready else "Stopped" if bridge_lifecycle.stopped else "Unavailable")
        self._state.setToolTip_(bridge_lifecycle.startup_error)

    @objc.python_method
    def __file__(self) -> str:
        return __file__
