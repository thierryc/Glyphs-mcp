"""Bounded, stateless native document context. No edits or font traversal."""
from glyphs_mcp_protocol.reads import CONTEXT_GLYPH_LIMIT
from .core import BridgeError

FIELDS = frozenset(('view', 'master', 'selectedGlyphs'))
_MISSING = object()


def value(owner, name, default=None):
    try:
        result = getattr(owner, name)
        return result() if callable(result) else result
    except Exception:
        return default


def current_font(glyphs):
    return value(glyphs, 'font', _MISSING)


def is_current(font, current, identity):
    if current is _MISSING:
        return None
    return current is not None and identity(font) == identity(current)


def view(font, identity):
    # A missing Edit View alone does not establish Font View: verify the native
    # selected tab against the document's known native controllers.
    window = value(value(font, 'parent'), 'windowController')
    selected = value(value(window, 'tabBarControl'), 'selectedTabItem')
    if selected is not None:
        for field, label in (('currentTab', 'edit'), ('fontView', 'font')):
            controller = value(font, field)
            if controller is not None and identity(selected) == identity(controller):
                return label
    return 'unavailable'


def selected_glyphs(font, native_view, limit):
    source = {'font': 'selection', 'edit': 'selectedLayers'}.get(native_view)
    result = dict(source='font.' + source if source else None, total=None,
                  returned=0, limit=limit, complete=False, items=[])
    collection = value(font, source) if source else None
    try:
        # NSArray's native count, not list(collection) or a count-by-iteration.
        total = len(collection)
    except Exception:
        result['unavailable'] = 'native selection count unavailable'
        return result
    result['total'] = total
    try:
        for index in range(min(total, limit)):
            item = collection[index]
            glyph = value(item, 'parent') if native_view == 'edit' else item
            name = value(glyph, 'name')
            if not isinstance(name, str) or not name:
                raise ValueError('missing native glyph name')
            result['items'].append(name)
    except Exception:
        result['unavailable'] = 'native selection item unavailable'
    result['returned'] = len(result['items'])
    result['complete'] = result['returned'] == total and 'unavailable' not in result
    return result


def read(font, entities, fields, identity):
    if len(entities) != 1:
        raise BridgeError('invalid_request', 'context requires one context entity only')
    request = entities[0]
    if set(request) - {'kind', 'glyphLimit'}:
        raise BridgeError('invalid_request', 'context accepts only kind and glyphLimit')
    if not fields or set(fields) - FIELDS:
        raise BridgeError('unsupported_read', 'context supports only view, master and selectedGlyphs')
    limit = request.get('glyphLimit', CONTEXT_GLYPH_LIMIT)
    if type(limit) is not int or not 1 <= limit <= CONTEXT_GLYPH_LIMIT:
        raise BridgeError('invalid_request', 'context glyphLimit must be an integer from 1 to 100')
    if 'glyphLimit' in request and 'selectedGlyphs' not in fields:
        raise BridgeError('invalid_request', 'glyphLimit requires selectedGlyphs')
    values = {}
    native_view = view(font, identity) if {'view', 'selectedGlyphs'} & set(fields) else None
    for field in fields:
        if field == 'view':
            values[field] = native_view
        elif field == 'master':
            master = value(font, 'selectedFontMaster')
            identifier, name = value(master, 'id'), value(master, 'name')
            values[field] = ({'id': identifier, 'name': name}
                             if isinstance(identifier, str) and identifier and isinstance(name, str) else None)
        else:
            values[field] = selected_glyphs(font, native_view, limit)
    return [{'entity': dict(request), 'values': values}]
