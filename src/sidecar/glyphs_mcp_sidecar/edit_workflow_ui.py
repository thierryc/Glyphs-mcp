"""Portable MCP Apps registration with first-class text tool results."""
from pathlib import Path
from typing import Any

from fastmcp.resources import TextResource
from fastmcp.tools.tool import ToolResult
from mcp.types import ReadResourceRequest, TextContent
from pydantic import Field

RESOURCE_URI = "ui://glyphs-mcp/edit-workflow-v1.html"
RESOURCE_MIME = "text/html;profile=mcp-app"
UI_META = {"ui": {"resourceUri": RESOURCE_URI, "visibility": ["model", "app"]}}
RESOURCE_META = {"ui": {"prefersBorder": True, "csp": {"connectDomains": [], "resourceDomains": []}}}


def preserve_ui_resource_metadata(mcp):
    # The pinned FastMCP also drops resource metadata when constructing read
    # contents. Supply the standard CSP on the wire for this one bundled App.
    handler = mcp._mcp_server.request_handlers[ReadResourceRequest]

    async def read(request):
        result = await handler(request)
        for content in result.root.contents:
            if str(content.uri) == RESOURCE_URI:
                content.meta = RESOURCE_META
        return result

    mcp._mcp_server.request_handlers[ReadResourceRequest] = read


class AppResource(TextResource):
    # FastMCP 2.12's default MIME validator predates parameterized MCP Apps MIME.
    mime_type: str = Field(default=RESOURCE_MIME)


def register_edit_workflow_tools(mcp, service):
    from .service import ServiceError

    html = Path(__file__).with_name("edit_workflow_v1.html").read_text(encoding="utf-8")
    mcp.add_resource(AppResource(
        uri=RESOURCE_URI, name="Glyphs edit workflow", title="Glyphs edit workflow",
        description="Save prerequisites, progress and reversible edit review, also available in text.",
        text=html, meta=RESOURCE_META,
    ))
    preserve_ui_resource_metadata(mcp)

    def result(callback):
        try:
            value = callback()
            payload = {"ok": True, "data": value}
            text = value["text"]
        except ServiceError as exc:
            payload = {"ok": False, "error": exc.as_dict()}
            text = exc.message
        return ToolResult(content=[TextContent(type="text", text=text)], structured_content=payload)

    @mcp.tool(name="start_edit_workflow", meta=UI_META,
              annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
    def start_edit_workflow(
        document_id: str, kind: str, idempotency_key: str, mode: str = "apply",
        delta: float | None = None, glyphs: list[str] | None = None, options: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Preferred conversational route for an authorized font edit. Reuse a unique idempotency_key on retries. Same typed scope as start_job; mutation kinds only. apply mode automatically prepares and applies complete results; preview mode waits. Never saves implicitly: dirty/new fonts return choices. Present the MCP App where supported and always retain the text choices. 'Save and continue' saves current work once, NOT the resulting edit. Ask for saving only if not already authorized. No user should type tool IDs, tokens or JSON. Existing Dimensions overwrite consent remains required. On warnings/skips review the full get_job report before selecting Apply; do not claim partial work as complete."""
        return result(lambda: service.edit_workflows.start(
            document_id, kind=kind, idempotency_key=idempotency_key, mode=mode,
            delta=delta, glyphs=glyphs, options=options))

    @mcp.tool(name="get_edit_workflow", meta=UI_META,
              annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
    def get_edit_workflow(workflow_id: str) -> ToolResult:
        """Read the authoritative workflow, revision, action tokens and underlying job evidence. Show the standard MCP App when available; otherwise convey its text and choices. Reuse the workflow ID, never restart on a timeout. Poll only while poll is true, without narrating unchanged status. A missing card does not stop authorized work. Source and dirty checks still apply; editing during preparation requires preparing again."""
        return result(lambda: service.edit_workflows.get(workflow_id))

    @mcp.tool(name="respond_edit_workflow", meta={"ui": {"visibility": ["model", "app"]}},
              annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False})
    def respond_edit_workflow(
        workflow_id: str, expected_revision: int, action_token: str,
        destination: str | None = None, approved_overwrites: list[dict[str, Any]] | None = None,
    ) -> ToolResult:
        """Execute one offered workflow choice. Map natural-language replies to the latest returned action token and revision; never ask users to supply these. A save choice needs explicit or already-established scoped user authorization and saves the entire document. Save As additionally requires an absolute new destination shown to the user. The prerequisite save does not authorize saving the new result. Retrying the SAME token and arguments never repeats its effects. Refresh stale choices; never blindly replace uncertain actions. For Dimensions Apply, pass exact requiredOverwrites only after explicit approval of every shown old/new value. Other Apply actions use the original edit authorization, or the user's preview acceptance. Client permission dialogs still apply."""
        return result(lambda: service.edit_workflows.respond(
            workflow_id, expected_revision, action_token, destination=destination,
            approved_overwrites=approved_overwrites))
