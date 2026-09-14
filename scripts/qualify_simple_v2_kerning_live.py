"""MCP kerning gate on an isolated Dactylotype copy, with response sampling."""

import asyncio
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'build/simple-v2/sidecar'),str(ROOT/'scripts')]
from fastmcp import Client
from glyphs_mcp_protocol import TOOL_NAMES,load_or_create_token
from glyphs_mcp_sidecar.bridge_client import BridgeClient
from glyphs_mcp_sidecar.source import source_hash
from qualify_simple_v2_live import _measurement,_assert_responsive

PAIRS=[['A','V'],['V','A'],['A','W'],['W','A'],['T','o'],['T','a'],['Y','o'],['Y','a'],
       ['V','o'],['W','o'],['L','T'],['L','Y'],['r','period'],['f','parenright']]


async def run():
    config=json.loads((ROOT/'build/lean-benefits-current.json').read_text())
    source=Path(config['source']);original=Path(config['original'])
    assert source.is_relative_to('/private/tmp') and source_hash(original)==config['originalHash']
    evidence={'source':str(source),'sourceHash':source_hash(source),'originalHash':config['originalHash']}
    output=ROOT/'build/kerning-live-acceptance.json'
    def record():output.write_text(json.dumps(evidence,indent=2)+'\n')
    bridge=BridgeClient('http://127.0.0.1:9681',load_or_create_token(),timeout=10)
    async with Client('http://127.0.0.1:9680/mcp/') as client:
        assert tuple(t.name for t in await client.list_tools())==TOOL_NAMES
        async def tool(name,**kw):
            r=await client.call_tool(name,kw);body=r.structured_content or json.loads(r.content[0].text)
            assert body['ok'],body
            return body['data']
        async def poll(job_id,terminal):
            samples=[];start=time.monotonic();ended=None
            while True:
                before=time.monotonic();await asyncio.to_thread(bridge.status);samples.append(time.monotonic()-before)
                job=await tool('get_job',job_id=job_id);now=time.monotonic()
                if job['status'] in terminal and ended is None:ended=now
                if ended is not None and len(samples)>=10 and now-ended>=2:break
                if now-start>180:raise TimeoutError('kerning gate timed out')
                await asyncio.sleep(.05)
            return job,dict(_measurement(samples),durationSeconds=now-start,postOperationSeconds=2)
        docs=await tool('list_documents')
        assert len(docs)==1 and Path(docs[0]['path']).resolve()==source.resolve() and not docs[0]['dirty'],docs
        doc=docs[0]
        job=await tool('start_job',document_id=doc['id'],kind='kerning_collision',options={'pairs':PAIRS,'targetGap':5.125})
        job,measurement=await poll(job['id'],{'ready','failed','cancelled'})
        evidence.update(jobId=job['id'],prepare=measurement,prepared=job);record()
        assert job['status']=='ready' and job['changeCount']>0 and not job['report']['unavailableCount'],job
        _assert_responsive(measurement)
        report=json.loads(Path(job['report']['path']).read_text())
        rows=report['pairs']
        entities=[{k:r[k] for k in ('master','direction','left','right')}|{'kind':'kerning'} for r in rows]
        async def read():
            values=[]
            for i in range(0,len(entities),50):values+=await tool('read_entities',document_id=doc['id'],entities=entities[i:i+50],fields=['value'])
            return [v['values']['value'] for v in values]
        baseline=await read()
        assert baseline==[r['storedBefore'] for r in rows]
        applied=False
        try:
            await tool('apply_job',job_id=job['id'])
            state,measurement=await poll(job['id'],{'applied','failed','cancelled'});applied=state['status']=='applied'
            evidence.update(apply=measurement,applied=state);record();assert applied,state
            actual=await read()
            assert actual==[r['after'] if r['status']=='suggested' else r['storedBefore'] for r in rows]
            assert all(abs(r['measurement']['minGap']+v-r['effectiveBefore']-5.125)<1e-8 for r,v in zip(rows,actual) if r['status']=='suggested')
            evidence.update(exactApply=True,pairs=len(rows),correctedPairs=job['changeCount'],unchangedPairs=sum(r['status']=='unchanged' for r in rows));record()
            _assert_responsive(measurement)
        finally:
            if applied:
                await tool('discard_job',job_id=job['id'])
                state,measurement=await poll(job['id'],{'discarded','failed','cancelled'})
                evidence.update(discard=measurement,discarded=state);record()
                assert state['status']=='discarded' and await read()==baseline,state
                evidence['exactRestoration']=True;record();_assert_responsive(measurement)
        assert source_hash(source)==evidence['sourceHash'] and source_hash(original)==config['originalHash']
        evidence.update(passed=True,sourceUnchanged=True,originalUnchanged=True);record()
        print(json.dumps({k:evidence[k] for k in ('passed','pairs','correctedPairs','unchangedPairs','prepare','apply','discard')}))


if __name__=='__main__':asyncio.run(run())
