"""Time-sliced, read-only typed preparation in the existing operation registry."""
import copy
import json
import time
from glyphs_mcp_protocol import validate_patch
from glyphs_mcp_protocol.preparation import simple

MAX_RESULT_BYTES = 4 * 1024 * 1024  # Existing bridge request ceiling, also for the eventual patch.


def _check(core, operation, error):
    state = core.adapter.document_state(operation['documentId'])
    request = operation['prepareRequest']
    if state.get('path') != request['sourcePath'] or state.get('generation') != request['generation']:
        raise error('stale_document', 'the intended document changed during preparation')
    if state.get('dirty') is not False:
        raise error('document_not_clean', 'save the font before preparing typed changes')
    return state


def begin(core, value, error):
    fields = {'jobId', 'documentId', 'sourcePath', 'sourceHash', 'generation', 'request'}
    if core.paused:
        raise error('server_stopped', 'the Glyphs MCP server is stopped')
    if not isinstance(value, dict) or set(value) != fields:
        raise error('invalid_request', 'native preparation fields are incomplete or unexpected')
    request = simple.validate_request(value['request'])
    patch = validate_patch(dict(version=1, **{k: value[k] for k in fields - {'request'}}, changes=[], summary='Preparing typed changes'))
    job_id = patch['jobId']
    with core._lock:
        old = core._operations.get(job_id)
        if old:
            if old.get('prepareRequest') != value:
                raise error('job_conflict', 'this job ID already belongs to another operation')
            return core._public(old)
        core._check_owner(patch['documentId'])
        operation = dict(jobId=job_id, documentId=patch['documentId'], patch=patch, status='preparing',
            index=0, applied=[], resolved=[], error=None, nativeStateBytes=0, startedAt=time.time(),
            prepareRequest=copy.deepcopy(value), prepared=True, longestPreparationChunk=0)
        _check(core, operation, error)
        operation['prepareIterator'] = simple.iterator(core.adapter._font(patch['documentId']), request)
        # Same bounded retry window as apply; no separate durable preparation registry.
        finished = [key for key, op in core._operations.items() if op['status'] not in {'preparing','applying','accepting','discarding','rolling_back'}]
        for key in finished[:-7]:
            del core._operations[key]
        core._operations[job_id] = operation
    _schedule(core, operation, error)
    return core._public(operation)


def _schedule(core, operation, error):
    try:
        core.schedule(lambda: advance(core, operation, error))
    except Exception as exc:
        fail(core, operation, exc)


def fail(core, operation, exc):
    operation.update(status='failed', error=core._error(exc).as_dict(), finishedAt=time.time())
    iterator = operation.pop('prepareIterator', None)
    if iterator is not None: iterator.close()
    operation.pop('preparedReport', None)


def advance(core, operation, error):
    if operation['status'] != 'preparing': return
    started = time.perf_counter()
    try:
        _check(core, operation, error)
        for _ in range(core.chunk_limit):
            try:
                next(operation['prepareIterator'])
            except StopIteration as done:
                changes, report = done.value
                request = operation['prepareRequest']
                patch = simple.patch(operation['jobId'], dict(id=operation['documentId'], path=request['sourcePath'],
                    generation=request['generation']), request['sourceHash'], request['request'], changes, report)
                if len(json.dumps(dict(patch=patch, report=report), ensure_ascii=False).encode()) > MAX_RESULT_BYTES:
                    raise error('request_too_large', 'prepared contents exceed the existing 4 MiB bridge limit')
                _check(core, operation, error)
                operation.update(status='ready', patch=patch, preparedReport=report, finishedAt=time.time())
                operation.pop('prepareIterator', None)
                break
            operation['index'] += 1
            if time.perf_counter() - started >= core.chunk_seconds: break
    except Exception as exc:
        fail(core, operation, exc)
    finally:
        operation['longestPreparationChunk'] = max(operation['longestPreparationChunk'], time.perf_counter()-started)
    if operation['status'] == 'preparing': _schedule(core, operation, error)


def result(core, job_id, error):
    op = core._operations.get(job_id)
    if not op or not op.get('prepared') or op['status'] != 'ready':
        raise error('job_not_ready', 'typed preparation is not ready')
    _check(core, op, error)
    return dict(patch=copy.deepcopy(op['patch']), report=copy.deepcopy(op.get('preparedReport')),
                longestChunkSeconds=op['longestPreparationChunk'])


def cancel(operation):
    operation.update(status='cancelled', finishedAt=time.time())
    iterator = operation.pop('prepareIterator', None)
    if iterator is not None: iterator.close()
    operation.pop('preparedReport', None)
    operation['patch']['changes'] = []
