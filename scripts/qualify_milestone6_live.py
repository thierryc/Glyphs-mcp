"""Phased, actual nine-tool acceptance. Native UI actions occur between phases."""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'build/simple-v2/sidecar'), str(ROOT / 'scripts')]
from fastmcp import Client
from glyphs_mcp_protocol import load_or_create_token
from glyphs_mcp_sidecar.bridge_client import BridgeClient
from glyphs_mcp_sidecar.source import source_hash
from qualify_simple_v2_live import _measurement

OUT = ROOT / 'build/live-acceptance'
CONFIG = json.loads((OUT / 'config.json').read_text())

async def run(cycle, phase):
    path = OUT / f'cycle-{cycle}.json'
    evidence = json.loads(path.read_text()) if path.exists() else {'cycle': cycle, 'phases': {}}
    def record():
        path.write_text(json.dumps(evidence, indent=2) + '\n')
    bridge = BridgeClient('http://127.0.0.1:9681', load_or_create_token(), timeout=15)
    async with Client('http://127.0.0.1:9680/mcp/') as client:
        async def tool(name, **kw):
            res = await client.call_tool(name, kw)
            body = res.structured_content or json.loads(res.content[0].text)
            assert body['ok'], body
            return body['data']
        docs = await tool('list_documents')
        assert len(docs) == 1 and docs[0]['path'] == CONFIG['source'], docs
        doc = docs[0]
        assert source_hash(Path(CONFIG['original'])) == CONFIG['originalHash']
        evidence['documentId'] = doc['id']
        async def poll(job_id, terminals):
            samples, errors = [], []
            started = time.monotonic(); ended = None
            while True:
                before = time.monotonic()
                try: await asyncio.to_thread(bridge.status)
                except Exception as exc: errors.append(str(exc))
                samples.append(time.monotonic() - before)
                job = await tool('get_job', job_id=job_id)
                now = time.monotonic()
                if job['status'] in terminals and ended is None: ended = now
                if ended and now-ended >= 2 and len(samples) >= 10: break
                assert now-started < 240, job
                await asyncio.sleep(.025)
            timing = dict(_measurement(samples), errors=errors, postOperationSeconds=2,
                          durationSeconds=round(time.monotonic()-started, 3))
            assert not errors, timing
            return job, timing
        async def read():
            values = []
            entities = evidence['entities']
            for i in range(0,len(entities),100):
                values.extend(await tool('read_entities', document_id=doc['id'],
                    entities=entities[i:i+100], fields=['width','outlineHash']))
            return [v['values'] for v in values]
        def check(actual, expected):
            differences = [(evidence['entities'][i], a, b) for i,(a,b) in enumerate(zip(actual,expected)) if a != b]
            assert len(actual) == len(expected) and not differences, differences[:4]
        async def prepare(kind):
            assert doc['dirty'] is False, doc
            kw = {'delta':8.125} if kind=='width_delta' else {'options':{'area':400.125}}
            job = await tool('start_job', document_id=doc['id'], kind=kind, **kw)
            job, timing = await poll(job['id'], {'ready','failed','cancelled'})
            evidence['phases'][phase+'-prepare'] = timing
            assert job['status'] == 'ready', job
            if kind == 'spacing':
                report_path = Path(job['report']['path'])
                report = json.loads(report_path.read_text())
                assert job['report']['unavailableCount'] == 0, job
                evidence['jobRoot'] = str(report_path.parent.parent)
                evidence['entities'] = [{'kind':'layer','glyph':r['glyph'],'id':r['layer']} for r in report['layers']]
                evidence['baseline'] = await read()
                assert len(evidence['baseline']) == 3807
            patch = json.loads((Path(evidence['jobRoot'])/job['id']/'patch.json').read_text())
            known = {(e['glyph'],e['id']) for e in evidence['entities']}
            extras = []
            for c in patch['changes']:
                key = (c['glyph'],c['layer'])
                if key not in known:
                    extras.append({'kind':'layer','glyph':key[0],'id':key[1]})
                    known.add(key)
            if extras:
                old = evidence['baseline']
                evidence['entities'].extend(extras)
                evidence['baseline'] = await read()
                assert evidence['baseline'][:len(old)] == old
            baseline = evidence['baseline']
            expected = [dict(v) for v in baseline]
            lookup = {(e['glyph'],e['id']): i for i,e in enumerate(evidence['entities'])}
            for change in patch['changes']:
                i = lookup[(change['glyph'],change['layer'])]
                if change['kind'] == 'translate':
                    assert baseline[i]['outlineHash'] == change['beforeHash']
                    expected[i]['outlineHash'] = change['afterHash']
                else:
                    assert baseline[i]['width'] == change['before'], change
                    expected[i]['width'] = change['after']
            evidence.update(jobId=job['id'], expected=expected, changeCount=len(patch['changes']))
            record()
            return job
        if phase == 'baseline':
            samples=[]; started=time.monotonic()
            while time.monotonic()-started < 3:
                before=time.monotonic(); await asyncio.to_thread(bridge.status)
                samples.append(time.monotonic()-before); await asyncio.sleep(.025)
            evidence['phases'][phase] = dict(_measurement(samples),errors=[])
            assert [t.name for t in await client.list_tools()] == ['get_status','list_documents','read_entities','start_job','get_job','apply_job','accept_job','discard_job','save_document']
        elif phase in {'spacing','fractional'}:
            job = await prepare('spacing' if phase=='spacing' else 'width_delta')
            await tool('apply_job',job_id=job['id'])
            job,timing=await poll(job['id'],{'applied','failed','cancelled'})
            evidence['phases'][phase] = dict(timing,status=job['status'],changes=evidence['changeCount'])
            record(); assert job['status']=='applied',job
            check(await read(), evidence['expected'])
            evidence['phases'][phase]['exactApply'] = True
        elif phase in {'undo','redo','native-revert'}:
            expected=[dict(v) for v in evidence['expected']]
            if phase == 'undo':
                for i,e in enumerate(evidence['entities']):
                    if e['glyph'] == 'R': expected[i] = evidence['baseline'][i]
            if phase == 'native-revert': expected=evidence['baseline']
            check(await read(), expected)
            evidence['phases'][phase] = {'exact':True,'nativeGlyph':'R','masters':9}
        elif phase == 'discard':
            await tool('discard_job',job_id=evidence['jobId'])
            job,timing=await poll(evidence['jobId'],{'discarded','failed','cancelled'})
            assert job['status']=='discarded',job
            check(await read(),evidence['baseline'])
            evidence['phases'][phase+'-'+str(evidence['changeCount'])] = dict(timing,exactRestoration=True)
        elif phase == 'cancel-prepare':
            assert not doc['dirty'],doc
            job=await tool('start_job',document_id=doc['id'],kind='spacing',options={'area':400.125})
            await tool('discard_job',job_id=job['id'])
            job,timing=await poll(job['id'],{'cancelled','discarded','failed'})
            assert job['status'] in {'cancelled','discarded'},job
            check(await read(),evidence['baseline'])
            remaining=sorted(p.name for p in (Path(evidence['jobRoot'])/job['id']).iterdir())
            assert not any(n in remaining for n in ('patch.json','source.glyphspackage','report.json'))
            evidence['phases'][phase]=dict(timing,status=job['status'],remaining=remaining,exactRestoration=True)
        elif phase == 'cancel-apply':
            job=await prepare('width_delta')
            operation=await tool('apply_job',job_id=job['id'])
            before_cancel=await tool('get_job',job_id=job['id'])
            await tool('discard_job',job_id=job['id'])
            job,timing=await poll(job['id'],{'cancelled','discarded','failed'})
            assert job['status'] in {'cancelled','discarded'},job
            check(await read(),evidence['baseline'])
            evidence['phases'][phase]=dict(timing,status=job['status'],beforeCancel=before_cancel,exactRestoration=True)
        elif phase == 'prepare-control':
            job=await prepare('spacing')
            await tool('discard_job',job_id=job['id'])
            current=await tool('get_job',job_id=job['id'])
            assert current['status']=='discarded', current
            check(await read(),evidence['baseline'])
            evidence['phases'][phase]={'noUIInteraction':True,'readyThenDiscarded':True,'exactBaseline':True}
        elif phase == 'saved':
            assert not doc['dirty'],doc
            def files(folder):
                return {str(p.relative_to(folder)):p.read_bytes() for p in folder.rglob('*') if p.is_file() and p.name not in {'UIState.plist','.DS_Store'}}
            source=files(Path(CONFIG['source'])); control=files(Path(CONFIG['control']))
            differences=[k for k in sorted(set(source)|set(control)) if source.get(k)!=control.get(k)]
            assert not differences,differences[:10]
            evidence['phases'][phase]={'nativeSaveControlMatches':True,'designFiles':len(source),'originalUnchanged':True}
        else: raise ValueError(phase)
        record()
        print(json.dumps({'cycle':cycle,'phase':phase,'passed':True,'result':evidence['phases'].get(phase,{})}))

if __name__ == '__main__': asyncio.run(run(int(sys.argv[1]),sys.argv[2]))
