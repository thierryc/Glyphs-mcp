# Revision evidence and recovery

Use this project guidance during native verification or after a failure. It is
separate from the pinned official corpus and does not establish host support.

## Compact verification record

Keep one record per tested revision in the task's existing report or workspace;
do not create a second reporting system. Include only applicable evidence:

- **Artifact:** absolute workspace and installed paths, bundle ID, principal
  class, version, file fingerprint and static validation result.
- **Loaded:** application bundle ID/version/build, visible revision behavior or
  bounded native diagnostic identifying the loaded class/revision. Installed
  bytes alone leave this unverified. Do not infer hot reload from a file change.
- **Behavior:** requested outcome, relevant source citation, expected and
  observed result for each tested case. Record viewport/zoom for visual proofs.
- **Preservation and cleanup:** captured unchanged data, native Undo/Redo where
  relevant, remaining installed test files and document state. A source hash
  proves disk preservation only; native state needs separate evidence.
- **Limits:** mark passed, failed, blocked or unverified explicitly. Record
  truncated evidence and untested hosts. Separate active task time, waiting,
  HTTP latency, directly measured native timing and estimated payload tokens.

An ordinary plugin task needs its relevant checks; a comparative benchmark's
full repetition protocol applies only when that benchmark is requested. A
required, well-explained native relaunch is not itself a skill failure.

## Recover from the observed failure

| Symptom | Next action and stopping point |
|---|---|
| Install appears stalled | Inspect native prompts before repeating Open. On the qualified 4.1 (4107) build, Start Window covered the installation alert; close only that window if it obscures the prompt. If no prompt is found, retain the error and inspect diagnostics before retrying. |
| Old plugin behavior after editing | Compare workspace and installed paths, bundle identity and revision. If bytes match but the old revision remains loaded, use the authorised native relaunch with unrelated work safe; verify the new behavior. If it still differs, capture class/path/traceback rather than installing repeatedly. |
| Syntax or principal-class validation fails | Correct the workspace artifact from the validator's exact error, validate again, then install. If provenance or loader verification fails, compare the pinned scaffold assets; do not bypass the check or replace a user's existing artifact. |
| Missing/corrupt offline documentation | Preserve `update_required` and the affected path; refresh the owned development skill through the existing installer. Preserve installation conflicts for explicit replacement with backup. No silent online or older-private substitution. |
| Unknown documentation ID | Search locally for its title/symbol. This is unrelated to an MCP font document ID; do not discover fonts. |
| MCP `document_not_found`, or bridge/Glyphs restarted | Rediscover on that same connection and match the intended font explicitly. A reopened copy gets a new ID. If it is absent, report that; never substitute the frontmost font. Other read errors do not require discovery. |
| Mac locked or UI inaccessible | Save a checkpoint with artifact/installed revision, last verified step, owned disposable paths and pending checks. Continue independent offline work. After unlock inspect the current app and loaded state before resuming the pending step; do not blindly replay installs. |

For native diagnostics use the menu observed for the running host as described
in [native iteration](native-iteration.md). A crash is failed evidence: retain
the crash report and the last verified action. Do not claim a root cause from
a passing retry. Resolve any risk to unrelated unsaved work before a relaunch;
reuse installation and execution authorisation already present in the task.
