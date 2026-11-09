"""Bounded health evidence and admission policy; no native or filesystem access."""
from copy import deepcopy

SNAPSHOT = 'health.snapshot.v1'
ADMISSION = 'health.admission.v1'
RETRY_SECONDS = 15
RECOVERY_SECONDS = 30
DEFAULT_FONT_BUDGET = 8


def font_budget(value):
    if type(value) is not int or not 1 <= value <= 128:
        raise ValueError('The font warning threshold must be an integer from 1 to 128.')
    return value


def classify(signals, *, now, budget=DEFAULT_FONT_BUDGET, recovering=False):
    """Classify observations, never infer pressure from footprint or missing data."""
    reasons = []
    pressure = signals.get('pressure', {})
    dispatch = signals.get('dispatch', {})
    native = signals.get('documents', {})
    delay = dispatch.get('pendingSeconds', 0) if dispatch.get('available') else 0
    critical = pressure.get('value') == 'critical'
    if critical:
        reasons.append('memory_pressure_critical')
    elif pressure.get('available') and pressure.get('value') == 'warning':
        reasons.append('memory_pressure_warning')
    if delay > 10:
        reasons.append('native_dispatch_delayed')
    elif delay > 2:
        reasons.append('native_dispatch_slow')
    if native.get('available') and native.get('fontCount', 0) >= budget:
        reasons.append('font_budget_reached')
    if recovering and not critical and delay <= 10:
        reasons.append('recovering')
    paused = critical or delay > 10 or recovering
    known = any(s.get('available') and not s.get('stale') for name, s in signals.items() if name != 'policy')
    state = 'paused' if paused else 'caution' if reasons else 'normal' if known else 'unknown'
    actions = (['defer_expensive_work', 'reuse_open_documents', 'process_sequentially'] if paused else
               ['reuse_open_documents', 'process_sequentially', 'avoid_unnecessary_tabs'] if reasons else [])
    return dict(state=state, reasons=reasons, recommendedActions=actions,
                admission=dict(deferExpensiveWork=paused, retryAfterSeconds=RETRY_SECONDS if paused else 0),
                fontWarningThreshold=budget)


def unavailable():
    return dict(version=1, available=False, state='unknown', reasons=['health_unavailable'],
                recommendedActions=[], admission=dict(deferExpensiveWork=False, retryAfterSeconds=0))


def advisory(value):
    if not value or value.get('state') not in {'caution', 'paused'}:
        return None
    result = {key: deepcopy(value.get(key)) for key in (
        'version', 'bridgeSessionId', 'revision', 'state', 'reasons', 'recommendedActions', 'admission')}
    result['text'] = ('Glyphs Health: pause new expensive work; retry after the indicated delay. '
                      if value['state'] == 'paused' else 'Glyphs Health: reduce load. ')
    result['text'] += 'Reuse open documents, process files sequentially, and avoid unnecessary tabs. Reasons: ' + ', '.join(value.get('reasons', [])) + '.'
    return result


def refusal(value):
    return dict(execution='not_started', retryAfterSeconds=RETRY_SECONDS, health=deepcopy(value))
