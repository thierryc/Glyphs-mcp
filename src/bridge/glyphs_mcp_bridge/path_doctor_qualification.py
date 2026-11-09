"""Qualification for exact in-memory seam edits, independent of native Save.

Native generic fixtures, numerical attribute/profile recovery and NSUndoManager
round trips qualified on Glyphs 4.2 (4202). Other hosts remain diagnostic-only.
See reports/path-doctor-20261029.md for scope and native persistence limitations.
"""
QUALIFIED_HOST = ('com.GeorgSeifert.Glyphs4', '4.2', '4202')


def repair_available():
    try:
        from .identity import host_identity
        host = host_identity()
        if tuple(str(host.get(k)) for k in ('identifier', 'version', 'build')) != QUALIFIED_HOST:
            return False
        from GlyphsApp import GSPath, GSNode
        import objc
        for owner in (GSPath(), GSNode()):
            methods = owner.pyobjc_instanceMethods
            if not all(callable(getattr(methods, k, None)) for k in ('attributes', 'setAttributes_')):
                return False
        point = objc.lookUpClass('GSPenPoint').alloc().init()
        from glyphs_mcp_protocol.preparation.path_attributes import PEN_FIELDS
        return all(callable(getattr(point.pyobjc_instanceMethods, k, None)) for k in PEN_FIELDS)
    except Exception:
        return False


def duplicate_repair_available():
    # Independently qualified with native identity retention and exact
    # NSUndoManager Undo/Redo on 2026-11-01. See path-cleanup qualification report.
    return repair_available()


def cleanup_available():
    from .outline_edit import native_remove_available
    return duplicate_repair_available() and native_remove_available()


def fitting_available():
    # Independent plugin-free native family/apply/recovery and NSUndoManager
    # qualification: reports/path-fitting-20261104.md. Do not inherit future
    # seam host changes as evidence for polygon reconstruction.
    try:
        from .identity import host_identity
        host=host_identity()
        if tuple(str(host.get(k)) for k in ('identifier','version','build')) != ('com.GeorgSeifert.Glyphs4','4.2','4202'):
            return False
        from GlyphsApp import GSNode,GSPath
        return all(callable(getattr(owner.pyobjc_instanceMethods,k,None))
                   for owner in (GSNode(),GSPath()) for k in ('attributes','setAttributes_'))
    except Exception:
        return False
