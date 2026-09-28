"""Small persistent interaction records; no font snapshots or mutation replay."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4
from glyphs_mcp_protocol import scripts
from .saved_script import unresolved

TERMINAL = {"saved", "discarded", "cancelled", "no_changes", "failed", "executed"}
ACTIVE = {"preparing", "applying", "saving", "discarding", "blocked_active", "blocked_review", "blocked_proposal", "resolving", "uncertain"}


class WorkflowStore:
    def __init__(self, root):
        self.root = Path(root) / "edit-workflows"
        self.records = {}
        self._active, self._keys, self._jobs, self._peers = {}, {}, {}, {}
        self._memberships = {}
        if self.root.is_dir():
            for path in sorted(self.root.glob("edit_*.json")):
                try:
                    value = json.loads(path.read_text())
                    if value["id"] != path.stem or value.get("version") != 1:
                        continue
                    self.records[value["id"]] = value
                    self._remember(value)
                    if value["state"] not in TERMINAL and value["state"] != "interrupted":
                        value["resumeState"] = value["state"]
                        self.update(value, state="interrupted", error={
                            "code": "workflow_interrupted",
                            "message": "The service restarted. No save or edit was replayed. Check the existing outcome before starting new work.",
                        })
                except (OSError, ValueError, KeyError, TypeError):
                    continue

    def create(self, document, arguments, request, mode, key, *, auto_keep=False):
        value = dict(version=1, id="edit_" + uuid4().hex, nonce=uuid4().hex,
                     document=deepcopy(document), arguments=deepcopy(arguments), request=request,
                     mode=mode, idempotencyKey=key, state="starting", revision=0,
                     jobId=None, blockerId=None, job=None, error=None, receipt=None,
                     usedActions={}, createdAt=time.time(), autoKeepRequested=auto_keep,
                     autoKeepEnabled=auto_keep)
        self.records[value["id"]] = value
        self.update(value)
        return value

    def update(self, value, *, advance_revision=True, **fields):
        value.update(deepcopy(fields))
        if advance_revision:
            value["revision"] += 1
        value["updatedAt"] = time.time()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self.root / (value["id"] + ".json")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True))
        temporary.chmod(0o600)
        temporary.replace(path)
        self._remember(value)

    def _remember(self, value):
        identity = value['id']
        active = (value['state'] in ACTIVE - {'uncertain'}
                  or value['state'] == 'ready' and value['mode'] == 'apply')
        peer = value['state'] not in TERMINAL or unresolved(value.get('job') or {})
        membership = (value['idempotencyKey'], value.get('jobId'), value['document']['id'] if peer else None)
        previous = self._memberships.get(identity, (None, None, None))
        for index, mapping in enumerate((self._keys, self._jobs, self._peers)):
            old, new = previous[index], membership[index]
            if old != new and old is not None:
                mapping[old].pop(identity, None)
                if not mapping[old]:
                    del mapping[old]
            if new is not None:
                mapping.setdefault(new, {})[identity] = None
        self._memberships[identity] = membership
        if active:
            self._active[identity] = None
        else:
            self._active.pop(identity, None)

    def active_records(self):
        return [self.records[key] for key in self._active]

    def matching_key(self, key):
        return next((self.records[identity] for identity in self._keys.get(key, ())), None)

    def matching_job(self, job_id):
        return next((self.records[key] for key in self._jobs.get(job_id, ())), None)

    def peers(self, document_id):
        return [self.records[key] for key in self._peers.get(document_id, ())]


def action_token(value, action):
    text = f'{value["nonce"]}:{value["revision"]}:{action}'
    return hashlib.sha256(text.encode()).hexdigest()


def report_needs_review(service, job, *, include_overwrites=True):
    """Inspect the complete report, never just its ten-row public sample."""
    report = job.get("report") or {}
    if report.get("path"):
        try:
            report = service.jobs.read_json(job["id"], "report.json")
        except (OSError, ValueError):
            return True
    def incomplete(item):
        if isinstance(item, list):
            return any(incomplete(child) for child in item)
        if not isinstance(item, dict):
            return False
        if item.get("status") in {"unavailable", "skipped", "failed", "error", "partial"}:
            return True
        flags = ("warning", "warnings", "skippedPairs", "unavailableCount", "skippedCount") + (("requiredOverwrites",) if include_overwrites else ())
        if any(item.get(key) for key in flags):
            return True
        return any(incomplete(child) for child in item.values())
    return incomplete(report)


MESSAGES = {
    "waiting_run": "Script ready.",
    "executed": "Changes kept without saving.",
    "waiting_save": "Save your font to continue.",
    "waiting_manual": "Save your font in Glyphs, then continue here.",
    "preparing": "Preparing changes…",
    "ready": "Changes ready to review.",
    "needs_review": "Some changes need your review.",
    "applying": "Applying changes…",
    "applied": "Changes applied.",
    "saving": "Saving font…",
    "discarding": "Discarding changes…",
    "blocked_active": "Waiting for an earlier change to this font.",
    "blocked_review": "Keep, save or undo the earlier changes to continue.",
    "blocked_proposal": "Review the earlier preview to continue.",
    "resolving": "Finishing the earlier change before continuing…",
    "outdated": "Your font has changed. Prepare the changes again.",
    "uncertain": "We couldn’t confirm the result. Check before trying again.",
    "saved": "Font saved.",
    "discarded": "Changes discarded.",
    "cancelled": "Request cancelled.",
    "no_changes": "No changes needed.",
    "failed": "We couldn’t finish this change.",
    "interrupted": "The connection was interrupted. Check the result to continue.",
}

# The first line is also the card heading; supporting copy stays in the same
# message so cards and text-only clients receive identical guidance.
GUIDANCE = {
    "waiting_save": "This saves the whole font, including your existing work. The changes you requested will remain unsaved until you save again.",
    "waiting_manual": "Choose Check and continue once you have saved.",
    "preparing": "You can inspect the font. If you edit it, these changes will need to be prepared again.",
    "ready": "Review the preview, then apply or discard it.",
    "needs_review": "Review the warnings and any changes that were skipped or could not be prepared before applying. Replacing existing values needs your approval.",
    "applied": "Keep ends this workflow’s selective Undo offer without saving. Glyphs’ native Undo/Redo remains available. Saving includes the whole font.",
    "blocked_review": "Saving includes the whole font. Undo affects only the earlier changes and stops if they conflict with later edits.",
    "blocked_proposal": "Return to that preview and apply or discard it first.",
    "outdated": "Preparation uses the current saved version of your font.",
}


def auto_keep_available(value):
    job = value.get('job') or {}
    operation = job.get('bridgeOperation') or {}
    evidence = operation.get('scriptResult') or {}
    return (value.get('autoKeepEnabled') is True and not value.get('blockerId')
            and value['state'] == 'applied'
            and job.get('status') == 'applied' and operation.get('status') == 'applied'
            and (value['request']['kind'] != 'python_script' or
                 evidence.get('executionSucceeded') is True and evidence.get('executed') is True)
            and not value.get('error') and not job.get('error') and not operation.get('error')
            and job.get('outcome') != 'unverified')


def offered_actions(value):
    actions = _offered_actions(value)
    if (value.get('autoKeepEnabled') is True and not value.get('blockerId')
            and value['state'] in {'preparing', 'waiting_save', 'waiting_manual', 'waiting_run', 'applying', 'applied'}):
        actions.append(('wait_for_answer', 'Wait for my answer'))
    return actions


def _offered_actions(value):
    state = value["state"]
    if value['request']['kind'] == 'checkpoint_restore' and state in {'failed','interrupted','uncertain'} and unresolved(value.get('job') or {}):
        return [('check_outcome','Check result'),('acknowledge_restore_outcome','Acknowledge uncertain restore')]
    if state == 'failed' and (value.get('job') or {}).get('status') == 'ready' and str((value.get('error') or {}).get('code','')).startswith('checkpoint_'):
        return [('apply', 'Retry baseline and apply'), ('cancel', 'Cancel')]
    if state == 'saved' and ((value.get('receipt') or {}).get('checkpoint') or {}).get('status') == 'failed':
        return [('retry_checkpoint', 'Retry checkpoint without saving')]
    if value.get('blockerId') and (value.get('job') or {}).get('resultKind') == 'script':
        return [('check_outcome', 'Check result')] if state in {'interrupted', 'uncertain'} else [
            ('check_continue', 'Check and continue'), ('cancel', 'Cancel this request')]
    if value['request']['kind'] == 'python_script':
        job = value.get('job') or {}
        executed = ((job.get('bridgeOperation') or {}).get('scriptResult') or {}).get('executed')
        restore = [('restore_saved_script', 'Restore saved version')] if (value.get('savedVersion') or {}).get('available') else []
        if state == 'waiting_run':
            if scripts.retired(value['request'].get('options', {})):
                return [('cancel', 'Cancel')]
            if value['document'].get('dirty') is not False:
                return [('save_run_script', 'Save and run'), ('manual_save', "I'll save in Glyphs"), ('cancel', 'Cancel')]
            return [('run_script', 'Run script'), ('cancel', 'Cancel')]
        if state == 'applied':
            return [('finish_script', 'Keep changes without saving'), ('save_result', 'Save font')] + restore
        if state in {'failed', 'cancelled'} and executed:
            return [('finish_script', 'Keep changes without saving')] + restore
        if state == 'executed':
            return []
        if state == 'applying':
            return [('cancel', 'Cancel remaining targets')] if value['request']['options'].get('entrypoint', 'per_target') == 'per_target' else []
    save = [("save_continue", "Save and continue")] if value["document"].get("path") else []
    if state == "waiting_save":
        return save + [("save_as_continue", "Save As…"), ("manual_save", "I'll save in Glyphs"), ("cancel", "Cancel")]
    if state == "waiting_manual":
        return [("check_continue", "Check and continue"), ("cancel", "Cancel")]
    if state == "outdated":
        return [("reprepare", "Prepare again")] + ([("save_reprepare", "Save and prepare again")] if save else []) + [("manual_save", "I'll save in Glyphs"), ("cancel", "Cancel")]
    if state in {"ready", "needs_review"}:
        return [("apply", "Apply changes"), ("discard", "Discard preview")]
    if value['request']['kind'] == 'checkpoint_restore' and state == 'applied':
        return [('finish_edit', 'Keep changes without saving'), ('save_result', 'Save font')]
    if state == "applied":
        return [("finish_edit", "Keep changes without saving"), ("save_result", "Save font"), ("save_result_as", "Save As…"), ("discard", "Undo these changes")]
    if state == "blocked_review":
        return [("keep_previous", "Keep earlier changes without saving"), ("save_previous", "Save earlier changes and continue"), ("discard_previous", "Undo earlier changes and continue"), ("cancel", "Cancel this request")]
    if state in {"blocked_active", "blocked_proposal"}:
        return [("check_continue", "Check and continue"), ("cancel", "Cancel this request")]
    if state == "preparing":
        return [("cancel", "Cancel preparation")]
    if state == "interrupted" and not value.get("jobId") and not value.get("saveRequest"):
        return [("check_outcome", "Check result"), ("cancel", "Cancel this request")]
    job = value.get('job') or {}
    if state == 'interrupted' and job.get('resultKind') == 'script' and (job.get('error') or {}).get('code') == 'bridge_operation_lost':
        return [('check_outcome', 'Check result'), ('acknowledge_script_outcome', 'Acknowledge unknown outcome')]
    if state in {"uncertain", "interrupted"}:
        return [("check_outcome", "Check result")]
    return []


def current_save_status(value):
    dirty = value['document'].get('dirty') if value.get('documentStateConfirmed') else None
    return ('The font has unsaved edits.' if dirty is True else
            'The font is currently saved.' if dirty is False else
            'Current save status could not be confirmed.')


def public_workflow(value, *, include_review=False, include_warning=False):
    result = {key: deepcopy(value.get(key)) for key in (
        "id", "revision", "document", "mode", "state", "jobId", "blockerId", "blockingWorkflowId", "job", "error", "receipt", "reviewInConversation", "savedVersion")}
    request = value["request"]
    if value.get('blockerId') and (result.get('job') or {}).get('resultKind') == 'script':
        result['job'] = {k: v for k, v in (result.get('job') or {}).items()
                         if k in {'id', 'status', 'resultKind', 'summary'}}
    options = request.get("options") or {}
    targets = options.get("targets") or options.get("changes") or options.get("pairs") or options.get("edits") or []
    targets = deepcopy(targets if isinstance(targets, dict) else targets[:100])
    result["scope"] = {"kind": request["kind"], "glyphs": request.get("glyphs", [])[:100],
                       "glyphCount": len(request.get("glyphs", [])), "masters": options.get("masters"),
                       "targets": targets}
    if request['kind'] == 'python_script' and isinstance(targets, dict) and isinstance(targets.get('glyphs'), list):
        result['scope']['targetSelectorGlyphCount'] = len(targets['glyphs'])
        result['scope']['targetsTruncated'] = len(targets['glyphs']) > 100
        targets['glyphs'] = targets['glyphs'][:100]
    finish_action = 'finish_script' if request['kind'] == 'python_script' else 'finish_edit'
    result['autoKeep'] = dict(enabled=value.get('autoKeepEnabled') is True, delaySeconds=30,
                             action=finish_action if auto_keep_available(value) else None)
    result['responseOrigin'] = value.get('responseOrigin')
    result['requestFingerprint'] = scripts.digest(request)
    result['documentStateConfirmed'] = value.get('documentStateConfirmed', False)
    if request['kind'] != 'python_script' and not value.get('blockerId') and (result.get('job') or {}).get('summary'):
        result['summary'] = result['job']['summary']
    if request['kind'] == 'python_script':
        result['summary'] = options.get('summary') or 'Run native Python on the requested font scope'
        result['entrypoint'] = options.get('entrypoint', 'per_target')
        if include_review:
            result['scriptReview'] = deepcopy(options)
        # Script evidence is opt-in; polling never repeats source or output.
        job = result.get('job') or {}
        report = job.get('report') or {}
        job['report'] = {k: report[k] for k in ('targetCount', 'skippedCount', 'sample') if k in report}
        job.pop('sample', None)
        job['changeCount'] = None
        op = job.get('bridgeOperation') or {}
        evidence = op.get('scriptResult') or {}
        if not include_review:
            evidence.pop('output', None)
            if op.get('error'):
                op['error'] = {k: op['error'].get(k) for k in ('code', 'message')}
            for item in (job, result):
                if item.get('error'):
                    item['error'] = {k: item['error'].get(k) for k in ('code', 'message')}
        job['message'] = None
        op['message'] = None
        if include_warning:
            result['warning'] = scripts.WARNING
    result["actions"] = [dict(action=name, label=label, token=action_token(value, name),
                              requiresDestination=name in {"save_as_continue", "save_result_as"})
                         for name, label in offered_actions(value)]
    result["message"] = MESSAGES.get(value["state"], "Checking your changes…")
    if guidance := GUIDANCE.get(value["state"]):
        result["message"] += "\n" + guidance
    if value.get("error"):
        result["message"] += "\nCheck your font in Glyphs and review Details before continuing."
    if request['kind'] == 'python_script':
        evidence = ((result.get('job') or {}).get('bridgeOperation') or {}).get('scriptResult') or {}
        messages = {
            'preparing': 'Validating script and resolving targets…',
            'waiting_run': 'Script ready.' if value['document'].get('dirty') is False else 'Save the current font before running.',
            'applying': 'Running script…',
            'applied': 'Script finished. Verify the intended result in Glyphs.',
            'executed': 'Changes kept without saving. This workflow’s restoration offer has ended.',
            'discarded': 'Saved version restored. Subsequent unsaved edits were replaced; external effects remain.',
            'uncertain': 'Result not confirmed. Check the existing result; do not replay the script.',
            'interrupted': 'Result not confirmed. Check the existing result; do not replay the script.',
        }
        result['message'] = messages.get(value['state'], result['message'])
        if value['state'] in {'failed', 'cancelled'} and evidence.get('executed'):
            result['message'] = 'Script stopped. Partial edits may remain; inspect the font before keeping or restoring them.'
        if evidence.get('executed'):
            result['verification'] = 'Intended changes have not been verified by the wrapper.'
        if (value.get('job') or {}).get('outcome') == 'unverified':
            result['message'] = 'Unknown script outcome acknowledged. Execution remains unverified; no code was replayed.'
    if request['kind'] == 'checkpoint_restore':
        if (value.get('job') or {}).get('outcome') == 'unverified' or unresolved(value.get('job') or {}):
            result['message'] = 'Historical restoration was not confirmed. Inspect the intended font; no reload was replayed. Acknowledgment ends this unresolved workflow without claiming recovery.'
        result['message'] = ('Historical font restored without saving. Later changes were replaced and Undo history was cleared.' if value['state'] == 'applied' else result['message'])
        if value['state'] in {'preparing','ready','needs_review'}:
            result['message'] += '\nRestore replaces all later changes in this font, including unsaved edits, and clears Undo history. It does not save or reset the repository.'
    checkpoint = (value.get('receipt') or {}).get('checkpoint') or {}
    if value['state'] == 'saved' and checkpoint:
        result['message'] = ('Font saved; checkpoint failed.' if checkpoint.get('status') == 'failed' else
                             'Font saved and checkpoint '+('reused: ' if checkpoint.get('status') == 'reused' else 'created: ')+checkpoint.get('revision','')[:12]+'.')
    if value['state'] == 'applied':
        result['message'] += '\n' + current_save_status(value)
    if value.get('blockerId') and (value.get('job') or {}).get('resultKind') == 'script':
        result['message'] = 'Finish the earlier script in its original conversation workflow before continuing.'
        result['message'] += '\nUse that workflow’s available Keep, Save or Restore saved version actions. Restore replaces all subsequent unsaved edits in the whole font.'
    if (value.get('job') or {}).get('checkpointEnabled') and value['state'] == 'applied':
        result['message'] += '\nSave font also creates a local Git checkpoint. Keep does not create a result checkpoint.'
    labels = "; ".join(item["label"] for item in result["actions"])
    result["text"] = f'{value["document"].get("familyName") or "Untitled font"} — {value["document"].get("path") or "Not saved yet"}\n{result["message"]}'
    if result.get('summary'):
        result['text'] += '\nIntended change: ' + result['summary']
    result["text"] += "\nOperation: " + request["kind"].replace("_", " ")
    if request['kind'] == 'kerning_edit':
        result['text'] += '\nScope: {} exact pair edits; master and direction are explicit for each pair.'.format(len(options['edits']))
        for change in ((result.get('job') or {}).get('sample') or [])[:10]:
            if change.get('kind') == 'kerning':
                before = 'absent' if change['before'] is None else str(change['before'])
                after = 'remove' if change['after'] is None else str(change['after'])
                result['text'] += '\n{} / {} · {} · {}: {} → {}'.format(change['left'], change['right'], change['master'], change['direction'], before, after)
    if request.get("glyphs"):
        result["text"] += "; glyphs: " + ", ".join(request["glyphs"][:8]) + ("…" if len(request["glyphs"]) > 8 else "")
    if options.get("masters"):
        result["text"] += "; masters: " + ", ".join(options["masters"])
    if request['kind'] == 'python_script':
        report = (result.get('job') or {}).get('report') or {}
        result['text'] += '\nScope: {} resolved surfaces; {} skipped.'.format(report.get('targetCount', 'pending'), report.get('skippedCount', 0))
        evidence = ((result.get('job') or {}).get('bridgeOperation') or {}).get('scriptResult') or {}
        if result['entrypoint'] == 'per_target' and evidence.get('executed'):
            result['text'] += '\nCompleted callbacks: {} / {}.'.format(evidence.get('executedTargets', 0), evidence.get('totalTargets', 0))
        if result.get('verification'):
            result['text'] += '\n' + result['verification']
        if result.get('warning'):
            result['text'] += '\n' + result['warning']
        if value.get('savedVersion') and value['savedVersion'].get('available'):
            result['text'] += '\nRestore saved version: reloads the whole font, replacing all current unsaved edits and clearing Undo history. The saved file is checked again before restoring.'
        if include_review:
            result['text'] += '\nScript details: ' + json.dumps(options, ensure_ascii=False)
            if evidence.get('output'):
                result['text'] += '\nScript output (text): ' + json.dumps(evidence['output'], ensure_ascii=False)
            if value.get('error'):
                result['text'] += '\nError details (text): ' + json.dumps(value['error'], ensure_ascii=False)
        else:
            result['text'] += '\nShow script: get_edit_workflow with include_review=true.'
    if value.get('blockingWorkflowId'):
        result['text'] += '\nEarlier workflow: ' + value['blockingWorkflowId']
    if request['kind'] not in {'python_script','checkpoint_restore'} and value['state'] == 'applied':
        result['text'] += '\nUndo these changes: restores only this edit and stops on conflicting later edits. Keep ends this offer; native Undo/Redo remains available.'
    if labels:
        result["text"] += "\nAvailable choices: " + labels + ". You can reply in ordinary language."
    if result.get('autoKeep', {}).get('action'):
        result['text'] += '\nIn an active card, Keep changes without saving is selected after 30 seconds. This ends this workflow’s recovery offer. Choose or say “Wait for my answer” to disable it. Text-only clients keep this choice manual.'
    elif value.get('autoKeepEnabled') is False and value['state'] == 'applied':
        result['text'] += '\nAutomatic Keep is off; waiting for your answer.'
    if value.get("error"):
        result["text"] += "\nDetails: " + str(value["error"].get("message", ""))
    result["poll"] = (value["state"] in ACTIVE and (value["state"] != "uncertain" or bool(value.get("jobId")))
                      or value["state"] == "ready" and value.get("mode") == "apply")
    # Some hosts omit structuredContent from the model's conversation. Keep the
    # same bounded control reference in tool text and App context updates.
    result["modelContext"] = json.dumps({
        "workflow_id": result["id"], "expected_revision": result["revision"],
        "document_id": result["document"]["id"], "state": result["state"], "poll": result["poll"],
        "requestFingerprint": result.get("requestFingerprint"),
        "blockingWorkflowId": result.get('blockingWorkflowId'),
        "autoKeep": result.get('autoKeep'),
        "actions": [dict(action=item["action"], label=item["label"], action_token=item["token"],
                         requiresDestination=item["requiresDestination"]) for item in result["actions"]],
    }, ensure_ascii=False, separators=(",", ":"))
    return result
