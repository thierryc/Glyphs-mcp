"""Session-local full-font copies: no Save, serialization or original-file writes."""
import uuid
from glyphs_mcp_protocol.source_identity import source_hash, SourceError


def available():
    try:
        from GlyphsApp import GSFont, GSDocument
        return callable(GSFont.copy) and callable(GSDocument.setFont_)
    except Exception:
        return False


def disk_hash(path):
    if not path:
        return None
    try:
        return source_hash(path)
    except (OSError, ValueError, SourceError):
        return None


def capture(core, op):
    font = core.adapter._font(op['documentId'])
    before = core.adapter.document_state(op['documentId'])
    snapshot = font.copy()
    if snapshot is None or core.adapter._native_identity(snapshot) == core.adapter._native_identity(font):
        raise ValueError('Glyphs did not produce an independent full-font recovery copy')
    if core.adapter.document_state(op['documentId']) != before:
        raise ValueError('document changed while capturing recovery')
    op['scriptSnapshot'] = snapshot
    op['snapshotDocument'] = before
    op['snapshotSourceHash'] = disk_hash(before.get('path'))
    op['scriptResult']['recovery'] = dict(kind='memory_snapshot', snapshotId=uuid.uuid4().hex,
        bridgeSessionId=core.bridge_session_id, available=True, preRunDirty=before['dirty'],
        survivesRestart=False)


def restore(core, op, request, error):
    recovery = op['scriptResult'].get('recovery') or {}
    if op.get('scriptSnapshot') is None or not recovery.get('available'):
        raise error('snapshot_unavailable', 'The pre-run snapshot is unavailable; no font was replaced')
    if request['sourceHash'] != recovery.get('snapshotId'):
        raise error('stale_snapshot', 'The recovery snapshot identity changed')
    state = core.adapter.document_state(op['documentId'])
    before = op['snapshotDocument']
    if state['generation'] != request['generation'] or state.get('path') != before.get('path'):
        raise error('stale_document', 'document changed after restoration review')
    font = core.adapter._font(op['documentId'])
    restored = op['scriptSnapshot'].copy()
    if restored is None:
        raise error('snapshot_unavailable', 'The recovery snapshot could not be copied')
    document = font.parent
    # A source changed outside this workflow cannot truthfully be called clean.
    dirty = before['dirty'] or bool(before.get('path') and (
        op.get('snapshotSourceHash') is None or disk_hash(before['path']) != op['snapshotSourceHash']))
    op['restoreRequest'] = dict(request)  # Retain before attempting native replacement.
    try:
        document.setFont_(restored)
        document.undoManager().removeAllActions()
        document.updateChangeCount_(2)  # Clear then reproduce the appropriate dirty state.
        if dirty:
            document.updateChangeCount_(0)
        after = core.adapter._document_state(restored)
        after['familyName'] = str(restored.familyName or 'Untitled')
        if after['dirty'] is not bool(dirty) or after.get('path') != before.get('path'):
            raise ValueError('native restoration did not retain its path and required dirty state')
        op['scriptResult'].update(beforeRunRestored=True, documentAfter=after)
        op.update(status='discarded', error=None)
        release(op)
    except BaseException as exc:
        op.update(status='failed', error=dict(code='restoration_unverified', message=str(exc)[:2000],
                  details=dict(writeAttempted=True, restoration='unverified')))
    return core._public(op)


def release(op):
    op.pop('scriptSnapshot', None)
    if op.get('scriptResult', {}).get('recovery'):
        op['scriptResult']['recovery']['available'] = False
