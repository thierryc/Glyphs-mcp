"""Seven-tool application service for the standalone sidecar."""

from __future__ import annotations

import math
import time
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Any, Mapping

from glyphs_mcp_protocol import PROTOCOL_VERSION, TOOL_NAMES, validate_patch
from glyphs_mcp_protocol.reads import READ_CAPABILITIES

from .bridge_client import BridgeClientError
from .jobs import JobStore
from .identity import IDENTITY, VERSION
from .lifecycle import ServiceLifecycle, activity, mutation
from .source import SourceError, snapshot_source, source_hash
from .worker import GlyphsCliWorker, WorkerError

JOB_KINDS = ("width_delta", "spacing", "kerning_collision", "start_nodes", "slant")


class ServiceError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.details = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class SidecarService:
    def __init__(self, bridge: Any, *, jobs: JobStore | None = None, worker: Any | None = None) -> None:
        self.bridge = bridge
        self.jobs = jobs or JobStore()
        self.worker = worker or GlyphsCliWorker()
        self._cancellations: dict[str, Event] = {}
        self._lock = RLock()
        self.lifecycle = ServiceLifecycle(self, ServiceError)
        for job in self.jobs.records():
            if job["status"] in {"preparing", "cancelling"}:
                self.jobs.update(job["id"], status="interrupted", error={
                    "code": "service_interrupted",
                    "message": "The previous service stopped during preparation. This job was not resubmitted.",
                })

    def reserve_idle(self):
        return self.lifecycle.reserve()

    def release_idle(self, reservation_id):
        return self.lifecycle.release(reservation_id)

    def close(self):
        # Release external preparation processes during a native Stop action.
        with self._lock:
            for cancel in self._cancellations.values():
                cancel.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with self._lock:
                if not self._cancellations:
                    return
            time.sleep(.02)

    def get_status(self) -> dict[str, Any]:
        try:
            bridge = {"reachable": True, **dict(self.bridge.status())}
        except Exception as exc:
            bridge = {"reachable": False, "error": self._error(exc).as_dict()}
        status = getattr(self.worker, "status", None)
        worker = status() if callable(status) else {"available": True, "kind": "injected"}
        return {
            "protocol": PROTOCOL_VERSION,
            "sidecarVersion": VERSION,
            **IDENTITY,
            "interface": "glyphs-mcp-sidecar", "interfaceVersion": 1,
            "jobKinds": list(JOB_KINDS),
            "readCapabilities": [name for name in READ_CAPABILITIES
                                 if name in (bridge.get("readCapabilities") or [])],
            "tools": list(TOOL_NAMES),
            "bridge": bridge,
            "worker": worker,
            "controlProtocol": 1,
            "activity": self.lifecycle.snapshot(),
            "acceptance": "Save in Glyphs to accept. Undo is per glyph; Revert or discard_job restores the whole job.",
        }

    def list_documents(self) -> list[dict[str, Any]]:
        try:
            return self.bridge.documents()
        except Exception as exc:
            raise self._error(exc) from exc

    def read_entities(
        self, document_id: str, entities: list[dict[str, Any]], fields: list[str]
    ) -> list[dict[str, Any]]:
        try:
            return self.bridge.read_entities(str(document_id), entities, fields)
        except Exception as exc:
            raise self._error(exc) from exc

    @mutation
    def start_job(
        self,
        document_id: str,
        *,
        kind: str,
        delta: float | None = None,
        glyphs: list[str] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        document = self._document(document_id)
        if not document.get("path"):
            raise ServiceError("document_path_required", "Save or Save As before starting a large job")
        if document.get("dirty") is not False:
            raise ServiceError("document_not_clean", "Save the font before starting a large job")
        if not isinstance(document.get("generation"), int):
            raise ServiceError("generation_unavailable", "Glyphs did not expose a bounded edit generation")
        request = self._job_request(kind, delta, glyphs, options)
        status = getattr(self.worker, "status", None)
        if callable(status) and not status().get("available"):
            raise ServiceError("worker_unavailable", "the external Glyphs worker is unavailable")
        job = self.jobs.create(document, request)
        cancel = Event()
        with self._lock:
            self._cancellations[job["id"]] = cancel
        thread = Thread(
            target=self._prepare,
            args=(job["id"], cancel),
            name="glyphs-mcp-" + job["id"],
            daemon=True,
        )
        thread.start()
        return self._public(job)

    def get_job(self, job_id: str, *, include_preview: bool = True) -> dict[str, Any]:
        job = self._job(job_id)
        if job["status"] in {"applying", "discarding"} or (
            job["status"] == "applied" and (job.get("error") or {}).get("code") == "job_not_found"
        ):
            try:
                operation = self.bridge.operation(job["id"])
            except Exception as exc:
                interrupted = self._interrupt_missing_operation(job, exc)
                if interrupted is not None:
                    return self._public(interrupted, include_preview=include_preview)
                raise self._error(exc) from exc
            state = operation.get("status")
            mapped = {
                "applied": "applied",
                "discarded": "discarded",
                "failed": "failed",
                "cancelled": "cancelled",
            }.get(state, job["status"])
            with self._lock:
                current = self._job(job["id"])
                if current != job:
                    return self._public(current, include_preview=include_preview)
                job = self.jobs.update(
                    job["id"], status=mapped, bridgeOperation=operation,
                    error=operation.get("error"),
                )
                if mapped in {"discarded", "cancelled"}:
                    self.jobs.release_bulk_artifacts(job["id"])
        return self._public(job, include_preview=include_preview)

    def _interrupt_missing_operation(self, job, error):
        if not isinstance(error, BridgeClientError) or error.code != "job_not_found":
            return None
        with self._lock:
            current = self._job(job["id"])
            if current != job:
                return current
            acknowledgement = job.get("bridgeOperation") or {}
            uncertain = ((job.get("error") or {}).get("details") or {}).get("execution") == "uncertain"
            if (self.lifecycle.pending or uncertain
                    or acknowledgement.get("jobId") != job["id"]
                    or acknowledgement.get("documentId") != job["document"]["id"]):
                return None
            # Missing history may follow a restart or finished-record eviction.
            # Preserve the last observation and artifacts; never infer restoration.
            return self.jobs.update(job["id"], status="interrupted", error={
                "code": "bridge_operation_lost",
                "message": "The native operation is no longer available; final edits and restoration are unverified. No replay was attempted. Inspect the intended font before preparing new work.",
                "details": {"previousStatus": job["status"], "outcome": "unverified", "restoration": "unverified"},
            })

    @staticmethod
    def _require_available_operation(job):
        error = job.get("error") or {}
        if job["status"] == "interrupted" and error.get("code") == "bridge_operation_lost":
            raise ServiceError(error["code"], error["message"], details=error.get("details"))

    @mutation
    def apply_job(self, job_id: str, *, include_preview: bool = True) -> dict[str, Any]:
        job = self._job(job_id)
        self._require_available_operation(job)
        if job["status"] in {"applying", "applied"}:
            return self.get_job(job_id, include_preview=include_preview)
        if job["status"] != "ready":
            raise ServiceError("job_not_ready", "the job is not ready to apply")
        document = self._document(job["document"]["id"])
        if document.get("path") != job["document"].get("path"):
            raise ServiceError("stale_document", "the document path changed while the job was prepared")
        if document.get("dirty") is not False:
            raise ServiceError("document_not_clean", "save or discard current edits before applying")
        if document.get("generation") != job["document"].get("generation"):
            raise ServiceError("stale_document", "the document changed while the job was prepared")
        try:
            observed_hash = source_hash(Path(document["path"]))
        except SourceError as exc:
            raise ServiceError("source_unavailable", str(exc)) from exc
        if observed_hash != job.get("sourceHash"):
            raise ServiceError("stale_source", "the saved source changed while the job was prepared")
        patch = validate_patch(self.jobs.read_json(job["id"], "patch.json"))
        self.jobs.update(job["id"], status="applying")
        try:
            operation = self.bridge.apply(patch)
        except Exception as exc:
            certain = isinstance(exc, BridgeClientError) and exc.details.get("execution") != "uncertain"
            self.jobs.update(job["id"], status="ready" if certain else "applying", error=self._error(exc).as_dict())
            raise self._error(exc) from exc
        job = self.jobs.update(job["id"], status="applying", bridgeOperation=operation)
        return self._public(job, include_preview=include_preview)

    @mutation
    def discard_job(self, job_id: str, *, include_preview: bool = True) -> dict[str, Any]:
        with self._lock:
            job = self._job(job_id)
            self._require_available_operation(job)
            if job["status"] in {"discarded", "cancelled"}:
                return self._public(job, include_preview=include_preview)
            if job["status"] in {"preparing", "cancelling"}:
                cancel = self._cancellations.get(job["id"])
                if cancel is not None:
                    cancel.set()
                return self._public(self.jobs.update(job["id"], status="cancelling"), include_preview=include_preview)
            if job["status"] == "ready":
                job = self.jobs.update(job["id"], status="discarded")
                self.jobs.release_bulk_artifacts(job["id"])
                return self._public(job, include_preview=include_preview)
        if job["status"] in {"applying", "applied", "discarding"}:
            self.jobs.update(job["id"], status="discarding")
            try:
                operation = self.bridge.discard(job["id"])
            except Exception as exc:
                certain = isinstance(exc, BridgeClientError) and exc.details.get("execution") != "uncertain"
                self.jobs.update(job["id"], status=job["status"] if certain else "discarding", error=self._error(exc).as_dict())
                raise self._error(exc) from exc
            return self._public(
                self.jobs.update(job["id"], status="discarding", bridgeOperation=operation),
                include_preview=include_preview,
            )
        raise ServiceError("job_not_discardable", "this job cannot be discarded")

    def _prepare(self, job_id: str, cancel: Event) -> None:
        try:
            job = self.jobs.get(job_id)
            self.jobs.update(job_id, phase="copying_source")
            if cancel.is_set():
                raise WorkerError("job cancelled")
            source_path, fingerprint = snapshot_source(
                Path(job["document"]["path"]), self.jobs.path(job_id)
            )
            if cancel.is_set():
                raise WorkerError("job cancelled")
            self.jobs.update(job_id, phase="preparing")
            patch = self.worker.prepare(
                self.jobs.path(job_id),
                job["document"],
                job["request"],
                source_path,
                fingerprint,
                cancel,
            )
            patch = validate_patch(patch)
            self.jobs.write_json(job_id, "patch.json", patch)
            report_path = self.jobs.path(job_id) / "report.json"
            report = self.jobs.read_json(job_id, "report.json") if report_path.is_file() else None
            rows = (report.get("layers", report.get("pairs", []))) if report else []
            with self._lock:
                if cancel.is_set() or self.jobs.get(job_id)["status"] != "preparing":
                    raise WorkerError("job cancelled")
                self.jobs.update(
                    job_id, status="ready", sourceHash=fingerprint,
                    summary=patch["summary"], changeCount=len(patch["changes"]), sample=patch["changes"][:10],
                    report=({"path": str(report_path), "claim": report["claim"],
                             "layerCount" if "layers" in report else "pairCount": len(rows), "sample": rows[:10],
                             "unavailableCount": sum(r["status"] == "unavailable" for r in rows)} if report else None),
                )
        except Exception as exc:
            with self._lock:
                cancelled = cancel.is_set() or str(exc) == "job cancelled"
                self.jobs.update(
                    job_id, status="cancelled" if cancelled else "failed",
                    error={"code": "cancelled" if cancelled else "job_failed", "message": str(exc)},
                )
        finally:
            with self._lock:
                if self.jobs.get(job_id)["status"] in {"cancelled", "failed"}:
                    self.jobs.release_bulk_artifacts(job_id)
                self._cancellations.pop(job_id, None)

    def _document(self, document_id: str) -> dict[str, Any]:
        for document in self.list_documents():
            if document.get("id") == str(document_id):
                return document
        raise ServiceError("document_not_found", "the Glyphs document is no longer open")

    @staticmethod
    def _job_request(kind: str, delta: float | None, glyphs: list[str] | None, options=None) -> dict[str, Any]:
        if str(kind) not in JOB_KINDS:
            raise ServiceError("unsupported_job", "supported jobs: width_delta, spacing, kerning_collision, start_nodes, slant")
        if kind == "width_delta" and (isinstance(delta, bool) or not isinstance(delta, (int, float)) or not math.isfinite(float(delta)) or delta == 0):
            raise ServiceError("invalid_request", "delta must be a finite non-zero number")
        names = []
        if glyphs is not None:
            if not isinstance(glyphs, list) or not 1 <= len(glyphs) <= 10_000:
                raise ServiceError("invalid_request", "glyphs must contain 1-10,000 names")
            names = [str(value).strip() for value in glyphs]
            if any(not value for value in names) or len(names) != len(set(names)):
                raise ServiceError("invalid_request", "glyph names must be non-empty and unique")
        if kind in ("spacing", "kerning_collision", "start_nodes", "slant"):
            from .spacing import validate_options as spacing_options
            from .collision import validate_options as collision_options
            from .start_node_job import validate_options as start_options
            from .slant_job import validate_options as slant_options
            validate_options = {"spacing": spacing_options, "kerning_collision": collision_options, "start_nodes": start_options, "slant": slant_options}[kind]
            try:
                if delta is not None:
                    raise ValueError(kind + " uses options, not delta")
                if kind == "kerning_collision" and names:
                    raise ValueError("kerning_collision selects explicit pairs in options")
                if kind == "start_nodes" and not 1 <= len(names) <= 100:
                    raise ValueError("start_nodes requires 1-100 explicit glyphs")
                return {"kind": kind, "glyphs": names, "options": validate_options({} if options is None else options)}
            except ValueError as error:
                raise ServiceError("invalid_request", str(error)) from error
        if options:
            raise ServiceError("invalid_request", "width_delta does not use options")
        return {"kind": "width_delta", "delta": delta, "glyphs": names}

    def _job(self, job_id: str) -> dict[str, Any]:
        try:
            return self.jobs.get(str(job_id))
        except KeyError as exc:
            raise ServiceError("job_not_found", "the job does not exist") from exc

    @staticmethod
    def _error(exc: Exception) -> ServiceError:
        if isinstance(exc, ServiceError):
            return exc
        if isinstance(exc, BridgeClientError):
            return ServiceError(exc.code, exc.message, details=exc.details)
        return ServiceError("bridge_failed", str(exc) or exc.__class__.__name__)

    @staticmethod
    def _public(job: Mapping[str, Any], *, include_preview: bool = True) -> dict[str, Any]:
        status = str(job["status"])
        result = {
            "id": job["id"],
            "status": status,
            "summary": job.get("summary"),
            "changeCount": int(job.get("changeCount") or 0),
            "sample": list(job.get("sample") or []),
            "report": job.get("report"),
            "error": job.get("error"),
            "bridgeOperation": job.get("bridgeOperation"),
            "activity": activity(job),
            "message": (
                "Review the change in Glyphs. Save to accept; Undo is per glyph. Revert or discard_job restores the whole job."
                if status == "applied"
                else None
            ),
        }
        if not include_preview:
            result.pop("sample")
            if isinstance(result["report"], dict):
                result["report"] = {k: v for k, v in result["report"].items() if k != "sample"}
            result["previewIncluded"] = False
        return result
