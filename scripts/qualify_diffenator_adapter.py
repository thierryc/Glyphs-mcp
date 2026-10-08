#!/usr/bin/env python3
"""Exercise the pinned adapter with compiled fixtures, without Glyphs or installation."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def make_font(path, *, width=400, variable=False, style='Regular'):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib.tables.TupleVariation import TupleVariation
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(['.notdef', 'A'])
    builder.setupCharacterMap({65: 'A'})
    empty = TTGlyphPen(None)
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0)); pen.lineTo((width, 0)); pen.lineTo((width, 700)); pen.lineTo((50, 700)); pen.closePath()
    builder.setupGlyf({'.notdef': empty.glyph(), 'A': pen.glyph()})
    builder.setupHorizontalMetrics({'.notdef': (500, 0), 'A': (600, 50)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(dict(familyName='Comparison Fixture', styleName=style,
                               uniqueFontIdentifier='Comparison Fixture ' + style,
                               fullName='Comparison Fixture ' + style, psName='ComparisonFixture-' + style))
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost(); builder.setupMaxp()
    if variable:
        builder.setupFvar([('wght', 100, 400, 900, 'Weight')],
                          [dict(location={'wght': 400}, stylename='Regular'), dict(location={'wght': 700}, stylename='Bold')])
        builder.setupGvar({'.notdef': [], 'A': [TupleVariation({'wght': (0, 1, 1)},
                                                            [(0, 0), (100, 0), (100, 0), (0, 0), None, None, None, None])]})
    builder.save(path)


def qualify(python, unicode_data, output):
    output.mkdir(parents=True, exist_ok=False)
    paths = {name: output / (name + '.ttf') for name in ('before', 'after', 'variable-before', 'variable-after', 'variable-moved', 'bold')}
    make_font(paths['before']); make_font(paths['after'], width=450)
    make_font(paths['variable-before'], variable=True); make_font(paths['variable-after'], width=450, variable=True)
    make_font(paths['bold'], style='Bold')
    from fontTools.ttLib import TTFont
    with TTFont(paths['variable-before']) as moved:
        moved['fvar'].instances[0].coordinates['wght'] = 500
        moved.save(paths['variable-moved'])
    words = output / 'words.csv'; words.write_text('A,latn,dflt\n')
    cases = [('identical', 'before', 'before', {'styles': 'instances'}),
             ('changed', 'before', 'after', {'styles': 'instances'}),
             ('custom-wordlist', 'before', 'after', {'styles': 'instances', 'userWordlist': str(words)}),
             ('variable-instances', 'variable-before', 'variable-after', {'styles': 'instances'}),
             ('variable-cross-product', 'variable-before', 'variable-after', {'styles': 'cross_product'}),
             ('variable-masters', 'variable-before', 'variable-after', {'styles': 'masters'}),
             ('variable-location-change', 'variable-before', 'variable-moved', {'styles': 'instances'}),
             ('variable-style-filter', 'variable-before', 'variable-after', {'styles': 'instances', 'filterStyles': 'Bold'}),
             ('style-mismatch', 'before', 'bold', {'styles': 'instances'})]
    results = []
    for name, before, after, options in cases:
        report = output / name
        request = dict(baseline=[str(paths[before])], candidate=[str(paths[after])],
                       options=options, output=str(report), unicodeData=str(unicode_data))
        request_path = output / (name + '.json'); request_path.write_text(json.dumps(request))
        result = subprocess.run([str(python), '-I', '-B', str(ROOT / 'src/sidecar/glyphs_mcp_sidecar/diffenator_adapter.py'),
                                 str(request_path)], capture_output=True, text=True, timeout=120)
        (output / (name + '.log')).write_text(result.stdout + result.stderr)
        if name == 'style-mismatch':
            if result.returncode == 0 or 'Style sets differ' not in result.stderr:
                raise RuntimeError('Style mismatch was not rejected')
            results.append(dict(case=name, rejected=True)); continue
        if result.returncode:
            raise RuntimeError(name + ': ' + result.stderr[-4000:])
        scope = json.loads((report / 'scope.json').read_text())['matchedStyles']
        if not (report / 'diffenator2-report.html').is_file():
            raise RuntimeError('Missing HTML report')
        if name == 'identical' and any(item['modifiedGlyphs'] for item in scope):
            raise RuntimeError('Identical outlines were reported as modified')
        if name == 'changed' and not any(item['modifiedGlyphs'] for item in scope):
            raise RuntimeError('Changed outline was not detected')
        if name == 'variable-cross-product' and {item['candidateCoordinates']['wght'] for item in scope} != {100, 400, 900}:
            raise RuntimeError('Cross product did not use min/default/max')
        if name == 'variable-location-change':
            regular = next(item for item in scope if item['candidateStyle'] == 'Regular')
            if regular['baselineCoordinates']['wght'] != 400 or regular['candidateCoordinates']['wght'] != 500 or regular['modifiedGlyphs'] == 0:
                raise RuntimeError('Named instance coordinate changes were not compared')
        if name == 'variable-style-filter' and (len(scope) != 1 or scope[0]['candidateStyle'] != 'Bold'):
            raise RuntimeError('Style filter did not select Bold')
        results.append(dict(case=name, matchedStyles=scope))
    evidence = dict(adapter='pinned Diffenator 2 implementation', cases=results, signedRuntimeVerified=False,
                    intelNativeVerified=False, installedRuntimeVerified=False)
    (output / 'qualification.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--unicode-data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(qualify(args.python.absolute(), args.unicode_data.resolve(), args.output.resolve()), indent=2))
