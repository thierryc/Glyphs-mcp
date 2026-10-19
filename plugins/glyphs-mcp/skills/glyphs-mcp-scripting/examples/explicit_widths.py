# MenuTitle: Set Explicit Layer Widths
# encoding: utf-8
"""Whole-script MCP example: no selection, sidebar, Save or Close operations.

Use entrypoint="script" and matching foreground targets. Supply params as:
{"rows": [{"glyph": "a", "layer": "EXACT_MASTER_ID",
           "expectedWidth": 500.0, "width": 501.25}]}
Resolve names and IDs before preparation. Only existing foregrounds are edited.
"""
import math


def apply_widths(font, rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Supply a nonempty explicit row list")
    resolved, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"glyph", "layer", "expectedWidth", "width"}:
            raise ValueError("Each row requires glyph, layer, expectedWidth and width")
        key = (row["glyph"], row["layer"])
        if not all(isinstance(x, str) and x for x in key) or key in seen:
            raise ValueError("Invalid or duplicate explicit target")
        seen.add(key)
        for field in ("expectedWidth", "width"):
            if isinstance(row[field], bool) or not isinstance(row[field], (int, float)) or not math.isfinite(row[field]):
                raise ValueError("Widths must be finite numbers")
        glyph = font.glyphs[row["glyph"]]
        if glyph is None:
            raise ValueError("Missing glyph: " + row["glyph"])
        layer = next((layer for layer in glyph.layers if str(layer.layerId) == row["layer"]), None)
        if layer is None or float(layer.width) != row["expectedWidth"]:
            raise ValueError("Missing layer or changed width: " + repr(key))
        resolved.append((layer, row["width"]))
    enabled = bool(font.isUpdateInterfaceEnabled())
    if enabled:
        font.disableUpdateInterface()
    try:
        for layer, width in resolved:
            layer.width = width
        for layer, width in resolved:
            if abs(float(layer.width) - width) > 1e-7:
                raise RuntimeError("Native width differs from requested value")
    finally:
        if enabled:
            font.enableUpdateInterface()


if __name__ == "__main__":
    apply_widths(font, params["rows"])
