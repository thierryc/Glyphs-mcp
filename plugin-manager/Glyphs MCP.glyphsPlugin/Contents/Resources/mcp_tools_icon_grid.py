# encoding: utf-8

"""Typed Glyphs MCP tools for fixed horizontal IconGrid centering."""

from __future__ import annotations

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from glyphs_icon_grid_adapter import (
    icon_grid_snapshot,
    reset_icon_grid_horizontal_center_transaction,
    set_icon_grid_horizontal_center_transaction,
)
from mcp_tool_helpers import _safe_json
from tool_registration import glyphs_tool


def _error_payload(error):
    return {
        "ok": False,
        "summary": {"changed": False},
        "error": {
            "code": "icon_grid_centering_error",
            "message": str(error),
            "recoverable": True,
        },
        "fontSaved": False,
        "redrawn": False,
    }


@glyphs_tool()
async def get_icon_grid_horizontal_center(
    font_index: int = 0,
    glyph_name: str = None,
    layer_id: str = None,
) -> str:
    """Read a layer's fixed IconGrid center and one-time position candidates."""

    try:
        return _safe_json(
            icon_grid_snapshot(
                font_index=font_index,
                glyph_name=glyph_name,
                layer_id=layer_id,
                app=Glyphs,
            )
        )
    except Exception as error:
        return _safe_json(_error_payload(error))


@glyphs_tool()
async def set_icon_grid_horizontal_center(
    font_index: int,
    glyph_name: str,
    layer_id: str,
    center_x: float,
    expected_state_fingerprint: str,
    dry_run: bool = True,
    confirm: bool = False,
) -> str:
    """Dry-run or store one fixed horizontal coordinate on a layer."""

    try:
        return _safe_json(
            set_icon_grid_horizontal_center_transaction(
                expected_state_fingerprint=expected_state_fingerprint,
                font_index=font_index,
                glyph_name=glyph_name,
                layer_id=layer_id,
                center_x=center_x,
                dry_run=dry_run,
                confirm=confirm,
                app=Glyphs,
            )
        )
    except Exception as error:
        return _safe_json(_error_payload(error))


@glyphs_tool()
async def reset_icon_grid_horizontal_center(
    font_index: int,
    glyph_name: str,
    layer_id: str,
    expected_state_fingerprint: str,
    dry_run: bool = True,
    confirm: bool = False,
) -> str:
    """Dry-run or remove only the active layer's IconGrid center policy."""

    try:
        return _safe_json(
            reset_icon_grid_horizontal_center_transaction(
                expected_state_fingerprint=expected_state_fingerprint,
                font_index=font_index,
                glyph_name=glyph_name,
                layer_id=layer_id,
                dry_run=dry_run,
                confirm=confirm,
                app=Glyphs,
            )
        )
    except Exception as error:
        return _safe_json(_error_payload(error))


__all__ = [
    "get_icon_grid_horizontal_center",
    "reset_icon_grid_horizontal_center",
    "set_icon_grid_horizontal_center",
]
