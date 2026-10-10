"""Save-free native Run, full pre-run restoration and unsaved duplicate receipts."""
from copy import deepcopy
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS
import pytest
ROOT=Path(__file__).resolve().parents[3]
for part in ('protocol','bridge','sidecar'):sys.path.insert(0,str(ROOT/'src'/part))
from glyphs_mcp_protocol import scripts, ProtocolError
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge import saved_script, script_snapshot
from glyphs_mcp_sidecar.service import SidecarService, ServiceError
from glyphs_mcp_sidecar.bridge_client import BridgeClientError
from glyphs_mcp_sidecar.jobs import JobStore
from test_simple_v2_edit_workflow import wait, choose


@pytest.fixture
def native(tmp_path,monkeypatch):
    host=NS(fonts=[],font=None,documentController=lambda:None)
    queue=[]
    class Manager:
        enabled=True
        def isUndoRegistrationEnabled(self):return self.enabled
        def disableUndoRegistration(self):self.enabled=False
        def enableUndoRegistration(self):self.enabled=True
        def removeAllActions(self):pass
    class Document:
        def __init__(self,font,dirty):self.font=font;self.changeCount=int(dirty);self.history=Manager()
        def isDocumentEdited(self):return self.changeCount>0
        def updateChangeCount_(self,value):self.changeCount=0 if value==2 else self.changeCount+1
        def undoManager(self):return self.history
        def setFont_(self,font):
            old=self.font;self.font=font;font.parent=self;font.filepath=old.filepath
            host.fonts[host.fonts.index(old)]=font;host.font=font
    class Font:
        def __init__(self,dirty=True,path=None):
            self.filepath=path;self.familyName='Snapshot fixture';self.parent=Document(self,dirty)
            self.glyphs={'A':NS(width=610)};self.masters=[NS(id='M1')];self.instances=[NS(name='Regular')]
            self.features=['before'];self.userData={'unsaved':7};self.tabs=[]
        def copy(self):
            other=Font(False)
            for attr in ('familyName','glyphs','masters','instances','features','userData'):
                setattr(other,attr,deepcopy(getattr(self,attr)))
            return other
        def show(self):
            if self not in host.fonts:host.fonts.append(self)
            host.font=self
        def save(self,*args,**kwargs):raise AssertionError('No Save in Run, Duplicate or Restore')
    monkeypatch.setitem(sys.modules,'GlyphsApp',NS(GSFont=Font,GSDocument=Document,Glyphs=host))
    saved_script.available.cache_clear()
    adapter=GlyphsAdapter(host);core=BridgeCore(adapter,queue.append)
    adapter._operation_font=adapter._font
    class Bridge:
        lose=False
        def status(self):return core.status()
        def documents(self):return core.list_documents()
        def invoke(self,func,*args):
            try:
                result=func(*args)
                while queue:queue.pop(0)()
                return result
            except BridgeError as exc:raise BridgeClientError(exc.code,exc.message,exc.details) from exc
        def review_script(self,request):return self.invoke(core.review_script,request)
        def reviewed_script(self,key):return saved_script.review_result(core,key,BridgeError)
        def run_script(self,request):return self.invoke(core.begin_script,request)
        def operation(self,key):return core.operation(key)
        def finish_script(self,key):return core.finish_script(key)
        def restore_saved_script(self,request):return self.invoke(lambda r:saved_script.restore(core,r,BridgeError),request)
        def duplicate_document(self,request):
            result=self.invoke(core.duplicate_document,request)
            if self.lose:
                self.lose=False
                raise BridgeClientError('bridge_timeout','lost duplicate response',{'execution':'uncertain'})
            return result
    # The public core has HTTP dispatch for reviews, not a direct method.
    core.review_script=lambda request:saved_script.review(core,request,BridgeError)
    bridge=Bridge();service=SidecarService(bridge,jobs=JobStore(tmp_path/'jobs'),worker=NS(status=lambda:{}))
    def add(dirty=True,path=None):
        font=Font(dirty,path);font.show();return font,adapter._id(font)
    yield host,core,bridge,service,add
    service.close();saved_script.available.cache_clear()


def run(service,identity,source='font.glyphs["A"].width=620\nfont.features.append("after")\nfont.userData["unsaved"]=9',key='run'):
    value=service.edit_workflows.start(identity,kind='python_script',idempotency_key=key,auto_keep=False,mode='preview',
        options=dict(entrypoint='script',source=source,targets=[]))
    value=wait(service,value,'waiting_run')
    value=choose(service,value,'run_script')
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        value=service.edit_workflows.get(value['id'])
        if value['state'] in {'applied','failed'}:return value
        time.sleep(.01)
    raise AssertionError(value)


@pytest.mark.parametrize('dirty,pathless',[(True,True),(False,True),(True,False),(False,False)])
def test_native_snapshot_restores_exact_pre_run_state(native,tmp_path,dirty,pathless):
    host,core,_,service,add=native
    path=None
    if not pathless:
        source=tmp_path/'Source.glyphs';source.write_text('original disk bytes');path=str(source)
    font,identity=add(dirty,path)
    value=run(service,identity)
    assert value['state']=='applied' and font.glyphs['A'].width==620
    assert value['savedVersion']['kind']=='memory_snapshot' and value['savedVersion']['available']
    old=value;value=choose(service,value,'restore_saved_script');choose(service,old,'restore_saved_script')
    assert value['state']=='discarded' and 'Earlier unsaved edits were retained' in value['message']
    restored=host.fonts[0]
    assert restored is not font and restored.glyphs['A'].width==610
    assert restored.features==['before'] and restored.userData=={'unsaved':7}
    assert value['document']['dirty'] is dirty and value['document']['path']==path
    assert value['document']['id'] != identity
    assert not core._operations[value['jobId']].get('scriptSnapshot')
    if path:assert source.read_text()=='original disk bytes'


def test_partial_failure_restores_unsaved_state_without_rerun(native):
    host,_,_,service,add=native;_,identity=add()
    value=run(service,identity,'font.glyphs["A"].width=699\nraise RuntimeError("partial")')
    assert value['state']=='failed' and host.fonts[0].glyphs['A'].width==699
    value=choose(service,value,'restore_saved_script')
    assert value['state']=='discarded' and host.fonts[0].glyphs['A'].width==610 and value['document']['dirty']


def test_direct_apply_captures_native_recovery_and_keeps_earlier_unsaved_edits(native):
    host, core, _, service, add = native
    font, identity = add(); font.userData['earlier'] = 42
    value = service.edit_workflows.start(identity, kind='python_script', idempotency_key='direct-native',
        mode='apply', auto_keep=False, options=dict(entrypoint='script', targets=[],
            source='font.glyphs["A"].width=777'))
    value = wait(service, value, 'applied')
    assert font.glyphs['A'].width == 777 and value['savedVersion']['available']
    value = choose(service, value, 'restore_saved_script')
    assert value['state'] == 'discarded'
    assert host.font.glyphs['A'].width == 610 and host.font.userData['earlier'] == 42
    assert value['document']['dirty'] and value['document']['path'] is None


def test_snapshot_failure_never_executes_or_dirties(native,monkeypatch):
    host,core,_,service,add=native;font,identity=add(False)
    monkeypatch.setattr(type(font),'copy',lambda _:None)
    value=run(service,identity)
    assert value['state']=='failed' and not value['job']['bridgeOperation']['scriptResult']['executed']
    assert not core.adapter.document_state(identity)['dirty'] and font.glyphs['A'].width==610


def test_keep_releases_native_snapshot(native):
    _,core,_,service,add=native;_,identity=add();value=run(service,identity)
    choose(service,value,'finish_script')
    op=core._operations[value['jobId']]
    assert 'scriptSnapshot' not in op and not op['scriptResult']['recovery']['available']


def test_external_source_change_restores_as_dirty_without_overwriting(native,tmp_path):
    host,_,_,service,add=native;source=tmp_path/'S.glyphs';source.write_text('before')
    _,identity=add(False,str(source));value=run(service,identity);source.write_text('external')
    value=choose(service,value,'restore_saved_script')
    assert value['state']=='discarded' and value['document']['dirty'] and host.fonts[0].glyphs['A'].width==610
    assert source.read_text()=='external'


@pytest.mark.parametrize('source',['pass','def run(): pass','async def run(layer, params, context): pass','def run(layer, params, context, extra): pass'])
def test_obvious_entrypoint_errors_reject_without_execution(source):
    with pytest.raises(ProtocolError):scripts.validate_options(dict(source=source,targets=[dict(glyph='A',layer='M')]))


def test_duplicate_includes_unsaved_changes_and_is_independent(native):
    host,core,_,service,add=native;source,identity=add();source.glyphs['A'].width=777
    other,_=add();before=core.adapter.document_state(identity)
    result=service.duplicate_document(identity,'duplicate','Demo')
    copy=core.adapter._font(result['id'])
    assert result['path'] is None and copy.familyName=='Demo' and copy.glyphs['A'].width==777
    copy.glyphs['A'].width=888
    assert source.glyphs['A'].width==777 and other.glyphs['A'].width==610
    assert core.adapter.document_state(identity)==before and len(host.fonts)==3
    assert service.duplicate_document(identity,'duplicate','Demo')['id']==result['id'] and len(host.fonts)==3
    with pytest.raises(ServiceError) as failure:service.duplicate_document(identity,'duplicate','Other')
    assert failure.value.code=='duplication_conflict'


def test_duplicate_lost_response_and_sidecar_restart_reuse_original(native):
    host,_,bridge,service,add=native;_,identity=add();bridge.lose=True
    with pytest.raises(ServiceError):service.duplicate_document(identity,'duplicate')
    assert len(host.fonts)==2
    restarted=SidecarService(bridge,jobs=JobStore(service.jobs.root),worker=service.worker)
    try:
        result=restarted.duplicate_document(identity,'duplicate')
        assert result['id'] and len(host.fonts)==2
    finally:restarted.close()


def test_duplicate_closed_copy_and_bridge_restart_never_recreate(native):
    host,core,_,service,add=native;_,identity=add();result=service.duplicate_document(identity,'duplicate')
    host.fonts.remove(core.adapter._font(result['id']))
    with pytest.raises(ServiceError) as failure:service.duplicate_document(identity,'duplicate')
    assert failure.value.code=='document_not_found' and len(host.fonts)==1
    core.bridge_session_id='restarted'
    with pytest.raises(ServiceError) as failure:service.duplicate_document(identity,'duplicate')
    assert failure.value.code=='duplication_outcome_unknown' and len(host.fonts)==1


def test_unavailable_disk_source_does_not_block_memory_run(native,tmp_path):
    _,_,_,service,add=native;_,identity=add(True,str(tmp_path/'missing.glyphs'))
    value=run(service,identity)
    assert value['state']=='applied' and value['savedVersion']['available']
    value=choose(service,value,'restore_saved_script')
    assert value['state']=='discarded' and value['document']['dirty']


def test_duplicate_failure_after_attachment_never_repeats(native,monkeypatch):
    host,_,_,service,add=native;font,identity=add()
    actual=type(font).show
    def fail(self):actual(self);raise RuntimeError('after attachment')
    monkeypatch.setattr(type(font),'show',fail)
    for _ in range(2):
        with pytest.raises(ServiceError) as failure:service.duplicate_document(identity,'fail')
        assert failure.value.code=='duplication_outcome_unknown' and failure.value.details.get('documentId')
    assert len(host.fonts)==2


def test_duplicate_rejects_paused_busy_and_unsupported_hosts(native,monkeypatch):
    host,core,_,service,add=native;_,identity=add()
    core.paused=True
    with pytest.raises(ServiceError) as failure:service.duplicate_document(identity,'paused')
    assert failure.value.code=='server_stopped'
    core.paused=False
    core._operations['busy']=dict(jobId='busy',documentId=identity,status='applied')
    with pytest.raises(ServiceError) as failure:service.duplicate_document(identity,'busy')
    assert failure.value.code=='document_busy'
    core._operations.clear()
    from glyphs_mcp_bridge import document_duplication
    monkeypatch.setattr(document_duplication,'available',lambda:False)
    with pytest.raises(ServiceError) as failure:service.duplicate_document(identity,'unsupported')
    assert failure.value.code=='unsupported_capability' and len(host.fonts)==1


def test_duplicate_public_transport_and_timeout_identity(native,monkeypatch):
    import asyncio
    from fastmcp import Client
    from glyphs_mcp_sidecar.server import create_server
    from glyphs_mcp_sidecar.bridge_client import BridgeClient
    from glyphs_mcp_bridge.http_server import BridgeHTTPServer
    from glyphs_mcp_protocol import document_duplication as contract, TOOL_NAMES
    import glyphs_mcp_sidecar.bridge_client as transport
    _,core,_,service,add=native;_,identity=add()
    owner=object.__new__(BridgeHTTPServer);owner.core=core
    handler=object.__new__(owner._handler());handler.path='/v1/documents/duplicate'
    request=dict(contract.options(identity,'http'),bridgeSessionId=core.bridge_session_id)
    assert handler._route({'duplication':request})['sourceDocumentId']==identity
    async def exercise():
        async with Client(create_server(service)) as client:
            catalog={tool.name:tool for tool in await client.list_tools()}
            assert set(catalog)==set(TOOL_NAMES) and len(catalog)==20
            assert set(catalog['duplicate_document'].inputSchema['required'])=={'document_id','idempotency_key'}
            result=await client.call_tool('duplicate_document',dict(document_id=identity,idempotency_key='public'))
            assert result.data['ok'] and result.data['data']['path'] is None
    asyncio.run(exercise())
    monkeypatch.setattr(transport,'urlopen',lambda *a,**kw:(_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(BridgeClientError) as failure:BridgeClient('http://localhost','test').duplicate_document(request)
    assert failure.value.details==dict(execution='uncertain',duplicationId=request['duplicationId'])


def test_duplicate_show_can_advance_ui_generation_without_source_edits(native,monkeypatch):
    _,core,_,service,add=native;source,identity=add()
    actual=type(source).show
    def show(font):
        actual(font)
        source.parent.changeCount+=1  # Native UI notification after detached copy.
    monkeypatch.setattr(type(source),'show',show)
    result=service.duplicate_document(identity,'ui-generation')
    assert result['path'] is None and source.glyphs['A'].width==610
