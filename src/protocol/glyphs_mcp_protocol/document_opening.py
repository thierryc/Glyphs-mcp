"""Document-independent, retry-safe opening of native Glyphs sources."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

from .document_creation import text
from .models import ProtocolError

CAPABILITY = "document.open.v1"


def source_path(value, *, formats=None):
    if (not isinstance(value, str) or not 1 <= len(value) <= 4096
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise ProtocolError("invalid_request", "path must be an absolute local path without control characters")
    path = Path(value)
    if not path.is_absolute():
        raise ProtocolError("invalid_request", "path must be absolute; URLs and home-relative paths are unsupported")
    try:
        path = path.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProtocolError("invalid_request", "the document path cannot be resolved") from exc
    if path.suffix.lower() not in (formats or {".glyphs", ".glyphspackage"}):
        raise ProtocolError("unsupported_format", "Open requires a .glyphs file or .glyphspackage folder")
    return str(path)


def validate_source(path, *, formats=None):
    source = Path(path)
    if not source.exists():
        raise ProtocolError("file_not_found", "the requested Glyphs source does not exist")
    suffix = source.suffix.lower()
    if suffix not in (formats or {".glyphs", ".glyphspackage"}):
        raise ProtocolError("unsupported_format", "Unsupported font source format")
    package = suffix in {".glyphspackage", ".ufo"}
    if (package and not source.is_dir()) or (not package and not source.is_file()):
        raise ProtocolError("invalid_request", "Font packages must be folders and font files must be regular files")


def options(path, idempotency_key):
    key = text(idempotency_key, "idempotency_key")
    return {"openId": "open_" + hashlib.sha256(key.encode("utf-8")).hexdigest(), "path": source_path(path)}


def request(value):
    if not isinstance(value, Mapping) or set(value) != {"openId", "path", "bridgeSessionId"}:
        raise ProtocolError("invalid_request", "opening request fields are incomplete or unexpected")
    identity = value["openId"]
    if (not isinstance(identity, str) or len(identity) != 69 or not identity.startswith("open_")
            or any(character not in "0123456789abcdef" for character in identity[5:])):
        raise ProtocolError("invalid_request", "invalid openId")
    # Retained requests already contain a canonical path. Do not resolve them
    # again: a later filesystem change must not redirect a reserved request.
    path = value["path"]
    if (not isinstance(path, str) or not 1 <= len(path) <= 4096 or not Path(path).is_absolute()
            or Path(path).suffix.lower() not in {".glyphs", ".glyphspackage"}
            or any(ord(character) < 32 or ord(character) == 127 for character in path)):
        raise ProtocolError("invalid_request", "invalid retained opening path")
    return {"openId": identity, "path": path, "bridgeSessionId": text(value["bridgeSessionId"], "bridgeSessionId")}
