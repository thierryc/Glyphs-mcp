"""Revision-bound dispatch for authorized native script jobs."""
from pathlib import Path
from glyphs_mcp_protocol import scripts
from .source import source_hash
from .bridge_client import BridgeClientError
from .saved_script import unresolved


def validate_capabilities(service, options, error):
    native = service.bridge.status()
    if scripts.NATIVE not in native.get('jobCapabilities', []):
        raise error('unsupported_job', 'native scripts require a coordinated runtime update (script.native.v1)')


def run(service, job_id, workflow_id, error):
    workflow = service.edit_workflows.store.records.get(workflow_id)
    if not workflow or workflow.get('jobId') != job_id or workflow.get('pendingAction') not in {'run_script', 'save_run_script'}:
        raise error('confirmation_required', 'use the current conversation Run action under task authorization')
    job = service._job(job_id)
    if job.get('resultKind') != 'script' or job['status'] != 'ready':
        raise error('job_not_ready', 'script review is not ready')
    for other in service.jobs.records():
        if other['id'] != job_id and (unresolved(other) or other['status'] in {'preparing', 'cancelling', 'applying', 'applied', 'accepting', 'accept_uncertain', 'discarding'}):
            raise error('document_busy', 'resolve outstanding MCP mutations before native execution')
    from .saved_script import save_before_run
    job = save_before_run(service, job, workflow, error)
    doc = service._document(job['document']['id'])
    if doc.get('dirty') is not False:
        raise error('document_not_clean', 'save or discard current edits before running')
    if doc.get('path') != job['document'].get('path') or doc.get('generation') != job['document'].get('generation'):
        raise error('stale_document', 'the document changed after script review')
    if source_hash(Path(doc['path'])) != job['sourceHash']:
        raise error('stale_source', 'the saved source changed after script review')
    report = service.jobs.read_json(job_id, 'report.json')
    options = scripts.validate_options(job['request']['options'])
    if scripts.digest(options) != report['requestHash'] or options != report['review']:
        raise error('stale_script', 'the reviewed source or parameters changed')
    request = dict(jobId=job_id, documentId=doc['id'], sourcePath=doc['path'], sourceHash=job['sourceHash'],
                   generation=doc['generation'], options=options, manifest=report['manifest'])
    service.jobs.update(job_id, status='applying')
    try:
        operation = service.bridge.run_script(request)
    except Exception as exc:
        # Never dispatch automatically again, even after a known preflight failure.
        certain = isinstance(exc, BridgeClientError) and exc.details.get('execution') != 'uncertain'
        service.jobs.update(job_id, status='failed' if certain else 'applying', error=service._error(exc).as_dict())
        raise service._error(exc) from exc
    return service._public(service.jobs.update(job_id, status='applying', bridgeOperation=operation))


def finish(service, job_id, error):
    job = service._job(job_id)
    if job.get('resultKind') != 'script' or job['status'] not in {'applied', 'failed', 'cancelled', 'completed'}:
        raise error('job_not_ready', 'script is not ready to finish')
    operation = service.bridge.finish_script(job_id)
    return service._public(service.jobs.update(job_id, status='completed', bridgeOperation=operation))


def acknowledge_lost(service, workflow, error):
    """Release a confirmed lost operation without claiming success or recovery."""
    job = service._job(workflow['jobId'])
    if (workflow.get('pendingAction') != 'acknowledge_script_outcome' or job.get('resultKind') != 'script'
            or job['status'] != 'interrupted' or (job.get('error') or {}).get('code') != 'bridge_operation_lost'):
        raise error('job_not_ready', 'only a confirmed missing script operation can be acknowledged')
    try:
        service.bridge.operation(job['id'])
    except BridgeClientError as exc:
        if exc.code != 'job_not_found':
            raise
    else:
        raise error('job_not_ready', 'the native operation is available; reconcile it before continuing')
    return service._public(service.jobs.update(job['id'], status='completed', outcome='unverified'))


def mutation_guard(method):
    """Serialize dispatch checks so a new job cannot race a live script."""
    from functools import wraps
    @wraps(method)
    def guarded(service, *args, **kwargs):
        from .service import ServiceError
        with service._script_dispatch_lock:
            with service._lock:
                if any(j['request']['kind'] == 'python_script'
                       and (unresolved(j) or j['status'] in {'applying', 'discarding', 'accept_uncertain'}
                            or j['status'] == 'interrupted' and (j.get('error') or {}).get('code') == 'bridge_operation_lost')
                       for j in service.jobs.records()):
                    raise ServiceError('document_busy', 'reconcile native execution before another mutation')
            return method(service, *args, **kwargs)
    return guarded


def invalidate_retired_review(jobs, job):
    if (job['request']['kind'] == 'python_script' and scripts.retired(job['request'].get('options', {}))
            and job['status'] in {'ready', 'preparing', 'cancelling'}):
        jobs.update(job['id'], status='failed', error={
            'code': 'retired_script_review',
            'message': 'This script review belongs to the retired interface. Prepare a new request; no code was run.',
        })
        return True
    return False
