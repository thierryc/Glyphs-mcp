from pathlib import Path
import json
from Foundation import NSURL
from GlyphsApp import GSFont, GSFontMaster, GSInstance, GSGlyph
import objc
root=Path(__file__).resolve().parent
rows=[]
for seeded in (False,True):
    f=GSFont();f.familyName='Probe';f.masters=[GSFontMaster()];f.instances=[GSInstance()]
    if seeded:f.glyphs.append(GSGlyph('.notdef'))
    for version in (3,4):
        p=root/f'package-probe-{seeded}-{version}.glyphspackage'
        assert not p.exists()
        f.save(str(p),formatVersion=version)
        result=GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(str(p)),None)
        doc=objc.lookUpClass('GSDocument').alloc().initWithContentsOfURL_ofType_error_(NSURL.fileURLWithPath_(str(p)),'com.glyphsapp.glyphspackage',None)
        rows.append({'seeded':seeded,'version':version,'direct':str(result),'document':str(doc)})
print(json.dumps(rows))
(root/'package-probe.json').write_text(json.dumps(rows,indent=2)+'\n')
