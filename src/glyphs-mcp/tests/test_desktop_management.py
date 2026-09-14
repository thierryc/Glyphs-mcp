"""Private routes share the MCP listener and cannot bypass the idle gate."""
import asyncio
import sys
from pathlib import Path

import httpx
import pytest

from test_simple_v2_sidecar import service, wait_for
from test_simple_v2_server_control import server, free_port_probe
from glyphs_mcp_sidecar.server import create_server
from glyphs_mcp_sidecar.service import ServiceError, SidecarService
from glyphs_mcp_sidecar.jobs import JobStore


def test_authenticated_private_routes_and_unchanged_public_tools(tmp_path):
    value, _, _ = service(tmp_path)
    async def check():
        mcp = create_server(value, control_token="x" * 32)
        assert len(await mcp.get_tools()) == 7
        app = mcp.http_app(stateless_http=True)
        async with app.lifespan(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
                assert (await client.get("/internal/status")).status_code == 403
                assert (await client.post("/internal/control", json={"action": "reserve"})).status_code == 403
                client.headers["Authorization"] = "Bearer " + "x" * 32
                response = await client.get("/internal/status")
                assert response.json()["data"]["controlProtocol"] == 1
                assert response.headers["cache-control"] == "no-store"
                reserve = await client.post("/internal/control", json={"action": "reserve"})
                identity = reserve.json()["data"]["reservationId"]
                with pytest.raises(ServiceError, match="reserved"):
                    value.start_job("doc_1", kind="width_delta", delta=8)
                assert (await client.post("/internal/control", json={"action": "stop"})).status_code == 400
                assert (await client.post("/internal/control", content="x" * 4097)).status_code == 400
                assert (await client.post("/internal/control", json={"action": "release", "reservationId": identity})).status_code == 200
        remote = httpx.ASGITransport(app=app, client=("192.168.1.5", 4000))
        async with httpx.AsyncClient(transport=remote, base_url="http://local", headers={"Authorization": "Bearer " + "x"*32}) as client:
            assert (await client.get("/internal/status")).status_code == 403
    asyncio.run(check())


@pytest.mark.parametrize("action,value", [("stop", None), ("port", "9790")])
def test_busy_control_leaves_process_and_settings_untouched(server, free_port_probe, monkeypatch, action, value):
    instance, state = server
    original = instance.agent.read_bytes()
    def busy(*args, **kwargs):
        raise RuntimeError("The service is busy")
    monkeypatch.setattr(instance, "_management", busy)
    with pytest.raises(RuntimeError, match="busy"):
        instance.run(action, value)
    assert instance.agent.read_bytes() == original
    assert state["running"]
    assert all(command[0] == "print" for command in state["commands"])


def test_failed_stop_releases_reservation(server, monkeypatch):
    from types import SimpleNamespace
    instance, state = server
    launch = instance._launchctl
    monkeypatch.setattr(instance, "_launchctl", lambda *args: SimpleNamespace(returncode=1, stderr="refused") if args[0] == "bootout" else launch(*args))
    with pytest.raises(RuntimeError, match="refused"):
        instance.run("stop")
    assert [entry[1] for entry in state["management"]] == ["reserve", "release"]
    assert state["running"]


def test_control_processes_share_one_exclusion_lock(server):
    instance, state = server
    with instance.exclusive():
        with pytest.raises(RuntimeError, match="already running"):
            instance.run("stop")
    assert state["commands"] == []


def test_control_refuses_a_listener_owned_by_another_process(server, monkeypatch):
    instance, state = server
    actions = []
    def manage(port, action, **values):
        actions.append(action)
        return {"reservationId": "other", "processId": 987}
    monkeypatch.setattr(instance, "_management", manage)
    with pytest.raises(RuntimeError, match="does not belong"):
        instance.run("stop")
    assert actions == ["reserve", "release"]
    assert state["running"] and all(command[0] == "print" for command in state["commands"])


def test_dispatch_intent_is_durable_before_native_reply(tmp_path):
    value, bridge, _ = service(tmp_path)
    job = value.start_job("doc_1", kind="width_delta", delta=8)
    wait_for(value, job["id"], "ready")
    calls = []
    def lost_reply(patch):
        calls.append(patch["jobId"])
        assert JobStore(value.jobs.root).get(job["id"])["status"] == "applying"
        raise TimeoutError("connection lost after dispatch")
    bridge.apply = lost_reply
    with pytest.raises(ServiceError):
        value.apply_job(job["id"])
    bridge.operation_state = "applied"
    restarted = SidecarService(bridge, jobs=JobStore(value.jobs.root), worker=value.worker)
    assert restarted.get_job(job["id"])["status"] == "applied"
    assert restarted.apply_job(job["id"])["status"] == "applied"
    assert calls == [job["id"]]


def test_worker_activity_covers_process_lifetime_and_failed_start(tmp_path, monkeypatch):
    from threading import Event
    from glyphs_mcp_sidecar.worker import GlyphsCliWorker
    from glyphs_mcp_sidecar import worker as module
    executable = tmp_path / "glyphs"; executable.write_text(""); executable.chmod(0o700)
    root = tmp_path / "job_abc"; root.mkdir()
    worker = GlyphsCliWorker(executable=str(executable), app="/Applications/Glyphs 4.app")
    def popen(*args, **kwargs):
        observed = worker.status()["executions"]
        assert observed[0]["jobId"] == root.name and observed[0]["phase"] == "starting"
        raise OSError("could not launch")
    monkeypatch.setattr(module.subprocess, "Popen", popen)
    with pytest.raises(OSError):
        worker.prepare(root, {}, {}, tmp_path / "font", "hash", Event())
    assert worker.status()["available"] and worker.status()["executions"] == []
