"""Opt-in checkpoints attached to existing job and verified-save identities."""
from pathlib import Path
from .checkpoint_git import Repository, CheckpointError
from .checkpoint_policy import policy_for


def _repository(service, job, phase, font):
    def persist(value):
        service.jobs.update(job['id'], **{phase: value})
    return Repository(font, service.jobs.path(job['id'])/phase, persist)


def establish_baseline(service, job, scope):
    policy = policy_for(job['document']['path'])
    if policy is None:
        return
    repository = _repository(service, job, 'checkpointBaseline', job['document']['path'])
    value = repository.checkpoint(job['sourceHash'], job['id']+'_baseline', {
        'schemaVersion': 1, 'intendedChange': 'Saved baseline before '+str(job.get('summary') or job['request']['kind']),
        'actions': [], 'manualChanges': 'possible', 'verification': {'savedSourceHash': job['sourceHash']},
    }, transaction=job.get('checkpointBaseline'))
    service.jobs.write_json(job['id'], 'action-scope.json', scope)
    service.jobs.update(job['id'], checkpointBaseline=value, checkpointPolicy=policy, actionAttempted=True)


def pending_actions(service, path):
    # Only on an explicit Save. Ordinary polling never scans history or hashes Git.
    return sorted((job for job in service.jobs.records()
                   if job.get('actionAttempted') and not job.get('checkpointRecorded')
                   and job['document'].get('path') == path), key=lambda job: job['createdAt'])


def _evidence(service, repository, actions):
    values, scopes = [], {}
    workflows = getattr(getattr(service, '_edit_workflows', None), 'store', None)
    for job in actions:
        name = job['id']+'_scope.json'
        try:
            scope = service.jobs.read_json(job['id'], 'action-scope.json')
        except (FileNotFoundError, ValueError):
            scope = None
        if scope is not None:
            scopes[name] = scope
        operation = job.get('bridgeOperation') or {}
        execution = operation.get('scriptResult') or {}
        values.append({
            'jobId': job['id'], 'workflowIds': sorted(value['id'] for value in (workflows.records.values() if workflows else []) if value.get('jobId') == job['id']),
            'baselineRevision': (job.get('checkpointBaseline') or {}).get('revision'),
            'request': job['request'], 'intendedChange': job.get('summary') or job['request']['kind'],
            'scope': {'count': len(scope) if isinstance(scope, list) else None,
                      'reference': repository.actions+'/'+name if scope is not None else None},
            'execution': {key: execution[key] for key in ('executed','executionSucceeded','executedTargets','totalTargets','cancelled','savedVersionRestored') if key in execution} if job.get('resultKind') == 'script' else {'operationStatus': operation.get('status'), 'jobStatus': job['status']},
            'verification': {'intendedResult': 'not independently verified',
                             'guardedApplication': operation.get('status') in {'applied','completed','accepting','accept_uncertain','accepted'} if job.get('resultKind') != 'script' else None},
            'outcome': job.get('outcome'), 'error': ({'code': job['error'].get('code'), 'message': str(job['error'].get('message', ''))[:2000]} if job.get('error') else None),
        })
    return values, scopes


def after_save(service, job, receipt):
    with service._checkpoint_lock:
        return _after_save(service, service.jobs.get(job['id']), receipt)


def _after_save(service, job, receipt):
    """Never call the editor here. Failed checkpoints retain their verified receipt."""
    previous = job.get('checkpointResult') or {}
    if previous.get('status') in {'created', 'reused'}:
        return {**receipt, 'checkpoint': previous}
    try:
        # The opted-in policy is captured before Save so disabling it mid-save
        # does not silently drop the promised checkpoint.
        policy = job.get('checkpointPolicy') or policy_for(receipt['path'])
        if policy is None:
            return receipt
        repository = _repository(service, job, 'checkpointTransaction', receipt['path'])
        frozen = job.get('checkpointEvidence')
        if frozen is None:
            actions = pending_actions(service, receipt.get('previousPath') or receipt['path'])
            values, scopes = _evidence(service, repository, actions)
            frozen = {'record': {
                'schemaVersion': 1, 'intendedChange': ('; '.join(str(v['intendedChange']) for v in values)[:500] or 'Save font'),
                'actions': values, 'manualChanges': 'possible',
                'save': {key: value for key,value in receipt.items() if key != 'checkpoint'},
                'verification': {'save': receipt['verification'], 'sourceHashAfter': receipt['sourceHashAfter'], 'intendedResult': 'see individual actions'},
            }, 'scopes': scopes, 'jobIds': [item['id'] for item in actions]}
            service.jobs.update(job['id'], checkpointPolicy=policy, checkpointEvidence=frozen, receipt=receipt)
        checkpoint = repository.checkpoint(receipt['sourceHashAfter'], receipt['saveId'], frozen['record'],
                                           transaction=job.get('checkpointTransaction'), scopes=frozen['scopes'])
        for identity in frozen['jobIds']:
            service.jobs.update(identity, checkpointRecorded=checkpoint['revision'])
    except Exception as exc:
        checkpoint = {'status': 'failed', 'message': 'Font saved; checkpoint failed.',
                      'error': {'code': getattr(exc, 'code', 'checkpoint_git_failed'), 'message': str(exc)[:2000]},
                      'retryJobId': job['id']}
    result = {**receipt, 'checkpoint': checkpoint}
    service.jobs.update(job['id'], checkpointResult=checkpoint, receipt=result)
    service.jobs.write_json(job['id'], 'receipt.json', result)
    return result


def retry(service, job_id):
    job = service._job(job_id)
    receipt = job.get('receipt')
    if (not receipt or receipt.get('verification') != 'native_and_source_hash'
            or not receipt.get('nativeSaveSucceeded') or not job.get('checkpointPolicy')):
        raise CheckpointError('checkpoint_not_retryable', 'A verified saved result with checkpoint policy is required.')
    return after_save(service, job, receipt)


def begin_save(service, document, request):
    policy = policy_for(request['path'])
    if not policy:
        return None
    job = service.jobs.create(document, {'kind': 'checkpoint_save', 'options': {}})
    return service.jobs.update(job['id'], status='accepting', resultKind='checkpoint',
                               saveRequest=request, checkpointPolicy=policy, summary='Save font and create checkpoint')


def reconcile_save(service, job):
    if job.get('receipt'):
        return service._public(job)
    from .saving import verify_save
    operation = service.bridge.save_operation(job['saveRequest']['saveId'])
    if operation.get('status') == 'saved':
        receipt = verify_save(job['saveRequest'], operation.get('native') or {})
        receipt = after_save(service, job, receipt)
        job = service.jobs.update(job['id'], status='accepted', receipt=receipt, error=None)
    return service._public(job)


def establish_typed_baseline(service, job, patch):
    try:
        establish_baseline(service, job, [{k:v for k,v in change.items() if k in {'glyph','layer','surface','master','field'}} for change in patch['changes']])
    except Exception as exc:
        raise service._error(exc) from exc
