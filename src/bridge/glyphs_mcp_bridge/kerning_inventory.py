"""Bounded native stored-pair pages; no table copy or effective-kerning engine."""
import base64
import binascii
import json
import math
from glyphs_mcp_protocol.reads import KERNING_PAGE_LIMIT, KERNING_SCAN_LIMIT
from .core import BridgeError
from .context import value

GROUP_FIELDS = frozenset(side + suffix for side in ('left', 'right', 'top', 'bottom')
                         for suffix in ('KerningGroup', 'KerningKey'))
TABLES = {'LTR': 'kerningLTR', 'RTL': 'kerningRTL', 'vertical': 'kerningVertical'}


def _invalid(message='use the unmodified nextCursor from the previous kerning page'):
    return BridgeError('invalid_request', message)


def _stale():
    return BridgeError('stale_kerning_cursor', 'kerning scope, change signal or boundary changed; restart without a cursor')


def _count(table):
    if table is None:
        return 0
    if not all(callable(getattr(table, name, None)) for name in ('count', 'keyAtIndex_', 'objectForKey_')):
        raise BridgeError('unsupported_read', 'indexed native kerning evidence unavailable; update the installation')
    return int(table.count())


def _decode(raw):
    if not isinstance(raw, str) or not raw.startswith('k1.') or len(raw) > 8192:
        raise _invalid()
    try:
        data = json.loads(base64.b64decode(raw[3:], altchars=b'-_', validate=True))
        if (not isinstance(data, dict) or set(data) != {'scope', 'count', 'generation', 'dirty', 'i', 'j', 'boundary'}
                or not isinstance(data['scope'], list) or len(data['scope']) != 5
                or not all(v is None or isinstance(v, str) for v in data['scope'])
                or any(type(data[k]) is not int or data[k] < 0 for k in ('count', 'i', 'j', 'generation'))
                or data['dirty'] is not None and type(data['dirty']) is not bool
                or not isinstance(data['boundary'], list) or len(data['boundary']) != 6):
            raise _invalid()
        b = data['boundary']
        if (type(b[0]) is not int or b[0] < 0 or not isinstance(b[1], str)
                or type(b[2]) is not int or b[2] < 0 or type(b[3]) is not int or b[3] < -1
                or b[4] is not None and not isinstance(b[4], str)
                or b[5] is not None and (type(b[5]) not in (int, float) or not math.isfinite(b[5]))):
            raise _invalid()
        return data
    except (ValueError, TypeError, binascii.Error, RecursionError) as error:
        raise _invalid() from error


def _side(font, key):
    if key.startswith('@'):
        return dict(key=key, glyph=None, kind='group')
    glyph = font.glyphForId_(key)  # Native direct lookup, never a font-wide ID map.
    name = value(glyph, 'name') if glyph is not None else None
    return dict(key=key, glyph=name, kind='glyph' if name else 'unresolved')


def read(adapter, font, document_id, entities, fields):
    if len(entities) != 1:
        raise _invalid('a kerning page must be the only entity selector')
    request = entities[0]
    if set(request) - {'kind', 'master', 'direction', 'limit', 'cursor', 'leftKey', 'rightKey'}:
        raise _invalid('kerning pages accept kind, master, direction, limit, cursor, leftKey and rightKey')
    if not fields or set(fields) - {'left', 'right', 'value'}:
        raise BridgeError('unsupported_read', 'kerning pages support requested left, right and value fields')
    limit = request.get('limit', KERNING_PAGE_LIMIT)
    if type(limit) is not int or not 1 <= limit <= KERNING_PAGE_LIMIT:
        raise _invalid('kerning page limit must be an integer from 1 to 100')
    master, direction = request.get('master'), request.get('direction')
    if not isinstance(direction, str) or direction not in TABLES:
        raise _invalid('kerning direction must be LTR, RTL or vertical')
    adapter._entity(font, 'master', {'id': master})
    for key in ('leftKey', 'rightKey'):
        if key in request and (not isinstance(request[key], str) or not 1 <= len(request[key]) <= 1024):
            raise _invalid(key + ' must be a nonempty raw stored key, at most 1024 characters')
    left, right = request.get('leftKey'), request.get('rightKey')
    scope = [document_id, master, direction, left, right]
    cursor = _decode(request['cursor']) if 'cursor' in request else None
    try:
        root = getattr(font, TABLES[direction])
        table = root.objectForKey_(master) if root is not None else None
        count = _count(table)
        generation, dirty = adapter._generation(font), adapter._dirty(font)
        i, j = (cursor['i'], cursor['j']) if cursor else (0, 0)
        outer = int(table.objectForKey_(left) is not None) if left and table is not None else (0 if left else count)
        if cursor:
            if (cursor['scope'] != scope or cursor['count'] != count or cursor['generation'] != generation
                    or cursor['dirty'] != dirty or i >= outer):
                raise _stale()
            bi, bk, bn, bj, br, bv = cursor['boundary']
            if bi >= outer or (left or str(table.keyAtIndex_(bi))) != bk:
                raise _stale()
            previous = table.objectForKey_(bk)
            if _count(previous) != bn or bj >= bn:
                raise _stale()
            if br is not None and ((right or str(previous.keyAtIndex_(bj))) != br
                                   or previous.objectForKey_(br) != bv):
                raise _stale()
        items, scanned, boundary = [], 0, None
        while i < outer and len(items) < limit and scanned < KERNING_SCAN_LIMIT:
            key = left or str(table.keyAtIndex_(i))
            group = table.objectForKey_(key)
            n = _count(group)
            if j > n:
                raise _stale()
            scanned += 1  # Charge even empty groups and right-filter misses.
            boundary = [i, key, n, -1, None, None]
            if right:
                amount = group.objectForKey_(right)
                if amount is not None:
                    _append(items, font, fields, key, right, amount)
                    boundary = [i, key, n, -1, right, amount]
                i, j = i + 1, 0
                continue
            while j < n and len(items) < limit and scanned < KERNING_SCAN_LIMIT:
                rk = str(group.keyAtIndex_(j)); amount = group.objectForKey_(rk)
                _append(items, font, fields, key, rk, amount)
                boundary = [i, key, n, j, rk, amount]
                scanned += 1; j += 1
            if j == n:
                i, j = i + 1, 0
        complete = i == outer
        next_cursor = None
        if not complete:
            payload = dict(scope=scope, count=count, generation=generation, dirty=dirty, i=i, j=j, boundary=boundary)
            next_cursor = 'k1.' + base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode()
            if len(next_cursor) > 8192:
                raise BridgeError('unsupported_read', 'native kerning keys exceed the bounded cursor size')
    except BridgeError:
        raise
    except Exception as error:
        raise BridgeError('unsupported_read', 'native kerning page evidence unavailable: ' + str(error)) from error
    return [{'entity': dict(request), 'values': dict(items=items, total=None, returned=len(items),
                complete=complete, nextCursor=next_cursor, scanned=scanned, scanLimit=KERNING_SCAN_LIMIT)}]


def _append(items, font, fields, left, right, amount):
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
        raise BridgeError('unsupported_read', 'native stored kerning value is unavailable or nonfinite')
    items.append({field: amount if field == 'value' else _side(font, left if field == 'left' else right)
                  for field in fields})
