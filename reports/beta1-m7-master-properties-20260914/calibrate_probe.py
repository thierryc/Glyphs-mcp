"""Detached calibration of the single read-tag wrapper and callback clock."""
from pathlib import Path
from types import SimpleNamespace as NS
from GlyphsApp import GSFont
import json,sys,time,statistics,os
S=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
for part in ('protocol','bridge'):sys.path.insert(0,str(S/'src'/part))
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
f=GSFont(str(OUT/'MasterPropertiesBound.glyphs'));a=GlyphsAdapter(NS(fonts=[f]));doc=a._id(f)
request=[dict(kind='masters',limit=8)];fields=['id','name','ascender','capHeight','xHeight','descender','italicAngle','axes'];tags=[];original=a.read_entities
def measured(document,entities,fields):tags.append(dict(entities=entities,fields=fields));return original(document,entities,fields)
def run(instrumented):
    a.read_entities=measured if instrumented else original;tags.clear();start=time.perf_counter()
    value=a.read_entities(doc,request,fields);elapsed=(time.perf_counter()-start)*1000
    if instrumented:dict(nativeMs=elapsed,reads=list(tags))
    return value,elapsed
rows=[]
try:
    for i in range(16):
        values={};times={}
        for mode in ([False,True] if i%2==0 else [True,False]):values[mode],times[mode]=run(mode)
        assert values[True]==values[False];rows.append(dict(phase='warmup' if i==0 else 'rep'+str(i),plainMs=times[False],instrumentedMs=times[True],differenceMs=times[True]-times[False]))
finally:a.read_entities=original
result=dict(samples=rows,load=os.getloadavg(),medianDifferenceMs=statistics.median(r['differenceMs'] for r in rows[1:]),note='Detached native source, alternating order. Wrapper/clock noise only; no live queue measurement or subtraction from reported latency.')
(OUT/'probe-overhead.json').write_text(json.dumps(result,indent=2));print('M7 calibration',result['medianDifferenceMs'])
