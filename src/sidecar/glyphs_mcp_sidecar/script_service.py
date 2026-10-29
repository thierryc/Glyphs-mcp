"""Revision-bound dispatch for authorized native script jobs."""
from glyphs_mcp_protocol import scripts
from .bridge_client import BridgeClientError
from .saved_script import unresolved
from glyphs_mcp_protocol.task_conflicts import CAPABILITY, conflicts, protection, describe


def validate_capabilities(service, options, error):
    native = service.bridge.status()
    if (scripts.SNAPSHOT not in native.get('jobCapabilities', []) or scripts.NATIVE not in native.get('jobCapabilities', [])
            or native.get('scriptPreparationVersion') != scripts.PREPARATION_VERSION):
        raise error('unsupported_job', 'native scripts require a coordinated runtime update (script.native.v1, script.recovery.snapshot.v1, preparation version 3)')


def scoped_recovery(service, *, refresh=False):
    if refresh:
        try:
            native = service.bridge.status()
            service._task_scoped_recovery = CAPABILITY in native.get('jobCapabilities', [])
            service._task_bridge_session = native.get('bridgeSessionId')
        except Exception:
            service._task_scoped_recovery = False
    return getattr(service, '_task_scoped_recovery', False)


BLOCKING_STATUSES = {'preparing', 'cancelling', 'ready', 'applying', 'applied', 'accepting', 'accept_uncertain', 'discarding', 'interrupted'}


def execution_blockers(service, job_id=None, *, document_id=None, exclusive=True, refresh=False, records=None):
    candidates = records if records is not None else service.jobs.select(BLOCKING_STATUSES, include_unresolved=True)
    if scoped_recovery(service, refresh=refresh) and document_id is not None:
        return [job for job in candidates if job['id'] != job_id
                and conflicts(job, document_id, exclusive=exclusive)]
    legacy = BLOCKING_STATUSES - {'ready', 'interrupted'}
    return [job for job in candidates if job['id'] != job_id and (
        job['status'] in legacy or unresolved(job) or
        document_id is not None and conflicts(job, document_id, exclusive=exclusive))]


def run(service, job_id, workflow_id, error):
    workflow = service.edit_workflows.store.records.get(workflow_id)
    if not workflow or workflow.get('jobId') != job_id or workflow.get('pendingAction') != 'run_script':
        raise error('workflow_action_required', 'Run must be dispatched by its authorized Apply workflow or current preview Run action')
    job = service._job(job_id)
    if job.get('resultKind') != 'script' or job['status'] != 'ready':
        raise error('job_not_ready', 'script review is not ready')
    for other in execution_blockers(service, job_id, document_id=job['document']['id'], refresh=True):
        if other['id'] != job_id:
            owner = protection(other)
            raise error('document_busy', describe(owner) if owner else 'Resolve outstanding MCP mutations before native execution.',
                        details={'blockingJobId': other['id'], 'blocker': owner})
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
        # Only a confirmed preflight refusal can return to the queue. A lost
        # response keeps the native attempt protected and is never replayed.
        certain = isinstance(exc, BridgeClientError) and exc.details.get('execution') != 'uncertain'
        service.jobs.update(job_id, status=('ready' if exc.code == 'document_busy' else 'failed') if certain else 'applying', error=service._error(exc).as_dict())
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
            scoped = scoped_recovery(service, refresh=True)
            with service._lock:
                document_id, own_job = None, None
                if args:
                    if method.__name__ in {'run_script', 'finish_edit', 'apply_job', 'accept_job'}:
                        own_job = service._job(args[0])
                        document_id = (own_job.get('document') or {}).get('id')
                    else:
                        document_id = args[0]
                elif 'document_id' in kwargs:
                    document_id = kwargs['document_id']
                elif 'job_id' in kwargs:
                    own_job = service._job(kwargs['job_id'])
                    document_id = (own_job.get('document') or {}).get('id')
                # Publishing staged files has no live Glyphs dependency. Its
                # destination is protected by the atomic publication service.
                if own_job and own_job.get('resultKind') == 'artifact':
                    return method(service, *args, **kwargs)
                for job in service.jobs.select(BLOCKING_STATUSES, include_unresolved=True):
                    if own_job and job['id'] == own_job['id']:
                        continue
                    if job['request']['kind'] not in {'python_script', 'checkpoint_restore'}:
                        continue
                    if scoped:
                        owner = protection(job)
                        diagnostic = method.__name__ == 'start_job' and kwargs.get('kind') in {'feature_compile', 'font_export', 'path_diagnostics'}
                        blocked = conflicts(job, document_id) and not (
                            diagnostic and owner and owner['reason'] in {'recovery', 'preview'})
                    else:
                        blocked = (unresolved(job) or job['status'] in {'applying', 'discarding', 'accept_uncertain'}
                                   or job['status'] == 'interrupted' and (job.get('error') or {}).get('code') == 'bridge_operation_lost')
                        owner = protection(job)
                    if blocked:
                        raise ServiceError('document_busy', describe(owner) if scoped and owner else
                                           'reconcile native execution before another mutation',
                                           details={'blockingJobId': job['id'], 'blocker': owner})
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
