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
from .outline import outline_state_hash, path_hash, validate_options as validate_outline_options
from .native_actions import (
    ACTION_SPECS,
    NATIVE_ACTIONS,
    recognized_actions,
    state_hash as native_action_state_hash,
    validate_options as validate_native_action_options,
)
from .compile_export import (
    JOB_CAPABILITIES,
    recognized_job_capabilities,
    validate_compile_options,
    validate_artifact_manifest,
    validate_export_options,
    validate_worker_result,
)

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
    "outline_state_hash",
    "path_hash",
    "validate_outline_options",
    "ACTION_SPECS",
    "NATIVE_ACTIONS",
    "recognized_actions",
    "native_action_state_hash",
    "validate_native_action_options",
    "JOB_CAPABILITIES",
    "recognized_job_capabilities",
    "validate_compile_options",
    "validate_artifact_manifest",
    "validate_export_options",
    "validate_worker_result",
]
