"""Exact-document detached copies with retained native outcomes."""
import copy
from glyphs_mcp_protocol import ProtocolError, document_duplication as contract
from .document_lifecycle import guard


def available():
    try:
        from GlyphsApp import GSFont, Glyphs
        return callable(getattr(Glyphs, 'documentController', None)) and all(callable(getattr(GSFont, method, None)) for method in ('copy', 'show'))
    except ImportError:
        return False


def public(core, op, error):
    if op['error']:
        failure = op['error']
        raise error(failure['code'], failure['message'], details=failure['details'])
    if op['result'] is None:
        raise error('duplication_in_progress', 'The original duplication is in progress')
    return {**copy.deepcopy(op['result']), **core.adapter.document_state(op['result']['id'])}


def duplicate(core, supplied, error):
    try:
        request = contract.request(supplied)
    except ProtocolError as exc:
        raise error(exc.code, exc.message) from exc
    if core.paused:
        raise error('server_stopped', 'the Glyphs MCP server is stopped')
    if request['bridgeSessionId'] != core.bridge_session_id:
        raise error('duplication_outcome_unknown', 'The bridge restarted; reconcile the original copy')
    with core._lock:
        previous = core._duplications.get(request['duplicationId'])
        if previous is not None:
            if previous['request'] != request:
                raise error('duplication_conflict', 'The duplication key belongs to another request')
            return public(core, previous, error)
        if not available():
            raise error('unsupported_capability', 'Native document duplication is unavailable')
        guard(core, request['documentId'], error)
        source = core.adapter._font(request['documentId'])
        before = core.adapter.document_state(request['documentId'])
        if len(core._duplications) >= 1024:
            raise error('duplication_limit_reached', 'This bridge session reached its duplication limit')
        op = dict(request=request, result=None, error=None)
        core._duplications[request['duplicationId']] = op
        font = None
        try:
            font = source.copy()
            if font is None or core.adapter._native_identity(font) == core.adapter._native_identity(source):
                raise ValueError('Native full-font copy is not independent')
            if request['familyName'] is not None:
                font.familyName = request['familyName']
            if core.adapter.document_state(request['documentId']) != before:
                raise ValueError('The source changed while constructing its detached copy')
            font.show()
            identity = core.adapter._id(font)
            state = core.adapter.document_state(identity)
            after_source = core.adapter.document_state(request['documentId'])
            # UPDATEINTERFACE can advance a dirty source's fallback generation
            # when a different window is shown. It does not describe font edits.
            if state.get('path') is not None or any(after_source.get(key) != before.get(key) for key in ('path', 'dirty')):
                raise ValueError('Native duplicate must be pathless and leave the source unchanged')
            op['result'] = dict(state, documentId=identity, sourceDocumentId=request['documentId'],
                familyName=str(font.familyName), duplicationId=request['duplicationId'],
                bridgeSessionId=core.bridge_session_id, created=True)
        except BaseException as exc:
            details = dict(duplicationId=request['duplicationId'], duplicationAttempted=True, nativeError=str(exc))
            if font is not None:
                try:
                    identity = core.adapter._id(font)
                    core.adapter.document_state(identity)
                    details['documentId'] = identity
                except Exception:
                    pass
            op['error'] = dict(code='duplication_outcome_unknown', message='Inspect the original duplication before a new request', details=details)
        return public(core, op, error)
