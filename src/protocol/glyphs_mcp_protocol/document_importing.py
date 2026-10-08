"""Explicit import of external font formats, separate from native Open."""
import hashlib
from collections.abc import Mapping
from pathlib import Path

from .document_creation import text
from .document_opening import source_path as normalize, validate_source as validate
from .models import ProtocolError

CAPABILITY = "document.import.v1"
FORMATS = frozenset({".ufo", ".otf", ".ttf"})


def options(path, idempotency_key):
    key = text(idempotency_key, "idempotency_key")
    try:
        path = normalize(path, formats=FORMATS)
    except ProtocolError as exc:
        if exc.code == "unsupported_format":
            raise ProtocolError(exc.code, "Import requires a .ufo folder, .otf file or .ttf file") from exc
        raise
    return {"importId": "import_" + hashlib.sha256(key.encode()).hexdigest(), "path": path}


def validate_source(path):
    validate(path, formats=FORMATS)


def request(value):
    if not isinstance(value, Mapping) or set(value) != {"importId", "path", "bridgeSessionId"}:
        raise ProtocolError("invalid_request", "import request fields are incomplete or unexpected")
    identity = value["importId"]
    if (not isinstance(identity, str) or len(identity) != 71 or not identity.startswith("import_")
            or any(character not in "0123456789abcdef" for character in identity[7:])):
        raise ProtocolError("invalid_request", "invalid importId")
    path = value["path"]
    if (not isinstance(path, str) or not 1 <= len(path) <= 4096 or not Path(path).is_absolute()
            or Path(path).suffix.lower() not in FORMATS
            or any(ord(c) < 32 or ord(c) == 127 for c in path)):
        raise ProtocolError("invalid_request", "invalid retained import path")
    return {"importId": identity, "path": path,
            "bridgeSessionId": text(value["bridgeSessionId"], "bridgeSessionId")}
