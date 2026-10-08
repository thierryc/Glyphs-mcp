"""Guarded job/save service and conversational workflow facade."""

from __future__ import annotations

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
from glyphs_mcp_protocol import dimensions, scripts

from .checkpoint_git import CheckpointError
from . import checkpoints, checkpoint_restore
from .bridge_client import BridgeClientError
from .jobs import JobStore
from .identity import IDENTITY, VERSION
from .lifecycle import ServiceLifecycle, activity, mutation
from . import saving, saved_script
from . import artifact_publication
from .script_service import mutation_guard
from .source import SourceError, snapshot_source, source_hash
from .worker import GlyphsCliWorker
from . import job_preparation

from .job_requests import JOB_KINDS
OUTLINE_WRITE_CAPABILITIES = ("outline.edit.v1", "outline.remove-node.v1", "outline.background.edit.v1")
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
        self._lock, self._script_dispatch_lock = RLock(), RLock()
        self._checkpoint_lock = RLock()
        self.lifecycle = ServiceLifecycle(self, ServiceError)
        for job in self.jobs.records():
            from .script_service import invalidate_retired_review
            if invalidate_retired_review(self.jobs, job):
                continue
            if job["status"] in {"preparing", "cancelling"}:
                self.jobs.update(job["id"], status="interrupted", error={
                    "code": "service_interrupted",
                    "message": "The previous service stopped during preparation. This job was not resubmitted.",
                })
            elif job["status"] == "accepting":
                if job.get('resultKind') == 'checkpoint':
                    continue  # Reconcile the existing save on demand, never replay it.
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
                        + (["checkpoint_restore"] if "font.checkpoint-restore.v1" in advertised_writes else [])
                        + (['python_script'] if scripts.NATIVE in job_capabilities else [])
                        + (["outline_edit"] if "outline.edit.v1" in advertised_writes else [])
                        + (["native_action"] if native_actions else [])
                        + (["dimensions_edit"] if dimensions.WRITE_CAPABILITY in advertised_writes else [])
                        + (["kerning_edit"] if "kerning.edit.exact.v1" in advertised_writes else [])
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
            "writeCapabilities": [name for name in (*OUTLINE_WRITE_CAPABILITIES, NATIVE_WRITE_CAPABILITY, dimensions.WRITE_CAPABILITY, "kerning.edit.exact.v1", "font.checkpoint-restore.v1", "document.create.v1", "document.open.v1")
                                  if name in advertised_writes and (name != NATIVE_WRITE_CAPABILITY or native_actions)],
            "nativeActions": native_actions,
            "jobCapabilities": job_capabilities,
            "tools": list(TOOL_NAMES),
            "bridge": bridge,
            "worker": worker,
            "controlProtocol": 1,
            "workflowCapabilities": ["edit.workflow.v1", "font.checkpoints.v1"],
            "activity": self.lifecycle.snapshot(),
            "acceptance": "Call accept_job to verify and save an applied job. apply_job remains reversible and never saves.",
        }

    def list_documents(self) -> list[dict[str, Any]]:
        try:
            return self.bridge.documents()
        except Exception as exc:
            raise self._error(exc) from exc

    @mutation
    def create_document(self, family_name: str, idempotency_key: str, units_per_em: int = 1000) -> dict[str, Any]:
        from . import document_creation
        try:
            return document_creation.create(self, ServiceError, family_name, idempotency_key, units_per_em)
        except Exception as exc:
            raise self._error(exc) from exc

    @mutation
    def open_document(self, path: str, idempotency_key: str) -> dict[str, Any]:
        from . import document_opening
        try:
            return document_opening.open_document(self, ServiceError, path, idempotency_key)
        except Exception as exc:
            raise self._error(exc) from exc

    def read_entities(
        self, document_id: str, entities: list[dict[str, Any]], fields: list[str]
    ) -> list[dict[str, Any]]:
        try:
            if any(str(item.get('kind','')).startswith('checkpoint_') for item in entities):
                from .checkpoint_history import read
                return read(self, str(document_id), entities, fields)
            return self.bridge.read_entities(str(document_id), entities, fields)
        except Exception as exc:
            raise self._error(exc) from exc

    @mutation
    @mutation_guard
    def start_job(
        self,
        document_id: str,
        *,
        kind: str,
        delta: float | None = None,
        glyphs: list[str] | None = None,
        options: dict[str, Any] | None = None,
        _workflow: bool = False,
    ) -> dict[str, Any]:
        if kind == 'checkpoint_restore':
            return checkpoint_restore.prepare(self, self._document(document_id), self.validate_job_request(kind, delta, glyphs, options))
        if kind == 'python_script' and not _workflow:
            raise ServiceError('workflow_required', 'native scripts require start_edit_workflow and its revision-bound Run action')
        document = self._document(document_id)
        if not document.get("path"):
            raise ServiceError("document_path_required", "Save or Save As before starting a large job")
        if document.get("dirty") is not False and not (_workflow and kind == 'python_script'):
            raise ServiceError("document_not_clean", "Save the font before starting a large job")
        if not isinstance(document.get("generation"), int):
            raise ServiceError("generation_unavailable", "Glyphs did not expose a bounded edit generation")
        request = self.validate_job_request(kind, delta, glyphs, options)
        native_prepare = self._native_preparation_available(request)
        job = self.jobs.create(document, request)
        cancel = Event()
        with self._lock:
            self._cancellations[job["id"]] = cancel
        if native_prepare:
            self.jobs.update(job["id"], preparationRoute="native")
        live_compile = kind == "feature_compile" and request["options"]["mode"] == "live"
        thread = Thread(
            target=(job_preparation.prepare_live_compile if live_compile else
                    job_preparation.prepare_native_typed if native_prepare else job_preparation.prepare_external),
            args=(self, job["id"], cancel),
            name="glyphs-mcp-" + job["id"],
            daemon=True,
        )
        thread.start()
        return self._public(job)

    def _native_preparation_available(self, request, bridge_status=None):
        from glyphs_mcp_protocol.preparation.simple import CAPABILITY, eligible
        if not eligible(request):
            return False
        status = bridge_status if bridge_status is not None else self.bridge.status()
        available = CAPABILITY in status.get("jobCapabilities", [])
        if request["kind"] == "kerning_edit" and (not available or "kerning.edit.exact.v1" not in status.get("writeCapabilities", [])):
            raise ServiceError("unsupported_job", "exact kerning native preparation is unavailable")
        return available

    def validate_job_request(self, kind, delta=None, glyphs=None, options=None):
        """Shared nonmutating preflight, including dirty/pathless workflow requests."""
        if kind == 'checkpoint_restore':
            return checkpoint_restore.validate(self, kind, delta, glyphs, options, ServiceError)
        request = self._job_request(kind, delta, glyphs, options)
        if kind == 'python_script':
            from .script_service import validate_capabilities
            validate_capabilities(self, request['options'], ServiceError)
            return request
        native_prepare = False
        if kind in ("outline_edit", "native_action", "feature_compile", "font_export", "dimensions_edit", "python_script", "kerning_edit"):
            try:
                bridge_status = self.bridge.status()
                advertised = bridge_status.get("writeCapabilities") or []
            except Exception:
                bridge_status = {}
                advertised = []
            if kind == "kerning_edit" and ("kerning.edit.exact.v1" not in advertised or not self._native_preparation_available(request, bridge_status)):
                raise ServiceError("unsupported_job", "exact kerning edits require a qualified native bridge; update the installation")
            if kind == "dimensions_edit" and dimensions.WRITE_CAPABILITY not in advertised:
                raise ServiceError("unsupported_job", "Dimensions writes are not qualified by the live bridge")
            if kind == "outline_edit" and "outline.edit.v1" not in advertised:
                raise ServiceError("unsupported_job", "outline_edit requires bridge capability outline.edit.v1")
            if (kind == "outline_edit"
                    and any(t.get("surface") == "background" for t in request["options"]["targets"])
                    and "outline.background.edit.v1" not in advertised):
                raise ServiceError("unsupported_job", "background edits require bridge capability outline.background.edit.v1")
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
            native_prepare = self._native_preparation_available(request, bridge_status)
            bridge_jobs = recognized_job_capabilities(bridge_status.get("jobCapabilities"))
            worker_status = self.worker.status() if kind in {"feature_compile", "font_export"} and callable(getattr(self.worker, "status", None)) else {"available": True}
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
        if kind == "width_delta":
            native_prepare = self._native_preparation_available(request)
        needs_worker = not native_prepare and not (kind == "feature_compile" and request["options"]["mode"] == "live")
        if needs_worker and callable(status) and not status().get("available"):
            raise ServiceError("worker_unavailable", "the external Glyphs worker is unavailable")
        return request

    def get_job(self, job_id: str, *, include_preview: bool = True) -> dict[str, Any]:
        job = self._job(job_id)
        if job.get('resultKind') == 'checkpoint':
            from .checkpoints import reconcile_save
            return reconcile_save(self, job)
        if job["status"] == "accepting" and job.get("resultKind") == "artifact":
            job = artifact_publication.reconcile(self, job)
            return self._public(job, include_preview=include_preview)
        if saved_script.unresolved(job) or job["status"] in {"applying", "applied", "accepting", "discarding"}:
            try:
                operation = self.bridge.operation(job["id"])
            except Exception as exc:
                interrupted = self._interrupt_missing_operation(job, exc)
                if interrupted is not None:
                    return self._public(interrupted, include_preview=include_preview)
                raise self._error(exc) from exc
            if operation.get('documentAfter') and job.get('resultKind') == 'historical_restore':
                job = self.jobs.update(job['id'], document=operation['documentAfter'])
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
                "completed": "completed",
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
                if mapped in {"discarded", "cancelled", "accepted"} or mapped == "completed" and job.get("resultKind") == "mutation":
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
    @mutation_guard
    def run_script(self, job_id, workflow_id):
        from . import script_service
        return script_service.run(self, job_id, workflow_id, ServiceError)

    @mutation
    def finish_script(self, job_id):
        from . import script_service
        return script_service.finish(self, job_id, ServiceError)

    @mutation
    @mutation_guard
    def finish_edit(self, job_id):
        job = self._job(job_id)
        if (job.get('resultKind') not in {'mutation','historical_restore'} or job['status'] not in {'applied', 'completed'}
                or job.get('error') or job.get('outcome') == 'unverified'):
            raise ServiceError('job_not_ready', 'only a successfully applied edit can be kept')
        if job['status'] == 'completed':
            self.jobs.release_bulk_artifacts(job_id)
            return self._public(job)
        operation = self.bridge.finish_edit(job_id)
        job = self.jobs.update(job_id, status='completed', bridgeOperation=operation)
        self.jobs.release_bulk_artifacts(job_id)
        return self._public(job)

    @mutation
    @mutation_guard
    def apply_job(self, job_id: str, *, include_preview: bool = True, approved_overwrites=None) -> dict[str, Any]:
        job = self._job(job_id)
        self._require_available_operation(job)
        if job.get('resultKind') == 'historical_restore':
            return checkpoint_restore.apply(self, job, ServiceError)
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
        checkpoints.establish_typed_baseline(self, job, patch)
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
    @mutation_guard
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
    @mutation_guard
    def save_document(
        self, document_id: str, *, destination: str | None = None, _on_prepared=None, retry_checkpoint_job_id=None
    ) -> dict[str, Any]:
        return saving.save_document(
            self, ServiceError, document_id, destination=destination, on_prepared=_on_prepared, retry_checkpoint_job_id=retry_checkpoint_job_id
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
                if job.get("preparationRoute") == "native":
                    self.bridge.discard(job["id"])
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
    def _job_request(kind, delta, glyphs, options=None):
        from .job_requests import validate
        return validate(kind, delta, glyphs, options, ServiceError)

    def _job(self, job_id: str) -> dict[str, Any]:
        try:
            return self.jobs.get(str(job_id))
        except KeyError as exc:
            raise ServiceError("job_not_found", "the job does not exist") from exc

    @staticmethod
    def _error(exc: Exception) -> ServiceError:
        if isinstance(exc, ServiceError):
            return exc
        if isinstance(exc, (BridgeClientError, CheckpointError)):
            return ServiceError(exc.code, exc.message, details=exc.details)
        return ServiceError("bridge_failed", str(exc) or exc.__class__.__name__)

    @staticmethod
    def _public(job: Mapping[str, Any], *, include_preview: bool = True) -> dict[str, Any]:
        from .job_view import public_job
        return public_job(job, include_preview=include_preview)
