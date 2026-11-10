"""Shared resource protection and explanations; never advances an operation.

Document recovery is independent of execution. An unrestricted invocation owns
the session only until native execution and cleanup have stopped. Unknown
native execution retains that protection until its existing reconciliation.
"""
from pathlib import PurePath

CAPABILITY = 'tasks.document-recovery.v1'
ACTIVE = {'preparing', 'cancelling', 'applying', 'rolling_back', 'discarding', 'accepting', 'saving'}
STOPPED_SCRIPT = {'failed', 'cancelled'}


def stopped_without_pending_writes(record, operation):
    if (operation.get('status') not in STOPPED_SCRIPT or record.get('status') not in STOPPED_SCRIPT
            or record.get('hasPendingWrites') or record.get('saveRequest') or record.get('restoreRequest')
            or operation.get('nativeSave')):
        return False
    for failure in (record.get('error') or {}, operation.get('error') or {}):
        details = failure.get('details') or {}
        if (failure.get('code') in {'restoration_unverified', 'bridge_operation_lost'}
                or details.get('writeAttempted') or details.get('execution') == 'uncertain' or details.get('cleanup')):
            return False
    return True


def stopped_script_released(record, operation=None):
    """Only explicit terminal native evidence can release a stopped script."""
    missing = operation is None and record.get('nativeOperationMissing') is True
    operation = operation if operation is not None else record.get('bridgeOperation') or record
    if not stopped_without_pending_writes(record, operation):
        return False
    if missing:
        return True  # Exact terminal operation confirmed absent by the live bridge.
    if operation.get('scriptRequest'):
        return (operation.get('scriptStage') == 'done' and 'cleanupSteps' not in operation
                and operation.get('scriptSnapshot') is None)
    recovery = (operation.get('scriptResult') or {}).get('recovery') or {}
    return (operation.get('stoppedReleased') is True and operation.get('recoveryAvailable') is False
            and recovery.get('available') is not True)


def protection(record):
    operation = record.get('bridgeOperation') or record
    request = record.get('request') or {}
    kind = request.get('kind')
    script = kind == 'python_script' or bool(operation.get('scriptRequest'))
    historical = kind == 'checkpoint_restore' or bool(operation.get('checkpointRestore'))
    status = record.get('status')
    evidence = operation.get('scriptResult') or {}
    error = record.get('error') or operation.get('error') or {}
    details = error.get('details') or {}
    document = record.get('document') or {}
    document_id = document.get('id') or operation.get('documentId')
    after = evidence.get('documentAfter') or operation.get('documentAfter') or {}
    if evidence.get('beforeRunRestored') or evidence.get('savedVersionRestored') or historical:
        document_id = after.get('id') or document_id
    reason, scope, wait = None, 'document', 'automatic'
    if status == 'accept_uncertain' or status == 'interrupted' and (
            error.get('code') == 'bridge_operation_lost' or details.get('execution') == 'uncertain'):
        reason, wait = 'outcome_unknown', 'check'
        scope = 'session' if script else 'document'
    elif status in {'failed', 'interrupted', 'applying', 'discarding'} and (
            error.get('code') == 'restoration_unverified' or historical and (
                details.get('writeAttempted') or record.get('restoreRequest'))):
        reason, scope, wait = 'outcome_unknown', 'session', 'check'
    elif status in ACTIVE:
        executing = script and (status == 'applying' or status in {'cancelling', 'discarding', 'rolling_back'}
                                and operation.get('status') not in {'applied', 'failed', 'cancelled', 'completed'})
        reason = 'execution' if executing else 'operation'
        scope = 'session' if executing else 'document'
    elif status == 'applied' or (script and status in STOPPED_SCRIPT and evidence.get('executed')
                                 and not stopped_script_released(record)):
        reason, wait = 'recovery', 'decision'
    elif status == 'ready' and record.get('resultKind') not in {'artifact', 'diagnostic'}:
        reason, wait = 'preview', 'decision'
    if reason is None:
        return None
    # Compiled-file comparisons and staged artifacts do not own live Glyphs.
    if record.get('inputKind') == 'compiled_fonts' or record.get('resultKind') == 'artifact':
        return None
    live = status != 'preparing' or script or record.get('preparationRoute') == 'native' or (
        kind == 'feature_compile' and request.get('options', {}).get('mode') == 'live')
    path = (document.get('path') or (operation.get('scriptRequest') or {}).get('sourcePath')
            or (operation.get('patch') or {}).get('sourcePath') or (operation.get('request') or {}).get('path'))
    return dict(jobId=record.get('id') or operation.get('jobId') or operation.get('saveId'),
                documentId=document_id, documentName=document.get('familyName') or (PurePath(path).name if path else 'this font'),
                scope=scope, reason=reason, wait=wait, live=live)


def conflicts(record, document_id, *, exclusive=False):
    owner = protection(record)
    return bool(owner and (owner['scope'] == 'session' or owner['documentId'] == document_id
                           or exclusive and owner['live'] and owner['reason'] == 'operation'))


def proof_conflicts(record, document_id):
    """Proof UI may inspect stopped edits without releasing their recovery.

    This exception belongs only to proof opening, never editing or closing.
    Keep conservative legacy statuses protected even without owner evidence.
    """
    from .document_closing import OWNING_STATUSES
    owner = protection(record)
    if owner and conflicts(record, document_id):
        return owner['reason'] != 'recovery'
    document = record.get('document') or {}
    same = (document.get('id') or record.get('documentId')) == document_id
    return same and record.get('status') in OWNING_STATUSES - {'applied'}


def describe(owner):
    name = owner['documentName']
    if owner['reason'] == 'queued_request':
        if owner['wait'] == 'check':
            return f'The earlier request for {name} needs an outcome check before this task can continue.'
        if owner['wait'] == 'decision':
            return f'Waiting for your decision on the earlier request for {name}. Open that task to continue.'
        return f'Waiting for the earlier request for {name}. This task will continue automatically.'
    if owner['reason'] == 'runtime_update':
        return f'This connection currently shares recovery across fonts. Review the earlier task in {name}, or update the bridge and sidecar together to allow independent fonts.'
    if owner['reason'] == 'outcome_unknown':
        return f'The outcome of earlier work in {name} is unknown. Check that task before continuing.'
    if owner['reason'] == 'execution':
        return f'Waiting for script execution and cleanup in {name}. This task will continue automatically when Glyphs is ready.'
    if owner['reason'] == 'recovery':
        return f'Earlier changes in {name} still have recovery available. Review that task before another edit to this font.'
    if owner['reason'] == 'preview':
        return f'An earlier preview for {name} needs a decision. Review or cancel that preview to continue.'
    return f'Waiting for another operation in {name} to finish. This task will continue automatically when Glyphs is ready.'


def retained(record):
    """Only truly finished, released records may leave the recent retry window."""
    owner = protection(record)
    return bool(owner or record.get('scriptSnapshot') is not None)
