"""Identity and activity evidence must never change font execution semantics."""
import asyncio
import base64
import sys
import time
from threading import Event
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for component in ('sidecar', 'protocol', 'bridge'):
    sys.path.insert(0, str(ROOT/'src'/component))

import pytest
from fastmcp import Client
from fastmcp.tools.tool import ToolResult
from mcp import types

from glyphs_mcp_sidecar.activity_feedback import workflow_progress
from glyphs_mcp_sidecar.presentation import workflow_call
from glyphs_mcp_sidecar.server import create_server
from glyphs_mcp_sidecar.proxy import create_proxy
from test_simple_v2_edit_workflow import env, start


def workflow(state='applying', *, entrypoint='per_target', completed=3, total=10):
    return dict(id='edit_activity', jobId='job_activity', state=state, updatedAt=123,
                request=dict(kind='python_script', options=dict(entrypoint=entrypoint)),
                job=dict(bridgeOperation=dict(completedChanges=completed, totalChanges=total)))


def test_measured_callbacks_and_whole_script_have_different_evidence():
    value = workflow()
    before = deepcopy(value)
    progress = workflow_progress(value)
    assert (progress['completed'], progress['total'], progress['unit']) == (3, 10, 'callbacks')
    assert progress['status'] == 'working' and not progress['indeterminate']
    assert value == before
    whole = workflow_progress(workflow(entrypoint='script'))
    assert whole['indeterminate'] and whole['completed'] is whole['total'] is None
    assert workflow_progress(workflow(completed=10))['label'] == 'Finishing script'


@pytest.mark.parametrize('state,status', [('queued','waiting'), ('waiting_run','needs_attention'),
    ('uncertain','needs_attention'), ('failed','finished'), ('cancelled','finished'), ('applied','finished')])
def test_progress_does_not_resolve_waiting_or_failed_work(state, status):
    value = workflow(state)
    progress = workflow_progress(value)
    assert progress['status'] == status and not progress['indeterminate']
    if state in {'failed','cancelled'}:
        assert progress['completed'] == 3
    if state == 'queued':
        assert progress['completed'] is None
        value['blocker'] = dict(wait='decision')
        assert workflow_progress(value)['status'] == 'needs_attention'


@pytest.mark.parametrize('completed,total', [(True,10), (-1,10), (11,10), (3,float('nan')), (0,0), (None,10), (1.5,10), (3,10.5)])
def test_invalid_or_unknown_counts_stay_indeterminate(completed, total):
    progress = workflow_progress(workflow(completed=completed,total=total))
    assert progress['indeterminate'] and progress['completed'] is progress['total'] is None


def test_blocked_workflow_never_exposes_its_owners_counts():
    value = workflow()
    value['blockerId'] = 'unrelated_job'
    progress = workflow_progress(value)
    assert progress['completed'] is progress['total'] is None


def test_authorized_ready_work_stays_working_while_explicit_previews_wait():
    value = workflow('ready')
    value['mode'] = 'apply'
    assert workflow_progress(value)['status'] == 'working'
    assert workflow_progress(value)['indeterminate']
    value['mode'] = 'preview'
    assert workflow_progress(value)['status'] == 'needs_attention'
    assert not workflow_progress(value)['indeterminate']


def test_server_and_stdio_proxy_advertise_the_same_offline_brand(env):
    if not hasattr(types, 'Icon'):
        pytest.skip('Server icons require the MCP SDK in the locked private runtime')
    async def run():
        server = create_server(env[0])
        for target in (server, create_proxy(server)):
            async with Client(target) as client:
                info = client.initialize_result.serverInfo
                if not {'websiteUrl', 'icons'} <= set(type(info).model_fields):
                    pytest.skip('Initialize response branding requires the locked runtime MCP SDK')
                assert info.websiteUrl == 'https://ap.cx/gmcp'
                icon, = info.icons
                assert icon.mimeType == 'image/png' and icon.sizes == ['1024x1024']
                assert base64.b64decode(icon.src.split(',',1)[1]) == (ROOT/'plugins/glyphs-mcp/assets/icon.png').read_bytes()
    asyncio.run(run())


def test_progress_notifications_are_scoped_to_one_read_and_hide_context_from_schema(env, monkeypatch):
    monkeypatch.setattr('glyphs_mcp_sidecar.presentation.FEEDBACK_DELAY_SECONDS', 0)
    original_get = env[0].edit_workflows.get
    def slow_get(*args, **kwargs):
        time.sleep(.03)
        return original_get(*args, **kwargs)
    monkeypatch.setattr(env[0].edit_workflows, 'get', slow_get)
    env[1].adapter.dirty = True
    value = start(env)
    notices = []
    async def record(progress, total, message):
        notices.append((progress,total,message))
    async def run():
        async with Client(create_server(env[0])) as client:
            catalog = {tool.name:tool for tool in await client.list_tools()}
            assert len(catalog) == 22
            for name in ('start_edit_workflow','get_edit_workflow','show_edit_workflow','respond_edit_workflow'):
                tool = catalog[name]
                assert 'ctx' not in tool.inputSchema['properties']
                assert len(tool.meta['openai/toolInvocation/invoking']) <= 64
                assert len(tool.meta['openai/toolInvocation/invoked']) <= 64
                assert ('resourceUri' in tool.meta['ui']) == (name=='show_edit_workflow')
            result = await client.call_tool('get_edit_workflow', {'workflow_id':value['id']}, progress_handler=record)
            assert result.structured_content['data']['state'] == 'waiting_save'
    asyncio.run(run())
    assert [n[0] for n in notices] == [0,1]
    assert all(n[1] is None for n in notices), 'request stages must not invent script percentages'
    assert env[1].applies == 0 and not env[1].adapter.save_calls


def test_telemetry_failure_never_replays_or_fails_an_operation(monkeypatch):
    monkeypatch.setattr('glyphs_mcp_sidecar.presentation.FEEDBACK_DELAY_SECONDS', 0)
    calls = []
    notified = Event()
    class Offline:
        async def report_progress(self, *args, **kwargs):
            notified.set()
            raise ConnectionError('view closed')
    result = ToolResult(content=[], structured_content={'ok':True,'data':{'progress':{'label':'Running script'}}})
    def operation():
        calls.append('called')
        assert notified.wait(2)
        return result
    assert asyncio.run(workflow_call(operation,Offline(),'Preparing request')) is result
    assert calls == ['called']
    assert asyncio.run(workflow_call(lambda:result,None,'Preparing request')) is result


def test_fast_polling_does_not_emit_repeated_activity_messages():
    notices = []
    class View:
        async def report_progress(self, *args, **kwargs): notices.append(args)
    result = ToolResult(content=[], structured_content={'ok':True,'data':{}})
    assert asyncio.run(workflow_call(lambda:result,View(),'Checking workflow')) is result
    assert notices == []


def test_unresponsive_progress_receiver_cannot_hold_the_operation_result(monkeypatch):
    monkeypatch.setattr('glyphs_mcp_sidecar.presentation.FEEDBACK_DELAY_SECONDS', 0)
    monkeypatch.setattr('glyphs_mcp_sidecar.presentation.REPORT_TIMEOUT_SECONDS', .01)
    class Unresponsive:
        async def report_progress(self, *args, **kwargs): await asyncio.Event().wait()
    result = ToolResult(content=[], structured_content={'ok':True,'data':{}})
    def operation():
        time.sleep(.03)
        return result
    async def run():
        return await asyncio.wait_for(workflow_call(operation,Unresponsive(),'Preparing request'),timeout=1)
    assert asyncio.run(run()) is result


def test_request_cancellation_never_replays_or_interrupts_the_native_callback(monkeypatch):
    monkeypatch.setattr('glyphs_mcp_sidecar.presentation.FEEDBACK_DELAY_SECONDS', 0)
    started, release, finished = Event(), Event(), Event()
    calls, notices = [], []
    class View:
        async def report_progress(self, *args, **kwargs): notices.append(args)
    def operation():
        calls.append('once')
        started.set()
        assert release.wait(2)
        finished.set()
        return ToolResult(content=[], structured_content={'ok':True,'data':{}})
    async def run():
        task = asyncio.create_task(workflow_call(operation,View(),'Working'))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
            before = list(notices)
            release.set()
            assert await asyncio.to_thread(finished.wait, 1)
            await asyncio.sleep(0)
            assert notices == before
        finally:
            release.set()
    asyncio.run(run())
    assert calls == ['once']
