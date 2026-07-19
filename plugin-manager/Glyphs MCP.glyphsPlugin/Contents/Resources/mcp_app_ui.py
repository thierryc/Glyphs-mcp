# encoding: utf-8

"""Register the versioned Glyphs MCP feedback panel as an MCP App resource."""

from __future__ import annotations

import logging
from pathlib import Path

from fastmcp.resources import TextResource
from pydantic import Field

from mcp_runtime import mcp


logger = logging.getLogger(__name__)

FEEDBACK_RESOURCE_URI = "ui://glyphs-mcp/feedback-v1.html"
FEEDBACK_RESOURCE_MIME = "text/html;profile=mcp-app"
FEEDBACK_RESOURCE_PATH = Path(__file__).resolve().parent / "feedback_ui_v1.html"


class MCPAppTextResource(TextResource):
    """TextResource variant allowing the registered MCP App MIME profile.

    FastMCP 2.12.0 validates MIME values without parameters. MCP Apps require
    ``text/html;profile=mcp-app``, so this narrow subclass relaxes only that
    field while leaving the installed dependency versions unchanged.
    """

    mime_type: str = Field(default=FEEDBACK_RESOURCE_MIME)


_registered = False


def register_feedback_resource() -> bool:
    """Register the feedback panel once and return whether it was added."""

    global _registered
    if _registered:
        return False

    html = FEEDBACK_RESOURCE_PATH.read_text(encoding="utf-8")
    resource = MCPAppTextResource(
        uri=FEEDBACK_RESOURCE_URI,
        name="Glyphs MCP Feedback",
        title="Glyphs MCP Feedback",
        description="Read-only review, dry-run confirmation, progress, and error feedback for Glyphs MCP.",
        mime_type=FEEDBACK_RESOURCE_MIME,
        text=html,
        meta={
            "ui": {
                "prefersBorder": True,
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": [],
                },
            }
        },
    )
    mcp.add_resource(resource)
    _registered = True
    logger.debug("Registered MCP App resource %s", FEEDBACK_RESOURCE_URI)
    return True


register_feedback_resource()


__all__ = [
    "FEEDBACK_RESOURCE_MIME",
    "FEEDBACK_RESOURCE_PATH",
    "FEEDBACK_RESOURCE_URI",
    "MCPAppTextResource",
    "register_feedback_resource",
]
