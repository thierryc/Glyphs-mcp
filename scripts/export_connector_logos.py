#!/usr/bin/env python3
"""Export connection logos from LitSquare Brands without changing the font source.

Requires glyphsLib and fontTools. Re-run with --source pointing to
litsquare-symbols/sf-symbols/litsquare-brands.glyphspackage.
"""
import argparse
import hashlib
import json
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from glyphsLib.parser import Parser

from export_desktop_icon import draw

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "macos-installer/GlyphsMCPInstaller/Resources"
LOGOS = {
    "codex": "CodexLogo",
    "claudecode": "ClaudeCodeLogo",
    "claude": "ClaudeLogo",
    "cursor": "CursorLogo",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def export(source):
    font_info = (source / "fontinfo.plist").read_bytes()
    font = Parser().parse(font_info.decode())
    master = next(item for item in font["fontMaster"] if item["name"] == "Regular")
    provenance = {
        "source": "litsquare-symbols/sf-symbols/litsquare-brands.glyphspackage",
        "repository": "https://github.com/thierryc/litsquare-symbols",
        "author": "Thierry Charbonnel / LitSquare",
        "license": "SIL Open Font License 1.1",
        "master": master["name"],
        "masterId": master["id"],
        "fontInfoSHA256": sha256(font_info),
        "logos": [],
    }
    for name, asset in LOGOS.items():
        glyph_data = (source / f"glyphs/litsquare.{name}.glyph").read_bytes()
        glyph = Parser().parse(glyph_data.decode())
        assert glyph["glyphname"] == f"litsquare.{name}"
        layer = next(item for item in glyph["layers"] if item["layerId"] == master["id"])
        bounds, outline = BoundsPen(None), SVGPathPen(None)
        for shape in layer["shapes"]:
            assert shape["closed"] == 1 and "nodes" in shape
            assert not shape.get("attr", {}).get("mask"), "Masked contours need separate export"
            # Glyphs 4 may append per-node metadata after x, y, and segment type.
            nodes = [node[:3] for node in shape["nodes"]]
            draw(nodes, bounds)
            draw(nodes, outline)
        x0, y0, x1, y1 = bounds.bounds
        scale = 32 / max(x1 - x0, y1 - y0)
        tx = (32 - scale * (x0 + x1)) / 2
        ty = (32 + scale * (y0 + y1)) / 2
        # Keep contour winding together for counters; flip the font's Y-up axis.
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">\n'
            f'  <path fill="black" fill-rule="nonzero" transform="matrix({scale:.12g} 0 0 {-scale:.12g} {tx:.12g} {ty:.12g})" '
            f'd="{outline.getCommands()}"/>\n</svg>\n'
        )
        destination = RESOURCES / f"Assets.xcassets/{asset}.imageset"
        destination.mkdir(parents=True, exist_ok=True)
        (destination / f"{asset}.svg").write_text(svg)
        (destination / "Contents.json").write_text(json.dumps({
            "images": [{"filename": f"{asset}.svg", "idiom": "universal"}],
            "info": {"author": "xcode", "version": 1},
            "properties": {"preserves-vector-representation": True, "template-rendering-intent": "template"},
        }, indent=2) + "\n")
        provenance["logos"].append({
            "glyph": glyph["glyphname"], "asset": asset,
            "glyphSHA256": sha256(glyph_data), "assetSHA256": sha256(svg.encode()),
            "bounds": bounds.bounds,
        })
    (RESOURCES / "Notices/connector-logo-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    export(parser.parse_args().source.expanduser())
