"""Detached Glyphs 4 metric/axis API evidence, before bridge implementation."""
from GlyphsApp import GSFont, GSFontMaster, GSAxis
from pathlib import Path
import json

f = GSFont()
f.axes = []
for ident, name, tag in [('M7_CUSTOM', 'Custom', 'CSTM'), ('M7_WEIGHT', 'Weight', 'wght')]:
    axis = GSAxis(); axis.axisId = ident; axis.name = name; axis.axisTag = tag
    f.axes.append(axis)
m = GSFontMaster(); m.id = 'M7_M1'; f.masters.append(m)
metrics = {'ascender': 812.375, 'capHeight': 705.125, 'xHeight': 513.875,
           'descender': -212.625, 'italicAngle': -12.375}
result = {'metrics': {}, 'axes': []}
for name, wanted in metrics.items():
    setattr(m, name, wanted)
    native = getattr(m, 'default' + name[0].upper() + name[1:])()
    result['metrics'][name] = {'requested': wanted, 'wrapper': getattr(m, name), 'native': native}
for index, axis in enumerate(f.axes):
    m.internalAxesValues[axis.axisId] = index * 100 + 12.375
    m.externalAxesValues[axis.axisId] = index * 200 + 40.625
    result['axes'].append({'axisId': axis.axisId, 'tag': axis.axisTag, 'name': axis.name,
        'index': index, 'internal': m.axisInternalValueValueForId_(axis.axisId),
        'external': m.axisExternalValueValueForId_(axis.axisId),
        'wrapperInternal': m.internalAxesValues[index], 'wrapperExternal': m.externalAxesValues[index]})
result['nativeCount'] = f.countOfAxes()
result['indexedAxis'] = f.objectInAxesAtIndex_(0).axisId
f.axes = list(reversed(list(f.axes)))
result['reordered'] = [{'id': a.axisId, 'value': m.internalAxesValues[a.axisId]} for a in f.axes]
Path(__file__).with_suffix('.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
