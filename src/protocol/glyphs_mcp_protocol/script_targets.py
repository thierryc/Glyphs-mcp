"""Immutable script target resolution without copying font contents."""
from collections.abc import Mapping
from . import scripts
from .preparation import stored_layers


def value(owner, name, default=None):
    attr = getattr(owner, name, default)
    return attr() if callable(attr) else attr


def has_content(layer):
    """Existing background content, independent of any particular callback."""
    return (any(len(value(layer, k, []) or []) for k in
                ('shapes', 'anchors', 'hints', 'guides', 'annotations', 'attributes', 'userData'))
            or value(layer, 'backgroundImage') is not None
            or any(value(layer, k) for k in ('leftMetricsKey', 'rightMetricsKey', 'widthMetricsKey')))


def owner(font, target):
    glyph = font.glyphs[target['glyph']]
    if glyph is None:
        raise ValueError('script glyph is unavailable: ' + target['glyph'])
    layer = next((l for l in stored_layers(glyph) if str(l.layerId) == target['layer']), None)
    if layer is None:
        raise ValueError('script layer is unavailable: ' + target['layer'])
    return layer


def iterate(font, spec):
    """Yield each candidate, including skips, so long empty scans can yield UI time."""
    if isinstance(spec, Mapping):
        mid = spec['master']
        if not any(str(m.id) == mid for m in font.masters):
            raise ValueError('script master is unavailable: ' + mid)
        names = (str(g.name) for g in font.glyphs) if spec['glyphs'] == 'all' else spec['glyphs']
        raw = (dict(glyph=n, layer=mid, surface=spec['surface']) for n in names)
    else:
        raw = scripts.targets(spec)
    # Bulk-all names are unique in the native collection. Explicit lists have
    # already been deduplicated during validation; retained keys stay bounded.
    selected = set()
    for item in raw:
        item = scripts.target(item)
        key = (item['glyph'], item['layer'], item['surface'])
        if key in selected:
            continue
        owning_layer = owner(font, item)
        reason = None
        layer = owning_layer
        if item['surface'] == 'background':
            if not value(owning_layer, 'hasBackground', False):
                reason = 'missing background'
            else:
                layer = owning_layer.background
                if not has_content(layer):
                    reason = 'empty background'
        if not reason: selected.add(key)
        yield item, layer, reason


def resolve(font, spec):
    """Synchronous helper for local scripting; bridge preparation consumes iterate in chunks."""
    manifest, skipped = [], dict(count=0, sample=[])
    size = 2
    for item, layer, reason in iterate(font, spec):
        if reason:
            skipped['count'] += 1
            if len(skipped['sample']) < 10:
                skipped['sample'].append(dict(item, status='skipped', reason=reason))
            continue
        size = scripts.check_size(size + len(scripts.wire_bytes(item)) + bool(manifest))
        manifest.append((item, layer))
    return manifest, skipped
