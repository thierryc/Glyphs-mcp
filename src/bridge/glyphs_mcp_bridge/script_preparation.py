"""Read-only script manifests, scheduled in the existing operation registry."""
import copy
import time
from glyphs_mcp_protocol import ProtocolError, scripts, script_targets


def check(core, op, error):
    request = op['scriptReviewRequest']
    state = core.adapter.document_state(op['documentId'])
    if (state.get('path') != request['sourcePath'] or state.get('generation') != request['generation']
            or state.get('dirty') != op['reviewDirty']):
        raise error('stale_document', 'document changed during script preparation')


def report_iterator(core, request, error):
    options = request['options']
    budget = scripts.ManifestBudget(request)
    manifest, skipped = [], dict(count=0, sample=[])
    for target, _, reason in script_targets.iterate(core.adapter._font(request['documentId']), options['targets']):
        if reason:
            skipped['count'] += 1
            if len(skipped['sample']) < 10:
                skipped['sample'].append(dict(target, status='skipped', reason=reason))
        else:
            budget.add(target)
            manifest.append(target)
        yield
    if options['entrypoint'] == 'per_target' and not manifest:
        raise error('invalid_request', 'no eligible script targets; missing or empty backgrounds were skipped',
                    details={'skippedCount': skipped['count'], 'sample': skipped['sample']})
    report = dict(kind='python_script', claim='Restore saved version reloads the whole font.',
        targetCount=len(manifest), skippedCount=skipped['count'], targets=skipped['sample'],
        manifest=manifest, review=options, requestHash=scripts.digest(options), requestBytes=budget.size)
    scripts.check_request(dict(request, manifest=manifest))
    scripts.check_size(len(scripts.wire_bytes(dict(ok=True, data=report))))
    return report


def begin(core, request, error):
    fields = {'jobId', 'documentId', 'generation', 'sourcePath', 'sourceHash', 'options'}
    if core.paused:
        raise error('server_stopped', 'the Glyphs MCP server is stopped')
    if not isinstance(request, dict) or set(request) != fields:
        raise error('invalid_request', 'native script preparation requires coordinated runtime version 2')
    try:
        options = scripts.validate_options(request['options'])
        scripts.check_request(request)
        identity = scripts.text(request['jobId'], 'jobId', 100)
    except ProtocolError as exc:
        raise error(exc.code, exc.message) from exc
    request = dict(request, options=options)
    with core._lock:
        old = core._operations.get(identity)
        if old is not None:
            if old.get('scriptReviewRequest') != request:
                raise error('job_conflict', 'script preparation ID belongs to another request')
            return core._public(old)
        core._check_owner(request['documentId'])
        state = core.adapter.document_state(request['documentId'])
        op = dict(jobId=identity, documentId=request['documentId'], status='preparing', prepared=True,
            scriptReviewRequest=copy.deepcopy(request), reviewDirty=state.get('dirty'),
            patch=dict(changes=[]), index=0, applied=[], resolved=[], nativeStateBytes=0,
            error=None, longestPreparationChunk=0, startedAt=time.time(), finishedAt=None)
        check(core, op, error)
        op['prepareIterator'] = report_iterator(core, request, error)
        from .script_execution import unresolved
        finished = [key for key, item in core._operations.items()
                    if item['status'] not in {'preparing', 'applying', 'accepting', 'discarding', 'rolling_back', 'applied', 'accept_uncertain'}
                    and not unresolved(item)]
        for key in finished[:-7]: del core._operations[key]
        core._operations[identity] = op
    schedule(core, op, error)
    return core._public(op)


def fail(core, op, exc, error):
    from .typed_preparation import fail as finish_failure
    if isinstance(exc, ProtocolError): exc = error(exc.code, exc.message)
    finish_failure(core, op, exc)


def schedule(core, op, error):
    try: core.schedule(lambda: advance(core, op, error))
    except Exception as exc: fail(core, op, exc, error)


def advance(core, op, error):
    if op['status'] != 'preparing': return
    started = time.perf_counter()
    try:
        check(core, op, error)
        for _ in range(core.chunk_limit):
            try: next(op['prepareIterator'])
            except StopIteration as done:
                check(core, op, error)
                op.update(status='ready', preparedReport=done.value, finishedAt=time.time())
                op.pop('prepareIterator', None)
                break
            op['index'] += 1
            if time.perf_counter()-started >= core.chunk_seconds: break
    except Exception as exc: fail(core, op, exc, error)
    finally:
        op['longestPreparationChunk'] = max(op['longestPreparationChunk'], time.perf_counter()-started)
    if op['status'] == 'preparing': schedule(core, op, error)


def result(core, identity, error):
    op = core._operations.get(identity)
    if not op or not op.get('scriptReviewRequest') or op['status'] != 'ready':
        raise error('job_not_ready', 'script preparation is not ready')
    check(core, op, error)
    return copy.deepcopy(op['preparedReport'])
