"""Actual seven-tool MCP spacing/apply/discard gate on one disposable document."""

import asyncio
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'build/simple-v2/sidecar'), str(ROOT/'scripts')]
from fastmcp import Client
from glyphs_mcp_protocol import load_or_create_token
from glyphs_mcp_sidecar.bridge_client import BridgeClient
from glyphs_mcp_sidecar.source import source_hash
from qualify_simple_v2_live import _measurement, _assert_responsive

NAMES = ['H','V','W','Y','x','n','o','zero','one','two','three','four','five','six',
         'seven','eight','nine','zero.tf','one.tf','seven.tf','acutecomb']


async def run():
    config = json.loads((ROOT/'build/lean-benefits-current.json').read_text())
    source, original = Path(config['source']), Path(config['original'])
    assert source.is_relative_to(Path('/private/tmp'))
    assert source_hash(original) == config['originalHash']
    bridge = BridgeClient('http://127.0.0.1:9681', load_or_create_token(), timeout=10)
    evidence = {'source':str(source),'sourceHash':source_hash(source),'originalHash':config['originalHash']}
    output = ROOT/'build/spacing-live-acceptance.json'

    def record(): output.write_text(json.dumps(evidence,indent=2)+'\n')

    async with Client('http://127.0.0.1:9680/mcp/') as client:
        catalog = await client.list_tools()
        assert [item.name for item in catalog] == ['get_status','list_documents','read_entities','start_job','get_job','apply_job','discard_job']

        async def tool(name, **arguments):
            result = await client.call_tool(name, arguments)
            body = result.structured_content or json.loads(result.content[0].text)
            if not body['ok']:
                raise RuntimeError(body.get('error'))
            return body['data']

        async def poll(job_id, terminal):
            samples=[]; started=time.monotonic(); ended=None
            while True:
                before=time.monotonic()
                await asyncio.to_thread(bridge.status)
                samples.append(time.monotonic()-before)
                job=await tool('get_job',job_id=job_id)
                now=time.monotonic()
                if job['status'] in terminal and ended is None: ended=now
                if ended is not None and len(samples)>=10 and now-ended>=2: break
                if now-started>180: raise TimeoutError('spacing phase exceeded 180 seconds')
                await asyncio.sleep(0.05)
            return job,dict(_measurement(samples),durationSeconds=time.monotonic()-started,postOperationSeconds=2)

        documents=await tool('list_documents')
        assert len(documents)==1 and Path(documents[0]['path']).resolve()==source.resolve(),documents
        document=documents[0]
        assert document['dirty'] is False,document
        job=await tool('start_job',document_id=document['id'],kind='spacing',glyphs=NAMES,options={'area':400.125})
        job,measurement=await poll(job['id'],{'ready','failed','cancelled'})
        evidence.update(jobId=job['id'],prepare=measurement,prepared=job);record()
        assert job['status']=='ready',job
        _assert_responsive(measurement)
        report_path=Path(job['report']['path'])
        report=json.loads(report_path.read_text())
        patch=json.loads(report_path.with_name('patch.json').read_text())
        assert job['changeCount']>0
        assert not job['report']['unavailableCount'],report
        entities=[{'kind':'layer','glyph':r['glyph'],'id':r['layer']} for r in report['layers']]

        async def read():
            values=[]
            for i in range(0,len(entities),50):
                values += await tool('read_entities',document_id=document['id'],entities=entities[i:i+50],fields=['width','outlineHash'])
            return {(v['entity']['glyph'],v['entity']['id']):v['values'] for v in values}

        baseline=await read()
        expected={key:dict(v) for key,v in baseline.items()}
        for change in patch['changes']:
            key=(change['glyph'],change['layer'])
            if change['kind']=='translate':
                assert baseline[key]['outlineHash']==change['beforeHash'],change
                expected[key]['outlineHash']=change['afterHash']
            else:
                assert abs(baseline[key]['width']-change['before'])<1e-5,change
                expected[key]['width']=baseline[key]['width']+(change['after']-change['before'])
        evidence['targetLayers']=len(baseline);record()
        applied=False
        try:
            await tool('apply_job',job_id=job['id'])
            current,measurement=await poll(job['id'],{'applied','failed','cancelled'})
            applied=current['status']=='applied'
            evidence.update(apply=measurement,applied=current);record()
            assert applied,current
            actual=await read()
            assert all(actual[k]['outlineHash']==v['outlineHash'] and abs(actual[k]['width']-v['width'])<1e-8 for k,v in expected.items())
            preserved=[r for r in report['layers'] if r['status']=='preserved' or r.get('preservedWidthReason')]
            assert all(actual[(r['glyph'],r['layer'])]['width']==baseline[(r['glyph'],r['layer'])]['width'] for r in preserved)
            evidence['exactApply']=True;evidence['preservedWidthLayers']=len(preserved);record()
            _assert_responsive(measurement)
        finally:
            if applied:
                await tool('discard_job',job_id=job['id'])
                current,measurement=await poll(job['id'],{'discarded','failed','cancelled'})
                evidence.update(discard=measurement,discarded=current);record()
                assert current['status']=='discarded',current
                assert await read()==baseline
                evidence['exactRestoration']=True;record()
                _assert_responsive(measurement)
        assert source_hash(source)==evidence['sourceHash']
        assert source_hash(original)==config['originalHash']
        evidence.update(originalUnchanged=True,sourceUnchanged=True,passed=True);record()
        print(json.dumps({k:evidence[k] for k in ('passed','targetLayers','preservedWidthLayers','prepare','apply','discard')}))


if __name__=='__main__': asyncio.run(run())
