"""Atomic release of an unapplied preview; never Cancel execution or Undo."""


def release(core, request, error):
    if (not isinstance(request, dict) or set(request) != {'jobId', 'documentId', 'bridgeSessionId'}
            or any(not isinstance(value, str) or not value for value in request.values())):
        raise error('invalid_request', 'An exact preview, document and bridge session are required.')
    with core._lock:
        if request['bridgeSessionId'] != core.bridge_session_id:
            raise error('stale_bridge_session', 'The preview belongs to another Glyphs session.')
        operation = core._operations.get(request['jobId'])
        if operation is None:
            raise error('job_not_found', 'The bridge does not retain this preview.')
        if operation['documentId'] != request['documentId']:
            raise error('target_conflict', 'The preview belongs to another font.')
        evidence = operation.get('scriptResult') or {}
        details = (operation.get('error') or {}).get('details') or {}
        if (operation['status'] not in {'ready', 'cancelled', 'discarded'}
                or not operation.get('prepared') or operation.get('scriptRequest')
                or operation.get('checkpointRestore') or operation.get('scriptSnapshot') is not None
                or operation.get('applied') or operation.get('resolved') or evidence.get('executed')
                or (evidence.get('recovery') or {}).get('available')
                or details.get('execution') == 'uncertain' or details.get('writeAttempted') or details.get('partialEditsPossible')
                or operation.get('restoreRequest') or operation.get('saveRequest')):
            raise error('preview_release_refused', 'Execution or recovery must be reconciled; the preview was not released.',
                        details={'jobId': request['jobId'], 'status': operation['status']})
        if operation['status'] == 'ready':
            from .typed_preparation import cancel
            cancel(operation)
        return core._public(operation)
