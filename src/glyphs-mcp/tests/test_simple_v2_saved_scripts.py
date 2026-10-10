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
    bridge=Bridge(source);bridge.runs=[];bridge.restores=[];bridge.reviews=[];bridge.ops={};bridge.snapshots={}
    bridge.status=lambda:dict(jobCapabilities=[scripts.NATIVE, scripts.SNAPSHOT],scriptPreparationVersion=scripts.PREPARATION_VERSION,writeCapabilities=[])
    def review(request):
        bridge.reviews.append(deepcopy(request));options=request['options']
        bridge.review_report=dict(claim='saved version',targetCount=1,skippedCount=0,targets=[],review=options,
            requestHash=scripts.digest(options),manifest=[dict(glyph='A',layer='M1',surface='foreground')])
        return dict(status='ready',jobId=request['jobId'])
    bridge.review_script=review
    bridge.reviewed_script=lambda identity:deepcopy(bridge.review_report)
    def run(request):
        before=(bridge.adapter.value, bridge.adapter.dirty)
        bridge.snapshots[request['jobId']]=before
        bridge.runs.append(request);bridge.adapter.value=620;bridge.adapter.dirty=True
        bridge.ops[request['jobId']]=dict(jobId=request['jobId'],documentId='doc_1',status='applied',error=None,
            scriptResult=dict(executed=True,executionSucceeded=True,changesVerified=False,
                recovery=dict(kind='memory_snapshot',snapshotId='snapshot_'+request['jobId'],available=True)))
        return bridge.ops[request['jobId']]
    bridge.run_script=run
    bridge.operation=lambda identity:deepcopy(bridge.ops[identity])
    def restore(request):
        bridge.restores.append(request);bridge.adapter.value,bridge.adapter.dirty=bridge.snapshots[request['jobId']]
        op=bridge.ops[request['jobId']];op['status']='discarded'
        op['scriptResult'].update(beforeRunRestored=True,documentAfter=bridge.documents()[0])
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


def authorized(service, key='authorized'):
    return service.edit_workflows.start('doc_1', kind='python_script', idempotency_key=key,
        mode='apply', auto_keep=False, options=dict(targets=[dict(glyph='A', layer='M1')],
            source='def run(layer, params, context):\n    layer.width += 20'))


def test_authorized_apply_runs_once_without_save_and_retains_recovery(env):
    service, bridge, source = env
    bridge.adapter.dirty = True; bridge.adapter.value = 610
    value = wait(service, authorized(service), 'applied')
    assert len(bridge.runs) == 1 and not bridge.adapter.save_calls
    assert value['savedVersion']['available'] and source.read_text() == '600'
    assert authorized(service)['id'] == value['id']
    for _ in range(3): service.edit_workflows.get(value['id'])
    assert len(bridge.runs) == 1
    value = choose(service, value, 'restore_saved_script')
    assert value['state'] == 'discarded' and bridge.adapter.value == 610 and bridge.adapter.dirty


def test_apply_poll_does_not_execute_or_disable_the_authorized_runner(env, monkeypatch):
    import time
    service, bridge, _ = env
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    value = authorized(service)
    deadline = time.monotonic() + 5
    while service.jobs.get(value['jobId'])['status'] != 'ready':
        assert time.monotonic() < deadline; time.sleep(.01)
    value = service.edit_workflows.get(value['id'])
    assert value['state'] == 'preparing' and not bridge.runs
    service.edit_workflows._advance(service.edit_workflows.store.records[value['id']])
    service.edit_workflows._advance(service.edit_workflows.store.records[value['id']], allow_apply=False)
    value = wait(service, value, 'applied')
    assert len(bridge.runs) == 1 and not bridge.adapter.save_calls


def test_authorized_apply_rejects_stale_state_without_running(env, monkeypatch):
    import time
    service, bridge, _ = env
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    value = authorized(service)
    deadline = time.monotonic() + 5
    while service.jobs.get(value['jobId'])['status'] != 'ready':
        assert time.monotonic() < deadline; time.sleep(.01)
    bridge.adapter.dirty = True
    record = service.edit_workflows.store.records[value['id']]
    service.edit_workflows._guard(record, lambda: service.edit_workflows._advance(record))
    assert record['state'] == 'outdated' and not record['scriptRunAuthorized']
    assert not bridge.runs and not bridge.adapter.save_calls


def test_authorized_apply_lost_response_never_replays(env):
    service, bridge, _ = env
    actual = bridge.run_script
    def lose(request):
        actual(request)
        raise BridgeClientError('bridge_timeout', 'lost response', {'execution': 'uncertain'})
    bridge.run_script = lose
    # A lost response is reconciled from the retained native operation; it may
    # settle before a client observes the transient uncertain state.
    value = wait(service, authorized(service), 'applied')
    for _ in range(3): value = service.edit_workflows.get(value['id'])
    assert len(bridge.runs) == 1 and not bridge.adapter.save_calls
    assert not service.edit_workflows.store.records[value['id']]['scriptRunAuthorized']


def test_sidecar_restart_does_not_execute_retained_apply_authorization(env, monkeypatch):
    import time
    service, bridge, _ = env
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    value = authorized(service)
    deadline = time.monotonic() + 5
    while service.jobs.get(value['jobId'])['status'] != 'ready':
        assert time.monotonic() < deadline; time.sleep(.01)
    service.close()
    restarted = SidecarService(bridge, jobs=JobStore(service.jobs.root), worker=NoWorker())
    try:
        record = restarted.edit_workflows.store.records[value['id']]
        assert record['state'] == 'interrupted' and not record['scriptRunAuthorized']
        restarted.edit_workflows._advance(record, allow_apply=False)
        assert record['state'] == 'waiting_run' and not bridge.runs
    finally: restarted.close()


def test_legacy_apply_record_never_gains_automatic_run_permission(env, monkeypatch):
    service, bridge, _ = env
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    value = wait(service, start(service), 'waiting_run')
    record = service.edit_workflows.store.records[value['id']]
    record['mode'] = 'apply'; record.pop('scriptRunAuthorized', None)
    service.edit_workflows._advance(record)
    assert record['state'] == 'waiting_run' and not bridge.runs


def test_dirty_review_and_run_preserve_preexisting_unsaved_changes(env):
    service,bridge,source=env;bridge.adapter.dirty=True;bridge.adapter.value=610
    value=wait(service,start(service),'waiting_run')
    assert not bridge.runs and not bridge.adapter.save_calls
    assert 'Save and run' not in value['text']
    previous=value;value=choose(service,value,'run_script');choose(service,previous,'run_script')
    value=wait(service,value,'applied')
    assert len(bridge.runs)==1 and not bridge.adapter.save_calls and source.read_text()=='600'
    assert value['savedVersion']['available'] and value['savedVersion']['kind']=='memory_snapshot'
    previous=value;value=choose(service,value,'restore_saved_script');choose(service,previous,'restore_saved_script')
    assert value['state']=='discarded' and len(bridge.restores)==1 and bridge.adapter.value==610 and bridge.adapter.dirty

def test_external_file_change_does_not_destroy_memory_snapshot(env):
    service,bridge,source=env
    value=wait(service,start(service),'waiting_run')
    value=wait(service,choose(service,value,'run_script'),'applied')
    source.write_text('external change')
    value=service.edit_workflows.get(value['id'])
    assert value['savedVersion']['available']
    assert any(a['label']=='Restore before run' for a in value['actions'])
    assert not bridge.adapter.save_calls

def test_run_never_calls_save_even_if_save_would_fail(env):
    service,bridge,source=env;bridge.adapter.dirty=True;value=wait(service,start(service),'waiting_run')
    bridge.save=lambda _: (_ for _ in ()).throw(AssertionError('unexpected Save'))
    value=wait(service,choose(service,value,'run_script'),'applied')
    assert len(bridge.runs)==1 and source.read_text()=='600'

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


def test_obsolete_save_and_run_action_is_not_offered(env):
    service,bridge,_=env;bridge.adapter.dirty=True;value=wait(service,start(service),'waiting_run')
    assert not any(a['action'] in {'save_run_script','manual_save'} for a in value['actions'])
    assert not bridge.adapter.save_calls and not bridge.runs

def test_changed_generation_blocks_run_without_save(env):
    service,bridge,_=env;value=wait(service,start(service),'waiting_run')
    original=bridge.documents
    bridge.documents=lambda:[dict(original()[0],generation=2)]
    value=choose(service,value,'run_script')
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


def test_dirty_font_can_keep_and_run_a_second_script_without_saving(env):
    service,bridge,_=env;bridge.adapter.dirty=True
    value=wait(service,start(service),'waiting_run')
    value=wait(service,choose(service,value,'run_script'),'applied')
    choose(service,value,'finish_script')
    value=wait(service,start(service,key='second'),'waiting_run')
    wait(service,choose(service,value,'run_script'),'applied')
    assert len(bridge.runs)==2 and not bridge.adapter.save_calls

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


def test_pathless_dirty_font_runs_without_save_as(env,tmp_path):
    service,bridge,source=env;bridge.adapter.path=None;bridge.adapter.dirty=True
    value=wait(service,start(service),'waiting_run')
    assert value['document']['path'] is None and not bridge.adapter.save_calls
    value=wait(service,choose(service,value,'run_script'),'applied')
    assert any(a['action']=='save_result_as' for a in value['actions'])
    value=choose(service,value,'restore_saved_script')
    assert value['document']['path'] is None and bridge.adapter.dirty and not bridge.adapter.save_calls

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
    bridge.ops[a['jobId']]['scriptResult'].pop('recovery')  # Historical disk-recovery records remain readable.
    service.jobs.update(a['jobId'],sourceHash=saved_script.source_hash(service.jobs.get(a['jobId'])['document']['path']))
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


def test_imported_font_can_run_and_offers_separate_save_as(env):
    service,bridge,_=env;bridge.adapter.path='/disposable.ttf';bridge.adapter.dirty=True
    value=wait(service,start(service),'waiting_run')
    value=wait(service,choose(service,value,'run_script'),'applied')
    actions={a['action'] for a in value['actions']}
    assert 'save_result_as' in actions and 'save_result' not in actions and not bridge.adapter.save_calls
