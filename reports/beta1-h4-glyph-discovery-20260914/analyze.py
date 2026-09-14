"""Reproduce H4 timing/token estimates offline from the recorded native run."""
from pathlib import Path
import json, statistics, math, os, sys, gzip
sys.path.insert(0, '/private/tmp/glyphs-metadata-tokenizer-20260910')
os.environ.setdefault('TIKTOKEN_CACHE_DIR', '/private/tmp/glyphs-metadata-tokenizer-cache')
import tiktoken
enc = tiktoken.get_encoding('o200k_base')
OUT = Path(__file__).resolve().parent
source = OUT / 'native-facts.json'
facts = json.loads(source.read_text() if source.exists() else gzip.decompress(source.with_suffix('.json.gz').read_bytes()))
def stats(xs):
    xs = sorted(xs)
    return dict(n=len(xs), median=statistics.median(xs), minimum=xs[0], maximum=xs[-1], p95=xs[math.ceil(.95*len(xs))-1]) if xs else None
def tok(value):
    return len(enc.encode(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)))
result = dict(tokenMethod='tiktoken '+tiktoken.__version__+' / o200k_base; sorted compact JSON with literal Unicode; {name,arguments} and one parsed response body; estimates, not billed usage', timings={}, tokens={}, loadBefore=facts['loadBefore'], loadAfter=facts['loadAfter'])
for label in ('100', '101', 'RobotoSlab'):
    reps = [t for t in facts['trials'] if t['label']==label and t['phase'].startswith('rep')]
    result['timings'][label] = {k:stats([t[k] for t in reps]) for k in ('readMs', 'discoveryMs', 'initialTotalMs')}
    result['timings'][label]['firstAndWarmup'] = [t for t in facts['trials'] if t['label']==label and not t['phase'].startswith('rep')]
    calls = [c for c in facts['calls'] if c['tool']=='read_entities' and c['phase'].startswith('rep') and c['result'].get('ok') and c['result']['data'][0]['values'].get('total')=={'100':100,'101':101,'RobotoSlab':1272}[label]]
    result['timings'][label]['pageHTTP'] = stats([c['httpMs'] for c in calls])
    result['timings'][label]['pageCallback'] = {k:stats([n[k] for c in calls for n in c['callbacks']]) for k in ('queueMs','nativeMs')}
    result['tokens'][label] = {k:stats([tok(dict(name=c['tool'],arguments=c['arguments'])) if k=='request' else tok(c['result']) for c in calls]) for k in ('request','response')}
    result['tokens'][label]['fiveFullInventories'] = [sum(tok(dict(name=c['tool'],arguments=c['arguments']))+tok(c['result']) for c in calls if c['phase']=='rep'+str(i)) for i in range(1,6)]
result['allCallbacks'] = {k:stats([c[k] for c in facts['callbacks']]) for k in ('queueMs','nativeMs')}
result['callCounts'] = {k:sum(c['tool']==k for c in facts['calls']) for k in ('get_status','list_documents','read_entities')}
result['toolErrors'] = [dict(arguments=c['arguments'],error=c['result']['error']) for c in facts['calls'] if not c['result'].get('ok')]
result['checks'] = dict(total=len(facts['checks']),passed=sum(c['passed'] for c in facts['checks']),distinct=len({c['name'] for c in facts['checks']}))
result['passed'] = facts.get('passed'); result['error'] = facts.get('error'); result['cleanupError'] = facts.get('cleanupError')
result['skillTextTokens'] = {name:len(enc.encode((OUT.parents[1]/'skills/glyphs'/name).read_text())) for name in ('SKILL.md','references/glyph-discovery.md')}
result['runtime'] = facts['runtime']
(OUT/'analysis.json').write_text(json.dumps(result,indent=2))
call_log = ''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in facts['calls']).encode()
(OUT/'calls.jsonl.gz').write_bytes(gzip.compress(call_log,mtime=0))
print(json.dumps({k:v for k,v in result.items() if k not in ('runtime','toolErrors')},indent=2))
