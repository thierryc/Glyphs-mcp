"""Immutable script target resolution without copying font contents."""
from collections.abc import Mapping
from . import scripts


def value(owner, name, default=None):
    attr = getattr(owner, name, default)
    return attr() if callable(attr) else attr


def has_content(layer):
    """Existing background content, independent of any particular callback."""
    return (any(len(value(layer, k, []) or []) for k in
                ('shapes', 'anchors', 'hints', 'guides', 'annotations', 'attributes', 'userData'))
            or value(layer, 'backgroundImage') is not None
            or any(value(layer, k) for k in ('leftMetricsKey', 'rightMetricsKey', 'widthMetricsKey')))


def resolve(font, spec):
    """Resolve once without lazily creating backgrounds."""
    if isinstance(spec, Mapping):
        mid = spec['master']
        if not any(str(m.id) == mid for m in font.masters):
            raise ValueError('script master is unavailable: ' + mid)
        names = (str(g.name) for g in font.glyphs) if spec['glyphs'] == 'all' else spec['glyphs']
        raw = (dict(glyph=n, layer=mid, surface=spec['surface']) for n in names)
    else:
        raw = scripts.targets(spec)  # Keep explicit request limits and overlap checks.
    manifest, skipped = [], dict(count=0, sample=[])
    # Bulk-all names are unique in the native collection. Explicit lists have
    # already been deduplicated during validation; retained keys stay bounded.
    selected = set()
    for item in raw:
        item = scripts.target(item)
        key = (item['glyph'], item['layer'], item['surface'])
        if key in selected:
            continue
        glyph = font.glyphs[item['glyph']]
        if glyph is None:
            raise ValueError('script glyph is unavailable: ' + item['glyph'])
        owner = next((l for l in glyph.layers if str(l.layerId) == item['layer']), None)
        if owner is None:
            raise ValueError('script layer is unavailable: ' + item['layer'])
        reason = None
        layer = owner
        if item['surface'] == 'background':
            if not value(owner, 'hasBackground', False):
                reason = 'missing background'
            else:
                layer = owner.background
                if not has_content(layer):
                    reason = 'empty background'
        if reason:
            skipped['count'] += 1
            if len(skipped['sample']) < 10:
                skipped['sample'].append(dict(item, status='skipped', reason=reason))
            continue
        if len(manifest) == scripts.MAX_TARGETS:
            scripts.fail('script targets resolve to more than 4,096 eligible surfaces')
        selected.add(key)
        manifest.append((item, layer))
    return manifest, skipped
