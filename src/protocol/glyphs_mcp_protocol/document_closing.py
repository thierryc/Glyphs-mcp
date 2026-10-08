"""Close a reviewed document state, with no implicit save or discard."""
import hashlib
from collections.abc import Mapping
from pathlib import Path

from .document_creation import text
from .models import ProtocolError

CAPABILITY = "document.close.v1"
ACTIVATE_CAPABILITY = "document.activate.v1"
# Ready and applied work owns its document until the existing lifecycle resolves it.
OWNING_STATUSES = frozenset({"preparing", "ready", "cancelling", "applying", "applied",
                           "accepting", "accept_uncertain", "discarding", "discard_uncertain",
                           "interrupted", "saved", "saving", "rolling_back"})


def options(document_id, idempotency_key, unsaved_changes, destination):
    if not isinstance(unsaved_changes, str) or unsaved_changes not in {"refuse", "save", "discard"}:
        raise ProtocolError("invalid_request", "unsaved_changes must be refuse, save or discard")
    if destination is not None and unsaved_changes != "save":
        raise ProtocolError("invalid_request", "destination is only valid with save")
    if destination is not None:
        if (not isinstance(destination, str) or not 1 <= len(destination) <= 4096
                or not Path(destination).is_absolute()
                or any(ord(c) < 32 or ord(c) == 127 for c in destination)):
            raise ProtocolError("invalid_request", "destination must be an absolute local path")
        destination = str(Path(destination).resolve())
    key = text(idempotency_key, "idempotency_key")
    return {"closeId": "close_" + hashlib.sha256(key.encode()).hexdigest(),
            "documentId": text(document_id, "document_id"),
            "unsavedChanges": unsaved_changes, "destination": destination}


def request(value):
    fields = {"closeId", "documentId", "bridgeSessionId", "state", "discard"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ProtocolError("invalid_request", "closing request fields are incomplete or unexpected")
    identity = value["closeId"]
    if (not isinstance(identity, str) or len(identity) != 70 or not identity.startswith("close_")
            or any(c not in "0123456789abcdef" for c in identity[6:])):
        raise ProtocolError("invalid_request", "invalid closeId")
    state = value["state"]
    if (not isinstance(state, Mapping) or set(state) != {"path", "dirty", "generation"}
            or (state["dirty"] is not None and type(state["dirty"]) is not bool)
            or type(state["generation"]) is not int
            or (state["path"] is not None and not isinstance(state["path"], str))
            or type(value["discard"]) is not bool):
        raise ProtocolError("invalid_request", "Close requires a reviewed path, dirty state and generation")
    return {"closeId": identity, "documentId": text(value["documentId"], "documentId"),
            "bridgeSessionId": text(value["bridgeSessionId"], "bridgeSessionId"),
            "state": dict(state), "discard": value["discard"]}
