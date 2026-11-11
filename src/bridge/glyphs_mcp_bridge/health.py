"""One bounded observer per bridge; snapshots never schedule native work."""
from collections import deque
from copy import deepcopy
import json
import time
from threading import Event, RLock, Thread

from glyphs_mcp_protocol import health as contract


class HealthMonitor:
    def __init__(self, session, *, clock=time.monotonic, wall=time.time):
        self.session, self.clock, self.wall = session, clock, wall
        self.lock, self.stopped = RLock(), Event()
        self.signals = {}
        self.observed_mono = {}
        self.history = deque(maxlen=60)
        self.revision = 0
        self.budget = None
        self.was_paused, self.recovered_at = False, None
        self.pending = {}
        self.observation_pending = False
        self.dirty = True
        self.thread = None
        self.resources = None
        self.policy_path = None

    def record(self, name, **value):
        with self.lock:
            if name == 'pressure' and value.get('value') == 'unknown' and self.signals.get(name, {}).get('value') == 'critical':
                value['value'] = 'critical'  # Loss of the observer is not evidence of recovery.
            self.signals[name] = dict(observedAt=self.wall(), **value)
            self.observed_mono[name] = self.clock()
            self.revision += 1
            self._recovery()

    def _delay(self):
        return max(0, self.clock() - min(self.pending.values())) if self.pending else 0

    def _recovery(self):
        critical = self.signals.get('pressure', {}).get('value') == 'critical' or self._delay() > 10
        if critical:
            self.was_paused, self.recovered_at = True, None
        elif self.was_paused:
            # Unknown pressure cannot clear a previously observed critical state.
            if self.signals.get('pressure', {}).get('value') == 'critical':
                return
            if self.recovered_at is None:
                self.recovered_at = self.clock()
            elif self.clock() - self.recovered_at >= contract.RECOVERY_SECONDS:
                self.was_paused, self.recovered_at = False, None

    def queued(self):
        with self.lock:
            if len(self.pending) >= 128:
                return None  # The oldest tracked calls already provide delay evidence.
            token = object()
            self.pending[token] = self.clock()
            return token

    def serviced(self, token):
        with self.lock:
            started = self.pending.pop(token, None)
            if started is not None:
                if self.clock() - started > 10:
                    self.was_paused, self.recovered_at = True, None
                self.record('dispatch', available=True, schedulingSeconds=max(0, self.clock() - started))

    def snapshot(self):
        with self.lock:
            now, wall = self.clock(), self.wall()
            signals = deepcopy(self.signals)
            for name, signal in signals.items():
                signal['ageSeconds'] = max(0, now - self.observed_mono[name])
                signal['stale'] = name == 'footprint' and signal['ageSeconds'] > 45
            signals.setdefault('dispatch', dict(available=False))['pendingSeconds'] = self._delay()
            signals['dispatch']['available'] = bool(self.pending) or signals['dispatch']['available']
            recovering = self.was_paused and (self.recovered_at is None or now - self.recovered_at < 30)
            policy = contract.classify(signals, now=now, budget=self.budget, recovering=recovering)
            return dict(version=1, available=True, bridgeSessionId=self.session, revision=self.revision,
                        observedAt=wall, signals=signals, **policy)

    def admit(self, error):
        value = self.snapshot()
        if value['admission']['deferExpensiveWork']:
            raise error('resource_pressure', 'Glyphs is reducing load. Defer new expensive work and retry after 15 seconds.',
                        details=contract.refusal(value))

    def invalidate_documents(self, _sender=None):
        with self.lock:
            self.dirty = True

    def observe_documents(self, adapter):
        try:
            observe = getattr(adapter, 'health_inventory', None)
            if observe is not None:
                self.record('documents', available=True, **observe())
            else:
                self.record('documents', available=False, complete=False)
        except Exception as exc:
            self.record('documents', available=False, complete=False, error=str(exc))

    def observe_footprint(self, value, now):
        self.history.append((now, value['bytes']))
        baseline_time, baseline_bytes = next(
            sample for sample in self.history if now - sample[0] <= contract.GROWTH_WINDOW_SECONDS
        )
        span = now - baseline_time
        if span >= 90:
            value = dict(value, growthBytes=value['bytes'] - baseline_bytes,
                         growthWindowSeconds=int(span))
        self.record('footprint', available=True, **value, sampleCount=len(self.history))

    def start(self, adapter, schedule, active, *, resources_factory=None, policy_path=None):
        if self.thread is not None:
            return
        if resources_factory is None:
            from .health_darwin import DarwinResources
            resources_factory = DarwinResources
        self.policy_path = policy_path
        # Initialization belongs to the main thread. No font traversal occurs on readers.
        self.observe_documents(adapter)
        self.dirty = False

        def run():
            try:
                self.resources = resources_factory(lambda value: self.record('pressure', available=value != 'unknown',
                    value=value, subscriptionActive=True))
                try:
                    self.record('pressure', available=False, value='unknown', subscriptionActive=True)
                    self.resources.subscribe()
                except Exception as exc:
                    self.record('pressure', available=False, value='unknown', subscriptionActive=False, error=str(exc))
            except Exception as exc:
                self.record('footprint', available=False, error=str(exc))
            next_sample = next_observe = 0
            while not self.stopped.is_set():
                now = self.clock()
                try:
                    busy = bool(active())
                except Exception as exc:
                    busy = False
                    self.record('dispatch', available=False, error=str(exc))
                state = self.snapshot()['state']
                interval = 30 if state == 'paused' else 15 if state == 'caution' else 5 if busy else 15
                if now >= next_sample:
                    if self.resources:
                        try:
                            self.observe_footprint(self.resources.footprint(), now)
                        except Exception as exc:
                            self.record('footprint', available=False, error=str(exc))
                    if policy_path:
                        try:
                            with policy_path.open('rb') as stream:
                                raw = stream.read(4097)
                            if len(raw) > 4096: raise ValueError('Health policy exceeds 4096 bytes')
                            value = json.loads(raw)
                            if type(value.get('version')) is not int or value['version'] != 1:
                                raise ValueError('Invalid health policy version')
                            with self.lock:
                                self.budget = contract.font_budget(value['fontWarningThreshold'])
                            self.record('policy', available=True)
                        except FileNotFoundError:
                            with self.lock: self.budget = None
                        except Exception as exc:
                            self.record('policy', available=False, error=str(exc))
                    next_sample = now + interval
                with self.lock:
                    self._recovery()
                    due = not self.observation_pending and now >= next_observe and (self.dirty or busy)
                    if due:
                        self.observation_pending, self.dirty = True, False
                if due:
                    token = self.queued()
                    def observe(token=token):
                        self.serviced(token)
                        try:
                            if not self.stopped.is_set(): self.observe_documents(adapter)
                        finally:
                            with self.lock: self.observation_pending = False
                    try:
                        schedule(observe)
                    except Exception as exc:
                        self.serviced(token)
                        with self.lock: self.observation_pending = False
                        self.record('documents', available=False, error=str(exc))
                    next_observe = now + max(5, interval)
                self.stopped.wait(1)
            if self.resources:
                self.resources.close()

        self.thread = Thread(target=run, name='glyphs-health', daemon=True)
        self.thread.start()

    def close(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=2)
