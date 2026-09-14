"""Public live reads plus a separately labelled instrumented sidecar process."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import math
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parents[2]/'reports/v1-v2/04-master-identification'
EXPECTED = json.loads((BASE/'expected.json').read_text())['scopes']


def now(): return datetime.now(timezone.utc).isoformat()
def stats(values):
    values = sorted(values)
    return {'n':len(values), 'medianMs':statistics.median(values), 'minMs':min(values),
            'maxMs':max(values), 'p95Ms':values[math.ceil(.95*len(values))-1]}


async def measure(args):
    from fastmcp import Client
    out = Path(args.output); out.mkdir(parents=True, exist_ok=False)
    facts = {'at':now(), 'mode':args.mode, 'endpoint':args.endpoint, 'loadBefore':os.getloadavg(),
             'logicalCPUs':os.cpu_count(), 'trials':[], 'checks':[], 'errors':[]}
    def record(row):
        with (out/'calls.jsonl').open('a') as f: f.write(json.dumps(row)+'\n')
    def check(name, condition, observed=None):
        facts['checks'].append({'name':name, 'passed':bool(condition), 'observed':observed})
        assert condition, (name,observed)
    async def call(client,name,arguments,phase):
        at=now(); start=time.perf_counter()
        result=await client.call_tool_mcp(name,arguments)
        ms=(time.perf_counter()-start)*1000
        raw=result.model_dump(mode='json'); body=json.loads(result.content[0].text)
        record({'at':at,'method':name,'arguments':arguments,'phase':phase,'ms':ms,'body':body,'raw':raw})
        return body,ms
    async def docs(client,phase):
        value,ms=await call(client,'list_documents',{},phase);check(phase+' list success',value['ok'])
        return value['data'],ms
    async def target(client,filename,phase):
        rows,ms=await docs(client,phase)
        matches=[row for row in rows if row.get('path')==str(Path(args.copies)/(filename+'.glyphs'))]
        check('unique exact path '+filename,len(matches)==1)
        return matches[0],ms
    async def page(client,doc,phase,selector=None):
        value,ms=await call(client,'read_entities',{'document_id':doc,'entities':[selector or {'kind':'masters','limit':100}], 'fields':['id','name']},phase)
        check(phase+' page success',value['ok'],value if not value['ok'] else None)
        return value['data'][0]['values'],ms
    async def inventory(client,doc,phase):
        rows=[];times=[];cursor=None
        for _ in range(10):
            selector={'kind':'masters','limit':100}
            if cursor:selector['cursor']=cursor
            value,ms=await page(client,doc,phase,selector);times.append(ms);rows+=value['items']
            if value['complete']:
                check('complete count',len(rows)==value['total'])
                return rows,times
            check('incomplete has continuation',value['nextCursor'] is not None)
            cursor=value['nextCursor']
        raise AssertionError('Unexpected unbounded pagination')
    try:
        async with Client(args.endpoint,timeout=30) as client:
            facts['handshake']=client.initialize_result.model_dump(mode='json')
            catalog=await client.list_tools();facts['catalog']=[t.model_dump(mode='json') for t in catalog]
            check('seven tools',len(catalog)==7)
            status,_=await call(client,'get_status',{},'identity');check('reachable',status['ok'])
            facts['identity']=status['data']
            manifest=json.loads(Path(args.manifest).read_text())
            check('sidecar fingerprint',status['data']['codeHash']==manifest['sidecar']['codeHash'])
            check('bridge fingerprint',status['data']['bridge']['codeHash']==manifest['bridge']['codeHash'])
            check('Glyphs 4 native host',status['data']['bridge']['host']=={'identifier':'com.GeorgSeifert.Glyphs4','version':'4.1','build':'4107'})
            if args.mode=='diagnostic':
                doc,_=await target(client,'core-06-trial-5','target')
                query={'document_id':doc['id'],'entities':[{'kind':'master','id':m['id']} for m in EXPECTED['core']['masters']], 'fields':['id','name']}
                for label,name,params in [('status','get_status',{}),('known-ids','read_entities',query)]:
                    values=[]
                    for index in range(21):
                        value,ms=await call(client,name,params,label+'-warmup' if index==0 else label)
                        check(label+' success',value['ok'])
                        if index:values.append(ms)
                        await asyncio.sleep(.05)
                    facts[label]=stats(values)
            elif args.mode=='benchmark':
                check('enumeration advertised','masters.list.v1' in status['data']['bridge'].get('readCapabilities',[]))
                for phase,suffix in [('first','00-first'),('warmup','01-warmup')]+[(f'trial-{i}',f'0{i+1}-trial-{i}') for i in range(1,6)]:
                    for scope in ('core','batch'):
                        identity,_=await call(client,'get_status',{},phase+'-'+scope+'-identity')
                        check('per trial identity',identity['data']['codeHash']==manifest['sidecar']['codeHash'] and identity['data']['bridge']['codeHash']==manifest['bridge']['codeHash'])
                        begin=time.perf_counter();doc,resolve_ms=await target(client,scope+'-'+suffix,phase+'-'+scope+'-target')
                        rows,times=await inventory(client,doc['id'],phase+'-'+scope+'-read')
                        verify=time.perf_counter();check(phase+' '+scope+' exact mapping',rows==EXPECTED[scope]['masters'])
                        facts['trials'].append({'phase':phase,'scope':scope,'rows':rows,'correctFields':len(rows)*2,
                            'resolveMs':resolve_ms,'readMs':sum(times),'readCalls':len(times),'sourceCalls':0,
                            'verificationMs':(time.perf_counter()-verify)*1000,'completionMs':(time.perf_counter()-begin)*1000})
                facts['timing']={scope:{metric:stats([t[metric] for t in facts['trials'] if t['scope']==scope and t['phase'].startswith('trial-')]) for metric in ('completionMs','readMs','resolveMs','verificationMs')} for scope in ('core','batch')}
            elif args.mode=='controls':
                doc,_=await target(client,'core-07-dirty','dirty-target')
                check('native dirty flag',doc['dirty'] is True,doc)
                changed=[dict(m) for m in EXPECTED['core']['masters']];changed[0]['name']='Regular'
                rows,_=await inventory(client,doc['id'],'dirty-inventory');check('dirty duplicate names',rows==changed,rows)
                queries=[('omitted',[{'kind':'master'}],['id'],'invalid_request'),('empty-id',[{'kind':'master','id':''}],['id'],'invalid_request'),
                    ('duplicate-alias',[{'kind':'master','id':'Regular'}],['id'],'target_not_found'),
                    ('mixed-missing',[{'kind':'master','id':rows[0]['id']},{'kind':'master','id':'missing'}],['id'],'target_not_found'),
                    ('mixed-page',[{'kind':'masters'},{'kind':'master','id':rows[0]['id']}],['id'],'invalid_request'),
                    ('limit101',[{'kind':'masters','limit':101}],['id'],'invalid_request'),
                    ('limit0',[{'kind':'masters','limit':0}],['id'],'invalid_request'),
                    ('unsupported',[{'kind':'masters'}],['axes'],'unsupported_read'),
                    ('empty-selectors',[],['id'],'invalid_request'),
                    ('101-selectors',[{'kind':'master','id':rows[0]['id']}]*101,['id'],'invalid_request')]
                for label,entities,fields,code in queries:
                    value,_=await call(client,'read_entities',{'document_id':doc['id'],'entities':entities,'fields':fields},label)
                    check(label,not value['ok'] and value['error']['code']==code,value)
                exact,_=await call(client,'read_entities',{'document_id':doc['id'],'entities':[{'kind':'master','id':m['id']} for m in reversed(rows)],'fields':['id','name']},'exact-duplicate')
                check('exact IDs disambiguate',exact['ok'] and [v['values'] for v in exact['data']]==list(reversed(rows)))
                all_docs,_=await docs(client,'unsaved-target');unsaved=[d for d in all_docs if d.get('path') is None and d['familyName']=='R04 Unsaved Qualification']
                check('unique unsaved font',len(unsaved)==1,unsaved)
                rows,_=await inventory(client,unsaved[0]['id'],'unsaved-inventory')
                check('unsaved opaque IDs and duplicate names',rows==[{'id':f'opaque-native-{i}','name':'Regular'} for i in range(3)],rows)
                batch,_=await target(client,'batch-00-first','batch-target');first,_=await page(client,batch['id'],'first-page')
                cursor=first['nextCursor'];cursor['total']+=1
                value,_=await call(client,'read_entities',{'document_id':batch['id'],'entities':[{'kind':'masters','cursor':cursor}],'fields':['id','name']},'stale-cursor')
                check('stale cursor rejected',not value['ok'] and value['error']['code']=='stale_master_cursor')
                control,_=await target(client,'core-00-first','unrelated-target');rows,_=await inventory(client,control['id'],'unrelated-inventory')
                check('unrelated font unchanged',rows==EXPECTED['core']['masters'])
            elif args.mode=='probe':
                doc,_=await target(client,'core-07-dirty','probe-target');samples=[];changed=None;start=time.monotonic()
                (out/'ready').write_text(now());print('READY',flush=True)
                while time.monotonic()-start<70:
                    rows,times=await inventory(client,doc['id'],'edit-probe');tick=time.monotonic()
                    samples.append({'at':now(),'ms':sum(times),'rows':rows})
                    if rows[0]['name']=='Regular' and changed is None:changed=tick
                    if changed and tick-changed>=2:break
                    await asyncio.sleep(.05)
                check('observed native edit',changed is not None)
                facts['samples']=samples;facts['postSeconds']=time.monotonic()-changed
                facts['postTiming']=stats([s['ms'] for s in samples if s['rows'][0]['name']=='Regular'])
            facts['finalDocuments'],_=await docs(client,'final-documents')
    except Exception as exc:
        facts['errors'].append(repr(exc))
        raise
    finally:
        facts['loadAfter']=os.getloadavg();facts['finishedAt']=now()
        (out/'facts.json').write_text(json.dumps(facts,indent=2)+'\n')
        print(json.dumps({k:v for k,v in facts.items() if k in ('timing','errors','status','known-ids','postTiming')},indent=2))


def serve(args):
    # Same installed sidecar implementation on a separate qualification endpoint.
    # Authentication is loaded locally, never put into the report/config/log.
    import qualify_discovery_identity as q
    install=Path.home()/'Library/Application Support/Glyphs MCP/lean-v2'
    sys.path.insert(0,str(install/'sidecar'))
    from glyphs_mcp_protocol import load_or_create_token
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    cfg={'sidecar':str(install/'sidecar'),'bridgePort':9681,'token':load_or_create_token(),
         'jobs':str(output/'jobs'),'glyphsCLI':str(install/'runtime/bin/glyphs'),'application':'/Applications/Glyphs 4.app',
         'port':args.port,'instrument':args.instrument,'sidecarTimings':str(output/'status-timings.json'),
         'sidecarReadTimings':str(output/'read-timings.json')}
    q.config=lambda:cfg
    (output/'pid').write_text(str(os.getpid()))
    q.sidecar_process()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['serve','benchmark','diagnostic','controls','probe'])
    parser.add_argument('--output',required=True);parser.add_argument('--copies');parser.add_argument('--manifest')
    parser.add_argument('--endpoint',default='http://127.0.0.1:9680/mcp/');parser.add_argument('--port',type=int,default=9684);parser.add_argument('--instrument',action='store_true')
    args=parser.parse_args()
    if args.mode=='serve':serve(args)
    else:asyncio.run(measure(args))
