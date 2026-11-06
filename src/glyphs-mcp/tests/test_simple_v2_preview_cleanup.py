"""Cancellation must release the native preview, including pre-fix orphans."""
import pytest

from test_simple_v2_script_snapshots import native, run
from test_simple_v2_edit_workflow import wait, choose
from glyphs_mcp_sidecar import task_expiration
from glyphs_mcp_sidecar.bridge_client import BridgeClientError
from glyphs_mcp_sidecar.service import ServiceError


@pytest.fixture
def preview(native, monkeypatch):
    _, core, bridge, service, add = native
    font, identity = add()
    monkeypatch.setattr(bridge, 'discard', lambda key: bridge.invoke(core.discard, key), raising=False)
    monkeypatch.setattr(bridge, 'operation', lambda key: bridge.invoke(core.operation, key))
    value = service.edit_workflows.start(identity, kind='python_script', idempotency_key='preview',
        mode='preview', auto_keep=False,
        options=dict(source='font.glyphs["A"].width=999', entrypoint='script', targets=[]))
    value = wait(service, value, 'waiting_run')
    return font, identity, core, bridge, service, value


def orphan(service, value, status='discarded'):
    job = service.jobs.get(value['jobId'])
    job.pop('preparationRoute', None)  # Records written by the affected runtime.
    job['status'] = status
    service.jobs._write(job)
    service.edit_workflows.store.update(service.edit_workflows.store.records[value['id']],
                                        state='cancelled', job=service._public(job))
    return job


def test_cancel_script_preview_releases_bridge_and_next_script_can_run(preview):
    font, identity, core, _, service, value = preview
    assert service.jobs.get(value['jobId'])['preparationRoute'] == 'native'
    result = wait(service, choose(service, value, 'cancel'), 'cancelled')
    assert result['state'] == 'cancelled'
    assert service.jobs.get(value['jobId'])['status'] == 'discarded'
    assert core.operation(value['jobId'])['status'] == 'cancelled'
    assert not core._operations[value['jobId']].get('scriptSnapshot')
    assert font.glyphs['A'].width == 610
    second = run(service, identity, key='after-cancel')
    assert second['state'] == 'applied' and font.glyphs['A'].width == 620


def test_ready_script_without_native_route_still_releases_preview(preview):
    _, _, core, _, service, value = preview
    job = service.jobs.get(value['jobId'])
    job.pop('preparationRoute')
    service.jobs._write(job)
    choose(service, value, 'cancel')
    assert core.operation(job['id'])['status'] == 'cancelled'


@pytest.mark.parametrize('status', ['discarded', 'cancelled'])
def test_repeated_discard_repairs_legacy_orphan_without_workflow_token(preview, status):
    font, _, core, _, service, value = preview
    job = orphan(service, value, status)
    result = service.discard_job(job['id'])
    assert result['status'] == status
    assert core.operation(job['id'])['status'] == 'cancelled'
    assert service.jobs.get(job['id'])['nativePreviewReleased']
    assert service.discard_job(job['id'])['status'] == status
    assert font.glyphs['A'].width == 610


def test_background_maintenance_repairs_closed_preview_without_waiting_for_expiry(preview):
    font, _, core, _, service, value = preview
    job = orphan(service, value)
    assert not task_expiration.due(service.edit_workflows.store.records[value['id']], job)
    task_expiration.expire(service)
    assert core.operation(job['id'])['status'] == 'cancelled'
    assert service.jobs.get(job['id'])['nativePreviewReleased']
    assert service.edit_workflows.store.records[value['id']]['state'] == 'cancelled'
    assert font.glyphs['A'].width == 610


def test_failed_native_cancellation_does_not_publish_discarded_or_delete_report(preview, monkeypatch):
    _, _, core, bridge, service, value = preview
    def unavailable(_):
        raise BridgeClientError('bridge_unavailable', 'Disconnected', {'execution': 'uncertain'})
    monkeypatch.setattr(bridge, 'discard', unavailable)
    with pytest.raises(ServiceError, match='Disconnected'):
        service.discard_job(value['jobId'])
    assert service.jobs.get(value['jobId'])['status'] == 'ready'
    assert (service.jobs.path(value['jobId']) / 'report.json').exists()
    assert core.operation(value['jobId'])['status'] == 'ready'
    monkeypatch.setattr(bridge, 'discard', lambda key: bridge.invoke(core.discard, key))
    assert service.discard_job(value['jobId'])['status'] == 'discarded'


def test_lost_native_cancellation_response_is_reconciled_without_rerun(preview, monkeypatch):
    font, _, core, bridge, service, value = preview
    calls = []
    def lose_reply(key):
        calls.append(key)
        bridge.invoke(core.discard, key)
        raise BridgeClientError('bridge_unavailable', 'Lost reply', {'execution': 'uncertain'})
    monkeypatch.setattr(bridge, 'discard', lose_reply)
    with pytest.raises(ServiceError, match='Lost reply'):
        service.discard_job(value['jobId'])
    assert service.jobs.get(value['jobId'])['status'] == 'ready'
    assert service.discard_job(value['jobId'])['status'] == 'discarded'
    assert calls == [value['jobId']] and font.glyphs['A'].width == 610


def test_repair_never_discards_an_executed_script_or_its_snapshot(preview):
    font, _, core, _, service, value = preview
    executed = choose(service, value, 'run_script')
    executed = wait(service, executed, 'applied')
    operation = core._operations[value['jobId']]
    snapshot = operation['scriptSnapshot']
    orphan(service, value)
    with pytest.raises(ServiceError) as caught:
        service.discard_job(value['jobId'])
    assert caught.value.code == 'preview_release_unverified'
    task_expiration.expire(service)
    assert operation['scriptSnapshot'] is snapshot
    assert operation['status'] == 'applied' and font.glyphs['A'].width == 999
    assert not service.jobs.get(value['jobId']).get('nativePreviewReleased')


def test_repair_after_bridge_restart_accepts_confirmed_missing_preview(preview):
    _, _, core, _, service, value = preview
    orphan(service, value)
    del core._operations[value['jobId']]
    assert service.discard_job(value['jobId'])['status'] == 'discarded'
    assert service.jobs.get(value['jobId'])['nativePreviewReleased']


def test_native_identity_mismatch_never_releases_another_document(preview, monkeypatch):
    _, _, core, bridge, service, value = preview
    orphan(service, value)
    operation = dict(core.operation(value['jobId']), documentId='another-font')
    monkeypatch.setattr(bridge, 'operation', lambda _: operation)
    with pytest.raises(ServiceError) as caught:
        service.discard_job(value['jobId'])
    assert caught.value.code == 'preview_release_unverified'
    assert core.operation(value['jobId'])['status'] == 'ready'


def test_passive_reads_do_not_repair_and_busy_maintenance_defers(preview, monkeypatch):
    from glyphs_mcp_sidecar.task_inventory import list_tasks
    _, _, core, bridge, service, value = preview
    orphan(service, value)
    list_tasks(service)
    service.get_status()
    assert core.operation(value['jobId'])['status'] == 'ready'
    monkeypatch.setattr(bridge, 'status', lambda: {'activeOperations': 1})
    task_expiration.expire(service)
    assert core.operation(value['jobId'])['status'] == 'ready'


def test_cancellation_during_report_publication_also_releases_native_preview(native, monkeypatch):
    _, core, bridge, service, add = native
    font, identity = add()
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    monkeypatch.setattr(bridge, 'discard', lambda key: bridge.invoke(core.discard, key), raising=False)
    write = service.jobs.write_json
    def cancel_on_report(job_id, name, data):
        path = write(job_id, name, data)
        if name == 'report.json':
            service._cancellations[job_id].set()
        return path
    monkeypatch.setattr(service.jobs, 'write_json', cancel_on_report)
    value = service.edit_workflows.start(identity, kind='python_script', idempotency_key='publication-race',
        mode='preview', auto_keep=False,
        options=dict(source='font.glyphs["A"].width=999', entrypoint='script', targets=[]))
    value = wait(service, value, 'cancelled')
    assert core.operation(value['jobId'])['status'] == 'cancelled'
    assert font.glyphs['A'].width == 610
