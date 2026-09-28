"""Small activity projection and process-control reservation for the sidecar."""
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
import fcntl
import os
import time
from uuid import uuid4

BUSY = frozenset(("preparing", "cancelling", "applying", "accepting", "discarding"))


def mutation(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self.lifecycle.mutation():
            return method(self, *args, **kwargs)
    return guarded


def activity(job):
    operation = job.get("bridgeOperation") or {}
    state = job["status"]
    phase = job.get("phase", state) if state == "preparing" else state
    document = job["document"]
    return {
        "jobId": job["id"],
        "document": document.get("familyName") or Path(document.get("path") or "Untitled").name,
        "kind": job["request"]["kind"], "phase": phase,
        "startedAt": job.get("phaseStartedAt", job["createdAt"]),
        "finishedAt": job.get("finishedAt"),
        "completed": operation.get("completedChanges") if state in ("applying", "accepting", "discarding", "applied", "accepted", "accept_uncertain", "discarded") else None,
        "total": operation.get("totalChanges") if state in ("applying", "accepting", "discarding", "applied", "accepted", "accept_uncertain", "discarded") else None,
        "message": (job.get("error") or {}).get("message"),
    }


class ServiceLifecycle:
    def __init__(self, service, error_type):
        self.service = service
        self.error = error_type
        self.clock = time.monotonic
        self.pending = 0
        self.reservation = None
        self.control_lock = None

    def _external_control_active(self):
        if self.control_lock is None:
            return False
        self.control_lock.parent.mkdir(parents=True, exist_ok=True)
        with self.control_lock.open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
        return False

    def _expire(self):
        if self.reservation and self.clock() >= self.reservation["deadline"]:
            self.reservation = None

    @contextmanager
    def mutation(self):
        with self.service._lock:
            self._expire()
            if self.reservation or self._external_control_active():
                raise self.error("service_reserved", "The service is reserved for a settings or installation change.")
            self.pending += 1
        try:
            yield
        finally:
            with self.service._lock:
                self.pending -= 1

    def reconcile(self):
        for job in self.service.jobs.select({'applying', 'accepting', 'discarding'}):
            try:
                self.service.get_job(job["id"])
            except Exception:
                # Keep the existing identity and last observation when native
                # execution cannot be reconciled. Never infer completion.
                pass

    def snapshot(self):
        self.reconcile()
        active = self.service.jobs.select(BUSY)
        selected = active[:10] + self.service.jobs.recent(max(0, 5-len(active)), exclude_statuses=BUSY)
        return {"jobs": [activity(job) for job in selected], "activeCount": len(active),
                "moreCount": max(0, len(active) - 10)}

    def reserve(self):
        self.reconcile()
        with self.service._lock:
            self._expire()
            if self.reservation:
                raise self.error("service_reserved", "The service is already reserved.")
            if self.pending or self.service._cancellations or self.service.jobs.count(BUSY) or self.service.jobs.select(set(), include_unresolved=True):
                raise self.error("service_busy", "The service is busy. Wait for the current operation to finish.")
            try:
                native = self.service.bridge.status()
            except Exception:
                native = {}
            if native.get("activeOperations", 0):
                raise self.error("service_busy", "Glyphs is busy applying or restoring changes.")
            identity = uuid4().hex
            self.reservation = {"id": identity, "deadline": self.clock() + 30}
            return {"reservationId": identity, "expiresInSeconds": 30, "processId": os.getpid()}

    def release(self, identity):
        with self.service._lock:
            self._expire()
            if not self.reservation:
                return {"released": True}
            if self.reservation["id"] != identity:
                raise self.error("reservation_mismatch", "This request does not own the service reservation.")
            self.reservation = None
            return {"released": True}
