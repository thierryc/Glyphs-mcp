"""Phased MCP/editor gate, allowing real native Undo/Redo between checks."""

import asyncio
import json
from pathlib import Path
import sys
import time
import tempfile
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'build/simple-v2/sidecar'),str(ROOT/'scripts')]
from fastmcp import Client
from glyphs_mcp_protocol import TOOL_NAMES,load_or_create_token
from glyphs_mcp_sidecar.bridge_client import BridgeClient
from glyphs_mcp_sidecar.source import source_hash,snapshot_source
from qualify_simple_v2_live import _measurement,_assert_responsive


async def run(action):
    config=json.loads((ROOT/'build/lean-benefits-current.json').read_text())
    source=Path(config['source']);assert source.is_relative_to('/private/tmp')
    assert source_hash(Path(config['original']))==config['originalHash']
    output=ROOT/'build/start-node-live-acceptance.json'
    evidence=json.loads(output.read_text()) if output.exists() and action!='seed' else {}
    def record():output.write_text(json.dumps(evidence,indent=2)+'\n')
    bridge=BridgeClient('http://127.0.0.1:9681',load_or_create_token(),timeout=10)
    async with Client('http://127.0.0.1:9680/mcp/') as client:
        assert tuple(t.name for t in await client.list_tools())==TOOL_NAMES
        async def tool(name,**kw):
            result=await client.call_tool(name,kw);body=result.structured_content or json.loads(result.content[0].text)
            assert body['ok'],body
            return body['data']
        async def poll(callback,terminal):
            samples=[];started=time.monotonic();ended=None
            while True:
                before=time.monotonic();await asyncio.to_thread(bridge.status);samples.append(time.monotonic()-before)
                state=await callback();now=time.monotonic()
                if state['status'] in terminal and ended is None:ended=now
                if ended is not None and len(samples)>=10 and now-ended>=2:break
                if now-started>180:raise TimeoutError('start-node phase timed out')
                await asyncio.sleep(.05)
            measurement=dict(_measurement(samples),durationSeconds=now-started,postOperationSeconds=2)
            return state,measurement
        docs=await tool('list_documents');assert len(docs)==1 and docs[0]['path']==str(source),docs
        doc=docs[0]
        async def values(changes):
            selectors=[dict(kind='layer',glyph=c['glyph'],id=c['layer']) for c in changes]
            result=await tool('read_entities',document_id=doc['id'],entities=selectors,fields=['outlineHash','width'])
            return [r['values'] for r in result]
        if action=='seed':
            plan=json.loads((ROOT/'build/start-node-fixture-plan.json').read_text())
            assert not doc['dirty'] and source_hash(source)==plan['sourceHash']
            patch=dict(version=1,jobId='start-fixture-'+uuid4().hex,documentId=doc['id'],sourcePath=str(source),
                sourceHash=plan['sourceHash'],generation=doc['generation'],changes=plan['changes'],summary='Disposable cyclic phase fixture')
            evidence.update(source=str(source),originalHash=config['originalHash'],sourceHashBeforeFixture=plan['sourceHash'],fixture=patch,
                originalValues=await values(patch['changes']))
            baseline,_=snapshot_source(source,Path(tempfile.mkdtemp(prefix='glyphs-start-node-baseline-')))
            evidence['baselineCopy']=str(baseline)
            record();await asyncio.to_thread(bridge.apply,patch)
            state,measurement=await poll(lambda:asyncio.to_thread(bridge.operation,patch['jobId']),{'applied','failed','cancelled'})
            evidence.update(seed=measurement,seedState=state);record();assert state['status']=='applied',state
            evidence['fixtureValues']=await values(patch['changes']);record()
            assert [v['outlineHash'] for v in evidence['fixtureValues']]==[c['afterHash'] for c in patch['changes']]
            _assert_responsive(measurement)
        elif action=='apply':
            assert not doc['dirty'],doc
            job=await tool('start_job',document_id=doc['id'],kind='start_nodes',glyphs=['o'])
            job,measurement=await poll(lambda:tool('get_job',job_id=job['id']),{'ready','failed','cancelled'})
            evidence.update(jobId=job['id'],prepared=job,prepare=measurement,sourceHashAtApply=source_hash(source));record()
            assert job['status']=='ready' and job['changeCount']==8,job
            _assert_responsive(measurement)
            await tool('apply_job',job_id=job['id'])
            state,measurement=await poll(lambda:tool('get_job',job_id=job['id']),{'applied','failed','cancelled'})
            evidence.update(apply=measurement,applied=state);record();assert state['status']=='applied',state
            assert await values(evidence['fixture']['changes'])==evidence['originalValues']
            evidence['exactApply']=True;record();_assert_responsive(measurement)
        elif action in ('verify-undo','verify-redo'):
            expected=evidence['fixtureValues' if action=='verify-undo' else 'originalValues']
            actual=await values(evidence['fixture']['changes'])
            assert actual==expected,{'action':action,'actual':actual,'expected':expected}
            evidence['nativeUndo' if action=='verify-undo' else 'nativeRedo']=True;record()
        elif action=='noop':
            assert not doc['dirty'],doc
            job=await tool('start_job',document_id=doc['id'],kind='start_nodes',glyphs=['o'])
            job,measurement=await poll(lambda:tool('get_job',job_id=job['id']),{'ready','failed','cancelled'})
            evidence.update(noop=measurement,noopJob=job);record()
            assert job['status']=='ready' and job['changeCount']==0,job
            await tool('discard_job',job_id=job['id']);evidence['secondApplicationNoop']=True;record();_assert_responsive(measurement)
        elif action in ('discard','restore-fixture'):
            if action=='discard':
                await tool('discard_job',job_id=evidence['jobId'])
                callback=lambda:tool('get_job',job_id=evidence['jobId'])
            else:
                await asyncio.to_thread(bridge.discard,evidence['fixture']['jobId'])
                callback=lambda:asyncio.to_thread(bridge.operation,evidence['fixture']['jobId'])
            state,measurement=await poll(callback,{'discarded','failed','cancelled'})
            evidence[action]=measurement;record();assert state['status']=='discarded',state
            expected=evidence['fixtureValues' if action=='discard' else 'originalValues']
            assert await values(evidence['fixture']['changes'])==expected
            evidence['exactDiscard' if action=='discard' else 'fixtureRestored']=True;record();_assert_responsive(measurement)
        elif action=='finish':
            assert not doc['dirty'] and all(evidence.get(k) for k in ('exactApply','nativeUndo','nativeRedo','secondApplicationNoop','exactDiscard','fixtureRestored'))
            baseline=Path(evidence['baselineCopy'])
            assert source_hash(baseline)==evidence['sourceHashBeforeFixture']
            files={p.relative_to(baseline) for p in baseline.rglob('*') if p.is_file()}
            assert files=={p.relative_to(source) for p in source.rglob('*') if p.is_file()}
            differences=[str(p) for p in sorted(files) if (baseline/p).read_bytes()!=(source/p).read_bytes()]
            assert not set(differences)-{'UIState.plist'},differences
            evidence.update(passed=True,originalUnchanged=True,savedDesignBytesRestored=True,
                            savedBytesRestored=not differences,uiStateDifferences=differences);record()
        print(json.dumps({'phase':action,'passed':True}))


if __name__=='__main__':asyncio.run(run(sys.argv[1]))
