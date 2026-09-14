"""Independent native proof; may traverse test fonts, never supplies MCP results."""
from GlyphsApp import GSPath
import objc,json,hashlib
FIELDS=('id','name','associatedMasterId','isMasterLayer','isSpecialLayer','isBraceLayer','isBracketLayer')
def native_id(obj):return int(objc.pyobjc_id(obj)) if obj is not None else None
def val(owner,name):
 v=getattr(owner,name);return v() if callable(v) else v
def mapping(proxy):return json.loads(json.dumps(dict(proxy),default=str,sort_keys=True))
def metadata(layer):return {k:val(layer,'layerId' if k=='id' else k) for k in FIELDS}
def rows(glyph):return [metadata(glyph.objectInLayersAtIndex_(i)) for i in range(glyph.countOfLayers())]
def shapes(layer):
 result=[]
 for s in layer.shapes:
  if isinstance(s,GSPath):result.append(dict(object=native_id(s),kind='path',closed=bool(s.closed),nodes=[dict(object=native_id(n),x=n.position.x,y=n.position.y,type=str(n.type),smooth=bool(n.smooth),name=n.name,userData=mapping(n.userData)) for n in s.nodes]))
  else:result.append(dict(object=native_id(s),kind='component',reference=s.componentName,transform=list(s.transform),alignment=s.alignment))
 return result
def layer_data(layer):
 return dict(object=native_id(layer),width=layer.width,keys=[layer.leftMetricsKey,layer.rightMetricsKey,layer.widthMetricsKey],shapes=shapes(layer),anchors=[dict(object=native_id(a),name=a.name,x=a.position.x,y=a.position.y) for a in layer.anchors],guides=[dict(object=native_id(g),x=g.position.x,y=g.position.y,angle=g.angle) for g in layer.guides],hints=[dict(object=native_id(h),originNode=native_id(h.originNode),targetNode=native_id(h.targetNode),type=str(h.type),horizontal=bool(h.horizontal)) for h in layer.hints],userData=mapping(layer.userData))
def snapshot(font):
 glyphs=[]
 for g in font.glyphs:
  layers=[]
  for l in g.pyobjc_instanceMethods.layers().allValues():
   r=dict(metadata=metadata(l),data=layer_data(l),attributes=mapping(l.attributes),background=layer_data(l.background) if val(l,'hasBackground') else None);layers.append(r)
  glyphs.append(dict(name=g.name,id=g.id,object=native_id(g),layers=sorted(layers,key=lambda r:r['metadata']['id'])))
 return dict(masters=[dict(id=m.id,name=m.name,object=native_id(m)) for m in font.masters],glyphs=glyphs)
def digest(data):return hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest()
