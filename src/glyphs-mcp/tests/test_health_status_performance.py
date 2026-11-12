"""Status/health latency gates under the contention seen in a live Glyphs session."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event
import time
import math

import httpx
from fastmcp import Client
import pytest

from glyphs_mcp_sidecar.server import create_server
from test_simple_v2_document_opening import setup
from test_simple_v2_edit_workflow import env as typed_env


@pytest.mark.performance
def test_status_and_health_stay_responsive_when_request_workers_are_occupied(tmp_path, request):
    host, core, _, service = setup(tmp_path)
    core.health.record('pressure', available=True, value='warning', subscriptionActive=True)
    service.status_cache.refresh()
    release, occupied = Event(), Event()
    samples = {'mcp': [], 'companion': []}

    async def exercise():
        loop = asyncio.get_running_loop()
        pool = ThreadPoolExecutor(max_workers=1)
        loop.set_default_executor(pool)
        mcp = create_server(service, control_token='x' * 32)
        app = mcp.http_app(stateless_http=True)
        def block():
            occupied.set()
            release.wait(10)
        try:
            async with app.lifespan(app), Client(mcp) as agent:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                        base_url='http://local', headers={'Authorization': 'Bearer ' + 'x' * 32}) as companion:
                    worker = loop.run_in_executor(None, block)
                    while not occupied.is_set(): await asyncio.sleep(.001)
                    gate = asyncio.Semaphore(4)
                    async def read(index):
                        async with gate:
                            start = time.perf_counter()
                            if index % 2:
                                result = (await companion.get('/internal/status')).json()
                                name = 'companion'
                            else:
                                result = (await agent.call_tool('get_status', {})).data
                                name = 'mcp'
                            samples[name].append(time.perf_counter() - start)
                            assert result['ok'] and result['data']['health']['state'] == 'caution'
                            assert result['data']['health']['bridgeSessionId'] == core.bridge_session_id
                    # Both transports must work while the only request worker
                    # stays occupied. A timeout cancels reads, never native work.
                    await asyncio.wait_for(asyncio.gather(*(read(i) for i in range(100))), 5)
                    release.set()
                    await worker
        finally:
            release.set()
            pool.shutdown(wait=True)

    try:
        asyncio.run(exercise())
        assert not host.fonts
        metrics = {}
        for name, times in samples.items():
            p95 = sorted(times)[math.ceil(len(times) * .95) - 1]
            if request.config.getoption('performance_gates'):
                assert p95 < .1, (name, p95)
            metrics[name] = {'requests': len(times), 'p95Milliseconds': p95 * 1000}
        (tmp_path / 'status-health-performance.json').write_text(json.dumps(metrics))
    finally:
        release.set()
        service.close()


@pytest.mark.performance
def test_busy_job_store_cannot_stall_fresh_health_publication(tmp_path, request):
    _, core, _, service = setup(tmp_path)
    original = service.get_status()['activity']
    core.health.record('pressure', available=True, value='warning', subscriptionActive=True)
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        with service.jobs._lock:
            start = time.perf_counter()
            result = pool.submit(service.status_cache.refresh).result(timeout=.5)
            if request.config.getoption('performance_gates'):
                assert time.perf_counter() - start < .1
            assert result['health']['state'] == 'caution'
            assert result['activity'] == {**original, 'stale': True}
            # Readers keep the new health evidence, even while activity is stale.
            assert service.get_status()['health']['revision'] == result['health']['revision']
        service.status_cache.refresh()
        assert not service.get_status()['activity'].get('stale', False)
    finally:
        pool.shutdown(wait=True)
        service.close()


@pytest.mark.integration
def test_companion_history_sync_workflow_intake_and_health_progress_together(typed_env):
    from test_simple_v2_task_history import closed, record
    from glyphs_mcp_protocol.health import SNAPSHOT, ADMISSION
    service, bridge, _, source = typed_env
    identity, _ = closed(typed_env)
    cleared = record(service, identity)
    bridge.core.health.record('documents', available=True, fontCount=0, complete=True)
    original = bridge.status
    bridge.status = lambda: dict(**original(), bridgeSessionId=bridge.core.bridge_session_id,
                                health=bridge.core.health.snapshot(), healthCapabilities=[SNAPSHOT, ADMISSION])
    service.status_cache.refresh()

    async def exercise():
        mcp = create_server(service, control_token='x' * 32)
        app = mcp.http_app(stateless_http=True)
        async with app.lifespan(app), Client(mcp) as agent:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local',
                    headers={'Authorization': 'Bearer ' + 'x' * 32}) as companion:
                arguments = dict(document_id='doc_1', kind='width_delta', delta=8,
                                 mode='preview', idempotency_key='concurrent-history-intake', auto_keep=False)
                intake, history, status = await asyncio.wait_for(asyncio.gather(
                    agent.call_tool('start_edit_workflow', arguments),
                    companion.post('/internal/task-history', json={'action': 'clear', 'records': [cleared]}),
                    companion.get('/internal/status')), 5)
                assert intake.data['ok'] and history.json()['ok'] and status.json()['ok']
                assert status.json()['data']['health']['available']
                again = await agent.call_tool('start_edit_workflow', arguments)
                assert again.data['data']['id'] == intake.data['data']['id']
    asyncio.run(exercise())
    assert bridge.applies == 0 and not bridge.adapter.save_calls
    assert bridge.adapter.value == 600 and source.read_text() == '600'
