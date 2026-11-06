"""Reconcile cancelled native script previews without ending edit recovery."""
from .bridge_client import BridgeClientError


def pending(job):
    return (job.get('request', {}).get('kind') == 'python_script'
            and job.get('phase') == 'preparing_native'
            and job.get('status') in {'discarded', 'cancelled'}
            and not job.get('nativePreviewReleased'))


def release(service, job, error):
    """A local terminal status is not proof that the bridge released its owner."""
    if job.get('nativePreviewReleased'):
        return
    try:
        try:
            operation = service.bridge.operation(job['id'])
        except BridgeClientError as exc:
            if exc.code != 'job_not_found':
                raise
            operation = None
        if operation is not None:
            if (operation.get('jobId') != job['id'] or
                    operation.get('documentId') != job['document']['id']):
                raise error('preview_release_unverified', 'The native preview identity could not be verified.')
            _check(operation, error)
            if operation['status'] in {'preparing', 'ready'}:
                operation = service.bridge.discard(job['id'])
                if (operation.get('jobId') != job['id'] or
                        operation.get('documentId') != job['document']['id']):
                    raise error('preview_release_unverified', 'Native cancellation returned another preview identity.')
                _check(operation, error)
                if operation['status'] not in {'cancelled', 'discarded'}:
                    raise error('preview_release_unverified', 'Native preview cancellation is not yet confirmed.')
        service.jobs.update(job['id'], nativePreviewReleased=True)
    except BridgeClientError as exc:
        raise error(exc.code, exc.message, details=exc.details) from exc


def _check(operation, error):
    if ((operation.get('scriptResult') or {}).get('executed') or operation.get('recoveryAvailable')
            or operation.get('status') not in {'preparing', 'ready', 'cancelled', 'discarded', 'failed', 'completed'}):
        raise error('preview_release_unverified',
                    'Native work may have executed. Reconcile its existing result before releasing recovery.',
                    details={'jobId': operation.get('jobId'), 'execution': 'uncertain'})
