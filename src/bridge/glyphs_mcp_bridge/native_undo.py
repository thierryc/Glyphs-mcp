"""Exact target values stored in Glyphs' native undo manager."""


class NativeUndoScope:
    """Group each touched glyph in its own native editing history.

    Glyphs routes Edit-view Undo to the glyph, not the document manager.
    Revert/discard_job are the whole-document discard paths.
    """

    def __init__(self, fallback=None):
        self.fallback = fallback
        self.managers = {}
        self._include(fallback)

    def _include(self, manager):
        if manager is None:
            return None
        try:
            import objc
            identity = int(objc.pyobjc_id(manager))
        except Exception:
            identity = id(manager)
        if identity not in self.managers:
            level = getattr(manager, "groupingLevel", lambda: None)()
            try:
                manager.beginUndoGrouping()
            except Exception:
                if level is not None and manager.groupingLevel() > level:
                    manager.endUndoGrouping()
                raise
            self.managers[identity] = manager
        return manager

    def manager_for(self, layer):
        manager = getattr(layer, "undoManager", None)
        manager = manager() if callable(manager) else manager
        return self._include(manager if manager is not None else self.fallback)

    def finish(self, name):
        first_error = None
        for manager in reversed(tuple(self.managers.values())):
            try:
                try:
                    manager.setActionName_(str(name)[:240])
                finally:
                    manager.endUndoGrouping()
            except Exception as error:
                first_error = first_error or error
        self.managers.clear()
        if first_error:
            raise first_error


def _weak_manager(manager):
    import weakref
    if hasattr(manager, "pyobjc_instanceMethods"):
        # A Python proxy can expire while the Objective-C object remains alive.
        from Foundation import NSHashTable
        table = NSHashTable.weakObjectsHashTable()
        table.addObject_(manager)
        return lambda: table.anyObject()
    return weakref.ref(manager)


def write_value(manager, target, key, value, read, exact_write, manager_ref=None):
    register = getattr(manager, "registerUndoWithTarget_handler_", None)
    enabled = getattr(manager, "isUndoRegistrationEnabled", lambda: True)()
    if not callable(register) or not enabled:
        exact_write(target, key, value)
        return
    before = read(target, key)
    manager_ref = manager_ref or _weak_manager(manager)

    def restore(owner):
        # Re-register the current value so native Redo is exact as well.
        # The stored block must not retain its owning native undo manager.
        active = manager_ref()
        if active is not None:
            write_value(active, owner, key, before, read, exact_write, manager_ref)

    # Register first: even a setter that mutates then raises has an inverse.
    register(target, restore)
    manager.disableUndoRegistration()
    try:
        exact_write(target, key, value)
    finally:
        manager.enableUndoRegistration()


def _read_scalar(target, field):
    value = getattr(target, field)
    return value() if callable(value) else value


def write_scalar(manager, target, field, value, exact_write, manager_ref=None):
    write_value(manager, target, field, value, _read_scalar, exact_write, manager_ref)
