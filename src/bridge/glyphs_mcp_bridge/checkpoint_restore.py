"""Historical font replacement inside Glyphs; never writes the open font's file."""
from pathlib import Path
from glyphs_mcp_protocol.source_identity import source_hash


def load(core, request, error):
    from Foundation import NSURL
    from GlyphsApp import GSFont
    value = GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(request['historicalPath']), None)
    font = value[0] if isinstance(value, tuple) else value
    if font is None or source_hash(request['historicalPath']) != request['historicalHash']:
        raise error('checkpoint_load_failed', 'Glyphs could not load the verified historical font.')
    return font


def replace(core, request, font, error):
    document = core.adapter._font(request['documentId']).parent
    # Retain the original document URL. The loaded font came from private staging.
    url = document.fileURL()
    document.setFont_(font)
    document.setFileURL_(url)
    document.undoManager().removeAllActions()
    document.updateChangeCount_(0)  # NSChangeDone: historical content is unsaved.
    state = core.adapter._document_state(font)
    state['familyName'] = str(font.familyName or 'Untitled')
    if state.get('path') != request['sourcePath'] or state.get('dirty') is not True:
        raise error('checkpoint_restore_unverified', 'The restored document binding or dirty state was not confirmed.')
    return state


def restore(core, request, error):
    fields = {'jobId','documentId','generation','sourcePath','sourceHash','historicalPath','historicalHash'}
    if not isinstance(request, dict) or set(request) != fields or type(request.get('generation')) is not int:
        raise error('invalid_request', 'Invalid checkpoint restoration request.')
    for name in ('sourcePath','historicalPath'):
        path = Path(request[name])
        if not path.is_absolute() or path.suffix.lower() not in {'.glyphs','.glyphspackage'} or path.resolve()!=path:
            raise error('invalid_request', 'Restoration requires regular absolute font paths.')
    if core.paused:
        raise error('server_stopped', 'The Glyphs MCP server is stopped.')
    existing = core._operations.get(request['jobId'])
    if existing:
        if existing.get('checkpointRestore') != request:
            raise error('job_conflict', 'This restore identity belongs to another request.')
        return core._public(existing)
    core._check_owner(request['documentId'])
    if any(op['documentId']==request['documentId'] and op['status'] in {'applied','accepting','accept_uncertain'} for op in core._operations.values()):
        raise error('document_busy', 'Finish the current edit before restoring a historical font.')
    state = core.adapter.document_state(request['documentId'])
    if state.get('path') != request['sourcePath'] or state.get('generation') != request['generation']:
        raise error('stale_document', 'The intended document changed after restoration was prepared.')
    if source_hash(request['sourcePath']) != request['sourceHash'] or source_hash(request['historicalPath']) != request['historicalHash']:
        raise error('stale_source', 'The saved or historical font changed before restoration.')
    font = load(core, request, error)
    operation = dict(jobId=request['jobId'],documentId=request['documentId'],status='applying',
                     checkpointRestore=dict(request),patch={'changes':[]},index=0,resolved=[],applied=[],
                     error=None,nativeStateBytes=0,restorationClosed=True)
    core._operations[request['jobId']] = operation  # Record before touching the live document.
    try:
        after = replace(core, request, font, error)
        operation.update(status='applied',documentId=after['id'],documentAfter=after)
    except BaseException as exc:
        operation.update(status='failed',error={'code':'checkpoint_restore_unverified','message':str(exc)[:2000],
                         'details':{'writeAttempted':True,'execution':'uncertain'}})
    return core._public(operation)


def acknowledge(core, identity, error):
    operation = core._operations.get(identity)
    if (not operation or not operation.get('checkpointRestore')
            or operation['status'] not in {'failed','completed'}):
        raise error('job_not_ready', 'No stopped historical restore to acknowledge.')
    operation.update(status='completed', outcome='unverified')
    return core._public(operation)
