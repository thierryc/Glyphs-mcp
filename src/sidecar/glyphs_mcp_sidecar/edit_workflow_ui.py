"""Portable MCP Apps registration with first-class text tool results."""
from pathlib import Path
from typing import Any

from fastmcp import Context
from fastmcp.resources import TextResource
from fastmcp.tools.tool import ToolResult
from mcp.types import ReadResourceRequest, TextContent
from pydantic import Field
from .presentation import invocation_meta, workflow_call

RESOURCE_URI = "ui://glyphs-mcp/edit-workflow-v1.html"
RESOURCE_MIME = "text/html;profile=mcp-app"
UI_META = {"ui": {"resourceUri": RESOURCE_URI, "visibility": ["model", "app"]},
           "openai/outputTemplate": RESOURCE_URI}
DATA_META = {"ui": {"visibility": ["model", "app"]}}
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

    @mcp.tool(name="start_edit_workflow", title="Start Glyphs edit",
              meta=invocation_meta(DATA_META, "Preparing Glyphs edit request", "Glyphs request checked"),
              annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
    async def start_edit_workflow(
        document_id: str, kind: str, idempotency_key: str, mode: str = "apply",
        delta: float | None = None, glyphs: list[str] | None = None, options: dict[str, Any] | None = None,
        auto_keep: bool = True, ctx: Context = None,
    ) -> ToolResult:
        """Perform an authorized edit; reuse the connection/document_id and retain idempotency_key for retries. Typed kinds include width_delta, spacing, kerning_edit, kerning_collision, start_nodes, slant, outline_edit, dimensions_edit and closed native_action. mode=apply prepares and applies complete typed results; preview waits. Warnings/skipped targets and Dimensions overwrites retain report review. Compilation/export use start_job. Preparation never saves; typed jobs on dirty/new fonts require separately authorized Save/Save As/manual saving. Native scripts run without Save on dirty/pathless fonts. Reuse existing save authorization; prerequisite saving does not authorize saving the result.

        With edit.queue.automatic.v1, busy Glyphs accepts the request as Waiting and returns its workflow_id immediately. The supervisor resumes it when its resource is available; reuse the same workflow/key instead of submitting again. queue.automaticResume=true needs no user decision. Same-font decisions retain their owning workflow and exact blocker; unrelated recovery stays open. Preview resumes preparation only. A service restart interrupts queued requests for review; uncertain native writes are never replayed. Cancel removes a waiting request without resolving its owner.

        kerning_edit requires kerning.edit.exact.v1. options.edits holds 1-100 exact entries: op=set|remove, master, direction=LTR|RTL|vertical and left/right side objects {kind:glyph,name:...} or {kind:group,key:...}; set alone has finite value (zero is stored, remove deletes). Preparation is native and read-only; guarded application and selective Undo retain Keep/Save. No collision analysis.

        python_script requires script.native.v1, script.recovery.snapshot.v1 and preparation version 3. Run captures a detached copy of the current font, including unsaved edits, without saving. Options: exact source, JSON params, entrypoint=per_target|script, targets and optional summary (500 characters). Callback run(layer,params,context); whole scripts may use targets:[]. Targets: explicit {glyph,layer,surface} entries or {master:exactId,glyphs:all|names,surface}; IDs identify owning foregrounds. No fixed script target-count ceiling; complete request limit 4 MiB, never truncate. Typed/read limits remain. Retired executionMode/recovery are rejected. Preparation validates syntax/targets without executing Python. For an in-scope edit request, dispatch the offered Run action under original authorization without mandatory source review, human click or another question. Write-only/review-only requests never authorize execution; writing includes code review. Explicit previews wait. Show the script warning once; exact source stays optional View details.

        Results offer Keep changes without saving, Save and selective typed Undo or whole-font script Restore before run. Script recovery is session-local and ends on Keep or verified Save; scripts do not promise native Undo/Redo. Typed Keep preserves native Undo/Redo. auto_keep=true lets a visible connected successful card Keep after 30 seconds. Set false for 'wait for my answer', disabled automatic feedback or inspection before deciding; honor that directive until changed. Existing workflows use wait_for_answer. Text-only clients remain manual.

        checkpoint_restore loads the selected whole-font version under a clear restore request: replaces later unsaved edits, clears Undo and returns a fresh binding without saving. Opt-in Git checkpoint failure is separate from Save success. Retain workflow_id; poll until a choice/outcome. Missing cards never block authorized work.

        Use native chat interaction first. This data tool does not open a card. Ask an unresolved decision with the host's available native question tool, otherwise ordinary chat. Never add another approval for an authorized action. Pause Automatic Keep with wait_for_answer before waiting on a native answer. Use show_edit_workflow only when a visual preview, substantial report, useful live progress/cancellation or recovery controls add value, or the user requests a card. Routine starts, polling and simple success need no card."""
        return await workflow_call(lambda: result(lambda: service.edit_workflows.start(
            document_id, kind=kind, idempotency_key=idempotency_key, mode=mode,
            delta=delta, glyphs=glyphs, options=options, auto_keep=auto_keep)), ctx, "Preparing Glyphs edit request")

    @mcp.tool(name="get_edit_workflow", title="Check Glyphs edit progress",
              meta=invocation_meta(DATA_META, "Checking Glyphs workflow", "Glyphs workflow status checked"),
              annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
    async def get_edit_workflow(workflow_id: str, include_review: bool = False, ctx: Context = None) -> ToolResult:
        """Read compact state, request fingerprint, revision, actions and progress. Ordinary polling needs no health/job reads. A read never executes Python, saves or applies edits. Use include_review=true for Show script or requested source/output details. Card-only uiRefreshIntervalMs keeps visible pending choices current without extending agent polling. Optional action presentation groups main/menu/countdown controls. On stale_workflow_action, read this same workflow; never replay the rejected mutation automatically. Cache only matching workflow/document/job/fingerprint; omitted fields preserve evidence, explicit empty values replace it. Refresh open View details on execution completion.

        Text includes the same workflow_id, expected_revision and action_token controls as cards; retain them internally for natural-language replies. Result buttons use Keep, Save and script Restore; optional action tooltip and actionSupportText explain their consequences and confirmed outcomes. Keep means keep without saving; Save saves the whole font. Existing longer conversational phrases remain valid. Poll the same workflow while poll=true until a choice/outcome; never restart after a timeout or narrate unchanged polls. Waiting with queue.automaticResume=true is accepted work that the supervisor will resume; explain this without asking to close recovery. Preparing is not Applied. blockingWorkflowId and blocker explain the owning task, resource scope, reason and whether waiting is automatic or needs a decision. With tasks.document-recovery.v1, stopped recovery protects its own document; independent fonts can continue. Refresh an obsolete blocker through its existing lifecycle rather than resolving unrelated work. Use the original choices for a genuine conflict, including manual typed Keep. Scripts use Keep/Save/Restore, not typed Undo. Restoration availability is display evidence and is validated again at use. Document edits during preparation require fresh preparation. This data read never opens another card; use native questions/chat for unresolved decisions, and show_edit_workflow only when the card adds useful information or controls."""
        return await workflow_call(lambda: result(lambda: service.edit_workflows.get(workflow_id, include_review=include_review)),
                                   ctx, "Checking Glyphs workflow")

    @mcp.tool(name="show_edit_workflow", title="Show Glyphs edit progress",
              meta=invocation_meta(UI_META, "Opening Glyphs workflow", "Glyphs workflow status available"),
              annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
    async def show_edit_workflow(workflow_id: str, include_review: bool = False, ctx: Context = None) -> ToolResult:
        """Open one optional MCP App card for an existing workflow, without applying, saving or starting work. Use only for a visual before/after preview, substantial review/evidence, meaningful live progress/cancellation, useful recovery controls, or an explicit request to see a card. Prefer native chat questions and ordinary text for simple decisions and outcomes; routine starts, polling, empty results and simple success need no card. Reuse the existing card as it refreshes rather than opening one for every stage. Unsupported hosts receive the same text and offered actions. Script/source details remain opt-in via include_review=true."""
        return await workflow_call(lambda: result(lambda: service.edit_workflows.get(workflow_id, include_review=include_review)),
                                   ctx, "Opening Glyphs workflow")

    @mcp.tool(name="respond_edit_workflow", title="Respond to Glyphs edit",
              meta=invocation_meta(DATA_META, "Processing Glyphs workflow choice", "Glyphs workflow choice checked"),
              annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False})
    async def respond_edit_workflow(
        workflow_id: str, expected_revision: int, action_token: str,
        destination: str | None = None, approved_overwrites: list[dict[str, Any]] | None = None,
        automatic: bool = False, ctx: Context = None,
    ) -> ToolResult:
        """Execute one offered action using workflow_id, expected_revision and action_token. Map conversational replies internally; users need not supply identifiers. Refresh get_edit_workflow before a later reply; use its matching revision/token. Retry the SAME token/arguments to reconcile, never substitute a new action after an uncertain outcome.

        In-scope edit authorization permits Apply or Run script without mandatory source inspection or a human click. Explicit previews wait for acceptance; write-only/review-only requests never authorize Run. Dimensions overwrites require explicit approval of every old/new value and exact approved_overwrites. Save choices require separate existing/explicit authorization for the whole document; Save As needs an absolute new destination shown to the user. Prerequisite Save does not authorize saving the result.

        Keep ends workflow recovery without saving; typed edits preserve native Undo. Typed Undo covers only recorded targets; Restore before run restores the whole pre-run font, including pre-existing unsaved edits, discards later edits, clears Undo and returns a fresh binding. This memory recovery is unavailable after Glyphs restarts. A clear restore request authorizes it. It never saves, reruns Python or restores external effects. Keep/Save ends the recovery offer.

        Map 'wait for my answer' immediately to wait_for_answer, disabling the countdown without cancelling the edit. automatic=true is reserved for the visible connected card's successful-result Keep; never auto Run, Save, Undo, Restore or settle failed/unknown/blocked results. Timeout evidence is not human approval. Cancellation stops remaining callbacks, not a currently running invocation. Client permission dialogs still apply."""
        return await workflow_call(lambda: result(lambda: service.edit_workflows.respond(
            workflow_id, expected_revision, action_token, destination=destination,
            approved_overwrites=approved_overwrites, automatic=automatic)), ctx, "Processing Glyphs workflow choice")
