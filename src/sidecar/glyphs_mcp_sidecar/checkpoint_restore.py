"""Prepare and dispatch historical restores using existing job/workflow identities."""
from pathlib import Path
from .checkpoint_git import Repository, CheckpointError
from .checkpoint_history import materialize
from .source import source_hash

CAPABILITY = 'font.checkpoint-restore.v1'


def validate(service, kind, delta, glyphs, options, error):
    if delta is not None or glyphs is not None or not isinstance(options,dict) or set(options)!={'revision'}:
        raise error('invalid_request', 'checkpoint_restore takes only options={revision: exact full revision}.')
    Repository.validate_revision(options['revision'])
    if CAPABILITY not in service.bridge.status().get('writeCapabilities',[]):
        raise error('unsupported_job', 'Historical restore requires a coordinated runtime update.')
    return dict(kind=kind,options=dict(options))


def prepare(service, document, request):
    if not document.get('path'):
        raise CheckpointError('document_path_required', 'Historical restore requires an existing saved path.')
    job=service.jobs.create(document,request)
    try:
        root=service.jobs.path(job['id'])
        repository=Repository(document['path'],root,lambda _:None)
        before=source_hash(document['path'])
        historical=materialize(repository,request['options']['revision'],root/'historical')
        job=service.jobs.update(job['id'],status='ready',sourceHash=before,resultKind='historical_restore',
            summary='Restore this font to '+request['options']['revision'][:12],changeCount=1,
            historicalPath=str(historical),historicalHash=source_hash(historical))
    except Exception as exc:
        service.jobs.update(job['id'],status='failed',error=service._error(exc).as_dict())
        raise
    return service._public(job)


def apply(service, job, error):
    if job['status'] in {'applying','applied','failed'}:
        return service.get_job(job['id'])
    if job['status']!='ready':raise error('job_not_ready','The historical restore is not ready.')
    document=service._document(job['document']['id'])
    if document.get('path')!=job['document']['path'] or document['generation']!=job['document']['generation']:
        raise error('stale_document','The intended font changed after restoration was prepared.')
    from .checkpoints import establish_baseline
    establish_baseline(service,job,[{'font':document['path'],'coverage':'whole font'}])
    request=dict(jobId=job['id'],documentId=document['id'],generation=document['generation'],
                 sourcePath=document['path'],sourceHash=job['sourceHash'],
                 historicalPath=job['historicalPath'],historicalHash=job['historicalHash'])
    service.jobs.update(job['id'],status='applying',restoreRequest=request)
    try:operation=service.bridge.restore_checkpoint(request)
    except Exception as exc:
        certain = getattr(exc,'details',{}).get('execution') != 'uncertain'
        service.jobs.update(job['id'],status='failed' if certain else 'applying',restoreRequest=None if certain else request,error=service._error(exc).as_dict())
        raise
    job=service.jobs.update(job['id'],status=operation['status'],bridgeOperation=operation,
                           document=operation.get('documentAfter') or document,error=operation.get('error'))
    return service._public(job)


def acknowledge(service, workflow, error):
    from .bridge_client import BridgeClientError
    job = service._job(workflow['jobId'])
    if (workflow.get('pendingAction') != 'acknowledge_restore_outcome'
            or job.get('resultKind') != 'historical_restore' or job['status'] not in {'failed','interrupted'}):
        raise error('job_not_ready', 'Only a stopped uncertain historical restore can be acknowledged.')
    try:
        operation = service.bridge.acknowledge_checkpoint_restore(job['id'])
    except BridgeClientError as exc:
        if exc.code != 'job_not_found': raise
        operation = job.get('bridgeOperation')
    return service._public(service.jobs.update(job['id'],status='completed',outcome='unverified',bridgeOperation=operation))
