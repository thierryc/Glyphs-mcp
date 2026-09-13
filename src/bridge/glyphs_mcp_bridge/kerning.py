"""Explicit native kerning keys; no class resolution or collision policy."""

from .native_undo import write_value

DIRECTIONS = {"LTR": 0, "RTL": 2, "vertical": 4}


def read(font, target):
    if font.masters[target["master"]] is None:
        raise ValueError("kerning master is unavailable")
    return font.kerningForPair(target["master"], target["left"], target["right"],
                               direction=DIRECTIONS[target["direction"]])


def write_exact(font, target, wanted):
    args = (target["master"], target["left"], target["right"])
    direction = DIRECTIONS[target["direction"]]
    if wanted is None:
        font.removeKerningForPair(*args, direction=direction)
    else:
        font.setKerningForPair(*args, wanted, direction=direction)


def write_undo(font, scope, change, *, reverse=False):
    # Collision jobs write exact pairs; native UI history belongs to the left glyph.
    glyph = None if change["left"].startswith("@") else font.glyphs[change["left"]]
    layer = glyph.layers[change["master"]] if glyph is not None else None
    manager = scope.manager_for(layer) if scope is not None else None
    key = {k: change[k] for k in ("master", "direction", "left", "right")}
    write_value(manager, font, key, change["before"] if reverse else change["after"], read, write_exact)
