"""Small persistent interaction records; no font snapshots or mutation replay."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

TERMINAL = {"saved", "discarded", "cancelled", "no_changes", "failed"}
ACTIVE = {"preparing", "applying", "saving", "discarding", "blocked_active", "blocked_review", "blocked_proposal", "resolving", "uncertain"}


class WorkflowStore:
    def __init__(self, root):
        self.root = Path(root) / "edit-workflows"
        self.records = {}
        if self.root.is_dir():
            for path in sorted(self.root.glob("edit_*.json")):
                try:
                    value = json.loads(path.read_text())
                    if value["id"] != path.stem or value.get("version") != 1:
                        continue
                    self.records[value["id"]] = value
                    if value["state"] not in TERMINAL and value["state"] != "interrupted":
                        value["resumeState"] = value["state"]
                        self.update(value, state="interrupted", error={
                            "code": "workflow_interrupted",
                            "message": "The service restarted. No save or edit was replayed. Check the existing outcome before starting new work.",
                        })
                except (OSError, ValueError, KeyError, TypeError):
                    continue

    def create(self, document, arguments, request, mode, key):
        value = dict(version=1, id="edit_" + uuid4().hex, nonce=uuid4().hex,
                     document=deepcopy(document), arguments=deepcopy(arguments), request=request,
                     mode=mode, idempotencyKey=key, state="starting", revision=0,
                     jobId=None, blockerId=None, job=None, error=None, receipt=None,
                     usedActions={}, createdAt=time.time())
        self.records[value["id"]] = value
        self.update(value)
        return value

    def update(self, value, **fields):
        value.update(deepcopy(fields))
        value["revision"] += 1
        value["updatedAt"] = time.time()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self.root / (value["id"] + ".json")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True))
        temporary.chmod(0o600)
        temporary.replace(path)


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
    "waiting_save": "Save your font to continue.",
    "waiting_manual": "Save your font in Glyphs, then continue here.",
    "preparing": "Preparing changes…",
    "ready": "Changes ready to review.",
    "needs_review": "Some changes need your review.",
    "applying": "Applying changes…",
    "applied": "Changes applied. Save your font to keep them.",
    "saving": "Saving font…",
    "discarding": "Discarding changes…",
    "blocked_active": "Waiting for an earlier change to this font.",
    "blocked_review": "Save or undo the earlier changes to continue.",
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
    "applied": "Saving includes the whole font, including any other edits.",
    "blocked_review": "Saving includes the whole font. Undo affects only the earlier changes and stops if they conflict with later edits.",
    "blocked_proposal": "Return to that preview and apply or discard it first.",
    "outdated": "Preparation uses the current saved version of your font.",
}


def offered_actions(value):
    state = value["state"]
    save = [("save_continue", "Save and continue")] if value["document"].get("path") else []
    if state == "waiting_save":
        return save + [("save_as_continue", "Save As…"), ("manual_save", "I'll save in Glyphs"), ("cancel", "Cancel")]
    if state == "waiting_manual":
        return [("check_continue", "Check and continue"), ("cancel", "Cancel")]
    if state == "outdated":
        return [("reprepare", "Prepare again")] + ([("save_reprepare", "Save and prepare again")] if save else []) + [("manual_save", "I'll save in Glyphs"), ("cancel", "Cancel")]
    if state in {"ready", "needs_review"}:
        return [("apply", "Apply changes"), ("discard", "Discard preview")]
    if state == "applied":
        return [("save_result", "Save font"), ("save_result_as", "Save As…"), ("discard", "Undo these changes")]
    if state == "blocked_review":
        return [("save_previous", "Save earlier changes and continue"), ("discard_previous", "Undo earlier changes and continue"), ("cancel", "Cancel this request")]
    if state in {"blocked_active", "blocked_proposal"}:
        return [("check_continue", "Check and continue"), ("cancel", "Cancel this request")]
    if state == "preparing":
        return [("cancel", "Cancel preparation")]
    if state == "interrupted" and not value.get("jobId") and not value.get("saveRequest"):
        return [("check_outcome", "Check result"), ("cancel", "Cancel this request")]
    if state in {"uncertain", "interrupted"}:
        return [("check_outcome", "Check result")]
    return []


def public_workflow(value):
    result = {key: deepcopy(value.get(key)) for key in (
        "id", "revision", "document", "mode", "state", "jobId", "blockerId", "job", "error", "receipt", "reviewInConversation")}
    request = value["request"]
    options = request.get("options") or {}
    result["scope"] = {"kind": request["kind"], "glyphs": request.get("glyphs", [])[:100],
                       "glyphCount": len(request.get("glyphs", [])), "masters": options.get("masters"),
                       "targets": (options.get("targets") or options.get("changes") or options.get("pairs") or [])[:100]}
    result["actions"] = [dict(action=name, label=label, token=action_token(value, name),
                              requiresDestination=name in {"save_as_continue", "save_result_as"})
                         for name, label in offered_actions(value)]
    result["message"] = MESSAGES.get(value["state"], "Checking your changes…")
    if guidance := GUIDANCE.get(value["state"]):
        result["message"] += "\n" + guidance
    if value.get("error"):
        result["message"] += "\nCheck your font in Glyphs and review Details before continuing."
    labels = "; ".join(item["label"] for item in result["actions"])
    result["text"] = f'{value["document"].get("familyName") or "Untitled font"} — {value["document"].get("path") or "Not saved yet"}\n{result["message"]}'
    result["text"] += "\nOperation: " + request["kind"].replace("_", " ")
    if request.get("glyphs"):
        result["text"] += "; glyphs: " + ", ".join(request["glyphs"][:8]) + ("…" if len(request["glyphs"]) > 8 else "")
    if options.get("masters"):
        result["text"] += "; masters: " + ", ".join(options["masters"])
    if labels:
        result["text"] += "\nAvailable choices: " + labels + ". You can reply in ordinary language."
    if value.get("error"):
        result["text"] += "\nDetails: " + str(value["error"].get("message", ""))
    result["poll"] = value["state"] in ACTIVE and (value["state"] != "uncertain" or bool(value.get("jobId")))
    return result
