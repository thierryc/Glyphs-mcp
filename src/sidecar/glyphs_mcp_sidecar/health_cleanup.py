"""Bounded, passive cleanup evidence and guarded background preview expiry."""
from copy import deepcopy
from functools import wraps
import json
import math
from threading import Lock, RLock
import time

from .bridge_client import BridgeClientError
from .preview_cleanup import pending
from .task_expiration import inactivity_days, last_activity
from glyphs_mcp_protocol.task_conflicts import protection
from glyphs_mcp_protocol.health import advisory

CAPABILITY = 'health.cleanup.v1'
PRESSURE_REASONS = {'memory_pressure_warning', 'memory_pressure_critical',
                    'native_dispatch_slow', 'native_dispatch_delayed'}
DEFAULT_PRESSURE_IDLE = 600
MAX_CANDIDATES = 20
BATCH_LIMIT = 4
INTERVAL_SECONDS = 15


def status(method):
    @wraps(method)
    def decorated(service, *args, **kwargs):
        result = method(service, *args, **kwargs)
        policy = getattr(service, 'health_cleanup', None)
        if policy is not None:
            policy.annotate(result)
        return result
    return decorated


def feedback(service, payload):
    try:
        value = service.get_status().get('health') or {}
    except Exception:
        return payload  # Optional health feedback cannot turn a completed action into failure.
    if value.get('state') in {'caution', 'paused'}:
        notice = payload.get('health') or advisory(value)
        if notice is None:
            return payload
        payload['health'] = notice
        for key in ('cleanupCandidates', 'cleanupObservation', 'cleanupPolicy', 'cleanupRecentActions'):
            if key in value:
                notice[key] = deepcopy(value[key])
        notice['text'] += (
            ' Cleanup candidates are advisory; only abandoned unapplied previews may be released automatically.'
            ' Applied edits and uncertain work retain recovery.')
    return payload


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


class HealthCleanupPolicy:
    def __init__(self, service):
        self.service = service
        self.lock, self.running = RLock(), Lock()
        self.observed = None
        self.session = None
        self.candidates = []
        self.total = 0
        self.complete = False
        self.recent = []
        self.policy = dict(version=1, enabled=True, pressurePreviewIdleSeconds=DEFAULT_PRESSURE_IDLE,
                           normalPreviewIdleSeconds=86400, maxCandidates=MAX_CANDIDATES,
                           batchLimit=BATCH_LIMIT, intervalSeconds=INTERVAL_SECONDS)

    def _settings(self):
        path = self.service.jobs.root / 'health-cleanup-policy.json'
        try:
            with path.open('rb') as stream:
                raw = stream.read(4097)
            if len(raw) > 4096:
                raise ValueError('Cleanup policy exceeds 4096 bytes.')
            data = json.loads(raw)
            if (not isinstance(data, dict) or set(data) - {'version', 'enabled', 'pressurePreviewIdleSeconds'}
                    or type(data.get('version')) is not int or data['version'] != 1
                    or type(data.get('enabled', True)) is not bool
                    or type(data.get('pressurePreviewIdleSeconds', DEFAULT_PRESSURE_IDLE)) is not int
                    or not 30 <= data.get('pressurePreviewIdleSeconds', DEFAULT_PRESSURE_IDLE) <= 86400):
                raise ValueError('Invalid health cleanup policy; automatic cleanup is postponed.')
        except FileNotFoundError:
            data = {}
        normal = inactivity_days(self.service) * 86400
        return dict(self.policy, enabled=data.get('enabled', True),
                    pressurePreviewIdleSeconds=min(data.get('pressurePreviewIdleSeconds', DEFAULT_PRESSURE_IDLE), normal),
                    normalPreviewIdleSeconds=normal, error=None)

    def annotate(self, result):
        """No native call, job/history lock, file read, refresh or action here."""
        with self.lock:
            age = None if self.observed is None else max(0, time.monotonic() - self.observed)
            session = result.get('bridge', {}).get('bridgeSessionId')
            stale = (age is None or age > 45 or not result.get('bridge', {}).get('reachable')
                     or session != self.session)
            rows = deepcopy(self.candidates)
            if stale:
                for row in rows:
                    row.update(automatic=False, blockedBy='stale_cleanup_observation')
            value = result.get('health')
            if not isinstance(value, dict):
                value = deepcopy(result.get('bridge', {}).get('health')) or dict(version=1, available=False, state='unknown', reasons=[])
                result['health'] = value
            value.update(cleanupCandidates=rows, cleanupPolicy=deepcopy(self.policy),
                         cleanupObservation=dict(available=self.observed is not None, ageSeconds=age,
                            stale=stale, complete=self.complete, total=self.total,
                            bridgeSessionId=self.session), cleanupRecentActions=deepcopy(self.recent))
            result['cleanupCapabilities'] = [CAPABILITY]

    def _snapshot(self):
        service = self.service
        jobs, total = service.jobs.cleanup_records()
        store = service.edit_workflows.store
        owners = {}
        with store.lock:
            for job in jobs:
                rows = []
                for identity in store._jobs.get(job['id'], ()):
                    value = store.records[identity]
                    rows.append({key: value.get(key) for key in
                        ('id', 'jobId', 'state', 'mode', 'revision', 'createdAt', 'lastActivityAt', 'updatedAt')})
                owners[job['id']] = rows
        return jobs, owners, total

    def _candidate(self, job, owners, native, policy, now):
        health = native.get('health') or {}
        pressure = (health.get('available') is True and health.get('state') in {'caution', 'paused'}
                    and bool(PRESSURE_REASONS.intersection(health.get('reasons') or [])))
        idle = policy['pressurePreviewIdleSeconds'] if pressure else policy['normalPreviewIdleSeconds']
        owner = protection(job)
        evidence = (job.get('bridgeOperation') or {}).get('scriptResult') or {}
        reason = (owner or {}).get('reason')
        details = (job.get('error') or {}).get('details') or {}
        uncertain = (job['status'] in {'interrupted', 'accept_uncertain'}
                     or details.get('execution') == 'uncertain' or details.get('writeAttempted')
                     or details.get('partialEditsPossible') or (job.get('error') or {}).get('code') in
                     {'restoration_unverified', 'bridge_operation_lost'})
        recover = (reason == 'recovery' or job['status'] == 'applied' or evidence.get('executed')
                   or (job.get('bridgeOperation') or {}).get('recoveryAvailable'))
        preview = (job['status'] == 'ready' and job.get('resultKind') in {'script', 'mutation'}
                   and job['request']['kind'] != 'checkpoint_restore'
                   and not job.get('hasSaveOrRestore') and not recover and not uncertain)
        repair = pending(job) and not recover and not uncertain
        waiting = all(row['mode'] == 'preview' and row['state'] in
                      {'waiting_run', 'ready', 'needs_review', 'outdated', 'interrupted'} for row in owners)
        timestamps = [last_activity(row) for row in owners] if owners else [last_activity(job, workflow=False)]
        timestamp = max((stamp for stamp in timestamps if _finite(stamp)), default=None)
        eligible = timestamp + idle if timestamp is not None else None
        old = eligible is not None and _finite(now) and timestamp <= now and eligible <= now
        action = ('reconcile_outcome' if uncertain or reason == 'outcome_unknown' else
                  'review_recovery' if recover else 'release_preview' if (preview and waiting or repair) else 'wait')
        blocked = ('outcome_uncertain' if uncertain or reason == 'outcome_unknown' else 'recovery_preserved' if recover
                   else 'policy_disabled' if not policy['enabled'] else 'active_execution_intent' if preview and not waiting
                   else 'within_idle_timeout' if preview and not old else None)
        if action == 'release_preview' and blocked is None:
            if native.get('previewReleaseVersion') != 1 or not native.get('bridgeSessionId'):
                blocked = 'bridge_update_required'
            elif (type(native.get('activeOperations')) is not int or native['activeOperations'] != 0
                  or (health.get('signals', {}).get('dispatch') or {}).get('pendingSeconds', 0) > 2):
                blocked = 'native_busy'
        return dict(jobId=job['id'], workflowId=owners[0]['id'] if len(owners) == 1 else None,
                    documentId=job['document'].get('id'), documentName=job['document'].get('familyName'),
                    status=job['status'], reason='cancelled_preview_reservation' if repair else
                    'abandoned_preview' if preview and old and waiting else reason or 'outcome_requires_review',
                    action=action, automatic=action == 'release_preview' and blocked is None,
                    blockedBy=blocked, eligibleAt=eligible, idleSeconds=idle,
                    changesFont=False, preservesRecovery=True, estimatedMemoryBytes=None)

    def run_once(self, *, now=None):
        """Background-only; native release atomically refuses execution/recovery."""
        if not self.running.acquire(blocking=False):
            return 0
        service = self.service
        workflows = service.edit_workflows
        acquired = []
        released = 0
        rows = None
        try:
            now = time.time() if now is None else now
            if not _finite(now):
                return 0
            try:
                policy = self._settings()
            except (OSError, ValueError, TypeError) as exc:
                policy = dict(self.policy, enabled=False, error=str(exc)[:240])
            for lock in (workflows.lock, service._script_dispatch_lock):
                if not lock.acquire(blocking=False):
                    return 0
                acquired.append(lock)
            jobs, owners, total = self._snapshot()
            native = service.bridge.status()
            rows = [self._candidate(job, owners[job['id']], native, policy, now) for job in jobs]
            rows.sort(key=lambda row: (not row['automatic'], row['eligibleAt'] or float('inf')))
            with self.lock:
                self.candidates, self.total, self.complete = deepcopy(rows[:MAX_CANDIDATES]), total, total <= MAX_CANDIDATES
                self.policy, self.session, self.observed = policy, native.get('bridgeSessionId'), time.monotonic()
            if not any(row['automatic'] for row in rows):
                return 0
            original = {job['id']: job for job in jobs}
            with service.lifecycle.mutation():
                for row in [row for row in rows if row['automatic']][:BATCH_LIMIT]:
                    try:
                        with workflows.store.lock, service._lock:
                            if service._cancellations or service.jobs.count({'preparing', 'cancelling', 'applying', 'accepting', 'discarding'}):
                                break
                            current = service.jobs.get(row['jobId'])
                            # Another client can alter durable metadata. Never act
                            # on a stale status or an old conversation decision.
                            if current['status'] != original[row['jobId']]['status'] or current['updatedAt'] != original[row['jobId']]['updatedAt']:
                                continue
                            if any(workflows._find(owner['id'])['revision'] != owner['revision'] for owner in owners[row['jobId']]):
                                continue
                            try:
                                operation = service.bridge.release_preview(row['jobId'], row['documentId'], self.session)
                            except BridgeClientError as exc:
                                if exc.code != 'job_not_found':
                                    raise
                                operation = None  # Exact session confirmed no owner remains.
                            if operation is not None and (operation.get('jobId') != row['jobId'] or
                                    operation.get('documentId') != row['documentId'] or
                                    operation.get('status') not in {'cancelled', 'discarded'} or
                                    (operation.get('scriptResult') or {}).get('executed') or operation.get('recoveryAvailable')):
                                raise BridgeClientError('preview_release_unverified', 'Native release did not verify an unapplied preview.')
                            metadata = dict(expiredAt=now, inactiveSince=row['eligibleAt'] - row['idleSeconds'] if row['eligibleAt'] else None,
                                            previousJobStatus=current['status'], reason='health_cleanup',
                                            message='Abandoned unapplied preview released. No font edit or save was performed.')
                            updated = service.jobs.update(row['jobId'], nativePreviewReleased=True,
                                **(dict(status='expired', expiration=metadata) if current['status'] == 'ready' else {}))
                            if current['status'] == 'ready':
                                for owner in owners[row['jobId']]:
                                    workflows._set(workflows._find(owner['id']), state='expired', scriptRunAuthorized=False,
                                        autoKeepEnabled=False, savedVersion=None, expiration=metadata,
                                        job=service._public(updated), blockerId=None, blocker=None, blockingWorkflowId=None)
                            released += 1
                            row.update(status=updated['status'], automatic=False, action='none', reason='preview_released', blockedBy=None)
                            self._record(row['jobId'], 'released', now)
                    except Exception as exc:
                        row.update(automatic=False, blockedBy=getattr(exc, 'code', 'cleanup_deferred'))
                        self._record(row['jobId'], getattr(exc, 'code', 'cleanup_deferred'), now)
                        if getattr(exc, 'code', '') in {'bridge_unavailable', 'glyphs_busy', 'stale_bridge_session'}:
                            break
            return released
        except Exception:
            # Missing/failed observations never authorize cleanup. Passive reads
            # retain the last snapshot with its original age rather than refreshing it.
            return released
        finally:
            if rows is not None:
                with self.lock:
                    self.candidates = deepcopy(rows[:MAX_CANDIDATES])
            for lock in reversed(acquired):
                lock.release()
            self.running.release()

    def _record(self, job_id, outcome, now):
        with self.lock:
            self.recent = (self.recent + [dict(jobId=job_id, outcome=outcome, observedAt=now)])[-8:]
