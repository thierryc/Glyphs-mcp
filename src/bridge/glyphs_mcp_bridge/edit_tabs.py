"""Main-thread native Edit tabs with retained attempts and exact document scope."""
import copy
from uuid import uuid4

from glyphs_mcp_protocol import ProtocolError
from glyphs_mcp_protocol import edit_tabs as contract
from .context import value
from .document_lifecycle import guard

MAX_OPENINGS = 1024


def available():
    try:
        from GlyphsApp import Glyphs, GSFont
        # The plugin-free/headless runtime exports GSFont.newTab but cannot show
        # documents. Do not advertise an editor action solely from that method.
        return (callable(getattr(Glyphs, "documentController", None))
                and all(callable(getattr(GSFont, name, None)) for name in ("newTab", "show")))
    except ImportError:
        return False


def public(core, operation, error_type):
    if operation["error"] is not None:
        error = operation["error"]
        raise error_type(error["code"], error["message"], details=error["details"])
    font = core.adapter._font(operation["request"]["documentId"])
    if operation["tab"] not in list(font.tabs):
        raise error_type("edit_tab_closed", "The original Edit tab was closed; a retry will not recreate it",
                         details={"tabId": operation["result"]["tabId"]})
    return {**copy.deepcopy(operation["result"]), **core.adapter.document_state(operation["request"]["documentId"])}


def open_edit_tab(core, supplied, error_type):
    try:
        request = contract.request(supplied)
    except ProtocolError as exc:
        raise error_type(exc.code, exc.message) from exc
    if core.paused:
        raise error_type("server_stopped", "the Glyphs MCP server is stopped")
    if request["bridgeSessionId"] != core.bridge_session_id:
        raise error_type("edit_tab_outcome_unknown", "The bridge restarted; reconcile the original tab before retrying")
    with core._lock:
        try:
            guard(core, request["documentId"], error_type)
        except error_type as exc:
            if exc.code == "document_busy":
                raise error_type(exc.code, "Resolve the pending MCP job before opening an Edit tab", details=exc.details) from exc
            raise
        previous = core._tab_openings.get(request["tabOpenId"])
        if previous is not None:
            if previous["request"] != request:
                raise error_type("edit_tab_conflict", "The Edit-tab key belongs to another request")
            return public(core, previous, error_type)
        if not available():
            raise error_type("unsupported_capability", "Native Edit-tab opening is unavailable")
        if len(core._tab_openings) >= MAX_OPENINGS:
            raise error_type("edit_tab_limit_reached", "This bridge session reached its Edit-tab opening limit")
        font = core.adapter._font(request["documentId"])
        masters = list(font.masters)
        master_id = request["masterId"]
        if master_id is None:
            master_id = value(value(font, "selectedFontMaster"), "id")
        indices = [i for i, master in enumerate(masters) if value(master, "id") == master_id]
        if len(indices) != 1:
            raise error_type("target_not_found", "The requested or current master cannot be resolved",
                             details={"masterId": master_id})
        content = request["text"] if request["text"] is not None else ""
        if request["glyphs"] is not None:
            content = []
            for name in request["glyphs"]:
                try:
                    glyph = font.glyphs[name]
                    layer = glyph.layers[master_id] if glyph is not None else None
                except LookupError:
                    layer = None
                if layer is None:
                    raise error_type("target_not_found", "An exact glyph/master layer is missing",
                                     details={"glyph": name, "masterId": master_id})
                content.append(layer)
        # Reserve before any UI call. Even a callback failure after attachment must not replay.
        before = list(font.tabs)
        tab_id = "edit_tab_" + uuid4().hex
        operation = {"request": request, "result": None, "error": None, "tab": None}
        core._tab_openings[request["tabOpenId"]] = operation
        attempted = False
        try:
            font.show()
            attempted = True
            tab = font.newTab(content)
            operation["tab"] = tab
            if tab is None or tab not in list(font.tabs) or tab in before:
                raise RuntimeError("Native tab creation did not return an attached new Edit tab")
            tab.masterIndex = indices[0]
            font.currentTab = tab
            from AppKit import NSApplication
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            if font.currentTab != tab or tab.masterIndex != indices[0]:
                raise RuntimeError("Native tab activation or master selection could not be verified")
            operation["result"] = {"documentId": request["documentId"], "tabId": tab_id,
                                   "tabOpenId": request["tabOpenId"], "bridgeSessionId": core.bridge_session_id,
                                   "masterId": master_id, "created": True, "activationRequested": True}
        except Exception as exc:
            attached = []
            if attempted:
                try:
                    attached = [tab for tab in font.tabs if tab not in before]
                    if len(attached) == 1:
                        operation["tab"] = attached[0]
                except Exception:
                    pass
            operation["error"] = {"code": "edit_tab_outcome_unknown" if attempted else "edit_tab_open_failed",
                                  "message": "Glyphs could not complete Edit-tab opening; inspect the original outcome before a new request",
                                  "details": {"documentId": request["documentId"], "tabOpenId": request["tabOpenId"],
                                              "tabId": tab_id if operation["tab"] is not None else None,
                                              "openingAttempted": attempted, "nativeError": str(exc)}}
        return public(core, operation, error_type)
