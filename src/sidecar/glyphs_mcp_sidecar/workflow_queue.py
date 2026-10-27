"""Bounded, save-free workflow intake while native dispatch is occupied.

The coordinator lock serializes dispatch; the store lock only protects short
record updates. Accepting, inspecting and cancelling waiting requests therefore
does not depend on Glyphs answering a main-thread call.
"""
from copy import deepcopy
import hmac
import json
import time

from glyphs_mcp_protocol.task_conflicts import protection
from .edit_workflow_state import TERMINAL, action_token, public_workflow
from .saved_script import unresolved

MAX_QUEUED = 128


def validate_intake(workflows, kind, key, mode, delta, glyphs, options, auto_keep):
    if type(auto_keep) is not bool:
        raise workflows.error('invalid_request', 'auto_keep must be true or false.')
    if mode not in {'apply', 'preview'} or not isinstance(key, str) or not 1 <= len(key) <= 128:
        raise workflows.error('invalid_request', 'Use apply/preview mode and a stable 1-128 character idempotency key.')
    if kind in {'feature_compile', 'font_export'}:
        raise workflows.error('unsupported_job', 'Edit workflows support mutation jobs only; use the existing diagnostic/export tools.')
    if kind == 'checkpoint_restore':
        from .checkpoint_git import Repository, CheckpointError
        if delta is not None or glyphs is not None or not isinstance(options, dict) or set(options) != {'revision'}:
            raise workflows.error('invalid_request', 'checkpoint_restore takes only options={revision: exact full revision}.')
        try:
            Repository.validate_revision(options['revision'])
        except CheckpointError as exc:
            raise workflows.error(exc.code, str(exc)) from exc
        return dict(kind=kind, options=deepcopy(options))
    return workflows.service._job_request(kind, delta, glyphs, options)


def matching(workflows, document_id, arguments, mode, key, auto_keep):
    value = workflows.store.matching_key(key)
    if value is not None and (value['document']['id'] != document_id or value['arguments'] != arguments
            or value['mode'] != mode or value.get('autoKeepRequested', auto_keep) != auto_keep):
        raise workflows.error('idempotency_conflict', 'This idempotency key belongs to another edit request.')
    return value


def pending_peers(workflows, document_id, *, before=None):
    peers = [p for p in workflows.store.peers(document_id)
             if p['state'] not in TERMINAL or unresolved(p.get('job') or {})]
    if before is not None:
        peers = [p for p in peers if p['id'] != before['id'] and
                 (p.get('queueSequence', 0), p['createdAt'], p['id']) <
                 (before.get('queueSequence', 0), before['createdAt'], before['id'])]
    return sorted(peers, key=lambda p: (p.get('queueSequence', 0), p['createdAt'], p['id']))


def predecessor_blocker(predecessor):
    """A dependency may need a person even though this request is queued."""
    if predecessor.get('jobId'):
        owner = protection(predecessor.get('job') or {})
        if owner:
            return dict(owner, workflowId=predecessor['id'])
    state = predecessor['state']
    wait = (predecessor.get('blocker') or {}).get('wait')
    if not wait:
        wait = ('check' if state in {'uncertain', 'interrupted'} else
                'automatic' if state in {'starting', 'queued', 'preparing', 'applying', 'saving',
                                         'discarding', 'resolving', 'blocked_active'} else 'decision')
    return dict(jobId=None, workflowId=predecessor['id'], documentId=predecessor['document']['id'],
                documentName=predecessor['document'].get('familyName') or 'this font',
                scope='document', reason='queued_request', wait=wait)


def enqueue(workflows, document_id, arguments, request, mode, key, auto_keep):
    with workflows.service.lifecycle.mutation(), workflows.store.lock:
        if workflows.stopped.is_set():
            raise workflows.error('service_stopped', 'The workflow service is stopping.')
        value = matching(workflows, document_id, arguments, mode, key, auto_keep)
        if value is not None:
            return public_workflow(deepcopy(value))
        if sum(v['state'] == 'queued' or not v.get('jobId') and v['state'] in {
                'blocked_active', 'blocked_review', 'blocked_proposal'}
                for v in workflows.store.records.values()) >= MAX_QUEUED:
            raise workflows.error('queue_full', 'The waiting queue is full. Let existing tasks finish or cancel a waiting request.')
        document = deepcopy(getattr(workflows.service, '_document_cache', {}).get(document_id) or {'id': document_id})
        peers = pending_peers(workflows, document_id)
        if peers:
            document = deepcopy(peers[-1]['document'])
        value = workflows.store.create(document, arguments, request, mode, key, auto_keep=auto_keep,
            script_run_authorized=request['kind'] == 'python_script' and mode == 'apply')
        from .script_service import execution_blockers
        blockers = execution_blockers(workflows.service, document_id=document_id,
                                      exclusive=request['kind'] == 'python_script')
        if not hasattr(workflows.service, '_task_scoped_recovery'):
            # Negotiate in the supervisor, never on the fast intake path. Until
            # then, do not claim that another font's stopped recovery needs a decision.
            blockers = [j for j in blockers if (owner := protection(j)) and (
                owner['documentId'] == document_id or owner['reason'] not in {'recovery', 'preview'})]
        blocker = (predecessor_blocker(peers[-1]) if peers else
                   protection(blockers[0]) if blockers else None)
        workflows.store.update(value, state='queued', queuedAt=time.time(),
            queuePredecessorId=peers[-1]['id'] if peers else None,
            blockingWorkflowId=peers[-1]['id'] if peers else None,
            blocker=blocker, blockerId=blockers[0]['id'] if blockers and not peers else None,
            job=workflows.service._public(blockers[0]) if blockers and not peers else None)
        result = public_workflow(deepcopy(value), include_warning=True)
    workflows._start_runner()
    return result


def advance(workflows, value):
    """Only the dispatch supervisor admits a queued request to preparation."""
    if value.get('cancelRequested'):
        workflows._set(value, state='cancelled', queuePredecessorId=None, queueAdmitting=False,
                       scriptRunAuthorized=False)
        return
    if value.get('queueRetryAt', 0) > time.time():
        return
    predecessor = workflows.store.records.get(value.get('queuePredecessorId'))
    if predecessor:
        for transition in predecessor.get('documentRebindings') or []:
            if value['document']['id'] == transition['before']:
                workflows._rebind(value, transition['after'])
    peers = pending_peers(workflows, value['document']['id'], before=value)
    predecessor = peers[-1] if peers else None
    if predecessor is not None:
        identity = predecessor.get('jobId')
        if identity:
            job = workflows.service.jobs.get(identity)
            owner = protection(job)
            workflows._set(value, queuePredecessorId=None, blockerId=identity, job=workflows.service._public(job),
                blockingWorkflowId=predecessor['id'], blocker=owner, state='blocked_active')
            workflows._advance(value, allow_apply=False)
        else:
            workflows._set(value, queuePredecessorId=predecessor['id'],
                           blockingWorkflowId=predecessor['id'], blocker=predecessor_blocker(predecessor))
        return
    from .script_service import execution_blockers, scoped_recovery
    if not hasattr(workflows.service, '_task_scoped_recovery'):
        scoped_recovery(workflows.service, refresh=True)
    blockers = execution_blockers(workflows.service, document_id=value['document']['id'],
        exclusive=value['request']['kind'] == 'python_script')
    if blockers:
        job = blockers[0]
        owner = protection(job)
        workflows._set(value, blockerId=job['id'], job=workflows.service._public(job),
                       queuePredecessorId=None, blocker=owner, state='blocked_active')
        workflows._advance(value, allow_apply=False)
        return
    workflows._set(value, queuePredecessorId=None, blockingWorkflowId=None,
                   blockerId=None, blocker=None, job=None, queueAdmitting=True)
    try:
        workflows._begin(value)
    finally:
        workflows._set(value, queueAdmitting=False)


def cancel_waiting(workflows, workflow_id, revision, token, *, destination=None, approved_overwrites=None, automatic=False):
    with workflows.service.lifecycle.mutation(), workflows.store.lock:
        value = workflows._find(workflow_id)
        signature = json.dumps([destination, approved_overwrites] + ([True] if automatic else []), sort_keys=True)
        if token in value['usedActions']:
            if value['usedActions'][token] != signature:
                raise workflows.error('action_conflict', 'This action token was already used with different values.')
            return public_workflow(deepcopy(value))
        if value['state'] != 'queued':
            raise workflows.error('workflow_busy', 'Glyphs is finishing an operation. Refresh this same task for its current choices.')
        if type(automatic) is not bool or automatic or destination is not None or approved_overwrites is not None:
            raise workflows.error('invalid_request', 'Cancel does not take a destination, overwrite approval or automatic selection.')
        if (type(revision) is not int or revision != value['revision'] or not isinstance(token, str)
                or not hmac.compare_digest(action_token(value, 'cancel'), token)):
            raise workflows.error('stale_workflow_action', 'This choice is outdated. Refresh this workflow before choosing again.',
                                  details={'workflowId': value['id']})
        value['usedActions'][token] = signature
        workflows.store.update(value, cancelRequested=True, scriptRunAuthorized=False,
            state='queued' if value.get('queueAdmitting') or value.get('jobId') else 'cancelled',
            responseOrigin='explicit_action', queuePredecessorId=None,
            blocker=None, blockerId=None, blockingWorkflowId=None)
        return public_workflow(deepcopy(value))
