"""Create one native font, retaining outcomes for retry reconciliation."""
from __future__ import annotations

import copy
from glyphs_mcp_protocol import ProtocolError
from glyphs_mcp_protocol import document_creation as contract

MAX_CREATIONS = 1024  # Never evict a key and accidentally allow a duplicate.


def available():
    try:
        from GlyphsApp import GSFont, GSFontMaster, GSInstance
        return all(callable(item) for item in (GSFont, GSFontMaster, GSInstance))
    except ImportError:
        return False


def construct(request, operation, error_type):
    """Configure only the detached new font before attaching its native document."""
    from GlyphsApp import GSFont, GSFontMaster, GSInstance
    font = GSFont()
    operation["font"] = font
    font.familyName = request["familyName"]
    font.upm = request["unitsPerEm"]
    font.glyphs = []
    # Constructor defaults vary by host. Normalize only this detached new font.
    font.masters = [GSFontMaster()]
    font.masters[0].name = "Regular"
    font.instances = [GSInstance()]
    font.instances[0].name = "Regular"
    font.instances[0].axes = list(font.masters[0].axes)
    from .context import value
    master_ids = [value(font.masters[0], "id", None)]
    instance_ids = [value(font.instances[0], "id", None)]
    if not all(isinstance(identity, str) and identity for identity in master_ids + instance_ids):
        raise error_type("creation_failed", "Native master or instance identity unavailable")
    return font, master_ids, instance_ids


def native(adapter, request, operation, error_type):
    font, master_ids, instance_ids = construct(request, operation, error_type)
    font.show()
    document_id = adapter._id(font)
    if adapter._native_identity(adapter._font(document_id)) != adapter._native_identity(font):
        raise error_type("creation_failed", "The new font did not become an open Glyphs document")
    state = adapter.document_state(document_id)
    if state["path"] is not None or state["dirty"] not in (True, False):
        raise error_type("creation_failed", "The new font has no verifiable unsaved document state")
    return {**state, "familyName": str(font.familyName), "unitsPerEm": int(font.upm),
            "masterIds": master_ids, "instanceIds": instance_ids,
            "creationId": request["creationId"], "bridgeSessionId": request["bridgeSessionId"]}


def public(core, operation, error_type):
    if operation["result"] is None and operation["error"] is None:
        raise error_type("creation_in_progress", "The original font creation is still running; retry with the same key")
    if operation["error"]:
        error = operation["error"]
        raise error_type(error["code"], error["message"], details=error["details"])
    result = copy.deepcopy(operation["result"])
    # A closed font must never be recreated by a retry; return fresh state for a live font.
    result.update(core.adapter.document_state(result["id"]))
    return result


def create(core, value, error_type):
    try:
        request = contract.request(value)
    except ProtocolError as exc:
        raise error_type(exc.code, exc.message) from exc
    if request["bridgeSessionId"] != core.bridge_session_id:
        raise error_type("creation_outcome_unknown", "The bridge restarted; reconcile the original font before creating another")
    with core._lock:
        previous = core._creations.get(request["creationId"])
        if previous is not None:
            if previous["request"] != request:
                raise error_type("creation_conflict", "The creation key belongs to another request")
            return public(core, previous, error_type)
        if len(core._creations) >= MAX_CREATIONS:
            raise error_type("creation_limit_reached", "This bridge session reached its font creation limit")
        operation = {"request": request, "result": None, "error": None, "font": None}
        core._creations[request["creationId"]] = operation
        try:
            operation["result"] = core.adapter.create_document(request, operation)
        except Exception as exc:
            details = {"creationId": request["creationId"], "creationAttempted": True}
            font = operation["font"]
            if font is not None:
                try:
                    if any(core.adapter._native_identity(item) == core.adapter._native_identity(font)
                           for item in core.adapter._fonts()):
                        details["documentId"] = core.adapter._id(font)
                except Exception:
                    pass
            operation["error"] = {"code": "creation_failed",
                                  "message": str(exc) or type(exc).__name__, "details": details}
        finally:
            # Keep the outcome, not a whole closed font. Live bindings own native retention.
            operation["font"] = None
        return public(core, operation, error_type)
