# encoding: utf-8

"""Expose a single "guide" resource for the Glyphs MCP server.

The guide is intentionally short and oriented toward LLM usage: the server is
tools-first; resources exist to help produce better tool calls and safer code.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastmcp.resources import FileResource

from mcp_tools import mcp

logger = logging.getLogger(__name__)

_GUIDE_RESOURCE_URI = "glyphs://glyphs-mcp/guide"
_GUIDE_PATH = Path(__file__).resolve().parent / "MCP_GUIDE.md"


def register_guide_resource() -> None:
    """Register the bundled guide as a single MCP resource."""

    if not _GUIDE_PATH.exists():
        logger.info("Guide file %s not found; skipping guide resource registration", _GUIDE_PATH)
        return

    try:
        mcp.add_resource(
            FileResource(
                uri=_GUIDE_RESOURCE_URI,
                name="Glyphs MCP guide",
                description="Quick reference for using the Glyphs MCP server (tools-first, local, safe patterns).",
                path=_GUIDE_PATH.resolve(),
                mime_type="text/markdown",
                tags={"guide", "glyphs-mcp"},
            )
        )
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.warning("Failed to register guide resource: %s", exc)


# Automatically register the resource when the plug-in imports this module.
if os.environ.get("GLYPHS_MCP_SKIP_AUTO_REGISTER") != "1":
    register_guide_resource()
