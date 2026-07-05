# encoding: utf-8

from __future__ import division, print_function, unicode_literals

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import _font_summary, _open_fonts_from_glyphs, _safe_json
from versioning import get_runtime_info


@mcp.tool()
async def get_server_info() -> str:
    """Return runtime identity and basic health details for this Glyphs MCP server."""
    payload = {"ok": True}
    try:
        payload.update(get_runtime_info())
    except Exception as exc:
        payload.update(
            {
                "version": "dev",
                "runtimeId": "dev+unknown",
                "codeHash": "unknown",
                "runtimeInfoError": str(exc),
            }
        )

    try:
        payload["glyphsReachable"] = bool(Glyphs)
        payload["glyphsVersion"] = getattr(Glyphs, "versionNumber", None)
    except Exception as exc:
        payload["glyphsReachable"] = False
        payload["glyphsError"] = str(exc)

    try:
        fonts = _open_fonts_from_glyphs(Glyphs)
        payload["openFontCount"] = len(fonts)
        payload["availableFonts"] = [_font_summary(font, i) for i, font in enumerate(fonts)]
    except Exception as exc:
        payload["openFontCount"] = None
        payload["availableFonts"] = []
        payload["fontDiscoveryError"] = str(exc)

    return _safe_json(payload)
