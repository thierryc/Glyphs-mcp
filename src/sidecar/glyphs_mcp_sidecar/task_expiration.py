"""Expire abandoned intent without choosing Keep, Save, Undo or Restore.

Age never proves that native work stopped. A background pass checks that Glyphs
is idle and the task has no remaining native recovery before closing metadata.
Original errors, reports, receipts and action history are retained.
"""
from copy import deepcopy
import json
import math
import time

from .bridge_client import BridgeClientError
from .lifecycle import BUSY
from .saved_script import unresolved

INACTIVITY_DAYS = 1
INACTIVITY_SECONDS = INACTIVITY_DAYS * 86400
WAITING = {'queued', 'waiting_save', 'waiting_manual', 'outdated', 'blocked_active',
           'blocked_review', 'blocked_proposal', 'waiting_run', 'ready', 'needs_review',
           'interrupted', 'uncertain', 'applied'}
STOPPED = {'ready', 'applied', 'failed', 'cancelled', 'interrupted', 'accept_uncertain', 'expired'}
MESSAGE = 'Expired after inactivity. No further work will run. The font was not changed or saved; the recorded outcome and diagnostics were retained.'


def inactivity_days(service):
    """Shared desktop preference; missing means one day, invalid postpones expiry."""
    path = service.jobs.root / 'task-policy.json'
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError:
        return INACTIVITY_DAYS
    if (not isinstance(value, dict) or value.get('version') != 1 or
            type(value.get('inactivityDays')) is not int or not 1 <= value['inactivityDays'] <= 365):
        raise ValueError('Invalid task expiry settings; automatic expiry postponed.')
    return value['inactivityDays']


def _timestamp(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def last_activity(value, job=None, *, workflow=True):
    if workflow:
        # Reads, progress and startup reconciliation must not renew old intent.
        values = [value.get('createdAt'), value.get('lastActivityAt', value.get('updatedAt'))]
    else:
        values = [value.get('createdAt'), value.get('updatedAt'), value.get('finishedAt')]
    if job and (not workflow or job.get('status') != 'ready'):
        values += ([(job.get('expiration') or {}).get('inactiveSince')] if job.get('status') == 'expired'
                   else [job.get('updatedAt'), job.get('finishedAt')])
    return max((t for t in values if _timestamp(t)), default=None)


def due(value, job=None, *, now=None, workflow=True, days=INACTIVITY_DAYS):
    now = time.time() if now is None else now
    activity = last_activity(value, job, workflow=workflow)
    return (_timestamp(now) and activity is not None and activity <= now
            and now - activity >= days * 86400)


def _native_released(service, identity, *, save=False, preview=False):
    try:
        operation = (service.bridge.save_operation(identity) if save else service.bridge.operation(identity))
    except BridgeClientError as exc:
        if exc.code in {'job_not_found', 'save_not_found'}:
            return True
        raise
    if save and isinstance(operation, dict) and operation.get('status') == 'failed':
        return True
    if preview and isinstance(operation, dict):
        if operation.get('status') == 'ready':
            # This is an unapplied preview, not Undo of an applied font edit.
            operation = service.bridge.discard(identity)
        if operation.get('status') == 'cancelled' and not (operation.get('scriptResult') or {}).get('executed'):
            return True
    return isinstance(operation, dict) and operation.get('status') in {
        'completed', 'accepted', 'saved', 'discarded'}


def _released(service, value, job):
    if job and not _native_released(service, job['id'], preview=job['status'] == 'ready'):
        return False
    if not job and value.get('jobId') and not _native_released(service, value['jobId']):
        return False  # Missing local metadata does not prove native recovery is gone.
    request = value.get('saveRequest') or (job or {}).get('saveRequest')
    if request:
        return bool(request.get('saveId')) and _native_released(service, request['saveId'], save=True)
    return True


def _metadata(value, job, now, *, workflow, days):
    return dict(expiredAt=now, inactiveSince=last_activity(value, job, workflow=workflow),
                inactivityDays=days,
                previousState=value.get('state' if workflow else 'status'),
                previousJobStatus=((job or {}).get('expiration') or {}).get('previousJobStatus', (job or {}).get('status')),
                previousBlockerId=value.get('blockerId'), message=MESSAGE)


def expire(service, *, now=None, limit=100):
    """Nonblocking background maintenance; passive task reads never run it."""
    now = time.time() if now is None else now
    if not _timestamp(now):
        return 0
    try:
        days = inactivity_days(service)
    except (OSError, ValueError):
        return 0
    workflows = service.edit_workflows
    if not workflows.lock.acquire(blocking=False):
        return 0
    if not service._script_dispatch_lock.acquire(blocking=False):
        workflows.lock.release()
        return 0
    count = 0
    try:
        with service._lock, workflows.store.lock:
            if service.lifecycle.pending or service._cancellations or service.jobs.count(BUSY):
                return 0
            values = deepcopy(list(workflows.store.records.values()))
            jobs = {j['id']: j for j in service.jobs.records()}
        candidates = []
        owned = {v['jobId'] for v in values if v.get('jobId')}
        for value in values:
            job = jobs.get(value.get('jobId'))
            if value['state'] == 'queued' and value.get('cancelRequested'):
                continue
            if ((value['state'] in WAITING or unresolved(job or {})) and
                    (not job or job['status'] in STOPPED) and due(value, job, now=now, days=days)):
                candidates.append((value, job, True))
        for job in jobs.values():
            if (job['id'] not in owned and job['status'] in {'interrupted', 'accept_uncertain', 'applied'}
                    and due(job, now=now, workflow=False, days=days)):
                candidates.append((job, job, False))
        if not candidates:
            return 0
        try:
            native = service.bridge.status()
        except Exception:
            return 0
        if not isinstance(native, dict) or type(native.get('activeOperations')) is not int or native['activeOperations'] != 0:
            return 0
        with service.lifecycle.mutation():
            for value, job, workflow in candidates[:limit]:
                try:
                    released = _released(service, value, job)
                except Exception:
                    break  # Do not hold up dispatch by retrying a disconnected bridge per task.
                if not released:
                    continue
                with service._lock, workflows.store.lock, service.jobs._lock:
                    if (service.lifecycle.pending != 1 or service._cancellations or service.jobs.count(BUSY)
                            or workflow and workflows._find(value['id']) != value
                            or job and service.jobs.get(job['id']) != job):
                        continue
                    metadata = _metadata(value, job, now, workflow=workflow, days=days)
                    if job and job['status'] not in {'completed', 'accepted', 'discarded', 'expired'}:
                        job = service.jobs.update(job['id'], status='expired', expiration=metadata)
                    if workflow:
                        fields = dict(state='expired', expiration=metadata, scriptRunAuthorized=False,
                            autoKeepEnabled=False, savedVersion=None, blockerId=None, blocker=None,
                            blockingWorkflowId=None, queuePredecessorId=None,
                            job=service._public(job) if job else None)
                        workflows._set(workflows._find(value['id']), **fields)
                    count += 1
        return count
    except workflows.error:
        return count  # A settings/install reservation must postpone maintenance.
    finally:
        service._script_dispatch_lock.release()
        workflows.lock.release()


def stop_old_queued_intent(workflows, value):
    """Do not execute an old queue entry before the next maintenance pass."""
    if value.get('cancelRequested'):
        return False  # Honor an accepted cancellation through its normal cleanup.
    job = workflows.service.jobs.get(value['jobId']) if value.get('jobId') else None
    if job and job['status'] != 'ready':
        return False  # Reconcile real execution/results; age cannot stop them.
    try:
        days = inactivity_days(workflows.service)
    except (OSError, ValueError):
        workflows._set(value, state='interrupted', scriptRunAuthorized=False,
                       error=dict(code='task_policy_unavailable',
                                  message='Task expiry settings could not be read. This waiting request was paused; no edit was run.'))
        return True
    if not due(value, job, days=days):
        return False
    with workflows.store.lock:
        if job:
            # Retain the preview until idle maintenance checks its native owner.
            workflows._set(value, state='waiting_run' if job.get('resultKind') == 'script' else 'needs_review',
                           scriptRunAuthorized=False, queuedAction=None)
        else:
            workflows._set(value, state='expired', expiration=_metadata(value, None, time.time(), workflow=True, days=days),
                           scriptRunAuthorized=False, autoKeepEnabled=False, blockerId=None, blocker=None,
                           blockingWorkflowId=None, queuePredecessorId=None, job=None)
    return True
