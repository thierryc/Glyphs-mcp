"""Journal Open requests before dispatch and retain keys across sidecar restarts."""
from __future__ import annotations

import fcntl
import json
import os

from glyphs_mcp_protocol import ProtocolError
from glyphs_mcp_protocol import document_opening as contract


def open_document(service, error_type, path, idempotency_key):
    try:
        options = contract.options(path, idempotency_key)
    except ProtocolError as exc:
        raise error_type(exc.code, exc.message) from exc
    root = service.jobs.root / "document-openings"
    root.mkdir(mode=0o700, exist_ok=True)
    record = root / (options["openId"] + ".json")
    with (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        status = service.bridge.status()
        if contract.CAPABILITY not in (status.get("writeCapabilities") or []):
            raise error_type("unsupported_capability", "Open requires document.open.v1; update bridge and sidecar together")
        session = status.get("bridgeSessionId")
        if not isinstance(session, str) or not session:
            raise error_type("unsupported_capability", "The bridge did not provide an opening session identity")
        request = {**options, "bridgeSessionId": session}
        if record.exists():
            try:
                retained = contract.request(json.loads(record.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError, ProtocolError) as exc:
                raise error_type("opening_outcome_unknown", "The original Open record is unreadable; reconcile before opening again") from exc
            if any(retained[key] != options[key] for key in options):
                raise error_type("opening_conflict", "The Open key belongs to another source path")
            if retained["bridgeSessionId"] != session:
                raise error_type("opening_outcome_unknown", "The bridge restarted; reconcile the original document before opening again",
                                 details={"openId": options["openId"]})
            request = retained
        else:
            try:
                contract.validate_source(options["path"])
            except ProtocolError as exc:
                raise error_type(exc.code, exc.message) from exc
            temporary = record.with_suffix(".tmp")
            with temporary.open("w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(request, stream, ensure_ascii=False, sort_keys=True)
                stream.flush(); os.fsync(stream.fileno())
            temporary.replace(record)
            descriptor = os.open(root, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return service.bridge.open_document(request)
