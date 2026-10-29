"""Compact activity evidence without another job store or execution lifecycle."""
import math


def operation_counts(operation, *, whole_script=False):
    if whole_script:
        return None, None
    completed, total = operation.get('completedChanges'), operation.get('totalChanges')
    if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or int(v) != v
            for v in (completed, total)) or not 0 <= completed <= total or total <= 0):
        return None, None
    return completed, total


def workflow_progress(value):
    request = value['request']
    state = value['state']
    job = value.get('job') or {}
    operation = job.get('bridgeOperation') or {}
    script = request['kind'] == 'python_script'
    whole_script = script and (request.get('options') or {}).get('entrypoint', 'per_target') == 'script'
    automatic_ready = state == 'ready' and value.get('mode') == 'apply'
    working = state in {'starting', 'preparing', 'applying', 'saving', 'discarding', 'resolving'} or automatic_ready
    waiting = state in {'queued', 'blocked_active'} and (value.get('blocker') or {}).get('wait') not in {'decision', 'check'}
    finished = state in {'applied', 'executed', 'saved', 'discarded', 'cancelled', 'failed', 'expired', 'no_changes'}
    status = 'working' if working else 'waiting' if waiting else 'finished' if finished else 'needs_attention'
    labels = {'starting': 'Checking request', 'queued': 'Waiting to start',
              'blocked_active': 'Waiting for another task', 'preparing': 'Preparing script' if script else 'Preparing changes',
              'applying': 'Running script' if script else 'Applying changes', 'saving': 'Saving font',
              'discarding': 'Restoring font' if script else 'Undoing changes', 'resolving': 'Checking outcome',
              'ready': 'Preview ready', 'waiting_run': 'Script ready to run', 'waiting_save': 'Waiting for save choice',
              'applied': 'Script finished; verify the result' if script else 'Changes applied',
              'executed': 'Changes kept without saving', 'saved': 'Font saved', 'discarded': 'Recovery finished',
              'cancelled': 'Task cancelled', 'failed': 'Task failed', 'expired': 'Task expired', 'no_changes': 'No changes needed'}
    completed, total = operation_counts(operation, whole_script=whole_script)
    # Retain partial failure evidence, but never show an earlier apply counter as
    # progress for a save, restoration or queued request owned by another task.
    if state not in {'applying', 'applied', 'failed', 'cancelled', 'executed'} or value.get('blockerId'):
        completed, total = None, None
    label = labels.get(state, 'Needs attention')
    if automatic_ready:
        label = 'Preparing to run script' if script else 'Preparing to apply changes'
    if state == 'applying' and total is not None and completed == total:
        label = 'Finishing script' if script else 'Finishing changes'
    return {'workflowId': value['id'], 'jobId': value.get('jobId'), 'state': state,
            'status': status, 'phase': state, 'label': label,
            'completed': completed, 'total': total, 'unit': 'callbacks' if script else 'changes',
            'indeterminate': working and total is None, 'updatedAt': value.get('updatedAt')}
