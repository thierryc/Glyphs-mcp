"""Milestone 4: polling work scales with active jobs, preserving durable evidence."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from test_simple_v2_edit_workflow import env, start, wait, choose
from glyphs_mcp_sidecar import jobs as job_module
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.lifecycle import ServiceLifecycle
from glyphs_mcp_sidecar.edit_workflow_state import WorkflowStore


def seed_history(store, count):
    for index in range(count):
        record = store.create(dict(id='history-doc',path='/history.glyphs'),
                              dict(kind='width_delta',glyphs=['A'],delta=1))
        store.update(record['id'],status='completed',resultKind='mutation',
                     sample=[dict(before=500,after=501)],summary='Historical evidence')


@pytest.mark.parametrize('count', [0, 100, 1000, 10000])
@pytest.mark.parametrize('active', [False, True])
def test_activity_poll_copies_only_bounded_recent_and_active_records(tmp_path, monkeypatch, count, active):
    store = JobStore(tmp_path/'jobs')
    seed_history(store,count)
    current = store.create(dict(id='live-doc'),dict(kind='width_delta')) if active else None
    touched = []
    original = job_module.copy.deepcopy
    def copy(value, *args, **kwargs):
        if isinstance(value,list):
            touched.extend(item['id'] for item in value if isinstance(item,dict) and 'id' in item)
        elif isinstance(value,dict) and 'id' in value:
            touched.append(value['id'])
        return original(value,*args,**kwargs)
    monkeypatch.setattr(job_module.copy,'deepcopy',copy)
    owner = SimpleNamespace(jobs=store)
    result = ServiceLifecycle(owner,RuntimeError).snapshot()
    assert result['activeCount'] == int(active)
    assert len(result['jobs']) == min(count+int(active),5)
    if active: assert result['jobs'][0]['jobId'] == current['id']
    assert len(touched) <= 11, (count,len(touched))


def test_unchanged_job_poll_does_not_write_or_change_timestamps(env, monkeypatch):
    service, _, _, _ = env
    workflow = wait(service,start(env,auto_keep=False),'applied')
    service.get_job(workflow['jobId'])  # Establish optional fields on old evidence.
    before = service.jobs.get(workflow['jobId'])
    writes = []
    write = service.jobs.write_json
    def measured(*args):
        writes.append(args[1]); return write(*args)
    monkeypatch.setattr(service.jobs,'write_json',measured)
    for _ in range(10): service.get_job(workflow['jobId'])
    assert writes == []
    assert service.jobs.get(workflow['jobId']) == before


def test_real_progress_and_uncertainty_remain_durable(tmp_path):
    store = JobStore(tmp_path/'jobs')
    job = store.create(dict(id='doc'),dict(kind='width_delta'))
    first = store.update(job['id'],status='applying',bridgeOperation=dict(status='applying',completedChanges=1))
    second = store.update(job['id'],bridgeOperation=dict(status='applying',completedChanges=2))
    assert second['updatedAt'] > first['updatedAt']
    assert second['phaseStartedAt'] == first['phaseStartedAt']
    error = dict(code='bridge_timeout',details=dict(execution='uncertain'))
    third = store.update(job['id'],error=error)
    assert JobStore(store.root).get(job['id']) == third


def test_workflow_supervisor_does_not_enumerate_completed_history(env):
    service, _, _, _ = env
    flows = service.edit_workflows
    # Seed through persistence so the same path also builds the volatile index.
    for index in range(100):
        value = flows.store.create(dict(id='old-doc'),dict(),dict(kind='width_delta'),
                                   'apply','history-'+str(index))
        flows.store.update(value,state='executed')
    active = flows.store.create(dict(id='live-doc'),dict(),dict(kind='width_delta'),
                               'apply','active')
    flows.store.update(active,state='preparing')
    class NoHistoryScan(dict):
        def values(self): raise AssertionError('supervisor must not enumerate completed history')
    flows.store.records = NoHistoryScan(flows.store.records)
    class OneTick:
        def __init__(self): self.count=0
        def wait(self,_): self.count+=1; return self.count>1
        def is_set(self): return False
        def set(self): pass
    flows.stopped = OneTick()
    advanced=[]
    flows._advance=lambda value: advanced.append(value['id'])
    flows._run()
    assert advanced == [active['id']]


def test_keep_duplicate_and_reconnect_rebuild_indexes_with_waiting_job(env):
    service,bridge,worker,_=env
    first=wait(service,start(env,auto_keep=False),'applied')
    next_job=service.edit_workflows.start('doc_1',kind='width_delta',delta=8,idempotency_key='next',auto_keep=False)
    assert next_job['blockingWorkflowId']==first['id']
    original=deepcopy(first)
    assert choose(service,first,'finish_edit')['state']=='executed'
    assert choose(service,original,'finish_edit')['state']=='executed'
    assert wait(service,next_job,'waiting_save')['blockerId'] is None
    root=service.jobs.root
    service.close()
    from glyphs_mcp_sidecar.service import SidecarService
    restarted=SidecarService(bridge,jobs=JobStore(root),worker=worker)
    try:
        assert restarted.edit_workflows.get(first['id'])['state']=='executed'
        assert restarted.edit_workflows.get(next_job['id'])['state']=='interrupted'
        assert bridge.applies==1 and not bridge.adapter.save_calls
    finally: restarted.close()


@pytest.mark.parametrize('status', ['failed', 'cancelled'])
def test_executed_failures_remain_in_working_set_until_settled(tmp_path, status):
    store = JobStore(tmp_path/'jobs')
    job = store.create(dict(id='doc'), dict(kind='python_script'))
    store.update(job['id'], status=status, resultKind='script',
                 bridgeOperation=dict(scriptResult=dict(executed=True)))
    other = store.create(dict(id='elsewhere'), dict(kind='python_script'))
    store.update(other['id'], status=status, resultKind='script',
                 bridgeOperation=dict(scriptResult=dict(executed=False)))
    for current in (store, JobStore(store.root)):
        assert [j['id'] for j in current.select(set(), include_unresolved=True)] == [job['id']]
        assert current.select(set(), document_id='elsewhere', include_unresolved=True) == []
    current.update(job['id'], status='completed')
    assert current.select(set(), include_unresolved=True) == []
    assert JobStore(store.root).select(set(), include_unresolved=True) == []


def test_job_update_distinguishes_missing_from_explicit_empty_and_survives_failed_write(tmp_path, monkeypatch):
    store = JobStore(tmp_path/'jobs')
    job = store.create(dict(id='doc'), dict(kind='width_delta'))
    changed = store.update(job['id'], receipt=None)
    assert 'receipt' in changed and changed['updatedAt'] > job['updatedAt']
    assert store.update(job['id'], receipt=None) == changed
    def fail(*args): raise OSError('disk full')
    monkeypatch.setattr(store, 'write_json', fail)
    with pytest.raises(OSError): store.update(job['id'], status='completed')
    assert store.count({'preparing'}) == 1 and store.count({'completed'}) == 0
    assert store.get(job['id']) == changed


def test_workflow_index_tracks_fresh_binding_and_failed_script_on_restart(tmp_path):
    store = WorkflowStore(tmp_path)
    value = store.create(dict(id='old'), {}, dict(kind='python_script'), 'apply', 'request')
    job = dict(id='job_1', status='failed', resultKind='script',
               bridgeOperation=dict(scriptResult=dict(executed=True)))
    store.update(value, state='failed', jobId='job_1', job=job)
    for current in (store, WorkflowStore(tmp_path)):
        record = current.matching_key('request')
        assert current.matching_job('job_1') is record
        assert current.peers('old') == [record]
        assert current.active_records() == []  # Manual inspection, never automatic replay.
        current.update(record, document=dict(id='fresh'), state='preparing', job=None)
        assert current.peers('old') == [] and current.peers('fresh') == [record]
        assert current.active_records() == [record]
        current.update(record, state='discarded')
        assert current.peers('fresh') == [] and current.active_records() == []
