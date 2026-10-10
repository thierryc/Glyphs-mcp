"""Duplicate the current live font, without saving either document."""
import hashlib
from collections.abc import Mapping
from .edit_tabs import exact_identifier
from .models import ProtocolError

CAPABILITY = 'document.duplicate.v1'


def options(document_id, idempotency_key, family_name=None):
    key = exact_identifier(idempotency_key, 'idempotency_key')
    return dict(duplicationId='duplicate_' + hashlib.sha256(key.encode('utf-8')).hexdigest(),
                documentId=exact_identifier(document_id, 'document_id'),
                familyName=exact_identifier(family_name, 'family_name') if family_name is not None else None)


def request(value):
    if not isinstance(value, Mapping) or set(value) != {'duplicationId', 'documentId', 'familyName', 'bridgeSessionId'}:
        raise ProtocolError('invalid_request', 'invalid duplication fields')
    identity = value['duplicationId']
    if not isinstance(identity, str) or len(identity) != 74 or not identity.startswith('duplicate_') or any(c not in '0123456789abcdef' for c in identity[10:]):
        raise ProtocolError('invalid_request', 'invalid duplicationId')
    return dict(duplicationId=identity, documentId=exact_identifier(value['documentId'], 'documentId'),
        familyName=exact_identifier(value['familyName'], 'familyName') if value['familyName'] is not None else None,
        bridgeSessionId=exact_identifier(value['bridgeSessionId'], 'bridgeSessionId'))
