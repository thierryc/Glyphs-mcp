"""Closed job request validation, shared by direct jobs and conversations."""
import math
from typing import Any
from glyphs_mcp_protocol import ProtocolError, dimensions, scripts

JOB_KINDS = ("width_delta", "spacing", "kerning_collision", "start_nodes", "slant")


def validate(kind, delta, glyphs, options, ServiceError):
    available = list(JOB_KINDS) + ["outline_edit", "native_action", "feature_compile", "font_export", "dimensions_edit", "python_script"]
    if str(kind) not in available:
        raise ServiceError("unsupported_job", "supported jobs: " + ", ".join(available))
    if kind == "width_delta" and (isinstance(delta, bool) or not isinstance(delta, (int, float)) or not math.isfinite(float(delta)) or delta == 0):
        raise ServiceError("invalid_request", "delta must be a finite non-zero number")
    names = []
    if glyphs is not None:
        if not isinstance(glyphs, list) or not 1 <= len(glyphs) <= 10_000:
            raise ServiceError("invalid_request", "glyphs must contain 1-10,000 names")
        names = [str(value).strip() for value in glyphs]
        if any(not value for value in names) or len(names) != len(set(names)):
            raise ServiceError("invalid_request", "glyph names must be non-empty and unique")
    if kind in ("spacing", "kerning_collision", "start_nodes", "slant", "outline_edit", "native_action", "feature_compile", "font_export", "dimensions_edit", "python_script"):
        from .spacing import validate_options as spacing_options
        from .collision import validate_options as collision_options
        from .start_node_job import validate_options as start_options
        from .slant_job import validate_options as slant_options
        from glyphs_mcp_protocol.outline import validate_options as outline_options
        from glyphs_mcp_protocol.native_actions import validate_options as native_action_options
        from glyphs_mcp_protocol.compile_export import (
            validate_compile_options, validate_export_options,
        )
        validate_options = {
            "spacing": spacing_options,
            "kerning_collision": collision_options,
            "start_nodes": start_options,
            "slant": slant_options,
            "outline_edit": outline_options,
            "native_action": native_action_options,
            "feature_compile": validate_compile_options,
            "font_export": validate_export_options,
            "dimensions_edit": dimensions.validate_options,
            "python_script": scripts.validate_options,
        }[kind]
        try:
            if delta is not None:
                raise ValueError(kind + " uses options, not delta")
            if kind == "kerning_collision" and names:
                raise ValueError("kerning_collision selects explicit pairs in options")
            if kind == "start_nodes" and not 1 <= len(names) <= 100:
                raise ValueError("start_nodes requires 1-100 explicit glyphs")
            if kind == "outline_edit" and names:
                raise ValueError("outline_edit selects glyphs inside options.targets")
            if kind in ("native_action", "feature_compile", "font_export", "dimensions_edit", "python_script") and glyphs is not None:
                raise ValueError(f"{kind} does not use top-level glyphs")
            return {"kind": kind, "glyphs": names, "options": validate_options({} if options is None else options)}
        except ProtocolError as error:
            raise ServiceError(error.code, error.message) from error
        except ValueError as error:
            raise ServiceError("invalid_request", str(error)) from error
    if options:
        raise ServiceError("invalid_request", "width_delta does not use options")
    return {"kind": "width_delta", "delta": delta, "glyphs": names}
