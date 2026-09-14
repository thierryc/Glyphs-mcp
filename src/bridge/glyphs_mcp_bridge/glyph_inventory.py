"""Fresh native glyph-name pages; a small opaque cursor, no inventory cache."""
import base64
import binascii
import json
from glyphs_mcp_protocol.reads import GLYPH_PAGE_LIMIT
from .core import BridgeError
from .context import value


def _invalid():
    return BridgeError('invalid_request', 'use the unmodified nextCursor from the previous glyph page')


def _decode(cursor):
    if not isinstance(cursor, str) or not cursor.startswith('g1.') or len(cursor) > 4096:
        raise _invalid()
    try:
        raw = base64.b64decode(cursor[3:], altchars=b'-_', validate=True)
        data = json.loads(raw)
        if (not isinstance(data, dict) or set(data) != {'document', 'offset', 'total', 'generation', 'dirty', 'after'}
                or not isinstance(data['document'], str) or not data['document']
                or type(data['offset']) is not int or data['offset'] < 1
                or type(data['total']) is not int or data['total'] <= data['offset']
                or type(data['generation']) is not int
                or data['dirty'] is not None and type(data['dirty']) is not bool
                or not isinstance(data['after'], list) or len(data['after']) != 2
                or not all(isinstance(v, str) and v for v in data['after'])):
            raise _invalid()
        return data
    except (ValueError, TypeError, binascii.Error, RecursionError) as error:
        raise _invalid() from error


def _name(glyph):
    name = value(glyph, 'name')
    if not isinstance(name, str) or not name:
        raise BridgeError('unsupported_read', 'native glyph name unavailable')
    return name


def _boundary(glyph):
    identifier = value(glyph, 'id')
    if not isinstance(identifier, str) or not identifier:
        raise BridgeError('unsupported_read', 'native glyph boundary identity unavailable')
    return [identifier, _name(glyph)]


def read(adapter, font, document_id, entities, fields):
    if len(entities) != 1:
        raise BridgeError('invalid_request', 'a glyph page must be the only entity selector')
    request = entities[0]
    if set(request) - {'kind', 'limit', 'cursor'}:
        raise BridgeError('invalid_request', 'glyph pages accept only kind, limit and cursor')
    if not fields or set(fields) != {'name'}:
        raise BridgeError('unsupported_read', 'glyph pages support only the name field')
    limit = request.get('limit', GLYPH_PAGE_LIMIT)
    if type(limit) is not int or not 1 <= limit <= GLYPH_PAGE_LIMIT:
        raise BridgeError('invalid_request', 'glyph page limit must be an integer from 1 to 100')
    cursor = _decode(request['cursor']) if 'cursor' in request else None
    glyphs = value(font, 'glyphs')
    try:
        total = len(glyphs)  # FontGlyphsProxy delegates to native GSFont.count().
    except Exception as error:
        raise BridgeError('unsupported_read', 'native glyph collection count unavailable') from error
    generation, dirty = adapter._generation(font), adapter._dirty(font)
    offset = cursor['offset'] if cursor else 0
    if cursor and (cursor['document'] != document_id or cursor['total'] != total
                   or cursor['generation'] != generation or cursor['dirty'] != dirty or offset >= total):
        raise BridgeError('stale_glyph_cursor', 'document, count or change signal changed; restart glyph discovery')
    try:
        if cursor and cursor['after'] != _boundary(glyphs[offset - 1]):
            raise BridgeError('stale_glyph_cursor', 'glyph page boundary changed; restart glyph discovery')
        # Only this page plus one preceding boundary; no previous-page rescans.
        items, last = [], None
        for index in range(offset, min(total, offset + limit)):
            last = glyphs[index]
            items.append({'name': _name(last)})
        end = offset + len(items)
        next_cursor = None
        if end < total:
            payload = dict(document=document_id, offset=end, total=total, generation=generation,
                           dirty=dirty, after=_boundary(last))
            next_cursor = 'g1.' + base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode()
    except (IndexError, KeyError, TypeError) as error:
        raise BridgeError('unsupported_read', 'native indexed glyph evidence unavailable') from error
    return [{'entity': dict(request), 'values': dict(items=items, total=total, returned=len(items),
                complete=end == total, nextCursor=next_cursor)}]
