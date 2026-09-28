"""Actual-editor typed pair lifecycle over the installed local MCP connection."""
import argparse,asyncio,json,time
from pathlib import Path
from fastmcp import Client

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--format',choices=['glyphs','glyphspackage'],required=True)
parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
fixture=json.loads((ROOT/'build/beta8-milestone8/editor'/args.format/'fixture.json').read_text())
assert not args.output.exists(),'Reconcile recorded workflows before retrying; preserve evidence'
evidence=dict(fixture=fixture,calls=[],cases=[],client='fresh local FastMCP HTTP connection; not Codex connector latency')


def record(): args.output.write_text(json.dumps(evidence,indent=2)+'\n')


async def main():
    async with Client('http://127.0.0.1:9680/mcp/') as client:
        async def call(name,expect_error=False,**params):
            started=time.perf_counter();result=await client.call_tool(name,params)
            body=result.structured_content or json.loads(result.content[0].text)
            evidence['calls'].append(dict(tool=name,seconds=time.perf_counter()-started,ok=body.get('ok')))
            if expect_error:return body
            assert body['ok'],body
            value=body['data']
            if name in {'start_edit_workflow','get_edit_workflow','respond_edit_workflow'}:
                evidence['workflow']=value;record()
            return value
        async def poll(value,*states):
            started=time.perf_counter()
            while value['state'] not in states:
                assert value['state'] not in {'failed','outdated','uncertain','interrupted'},value
                assert time.perf_counter()-started<120,value
                await asyncio.sleep(.1);value=await call('get_edit_workflow',workflow_id=value['id'])
            return value
        async def choose(value,name):
            value=await call('get_edit_workflow',workflow_id=value['id'])
            choice=next(a for a in value['actions'] if a['action']==name)
            params=dict(workflow_id=value['id'],expected_revision=value['revision'],action_token=choice['token'])
            return await call('respond_edit_workflow',**params),params
        docs=await call('list_documents');document=next(d for d in docs if d['path']==fixture['path'])
        assert document['dirty'] is False
        doc=document['id'];mid=fixture['master'];evidence['document']=document
        evidence['status']=await call('get_status')
        assert 'kerning.edit.exact.v1' in evidence['status']['writeCapabilities']
        async def stored(left,right,direction,master=mid):
            values=await call('read_entities',document_id=doc,entities=[dict(kind='kerning',master=master,direction=direction,left=left,right=right)],fields=['value'])
            return values[0]['values']['value']
        async def controls():
            return await call('read_entities',document_id=doc,entities=[dict(kind='layer',glyph=n,id=mid) for n in ('A','V','n')],fields=['width','outlineHash'])
        initial_controls=await controls()
        async def begin(row,key,mode='preview'):
            return await call('start_edit_workflow',document_id=doc,kind='kerning_edit',options=dict(edits=[row]),mode=mode,auto_keep=False,idempotency_key=key)
        for direction,prefixes in [('LTR',('@MMK_L_right_A','@MMK_R_left_V')),('RTL',('@MMK_R_left_A','@MMK_L_right_V')),('vertical',('@MMK_T_bottom_A','@MMK_B_top_V'))]:
            for gl,gr in ((False,False),(True,False),(False,True),(True,True)):
                left,right=prefixes[0] if gl else 'A',prefixes[1] if gr else 'V'
                for desired in (-72.5,0,None):
                    before=await stored(left,right,direction)
                    if desired is None and before is None:
                        # Seed an explicit zero through the same public route so deletion is real.
                        seed=dict(op='set',master=mid,direction=direction,left=dict(kind='group',key=left) if gl else dict(kind='glyph',name=left),right=dict(kind='group',key=right) if gr else dict(kind='glyph',name=right),value=0)
                        v=await poll(await begin(seed,f'm8-{args.format}-{direction}-{gl}-{gr}-seed','apply'),'applied')
                        v,_=await choose(v,'save_result');await poll(v,'saved');before=0
                    row=dict(op='remove' if desired is None else 'set',master=mid,direction=direction,
                             left=dict(kind='group',key=left) if gl else dict(kind='glyph',name=left),
                             right=dict(kind='group',key=right) if gr else dict(kind='glyph',name=right),
                             **({} if desired is None else dict(value=desired)))
                    key=f'm8-{args.format}-{direction}-{gl}-{gr}-{desired}'
                    started=time.perf_counter();value=await poll(await begin(row,key),'ready')
                    preparation=time.perf_counter()-started;assert await stored(left,right,direction)==before
                    value,dispatch=await choose(value,'apply');value=await poll(value,'applied')
                    assert await stored(left,right,direction)==desired
                    duplicate=await call('respond_edit_workflow',**dispatch);assert duplicate['jobId']==value['jobId']
                    assert await controls()==initial_controls
                    assert await stored('A','V',direction,fixture['otherMaster'])==-31.125
                    value,_=await choose(value,'discard');value=await poll(value,'discarded')
                    assert await stored(left,right,direction)==before
                    save=await call('save_document',document_id=doc)
                    assert save['nativeSaveSucceeded'] and save['dirtyAfter'] is False,save
                    evidence['cases'].append(dict(direction=direction,left=left,right=right,before=before,after=desired,
                                                  preparationSeconds=preparation,duplicateApply=True,selectiveRecovery=True,actualEditorSave=True))
                    record()
        # Keep releases ownership, preserves dirty state, and the waiting preview
        # requests a separately authorized prerequisite Save before preparing.
        row=dict(op='set',master=mid,direction='LTR',left=dict(kind='glyph',name='A'),right=dict(kind='glyph',name='V'),value=-63.125)
        first=await poll(await begin(row,'m8-'+args.format+'-keep','apply'),'applied')
        waiting=await begin(dict(row,value=-64.25),'m8-'+args.format+'-waiting')
        assert waiting['blockingWorkflowId']==first['id'],waiting
        kept,dispatch=await choose(first,'finish_edit');assert kept['state']=='executed'
        duplicate=await call('respond_edit_workflow',**dispatch);assert duplicate['state']=='executed'
        live=next(d for d in await call('list_documents') if d['id']==doc);assert live['dirty'] is True
        waiting=await poll(waiting,'waiting_save')
        waiting,_=await choose(waiting,'save_continue');waiting=await poll(waiting,'ready')
        assert await stored('A','V','LTR')==-63.125
        # Reconnect before dispatch; same workflow must remain ready, never replayed.
        async with Client('http://127.0.0.1:9680/mcp/') as fresh:
            response=await fresh.call_tool('get_edit_workflow',dict(workflow_id=waiting['id']))
            body=response.structured_content or json.loads(response.content[0].text)
            assert body['ok'] and body['data']['state']=='ready'
        waiting,_=await choose(waiting,'apply');waiting=await poll(waiting,'applied')
        waiting,_=await choose(waiting,'save_result');waiting=await poll(waiting,'saved')
        assert await stored('A','V','LTR')==-64.25
        evidence['keepNextTask']=dict(kept=kept['id'],waiting=waiting['id'],dirtyPreserved=True,reconnected=True,saved=True)
        assert await controls()==initial_controls
        evidence['documentsAfter']=await call('list_documents');evidence['passed']=True;record()


try:asyncio.run(main())
except BaseException:
    import traceback
    evidence['error']=traceback.format_exc();record();raise
