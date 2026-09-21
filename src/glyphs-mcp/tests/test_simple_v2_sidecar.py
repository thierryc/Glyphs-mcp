"""Sidecar job tests with a fake bridge and worker."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

import pytest


REPO = Path(__file__).resolve().parents[3]
for root in (
    REPO / "src" / "protocol",
    REPO / "src" / "bridge",
    REPO / "src" / "sidecar",
):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from glyphs_mcp_protocol import TOOL_NAMES  # noqa: E402
from glyphs_mcp_sidecar.bridge_client import BridgeClient  # noqa: E402
from glyphs_mcp_sidecar.jobs import JobStore  # noqa: E402
from glyphs_mcp_sidecar import native_worker  # noqa: E402
from glyphs_mcp_sidecar.service import ServiceError, SidecarService  # noqa: E402
from glyphs_mcp_sidecar.source import snapshot_source, source_hash  # noqa: E402


class FakeBridge:
    def __init__(self, path: Path) -> None:
        self.document = {
            "id": "doc_1",
            "familyName": "Disposable",
            "path": str(path),
            "dirty": False,
            "generation": 3,
        }
        self.operation_state = "applying"
        self.patch = None

    def status(self):
        return {"protocol": 1, "activity": "ready"}

    def documents(self):
        return [dict(self.document)]

    def read_entities(self, document_id, entities, fields):
        return [{"entity": entities[0], "values": {fields[0]: "A"}}]

    def apply(self, patch):
        self.patch = patch
        return {"jobId": patch["jobId"], "status": "applying"}

    def operation(self, job_id):
        return {
            "jobId": job_id,
            "status": self.operation_state,
            "error": None,
            "completedChanges": 1,
            "totalChanges": 1,
        }

    def discard(self, job_id):
        self.operation_state = "discarded"
        return {"jobId": job_id, "status": "discarded", "error": None}


class FakeWorker:
    @staticmethod
    def status():
        return {"available": True, "kind": "fake"}

    @staticmethod
    def prepare(job_root, document, request, source_path, fingerprint, cancel):
        assert source_path.read_bytes() == b"saved font"
        assert request == {"kind": "width_delta", "delta": 8, "glyphs": []}
        return {
            "version": 1,
            "jobId": job_root.name,
            "documentId": document["id"],
            "sourcePath": document["path"],
            "sourceHash": fingerprint,
            "generation": document["generation"],
            "changes": [
                {
                    "kind": "set",
                    "glyph": "A",
                    "layer": "M1",
                    "field": "width",
                    "before": 600,
                    "after": 608,
                }
            ],
            "summary": "Add 8 units to all layers",
        }


def wait_for(service: SidecarService, job_id: str, status: str) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = service.get_job(job_id)
        if job["status"] == status:
            return job
        time.sleep(0.01)
    raise AssertionError("job did not reach " + status)


def service(tmp_path: Path) -> tuple[SidecarService, FakeBridge, Path]:
    source = tmp_path / "Disposable.glyphs"
    source.write_bytes(b"saved font")
    bridge = FakeBridge(source)
    value = SidecarService(bridge, jobs=JobStore(tmp_path / "jobs"), worker=FakeWorker())
    return value, bridge, source


def test_cancellation_wins_before_worker_publishes_and_defers_artifact_release(tmp_path):
    value, _, _ = service(tmp_path)
    prepared, finish = Event(), Event()
    worker = value.worker.prepare
    sources = []
    def prepare(*args):
        result = worker(*args)
        sources.append(args[3])
        prepared.set()
        assert finish.wait(3)
        assert sources[0].exists()
        return result  # Native preparation can finish just as cancellation arrives.
    value.worker = type('Worker', (), {'prepare': staticmethod(prepare)})()
    job = value.start_job('doc_1', kind='width_delta', delta=8)
    assert prepared.wait(3)
    try:
        assert value.discard_job(job['id'])['status'] == 'cancelling'
        assert sources[0].exists()
    finally:
        finish.set()
    assert wait_for(value, job['id'], 'cancelled')['error']['code'] == 'cancelled'
    value.close()
    assert not sources[0].exists()
    assert value.jobs.get(job['id'])['status'] == 'cancelled'


def test_publication_wins_and_waiting_discard_rechecks_fresh_state(tmp_path):
    value, _, _ = service(tmp_path)
    publishing, finish = Event(), Event()
    update = value.jobs.update
    def publish(job_id, **changes):
        if changes.get('status') == 'ready':
            publishing.set()
            assert finish.wait(3)
        return update(job_id, **changes)
    value.jobs.update = publish
    job = value.start_job('doc_1', kind='width_delta', delta=8)
    assert publishing.wait(3)
    requested, results = Event(), []
    def discard():
        requested.set()
        results.append(value.discard_job(job['id']))
    thread = Thread(target=discard)
    thread.start()
    assert requested.wait(3)
    finish.set()
    thread.join(3)
    value.close()
    assert results[0]['status'] == 'discarded'
    assert value.jobs.get(job['id'])['status'] == 'discarded'
    assert not (value.jobs.path(job['id']) / 'patch.json').exists()


@pytest.mark.parametrize('execution', ['cancelled', 'uncertain'])
def test_dispatch_timeout_retains_job_identity_and_reconciles_without_resubmission(tmp_path, execution):
    from glyphs_mcp_sidecar.bridge_client import BridgeClientError
    value, bridge, _ = service(tmp_path)
    job = value.start_job('doc_1', kind='width_delta', delta=8)
    wait_for(value, job['id'], 'ready')
    calls = []
    def apply(patch):
        calls.append(patch['jobId'])
        raise BridgeClientError('glyphs_busy', 'bounded dispatch', {'execution': execution, 'jobId': job['id']})
    bridge.apply = apply
    with pytest.raises(ServiceError) as error:
        value.apply_job(job['id'])
    assert error.value.details['jobId'] == job['id']
    assert value.jobs.get(job['id'])['status'] == ('applying' if execution == 'uncertain' else 'ready')
    if execution == 'uncertain':
        bridge.operation_state = 'applied'
        assert value.apply_job(job['id'])['status'] == 'applied'
        assert calls == [job['id']]


def test_source_copy_and_package_hash_are_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "A.glyphs"
    source.write_bytes(b"font")
    root = tmp_path / "job"
    root.mkdir()
    copied, fingerprint = snapshot_source(source, root)
    assert copied.read_bytes() == b"font"
    assert fingerprint == source_hash(source) == source_hash(copied)

    package_a = tmp_path / "A.glyphspackage"
    package_b = tmp_path / "B.glyphspackage"
    for package in (package_a, package_b):
        package.mkdir()
        (package / "fontinfo.plist").write_text("info")
        (package / "glyphs").mkdir()
        (package / "glyphs" / "A.glyph").write_text("glyph")
    assert source_hash(package_a) == source_hash(package_b)


def test_prepare_apply_and_single_acceptance_message(tmp_path: Path) -> None:
    value, bridge, _source = service(tmp_path)
    started = value.start_job("doc_1", kind="width_delta", delta=8)
    assert started["status"] == "preparing"
    ready = wait_for(value, started["id"], "ready")
    assert ready["changeCount"] == 1
    assert len(ready["sample"]) == 1
    applying = value.apply_job(started["id"])
    assert applying["status"] == "applying"
    bridge.operation_state = "applied"
    applied = value.get_job(started["id"])
    assert applied["status"] == "applied"
    assert "accept_job" in applied["message"]
    assert bridge.patch["sourcePath"].endswith("Disposable.glyphs")
    assert value.jobs.path(started["id"]).joinpath("source.glyphs").exists()


def test_source_or_document_change_refuses_apply_without_bridge_write(tmp_path: Path) -> None:
    value, bridge, source = service(tmp_path)
    job_id = value.start_job("doc_1", kind="width_delta", delta=8)["id"]
    wait_for(value, job_id, "ready")
    source.write_bytes(b"changed on disk")
    with pytest.raises(ServiceError) as caught:
        value.apply_job(job_id)
    assert caught.value.code == "stale_source"
    assert bridge.patch is None


def test_dirty_documents_are_rejected_before_job_creation(tmp_path: Path) -> None:
    value, bridge, _source = service(tmp_path)
    bridge.document["dirty"] = True
    with pytest.raises(ServiceError) as caught:
        value.start_job("doc_1", kind="width_delta", delta=8)
    assert caught.value.code == "document_not_clean"
    assert not list(value.jobs.root.iterdir())


def test_discarded_ready_job_removes_bulk_artifacts_but_keeps_state(tmp_path: Path) -> None:
    value, _bridge, _source = service(tmp_path)
    job_id = value.start_job("doc_1", kind="width_delta", delta=8)["id"]
    wait_for(value, job_id, "ready")
    discarded = value.discard_job(job_id)
    assert discarded["status"] == "discarded"
    assert [item.name for item in value.jobs.path(job_id).iterdir()] == ["state.json"]


@pytest.mark.parametrize("shutdown", [False, True])
def test_discard_or_shutdown_cancels_external_preparation_and_cleans_its_copy(tmp_path: Path, shutdown: bool) -> None:
    entered = Event()

    class BlockingWorker(FakeWorker):
        @staticmethod
        def prepare(job_root, document, request, source_path, fingerprint, cancel):
            entered.set()
            cancel.wait(2)
            raise RuntimeError("job cancelled")

    source = tmp_path / "Disposable.glyphs"
    source.write_bytes(b"saved font")
    bridge = FakeBridge(source)
    value = SidecarService(
        bridge, jobs=JobStore(tmp_path / "jobs"), worker=BlockingWorker()
    )
    job_id = value.start_job("doc_1", kind="width_delta", delta=8)["id"]
    assert entered.wait(1)
    if shutdown:
        value.close()
        assert not value._cancellations
    else:
        assert value.discard_job(job_id)["status"] == "cancelling"
    wait_for(value, job_id, "cancelled")
    assert [item.name for item in value.jobs.path(job_id).iterdir()] == ["state.json"]


def test_fastmcp_surface_matches_the_protocol(tmp_path: Path) -> None:
    code = """
import asyncio
import json
from glyphs_mcp_sidecar.server import create_server

server = create_server(object())
tools = asyncio.run(server.get_tools())
print(json.dumps({name: tool.description for name, tool in tools.items()}, sort_keys=True))
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        str(REPO / "src" / name) for name in ("protocol", "bridge", "sidecar")
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    tools = json.loads(completed.stdout)
    assert tuple(name for name in TOOL_NAMES if name in tools) == TOOL_NAMES
    assert set(tools) == set(TOOL_NAMES)
    assert "not acceptance" in tools["apply_job"]


def test_bridge_client_sends_the_shared_token_without_a_socket() -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return json.dumps({"ok": True, "data": {"protocol": 1}}).encode()

    def open_request(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return Response()

    with patch("glyphs_mcp_sidecar.bridge_client.urlopen", side_effect=open_request):
        result = BridgeClient("http://127.0.0.1:9681", "x" * 32).status()
    assert result["protocol"] == 1
    assert captured == {
        "authorization": "Bearer " + "x" * 32,
        "url": "http://127.0.0.1:9681/v1/status",
        "timeout": 15.0,
    }


def test_native_worker_preserves_fractional_width_delta_without_native_rounding(monkeypatch) -> None:
    class GridWidthLayer:
        layerId = "M1"
        associatedMasterId = "M1"

        def __init__(self) -> None:
            self._width = 1349.36

        @property
        def width(self):
            return self._width

        @width.setter
        def width(self, value):
            self._width = round(value)

    layer = GridWidthLayer()
    font = type("Font", (), {"glyphs": [type("Glyph", (), {"name": "A", "layers": [layer]})()]})()
    monkeypatch.setattr(native_worker, "_load_font", lambda _path: font)
    result = native_worker.build_patch(
        {
            "jobId": "job_1",
            "document": {
                "id": "doc_1",
                "path": "/tmp/Disposable.glyphs",
                "generation": 3,
            },
            "request": {"kind": "width_delta", "delta": 8, "glyphs": []},
            "source": "/tmp/source.glyphs",
            "sourceHash": "sha256:" + "a" * 64,
        }
    )

    assert result["changes"][0]["before"] == 1349.36
    assert result["changes"][0]["after"] == 1357.36
    assert layer.width == 1349.36


def test_http_restart_does_not_require_a_new_client_session(tmp_path: Path) -> None:
    # Exercise the actual HTTP configuration chosen by main(), then send a
    # tool request carrying a previous process's session ID without initialize.
    code = r'''
import asyncio, json, tempfile
from unittest.mock import patch
import httpx
from glyphs_mcp_sidecar import server
captured = {}
class Capture:
    def run(self, **kwargs):
        captured.update(kwargs)
with patch.object(server, "load_or_create_token", return_value="x"*32), patch.object(server, "create_server", return_value=Capture()):
    server.main(["--transport", "http", "--jobs", tempfile.mkdtemp()])
class Service:
    closed = False
    def close(self):
        self.closed = True
    def get_status(self):
        return {"available": True}
async def check():
    service = Service()
    app = server.create_server(service).http_app(path=captured["path"], stateless_http=captured["stateless_http"])
    async with app.lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/mcp/", headers={"Accept":"application/json, text/event-stream", "Mcp-Session-Id":"old-process-session", "MCP-Protocol-Version":"2025-03-26"}, json={"jsonrpc":"2.0", "id":1, "method":"tools/call", "params":{"name":"get_status", "arguments":{}}})
            assert response.status_code == 200, response.text
            assert '"available":true' in response.text.replace(" ", "").replace('\\"', '"'), response.text
            assert not service.closed, "HTTP completion must not cancel external jobs"
asyncio.run(check())
'''
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(str(REPO / "src" / name) for name in ("protocol", "bridge", "sidecar"))
    subprocess.run([sys.executable, "-c", code], env=environment, check=True, capture_output=True, text=True)


@pytest.mark.parametrize("transport", ["http", "stdio"])
def test_server_shutdown_closes_external_workers(transport: str, tmp_path: Path) -> None:
    from glyphs_mcp_sidecar import server
    from unittest.mock import Mock

    service = Mock()
    mcp = Mock()
    mcp.run.side_effect = KeyboardInterrupt
    with patch.object(server, "load_or_create_token", return_value="x" * 32), \
         patch.object(server, "SidecarService", return_value=service), \
         patch.object(server, "create_server", return_value=mcp):
        with pytest.raises(KeyboardInterrupt):
            server.main(["--transport", transport, "--jobs", str(tmp_path / "jobs")])
    service.close.assert_called_once_with()


def test_selection_capability_is_negotiated_without_fallback(tmp_path):
    value, bridge, _ = service(tmp_path)
    try:
        bridge.status = lambda: {'protocol': 1, 'readCapabilities': ['selection.context.v1', 'unknown.future']}
        status = value.get_status()
        assert status['readCapabilities'] == ['selection.context.v1']
        assert tuple(status['tools']) == TOOL_NAMES
        bridge.status = lambda: {'protocol': 1, 'readCapabilities': ['selection.nodes.native.v1']}
        assert 'selection.context.v1' not in value.get_status()['readCapabilities']
        # The dictionary/fields pass through the existing route, with no extra
        # status request, alternate selector or synthesis of missing evidence.
        calls = []
        bridge.read_entities = lambda *args: calls.append(args) or [{'values': {'nodes': None}}]
        entities, fields = [{'kind':'selection','nodeLimit':64}], ['glyph','layer','nodes']
        assert value.read_entities('doc_1', entities, fields) == [{'values': {'nodes': None}}]
        assert calls == [('doc_1', entities, fields)]
    finally:
        value.close()
