"""Exercise conversational orchestration through the real job and native core guards."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import time
from threading import Event

import pytest

from test_simple_v2_save import _BridgeSaveAdapter, _Queue, BridgeCore, BridgeError
from glyphs_mcp_sidecar.bridge_client import BridgeClientError
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.service import SidecarService, ServiceError
from glyphs_mcp_sidecar.edit_workflow_state import report_needs_review


class Adapter(_BridgeSaveAdapter):
    def __init__(self, path):
        super().__init__(path)
        self.closed = False

    def list_documents(self):
        return [] if self.closed else [dict(super().list_documents()[0], familyName="Test family")]

    def save_document(self, document_id, target, mode):
        result = super().save_document(document_id, target, mode)
        Path(target).write_text(str(self.value))
        return result


class Bridge:
    def __init__(self, path):
        self.adapter, self.queue = Adapter(path), _Queue()
        self.core = BridgeCore(self.adapter, self.queue)
        self.applies = 0

    def status(self):
        return {"protocol": 1, "activeOperations": 0}

    def documents(self):
        return self.adapter.list_documents()

    def call(self, method, *args, **kwargs):
        try:
            result = method(*args, **kwargs)
            self.queue.drain()
            return result
        except BridgeError as exc:
            raise BridgeClientError(exc.code, exc.message, exc.details) from exc

    def apply(self, patch):
        self.applies += 1
        return self.call(self.core.begin_apply, patch)

    def operation(self, identity):
        return self.call(self.core.operation, identity)

    def discard(self, identity):
        return self.call(self.core.discard, identity)

    def save(self, request):
        return self.call(self.core.begin_save, request)

    def save_operation(self, identity):
        return self.call(self.core.save_operation, identity)

    def accept(self, identity, request):
        return self.call(self.core.begin_accept, identity, request)

    def complete_accept(self, identity, **kwargs):
        return self.call(self.core.complete_accept, identity, **kwargs)


class Worker:
    def __init__(self):
        self.report = None
        self.gate = None
        self.calls = 0
        self.no_changes = False

    def status(self):
        return {"available": True}

    def prepare(self, root, document, request, source, fingerprint, cancel):
        self.calls += 1
        if self.gate:
            assert self.gate.wait(3)
        before = float(source.read_text())
        if self.report is not None:
            (root / "report.json").write_text(json.dumps(self.report))
        return dict(version=1, jobId=root.name, documentId=document["id"], sourcePath=document["path"],
                    sourceHash=fingerprint, generation=document["generation"], summary="Add 8 units",
                    changes=[] if self.no_changes else [dict(kind="set", glyph="A", layer="M1", field="width", before=before, after=before+8)])


@pytest.fixture
def env(tmp_path):
    source = tmp_path / "Test.glyphs"; source.write_text("600")
    bridge, worker = Bridge(source), Worker()
    service = SidecarService(bridge, jobs=JobStore(tmp_path / "jobs"), worker=worker)
    yield service, bridge, worker, source
    if worker.gate:
        worker.gate.set()
    service.close()


def start(env, **kwargs):
    return env[0].edit_workflows.start("doc_1", kind="width_delta", delta=8, idempotency_key="request1", **kwargs)


def choose(service, workflow, action, **kwargs):
    token = next(a["token"] for a in workflow["actions"] if a["action"] == action)
    return service.edit_workflows.respond(workflow["id"], workflow["revision"], token, **kwargs)


def wait(service, value, state):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = service.edit_workflows.get(value["id"])
        if value["state"] == state:
            return value
        time.sleep(.02)
    raise AssertionError(value)


def test_clean_request_applies_without_ui_and_never_saves(env):
    service, bridge, worker, source = env
    value = start(env)
    # The coordinator, not get/poll or a model turn, must drive the operation.
    deadline = time.monotonic() + 4
    while bridge.adapter.value == 600 and time.monotonic() < deadline:
        time.sleep(.02)
    assert bridge.adapter.value == 608
    assert wait(service, value, "applied")["jobId"]
    assert source.read_text() == "600"
    assert bridge.adapter.dirty and bridge.adapter.save_calls == []


def test_save_continue_saves_once_then_separate_result_save(env):
    service, bridge, worker, source = env
    bridge.adapter.value = 700; bridge.adapter.dirty = True
    value = start(env); assert value["state"] == "waiting_save" and worker.calls == 0
    original = deepcopy(value)
    value = choose(service, value, "save_continue")
    choose(service, original, "save_continue")  # response-loss retry
    value = wait(service, value, "applied")
    assert bridge.adapter.value == 708 and float(source.read_text()) == 700
    assert len(bridge.adapter.save_calls) == 1
    value = choose(service, value, "save_result")
    assert wait(service, value, "saved")["receipt"]["verification"] == "native_and_source_hash"
    assert len(bridge.adapter.save_calls) == 2 and float(source.read_text()) == 708


def test_preview_and_no_change(env):
    service, bridge, worker, _ = env
    value = wait(service, start(env, mode="preview"), "ready")
    assert bridge.applies == 0
    value = wait(service, choose(service, value, "apply"), "applied")
    wait(service, choose(service, value, "discard"), "discarded")
    assert bridge.adapter.value == 600


def test_no_change_result_does_not_apply_or_save(env):
    service, bridge, worker, _ = env
    worker.no_changes = True
    wait(service, start(env), "no_changes")
    assert bridge.applies == 0 and not bridge.adapter.save_calls


@pytest.mark.parametrize("reason", ["warning", "skipped", "unavailable", "overwrite"])
def test_complete_report_gate_not_just_sample(env, reason):
    service, bridge, worker, _ = env
    worker.report = {"claim": "Test", "targets": [{"status":"unchanged"} for _ in range(12)]}
    if reason == "warning": worker.report["warnings"] = ["Review geometry"]
    elif reason == "overwrite": worker.report["requiredOverwrites"] = [{"master":"M1", "key":"x"}]
    else: worker.report["targets"][-1]["status"] = reason
    value = wait(service, start(env), "needs_review")
    assert bridge.applies == 0
    assert report_needs_review(service, value["job"])
    assert value['reviewInConversation'] is (reason != 'overwrite')


def test_pathless_save_as_and_destination_retry(env, tmp_path):
    service, bridge, worker, source = env
    bridge.adapter.path = None; bridge.adapter.dirty = True
    value = start(env)
    assert "save_continue" not in {a["action"] for a in value["actions"]}
    value = choose(service, value, "save_as_continue", destination=str(source))
    assert value["state"] == "waiting_save" and value["error"]["code"] == "destination_exists"
    target = tmp_path / "New.glyphs"
    value = choose(service, value, "save_as_continue", destination=str(target))
    wait(service, value, "applied")
    assert bridge.adapter.path == str(target) and target.read_text() == "600"


def test_manual_save_as_resumes_same_document(env, tmp_path):
    service, bridge, _, _ = env
    bridge.adapter.dirty = True
    value = choose(service, start(env), "manual_save")
    target = tmp_path / "Manual.glyphs"
    bridge.adapter.save_document("doc_1", str(target), "save_as")
    wait(service, choose(service, value, "check_continue"), "applied")
    assert bridge.applies == 1


def test_duplicate_start_and_stale_simultaneous_choices(env):
    service, bridge, _, _ = env
    bridge.adapter.dirty = True
    value = start(env)
    assert start(env)["id"] == value["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: choose(service, value, "save_continue"), range(2)))
    wait(service, results[0], "applied")
    assert len(bridge.adapter.save_calls) == 1 and bridge.applies == 1
    with pytest.raises(ServiceError, match="outdated"):
        choose(service, value, "cancel")
    with pytest.raises(ServiceError, match="another edit request"):
        service.edit_workflows.start("doc_1", kind="width_delta", delta=9, idempotency_key="request1")


def test_invalid_request_or_worker_never_prompts_save(env):
    service, bridge, worker, _ = env
    bridge.adapter.dirty = True
    with pytest.raises(ServiceError):
        service.edit_workflows.start("doc_1", kind="width_delta", delta=0, idempotency_key="bad")
    worker.status = lambda: {"available":False}
    with pytest.raises(ServiceError, match="unavailable"):
        start(env)
    assert bridge.adapter.save_calls == [] and service.edit_workflows.store.records == {}


def test_edit_during_prepare_does_not_retry_or_overwrite(env):
    service, bridge, worker, _ = env
    worker.gate = Event()
    value = start(env)
    bridge.adapter.value = 720; bridge.adapter.dirty = True
    worker.gate.set()
    value = wait(service, value, "outdated")
    assert bridge.applies == 0 and bridge.adapter.value == 720
    value = choose(service, value, "save_reprepare")
    wait(service, value, "applied")
    assert bridge.adapter.value == 728 and worker.calls == 2


def test_cancel_preparation_preserves_user_changes(env):
    service, bridge, worker, source = env
    worker.gate = Event(); value = start(env)
    value = choose(service, value, "cancel"); worker.gate.set()
    wait(service, value, "cancelled")
    assert bridge.applies == 0 and source.read_text() == "600"


def test_pending_request_resumes_after_previous_saved(env):
    service, bridge, worker, source = env
    first = wait(service, start(env), "applied")
    second = service.edit_workflows.start("doc_1", kind="width_delta", delta=8, idempotency_key="second")
    second = wait(service, second, "blocked_review")
    with pytest.raises(ServiceError, match="existing request"):
        service.edit_workflows.start("doc_1", kind="width_delta", delta=8, idempotency_key="third")
    second = choose(service, second, "save_previous")
    wait(service, second, "applied")
    assert bridge.adapter.value == 616 and float(source.read_text()) == 608
    assert len(bridge.adapter.save_calls) == 1


def test_restart_never_replays_consumed_save_or_apply(env):
    service, bridge, worker, _ = env
    bridge.adapter.dirty = True
    value = start(env); service.edit_workflows.close()
    replacement = SidecarService(bridge, jobs=JobStore(service.jobs.root), worker=worker)
    try:
        restored = replacement.edit_workflows.get(value["id"])
        assert restored["state"] == "interrupted"
        with pytest.raises(ServiceError, match="outdated"):
            choose(replacement, value, "save_continue")
        assert bridge.adapter.save_calls == [] and worker.calls == 0
    finally: replacement.close()


def test_uncertain_prerequisite_save_never_replays(env):
    service, bridge, worker, _ = env
    bridge.adapter.dirty = True
    calls = []
    def uncertain(*args, **kwargs):
        calls.append(True)
        raise ServiceError("bridge_unavailable", "Save outcome unknown", details={"execution":"uncertain", "writeAttempted":True})
    service.save_document = uncertain
    original = start(env); value = choose(service, original, "save_continue")
    assert value["state"] == "uncertain"
    choose(service, original, "save_continue")
    choose(service, value, "check_outcome")
    assert len(calls) == 1 and worker.calls == 0


def test_closed_document_does_not_substitute(env):
    service, bridge, _, _ = env
    bridge.adapter.dirty = True
    value = start(env); bridge.adapter.closed = True
    value = choose(service, value, "save_continue")
    assert value["state"] == "failed" and value["error"]["code"] == "document_not_found"
    assert not bridge.adapter.save_calls


def test_mcp_app_and_proxy_preserve_text_resources_metadata_and_actions(env):
    from fastmcp import Client
    from glyphs_mcp_sidecar.proxy import create_proxy
    from glyphs_mcp_sidecar.server import create_server
    from glyphs_mcp_sidecar.edit_workflow_ui import RESOURCE_URI, RESOURCE_MIME
    service, bridge, _, _ = env
    bridge.adapter.dirty = True
    async def run():
        server = create_server(service)
        proxy = create_proxy(server)
        for host in (server, proxy):
            async with Client(host) as client:
                catalog = {t.name:t for t in await client.list_tools()}
                assert len(catalog) == 12
                assert catalog["start_edit_workflow"].meta["ui"]["resourceUri"] == RESOURCE_URI
                resources = await client.read_resource(RESOURCE_URI)
                assert resources[0].mimeType == RESOURCE_MIME
                assert resources[0].meta['ui']['csp']['connectDomains'] == []
                assert resources[0].meta['ui']['prefersBorder'] is True
                assert "ui/initialize" in resources[0].text
                result = await client.call_tool("start_edit_workflow", dict(document_id="doc_1", kind="width_delta", delta=8, idempotency_key="shared"))
                assert result.structured_content["data"]["state"] == "waiting_save"
                assert "Save and continue" in result.content[0].text
    asyncio.run(run())


def test_saved_outcome_reconciles_without_replaying_save(env):
    service, bridge, worker, _ = env
    bridge.adapter.dirty = True
    save, observe = bridge.save, bridge.save_operation
    def lost(request):
        save(request)
        raise BridgeClientError('transport_lost', 'Response lost', {'execution':'uncertain'})
    bridge.save = lost
    bridge.save_operation = lambda identity: (_ for _ in ()).throw(ConnectionError('Offline'))
    value = choose(service, start(env), 'save_continue')
    assert value['state'] == 'uncertain' and len(bridge.adapter.save_calls) == 1 and worker.calls == 0
    bridge.save_operation = observe
    value = choose(service, value, 'check_outcome')
    assert value['state'] == 'waiting_manual' and value['receipt']['verification'] == 'native_and_source_hash'
    wait(service, choose(service, value, 'check_continue'), 'applied')
    assert len(bridge.adapter.save_calls) == 1 and bridge.applies == 1


def test_guarded_discard_preserves_subsequent_edit(env):
    service, bridge, _, _ = env
    value = wait(service, start(env), 'applied')
    bridge.adapter.value = 900
    value = choose(service, value, 'discard')
    # Native recovery reports a conflict; the workflow must not replace it with success.
    deadline = time.monotonic() + 3
    while value['state'] == 'discarding' and time.monotonic() < deadline:
        time.sleep(.02); value = service.edit_workflows.get(value['id'])
    assert bridge.adapter.value == 900 and value['job']['error']
    assert value['state'] != 'discarded'
    assert 'Changes discarded.' not in value['text']
    assert 'Changes undone.' not in value['text']
    assert not bridge.adapter.save_calls


def test_lowlevel_job_resolution_and_one_pending_request(env):
    service, bridge, worker, _ = env
    worker.gate = Event()
    first = service.start_job('doc_1', kind='width_delta', delta=8)
    value = start(env)
    assert value['blockerId'] == first['id']
    with pytest.raises(ServiceError, match='existing request'):
        service.edit_workflows.start('doc_1', kind='width_delta', delta=16, idempotency_key='third')
    worker.gate.set()
    value = wait(service, value, 'blocked_proposal')
    service.discard_job(first['id'])
    wait(service, value, 'applied')
    assert bridge.applies == 1


def test_final_save_as_shows_verified_destination(env, tmp_path):
    service, bridge, _, source = env
    value = wait(service, start(env), 'applied')
    target = tmp_path/'Result.glyphs'
    value = wait(service, choose(service, value, 'save_result_as', destination=str(target)), 'saved')
    assert value['document']['path'] == str(target) and value['receipt']['path'] == str(target)
    assert source.read_text() == '600' and float(target.read_text()) == 608


def test_full_text_only_mcp_without_skills(env):
    from fastmcp import Client
    from glyphs_mcp_sidecar.server import create_server
    service, bridge, worker, source = env
    bridge.adapter.dirty = True
    def text_control(result):
        # Deliberately never read structured_content: Claude may omit it from
        # the model's conversation even though the card receives it.
        return json.loads(result.content[1].text)

    async def run():
        async with Client(create_server(service)) as client:
            result = await client.call_tool('start_edit_workflow', dict(document_id='doc_1', kind='width_delta', delta=8, idempotency_key='text'))
            data = text_control(result)
            assert 'Save and continue' in result.content[0].text
            selected = next(a for a in data['actions'] if a['label'] == 'Save and continue')
            result = await client.call_tool('respond_edit_workflow', dict(workflow_id=data['workflow_id'], expected_revision=data['expected_revision'], action_token=selected['action_token']))
            deadline = time.monotonic() + 5
            while text_control(result)['poll']:
                assert time.monotonic() < deadline
                await asyncio.sleep(.01)
                result = await client.call_tool('get_edit_workflow', dict(workflow_id=data['workflow_id']))
            assert text_control(result)['state'] == 'applied'
            assert 'Changes applied. Save your font to keep them.' in result.content[0].text
            assert len(bridge.adapter.save_calls) == 1 and source.read_text() == '600'
            # A later plain "Save the font" uses the retained reference and a
            # fresh offered action; no user-supplied identifier is necessary.
            result = await client.call_tool('get_edit_workflow', dict(workflow_id=data['workflow_id']))
            data = text_control(result)
            selected = next(a for a in data['actions'] if a['label'] == 'Save font')
            result = await client.call_tool('respond_edit_workflow', dict(workflow_id=data['workflow_id'], expected_revision=data['expected_revision'], action_token=selected['action_token']))
            while text_control(result)['poll']:
                assert time.monotonic() < deadline
                await asyncio.sleep(.01)
                result = await client.call_tool('get_edit_workflow', dict(workflow_id=data['workflow_id']))
            assert text_control(result)['state'] == 'saved'
            assert not text_control(result)['actions']
    asyncio.run(run())
    assert len(bridge.adapter.save_calls) == 2 and float(source.read_text()) == 608
