"""Archival retains unknown outcomes and never substitutes for recovery."""
from concurrent.futures import ThreadPoolExecutor
import asyncio

import httpx
import pytest
from test_simple_v2_edit_workflow import env as typed_env
from glyphs_mcp_sidecar import task_archive
from glyphs_mcp_sidecar.bridge_client import BridgeClientError
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.service import ServiceError
from glyphs_mcp_sidecar.task_inventory import list_tasks


def orphan(env, **changes):
    service, _, _, source = env
    job = service.jobs.create(dict(id='doc_1', familyName='HandPrint', path=str(source)), dict(kind='kerning_edit', options={}))
    return service.jobs.update(job['id'], status='interrupted', resultKind='mutation',
        error=dict(code='bridge_operation_lost', message='Final edits and restoration are unverified.'), **changes)


def archive(service, snapshot):
    return task_archive.respond(service, snapshot['jobId'], snapshot['revision'], snapshot['actions'][0]['token'])


def test_archive_retains_exact_evidence_artifacts_and_unverified_history(typed_env):
    service, bridge, worker, source = typed_env
    job = orphan(typed_env)
    service.jobs.write_json(job['id'], 'report.json', {'diagnostics': 'keep me'})
    state_path = service.jobs.path(job['id']) / 'state.json'
    before = state_path.read_bytes(), source.read_bytes(), bridge.adapter.value, worker.calls
    snapshot = task_archive.options(service, job['id'])
    assert not snapshot['closed'] and snapshot['receipt'] is None
    assert [item['action'] for item in snapshot['actions']] == ['archive_interrupted']
    assert 'Unverified' in snapshot['actions'][0]['consequence']
    result = archive(service, snapshot)
    assert result['closed'] and result['state'] == 'archived' and not result['actions']
    assert 'Unverified' in result['receipt'] and result['warning'] == job['error']['message']
    assert (state_path.read_bytes(), source.read_bytes(), bridge.adapter.value, worker.calls) == before
    assert service.jobs.read_json(job['id'], 'report.json') == {'diagnostics': 'keep me'}
    item = list_tasks(service)['tasks'][0]
    assert item['closed'] and item['outcome'] == 'unverified' and item['state'] == 'archived'
    assert item['message'] == job['error']['message'] and item['supportText'] == result['receipt']
    assert not bridge.applies and not bridge.adapter.save_calls
    # Durable across JobStore reload, without changing the execution status.
    service.jobs = JobStore(service.jobs.root)
    assert list_tasks(service)['tasks'][0]['closed']
    assert service.jobs.get(job['id'])['status'] == 'interrupted'
    # A later observation automatically returns the task to attention.
    service.jobs.update(job['id'], error={'code': 'new_evidence', 'message': 'Review again'})
    assert not list_tasks(service)['tasks'][0]['closed']


@pytest.mark.parametrize('changes', [
    {'request': {'kind': 'python_script'}}, {'request': {'kind': 'checkpoint_restore'}},
    {'restoreRequest': {'baseline': 'owned'}}, {'saveRequest': {'destination': 'pending'}},
    {'error': {'details': {'writeAttempted': True}}}, {'error': {'details': {'execution': 'uncertain'}}},
    {'resultKind': 'historical_restore', 'restoreRequest': {'baseline': 'owned'}},
])
def test_unresolved_ownership_cannot_be_hidden(typed_env, changes):
    service, *_ = typed_env
    job = orphan(typed_env)
    service.jobs.update(job['id'], **changes)
    result = task_archive.options(service, job['id'])
    assert not result['actions'] and not result['closed'] and not result['receipt']
    assert not (service.jobs.path(job['id']) / 'task-archive.json').exists()


@pytest.mark.parametrize('status', ['preparing', 'applying', 'applied', 'accept_uncertain', 'failed', 'completed'])
def test_only_interrupted_records_are_archivable(typed_env, status):
    service, *_ = typed_env
    job = orphan(typed_env)
    service.jobs.update(job['id'], status=status)
    assert not task_archive.options(service, job['id'])['actions']


def test_owned_and_blocking_jobs_are_refused(typed_env):
    service, *_ = typed_env
    job = orphan(typed_env)
    document = job['document']; request = job['request']
    value = service.edit_workflows.store.create(document, request, request, 'apply', 'owner')
    service.edit_workflows.store.update(value, state='interrupted', jobId=job['id'])
    assert not task_archive.options(service, job['id'])['actions']
    service.edit_workflows.store.update(value, jobId=None, blockerId=job['id'])
    assert 'blocking' in task_archive.options(service, job['id'])['message']
    assert not task_archive.options(service, job['id'])['actions']


@pytest.mark.parametrize('mode', ['native_busy', 'native_unknown', 'native_exists', 'disconnect', 'worker', 'pending', 'other_job'])
def test_busy_unknown_and_existing_native_operations_are_refused(typed_env, mode):
    service, bridge, *_ = typed_env
    job = orphan(typed_env)
    if mode == 'native_busy': bridge.status = lambda: {'activeOperations': 1}
    if mode == 'native_unknown': bridge.status = lambda: {}
    if mode == 'native_exists': bridge.operation = lambda _: {'status': 'completed'}
    if mode == 'disconnect':
        def disconnected(_): raise BridgeClientError('bridge_unavailable', 'Disconnected')
        bridge.operation = disconnected
    if mode == 'worker':
        from threading import Event
        service._cancellations[job['id']] = Event()
    if mode == 'pending': service.lifecycle.pending = 1
    if mode == 'other_job': service.jobs.create(job['document'], job['request'])
    result = task_archive.options(service, job['id'])
    assert not result['actions'] and not result['closed'] and not result['receipt']
    service._cancellations.clear()


@pytest.mark.parametrize('change', ['evidence', 'busy', 'blocker', 'reservation', 'native', 'token'])
def test_dispatch_rechecks_eligibility_and_stale_choices(typed_env, change):
    service, bridge, *_ = typed_env
    job = orphan(typed_env)
    snapshot = task_archive.options(service, job['id'])
    if change == 'evidence': service.jobs.update(job['id'], summary='New evidence')
    if change == 'busy': bridge.status = lambda: {'activeOperations': 1}
    if change == 'native': bridge.operation = lambda _: {'status': 'applied'}
    if change == 'token': snapshot['actions'][0]['token'] = 'a' * 64
    if change == 'blocker':
        value = service.edit_workflows.store.create(job['document'], job['request'], job['request'], 'apply', 'blocked')
        service.edit_workflows.store.update(value, blockerId=job['id'])
    if change == 'reservation': service.reserve_idle()
    with pytest.raises(ServiceError): archive(service, snapshot)
    assert not (service.jobs.path(job['id']) / 'task-archive.json').exists()
    assert not list_tasks(service)['tasks'][0]['closed']


def test_concurrent_archive_and_lost_reply_are_reconciled_without_replay(typed_env):
    service, *_ = typed_env
    job = orphan(typed_env)
    snapshot = task_archive.options(service, job['id'])
    def attempt():
        try: return archive(service, snapshot)['closed']
        except ServiceError: return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: attempt(), range(2))) == [False, True]
    marker = service.jobs.read_json(job['id'], 'task-archive.json')
    assert task_archive.options(service, job['id'])['closed']
    assert not task_archive.options(service, job['id'])['actions']
    assert service.jobs.read_json(job['id'], 'task-archive.json') == marker


def test_new_blocker_association_reopens_an_archived_record(typed_env):
    service, *_ = typed_env
    job = orphan(typed_env)
    archive(service, task_archive.options(service, job['id']))
    value = service.edit_workflows.store.create(job['document'], job['request'], job['request'], 'apply', 'new_blocker')
    service.edit_workflows.store.update(value, blockerId=job['id'])
    tasks = {task['id']: task for task in list_tasks(service)['tasks']}
    assert not tasks[job['id']]['closed']
    assert tasks[job['id']]['blocking'] == [value['id']]
    assert not task_archive.options(service, job['id'])['closed']


def test_failed_marker_write_never_returns_a_success_receipt(typed_env, monkeypatch):
    service, *_ = typed_env
    job = orphan(typed_env)
    snapshot = task_archive.options(service, job['id'])
    def failed(*_): raise OSError('Fixture write failure')
    with monkeypatch.context() as patch:
        patch.setattr(service.jobs, 'write_json', failed)
        with pytest.raises(OSError, match='Fixture write failure'): archive(service, snapshot)
    result = task_archive.options(service, job['id'])
    assert not result['closed'] and result['receipt'] is None
    assert not list_tasks(service)['tasks'][0]['closed']


def test_other_unresolved_recovery_blocks_archiving(typed_env):
    service, *_ = typed_env
    job = orphan(typed_env)
    other = service.jobs.create(job['document'], dict(kind='python_script'))
    service.jobs.update(other['id'], status='failed', resultKind='script', bridgeOperation={'scriptResult': {'executed': True}})
    assert not task_archive.options(service, job['id'])['actions']


def test_archive_route_is_authenticated_and_identity_is_exclusive(typed_env):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from glyphs_mcp_sidecar.management import register_routes
    service, *_ = typed_env
    job = orphan(typed_env)
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
            payload = {'action': 'options', 'job_id': job['id']}
            assert (await client.post('/internal/task-recovery', json=payload)).status_code == 403
            client.headers['Authorization'] = 'Bearer fixture-token'
            assert (await client.post('/internal/task-recovery', json=dict(payload, workflow_id='edit_other'))).status_code == 400
            result = await client.post('/internal/task-recovery', json=payload)
            snapshot = result.json()['data']
            assert result.status_code == 200 and snapshot['jobId'] == job['id']
            result = await client.post('/internal/task-recovery', json=dict(action='respond', job_id=job['id'],
                expected_revision=snapshot['revision'], action_token=snapshot['actions'][0]['token']))
            assert result.status_code == 200 and result.json()['data']['closed']
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('192.168.0.2', 1234)), base_url='http://local', headers={'Authorization': 'Bearer fixture-token'}) as client:
            assert (await client.post('/internal/task-recovery', json=payload)).status_code == 403
    asyncio.run(check())
