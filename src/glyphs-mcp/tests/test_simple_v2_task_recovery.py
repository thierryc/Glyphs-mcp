"""Companion recovery uses real workflow/native guards, never forced deletion."""
import asyncio
import time

import httpx
import pytest
from test_simple_v2_edit_workflow import env as typed_env, start, wait
from test_simple_v2_saved_scripts import env as script_env, authorized
from glyphs_mcp_sidecar import task_recovery
from glyphs_mcp_sidecar.bridge_client import BridgeClientError
from glyphs_mcp_sidecar.service import ServiceError


def choose(service, snapshot):
    return task_recovery.respond(service, snapshot['workflowId'], snapshot['revision'], snapshot['actions'][0]['token'])


def test_script_close_keeps_changes_without_save_or_replay(script_env):
    service, bridge, source = script_env
    value = wait(service, authorized(service), 'applied')
    before = (bridge.adapter.value, source.read_bytes(), len(bridge.runs))
    snapshot = task_recovery.options(service, value['id'])
    assert [a['action'] for a in snapshot['actions']] == ['finish_script']
    assert 'temporary recovery' in snapshot['actions'][0]['consequence']
    assert not snapshot['closed'] and not snapshot['receipt']
    result = choose(service, snapshot)
    assert result['closed'] and 'No save was performed' in result['receipt']
    assert not result['actions']
    assert (bridge.adapter.value, source.read_bytes(), len(bridge.runs)) == before
    assert not bridge.adapter.save_calls and not bridge.restores


def test_typed_keep_preserves_selective_undo_wording_and_native_guard(typed_env):
    service, bridge, _, source = typed_env
    value = wait(service, start(typed_env, auto_keep=False), 'applied')
    snapshot = task_recovery.options(service, value['id'])
    assert [a['action'] for a in snapshot['actions']] == ['finish_edit']
    assert 'selective Undo' in snapshot['actions'][0]['consequence']
    result = choose(service, snapshot)
    assert result['closed'] and result['state'] == 'executed'
    assert bridge.adapter.value == 608 and source.read_text() == '600'
    assert not bridge.adapter.save_calls


def test_stale_and_save_restore_tokens_cannot_dispatch(script_env):
    service, bridge, _ = script_env
    value = wait(service, authorized(service), 'applied')
    snapshot = task_recovery.options(service, value['id'])
    for action in value['actions']:
        if action['action'] in {'save_result', 'restore_saved_script'}:
            with pytest.raises(ServiceError, match='outdated'):
                task_recovery.respond(service, value['id'], value['revision'], action['token'])
    service.edit_workflows.store.update(service.edit_workflows.store.records[value['id']])
    with pytest.raises(ServiceError, match='outdated'):
        choose(service, snapshot)
    assert not bridge.adapter.save_calls and not bridge.restores
    assert service.jobs.get(value['jobId'])['status'] == 'applied'


def test_inspecting_interrupted_ready_script_never_resumes_it(script_env, monkeypatch):
    service, bridge, _ = script_env
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    value = authorized(service)
    deadline = time.monotonic() + 5
    while service.jobs.get(value['jobId'])['status'] != 'ready':
        assert time.monotonic() < deadline
        time.sleep(.01)
    record = service.edit_workflows.store.records[value['id']]
    service.edit_workflows._set(record, state='interrupted', scriptRunAuthorized=False)
    for _ in range(3):
        result = task_recovery.options(service, value['id'])
        assert result['state'] == 'interrupted' and not result['actions'] and not result['closed']
    assert not bridge.runs and not bridge.adapter.save_calls


def test_cancel_blocked_request_does_not_resolve_or_start_its_owner(typed_env):
    service, bridge, worker, _ = typed_env
    owner = wait(service, start(typed_env, auto_keep=False), 'applied')
    child = service.edit_workflows.start('doc_1', kind='width_delta', delta=4, idempotency_key='waiting', auto_keep=False)
    snapshot = task_recovery.options(service, child['id'])
    assert [a['action'] for a in snapshot['actions']] == ['cancel']
    calls = worker.calls
    result = choose(service, snapshot)
    assert result['closed'] and result['state'] == 'cancelled'
    record = service.edit_workflows.store.records[child['id']]
    assert not record.get('blockerId')
    assert service.edit_workflows.store.records[owner['id']]['state'] == 'applied'
    assert service.jobs.get(owner['jobId'])['status'] == 'applied'
    assert worker.calls == calls and bridge.applies == 1 and not bridge.adapter.save_calls


def test_preview_can_be_cancelled_without_applying(typed_env):
    service, bridge, _, _ = typed_env
    value = wait(service, start(typed_env, mode='preview', auto_keep=False), 'ready')
    snapshot = task_recovery.options(service, value['id'])
    assert [a['action'] for a in snapshot['actions']] == ['discard']
    result = choose(service, snapshot)
    assert result['closed'] and bridge.applies == 0 and bridge.adapter.value == 600


def test_unknown_native_outcome_has_no_closing_choice(script_env):
    service, bridge, _ = script_env
    value = wait(service, authorized(service), 'applied')
    def missing(identity):
        raise BridgeClientError('job_not_found', 'Native operation unavailable')
    bridge.operation = missing
    result = task_recovery.options(service, value['id'])
    assert not result['closed'] and not result['receipt'] and not result['actions']
    assert len(bridge.runs) == 1 and not bridge.adapter.save_calls


def test_reservation_blocks_close(script_env):
    service, _, _ = script_env
    value = wait(service, authorized(service), 'applied')
    snapshot = task_recovery.options(service, value['id'])
    # Reserve through the same lifecycle gate used by installation/settings.
    service.lifecycle.reservation = {'deadline': service.lifecycle.clock() + 30}
    with pytest.raises(ServiceError, match='reserved'):
        choose(service, snapshot)
    assert service.jobs.get(value['jobId'])['status'] == 'applied'
    service.lifecycle.reservation = None


def test_lost_close_response_requires_authoritative_reconciliation(script_env):
    service, bridge, _ = script_env
    value = wait(service, authorized(service), 'applied')
    snapshot = task_recovery.options(service, value['id'])
    original = bridge.finish_script
    finishes = []
    def lost(identity):
        finishes.append(identity)
        original(identity)
        raise BridgeClientError('bridge_timeout', 'Reply lost', {'execution': 'uncertain'})
    bridge.finish_script = lost
    with pytest.raises(ServiceError, match='Reply lost'):
        choose(service, snapshot)
    current = task_recovery.options(service, value['id'])
    assert current['closed'] and current['receipt'] and finishes == [value['jobId']]
    with pytest.raises(ServiceError):
        choose(service, snapshot)
    assert len(finishes) == 1


def test_recovery_route_auth_payload_and_allowlist(script_env):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from glyphs_mcp_sidecar.management import register_routes
    service, bridge, _ = script_env
    value = wait(service, authorized(service), 'applied')
    class Router:
        def __init__(self): self.routes = []
        def custom_route(self, path, methods):
            def decorate(callback):
                self.routes.append(Route(path, callback, methods=methods)); return callback
            return decorate
    router = Router(); register_routes(router, service, 'fixture-token')
    app = Starlette(routes=router.routes)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 1234)), base_url='http://local') as client:
            payload = {'action': 'options', 'workflow_id': value['id']}
            assert (await client.post('/internal/task-recovery', json=payload)).status_code == 403
            client.headers['Authorization'] = 'Bearer fixture-token'
            for malformed in [[], {}, dict(payload, extra=True), dict(payload, action='save'), dict(payload, action='respond'), None]:
                assert (await client.post('/internal/task-recovery', json=malformed)).status_code == 400
            assert (await client.post('/internal/task-recovery', content='x'*2049)).status_code == 400
            result = await client.post('/internal/task-recovery', json=payload)
            assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
            snapshot = result.json()['data']
            forbidden = next(a for a in value['actions'] if a['action'] == 'save_result')
            response = await client.post('/internal/task-recovery', json={'action':'respond','workflow_id':value['id'],'expected_revision':snapshot['revision'],'action_token':forbidden['token']})
            assert response.status_code == 409
            response = await client.post('/internal/task-recovery', json={'action':'respond','workflow_id':value['id'],'expected_revision':snapshot['revision'],'action_token':snapshot['actions'][0]['token']})
            assert response.status_code == 200 and response.json()['data']['closed']
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('192.168.0.2', 1234)), base_url='http://local', headers={'Authorization':'Bearer fixture-token'}) as client:
            assert (await client.post('/internal/task-recovery', json=payload)).status_code == 403
    asyncio.run(check())
    assert not bridge.adapter.save_calls and not bridge.restores


def test_agent_and_companion_race_cannot_close_twice(script_env):
    from concurrent.futures import ThreadPoolExecutor
    service, bridge, _ = script_env
    value = wait(service, authorized(service), 'applied')
    snapshot = task_recovery.options(service, value['id'])
    finishes = []
    original = bridge.finish_script
    def finish(identity):
        finishes.append(identity)
        return original(identity)
    bridge.finish_script = finish
    def companion():
        try: return choose(service, snapshot)
        except ServiceError as exc: return exc.code
    def agent():
        return service.edit_workflows.respond(value['id'], snapshot['revision'], snapshot['actions'][0]['token'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(companion), pool.submit(agent)]
        for future in futures: future.result(timeout=5)
    assert finishes == [value['jobId']]
    assert task_recovery.options(service, value['id'])['closed']


@pytest.mark.parametrize('status', ['failed', 'cancelled'])
def test_partial_results_require_explicit_keep_before_closing(script_env, status):
    service, bridge, _ = script_env
    value = wait(service, authorized(service), 'applied')
    operation = bridge.ops[value['jobId']]
    operation['status'] = status
    operation['error'] = {'code': 'script_failed', 'message': 'Partial execution'}
    operation['scriptResult']['executionSucceeded'] = False
    service.jobs.update(value['jobId'], status=status, bridgeOperation=operation, error=operation['error'])
    snapshot = task_recovery.options(service, value['id'])
    assert not snapshot['closed'] and not snapshot['receipt']
    assert [a['action'] for a in snapshot['actions']] == ['finish_script']
    assert 'Partial edits may remain' in snapshot['actions'][0]['consequence']
    assert choose(service, snapshot)['closed']
    assert len(bridge.runs) == 1 and not bridge.restores and not bridge.adapter.save_calls


def test_running_cancel_retains_partial_recovery_without_success_receipt(script_env):
    service, bridge, _ = script_env
    value = wait(service, authorized(service), 'applied')
    operation = bridge.ops[value['jobId']]
    operation['status'] = 'applying'
    service.jobs.update(value['jobId'], status='applying', bridgeOperation=operation)
    service.edit_workflows._set(service.edit_workflows.store.records[value['id']], state='applying')
    def cancel(identity):
        operation['status'] = 'cancelled'
        operation['scriptResult']['executionSucceeded'] = False
        return operation
    bridge.discard = cancel
    snapshot = task_recovery.options(service, value['id'])
    assert snapshot['actions'][0]['label'] == 'Cancel Remaining Work'
    result = choose(service, snapshot)
    assert not result['closed'] and result['receipt'] is None
    assert [a['action'] for a in result['actions']] == ['finish_script']
    assert len(bridge.runs) == 1 and not bridge.restores


def test_bridge_failure_cannot_offer_stale_close(script_env):
    service, bridge, _ = script_env
    value = wait(service, authorized(service), 'applied')
    def unavailable(identity):
        raise BridgeClientError('bridge_failed', 'Disconnected')
    bridge.operation = unavailable
    result = task_recovery.options(service, value['id'])
    assert not result['closed'] and not result['receipt'] and not result['actions']
    assert 'could not be checked' in result['message']
