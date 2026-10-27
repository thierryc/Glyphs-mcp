"""Expiry closes stale intent, never an available font recovery or active write."""
from copy import deepcopy
import json
import time

import pytest

from test_simple_v2_edit_workflow import env, start, wait, choose
from test_simple_v2_script_snapshots import native
from glyphs_mcp_sidecar.bridge_client import BridgeClientError
from glyphs_mcp_sidecar.service import ServiceError
from glyphs_mcp_sidecar.task_inventory import list_tasks
from glyphs_mcp_sidecar import task_expiration as expiry
from glyphs_mcp_sidecar.task_history import start_cleanup

DAY = 86400


def aged_job(service, *, age=2 * DAY, status='interrupted', kind='width_delta'):
    job = service.jobs.create({'id': 'old-font', 'familyName': 'Old font'}, {'kind': kind})
    job.update(status=status, resultKind='script' if kind == 'python_script' else 'mutation',
               createdAt=time.time() - age, updatedAt=time.time() - age,
               finishedAt=time.time() - age,
               error={'code': 'bridge_operation_lost', 'message': 'Earlier outcome is unknown.'})
    service.jobs._write(job)
    return deepcopy(job)


def aged_workflow(service, job=None, *, state='interrupted', age=2 * DAY, key='old-request'):
    request = job['request'] if job else {'kind': 'width_delta', 'delta': 8}
    doc = job['document'] if job else {'id': 'old-font', 'familyName': 'Old font'}
    value = service.edit_workflows.store.create(doc, request, request, 'apply', key, script_run_authorized=True)
    service.edit_workflows.store.update(value, state=state, jobId=job['id'] if job else None, job=job,
        createdAt=time.time() - age, lastActivityAt=time.time() - age)
    return value


def test_orphan_expiry_keeps_unknown_outcome_reports_and_font_untouched(env):
    service, bridge, worker, source = env
    job = aged_job(service)
    service.jobs.write_json(job['id'], 'report.json', {'diagnostics': 'retain'})
    before = source.read_bytes(), bridge.adapter.value, worker.calls
    assert expiry.expire(service) == 1
    changed = service.jobs.get(job['id'])
    assert changed['status'] == 'expired' and changed['error'] == job['error']
    assert changed['expiration']['previousState'] == 'interrupted'
    assert changed['expiration']['inactivityDays'] == 1
    assert (source.read_bytes(), bridge.adapter.value, worker.calls) == before
    assert service.jobs.read_json(job['id'], 'report.json') == {'diagnostics': 'retain'}
    item = list_tasks(service)['tasks'][0]
    assert item['closed'] and item['taskStatus'] == 'finished' and item['state'] == 'expired'
    assert item['outcomeLabel'] == 'Outcome unknown'
    assert item['updatedAt'] == job['updatedAt'] and item['expiredAt']
    assert expiry.expire(service) == 0


def test_owned_interruption_and_its_old_waiter_expire_without_consuming_actions(env):
    service = env[0]
    job = aged_job(service)
    first = aged_workflow(service, job)
    second = aged_workflow(service, key='waiting', state='blocked_review')
    service.edit_workflows.store.update(second, blockerId=job['id'], blocker={'wait': 'check'},
                                       blockingWorkflowId=first['id'])
    assert expiry.expire(service) == 2
    for value in [first, second]:
        assert value['state'] == 'expired' and not value['scriptRunAuthorized']
        assert value['usedActions'] == {} and value['blockerId'] is None
        assert service.edit_workflows.get(value['id'])['actions'] == []
    assert all(t['closed'] and not t['blockedBy'] for t in list_tasks(service)['tasks'])


def test_setting_changes_apply_without_restart_and_default_is_one_day(env):
    service = env[0]
    job = aged_job(service)
    policy = service.jobs.root / 'task-policy.json'
    assert expiry.inactivity_days(service) == 1
    policy.write_text(json.dumps({'version': 1, 'inactivityDays': 7}))
    assert expiry.expire(service) == 0
    policy.write_text(json.dumps({'version': 1, 'inactivityDays': 1}))
    assert expiry.expire(service) == 1
    assert service.jobs.get(job['id'])['expiration']['inactivityDays'] == 1


@pytest.mark.parametrize('value', [0, -1, True, 366, '7', None])
def test_invalid_settings_postpone_automatic_expiry(env, value):
    service = env[0]; job = aged_job(service)
    (service.jobs.root / 'task-policy.json').write_text(json.dumps({'version': 1, 'inactivityDays': value}))
    assert expiry.expire(service) == 0
    assert service.jobs.get(job['id']) == job


@pytest.mark.parametrize('age', [DAY - 1, -DAY])
def test_recent_or_future_dated_tasks_do_not_expire(env, age):
    service = env[0]; job = aged_job(service, age=age)
    assert expiry.expire(service) == 0 and service.jobs.get(job['id']) == job


@pytest.mark.parametrize('condition', ['offline', 'native_busy', 'pending', 'worker', 'reservation', 'available_recovery'])
def test_work_recovery_and_installation_reservations_are_kept(env, condition):
    service, bridge, *_ = env
    job = aged_job(service, status='applied' if condition == 'available_recovery' else 'interrupted')
    if condition == 'offline':
        bridge.status = lambda: (_ for _ in ()).throw(BridgeClientError('bridge_unavailable', 'Offline'))
    if condition == 'native_busy': bridge.status = lambda: {'activeOperations': 1}
    if condition == 'pending': service.lifecycle.pending = 1
    if condition == 'worker': service._cancellations['other'] = object()
    if condition == 'reservation': service.lifecycle.reservation = {'id': 'settings', 'deadline': time.monotonic() + 100}
    if condition == 'available_recovery':
        bridge.operation = lambda _: {'status': 'applied', 'recoveryAvailable': True}
    try:
        assert expiry.expire(service) == 0
        assert service.jobs.get(job['id']) == job
    finally:
        service._cancellations.clear(); service.lifecycle.pending = 0; service.lifecycle.reservation = None


def test_late_evidence_prevents_expiring_a_checked_record(env):
    service, bridge, *_ = env
    job = aged_job(service)
    def changed(identity):
        service.jobs.update(identity, summary='Fresh evidence')
        raise BridgeClientError('job_not_found', 'No operation')
    bridge.operation = changed
    assert expiry.expire(service) == 0
    assert service.jobs.get(job['id'])['status'] == 'interrupted'


def test_passive_inventory_never_expires_tasks(env):
    service = env[0]; job = aged_job(service)
    value = aged_workflow(service, job)
    before = deepcopy(value), service.jobs.records()
    list_tasks(service)
    assert (value, service.jobs.records()) == before


def test_expired_queued_intent_never_starts_when_glyphs_returns(env, monkeypatch):
    service, bridge, worker, _ = env
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    value = aged_workflow(service, state='queued')
    service.edit_workflows._advance(value)
    assert value['state'] == 'expired' and worker.calls == bridge.applies == 0
    assert service.edit_workflows.get(value['id'])['actions'] == []


def test_old_prepared_queue_request_loses_auto_execution_authorization(env, monkeypatch):
    service, bridge, worker, _ = env
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    value = wait(service, start(env, mode='preview'), 'ready')
    record = service.edit_workflows.store.records[value['id']]
    service.edit_workflows.store.update(record, state='queued', queuedAction='apply',
        createdAt=time.time() - 2 * DAY, lastActivityAt=time.time() - 2 * DAY)
    service.edit_workflows._advance(record)
    assert record['state'] == 'needs_review' and bridge.applies == 0
    assert expiry.expire(service) == 1 and record['state'] == 'expired'


def test_native_available_snapshot_never_expires(native, monkeypatch):
    _, core, bridge, service, add = native
    from test_simple_v2_script_snapshots import run
    _, identity = add()
    value = run(service, identity)
    record = service.edit_workflows.store.records[value['id']]
    old = time.time() - 100 * DAY
    service.edit_workflows.store.update(record, createdAt=old, lastActivityAt=old)
    job = service.jobs.get(record['jobId']); job.update(createdAt=old, updatedAt=old, finishedAt=old)
    service.jobs._write(job)
    assert expiry.expire(service) == 0
    assert core._operations[job['id']]['scriptSnapshot'] is not None


def test_native_unapplied_preview_is_cancelled_without_editing_font(native, monkeypatch):
    _, core, bridge, service, add = native
    font, identity = add()
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    monkeypatch.setattr(bridge, 'discard', lambda key: bridge.invoke(core.discard, key), raising=False)
    value = service.edit_workflows.start(identity, kind='python_script', idempotency_key='preview',
        mode='preview', auto_keep=False, options={'source': 'font.glyphs["A"].width=999', 'entrypoint': 'script', 'targets': []})
    value = wait(service, value, 'waiting_run')
    record = service.edit_workflows.store.records[value['id']]
    old = time.time() - 2 * DAY
    service.edit_workflows.store.update(record, createdAt=old, lastActivityAt=old)
    # The prepared report must remain available as diagnostics after expiry.
    report = service.jobs.read_json(value['jobId'], 'report.json')
    assert expiry.expire(service) == 1
    assert record['state'] == 'expired' and not record['scriptRunAuthorized']
    assert core._operations[value['jobId']]['status'] == 'cancelled'
    assert font.glyphs['A'].width == 610
    assert service.jobs.read_json(value['jobId'], 'report.json') == report


def test_queue_progress_does_not_renew_old_authorization(env):
    service = env[0]
    value = aged_workflow(service, state='queued')
    service.edit_workflows.store.update(value, blocker={'wait': 'automatic'})
    assert expiry.due(value)
    assert expiry.stop_old_queued_intent(service.edit_workflows, value)
    assert value['state'] == 'expired'


def test_broken_settings_pause_queued_work_instead_of_running_it(env):
    service = env[0]
    value = aged_workflow(service, state='queued')
    (service.jobs.root / 'task-policy.json').write_text('broken')
    assert expiry.stop_old_queued_intent(service.edit_workflows, value)
    assert value['state'] == 'interrupted' and value['error']['code'] == 'task_policy_unavailable'
    assert not value['scriptRunAuthorized']


def test_an_accepted_old_queue_cancellation_is_not_replaced_by_expiry(env, monkeypatch):
    service, bridge, *_ = env
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    value = wait(service, start(env, mode='preview'), 'ready')
    record = service.edit_workflows.store.records[value['id']]
    old = time.time() - 2 * DAY
    service.edit_workflows.store.update(record, state='queued', createdAt=old, lastActivityAt=old)
    current = service.edit_workflows.get(record['id'])
    choose(service, current, 'cancel')
    assert expiry.expire(service) == 0
    service.edit_workflows._advance(record)
    service.edit_workflows._advance(record)
    assert record['state'] == 'cancelled' and bridge.applies == 0


def test_missing_local_job_does_not_hide_native_recovery(env):
    service, bridge, *_ = env
    value = aged_workflow(service)
    service.edit_workflows.store.update(value, jobId='job_' + 'f' * 32)
    bridge.operation = lambda _: {'status': 'applied', 'recoveryAvailable': True}
    assert expiry.expire(service) == 0
    assert value['state'] == 'interrupted'


def test_lost_partial_result_expires_with_partial_outcome_retained(env):
    service = env[0]
    job = aged_job(service, status='failed', kind='python_script')
    job['bridgeOperation'] = {'scriptResult': {'executed': True, 'executionSucceeded': False}}
    service.jobs._write(job)
    value = aged_workflow(service, job, state='failed')
    assert expiry.expire(service) == 1
    item = next(t for t in list_tasks(service)['tasks'] if t['id'] == value['id'])
    assert item['closed'] and item['taskStatus'] == 'finished'
    assert item['outcomeLabel'] == 'Partial changes may remain'


def test_background_worker_expires_without_opening_tasks(env):
    service = env[0]; job = aged_job(service)
    stop = start_cleanup(service, interval=.02)
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and service.jobs.get(job['id'])['status'] != 'expired':
            time.sleep(.01)
        assert service.jobs.get(job['id'])['status'] == 'expired'
    finally:
        stop()
