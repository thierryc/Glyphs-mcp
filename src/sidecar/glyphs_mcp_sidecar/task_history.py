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
                if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('entries'), dict):
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
    with service.edit_workflows.lock, service._script_dispatch_lock, service._lock, service.jobs._lock:
        tasks = {task['id']: task for task in _tasks(service)}
        with service.lifecycle.mutation(), _ledger(service) as (data, path):
            entries = data['entries']
            changed = False
            for record in records:
                identity = record['id']; previous = entries.get(identity)
                if action == 'restore':
                    # Expiration is permanent only for that exact evidence.
                    if isinstance(previous, dict) and previous.get('phase') != 'expired':
                        del entries[identity]; changed = True
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
    if any(value.get('blockingWorkflowId') == task['id'] or
           (task.get('jobId') and value.get('blockerId') == task['jobId'])
           for value in service.edit_workflows.store.records.values()):
        return False
    if task.get('jobId') and job is None:
        return False
    if not job:
        return True
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
    return isinstance(operation, dict) and operation.get('status') in {'saved', 'accepted', 'completed', 'discarded'}


def _fresh(service, task, jobs, revision):
    from .task_inventory import _history_revision, _origin
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


def cleanup(service, *, now=None):
    """Drop expired summaries only after a fresh, idle, guarded snapshot."""
    if not (service.jobs.root / 'task-history' / 'ledger.json').exists():
        return 0
    now = time.time() if now is None else now
    if not math.isfinite(now):
        return 0
    from .task_inventory import _tasks
    with service.edit_workflows.lock, service._script_dispatch_lock, service._lock, service.jobs._lock:
        if (service.lifecycle.pending or service._cancellations or service.jobs.count(BUSY)
                or service.jobs.select(set(), include_unresolved=True)):
            return 0
        try:
            native = service.bridge.status()
            if type(native.get('activeOperations')) is not int or native['activeOperations'] != 0:
                return 0
        except Exception:
            return 0
        tasks = {task['id']: task for task in _tasks(service)}
        jobs = {job['id']: job for job in service.jobs.records()}
        expired = 0
        with service.lifecycle.mutation(), _ledger(service) as (data, path):
            changed = False
            for identity, entry in list(data['entries'].items()):
                if not isinstance(entry, dict):
                    continue
                task = tasks.get(identity)
                # New evidence / reopening cancels retention; never auto-clear it.
                if task and not _matches(entry, task):
                    del data['entries'][identity]; changed = True
                    continue
                cleared = entry.get('clearedAt')
                if (not task or entry.get('phase') != 'cleared' or type(cleared) not in (int, float)
                        or not math.isfinite(cleared) or cleared < 0 or now - cleared < RETENTION_SECONDS
                        or not _safe(service, task, jobs)):
                    continue
                # Native checks can take time. Recheck canonical evidence before
                # committing, including writes from another sidecar process.
                if not _fresh(service, task, jobs, entry['revision']):
                    continue
                # Minimal exclusion marker: no title, path, prompt, error or outcome.
                data['entries'][identity] = dict(phase='expired', revision=entry['revision'], expiredAt=now)
                changed = True; expired += 1
            if changed:
                _write(path, data)
        return expired


def start_cleanup(service, *, interval=3600):
    """Process lifetime worker, independent of the companion and MCP requests."""
    stopped = Event()
    def run():
        from .task_expiration import expire
        next_history = 0
        while not stopped.is_set():
            try:
                expire(service)
                if time.monotonic() >= next_history:
                    cleanup(service)
                    next_history = time.monotonic() + interval
            except Exception:
                logging.getLogger(__name__).info('Task maintenance postponed; retained records were left intact.')
            if stopped.wait(min(interval, 60)):
                break
    thread = Thread(target=run, name='glyphs-history-retention', daemon=True)
    thread.start()
    def stop():
        stopped.set()
        thread.join(timeout=1)
    return stop
