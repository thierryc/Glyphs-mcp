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
