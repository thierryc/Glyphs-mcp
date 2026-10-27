"""Waiting is durable intake, not a replay of an uncertain native write."""
from concurrent.futures import ThreadPoolExecutor
import asyncio
from threading import Event
import time

import pytest

from test_simple_v2_edit_workflow import env, start, choose, wait
from test_simple_v2_script_snapshots import native
from glyphs_mcp_sidecar.bridge_client import BridgeClientError
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.service import SidecarService, ServiceError
from glyphs_mcp_sidecar.task_inventory import list_tasks
from glyphs_mcp_sidecar import workflow_queue


def script(service, document, key, mode='apply'):
    return service.edit_workflows.start(document, kind='python_script', mode=mode,
        idempotency_key=key, auto_keep=False,
        options=dict(source='font.glyphs["A"].width=700', entrypoint='script', targets=[]))


def tick(service, value):
    coordinator = service.edit_workflows
    with coordinator.lock:
        record = coordinator._find(value['id'])
        coordinator._guard(record, lambda: coordinator._advance(record))
    return coordinator.get(value['id'])


def until(service, value, state):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        value = tick(service, value)
        if value['state'] == state:
            return value
        time.sleep(.01)
    raise AssertionError(value)


def occupy(coordinator, entered, release):
    with coordinator.lock:
        entered.set()
        assert release.wait(4)


def test_intake_inspection_and_cancel_do_not_wait_for_native_dispatch(env, monkeypatch):
    service, bridge, worker, _ = env
    coordinator = service.edit_workflows
    monkeypatch.setattr(coordinator, '_start_runner', lambda: None)
    def forbidden():
        raise AssertionError('Queue intake must not call the occupied Glyphs main thread')
    monkeypatch.setattr(bridge, 'status', forbidden)
    monkeypatch.setattr(bridge, 'documents', forbidden)
    entered, release = Event(), Event()
    with ThreadPoolExecutor() as pool:
        busy = pool.submit(occupy, coordinator, entered, release)
        assert entered.wait(1)
        try:
            value = pool.submit(start, env).result(timeout=1)
            assert value['state'] == 'queued' and value['queue']['automaticResume']
            assert 'automatically' in value['message']
            assert pool.submit(coordinator.get, value['id']).result(timeout=1)['id'] == value['id']
            inventory = pool.submit(list_tasks, service).result(timeout=1)
            assert inventory['tasks'][0]['taskStatus'] == 'waiting'
            assert start(env)['id'] == value['id']  # Lost intake reply is safe to retry.
            cancelled = pool.submit(choose, service, value, 'cancel').result(timeout=1)
            assert cancelled['state'] == 'cancelled'
            assert choose(service, value, 'cancel')['state'] == 'cancelled'
            assert not worker.calls and not bridge.applies
        finally:
            release.set()
        busy.result(timeout=1)


def test_mcp_accepts_and_cancels_while_another_call_is_waiting_on_glyphs(env, monkeypatch):
    from fastmcp import Client
    from glyphs_mcp_sidecar.server import create_server
    service, bridge, _, _ = env
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    entered, release = Event(), Event()
    documents = bridge.documents
    def blocked_documents():
        entered.set()
        assert release.wait(4)
        return documents()
    monkeypatch.setattr(bridge, 'documents', blocked_documents)

    async def exercise():
        async with Client(create_server(service)) as client:
            first = asyncio.create_task(client.call_tool('start_edit_workflow', dict(
                document_id='doc_1', kind='width_delta', delta=8, idempotency_key='first')))
            try:
                assert await asyncio.to_thread(entered.wait, 1)
                second = await asyncio.wait_for(client.call_tool('start_edit_workflow', dict(
                    document_id='doc_1', kind='width_delta', delta=8, idempotency_key='second')), 1)
                value = second.structured_content['data']
                assert value['state'] == 'queued'
                action = next(a for a in value['actions'] if a['action'] == 'cancel')
                cancelled = await asyncio.wait_for(client.call_tool('respond_edit_workflow', dict(
                    workflow_id=value['id'], expected_revision=value['revision'], action_token=action['token'])), 1)
                assert cancelled.structured_content['data']['state'] == 'cancelled'
            finally:
                release.set()
                await first
    asyncio.run(exercise())


def test_fifo_waits_for_decisions_and_independent_font_overtakes(native, monkeypatch):
    _, core, _, service, add = native
    coordinator = service.edit_workflows
    monkeypatch.setattr(coordinator, '_start_runner', lambda: None)
    _, first_id = add(); _, other_id = add()
    first = until(service, script(service, first_id, 'first', 'preview'), 'waiting_run')
    second = script(service, first_id, 'second', 'preview')
    third = script(service, first_id, 'third', 'preview')
    third = tick(service, third)
    assert third['state'] == 'queued' and third['blocker']['workflowId'] == second['id']
    second = until(service, second, 'blocked_proposal')
    third = tick(service, third)
    assert third['blocker']['wait'] == 'decision' and not third['poll']
    assert 'decision' in third['message'] and not third['queue']['automaticResume']
    inventory = {t['id']: t for t in list_tasks(service)['tasks']}
    assert second['id'] in inventory[third['id']]['blockedBy']
    other = until(service, script(service, other_id, 'other'), 'applied')
    snapshot = core._operations[other['jobId']]['scriptSnapshot']
    choose(service, first, 'cancel')
    first = until(service, first, 'cancelled')
    second = until(service, second, 'waiting_run')
    third = tick(service, third)
    assert third['state'] == 'blocked_proposal' and third['blockerId'] == second['jobId']
    assert core._operations[other['jobId']]['scriptSnapshot'] is snapshot
    assert third['jobId'] is None


def test_queue_automatically_resumes_without_releasing_another_fonts_recovery(native, monkeypatch):
    _, core, _, service, add = native
    _, first_id = add(); _, second_id = add()
    first = until(service, script(service, first_id, 'first'), 'applied')
    snapshot = core._operations[first['jobId']]['scriptSnapshot']
    coordinator = service.edit_workflows
    entered, release = Event(), Event()
    with ThreadPoolExecutor() as pool:
        busy = pool.submit(occupy, coordinator, entered, release)
        assert entered.wait(1)
        try:
            second = script(service, second_id, 'second')
            assert second['state'] == 'queued'
        finally:
            release.set()
        busy.result(timeout=1)
    second = wait(service, second, 'applied')  # Real supervisor resumes it.
    assert core._operations[first['jobId']]['scriptSnapshot'] is snapshot
    assert core._operations[first['jobId']]['status'] == 'applied'
    assert second['savedVersion']['available']


def test_all_waiters_follow_only_the_authoritative_restoration_binding(native, monkeypatch):
    _, _, _, service, add = native
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    _, identity = add()
    first = until(service, script(service, identity, 'first'), 'applied')
    second = until(service, script(service, identity, 'second', 'preview'), 'blocked_review')
    third = script(service, identity, 'third', 'preview')
    assert third['state'] == 'queued' and third['queue']['automaticResume'] is False
    restored = choose(service, first, 'restore_saved_script')
    assert restored['document']['id'] != identity
    second = until(service, second, 'waiting_run')
    third = tick(service, third)
    assert third['document']['id'] == second['document']['id'] == restored['document']['id']
    assert third['state'] == 'blocked_proposal'
    second = until(service, choose(service, second, 'cancel'), 'cancelled')
    third = until(service, third, 'waiting_run')
    assert third['document']['id'] == restored['document']['id']


def test_queue_offline_then_ready_preserves_preview_authorization(native, monkeypatch):
    _, _, bridge, service, add = native
    font, identity = add()
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    documents = bridge.documents
    def offline():
        raise BridgeClientError('bridge_unavailable', 'Glyphs is not ready')
    monkeypatch.setattr(bridge, 'documents', offline)
    value = script(service, identity, 'offline', 'preview')
    assert value['state'] == 'queued' and 'requires your review' in value['message']
    assert tick(service, value)['state'] == 'queued'
    monkeypatch.setattr(bridge, 'documents', documents)
    value = until(service, value, 'waiting_run')
    assert font.glyphs['A'].width == 610
    assert tick(service, value)['state'] == 'waiting_run'


def test_known_busy_run_retries_same_prepared_job_and_keeps_explicit_authorization(native, monkeypatch):
    _, core, bridge, service, add = native
    font, identity = add()
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    value = until(service, script(service, identity, 'run', 'preview'), 'waiting_run')
    run = bridge.run_script
    calls = []
    def once_busy(request):
        calls.append(request['jobId'])
        if len(calls) == 1:
            raise BridgeClientError('document_busy', 'Native operation is finishing')
        return run(request)
    monkeypatch.setattr(bridge, 'run_script', once_busy)
    value = choose(service, value, 'run_script')
    assert value['state'] == 'queued'
    value = until(service, value, 'applied')
    assert calls == [value['jobId'], value['jobId']]
    assert font.glyphs['A'].width == 700
    assert core._operations[value['jobId']]['scriptResult']['executedTargets'] == 0


def test_unknown_native_write_is_never_queued_or_replayed(native, monkeypatch):
    _, _, bridge, service, add = native
    _, identity = add()
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    value = until(service, script(service, identity, 'unknown', 'preview'), 'waiting_run')
    calls = []
    def lost(request):
        calls.append(request)
        raise BridgeClientError('bridge_timeout', 'Reply lost', {'execution': 'uncertain'})
    monkeypatch.setattr(bridge, 'run_script', lost)
    value = choose(service, value, 'run_script')
    assert value['state'] == 'uncertain' and not value['queue']
    for _ in range(3):
        tick(service, value)
    assert len(calls) == 1


def test_busy_preparation_retries_only_read_only_preparation(native, monkeypatch):
    _, _, bridge, service, add = native
    font, identity = add()
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    review = bridge.review_script
    attempts = []
    def once_busy(request):
        attempts.append(request['jobId'])
        if len(attempts) == 1:
            raise BridgeClientError('document_busy', 'Another native operation is finishing')
        return review(request)
    monkeypatch.setattr(bridge, 'review_script', once_busy)
    value = until(service, script(service, identity, 'prepare', 'preview'), 'waiting_run')
    assert len(attempts) == 2 and attempts[0] != attempts[1]
    assert font.glyphs['A'].width == 610
    assert {j['status'] for j in service.jobs.records()} == {'failed', 'ready'}


def test_busy_typed_apply_resumes_without_duplicate_preparation(env, monkeypatch):
    service, bridge, worker, _ = env
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    value = until(service, start(env, mode='preview'), 'ready')
    apply = bridge.apply
    attempts = []
    def once_busy(patch):
        attempts.append(patch['jobId'])
        if len(attempts) == 1:
            raise BridgeClientError('document_busy', 'Glyphs is busy')
        return apply(patch)
    monkeypatch.setattr(bridge, 'apply', once_busy)
    value = choose(service, value, 'apply')
    assert value['state'] == 'queued'
    value = until(service, value, 'applied')
    assert attempts == [value['jobId'], value['jobId']]
    assert worker.calls == bridge.applies == 1 and bridge.adapter.value == 608


def test_stale_prepared_request_is_not_reprepared_or_applied_after_waiting(native, monkeypatch):
    _, _, bridge, service, add = native
    font, identity = add()
    monkeypatch.setattr(service.edit_workflows, '_start_runner', lambda: None)
    value = until(service, script(service, identity, 'stale', 'preview'), 'waiting_run')
    run = bridge.run_script
    monkeypatch.setattr(bridge, 'run_script', lambda _: (_ for _ in ()).throw(
        BridgeClientError('document_busy', 'Glyphs is busy')))
    value = choose(service, value, 'run_script')
    assert value['state'] == 'queued'
    monkeypatch.setattr(bridge, 'run_script', run)
    font.parent.updateChangeCount_(0)
    value = tick(service, value)
    assert value['state'] == 'outdated'
    assert font.glyphs['A'].width == 610


def test_queued_prepared_run_can_be_cancelled_while_dispatch_is_busy(native, monkeypatch):
    _, _, bridge, service, add = native
    font, identity = add()
    coordinator = service.edit_workflows
    monkeypatch.setattr(coordinator, '_start_runner', lambda: None)
    value = until(service, script(service, identity, 'cancel-ready', 'preview'), 'waiting_run')
    monkeypatch.setattr(bridge, 'run_script', lambda _: (_ for _ in ()).throw(
        BridgeClientError('document_busy', 'Glyphs is busy')))
    value = choose(service, value, 'run_script')
    entered, release = Event(), Event()
    with ThreadPoolExecutor() as pool:
        busy = pool.submit(occupy, coordinator, entered, release)
        assert entered.wait(1)
        try:
            value = choose(service, value, 'cancel')
            assert 'will not run' in value['message']
        finally:
            release.set()
        busy.result(timeout=1)
    value = until(service, value, 'cancelled')
    assert font.glyphs['A'].width == 610
    assert service.jobs.get(value['jobId'])['status'] == 'discarded'


def test_waiting_reads_and_cancel_never_call_glyphs_even_before_supervisor_tick(native, monkeypatch):
    _, _, bridge, service, add = native
    _, identity = add()
    coordinator = service.edit_workflows
    monkeypatch.setattr(coordinator, '_start_runner', lambda: None)
    value = until(service, script(service, identity, 'passive', 'preview'), 'waiting_run')
    monkeypatch.setattr(bridge, 'run_script', lambda _: (_ for _ in ()).throw(
        BridgeClientError('document_busy', 'Glyphs is busy')))
    value = choose(service, value, 'run_script')
    calls = []
    def forbidden(*args):
        calls.append(args)
        raise AssertionError('A queued read/cancel must not call Glyphs')
    monkeypatch.setattr(bridge, 'status', forbidden)
    monkeypatch.setattr(bridge, 'documents', forbidden)
    monkeypatch.setattr(service, 'discard_job', forbidden)
    value = coordinator.get(value['id'])
    cancelled = choose(service, value, 'cancel')
    assert 'will not run' in cancelled['message']
    assert not calls


def test_cancel_wins_the_race_with_queued_typed_dispatch(env, monkeypatch):
    from glyphs_mcp_sidecar import script_service
    service, bridge, _, _ = env
    coordinator = service.edit_workflows
    monkeypatch.setattr(coordinator, '_start_runner', lambda: None)
    value = until(service, start(env, mode='preview'), 'ready')
    apply = bridge.apply
    monkeypatch.setattr(bridge, 'apply', lambda _: (_ for _ in ()).throw(
        BridgeClientError('document_busy', 'Glyphs is busy')))
    value = choose(service, value, 'apply')
    monkeypatch.setattr(bridge, 'apply', apply)
    blockers = script_service.execution_blockers
    entered, release = Event(), Event()
    def blocked_check(*args, **kwargs):
        if len(args) > 1 and args[1] == value['jobId']:
            entered.set()
            assert release.wait(3)
        return blockers(*args, **kwargs)
    monkeypatch.setattr(script_service, 'execution_blockers', blocked_check)
    with ThreadPoolExecutor() as pool:
        dispatch = pool.submit(tick, service, value)
        assert entered.wait(1)
        try:
            value = choose(service, value, 'cancel')
            assert 'will not run' in value['message']
        finally:
            release.set()
        dispatch.result(timeout=1)
    until(service, value, 'cancelled')
    assert bridge.applies == 0 and bridge.adapter.value == 600


def test_cancel_during_admission_cannot_start_an_edit(env, monkeypatch):
    service, bridge, worker, _ = env
    coordinator = service.edit_workflows
    monkeypatch.setattr(coordinator, '_start_runner', lambda: None)
    arguments = dict(kind='width_delta', delta=8, glyphs=None, options=None)
    value = workflow_queue.enqueue(coordinator, 'doc_1', arguments, {'kind': 'width_delta', 'delta': 8},
                                   'apply', 'admission', False)
    entered, release = Event(), Event()
    documents = bridge.documents
    def blocked_documents():
        entered.set()
        assert release.wait(3)
        return documents()
    monkeypatch.setattr(bridge, 'documents', blocked_documents)
    with ThreadPoolExecutor() as pool:
        admission = pool.submit(tick, service, value)
        assert entered.wait(1)
        try:
            current = coordinator.get(value['id'])
            cancelled = choose(service, current, 'cancel')
            assert 'will not run' in cancelled['message']
        finally:
            release.set()
        assert admission.result(timeout=2)['state'] == 'cancelled'
    assert worker.calls == bridge.applies == 0


def test_bounded_queue_validates_intake_and_does_not_duplicate_retry(env, monkeypatch):
    service = env[0]
    coordinator = service.edit_workflows
    monkeypatch.setattr(coordinator, '_start_runner', lambda: None)
    monkeypatch.setattr(workflow_queue, 'MAX_QUEUED', 2)
    entered, release = Event(), Event()
    with ThreadPoolExecutor() as pool:
        busy = pool.submit(occupy, coordinator, entered, release)
        assert entered.wait(1)
        try:
            first = start(env)
            second = coordinator.start('doc_1', kind='width_delta', delta=9, idempotency_key='second')
            assert start(env)['id'] == first['id']
            with pytest.raises(ServiceError) as failure:
                coordinator.start('doc_1', kind='width_delta', delta=8, idempotency_key='third')
            assert failure.value.code == 'queue_full'
            with pytest.raises(ServiceError) as failure:
                coordinator.start('doc_1', kind='not_a_kind', idempotency_key='invalid')
            assert failure.value.code != 'queue_full'
            with pytest.raises(ServiceError) as failure:
                coordinator.start('doc_1', kind='checkpoint_restore', options={'revision': 'HEAD'},
                                  idempotency_key='invalid-revision')
            assert failure.value.code == 'invalid_request'
            with pytest.raises(ServiceError) as failure:
                coordinator.start('doc_1', kind='width_delta', delta=9, idempotency_key='request1')
            assert failure.value.code == 'idempotency_conflict'
            assert len(coordinator.store.records) == 2
        finally:
            release.set()
        busy.result(timeout=1)


def test_restart_does_not_execute_queued_authorization(env, monkeypatch):
    service, bridge, worker, _ = env
    coordinator = service.edit_workflows
    monkeypatch.setattr(coordinator, '_start_runner', lambda: None)
    arguments = dict(kind='width_delta', delta=8, glyphs=None, options=None)
    value = workflow_queue.enqueue(coordinator, 'doc_1', arguments, {'kind': 'width_delta', 'delta': 8},
                                   'apply', 'restart', False)
    replacement = SidecarService(bridge, jobs=JobStore(service.jobs.root), worker=worker)
    try:
        restored = replacement.edit_workflows.get(value['id'])
        assert restored['state'] == 'interrupted' and not restored['queue']
        assert not replacement.edit_workflows.store.records[value['id']]['scriptRunAuthorized']
        assert not worker.calls and not bridge.applies
    finally:
        replacement.close()
