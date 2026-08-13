# encoding: utf-8

"""Typed Glyphs MCP tools for LitSquare metadata and selected path roles."""

from __future__ import annotations

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from glyphs_litsquare_adapter import (
    metadata_snapshot,
    patch_metadata_transaction,
    selected_path_snapshot,
    set_path_roles_transaction,
)
from mcp_tool_helpers import _run_on_main_thread, _safe_json
from tool_registration import glyphs_tool


def _error_payload(error):
    return {
        "ok": False,
        "summary": {"changed": False},
        "error": {
            "code": "litsquare_error",
            "message": str(error),
            "recoverable": True,
        },
        "fontSaved": False,
    }


@glyphs_tool()
async def get_litsquare_metadata(
    font_index: int = 0,
    glyph_name: str = None,
    layer_id: str = None,
    include_inherited: bool = True,
) -> str:
    """Read direct LitSquare Font, Glyph, and Layer metadata plus effective settings."""

    try:
        result = _run_on_main_thread(
            lambda: metadata_snapshot(
                font_index=font_index,
                glyph_name=glyph_name,
                layer_id=layer_id,
                include_inherited=include_inherited,
                app=Glyphs,
            )
        )
        return _safe_json(result)
    except Exception as error:
        return _safe_json(_error_payload(error))


@glyphs_tool()
async def get_selected_litsquare_path_roles(font_index: int = 0) -> str:
    """Read LitSquare roles for selected paths in the active glyph layer."""

    try:
        result = _run_on_main_thread(lambda: selected_path_snapshot(font_index=font_index, app=Glyphs))
        return _safe_json(result)
    except Exception as error:
        return _safe_json(_error_payload(error))


@glyphs_tool()
async def patch_litsquare_metadata(
    scope: str,
    patch: dict,
    font_index: int = 0,
    glyph_name: str = None,
    layer_id: str = None,
    expected_updated_at: str = None,
    dry_run: bool = True,
    confirm: bool = False,
) -> str:
    """Dry-run or confirm an RFC 7396 patch to one explicit LitSquare scope.

    The tool preserves unknown LitSquare fields and unrelated user-data
    namespaces, manages updatedAt, verifies native readback, and never saves.
    """

    try:
        result = patch_metadata_transaction(
            scope=scope,
            patch=patch,
            font_index=font_index,
            glyph_name=glyph_name,
            layer_id=layer_id,
            expected_updated_at=expected_updated_at,
            dry_run=dry_run,
            confirm=confirm,
            app=Glyphs,
        )
        return _safe_json(result)
    except Exception as error:
        return _safe_json(_error_payload(error))


@glyphs_tool()
async def set_litsquare_path_roles(
    targets: list,
    role: str = None,
    font_index: int = 0,
    dry_run: bool = True,
    confirm: bool = False,
) -> str:
    """Dry-run or confirm one open-string role for explicit reviewed paths.

    Leading and trailing whitespace is trimmed; pass role=null or an empty
    string to remove the namespaced role. Target fingerprints and expected
    roles are rechecked atomically before any mutation. The tool preserves
    every built-in path attribute and never saves.
    """

    try:
        result = set_path_roles_transaction(
            targets=targets,
            role=role,
            font_index=font_index,
            dry_run=dry_run,
            confirm=confirm,
            app=Glyphs,
        )
        return _safe_json(result)
    except Exception as error:
        return _safe_json(_error_payload(error))


__all__ = [
    "get_litsquare_metadata",
    "get_selected_litsquare_path_roles",
    "patch_litsquare_metadata",
    "set_litsquare_path_roles",
]
