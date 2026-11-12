"""Health reads are passive; admission preserves retry and recovery semantics."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import statistics
import sys
import time
from threading import Event
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
for component in ('protocol', 'bridge', 'sidecar'):
    sys.path.insert(0, str(ROOT / 'src' / component))

from glyphs_mcp_protocol import health as contract
from glyphs_mcp_bridge.health import HealthMonitor
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from glyphs_mcp_bridge.http_server import BridgeHTTPServer
from glyphs_mcp_sidecar.bridge_client import BridgeClient
from glyphs_mcp_sidecar.health import StatusCache, feedback
from glyphs_mcp_sidecar.service import SidecarService
from glyphs_mcp_sidecar.jobs import JobStore
from test_simple_v2_document_opening import setup, source
from test_simple_v2_edit_workflow import env, start, choose
from glyphs_mcp_sidecar.task_inventory import list_tasks


class Clock:
    value = 100.
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds


def monitor():
    clock = Clock()
    return HealthMonitor('session', clock=clock, wall=clock), clock


@pytest.mark.parametrize('count,state', [(0, 'normal'), (7, 'normal'), (8, 'caution'), (128, 'caution')])
def test_font_budget_never_blocks(count, state):
    value, _ = monitor()
    value.budget = 8
    value.record('documents', available=True, fontCount=count, complete=True)
    assert value.snapshot()['state'] == state
    value.admit(BridgeError)


def test_default_font_count_is_context_without_an_override():
    value, _ = monitor()
    value.record('documents', available=True, fontCount=16)
    snapshot = value.snapshot()
    assert snapshot['state'] == 'normal'
    assert snapshot['fontWarningThreshold'] is None


def test_footprint_trend_uses_only_recent_monotonic_samples():
    value, clock = monitor()
    for seconds, size in ((0, 100), (20, 200), (140, 300)):
        clock.value = 100 + seconds
        value.observe_footprint(dict(bytes=size), clock())
    footprint = value.snapshot()['signals']['footprint']
    assert footprint['growthBytes'] == 100
    assert footprint['growthWindowSeconds'] == 120
    clock.advance(121)
    value.observe_footprint(dict(bytes=400), clock())
    assert 'growthBytes' not in value.snapshot()['signals']['footprint']


@pytest.mark.parametrize('budget', [0, 129, True, 8.0, '8', None])
def test_invalid_budget_rejected(budget):
    with pytest.raises(ValueError): contract.font_budget(budget)


def test_unknown_is_not_healthy_and_footprint_never_blocks():
    value, _ = monitor()
    assert value.snapshot()['state'] == 'unknown'
    value.record('policy', available=True)
    assert value.snapshot()['state'] == 'unknown'  # A valid setting is not a health observation.
    value.record('footprint', available=True, bytes=10**15)
    assert not value.snapshot()['admission']['deferExpensiveWork']
    value.admit(BridgeError)


def test_critical_immediate_warning_recovery_and_oscillation():
    value, clock = monitor()
    value.record('pressure', available=True, value='critical', subscriptionActive=True)
    with pytest.raises(BridgeError) as caught: value.admit(BridgeError)
    assert caught.value.details['execution'] == 'not_started'
    assert caught.value.details['retryAfterSeconds'] == 15
    value.record('pressure', available=True, value='warning', subscriptionActive=True)
    clock.advance(29)
    assert value.snapshot()['state'] == 'paused'
    value.record('pressure', available=True, value='critical', subscriptionActive=True)
    value.record('pressure', available=True, value='normal', subscriptionActive=True)
    clock.advance(29)
    assert value.snapshot()['state'] == 'paused'
    clock.advance(1)
    value.record('footprint', available=True, bytes=100)
    assert value.snapshot()['state'] == 'normal'


def test_loss_of_pressure_observer_cannot_clear_critical():
    value, clock = monitor()
    value.record('pressure', available=True, value='critical')
    value.record('pressure', available=False, value='unknown', subscriptionActive=False)
    clock.advance(1000)
    assert value.snapshot()['state'] == 'paused'


def test_dispatch_queue_delay_is_not_execution_time_and_recovery_waits():
    value, clock = monitor()
    token = value.queued()
    clock.advance(3)
    assert value.snapshot()['state'] == 'caution'
    clock.advance(8)
    assert value.snapshot()['state'] == 'paused'
    value.serviced(token)
    assert value.snapshot()['signals']['dispatch']['schedulingSeconds'] == 11
    assert value.snapshot()['state'] == 'paused'
    clock.advance(30)
    value.record('footprint', available=True, bytes=100)
    assert value.snapshot()['state'] == 'normal'
    clock.advance(100)  # An executing operation is not an outstanding scheduling delay.
    assert value.snapshot()['state'] == 'normal'


def test_event_pressure_does_not_expire_like_sampled_footprint():
    value, clock = monitor()
    value.record('pressure', available=True, value='warning', subscriptionActive=True)
    value.record('footprint', available=True, bytes=100)
    clock.advance(60)
    snapshot = value.snapshot()
    assert snapshot['signals']['footprint']['stale']
    assert not snapshot['signals']['pressure']['stale']
    assert snapshot['state'] == 'caution'


def test_snapshot_copies_are_isolated_and_restart_drops_evidence():
    value, _ = monitor()
    value.record('documents', available=True, fontCount=8, complete=False)
    snapshot = value.snapshot()
    snapshot['signals']['documents']['fontCount'] = 0
    assert value.snapshot()['signals']['documents']['fontCount'] == 8
    restarted = HealthMonitor('new-session')
    assert restarted.snapshot()['signals'].get('documents') is None
    assert restarted.snapshot()['bridgeSessionId'] != value.snapshot()['bridgeSessionId']


@pytest.mark.performance
def test_cached_status_under_blocked_native_scheduler(tmp_path, request):
    host, core, _, service = setup(tmp_path)
    calls = []
    class Blocked:
        def call(self, callback):
            calls.append(callback)
            raise AssertionError('Status must not dispatch native work')
    server = BridgeHTTPServer(core, Blocked(), token='health-test', port=0)
    server.start()
    client = BridgeClient('http://127.0.0.1:' + str(server.address[1]), 'health-test')
    latencies = []
    try:
        def read(_):
            started = time.perf_counter()
            result = client.status()
            latencies.append(time.perf_counter() - started)
            return result
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(read, range(100)))
        assert all(r['health']['bridgeSessionId'] == core.bridge_session_id for r in results)
        assert not calls and not host.fonts
        if request.config.getoption('performance_gates'):
            assert sorted(latencies)[94] < .1
        service.bridge.status = lambda: pytest.fail('Passive sidecar status requested bridge status')
        service.get_job = lambda *_a, **_k: pytest.fail('Status reconciled a job')
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: service.get_status(), range(100)))
    finally:
        server.stop()
        service.close()


def test_deferred_open_has_no_native_attempt_and_same_key_can_retry(tmp_path):
    host, core, _, service = setup(tmp_path)
    clock = Clock()
    core.health = HealthMonitor(core.bridge_session_id, clock=clock, wall=clock)
    path = source(tmp_path)
    core.health.record('pressure', available=True, value='critical')
    with pytest.raises(Exception) as caught: service.open_document(str(path), 'same-key')
    assert caught.value.code == 'resource_pressure'
    assert not host.calls and not core._openings
    core.health.record('pressure', available=True, value='normal')
    clock.advance(30)
    core.health.record('footprint', available=True, bytes=100)
    first = service.open_document(str(path), 'same-key')
    core.health.record('pressure', available=True, value='critical')
    assert service.open_document(str(path), 'same-key')['id'] == first['id']
    assert service.open_document(str(path), 'another-key')['alreadyOpen']
    assert len(host.calls) == 1


def test_sidecar_cache_reads_never_collect_and_have_explicit_freshness():
    calls = []
    cache = StatusCache(lambda: calls.append(1) or dict(health=contract.unavailable()))
    assert not cache.snapshot()['statusReady']
    cache.refresh()
    for _ in range(100): cache.snapshot()
    assert len(calls) == 1
    assert cache.snapshot()['statusObservation']['ageSeconds'] is not None


def test_production_startup_serves_checking_without_waiting_for_busy_bridge(tmp_path):
    entered, release = Event(), Event()
    def busy_bridge():
        entered.set()
        assert release.wait(3)
        return dict(protocol=1, bridgeSessionId='ready')
    service = SidecarService(NS(status=busy_bridge), jobs=JobStore(tmp_path),
                            worker=NS(status=lambda: {}), initialize_status=False)
    assert not entered.is_set()
    service.status_cache.start()
    try:
        assert entered.wait(1)
        for _ in range(100):
            value = service.get_status()
            assert value['interface'] == 'glyphs-mcp-sidecar'
            assert value['bridge']['checking'] and not value['statusReady']
            assert not value['statusObservation']['stale']
        release.set()
        deadline = time.monotonic() + 2
        while not service.get_status()['statusReady'] and time.monotonic() < deadline: time.sleep(.01)
        assert service.get_status()['statusReady']
    finally:
        release.set()
        service.close()


def test_newer_admission_wins_over_slow_refresh_and_invalidates_old_session():
    old, _ = monitor()
    old.session = 'old-session'
    old.record('documents', available=True, fontCount=0)
    initial = dict(bridge=dict(reachable=True, bridgeSessionId='old-session'), health=old.snapshot(),
                   readCapabilities=['old'], jobKinds=['old'], statusReady=True)
    cache = StatusCache(lambda: deepcopy(initial))
    cache.refresh()
    entered, release = Event(), Event()
    def slow():
        entered.set()
        assert release.wait(2)
        return deepcopy(initial)
    cache.collect = slow
    newer, _ = monitor()
    newer.session = 'new-session'
    newer.record('pressure', available=True, value='critical')
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(cache.refresh)
        assert entered.wait(1)
        try:
            cache.observe_health(dict(bridgeSessionId='new-session', health=newer.snapshot(),
                healthCapabilities=[contract.SNAPSHOT, contract.ADMISSION]))
        finally:
            release.set()
        pending.result(timeout=2)
    value = cache.snapshot()
    assert value['health']['state'] == 'paused'
    assert value['health']['bridgeSessionId'] == value['bridge']['bridgeSessionId'] == 'new-session'
    assert not value['statusReady'] and value['bridge']['checking']
    assert not value['readCapabilities'] and not value['jobKinds']


def test_bridge_transport_loss_cannot_clear_known_pressure(tmp_path):
    value, _clock = monitor()
    value.record('pressure', available=True, value='critical')
    bridge = NS(status=lambda: dict(bridgeSessionId='session', health=value.snapshot(),
        healthCapabilities=[contract.SNAPSHOT, contract.ADMISSION]))
    service = SidecarService(bridge, jobs=JobStore(tmp_path), worker=NS(status=lambda: {}))
    bridge.status = lambda: (_ for _ in ()).throw(OSError('offline'))
    service.status_cache.refresh()
    assert service.get_status()['health']['state'] == 'paused'
    assert not service.get_status()['bridge']['reachable']
    with pytest.raises(Exception) as caught: service.admit_expensive()
    assert caught.value.code == 'resource_pressure'
    assert caught.value.details['execution'] == 'not_started'
    restarted = HealthMonitor('restarted')
    bridge.status = lambda: dict(bridgeSessionId='restarted', health=restarted.snapshot(),
        healthCapabilities=[contract.SNAPSHOT, contract.ADMISSION])
    service.status_cache.refresh()
    assert service.get_status()['health']['state'] == 'unknown'
    service.close()


def test_signal_age_continues_across_failed_refresh(monkeypatch):
    value, clock = monitor()
    value.record('pressure', available=True, value='critical')
    value.record('footprint', available=True, bytes=100)
    monkeypatch.setattr('glyphs_mcp_sidecar.health.time.monotonic', clock)
    cache = StatusCache(lambda: dict(bridge=dict(reachable=True), health=value.snapshot(),
        healthCapabilities=[contract.SNAPSHOT, contract.ADMISSION]))
    cache.refresh()
    clock.advance(60)
    cache.collect = lambda: dict(bridge=dict(reachable=False), health=contract.unavailable())
    cache.refresh()
    snapshot = cache.snapshot()
    assert snapshot['health']['state'] == 'paused'
    assert snapshot['health']['signals']['footprint']['ageSeconds'] >= 60
    assert snapshot['health']['signals']['footprint']['stale']


def test_advisory_is_outside_data_and_is_model_visible():
    value, _ = monitor()
    value.record('pressure', available=True, value='warning')
    service = NS(get_status=lambda: dict(health=value.snapshot()))
    payload = dict(ok=True, data=[dict(id='doc')])
    original = deepcopy(payload['data'])
    feedback(service, payload)
    assert payload['data'] == original
    assert 'Routine edits can continue' in payload['health']['text']
    assert 'process_sequentially' not in payload['health']['recommendedActions']
    assert not contract.advisory(contract.unavailable())


@pytest.mark.parametrize('work,phrase', [
    ('routine', 'Routine edits can continue'),
    ('document', 'Reuse open fonts'),
    ('export', 'Run exports or feature compiles one at a time'),
    ('snapshot', 'Run one whole-font snapshot or restore at a time'),
    ('comparison', 'Run one font comparison at a time'),
])
def test_pressure_guidance_matches_the_work_without_changing_admission(work, phrase):
    value, _ = monitor()
    value.record('pressure', available=True, value='warning')
    service = NS(get_status=lambda: dict(health=value.snapshot()))
    result = feedback(service, dict(ok=True, data={}), work=work)['health']
    assert phrase in result['text']
    assert not result['admission']['deferExpensiveWork']
    value.record('pressure', available=True, value='critical')
    result = feedback(service, dict(ok=True, data={}), work=work)['health']
    assert result['recommendedActions'] == ['defer_expensive_work']
    assert result['admission']['deferExpensiveWork']


def test_bounded_pending_dispatch_tracker():
    value, clock = monitor()
    for _ in range(1000): value.queued()
    assert len(value.pending) == 128
    clock.advance(3600)
    assert value.snapshot()['state'] == 'paused'


def test_observer_coalesces_redraw_storm_and_skips_missed_intervals():
    value, clock = monitor()
    queue = []
    class Resources:
        def __init__(self, callback): pass
        def subscribe(self): raise OSError('synthetic unavailable source')
        def footprint(self): return dict(bytes=100, processId=1, processStarted=1)
        def close(self): pass
    value.start(NS(health_inventory=lambda: dict(fontCount=0, complete=True)),
                queue.append, lambda: True, resources_factory=Resources)
    try:
        deadline = time.monotonic() + 2
        while not queue and time.monotonic() < deadline: time.sleep(.01)
        assert len(queue) == 1
        for _ in range(1000): value.invalidate_documents()
        clock.advance(3600)
        # Let the real coordinator tick with a one-hour virtual scheduling gap.
        time.sleep(1.1)
        assert len(queue) == 1 and value.observation_pending
        snapshot = value.snapshot()
        assert snapshot['state'] == 'paused'
        assert snapshot['signals']['pressure']['available'] is False
        assert snapshot['signals']['footprint']['available'] is True
        queue.pop()()
        assert not value.observation_pending
    finally:
        value.close()


def test_darwin_footprint_and_subscription_shutdown():
    if sys.platform != 'darwin': pytest.skip('Darwin only')
    from glyphs_mcp_bridge.health_darwin import DarwinResources
    resources = DarwinResources(lambda _: None)
    footprint = resources.footprint()
    assert footprint['bytes'] > 0 and footprint['processStarted'] > 0
    try:
        resources.subscribe()
    finally:
        resources.close()


def test_health_wait_preserves_identity_preview_and_cancellation(env, monkeypatch):
    service, bridge, worker, _ = env
    value, _clock = monitor()
    value.record('pressure', available=True, value='critical')
    monkeypatch.setattr(bridge, 'status', lambda: dict(health=value.snapshot(),
        healthCapabilities=[contract.SNAPSHOT, contract.ADMISSION], protocol=1))
    service.status_cache.refresh()
    coordinator = service.edit_workflows
    monkeypatch.setattr(coordinator, '_start_runner', lambda: None)
    waiting = start(env, mode='preview')
    assert waiting['state'] == 'queued' and waiting['queue']['automaticResume']
    assert waiting['queue']['reason'] == 'resource_pressure'
    assert 'review' in waiting['message']
    assert start(env, mode='preview')['id'] == waiting['id']
    assert not worker.calls and not bridge.applies
    task = list_tasks(service)['tasks'][0]
    assert task['taskStatus'] == 'waiting'
    assert task['blockers'][0]['reason'] == 'resource_pressure'
    revision = waiting['revision']
    for _ in range(10): assert coordinator.get(waiting['id'])['revision'] == revision
    assert choose(service, waiting, 'cancel')['state'] == 'cancelled'
    assert not worker.calls and not bridge.applies


def test_health_wait_resumes_once_after_recovery(env, monkeypatch):
    service, bridge, worker, _ = env
    value, clock = monitor()
    original = bridge.status
    monkeypatch.setattr(bridge, 'status', lambda: dict(**original(), health=value.snapshot(),
        healthCapabilities=[contract.SNAPSHOT, contract.ADMISSION]))
    service.status_cache.refresh()
    coordinator = service.edit_workflows
    monkeypatch.setattr(coordinator, '_start_runner', lambda: None)
    value.record('pressure', available=True, value='critical')
    waiting = start(env)
    record = coordinator._find(waiting['id'])
    coordinator._guard(record, lambda: coordinator._advance(record))
    assert not worker.calls
    value.record('pressure', available=True, value='normal')
    clock.advance(30)
    value.record('footprint', available=True, bytes=100)
    record['queueRetryAt'] = 0
    deadline = time.monotonic() + 3
    while record['state'] != 'applied' and time.monotonic() < deadline:
        coordinator._guard(record, lambda: coordinator._advance(record))
        time.sleep(.01)
    assert record['state'] == 'applied'
    assert worker.calls == 1 and bridge.applies == 1


def test_pressure_does_not_change_existing_action_tokens(env, monkeypatch):
    service, bridge, _worker, _ = env
    value, _clock = monitor()
    original = bridge.status
    monkeypatch.setattr(bridge, 'status', lambda: dict(**original(), health=value.snapshot(),
        healthCapabilities=[contract.SNAPSHOT, contract.ADMISSION]))
    service.status_cache.refresh()
    waiting = start(env, mode='preview')
    deadline = time.monotonic() + 3
    while waiting['state'] != 'ready' and time.monotonic() < deadline:
        waiting = service.edit_workflows.get(waiting['id'])
        time.sleep(.01)
    assert waiting['state'] == 'ready'
    before = [(a['action'], a['token']) for a in waiting['actions']]
    value.record('pressure', available=True, value='critical')
    payload = dict(ok=True, data=deepcopy(waiting))
    service.status_cache.refresh()
    feedback(service, payload)
    assert payload['health']['state'] == 'paused'
    assert [(a['action'], a['token']) for a in payload['data']['actions']] == before
    assert payload['data']['revision'] == waiting['revision']
