"""Lossless native stroke evidence and attribute snapshots (no wrapper setters).

GSPenPoint's DBL_MAX sentinels are inherited values, not missing evidence.
Only authored position is used for geometry; never positionPrecise.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

PEN_FIELDS = ('t', 'width', 'height', 'angle', 'strokePosition',
              'progressionIn', 'progressionOut', 'isLocked')
PEN_KEYS = {'t', 'width', 'height', 'angle', 'strokePos', 'progressionIn', 'progressionOut', 'progIn', 'progOut', 'locked'}


def native(owner, name, *args):
    methods = getattr(owner, 'pyobjc_instanceMethods', owner)
    value = getattr(methods, name)
    return value(*args) if callable(value) else value


def attributes(owner):
    if not hasattr(owner, 'attributes'):
        return {}
    result = native(owner, 'attributes')
    return result if result is not None else {}


def plain(value):
    """Closed, deterministic projection; unknown native references fail closed."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('non-finite native attribute')
        return {'float': value.hex()}
    if type(value).__name__ == 'GSPenPoint' or all(hasattr(value, k) for k in PEN_FIELDS):
        fields = {k: plain(native(value, k)) for k in PEN_FIELDS}
        method = getattr(getattr(value, 'pyobjc_instanceMethods', value), 'propertyListValueFormat_error_', None)
        if callable(method):
            serialized, error = method(4, None)
            if error is not None:
                raise ValueError('native Pen-point serialization failed')
            fields['stored'] = plain(serialized)
        return {'penPoint': fields}
    if isinstance(value, Mapping) or hasattr(value, 'allKeys'):
        keys = list(value.keys()) if hasattr(value, 'keys') else list(value.allKeys())
        if any(not isinstance(k, str) for k in keys):
            raise ValueError('unsupported non-string attribute key')
        return {str(k): plain(value[k]) for k in sorted(keys)}
    if isinstance(value, (list, tuple)) or type(value).__name__ in ('__NSArrayM', '__NSArrayI', 'NSArray', 'NSMutableArray', '__NSSingleObjectArrayI'):
        return [plain(v) for v in value]
    raise ValueError('unsupported native attribute/reference: ' + type(value).__name__)


def state(owner):
    result = {'attributes': plain(attributes(owner))}
    # User data can carry external node addresses; include it in stale guards.
    raw = getattr(owner, 'userData', {})
    if callable(raw): raw = raw()
    if raw is not None:
        try: raw = dict(raw)
        except (TypeError, ValueError): pass
    result['userData'] = plain(raw or {})
    return result


def clone_value(value):
    if isinstance(value, Mapping) or hasattr(value, 'allKeys'):
        return {str(k): clone_value(value[k]) for k in value}
    if isinstance(value, (list, tuple)) or type(value).__name__ in ('__NSArrayM', '__NSArrayI', 'NSArray', 'NSMutableArray', '__NSSingleObjectArrayI'):
        return [clone_value(v) for v in value]
    if hasattr(value, 'copy') and not isinstance(value, (str, int, float, bool)):
        return value.copy()
    return value


def snapshot(owner):
    return clone_value(attributes(owner))


def restore(owner, saved):
    # The wrapper formats attribute numbers. Use the qualified native selectors.
    if not hasattr(owner, 'attributes') and not saved:
        return
    methods = getattr(owner, 'pyobjc_instanceMethods', owner)
    setter = getattr(methods, 'setAttributes_', None)
    if callable(setter):
        setter(clone_value(saved))
    elif isinstance(getattr(owner, 'attributes', None), dict):
        owner.attributes = clone_value(saved)  # Generic regression host only.
    else:
        raise ValueError('exact native attribute writer unavailable')
    if plain(attributes(owner)) != plain(saved):
        raise ValueError('native attribute round trip changed precision or explicit defaults')


def transfer_profiles(destination, source):
    incoming = attributes(source).get('penPoints')
    wanted = snapshot(destination)
    if incoming is None:
        wanted.pop('penPoints', None)
    else:
        wanted['penPoints'] = clone_value(incoming)
    restore(destination, wanted)
