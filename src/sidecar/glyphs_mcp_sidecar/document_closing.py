"""Durable Save-and-Close intent; retries never save or discard newer edits."""
import fcntl
import json
import os
from pathlib import Path

from glyphs_mcp_protocol import ProtocolError
from glyphs_mcp_protocol import document_closing as contract
from .jobs import JobStore
from .saved_script import unresolved
from .source import SourceError, font_source_hash
from . import saving


def write(record, value):
    temporary = record.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        stream.flush(); os.fsync(stream.fileno())
    temporary.replace(record)
    descriptor = os.open(record.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def guard(service, document, error_type, *, ignore_job_id=None):
    # Fresh disk records also cover preparation owned by another sidecar process.
    for job in JobStore(service.jobs.root).records():
        if job["id"] == ignore_job_id:
            continue
        owner = job["document"]
        same = (owner.get("id") == document["id"] or
                (owner.get("path") and document.get("path") and
                 saving._same_path(Path(owner["path"]), Path(document["path"]))))
        if unresolved(job) or (same and job["status"] in contract.OWNING_STATUSES):
            raise error_type("document_busy", "Resolve the pending MCP job before closing this font",
                             details={"jobId": job["id"], "status": job["status"]})


def close_document(service, error_type, document_id, idempotency_key, unsaved_changes="refuse", destination=None):
    try:
        options = contract.options(document_id, idempotency_key, unsaved_changes, destination)
    except ProtocolError as exc:
        raise error_type(exc.code, exc.message) from exc
    root = service.jobs.root / "document-closings"
    root.mkdir(mode=0o700, exist_ok=True)
    record = root / (options["closeId"] + ".json")
    with service._lock, (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        status = service.bridge.status()
        if contract.CAPABILITY not in (status.get("writeCapabilities") or []):
            raise error_type("unsupported_capability", "Close requires document.close.v1; update bridge and sidecar together")
        session = status.get("bridgeSessionId")
        if not isinstance(session, str) or not session:
            raise error_type("unsupported_capability", "Close requires a bridge session identity")
        if record.exists():
            try:
                retained = json.loads(record.read_text(encoding="utf-8"))
                if not isinstance(retained, dict) or not isinstance(retained.get("options"), dict):
                    raise ValueError("invalid closing record")
                if (not isinstance(retained.get("initialState"), dict)
                        or set(retained["initialState"]) != {"path", "dirty", "generation"}):
                    raise ValueError("invalid closing state")
                if retained.get("closeRequest") is not None:
                    contract.request(retained["closeRequest"])
            except (OSError, ValueError, TypeError, ProtocolError) as exc:
                raise error_type("closing_outcome_unknown", "The original Close record is unreadable; reconcile before retrying") from exc
            if retained["options"] != options:
                raise error_type("closing_conflict", "The Close key belongs to another document or save/discard choice")
            if retained.get("bridgeSessionId") != session:
                raise error_type("closing_outcome_unknown", "The bridge restarted; reconcile the original Close before retrying")
        else:
            document = service._document(options["documentId"])
            guard(service, document, error_type)
            if document.get("dirty") is not False and unsaved_changes == "refuse":
                raise error_type("unsaved_changes_required", "This font has unsaved or unknown changes; choose Save, Discard or Cancel",
                                 details={"documentId": document["id"], "dirty": document.get("dirty")})
            retained = {"options": options, "bridgeSessionId": session,
                        "initialState": {key: document.get(key) for key in ("path", "dirty", "generation")}}
            write(record, retained)
        if retained.get("closeRequest") is None:
            document = service._document(options["documentId"])
            checkpoint_id = (retained.get("saveRequest") or {}).get("checkpointJobId")
            guard(service, document, error_type, ignore_job_id=checkpoint_id)
            if unsaved_changes == "save":
                if not retained.get("saveRequest"):
                    if any(document.get(k) != v for k, v in retained["initialState"].items()):
                        raise error_type("stale_document", "The font changed after Close was prepared; review it before a new request")
                    def prepared(request):
                        request["reviewedGeneration"] = retained["initialState"]["generation"]
                        retained["saveRequest"] = dict(request)
                        write(record, retained)
                    receipt = service.save_document(document["id"], destination=options["destination"], _on_prepared=prepared)
                    retained["receipt"] = receipt
                    write(record, retained)
                request = retained["saveRequest"]
                # Reconcile the original Save only. A missing outcome never
                # authorizes a second Save, especially after later manual edits.
                operation = service.bridge.save_operation(request["saveId"])
                if operation.get("status") != "saved":
                    raise error_type("closing_save_unverified", "The original Save is unverified; the font remains open",
                                     details={"saveId": request["saveId"]})
                if not retained.get("receipt"):
                    try:
                        receipt = saving.verify_save(request, operation.get("native") or {})
                    except saving.SaveError as exc:
                        raise saving.service_error(exc, error_type) from exc
                    if checkpoint_id:
                        from .checkpoints import after_save
                        receipt = after_save(service, service.jobs.get(checkpoint_id), receipt)
                        service.jobs.update(checkpoint_id, status="accepted", receipt=receipt)
                    retained["receipt"] = receipt
                    write(record, retained)
                receipt = retained["receipt"]
                if checkpoint_id and (receipt.get("checkpoint") or {}).get("status") == "failed":
                    # The user may already have retried the existing checkpoint.
                    # Adopt that verified receipt without resaving or retrying Git.
                    job = service.jobs.get(checkpoint_id)
                    refreshed = job.get("receipt") or {}
                    if job["status"] == "accepted" and refreshed.get("saveId") == request["saveId"]:
                        receipt = retained["receipt"] = refreshed
                        write(record, retained)
                if (receipt.get("checkpoint") or {}).get("status") == "failed":
                    raise error_type("closing_checkpoint_failed", "The font was saved but its checkpoint failed; it remains open",
                                     details={"receipt": receipt})
                native = operation.get("native") or {}
                state = {"path": native.get("path"), "dirty": native.get("dirty"), "generation": native.get("generation")}
            else:
                state = retained["initialState"]
            retained["closeRequest"] = {"closeId": options["closeId"], "documentId": options["documentId"],
                                        "bridgeSessionId": session, "state": state,
                                        "discard": unsaved_changes == "discard"}
            write(record, retained)
        # A lost Close response uses the exact persisted state and key. Bridge
        # replay returns its outcome even though the native font is now closed.
        for document in service.list_documents():
            if document["id"] == options["documentId"]:
                guard(service, document, error_type,
                      ignore_job_id=(retained.get("saveRequest") or {}).get("checkpointJobId"))
                if retained.get("receipt"):
                    try:
                        receipt = retained["receipt"]
                        unchanged = font_source_hash(Path(receipt["path"])) == receipt["sourceHashAfter"]
                    except (OSError, SourceError) as exc:
                        raise error_type("closing_save_unverified", "The saved source is unavailable; the font remains open") from exc
                    if not unchanged:
                        raise error_type("closing_save_unverified", "The saved file changed after Save-and-Close was prepared; the font remains open")
        result = service.bridge.close_document(retained["closeRequest"])
        return {**result, **({"saveReceipt": retained["receipt"]} if retained.get("receipt") else {})}
