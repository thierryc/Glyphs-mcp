"""Native workflow authorization, baseline ownership and recovery."""
from copy import deepcopy
from pathlib import Path
import pytest
import sys
ROOT=Path(__file__).resolve().parents[3]
for part in ("protocol", "bridge", "sidecar"):sys.path.insert(0,str(ROOT/"src"/part))
from glyphs_mcp_protocol import scripts, ProtocolError
from glyphs_mcp_sidecar.service import SidecarService, ServiceError
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.bridge_client import BridgeClientError
from test_simple_v2_edit_workflow import Bridge, wait, choose


class NoWorker:
    def status(self): raise AssertionError('fast route must not need a worker')
    def prepare(self, *args): raise AssertionError('fast route started a worker')


@pytest.fixture
def env(tmp_path):
    source=tmp_path/'Test.glyphs';source.write_text('600')
    bridge=Bridge(source);bridge.runs=[];bridge.restores=[];bridge.reviews=[];bridge.ops={}
    bridge.status=lambda:dict(jobCapabilities=[scripts.NATIVE],writeCapabilities=[])
    def review(request):
        bridge.reviews.append(deepcopy(request));options=request['options']
        return dict(claim='saved version',targetCount=1,skippedCount=0,targets=[],review=options,
            requestHash=scripts.digest(options),manifest=[dict(glyph='A',layer='M1',surface='foreground')])
    bridge.review_script=review
    def run(request):
        assert not bridge.adapter.dirty and source.read_text()=='600'
        bridge.runs.append(request);bridge.adapter.value=620;bridge.adapter.dirty=True
        bridge.ops[request['jobId']]=dict(jobId=request['jobId'],documentId='doc_1',status='applied',error=None,
            scriptResult=dict(executed=True,executionSucceeded=True,changesVerified=False))
        return bridge.ops[request['jobId']]
    bridge.run_script=run
    bridge.operation=lambda identity:deepcopy(bridge.ops[identity])
    def restore(request):
        bridge.restores.append(request);bridge.adapter.value=float(source.read_text());bridge.adapter.dirty=False
        op=bridge.ops[request['jobId']];op['status']='discarded'
        op['scriptResult'].update(savedVersionRestored=True,documentAfter=bridge.documents()[0])
        return deepcopy(op)
    bridge.restore_saved_script=restore
    def finish(identity):
        bridge.ops[identity]['status']='completed';return bridge.ops[identity]
    bridge.finish_script=finish
    service=SidecarService(bridge,jobs=JobStore(tmp_path/'jobs'),worker=NoWorker())
    yield service,bridge,source
    service.close()


def start(service, key='fast', **kwargs):
    return service.edit_workflows.start('doc_1',kind='python_script',idempotency_key=key,mode='preview',options=dict(
        targets=[dict(glyph='A',layer='M1')],source='def run(layer, params, context):\n    layer.width += 20'), **kwargs)


def test_dirty_review_does_not_save_or_execute_and_save_run_is_once(env):
    service,bridge,source=env;bridge.adapter.dirty=True
    value=wait(service,start(service),'waiting_run')
    assert not bridge.runs and not bridge.adapter.save_calls
    assert 'Save and run' in value['text'] and 'scriptReview' not in value
    previous=value;value=choose(service,value,'save_run_script');choose(service,previous,'save_run_script')
    value=wait(service,value,'applied')
    assert len(bridge.runs)==len(bridge.adapter.save_calls)==1
    assert bridge.adapter.dirty and source.read_text()=='600'
    assert not (service.jobs.path(value['jobId'])/'source.glyphs').exists()
    assert value['savedVersion']['available'] and 'all current unsaved edits' in value['text']
    previous=value;value=choose(service,value,'restore_saved_script');choose(service,previous,'restore_saved_script')
    assert value['state']=='discarded' and len(bridge.restores)==1 and bridge.adapter.value==600


def test_pre_review_save_baseline_change_invalidates_restore(env):
    service,bridge,source=env
    value=wait(service,start(service),'waiting_run')
    value=wait(service,choose(service,value,'run_script'),'applied')
    old=value;source.write_text('changed by script or user')
    value=service.edit_workflows.get(value['id'])
    assert not value['savedVersion']['available']
    assert all(a['action']!='restore_saved_script' for a in value['actions'])
    with pytest.raises(ServiceError,match='outdated'):choose(service,old,'restore_saved_script')
    assert not bridge.restores


def test_save_failure_never_runs_script(env):
    service,bridge,source=env;bridge.adapter.dirty=True;value=wait(service,start(service),'waiting_run')
    def fail(request):raise BridgeClientError('native_save_failed','could not save')
    bridge.save=fail
    value=choose(service,value,'save_run_script')
    assert not bridge.runs and source.read_text()=='600'
    assert value['error']['code']=='native_save_failed'


def test_changed_document_is_rejected_before_save(env):
    service,bridge,source=env;value=wait(service,start(service),'waiting_run')
    bridge.adapter.dirty=True
    value=choose(service,value,'run_script')
    assert value['state']=='outdated' and not bridge.adapter.save_calls and not bridge.runs


def test_changed_review_is_rejected_before_save(env):
    service,bridge,source=env;value=wait(service,start(service),'waiting_run')
    job=service.jobs.get(value['jobId']);job['request']['options']['params']={'delta':99}
    service.jobs.update(job['id'],request=job['request'])
    value=choose(service,value,'run_script')
    assert value['error']['code']=='stale_script' and not bridge.adapter.save_calls and not bridge.runs


def test_keep_releases_job_and_ends_restoration_offer(env):
    service,bridge,source=env;value=wait(service,start(service),'waiting_run')
    value=wait(service,choose(service,value,'run_script'),'applied')
    value=choose(service,value,'finish_script')
    assert value['state']=='executed' and value['savedVersion'] is None
    assert source.read_text()=='600' and bridge.adapter.dirty


def test_single_native_route_rejects_retired_fields():
    opts=dict(source='def run(layer, params, context): pass',targets=[dict(glyph='A',layer='M1')])
    assert scripts.validate_options(opts)['entrypoint']=='per_target'
    for field in ({'recovery':'saved_file'}, {'executionMode':'scoped'}, {'executionMode':'unrestricted'}):
        with pytest.raises(ProtocolError, match='retired'):scripts.validate_options(dict(opts, **field))


def test_clean_saved_baseline_never_saves(env):
    service,bridge,_=env
    value=wait(service,start(service),'waiting_run')
    assert [a['label'] for a in value['actions']]==['Run script','Cancel','Wait for my answer']
    value=wait(service,choose(service,value,'run_script'),'applied')
    assert len(bridge.runs)==1 and not bridge.adapter.save_calls


def test_fast_route_requires_its_advertised_capability(env):
    service,bridge,_=env;bridge.status=lambda:dict(jobCapabilities=['script.saved-file.v1'],writeCapabilities=[])
    with pytest.raises(ServiceError,match='runtime update'):start(service)


def test_restore_timeout_reconciles_without_replaying(env):
    service,bridge,_=env;value=wait(service,start(service),'waiting_run')
    value=wait(service,choose(service,value,'run_script'),'applied');original=bridge.restore_saved_script
    def lost(request):
        original(request)
        raise BridgeClientError('bridge_timeout','lost response',{'execution':'uncertain'})
    bridge.restore_saved_script=lost
    old=value;choose(service,value,'restore_saved_script');choose(service,old,'restore_saved_script')
    value=wait(service,old,'discarded')
    assert len(bridge.restores)==1 and len(bridge.runs)==1


def test_uncertain_prerequisite_save_never_becomes_auto_run(env):
    service,bridge,_=env;bridge.adapter.dirty=True;value=wait(service,start(service),'waiting_run')
    actual=bridge.save
    def lost(request):
        actual(request)
        raise BridgeClientError('bridge_timeout','save response lost',{'execution':'uncertain'})
    bridge.save=lost;actual_read=bridge.save_operation
    def missing(identity):raise BridgeClientError('bridge_timeout','save status unavailable')
    bridge.save_operation=missing
    value=choose(service,value,'save_run_script')
    assert value['state']=='uncertain' and not bridge.runs
    value=service.edit_workflows.get(value['id'])
    assert value['state']=='uncertain' and all(a['action']!='save_run_script' for a in value['actions'])
    bridge.save_operation=actual_read
    value=choose(service,value,'check_outcome')
    assert value['state']=='outdated' and not bridge.runs and len(bridge.adapter.save_calls)==1


def test_native_save_rechecks_reviewed_generation_before_writing(env):
    service,bridge,_=env;bridge.adapter.dirty=True;value=wait(service,start(service),'waiting_run')
    actual=bridge.save
    def intervening(request):
        bridge.adapter.document_state=lambda _:dict(bridge.documents()[0],generation=2)
        return actual(request)
    bridge.save=intervening
    value=choose(service,value,'save_run_script')
    assert value['state']=='outdated' and not bridge.runs and not bridge.adapter.save_calls


def test_native_restore_rejects_changed_file_before_loading(env):
    service,bridge,source=env
    from glyphs_mcp_bridge.saved_script import restore
    from glyphs_mcp_bridge.core import BridgeError
    from glyphs_mcp_protocol.source_identity import source_hash
    from types import SimpleNamespace
    baseline=source_hash(source)
    op=dict(jobId='job',documentId='doc_1',status='applied',scriptRequest=dict(options=dict(),sourcePath=str(source),sourceHash=baseline),scriptResult={'executed':True})
    core=SimpleNamespace(_operations={'job':op},adapter=bridge.adapter,_check_owner=lambda *a,**kw:None)
    source.write_text('overwritten')
    with pytest.raises(BridgeError,match='saved file has changed'):restore(core,dict(jobId='job',sourceHash=baseline,generation=1),BridgeError)
    assert 'restoreRequest' not in op


def test_manual_save_revalidates_without_wrapper_save(env):
    service,bridge,source=env;bridge.adapter.dirty=True
    value=wait(service,start(service),'waiting_run')
    value=choose(service,value,'manual_save')
    assert value['state']=='waiting_manual' and not bridge.runs and not bridge.adapter.save_calls
    bridge.adapter.dirty=False  # The fixture's on-disk contents already match.
    value=wait(service,choose(service,value,'check_continue'),'waiting_run')
    assert len(bridge.reviews)==2 and not bridge.runs
    wait(service,choose(service,value,'run_script'),'applied')
    assert not bridge.adapter.save_calls and len(bridge.runs)==1


def test_partial_failure_can_keep_without_restoring_or_rerunning(env):
    service,bridge,_=env
    value=wait(service,start(service),'waiting_run')
    value=wait(service,choose(service,value,'run_script'),'applied')
    identity=value['jobId'];bridge.ops[identity]['status']='failed'
    bridge.ops[identity]['error']={'code':'script_failed','message':'partial failure'}
    value=service.edit_workflows.get(value['id'])
    assert value['state']=='failed' and 'Partial edits' in value['text']
    value=choose(service,value,'finish_script')
    assert value['state']=='executed' and value['savedVersion'] is None
    assert len(bridge.runs)==1 and not bridge.restores and bridge.adapter.dirty


def test_closed_document_has_no_restore_action(env):
    service,bridge,_=env
    value=wait(service,start(service),'waiting_run')
    value=wait(service,choose(service,value,'run_script'),'applied')
    bridge.adapter.closed=True
    value=service.edit_workflows.get(value['id'])
    assert not value['savedVersion']['available']
    assert all(a['action']!='restore_saved_script' for a in value['actions'])
    assert not bridge.restores


def test_new_document_save_as_never_overwrites_and_does_not_auto_run(env,tmp_path):
    service,bridge,source=env
    bridge.adapter.path=None;bridge.adapter.dirty=True
    value=start(service)
    assert value['state']=='waiting_save' and not bridge.reviews and not bridge.runs
    value=choose(service,value,'save_as_continue',destination=str(source))
    assert value['error']['code']=='destination_exists' and not bridge.runs and not bridge.adapter.save_calls
    target=tmp_path/'New.glyphs'
    value=choose(service,value,'save_as_continue',destination=str(target))
    value=wait(service,value,'waiting_run')
    assert value['document']['path']==str(target) and len(bridge.adapter.save_calls)==1 and not bridge.runs
    value=wait(service,choose(service,value,'run_script'),'applied')
    assert len(bridge.adapter.save_calls)==1 and len(bridge.runs)==1


@pytest.mark.parametrize('resolution', ['finish_script','restore_saved_script','save_result'])
def test_script_blocker_resolves_without_typed_undo(env, resolution):
    service,bridge,source=env
    a=wait(service,start(service),'waiting_run')
    a=wait(service,choose(service,a,'run_script'),'applied')
    if resolution=='save_result':
        # Acceptance is covered by real native tests; isolate blocker settlement.
        def accept(identity,**kw):
            bridge.ops[identity]['status']='accepted';bridge.adapter.dirty=False
            return service._public(service.jobs.update(identity,status='accepted'))
        service.accept_job=accept
    b=wait(service,start(service,'second'),'blocked_review')
    assert b['blockingWorkflowId']==a['id']
    assert a['id'] in b['modelContext'] and 'Undo earlier' not in b['text']
    assert 'Completed callbacks' not in b['text'] and 'bridgeOperation' not in b['job']
    assert {x['action'] for x in b['actions']}=={'check_continue','cancel'}
    old=a;choose(service,a,resolution);choose(service,old,resolution)
    b=wait(service,b,'waiting_run')
    assert not b['blockerId'] and not b['blockingWorkflowId'] and len(bridge.runs)==1
    assert b['document']['dirty']==(resolution=='finish_script')


def test_waiting_task_uses_only_restoration_binding(env):
    service,bridge,_=env
    a=wait(service,start(service),'waiting_run');a=wait(service,choose(service,a,'run_script'),'applied')
    b=wait(service,start(service,'next'),'blocked_review')
    original=bridge.restore_saved_script
    def restore(request):
        op=original(request)
        documents=bridge.documents
        bridge.documents=lambda:[dict(doc,id='doc_restored') for doc in documents()]
        op['scriptResult']['documentAfter']=bridge.documents()[0]
        bridge.ops[request['jobId']]=deepcopy(op)
        return op
    bridge.restore_saved_script=restore
    choose(service,a,'restore_saved_script')
    b=wait(service,b,'waiting_run')
    assert b['document']['id']=='doc_restored'
    assert bridge.reviews[-1]['documentId']=='doc_restored'


@pytest.mark.parametrize('status',['failed','cancelled'])
def test_partial_script_blocks_next_task_until_keep(env,status):
    service,bridge,_=env
    a=wait(service,start(service),'waiting_run');a=wait(service,choose(service,a,'run_script'),'applied')
    bridge.ops[a['jobId']]['status']=status
    a=service.edit_workflows.get(a['id'])
    assert a['state']==status
    b=wait(service,start(service,'after-partial'),'blocked_review')
    assert b['blockingWorkflowId']==a['id'] and len(bridge.reviews)==1
    choose(service,a,'finish_script')
    wait(service,b,'waiting_run')
    assert len(bridge.runs)==1


def test_completed_blocker_reconciles_after_restart(env):
    service,bridge,_=env
    a=wait(service,start(service),'waiting_run');a=wait(service,choose(service,a,'run_script'),'applied')
    b=wait(service,start(service,'after-restart'),'blocked_review')
    service.close()
    # Keep completed natively before the connection returned its response.
    bridge.finish_script(a['jobId'])
    restarted=SidecarService(bridge,jobs=JobStore(service.jobs.root),worker=NoWorker())
    try:
        b=wait(restarted,b,'waiting_run')
        assert len(bridge.runs)==1 and b['blockingWorkflowId'] is None
    finally:restarted.close()


def test_ready_script_read_does_not_wait_for_tick_or_execute(env,monkeypatch):
    import time
    service,bridge,_=env
    monkeypatch.setattr(service.edit_workflows,'_start_runner',lambda:None)
    value=start(service)
    deadline=time.monotonic()+5
    while service.jobs.get(value['jobId'])['status']!='ready':
        assert time.monotonic()<deadline
        time.sleep(.005)
    assert service.edit_workflows.get(value['id'])['state']=='waiting_run'
    assert not bridge.runs and not bridge.adapter.save_calls


def test_presentation_hash_memo_expiry_invalidation_and_restart(env,monkeypatch):
    from glyphs_mcp_sidecar import saved_script
    service,bridge,_=env
    a=wait(service,start(service),'waiting_run');a=wait(service,choose(service,a,'run_script'),'applied')
    calls=[];actual=saved_script.source_hash;clock=[10.0]
    monkeypatch.setattr(saved_script,'source_hash',lambda p:(calls.append(str(p)),actual(p))[1])
    monkeypatch.setattr(saved_script.time,'monotonic',lambda:clock[0])
    saved_script.invalidate(service)
    for _ in range(10):service.edit_workflows.get(a['id'])
    assert len(calls)==1
    clock[0]+=5
    service.edit_workflows.get(a['id']);assert len(calls)==2
    saved_script.invalidate(service,'doc_1')
    service.edit_workflows.get(a['id']);assert len(calls)==3
    choose(service,service.edit_workflows.get(a['id']),'finish_script')
    assert not service.edit_workflows.baseline_memos


def test_running_script_cancel_survives_progress_but_not_completion(env):
    service,bridge,_=env
    value=wait(service,start(service),'waiting_run')
    workflows=service.edit_workflows
    workflows.close()
    value=choose(service,value,'run_script')
    op=bridge.ops[value['jobId']];op['status']='applying'
    op['scriptResult'].update(executedTargets=1,totalTargets=100)
    def poll():
        workflows._advance(workflows._find(value['id']), allow_apply=False)
        return workflows.get(value['id'])
    value=poll();old=value
    for count in range(2,12):
        op['scriptResult']['executedTargets']=count
        value=poll()
        assert value['revision']==old['revision']
        assert value['actions']==old['actions']
    calls=[]
    def cancel(identity):
        calls.append(identity);op['status']='cancelled';return deepcopy(op)
    bridge.discard=cancel
    choose(service,old,'cancel')
    choose(service,old,'cancel')
    assert calls==[old['jobId']]
    done=poll()
    assert done['state']=='cancelled' and done['revision']>old['revision']


def test_running_script_cancel_invalidated_by_completion(env):
    service,bridge,_=env
    value=wait(service,start(service),'waiting_run');service.edit_workflows.close()
    value=choose(service,value,'run_script');op=bridge.ops[value['jobId']];op['status']='applying'
    old=service.edit_workflows.get(value['id'])
    op['status']='applied'
    service.edit_workflows._advance(service.edit_workflows._find(value['id']), allow_apply=False)
    value=service.edit_workflows.get(value['id'])
    assert value['revision']>old['revision']
    with pytest.raises(ServiceError,match='outdated'):choose(service,old,'cancel')


def test_auto_keep_only_offered_after_success_and_polling_never_keeps(env):
    service,bridge,source=env
    value=wait(service,start(service),'waiting_run')
    assert value['autoKeep']==dict(enabled=True,delaySeconds=30,action=None)
    token=next(a['token'] for a in value['actions'] if a['action']=='run_script')
    with pytest.raises(ServiceError,match='only available for Keep'):
        service.edit_workflows.respond(value['id'],value['revision'],token,automatic=True)
    assert not bridge.runs
    value=wait(service,choose(service,value,'run_script'),'applied')
    assert value['autoKeep']['action']=='finish_script'
    for _ in range(10):
        value=service.edit_workflows.get(value['id'])
        assert value['state']=='applied'
    token=next(a['token'] for a in value['actions'] if a['action']=='finish_script')
    result=service.edit_workflows.respond(value['id'],value['revision'],token,automatic=True)
    assert result['state']=='executed' and result['responseOrigin']=='card_timeout'
    assert result['savedVersion'] is None and source.read_text()=='600' and bridge.adapter.dirty
    assert service.edit_workflows.respond(value['id'],value['revision'],token,automatic=True)['state']=='executed'
    assert len(bridge.runs)==1 and not bridge.adapter.save_calls and not bridge.restores


def test_wait_for_answer_disables_across_reads_restart_and_old_card(env):
    from glyphs_mcp_sidecar.edit_workflow import EditWorkflows
    service,bridge,_=env
    value=wait(service,start(service),'waiting_run')
    value=wait(service,choose(service,value,'run_script'),'applied')
    old=deepcopy(value)
    value=choose(service,value,'wait_for_answer')
    assert value['state']=='applied' and value['autoKeep']['enabled'] is False
    assert value['savedVersion']['available']
    with pytest.raises(ServiceError,match='outdated'):
        service.edit_workflows.respond(old['id'],old['revision'],next(a['token'] for a in old['actions'] if a['action']=='finish_script'),automatic=True)
    service.edit_workflows.close()
    service._edit_workflows=EditWorkflows(service,ServiceError)
    value=choose(service,service.edit_workflows.get(value['id']),'check_outcome')
    assert value['state']=='applied' and value['autoKeep']['enabled'] is False
    token=next(a['token'] for a in value['actions'] if a['action']=='finish_script')
    with pytest.raises(ServiceError,match='only available for Keep'):
        service.edit_workflows.respond(value['id'],value['revision'],token,automatic=True)
    assert len(bridge.runs)==1


def test_auto_keep_explicit_opt_out_and_original_idempotency(env):
    service,bridge,_=env
    value=wait(service,start(service,auto_keep=False),'waiting_run')
    assert value['autoKeep']['enabled'] is False
    assert all(a['action']!='wait_for_answer' for a in value['actions'])
    with pytest.raises(ServiceError,match='another edit request'):
        start(service,auto_keep=True)
    value=wait(service,choose(service,value,'run_script'),'applied')
    assert value['autoKeep']['action'] is None
    assert 'Automatic Keep is off' in value['text']


@pytest.mark.parametrize('status',['failed','cancelled','interrupted'])
def test_partial_or_unknown_outcome_never_auto_keeps(env,status):
    service,bridge,_=env
    value=wait(service,start(service),'waiting_run')
    value=wait(service,choose(service,value,'run_script'),'applied')
    op=bridge.ops[value['jobId']];op['status']=status
    op['scriptResult']['executionSucceeded']=False
    service.jobs.update(value['jobId'],status=status,bridgeOperation=op)
    record=service.edit_workflows.store.records[value['id']]
    service.edit_workflows._set(record,state=status,job=service.get_job(value['jobId']))
    value=service.edit_workflows.get(value['id'])
    assert value['autoKeep']['action'] is None
    assert len(bridge.runs)==1


def test_existing_records_never_gain_auto_keep(env):
    service,_,_=env
    value=wait(service,start(service),'waiting_run')
    value=wait(service,choose(service,value,'run_script'),'applied')
    record=service.edit_workflows.store.records[value['id']]
    record.pop('autoKeepEnabled');record.pop('autoKeepRequested')
    assert service.edit_workflows.get(value['id'])['autoKeep']['action'] is None
    assert start(service)['autoKeep']['enabled'] is False


def test_result_wording_uses_fresh_document_not_execution_snapshot(env):
    service, bridge, source = env
    value=wait(service,start(service),'waiting_run')
    value=wait(service,choose(service,value,'run_script'),'applied')
    bridge.ops[value['jobId']]['scriptResult']['documentAfter']={'dirty':True}
    bridge.adapter.dirty=False  # Simulate a later editor save.
    value=service.edit_workflows.get(value['id'])
    assert 'currently saved' in value['message'] and 'has unsaved edits' not in value['message']
    bridge.adapter.closed=True
    value=service.edit_workflows.get(value['id'])
    assert 'could not be confirmed' in value['message']
