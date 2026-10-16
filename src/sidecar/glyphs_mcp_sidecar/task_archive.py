"""Archive orphan interrupted diagnostics without resolving execution or recovery.

The separate marker is bound to the complete job evidence. A later job update
invalidates it, so a changed outcome returns to the attention list.
"""
import hashlib
import hmac
import json
import secrets
import time

from .bridge_client import BridgeClientError
from .lifecycle import BUSY
from .saved_script import unresolved

RECEIPT = 'Task archived. Outcome: Unverified. Archiving did not change or save the font. Diagnostics have been retained.'
CONSEQUENCE = 'Move this interrupted task to recently closed tasks with an Unverified outcome. Keep its diagnostics. This does not stop work, save the font, restore changes, or confirm what happened in Glyphs.'


def fingerprint(job):
    return hashlib.sha256(json.dumps(job, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def marker(service, job, workflow_values=None):
    if workflow_values is None:
        with service.edit_workflows.lock:
            workflow_values = list(service.edit_workflows.store.records.values())
    if job['status'] != 'interrupted' or any(job['id'] in (value.get('jobId'), value.get('blockerId'), value.get('blockingJobId'))
            for value in workflow_values):
        return None
    try:
        value = service.jobs.read_json(job['id'], 'task-archive.json')
        if (value.get('version') == 1 and value.get('jobId') == job['id']
                and value.get('fingerprint') == fingerprint(job)
                and value.get('outcome') == 'unverified' and type(value.get('archivedAt')) in (int, float)):
            return value
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return None


def _reason(service, job):
    if job['status'] != 'interrupted':
        return 'Only interrupted tasks can be archived. Check this task in your agent.'
    values = service.edit_workflows.store.records.values()
    if any(value.get('jobId') == job['id'] for value in values):
        return 'This task still belongs to a workflow. Use its existing recovery choices or continue in your agent.'
    if any(job['id'] in (value.get('blockerId'), value.get('blockingJobId')) for value in values):
        return 'This task is blocking another request. Resolve it in your agent before archiving.'
    # Preserve the same script / historical-restore ownership that blocks new
    # mutations. A missing native operation is not permission to release it.
    details = (job.get('error') or {}).get('details') or {}
    if (unresolved(job) or job.get('restoreRequest') or job.get('saveRequest')
            or details.get('writeAttempted') or details.get('execution') == 'uncertain'
            or (job.get('request') or {}).get('kind') in {'python_script', 'checkpoint_restore'}):
        return 'Recovery or save ownership may remain unresolved. Review this task in your agent; it cannot be archived here.'
    if (service.lifecycle.pending or service._cancellations or service.jobs.count(BUSY)
            or service.jobs.select(set(), include_unresolved=True)):
        return 'Work or recovery is still active. Wait for it to finish, then check again.'
    try:
        native = service.bridge.status()
        if type(native.get('activeOperations')) is not int or native['activeOperations'] != 0:
            return 'Glyphs must be connected and have no active operations before archiving. Check again when idle.'
        try:
            service.bridge.operation(job['id'])
        except BridgeClientError as exc:
            if exc.code != 'job_not_found':
                raise
        else:
            return 'A native operation still exists for this task. Review its outcome and recovery choices in your agent.'
    except Exception:
        return 'The native operation could not be checked. Reconnect to Glyphs and check again; nothing was archived.'
    return None


def options(service, job_id):
    with service.edit_workflows.lock, service._script_dispatch_lock, service._lock, service.jobs._lock:
        job = service._job(job_id)
        archived = marker(service, job)
        reason = None if archived else _reason(service, job)
        digest = fingerprint(job)
        # Process-local secret: after a restart, the app must fetch fresh choices.
        if not hasattr(service, '_task_archive_secret'):
            service._task_archive_secret = secrets.token_bytes(32)
        token = hmac.new(service._task_archive_secret, ('archive_interrupted:' + digest).encode(), hashlib.sha256).hexdigest()
        document = job.get('document') or {}
        return dict(workflowId=None, jobId=job['id'], revision=int(digest[:13], 16),
                    state='archived' if archived else job['status'],
                    documentName=document.get('familyName') or 'Untitled font', path=document.get('path'),
                    message=RECEIPT if archived else reason or 'Archive this interrupted record after checking the font in Glyphs.',
                    warning=(job.get('error') or {}).get('message'), closed=bool(archived), pending=False,
                    receipt=RECEIPT if archived else None,
                    actions=[] if archived or reason else [dict(action='archive_interrupted', label='Archive Interrupted Task',
                                                              consequence=CONSEQUENCE, token=token)])


def respond(service, job_id, revision, token):
    with service.edit_workflows.lock, service._script_dispatch_lock, service._lock, service.jobs._lock:
        current = options(service, job_id)
        if (type(revision) is not int or revision != current['revision'] or not current['actions']
                or not hmac.compare_digest(current['actions'][0]['token'], token)):
            raise service.edit_workflows.error('stale_task_archive', 'Archiving is outdated or unsafe. Check the task again before choosing.')
        # Respect installation reservations. This writes only diagnostic metadata;
        # no native lifecycle action, artifact release, or job status change.
        with service.lifecycle.mutation():
            job = service._job(job_id)
            digest = fingerprint(job)
            expected = hmac.new(service._task_archive_secret, ('archive_interrupted:' + digest).encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, token):
                raise service.edit_workflows.error('stale_task_archive', 'The task changed while checking. Check again; nothing was archived.')
            service.jobs.write_json(job_id, 'task-archive.json', dict(version=1, jobId=job_id,
                fingerprint=digest, archivedAt=time.time(), outcome='unverified'))
        return options(service, job_id)
