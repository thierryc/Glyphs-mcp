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
        """Perform an authorized edit; reuse the connection/document_id and retain idempotency_key for retries. Typed kinds include width_delta, spacing, kerning_edit, kerning_collision, start_nodes, slant, outline_edit, dimensions_edit and closed native_action. mode=apply prepares and applies complete typed results; preview waits. Warnings/skipped targets and Dimensions overwrites retain report review. Compilation/export use start_job. Preparation never saves; dirty/new fonts require separately authorized Save/Save As/manual saving. Reuse existing save authorization; prerequisite saving does not authorize saving the result.

        kerning_edit requires kerning.edit.exact.v1. options.edits holds 1-100 exact entries: op=set|remove, master, direction=LTR|RTL|vertical and left/right side objects {kind:glyph,name:...} or {kind:group,key:...}; set alone has finite value (zero is stored, remove deletes). Preparation is native and read-only; guarded application and selective Undo retain Keep/Save. No collision analysis.

        python_script requires script.native.v1. Options: exact source, JSON params, entrypoint=per_target|script, targets and optional summary (500 characters). Callback run(layer,params,context); whole scripts may use targets:[]. Targets: explicit {glyph,layer,surface} entries or {master:exactId,glyphs:all|names,surface}; IDs identify owning foregrounds. No fixed script target-count ceiling; complete request limit 4 MiB, never truncate. Typed/read limits remain. Retired executionMode/recovery are rejected. Preparation validates syntax/targets without executing Python. For an in-scope edit request, dispatch the offered Run action under original authorization without mandatory source review, human click or another question. Write-only/review-only requests never authorize execution; writing includes code review. Explicit previews wait. Show the script warning once; exact source stays optional View details.

        Results offer Keep changes without saving, Save and selective typed Undo or whole-font script Restore saved version. Keep ends workflow recovery and preserves native Undo/Redo. auto_keep=true lets a visible connected successful card Keep after 30 seconds. Set false for 'wait for my answer', disabled automatic feedback or inspection before deciding; honor that directive until changed. Existing workflows use wait_for_answer. Text-only clients remain manual.

        checkpoint_restore loads the selected whole-font version under a clear restore request: replaces later unsaved edits, clears Undo and returns a fresh binding without saving. Opt-in Git checkpoint failure is separate from Save success. Retain workflow_id; poll until a choice/outcome. Missing cards never block authorized work."""
        return result(lambda: service.edit_workflows.start(
            document_id, kind=kind, idempotency_key=idempotency_key, mode=mode,
            delta=delta, glyphs=glyphs, options=options, auto_keep=auto_keep))

    @mcp.tool(name="get_edit_workflow", meta=UI_META,
              annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
    def get_edit_workflow(workflow_id: str, include_review: bool = False) -> ToolResult:
        """Read compact state, request fingerprint, revision, actions and progress. Ordinary polling needs no health/job reads. A read never executes Python, saves or applies edits. Use include_review=true for Show script or requested source/output details. Card-only uiRefreshIntervalMs keeps visible pending choices current without extending agent polling. Optional action presentation groups main/menu/countdown controls. On stale_workflow_action, read this same workflow; never replay the rejected mutation automatically. Cache only matching workflow/document/job/fingerprint; omitted fields preserve evidence, explicit empty values replace it. Refresh open View details on execution completion.

        Text includes the same workflow_id, expected_revision and action_token controls as cards; retain them internally for natural-language replies. Poll the same workflow while poll=true until a choice/outcome; never restart after a timeout or narrate unchanged polls. Preparing is not Applied. blockingWorkflowId identifies earlier unresolved work; use its original choices, including manual typed Keep. Scripts use Keep/Save/Restore, not typed Undo. Restoration availability is display evidence and is validated again at use. Document edits during preparation require fresh preparation."""
        return result(lambda: service.edit_workflows.get(workflow_id, include_review=include_review))

    @mcp.tool(name="respond_edit_workflow", meta={"ui": {"visibility": ["model", "app"]}},
              annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False})
    def respond_edit_workflow(
        workflow_id: str, expected_revision: int, action_token: str,
        destination: str | None = None, approved_overwrites: list[dict[str, Any]] | None = None,
        automatic: bool = False,
    ) -> ToolResult:
        """Execute one offered action using workflow_id, expected_revision and action_token. Map conversational replies internally; users need not supply identifiers. Refresh get_edit_workflow before a later reply; use its matching revision/token. Retry the SAME token/arguments to reconcile, never substitute a new action after an uncertain outcome.

        In-scope edit authorization permits Apply or Run script without mandatory source inspection or a human click. Explicit previews wait for acceptance; write-only/review-only requests never authorize Run. Dimensions overwrites require explicit approval of every old/new value and exact approved_overwrites. Save choices require separate existing/explicit authorization for the whole document; Save As needs an absolute new destination shown to the user. Prerequisite Save does not authorize saving the result.

        Keep ends workflow recovery without saving and preserves native Undo. Typed Undo covers only recorded targets; Restore saved version reloads the whole font, discards later unsaved edits, clears Undo and returns a fresh binding. A clear restore request authorizes it. It never saves, reruns Python or restores external effects. Keep/Save ends the recovery offer.

        Map 'wait for my answer' immediately to wait_for_answer, disabling the countdown without cancelling the edit. automatic=true is reserved for the visible connected card's successful-result Keep; never auto Run, Save, Undo, Restore or settle failed/unknown/blocked results. Timeout evidence is not human approval. Cancellation stops remaining callbacks, not a currently running invocation. Client permission dialogs still apply."""
        return result(lambda: service.edit_workflows.respond(
            workflow_id, expected_revision, action_token, destination=destination,
            approved_overwrites=approved_overwrites, automatic=automatic))
