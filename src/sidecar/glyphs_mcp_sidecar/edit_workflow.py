"""Conversation orchestration over the existing, guarded job/save services."""
from copy import deepcopy
import hmac
import json
from threading import Event, RLock, Thread
from . import saving

from .edit_workflow_state import (
    ACTIVE, TERMINAL, WorkflowStore, action_token, offered_actions,
    public_workflow, report_needs_review,
)

JOB_BUSY = {"preparing", "cancelling", "ready", "applying", "applied", "accepting", "discarding"}
STALE = {"document_not_clean", "stale_document", "stale_source", "source_unavailable"}


class EditWorkflows:
    def __init__(self, service, error_type):
        self.service, self.error = service, error_type
        self.store = WorkflowStore(service.jobs.root)
        self.lock, self.stopped = RLock(), Event()
        self.thread = None

    def close(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=5)

    def _start_runner(self):
        if self.thread is None:
            self.thread = Thread(target=self._run, name="glyphs-edit-workflows", daemon=True)
            self.thread.start()

    def _run(self):
        while not self.stopped.wait(.25):
            with self.lock:
                for value in list(self.store.records.values()):
                    if self.stopped.is_set():
                        return
                    if value["state"] in ACTIVE and value["state"] != "uncertain":
                        self._guard(value, lambda: self._advance(value))

    def _find(self, identity):
        value = self.store.records.get(str(identity))
        if value is None:
            raise self.error("workflow_not_found", "This workflow is unavailable; do not infer another font.")
        return value

    def _set(self, value, **fields):
        if any(value.get(key) != item for key, item in fields.items()):
            self.store.update(value, **fields)

    def _guard(self, value, callback, *, recover_state=None):
        try:
            callback()
        except Exception as exc:
            error = self.service._error(exc).as_dict()
            details = error.get("details") or {}
            uncertain = details.get("execution") == "uncertain" or details.get("writeAttempted") is True
            state = "uncertain" if uncertain else "outdated" if error["code"] in STALE else "failed"
            # A failed/unknown apply or discard call can already have entered native execution.
            if value.get("jobId") or value.get("blockerId"):
                try:
                    job = self.service.jobs.get(value.get("jobId") or value["blockerId"])
                except (KeyError, OSError):
                    job = {}
                if job.get("status") in {"applying", "accepting", "discarding", "accept_uncertain"}:
                    state = "uncertain"
                elif state == "outdated" and job.get("status") == "applied":
                    state = "applied"  # Never turn an applied result into a reprepare/discard shortcut.
            if state == "failed" and recover_state and error["code"] not in {"document_not_found", "bridge_failed", "job_not_found"}:
                state = recover_state
            self._set(value, state=state, error=error)

    def start(self, document_id, *, kind, idempotency_key, mode="apply", delta=None, glyphs=None, options=None):
        if mode not in {"apply", "preview"} or not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128:
            raise self.error("invalid_request", "Use apply/preview mode and a stable 1-128 character idempotency key.")
        if kind in {"feature_compile", "font_export"}:
            raise self.error("unsupported_job", "Edit workflows support mutation jobs only; use the existing diagnostic/export tools.")
        arguments = dict(kind=kind, delta=delta, glyphs=deepcopy(glyphs), options=deepcopy(options))
        with self.lock, self.service.lifecycle.mutation():
            if self.stopped.is_set():
                raise self.error("service_stopped", "The workflow service is stopping.")
            for value in self.store.records.values():
                if value["idempotencyKey"] == idempotency_key:
                    if value["document"]["id"] != document_id or value["arguments"] != arguments or value["mode"] != mode:
                        raise self.error("idempotency_conflict", "This idempotency key belongs to another edit request.")
                    return public_workflow(value)
            document = self.service._document(document_id)
            request = self.service.validate_job_request(**arguments)
            if type(document.get("generation")) is not int:
                raise self.error("generation_unavailable", "Glyphs did not expose an edit generation.")
            peers = [v for v in self.store.records.values() if v["document"]["id"] == document_id and v["state"] not in TERMINAL]
            for peer in peers:
                if peer.get("jobId") and peer["state"] in {"applied", "ready", "needs_review"}:
                    self._guard(peer, lambda: self._advance(peer, allow_apply=False))
            peers = [p for p in peers if p["state"] not in TERMINAL]
            if len(peers) >= 2 or any(not p.get("jobId") or p["state"] in {"uncertain", "interrupted"} for p in peers):
                raise self.error("workflow_busy", "Resolve the existing request for this font first.",
                                 details={"workflowId": peers[-1]["id"]})
            value = self.store.create(document, arguments, request, mode, idempotency_key)
            blockers = [j for j in self.service.jobs.records()
                        if j["document"]["id"] == document_id and j["status"] in JOB_BUSY]
            if blockers:
                self._set(value, blockerId=blockers[0]["id"], state="blocked_active")
                self._guard(value, lambda: self._advance(value))
            else:
                self._guard(value, lambda: self._begin(value))
            self._start_runner()
            return public_workflow(value)

    def get(self, workflow_id):
        with self.lock:
            value = self._find(workflow_id)
            if value.get("jobId") and not value.get("blockerId") and value["state"] in {"applied", "ready", "needs_review", "uncertain"}:
                self._guard(value, lambda: self._advance(value, allow_apply=False))
            if value["state"] in {"applied", "saved"}:
                try:
                    self._set(value, document=self.service._document(value["document"]["id"]))
                except Exception:
                    pass  # A receipt remains valid after closing its document.
            return public_workflow(value)

    def respond(self, workflow_id, expected_revision, action_token_value, *, destination=None, approved_overwrites=None):
        with self.lock, self.service.lifecycle.mutation():
            value = self._find(workflow_id)
            signature = json.dumps([destination, approved_overwrites], sort_keys=True)
            used = value["usedActions"].get(str(action_token_value))
            if used is not None:
                if used != signature:
                    raise self.error("action_conflict", "This action token was already used with different values.")
                return public_workflow(value)
            actions = dict(offered_actions(value))
            action = next((name for name in actions if isinstance(action_token_value, str)
                           and hmac.compare_digest(action_token(value, name), action_token_value)), None)
            if type(expected_revision) is not int or expected_revision != value["revision"] or action is None:
                raise self.error("stale_workflow_action", "This choice is outdated. Refresh this workflow before choosing again.",
                                 details={"workflowId": value["id"]})
            as_action = action in {"save_as_continue", "save_result_as"}
            if as_action and not destination or destination is not None and not as_action:
                raise self.error("invalid_request", "A destination is required only for Save As actions.")
            if approved_overwrites is not None and action != "apply":
                raise self.error("invalid_request", "Overwrite approval belongs only to Apply changes.")
            # Record consumption before any side effect; a lost response cannot replay it.
            previous_state = value["state"]
            value["usedActions"][action_token_value] = signature
            self.store.update(value, pendingAction=action, error=None)
            self._guard(value, lambda: self._respond(value, action, destination, approved_overwrites), recover_state=previous_state)
            self.store.update(value, pendingAction=None)
            self._start_runner()
            return public_workflow(value)

    def _document(self, value, *, allow_path_change=False):
        document = self.service._document(value["document"]["id"])
        if not allow_path_change and document.get("path") != value["document"].get("path"):
            raise self.error("stale_document", "The font's path changed. Check the intended document before continuing.")
        value["document"] = document
        return document

    def _begin(self, value):
        document = self._document(value, allow_path_change=True)
        self.service.validate_job_request(**value["arguments"])
        if not document.get("path") or document.get("dirty") is not False:
            self._set(value, state="waiting_save")
            return
        self._set(value, state="preparing", error=None, reviewInConversation=False)
        job = self.service.start_job(document["id"], **value["arguments"])
        self._set(value, jobId=job["id"], job=job)

    def _advance(self, value, *, allow_apply=True):
        if value.get("blockerId"):
            job = self.service.get_job(value["blockerId"])
            self._set(value, job=job)
            if job["status"] in {"accepted", "discarded", "cancelled"}:
                self._set(value, blockerId=None, job=None)
                self._begin(value)
            elif job["status"] == "applied":
                self._set(value, state="blocked_review")
            elif job["status"] == "ready":
                self._set(value, state="blocked_proposal")
            elif job["status"] in {"failed", "interrupted", "accept_uncertain"}:
                self._set(value, state="interrupted", error=job.get("error"))
            return
        if not value.get("jobId"):
            return
        job = self.service.get_job(value["jobId"])
        self._set(value, job=job)
        state = job["status"]
        if state == "ready":
            if report_needs_review(self.service, job):
                self._set(value, state="needs_review", reviewInConversation=report_needs_review(self.service, job, include_overwrites=False))
            elif not job["changeCount"] and allow_apply:
                self.service.discard_job(job["id"])
                self._set(value, state="no_changes")
            elif value["mode"] == "preview" or not allow_apply:
                self._set(value, state="ready")
            else:
                self._apply(value)
        else:
            mapped = {"accepted": "saved", "accepting": "saving", "accept_uncertain": "uncertain",
                      "cancelling": "discarding"}.get(state, state)
            if value.get("cancelRequested") and state in {"cancelled", "discarded"}:
                mapped = "cancelled"
            self._set(value, state=mapped, error=job.get("error"), receipt=job.get("receipt") or value.get("receipt"))

    def _apply(self, value, approved_overwrites=None):
        self._document(value)
        self._set(value, state="applying")
        job = self.service.apply_job(value["jobId"], approved_overwrites=approved_overwrites)
        self._set(value, job=job)

    def _respond(self, value, action, destination, approved_overwrites):
        if action == "check_outcome":
            # Read/reconcile only; never resume preparation or replay a saved intent.
            if value.get("blockerId"):
                job = self.service.get_job(value["blockerId"])
                self._set(value, job=job)
                if job["status"] in {"accepted", "discarded", "cancelled", "applied", "ready"}:
                    self._set(value, state="blocked_proposal" if job["status"] == "ready" else "blocked_review" if job["status"] == "applied" else "waiting_manual", error=None)
            elif value.get("jobId"):
                self._advance(value, allow_apply=False)
            elif value.get("saveRequest"):
                request = value["saveRequest"]
                operation = self.service.bridge.save_operation(request["saveId"])
                self._set(value, saveOperation=operation)
                if operation.get("status") == "saved":
                    try:
                        receipt = saving.verify_save(request, operation.get("native") or {})
                    except saving.SaveError as exc:
                        raise saving.service_error(exc, self.error) from exc
                    self._set(value, state="waiting_manual", receipt=receipt, error=None)
            return
        if action == "cancel":
            if value.get("jobId"):
                job = self.service.discard_job(value["jobId"])
                self._set(value, job=job, state="discarding", cancelRequested=True)
            else:
                self._set(value, state="cancelled")
            return
        if action == "manual_save":
            if value.get("jobId"):
                self.service.discard_job(value["jobId"])
                self._set(value, jobId=None, job=None)
            self._set(value, state="waiting_manual")
            return
        if action in {"save_previous", "discard_previous"}:
            self._document(value)
            call = self.service.accept_job if action == "save_previous" else self.service.discard_job
            self._set(value, state="resolving")
            job = call(value["blockerId"])
            self._set(value, job=job)
            return
        if action == "check_continue" and value.get("blockerId"):
            self._advance(value)
            return
        if action in {"check_continue", "reprepare", "save_reprepare", "save_continue", "save_as_continue"}:
            self._document(value, allow_path_change=action in {"check_continue", "reprepare"})
            self.service.validate_job_request(**value["arguments"])
            if value.get("jobId"):
                self.service.discard_job(value["jobId"])
                self._set(value, jobId=None, job=None)
            if action.startswith("save_"):
                self._set(value, state="saving")
                receipt = self.service.save_document(value["document"]["id"], destination=destination,
                    _on_prepared=lambda request: self._set(value, saveRequest=request))
                self._set(value, receipt=receipt)
            self._begin(value)
        elif action == "apply":
            self._apply(value, approved_overwrites)
        elif action in {"save_result", "save_result_as"}:
            self._document(value)
            self._set(value, state="saving")
            job = self.service.accept_job(value["jobId"], destination=destination)
            self._set(value, job=job)
        elif action == "discard":
            self._document(value)
            self._set(value, state="discarding")
            job = self.service.discard_job(value["jobId"])
            self._set(value, job=job)
