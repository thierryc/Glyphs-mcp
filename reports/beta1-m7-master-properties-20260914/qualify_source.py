"""Generate stable baselines and qualify M7 using detached native fonts."""
from pathlib import Path
from types import SimpleNamespace as NS
from GlyphsApp import GSFont, GSFontMaster, GSAxis
import sys,json,hashlib,re,traceback,time
S=Path(__file__).resolve().parents[2]; OUT=Path(__file__).parent
for part in ('protocol','bridge'):sys.path.insert(0,str(S/'src'/part))
sys.path.insert(0,str(OUT));import m7_oracle as oracle
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeError
checks=[]
def check(name,wanted,got):
    checks.append(dict(name=name,expected=wanted,observed=got,passed=wanted==got))
    assert wanted==got,name
def generate(label,masters,axes):
    p=OUT/(label+'.glyphs')
    f=GSFont(str(S/'reports/beta1-h4-glyph-discovery-20260914/GlyphInventory1.glyphs'))
    f.familyName='M7 '+label
    while len(f.masters)<masters:
        m=f.masters[-1].copy();m.id='M7_TEMP_'+str(len(f.masters));f.masters.append(m)
    f.axes=[]
    for i in range(axes):
        a=GSAxis();a.axisId='a%02d'%(i+1);a.name=('Custom','Weight','Width')[i] if i<3 else 'Custom %02d'%i
        a.axisTag=('CSTM','wght','wdth')[i] if i<3 else 'X%03d'%i;f.axes.append(a)
    for mi,m in enumerate(f.masters):
        m.name='Regular'  # Existing fixed IDs and associations remain intact.
        for key,value in dict(ascender=812.375+mi,capHeight=705.125+mi,xHeight=513.875+mi,
                              descender=-212.625-mi,italicAngle=(0,-12.375,9.625)[mi%3]).items():setattr(m,key,value)
        for i,a in enumerate(f.axes):
            m.internalAxesValues[a.axisId]=mi*100+i+.125
            m.externalAxesValues[a.axisId]=mi*200+i+.625
    expected=oracle.rows(f)
    temp=OUT/(label+'.generated.glyphs');f.save(str(temp))
    text=temp.read_text();text=re.sub(r'(?m)^\.appVersion = .*?;', '.appVersion = "4107";',text,count=1)
    text=re.sub(r'(?m)^(date|lastChange) = "[^"]*";',r'\1 = "2026-09-14 19:00:00 +0000";',text)
    temp.unlink()
    if p.exists():check(label+' deterministic baseline',p.read_text(),text)
    else:p.write_text(text)
    return p,expected
try:
    sources=[]
    for label,masters,axes in [('MasterPropertiesTest',3,3),('MasterPropertiesBound',9,32)]:
        p,expected=generate(label,masters,axes);sources.append((label,p,expected))
    real=json.loads((S/'reports/rv01-realistic-20260914/font-source/SOURCE.json').read_text())
    p=Path(real['files'][0]['local']);check('Roboto source checksum',real['files'][0]['sha256'],hashlib.sha256(p.read_bytes()).hexdigest())
    sources.append(('RobotoSlab',p,None));fixtures=[]
    for label,p,expected in sources:
        f=GSFont(str(p));a=GlyphsAdapter(NS(fonts=[f],font=f));doc=a._id(f)
        before=oracle.digest(oracle.snapshot(f));rows=oracle.rows(f)
        if expected is not None:check(label+' persisted exact expected values',expected,rows)
        for m,row in zip(f.masters,rows):
            for fields in ([*oracle.FIELDS],['id','italicAngle'],['id','name'],['axes']):
                r=a.read_entities(doc,[dict(kind='master',id=m.id)],fields)[0]['values']
                check(label+' '+m.id+' '+','.join(fields),{k:row[k] for k in fields},r)
        items=[];cursor=None;limit=8 if len(f.axes)==32 else 100
        while True:
            req=dict(kind='masters',limit=limit)
            if cursor: req['cursor']=cursor
            r=a.read_entities(doc,[req],list(oracle.FIELDS))[0]['values'];items+=r['items']
            if r['complete']:break
            cursor=r['nextCursor']
        check(label+' all native pages',rows,items)
        if len(f.axes)==32:
            try:a.read_entities(doc,[dict(kind='masters')],['axes'])
            except BridgeError as e:check('native aggregate bound','invalid_request',e.code)
            else:raise AssertionError('native aggregate bound not enforced')
        check(label+' exact preservation',before,oracle.digest(oracle.snapshot(f)))
        fixtures.append(dict(label=label,path=str(p),sourceSHA256=hashlib.sha256(p.read_bytes()).hexdigest(),expected=rows))
    # Detached edge cases; these do not alter the saved baseline.
    f=GSFont(str(sources[0][1]));a=GlyphsAdapter(NS(fonts=[f]));doc=a._id(f);m=f.masters[0]
    f.axes=list(reversed(list(f.axes)))
    check('reordered axes exact native IDs',oracle.rows(f)[0]['axes'],a.read_entities(doc,[dict(kind='master',id=m.id)],['axes'])[0]['values']['axes'])
    f.axes=[]
    check('native zero axes',dict(items=[],total=0,returned=0,complete=True),a.read_entities(doc,[dict(kind='master',id=m.id)],['axes'])[0]['values']['axes'])
    (OUT/'fixtures.json').write_text(json.dumps(dict(fixtures=fixtures,realSource=real),indent=2))
    facts=dict(passed=True,checks=checks)
except Exception:facts=dict(passed=False,checks=checks,error=traceback.format_exc())
(OUT/'native-source.json').write_text(json.dumps(facts,indent=2));print('M7 SOURCE',len(checks),facts['passed'],facts.get('error',''))
if not facts['passed']:raise RuntimeError(facts['error'])
