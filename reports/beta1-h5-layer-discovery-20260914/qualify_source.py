"""H5 reproducible fixture and isolated native source gate; no GUI documents."""
from pathlib import Path
from types import SimpleNamespace as NS
import hashlib,json,re,sys
from GlyphsApp import GSFont,GSGlyph
S=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
for part in ('protocol','bridge'):sys.path.insert(0,str(S/'src'/part))
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
FIELDS=['id','name','associatedMasterId','isMasterLayer','isSpecialLayer','isBraceLayer','isBracketLayer']
path=OUT/'LayerDiscoveryTest.glyphs'
if not path.exists():
 f=GSFont(str(S/'reports/beta1-h4-glyph-discovery-20260914/GlyphInventory1.glyphs'));a=f.glyphs[0];a.name='a';f.familyName='H5 Layer Discovery'
 for name in ('b','many'):
  clone=a.copy();clone.name=name;f.glyphs.append(clone)
 axis=f.axes[0].axisId
 for identity,name,attrs in [('H5_INTERMEDIATE','intermediate',{'coordinates':{axis:150}}),('H5_ALTERNATE','alternate',{'axisRules':{axis:{'min':500}}}),('H5_BACKUP','Duplicate',{}),('H5_BACKUP2','Duplicate',{})]:
  layer=a.layers[f.masters[0].id].copy();layer.name=name;layer.associatedMasterId=f.masters[0].id
  for k,v in attrs.items():layer.attributes[k]=v
  if identity=='H5_BACKUP':del layer.paths[0].nodes[-1]
  a.setLayer_forId_(layer,identity)
 for i in range(102):
  layer=f.glyphs['many'].layers[f.masters[i%3].id].copy();layer.name='Duplicate';layer.associatedMasterId=f.masters[i%3].id
  f.glyphs['many'].setLayer_forId_(layer,'H5_EXTRA_%03d'%i)
 a.layers[f.masters[0].id].background.shapes.append(a.layers[f.masters[0].id].paths[0].copy())
 f.save(str(path))
 text=re.sub(r'(?m)^\.appVersion = .*?;', '.appVersion = "4107";',path.read_text(),count=1)
 text=re.sub(r'(?m)^(date|lastChange) = "[^"]*";',r'\1 = "2026-09-14 18:00:00 +0000";',text);path.write_text(text)
source=json.loads((S/'reports/rv01-realistic-20260914/font-source/SOURCE.json').read_text());real=Path(source['files'][0]['local'])
assert hashlib.sha256(real.read_bytes()).hexdigest()==source['files'][0]['sha256']
fixtures=[dict(label='synthetic',path=str(path)),dict(label='RobotoSlab',path=str(real))];checks=[]
def check(name,expected,observed):
 checks.append(dict(name=name,expected=expected,observed=observed,passed=expected==observed));assert expected==observed,name
ns={'__file__':str(S.parents[2]/'scripts/selection_fixture.py'),'__name__':'h5_oracle'}
exec(compile(Path(ns['__file__']).read_text(),ns['__file__'],'exec'),ns)
def proof(font):return hashlib.sha256(json.dumps(ns['snapshot'](font),sort_keys=True).encode()).hexdigest()
def rows(g):return [{k:getattr(g.objectInLayersAtIndex_(i),'layerId' if k=='id' else k) for k in FIELDS} for i in range(g.countOfLayers())]
for fixture in fixtures:
 fixture['sourceSHA256']=hashlib.sha256(Path(fixture['path']).read_bytes()).hexdigest();f=GSFont(fixture['path']);a=GlyphsAdapter(NS(fonts=[f],font=f));doc=a._id(f);before=proof(f);expected={}
 for name in (('a','b','many') if fixture['label']=='synthetic' else ('a','A','g','adieresis','one')):
  g=f.glyphs[name];expected[name]=rows(g);cursor=None;items=[]
  while True:
   req=dict(kind='layers',glyph=name,limit=100,**({'cursor':cursor} if cursor else {}));result=a.read_entities(doc,[req],FIELDS)[0]['values'];items.extend(result['items']);cursor=result['nextCursor']
   check(fixture['label']+' '+name+' count',len(expected[name]),result['total'])
   if result['complete']:check(name+' terminal cursor',None,cursor);break
  check(fixture['label']+' '+name+' native order/metadata',expected[name],items)
  for row in items:
   r=a.read_entities(doc,[dict(kind='layer',glyph=name,id=row['id'])],['id','name','width'])[0]['values']
   check(fixture['label']+' '+name+' exact round trip '+row['id'],dict(id=row['id'],name=row['name'],width=g.layerForId_(row['id']).width),r)
 if fixture['label']=='synthetic':
  g=f.glyphs['a'];check('intermediate native flag',True,g.layerForId_('H5_INTERMEDIATE').isBraceLayer);check('alternate native flag',True,g.layerForId_('H5_ALTERNATE').isBracketLayer)
  check('incompatible backup',True,g.layerForId_('H5_BACKUP').compareString()!=g.layers[f.masters[0].id].compareString())
  check('three masters',3,len(f.masters));check('many layers',105,g.parent.glyphs['many'].countOfLayers())
 check(fixture['label']+' native preservation',before,proof(f));check(fixture['label']+' file preserved',fixture['sourceSHA256'],hashlib.sha256(Path(fixture['path']).read_bytes()).hexdigest());fixture['expected']=expected
(OUT/'fixtures.json').write_text(json.dumps(dict(fixtures=fixtures,realSource=source),indent=2))
(OUT/'native-source.json').write_text(json.dumps(dict(passed=True,checks=checks),indent=2));print('H5 SOURCE',len(checks),'checks passed')
