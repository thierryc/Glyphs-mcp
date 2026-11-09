"""Read installed filter identities; never construct or execute a filter."""
from itertools import islice

CAPABILITY = 'filters.inventory.v1'
LIMIT = 256


def _metadata(owner, key):
    value = getattr(owner, key, None)
    value = value() if callable(value) else value
    return str(value)[:255] if value is not None else None


def inventory():
    try:
        from GlyphsApp import Glyphs
        filters = Glyphs.filters
        if filters is None:
            raise ValueError('filter collection unavailable')
        items = []
        for item in islice(iter(filters), LIMIT + 1):
            if len(items) == LIMIT:
                items.sort(key=lambda item: (item['className'], item['displayName'] or ''))
                return dict(available=True, items=items, truncated=True)
            items.append(dict(className=type(item).__name__[:255],
                              displayName=_metadata(item, 'title') or _metadata(item, 'name'),
                              version=_metadata(item, 'version') or _metadata(item, 'versionString')))
        items.sort(key=lambda item: (item['className'], item['displayName'] or ''))
        return dict(available=True, items=items, truncated=False)
    except Exception as exc:
        return dict(available=False, items=[], truncated=False,
                    error=dict(code='filter_inventory_unavailable',
                               message='Native filter identities could not be read',
                               exception=type(exc).__name__))
