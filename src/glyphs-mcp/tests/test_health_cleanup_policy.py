"""Health cleanup expires only proven unapplied, abandoned previews."""
from copy import deepcopy
import json
import time
from types import SimpleNamespace as NS

import pytest

from test_simple_v2_script_snapshots import native, run
from test_simple_v2_edit_workflow import wait, choose
from glyphs_mcp_bridge import preview_release
from glyphs_mcp_bridge.core import BridgeError
from glyphs_mcp_sidecar.bridge_client import BridgeClientError, BridgeClient
from glyphs_mcp_sidecar.health_cleanup import feedback, MAX_CANDIDATES


@pytest.fixture
def setup(native, monkeypatch):
    _, core, bridge, service, add = native
    font, identity = add()
    original = bridge.status
    health = dict(version=1, available=True, state='caution', reasons=['memory_pressure_warning'],
                  signals={'dispatch': {'pendingSeconds': 0}}, admission={'deferExpensiveWork': False})
    monkeypatch.setattr(bridge, 'status', lambda: dict(original(), previewReleaseVersion=1, health=deepcopy(health)))
    monkeypatch.setattr(bridge, 'release_preview', lambda key, doc, session:
        bridge.invoke(lambda value: preview_release.release(core, value, BridgeError),
                      dict(jobId=key, documentId=doc, bridgeSessionId=session)), raising=False)
    return font, identity, core, bridge, service, health


def preview(setup, key='preview', age=601, mode='preview'):
    _, identity, _, _, service, _ = setup
    value = service.edit_workflows.start(identity, kind='python_script', idempotency_key=key,
        mode=mode, auto_keep=False, options=dict(source='raise RuntimeError("preview must never run")',
            entrypoint='script', targets=[]))
    value = wait(service, value, 'waiting_run')
    record = service.edit_workflows.store.records[value['id']]
    old = time.time() - age
    service.edit_workflows.store.update(record, createdAt=old, lastActivityAt=old)
    return service.edit_workflows.get(value['id'])


def test_pressure_releases_abandoned_preview_without_edit_save_or_run(setup):
    font, _, core, _, service, _ = setup
    value = preview(setup)
    assert service.health_cleanup.run_once() == 1
    assert core.operation(value['jobId'])['status'] == 'cancelled'
    assert service.jobs.get(value['jobId'])['status'] == 'expired'
    assert service.edit_workflows.get(value['id'])['state'] == 'expired'
    assert font.glyphs['A'].width == 610
    assert not core._operations[value['jobId']].get('scriptSnapshot')
    assert service.health_cleanup.run_once() == 0


def test_recent_preview_and_polls_do_not_extend_original_idle_deadline(setup):
    _, _, core, _, service, _ = setup
    value = preview(setup, age=100)
    assert service.health_cleanup.run_once() == 0
    observed = service.get_status()['health']['cleanupCandidates'][0]
    assert observed['blockedBy'] == 'within_idle_timeout' and not observed['automatic']
    for _ in range(4): service.edit_workflows.get(value['id'])
    assert service.health_cleanup.run_once(now=time.time() + 501) == 1
    assert core.operation(value['jobId'])['status'] == 'cancelled'


def test_normal_load_respects_existing_day_expiry_instead_of_pressure_deadline(setup):
    _, _, core, _, service, health = setup
    value = preview(setup)
    health.update(state='normal', reasons=[])
    assert service.health_cleanup.run_once() == 0
    assert core.operation(value['jobId'])['status'] == 'ready'
    assert service.health_cleanup.run_once(now=time.time() + 86400) == 1


def test_font_warning_alone_does_not_shorten_preview_lifetime(setup):
    _, _, core, _, service, health = setup
    value = preview(setup)
    health['reasons'] = ['font_budget_reached']
    assert service.health_cleanup.run_once() == 0
    assert core.operation(value['jobId'])['status'] == 'ready'


@pytest.mark.parametrize('state,reason', [('caution', 'memory_pressure_warning'), ('paused', 'memory_pressure_critical')])
def test_pressure_cleanup_never_keeps_saves_or_restores_applied_recovery(setup, state, reason):
    font, identity, core, _, service, health = setup
    applied = run(service, identity)
    operation = core._operations[applied['jobId']]
    snapshot = operation['scriptSnapshot']
    health.update(state=state, reasons=[reason])
    assert service.health_cleanup.run_once(now=time.time() + 100 * 86400) == 0
    candidate = service.get_status()['health']['cleanupCandidates'][0]
    assert candidate['action'] == 'review_recovery' and candidate['preservesRecovery']
    assert not candidate['automatic'] and candidate['blockedBy'] == 'recovery_preserved'
    assert operation['scriptSnapshot'] is snapshot and font.glyphs['A'].width == 620


@pytest.mark.parametrize('status', ['interrupted', 'accept_uncertain', 'failed', 'ready'])
def test_uncertain_work_never_becomes_automatic_cleanup(setup, status):
    _, _, core, _, service, _ = setup
    value = preview(setup)
    service.jobs.update(value['jobId'], status=status,
        error=dict(code='restoration_unverified', details={'execution': 'uncertain', 'writeAttempted': True}))
    assert service.health_cleanup.run_once(now=time.time() + 100 * 86400) == 0
    candidate = service.get_status()['health']['cleanupCandidates'][0]
    assert candidate['blockedBy'] == 'outcome_uncertain' and not candidate['automatic']
    assert core.operation(value['jobId'])['status'] == 'ready'


def test_automatic_apply_intent_is_never_treated_as_abandoned_preview(setup):
    _, _, core, _, service, _ = setup
    value = preview(setup)
    record = service.edit_workflows.store.records[value['id']]
    service.edit_workflows.store.update(record, mode='apply', state='queued', scriptRunAuthorized=True)
    assert service.health_cleanup.run_once(now=time.time() + 100 * 86400) == 0
    assert core.operation(value['jobId'])['status'] == 'ready'


def test_native_guard_refuses_race_with_execution_without_even_cancelling_remaining_work(setup, monkeypatch):
    _, _, core, bridge, service, _ = setup
    value = preview(setup)
    original = bridge.release_preview
    operation = core._operations[value['jobId']]
    def race(*args):
        operation['status'] = 'applying'
        operation['cancelRequested'] = False
        return original(*args)
    monkeypatch.setattr(bridge, 'release_preview', race)
    assert service.health_cleanup.run_once() == 0
    assert operation['status'] == 'applying' and operation['cancelRequested'] is False
    assert service.jobs.get(value['jobId'])['status'] == 'ready'


def test_lost_release_reply_is_reconciled_idempotently_on_next_pass(setup, monkeypatch):
    font, _, core, bridge, service, _ = setup
    value = preview(setup)
    original = bridge.release_preview
    def lose(*args):
        original(*args)
        raise BridgeClientError('bridge_unavailable', 'Lost response')
    monkeypatch.setattr(bridge, 'release_preview', lose)
    assert service.health_cleanup.run_once() == 0
    assert service.jobs.get(value['jobId'])['status'] == 'ready'
    monkeypatch.setattr(bridge, 'release_preview', original)
    assert service.health_cleanup.run_once() == 1
    assert core.operation(value['jobId'])['status'] == 'cancelled' and font.glyphs['A'].width == 610


def test_old_bridge_exposes_candidate_without_attempting_unsafe_discard(setup, monkeypatch):
    _, _, core, bridge, service, _ = setup
    value = preview(setup)
    original = bridge.status
    monkeypatch.setattr(bridge, 'status', lambda: dict(original(), previewReleaseVersion=0))
    assert service.health_cleanup.run_once() == 0
    assert service.get_status()['health']['cleanupCandidates'][0]['blockedBy'] == 'bridge_update_required'
    assert core.operation(value['jobId'])['status'] == 'ready'


@pytest.mark.parametrize('settings', ['broken', '{"version":1,"enabled":"yes"}', '{"version":1,"pressurePreviewIdleSeconds":0}'])
def test_invalid_policy_is_fail_closed(setup, settings):
    _, _, core, _, service, _ = setup
    value = preview(setup)
    (service.jobs.root / 'health-cleanup-policy.json').write_text(settings)
    assert service.health_cleanup.run_once() == 0
    assert service.get_status()['health']['cleanupPolicy']['error']
    assert core.operation(value['jobId'])['status'] == 'ready'


def test_disabled_policy_does_not_release_even_old_previews(setup):
    _, _, core, _, service, _ = setup
    value = preview(setup)
    (service.jobs.root / 'health-cleanup-policy.json').write_text('{"version":1,"enabled":false}')
    assert service.health_cleanup.run_once(now=time.time() + 100 * 86400) == 0
    assert core.operation(value['jobId'])['status'] == 'ready'


def test_snapshot_and_feedback_are_passive_bounded_and_isolated(setup, monkeypatch):
    _, _, _, _, service, _ = setup
    preview(setup, age=100)
    service.health_cleanup.run_once()
    original = service.get_status
    observed = original()
    observed['health']['cleanupCandidates'][0]['documentId'] = 'tampered'
    def forbidden(*args, **kwargs): raise AssertionError('Passive reads must not scan or dispatch')
    monkeypatch.setattr(service.jobs, 'records', forbidden)
    monkeypatch.setattr(service.jobs, 'cleanup_records', forbidden)
    monkeypatch.setattr(service.health_cleanup, 'run_once', forbidden)
    for _ in range(100):
        result = original()
        assert result['health']['cleanupCandidates'][0]['documentId'] != 'tampered'
        assert len(result['health']['cleanupCandidates']) <= MAX_CANDIDATES
    # Feedback consumes already cached status; it carries the same candidates.
    payload = feedback(NS(get_status=lambda: result), {'ok': True, 'data': {}})
    assert payload['health']['cleanupCandidates'] == result['health']['cleanupCandidates']


def test_stale_or_cross_session_observation_cannot_advertise_automatic_permission(setup):
    _, _, _, _, service, _ = setup
    preview(setup, age=100)
    service.health_cleanup.run_once()
    result = {'bridge': {'reachable': True, 'bridgeSessionId': 'another-session'}}
    service.health_cleanup.annotate(result)
    assert result['health']['cleanupObservation']['stale']
    assert not any(row['automatic'] for row in result['health']['cleanupCandidates'])


def test_native_guard_checks_session_document_and_retained_recovery(setup):
    _, _, core, _, service, _ = setup
    value = preview(setup)
    request = dict(jobId=value['jobId'], documentId=value['document']['id'], bridgeSessionId=core.bridge_session_id)
    for changed in [dict(request, bridgeSessionId='old'), dict(request, documentId='another-font')]:
        with pytest.raises(BridgeError): preview_release.release(core, changed, BridgeError)
    operation = core._operations[value['jobId']]
    operation['resolved'] = [object()]
    with pytest.raises(BridgeError): preview_release.release(core, request, BridgeError)
    assert operation['status'] == 'ready'


def test_bridge_client_uses_atomic_release_route_and_exact_identity(monkeypatch):
    client = BridgeClient('http://127.0.0.1:1', 'test')
    calls = []
    monkeypatch.setattr(client, '_post', lambda path, body: calls.append((path, body)))
    client.release_preview('job_x', 'doc_x', 'session_x')
    assert calls == [('/v1/preview/release', dict(jobId='job_x', documentId='doc_x', bridgeSessionId='session_x'))]


def test_batch_limit_bounds_native_work_and_subsequent_pass_makes_progress(setup):
    _, _, core, _, service, _ = setup
    ids = []
    for index in range(6):
        job = service.jobs.create({'id': f'doc_{index}', 'familyName': 'Fixture'}, {'kind': 'width_delta'})
        service.jobs.update(job['id'], status='ready', resultKind='mutation', createdAt=time.time() - 900,
                            updatedAt=time.time() - 900, finishedAt=time.time() - 900)
        stored = service.jobs.get(job['id'])
        stored.update(updatedAt=time.time() - 900, finishedAt=time.time() - 900)
        service.jobs._write(stored)
        core._operations[job['id']] = dict(jobId=job['id'], documentId=f'doc_{index}', status='ready', prepared=True,
            patch={'changes': []}, index=0, applied=[], resolved=[], error=None)
        ids.append(job['id'])
    assert service.health_cleanup.run_once() == 4
    assert service.health_cleanup.run_once() == 2
    assert all(core.operation(key)['status'] == 'cancelled' for key in ids)


def test_compact_projection_never_copies_source_or_completed_history(setup):
    _, identity, _, _, service, _ = setup
    class NeverCopy:
        def __deepcopy__(self, memo): raise AssertionError('Source payload copied')
    with service.jobs._lock:
        for index in range(1000):
            service.jobs._remember(dict(id=f'job_history_{index}', status='completed', updatedAt=index,
                createdAt=index, document={'id': identity}, request={'kind': 'python_script', 'options': NeverCopy()}))
        for index in range(140):
            service.jobs._remember(dict(id=f'job_ready_{index}', status='ready', updatedAt=index,
                createdAt=index, resultKind='script', document={'id': identity},
                request={'kind': 'python_script', 'options': NeverCopy()}))
    rows, total = service.jobs.cleanup_records()
    assert len(rows) == 128 and total == 140
    assert all(row['request'] == {'kind': 'python_script'} for row in rows)
    assert 'options' not in json.dumps(rows)


def test_fresh_conversation_decision_during_observation_defers_cleanup(setup, monkeypatch):
    _, _, core, bridge, service, _ = setup
    value = preview(setup)
    original = bridge.status
    def decision():
        record = service.edit_workflows.store.records[value['id']]
        service.edit_workflows.store.update(record, lastActivityAt=time.time())
        return original()
    monkeypatch.setattr(bridge, 'status', decision)
    assert service.health_cleanup.run_once() == 0
    assert core.operation(value['jobId'])['status'] == 'ready'


def test_atomic_guard_is_reached_through_authenticated_http_route(setup):
    from glyphs_mcp_bridge.http_server import BridgeHTTPServer
    _, _, core, _, _, _ = setup
    value = preview(setup)
    server = BridgeHTTPServer(core, NS(call=lambda callback: callback()), token='cleanup-test', port=0)
    server.start()
    try:
        client = BridgeClient('http://127.0.0.1:' + str(server.address[1]), 'cleanup-test')
        for _ in range(2):
            result = client.release_preview(value['jobId'], value['document']['id'], core.bridge_session_id)
            assert result['status'] == 'cancelled' and not result['recoveryAvailable']
        with pytest.raises(BridgeClientError) as caught:
            client.release_preview(value['jobId'], value['document']['id'], 'old-session')
        assert caught.value.code == 'stale_bridge_session'
    finally:
        server.stop()
