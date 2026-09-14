"""Generate the H3 disposable baseline using the unchanged P06 source in Glyphs 4."""
from GlyphsApp import GSFont
from pathlib import Path
import json, hashlib, re
S=Path(__file__).resolve().parents[2]
BASE=S.parents[2]/'reports/v1-v2/06-selection-inspection/SelectionInspectionTest.glyphs'
OUT=S/'reports/beta1-h3-context-20260914/ContextTest.glyphs'
assert not OUT.exists(), 'Preserve the existing H3 baseline'
font=GSFont(str(BASE));font.familyName='MCP H3 Context'
for i in range(100):
    glyph=font.glyphs['control'].copy();glyph.name='h3test%03d'%i;font.glyphs.append(glyph)
font.save(str(OUT))
text=re.sub(r'(?m)^(date|lastChange) = "[^"]*";',r'\1 = "2026-09-14 16:00:00 +0000";',OUT.read_text())
OUT.write_text(text)
OUT.with_suffix('.expected.json').write_text(json.dumps(dict(source=str(BASE),sourceSHA256=hashlib.sha256(BASE.read_bytes()).hexdigest(),sha256=hashlib.sha256(OUT.read_bytes()).hexdigest(),glyphCount=109,masters=[dict(id=m.id,name=m.name) for m in font.masters]),indent=2))
print('H3 BASELINE GENERATED',OUT)
