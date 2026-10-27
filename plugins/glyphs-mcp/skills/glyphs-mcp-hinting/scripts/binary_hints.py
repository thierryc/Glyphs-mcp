"""Inventory actual CFF/CFF2 or TrueType hint data without rewriting fonts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from fontTools.ttLib import TTFont

HINT_OPS = {'hstem', 'vstem', 'hstemhm', 'vstemhm', 'hintmask', 'cntrmask'}
FLEX_OPS = {'flex', 'hflex', 'hflex1', 'flex1'}
PRIVATE_KEYS = ['BlueValues', 'OtherBlues', 'FamilyBlues', 'FamilyOtherBlues', 'BlueScale',
                'BlueShift', 'BlueFuzz', 'StdHW', 'StdVW', 'StemSnapH', 'StemSnapV',
                'ForceBold', 'LanguageGroup', 'ExpansionFactor']

def private_dicts(top):
    if hasattr(top, 'FDArray'):
        return [(i, fd.Private) for i, fd in enumerate(top.FDArray)]
    return [(0, top.Private)]

def audit(path):
    path = Path(path).resolve(); original = path.read_bytes(); sha = hashlib.sha256(original).hexdigest()
    f = TTFont(path); result = {'file': str(path), 'sha256': sha, 'glyphCount': len(f.getGlyphOrder()),
                             'container': f.flavor or 'sfnt', 'unitsPerEm': f['head'].unitsPerEm, 'variable': 'fvar' in f,
                             'axes': [{'tag': a.axisTag, 'min': a.minValue, 'default': a.defaultValue, 'max': a.maxValue}
                                      for a in f['fvar'].axes] if 'fvar' in f else []}
    if 'CFF ' in f or 'CFF2' in f:
        tag = 'CFF2' if 'CFF2' in f else 'CFF '; cff = f[tag].cff; top = cff.topDictIndex[0]
        privates = []
        for index, private in private_dicts(top):
            values = {k: getattr(private, k, None) for k in PRIVATE_KEYS}
            raw = {k: private.rawDict[k] for k in PRIVATE_KEYS if k in private.rawDict}
            zones = []
            for key in ['BlueValues', 'OtherBlues']:
                v = values[key] or []
                # Blended CFF2 data can be nested; do not pretend it is a scalar zone.
                if all(isinstance(x, (int, float)) for x in v) and len(v) % 2 == 0:
                    zones += [abs(v[i+1] - v[i]) for i in range(0, len(v), 2)]
            max_zone = max(zones, default=0); scale = values['BlueScale']
            privates.append({'index': index, 'effective': values, 'explicit': raw,
                             'maxScalarZone': max_zone,
                             'blueScaleZoneConcern': (bool(max_zone and isinstance(scale, (int, float)) and scale * max_zone > 1) if f['head'].unitsPerEm == 1000 else None),
                             'zoneCheckQualifiedAt1000UPM': f['head'].unitsPerEm == 1000,
                             'note': 'Zone concern is diagnostic, not a renderer verdict or automatic fix.'})
        # Desubroutinize in memory: counting only top-level programs misses hints in subroutines.
        cff.desubroutinize(); glyphs = []; ops = Counter(); flex = Counter()
        for name in f.getGlyphOrder():
            cs = top.CharStrings[name]; cs.decompile()
            counts = Counter(t for t in cs.program if isinstance(t, str) and t in HINT_OPS)
            fc = Counter(t for t in cs.program if isinstance(t, str) and t in FLEX_OPS)
            ops.update(counts); flex.update(fc)
            fd = int(top.FDSelect[f.getGlyphID(name)]) if hasattr(top, 'FDSelect') else 0
            glyphs.append({'glyph': name, 'fontDict': fd, 'operators': dict(counts), 'flexOperators': dict(fc)})
        result.update({'outlineFormat': tag.strip(), 'fontMatrix': getattr(top, 'FontMatrix', None), 'privateDictionaries': privates, 'glyphs': glyphs,
                       'hintOperators': dict(ops), 'flexOperators': dict(flex),
                       'glyphsWithHintOperators': sum(bool(g['operators']) for g in glyphs),
                       'limitations': ['Counts are operator occurrences, not the number of stems.',
                                       'Implied vertical stems and blend operands require CharString interpretation.',
                                       'No hint-mask semantics or variable-region safety certification.']})
    elif 'glyf' in f:
        glyphs = []; total = 0
        for name in f.getGlyphOrder():
            glyph = f['glyf'][name]; program = getattr(glyph, 'program', None)
            n = len(program.getBytecode()) if program is not None else 0
            glyphs.append({'glyph': name, 'instructionBytes': n, 'composite': glyph.isComposite()}); total += n
        result.update({'outlineFormat': 'glyf', 'glyphs': glyphs, 'instructionBytes': total,
                       'glyphsWithInstructions': sum(g['instructionBytes'] > 0 for g in glyphs),
                       'fontPrograms': {tag: len(f.getTableData(tag)) if tag in f else None for tag in ['cvt ', 'fpgm', 'prep', 'cvar']},
                       'gasp': f['gasp'].gaspRange if 'gasp' in f else None,
                       'limitations': ['Presence and byte counts do not validate bytecode behavior.']})
    else:
        raise ValueError('No supported CFF/CFF2/glyf table')
    f.close()
    if path.read_bytes() != original:
        raise RuntimeError('Input changed while reading')
    return result | {'inputUnchanged': True}

def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('fonts', type=Path, nargs='+'); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); rows = [audit(path) for path in a.fonts]
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x', encoding='utf-8') as out:
        json.dump({'schemaVersion': 1, 'fonts': rows}, out, indent=2); out.write('\n')
    print(json.dumps([{'file': r['file'], 'outlineFormat': r['outlineFormat'], 'glyphCount': r['glyphCount'],
                       'hintedGlyphs': r.get('glyphsWithHintOperators', r.get('glyphsWithInstructions')),
                       'inputUnchanged': r['inputUnchanged']} for r in rows]))

if __name__ == '__main__':
    main()
