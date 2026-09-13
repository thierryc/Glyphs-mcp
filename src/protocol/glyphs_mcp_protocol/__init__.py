"""Shared, dependency-free contracts for the lean Glyphs MCP architecture."""

from .models import (
    PATCH_VERSION,
    PROTOCOL_VERSION,
    TOOL_NAMES,
    ProtocolError,
    canonical_json,
    outline_hash,
    validate_companion_manifest,
    validate_patch,
)
from .auth import default_token_path, load_or_create_token

__all__ = [
    "PATCH_VERSION",
    "PROTOCOL_VERSION",
    "TOOL_NAMES",
    "ProtocolError",
    "canonical_json",
    "outline_hash",
    "validate_companion_manifest",
    "validate_patch",
    "default_token_path",
    "load_or_create_token",
]
