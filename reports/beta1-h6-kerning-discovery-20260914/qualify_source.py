"""Generate the reproducible H6 fixture and qualify native source before install."""
from pathlib import Path
from types import SimpleNamespace as NS
import hashlib,json,re,sys,traceback
from GlyphsApp import GSFont,GSGlyph
S=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
for part in ('protocol','bridge'):sys.path.insert(0,str(S/'src'/part))
sys.path.insert(0,str(OUT));import h6_oracle as oracle
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeError
p=OUT/'KerningDiscoveryTest.glyphs'
if not p.exists():
 f=GSFont(str(S/'reports/beta1-h4-glyph-discovery-20260914/GlyphInventory1.glyphs'));g=f.glyphs[0];g.name='A';g.id='H6_A';f.familyName='H6 Kerning Discovery'
 for name in ('V','ungrouped'):
  clone=g.copy();clone.name=name;clone.id='H6_'+name;f.glyphs.append(clone)
 for side in ('left','right','top','bottom'):setattr(g,side+'KerningGroup',side+'A')
 f.glyphs['V'].leftKerningGroup='V'
 for mi,m in enumerate(f.masters):
  for d in (0,2,4):
   f.setKerningForPair(m.id,'A','V',-.125-mi-d,direction=d)
   f.setKerningForPair(m.id,'V','A',0,direction=d)
   f.setKerningForPair(m.id,'@MMK_L_rightA','@MMK_R_V',-45.25-mi-d,direction=d)
   if mi==1:
    for i in range(305):f.setKerningForPair(m.id,'@MMK_L_%03d'%i,'@MMK_R_V',-i-.25,direction=d)
 f.save(str(p));s=p.read_text();s=re.sub(r'(?m)^\.appVersion = .*?;', '.appVersion = "4107";',s,count=1);s=re.sub(r'(?m)^(date|lastChange) = "[^"]*";',r'\1 = "2026-09-14 19:00:00 +0000";',s);p.write_text(s)
source=json.loads((S/'reports/rv01-realistic-20260914/font-source/SOURCE.json').read_text());real=Path(source['files'][0]['local'])
assert hashlib.sha256(real.read_bytes()).hexdigest()==source['files'][0]['sha256']
checks=[];fixtures=[]
def check(name,expected,observed):
 checks.append(dict(name=name,expected=expected,observed=observed,passed=expected==observed));assert expected==observed,name
for label,path in (('synthetic',p),('RobotoSlab',real)):
 f=GSFont(str(path));a=GlyphsAdapter(NS(fonts=[f],font=f));doc=a._id(f);before=oracle.digest(oracle.snapshot(f));expected={}
 for g in ([f.glyphs['A'],f.glyphs['V'],f.glyphs['ungrouped']] if label=='synthetic' else [f.glyphs['A'],f.glyphs['V'],f.glyphs['a']]):
  got=a.read_entities(doc,[dict(kind='glyph',id=g.name)],oracle.GROUP_FIELDS)[0]['values'];check(label+' groups '+g.name,{k:getattr(g,k) for k in oracle.GROUP_FIELDS},got)
 for m in f.masters:
  expected[m.id]={}
  for d in ('LTR','RTL','vertical'):
   rows=oracle.rows(f,m.id,d);expected[m.id][d]=rows;items=[];cursor=None;pages=0
   while True:
    req=dict(kind='kerning_pairs',master=m.id,direction=d,**({'cursor':cursor} if cursor else {}));r=a.read_entities(doc,[req],['left','right','value'])[0]['values'];items+=r['items'];pages+=1
    check(label+' '+m.id+' '+d+' page '+str(pages)+' bounds',True,r['returned']<=100 and r['scanned']<=256 and r['total'] is None)
    if r['complete']:check('terminal cursor',None,r['nextCursor']);break
    cursor=r['nextCursor'];assert pages<200
   check(label+' '+m.id+' '+d+' native oracle',rows,items)
   selectors=[dict(kind='kerning',master=m.id,direction=d,left=r['left']['key'] if r['left']['kind']=='group' else r['left']['glyph'],right=r['right']['key'] if r['right']['kind']=='group' else r['right']['glyph']) for r in rows]
   for offset in range(0,len(selectors),100):
    got=a.read_entities(doc,selectors[offset:offset+100],['value']);check(label+' '+m.id+' '+d+' exact roundtrip '+str(offset),[r['value'] for r in rows[offset:offset+100]],[r['values']['value'] for r in got])
 if label=='synthetic':
  m=f.masters[0].id
  # Native corruption/empty-group evidence stays on this detached disposable font.
  table=f.kerningLTR[m];inner=table.objectForKey_(table.keyAtIndex_(0));inner.setObject_forKey_(-.75,'H6_UNKNOWN')
  got=a.read_entities(doc,[dict(kind='kerning_pairs',master=m,direction='LTR')],['right'])[0]['values'];check('unresolved raw key',True,any(r['right']['kind']=='unresolved' and r['right']['key']=='H6_UNKNOWN' for r in got['items']))
  inner.removeObjectForKey_('H6_UNKNOWN')
 check(label+' exact object/data preservation',before,oracle.digest(oracle.snapshot(f)))
 fixtures.append(dict(label=label,path=str(path),sourceSHA256=hashlib.sha256(path.read_bytes()).hexdigest(),masters=[m.id for m in f.masters],expected=expected))
(OUT/'fixtures.json').write_text(json.dumps(dict(fixtures=fixtures,realSource=source),indent=2))
(OUT/'native-source.json').write_text(json.dumps(dict(passed=True,checks=checks),indent=2));print('H6 SOURCE',len(checks),'checks passed')
