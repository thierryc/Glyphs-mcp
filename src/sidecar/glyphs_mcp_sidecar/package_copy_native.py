"""Detached native package conversion. Run as a script by glyphs-cli, never in the UI app."""

import json
from pathlib import Path
import sys


def load_font(path):
    from Foundation import NSURL
    from GlyphsApp import GSFont

    result = GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(str(path)), None)
    font, error = result if isinstance(result, tuple) else (result, None)
    if font is None or error is not None:
        raise ValueError(str(error or "Glyphs could not load the source"))
    return font


def canonical(path):
    from Foundation import NSData, NSPropertyListSerialization

    data = NSData.dataWithContentsOfFile_(str(path))
    value, _, error = NSPropertyListSerialization.propertyListWithData_options_format_error_(data, 1, None, None)
    if value is None or error is not None:
        raise ValueError("Could not verify the native font serialization")
    # Only glyph metadata is exempt. A lastChange key in userData or another
    # part of the font must still compare exactly.
    for glyph in value.get("glyphs", []):
        glyph.pop("lastChange", None)
    return value


def convert(source, package, scratch):
    font = load_font(source)
    font.save(str(package), makeCopy=True)
    if not all((package / name).exists() for name in ("fontinfo.plist", "order.plist", "glyphs")):
        raise ValueError("Glyphs did not create a complete package")
    reopened = load_font(package)
    if font.formatVersion != reopened.formatVersion:
        raise ValueError("The package changed the source format version")
    if [g.name for g in font.glyphs] != [g.name for g in reopened.glyphs]:
        raise ValueError("The package changed the glyph order")
    if [m.id for m in font.masters] != [m.id for m in reopened.masters]:
        raise ValueError("The package changed the font masters")
    def image_paths(value):
        return [(glyph.name, layer.layerId, str(layer.backgroundImage.path))
                for glyph in value.glyphs for layer in glyph.layers if layer.backgroundImage is not None]
    if image_paths(font) != image_paths(reopened):
        raise ValueError("The package changed a background image reference")
    # Keep canonical files beside the source too. Native background image
    # serialization uses the target directory when rebasing relative paths.
    before = source.parent / (scratch.name + ".before.glyphs")
    after = source.parent / (scratch.name + ".after.glyphs")
    font.save(str(before), makeCopy=True)
    reopened.save(str(after), makeCopy=True)
    if canonical(before) != canonical(after):
        raise ValueError("Package verification found differences beyond glyph modification timestamps")
    return {"glyphCount": len(font.glyphs), "masterCount": len(font.masters),
            "formatVersion": int(font.formatVersion)}


def main():
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try:
        result = convert(Path(request["source"]), Path(request["package"]), Path(request["scratch"]))
    except Exception as error:
        Path(request["result"]).write_text(json.dumps({"error": str(error)}), encoding="utf-8")
        return 1
    Path(request["result"]).write_text(json.dumps(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
