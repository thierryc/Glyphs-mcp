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
            content = [TextContent(type="text", text=text), TextContent(type="text", text=value["modelContext"])]
        except ServiceError as exc:
            payload = {"ok": False, "error": exc.as_dict()}
            text = exc.message
            content = [TextContent(type="text", text=text)]
        return ToolResult(content=content, structured_content=payload)

    @mcp.tool(name="start_edit_workflow", meta=UI_META,
              annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
    def start_edit_workflow(
        document_id: str, kind: str, idempotency_key: str, mode: str = "apply",
        delta: float | None = None, glyphs: list[str] | None = None, options: dict[str, Any] | None = None,
        auto_keep: bool = True,
    ) -> ToolResult:
        """Perform an authorized font edit through the conversation workflow. Reuse idempotency_key on retries. Typed apply mode prepares and applies complete results; preview waits. python_script uses source, JSON params, entrypoint=per_target|script, targets and optional summary (500 characters); requires script.native.v1. Preparation validates syntax and targets without executing Python or saving. For a result-focused task, dispatch the current Run action under original task authorization: no source review, human click or extra Run question is required. Write-only/review-only script requests do not authorize execution; writing a script includes code review. Explicit previews wait for authorization. Dirty/new fonts require separately authorized saving; reuse existing save authorization. Never save the resulting edit implicitly. New edit workflows default to auto_keep=true: an active card selects Keep changes without saving after 30 seconds on success, ending workflow recovery. Typed Keep preserves native Undo/Redo. Pass auto_keep=false when the user says wait for my answer, disables automatic feedback, or asks to inspect the result before deciding. This directive persists in the conversation until changed. Existing workflows use their wait_for_answer action. Text-only clients never infer an answer from elapsed time. Show the one-time script warning and summary; exact source is optional Script details. Keep workflow_id and poll until a choice or outcome. Missing cards do not stop authorized work. Retain typed overwrite approval and report review requirements; do not claim skipped work as complete."""
        return result(lambda: service.edit_workflows.start(
            document_id, kind=kind, idempotency_key=idempotency_key, mode=mode,
            delta=delta, glyphs=glyphs, options=options, auto_keep=auto_keep))

    @mcp.tool(name="get_edit_workflow", meta=UI_META,
              annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
    def get_edit_workflow(workflow_id: str, include_review: bool = False) -> ToolResult:
        """Read compact workflow state, request fingerprint, revision, actions and progress. Use include_review=true only for Show script or requested source/output details; ordinary polling omits them. A read never executes Python. For blockers, blockingWorkflowId identifies the original workflow when available; typed blockers also offer manual Keep. For scripts, use Keep/Save/Restore actions, never typed Undo. Restoration availability is recently checked display evidence; the baseline is checked again at Restore. The JSON text control reference contains workflow_id, expected_revision and actions with action_token, even without structured data. Retain it internally for natural-language follow-ups. Show the standard MCP App when available; otherwise convey its text and choices. Reuse the workflow ID, never restart on a timeout. Poll while poll is true until a choice or outcome, without narrating unchanged status; Preparing is not Applied. A missing card does not stop authorized work. Source and dirty checks still apply; editing during preparation requires preparing again."""
        return result(lambda: service.edit_workflows.get(workflow_id, include_review=include_review))

    @mcp.tool(name="respond_edit_workflow", meta={"ui": {"visibility": ["model", "app"]}},
              annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False})
    def respond_edit_workflow(
        workflow_id: str, expected_revision: int, action_token: str,
        destination: str | None = None, approved_overwrites: list[dict[str, Any]] | None = None,
        automatic: bool = False,
    ) -> ToolResult:
        """Execute one offered workflow choice. Map natural-language replies to the JSON text control reference's workflow_id, expected_revision and matching action_token; never ask users to supply these. Refresh with get_edit_workflow before acting on a later reply such as 'Save the font', since the card or worker may have advanced. A save choice needs explicit or already-established scoped user authorization and saves the entire document. Save As additionally requires an absolute new destination shown to the user. The prerequisite save does not authorize saving the new result. Retrying the SAME token and arguments never repeats its effects. Refresh stale choices; never blindly replace uncertain actions. For Dimensions Apply, pass exact requiredOverwrites only after explicit approval of every shown old/new value. Other Apply actions use the original edit authorization, or the user's preview acceptance. Run script uses original in-scope task authorization; optional source inspection and a human click are not prerequisites. Write-only or review-only requests do not authorize Run, and explicit previews wait. Save and run needs authorization to save the whole font; reuse established authorization without another question. Clear restoration requests authorize Restore saved version: it replaces all later unsaved font edits and clears Undo history, never saves or reruns Python, and cannot restore external effects. Keeping or saving ends the restoration offer. Map wait for my answer to the wait_for_answer action immediately; it disables this workflow countdown without cancelling the edit. The automatic=true flag is reserved for the card countdown and only permits Keep after success, never Run, Save, Restore or partial/unknown outcomes. A timeout origin is recorded as evidence, not proof of human approval. Cancellation stops remaining callbacks and cannot safely force-stop the current invocation. Client permission dialogs still apply."""
        return result(lambda: service.edit_workflows.respond(
            workflow_id, expected_revision, action_token, destination=destination,
            approved_overwrites=approved_overwrites, automatic=automatic))
