"""Durable creation keys across sidecar restarts; never replay across bridge sessions."""
from __future__ import annotations

import fcntl
import json
import os
from glyphs_mcp_protocol import ProtocolError
from glyphs_mcp_protocol import document_creation as contract


def create(service, error_type, family_name, idempotency_key, units_per_em):
    try:
        options = contract.options(family_name, idempotency_key, units_per_em)
    except ProtocolError as exc:
        raise error_type(exc.code, exc.message) from exc
    root = service.jobs.root / "document-creations"
    root.mkdir(mode=0o700, exist_ok=True)
    path = root / (options["creationId"] + ".json")
    # Shared by HTTP/stdio services using the same jobs root.
    with (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        status = service.bridge.status()
        if contract.CAPABILITY not in (status.get("writeCapabilities") or []):
            raise error_type("unsupported_capability", "Font creation requires document.create.v1; update bridge and sidecar together")
        session = status.get("bridgeSessionId")
        if not isinstance(session, str) or not session:
            raise error_type("unsupported_capability", "The bridge did not provide a creation session identity")
        request = {**options, "bridgeSessionId": session}
        if path.exists():
            try:
                retained = contract.request(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError) as exc:
                raise error_type("creation_outcome_unknown", "The original creation record is unreadable; do not repeat creation") from exc
            if any(retained[key] != options[key] for key in options):
                raise error_type("creation_conflict", "The creation key belongs to another request")
            if retained["bridgeSessionId"] != session:
                raise error_type("creation_outcome_unknown", "The bridge restarted; reconcile the original font before creating another",
                                 details={"creationId": options["creationId"]})
            request = retained
        else:
            temporary = path.with_suffix(".tmp")
            with temporary.open("w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(request, stream, ensure_ascii=False, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
            descriptor = os.open(root, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        # Same request is safe even after a lost response: the bridge retains the result.
        return service.bridge.create_document(request)
