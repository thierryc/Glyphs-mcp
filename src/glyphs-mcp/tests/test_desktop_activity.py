"""Activity is metadata only; lifecycle reservations serialize with mutations."""
from threading import Event, Thread

import pytest

from test_simple_v2_sidecar import FakeWorker, service, wait_for
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.service import ServiceError, SidecarService
from glyphs_mcp_sidecar.bridge_client import BridgeClientError


def test_configured_worker_path_never_falls_back_to_shell_resolution(tmp_path, monkeypatch):
    from glyphs_mcp_sidecar.worker import GlyphsCliWorker
    monkeypatch.setattr('glyphs_mcp_sidecar.worker.shutil.which', lambda _: '/bin/sh')
    assert GlyphsCliWorker(executable=str(tmp_path/'missing'), app='/Applications/Glyphs.app').status()['available'] is False


def test_worker_running_identity_and_exit_are_observed_deterministically(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from glyphs_mcp_sidecar.worker import GlyphsCliWorker
    value, _, _ = service(tmp_path)
    entered, finish = Event(), Event()
    worker = GlyphsCliWorker(executable='/bin/sh', app='/Applications/Glyphs.app')
    def communicate(process, cancel):
        entered.set()
        assert finish.wait(3)
        return '', 'synthetic worker failure'
    monkeypatch.setattr(worker, '_communicate', communicate)
    monkeypatch.setattr('glyphs_mcp_sidecar.worker.subprocess.Popen', lambda *a, **kw: SimpleNamespace(pid=4321, returncode=1))
    value.worker = worker
    job = value.start_job('doc_1', kind='width_delta', delta=8)
    assert entered.wait(3)
    try:
        execution = worker.status()['executions'][0]
        assert execution['jobId'] == job['id'] and execution['pid'] == 4321
        assert execution['phase'] == 'running' and execution['startedAt'] > 0
        assert worker.status()['available'] is True
    finally:
        finish.set()
    wait_for(value, job['id'], 'failed')
    assert worker.status()['executions'] == []
    assert worker.status()['available'] is True


def test_activity_tracks_preparation_without_scanning_font_artifacts(tmp_path):
    value, _, _ = service(tmp_path)
    entered, finish = Event(), Event()

    def prepare(*args):
        entered.set()
        assert finish.wait(3)
        return FakeWorker.prepare(*args)

    value.worker = type("Worker", (), {"prepare": staticmethod(prepare)})()
    job = value.start_job("doc_1", kind="width_delta", delta=8)
    assert entered.wait(3)
    try:
        status = value.get_status()
        assert status["controlProtocol"] == 1
        assert status["activity"]["activeCount"] == 1
        activity = status["activity"]["jobs"][0]
        assert activity["jobId"] == job["id"]
        assert activity["document"] == "Disposable"
        assert activity["phase"] == "preparing"
        assert activity["completed"] is None and activity["total"] is None
        assert "sample" not in activity and "sourcePath" not in activity
        with pytest.raises(ServiceError, match="busy"):
            value.reserve_idle()
    finally:
        finish.set()
    ready = wait_for(value, job["id"], "ready")
    assert ready["activity"]["phase"] == "ready"
    assert value.get_status()["activity"]["activeCount"] == 0


def test_reservation_prevents_mutations_and_wrong_release_keeps_ownership(tmp_path):
    value, _, _ = service(tmp_path)
    lease = value.reserve_idle()
    with pytest.raises(ServiceError, match="reserved"):
        value.start_job("doc_1", kind="width_delta", delta=8)
    assert value.jobs.records() == []
    with pytest.raises(ServiceError, match="reservation"):
        value.release_idle("different-owner")
    with pytest.raises(ServiceError, match="reserved"):
        value.start_job("doc_1", kind="width_delta", delta=8)
    value.release_idle(lease["reservationId"])
    job = value.start_job("doc_1", kind="width_delta", delta=8)
    wait_for(value, job["id"], "ready")


def test_abandoned_reservation_expires_without_replaying_work(tmp_path, monkeypatch):
    value, _, _ = service(tmp_path)
    clock = [100.0]
    monkeypatch.setattr(value.lifecycle, "clock", lambda: clock[0])
    value.reserve_idle()
    clock[0] += 31
    job = value.start_job("doc_1", kind="width_delta", delta=8)
    wait_for(value, job["id"], "ready")


def test_replacement_service_cannot_start_jobs_until_control_transaction_releases(tmp_path):
    import fcntl
    value, _, _ = service(tmp_path)
    lock_path = tmp_path / '.control.lock'
    value.lifecycle.control_lock = lock_path
    with lock_path.open('a') as control:
        fcntl.flock(control, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ServiceError, match='reserved'):
            value.start_job('doc_1', kind='width_delta', delta=8)
        assert value.jobs.records() == []
    job = value.start_job('doc_1', kind='width_delta', delta=8)
    wait_for(value, job['id'], 'ready')


def test_pending_start_wins_before_job_record_exists(tmp_path):
    value, bridge, _ = service(tmp_path)
    entered, finish = Event(), Event()
    documents = bridge.documents
    results = []

    def blocked_documents():
        entered.set()
        assert finish.wait(3)
        return documents()

    bridge.documents = blocked_documents
    thread = Thread(target=lambda: results.append(value.start_job("doc_1", kind="width_delta", delta=8)))
    thread.start()
    assert entered.wait(3)
    try:
        assert value.jobs.records() == []
        with pytest.raises(ServiceError, match="busy"):
            value.reserve_idle()
    finally:
        finish.set()
        thread.join(3)
    assert not thread.is_alive()
    wait_for(value, results[0]["id"], "ready")


def test_applying_progress_reconciles_before_reserving(tmp_path):
    value, bridge, _ = service(tmp_path)
    job = value.start_job("doc_1", kind="width_delta", delta=8)
    wait_for(value, job["id"], "ready")
    value.apply_job(job["id"])
    activity = value.get_status()["activity"]["jobs"][0]
    assert activity["completed"] == 1 and activity["total"] == 1
    assert activity["phase"] == "applying"
    with pytest.raises(ServiceError, match="busy"):
        value.reserve_idle()
    bridge.operation_state = "applied"
    lease = value.reserve_idle()
    assert value.get_job(job["id"])["status"] == "applied"
    value.release_idle(lease["reservationId"])


def test_reservation_cannot_pass_pending_native_dispatch(tmp_path):
    value, bridge, _ = service(tmp_path)
    job = value.start_job("doc_1", kind="width_delta", delta=8)
    wait_for(value, job["id"], "ready")
    entered, finish = Event(), Event()
    apply = bridge.apply

    def blocked_apply(patch):
        entered.set()
        assert finish.wait(3)
        return apply(patch)

    bridge.apply = blocked_apply
    thread = Thread(target=lambda: value.apply_job(job["id"]))
    thread.start()
    assert entered.wait(3)
    try:
        with pytest.raises(ServiceError, match="busy"):
            value.reserve_idle()
    finally:
        finish.set()
        thread.join(3)
    assert value.get_job(job["id"])["status"] == "applying"


def test_ready_job_and_exact_artifacts_survive_service_restart(tmp_path):
    value, bridge, _ = service(tmp_path)
    job = value.start_job("doc_1", kind="width_delta", delta=8)
    wait_for(value, job["id"], "ready")
    artifact = value.jobs.path(job["id"]) / "patch.json"
    original = artifact.read_bytes()
    value.close()
    restarted = SidecarService(bridge, jobs=JobStore(value.jobs.root), worker=FakeWorker())
    assert restarted.get_job(job["id"])["status"] == "ready"
    assert artifact.read_bytes() == original
    assert restarted.get_status()["activity"]["jobs"][0]["jobId"] == job["id"]


def test_restart_reports_interrupted_preparation_without_resubmission(tmp_path):
    value, bridge, _ = service(tmp_path)
    job = value.jobs.create(bridge.document, {"kind": "width_delta", "delta": 8, "glyphs": []})
    restarted = SidecarService(bridge, jobs=JobStore(value.jobs.root), worker=FakeWorker())
    observed = restarted.get_job(job["id"])
    assert observed["status"] == "interrupted"
    assert observed["error"]["code"] == "service_interrupted"
    assert restarted.get_status()["activity"]["activeCount"] == 0
    assert not (restarted.jobs.path(job["id"]) / "patch.json").exists()


def acknowledged_job(value, bridge, state="applying"):
    job = value.jobs.create(bridge.document, {"kind": "width_delta", "delta": 8, "glyphs": []})
    for name in ("patch.json", "report.json"):
        value.jobs.write_json(job["id"], name, {"retained": name})
    return value.jobs.update(job["id"], status=state, bridgeOperation={
        "jobId": job["id"], "documentId": bridge.document["id"], "status": state,
        "completedChanges": 1, "totalChanges": 2,
    })


def missing_operation(job_id):
    raise BridgeClientError("job_not_found", "the bridge does not know this job")


@pytest.mark.parametrize("state", ["applying", "discarding"])
@pytest.mark.parametrize("restart", [False, True])
def test_acknowledged_lost_operation_is_interrupted_without_replay(tmp_path, state, restart):
    value, bridge, _ = service(tmp_path)
    job = acknowledged_job(value, bridge, state)
    artifacts = {p.name: p.read_bytes() for p in value.jobs.path(job["id"]).glob("*.json") if p.name != "state.json"}
    if restart:
        value = SidecarService(bridge, jobs=JobStore(value.jobs.root), worker=FakeWorker())
    bridge.operation = missing_operation
    bridge.documents = lambda: pytest.fail("Reconciliation does not discover fonts")
    bridge.apply = bridge.discard = lambda *args: pytest.fail("Never replay or restore lost history")
    result = value.get_job(job["id"], include_preview=False)
    assert result["status"] == "interrupted"
    assert result["bridgeOperation"] == job["bridgeOperation"]
    assert result["error"]["code"] == "bridge_operation_lost"
    assert result["error"]["details"] == {"previousStatus": state, "outcome": "unverified", "restoration": "unverified"}
    assert "crash" not in result["error"]["message"].lower()
    assert result["activity"]["completed"] is None and result["activity"]["total"] is None
    assert result["activity"]["finishedAt"] is not None
    assert value.get_status()["activity"]["activeCount"] == 0
    state_bytes = (value.jobs.path(job["id"]) / "state.json").read_bytes()
    assert value.get_job(job["id"], include_preview=False) == result
    assert (value.jobs.path(job["id"]) / "state.json").read_bytes() == state_bytes
    for method in (value.apply_job, value.discard_job):
        with pytest.raises(ServiceError) as error:
            method(job["id"])
        assert error.value.code == "bridge_operation_lost"
    assert {p.name:p.read_bytes() for p in value.jobs.path(job["id"]).glob("*.json") if p.name != "state.json"} == artifacts
    lease = value.reserve_idle()
    value.release_idle(lease["reservationId"])


@pytest.mark.parametrize("code", ["bridge_unavailable", "bridge_response_invalid", "server_stopped", "glyphs_busy"])
def test_transient_native_errors_do_not_clear_busy_state(tmp_path, code):
    value, bridge, _ = service(tmp_path)
    job = acknowledged_job(value, bridge)
    def unavailable(job_id):
        raise BridgeClientError(code, "temporary evidence unavailable")
    bridge.operation = unavailable
    with pytest.raises(ServiceError): value.get_job(job["id"])
    assert value.jobs.get(job["id"]) == job
    with pytest.raises(ServiceError) as error: value.reserve_idle()
    assert error.value.code == "service_busy"


@pytest.mark.parametrize("condition", ["absent", "wrong_job", "wrong_document", "uncertain", "pending"])
def test_missing_operation_requires_matching_acknowledgement_and_no_pending_write(tmp_path, condition):
    value, bridge, _ = service(tmp_path)
    job = acknowledged_job(value, bridge)
    acknowledgement = dict(job["bridgeOperation"])
    if condition == "absent": acknowledgement = None
    if condition == "wrong_job": acknowledgement["jobId"] = "job_other"
    if condition == "wrong_document": acknowledgement["documentId"] = "doc_other"
    changes = {"bridgeOperation": acknowledgement}
    if condition == "uncertain": changes["error"] = {"code": "glyphs_busy", "details": {"execution": "uncertain"}}
    job = value.jobs.update(job["id"], **changes)
    bridge.operation = missing_operation
    if condition == "pending": value.lifecycle.pending = 1
    with pytest.raises(ServiceError): value.get_job(job["id"])
    assert value.jobs.get(job["id"]) == job
    with pytest.raises(ServiceError) as error: value.reserve_idle()
    assert error.value.code == "service_busy"


@pytest.mark.parametrize("new_state", ["applying", "applied"])
def test_missing_poll_does_not_overwrite_newer_acknowledgement_or_completion(tmp_path, new_state):
    value, bridge, _ = service(tmp_path)
    job = acknowledged_job(value, bridge)
    entered, finish = Event(), Event()
    results = []
    def delayed_missing(job_id):
        entered.set()
        assert finish.wait(3)
        missing_operation(job_id)
    bridge.operation = delayed_missing
    thread = Thread(target=lambda: results.append(value.get_job(job["id"])))
    thread.start()
    assert entered.wait(3)
    newer = value.jobs.update(job["id"], status=new_state,
                            bridgeOperation={**job["bridgeOperation"], "status":new_state, "completedChanges":2})
    finish.set(); thread.join(3)
    assert not thread.is_alive()
    assert results[0]["status"] == new_state
    assert value.jobs.get(job["id"]) == newer


def test_slow_successful_poll_does_not_regress_newer_terminal_state(tmp_path):
    value, bridge, _ = service(tmp_path)
    job = acknowledged_job(value, bridge)
    entered, finish = Event(), Event()
    results = []
    def delayed(job_id):
        entered.set(); assert finish.wait(3)
        return job["bridgeOperation"]
    bridge.operation = delayed
    thread = Thread(target=lambda: results.append(value.get_job(job["id"])))
    thread.start(); assert entered.wait(3)
    newer = value.jobs.update(job["id"], status="applied")
    finish.set(); thread.join(3)
    assert not thread.is_alive()
    assert results[0]["status"] == "applied"
    assert value.jobs.get(job["id"]) == newer


def test_evicted_finished_record_after_discard_refusal_reports_missing_history(tmp_path):
    value, bridge, _ = service(tmp_path)
    job = acknowledged_job(value, bridge, "applied")
    bridge.discard = bridge.operation = missing_operation
    with pytest.raises(ServiceError) as error: value.discard_job(job["id"])
    assert error.value.code == "job_not_found"
    result = value.get_job(job["id"])
    assert result["status"] == "interrupted"
    assert result["error"]["details"]["previousStatus"] == "applied"
    assert result["bridgeOperation"] == job["bridgeOperation"]
    assert (value.jobs.path(job["id"])/"patch.json").exists()


@pytest.mark.parametrize("other_work", ["sidecar", "native"])
def test_reconciling_lost_job_does_not_hide_other_work(tmp_path, other_work):
    value, bridge, _ = service(tmp_path)
    lost = acknowledged_job(value, bridge)
    bridge.operation = missing_operation
    if other_work == "sidecar": value.jobs.create(bridge.document, {"kind":"width_delta","delta":8,"glyphs":[]})
    else: bridge.status = lambda: {"protocol":1, "activeOperations":1}
    assert value.get_job(lost["id"])["status"] == "interrupted"
    with pytest.raises(ServiceError) as error: value.reserve_idle()
    assert error.value.code == "service_busy"
