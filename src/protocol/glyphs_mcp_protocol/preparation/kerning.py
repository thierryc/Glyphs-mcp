"""Read exact native entries in scheduled chunks; never call a live setter."""
from .. import kerning_edits as contract


def prepare_iter(font, request):
    rows = contract.validate_options(request['options'])['edits']
    needed = {s['key'] for row in rows for s in (row['left'], row['right']) if s['kind'] == 'group'}
    anchors = {}
    if needed:
        # Resolve only requested groups, one glyph per scheduling step. Keep one
        # anchor per group instead of a font-wide glyph map or membership copy.
        for glyph in font.glyphs:
            for prefix, side in contract.GROUPS.items():
                group = getattr(glyph, side + 'KerningGroup', None)
                key = prefix + str(group) if group else None
                if key in needed and key not in anchors: anchors[key] = contract.glyph_state(glyph)
            yield
            if len(anchors) == len(needed): break
        if needed - anchors.keys():
            contract.fail('Kerning groups have no available members: ' + ', '.join(sorted(needed - anchors.keys())), 'target_not_found')
    changes, report = [], []
    for row in rows:
        master = font.masters[row['master']]
        if master is None or str(master.id) != row['master']:
            contract.fail('Kerning master is unavailable: ' + row['master'], 'target_not_found')
        keys, guard = {}, {}
        for side in ('left', 'right'):
            item = row[side]
            key = item.get('key', item.get('name'))
            if item['kind'] == 'group': state = anchors[key]
            else:
                glyph = font.glyphs[key]
                if glyph is None or str(glyph.name) != key:
                    contract.fail('Kerning glyph is unavailable: ' + key, 'target_not_found')
                state = contract.glyph_state(glyph)
            keys[side], guard[side] = key, state
        target = dict(master=row['master'], direction=row['direction'], **keys)
        before = contract.read_stored(font, row['master'], keys['left'], keys['right'], row['direction'])
        if before is not None: contract.number(before)
        after = row.get('value')
        changed = before != after
        if changed: changes.append(dict(kind='kerning', **target, before=before, after=after, targetGuard=guard))
        report.append(dict(**target, op=row['op'], before=before, after=after, status='changed' if changed else 'unchanged'))
        yield
    return changes, dict(kind='kerning_edit', pairs=report, targetCount=len(rows), changedCount=len(changes),
                         noChangeCount=len(rows)-len(changes),
                         claim='Exact stored entries only. Zero is stored; remove deletes an entry and may reveal inherited kerning. No collision analysis or group expansion. Application never saves.')
