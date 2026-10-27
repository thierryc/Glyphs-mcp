"""Reject geometry/metric/layout drift, then render matched diagnostic glyphs."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from fontTools.ttLib import TTFont, TTLibError
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.pens.recordingPen import RecordingPen
from PIL import Image, ImageDraw, ImageFont, ImageChops, features


def geometry(font, location=None):
    gs = font.getGlyphSet(location=location); result = {}
    for n in font.getGlyphOrder():
        p = RecordingPen(); gs[n].draw(p); result[n] = p.value
    return result


def validate_location(font, location):
    if not location:
        return
    if 'fvar' not in font:
        raise ValueError('Variation location supplied for a static font')
    axes = {a.axisTag: a for a in font['fvar'].axes}
    for key, value in location.items():
        if key not in axes or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'Unknown axis or invalid variation coordinate: {key}')
        if not axes[key].minValue <= value <= axes[key].maxValue:
            raise ValueError(f'Variation coordinate outside declared range: {key}={value}')


def outline_scale(font):
    tag = 'CFF2' if 'CFF2' in font else 'CFF ' if 'CFF ' in font else None
    if not tag:
        return None
    top = font[tag].cff.topDictIndex[0]
    return {'topFontMatrix': getattr(top, 'FontMatrix', None),
            'fdFontMatrices': [getattr(fd, 'FontMatrix', None) for fd in top.FDArray] if hasattr(top, 'FDArray') else []}


def compare(base, candidate, locations=None):
    """Exact comparison. Geometry differences are reported, never waived by pixel scores."""
    a = TTFont(base); b = TTFont(candidate)
    if a.getGlyphOrder() != b.getGlyphOrder():
        raise ValueError('Different glyph order/set: not a hint-only comparison')
    rows = []
    for loc in locations or [None]:
        validate_location(a, loc); validate_location(b, loc)
        ga = geometry(a, loc); gb = geometry(b, loc)
        changed = [n for n in ga if ga[n] != gb[n]]
        rows.append({'location': loc or {}, 'changedOutlines': changed})
    metrics = [n for n in a.getGlyphOrder() if a['hmtx'][n] != b['hmtx'][n]]
    head_keys = ['unitsPerEm', 'flags', 'macStyle', 'lowestRecPPEM', 'fontDirectionHint', 'glyphDataFormat']
    head = [key for key in head_keys if getattr(a['head'], key) != getattr(b['head'], key)]
    scale_changed = outline_scale(a) != outline_scale(b)
    tables = ['head'] if head else []
    if scale_changed:
        tables.append('outline FontMatrix')
    for tag in ['cmap', 'GSUB', 'GPOS', 'GDEF', 'name', 'OS/2', 'hhea', 'vhea', 'vmtx',
                'fvar', 'avar', 'STAT', 'HVAR', 'VVAR', 'MVAR']:
        if (tag in a) != (tag in b) or (tag in a and a[tag].compile(a) != b[tag].compile(b)):
            tables.append(tag)
    a.close(); b.close()
    return {'locations': rows, 'changedMetrics': metrics, 'changedHeadFields': head,
            'outlineScaleChanged': scale_changed, 'changedTables': tables,
            'hintOnlyChecksPass': not metrics and not tables and all(not r['changedOutlines'] for r in rows)}


def render(plan, output, label_font):
    """Plan: {glyphs, sizes?, phases?, location?, modes:[{name,file},...]}."""
    if (len(plan['modes']) < 2 or not plan['glyphs'] or len(set(plan['glyphs'])) != len(plan['glyphs'])
        or len(set(m['name'] for m in plan['modes'])) != len(plan['modes'])):
        raise ValueError('Need two modes and unique explicit glyph names')
    sizes = plan.get('sizes', [12, 16, 24, 32]); phases = plan.get('phases', [0])
    if not sizes or any(not isinstance(p, int) or not 1 <= p <= 256 for p in sizes):
        raise ValueError('Sizes must be integer ppem in 1..256')
    if not phases or any(not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p < 1 for p in phases):
        raise ValueError('Phases must be finite fractions in [0,1)')
    if len(plan['glyphs']) > 65534:
        raise ValueError('Diagnostic alias range exhausted')
    output.mkdir(parents=True, exist_ok=False)
    modes = plan['modes']; names = plan['glyphs']; cp = {n: 0xF0000+i for i, n in enumerate(names)}
    binding = {str(Path(m['file']).resolve()): hashlib.sha256(Path(m['file']).read_bytes()).hexdigest() for m in modes}
    locations = list(plan.get('checkLocations') or [plan.get('location') or None])
    if plan.get('location') and plan['location'] not in locations:
        locations.append(plan['location'])
    comparisons = []
    for mode in modes[1:]:
        try:
            row = compare(modes[0]['file'], mode['file'], locations)
        except (ValueError, KeyError, TTLibError) as error:
            row = {'hintOnlyChecksPass': False, 'error': {'type': type(error).__name__, 'message': str(error)}}
        comparisons.append(row | {'mode': mode['name']})
    result = {'schemaVersion': 1, 'inputs': binding, 'preservation': comparisons, 'FreeType': features.version('freetype2'),
              'renderer': 'Pillow BASIC, grayscale; library default CFF/TT driver settings', 'location': plan.get('location', {}),
              'scope': 'Isolated glyphs; this proof does not test shaping, browser CSS or application acceptance.'}
    if not all(r['hintOnlyChecksPass'] for r in comparisons):
        (output/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
        raise ValueError('Geometry/metrics/layout/identity drift: see comparison.json; raster preference cannot approve it')
    fonts = {}
    for i, mode in enumerate(modes):
        font = TTFont(mode['file']); order = font.getGlyphOrder()
        missing = set(names)-set(order)
        if missing:
            raise ValueError(f'Missing glyphs in {mode["name"]}: {sorted(missing)}')
        sub = CmapSubtable.newSubtable(12); sub.platformID = 3; sub.platEncID = 10; sub.language = 0
        sub.cmap = {**(font.getBestCmap() or {}), **{v: k for k, v in cp.items()}}
        font['cmap'].tables = [t for t in font['cmap'].tables if not(t.platformID == 3 and t.platEncID == 10)] + [sub]
        dst = output/f'proof-{i}.otf'; font.flavor = None; font.save(dst)
        for size in sizes:
            ft = ImageFont.truetype(str(dst), size, layout_engine=ImageFont.Layout.BASIC)
            if 'fvar' in font:
                loc = plan.get('location', {}); validate_location(font, loc); ft.set_variation_by_axes([loc.get(a.axisTag, a.defaultValue) for a in font['fvar'].axes])
            elif plan.get('location'):
                raise ValueError('Variation location supplied for a static font')
            fonts[i, size] = ft
        font.close()
    # Shared bounds for every glyph/mode/phase/size; baseline fixed, no independent recentering.
    boxes = [fonts[i, p].getbbox(chr(cp[n]), anchor='ls') for i in range(len(modes)) for p in sizes for n in names]
    x0 = min(b[0] for b in boxes)-4; y0 = min(b[1] for b in boxes)-4
    x1 = max(b[2] for b in boxes)+5; y1 = max(b[3] for b in boxes)+4
    w, h = x1-x0, y1-y0
    def tile(i, n, p, phase=0):
        im = Image.new('L', (w, h), 255)
        ImageDraw.Draw(im).text((-x0+phase, -y0), chr(cp[n]), font=fonts[i, p], anchor='ls', fill=0)
        return im
    pixels = []
    for n in names:
        for p in sizes:
            for phase in phases:
                base = tile(0, n, p, phase)
                for i in range(1, len(modes)):
                    hist = ImageChops.difference(base, tile(i, n, p, phase)).histogram()
                    pixels.append({'glyph': n, 'ppem': p, 'phase': phase, 'mode': modes[i]['name'], 'changedPixels': sum(hist[1:])})
    label = ImageFont.truetype(str(label_font), 15); scale = 3; cellw = max(240, w*scale+30); cellh = h*scale+30
    pages = []
    for start in range(0, len(names), 6):
        group = names[start:start+6]; im = Image.new('L', (cellw*len(modes), 55+cellh*len(group)*len(sizes)), 255); d = ImageDraw.Draw(im)
        for i, mode in enumerate(modes):
            d.text((i*cellw+8, 10), mode['name'], font=label, fill=0)
            for ni, n in enumerate(group):
                for pi, p in enumerate(sizes):
                    y = 55+(ni*len(sizes)+pi)*cellh
                    d.text((i*cellw+8, y), f'{n} / {p}px', font=label, fill=0)
                    im.paste(tile(i, n, p).resize((w*scale, h*scale), Image.Resampling.NEAREST), (i*cellw+8, y+22))
        name = f'proof-{start//6+1:03}.png'; im.save(output/name); pages.append({'file': name, 'glyphs': group})
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest for p, digest in binding.items()):
        raise RuntimeError('Input font changed during proof')
    result.update({'pixels': pixels, 'pages': pages, 'inputFilesUnchanged': True, 'qualityWinner': 'requires visual review; pixel difference is not a score'})
    (output/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('plan', type=Path); p.add_argument('--output', type=Path, required=True); p.add_argument('--label-font', type=Path, required=True)
    a = p.parse_args(); plan = json.loads(a.plan.read_text()); r = render(plan, a.output, a.label_font)
    print(json.dumps({'pages': len(r['pages']), 'pixelComparisons': len(r['pixels']), 'preservation': 'exact', 'qualityWinner': r['qualityWinner']}))

if __name__ == '__main__':
    main()
