"""Prepare compact width/translation patches in the isolated native worker."""

from . import spacing
from glyphs_mcp_protocol import outline_hash
from glyphs_mcp_protocol.geometry import same_font_units


def layer_hash(layer, dx=0, dy=0):
    points = []
    for pi, path in enumerate(layer.paths):
        for ni, node in enumerate(path.nodes):
            points.append((node.position.x+dx, node.position.y+dy, f'path:{pi}:{ni}:{node.type}'))
    for i, component in enumerate(layer.components):
        points.append((component.position.x+dx, component.position.y+dy, f'component:{i}:{component.componentName}'))
    for i, anchor in enumerate(layer.anchors):
        points.append((anchor.position.x+dx, anchor.position.y+dy, f'anchor:{i}:{anchor.name}'))
    return outline_hash(points)


def prepare(font, request):
    options = spacing.validate_options(request.get('options', {}))
    names = set(request.get('glyphs') or [])
    found, changes, rows = set(), [], []
    for glyph in font.glyphs:
        name = str(glyph.name)
        if names and name not in names:
            continue
        found.add(name)
        for layer in glyph.layers:
            master = str(layer.associatedMasterId)
            if str(layer.layerId) != master or options['masters'] and master not in options['masters']:
                continue
            try:
                working = spacing.exact_copy(layer)
                row = spacing.suggest(font, glyph, working, options)
                if row['status'] == 'suggested':
                    target = {'glyph': name, 'layer': str(layer.layerId)}
                    dx = 0 if same_font_units(row['dx'], 0) else row['dx']
                    before, proposed = row['before']['width'], row['after']['width']
                    after = before if same_font_units(before, proposed) else proposed
                    # The proof must describe the effective patch, including
                    # bearings when a negligible translation is omitted.
                    row['after']['width'] = after
                    for bearing, delta in (('lsb', dx), ('rsb', after-before-dx)):
                        if bearing in row['before']:
                            row['after'][bearing] = row['before'][bearing] + delta
                    row['dx'] = dx
                    if not dx and after == before:
                        row.update(status='preserved', reason='below_tolerance', after=dict(row['before']))
                    if dx:
                        candidate = spacing.exact_copy(working)
                        # Match the bridge's foreground-only position writes.
                        # Whole-layer transforms also move guides and images.
                        owners = ([n for p in candidate.paths for n in p.nodes] +
                                  list(candidate.anchors) + list(candidate.components))
                        positions = [(owner.position.x + dx, owner.position.y) for owner in owners]
                        for owner, position in zip(owners, positions):
                            owner.position = position
                        refresh = getattr(candidate, 'setNeedUpdateShapes', None)
                        if callable(refresh):
                            refresh()
                        # Native curve bounds use approximate extrema. Verify
                        # physical translation through coordinates, not those
                        # cached extrema (which can differ by 0.0001 units).
                        if any((owner.position.x, owner.position.y) != position
                               for owner, position in zip(owners, positions)) or layer_hash(candidate) != layer_hash(layer, dx=dx):
                            raise ValueError('native translation did not preserve exact coordinates')
                        changes.append(dict(target, kind='translate', dx=dx, dy=0,
                                            beforeHash=layer_hash(layer), afterHash=layer_hash(candidate)))
                    if before != after:
                        changes.append(dict(target, kind='set', field='width', before=before, after=after))
            except ValueError as error:
                row = {'glyph': name, 'layer': str(layer.layerId), 'status': 'unavailable', 'reason': str(error)}
            rows.append(row)
    missing = sorted(names-found)
    if missing:
        raise ValueError('selected glyphs are missing: '+', '.join(missing[:10]))
    if not rows:
        raise ValueError('no master layers matched the spacing request')
    return changes, {'kind': 'spacing', 'layers': rows,
                     'claim': 'Reference selection and preservation of specified metrics; sampled spacing suggestions, not optimal optical spacing.'}
