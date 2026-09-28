"""Authorized disposable-editor checks over the installed MCP transport.

Open the fixture using the native UI first. Never opens, closes or rewrites a
font file; all edits and saves use the established conversation/job services.
This local transport timing is separate from Codex connector latency.
"""
import argparse
import asyncio
import json
from pathlib import Path
import time

from fastmcp import Client

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
source = args.source.resolve()
assert source.parent == ROOT / 'build/beta8-milestone3/editor'
assert source.name == 'Cleanup.glyphspackage'
assert not args.output.exists(), 'Preserve evidence; reconcile the recorded workflow before retrying.'
evidence = dict(source=str(source), client='fresh local FastMCP connection', calls=[], checks=[])


def record():
    args.output.write_text(json.dumps(evidence, indent=2) + '\n')


async def main():
    async with Client('http://127.0.0.1:9680/mcp/') as client:
        async def tool(name, **kwargs):
            started = time.perf_counter()
            result = await client.call_tool(name, kwargs)
            body = result.structured_content or json.loads(result.content[0].text)
            evidence['calls'].append(dict(tool=name, seconds=time.perf_counter()-started))
            assert body['ok'], body
            return body['data']

        async def poll(value, expected):
            started = time.perf_counter()
            while value['state'] not in expected:
                assert value['state'] not in {'failed', 'uncertain', 'interrupted', 'outdated'}, value
                assert time.perf_counter()-started < 300, value
                await asyncio.sleep(.1)
                value = await tool('get_edit_workflow', workflow_id=value['id'], include_review=True)
            evidence['workflow'] = value
            record()
            return value

        async def action(value, name):
            value = await tool('get_edit_workflow', workflow_id=value['id'])
            choice = next(a for a in value['actions'] if a['action'] == name)
            result = await tool('respond_edit_workflow', workflow_id=value['id'],
                                expected_revision=value['revision'], action_token=choice['token'])
            evidence['workflow'] = result
            record()
            return result

        docs = await tool('list_documents')
        doc = next(d for d in docs if d['path'] == str(source))
        assert doc['dirty'] is False
        evidence['document'] = doc
        evidence['status'] = await tool('get_status')
        page = await tool('read_entities', document_id=doc['id'],
                          entities=[dict(kind='masters', limit=100)], fields=['id','name'])
        assert page[0]['values']['complete'] and len(page[0]['values']['items']) == 1
        mid = page[0]['values']['items'][0]['id']

        async def widths(changed):
            started = time.perf_counter()
            for start in range(0, 5000, 100):
                rows = await tool('read_entities', document_id=doc['id'],
                    entities=[dict(kind='layer',glyph='probe'+str(i),id=mid)
                              for i in range(start,start+100)], fields=['width'])
                assert len(rows) == 100
                for i,row in enumerate(rows,start):
                    assert row['values']['width'] == (500.375 if changed and i < 4096 else 500), row
            evidence['checks'].append(dict(check='all_widths', changed=changed,
                targets=4096,controls=904,seconds=time.perf_counter()-started))
            record()

        await widths(False)
        started = time.perf_counter()
        value = await tool('start_edit_workflow', document_id=doc['id'], kind='width_delta',
            glyphs=['probe'+str(i) for i in range(4096)], delta=.375, mode='apply',
            auto_keep=False, idempotency_key='m3-editor-package-large-20260927')
        evidence['workflow'] = value
        record()
        value = await poll(value, {'applied'})
        assert value['job']['bridgeOperation']['completedChanges'] == 4096
        evidence['applySeconds'] = time.perf_counter()-started
        await widths(True)
        started = time.perf_counter()
        value = await poll(await action(value,'discard'), {'discarded'})
        evidence['recoverySeconds'] = time.perf_counter()-started
        await widths(False)
        evidence['save'] = await tool('save_document', document_id=doc['id'])
        assert evidence['save']['nativeSaveSucceeded'] and evidence['save']['dirtyAfter'] is False
        record()
        verification = '''checked = 0
for glyph in font.glyphs:
    layer = glyph.layers[params['master']]
    assert layer.width == 500, glyph.name
    for surface in (layer, layer.background):
        flag = surface.temporarilyDisableRounding
        assert not (flag() if callable(flag) else flag), glyph.name
    manager = glyph.undoManager()
    assert manager.groupingLevel() == 0, glyph.name
    assert manager.groupsByEvent(), glyph.name
    checked += 1
print('Verified', checked, 'glyphs: widths, rounding flags, closed Undo groups')
'''
        value = await tool('start_edit_workflow', document_id=doc['id'],kind='python_script',
            mode='apply',auto_keep=False,idempotency_key='m3-editor-package-large-verify-20260927',
            options=dict(entrypoint='script',targets=[],source=verification,params=dict(master=mid),
                         summary='Verify restored widths, rounding settings and closed Undo groups'))
        value = await poll(value, {'waiting_run'})
        value = await poll(await action(value,'run_script'), {'applied'})
        output = value['job']['bridgeOperation']['scriptResult']['output']
        assert 'Verified 5000 glyphs' in output, output
        evidence['nativeVerification'] = output
        await action(value,'finish_script')
        evidence['finalSave'] = await tool('save_document',document_id=doc['id'])
        evidence['passed'] = True
        record()
        print(json.dumps({k:evidence[k] for k in ('passed','applySeconds','recoverySeconds','checks','nativeVerification')}),flush=True)


record()
asyncio.run(main())
