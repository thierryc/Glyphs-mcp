"""Requested native master defaults and bounded axis positions; no edits/cache."""
import math
from glyphs_mcp_protocol.reads import MASTER_AXIS_LIMIT, MASTER_AXIS_ITEMS_LIMIT, MASTER_PAGE_LIMIT
from .core import BridgeError
from .context import value
from typing import Mapping

METRICS = {'ascender': 'defaultAscender', 'capHeight': 'defaultCapHeight',
           'xHeight': 'defaultXHeight', 'descender': 'defaultDescender',
           'italicAngle': 'defaultItalicAngle'}
FIELDS = frozenset((*METRICS, 'axes'))


def _unavailable(field):
    return BridgeError('unsupported_read', f'native master {field} evidence unavailable')


def _get(owner, field, *args):
    try:
        value = getattr(owner, field)
        if args and not callable(value):
            raise _unavailable(field)
        return value(*args) if callable(value) else value
    except Exception as error:
        raise _unavailable(field) from error


def _number(value, field):
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                              or not math.isfinite(value)):
        raise _unavailable(field)
    return value


def preflight(font, owners):
    count = _get(font, 'countOfAxes')
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise _unavailable('axis count')
    if count > MASTER_AXIS_LIMIT or count * owners > MASTER_AXIS_ITEMS_LIMIT:
        raise BridgeError('invalid_request', 'axes require at most 32 axes per master and '
                          '256 master-axis items per request; request fewer masters or omit axes',
                          details={'axesPerMaster': count, 'masters': owners,
                                   'axisLimit': MASTER_AXIS_LIMIT, 'axisItemsLimit': MASTER_AXIS_ITEMS_LIMIT})
    return count


def read(master, field):
    if field in METRICS:
        # The Glyphs Python metric properties truncate native fractional defaults.
        value = _number(_get(master, METRICS[field]), field)
        if value is None:
            raise _unavailable(field)
        return value
    font = _get(master, 'font')
    count = preflight(font, 1)
    items, unavailable = [], []
    for index in range(count):
        axis = _get(font, 'objectInAxesAtIndex_', index)
        item = {'index': index}
        for key, prop in (('axisId', 'axisId'), ('tag', 'axisTag'), ('name', 'name')):
            item[key] = _get(axis, prop)
            if not isinstance(item[key], str) or key == 'axisId' and not item[key]:
                raise _unavailable('axis ' + prop)
        for key, prop in (('internalValue', 'axisInternalValueValueForId_'),
                          ('externalValue', 'axisExternalValueValueForId_')):
            item[key] = _number(_get(master, prop, item['axisId']), key)
            if item[key] is None:
                unavailable.append({'axisId': item['axisId'], 'field': key})
        items.append(item)
    result = dict(items=items, total=count, returned=len(items), complete=not unavailable)
    if unavailable:
        result['unavailable'] = unavailable
    return result


def page(adapter, font, document_id, request, fields):
    if set(request) - {"kind", "limit", "cursor"}:
        raise BridgeError("invalid_request", "master pages accept only kind, limit and cursor")
    if not fields or set(fields) - adapter.MASTER_FIELDS:
        raise BridgeError("unsupported_read", "unsupported master page fields: " + ", ".join(sorted(set(fields) - adapter.MASTER_FIELDS)))
    limit = request.get("limit", MASTER_PAGE_LIMIT)
    if type(limit) is not int or not 1 <= limit <= MASTER_PAGE_LIMIT:
        raise BridgeError("invalid_request", "master page limit must be an integer from 1 to 100")
    masters = value(font, "masters", None)
    if masters is None:
        raise BridgeError("unsupported_read", "native master collection is unavailable")
    total = len(masters)
    cursor = request.get("cursor")
    offset = 0
    if cursor is not None:
        if (not isinstance(cursor, Mapping) or set(cursor) != {"documentId", "offset", "total", "afterId"}
                or type(cursor.get("offset")) is not int or cursor["offset"] < 1
                or type(cursor.get("total")) is not int or cursor["total"] < 1
                or not isinstance(cursor.get("afterId"), str) or not cursor["afterId"]
                or not isinstance(cursor.get("documentId"), str)):
            raise BridgeError("invalid_request", "use the nextCursor returned by the previous master page")
        offset = cursor["offset"]
        if (cursor["documentId"] != document_id or cursor["total"] != total or offset >= total
                or value(masters[offset - 1], "id") != cursor["afterId"]):
            raise BridgeError("stale_master_cursor", "master page boundary changed; restart discovery without a cursor")
    # Native indexed access visits this page and at most one boundary master.
    # A cursor detects count/boundary changes, not an atomic multi-call snapshot.
    end = min(total, offset + limit)
    if "axes" in fields and end > offset:
        preflight(font, end - offset)
    items = []
    for index in range(offset, end):
        master = masters[index]
        items.append({field: adapter._read_field(master, field, "master") for field in dict.fromkeys(fields)})
    next_cursor = None if end == total else {
        "documentId": document_id, "offset": end, "total": total,
        "afterId": value(masters[end - 1], "id"),
    }
    return {"items": items, "total": total, "complete": end == total, "nextCursor": next_cursor}
