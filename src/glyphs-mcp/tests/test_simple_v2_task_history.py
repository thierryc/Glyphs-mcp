"""Cleared presentation history expires; canonical safety evidence never does."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event

import httpx
import pytest
from test_simple_v2_edit_workflow import env as typed_env
from test_simple_v2_task_archive import orphan, archive
from glyphs_mcp_sidecar import task_archive, task_history
from glyphs_mcp_sidecar.bridge_client import BridgeClientError
from glyphs_mcp_sidecar.service import ServiceError
from glyphs_mcp_sidecar.task_inventory import list_tasks

DAY = 86400
START = 1_000_000.0


def closed(env, *, workflow=True):
    service, _, _, source = env
    doc = dict(id='doc_1', familyName='Test', path=str(source))
    request = dict(kind='width_delta', options={})
    job = service.jobs.create(doc, request)
    job = service.jobs.update(job['id'], status='completed', resultKind='mutation', error={'code': 'retained', 'message': 'Diagnostic evidence'})
    if not workflow:
        return job['id'], job
    value = service.edit_workflows.store.create(doc, request, request, 'apply', job['id'])
    service.edit_workflows.store.update(value, state='executed', jobId=job['id'], job=job)
    return value['id'], job


def record(service, identity):
    task = next(task for task in list_tasks(service)['tasks'] if task['id'] == identity)
    return dict(id=identity, revision=task['historyRevision'])


def ledger(service):
    return json.loads((service.jobs.root / 'task-history/ledger.json').read_text())['entries']


@pytest.mark.parametrize('workflow', [True, False])
def test_expiry_boundary_preserves_every_canonical_byte_and_prevents_restoration(typed_env, workflow):
    service, bridge, worker, source = typed_env
    identity, job = closed(typed_env, workflow=workflow)
    for name in ['diagnostic.json', 'receipt.json', 'checkpointBaseline', 'checkpointTransaction', 'snapshot.json']:
        service.jobs.write_json(job['id'], name if name.endswith('.json') else name+'.json', {'recovery': 'protected'})
    before = {path: path.read_bytes() for path in service.jobs.root.rglob('*') if path.is_file()}
    request = record(service, identity)
    task_history.change(service, 'clear', [request], now=START)
    task_history.change(service, 'clear', [request], now=START + 10*DAY)
    assert ledger(service)[identity]['clearedAt'] == START
    assert task_history.cleanup(service, now=START + 30*DAY - 1) == 0
    assert any(task['id'] == identity for task in list_tasks(service)['tasks'])
    assert task_history.cleanup(service, now=START + 30*DAY) == 1
    assert identity not in {task['id'] for task in list_tasks(service)['tasks']}
    assert identity not in {task['id'] for task in list_tasks(service)['index']}
    assert set(ledger(service)[identity]) == {'phase', 'revision', 'expiredAt'}
    task_history.change(service, 'restore', [dict(id=identity)], now=START + 31*DAY)
    assert not list_tasks(service)['tasks']
    assert task_history.cleanup(service, now=START + 60*DAY) == 0
    for path, content in before.items(): assert path.read_bytes() == content
    assert source.read_text() == '600' and bridge.adapter.value == 600
    assert not bridge.applies and not bridge.adapter.save_calls and not worker.calls


def test_restore_cancels_retention_and_reclear_starts_a_new_period(typed_env):
    service, *_ = typed_env
    identity, _ = closed(typed_env)
    request = record(service, identity)
    task_history.change(service, 'clear', [request], now=START)
    task_history.change(service, 'restore', [dict(id=identity)], now=START + 29*DAY)
    assert identity not in ledger(service)
    assert task_history.cleanup(service, now=START + 31*DAY) == 0
    task_history.change(service, 'clear', [request], now=START + 31*DAY)
    assert ledger(service)[identity]['clearedAt'] == START + 31*DAY
    assert task_history.cleanup(service, now=START + 60*DAY) == 0


def test_archived_unverified_diagnostics_and_archive_marker_remain_intact(typed_env):
    service, *_ = typed_env
    job = orphan(typed_env)
    archive(service, task_archive.options(service, job['id']))
    archive_path = service.jobs.path(job['id']) / 'task-archive.json'
    original = archive_path.read_bytes(), service.jobs.get(job['id'])
    task_history.change(service, 'clear', [record(service, job['id'])], now=START)
    assert task_history.cleanup(service, now=START + 31*DAY) == 1
    assert not list_tasks(service)['tasks']
    assert (archive_path.read_bytes(), service.jobs.get(job['id'])) == original
    assert task_archive.options(service, job['id'])['state'] == 'archived'
    assert 'Unverified' in task_archive.options(service, job['id'])['receipt']


@pytest.mark.parametrize('change', ['open', 'evidence', 'blocker', 'recovery', 'missing_job'])
def test_changed_or_protected_tasks_are_never_expired(typed_env, change):
    service, *_ = typed_env
    identity, job = closed(typed_env)
    task_history.change(service, 'clear', [record(service, identity)], now=START)
    if change == 'open':
        service.edit_workflows._set(service.edit_workflows.store.records[identity], state='uncertain')
    elif change == 'evidence': service.jobs.update(job['id'], summary='New diagnostic evidence')
    elif change == 'blocker':
        value = service.edit_workflows.store.create(job['document'], job['request'], job['request'], 'apply', 'blocking')
        service.edit_workflows.store.update(value, state='interrupted', blockerId=job['id'], blockingWorkflowId=identity)
    elif change == 'recovery':
        service.jobs.update(job['id'], status='failed', resultKind='script', bridgeOperation={'scriptResult': {'executed': True}})
    else:
        service.jobs.path(job['id']).joinpath('state.json').unlink()
    assert task_history.cleanup(service, now=START + 31*DAY) == 0
    assert identity in {task['id'] for task in list_tasks(service)['tasks']}


@pytest.mark.parametrize('mode', ['worker', 'pending', 'native_busy', 'native_unknown', 'disconnected', 'native_recovery', 'reservation'])
def test_active_or_unknown_state_postpones_cleanup(typed_env, mode):
    service, bridge, *_ = typed_env
    identity, job = closed(typed_env)
    task_history.change(service, 'clear', [record(service, identity)], now=START)
    if mode == 'worker': service._cancellations['fixture'] = Event()
    if mode == 'pending': service.lifecycle.pending = 1
    if mode == 'native_busy': bridge.status = lambda: {'activeOperations': 1}
    if mode == 'native_unknown': bridge.status = lambda: {}
    if mode == 'native_recovery': bridge.operation = lambda _: {'status': 'applied'}
    if mode == 'disconnected':
        def failed(): raise OSError('Disconnected')
        bridge.status = failed
    if mode == 'reservation': service.reserve_idle()
    try:
        assert task_history.cleanup(service, now=START + 31*DAY) == 0
    except ServiceError as error:
        assert mode == 'reservation' and error.code == 'service_reserved'
    assert ledger(service)[identity]['phase'] == 'cleared'
    service._cancellations.clear()


def test_new_evidence_revives_expired_history_and_rejects_stale_clear(typed_env):
    service, *_ = typed_env
    identity, job = closed(typed_env)
    stale = record(service, identity)
    task_history.change(service, 'clear', [stale], now=START)
    assert task_history.cleanup(service, now=START + 31*DAY) == 1
    service.jobs.update(job['id'], summary='Outcome updated')
    assert identity in {task['id'] for task in list_tasks(service)['tasks']}
    task_history.cleanup(service, now=START + 32*DAY)
    assert identity not in ledger(service)
    task_history.change(service, 'clear', [stale], now=START + 33*DAY)
    assert identity not in ledger(service)


def test_concurrent_restore_and_expiry_are_atomic(typed_env):
    service, *_ = typed_env
    identity, _ = closed(typed_env)
    task_history.change(service, 'clear', [record(service, identity)], now=START)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(task_history.cleanup, service, now=START + 31*DAY)
        b = pool.submit(task_history.change, service, 'restore', [dict(id=identity)])
        expired = a.result(timeout=5); b.result(timeout=5)
    assert bool(list_tasks(service)['tasks']) == (expired == 0)
    assert all('summary' not in entry for entry in ledger(service).values())


def test_failed_atomic_replace_retains_summary_and_is_retryable(typed_env, monkeypatch):
    service, *_ = typed_env
    identity, _ = closed(typed_env)
    task_history.change(service, 'clear', [record(service, identity)], now=START)
    before = ledger(service)
    with monkeypatch.context() as patch:
        def failed(*_): raise OSError('Fixture interrupted write')
        patch.setattr(task_history, '_write', failed)
        with pytest.raises(OSError): task_history.cleanup(service, now=START + 31*DAY)
    assert ledger(service) == before and list_tasks(service)['tasks']
    assert task_history.cleanup(service, now=START + 31*DAY) == 1


@pytest.mark.parametrize('raw', ['{broken', '[]', '{"version":1,"entries":[]}'])
def test_corrupt_metadata_preserves_visible_history(typed_env, raw):
    service, *_ = typed_env
    identity, _ = closed(typed_env)
    task_history.change(service, 'clear', [record(service, identity)], now=START)
    (service.jobs.root / 'task-history/ledger.json').write_text(raw)
    assert list_tasks(service)['tasks']
    with pytest.raises((ValueError, AttributeError)): task_history.cleanup(service, now=START + 31*DAY)
    assert list_tasks(service)['tasks']


def test_passive_reads_do_not_cleanup_or_query_native(typed_env):
    service, bridge, *_ = typed_env
    identity, _ = closed(typed_env)
    task_history.change(service, 'clear', [record(service, identity)], now=1)
    def forbidden(*_): raise AssertionError('Passive read called native code')
    bridge.status = forbidden; bridge.operation = forbidden
    assert list_tasks(service)['tasks']
    assert ledger(service)[identity]['phase'] == 'cleared'


@pytest.mark.parametrize('timestamp', [float('nan'), float('inf'), -1, 'unknown', None, START + 100*DAY])
def test_invalid_or_future_clear_dates_never_trigger_expiry(typed_env, timestamp):
    service, *_ = typed_env
    identity, _ = closed(typed_env)
    task_history.change(service, 'clear', [record(service, identity)], now=START)
    path = service.jobs.root / 'task-history/ledger.json'
    data = json.loads(path.read_text()); data['entries'][identity]['clearedAt'] = timestamp
    path.write_text(json.dumps(data))
    assert task_history.cleanup(service, now=START + 31*DAY) == 0
    assert list_tasks(service)['tasks']


def test_evidence_changed_during_native_read_cannot_be_expired(typed_env):
    service, bridge, *_ = typed_env
    identity, job = closed(typed_env)
    task_history.change(service, 'clear', [record(service, identity)], now=START)
    def changed(_):
        service.jobs.update(job['id'], summary='Changed during check')
        raise BridgeClientError('job_not_found', 'Operation missing')
    bridge.operation = changed
    assert task_history.cleanup(service, now=START + 31*DAY) == 0
    assert list_tasks(service)['tasks']


@pytest.mark.parametrize('state', ['preparing', 'applied', 'uncertain', 'interrupted'])
def test_clear_cannot_schedule_an_open_workflow(typed_env, state):
    service, *_ = typed_env
    identity, _ = closed(typed_env)
    service.edit_workflows._set(service.edit_workflows.store.records[identity], state=state)
    task_history.change(service, 'clear', [dict(id=identity)], now=START)
    assert not (service.jobs.root / 'task-history/ledger.json').exists()
    assert identity in {task['id'] for task in list_tasks(service)['tasks']}


@pytest.mark.parametrize('fail', [True, False])
def test_transport_lifetime_starts_cleanup_and_stops_before_service_shutdown(tmp_path, monkeypatch, fail):
    from types import SimpleNamespace
    from glyphs_mcp_sidecar import server
    events = []
    fixture = SimpleNamespace(lifecycle=SimpleNamespace(control_lock=None), close=lambda: events.append('close'))
    monkeypatch.setattr(server, 'load_or_create_token', lambda: 'fixture-token')
    monkeypatch.setattr(server, 'BridgeClient', lambda *_: None)
    monkeypatch.setattr(server, 'GlyphsCliWorker', lambda **_: None)
    monkeypatch.setattr(server, 'SidecarService', lambda *_, **__: fixture)
    def transport(**_):
        events.append('run')
        if fail: raise RuntimeError('Fixture transport stopped')
    monkeypatch.setattr(server, 'create_server', lambda *_, **__: SimpleNamespace(run=transport))
    def start(_):
        events.append('start')
        return lambda: events.append('stop')
    monkeypatch.setattr(task_history, 'start_cleanup', start)
    if fail:
        with pytest.raises(RuntimeError): server.main(['--jobs', str(tmp_path)])
    else: assert server.main(['--jobs', str(tmp_path)]) == 0
    assert events == ['start', 'run', 'stop', 'close']


def test_process_worker_runs_startup_and_periodic_cleanup_then_stops(typed_env, monkeypatch):
    service, *_ = typed_env
    called = Event(); again = Event(); calls = []
    def sweep(_):
        calls.append(1)
        (called if len(calls) == 1 else again).set()
    monkeypatch.setattr(task_history, 'cleanup', sweep)
    stop = task_history.start_cleanup(service, interval=.01)
    try: assert called.wait(2) and again.wait(2)
    finally: stop()
    before = len(calls)
    assert not Event().wait(.03) and len(calls) == before


def test_loopback_history_route_auth_and_bounds(typed_env):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from glyphs_mcp_sidecar.management import register_routes
    service, *_ = typed_env
    identity, _ = closed(typed_env)
    class Router:
        def __init__(self): self.routes = []
        def custom_route(self, path, methods):
            def decorate(callback): self.routes.append(Route(path, callback, methods=methods)); return callback
            return decorate
    router = Router(); register_routes(router, service, 'fixture-token')
    app = Starlette(routes=router.routes)
    async def check():
        payload = dict(action='clear', records=[record(service, identity)])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 1234)), base_url='http://local') as client:
            assert (await client.post('/internal/task-history', json=payload)).status_code == 403
            client.headers['Authorization'] = 'Bearer fixture-token'
            for value in [[], {}, dict(payload, extra=True), dict(payload, action='purge'), dict(payload, records=[{'id':'../outside'}]), dict(payload, records=[{'id':identity,'revision':'stale'}]), dict(payload, records=[{'id':identity}]*101)]:
                assert (await client.post('/internal/task-history', json=value)).status_code in {400, 409}
            assert (await client.post('/internal/task-history', content='x'*32769)).status_code == 400
            result = await client.post('/internal/task-history', json=payload)
            assert result.status_code == 200 and result.json()['data']['retentionDays'] == 30
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('192.168.0.2',1234)), base_url='http://local', headers={'Authorization':'Bearer fixture-token'}) as client:
            assert (await client.post('/internal/task-history', json=payload)).status_code == 403
    asyncio.run(check())
