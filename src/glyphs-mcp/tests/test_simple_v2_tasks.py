"""Passive inventory, conversation capture and native-script blocker evidence."""
from copy import deepcopy
import json
from threading import RLock
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_simple_v2_sidecar import JobStore
from glyphs_mcp_sidecar.edit_workflow_state import WorkflowStore, offered_actions
from glyphs_mcp_sidecar.task_inventory import list_tasks, register_origin
from glyphs_mcp_sidecar.task_origin_hook import association


@pytest.fixture
def inventory(tmp_path):
    jobs = JobStore(tmp_path / 'jobs')
    store = WorkflowStore(jobs.root)
    return SimpleNamespace(jobs=jobs, edit_workflows=SimpleNamespace(lock=RLock(), store=store))


def task(service, *, font='Bryan', state='applied', status='applied', kind='python_script'):
    document = dict(id=font, familyName=font, path='/tmp/' + font + '.glyphs')
    request = dict(kind=kind, options={})
    job = service.jobs.create(document, request)
    job = service.jobs.update(job['id'], status=status, resultKind='script' if kind == 'python_script' else 'mutation')
    value = service.edit_workflows.store.create(document, request, request, 'apply', uuid4().hex)
    service.edit_workflows.store.update(value, jobId=job['id'], job=job, state=state)
    return value, job


def test_inventory_is_passive_and_deduplicates_jobs(inventory):
    value, job = task(inventory)
    before = deepcopy(inventory.edit_workflows.store.records)
    jobs = inventory.jobs.records()
    result = list_tasks(inventory)
    assert len(result['tasks']) == 1
    item = result['tasks'][0]
    assert item['id'] == value['id'] and item['jobId'] == job['id']
    assert item['state'] == 'needs_decision' and not item['closed']
    assert inventory.edit_workflows.store.records == before
    assert inventory.jobs.records() == jobs
    assert not any(key in item for key in ('actions', 'action_token', 'request', 'source', 'nonce'))


def test_open_tasks_never_disappear_behind_history(inventory):
    value, _ = task(inventory)
    for _ in range(60):
        task(inventory, state='saved', status='accepted', kind='width_delta')
    page = list_tasks(inventory, limit=20)
    assert len(page['tasks']) == 21 and page['nextCursor'] == 20
    assert any(item['id'] == value['id'] for item in page['tasks'])
    final = list_tasks(inventory, cursor=40, limit=20)
    assert len(final['tasks']) == 21 and final['nextCursor'] is None


def test_cross_font_script_blockers_are_named_both_ways(inventory):
    owner, job = task(inventory)
    waiting, _ = task(inventory, font='LeftyNote', state='blocked_review', status='ready')
    inventory.edit_workflows.store.update(waiting, blockerId=job['id'])
    values = {item['id']: item for item in list_tasks(inventory)['tasks']}
    assert values[owner['id']]['blocking'] == [waiting['id']]
    assert values[waiting['id']]['blockedBy'] == [owner['id']]
    assert values[waiting['id']]['documentName'] == 'LeftyNote'
    assert values[waiting['id']]['state'] == 'blocked'


@pytest.mark.parametrize('status', ['failed', 'cancelled'])
def test_executed_partial_failures_remain_open(inventory, status):
    value, job = task(inventory, state=status, status=status)
    inventory.jobs.update(job['id'], bridgeOperation={'scriptResult': {'executed': True, 'executionSucceeded': False}})
    item = list_tasks(inventory)['tasks'][0]
    assert not item['closed'] and item['state'] == 'needs_decision'


def test_uncertain_and_interrupted_never_imply_success(inventory):
    for state in ['uncertain', 'interrupted']:
        task(inventory, state=state, status='accept_uncertain')
    assert all(not item['closed'] and not item['supportText'] for item in list_tasks(inventory)['tasks'])


def test_orphan_job_is_visible(inventory):
    job = inventory.jobs.create({'id': 'other', 'familyName': 'Other'}, {'kind': 'spacing'})
    item = list_tasks(inventory)['tasks'][0]
    assert item['id'] == job['id'] and item['workflowId'] is None


def test_origin_is_idempotent_and_never_revises_workflow(inventory):
    value, _ = task(inventory)
    before = deepcopy(value)
    identity = str(uuid4())
    first = register_origin(inventory, value['id'], 'codex', identity)
    assert register_origin(inventory, value['id'], 'codex', identity) == first
    assert value == before
    assert list_tasks(inventory)['tasks'][0]['origin']['conversationId'] == identity
    conflict = register_origin(inventory, value['id'], 'codex', str(uuid4()))
    assert conflict['conflict'] is True and conflict['conversationId'] == identity


@pytest.mark.parametrize('workflow,agent,identity', [('../bad','codex',str(uuid4())), ('edit_'+'a'*32,'other',str(uuid4())), ('edit_'+'a'*32,'codex','codex://settings')])
def test_origin_rejects_paths_and_arbitrary_links(inventory, workflow, agent, identity):
    with pytest.raises(ValueError):
        register_origin(inventory, workflow, agent, identity)


@pytest.mark.parametrize('agent,shape', [('codex','structured'),('claude_code','string'),('codex','content')])
def test_hook_extracts_only_successful_workflow_start(agent, shape):
    identity, workflow = str(uuid4()), 'edit_' + 'a'*32
    payload = {'ok': True, 'data': {'id': workflow}}
    response = {'structuredContent': payload} if shape == 'structured' else json.dumps(payload) if shape == 'string' else {'content': [{'type':'text','text':json.dumps(payload)}]}
    event = dict(hook_event_name='PostToolUse', tool_name='mcp__glyphs_mcp__start_edit_workflow', session_id=identity, tool_response=response)
    assert association(event, agent) == dict(agent=agent, workflowId=workflow, conversationId=identity)
    event['tool_name'] = 'mcp__glyphs_mcp__get_edit_workflow'
    assert association(event, agent) is None
    event['tool_name'] = 'mcp__another_server__start_edit_workflow'
    assert association(event, agent) is None


def test_failed_tool_result_never_associates_a_chat():
    event = dict(hook_event_name='PostToolUse', tool_name='mcp__glyphs-mcp__start_edit_workflow', session_id=str(uuid4()), tool_response={'isError': True, 'structuredContent': {'ok': True, 'data': {'id': 'edit_'+'a'*32}}})
    assert association(event, 'codex') is None


def test_preflight_failure_retains_existing_cancel(inventory):
    value, _ = task(inventory, state='failed', status='ready')
    value['error'] = {'code': 'document_busy'}
    assert offered_actions(value) == [('cancel', 'Cancel')]


def test_checkpoint_failure_is_separate_from_font_save(inventory):
    value, _ = task(inventory, state='saved', status='accepted', kind='width_delta')
    value['receipt'] = {'checkpoint': {'status': 'failed', 'error': {'message': 'Git unavailable'}}}
    item = list_tasks(inventory)['tasks'][0]
    assert item['closed'] and item['checkpointWarning'] == 'Git unavailable'
    assert 'Font saved' in item['supportText']


def test_management_inventory_has_local_auth_and_no_mutation_route(inventory):
    import asyncio
    import httpx
    from starlette.applications import Starlette
    from starlette.routing import Route
    from glyphs_mcp_sidecar.management import register_routes
    class Router:
        def __init__(self): self.routes = []
        def custom_route(self, path, methods):
            def decorate(callback):
                self.routes.append(Route(path, callback, methods=methods)); return callback
            return decorate
    inventory.get_status = lambda: {}
    router = Router(); register_routes(router, inventory, 'local-test-token')
    app = Starlette(routes=router.routes)
    value, _ = task(inventory)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1',1234)),base_url='http://local') as client:
            assert (await client.get('/internal/tasks')).status_code == 403
            headers = {'Authorization':'Bearer local-test-token'}
            result = await client.get('/internal/tasks',headers=headers)
            assert result.status_code == 200 and result.json()['data']['tasks'][0]['id'] == value['id']
            assert (await client.post('/internal/tasks',headers=headers,json={'action':'save'})).status_code == 405
            assert (await client.post('/internal/task-origins',headers=headers,json={'workflowId':value['id'],'agent':'codex','conversationId':str(uuid4())})).status_code == 200
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('192.0.2.1',1234)),base_url='http://local') as client:
            assert (await client.get('/internal/tasks',headers=headers)).status_code == 403
    asyncio.run(check())

@pytest.mark.parametrize('same_font', [True, False])
@pytest.mark.parametrize('result_kind', ['script', 'historical_restore'])
def test_restored_blocker_only_rebinds_its_own_document(inventory, same_font, result_kind):
    from glyphs_mcp_sidecar.edit_workflow import EditWorkflows
    value, own_job = task(inventory, font='Bryan' if same_font else 'LeftyNote', state='blocked_review', status='ready')
    owner = inventory.jobs.create({'id':'Bryan','familyName':'Bryan'}, {'kind':'python_script','options':{}})
    after = {'id':'Bryan-reloaded','familyName':'Bryan'}
    owner = inventory.jobs.update(owner['id'],status='discarded',resultKind=result_kind,
        document=after if result_kind == 'historical_restore' else owner['document'],
        restoreRequest={'documentId':'Bryan'},
        bridgeOperation={'scriptResult':{'beforeRunRestored':True,'documentAfter':after}} if result_kind == 'script' else {'documentAfter':after})
    inventory.edit_workflows.store.update(value,blockerId=owner['id'])
    coordinator = EditWorkflows.__new__(EditWorkflows)
    coordinator.service = inventory
    coordinator.store = inventory.edit_workflows.store
    coordinator.baseline_memos = {}
    inventory.get_job = lambda identity: inventory.jobs.get(identity)
    began=[]
    coordinator._begin=lambda request: began.append(request['document']['id'])
    coordinator._advance(value, allow_apply=False)
    assert began == ['Bryan-reloaded' if same_font else 'LeftyNote']


def test_unverified_acknowledgement_never_becomes_a_success_receipt(inventory):
    value, job = task(inventory, state='executed',status='completed')
    inventory.jobs.update(job['id'],outcome='unverified')
    item=list_tasks(inventory)['tasks'][0]
    assert item['closed'] and item['state']=='unknown' and item['supportText'] is None


def test_hook_uses_existing_custom_port_token_and_no_proxy_or_redirect(tmp_path, monkeypatch):
    import io
    import plistlib
    import glyphs_mcp_sidecar.task_origin_hook as hook
    home = tmp_path / 'home'; home.mkdir()
    token = home / 'custom-token'; token.write_text('local-test-secret')
    launch = home / 'Library/LaunchAgents/com.ap.cx.glyphs-mcp-sidecar.plist'
    launch.parent.mkdir(parents=True)
    launch.write_bytes(plistlib.dumps({'ProgramArguments':['python','run.py','--port','9790'], 'EnvironmentVariables':{'GLYPHS_MCP_BRIDGE_TOKEN_FILE':str(token)}}))
    monkeypatch.setattr(hook.Path, 'home', lambda: home)
    event = dict(hook_event_name='PostToolUse',tool_name='mcp__glyphs-mcp__start_edit_workflow',session_id=str(uuid4()),tool_response=json.dumps({'ok':True,'data':{'id':'edit_'+'a'*32}}))
    monkeypatch.setattr(hook.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(json.dumps(event).encode())))
    captured = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return b'{}'
    class Opener:
        def open(self, request, timeout):
            captured.update(url=request.full_url, timeout=timeout, authorization=request.get_header('Authorization'), value=json.loads(request.data))
            return Response()
    def opener(*handlers):
        assert handlers[0].proxies == {}
        assert handlers[1].redirect_request(None,None,302,'Found',{},'https://example.com') is None
        return Opener()
    monkeypatch.setattr(hook, 'build_opener', opener)
    assert hook.main(['--agent','claude_code']) == 0
    assert captured['url']=='http://127.0.0.1:9790/internal/task-origins'
    assert captured['authorization']=='Bearer local-test-secret' and captured['timeout']==1
    assert captured['value']['conversationId']==event['session_id']


def test_closed_history_index_counts_all_tasks_without_loading_all_details(inventory):
    for _ in range(55): task(inventory,state='saved',status='accepted',kind='width_delta')
    page=list_tasks(inventory,limit=10)
    assert len(page['tasks'])==10 and len(page['index'])==55
    assert all(set(entry)=={'id','createdAt','closed','historyRevision'} for entry in page['index'])
    assert all(len(entry['historyRevision']) == 64 for entry in page['index'])

@pytest.mark.parametrize('native_state,expected', [('applied','needs_decision'),('applying','unknown'),('accept_uncertain','unknown'),('accepted','unknown')])
def test_failed_workflow_keeps_outstanding_native_evidence_visible(inventory, native_state, expected):
    task(inventory,state='failed',status=native_state,kind='width_delta')
    result=list_tasks(inventory)['tasks'][0]
    assert not result['closed'] and result['state']==expected
    assert result['supportText'] is None

@pytest.mark.parametrize('raw', ['[1,2]', 'false', '{bad json}', '{"agent":"codex","conversationId":123}'])
def test_corrupt_origin_falls_back_without_hiding_tasks(inventory, raw):
    value,_=task(inventory)
    path=inventory.jobs.root/'task-origins'/f"{value['id']}.json"
    path.parent.mkdir();path.write_text(raw)
    items=list_tasks(inventory)['tasks']
    assert len(items)==1 and items[0]['origin'] is None
