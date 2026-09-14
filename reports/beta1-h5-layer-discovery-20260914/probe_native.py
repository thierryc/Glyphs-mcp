"""H5 native API and bounded-index probe; isolated objects only, no open fonts."""
from GlyphsApp import GSFont,GSLayer
from pathlib import Path
import json,inspect,time
S=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
font=GSFont(str(S/'reports/beta1-h3-context-20260914/ContextTest.glyphs'));g=font.glyphs['control'];rows=[]
for identity,name,attr in [('H5_INTERMEDIATE','custom intermediate',{'coordinates':{font.axes[0].axisId:150}}),('H5_ALTERNATE','custom alternate',{'axisRules':{font.axes[0].axisId:{'min':500}}}),('H5_BACKUP','Duplicate',{}),('H5_BACKUP2','Duplicate',{})]:
 l=g.layers[font.masters[0].id].copy();l.name=name;l.associatedMasterId=font.masters[0].id
 for k,v in attr.items():l.attributes[k]=v
 g.setLayer_forId_(l,identity)
fields=['layerId','name','associatedMasterId','isMasterLayer','isSpecialLayer','isBraceLayer','isBracketLayer']
def read(l):
 d={}
 for k in fields:
  try:v=getattr(l,k);d[k]=v() if callable(v) else v
  except Exception as e:d[k]={'error':str(e)}
 return d
for i in range(g.countOfLayers()):rows.append(read(g.objectInLayersAtIndex_(i)))
# Compare native KVC order with wrapper order explicitly; the wrapper rescans extras.
result=dict(nativeRows=rows,wrapperRows=[read(l) for l in g.layers],nativeCount=g.countOfLayers(),nativeIndices=list(range(g.countOfLayers())),wrapperSource=inspect.getsource(type(g.layers).getByIndex),wrapperFile=inspect.getfile(type(g.layers)),masterIds=[m.id for m in font.masters],nativeMethods=['countOfLayers','objectInLayersAtIndex_'],isolated=True)
(OUT/'native-probe.json').write_text(json.dumps(result,indent=2));print('H5 PROBE',json.dumps(rows))
