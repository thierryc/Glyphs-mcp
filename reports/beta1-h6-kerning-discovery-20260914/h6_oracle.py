"""Independent full native oracle; never supplies missing public MCP results."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'beta1-h5-layer-discovery-20260914'))
import h5_oracle as base
GROUP_FIELDS=[side+suffix for side in ('left','right','top','bottom') for suffix in ('KerningGroup','KerningKey')]
TABLES={'LTR':'kerningLTR','RTL':'kerningRTL','vertical':'kerningVertical'}
def side(font,key):
 if str(key).startswith('@'):return dict(key=str(key),glyph=None,kind='group')
 g=font.glyphForId_(key);name=g.name if g is not None else None
 return dict(key=str(key),glyph=name,kind='glyph' if name else 'unresolved')
def rows(font,master,direction,left=None,right=None):
 root=getattr(font,TABLES[direction]);table=root.get(master,{}) if root is not None else {};result=[]
 for lk,group in table.items():
  if left is not None and lk!=left:continue
  for rk,v in group.items():
   if right is None or rk==right:result.append(dict(left=side(font,lk),right=side(font,rk),value=v))
 return result
def snapshot(font):
 data=base.snapshot(font)
 data['groups']={g.name:{k:getattr(g,k) for k in GROUP_FIELDS} for g in font.glyphs}
 data['kerning']={d:{str(m):{str(l):dict(r) for l,r in table.items()} for m,table in (getattr(font,attr) or {}).items()} for d,attr in TABLES.items()}
 return data
digest=base.digest
