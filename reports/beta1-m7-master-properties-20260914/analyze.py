"""Reproduce M7 timings and estimated payload tokens; retain original failures."""
from pathlib import Path
import json,statistics,math,os,sys,gzip
sys.path.insert(0,'/private/tmp/glyphs-metadata-tokenizer-20260910')
os.environ.setdefault('TIKTOKEN_CACHE_DIR','/private/tmp/glyphs-metadata-tokenizer-cache')
import tiktoken
OUT=Path(__file__).resolve().parent;enc=tiktoken.get_encoding('o200k_base')
def load(name):
    p=OUT/name;return json.loads(p.read_bytes() if p.exists() else gzip.decompress(p.with_suffix(p.suffix+'.gz').read_bytes()))
facts=load('native-facts.json')
def stats(xs):
    xs=sorted(xs);return dict(n=len(xs),median=statistics.median(xs),minimum=xs[0],maximum=xs[-1],p95=xs[math.ceil(.95*len(xs))-1]) if xs else None
def tokens(value):return len(enc.encode(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)))
def cost(c):return tokens(dict(name=c['tool'],arguments=c['arguments']))+tokens(c['result'])
r=dict(tokenMethod='tiktoken '+tiktoken.__version__+' / o200k_base; compact sorted JSON, literal Unicode; {name,arguments} plus one parsed response body. Estimated tokens, not billed usage.',timings={},tokens={})
for label in ('small','bound','RobotoSlab'):
    reps=[t for t in facts['trials'] if t['label']==label and t['phase'].startswith('rep')]
    calls=[facts['calls'][i] for t in reps for i in t['callIndices']]
    r['timings'][label]={key:stats([t[key] for t in reps]) for key in ('discoveryMs','readMs','initialTotalMs')}
    r['timings'][label]['pageHTTP']=stats([c['httpMs'] for c in calls])
    r['timings'][label]['nativeCallbacks']={key:stats([cb[key] for c in calls for cb in c['callbacks'] if cb['reads']]) for key in ('nativeMs','queueMs')}
    r['timings'][label]['firstAndWarmup']=[t for t in facts['trials'] if t['label']==label and not t['phase'].startswith('rep')]
    r['tokens'][label]=stats([sum(cost(facts['calls'][i]) for i in t['callIndices']) for t in reps])
    sequences=[]
    for t in reps:
        indices=[t['callIndices'][0]-1,*t['callIndices'],t['callIndices'][-1]+1]
        sequence=[facts['calls'][i] for i in indices]
        assert sequence[0]['tool']=='list_documents' and sequence[-1]['phase']=='compact'
        sequences.append(dict(httpMs=sum(c['httpMs'] for c in sequence),tokens=sum(cost(c) for c in sequence),calls=len(sequence)))
    r['timings'][label]['discoveryFullCompact']={key:stats([s[key] for s in sequences]) for key in ('httpMs','tokens','calls')}
r['compact']={key:stats([c['httpMs'] if key=='httpMs' else cost(c) for c in facts['calls'] if c['phase']=='compact']) for key in ('httpMs','tokens')}
r['allCallbacks']={key:stats([c[key] for c in facts['callbacks']]) for key in ('nativeMs','queueMs')}
r['readCallbacks']={key:stats([c[key] for c in facts['callbacks'] if c['reads']]) for key in ('nativeMs','queueMs')}
r['twoSecondProbe']={key:stats([cb[key] for c in facts['calls'] if c['phase']=='two-second-probe' for cb in c['callbacks'] if cb['reads']]) for key in ('nativeMs','queueMs')}
r['discoveryTokens']=stats([cost(c) for c in facts['calls'] if c['tool']=='list_documents'])
r['callCounts']={tool:sum(c['tool']==tool for c in facts['calls']) for tool in ('get_status','list_documents','read_entities')}
r['expectedErrorCalls']=[dict(arguments=c['arguments'],error=c['result']['error']) for c in facts['calls'] if not c['result'].get('ok')]
r['checks']=dict(total=len(facts['checks']),passed=sum(c['passed'] for c in facts['checks']))
r.update({key:facts.get(key) for key in ('passed','error','cleanupError','startedAt','finishedAt','loadBefore','loadAfter')})
r['loads']=[t['load'] for t in facts['trials']];r['openDocumentCounts']=sorted({t['openDocuments'] for t in facts['trials']})
r['setupTimes']=stats([t['settleMs'] for t in facts['fixtureSetup'] if 'settleMs' in t]);r['nativeDirtyOpeningChanges']=[t for t in facts['fixtureSetup'] if t.get('dirtyBeforeReads')!=t.get('dirtyImmediately') and 'dirtyBeforeReads' in t]
r['skillTokens']={name:len(enc.encode((OUT.parents[1]/'skills/glyphs'/name).read_text())) for name in ('SKILL.md','references/master-reads.md')}
before=load('baseline-catalog.json')[1]['response']['result']['tools'];after=facts['catalog']['tools']
r['readToolDescriptionTokens']={key:len(enc.encode(next(t['description'] for t in tools if t['name']=='read_entities'))) for key,tools in [('before',before),('after',after)]}
(OUT/'analysis.json').write_text(json.dumps(r,indent=2))
(OUT/'calls.jsonl.gz').write_bytes(gzip.compress(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in facts['calls']).encode(),mtime=0))
print(json.dumps({k:v for k,v in r.items() if k not in ('expectedErrorCalls','loads','nativeDirtyOpeningChanges')},indent=2))
