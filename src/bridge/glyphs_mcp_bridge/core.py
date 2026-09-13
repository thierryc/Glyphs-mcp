"""Small bridge coordinator with time-sliced, target-checked application."""

from __future__ import annotations

import copy
import math
import numbers
import time
from threading import RLock
from typing import Any, Callable, Mapping, Protocol

from glyphs_mcp_protocol import PROTOCOL_VERSION, ProtocolError, validate_patch
from glyphs_mcp_protocol.reads import READ_CAPABILITIES

from .companions import CompanionRegistry
from .identity import IDENTITY, VERSION, host_identity

ACTIVE = {"applying", "discarding", "rolling_back"}


class BridgeError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.details = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class BridgeAdapter(Protocol):
    def list_documents(self) -> list[dict[str, Any]]: ...
    def read_entities(self, document_id: str, entities: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]: ...
    def document_state(self, document_id: str) -> dict[str, Any]: ...
    def current_value(self, document_id: str, change: Mapping[str, Any], *, reverse: bool = False) -> Any: ...
    def apply_change(self, document_id: str, change: Mapping[str, Any], *, reverse: bool = False) -> None: ...
    def capture_state(self, document_id: str, change: Mapping[str, Any]) -> Any: ...
    def begin_undo(self, document_id: str) -> None: ...
    def end_undo(self, document_id: str, name: str) -> None: ...


class BridgeCore:
    """Coordinates only explicit targets; it never captures a complete font."""

    def __init__(self, adapter: BridgeAdapter, schedule: Callable[[Callable[[], None]], None], *,
                 chunk_ms: float = 10.0, chunk_limit: int = 50,
                 companions: CompanionRegistry | None = None) -> None:
        self.adapter = adapter
        self.host = host_identity()
        self.schedule = schedule
        self.chunk_seconds = max(0.001, min(float(chunk_ms), 12.0) / 1000.0)
        self.chunk_limit = max(1, min(int(chunk_limit), 500))
        self.companions = companions or CompanionRegistry()
        self._operations: dict[str, dict[str, Any]] = {}
        self._lock = RLock()
        self.paused = False

    @staticmethod
    def _same_value(observed: Any, expected: Any, *, normalized: bool = False) -> bool:
        if all(isinstance(v, numbers.Real) and not isinstance(v, bool) for v in (observed, expected)):
            return math.isclose(float(observed), float(expected), rel_tol=1e-12,
                                abs_tol=0.05 if normalized else 1e-9)
        return observed == expected

    @staticmethod
    def _resolve_live_scalar(change: Mapping[str, Any], observed: Any) -> dict[str, Any]:
        resolved = dict(change)
        before, after = change["before"], change["after"]
        if all(isinstance(v, numbers.Real) and not isinstance(v, bool) for v in (observed, before, after)):
            live_before = float(observed)
            resolved["before"] = live_before
            resolved["after"] = live_before + (float(after) - float(before))
        return resolved

    def status(self) -> dict[str, Any]:
        with self._lock:
            active = sum(item["status"] in ACTIVE for item in self._operations.values())
        return {
            "protocol": PROTOCOL_VERSION, "bridgeVersion": VERSION,
            **IDENTITY, "host": self.host,
            "readCapabilities": list(READ_CAPABILITIES),
            "activity": "busy" if active else "ready", "activeOperations": active,
            "companions": self.companions.list(),
        }

    def list_documents(self) -> list[dict[str, Any]]:
        return self.adapter.list_documents()

    def read_entities(self, document_id: str, entities: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
        if not isinstance(entities, list) or not 1 <= len(entities) <= 100:
            raise BridgeError("invalid_request", "read_entities requires 1-100 explicit entities")
        if not isinstance(fields, list) or not 1 <= len(fields) <= 32:
            raise BridgeError("invalid_request", "read_entities requires 1-32 fields")
        return self.adapter.read_entities(str(document_id), entities, [str(item) for item in fields])

    def begin_apply(self, value: Any) -> dict[str, Any]:
        if self.paused:
            raise BridgeError("server_stopped", "the Glyphs MCP server is stopped")
        try:
            patch = validate_patch(value)
        except ProtocolError as exc:
            raise BridgeError(exc.code, exc.message) from exc
        job_id = patch["jobId"]
        with self._lock:
            existing = self._operations.get(job_id)
            if existing is not None:
                if existing["patch"] != patch:
                    raise BridgeError("job_conflict", "job ID already belongs to another patch")
                return self._public(existing)
            self._check_owner(patch["documentId"])
        state = self.adapter.document_state(patch["documentId"])
        if state.get("path") != patch["sourcePath"]:
            raise BridgeError("stale_document", "the document path changed before application")
        if state.get("dirty") is not False:
            raise BridgeError("document_not_clean", "save the document before applying this job")
        if state.get("generation") != patch["generation"]:
            raise BridgeError("stale_document", "the document changed while the job was prepared")
        operation = dict(jobId=job_id, documentId=patch["documentId"], patch=patch,
                         status="applying", direction="forward", index=0, applied=[], resolved=[],
                         cancelRequested=False, rollbackReverse=True, error=None,
                         startedAt=time.time(), finishedAt=None)
        with self._lock:
            existing = self._operations.get(job_id)
            if existing is not None:
                if existing["patch"] != patch:
                    raise BridgeError("job_conflict", "job ID already belongs to another patch")
                return self._public(existing)
            self._check_owner(patch["documentId"])
            # Keep a bounded recent retry/discard window. Native Undo owns
            # its inverses independently of these bridge operation records.
            finished = [key for key, item in self._operations.items()
                        if item["status"] not in ACTIVE]
            for key in finished[:-7]:
                del self._operations[key]
            self._operations[job_id] = operation
        self._launch(operation)
        return self._public(operation)

    def _check_owner(self, document_id):
        if any(item["documentId"] == document_id and item["status"] in ACTIVE
               for item in self._operations.values()):
            raise BridgeError("document_busy", "another operation is changing this document")

    def _launch(self, operation):
        try:
            operation["undoOpen"] = True
            self.adapter.begin_undo(operation["documentId"])
            self._schedule(operation)
        except Exception as exc:
            self._finish(operation, "failed", self._error(exc))

    def _schedule(self, operation):
        try:
            self.schedule(lambda: self._run_chunk(operation["jobId"]))
        except Exception as exc:
            error = self._error(exc)
            previous = (operation["error"] or {}).get("details", {}).get("recovery", {})
            error.details["recovery"] = {"complete": not operation["applied"] and previous.get("currentTargetRestored", True)}
            self._finish(operation, "failed", error)

    def discard(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            operation = self._operations.get(str(job_id))
            if operation is None:
                raise BridgeError("job_not_found", "the bridge does not know this job")
            if operation["status"] in {"applying", "rolling_back"}:
                operation["cancelRequested"] = True
                return self._public(operation)
            if operation["status"] in {"discarding", "discarded", "cancelled", "failed"}:
                return self._public(operation)
            if operation["status"] != "applied":
                raise BridgeError("job_not_discardable", "the job is not applied")
            self._check_owner(operation["documentId"])
            operation.update(status="discarding", direction="restore", index=0,
                             applied=[], cancelRequested=False, error=None)
        self._launch(operation)
        return self._public(operation)

    def operation(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            operation = self._operations.get(str(job_id))
            if operation is None:
                raise BridgeError("job_not_found", "the bridge does not know this job")
            return self._public(operation)

    def _run_chunk(self, job_id: str) -> None:
        with self._lock:
            operation = self._operations.get(job_id)
            if operation is None or operation["status"] not in ACTIVE:
                return
        if operation["cancelRequested"] and operation["status"] == "applying":
            self._start_rollback(operation, BridgeError("cancelled", "application was cancelled"), reverse=True)
        deadline = time.perf_counter() + self.chunk_seconds
        processed = 0
        try:
            while processed < self.chunk_limit and time.perf_counter() < deadline:
                if operation["status"] == "rolling_back":
                    if not operation["applied"]:
                        recovery = operation["error"].setdefault("details", {}).setdefault("recovery", {})
                        recovery["complete"] = recovery.get("currentTargetRestored", True)
                        state = "cancelled" if operation["error"]["code"] == "cancelled" else "failed"
                        self._finish(operation, state)
                        return
                    change = operation["applied"][-1]
                    self._apply_one(operation, change, reverse=operation["rollbackReverse"])
                    operation["applied"].pop()
                else:
                    forward = operation["direction"] == "forward"
                    changes = operation["patch"]["changes"] if forward else operation["resolved"]
                    index = operation["index"]
                    if index >= len(changes):
                        self._finish(operation, "applied" if forward else "discarded")
                        return
                    change = changes[index]
                    applied = self._apply_one(operation, change, reverse=not forward)
                    operation["applied"].append(applied)
                    if forward:
                        operation["resolved"].append(applied)
                    operation["index"] += 1
                processed += 1
        except Exception as exc:
            error = self._error(exc)
            if operation["status"] in {"applying", "discarding"}:
                self._start_rollback(operation, error, reverse=operation["status"] == "applying")
            else:
                error.details["recovery"] = {"complete": False, "remaining": len(operation["applied"])}
                self._finish(operation, "failed", error)
                return
        self._schedule(operation)

    def _apply_one(self, operation, change, *, reverse):
        target = {k: v for k, v in change.items()
                  if k not in ("before", "after", "beforeHash", "afterHash", "nativeBefore", "nativeAfter")}
        if change["kind"] in ("translate", "start_node"):
            expected = change["afterHash"] if reverse else change["beforeHash"]
            wanted = change["beforeHash"] if reverse else change["afterHash"]
        else:
            expected = change["after"] if reverse else change["before"]
            wanted = change["before"] if reverse else change["after"]
        observed = self.adapter.current_value(operation["documentId"], change, reverse=reverse)
        if not self._same_value(observed, expected, normalized=not reverse and change["kind"] == "set"):
            raise BridgeError("target_conflict", "a target changed before it could be written",
                              details={"target": target, "expected": expected, "observed": observed})
        if change["kind"] == "set" and not reverse:
            resolved = self._resolve_live_scalar(change, observed)
            expected = resolved["before"]
            wanted = resolved["after"]
        else:
            resolved = dict(change)
        document_id = operation["documentId"]
        hashed = change["kind"] in ("translate", "start_node")
        if hashed:
            resolved["nativeAfter" if reverse else "nativeBefore"] = self.adapter.capture_state(document_id, change)
        else:
            resolved["after" if reverse else "before"] = observed
        try:
            self.adapter.apply_change(document_id, resolved, reverse=reverse)
            readback = self.adapter.current_value(document_id, resolved, reverse=reverse)
            if not self._same_value(readback, wanted):
                raise BridgeError("readback_failed", "Glyphs did not retain the requested target value",
                                  details={"wanted": wanted, "observed": readback})
            if hashed:
                resolved["nativeBefore" if reverse else "nativeAfter"] = self.adapter.capture_state(document_id, change)
        except Exception as exc:
            error = self._error(exc)
            error.details["target"] = target
            recovery = {"complete": False, "currentTargetRestored": False}
            try:
                self.adapter.apply_change(document_id, resolved, reverse=not reverse)
            except Exception as restore_error:
                recovery["writeError"] = str(restore_error)
            try:
                restored = self.adapter.current_value(document_id, resolved, reverse=not reverse)
                recovery["currentTargetRestored"] = self._same_value(restored, observed)
            except Exception as read_error:
                recovery["readError"] = str(read_error)
            error.details["recovery"] = recovery
            raise error from exc
        return resolved

    def _start_rollback(self, operation, error, *, reverse):
        operation.update(status="rolling_back", error=error.as_dict(),
                         rollbackReverse=bool(reverse), cancelRequested=False)

    @staticmethod
    def _error(exc):
        return exc if isinstance(exc, BridgeError) else BridgeError("native_write_failed", str(exc) or type(exc).__name__)

    def _finish(self, operation, status, error=None):
        if error is not None:
            operation["error"] = error.as_dict()
        try:
            if operation.pop("undoOpen", False):
                self.adapter.end_undo(operation["documentId"], "Glyphs MCP: " + operation["patch"]["summary"])
        except Exception as exc:
            status = "failed"
            error = operation["error"] or self._error(exc).as_dict()
            error.setdefault("details", {})["cleanup"] = str(exc)
            operation["error"] = error
        finally:
            with self._lock:
                operation.update(status=status, finishedAt=time.time(), applied=[])
                if status != "applied":
                    operation["resolved"] = []

    @staticmethod
    def _public(operation: Mapping[str, Any]) -> dict[str, Any]:
        count = len(operation["patch"]["changes"])
        return {
            "jobId": operation["jobId"],
            "documentId": operation["documentId"],
            "status": operation["status"],
            "completedChanges": max(0, min(count, int(operation["index"]))),
            "totalChanges": count,
            "error": copy.deepcopy(operation["error"]),
            "message": (
                "Review the change in Glyphs. Save to accept; Undo restores each glyph. Revert or discard_job restores the whole job."
                if operation["status"] == "applied"
                else None
            ),
        }
