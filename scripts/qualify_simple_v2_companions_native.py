"""Check built Reporter entry points through glyphs-cli with plugins disabled.

This exercises the real SDK and Cocoa selectors. The editor acceptance steps in
src/companions/TESTING.md remain necessary to verify visible canvas redraws.
"""

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from AppKit import NSApp, NSMakeRect, NSMenu, NSMenuItem, NSView
from GlyphsApp import EDIT_MENU, menuTagLookup


ROOT = Path(__file__).resolve().parents[1]


def main():
    # glyphs-cli has no editor menu. Supply only the native Edit menu needed by
    # the Reference Reporter's normal start() callback in this isolated process.
    main_menu = NSMenu.new()
    edit = NSMenuItem.new()
    edit.setTag_(menuTagLookup[EDIT_MENU])
    edit.setSubmenu_(NSMenu.new())
    main_menu.addItem_(edit)
    NSApp.setMainMenu_(main_menu)
    rows = []
    for title, class_name in (("Curve", "GlyphsCurveInspector"),
                              ("Reference", "GlyphsReferenceInspector")):
        resources = ROOT / "build/simple-v2" / ("Glyphs " + title + " Inspector.glyphsReporter") / "Contents/Resources"
        sys.path.insert(0, str(resources))
        spec = importlib.util.spec_from_file_location("gate_" + title.lower(), resources / "plugin.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        owner = getattr(module, class_name).alloc().init()
        assert owner.respondsToSelector_("setController:")
        assert owner.respondsToSelector_("willActivate")
        assert owner.needsExtraMainOutlineDrawingForActiveLayer_(None)
        assert owner.needsExtraMainOutlineDrawingForInactiveLayer_(None)
        row = {"class": class_name, "nativeOutlineEnabled": True, "controllerSelector": True}
        if title == "Reference":
            # The SDK must route only the edited occurrence to our overlay;
            # repeated text can reuse the same native GSLayer object.
            assert owner._foreground
            assert not owner._inactiveLayerForeground and not owner._inactiveLayerBackground
            assert not owner._preview
            row["editedOccurrenceOnly"] = True
        rows.append(row)

    from glyphs_mcp_companions import invalidate_view

    view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 300, 300))
    invalidate_view(SimpleNamespace(font=SimpleNamespace(
        currentTab=SimpleNamespace(graphicView=lambda: view))))
    # An offscreen NSView need not set needsDisplay; visible pixels are tested
    # separately. This verifies PyObjC accepts the native invalidation selector.
    assert view.respondsToSelector_("setNeedsDisplay:")
    result = {"passed": True, "nativeViewSetterAccepted": True, "reporters": rows,
              "scope": "built entry points and native SDK; editor rendering is a separate gate"}
    (ROOT / "build/companions-native-acceptance.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
