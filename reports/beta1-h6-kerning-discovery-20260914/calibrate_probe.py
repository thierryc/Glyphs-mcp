"""Detached-host instrumentation calibration; never modifies GUI documents."""
from pathlib import Path
from types import SimpleNamespace as NS
import json,sys,time,statistics,os,gzip
from GlyphsApp import GSFont
S=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
for part in ('protocol','bridge'):sys.path.insert(0,str(S/'src'/part))
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge import kerning_inventory as ki
f=GSFont(json.loads((OUT/'fixtures.json').read_bytes() if (OUT/'fixtures.json').exists() else gzip.decompress((OUT/'fixtures.json.gz').read_bytes()))['fixtures'][1]['path']);a=GlyphsAdapter(NS(fonts=[f],font=f));doc=a._id(f);req=[dict(kind='kerning_pairs',master=f.masters[0].id,direction='LTR')];fields=['left','right','value'];count0=ki._count;side0=ki._side;counts=lookups=0

def count(table):
 global counts
 counts+=1;return count0(table)
def side(font,key):
 global lookups
 lookups+=int(not key.startswith('@'));return side0(font,key)
def run(instrumented):
 ki._count=count if instrumented else count0;ki._side=side if instrumented else side0
 queued=time.perf_counter();start=time.perf_counter();value=a.read_entities(doc,req,fields);elapsed=time.perf_counter()-start
 return value,elapsed*1000
rows=[]
try:
 for i in range(16):
  values={};times={}
  for mode in ([False,True] if i%2==0 else [True,False]):values[mode],times[mode]=run(mode)
  assert values[True]==values[False]
  rows.append(dict(phase='warmup' if i==0 else 'rep'+str(i),plainMs=times[False],instrumentedMs=times[True],differenceMs=times[True]-times[False]))
finally:ki._count=count0;ki._side=side0
result=dict(samples=rows,load=os.getloadavg(),medianDifferenceMs=statistics.median(r['differenceMs'] for r in rows[1:]),note='Detached native source projection, alternating order; measures wrappers/clock noise, not live scheduling overhead. No correction subtracted from reported HTTP/native times.')
(OUT/'probe-overhead.json').write_text(json.dumps(result,indent=2));print('PROBE OVERHEAD',result['medianDifferenceMs'])
