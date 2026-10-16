"""Detached native probe; does not access or change editor documents.

glyphs run --quiet --app '/Applications/Glyphs 4.app' --plugins '' probe.py
Stdout is JSON evidence; retain stderr for native errors swallowed by evaluation.
This does not verify a live Font View sidebar.
"""
import json
import objc
from Foundation import NSPredicate, NSBundle
from GlyphsApp import GSFont, GSGlyph, Glyphs

out = {'application': dict(NSBundle.bundleWithPath_('/Applications/Glyphs 4.app').infoDictionary()).get('CFBundleShortVersionString'), 'build': dict(NSBundle.bundleWithPath_('/Applications/Glyphs 4.app').infoDictionary()).get('CFBundleVersion'), 'tests': []}
font = GSFont()
for name in ('a', 'A', 'a.sc', 'one', 'acutecomb'):
    font.glyphs.append(GSGlyph(name))
expressions = ['case == 2 AND category == "Letter"', 'case == lower AND category == "Letter"', 'glyphInfo.case == 2 AND category == "Letter"', 'subCategory == "Lowercase" AND category == "Letter"']
for expression in expressions:
    entry = {'expression': expression, 'glyphs': []}
    try:
        predicate = NSPredicate.predicateWithFormat_(expression)
        entry['parsed'] = str(predicate.predicateFormat())
        for glyph in font.glyphs:
            try:
                entry['glyphs'].append({'name': glyph.name, 'match': bool(predicate.evaluateWithObject_(glyph))})
            except Exception as error:
                entry['glyphs'].append({'name': glyph.name, 'error': str(error)})
        cls = objc.lookUpClass('GSSidebarItem')
        item = cls.alloc().init()
        item.setName_('Probe')
        item.setFont_(font)
        item.setPredicateFormat_(expression)
        entry['sidebarPredicate'] = str(item.predicate())
        entry['sidebarCount'] = item.count()
    except Exception as error:
        entry['error'] = str(error)
    out['tests'].append(entry)
first = out['tests'][0]
assert 'error' not in first, first
assert {g['name'] for g in first['glyphs'] if g.get('match')} == {'a'}, first
assert first['sidebarPredicate'] == first['expression'], first
for control in out['tests'][1:]:
    assert not any(g.get('match') for g in control['glyphs']), control
out['assertionsPassed'] = True
print(json.dumps(out, indent=2))
