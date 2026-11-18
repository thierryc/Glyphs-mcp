"""Retention of cleared presentation history, independent of recovery evidence.

Only this ledger is rewritten. Jobs, workflow state, archive outcomes, receipts,
diagnostics and native operations are never deleted or changed here.
"""
from contextlib import contextmanager
import fcntl
import json
import logging
import math
import re
import time
from threading import Event, RLock, Thread

from .bridge_client import BridgeClientError
from .lifecycle import BUSY
from .saved_script import unresolved

RETENTION_SECONDS = 30 * 24 * 60 * 60
_LOCK = RLock()
_ID = re.compile(r'^(?:edit|job)_[0-9a-f]{32}$')
_REVISION = re.compile(r'^[0-9a-f]{64}$')


@contextmanager
def _ledger(service):
    root = service.jobs.root / 'task-history'
    with _LOCK:
        root.mkdir(mode=0o700, exist_ok=True)
        with (root / 'ledger.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = root / 'ledger.json'
            if path.exists():
                data = json.loads(path.read_text())
                if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('entries'), dict) or not isinstance(data.get('observed', {}), dict):
                    raise ValueError('Invalid history ledger; cleanup has been postponed.')
            else:
                data = dict(version=1, entries={})
            yield data, path


def _write(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, sort_keys=True, separators=(',', ':')))
    temporary.chmod(0o600)
    temporary.replace(path)


def _matches(entry, task):
    return (isinstance(entry, dict) and entry.get('revision') == task.get('historyRevision')
            and task['closed'] and not task['blockedBy'] and not task['blocking'])


def visible_history(service, tasks):
    # Reading Tasks remains passive. Corruption shows history instead of hiding
    # evidence. No timer, native reconciliation or cleanup runs in this read.
    path = service.jobs.root / 'task-history' / 'ledger.json'
    try:
        data = json.loads(path.read_text())
        if data.get('version') != 1 or not isinstance(data.get('entries'), dict):
            return tasks
        entries = data['entries']
        return [task for task in tasks if not (
            _matches(entries.get(task['id']), task) and entries[task['id']].get('phase') == 'expired')]
    except (OSError, ValueError, AttributeError, TypeError):
        return tasks


def change(service, action, records, *, now=None):
    """Authenticated companion outbox: clear is idempotent; restore cancels it."""
    if (action not in {'clear', 'restore'} or not isinstance(records, list) or not 1 <= len(records) <= 100
            or any(not isinstance(record, dict) or set(record) - {'id', 'revision'}
                   or not isinstance(record.get('id'), str) or not _ID.fullmatch(record['id'])
                   or ('revision' in record and (not isinstance(record['revision'], str)
                                                or not _REVISION.fullmatch(record['revision']))) for record in records)):
        raise ValueError('Invalid history request.')
    now = time.time() if now is None else now
    from .task_inventory import _tasks
    workflows = service.edit_workflows
    # Intake holds the workflow store before consulting jobs. Never retain the
    # job/service locks while waiting for that store (including inside _tasks).
    with workflows.lock, service._script_dispatch_lock, workflows.store.lock, service._lock, service.jobs._lock:
        tasks = {task['id']: task for task in _tasks(service)}
        with service.lifecycle.mutation(), _ledger(service) as (data, path):
            entries = data['entries']
            changed = False
            for record in records:
                identity = record['id']; previous = entries.get(identity)
                if action == 'restore':
                    # Expiration is permanent only for that exact evidence.
                    if isinstance(previous, dict) and previous.get('phase') != 'expired':
                        del entries[identity]
                        data.setdefault('observed', {})[identity] = dict(
                            revision=previous.get('revision'), since=now)
                        changed = True
                    continue
                task = tasks.get(identity)
                if (not task or not task['closed'] or task['blockedBy'] or task['blocking']
                        or ('revision' in record and record['revision'] != task['historyRevision'])):
                    continue
                if _matches(previous, task):
                    continue  # Lost replies and repeated Clear never reset the clock.
                entries[identity] = dict(phase='cleared', clearedAt=now, revision=task['historyRevision'], summary=task)
                changed = True
            if changed:
                _write(path, data)
        return dict(version=1, retentionDays=30)


def _safe(service, task, jobs):
    if not task['closed'] or task['blocking'] or task['blockedBy']:
        return False
    job = jobs.get(task.get('jobId'))
    with service.edit_workflows.store.lock:
        workflow = dict(service.edit_workflows.store.records.get(task.get('workflowId'), {}))
    if (any(workflow.get(k) for k in ('blockerId', 'pendingAction', 'queuedAction', 'queuePredecessorId'))
            or (workflow.get('savedVersion') or {}).get('available') or (job or {}).get('hasPendingWrites')):
        return False
    for request in (workflow.get('saveRequest'), (job or {}).get('saveRequest')):
        if request:
            from .task_expiration import _native_released
            try:
                if not request.get('saveId') or not _native_released(service, request['saveId'], save=True):
                    return False
            except Exception:
                return False
    if task.get('jobId') and job is None:
        return False
    if not job:
        return True
    if job.get('restoreRequest') and job['status'] != 'discarded':
        return False
    if unresolved(job) or job['status'] not in {'accepted', 'completed', 'discarded', 'cancelled', 'failed', 'interrupted', 'expired'}:
        return False
    if job['status'] == 'interrupted' and task['state'] != 'archived':
        return False
    try:
        operation = service.bridge.operation(job['id'])
    except BridgeClientError as exc:
        return exc.code == 'job_not_found'
    except Exception:
        return False
    # A failed/cancelled native result may still own partial-change recovery.
    from glyphs_mcp_protocol.task_conflicts import stopped_script_released
    return (isinstance(operation, dict) and not operation.get('hasPendingWrites')
        and not operation.get('recoveryAvailable')
        and not ((operation.get('scriptResult') or {}).get('recovery') or {}).get('available')
        and (operation.get('status') in {'saved', 'accepted', 'completed', 'discarded'}
        or job.get('resultKind') == 'script' and stopped_script_released(job, operation)))


def _fresh(service, task, jobs, revision):
    from .task_inventory import _history_revision, _origin
    if (service.lifecycle.pending != 1 or service._cancellations or service.jobs.count(BUSY)
            or any(value.get('queuePredecessorId') == task['id'] or value.get('blockingWorkflowId') == task['id']
                   or (task.get('jobId') and task['jobId'] in (value.get('blockerId'), value.get('blockingJobId')))
                   for value in service.edit_workflows.store.records.values())):
        return False
    try:
        job = jobs.get(task.get('jobId'))
        if job and service.jobs.get(job['id']) != job:
            return False
        if task.get('workflowId'):
            workflow = service.edit_workflows.store.records[task['workflowId']]
            recorded = json.loads((service.edit_workflows.store.root / (workflow['id'] + '.json')).read_text())
            return recorded == workflow and _history_revision(workflow, job or {}, _origin(service, workflow['id'])) == revision
        from .task_archive import marker
        return _history_revision(job, marker(service, job)) == revision
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _closure_bound(service, task, job, now):
    """Latest canonical evidence is a conservative upper bound on closure."""
    with service.edit_workflows.store.lock:
        workflow = dict(service.edit_workflows.store.records.get(task.get('workflowId'), {}))
    values = []
    for record in (workflow, job):
        if record:
            created, updated = record.get('createdAt'), record.get('updatedAt')
            if (type(created) not in (float, int) or type(updated) not in (float, int)
                    or not 0 < created <= updated):
                return None
            values.append(updated)
    for record in (workflow, job):
        if record and record.get('expiration'):
            values.append(record['expiration'].get('expiredAt'))
    if task['state'] == 'archived':
        values.append(task.get('updatedAt'))
    if task.get('origin'):
        values.append(task['origin'].get('capturedAt'))
    if values and all(type(t) in (int, float) and math.isfinite(t) and 0 < t <= now for t in values):
        return max(values)
    return None


def cleanup(service, *, now=None, limit=100):
    """Age closed summaries from durable closure evidence or verified observation."""
    now = time.time() if now is None else now
    if type(now) not in (int, float) or not math.isfinite(now) or now <= 0:
        return 0
    from .task_inventory import _tasks
    from .task_expiration import fair_batch
    workflows = service.edit_workflows
    with workflows.lock, service._script_dispatch_lock:
        service._history_backlog = False
        with workflows.store.lock, service._lock, service.jobs._lock:
            if service.lifecycle.pending or service._cancellations or service.jobs.count(BUSY):
                return 0
            tasks = {task['id']: task for task in _tasks(service)}
            jobs = service.jobs.inventory_records()
        expired = 0
        with service.lifecycle.mutation(), _ledger(service) as (data, path):
            entries = data['entries']
            observed = data.setdefault('observed', {})
            changed = False
            candidates = []
            for identity, task in tasks.items():
                entry = entries.get(identity)
                revision = task['historyRevision']
                observation = observed.get(identity)
                if entry is not None and not _matches(entry, task):
                    del entries[identity]
                    # Any later closure starts a fresh period. Keep this marker
                    # even while the task is open and across process restarts.
                    observed[identity] = dict(revision=None, since=now)
                    changed = True
                    entry = None
                    observation = observed[identity]
                if not task['closed'] or task['blockedBy'] or task['blocking']:
                    continue
                if entry is not None:
                    if entry.get('phase') != 'cleared':
                        continue
                    since = entry.get('clearedAt')
                    if type(since) not in (float, int) or not math.isfinite(since) or since <= 0:
                        continue
                elif observation is not None:
                    if not isinstance(observation, dict):
                        continue
                    since = observation.get('since') if observation.get('revision') == revision else None
                    if since is not None and (type(since) not in (int, float) or not math.isfinite(since) or since <= 0):
                        continue
                else:
                    since = _closure_bound(service, task, jobs.get(task.get('jobId')), now)
                if ((entry is None and observation is None) or since is None
                        or now - since >= RETENTION_SECONDS):
                    candidates.append((task, since))
            if candidates:
                try:
                    native = service.bridge.status()
                    idle = type(native.get('activeOperations')) is int and native['activeOperations'] == 0
                except Exception:
                    idle = False
                if idle:
                    checked = 0
                    for task, since in fair_batch(service, '_history_cursor', candidates, lambda row: row[0]['id'], limit):
                        identity, revision = task['id'], task['historyRevision']
                        if not _safe(service, task, jobs):
                            continue
                        with workflows.store.lock, service._lock, service.jobs._lock:
                            if not _fresh(service, task, jobs, revision):
                                continue
                        if since is None or now - since < RETENTION_SECONDS:
                            observed[identity] = dict(revision=revision, since=now if since is None else since)
                        else:
                            entries[identity] = dict(phase='expired', revision=revision, expiredAt=now)
                            observed.pop(identity, None)
                            expired += 1
                        changed = True
                        checked += 1
                    # Drain overdue work in bounded passes after a long shutdown.
                    # A protected batch yields until the next regular sweep.
                    service._history_backlog = len(candidates) > limit and checked > 0
            if changed:
                _write(path, data)
        return expired


def start_cleanup(service, *, interval=3600):
    """Process lifetime worker, independent of the companion and MCP requests."""
    stopped = Event()
    def attempt(operation, *args):
        try:
            operation(*args)
        except Exception:
            logging.getLogger(__name__).info('Task maintenance postponed: %s', operation.__name__)

    def run():
        from .task_expiration import expire
        next_history = 0
        while not stopped.is_set():
            attempt(service.edit_workflows.reconcile_stopped)
            attempt(service.health_cleanup.run_once)
            attempt(expire, service)
            if time.monotonic() >= next_history:
                attempt(cleanup, service)
                delay = min(15, interval) if getattr(service, '_history_backlog', False) else interval
                next_history = time.monotonic() + delay
            if stopped.wait(min(interval, 15)):
                break
    thread = Thread(target=run, name='glyphs-history-retention', daemon=True)
    thread.start()
    def stop():
        stopped.set()
        thread.join(timeout=1)
    return stop
