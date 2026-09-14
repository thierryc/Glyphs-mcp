"""Generate H4 fixtures and qualify the source on isolated native Glyphs objects.
Run with glyphs run --app '/Applications/Glyphs 4.app' --plugins '' SCRIPT.
Only harness oracles traverse complete fonts. The candidate only reads pages.
"""
from pathlib import Path
from types import SimpleNamespace as NS
import hashlib,json,re,sys,time,statistics
from GlyphsApp import GSFont,GSGlyph
S=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
for part in ('protocol','bridge'):sys.path.insert(0,str(S/'src'/part))
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
BASE=S/'reports/beta1-h3-context-20260914/ContextTest.glyphs'
source=json.loads((S/'reports/rv01-realistic-20260914/font-source/SOURCE.json').read_text())
real=Path(source['files'][0]['local'])
assert hashlib.sha256(real.read_bytes()).hexdigest()==source['files'][0]['sha256']
checks=[];fixtures=[]
def check(name,expected,observed):
 checks.append(dict(name=name,expected=expected,observed=observed,passed=expected==observed));assert expected==observed,name
for count in (0,1,100,101):
 path=OUT/('GlyphInventory%d.glyphs'%count)
 if not path.exists():
  font=GSFont(str(BASE));template=font.glyphs['control'].copy()
  for glyph in list(font.glyphs):del font.glyphs[glyph.name]
  for i in range(count):g=template.copy();g.name='h4g%03d'%i;font.glyphs.append(g)
  font.familyName='H4 Glyph Inventory %d'%count;font.save(str(path))
  text=re.sub(r'(?m)^\.appVersion = .*?;', '.appVersion = "4107";',path.read_text(),count=1)
  text=re.sub(r'(?m)^(date|lastChange) = "[^"]*";',r'\1 = "2026-09-14 17:00:00 +0000";',text);path.write_text(text)
 fixtures.append(dict(label=str(count),path=str(path),sourceSHA256=hashlib.sha256(path.read_bytes()).hexdigest()))
fixtures.append(dict(label='RobotoSlab',path=str(real),sourceSHA256=source['files'][0]['sha256']))
ns={'__file__':str(S.parents[2]/'scripts/selection_fixture.py'),'__name__':'h4_oracle'}
exec(compile(Path(ns['__file__']).read_text(),ns['__file__'],'exec'),ns)
def proof(font):return hashlib.sha256(json.dumps(ns['snapshot'](font),sort_keys=True).encode()).hexdigest()
for fixture in fixtures:
 font=GSFont(fixture['path']);bridge=GlyphsAdapter(NS(fonts=[font],font=font));doc=bridge._id(font)
 expected=[g.name for g in font.glyphs];before=proof(font);names=[];cursor=None;samples=[]
 while True:
  selector=dict(kind='glyphs',limit=100,**({'cursor':cursor} if cursor else {}));start=time.perf_counter()
  result=bridge.read_entities(doc,[selector],['name'])[0]['values'];samples.append((time.perf_counter()-start)*1000)
  names.extend(x['name'] for x in result['items']);cursor=result['nextCursor']
  check(fixture['label']+' count',len(expected),result['total'])
  if cursor is None:break
 check(fixture['label']+' exact native order',expected,names)
 check(fixture['label']+' completeness',True,result['complete'])
 check(fixture['label']+' native preservation',before,proof(font))
 check(fixture['label']+' file immutable',fixture['sourceSHA256'],hashlib.sha256(Path(fixture['path']).read_bytes()).hexdigest())
 fixture.update(total=len(expected),names=expected,masters=[dict(id=m.id,name=m.name) for m in font.masters],pageMs=samples)
(OUT/'fixtures.json').write_text(json.dumps(dict(realSource=source,fixtures=fixtures),indent=2))
(OUT/'native-source.json').write_text(json.dumps(dict(passed=True,checks=checks,module=str(Path(sys.modules['glyphs_mcp_bridge.glyph_inventory'].__file__)),scope='isolated native source; installed HTTP qualification separate'),indent=2))
print('H4 SOURCE',len(checks),'checks passed')
