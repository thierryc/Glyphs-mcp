"""One-shot reference loading; invoked by glyphs-cli with plugins disabled."""

import json
import sys
from pathlib import Path

from .geometry import path_elements
from .sources import resolve_reference


def snapshot(payload):
    from Foundation import NSURL
    from GlyphsApp import GSFont

    reference = resolve_reference(payload["reference"], payload["source"], payload["cache"],
                                  refresh=payload.get("refresh", False))
    loaded = GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(reference["path"]), None)
    font = loaded[0] if isinstance(loaded, tuple) else loaded
    if font is None:
        raise ValueError("Glyphs could not load the comparison reference")
    glyph = font.glyphs[payload["glyph"]]
    if glyph is None:
        return {**reference, "missingGlyph": True, "outline": [], "anchors": {}, "width": None}
    layer = glyph.layers[payload["layer"]]
    if layer is None:
        if payload.get("masterLayer") is False:
            raise ValueError("The reference has no matching special layer")
        matches = [master for master in font.masters if str(master.name) == payload.get("masterName")]
        if len(matches) != 1:
            raise ValueError("No matching reference layer or unique master name")
        layer = glyph.layers[matches[0].id]
    if layer is None:
        raise ValueError("The reference has no matching layer")
    outline = path_elements(layer.completeBezierPath)
    return {**reference, "missingGlyph": False, "outline": outline,
            "openOutline": path_elements(layer.completeOpenBezierPath), "width": float(layer.width),
            "anchors": {str(a.name): [float(a.position.x), float(a.position.y)] for a in layer.anchors}}


def main():
    request = Path(sys.argv[-1])
    payload = json.loads(request.read_text())
    try:
        result = {"ok": True, "data": snapshot(payload)}
    except Exception as error:
        result = {"ok": False, "error": str(error) or type(error).__name__}
    Path(payload["output"]).write_text(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
