"""Reproduce H6 measurements; estimates count one parsed body, not SSE duplication."""
from pathlib import Path
import json,statistics,math,os,sys,gzip
sys.path.insert(0,'/private/tmp/glyphs-metadata-tokenizer-20260910');os.environ.setdefault('TIKTOKEN_CACHE_DIR','/private/tmp/glyphs-metadata-tokenizer-cache')
import tiktoken
enc=tiktoken.get_encoding('o200k_base');OUT=Path(__file__).resolve().parent
p=OUT/'native-facts.json';facts=json.loads(p.read_text() if p.exists() else gzip.decompress(p.with_suffix('.json.gz').read_bytes()))
def stats(xs):
 xs=sorted(xs);return dict(n=len(xs),median=statistics.median(xs),minimum=xs[0],maximum=xs[-1],p95=xs[math.ceil(.95*len(xs))-1]) if xs else None
def tok(v):return len(enc.encode(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)))
def tokens(c):return tok(dict(name=c['tool'],arguments=c['arguments']))+tok(c['result'])
r=dict(tokenMethod='tiktoken '+tiktoken.__version__+' / o200k_base; sorted compact JSON, literal Unicode; {name,arguments} + one parsed response body; estimates, not billed usage',timings={},tokens={},loadBefore=facts['loadBefore'],loadAfter=facts.get('loadAfter'),startedAt=facts['startedAt'],finishedAt=facts.get('finishedAt'))
for label in ('small','many','RobotoSlab'):
 reps=[t for t in facts['trials'] if t['label']==label and t['phase'].startswith('rep')];calls=[facts['calls'][i] for t in reps for i in t['callIndices']]
 r['timings'][label]={k:stats([t[k] for t in reps]) for k in ('readMs','discoveryMs','initialTotalMs')}
 r['timings'][label]['firstAndWarmup']=[t for t in facts['trials'] if t['label']==label and not t['phase'].startswith('rep')]
 r['timings'][label]['pageHTTP']=stats([c['httpMs'] for c in calls]);r['timings'][label]['pageCallback']={k:stats([n[k] for c in calls for n in c['callbacks'] if n['countReads']]) for k in ('queueMs','nativeMs')}
 r['tokens'][label]=dict(pages=stats([tokens(c) for c in calls]),fullInventories=[sum(tokens(facts['calls'][i]) for i in t['callIndices']) for t in reps])
r['discoveryTokens']=stats([tokens(c) for c in facts['calls'] if c['tool']=='list_documents'])
r['groupReadTokens']=stats([tokens(c) for c in facts['calls'] if c['tool']=='read_entities' and c['arguments']['entities'][0]['kind']=='glyph' and c['result'].get('ok')])
r['allCallbacks']={k:stats([c[k] for c in facts['callbacks']]) for k in ('queueMs','nativeMs')}
r['callCounts']={k:sum(c['tool']==k for c in facts['calls']) for k in ('get_status','list_documents','read_entities')}
r['toolErrors']=[dict(arguments=c['arguments'],error=c['result']['error']) for c in facts['calls'] if not c['result'].get('ok')]
r['checks']=dict(total=len(facts['checks']),passed=sum(c['passed'] for c in facts['checks']));r['passed']=facts.get('passed');r['error']=facts.get('error');r['cleanupError']=facts.get('cleanupError');r['runtime']=facts['runtime'];r['timedOpenDocumentCounts']=sorted({t['openDocuments'] for t in facts['trials']})
r['skillTextTokens']={name:len(enc.encode((OUT.parents[1]/'skills/glyphs'/name).read_text())) for name in ('SKILL.md','references/kerning-discovery.md')}
(OUT/'analysis.json').write_text(json.dumps(r,indent=2));(OUT/'calls.jsonl.gz').write_bytes(gzip.compress(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in facts['calls']).encode(),mtime=0))
print(json.dumps({k:v for k,v in r.items() if k not in ('runtime','toolErrors')},indent=2))
