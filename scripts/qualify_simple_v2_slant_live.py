"""Phased seven-tool slant acceptance, with time for a native visual check."""

import asyncio
import json
from pathlib import Path
import sys
import time
import tempfile

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
    output=ROOT/'build/slant-live-acceptance.json'
    evidence=json.loads(output.read_text()) if output.exists() and action!='apply' else {}
    def record():output.write_text(json.dumps(evidence,indent=2)+'\n')
    bridge=BridgeClient('http://127.0.0.1:9681',load_or_create_token(),timeout=10)
    async with Client('http://127.0.0.1:9680/mcp/') as client:
        assert tuple(t.name for t in await client.list_tools())==TOOL_NAMES
        async def tool(name,**kw):
            result=await client.call_tool(name,kw);body=result.structured_content or json.loads(result.content[0].text)
            assert body['ok'],body
            return body['data']
        async def poll(job_id,terminal):
            samples=[];started=time.monotonic();ended=None
            while True:
                before=time.monotonic();await asyncio.to_thread(bridge.status);samples.append(time.monotonic()-before)
                state=await tool('get_job',job_id=job_id);now=time.monotonic()
                if state['status'] in terminal and ended is None:ended=now
                if ended is not None and len(samples)>=10 and now-ended>=2:break
                if now-started>180:raise TimeoutError('slant phase timed out')
                await asyncio.sleep(.05)
            return state,dict(_measurement(samples),durationSeconds=now-started,postOperationSeconds=2)
        docs=await tool('list_documents');assert len(docs)==1 and docs[0]['path']==str(source),docs
        doc=docs[0]
        async def values():
            selectors=[dict(kind='layer',glyph=c['glyph'],id=c['layer']) for c in evidence['targets']]
            result=[]
            for offset in range(0,len(selectors),50):
                result+=await tool('read_entities',document_id=doc['id'],entities=selectors[offset:offset+50],fields=['outlineHash','width'])
            return [r['values'] for r in result]
        if action=='apply':
            assert not doc['dirty'],doc
            preflight=json.loads((ROOT/'build/slant-dactylotype-preflight.json').read_text())
            baseline,baseline_hash=snapshot_source(source,Path(tempfile.mkdtemp(prefix='glyphs-slant-baseline-')))
            evidence.update(source=str(source),sourceHash=baseline_hash,baselineCopy=str(baseline),originalHash=config['originalHash'])
            record()
            job=await tool('start_job',document_id=doc['id'],kind='slant',glyphs=preflight['glyphs'],options={'angle':12,'preserveStraightStems':True})
            job,measurement=await poll(job['id'],{'ready','failed','cancelled'})
            evidence.update(jobId=job['id'],prepared=job,prepare=measurement);record()
            assert job['status']=='ready' and job['changeCount']==preflight['changes'],job
            _assert_responsive(measurement)
            report=json.loads(Path(job['report']['path']).read_text())
            evidence['targets']=report['layers'];evidence['before']=await values()
            evidence['correctedPairs']=sum(r.get('correction',{}).get('compensatedPairCount',0) for r in report['layers'])
            assert evidence['correctedPairs']>=1
            assert [v['outlineHash'] for v in evidence['before']]==[r['beforeHash'] for r in report['layers']]
            record();await tool('apply_job',job_id=job['id'])
            job,measurement=await poll(job['id'],{'applied','failed','cancelled'})
            evidence.update(applied=job,apply=measurement);record();assert job['status']=='applied',job
            after=await values()
            assert [v['outlineHash'] for v in after]==[r['afterHash'] for r in report['layers']]
            assert [v['width'] for v in after]==[v['width'] for v in evidence['before']]
            evidence.update(exactApply=True,widthsPreserved=True,targetLayers=len(after));record();_assert_responsive(measurement)
        elif action=='discard':
            await tool('discard_job',job_id=evidence['jobId'])
            job,measurement=await poll(evidence['jobId'],{'discarded','failed','cancelled'})
            evidence.update(discarded=job,discard=measurement);record();assert job['status']=='discarded',job
            assert await values()==evidence['before']
            assert source_hash(source)==evidence['sourceHash']
            evidence.update(exactDiscard=True,sourceUnchangedDuringGate=True);record();_assert_responsive(measurement)
        elif action=='finish':
            assert not doc['dirty'] and evidence['exactApply'] and evidence['exactDiscard'],doc
            baseline=Path(evidence['baselineCopy']);assert source_hash(baseline)==evidence['sourceHash']
            files={p.relative_to(baseline) for p in baseline.rglob('*') if p.is_file()}
            assert files=={p.relative_to(source) for p in source.rglob('*') if p.is_file()}
            differences=[str(p) for p in sorted(files) if (baseline/p).read_bytes()!=(source/p).read_bytes()]
            assert not set(differences)-{'UIState.plist'},differences
            evidence.update(passed=True,originalUnchanged=True,savedDesignBytesRestored=True,uiStateDifferences=differences);record()
            config['sourceHash']=source_hash(source)
            if 'straight-stem correction' not in config['completed']:config['completed'].append('straight-stem correction')
            (ROOT/'build/lean-benefits-current.json').write_text(json.dumps(config,indent=2)+'\n')
        else:raise ValueError(action)
        print(json.dumps({'phase':action,'passed':True,**{k:evidence[k] for k in ('targetLayers','correctedPairs','prepare','apply','discard') if k in evidence}}))


if __name__=='__main__':asyncio.run(run(sys.argv[1]))
