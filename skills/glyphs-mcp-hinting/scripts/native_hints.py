"""Native GSHint classification. Accept an explicit font; never use Glyphs.font."""
import argparse
from collections import Counter
import json
from pathlib import Path
from source_hints import file_map, digest, HINT_PARAMETERS


def value(obj, key):
    v = getattr(obj, key)
    return v() if callable(v) else v


def plain(obj):
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): plain(v) for k, v in obj.items()}
    if hasattr(obj, 'x') and hasattr(obj, 'y'):
        return [float(obj.x), float(obj.y)]
    if hasattr(obj, 'width') and hasattr(obj, 'height'):
        return [float(obj.width), float(obj.height)]
    if hasattr(obj, 'length') and hasattr(obj, 'indexAtPosition_'):
        return [int(obj.indexAtPosition_(i)) for i in range(int(obj.length()))]
    try:
        return [plain(v) for v in obj]
    except TypeError:
        return {'nativeClass': type(obj).__name__, 'description': str(obj)}


def hint_record(hint):
    errors = {}; row = {}
    for key in ['type', 'horizontal', 'isPostScript', 'isTrueType', 'isCorner', 'position', 'width',
                'originIndex', 'targetIndex', 'otherIndex1', 'otherIndex2', 'stem', 'options', 'name']:
        try:
            row[key] = plain(value(hint, key))
        except (AttributeError, TypeError, ValueError) as e:
            errors[key] = str(e)
    row['class'] = ('outline-helper' if row.get('isCorner') else 'postscript' if row.get('isPostScript')
                    else 'truetype' if row.get('isTrueType') else 'unknown')
    if errors:
        row['unavailable'] = errors
    return row


def hint_parameters(obj):
    out = []
    for p in obj.customParameters:
        name = str(p.name); normalized = name.lower().replace(' ', '')
        if normalized in HINT_PARAMETERS or 'hint' in normalized or normalized.startswith(('ttfautohint', 'ttfzone', 'ttfstem')):
            out.append({'name': name, 'value': plain(p.value)})
    return out


def inventory(font):
    """Read all native foreground layers, and backgrounds when a presence API exists."""
    counts = Counter(); scopes = Counter(); rows = []; layers = 0; unavailable = []
    mids = {str(m.id) for m in font.masters}
    for glyph in font.glyphs:
        for layer in glyph.layers:
            layers += 1; lid = str(layer.layerId); role = 'master' if lid in mids else 'special-or-backup'
            surfaces = [('foreground', layer)]
            try:
                has_background = bool(value(layer, 'hasBackground'))
            except AttributeError:
                has_background = False
                if 'background-presence-api' not in unavailable:
                    unavailable.append('background-presence-api')
            if has_background:
                surfaces.append(('foreground/background', layer.background))
            for surface, owner in surfaces:
                for i, hint in enumerate(owner.hints):
                    r = hint_record(hint); scope = role + '/' + surface
                    counts[r['class']] += 1; scopes[scope] += 1
                    rows.append({'glyph': str(glyph.name), 'layer': lid, 'scope': scope, 'index': i, **r})
    return {'schemaVersion': 1, 'family': str(font.familyName), 'glyphCount': len(font.glyphs),
            'layerCount': layers, 'hintCount': len(rows), 'countsByClass': dict(counts), 'countsByScope': dict(scopes),
            'fontParameters': hint_parameters(font),
            'instances': [{'id': plain(value(i, 'id')), 'name': str(i.name), 'active': bool(i.active),
                           'hintParameters': hint_parameters(i)} for i in font.instances],
            'masters': [{'id': str(m.id), 'name': str(m.name), 'stems': plain(list(m.stems)),
                         'zones': [{'position': float(z.position), 'size': float(z.size)} for z in m.alignmentZones],
                         'hintParameters': hint_parameters(m)} for m in font.masters],
            'hints': rows, 'unavailable': unavailable,
            'limitations': ['Opaque userData archives are not decoded.',
                            'If background-presence API is unavailable, use the raw saved-source inventory for backgrounds.',
                            'Stem sentinel values are retained as native integers, not assumed valid indexes.',
                            'Native point-link indexes are inventoried, not validated.']}


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--source', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); source = a.source.resolve(); output = a.output.resolve()
    if output == source or (source.is_dir() and source in output.parents):
        raise ValueError('Report must be outside font source')
    before = file_map(source)
    from Foundation import NSURL
    from GlyphsApp import GSFont
    font, error = GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(str(source)), None)
    if font is None:
        raise RuntimeError(str(error))
    result = inventory(font)
    if before != file_map(source):
        raise RuntimeError('Source changed during native read')
    result.update({'source': str(source), 'sourceSHA256': digest(before), 'sourceUnchanged': True})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2, ensure_ascii=False); out.write('\n')
    print(json.dumps({k: result[k] for k in ['glyphCount', 'layerCount', 'hintCount', 'countsByClass', 'countsByScope', 'sourceUnchanged', 'unavailable']}))

if __name__ == '__main__':
    main()
