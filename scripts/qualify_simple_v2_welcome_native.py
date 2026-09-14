"""Native welcome construction; visible first-launch acceptance is separate."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
resources=ROOT/'build/simple-v2/Glyphs MCP Bridge.glyphsPlugin/Contents/Resources'
sys.path.insert(0,str(resources))
from AppKit import NSApp, NSImage
from glyphs_mcp_bridge.server_panel import GlyphsMCPServerPlugin

controller=GlyphsMCPServerPlugin.alloc().init()
controller.settings()
window=controller._create_window('welcome_panel.json')
assert window.title()=='Welcome to Glyphs MCP'
assert window.contentView().frame().size.width==440
assert window.contentView().frame().size.height==370
buttons=[v for v in window.contentView().subviews() if hasattr(v,'title')]
assert {str(v.title()) for v in buttons} >= {'Documentation','GitHub Issues','Support','Close'}
assert NSImage.imageWithSystemSymbolName_accessibilityDescription_('heart.circle','Welcome & Support') is not None
assert NSApp.modalWindow() is not window
window.close()
result={'nativePlaceholderConstruction':True,'nativeHeartSymbol':True,'nonmodal':True,'scope':'Native Cocoa construction; visible app acceptance remains separate'}
(ROOT/'build/welcome-native.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
