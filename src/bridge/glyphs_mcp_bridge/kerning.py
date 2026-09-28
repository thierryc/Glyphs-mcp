"""Explicit native kerning keys; no class resolution or collision policy."""

from .native_undo import write_value
from glyphs_mcp_protocol.kerning_edits import check_guard, read_stored

DIRECTIONS = {"LTR": 0, "RTL": 2, "vertical": 4}


def read(font, target):
    check_guard(font, target)
    if font.masters[target["master"]] is None:
        raise ValueError("kerning master is unavailable")
    return read_stored(font, target['master'], target['left'], target['right'], target['direction'])


def write_exact(font, target, wanted):
    args = (target["master"], target["left"], target["right"])
    direction = DIRECTIONS[target["direction"]]
    # GSFont's setter registers with the document even when Edit-view history
    # belongs to a glyph. write_value owns the exact inverse on the chosen
    # manager; suppress the native second registration, including Undo/Redo.
    parent = getattr(font, 'parent', None)
    getter = getattr(parent, 'undoManager', None)
    manager = getter() if callable(getter) else getter
    enabled = callable(getattr(manager, 'isUndoRegistrationEnabled', None)) and manager.isUndoRegistrationEnabled()
    if enabled: manager.disableUndoRegistration()
    try:
        if wanted is None:
            font.removeKerningForPair(*args, direction=direction)
        else:
            font.setKerningForPair(*args, wanted, direction=direction)
    finally:
        if enabled: manager.enableUndoRegistration()


def write_undo(font, scope, change, *, reverse=False):
    # Collision jobs write exact pairs; native UI history belongs to the left glyph.
    glyph = None if change["left"].startswith("@") else font.glyphs[change["left"]]
    layer = glyph.layers[change["master"]] if glyph is not None else None
    manager = scope.manager_for(layer) if scope is not None else None
    if change.get('targetGuard') and (manager is None or not callable(getattr(manager, 'registerUndoWithTarget_handler_', None))
                                    or not manager.isUndoRegistrationEnabled()):
        raise ValueError('Native kerning Undo is unavailable; no exact edit was applied')
    key = {k: change[k] for k in ("master", "direction", "left", "right")}
    write_value(manager, font, key, change["before"] if reverse else change["after"], read, write_exact)
