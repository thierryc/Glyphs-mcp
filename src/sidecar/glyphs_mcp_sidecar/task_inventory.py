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
from uuid import uuid4

from .edit_workflow_state import TERMINAL, action_support_text, remaining_work
from .saved_script import stopped_outcome, unresolved
from .preview_cleanup import failed_dispatch_pending
from glyphs_mcp_protocol.task_conflicts import protection, conflicts, describe, stopped_script_released

_ORIGIN_LOCK = RLock()
_PAGE_LOCK = RLock()

RUNNING = {'starting', 'preparing', 'applying', 'saving', 'accepting', 'discarding', 'cancelling', 'resolving'}
JOB_CLOSED = {'accepted', 'completed', 'discarded', 'cancelled', 'failed', 'interrupted', 'expired'}
IDENTIFIER = re.compile(r'^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$')
WORKFLOW_ID = re.compile(r'^edit_[0-9a-f]{32}$')


def _label(request):
    return str((request.get('options') or {}).get('summary') or {
        'python_script': 'Run script', 'width_delta': 'Change widths', 'spacing': 'Adjust spacing',
        'kerning_edit': 'Edit kerning', 'kerning_collision': 'Review kerning',
        'checkpoint_restore': 'Restore font version', 'outline_edit': 'Edit outlines',
        'dimensions_edit': 'Change font settings', 'slant': 'Slant outlines',
        'start_nodes': 'Align start nodes', 'font_export': 'Export font',
        'feature_compile': 'Compile features', 'checkpoint_save': 'Save font', 'font_compare': 'Compare fonts',
    }.get(request.get('kind'), 'Font changes'))[:500]


def _state(value, job, workflow):
    state = value.get('state' if workflow else 'status', 'uncertain')
    if state == 'expired':
        return 'expired', True
    owner = protection(job)
    if owner and owner['reason'] == 'outcome_unknown':
        return 'unknown', False
    if state in {'uncertain', 'accept_uncertain'}:
        return 'unknown', False
    if value.get('blockerId'):
        return 'blocked', False
    if state == 'queued':
        return 'waiting', False
    if failed_dispatch_pending(job) or job.get('previewReleasePending'):
        return 'waiting', False
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


def _file_version(path):
    try:
        info = path.stat()
        return info.st_ino, info.st_mtime_ns, info.st_size
    except FileNotFoundError:
        return None


def _inputs(service):
    return (service.edit_workflows.store.inventory_generation, service.jobs.inventory_generation,
            getattr(service, '_task_scoped_recovery', False), getattr(service, '_task_bridge_session', None),
            _file_version(service.jobs.root / 'task-origins'),
            _file_version(service.jobs.root / 'task-history' / 'ledger.json'))


def _snapshot(service):
    from .task_history import visible_history
    ordered = visible_history(service, _tasks(service))
    return (ordered, [task for task in ordered if not task['closed']],
            [task for task in ordered if task['closed']])


def list_tasks(service, cursor=0, limit=50, *, version=1, revision=None, include_index=False):
    if (type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 100
            or version not in (1, 2)):
        raise ValueError('Invalid task page')
    if version == 2:
        # One concurrent builder per generation. Capture the inputs before the
        # snapshot so a concurrent mutation always invalidates the next read.
        with _PAGE_LOCK:
            inputs = _inputs(service)
            cached = getattr(service, '_task_inventory_snapshot', None)
            if cached is None or cached[0] != inputs:
                cached = inputs, uuid4().hex, _snapshot(service)
                service._task_inventory_snapshot = cached
            _, current, (ordered, open_tasks, closed_tasks) = cached
        reset = bool(cursor and revision and revision != current)
        if reset:
            cursor = 0
        unchanged = cursor == 0 and revision == current and not include_index
        result = dict(version=2, revision=current, unchanged=unchanged, reset=reset,
                      totalCount=len(ordered), openCount=len(open_tasks), closedCount=len(closed_tasks))
    else:
        ordered, open_tasks, closed_tasks = _snapshot(service)
        unchanged = False
        result = dict(version=1)
    end = cursor + limit
    rows = [] if unchanged else open_tasks + closed_tasks[cursor:end]
    result.update(observedAt=time.time(), tasks=deepcopy(rows) if version == 2 else rows,
                  nextCursor=end if end < len(closed_tasks) else None)
    if version == 1 or include_index:
        result['index'] = [{key: task[key] for key in ('id', 'createdAt', 'closed', 'historyRevision')}
                           for task in ordered]
    return result


def _tasks(service):
    """Complete passive snapshot, including retained history; never advances work."""
    coordinator = service.edit_workflows
    # Workflow transitions mutate their records in place. Project while the
    # store is locked. JobStore replaces each indexed job on write, so its
    # detached mapping remains a stable read-only view across later writes.
    with getattr(coordinator.store, 'lock', coordinator.lock):
        return _project_tasks(service, list(coordinator.store.records.values()), service.jobs.inventory_records())


def _project_tasks(service, values, jobs):
    origins = {path.stem: _origin(service, path.stem)
               for path in (service.jobs.root / 'task-origins').glob('edit_*.json')}
    from .script_service import execution_blockers, scoped_recovery
    scoped = scoped_recovery(service)
    bridge_session = getattr(service, '_task_bridge_session', None)
    owners = [job for job in jobs.values() if protection(job)]
    tasks, owned = [], {value['saveRequest']['checkpointJobId'] for value in values
                        if (value.get('saveRequest') or {}).get('checkpointJobId')}
    by_workflow = {value['id']: value for value in values}
    referenced_jobs = {value.get(key) for value in values for key in ('jobId', 'blockerId', 'blockingJobId')}
    for value in values:
        job_id = value.get('jobId')
        job = jobs.get(job_id) or (value.get('job') if not value.get('blockerId') else None) or {}
        if job_id:
            owned.add(job_id)
        state, closed = _state(value, job, True)
        task = _project(value, job, state, closed, True, bridge_session=bridge_session)
        task['origin'] = origins.get(value['id'])
        task['historyRevision'] = _history_revision(value, job, task['origin'])
        pending = (not closed and not unresolved(job) and value.get('state') in {
            'queued', 'starting', 'preparing', 'ready', 'waiting_run', 'failed', 'blocked_active', 'blocked_review', 'blocked_proposal'})
        candidates = []
        if pending:
            if scoped or (value.get('request') or {}).get('kind') == 'python_script':
                candidates = execution_blockers(service, job_id, document_id=task['documentId'],
                    exclusive=(value.get('request') or {}).get('kind') == 'python_script', records=owners)
            elif value.get('blockerId') in jobs:
                candidates = [jobs[value['blockerId']]]
        task['blockingJobIds'] = [j['id'] for j in candidates]
        task['blockers'] = []
        if value.get('healthWait') and value.get('state') == 'queued':
            task['blockers'].append(dict(scope='session', reason='resource_pressure', wait='automatic',
                jobId=None, documentId=task['documentId'], message=value['healthWait']['text']))
        for candidate in candidates:
            owner = protection(candidate)
            if owner:
                if not scoped and owner['documentId'] != task['documentId'] and owner['reason'] in {'recovery', 'preview'}:
                    owner.update(scope='session', reason='runtime_update', wait='decision')
                task['blockers'].append(dict(owner, message=describe(owner)))
        predecessor = by_workflow.get(value.get('queuePredecessorId'))
        if predecessor and predecessor['state'] != 'expired' and not closed:
            from .workflow_queue import predecessor_blocker
            owner = predecessor_blocker(predecessor)
            if not owner.get('jobId') or not any(b.get('jobId') == owner['jobId'] for b in task['blockers']):
                task['blockers'].append(dict(owner, taskId=predecessor['id'], message=describe(owner)))
        tasks.append(task)
    for job in jobs.values():
        if job['id'] not in owned:
            state, closed = _state(job, job, False)
            task = dict(_project(job, job, state, closed, False, bridge_session=bridge_session), origin=None, blockingJobIds=[], blockers=[])
            from .task_archive import marker, RECEIPT
            archived = marker(service, job, ()) if job['id'] not in referenced_jobs else None
            if archived:
                task.update(state='archived', closed=True, outcome='unverified', supportText=RECEIPT,
                        updatedAt=archived['archivedAt'], remainingWork=None)
            task['historyRevision'] = _history_revision(job, archived)
            tasks.append(task)
    by_job = {task['jobId']: task for task in tasks if task.get('jobId')}
    for task in tasks:
        task['blockedBy'] = [by_job[key]['id'] for key in task.pop('blockingJobIds') if key in by_job and not by_job[key]['closed'] and by_job[key]['id'] != task['id']]
        task['blockedBy'] += [b['taskId'] for b in task['blockers'] if b.get('taskId') and b['taskId'] not in task['blockedBy']]
        if task['blockedBy'] and task['state'] not in {'running', 'unknown', 'interrupted'}:
            task['state'] = 'blocked'
        task['blocking'] = []
        for blocker in task['blockers']:
            owner_task = by_job.get(blocker['jobId'])
            blocker['taskId'] = owner_task['id'] if owner_task else blocker.get('taskId')
            blocker['workflowId'] = owner_task.get('workflowId') if owner_task else blocker.get('workflowId')
        if task['blockers'] and task['message'] and task['message'].startswith('Waiting for Glyphs.'):
            task['message'] = None  # The precise blocker below supplies the explanation.
        task['taskStatus'] = _task_status(task, task['blockers'])
        if task['blockers']:
            task['remainingWork'] = None  # The blocker card names the dependency and next step.
    by_id = {task['id']: task for task in tasks}
    for task in tasks:
        for identity in task['blockedBy']:
            by_id[identity]['blocking'].append(task['id'])
    return sorted(tasks, key=lambda task: (task['updatedAt'], task['id']), reverse=True)


def _task_status(task, blockers):
    if task['state'] == 'expired':
        return 'finished'
    if blockers:
        return 'needs_attention' if any(b['wait'] != 'automatic' for b in blockers) else 'waiting'
    if task['state'] == 'running':
        return 'working'
    if task['state'] == 'waiting':
        return 'waiting'
    if task['closed'] or task.get('outcome') == 'applied' and task['state'] == 'needs_decision' and not task.get('message'):
        return 'finished'
    return 'needs_attention'


def _outcome(value, job, workflow):
    state = value.get('state') if workflow else job.get('status')
    if state == 'expired':
        previous = (value.get('expiration') or {}).get('previousState')
        evidence = (job.get('bridgeOperation') or {}).get('scriptResult') or {}
        if (job.get('outcome') == 'partial' or
                ((job.get('error') or {}).get('details') or {}).get('recovery', {}).get('complete') is False):
            return 'Partial changes may remain'
        if job.get('outcome') == 'unverified':
            return 'Unverified'
        if evidence.get('executed'):
            return 'Unverified' if evidence.get('executionSucceeded') else 'Partial changes may remain'
        return 'Outcome unknown' if previous in {'uncertain', 'interrupted', 'accept_uncertain'} else None
    if job.get('outcome') == 'unverified':
        return 'Unverified'
    owner = protection(job)
    if owner and owner['reason'] == 'outcome_unknown':
        return 'Outcome unknown'
    stopped = stopped_outcome(job) or job.get('outcome')
    if stopped == 'unverified':
        return 'Unverified'
    if (stopped == 'partial' or unresolved(job)
            or ((job.get('error') or {}).get('details') or {}).get('recovery', {}).get('complete') is False):
        return 'Partial changes may remain'
    if state == 'completed' and job.get('resultKind') == 'diagnostic' and (job.get('report') or {}).get('success') is False:
        return 'Issues found'
    if state == 'applied':
        return 'Script finished' if job.get('resultKind') == 'script' else 'Changes applied'
    return {'saved': 'Saved', 'accepted': 'Saved' if job.get('resultKind') != 'artifact' else 'Exported',
            'executed': 'Changes kept', 'completed': 'Completed', 'discarded': 'Restored' if job.get('resultKind') in {'script', 'historical_restore'} else 'Discarded',
            'cancelled': 'Cancelled', 'failed': 'Failed', 'no_changes': 'No changes needed',
            'interrupted': 'Outcome unknown', 'uncertain': 'Outcome unknown'}.get(state)


def _recovery(value, job, bridge_session=None):
    if value.get('state', value.get('status')) == 'expired':
        return 'unavailable' if value.get('jobId') or job else 'none'
    if job.get('resultKind') in {'artifact', 'diagnostic', 'checkpoint'}:
        return 'none'
    operation = job.get('bridgeOperation') or {}
    evidence = operation.get('scriptResult') or {}
    recovery = value.get('savedVersion') or evidence.get('recovery') or {}
    if job.get('resultKind') == 'script' and stopped_script_released(job):
        return 'unavailable'
    if operation.get('restorationClosed') or job.get('status') in {'completed', 'accepted', 'discarded'}:
        return 'ended'
    if (job.get('error') or {}).get('code') in {'bridge_operation_lost', 'restoration_unverified'}:
        return 'unavailable'
    if recovery.get('bridgeSessionId') and bridge_session and recovery['bridgeSessionId'] != bridge_session:
        return 'unavailable'
    if recovery:
        return 'available' if recovery.get('available') else 'unavailable'
    if operation.get('recoveryAvailable') is True and job.get('status') == 'applied':
        return 'available'
    return 'unknown' if unresolved(job) or job.get('status') == 'applied' else 'none'


def _project(value, job, state, closed, workflow, *, bridge_session=None):
    document = value.get('document') or {}
    request = value.get('request') or {}
    error = value.get('error') or job.get('error') or {}
    message = error.get('message')
    expiration = value.get('expiration') or {}
    if state == 'expired':
        message = expiration.get('message', 'Task expired after inactivity. The recorded outcome was retained.')
        if error.get('message'):
            message += '\n' + error['message']
    if workflow and value.get('state') == 'queued':
        message = ('Cancelling this waiting request. It will not run.' if value.get('cancelRequested') else
                   'Waiting for Glyphs. This task will continue automatically when Glyphs is ready.')
    if ((error.get('details') or {}).get('recovery') or {}).get('complete') is False:
        message = 'Automatic recovery was incomplete. Inspect this font; partial changes may remain.' + (' ' + message if message else '')
    if error.get('code') == 'destination_exists' and (error.get('details') or {}).get('destination'):
        message = 'Choose a new export destination. This destination already exists: ' + error['details']['destination']
    receipt = value.get('receipt') or job.get('receipt') or {}
    checkpoint = receipt.get('checkpoint') or {}
    warning = checkpoint.get('error') if isinstance(checkpoint, dict) else None
    if isinstance(warning, dict):
        warning = warning.get('message') or 'The Git checkpoint failed; the font save succeeded.'
    if isinstance(checkpoint, dict) and checkpoint.get('status') == 'failed' and not warning:
        warning = 'The Git checkpoint failed; the font save succeeded.'
    recovery = _recovery(value, job, bridge_session)
    outcome = value.get('state') if workflow else job.get('status')
    if closed and state != 'expired':
        outcome = stopped_outcome(job) or job.get('outcome') or outcome
    return dict(id=value['id'], workflowId=value['id'] if workflow else None,
                jobId=value.get('jobId') if workflow else value['id'], title=_label(request),
                documentName=document.get('familyName') or Path(document.get('path') or 'Untitled').name,
                documentId=document.get('id'), path=document.get('path'), state=state, closed=closed,
                createdAt=value.get('createdAt', 0),
                updatedAt=expiration.get('inactiveSince') or value.get('updatedAt', value.get('createdAt', 0)),
                expiredAt=expiration.get('expiredAt'),
                saveStatus=('unsaved' if document.get('dirty') else 'saved') if value.get('documentStateConfirmed') and type(document.get('dirty')) is bool else 'unknown',
                message=message, supportText=action_support_text(dict(value, job=job)) if workflow and closed else None, outcome=outcome,
                recoveryStatus=recovery, outcomeLabel=_outcome(value, job, workflow),
                remainingWork=None if closed else remaining_work(value, job, recovery_status=recovery),
                checkpointWarning=warning,
                progress=job.get('bridgeOperation', {}).get('completedChanges'),
                total=job.get('bridgeOperation', {}).get('totalChanges'))


def _history_revision(*evidence):
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
