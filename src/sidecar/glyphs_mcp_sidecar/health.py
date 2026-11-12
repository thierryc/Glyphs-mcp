"""Passive status cache and portable, model-visible health feedback."""
from copy import deepcopy
import time
from threading import Event, RLock, Thread
from glyphs_mcp_protocol import health as contract


class StatusCache:
    def __init__(self, collect):
        self.collect = collect
        self.lock, self.stopped = RLock(), Event()
        self.wake = Event()
        self.thread = None
        self.value = dict(bridge=dict(reachable=False, checking=True), statusReady=False,
                          health=contract.unavailable())
        self.observed = None
        self.native_health = None
        self.native_observed = 0

    def refresh(self):
        started = time.monotonic()
        value = self.collect()
        with self.lock:
            if started < self.native_observed:
                # A newer admission response wins over a slower background collection.
                self.wake.set()
                return deepcopy(self.value)
            previous = self.value
            paused = self.native_health and self.native_health.get('admission', {}).get('deferExpensiveWork')
            if not value.get('bridge', {}).get('reachable') and paused:
                # A transport failure does not establish recovery or a new session.
                value['healthCapabilities'] = deepcopy(previous.get('healthCapabilities', []))
            else:
                self.native_health = deepcopy(value.get('health'))
                self.native_observed = time.monotonic()
            self.value, self.observed = value, time.monotonic()
        return value

    def snapshot(self):
        with self.lock:
            value = deepcopy(self.value)
            age = max(0, time.monotonic() - self.observed) if self.observed is not None else None
            checking = value.get('bridge', {}).get('checking', False)
            value['statusObservation'] = dict(ageSeconds=age, stale=(age is None and not checking) or (age is not None and age > 45))
            if self.native_health is not None:
                value['health'] = deepcopy(self.native_health)
                native_age = max(0, time.monotonic() - self.native_observed)
                value['health']['cacheAgeSeconds'] = native_age
                for name, signal in value['health'].get('signals', {}).items():
                    signal['ageSeconds'] = signal.get('ageSeconds', 0) + native_age
                    signal['stale'] = (signal.get('stale', False) or not value.get('bridge', {}).get('reachable')
                                       or name == 'footprint' and signal['ageSeconds'] > 45)
            if value['statusObservation']['stale']:
                value['bridge']['stale'] = True
                value['bridge']['reachable'] = False
                if not value.get('health', {}).get('admission', {}).get('deferExpensiveWork'):
                    value['health'] = contract.unavailable()
            return value

    def observe_health(self, native):
        # Called only by an actual admission check, never a feedback/status reader.
        with self.lock:
            self.native_health = deepcopy(native.get('health')) if contract.SNAPSHOT in native.get('healthCapabilities', []) else None
            self.value['healthCapabilities'] = list(native.get('healthCapabilities', []))
            self.native_observed = time.monotonic()
            old_session = self.value.get('bridge', {}).get('bridgeSessionId')
            if old_session and old_session != native.get('bridgeSessionId'):
                # Do not combine old negotiated capabilities with a restarted bridge.
                self.value['bridge'] = dict(native, reachable=True, checking=True)
                self.value['statusReady'] = False
                for key in ('readCapabilities', 'writeCapabilities', 'jobCapabilities', 'jobKinds', 'nativeActions'):
                    self.value[key] = []
                self.wake.set()

    def start(self):
        if self.thread is not None:
            return
        def run():
            delay = 0 if self.observed is None else 5 if self.value.get('activity', {}).get('activeCount') else 30
            while not self.stopped.is_set():
                self.wake.wait(delay)
                self.wake.clear()
                if self.stopped.is_set(): break
                try:
                    value = self.refresh()
                    delay = (5 if value.get('activity', {}).get('activeCount') else 30) if value.get('bridge', {}).get('reachable') else min(60, delay * 2)
                except Exception:
                    delay = min(60, delay * 2)
                # Coalesce mutation notifications without a refresh feedback loop.
                self.stopped.wait(1)
        with self.lock:
            if self.thread is None:
                self.thread = Thread(target=run, name='glyphs-status-cache', daemon=True)
                self.thread.start()

    def close(self):
        self.stopped.set()
        self.wake.set()
        if self.thread: self.thread.join(timeout=2)


def feedback(service, payload, *, work='overview'):
    status = getattr(service, 'get_status', None)
    value = (payload.get('error') or {}).get('details', {}).get('health') or (status().get('health') if status else None)
    data = payload.get('data')
    if work == 'document' and isinstance(data, dict) and data.get('alreadyOpen') is True:
        work = 'routine'
    notice = contract.advisory(value, work=work)
    if notice:
        payload['health'] = notice
    return payload
