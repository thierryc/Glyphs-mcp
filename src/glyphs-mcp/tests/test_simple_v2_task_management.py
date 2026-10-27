"""Task situations across documents, recovery, runtime versions and restarts."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
for part in ('protocol', 'bridge', 'sidecar'):
    sys.path.insert(0, str(ROOT / 'src' / part))

from glyphs_mcp_protocol.task_conflicts import CAPABILITY, conflicts, protection
from glyphs_mcp_sidecar.task_inventory import list_tasks
from glyphs_mcp_bridge.core import BridgeError
from test_simple_v2_script_snapshots import native, run
from test_simple_v2_edit_workflow import choose, wait
from test_simple_v2_tasks import inventory, task
from test_simple_v2_document_lifecycle import setup as documents


def request(service, document, key):
    return service.edit_workflows.start(document, kind='python_script', mode='preview',
        idempotency_key=key, auto_keep=False,
        options=dict(source='font.glyphs["A"].width=700', entrypoint='script', targets=[]))


def tasks(service):
    return {task['id']: task for task in list_tasks(service)['tasks']}


@pytest.mark.parametrize('partial', [False, True])
def test_independent_fonts_keep_separate_recovery_and_restore(native, partial):
    host, core, bridge, service, add = native
    first_font, first_id = add()
    source = 'font.glyphs["A"].width=650' + ('\nraise RuntimeError("partial")' if partial else '')
    first = run(service, first_id, source, key='first')
    second_font, second_id = add()
    second = run(service, second_id, key='second')
    assert second['state'] == 'applied'
    assert core._operations[first['jobId']]['scriptSnapshot'] is not None
    before = deepcopy(service.jobs.records())
    values = tasks(service)
    assert values[first['id']]['taskStatus'] == ('needs_attention' if partial else 'finished')
    assert values[second['id']]['taskStatus'] == 'finished'
    assert values[first['id']]['recoveryStatus'] == 'available'
    assert not values[second['id']]['blockedBy']
    assert service.jobs.records() == before  # Opening Tasks is passive.
    restored = choose(service, first, 'restore_saved_script')
    assert restored['document']['id'] != first_id
    assert host.fonts[0].glyphs['A'].width == 610
    assert host.fonts[1] is second_font and second_font.glyphs['A'].width == 620
    assert core._operations[second['jobId']]['scriptSnapshot'] is not None
    choose(service, second, 'finish_script')
    assert host.fonts[1].parent.isDocumentEdited()


def test_same_document_requires_decision_and_names_the_owner(native):
    _, core, _, service, add = native
    _, identity = add()
    first = run(service, identity)
    second = wait(service, request(service, identity, 'same-font'), 'blocked_review')
    assert second['blocker']['reason'] == 'recovery'
    assert second['blocker']['scope'] == 'document'
    assert second['blockingWorkflowId'] == first['id']
    assert 'whole font' in second['text']
    item = tasks(service)[second['id']]
    assert item['taskStatus'] == 'needs_attention'
    assert item['blockers'][0]['taskId'] == first['id']
    choose(service, second, 'cancel')
    assert core._operations[first['jobId']]['scriptSnapshot'] is not None


def test_old_cross_font_waiter_becomes_independent_after_capability_negotiation(native):
    _, core, bridge, service, add = native
    _, first_id = add(); first = run(service, first_id)
    _, second_id = add()
    status = bridge.status
    bridge.status = lambda: dict(status(), jobCapabilities=[c for c in status()['jobCapabilities'] if c != CAPABILITY])
    second = wait(service, request(service, second_id, 'old-waiter'), 'blocked_review')
    assert second['blocker']['reason'] == 'runtime_update'
    assert 'shares recovery across fonts' in second['text']
    bridge.status = status
    second = wait(service, second, 'waiting_run')
    assert not second['blockerId'] and not second.get('blocker')
    assert core._operations[first['jobId']]['scriptSnapshot'] is not None
    assert second['state'] == 'waiting_run'  # Preview authorization is preserved.


def test_retained_snapshots_survive_recent_operation_pruning(native):
    host, core, _, service, add = native
    values = []
    for index in range(11):
        _, identity = add()
        values.append(run(service, identity, key=f'font-{index}'))
    assert all(core._operations[value['jobId']]['scriptSnapshot'] is not None for value in values)
    choose(service, values[0], 'restore_saved_script')
    assert host.fonts[0].glyphs['A'].width == 610
    assert all(font.glyphs['A'].width == 620 for font in host.fonts[1:])


@pytest.mark.parametrize('status,kind,executed,scope,reason', [
    ('applying', 'python_script', True, 'session', 'execution'),
    ('discarding', 'python_script', True, 'session', 'execution'),
    ('applied', 'python_script', True, 'document', 'recovery'),
    ('failed', 'python_script', True, 'document', 'recovery'),
    ('cancelled', 'python_script', True, 'document', 'recovery'),
    ('applying', 'width_delta', False, 'document', 'operation'),
    ('applied', 'width_delta', False, 'document', 'recovery'),
    ('ready', 'width_delta', False, 'document', 'preview'),
    ('saving', 'save', False, 'document', 'operation'),
])
def test_shared_resource_rules(status, kind, executed, scope, reason):
    record = dict(id='job', document={'id': 'A'}, request={'kind': kind}, status=status,
        bridgeOperation={'scriptResult': {'executed': executed}})
    owner = protection(record)
    assert (owner['scope'], owner['reason']) == (scope, reason)
    assert conflicts(record, 'A')
    assert conflicts(record, 'B') == (scope == 'session')
    assert conflicts(record, 'B', exclusive=True) == (scope == 'session' or reason == 'operation')


def test_unknown_execution_stays_protected_and_staged_artifacts_are_independent():
    record = dict(id='job', document={'id': 'A'}, request={'kind': 'python_script'},
        status='interrupted', error={'code': 'bridge_operation_lost'})
    assert conflicts(record, 'B')
    assert protection(record)['wait'] == 'check'
    record.update(resultKind='artifact', inputKind='compiled_fonts')
    assert not conflicts(record, 'B', exclusive=True)


def test_native_owner_protects_execution_but_not_other_document_recovery(native):
    _, core, _, service, add = native
    _, identity = add(); value = run(service, identity)
    operation = core._operations[value['jobId']]
    core._check_owner('another-document')
    with pytest.raises(BridgeError):
        core._check_owner(identity)
    operation['status'] = 'applying'
    with pytest.raises(BridgeError, match='execution and cleanup'):
        core._check_owner('another-document')


def test_successful_tasks_are_finished_without_closing_recovery(native):
    _, core, _, service, add = native
    _, identity = add(); value = run(service, identity)
    item = tasks(service)[value['id']]
    assert item['taskStatus'] == 'finished' and item['outcomeLabel'] == 'Script finished'
    assert not item['closed'] and item['recoveryStatus'] == 'available'
    choose(service, value, 'finish_script')
    item = tasks(service)[value['id']]
    assert item['closed'] and item['recoveryStatus'] == 'ended'
    assert item['outcomeLabel'] == 'Changes kept'


@pytest.mark.parametrize('state,status,expected', [
    ('preparing', 'preparing', 'working'),
    ('applying', 'applying', 'working'),
    ('saving', 'accepting', 'working'),
    ('discarding', 'discarding', 'working'),
    ('waiting_run', 'ready', 'needs_attention'),
    ('ready', 'ready', 'needs_attention'),
    ('waiting_save', 'ready', 'needs_attention'),
    ('outdated', 'ready', 'needs_attention'),
    ('uncertain', 'applying', 'needs_attention'),
    ('interrupted', 'interrupted', 'needs_attention'),
    ('applied', 'applied', 'finished'),
    ('saved', 'accepted', 'finished'),
    ('executed', 'completed', 'finished'),
    ('failed', 'failed', 'finished'),
    ('cancelled', 'cancelled', 'finished'),
])
def test_task_situations_have_simple_statuses(inventory, state, status, expected):
    value, _ = task(inventory, state=state, status=status, kind='width_delta')
    assert tasks(inventory)[value['id']]['taskStatus'] == expected


def test_waiting_for_work_is_distinct_from_waiting_for_a_decision(inventory):
    owner, job = task(inventory, state='applying', status='applying')
    waiting, _ = task(inventory, font='Other', state='blocked_active', status='ready')
    inventory.edit_workflows.store.update(waiting, blockerId=job['id'])
    item = tasks(inventory)[waiting['id']]
    assert item['taskStatus'] == 'waiting'
    assert item['blockers'][0]['wait'] == 'automatic'
    inventory.jobs.update(job['id'], status='applied')
    item = tasks(inventory)[waiting['id']]
    assert item['taskStatus'] == 'needs_attention'


def test_recovery_in_another_font_does_not_prevent_close(documents):
    host, core, _, service, add = documents
    first, first_id = add(dirty=True)
    second, second_id = add()
    job = service.jobs.create(core.adapter.document_state(first_id), {'kind': 'python_script'})
    service.jobs.update(job['id'], status='failed', resultKind='script',
        bridgeOperation={'scriptResult': {'executed': True}})
    result = service.close_document(second_id, 'close-independent')
    assert result['closed'] and host.fonts == [first]
    assert service.jobs.get(job['id'])['status'] == 'failed'


def test_save_checkpoint_is_folded_into_its_request(inventory):
    value, _ = task(inventory, state='waiting_save', status='ready', kind='width_delta')
    child = inventory.jobs.create({'id': 'Bryan'}, {'kind': 'checkpoint_save'})
    inventory.edit_workflows.store.update(value, saveRequest={'checkpointJobId': child['id']})
    assert list(tasks(inventory)) == [value['id']]


def test_recovery_in_another_font_does_not_prevent_explicit_save(documents, tmp_path):
    host, core, _, service, add = documents
    first, first_id = add(dirty=True)
    path = tmp_path / 'Other.glyphs'; path.write_text('before')
    second, second_id = add(str(path), dirty=True)
    job = service.jobs.create(core.adapter.document_state(first_id), {'kind': 'python_script'})
    service.jobs.update(job['id'], status='failed', resultKind='script',
        bridgeOperation={'scriptResult': {'executed': True}})
    receipt = service.save_document(second_id)
    assert receipt['verification'] == 'native_and_source_hash'
    assert first.parent.isDocumentEdited and not second.parent.isDocumentEdited
    assert service.jobs.get(job['id'])['status'] == 'failed'


def test_independent_duplicate_preserves_other_fonts_recovery(native):
    host, core, _, service, add = native
    _, first_id = add(); first = run(service, first_id)
    second, second_id = add()
    result = service.duplicate_document(second_id, 'duplicate-independent')
    assert result['documentId'] not in {first_id, second_id}
    assert core._operations[first['jobId']]['scriptSnapshot'] is not None
    assert second.glyphs['A'].width == 610


def test_known_bridge_restart_does_not_advertise_lost_memory_recovery(native):
    _, _, _, service, add = native
    _, identity = add(); value = run(service, identity)
    service._task_bridge_session = 'another-bridge-session'
    assert tasks(service)[value['id']]['recoveryStatus'] == 'unavailable'


def test_acknowledged_or_kept_unknown_restoration_releases_its_protection():
    record = dict(id='job', document={'id': 'A'}, request={'kind': 'checkpoint_restore'},
        status='failed', error={'code': 'restoration_unverified', 'details': {'writeAttempted': True}})
    assert conflicts(record, 'B')
    record.update(status='completed', outcome='unverified')
    assert protection(record) is None


def test_lost_native_operation_cannot_keep_advertising_cached_recovery(native):
    _, _, _, service, add = native
    _, identity = add(); value = run(service, identity)
    service.jobs.update(value['jobId'], status='interrupted', error={'code': 'bridge_operation_lost'})
    item = tasks(service)[value['id']]
    assert item['taskStatus'] == 'needs_attention'
    assert item['outcomeLabel'] == 'Outcome unknown'
    assert item['recoveryStatus'] == 'unavailable'


def test_ordinary_workflow_polling_reuses_negotiated_capabilities(native):
    _, _, bridge, service, add = native
    _, identity = add(); value = run(service, identity)
    status = bridge.status
    reads = []
    def observed_status():
        reads.append(True)
        return status()
    bridge.status = observed_status
    for _ in range(3):
        service.edit_workflows.get(value['id'])
    assert not reads


def test_diagnostic_findings_are_a_finished_result_with_no_recovery(inventory):
    job = inventory.jobs.create({'id': 'A'}, {'kind': 'feature_compile'})
    inventory.jobs.update(job['id'], status='completed', resultKind='diagnostic', report={'success': False})
    item = tasks(inventory)[job['id']]
    assert item['taskStatus'] == 'finished' and item['outcomeLabel'] == 'Issues found'
    assert item['recoveryStatus'] == 'none' and not item['blockers']


def test_incomplete_typed_recovery_remains_visible_for_review(inventory):
    job = inventory.jobs.create({'id': 'A'}, {'kind': 'width_delta'})
    inventory.jobs.update(job['id'], status='failed', resultKind='mutation',
        error={'code': 'native_write_failed', 'message': 'A target could not be restored',
               'details': {'recovery': {'complete': False, 'remaining': 1}}})
    item = tasks(inventory)[job['id']]
    assert item['taskStatus'] == 'needs_attention'
    assert item['outcomeLabel'] == 'Partial changes may remain'
    assert 'Automatic recovery was incomplete' in item['message']
    assert item['closed']  # Native work stopped; this warning does not take a new lock.
