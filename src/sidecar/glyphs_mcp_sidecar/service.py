"""Guarded job/save service and conversational workflow facade."""

from __future__ import annotations

import math
import time
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Any, Mapping

from glyphs_mcp_protocol import (
    PROTOCOL_VERSION,
    TOOL_NAMES,
    ProtocolError,
    recognized_actions,
    recognized_job_capabilities,
    validate_patch,
)
from glyphs_mcp_protocol.reads import READ_CAPABILITIES
from glyphs_mcp_protocol import dimensions

from .bridge_client import BridgeClientError
from .jobs import JobStore
from .identity import IDENTITY, VERSION
from .lifecycle import ServiceLifecycle, activity, mutation
from . import saving
from . import artifact_publication
from .source import SourceError, snapshot_source, source_hash
from .worker import GlyphsCliWorker
from . import job_preparation

JOB_KINDS = ("width_delta", "spacing", "kerning_collision", "start_nodes", "slant")
OUTLINE_WRITE_CAPABILITIES = ("outline.edit.v1", "outline.remove-node.v1")
NATIVE_WRITE_CAPABILITY = "native.action.v1"


def _uses_native_remove(request):
    return any(operation.get("op") == "remove_node"
               for target in request.get("options", {}).get("targets", [])
               for operation in target.get("operations", []))


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
            elif job["status"] == "accepting":
                if job.get("resultKind") == "artifact":
                    artifact_publication.reconcile(self, job)
                    continue
                receipt_path = self.jobs.path(job["id"]) / "receipt.json"
                if receipt_path.is_file():
                    try:
                        receipt = self.jobs.read_json(job["id"], "receipt.json")
                    except Exception:
                        continue
                    if not saving.valid_job_receipt(job, receipt):
                        continue
                    self.jobs.update(
                        job["id"], status="accepted", receipt=receipt, error=None
                    )
                    saving.reconcile_accepted(self, self.jobs.get(job["id"]))
                    self.jobs.release_bulk_artifacts(job["id"])

    @property
    def edit_workflows(self):
        from .edit_workflow import EditWorkflows
        with self._lock:
            if not hasattr(self, "_edit_workflows"):
                self._edit_workflows = EditWorkflows(self, ServiceError)
            return self._edit_workflows

    def reserve_idle(self):
        return self.lifecycle.reserve()

    def release_idle(self, reservation_id):
        return self.lifecycle.release(reservation_id)

    def close(self):
        if hasattr(self, "_edit_workflows"):
            self._edit_workflows.close()
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
        advertised_writes = bridge.get("writeCapabilities") or []
        job_capabilities = sorted(set(
            recognized_job_capabilities(bridge.get("jobCapabilities"))
            + recognized_job_capabilities(worker.get("jobCapabilities"))
        ))
        native_actions = (
            recognized_actions(bridge.get("nativeActions"))
            if NATIVE_WRITE_CAPABILITY in advertised_writes else []
        )
        return {
            "protocol": PROTOCOL_VERSION,
            "sidecarVersion": VERSION,
            **IDENTITY,
            "interface": "glyphs-mcp-sidecar", "interfaceVersion": 1,
            "jobKinds": list(JOB_KINDS)
                        + (["outline_edit"] if "outline.edit.v1" in advertised_writes else [])
                        + (["native_action"] if native_actions else [])
                        + (["dimensions_edit"] if dimensions.WRITE_CAPABILITY in advertised_writes else [])
                        + (["feature_compile"] if any(
                            name in job_capabilities for name in (
                                "feature.compile.saved.v1", "feature.compile.live.v1"
                            )
                        ) else [])
                        + (["font_export"] if "font.verify.tables.v1" in job_capabilities and any(
                            name in job_capabilities for name in (
                                "font.export.static.v1", "font.export.variable.v1"
                            )
                        ) else []),
            "readCapabilities": [name for name in READ_CAPABILITIES
                                 if name in (bridge.get("readCapabilities") or [])],
            "writeCapabilities": [name for name in (*OUTLINE_WRITE_CAPABILITIES, NATIVE_WRITE_CAPABILITY, dimensions.WRITE_CAPABILITY)
                                  if name in advertised_writes and (name != NATIVE_WRITE_CAPABILITY or native_actions)],
            "nativeActions": native_actions,
            "jobCapabilities": job_capabilities,
            "tools": list(TOOL_NAMES),
            "bridge": bridge,
            "worker": worker,
            "controlProtocol": 1,
            "workflowCapabilities": ["edit.workflow.v1"],
            "activity": self.lifecycle.snapshot(),
            "acceptance": "Call accept_job to verify and save an applied job. apply_job remains reversible and never saves.",
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
        request = self.validate_job_request(kind, delta, glyphs, options)
        job = self.jobs.create(document, request)
        cancel = Event()
        with self._lock:
            self._cancellations[job["id"]] = cancel
        live_compile = kind == "feature_compile" and request["options"]["mode"] == "live"
        thread = Thread(
            target=job_preparation.prepare_live_compile if live_compile else job_preparation.prepare_external,
            args=(self, job["id"], cancel),
            name="glyphs-mcp-" + job["id"],
            daemon=True,
        )
        thread.start()
        return self._public(job)

    def validate_job_request(self, kind, delta=None, glyphs=None, options=None):
        """Shared nonmutating preflight, including dirty/pathless workflow requests."""
        request = self._job_request(kind, delta, glyphs, options)
        if kind in ("outline_edit", "native_action", "feature_compile", "font_export", "dimensions_edit"):
            try:
                bridge_status = self.bridge.status()
                advertised = bridge_status.get("writeCapabilities") or []
            except Exception:
                bridge_status = {}
                advertised = []
            if kind == "dimensions_edit" and dimensions.WRITE_CAPABILITY not in advertised:
                raise ServiceError("unsupported_job", "Dimensions writes are not qualified by the live bridge")
            if kind == "outline_edit" and "outline.edit.v1" not in advertised:
                raise ServiceError("unsupported_job", "outline_edit requires bridge capability outline.edit.v1")
            if kind == "outline_edit" and _uses_native_remove(request) and "outline.remove-node.v1" not in advertised:
                raise ServiceError(
                    "unsupported_job",
                    "remove_node requires bridge capability outline.remove-node.v1",
                )
            if kind == "native_action":
                actions = recognized_actions(bridge_status.get("nativeActions"))
                if NATIVE_WRITE_CAPABILITY not in advertised or request["options"]["action"] not in actions:
                    raise ServiceError(
                        "unsupported_job",
                        f"native action {request['options']['action']} is not advertised by the live bridge",
                    )
            bridge_jobs = recognized_job_capabilities(bridge_status.get("jobCapabilities"))
            worker_status = self.worker.status() if callable(getattr(self.worker, "status", None)) else {"available": True}
            worker_jobs = recognized_job_capabilities(worker_status.get("jobCapabilities"))
            if kind == "feature_compile":
                mode = request["options"]["mode"]
                required = f"feature.compile.{mode}.v1"
                advertised_jobs = bridge_jobs if mode == "live" else worker_jobs
                if required not in advertised_jobs:
                    raise ServiceError("unsupported_job", f"feature_compile {mode} mode is not advertised")
            if kind == "font_export" and not any(
                name in worker_jobs for name in ("font.export.static.v1", "font.export.variable.v1")
            ):
                raise ServiceError("unsupported_job", "font_export is not advertised by the external worker")
            if kind == "font_export":
                if "font.verify.tables.v1" not in worker_jobs:
                    raise ServiceError("unsupported_job", "font_export requires structural table verification")
                if any(name != "plain" for name in request["options"]["containers"]) and "font.export.web.v1" not in worker_jobs:
                    raise ServiceError("unsupported_job", "WOFF/WOFF2 export is not advertised by the external worker")
                if request["options"]["verification"]["shapingCases"] and "font.verify.shaping.v1" not in worker_jobs:
                    raise ServiceError("unsupported_job", "HarfBuzz shaping verification is not advertised by the external worker")
        status = getattr(self.worker, "status", None)
        needs_worker = not (kind == "feature_compile" and request["options"]["mode"] == "live")
        if needs_worker and callable(status) and not status().get("available"):
            raise ServiceError("worker_unavailable", "the external Glyphs worker is unavailable")
        return request

    def get_job(self, job_id: str, *, include_preview: bool = True) -> dict[str, Any]:
        job = self._job(job_id)
        if job["status"] == "accepting" and job.get("resultKind") == "artifact":
            job = artifact_publication.reconcile(self, job)
            return self._public(job, include_preview=include_preview)
        if job["status"] in {"applying", "accepting", "discarding"} or (
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
            if state == "saved":
                return self._complete_acceptance(
                    job, operation, include_preview=include_preview
                )
            mapped = {
                "applied": "applied",
                "accepting": "accepting",
                "accepted": "accepted",
                "accept_uncertain": "accept_uncertain",
                "discarded": "discarded",
                "failed": "failed",
                "cancelled": "cancelled",
            }.get(state, job["status"])
            operation_error = operation.get("error")
            if state == "accept_uncertain" and isinstance(job.get("saveRequest"), Mapping):
                operation_error = dict(operation_error or {})
                details = saving.observed_details(
                    self, job["saveRequest"], operation.get("nativeSave") or {}
                )
                details.update(operation_error.get("details") or {})
                details["writeAttempted"] = True
                operation_error["details"] = details
            with self._lock:
                current = self._job(job["id"])
                if current != job:
                    return self._public(current, include_preview=include_preview)
                job = self.jobs.update(
                    job["id"], status=mapped, bridgeOperation=operation,
                    error=operation_error,
                    receipt=operation.get("receipt") or job.get("receipt"),
                )
                if mapped in {"discarded", "cancelled", "accepted"}:
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
            accepting = job["status"] == "accepting"
            if accepting and not self.lifecycle.pending:
                details = saving.observed_details(
                    self, job.get("saveRequest") or {}
                )
                details.update({"previousStatus": job["status"], "outcome": "unverified", "restoration": "blocked", "writeAttempted": True})
                return self.jobs.update(job["id"], status="accept_uncertain", error={
                    "code": "bridge_operation_lost",
                    "message": "The native acceptance operation is no longer available; whether the font was saved is unverified. No replay was attempted.",
                    "details": details,
                })
            if (self.lifecycle.pending or uncertain
                    or acknowledgement.get("jobId") != job["id"]
                    or acknowledgement.get("documentId") != job["document"]["id"]):
                return None
            # Missing history may follow a restart or finished-record eviction.
            # Preserve the last observation and artifacts; never infer restoration.
            return self.jobs.update(job["id"], status="accept_uncertain" if accepting else "interrupted", error={
                "code": "bridge_operation_lost",
                "message": (
                    "The native acceptance operation is no longer available; whether the font was saved is unverified. No replay was attempted."
                    if accepting else
                    "The native operation is no longer available; final edits and restoration are unverified. No replay was attempted. Inspect the intended font before preparing new work."
                ),
                "details": {"previousStatus": job["status"], "outcome": "unverified", "restoration": "blocked" if accepting else "unverified"},
            })

    @staticmethod
    def _require_available_operation(job):
        error = job.get("error") or {}
        if job["status"] == "interrupted" and error.get("code") == "bridge_operation_lost":
            raise ServiceError(error["code"], error["message"], details=error.get("details"))

    @mutation
    def apply_job(self, job_id: str, *, include_preview: bool = True, approved_overwrites=None) -> dict[str, Any]:
        job = self._job(job_id)
        self._require_available_operation(job)
        if job.get("resultKind") not in (None, "mutation"):
            raise ServiceError("job_not_applicable", "this job does not produce a live document mutation")
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
        try:
            approved = dimensions.validate_approval(patch["changes"], approved_overwrites)
        except ProtocolError as exc:
            raise ServiceError(exc.code, exc.message) from exc
        self.jobs.update(job["id"], status="applying", overwriteApproval=approved)
        try:
            operation = (self.bridge.apply(patch, approved_overwrites=approved)
                         if job["request"]["kind"] == "dimensions_edit" else self.bridge.apply(patch))
        except Exception as exc:
            certain = isinstance(exc, BridgeClientError) and exc.details.get("execution") != "uncertain"
            self.jobs.update(job["id"], status="ready" if certain else "applying", error=self._error(exc).as_dict())
            raise self._error(exc) from exc
        job = self.jobs.update(job["id"], status="applying", bridgeOperation=operation)
        return self._public(job, include_preview=include_preview)

    @mutation
    def accept_job(
        self,
        job_id: str,
        *,
        destination: str | None = None,
        include_preview: bool = True,
    ) -> dict[str, Any]:
        job = self._job(job_id)
        if job.get("resultKind") == "artifact":
            return artifact_publication.accept(
                self, ServiceError, job,
                destination=destination, include_preview=include_preview,
            )
        return saving.accept_job(
            self, ServiceError, job_id,
            destination=destination, include_preview=include_preview,
        )

    def _complete_acceptance(self, job, operation, *, include_preview=True):
        return saving.complete_acceptance(
            self, job, operation, include_preview=include_preview
        )

    @mutation
    def save_document(
        self, document_id: str, *, destination: str | None = None, _on_prepared=None
    ) -> dict[str, Any]:
        return saving.save_document(
            self, ServiceError, document_id, destination=destination, on_prepared=_on_prepared
        )

    @mutation
    def discard_job(self, job_id: str, *, include_preview: bool = True) -> dict[str, Any]:
        with self._lock:
            job = self._job(job_id)
            self._require_available_operation(job)
            if job["status"] in {"discarded", "cancelled"}:
                return self._public(job, include_preview=include_preview)
            if job["status"] in {"accepted", "accept_uncertain"}:
                raise ServiceError(
                    "job_not_discardable",
                    "An accepted or potentially saved job cannot be discarded automatically",
                )
            if job["status"] == "accepting":
                raise ServiceError(
                    "document_busy", "The job is being validated and saved"
                )
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

    def _document(self, document_id: str) -> dict[str, Any]:
        for document in self.list_documents():
            if document.get("id") == str(document_id):
                return document
        raise ServiceError("document_not_found", "the Glyphs document is no longer open")

    @staticmethod
    def _job_request(kind: str, delta: float | None, glyphs: list[str] | None, options=None) -> dict[str, Any]:
        available = list(JOB_KINDS) + ["outline_edit", "native_action", "feature_compile", "font_export", "dimensions_edit"]
        if str(kind) not in available:
            raise ServiceError("unsupported_job", "supported jobs: " + ", ".join(available))
        if kind == "width_delta" and (isinstance(delta, bool) or not isinstance(delta, (int, float)) or not math.isfinite(float(delta)) or delta == 0):
            raise ServiceError("invalid_request", "delta must be a finite non-zero number")
        names = []
        if glyphs is not None:
            if not isinstance(glyphs, list) or not 1 <= len(glyphs) <= 10_000:
                raise ServiceError("invalid_request", "glyphs must contain 1-10,000 names")
            names = [str(value).strip() for value in glyphs]
            if any(not value for value in names) or len(names) != len(set(names)):
                raise ServiceError("invalid_request", "glyph names must be non-empty and unique")
        if kind in ("spacing", "kerning_collision", "start_nodes", "slant", "outline_edit", "native_action", "feature_compile", "font_export", "dimensions_edit"):
            from .spacing import validate_options as spacing_options
            from .collision import validate_options as collision_options
            from .start_node_job import validate_options as start_options
            from .slant_job import validate_options as slant_options
            from glyphs_mcp_protocol.outline import validate_options as outline_options
            from glyphs_mcp_protocol.native_actions import validate_options as native_action_options
            from glyphs_mcp_protocol.compile_export import (
                validate_compile_options, validate_export_options,
            )
            validate_options = {
                "spacing": spacing_options,
                "kerning_collision": collision_options,
                "start_nodes": start_options,
                "slant": slant_options,
                "outline_edit": outline_options,
                "native_action": native_action_options,
                "feature_compile": validate_compile_options,
                "font_export": validate_export_options,
                "dimensions_edit": dimensions.validate_options,
            }[kind]
            try:
                if delta is not None:
                    raise ValueError(kind + " uses options, not delta")
                if kind == "kerning_collision" and names:
                    raise ValueError("kerning_collision selects explicit pairs in options")
                if kind == "start_nodes" and not 1 <= len(names) <= 100:
                    raise ValueError("start_nodes requires 1-100 explicit glyphs")
                if kind == "outline_edit" and names:
                    raise ValueError("outline_edit selects glyphs inside options.targets")
                if kind in ("native_action", "feature_compile", "font_export", "dimensions_edit") and glyphs is not None:
                    raise ValueError(f"{kind} does not use top-level glyphs")
                return {"kind": kind, "glyphs": names, "options": validate_options({} if options is None else options)}
            except ProtocolError as error:
                raise ServiceError(error.code, error.message) from error
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
            "resultKind": job.get("resultKind") or "mutation",
            "changeCount": int(job.get("changeCount") or 0),
            "sample": list(job.get("sample") or []),
            "report": job.get("report"),
            "manifest": job.get("manifest"),
            "error": job.get("error"),
            "receipt": job.get("receipt"),
            "bridgeOperation": job.get("bridgeOperation"),
            "activity": activity(job),
            "message": (
                "Review the change in Glyphs. Call accept_job to verify and save it; Undo is per glyph. Revert or discard_job restores the whole job."
                if status == "applied"
                else "Review the verified manifest and report. Call accept_job with a new absolute destination directory to publish it."
                if status == "ready" and job.get("resultKind") == "artifact"
                else None
            ),
        }
        if status == "applied" and job.get("request", {}).get("kind") == "dimensions_edit":
            result["message"] = "Dimensions changed without saving. Native document Undo/Redo or discard_job restores the notes. Save separately when authorized."
        if not include_preview:
            result.pop("sample")
            if isinstance(result["report"], dict):
                result["report"] = {k: v for k, v in result["report"].items() if k != "sample"}
            result["previewIncluded"] = False
        return result
