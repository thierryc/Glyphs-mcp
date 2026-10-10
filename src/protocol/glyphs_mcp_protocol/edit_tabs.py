"""Save-free, exact-document Edit-tab opening contract."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping

from .document_creation import text as identifier
from .models import ProtocolError

CAPABILITY = "document.edit-tab.open.v1"
MAX_TEXT = 4096
MAX_GLYPHS = 100


def exact_identifier(value, label):
    checked = identifier(value, label)
    if checked != value or any(0xD800 <= ord(c) <= 0xDFFF for c in checked):
        raise ProtocolError("invalid_request", f"{label} must be an exact Unicode identifier without surrounding whitespace")
    return checked


def contents(text, glyphs, master_id):
    if text is not None and glyphs is not None:
        raise ProtocolError("invalid_request", "Supply text or glyphs, not both")
    if text is not None:
        if (not isinstance(text, str) or len(text) > MAX_TEXT
                or any((ord(c) < 32 and c not in '\n\r\t') or ord(c) == 127
                       or 0xD800 <= ord(c) <= 0xDFFF for c in text)):
            raise ProtocolError("invalid_request", "text must contain at most 4096 Unicode characters without unsupported controls")
    if glyphs is not None:
        if not isinstance(glyphs, list) or not 1 <= len(glyphs) <= MAX_GLYPHS:
            raise ProtocolError("invalid_request", "glyphs must contain 1-100 exact glyph names")
        glyphs = [exact_identifier(name, "glyph name") for name in glyphs]
    return {"text": text, "glyphs": glyphs,
            "masterId": exact_identifier(master_id, "master_id") if master_id is not None else None}


def options(document_id, idempotency_key, text=None, glyphs=None, master_id=None):
    key = exact_identifier(idempotency_key, "idempotency_key")
    return {"tabOpenId": "tab_open_" + hashlib.sha256(key.encode("utf-8")).hexdigest(),
            "documentId": exact_identifier(document_id, "document_id"),
            **contents(text, glyphs, master_id)}


def request(value):
    fields = {"tabOpenId", "documentId", "bridgeSessionId", "text", "glyphs", "masterId"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ProtocolError("invalid_request", "Edit-tab request fields are incomplete or unexpected")
    identity = value["tabOpenId"]
    if (not isinstance(identity, str) or len(identity) != 73 or not identity.startswith("tab_open_")
            or any(c not in "0123456789abcdef" for c in identity[9:])):
        raise ProtocolError("invalid_request", "invalid tabOpenId")
    return {"tabOpenId": identity,
            "documentId": exact_identifier(value["documentId"], "documentId"),
            "bridgeSessionId": exact_identifier(value["bridgeSessionId"], "bridgeSessionId"),
            **contents(value["text"], value["glyphs"], value["masterId"])}
