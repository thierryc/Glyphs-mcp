"""Live script review and explicit whole-document saved-file restoration."""
from functools import lru_cache
from glyphs_mcp_protocol import scripts, script_targets
from glyphs_mcp_protocol.source_identity import source_hash


@lru_cache(maxsize=1)
def available():
    try:
        from GlyphsApp import GSFont, GSDocument
        return callable(GSFont.initWithURL_error_) and callable(GSDocument.setFont_)
    except Exception:
        return False


def review(core, request, error):
    if not isinstance(request, dict) or set(request) != {'documentId', 'generation', 'sourcePath', 'options'}:
        raise error('invalid_request', 'invalid native script review')
    options = scripts.validate_options(request['options'])
    state = core.adapter.document_state(request['documentId'])
    if state['generation'] != request['generation'] or state.get('path') != request['sourcePath']:
        raise error('stale_document', 'document changed while preparing script review')
    selected, skipped = script_targets.resolve(core.adapter._font(request['documentId']), options['targets'])
    if options['entrypoint'] == 'per_target' and not selected:
        raise error('invalid_request', 'no eligible script targets; missing or empty backgrounds were skipped',
                    details={'skippedCount': skipped['count'], 'sample': skipped['sample']})
    return dict(kind='python_script', claim='Restore saved version reloads the whole font.',
                targetCount=len(selected), skippedCount=skipped['count'],
                targets=skipped['sample'], manifest=[t for t, _ in selected],
                review=options, requestHash=scripts.digest(options))


def restore(core, request, error):
    if not isinstance(request, dict) or set(request) != {'jobId', 'generation', 'sourceHash'}:
        raise error('invalid_request', 'invalid saved-version restoration')
    op = core._operations.get(request['jobId'])
    if not op or not op.get('scriptRequest'):
        raise error('job_not_found', 'saved script operation is unavailable')
    if op.get('restorationClosed') or op['status'] in {'accepted', 'completed'}:
        raise error('job_not_ready', 'this workflow restoration offer has ended')
    if op.get('restoreRequest'):
        if op['restoreRequest'] != request:
            raise error('action_conflict', 'this restoration already has another request')
        return core._public(op)  # Never repeat a potentially attempted reload.
    if op['status'] not in {'applied', 'failed', 'cancelled'} or not op['scriptResult']['executed']:
        raise error('job_not_ready', 'script must have stopped before restoring')
    if any(o is not op and o['status'] in {'applying', 'applied', 'discarding', 'rolling_back', 'accepting', 'accept_uncertain'} for o in core._operations.values()):
        raise error('document_busy', 'resolve outstanding MCP changes before restoring a whole document')
    core._check_owner(op['documentId'], ignore_job_id=op['jobId'])
    state = core.adapter.document_state(op['documentId'])
    path = op['scriptRequest']['sourcePath']
    if state.get('path') != path or state['generation'] != request['generation']:
        raise error('stale_document', 'document changed after restoration review')
    if request['sourceHash'] != op['scriptRequest']['sourceHash'] or source_hash(path) != request['sourceHash']:
        raise error('saved_version_changed', 'The saved file has changed. Use an earlier version in Glyphs; the original baseline cannot be restored from this file.')
    from Foundation import NSURL
    from GlyphsApp import GSFont
    # Parse with Glyphs before touching the live document. No file is overwritten.
    loaded = GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(path), None)
    restored = loaded[0] if isinstance(loaded, tuple) else loaded
    if restored is None or source_hash(path) != request['sourceHash']:
        raise error('saved_version_unavailable', 'Glyphs could not load the unchanged saved version')
    font = core.adapter._font(op['documentId'])
    document = font.parent
    op['restoreRequest'] = dict(request)
    try:
        document.setFont_(restored)
        document.undoManager().removeAllActions()
        document.updateChangeCount_(2)  # NSChangeCleared; native reload, no save.
        after = core.adapter._document_state(restored)
        after['familyName'] = str(restored.familyName or 'Untitled')
        if after['dirty'] is not False or after['path'] != path:
            raise ValueError('native restored document did not retain its saved path and clean state')
        op['scriptResult']['savedVersionRestored'] = True
        op['scriptResult']['documentAfter'] = after
        op.update(status='discarded', error=None)
    except BaseException as exc:
        op.update(status='failed', error=dict(code='restoration_unverified', message=str(exc)[:2000],
                  details=dict(writeAttempted=True, restoration='unverified')))
    return core._public(op)
