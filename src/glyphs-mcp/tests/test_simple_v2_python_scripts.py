"""Script contracts, chat consent, retries, and bounded transfer."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[3]
for part in ('protocol', 'bridge', 'sidecar'): sys.path.insert(0, str(ROOT/'src'/part))
from glyphs_mcp_protocol import scripts, validate_patch, ProtocolError
from glyphs_mcp_protocol.script_runtime import ScriptRuntime
from glyphs_mcp_sidecar.service import SidecarService, ServiceError
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_bridge.core import BridgeError
from test_simple_v2_saved_scripts import env as script_env
from test_simple_v2_edit_workflow import Bridge, wait


def options(**extra):
    return dict(source='def run(layer, params, context):\n    layer.width += params.get("delta", 1)',
                targets=[dict(glyph='A',layer='M1')], **extra)


@pytest.mark.parametrize('extra', [dict(executionMode='oops'), dict(summary='a'*501), dict(recovery='none'),
                                 dict(params={'bad':float('nan')}), dict(entrypoint='other')])
def test_invalid_script_requests(extra):
    with pytest.raises(ProtocolError): scripts.validate_options(options(**extra))


def test_source_validation_does_not_execute(tmp_path):
    marker=tmp_path/'must-not-exist'
    source=f'from pathlib import Path\nPath({str(marker)!r}).write_text("ran")'
    result=scripts.validate_options(dict(source=source,targets=[],entrypoint='script'))
    assert not marker.exists() and result['source']==source
    with pytest.raises(ProtocolError): scripts.validate_options(dict(result,source='def broken('))


def test_deduplicate_reject_overlaps_and_large_scope():
    t=dict(glyph='A',layer='M1')
    assert len(scripts.targets([t,t]))==1
    with pytest.raises(ProtocolError): scripts.targets([t,dict(t,surface='background')])
    with pytest.raises(ProtocolError): scripts.targets([t]*4097)


def test_runtime_compiles_once_params_and_output_are_bounded():
    opts=scripts.validate_options(dict(options(),source='print("x" * 40000)\ndef run(layer, params, context):\n    layer.append(context["index"])'))
    runner=ScriptRuntime(opts); runner.initialize(); target=[]
    runner.run_target(target,{},0,1)
    assert target==[0] and len(runner.output)<17000 and 'truncated' in runner.output
    with pytest.raises(RuntimeError): runner.initialize()


def test_whole_script_main_guard_runs_once():
    opts=scripts.validate_options(dict(entrypoint='script',targets=[],
        source='if __name__ == "__main__":\n    font.append(params["value"])',params={'value':7}))
    font=[];runtime=ScriptRuntime(opts,font=font);runtime.initialize()
    assert font==[7]
    with pytest.raises(RuntimeError):runtime.initialize()
    assert font==[7]


def start_script(service, **extra):
    return service.edit_workflows.start(service.list_documents()[0]['id'],kind='python_script',idempotency_key='script-test',
                                        options=options(**extra))


def test_native_requires_workflow_but_not_source_review(script_env):
    service,bridge,_=script_env
    with pytest.raises(ServiceError,match='start_edit_workflow'):
        service.start_job('doc',kind='python_script',options=options())
    value=start_script(service)
    value=wait(service,value,'waiting_run')
    assert not bridge.runs and 'scriptReview' not in value
    with pytest.raises(ServiceError): service.apply_job(value['jobId'])
    with pytest.raises(ServiceError): service.run_script(value['jobId'],value['id'])
    action=next(a for a in value['actions'] if a['action']=='run_script')
    args=(value['id'],value['revision'],action['token'])
    service.edit_workflows.respond(*args)
    service.edit_workflows.respond(*args)
    assert len(bridge.runs)==1
    value=wait(service,value,'applied')
    assert any(a['label']=='Restore saved version' for a in value['actions'])


def test_dirty_fonts_reuse_save_choices(script_env):
    service,bridge,_=script_env; bridge.adapter.dirty=True
    value=start_script(service)
    value=wait(service,value,'waiting_run')
    assert not bridge.runs and any(a['action']=='save_run_script' for a in value['actions'])


def test_changed_document_or_report_cannot_run(script_env):
    service,bridge,source=script_env
    value=wait(service,start_script(service),'waiting_run')
    source.write_text('changed')
    action=next(a for a in value['actions'] if a['action']=='run_script')
    result=service.edit_workflows.respond(value['id'],value['revision'],action['token'])
    assert result['state']=='outdated' and not bridge.runs


def test_bulk_selector_and_review_are_immutable(script_env):
    service,bridge,_=script_env
    opts=options();opts['targets']=dict(master='M1',glyphs='all',surface='background')
    value=service.edit_workflows.start(service.list_documents()[0]['id'],kind='python_script',idempotency_key='bulk',options=opts)
    value=wait(service,value,'waiting_run')
    assert value['scope']['targets']==opts['targets']
    value=service.edit_workflows.get(value['id'],include_review=True)
    value['scriptReview']['source']='raise RuntimeError("changed")'
    fresh=service.edit_workflows.get(value['id'],include_review=True)
    assert fresh['scriptReview']['source']==opts['source'] and not bridge.runs
    assert 'review' not in service.get_job(value['jobId'],include_preview=False)['report']


@pytest.mark.parametrize('change',['source','params','targets'])
def test_changed_review_request_rejects_run(script_env,change):
    service,bridge,_=script_env
    value=wait(service,start_script(service),'waiting_run')
    job=service.jobs.get(value['jobId']);request=job['request']
    request['options'][change]={'source':'print("changed")','params':{'delta':4},'targets':[dict(glyph='B',layer='M1')]}[change]
    service.jobs.update(job['id'],request=request)
    action=next(a for a in value['actions'] if a['action']=='run_script')
    result=service.edit_workflows.respond(value['id'],value['revision'],action['token'])
    assert result['error']['code']=='stale_script' and not bridge.runs


def test_reconnect_reconciles_without_replaying(script_env):
    from glyphs_mcp_sidecar.bridge_client import BridgeClientError
    service,bridge,_=script_env
    value=wait(service,start_script(service),'waiting_run')
    actual_run=bridge.run_script
    def disconnected(request):
        actual_run(request)
        raise BridgeClientError('bridge_timeout','lost response',{'execution':'uncertain'})
    bridge.run_script=disconnected
    action=next(a for a in value['actions'] if a['action']=='run_script')
    args=(value['id'],value['revision'],action['token'])
    service.edit_workflows.respond(*args)
    value=wait(service,value,'applied')
    service.edit_workflows.respond(*args)
    assert len(bridge.runs)==1
    service.close()
    restarted=SidecarService(bridge,jobs=JobStore(service.jobs.root),worker=service.worker)
    try:
        restarted.edit_workflows.get(value['id'])
        assert len(bridge.runs)==1
    finally:restarted.close()


def test_oversized_params_and_state_rejected():
    with pytest.raises(ProtocolError):scripts.validate_options(options(params={'big':'a'*scripts.MAX_PARAMS_BYTES}))
    with pytest.raises(ProtocolError):scripts.validate_options(dict(options(), source='a'* (scripts.MAX_SOURCE_BYTES+1)))


def test_unrestricted_ownership_prevents_other_mcp_mutations(script_env):
    service,bridge,_=script_env
    value=wait(service,start_script(service),'waiting_run')
    service.jobs.update(value['jobId'],status='applying')
    with pytest.raises(ServiceError,match='reconcile native'):
        service.start_job(service.list_documents()[0]['id'],kind='width_delta',delta=1,glyphs=['A'])
    assert not bridge.runs


def test_interrupted_preparation_does_not_reserve_live_execution(script_env):
    service,bridge,_=script_env
    value=wait(service,start_script(service),'waiting_run')
    service.jobs.update(value['jobId'],status='interrupted',error={'code':'service_interrupted'})
    from glyphs_mcp_sidecar.script_service import mutation_guard
    assert mutation_guard(lambda service: 'allowed')(service)=='allowed'
    assert not bridge.runs


def test_lost_native_operation_requires_acknowledgement_without_replay(script_env):
    from glyphs_mcp_sidecar.bridge_client import BridgeClientError
    from glyphs_mcp_sidecar.script_service import mutation_guard
    service,bridge,_=script_env
    value=wait(service,start_script(service),'waiting_run')
    action=next(a for a in value['actions'] if a['action']=='run_script')
    service.edit_workflows.respond(value['id'],value['revision'],action['token'])
    value=wait(service,value,'applied')
    def missing(identity):raise BridgeClientError('job_not_found','native operation lost')
    bridge.operation=missing
    value=service.edit_workflows.get(value['id'])
    assert value['state']=='interrupted'
    with pytest.raises(ServiceError):mutation_guard(lambda service:None)(service)
    action=next(a for a in value['actions'] if a['action']=='acknowledge_script_outcome')
    args=(value['id'],value['revision'],action['token'])
    value=service.edit_workflows.respond(*args)
    service.edit_workflows.respond(*args)
    assert value['state']=='executed' and value['job']['outcome']=='unverified'
    assert 'remains unverified' in value['text'] and len(bridge.runs)==1
    assert mutation_guard(lambda service:True)(service)


def test_bridge_rejects_oversize_before_network_dispatch():
    from glyphs_mcp_sidecar.bridge_client import BridgeClient, BridgeClientError
    bridge=BridgeClient('http://127.0.0.1:1','unused')
    with pytest.raises(BridgeClientError) as failure:
        bridge.run_script({'source':'x'*(4*1024*1024)})
    assert failure.value.code=='request_too_large' and 'execution' not in failure.value.details


def test_optional_details_are_immutable_and_polling_is_compact(script_env):
    service,bridge,_=script_env
    value=start_script(service)
    assert scripts.WARNING in value['text']
    value=wait(service,value,'waiting_run')
    assert scripts.WARNING not in value['text'] and 'scriptReview' not in value
    assert 'def run(' not in json.dumps(value)
    assert value['requestFingerprint'] and not bridge.runs
    details=service.edit_workflows.get(value['id'], include_review=True)
    assert details['scriptReview']['source']==options()['source']
    details['scriptReview']['source']='changed'
    assert service.edit_workflows.get(value['id'],include_review=True)['scriptReview']['source']==options()['source']


def test_old_review_is_readable_but_not_executable_after_restart(script_env):
    service,bridge,_=script_env
    value=wait(service,start_script(service),'waiting_run')
    job=service.jobs.get(value['jobId'])
    job['request']['options']['executionMode']='scoped'
    service.jobs.update(job['id'],request=job['request'])
    service.close()
    restarted=SidecarService(bridge,jobs=JobStore(service.jobs.root),worker=service.worker)
    try:
        assert restarted.get_job(job['id'])['error']['code']=='retired_script_review'
        with pytest.raises(ServiceError):restarted.apply_job(job['id'])
        assert not bridge.runs
    finally:restarted.close()


def test_eligible_resolution_and_background_ownership():
    from glyphs_mcp_protocol.script_targets import resolve
    owner=SimpleNamespace(layerId='M1',hasBackground=False)
    glyph=SimpleNamespace(name='A',layers=[owner])
    font=SimpleNamespace(glyphs={'A':glyph},masters=[SimpleNamespace(id='M1')])
    spec=[dict(glyph='A',layer='M1',surface='background')]
    selected,skipped=resolve(font,spec)
    assert not selected and skipped['sample'][0]['reason']=='missing background'
    owner.hasBackground=True;owner.background=SimpleNamespace(shapes=[],anchors=[],hints=[],guides=[],annotations=[])
    selected,skipped=resolve(font,spec)
    assert not selected and skipped['sample'][0]['reason']=='empty background'
    owner.background.shapes=[object()]
    selected,skipped=resolve(font,spec)
    assert selected==[(spec[0],owner.background)] and skipped['count']==0
    with pytest.raises(ValueError,match='layer is unavailable'):
        resolve(font,[dict(glyph='A',layer='background-internal-id',surface='background')])
    with pytest.raises(ValueError,match='master is unavailable'):
        resolve(font,dict(master='missing',glyphs=['A'],surface='foreground'))


def test_no_eligible_callbacks_never_initialize_module():
    from glyphs_mcp_bridge.saved_script import review
    from types import SimpleNamespace
    font=SimpleNamespace(glyphs={'A':SimpleNamespace(layers=[SimpleNamespace(layerId='M1',hasBackground=False)])})
    adapter=SimpleNamespace(_font=lambda _:font,document_state=lambda _:dict(generation=1,path='/font.glyphs'))
    opts=scripts.validate_options(dict(source='raise AssertionError("module ran")',targets=[dict(glyph='A',layer='M1',surface='background')]))
    with pytest.raises(BridgeError,match='no eligible script targets') as error:
        review(SimpleNamespace(adapter=adapter),dict(documentId='doc',generation=1,sourcePath='/font.glyphs',options=opts),BridgeError)
    assert error.value.details['skippedCount']==1


@pytest.mark.parametrize('contents', [dict(backgroundImage=object()), dict(userData={'note':'yes'}),
    dict(attributes={'color':1}), dict(leftMetricsKey='=H'),dict(rightMetricsKey='=H'),dict(widthMetricsKey='=H')])
def test_background_content_is_not_limited_to_paths(contents):
    from glyphs_mcp_protocol.script_targets import resolve
    background=SimpleNamespace(**contents)
    owner=SimpleNamespace(layerId='M1',hasBackground=True,background=background)
    font=SimpleNamespace(glyphs={'A':SimpleNamespace(layers=[owner])})
    selected,skipped=resolve(font,[dict(glyph='A',layer='M1',surface='background')])
    assert len(selected)==1 and selected[0][1] is background and skipped['count']==0


@pytest.mark.parametrize('eligible',[1,4096,4097])
def test_bulk_limit_counts_eligible_surfaces_and_bounds_skips(eligible):
    from glyphs_mcp_protocol.script_targets import resolve
    class Glyphs(dict):
        def __iter__(self):return iter(self.values())
    class EmptyOwner:
        layerId='M1';hasBackground=False
        @property
        def background(self):raise AssertionError('created missing background')
    glyphs=Glyphs()
    for i in range(5000):
        layer=SimpleNamespace(layerId='M1',hasBackground=True,background=SimpleNamespace(shapes=[object()])) if i<eligible else EmptyOwner()
        glyphs[str(i)]=SimpleNamespace(name=str(i),layers=[layer])
    font=SimpleNamespace(glyphs=glyphs,masters=[SimpleNamespace(id='M1')])
    spec=dict(master='M1',glyphs='all',surface='background')
    if eligible>4096:
        with pytest.raises(ProtocolError,match='4,096 eligible'):resolve(font,spec)
    else:
        selected,skipped=resolve(font,spec)
        assert len(selected)==eligible and skipped['count']==5000-eligible
        assert len(skipped['sample'])==10
