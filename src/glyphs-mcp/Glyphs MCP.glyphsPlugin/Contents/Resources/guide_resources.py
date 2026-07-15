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
_GLYPHS3_COMPAT_RESOURCE_URI = "glyphs://glyphs-mcp/glyphs3-compatibility"
_RESOURCES_DIR = Path(__file__).resolve().parent
_GUIDE_PATH = _RESOURCES_DIR / "MCP_GUIDE.md"
_GLYPHS3_COMPAT_PATH = _RESOURCES_DIR / "GLYPHS3_COMPATIBILITY.md"


def _add_markdown_resource(uri: str, name: str, description: str, path: Path, tags: set[str]) -> None:
    if not path.exists():
        logger.info("Guide file %s not found; skipping resource registration", path)
        return

    mcp.add_resource(
        FileResource(
            uri=uri,
            name=name,
            description=description,
            path=path.resolve(),
            mime_type="text/markdown",
            tags=tags,
        )
    )


def register_guide_resource() -> None:
    """Register bundled guide resources."""

    try:
        _add_markdown_resource(
            uri=_GUIDE_RESOURCE_URI,
            name="Glyphs MCP guide",
            description="Quick reference for using the Glyphs MCP server (tools-first, local, safe patterns).",
            path=_GUIDE_PATH,
            tags={"guide", "glyphs-mcp"},
        )
        _add_markdown_resource(
            uri=_GLYPHS3_COMPAT_RESOURCE_URI,
            name="Glyphs 3 compatibility notes",
            description="Known limitations when running Glyphs MCP in Glyphs 3.",
            path=_GLYPHS3_COMPAT_PATH,
            tags={"guide", "glyphs-mcp", "glyphs3", "compatibility"},
        )
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.warning("Failed to register guide resources: %s", exc)


# Automatically register the resource when the plug-in imports this module.
if os.environ.get("GLYPHS_MCP_SKIP_AUTO_REGISTER") != "1":
    register_guide_resource()
