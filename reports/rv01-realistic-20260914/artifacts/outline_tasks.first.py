"""Explicit, bounded native Glyphs 4 benchmark actions. No automatic font selection."""
from GlyphsApp import GSNode,LINE,CURVE,OFFCURVE

def layers(font,name,master_ids):
 g=font.glyphs[name]
 if g is None:raise ValueError('Missing glyph: '+name)
 if not master_ids or len(master_ids)>32:raise ValueError('Supply 1–32 exact master IDs')
 if any(mid not in [m.id for m in font.masters] for mid in master_ids):raise ValueError('Unknown master')
 return [g.layers[mid] for mid in master_ids]

def adjust_handle(font,master_ids):
 targets=layers(font,'o',master_ids);result=[]
 for l in targets:
  p=l.paths[0];idx=next(i for i,n in enumerate(p.nodes) if n.type==OFFCURVE)
  n=p.nodes[idx];n.position=(n.position.x+2.5,n.position.y);result.append(dict(layer=l.layerId,path=0,node=idx))
 return result

def add_stem_midpoint(font,master_ids):
 result=[]
 for l in layers(font,'H',master_ids):
  p=l.paths[0];a,b=p.nodes[0],p.nodes[1]
  if a.type!=LINE or b.type!=LINE:raise ValueError('Expected an explicit straight segment')
  n=GSNode(((a.position.x+b.position.x)/2,(a.position.y+b.position.y)/2),LINE)
  p.nodes.insert(1,n);result.append(dict(layer=l.layerId,path=0,node=1))
 return result

def remove_stem_midpoint(font,master_ids):
 targets=layers(font,'H',master_ids)
 # Verify every layer before changing any layer. Only the explicit seeded node.
 for l in targets:
  p=l.paths[0];a,n,b=list(p.nodes)[:3]
  if len(p.nodes)!=31 or any(x.type!=LINE for x in (a,n,b)):raise ValueError('Expected a 31-node seeded stem')
  if (n.position.x,n.position.y)!=((a.position.x+b.position.x)/2,(a.position.y+b.position.y)/2):raise ValueError('Point is not the exact redundant midpoint')
 for l in targets:del l.paths[0].nodes[1]
 return len(targets)

def add_extrema(font,master_ids):
 result=[]
 for l in layers(font,'at',master_ids):
  before=[len(p.nodes) for p in l.paths]
  for p in l.paths:p.addNodesAtExtremes(force=False,checkSelection=False)
  result.append(dict(layer=l.layerId,before=before,after=[len(p.nodes) for p in l.paths]))
 return result

def split_o_midpoint(font,master_ids):
 # One explicit homologous first cubic, across all masters; no correspondence engine.
 targets=layers(font,'o',master_ids)
 for l in targets:
  p=l.paths[0]
  if [n.type for n in list(p.nodes)[3:7]]!=[LINE,OFFCURVE,OFFCURVE,CURVE]:raise ValueError('Unexpected first cubic topology')
 for l in targets:
  p=l.paths[0];a,h1,h2,b=list(p.nodes)[3:7]
  def xy(n):return (float(n.position.x),float(n.position.y))
  def mid(u,v):return ((u[0]+v[0])/2,(u[1]+v[1])/2)
  A,B,C,D=map(xy,(a,h1,h2,b));AB,BC,CD=mid(A,B),mid(B,C),mid(C,D)
  ABC,BCD=mid(AB,BC),mid(BC,CD);M=mid(ABC,BCD)
  # Keep all existing objects. Existing handles become the two handles of left half.
  h1.position=AB;h2.position=ABC
  middle=GSNode(M,CURVE);middle.smooth=True
  p.nodes.insert(6,middle);p.nodes.insert(7,GSNode(BCD,OFFCURVE));p.nodes.insert(8,GSNode(CD,OFFCURVE))
 return len(targets)
