"""Journal duplicate intents; never repeat an unknown creation after restart."""
import fcntl
import json
from glyphs_mcp_protocol import ProtocolError, document_duplication as contract
from .document_closing import guard, write


def duplicate(service, error, document_id, idempotency_key, family_name=None):
    try:
        options = contract.options(document_id, idempotency_key, family_name)
    except ProtocolError as exc:
        raise error(exc.code, exc.message) from exc
    root = service.jobs.root / 'document-duplications'
    root.mkdir(mode=0o700, exist_ok=True)
    record = root / (options['duplicationId'] + '.json')
    with (root / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        status = service.bridge.status()
        if contract.CAPABILITY not in (status.get('writeCapabilities') or []):
            raise error('unsupported_capability', 'Duplicate requires document.duplicate.v1')
        session = status.get('bridgeSessionId')
        if not isinstance(session, str) or not session:
            raise error('unsupported_capability', 'Duplicate requires a bridge session identity')
        request = dict(options, bridgeSessionId=session)
        if record.exists():
            try:
                retained = contract.request(json.loads(record.read_text()))
            except (OSError, ValueError, ProtocolError) as exc:
                raise error('duplication_outcome_unknown', 'The original duplication record is unreadable') from exc
            if any(retained[key] != options[key] for key in options):
                raise error('duplication_conflict', 'The duplication key belongs to another request')
            if retained['bridgeSessionId'] != session:
                raise error('duplication_outcome_unknown', 'The bridge restarted; reconcile the original copy')
            return service.bridge.duplicate_document(retained)
        guard(service, service._document(document_id), error)
        write(record, request)
        return service.bridge.duplicate_document(request)
