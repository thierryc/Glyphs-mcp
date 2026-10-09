"""Keep is an idempotent lifecycle action, never a save or rollback bypass."""
from copy import deepcopy
import pytest
from test_simple_v2_edit_workflow import env, start, wait, choose
from glyphs_mcp_sidecar.edit_workflow_state import WorkflowStore, auto_keep_available
from glyphs_mcp_sidecar.service import SidecarService, ServiceError
from glyphs_mcp_bridge.core import BridgeError


def test_keep_releases_waiter_without_save_and_survives_reconnect(env):
    service, bridge, worker, source = env
    first = wait(service, start(env), 'applied')
    second = service.edit_workflows.start('doc_1', kind='width_delta', delta=8, idempotency_key='second')
    assert second['state'] == 'blocked_review'
    assert second['blockingWorkflowId'] == first['id']
    original = deepcopy(first)
    finished = choose(service, first, 'finish_edit')
    assert finished['state'] == 'executed'
    assert choose(service, original, 'finish_edit')['state'] == 'executed'
    assert bridge.adapter.value == 608 and bridge.adapter.dirty
    assert source.read_text() == '600' and bridge.adapter.save_calls == []
    assert not bridge.core._operations[first['jobId']]['resolved']
    assert {p.name for p in service.jobs.path(first['jobId']).iterdir()} == {'state.json'}
    assert wait(service, second, 'waiting_save')['blockerId'] is None
    with pytest.raises(ServiceError):
        service.discard_job(first['jobId'])
    service.close()
    again = SidecarService(bridge, jobs=service.jobs, worker=worker)
    try:
        assert again.edit_workflows.get(first['id'])['state'] == 'executed'
    finally:
        again.close()


def test_keep_direct_job_from_waiting_workflow(env):
    service, bridge, _, _ = env
    direct = service.start_job('doc_1', kind='width_delta', delta=8)
    import time
    for _ in range(200):
        if service.get_job(direct['id'])['status'] == 'ready': break
        time.sleep(.01)
    service.apply_job(direct['id'])
    waiter = start(env)
    assert waiter['state'] == 'blocked_review' and waiter['blockingWorkflowId'] is None
    waiter = choose(service, waiter, 'keep_previous')
    assert wait(service, waiter, 'waiting_save')['blockerId'] is None
    assert not bridge.adapter.save_calls


def test_reconciled_keep_releases_temporary_files_and_retains_evidence(env):
    service, bridge, _, _ = env
    value = wait(service, start(env), 'applied')
    job_id = value['jobId']
    assert (service.jobs.path(job_id)/'patch.json').exists()
    bridge.core.finish_edit(job_id)  # Native completion, sidecar response was lost.
    assert service.edit_workflows.get(value['id'])['state'] == 'executed'
    assert {p.name for p in service.jobs.path(job_id).iterdir()} == {'state.json'}
    retained = service.jobs.get(job_id)
    assert retained['request']['kind'] == 'width_delta' and retained['changeCount'] == 1
    assert retained['sample'][0]['after'] == 608
    assert not bridge.adapter.save_calls


def test_typed_automatic_keep_and_opt_out(env):
    service, bridge, _, _ = env
    value = wait(service, start(env), 'applied')
    assert value['autoKeep']['action'] == 'finish_edit'
    old = deepcopy(value)
    value = choose(service, value, 'wait_for_answer')
    assert value['autoKeep']['enabled'] is False
    with pytest.raises(ServiceError): choose(service, old, 'finish_edit', automatic=True)
    with pytest.raises(ServiceError): choose(service, value, 'finish_edit', automatic=True)
    value = choose(service, value, 'finish_edit')
    assert value['state'] == 'executed' and not bridge.adapter.save_calls


def test_automatic_keep_success_and_legacy_typed_manual(env):
    service, bridge, _, _ = env
    value = wait(service, start(env), 'applied')
    record = service.edit_workflows.store.records[value['id']]
    record['autoKeepEnabled'] = False  # Persisted pre-unification typed policy.
    assert not auto_keep_available(record)
    record['autoKeepEnabled'] = True
    assert choose(service, value, 'finish_edit', automatic=True)['state'] == 'executed'


@pytest.mark.parametrize('status', ['failed', 'cancelled', 'applying', 'rolling_back', 'discarding'])
def test_keep_never_releases_incomplete_or_failed_operations(env, status):
    service, bridge, _, _ = env
    value = wait(service, start(env), 'applied')
    op = bridge.core._operations[value['jobId']]
    op['status'] = status
    with pytest.raises(BridgeError): bridge.core.finish_edit(value['jobId'])
    assert op['resolved']


def test_prepared_read_is_ready_without_running_supervisor(env):
    service, bridge, _, _ = env
    service.edit_workflows._start_runner = lambda: None
    value = start(env)
    assert wait(service, value, 'ready')['state'] == 'ready'
    assert bridge.applies == 0


def test_typed_result_save_status_uses_fresh_document_evidence(env):
    service, bridge, _, _ = env
    value = wait(service, start(env), 'applied')
    assert 'The font has unsaved edits.' in value['text']
    bridge.adapter.dirty = False  # User saved independently in Glyphs.
    value = service.edit_workflows.get(value['id'])
    assert 'The font is currently saved.' in value['text']
    assert 'The font has unsaved edits.' not in value['text']
    assert not bridge.adapter.save_calls


def test_routing_fixtures_use_same_actions_without_saving(tmp_path):
    import json
    from pathlib import Path
    from glyphs_mcp_sidecar.edit_workflow_state import WorkflowStore, public_workflow
    rows=json.loads((Path(__file__).parent/'fixtures/unified_result_routing.json').read_text())
    store=WorkflowStore(tmp_path)
    for i,row in enumerate(rows):
        value=store.create(dict(id='doc',path='/font.glyphs',dirty=True),{},dict(kind=row['kind'],options={}), 'apply',str(i),auto_keep=row['auto_keep'])
        value.update(state='applied',job=dict(status='applied',bridgeOperation=dict(status='applied',scriptResult=dict(executed=True,executionSucceeded=True))),savedVersion=dict(available=True))
        result=public_workflow(value)
        actions={a['action'] for a in result['actions']}
        assert row['finishAction'] in actions and row['recoveryAction'] in actions
        assert result['autoKeep']['enabled']==row['auto_keep']
        assert 'Keep without saving' in result['text']
        assert 'Save font' in result['text']
