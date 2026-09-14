# MenuTitle: RV02 Master Audit
"""Bounded read-only Glyphs 4 audit. Call audit(font, glyph_names, master_ids)."""
from GlyphsApp import OFFCURVE
REVISION=1

def native_value(obj,name):
 value=getattr(obj,name)
 return value() if callable(value) else value

def audit(font,glyph_names,master_ids):
 if not glyph_names or len(glyph_names)>20:raise ValueError('Supply 1–20 glyph names')
 if not master_ids or len(master_ids)>32:raise ValueError('Supply 1–32 exact master IDs')
 available={m.id for m in font.masters}
 if not set(master_ids)<=available:raise ValueError('Unknown master ID')
 rows=[]
 for name in glyph_names:
  g=font.glyphs[name]
  if g is None:raise ValueError('Missing glyph: '+name)
  for mid in master_ids:
   l=g.layers[mid];nodes=[n for p in l.paths for n in p.nodes]
   row=dict(glyph=name,layer=l.layerId,width=float(l.width),paths=len(l.paths),components=len(l.components),nodes=len(nodes),offcurve=sum(n.type==OFFCURVE for n in nodes),mastersCompatible=bool(native_value(g,'mastersCompatible')))
   rows.append(row)
 return dict(revision=REVISION,total=len(rows),returned=len(rows),complete=True,rows=rows)
