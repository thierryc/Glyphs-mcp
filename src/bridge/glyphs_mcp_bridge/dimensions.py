"""Exact, bounded Dimensions metadata with document-level native history."""
from glyphs_mcp_protocol import dimensions as contract
from .native_undo import write_value


def available():
    # Write support is qualified against the actual palette, not merely a setter.
    try:
        from GlyphsApp import Glyphs
        return float(Glyphs.buildNumber) == 4107 and str(Glyphs.versionString).startswith("4.")
    except (ImportError, AttributeError, TypeError, ValueError):
        return False


def root(font):
    return font.userData[contract.STORAGE_KEY]


def master(font, identity):
    try:
        owner = font.masters[identity]
    except (KeyError, IndexError, TypeError):
        owner = None
    if owner is None or str(owner.id) != identity:
        contract.fail("Dimensions master is unavailable", "target_not_found")
    return owner


def read(font, change):
    master(font, change["master"])
    return contract.read_state(root(font), change["master"], change["key"])


def read_master(owner):
    return contract.read_rows(root(owner.font), str(owner.id), editable=available())


def write_exact(font, target, wanted):
    master(font, target["master"])
    result = contract.replace(root(font), target["master"], target["key"], wanted, target["containersBefore"])
    if result is None:
        del font.userData[contract.STORAGE_KEY]
    else:
        font.userData[contract.STORAGE_KEY] = result
    refresh(font)


def refresh(font):
    # Same notification observed by Glyphs' built-in Dimensions palette. This
    # updates the display without opening windows or changing selection.
    from Foundation import NSNotificationCenter
    NSNotificationCenter.defaultCenter().postNotificationName_object_("GSUpdateInterface", font)


def write_undo(font, scope, change, *, reverse=False):
    manager = scope.document_manager() if scope is not None else None
    if manager is None or not manager.isUndoRegistrationEnabled():
        contract.fail("Dimensions editing requires native document Undo", "native_undo_unavailable")
    target = {key: change[key] for key in ("master", "key", "containersBefore")}
    write_value(manager, font, target, change["before"] if reverse else change["after"], read, write_exact)
