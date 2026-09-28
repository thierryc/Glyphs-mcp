"""Historical restore uses the editor, exact binding and existing operation registry."""
import pytest
from test_simple_v2_edit_workflow import Bridge
from glyphs_mcp_protocol.source_identity import source_hash
from glyphs_mcp_bridge.core import BridgeError


def test_restore_is_in_memory_exactly_once_and_returns_fresh_binding(tmp_path,monkeypatch):
    from glyphs_mcp_bridge import checkpoint_restore
    path=tmp_path/'Test.glyphs';path.write_text('600')
    historical=tmp_path/'history.glyphs';historical.write_text('500')
    bridge=Bridge(path);core=bridge.core;calls=[]
    def load(core,request,error):
        calls.append(request);return object()
    def replace(core,request,font,error):
        bridge.adapter.value=500;bridge.adapter.dirty=True
        return dict(core.adapter.document_state('doc_1'),id='doc_fresh',dirty=True)
    monkeypatch.setattr(checkpoint_restore,'load',load);monkeypatch.setattr(checkpoint_restore,'replace',replace)
    request=dict(jobId='job_restore',documentId='doc_1',generation=bridge.adapter.document_state('doc_1')['generation'],
                 sourcePath=str(path),sourceHash=source_hash(path),historicalPath=str(historical),historicalHash=source_hash(historical))
    result=checkpoint_restore.restore(core,request,BridgeError)
    assert result['status']=='applied' and result['documentAfter']['id']=='doc_fresh'
    assert path.read_text()=='600' and len(calls)==1
    assert checkpoint_restore.restore(core,request,BridgeError)==result and len(calls)==1
    assert bridge.adapter.save_calls==[]
    with pytest.raises(BridgeError):core.discard('job_restore')
    core.finish_edit('job_restore')


def test_stale_restore_does_not_load_or_replace(tmp_path,monkeypatch):
    from glyphs_mcp_bridge import checkpoint_restore
    path=tmp_path/'Test.glyphs';path.write_text('600');bridge=Bridge(path)
    request=dict(jobId='job_restore',documentId='doc_1',generation=-1,sourcePath=str(path),sourceHash=source_hash(path),historicalPath=str(path),historicalHash=source_hash(path))
    monkeypatch.setattr(checkpoint_restore,'load',lambda *args: pytest.fail('must not load'))
    with pytest.raises(BridgeError,match='changed'):checkpoint_restore.restore(bridge.core,request,BridgeError)


def test_partial_restore_is_unresolved_until_explicit_acknowledgment(tmp_path,monkeypatch):
    from glyphs_mcp_bridge import checkpoint_restore
    path=tmp_path/'Test.glyphs';path.write_text('600');bridge=Bridge(path);core=bridge.core
    request=dict(jobId='job_partial_restore',documentId='doc_1',generation=1,sourcePath=str(path),sourceHash=source_hash(path),historicalPath=str(path),historicalHash=source_hash(path))
    monkeypatch.setattr(checkpoint_restore,'load',lambda *args:object())
    monkeypatch.setattr(checkpoint_restore,'replace',lambda *args:(_ for _ in ()).throw(RuntimeError('replacement interrupted')))
    value=checkpoint_restore.restore(core,request,BridgeError)
    assert value['status']=='failed' and value['error']['details']['writeAttempted']
    with pytest.raises(BridgeError):core._check_owner('doc_1')
    with pytest.raises(BridgeError):core.finish_edit('job_partial_restore')
    assert checkpoint_restore.acknowledge(core,'job_partial_restore',BridgeError)['status']=='completed'
    core._check_owner('doc_1')
    assert path.read_text()=='600' and not bridge.adapter.save_calls
