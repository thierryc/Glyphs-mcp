"""Native preparation remains read-only and feeds the existing guarded patch path."""
from copy import deepcopy
from types import SimpleNamespace
import time
import pytest
from test_simple_v2_edit_workflow import env, start, wait, choose
from glyphs_mcp_protocol.preparation import simple
from glyphs_mcp_bridge import typed_preparation
from glyphs_mcp_bridge.core import BridgeError


def enable(bridge):
    bridge.adapter._font=lambda doc:SimpleNamespace(glyphs=[SimpleNamespace(name='A',layers=[SimpleNamespace(layerId='M1', width=bridge.adapter.value)])])
    bridge.status=bridge.core.status
    bridge.prepare_typed=lambda r:bridge.call(typed_preparation.begin,bridge.core,r,BridgeError)
    bridge.prepared_typed=lambda j:bridge.call(typed_preparation.result,bridge.core,j,BridgeError)


def test_native_preview_and_keep_never_launch_worker_or_copy(env):
    service,bridge,worker,source=env;enable(bridge)
    worker.status=lambda:(_ for _ in ()).throw(AssertionError('must not query worker'))
    worker.prepare=lambda *a:(_ for _ in ()).throw(AssertionError('must not launch worker'))
    value=wait(service,start(env,mode='preview'),'ready')
    assert bridge.adapter.value==600 and not bridge.adapter.dirty and not bridge.applies
    assert not list(service.jobs.path(value['jobId']).glob('source*'))
    assert service.jobs.get(value['jobId'])['preparationRoute']=='native'
    value=wait(service,choose(service,value,'apply'),'applied')
    assert bridge.adapter.value==608
    assert choose(service,value,'finish_edit')['state']=='executed'
    assert source.read_text()=='600' and not bridge.adapter.save_calls


def request(source, count=1):
    return dict(jobId='job_prepare',documentId='doc_1',sourcePath=str(source),sourceHash='sha256:'+'a'*64,
        generation=1, request=dict(kind='width_delta',delta=.25,glyphs=[]))


def test_chunking_cancellation_and_document_change(env):
    service,bridge,_,source=env;enable(bridge)
    bridge.core.chunk_limit=1
    bridge.adapter._font=lambda doc:SimpleNamespace(glyphs=[SimpleNamespace(name='A',layers=[SimpleNamespace(layerId='M'+str(i),width=600) for i in range(5)])])
    op=typed_preparation.begin(bridge.core,request(source),BridgeError)
    assert op['status']=='preparing'
    bridge.queue.items.pop(0)()
    assert bridge.core.operation(op['jobId'])['status']=='preparing'
    bridge.adapter.dirty=True
    bridge.queue.drain()
    assert bridge.core.operation(op['jobId'])['error']['code']=='document_not_clean'
    assert bridge.adapter.value==600
    bridge.adapter.dirty=False
    r=request(source);r['jobId']='job_cancel'
    typed_preparation.begin(bridge.core,r,BridgeError)
    bridge.core.discard(r['jobId']);bridge.queue.drain()
    assert bridge.core.operation(r['jobId'])['status']=='cancelled'
    assert 'prepareIterator' not in bridge.core._operations[r['jobId']]


def test_advertised_failure_does_not_fallback_to_worker(env):
    service,bridge,worker,source=env;enable(bridge)
    def fail(r):raise BridgeError('native_failure','probe')
    bridge.prepare_typed=fail
    value=wait(service,start(env),'failed')
    assert worker.calls==bridge.applies==0


def test_lost_capability_read_does_not_leave_an_unstarted_job(env):
    service, bridge, worker, _ = env
    enable(bridge)
    calls = []
    def availability(request, bridge_status=None):
        calls.append(True)
        if len(calls) == 2: raise RuntimeError('lost capability read')
        return True
    service._native_preparation_available = availability
    with pytest.raises(RuntimeError, match='lost capability read'):
        service.start_job('doc_1', kind='width_delta', delta=8)
    assert not service.jobs.records() and not service._cancellations
    assert worker.calls == bridge.applies == 0


def test_stale_source_rejected_at_application(env):
    service,bridge,_,source=env;enable(bridge)
    value=wait(service,start(env,mode='preview'),'ready')
    source.write_text('700')
    result=choose(service,value,'apply')
    assert result['state']=='outdated' and bridge.adapter.value==600


def test_outline_eligibility_is_closed_and_whole_request():
    base=dict(kind='outline_edit',options=dict(targets=[dict(operations=[dict(op='update_nodes',updates=[dict(index=0,delta=dict(dx=.25,dy=0))])])]))
    assert simple.eligible(base)
    for field,value in [('name','x'),('smooth',True),('type','line')]:
        changed=deepcopy(base);changed['options']['targets'][0]['operations'][0]['updates'][0][field]=value
        assert not simple.eligible(changed)
    changed=deepcopy(base);changed['options']['targets'].append(dict(operations=[dict(op='reverse_path')]))
    assert not simple.eligible(changed)
    for kind in ['spacing','kerning_collision','slant','start_nodes','font_export','feature_compile']:
        assert not simple.eligible(dict(kind=kind))


def test_duplicate_preparation_and_result_limit(env,monkeypatch):
    service,bridge,worker,source=env;enable(bridge)
    r=request(source)
    typed_preparation.begin(bridge.core,r,BridgeError)
    typed_preparation.begin(bridge.core,r,BridgeError)
    assert len(bridge.queue.items)==1
    monkeypatch.setattr(typed_preparation,'MAX_RESULT_BYTES',32)
    bridge.queue.drain()
    assert bridge.core.operation(r['jobId'])['error']['code']=='request_too_large'
    assert bridge.adapter.value==600 and not bridge.adapter.save_calls


def test_width_reads_only_stored_layers_never_lazy_wrapper():
    from glyphs_mcp_protocol.preparation import consume
    class Glyph:
        name='A'
        def countOfLayers(self):return 1
        def objectInLayersAtIndex_(self,i):return SimpleNamespace(layerId='stored',width=500)
        @property
        def layers(self):raise AssertionError('wrapper may create a missing master layer')
    changes, _=consume(simple.width_iter(SimpleNamespace(glyphs=[Glyph()]),dict(glyphs=[],delta=.25)))
    assert [(c['layer'],c['after']) for c in changes]==[('stored',500.25)]


def test_native_action_normalized_request_can_be_prepared_twice():
    from glyphs_mcp_protocol.native_actions import validate_options
    request=dict(kind='native_action',glyphs=[],options=validate_options(dict(action='set_glyph_color',arguments=dict(color='red'),targets=[dict(glyph='A')])))
    assert simple.validate_request(request)==request
    forged=deepcopy(request);forged['options']['scope']='font'
    with pytest.raises(ValueError):simple.validate_request(forged)
