"""Bounded native layer pages for one named glyph; no geometry or type model."""
import base64
import binascii
import json
from glyphs_mcp_protocol.reads import LAYER_PAGE_LIMIT
from .core import BridgeError
from .context import value

FLAGS = frozenset(('isMasterLayer', 'isSpecialLayer', 'isBraceLayer', 'isBracketLayer'))
FIELDS = frozenset(('id', 'name', 'associatedMasterId', *FLAGS))


def _invalid():
    return BridgeError('invalid_request', 'use the unmodified nextCursor from the previous layer page')


def _decode(cursor):
    if not isinstance(cursor, str) or not cursor.startswith('l1.') or len(cursor) > 4096:
        raise _invalid()
    try:
        data = json.loads(base64.b64decode(cursor[3:], altchars=b'-_', validate=True))
        if (not isinstance(data, dict) or set(data) != {'document', 'glyph', 'offset', 'total', 'generation', 'dirty', 'after'}
                or not isinstance(data['document'], str) or not data['document']
                or type(data['offset']) is not int or data['offset'] < 1
                or type(data['total']) is not int or data['total'] <= data['offset']
                or type(data['generation']) is not int
                or data['dirty'] is not None and type(data['dirty']) is not bool
                or not isinstance(data['glyph'], list) or len(data['glyph']) != 2
                or not all(isinstance(v, str) and v for v in data['glyph'])
                or not isinstance(data['after'], list) or len(data['after']) != 2
                or not isinstance(data['after'][0], str) or not data['after'][0]
                or data['after'][1] is not None and not isinstance(data['after'][1], str)):
            raise _invalid()
        return data
    except (ValueError, TypeError, binascii.Error, RecursionError) as error:
        raise _invalid() from error


def _field(layer, field):
    result = value(layer, 'layerId' if field == 'id' else field)
    if field == 'id':
        if not isinstance(result, str) or not result:
            raise BridgeError('unsupported_read', 'native layer ID unavailable')
        return result
    if field in FLAGS:
        return bool(result) if type(result) in (bool, int) and result in (0, 1) else None
    return result if isinstance(result, str) else None


def _boundary(layer):
    return [_field(layer, 'id'), _field(layer, 'name')]


def read(adapter, font, document_id, entities, fields):
    if len(entities) != 1:
        raise BridgeError('invalid_request', 'a layer page must be the only entity selector')
    request = entities[0]
    if set(request) - {'kind', 'glyph', 'limit', 'cursor'}:
        raise BridgeError('invalid_request', 'layer pages accept only kind, glyph, limit and cursor')
    name = request.get('glyph')
    if not isinstance(name, str) or not name:
        raise BridgeError('invalid_request', 'layer pages require one nonempty glyph name')
    if not fields or set(fields) - FIELDS:
        raise BridgeError('unsupported_read', 'layer pages support id, name, associatedMasterId and native classification flags')
    limit = request.get('limit', LAYER_PAGE_LIMIT)
    if type(limit) is not int or not 1 <= limit <= LAYER_PAGE_LIMIT:
        raise BridgeError('invalid_request', 'layer page limit must be an integer from 1 to 100')
    cursor = _decode(request['cursor']) if 'cursor' in request else None
    glyph = adapter._glyph(font, name)
    target = [name, value(glyph, 'id')]
    if not isinstance(target[1], str) or not target[1]:
        raise BridgeError('unsupported_read', 'native glyph identity unavailable')
    # GlyphLayerProxy integer lookup rescans extra layers. Use the native KVC
    # collection order directly, not the wrapper's master-first presentation.
    total = value(glyph, 'countOfLayers')
    try:
        getter = getattr(glyph, 'objectInLayersAtIndex_', None)
    except Exception as error:
        raise BridgeError('unsupported_read', 'native layer index accessor unavailable') from error
    if type(total) is not int or total < 0 or not callable(getter):
        raise BridgeError('unsupported_read', 'native indexed layer collection unavailable')
    generation, dirty = adapter._generation(font), adapter._dirty(font)
    offset = cursor['offset'] if cursor else 0
    if cursor and (cursor['document'] != document_id or cursor['glyph'] != target or cursor['total'] != total
                   or cursor['generation'] != generation or cursor['dirty'] != dirty or offset >= total):
        raise BridgeError('stale_layer_cursor', 'document, glyph, count or change signal changed; restart layer discovery')
    try:
        if cursor and cursor['after'] != _boundary(getter(offset - 1)):
            raise BridgeError('stale_layer_cursor', 'layer page boundary changed; restart layer discovery')
        items, last = [], None
        for index in range(offset, min(total, offset + limit)):
            last = getter(index)
            if last is None:
                raise BridgeError('unsupported_read', 'native layer evidence unavailable')
            items.append({field: _field(last, field) for field in fields})
        end = offset + len(items)
        next_cursor = None
        if end < total:
            payload = dict(document=document_id, glyph=target, offset=end, total=total,
                           generation=generation, dirty=dirty, after=_boundary(last))
            next_cursor = 'l1.' + base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode()
    except BridgeError:
        raise
    except Exception as error:
        raise BridgeError('unsupported_read', 'native indexed layer evidence unavailable') from error
    return [{'entity': dict(request), 'values': dict(items=items, total=total, returned=len(items),
                complete=end == total, nextCursor=next_cursor)}]
