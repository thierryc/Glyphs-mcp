"""Native script preparation and current-state or historical recovery."""
from pathlib import Path
import time
from glyphs_mcp_protocol import ProtocolError, scripts
from .source import source_hash
from .worker import WorkerError

BASELINE_MEMO_SECONDS = 5.0


def unresolved(job):
    if job.get('resultKind') == 'historical_restore' and job.get('status') in {'failed','interrupted'}:
        return bool((job.get('error') or {}).get('details', {}).get('writeAttempted') or job.get('restoreRequest'))
    return (job.get('resultKind') == 'script' and job.get('status') in {'failed', 'cancelled'}
            and bool(((job.get('bridgeOperation') or {}).get('scriptResult') or {}).get('executed')))


def invalidate(service, document_id=None):
    memos = service.edit_workflows.baseline_memos
    for key, memo in list(memos.items()):
        if document_id is None or memo['documentId'] == document_id:
            memos.pop(key, None)


def prepare(service, job, cancel):
    doc = job['document']
    fingerprint = None  # Live state, not a saved file, is the execution baseline.
    service.jobs.update(job['id'], phase='preparing_native')
    try:
        if cancel.is_set(): raise WorkerError('job cancelled')
        operation = service.bridge.review_script(dict(jobId=job['id'], documentId=doc['id'], generation=doc['generation'],
            sourcePath=doc['path'], sourceHash=fingerprint, options=job['request']['options']))
        while operation['status'] == 'preparing':
            if cancel.wait(.01): raise WorkerError('job cancelled')
            operation = service.bridge.operation(job['id'])
        if operation['status'] != 'ready':
            from .bridge_client import BridgeClientError
            failure = operation.get('error') or dict(code='job_failed', message='script preparation did not finish')
            raise BridgeClientError(failure['code'], failure['message'], failure.get('details'))
        report = service.bridge.reviewed_script(job['id'])
    except Exception:
        try: service.bridge.discard(job['id'])
        except Exception: pass  # Preparation is read-only; it cannot have executed Python.
        raise
    path = service.jobs.write_json(job['id'], 'report.json', report)
    from .job_preparation import _mutation_report
    with service._lock:
        if cancel.is_set() or service.jobs.get(job['id'])['status'] != 'preparing':
            raise WorkerError('job cancelled')
        service.jobs.update(job['id'], status='ready', resultKind='script', sourceHash=fingerprint,
                            summary=job['request']['options'].get('summary', 'Native Python script'), changeCount=None, sample=[],
                            report=_mutation_report(report, path))


def execution_request(job, report, error):
    doc = job['document']
    request = dict(jobId=job['id'], documentId=doc['id'], sourcePath=doc['path'], sourceHash=job['sourceHash'],
                   generation=doc['generation'], options=job['request']['options'], manifest=report['manifest'])
    try: scripts.check_request(request)
    except ProtocolError as exc: raise error(exc.code, exc.message) from exc
    return request



def refresh(service, workflow):
    """A restoration action describes the entire currently observed document."""
    if workflow['request']['kind'] != 'python_script' or scripts.retired(workflow['request'].get('options', {})):
        return
    job = workflow.get('job') or {}
    executed = ((job.get('bridgeOperation') or {}).get('scriptResult') or {}).get('executed')
    if workflow['state'] in {'saved', 'executed', 'discarded'}:
        service.edit_workflows.baseline_memos.pop(workflow['id'], None)
        service.edit_workflows._set(workflow, savedVersion=None)
        return
    if not executed or workflow['state'] not in {'applied', 'failed', 'cancelled'}:
        return
    internal = service._job(job['id'])
    recovery = ((internal.get('bridgeOperation') or {}).get('scriptResult') or {}).get('recovery') or {}
    if recovery.get('kind') == 'memory_snapshot':
        result = dict(recovery, sourceHash=recovery['snapshotId'], available=False)
        try:
            document = service._document(internal['document']['id'])
            result.update(generation=document['generation'], available=bool(recovery.get('available')) and
                document.get('path') == internal['document'].get('path') and
                (internal.get('error') or {}).get('code') != 'restoration_unverified')
            service.edit_workflows._set(workflow, document=document)
        except Exception:
            pass
        result['message'] = 'Restore before run replaces the whole font with its pre-run state, including pre-existing unsaved edits. Later edits and Undo history are discarded. Recovery is lost when Glyphs restarts; external effects are excluded.'
        service.edit_workflows._set(workflow, savedVersion=result)
        return
    result = dict(available=False, path=internal['document']['path'], sourceHash=internal['sourceHash'])
    try:
        document = service._document(internal['document']['id'])
        result['generation'] = document['generation']
        info = Path(result['path']).stat()
        key = (job['id'], result['path'], result['sourceHash'], document['id'],
               document.get('path'), document.get('generation'), document.get('dirty'),
               info.st_ino, info.st_size, info.st_mtime_ns)
        memos = service.edit_workflows.baseline_memos
        memo = memos.get(workflow['id'])
        now = time.monotonic()
        if not memo or memo['key'] != key or now - memo['checkedAt'] >= BASELINE_MEMO_SECONDS:
            memo = dict(key=key, documentId=document['id'], checkedAt=now,
                        matches=document.get('path') == result['path'] and source_hash(Path(result['path'])) == result['sourceHash'])
            memos[workflow['id']] = memo
        result['available'] = ((job.get('error') or {}).get('code') != 'restoration_unverified'
                               and memo['matches'])
        result['message'] = ('Restore saved version replaces all current edits since the saved baseline, including later manual edits. The saved file is checked again before restoring.'
                             if result['available'] else 'The saved baseline changed or restoration is unverified. Inspect the saved version in Glyphs; no reload will be replayed.')
        service.edit_workflows._set(workflow, document=document)
    except Exception:
        service.edit_workflows.baseline_memos.pop(workflow['id'], None)
        result['message'] = 'The original document or saved baseline is unavailable; inspect it in Glyphs.'
    service.edit_workflows._set(workflow, savedVersion=result)


def restore(service, workflow, error):
    baseline = workflow.get('savedVersion') or {}
    if not baseline.get('available') or workflow.get('pendingAction') != 'restore_saved_script':
        raise error('confirmation_required', 'use the current whole-document restoration action')
    job = service._job(workflow['jobId'])
    invalidate(service, job['document']['id'])
    # Preserve the dispatch record before crossing the bridge; never replay on reconnect.
    request = dict(jobId=job['id'], generation=baseline['generation'], sourceHash=baseline['sourceHash'])
    service.jobs.update(job['id'], status='discarding', restoreRequest=request)
    try:
        operation = service.bridge.restore_saved_script(request)
    except Exception as exc:
        from .bridge_client import BridgeClientError
        certain = isinstance(exc, BridgeClientError) and exc.details.get('execution') != 'uncertain'
        service.jobs.update(job['id'], status=job['status'] if certain else 'discarding', error=service._error(exc).as_dict())
        raise
    changed = service.jobs.update(job['id'], status=operation['status'], bridgeOperation=operation, error=operation.get('error'))
    service.edit_workflows._set(workflow, job=service._public(changed), state=operation['status'], savedVersion=None)
    after = operation.get('scriptResult', {}).get('documentAfter')
    if after and operation['status'] == 'discarded':
        service.edit_workflows._rebind(workflow, after)


def reconcile_save(service, workflow, error):
    request = workflow.get('saveRequest')
    job = service._job(workflow['jobId'])
    if not request or job['status'] != 'ready':
        return False
    from . import saving
    operation = service.bridge.save_operation(request['saveId'])
    if operation.get('status') == 'saved':
        receipt = saving.verify_save(request, operation.get('native') or {})
        if request.get('checkpointJobId'):
            receipt = service.get_job(request['checkpointJobId'])['receipt']
        service.edit_workflows._set(workflow, state='outdated', receipt=receipt, error=None)
    else:
        service.edit_workflows._set(workflow, state='failed', error=operation.get('error') or
            dict(code='save_unverified', message='The prerequisite save is unverified; no script was run.'))
    return True
