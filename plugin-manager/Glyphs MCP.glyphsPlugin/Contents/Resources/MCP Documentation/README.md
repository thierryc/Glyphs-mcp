# MCP Documentation

This directory is the generated, searchable documentation bundle shipped with
Glyphs MCP. It contains the official Glyphs Python ObjectWrapper reference,
the version 3 and 4 file-format specifications, and the regular ``.glyphs``
and ``fontinfo.plist`` schemas.

The generator lives in the main repository at
``src/glyphs-mcp/scripts/generate_documentation.py``. It reads the pinned
official ``GlyphsSDK`` submodule and writes the tracked ``docs/`` pages and
``index.json`` manifest here. Do not edit generated pages by hand.

## Regenerate

Run ``python3 src/glyphs-mcp/scripts/generate_documentation.py`` from the
repository root. ``copy_documentation.py`` remains as a compatibility entry
point for older release instructions.
