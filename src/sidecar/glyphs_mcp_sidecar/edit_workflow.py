"""Conversation orchestration over the existing, guarded job/save services."""
from copy import deepcopy
import hmac
import json
from threading import Event, RLock, Thread
from . import saving, saved_script
from glyphs_mcp_protocol import scripts

from .edit_workflow_state import (
    ACTIVE, TERMINAL, WorkflowStore, action_token, offered_actions,
    public_workflow, report_needs_review, auto_keep_available,
)

JOB_BUSY = {"preparing", "cancelling", "ready", "applying", "applied", "accepting", "discarding"}
STALE = {"document_not_clean", "stale_document", "stale_source", "source_unavailable"}


class EditWorkflows:
    def __init__(self, service, error_type):
        self.service, self.error = service, error_type
        self.store = WorkflowStore(service.jobs.root)
        self.lock, self.stopped = RLock(), Event()
        self.thread = None
        self.baseline_memos = {}  # Display-only, never persisted or used at dispatch.

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
                    if (value["state"] in ACTIVE and value["state"] != "uncertain"
                            or value["state"] == "ready" and value["mode"] == "apply"):
                        self._guard(value, lambda: self._advance(value))

    def _find(self, identity):
        value = self.store.records.get(str(identity))
        if value is None:
            raise self.error("workflow_not_found", "This workflow is unavailable; do not infer another font.")
        return value

    def _set(self, value, **fields):
        if fields.get('state') in {'saved', 'executed', 'discarded', 'interrupted', 'uncertain'}:
            self.baseline_memos.pop(value['id'], None)
        if any(value.get(key) != item for key, item in fields.items()):
            old, new = value.get('job') or {}, fields.get('job') or {}
            progress_only = (set(fields) == {'job'} and value['state'] == 'applying'
                             and value['request']['kind'] == 'python_script'
                             and old.get('id') == new.get('id') == value.get('jobId')
                             and old.get('status') == new.get('status') == 'applying'
                             and old.get('error') == new.get('error'))
            # Cancel stays usable across progress reads; state/error/identity
            # transitions still invalidate every action, including Run/Restore.
            self.store.update(value, advance_revision=not progress_only, **fields)

    def _guard(self, value, callback, *, recover_state=None):
        try:
            callback()
        except Exception as exc:
            saved_script.invalidate(self.service)
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

    def start(self, document_id, *, kind, idempotency_key, mode="apply", delta=None, glyphs=None, options=None, auto_keep=True):
        if type(auto_keep) is not bool:
            raise self.error('invalid_request', 'auto_keep must be true or false.')
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
                    if (value["document"]["id"] != document_id or value["arguments"] != arguments or value["mode"] != mode
                            or value.get('autoKeepRequested', auto_keep) != auto_keep):
                        raise self.error("idempotency_conflict", "This idempotency key belongs to another edit request.")
                    return public_workflow(value)
            document = self.service._document(document_id)
            request = self.service.validate_job_request(**arguments)
            if type(document.get("generation")) is not int:
                raise self.error("generation_unavailable", "Glyphs did not expose an edit generation.")
            peers = [v for v in self.store.records.values() if v["document"]["id"] == document_id
                     and (v["state"] not in TERMINAL or saved_script.unresolved(v.get('job') or {}))]
            for peer in peers:
                if peer.get("jobId") and peer["state"] in {"applied", "ready", "needs_review"}:
                    self._guard(peer, lambda: self._advance(peer, allow_apply=False))
            peers = [p for p in peers if p["state"] not in TERMINAL or saved_script.unresolved(p.get('job') or {})]
            if len(peers) >= 2 or any(not p.get("jobId") or p["state"] in {"uncertain", "interrupted"} for p in peers):
                raise self.error("workflow_busy", "Resolve the existing request for this font first.",
                                 details={"workflowId": peers[-1]["id"]})
            value = self.store.create(document, arguments, request, mode, idempotency_key, auto_keep=auto_keep)
            blockers = [j for j in self.service.jobs.records()
                        if j["document"]["id"] == document_id and (j["status"] in JOB_BUSY or saved_script.unresolved(j))]
            if blockers:
                self._set(value, blockerId=blockers[0]["id"], state="blocked_active")
                self._guard(value, lambda: self._advance(value))
            else:
                self._guard(value, lambda: self._begin(value))
            self._start_runner()
            return public_workflow(value, include_warning=True)

    def get(self, workflow_id, *, include_review=False):
        with self.lock:
            value = self._find(workflow_id)
            fast_ready = value['state'] == 'preparing'
            if value.get('blockerId') or (value.get("jobId") and (fast_ready or saved_script.unresolved(value.get('job') or {}) or value["state"] in {"applied", "ready", "needs_review", "waiting_run", "uncertain"})):
                self._guard(value, lambda: self._advance(value, allow_apply=False))
            if value["state"] in {"applied", "saved"}:
                try:
                    self._set(value, document=self.service._document(value["document"]["id"]), documentStateConfirmed=True)
                except Exception:
                    self._set(value, documentStateConfirmed=False)  # Historical receipt stays valid.
            saved_script.refresh(self.service, value)
            return public_workflow(value, include_review=include_review)

    def respond(self, workflow_id, expected_revision, action_token_value, *, destination=None, approved_overwrites=None, automatic=False):
        if type(automatic) is not bool:
            raise self.error('invalid_request', 'automatic must be true or false.')
        with self.lock, self.service.lifecycle.mutation():
            value = self._find(workflow_id)
            # Preserve old explicit-action signatures for reconnect retries.
            signature = json.dumps([destination, approved_overwrites] + ([True] if automatic else []), sort_keys=True)
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
            if automatic and (action not in {'finish_script', 'finish_edit'} or not auto_keep_available(value)):
                raise self.error('invalid_request', 'Automatic selection is only available for Keep after a successful edit.')
            if as_action and not destination or destination is not None and not as_action:
                raise self.error("invalid_request", "A destination is required only for Save As actions.")
            if approved_overwrites is not None and action != "apply":
                raise self.error("invalid_request", "Overwrite approval belongs only to Apply changes.")
            # Record consumption before any side effect; a lost response cannot replay it.
            previous_state = value["state"]
            value["usedActions"][action_token_value] = signature
            self.store.update(value, pendingAction=action, error=None,
                              responseOrigin='card_timeout' if automatic else 'explicit_action')
            self._guard(value, lambda: self._respond(value, action, destination, approved_overwrites), recover_state=previous_state)
            self.store.update(value, pendingAction=None)
            saved_script.refresh(self.service, value)
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
        if not document.get("path") or (document.get("dirty") is not False and value["request"]["kind"] != "python_script"):
            self._set(value, state="waiting_save")
            return
        self._set(value, state="preparing", error=None, reviewInConversation=False)
        extra = {'_workflow': True} if value['request']['kind'] == 'python_script' else {}
        job = self.service.start_job(document["id"], **value["arguments"], **extra)
        self._set(value, jobId=job["id"], job=job)

    def _advance(self, value, *, allow_apply=True):
        if value.get("blockerId"):
            job = self.service.get_job(value["blockerId"])
            original = next((w for w in self.store.records.values() if w.get('jobId') == job['id']), None)
            self._set(value, job=job, blockingWorkflowId=original['id'] if original else None)
            if job["status"] in {"accepted", "discarded", "completed", "cancelled"} and not saved_script.unresolved(job):
                restored = ((job.get('bridgeOperation') or {}).get('scriptResult') or {})
                if restored.get('savedVersionRestored') and restored.get('documentAfter'):
                    # Only this operation's authoritative reload can replace a binding.
                    self._set(value, document=restored['documentAfter'])
                self._set(value, blockerId=None, blockingWorkflowId=None, job=None, error=None)
                self._begin(value)
            elif job["status"] == "applied" or saved_script.unresolved(job):
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
        restored = (job.get('bridgeOperation') or {}).get('scriptResult') or {}
        if state == 'discarded' and restored.get('savedVersionRestored') and restored.get('documentAfter'):
            self._set(value, document=restored['documentAfter'], savedVersion=None)
        if state == 'completed' and job.get('resultKind') in {'script', 'mutation'}:
            self._set(value, state='executed')
            return
        if state == "ready":
            if value['state'] == 'uncertain' and value['request']['kind'] == 'python_script' and value.get('saveRequest'):
                return
            if job.get('resultKind') == 'script':
                self._set(value, state='waiting_run')
                return
            if report_needs_review(self.service, job):
                self._set(value, state="needs_review", reviewInConversation=value['request']['kind'] != 'python_script' and report_needs_review(self.service, job, include_overwrites=False))
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
        if action == 'wait_for_answer':
            self._set(value, autoKeepEnabled=False)
            return
        if action == 'acknowledge_script_outcome':
            from .script_service import acknowledge_lost
            job = acknowledge_lost(self.service, value, self.error)
            self._set(value, job=job, state='executed', savedVersion=None)
            return
        if action == 'restore_saved_script':
            with self.service._script_dispatch_lock:
                saved_script.restore(self.service, value, self.error)
            return
        if action in {'run_script', 'save_run_script'}:
            self._set(value, state='applying')
            job = self.service.run_script(value['jobId'], value['id'])
            self._set(value, job=job)
            return
        if action in {'finish_script', 'finish_edit'}:
            finish = self.service.finish_script if action == 'finish_script' else self.service.finish_edit
            job = finish(value['jobId'])
            self._set(value, job=job, state='executed', savedVersion=None)
            return
        if action == "check_outcome":
            if value['request']['kind'] == 'python_script' and value.get('jobId') and saved_script.reconcile_save(self.service, value, self.error):
                return
            # Read/reconcile only; never resume preparation or replay a saved intent.
            if value.get("blockerId"):
                self._advance(value, allow_apply=False)
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
        if action in {"keep_previous", "save_previous", "discard_previous"}:
            self._document(value)
            call = {"keep_previous": self.service.finish_edit, "save_previous": self.service.accept_job,
                    "discard_previous": self.service.discard_job}[action]
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
