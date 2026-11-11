"""Bounded health evidence and admission policy; no native or filesystem access."""
from copy import deepcopy

SNAPSHOT = 'health.snapshot.v1'
ADMISSION = 'health.admission.v1'
RETRY_SECONDS = 15
RECOVERY_SECONDS = 30
GROWTH_WINDOW_SECONDS = 120

HEAVY_WORK = {
    'document': 'Reuse open fonts and open, import or duplicate one font at a time.',
    'export': 'Run exports or feature compiles one at a time.',
    'snapshot': 'Run one whole-font snapshot or restore at a time.',
    'comparison': 'Run one font comparison at a time.',
}


def job_work(kind):
    if kind in ('font_export', 'feature_compile'):
        return 'export'
    if kind in ('python_script', 'checkpoint_restore'):
        return 'snapshot'
    return 'routine'


def font_budget(value):
    if type(value) is not int or not 1 <= value <= 128:
        raise ValueError('The font warning threshold must be an integer from 1 to 128.')
    return value


def classify(signals, *, now, budget=None, recovering=False):
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
    if budget is not None and native.get('available') and native.get('fontCount', 0) >= budget:
        reasons.append('font_budget_reached')
    if recovering and not critical and delay <= 10:
        reasons.append('recovering')
    paused = critical or delay > 10 or recovering
    known = any(s.get('available') and not s.get('stale') for name, s in signals.items() if name != 'policy')
    state = 'paused' if paused else 'caution' if reasons else 'normal' if known else 'unknown'
    actions, _ = _guidance(reasons, paused, 'overview')
    return dict(state=state, reasons=reasons, recommendedActions=actions,
                admission=dict(deferExpensiveWork=paused, retryAfterSeconds=RETRY_SECONDS if paused else 0),
                fontWarningThreshold=budget)


def unavailable():
    return dict(version=1, available=False, state='unknown', reasons=['health_unavailable'],
                recommendedActions=[], admission=dict(deferExpensiveWork=False, retryAfterSeconds=0))


def _guidance(reasons, paused, work):
    if paused:
        return ['defer_expensive_work'], 'Defer new expensive work and retry after the indicated delay.'
    if 'native_dispatch_slow' in reasons:
        return ['process_sequentially'], 'Glyphs is responding slowly. Wait for the current operation before starting another.'
    if 'memory_pressure_warning' in reasons:
        prefix = 'macOS reports elevated system memory pressure. '
        if work in HEAVY_WORK:
            actions = ['process_sequentially']
            if work == 'document':
                actions.append('reuse_open_documents')
            return actions, prefix + HEAVY_WORK[work]
        if work == 'routine':
            return ['continue_routine_work'], prefix + 'Routine edits can continue.'
        return ['continue_routine_work', 'process_heavy_work_sequentially'], (
            prefix + 'Routine edits can continue. Run large imports, exports, comparisons and whole-font snapshots one at a time.')
    if 'font_budget_reached' in reasons:
        prefix = 'The configured open-font warning threshold was reached. '
        if work in ('overview', 'document'):
            return ['reuse_open_documents'], prefix + 'Reuse open fonts when possible.'
        return ['continue_routine_work'], prefix + 'Work in the current font can continue.'
    return [], ''


def advisory(value, *, work='overview'):
    if not value or value.get('state') not in {'caution', 'paused'}:
        return None
    result = {key: deepcopy(value.get(key)) for key in (
        'version', 'bridgeSessionId', 'revision', 'state', 'reasons', 'recommendedActions', 'admission')}
    actions, guidance = _guidance(value.get('reasons') or [], value['state'] == 'paused', work)
    if not guidance:
        return None
    result['recommendedActions'] = actions
    result['text'] = 'Glyphs Health: ' + guidance
    return result


def refusal(value):
    return dict(execution='not_started', retryAfterSeconds=RETRY_SECONDS, health=deepcopy(value))
