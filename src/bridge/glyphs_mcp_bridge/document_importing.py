"""Native external font import; never save, re-export or change import settings."""
import copy
from pathlib import Path

from glyphs_mcp_protocol import ProtocolError
from glyphs_mcp_protocol import document_importing as contract
from . import document_opening
from .context import value


def native(adapter, request, operation, error_type):
    existing = {adapter._native_identity(font): font for font in adapter._fonts()
                if document_opening.matches(value(font, "filepath", None), request["path"])}
    if len(existing) > 1:
        raise error_type("ambiguous_document", "More than one open document matches this import",
                         details={"documentIds": [adapter._id(font) for font in existing.values()]})
    if existing:
        font = next(iter(existing.values()))
    else:
        try:
            contract.validate_source(request["path"])
        except ProtocolError as exc:
            raise error_type(exc.code, exc.message) from exc
        operation["attempted"] = True
        font = adapter.glyphs.open(request["path"], showInterface=True)
        if font is None:
            raise error_type("importing_failed", "Glyphs could not import the requested font")
        # The native importer may return a pathless font rather than retain the
        # compiled source path. Bind the actual returned document, never current.
        adapter._font(adapter._id(font))
    compiled = Path(request["path"]).suffix.lower() in {".otf", ".ttf"}
    return {**adapter.document_state(adapter._id(font)),
            "familyName": str(value(font, "familyName", "Untitled") or "Untitled"),
            "alreadyOpen": bool(existing), "importId": request["importId"],
            "bridgeSessionId": request["bridgeSessionId"], "sourcePath": request["path"],
            "sourceFormat": Path(request["path"]).suffix.lower()[1:],
            "requiresSaveAs": True, "nativeSourceFormats": ["glyphs", "glyphspackage"],
            "viewOnlyUntilSaveAs": compiled,
            "warnings": (["Compiled font import can lose hinting and OpenType tables; re-export may differ from the original."]
                         if compiled else [])}


def import_document(core, value, error_type):
    try:
        request = contract.request(value)
    except ProtocolError as exc:
        raise error_type(exc.code, exc.message) from exc
    if core.paused:
        raise error_type("server_stopped", "the Glyphs MCP server is stopped")
    if request["bridgeSessionId"] != core.bridge_session_id:
        raise error_type("importing_outcome_unknown", "The bridge restarted; reconcile the original import before importing again")
    with core._lock:
        operation = core._imports.get(request["importId"])
        if operation is not None:
            if operation["request"] != request:
                raise error_type("importing_conflict", "The Import key belongs to another request")
        else:
            if not document_opening.available(core.adapter):
                raise error_type("unsupported_capability", "Native font import is unavailable")
            if len(core._imports) >= document_opening.MAX_OPENINGS:
                raise error_type("importing_limit_reached", "This bridge session reached its import limit")
            operation = {"request": request, "result": None, "error": None, "attempted": False}
            core._imports[request["importId"]] = operation
            try:
                operation["result"] = core.adapter.import_document(request, operation)
            except Exception as exc:
                operation["error"] = {"code": getattr(exc, "code", "importing_failed"),
                                      "message": str(exc) or type(exc).__name__,
                                      "details": {**getattr(exc, "details", {}), "importId": request["importId"],
                                                  "importingAttempted": operation["attempted"]}}
        if operation["error"]:
            error = operation["error"]
            raise error_type(error["code"], error["message"], details=error["details"])
        if operation["result"] is None:
            raise error_type("importing_in_progress", "The original Import is still running; retry with the same key")
        result = copy.deepcopy(operation["result"])
        result.update(core.adapter.document_state(result["id"]))
        result["familyName"] = str(value_of_font(core, result["id"]))
        result["requiresSaveAs"] = not result.get("path") or Path(result["path"]).suffix.lower() not in {".glyphs", ".glyphspackage"}
        result["viewOnlyUntilSaveAs"] = result["sourceFormat"] in {"otf", "ttf"} and result["requiresSaveAs"]
        return result


def value_of_font(core, document_id):
    return value(core.adapter._font(document_id), "familyName", "Untitled") or "Untitled"
