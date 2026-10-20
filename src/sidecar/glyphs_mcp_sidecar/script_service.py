"""Revision-bound dispatch for authorized native script jobs."""
from glyphs_mcp_protocol import scripts
from .bridge_client import BridgeClientError
from .saved_script import unresolved


def validate_capabilities(service, options, error):
    native = service.bridge.status()
    if (scripts.SNAPSHOT not in native.get('jobCapabilities', []) or scripts.NATIVE not in native.get('jobCapabilities', [])
            or native.get('scriptPreparationVersion') != scripts.PREPARATION_VERSION):
        raise error('unsupported_job', 'native scripts require a coordinated runtime update (script.native.v1, script.recovery.snapshot.v1, preparation version 3)')


def execution_blockers(service, job_id=None):
    return [job for job in service.jobs.select(
        {'preparing', 'cancelling', 'applying', 'applied', 'accepting', 'accept_uncertain', 'discarding'},
        include_unresolved=True) if job['id'] != job_id]


def run(service, job_id, workflow_id, error):
    workflow = service.edit_workflows.store.records.get(workflow_id)
    if not workflow or workflow.get('jobId') != job_id or workflow.get('pendingAction') != 'run_script':
        raise error('workflow_action_required', 'Run must be dispatched by its authorized Apply workflow or current preview Run action')
    job = service._job(job_id)
    if job.get('resultKind') != 'script' or job['status'] != 'ready':
        raise error('job_not_ready', 'script review is not ready')
    for other in execution_blockers(service, job_id):
        if other['id'] != job_id:
            raise error('document_busy', 'resolve outstanding MCP mutations before native execution', details={'blockingJobId': other['id']})
    validate_capabilities(service, job['request']['options'], error)
    doc = service._document(job['document']['id'])
    if any(doc.get(key) != job['document'].get(key) for key in ('path', 'generation', 'dirty')):
        raise error('stale_document', 'the document changed after script review')
    report = service.jobs.read_json(job_id, 'report.json')
    options = job['request']['options']
    if scripts.digest(options) != report['requestHash'] or options != report['review']:
        raise error('stale_script', 'the reviewed source or parameters changed')
    scripts.validate_options(options)
    from .saved_script import execution_request
    request = execution_request(job, report, error)
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
                if any(j['request']['kind'] in {'python_script','checkpoint_restore'}
                       and (unresolved(j) or j['status'] in {'applying', 'discarding', 'accept_uncertain'}
                            or j['status'] == 'interrupted' and (j.get('error') or {}).get('code') == 'bridge_operation_lost')
                       for j in service.jobs.select({'applying', 'discarding', 'accept_uncertain', 'interrupted'}, include_unresolved=True)):
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
