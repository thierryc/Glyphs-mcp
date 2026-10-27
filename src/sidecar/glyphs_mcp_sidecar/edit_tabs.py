"""Durably reserve Edit-tab intents without saving fonts or creating edit jobs."""
import fcntl
import json

from glyphs_mcp_protocol import ProtocolError
from glyphs_mcp_protocol import edit_tabs as contract
from .document_closing import guard, write


def open_edit_tab(service, error_type, document_id, idempotency_key, text=None, glyphs=None, master_id=None):
    try:
        options = contract.options(document_id, idempotency_key, text, glyphs, master_id)
    except ProtocolError as exc:
        raise error_type(exc.code, exc.message) from exc
    root = service.jobs.root / "edit-tab-openings"
    root.mkdir(mode=0o700, exist_ok=True)
    record = root / (options["tabOpenId"] + ".json")
    with (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        status = service.bridge.status()
        if contract.CAPABILITY not in (status.get("writeCapabilities") or []):
            raise error_type("unsupported_capability", "Open Edit tab requires document.edit-tab.open.v1; update bridge and sidecar together")
        session = status.get("bridgeSessionId")
        if not isinstance(session, str) or not session:
            raise error_type("unsupported_capability", "Open Edit tab requires a bridge session identity")
        request = {**options, "bridgeSessionId": session}
        if record.exists():
            try:
                retained = contract.request(json.loads(record.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError, ProtocolError) as exc:
                raise error_type("edit_tab_outcome_unknown", "The original Edit-tab record is unreadable; reconcile before retrying") from exc
            if any(retained[key] != options[key] for key in options):
                raise error_type("edit_tab_conflict", "The Edit-tab key belongs to another request")
            if retained["bridgeSessionId"] != session:
                raise error_type("edit_tab_outcome_unknown", "The bridge restarted; reconcile the original tab before opening again",
                                 details={"tabOpenId": options["tabOpenId"]})
            request = retained
        # Guard UI-context changes against pending native work, but never require Save.
        document = service._document(options["documentId"])
        try:
            guard(service, document, error_type)
        except error_type as exc:
            if exc.code == "document_busy":
                raise error_type(exc.code, exc.message, details=exc.details) from exc
            raise
        if not record.exists():
            write(record, request)
        return service.bridge.open_edit_tab(request)
