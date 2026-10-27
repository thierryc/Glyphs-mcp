"""Read Glyphs syntax, never a glyphsLib font model. No source writes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

PS_TYPES = {'Stem', 'TopGhost', 'BottomGhost'}
TT_TYPES = {'TTAnchor', 'TTStem', 'TTAlign', 'TTInterpolate', 'TTDiagonal', 'TTDelta', 'TTSnap', 'TTShift'}
HELPER_TYPES = {'Corner', 'Cap', 'Brush', 'Segment'}
HINT_PARAMETERS = {'bluescale', 'blueshift', 'bluefuzz', 'familyalignmentzones', 'gethintsfrommaster', 'autohint', 'autohinting', 'disableautohinting', 'ttfzones', 'ttfstems', 'ttfautohintoptions', 'ttfautohintcontrolinstructions', 'ttfautohintreferencefont', 'ttfautohintfallbackscript', 'ttfautohintstrongstems', 'ttfautohintxheight', 'ttfautohintwindowscompatibility', 'ttfautohintdehint', 'ttfautohintadjustsubglyphs', 'ttfautohinthintranges', 'ttminimumdistance', 'ttzoneroundingthreshold', 'ttfovershootsuppressionbelowppm', 'gasptable', 'preptableassembly', 'fpgmtableassembly', 'cvttable', 'cvtvariations'}

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def file_map(source):
    source = Path(source)
    paths = sorted(source.rglob('*')) if source.is_dir() else [source]
    result = {}
    for p in paths:
        if p.is_symlink():
            raise ValueError(f'Symlink in source: {p}')
        if p.is_file() and not (source.is_dir() and p.relative_to(source).as_posix() == 'UIState.plist'):
            result[p.relative_to(source).as_posix() if source.is_dir() else p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result

def classify(raw):
    name = str(raw.get('type', ''))
    if name in HELPER_TYPES:
        return 'outline-helper'
    if name in PS_TYPES:
        return 'postscript'
    if name in TT_TYPES or name.startswith('TT'):
        return 'truetype'
    return 'unknown'  # Preserve unknown types; never silently count them as PS.

def parameters(obj):
    rows = obj.get('customParameters', [])
    return [p for p in rows if str(p.get('name', '')).lower().replace(' ', '') in HINT_PARAMETERS
            or 'hint' in str(p.get('name', '')).lower()
            or str(p.get('name', '')).lower().startswith(('ttfautohint', 'ttfzone', 'ttfstem'))]

def instance_record(obj):
    name = obj.get('name')
    properties = obj.get('properties', [])
    if not name:
        for prop in properties:
            if prop.get('key') == 'styleNames':
                entries = prop.get('values', [])
                name = next((v.get('value') for v in entries if v.get('language') == 'dflt'), None)
                name = name or prop.get('value') or next((v.get('value') for v in entries), None)
                break
    return {'id': obj.get('id'), 'name': name, 'axesValues': obj.get('axesValues'),
            'properties': properties, 'hintParameters': parameters(obj)}


def walk_layers(layer, surface='foreground'):
    yield surface, layer
    background = layer.get('background')
    if isinstance(background, dict):
        yield from walk_layers(background, surface + '/background')


def inventory_objects(info, glyphs):
    masters = info.get('fontMaster', info.get('masters', []))
    mids = {m.get('id') for m in masters}
    scopes = Counter(); classes = Counter(); types = Counter(); hinted_glyphs = set(); records = []; dependencies = {}
    total_layers = 0
    for glyph in glyphs:
        name = glyph.get('glyphname', glyph.get('name'))
        if not name:
            raise ValueError('Glyph without identity')
        consumers = set()
        for layer in glyph.get('layers', []):
            total_layers += 1
            lid = layer.get('layerId'); assoc = layer.get('associatedMasterId')
            role = 'master' if lid in mids else 'special-or-backup'
            for surface, obj in walk_layers(layer):
                for shape in obj.get('shapes', []) + obj.get('components', []):
                    if isinstance(shape, dict):
                        provider = shape.get('ref', shape.get('name'))
                        if provider:
                            consumers.add(provider)
                hints = obj.get('hints', [])
                for index, raw in enumerate(hints):
                    if not isinstance(raw, dict):
                        raise ValueError(f'Invalid hint in {name}/{lid}')
                    kind = classify(raw); scope = f'{role}/{surface}'
                    classes[kind] += 1; types[str(raw.get('type', 'unknown'))] += 1; scopes[scope] += 1
                    if role == 'master' and surface == 'foreground':
                        hinted_glyphs.add(name)
                    records.append({'glyph': name, 'export': glyph.get('export', 1) != 0,
                                    'layer': lid, 'associatedMaster': assoc, 'scope': scope,
                                    'index': index, 'class': kind, 'type': raw.get('type'),
                                    'linked': bool(raw.get('origin') is not None or raw.get('target') is not None),
                                    'raw': raw})
        dependencies[name] = sorted(consumers)
    return {'schemaVersion': 1, 'glyphCount': len(glyphs), 'layerCount': total_layers,
            'hintCount': len(records), 'masterForegroundHintedGlyphs': len(hinted_glyphs),
            'countsByScope': dict(scopes), 'countsByClass': dict(classes), 'countsByRawType': dict(types),
            'fontParameters': parameters(info), 'stemDefinitions': info.get('stems', []),
            'masters': [{k: m.get(k) for k in ['id', 'name', 'stemValues', 'metricValues', 'alignmentZones']}
                        | {'hintParameters': parameters(m)} for m in masters],
            'instances': [instance_record(i) for i in info.get('instances', [])],
            'componentProviders': dependencies, 'hints': records,
            'limitations': ['Saved source only; unsaved editor state is not inspected.',
                            'Opaque userData/archive blobs are preserved but not interpreted.',
                            'Raw type classification is provisional for unknown/new hint kinds; native flags take precedence.',
                            'Linked references are reported, not validated against node topology.']}


def audit(source):
    from glyphsLib.parser import Parser
    source = Path(source).resolve(); before = file_map(source)
    parse = lambda p: Parser().parse(p.read_text(encoding='utf-8'))
    if source.is_dir():
        if source.suffix != '.glyphspackage':
            raise ValueError('Expected .glyphspackage')
        info = parse(source / 'fontinfo.plist')
        glyphs = [parse(p) for p in sorted((source / 'glyphs').glob('*.glyph'))]
        if not glyphs:
            raise ValueError('No per-glyph records found')
    else:
        info = parse(source); glyphs = info['glyphs']
    result = inventory_objects(info, glyphs)
    after = file_map(source)
    if before != after:
        raise RuntimeError('Source changed during inventory; discard this mixed-state report')
    return result | {'source': str(source), 'sourceFiles': before, 'sourceSHA256': digest(before),
                     'sourceUnchanged': True, 'sourceFormat': info.get('.formatVersion', 'not-declared')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    source = a.source.resolve(); output = a.output.resolve()
    if output == source or (source.is_dir() and source in output.parents):
        raise ValueError('Report must be outside font source')
    result = audit(source)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2, ensure_ascii=False); out.write('\n')
    print(json.dumps({k: result[k] for k in ['glyphCount', 'layerCount', 'hintCount', 'countsByScope', 'countsByClass', 'masterForegroundHintedGlyphs', 'sourceSHA256', 'sourceUnchanged']}))

if __name__ == '__main__':
    main()
