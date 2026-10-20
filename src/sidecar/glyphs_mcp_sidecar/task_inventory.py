"""Passive task projection and optional, local conversation associations.

Never calls get_job/get_edit_workflow: opening a monitor must not dispatch work.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import time
from threading import RLock

from .edit_workflow_state import TERMINAL, action_support_text
from .saved_script import unresolved

_ORIGIN_LOCK = RLock()

RUNNING = {'starting', 'preparing', 'applying', 'saving', 'accepting', 'discarding', 'cancelling', 'resolving'}
JOB_CLOSED = {'accepted', 'completed', 'discarded', 'cancelled', 'failed', 'interrupted'}
IDENTIFIER = re.compile(r'^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$')
WORKFLOW_ID = re.compile(r'^edit_[0-9a-f]{32}$')


def _label(request):
    return str((request.get('options') or {}).get('summary') or {
        'python_script': 'Run script', 'width_delta': 'Change widths', 'spacing': 'Adjust spacing',
        'kerning_edit': 'Edit kerning', 'kerning_collision': 'Review kerning',
        'checkpoint_restore': 'Restore font version', 'outline_edit': 'Edit outlines',
        'dimensions_edit': 'Change font settings', 'slant': 'Slant outlines',
        'start_nodes': 'Align start nodes', 'font_export': 'Export font',
        'feature_compile': 'Compile features',
    }.get(request.get('kind'), 'Font changes'))[:500]


def _state(value, job, workflow):
    state = value.get('state' if workflow else 'status', 'uncertain')
    if state in {'uncertain', 'accept_uncertain'}:
        return 'unknown', False
    if value.get('blockerId'):
        return 'blocked', False
    if job.get('status') == 'accept_uncertain':
        return 'unknown', False
    if workflow and state == 'failed' and job.get('status') in {'applied', 'ready', 'applying', 'accepting', 'discarding', 'accepted'}:
        return ('needs_decision' if job['status'] in {'applied', 'ready'} else 'unknown'), False
    if unresolved(job):
        return ('running' if job.get('status') in RUNNING else 'needs_decision'), False
    if state == 'failed' and job.get('status') == 'ready':
        return 'needs_decision', False
    if state == 'interrupted':
        return 'interrupted', False
    if state in RUNNING:
        return 'running', False
    if state in {'applied', 'ready', 'needs_review', 'waiting_run', 'waiting_save', 'waiting_manual', 'outdated'}:
        return 'needs_decision', False
    closed = state in (TERMINAL if workflow else JOB_CLOSED)
    if job.get('outcome') == 'unverified':
        return 'unknown', closed
    return ('failed' if state == 'failed' else 'closed') if closed else 'unknown', closed


def _origin_path(service, identity):
    return service.jobs.root / 'task-origins' / (identity + '.json')


def _origin(service, identity):
    try:
        value = json.loads(_origin_path(service, identity).read_text())
        if value.get('agent') not in {'codex', 'claude_code'} or not isinstance(value.get('conversationId'), str) or not IDENTIFIER.fullmatch(value['conversationId']) or ('conflict' in value and type(value['conflict']) is not bool):
            return None
        return {key: value[key] for key in ('agent', 'conversationId', 'capturedAt', 'conflict') if key in value}
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def register_origin(service, workflow_id, agent, conversation_id):
    if not WORKFLOW_ID.fullmatch(workflow_id or '') or agent not in {'codex', 'claude_code'} or not IDENTIFIER.fullmatch(conversation_id or ''):
        raise ValueError('Invalid conversation association')
    coordinator = service.edit_workflows
    with _ORIGIN_LOCK:
        if workflow_id not in coordinator.store.records:
            raise ValueError('Unknown workflow')
        path = _origin_path(service, workflow_id)
        existing = _origin(service, workflow_id)
        if existing:
            if existing['agent'] == agent and existing['conversationId'] == conversation_id:
                return existing
            value = dict(existing, conflict=True)
        else:
            value = dict(agent=agent, conversationId=conversation_id, capturedAt=time.time())
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value))
        temporary.chmod(0o600)
        temporary.replace(path)
        return value


def list_tasks(service, cursor=0, limit=50):
    if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Invalid task page')
    from .task_history import visible_history
    ordered = visible_history(service, _tasks(service))
    open_tasks = [task for task in ordered if not task['closed']]
    closed_tasks = [task for task in ordered if task['closed']]
    page = closed_tasks[cursor:cursor + limit]
    return dict(version=1, observedAt=time.time(), tasks=open_tasks + page,
                index=[{key: task[key] for key in ("id", "createdAt", "closed", "historyRevision")} for task in ordered],
                nextCursor=cursor + len(page) if cursor + len(page) < len(closed_tasks) else None)


def _tasks(service):
    """Complete passive snapshot, including retained history; never advances work."""
    coordinator = service.edit_workflows
    with coordinator.lock:
        values = deepcopy(list(coordinator.store.records.values()))
        jobs = {job['id']: job for job in service.jobs.records()}
        origins = {value['id']: _origin(service, value['id']) for value in values}
        from .script_service import execution_blockers
        global_blockers = execution_blockers(service)
    tasks, owned = [], set()
    for value in values:
        job_id = value.get('jobId')
        job = jobs.get(job_id) or (value.get('job') if not value.get('blockerId') else None) or {}
        if job_id:
            owned.add(job_id)
        state, closed = _state(value, job, True)
        task = _project(value, job, state, closed, True)
        task['origin'] = origins[value['id']]
        task['historyRevision'] = _history_revision(value, job, task['origin'])
        task['blockingJobIds'] = [value['blockerId']] if value.get('blockerId') else []
        # Native scripts serialize globally, including across documents.
        if not closed and not unresolved(job) and value.get('state') in {'starting', 'preparing', 'ready', 'waiting_run', 'failed', 'blocked_active', 'blocked_review', 'blocked_proposal'} and (value.get('request') or {}).get('kind') == 'python_script':
            task['blockingJobIds'] = list(dict.fromkeys(task['blockingJobIds'] + [j['id'] for j in global_blockers if j['id'] != job_id]))
        tasks.append(task)
    for job in jobs.values():
        if job['id'] not in owned:
            state, closed = _state(job, job, False)
            task = dict(_project(job, job, state, closed, False), origin=None, blockingJobIds=[])
            from .task_archive import marker, RECEIPT
            archived = marker(service, job, values)
            if archived:
                task.update(state='archived', closed=True, outcome='unverified', supportText=RECEIPT,
                            updatedAt=archived['archivedAt'])
            task['historyRevision'] = _history_revision(job, archived)
            tasks.append(task)
    by_job = {task['jobId']: task for task in tasks if task.get('jobId')}
    for task in tasks:
        task['blockedBy'] = [by_job[key]['id'] for key in task.pop('blockingJobIds') if key in by_job and not by_job[key]['closed'] and by_job[key]['id'] != task['id']]
        if task['blockedBy'] and task['state'] not in {'running', 'unknown', 'interrupted'}:
            task['state'] = 'blocked'
        task['blocking'] = []
    by_id = {task['id']: task for task in tasks}
    for task in tasks:
        for identity in task['blockedBy']:
            by_id[identity]['blocking'].append(task['id'])
    return sorted(tasks, key=lambda task: (task['updatedAt'], task['id']), reverse=True)


def _project(value, job, state, closed, workflow):
    document = value.get('document') or {}
    request = value.get('request') or {}
    error = value.get('error') or job.get('error') or {}
    receipt = value.get('receipt') or job.get('receipt') or {}
    checkpoint = receipt.get('checkpoint') or {}
    warning = checkpoint.get('error') if isinstance(checkpoint, dict) else None
    if isinstance(warning, dict):
        warning = warning.get('message') or 'The Git checkpoint failed; the font save succeeded.'
    if isinstance(checkpoint, dict) and checkpoint.get('status') == 'failed' and not warning:
        warning = 'The Git checkpoint failed; the font save succeeded.'
    return dict(id=value['id'], workflowId=value['id'] if workflow else None,
                jobId=value.get('jobId') if workflow else value['id'], title=_label(request),
                documentName=document.get('familyName') or Path(document.get('path') or 'Untitled').name,
                documentId=document.get('id'), path=document.get('path'), state=state, closed=closed,
                createdAt=value.get('createdAt', 0), updatedAt=value.get('updatedAt', value.get('createdAt', 0)),
                saveStatus=('unsaved' if document.get('dirty') else 'saved') if value.get('documentStateConfirmed') and type(document.get('dirty')) is bool else 'unknown',
                message=error.get('message'), supportText=action_support_text(dict(value, job=job)) if workflow and closed else None, outcome=value.get('state') if workflow else job.get('status'),
                checkpointWarning=warning,
                progress=job.get('bridgeOperation', {}).get('completedChanges'),
                total=job.get('bridgeOperation', {}).get('totalChanges'))


def _history_revision(*evidence):
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
