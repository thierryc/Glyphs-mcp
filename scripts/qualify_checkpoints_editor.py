"""Installed editor checkpoint qualification. Disposable open fonts only; no code replay."""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
from fastmcp import Client
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/sidecar'),str(ROOT/'src/protocol')]
from glyphs_mcp_protocol.source_identity import source_hash
from glyphs_mcp_sidecar.checkpoint_git import Repository
from glyphs_mcp_sidecar.checkpoint_history import materialize
parser=argparse.ArgumentParser();parser.add_argument('--format',choices=['glyphs','glyphspackage'],required=True);parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();folder=ROOT/'build/beta8-milestone6/editor'/args.format
font=folder/('Checkpoint.'+args.format)
assert font.exists() and not args.output.exists()
evidence={'format':args.format,'client':'fresh FastMCP client; actual Glyphs editor; same editor process','calls':[],'runs':[]}

def record():args.output.write_text(json.dumps(evidence,indent=2)+'\n')
def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(folder),*args])

async def main():
    async with Client('http://127.0.0.1:9680/mcp/') as client:
        async def tool(name,**kwargs):
            start=time.perf_counter();result=await client.call_tool(name,kwargs)
            body=result.structured_content or json.loads(result.content[0].text)
            evidence['calls'].append(dict(tool=name,seconds=time.perf_counter()-start))
            assert body['ok'],body
            return body['data']
        async def poll(value,states):
            start=time.monotonic()
            while value['state'] not in states:
                if value['state']=='waiting_save':
                    value=await action(value,'save_continue')
                    continue
                assert value['state'] not in {'failed','uncertain','interrupted','outdated'},value
                assert time.monotonic()-start<120,value
                await asyncio.sleep(.05);value=await tool('get_edit_workflow',workflow_id=value['id'])
            evidence['workflow']=value;record();return value
        async def action(value,name):
            value=await tool('get_edit_workflow',workflow_id=value['id'])
            choice=next(a for a in value['actions'] if a['action']==name)
            return await tool('respond_edit_workflow',workflow_id=value['id'],expected_revision=value['revision'],action_token=choice['token'])
        async def request(kind,**kwargs):
            return await tool('start_edit_workflow',document_id=doc['id'],kind=kind,mode='apply',auto_keep=False,idempotency_key='m6-'+uuid4().hex,**kwargs)
        async def widths():
            rows=await tool('read_entities',document_id=doc['id'],entities=[dict(kind='layer',glyph=name,id=master) for name in ['H','A']],fields=['width'])
            return [r['values']['width'] for r in rows]
        docs=await tool('list_documents');doc=next(d for d in docs if d['path']==str(font))
        assert doc['dirty'] is False
        evidence['status']=await tool('get_status');evidence['initialDocument']=doc
        master='0578215A-7423-43EB-8AD4-4C95A1C78DFA'
        baseline=git('rev-parse','HEAD').decode().strip();staged=git('diff','--cached','--binary');unrelated=(folder/'unrelated.txt').read_bytes()
        before=await widths();evidence['baseline']=baseline;evidence['baselineWidths']=before
        native_reference=materialize(Repository(font,folder/'unused',lambda _:None),baseline,ROOT/'build/beta8-milestone6'/('reference-'+args.format+'-'+uuid4().hex))
        for index in range(5):
            started=time.perf_counter();value=await poll(await request('width_delta',glyphs=['H'],delta=.125),{'applied'})
            execution=time.perf_counter()-started
            observed=await widths();assert abs(observed[0]-(before[0]+.125*(index+1)))<1e-6 and observed[1]==before[1]
            started=time.perf_counter();wall=time.time();value=await poll(await action(value,'save_result'),{'saved'})
            elapsed=time.perf_counter()-started;finished_wall=time.time();receipt=value['receipt'];checkpoint=receipt['checkpoint']
            assert checkpoint['status']=='created',receipt
            assert source_hash(font)==receipt['sourceHashAfter']
            repository=Repository(font,folder/'unused',lambda _:None)
            assert repository.tree_entries(checkpoint['revision'])==repository._snapshot(receipt['sourceHashAfter'])
            assert git('diff','--cached','--binary')==staged and (folder/'unrelated.txt').read_bytes()==unrelated
            evidence['runs'].append(dict(repetition=index+1,preparationAndApplicationSeconds=execution,saveAndCheckpointSeconds=elapsed,
                dispatchToVerifiedSaveSeconds=receipt['savedAt']-wall,verifiedSaveToResponseSeconds=finished_wall-receipt['savedAt'],checkpoint=checkpoint,receipt=receipt))
            record()
        # Failure after live edits is kept explicitly, then replaced by history.
        script="""from GlyphsApp import GSFeature, GSLTR
font.grid=0
layer=font.glyphs['H'].layers[params['master']]
layer.width += 17.375
for path in layer.paths:
    for node in path.nodes:
        node.position=(node.position.x + .375,node.position.y - .625)
font.userData['checkpoint_partial_test']='later unsaved'
font.setKerningForPair(params['master'],'A','V',-123.25,GSLTR)
feature=GSFeature();feature.name='zzzz';feature.code='sub H by A;';font.features.append(feature)
raise RuntimeError('Intentional partial-edit qualification')
"""
        value=await poll(await request('python_script',options=dict(entrypoint='script',targets=[],source=script,params={'master':master},summary='Exercise partial edits on the disposable checkpoint font')) ,{'waiting_run'})
        value=await poll(await action(value,'run_script'),{'failed'})
        assert value['job']['bridgeOperation']['scriptResult']['executed']
        await action(value,'finish_script')
        saved_hash=source_hash(font)
        value=await poll(await request('checkpoint_restore',options={'revision':baseline}),{'applied'})
        assert value['document']['id']!=doc['id'];doc=value['document'];evidence['restoredDocument']=doc
        assert source_hash(font)==saved_hash and await widths()==before
        revision=value['revision'];assert (await tool('get_edit_workflow',workflow_id=value['id']))['revision']==revision
        value=await poll(await action(value,'save_result'),{'saved'})
        assert value['receipt']['checkpoint']['status']=='created'
        evidence['restoreReceipt']=value['receipt']
        verify="""from GlyphsApp import GSFont
from Foundation import NSURL
loaded=GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(params['reference']),None)
old=loaded[0] if isinstance(loaded,tuple) else loaded
assert old is not None
assert font.userData['checkpoint_partial_test'] is None
def pairs(value):
    names={str(g.id):g.name for g in value.glyphs}
    return sorted((str(master),names.get(str(left),str(left)),names.get(str(right),str(right)),float(amount)) for master,lefts in value.kerning.items() for left,rights in lefts.items() for right,amount in rights.items())
assert pairs(font)==pairs(old),'kerning values'
assert [(f.name,f.code) for f in font.features]==[(f.name,f.code) for f in old.features]
assert font.grid==old.grid
checked=0
for name in ['H','A','V','T','o','n']:
    assert not font.glyphs[name].undoManager().canUndo(),name
    for prior in old.glyphs[name].layers:
        current=font.glyphs[name].layers[prior.layerId]
        assert current.width==prior.width,(name,prior.layerId,current.width,prior.width)
        assert [[(n.position.x,n.position.y,n.type,n.smooth) for n in p.nodes] for p in current.paths]==[[(n.position.x,n.position.y,n.type,n.smooth) for n in p.nodes] for p in prior.paths],name
        checked+=1
assert not font.parent.undoManager().canUndo()
print('Verified outlines, widths, kerning, features, metadata, grid and cleared document Undo:',checked,'layers')
"""
        value=await poll(await request('python_script',options=dict(entrypoint='script',targets=[],source=verify,params={'reference':str(native_reference)},summary='Verify restored font content and cleared document Undo')),{'waiting_run'})
        value=await poll(await action(value,'run_script'),{'applied'})
        details=await tool('get_edit_workflow',workflow_id=value['id'],include_review=True);evidence['nativeVerification']=details['job']['bridgeOperation']['scriptResult']
        await action(value,'finish_script')
        # A hook added after application makes Git fail after a successful Save.
        value=await poll(await request('width_delta',glyphs=['H'],delta=.125),{'applied'})
        hook=folder/'.git/hooks/pre-commit';hook.parent.mkdir(exist_ok=True);hook.write_text('#!/bin/sh\nexit 0\n');hook.chmod(0o755)
        value=await poll(await action(value,'save_result'),{'saved'})
        assert value['receipt']['checkpoint']['status']=='failed'
        saved=value['receipt'];hook.unlink();value=await action(value,'retry_checkpoint')
        assert value['receipt']['checkpoint']['status']=='created' and value['receipt']['savedAt']==saved['savedAt']
        evidence['checkpointRetry']={'failedReceipt':saved,'retriedReceipt':value['receipt']}
        assert git('diff','--cached','--binary')==staged and (folder/'unrelated.txt').read_bytes()==unrelated
        evidence['passed']=True;record()
asyncio.run(main())
