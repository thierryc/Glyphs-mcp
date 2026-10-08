"""Exact native document targeting, state guards and retained Close outcomes."""
import copy

from glyphs_mcp_protocol import ProtocolError
from glyphs_mcp_protocol import document_closing as contract
from glyphs_mcp_protocol.document_creation import text


def available(action):
    try:
        from GlyphsApp import GSFont
        return callable(getattr(GSFont, action, None))
    except ImportError:
        return False


def guard(core, document_id, error_type):
    core._check_owner(document_id)
    for item in core._operations.values():
        if item.get("documentId") == document_id and item["status"] in contract.OWNING_STATUSES:
            raise error_type("document_busy", "Resolve the document's pending MCP job before closing",
                             details={"jobId": item["jobId"], "status": item["status"]})


def activate(core, document_id, error_type):
    try:
        document_id = text(document_id, "document_id")
    except ProtocolError as exc:
        raise error_type(exc.code, exc.message) from exc
    if core.paused:
        raise error_type("server_stopped", "the Glyphs MCP server is stopped")
    if not available("show"):
        raise error_type("unsupported_capability", "Native document activation is unavailable")
    with core._lock:
        # Show can add a detached font. Resolve a live ID first to prevent that.
        font = core.adapter._font(document_id)
        try:
            font.show()
            from AppKit import NSApplication
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            document = next(item for item in core.adapter.list_documents() if item["id"] == document_id)
        except Exception as exc:
            raise error_type("activation_failed", "Glyphs could not activate the requested font window",
                             details={"documentId": document_id, "nativeError": str(exc)}) from exc
        return {**document, "windowShown": True, "activationRequested": True}


def close(core, value, error_type):
    try:
        request = contract.request(value)
    except ProtocolError as exc:
        raise error_type(exc.code, exc.message) from exc
    if core.paused:
        raise error_type("server_stopped", "the Glyphs MCP server is stopped")
    if request["bridgeSessionId"] != core.bridge_session_id:
        raise error_type("closing_outcome_unknown", "The bridge restarted; reconcile the original Close before retrying")
    with core._lock:
        operation = core._closes.get(request["closeId"])
        if operation is not None:
            if operation["request"] != request:
                raise error_type("closing_conflict", "The Close key belongs to another request")
            if operation.get("result"):
                return copy.deepcopy(operation["result"])
            # Observe a possibly asynchronous native close, but never repeat it.
            if not any(d["id"] == request["documentId"] for d in core.adapter.list_documents()):
                operation["result"] = result(request)
                return copy.deepcopy(operation["result"])
            raise error_type("closing_outcome_unknown", "The original Close did not remove the font; inspect it before a new request",
                             details={"closeId": request["closeId"], "documentId": request["documentId"]})
        if not available("close"):
            raise error_type("unsupported_capability", "Native document closing is unavailable")
        if len(core._closes) >= 1024:
            raise error_type("closing_limit_reached", "This bridge session reached its closing limit")
        guard(core, request["documentId"], error_type)
        state = core.adapter.document_state(request["documentId"])
        if any(state.get(key) != expected for key, expected in request["state"].items()):
            raise error_type("stale_document", "The font changed after Close was prepared; review it before a new request")
        if state.get("dirty") is not False and not request["discard"]:
            raise error_type("unsaved_changes_required", "Choose Save or Discard before closing unsaved work")
        font = core.adapter._font(request["documentId"])
        operation = {"request": request, "result": None}
        core._closes[request["closeId"]] = operation
        try:
            # Save was verified by the sidecar, or discard was explicitly chosen.
            # Never invoke Glyphs' modal close confirmation from a tool call.
            font.close(ignoreChanges=True)
        except Exception as exc:
            if any(d["id"] == request["documentId"] for d in core.adapter.list_documents()):
                raise error_type("closing_outcome_unknown", "The native Close failed; inspect the original font before a new request",
                                 details={"closeId": request["closeId"], "nativeError": str(exc)}) from exc
        if any(d["id"] == request["documentId"] for d in core.adapter.list_documents()):
            raise error_type("closing_outcome_unknown", "Glyphs has not removed the requested document; retry the same key to observe it",
                             details={"closeId": request["closeId"]})
        operation["result"] = result(request)
        return copy.deepcopy(operation["result"])


def result(request):
    return {"id": request["documentId"], "path": request["state"]["path"], "closed": True,
            "discardedUnsavedChanges": request["discard"] and request["state"]["dirty"] is not False,
            "closeId": request["closeId"], "bridgeSessionId": request["bridgeSessionId"]}
