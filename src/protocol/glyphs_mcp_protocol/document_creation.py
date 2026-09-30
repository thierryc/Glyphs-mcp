"""Closed, document-independent font creation contract."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from .models import ProtocolError

CAPABILITY = "document.create.v1"


def text(value, label):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 255:
        raise ProtocolError("invalid_request", f"{label} must be 1-255 characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ProtocolError("invalid_request", f"{label} must not contain control characters")
    return value.strip()


def options(family_name, idempotency_key, units_per_em=1000):
    family = text(family_name, "family_name")
    key = text(idempotency_key, "idempotency_key")
    if type(units_per_em) is not int or not 16 <= units_per_em <= 16384:
        raise ProtocolError("invalid_request", "units_per_em must be an integer from 16 to 16384")
    return {
        "creationId": "create_" + hashlib.sha256(key.encode("utf-8")).hexdigest(),
        "familyName": family, "unitsPerEm": units_per_em,
    }


def request(value):
    fields = {"creationId", "bridgeSessionId", "familyName", "unitsPerEm"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ProtocolError("invalid_request", "creation request fields are incomplete or unexpected")
    identity = value["creationId"]
    if not isinstance(identity, str) or not identity.startswith("create_") or len(identity) != 71:
        raise ProtocolError("invalid_request", "invalid creationId")
    if any(character not in "0123456789abcdef" for character in identity[7:]):
        raise ProtocolError("invalid_request", "invalid creationId")
    normalized = options(value["familyName"], "validation", value["unitsPerEm"])
    return {**normalized, "creationId": identity,
            "bridgeSessionId": text(value["bridgeSessionId"], "bridgeSessionId")}
