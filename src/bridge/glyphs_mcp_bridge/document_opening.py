"""Open native sources on the main thread without reloading existing fonts."""
from __future__ import annotations

import copy
from pathlib import Path

from glyphs_mcp_protocol import ProtocolError
from glyphs_mcp_protocol import document_opening as contract

MAX_OPENINGS = 1024


def available(adapter):
    return callable(getattr(getattr(adapter, "glyphs", None), "open", None))


def matches(path, expected):
    if not path:
        return False
    try:
        return Path(path).resolve() == Path(expected) or Path(path).samefile(expected)
    except (OSError, ValueError, RuntimeError):
        return False


def native(adapter, request, operation, error_type):
    from .context import value

    existing = {adapter._native_identity(font): font for font in adapter._fonts()
                if matches(value(font, "filepath", None), request["path"])}
    if len(existing) > 1:
        raise error_type("ambiguous_document", "More than one open document matches this source; choose the intended document",
                         details={"documentIds": [adapter._id(font) for font in existing.values()]})
    if existing:
        return result(adapter, next(iter(existing.values())), request, already_open=True)
    try:
        contract.validate_source(request["path"])
    except ProtocolError as exc:
        raise error_type(exc.code, exc.message) from exc
    operation["attempted"] = True
    font = adapter.glyphs.open(request["path"], showInterface=True)
    if font is None:
        raise error_type("opening_failed", "Glyphs could not open the requested source")
    operation["font"] = font
    document_id = adapter._id(font)
    if adapter._native_identity(adapter._font(document_id)) != adapter._native_identity(font):
        raise error_type("opening_failed", "The opened font did not become a live Glyphs document")
    if not matches(value(font, "filepath", None), request["path"]):
        raise error_type("opening_failed", "Glyphs returned a document for a different source")
    return result(adapter, font, request, already_open=False)


def result(adapter, font, request, *, already_open):
    from .context import value
    return {**adapter.document_state(adapter._id(font)),
            "familyName": str(value(font, "familyName", "Untitled") or "Untitled"),
            "alreadyOpen": already_open, "openId": request["openId"],
            "bridgeSessionId": request["bridgeSessionId"]}


def public(core, operation, error_type):
    if operation["result"] is None and operation["error"] is None:
        raise error_type("opening_in_progress", "The original Open is still running; retry with the same key")
    if operation["error"]:
        error = operation["error"]
        raise error_type(error["code"], error["message"], details=error["details"])
    value = copy.deepcopy(operation["result"])
    value.update(core.adapter.document_state(value["id"]))
    from .context import value as native_value
    value["familyName"] = str(native_value(core.adapter._font(value["id"]), "familyName", "Untitled") or "Untitled")
    return value


def open_document(core, value, error_type):
    try:
        request = contract.request(value)
    except ProtocolError as exc:
        raise error_type(exc.code, exc.message) from exc
    if core.paused:
        raise error_type("server_stopped", "the Glyphs MCP server is stopped")
    if request["bridgeSessionId"] != core.bridge_session_id:
        raise error_type("opening_outcome_unknown", "The bridge restarted; reconcile the original document before opening again")
    with core._lock:
        previous = core._openings.get(request["openId"])
        if previous is not None:
            if previous["request"] != request:
                raise error_type("opening_conflict", "The Open key belongs to another request")
            return public(core, previous, error_type)
        if not available(core.adapter):
            raise error_type("unsupported_capability", "Native document opening is unavailable")
        if len(core._openings) >= MAX_OPENINGS:
            raise error_type("opening_limit_reached", "This bridge session reached its document opening limit")
        operation = {"request": request, "result": None, "error": None, "font": None, "attempted": False}
        core._openings[request["openId"]] = operation
        try:
            operation["result"] = core.adapter.open_document(request, operation)
        except Exception as exc:
            details = {**getattr(exc, "details", {}), "openId": request["openId"],
                       "openingAttempted": operation["attempted"]}
            # A native call can attach its document and then fail. Discover
            # only the exact requested path; never substitute the current font.
            try:
                for font in core.adapter._fonts() if operation["attempted"] else []:
                    from .context import value as native_value
                    if matches(native_value(font, "filepath", None), request["path"]):
                        details["documentId"] = core.adapter._id(font)
                        break
            except Exception:
                pass
            operation["error"] = {"code": getattr(exc, "code", "opening_failed"),
                                  "message": str(exc) or type(exc).__name__, "details": details}
        finally:
            operation["font"] = None
        return public(core, operation, error_type)
