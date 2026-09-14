"""Reproduce H3 timing and token estimates; no native or network access."""
from pathlib import Path
import json, statistics, math, os, sys, gzip
sys.path.insert(0,'/private/tmp/glyphs-metadata-tokenizer-20260910')
os.environ.setdefault('TIKTOKEN_CACHE_DIR','/private/tmp/glyphs-metadata-tokenizer-cache')
import tiktoken
enc=tiktoken.get_encoding('o200k_base')
OUT=Path(__file__).resolve().parent
source=OUT/'native-facts.json'
facts=json.loads(source.read_text() if source.exists() else gzip.decompress(source.with_suffix('.json.gz').read_bytes()))
def stats(xs):
    xs=sorted(xs)
    return dict(n=len(xs),median=statistics.median(xs),minimum=xs[0],maximum=xs[-1],p95=xs[math.ceil(.95*len(xs))-1]) if xs else None
def tok(value):return len(enc.encode(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)))
result=dict(tokenMethod='tiktoken '+tiktoken.__version__+' / o200k_base; sorted compact JSON with literal Unicode; {name,arguments} and one parsed response body; estimated tokens, not billed usage',timings={},tokens={},calls=len(facts['calls']),harnessErrors=facts.get('harnessErrors',[]),loadBefore=facts['loadBefore'],loadAfter=facts['loadAfter'])
for size in ('small','bounded'):
    reps=[x for x in facts['timings'] if x['size']==size and x['phase'].startswith('rep')]
    result['timings'][size]={key:stats([r[key] for r in reps]) for key in ('httpReadMs','discoveryMs','initialTotalMs')}
    result['timings'][size]['firstAndWarmup']=[x for x in facts['timings'] if x['size']==size and not x['phase'].startswith('rep')]
for count in (2,109):
    calls=[c for c in facts['calls'] if c['tool']=='read_entities' and c['phase'].startswith('rep') and c['result']['data'][0]['values'].get('selectedGlyphs',{}).get('total')==count]
    result['tokens'][str(count)]={'request':stats([tok(dict(name=c['tool'],arguments=c['arguments'])) for c in calls]),'response':stats([tok(c['result']) for c in calls])}
    result['timings']['nativeContext'+str(count)]={key:stats([n[key] for c in calls for n in c['nativeCallbacks']]) for key in ('queueMs','callbackMs')}
result['nativeAllCallbacks']={key:stats([n[key] for n in facts['nativeCallbacks']]) for key in ('queueMs','callbackMs')}
result['callCounts']={tool:sum(c['tool']==tool for c in facts['calls']) for tool in ('get_status','list_documents','read_entities')}
result['toolErrors']=[dict(arguments=c['arguments'],error=c['result']['error']) for c in facts['calls'] if not c['result'].get('ok')]
latest={c['name']:c for c in facts['checks']}
result['uniqueChecks']=len(latest);result['uniquePassed']=sum(c['passed'] for c in latest.values())
result['rawChecks']=len(facts['checks']);result['rawPassed']=sum(c['passed'] for c in facts['checks'])
result['nativeRunPassed']=facts['passed'];result['cleanupError']=facts.get('cleanupError')
result['skillTextTokens']={name:len(enc.encode((OUT.parents[1]/'skills/glyphs'/name).read_text())) for name in ('SKILL.md','references/context-reads.md')}
result['runtime']={p:facts['runtime'].get(p) for p in ('runtimeId','codeHash','release')};result['runtime']['bridge']=facts['runtime']['bridge']
(OUT/'analysis.json').write_text(json.dumps(result,indent=2))
with (OUT/'calls.jsonl').open('w') as f:
    for call in facts['calls']:f.write(json.dumps(call,ensure_ascii=False)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('toolErrors','runtime','harnessErrors')},indent=2))
