from GlyphsApp import GSFont,GSFontMaster,GSGlyph
import json,time,statistics
f=GSFont();m=GSFontMaster();m.id='H6_M1';f.masters.append(m)
for name in ('A','V'):f.glyphs.append(GSGlyph(name))
rows=[]
for d,attr in ((0,'kerningLTR'),(2,'kerningRTL'),(4,'kerningVertical')):
 for i in range(1200):f.setKerningForPair(m.id,'@MMK_L_%04d'%i,'@MMK_R_V',-20.25,direction=d)
 table=getattr(f,attr)[m.id];times=[]
 for offset in (0,500,1000):
  for _ in range(7):
   start=time.perf_counter();items=[]
   for i in range(offset,offset+100):
    key=table.keyAtIndex_(i);inner=table.objectForKey_(key);right=inner.keyAtIndex_(0);items.append((key,right,inner.objectForKey_(right)))
   times.append((time.perf_counter()-start)*1000)
 rows.append(dict(direction=d,type=type(table).__name__,inner=type(inner).__name__,count=table.count(),first=table.keyAtIndex_(0),last=table.keyAtIndex_(1199),samplesMs=times))
print('RESULT',json.dumps(rows))
open('/private/tmp/glyphs-h6-20260914/prototype.json','w').write(json.dumps(rows,indent=2))
