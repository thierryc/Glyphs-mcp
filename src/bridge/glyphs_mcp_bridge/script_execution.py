"""Exactly-once native scripts using the bridge's job registry."""
import copy
import time
import traceback
from glyphs_mcp_protocol import ProtocolError, scripts, script_targets
from glyphs_mcp_protocol.script_runtime import ScriptRuntime


def unresolved(operation):
    if operation.get('checkpointRestore') and operation['status'] == 'failed':
        return bool((operation.get('error') or {}).get('details', {}).get('writeAttempted'))
    return (bool(operation.get('scriptRequest')) and operation['status'] in {'failed', 'cancelled'}
            and operation.get('scriptResult', {}).get('executed', False))


def begin(core, request, error):
    if not isinstance(request, dict) or set(request) != {'jobId', 'documentId', 'sourcePath', 'sourceHash', 'generation', 'options', 'manifest'}:
        raise error('invalid_request', 'invalid script execution request')
    try:
        scripts.check_request(request)
        options = scripts.validate_options(request['options'])
    except ProtocolError as exc:
        raise error(exc.code, exc.message) from exc
    identity = scripts.text(request['jobId'], 'jobId', 100)
    old = core._operations.get(identity)
    if old is not None and not (old.get('scriptReviewRequest') and old['status'] == 'ready'):
        if old.get('scriptRequest') != request:
            raise error('job_conflict', 'script job ID belongs to another request')
        return core._public(old)
    if old is not None:
        reviewed = old['scriptReviewRequest']
        if (any(reviewed[k] != request[k] for k in ('documentId', 'sourcePath', 'options'))
                or old['preparedReport']['manifest'] != request['manifest']):
            raise error('job_conflict', 'script execution differs from the prepared request')
    core._check_owner(request['documentId'], ignore_job_id=identity)
    if any(unresolved(o) or o['status'] in {'applying', 'rolling_back', 'discarding', 'accepting', 'applied', 'accept_uncertain'} for o in core._operations.values()):
        raise error('document_busy', 'resolve existing MCP mutations before native execution')
    if any(o['status'] == 'saving' for o in core._saves.values()):
        raise error('document_busy', 'a document is being saved')
    finished = [key for key, item in core._operations.items() if item['status'] not in {'preparing', 'applying', 'rolling_back', 'discarding', 'accepting'}]
    for key in finished[:-7]:
        del core._operations[key]
    state = core.adapter.document_state(request['documentId'])
    if state.get('path') != request['sourcePath'] or state.get('generation') != request['generation']:
        raise error('stale_document', 'the document changed after script review')
    if state.get('dirty') is not False:
        raise error('document_not_clean', 'save the font before native execution')
    # Validate every reviewed target. A changed manifest is never re-resolved silently.
    rows = request['manifest']
    if not isinstance(rows, list):
        raise error('invalid_request', 'invalid script manifest')
    try:
        normalized = scripts.targets(rows)
    except ProtocolError as exc:
        raise error(exc.code, exc.message) from exc
    if len(normalized) != len(rows):
        raise error('invalid_request', 'duplicate script manifest targets')
    if rows != normalized:
        raise error('invalid_request', 'invalid manifest row')
    if options['entrypoint'] == 'per_target' and not rows:
        raise error('invalid_request', 'no eligible script targets')
    patch = dict(version=1, **{k: request[k] for k in ('jobId', 'documentId', 'sourcePath', 'sourceHash', 'generation')},
                 changes=[], summary=options.get('summary', 'Native Python script'))
    operation = dict(jobId=identity, documentId=request['documentId'], patch=patch, status='applying',
                     direction='forward', index=0, applied=[], resolved=[], cancelRequested=False,
                     error=None, rollbackReverse=True, nativeStateBytes=0, startedAt=time.time(), finishedAt=None,
                     scriptRequest=copy.deepcopy(request), scriptStage='resolve', scriptIndex=0,
                     longestPreparationChunk=(old or {}).get('longestPreparationChunk'),
                     scriptCandidates=script_targets.iterate(core.adapter._font(request['documentId']), options['targets']),
                     scriptTargets=[], scriptResult=dict(executed=False, output='', entrypoint=options['entrypoint'],
                                                       executionSucceeded=False, changesVerified=False,
                                                       executedTargets=0, totalTargets=len(rows)))
    core._operations[identity] = operation
    core._launch(operation)
    return core._public(operation)


def _invoke(operation, callback, row=None):
    if row is not None:
        managers = {id(row['manager']): row['manager']} if row.get('manager') is not None else {}
    else:
        managers = operation['scriptManagers']
    managers = dict(managers)
    document_manager = operation.get('scriptDocumentManager')
    if document_manager is not None:
        managers[id(document_manager)] = document_manager
    disabled = []
    try:
        for manager in managers.values():
            if not manager.isUndoRegistrationEnabled():
                raise ValueError('native Undo registration is disabled')
            manager.disableUndoRegistration(); disabled.append(manager)
        return callback()
    finally:
        for manager in reversed(disabled): manager.enableUndoRegistration()


def _verify_owner(core, op, row):
    # Deliberately bypass the operation cache: unrestricted code can delete,
    # replace or rename objects, or close the document during its invocation.
    target = row['target']
    font = core.adapter._font(op['documentId'])
    owner = script_targets.owner(font, target)
    if target['surface'] == 'background':
        if not script_targets.value(owner, 'hasBackground', False):
            raise ValueError('the declared background was removed')
        owner = owner.background
    if core.adapter._native_identity(owner) != core.adapter._native_identity(row['layer']):
        raise ValueError('the declared layer was replaced; execution cannot continue')


def advance(core, op):
    """One bounded wrapper step; a Python invocation cannot be safely preempted."""
    request = op['scriptRequest']; options = request['options']; stage = op['scriptStage']
    rows = op['scriptTargets']
    try:
        if op['cancelRequested'] and stage not in ('cleanup', 'done'):
            raise RuntimeError('script cancelled; remaining callbacks were not run')
        if stage == 'resolve':
            try:
                target, _, reason = next(op['scriptCandidates'])
            except StopIteration:
                if op['scriptIndex'] != len(request['manifest']):
                    raise ValueError('resolved script targets changed after preparation')
                op.pop('scriptCandidates', None)
                font = core.adapter._operation_font(op['documentId'])
                op.setdefault('scriptManagers', {})
                op['scriptDocumentManager'] = script_targets.value(font.parent, 'undoManager')
                op['scriptRuntime'] = ScriptRuntime(options, font=font, targets=[r['layer'] for r in rows], glyphs=core.adapter.glyphs)
                op['scriptStage'] = 'initialize'
                return
            if reason: return
            index = op['scriptIndex']
            if index >= len(request['manifest']) or target != request['manifest'][index]:
                raise ValueError('resolved script targets changed after preparation')
            layer, manager = core.adapter.script_target(op['documentId'], target)
            rows.append(dict(target=target, layer=layer, manager=manager))
            if manager is not None:
                op.setdefault('scriptManagers', {})[id(manager)] = manager
            op['scriptIndex'] += 1
        elif stage == 'initialize':
            from glyphs_mcp_protocol.source_identity import source_hash
            if source_hash(request['sourcePath']) != request['sourceHash']:
                raise ValueError('saved baseline changed before execution')
            state = core.adapter.document_state(op['documentId'])
            if state.get('dirty') is not False or state.get('generation') != request['generation'] or state.get('path') != request['sourcePath']:
                raise ValueError('document changed before script execution')
            # Mark before execution: a script that saves can legitimately leave
            # the document clean. Never dirty it again merely to claim changes.
            core.adapter._font(op['documentId']).parent.updateChangeCount_(0)
            op['scriptResult']['executed'] = True
            _invoke(op, op['scriptRuntime'].initialize)
            op['scriptStage'] = 'run' if options['entrypoint'] == 'per_target' else 'complete'
            op['scriptResult']['executionSucceeded'] = options['entrypoint'] == 'script'
            op['scriptIndex'] = 0
        elif stage == 'run':
            index = op['scriptIndex']
            if index == len(rows):
                op['scriptResult']['executionSucceeded'] = True
                op['scriptStage'] = 'complete'
                return
            row = rows[index]
            _verify_owner(core, op, row)
            _invoke(op, lambda: op['scriptRuntime'].run_target(row['layer'], row['target'], index, len(rows)), row=row)
            op['scriptIndex'] += 1
            op['scriptResult']['executedTargets'] += 1
        elif stage == 'complete':
            op['scriptResult']['documentAfter'] = core.adapter.document_state(op['documentId'])
            op['scriptResult']['output'] = op['scriptRuntime'].output
            op['scriptStage'] = 'cleanup'
        elif stage == 'cleanup':
            candidates = op.pop('scriptCandidates', None)
            if candidates is not None: candidates.close()
            if rows:
                from .script_adapter import release
                row = rows.pop()
                op.get('scriptManagers', {}).pop(id(row.get('manager')), None)
                release(core.adapter, op['documentId'], row['layer'])
                return
            op.pop('scriptRuntime', None); op.pop('scriptManagers', None); op.pop('scriptDocumentManager', None)
            op['scriptStage'] = 'done'
            core._finish(op, 'cancelled' if op['cancelRequested'] else 'failed' if op['error'] else 'applied')
            op.pop('scriptTargets', None)
    except BaseException as error:
        runtime = op.get('scriptRuntime')
        op['scriptResult']['output'] = runtime.output if runtime else ''
        details = dict(traceback=traceback.format_exc()[-scripts.MAX_OUTPUT_CHARS:],
                       partialEditsPossible=op['scriptResult']['executed'], externalEffects='unverified')
        if op.get('error'):
            op['error'].setdefault('details', {})['cleanup'] = str(error)[:2000]
        else:
            op['error'] = dict(code='script_cancelled' if op['cancelRequested'] else 'script_failed',
                               message=(str(error) or type(error).__name__)[:2000], details=details)
        op['scriptStage'] = 'cleanup'


def check_pre_execution(core, op):
    """Once per scheduled chunk; avoid an O(targets) native-state read per step."""
    if op['scriptStage'] != 'resolve': return
    request = op['scriptRequest']
    try:
        state = core.adapter.document_state(op['documentId'])
        if (state.get('dirty') is not False or state.get('generation') != request['generation']
                or state.get('path') != request['sourcePath']):
            raise ValueError('document changed before script execution')
    except Exception as exc:
        op['error'] = dict(code='stale_document', message=str(exc)[:2000], details={'partialEditsPossible':False})
        op['scriptStage'] = 'cleanup'
