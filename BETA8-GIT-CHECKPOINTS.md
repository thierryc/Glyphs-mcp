# Milestone 6 — Git checkpoints and a Git-enabled font project template

Status: **implemented and qualified locally, September 28, 2026**. See the
[behavior, tests, performance and limitations report](reports/beta8-milestone6/README.md).
Stop here before consolidation (milestone 7);
kerning moves to milestone 8. Milestone 5 and its installed-card gate remain open.
This document retains the user-supplied implementation contract. Checkpointing
remains opt-in; this work does not enable it for existing font projects.

[Return to the milestone sequence](BETA8-MILESTONES.md).

## Goal
Make font edits recoverable after saving, with a readable history of agent
actions available on demand in chat and the Glyphs MCP app.

Work within the current v2 architecture. Preserve existing typed recovery,
native-script saved-version restoration, twelve public tools and current
authorization rules. Write tests first. Preserve unrelated work.

## 1. Project policy and authorization

Add an opt-in project setting:

“Create a Git checkpoint when saving through MCP.”

The setting applies to one explicitly identified font project. Enabling it
authorizes local checkpoints for that project, including a required starting
checkpoint. It does not authorize additional font saves, pushing, publishing,
repository initialization or unrelated commits.

AGENTS.md documents the preference for agents; it is not a runtime
configuration parser. The project setting controls server/app behavior.

## 2. Establish an exact baseline

Before an authorized font mutation in an enabled project:

- Resolve the intended font and containing Git repository.
- Reuse an existing checkpoint when its font contents exactly match the
  verified saved baseline.
- Otherwise create a checkpoint of that saved baseline before editing.
- A clean saved font must not receive another Save merely to create a commit.
- Dirty/new fonts retain existing authorized Save, Save As and manual-save
  workflows.
- Do not claim checkpoint protection if baseline creation failed or remains
  uncertain. Resolve that outcome before executing the edit.

Do not silently treat HEAD as the baseline when the font differs from HEAD.

## 3. Checkpoint after saving

After a verified MCP Save or accepted-result Save:

- Commit the exact saved font contents and their action record.
- Cover both .glyphs files and complete .glyphspackage contents, including
  additions and deletions.
- Include only the intended font/package and its action record.
- Preserve unrelated working-tree changes and staged content.
- Detect conflicting Git operations, concurrent branch/file changes and
  ambiguous staged changes rather than silently incorporating them.
- Verify the committed font matches the save receipt.
- Do not create empty commits or push automatically.

Saving and committing are separate outcomes. If Save succeeds but Git fails,
report “Font saved; checkpoint failed.” Retrying must reconcile or retry only
the checkpoint, never repeat the edit or Save.

Reuse existing save IDs, job records and reconciliation where possible.
Duplicate requests, reconnects and uncertain commit responses must not produce
duplicate checkpoints. Do not add another recovery database or backup system.

## 4. Durable action records

Use a small, versioned, machine-readable action record stored in the same commit,
with a concise human-readable commit message.

Record:
- Intended change and font path relative to the repository.
- Workflow/job identifiers and baseline revision.
- Typed operation or exact script and parameters.
- Declared targets or a bounded summary with a durable reference to full scope.
- Execution outcome and verification evidence, clearly distinguished.
- Known manual/unattributed changes and incomplete evidence.
- Save verification and action-record schema version.

A single Save may contain several agent actions and manual edits. Do not
attribute the entire font diff to the LLM or invent verified change counts.

Do not store full chat transcripts, hidden reasoning or unrestricted logs.
Keep outputs bounded. Do not require recording the enclosing commit’s own hash
inside its committed action record; return that hash in the checkpoint receipt.

## 5. History, comparison and restoration

Expose the same checkpoint information on demand in chat and the desktop app,
using existing public tools with negotiated extensions where necessary.
Add no public tool.

Support:
- Show recent checkpoints for this font.
- Show actions and verification details for a checkpoint.
- Compare font versions.
- Restore this font to a selected checkpoint.

Reuse the existing desktop Git diff browser and font comparison components.
Keep history reads paginated and bounded; do not load all history during polling.

Restoration:
- Restores only the intended font/package, never resets the whole repository.
- Coordinates with Glyphs and outstanding MCP jobs.
- Never replaces an open font’s files behind Glyphs.
- Clearly states that restoring a version replaces later font changes,
  including unsaved edits, and may clear Undo history.
- Returns the authoritative fresh document binding.
- Never reruns the original script.
- Preserves Git history; a subsequently authorized Save creates a new checkpoint
  recording the restoration.

A clear request to restore supplies restoration authorization. Saving the
restored result follows the existing save-authorization contract.

## 6. Conversation and app wording

Keep the normal edit workflow compact:

Keep changes without saving
Save font
Existing selective Undo or Restore saved version

When checkpointing is enabled, explain beside Save that it creates a local Git
checkpoint. Keep without saving creates no result checkpoint.

After success, show:
“Font saved and checkpoint created: <short revision>.”

Offer on-demand:
Show actions · Compare · Restore this checkpoint

Show Save and checkpoint failures separately. Do not introduce mandatory source
review, an extra confirmation on every authorized checkpoint, or automatic push.

## 7. Add a font project template

Create a selectable “Font project with Git checkpoints” template through the
existing project-template infrastructure and registry in the Glyphs MCP app.

Include:
- README explaining Save, checkpoints, history and whole-font restoration.
- AGENTS.md with the directive below.
- Appropriate font-project .gitignore entries.
- The minimal project configuration required to enable checkpointing.
- A documented location and schema for action records.

Use the existing template creation flow. Explicitly describe Git initialization
when creating a new project; never initialize or rewrite an existing repository
silently. Do not bundle a copyrighted font or modify an existing project merely
because the template was selected.

Template AGENTS.md directive:

```markdown
## Git checkpoints for font saves

This project uses local Git checkpoints for authorized MCP font edits and saves.

Before editing, ensure the verified saved baseline is represented by a
checkpoint. Reuse an existing matching checkpoint when possible.

After an authorized MCP save completes and is verified, create a local
checkpoint containing the intended font and its action record. Include the
intended change, affected scope and actual verification evidence.

Preserve unrelated files and staged changes. Do not create empty commits,
initialize another repository or push automatically.

If committing fails after saving, report “Font saved; checkpoint failed.”
Reconcile or retry the checkpoint without repeating the edit or Save.

Keep without saving creates no result checkpoint. This policy authorizes local
checkpoints, not additional font saves.

Explain whole-font restoration coverage before restoring a historical version.
Never reset the whole repository or overwrite files behind an open Glyphs font.
```

## 8. Verification and completion

Write failing tests before implementation. Cover:

- Existing matching baseline and uncommitted saved baseline.
- Zero Save calls for clean-baseline checkpoint creation.
- Authorized dirty/new Save and Save As.
- No-effect saves, multiple actions and manual edits.
- Both font formats, package additions/deletions and multiple fonts in one repo.
- Unrelated staged/unstaged changes, conflicts, missing Git identity, hooks,
  concurrent changes and commit failure after successful Save.
- Duplicate requests, uncertain outcomes, reconnects and restart reconciliation.
- Bounded history reads and durable action-record retrieval.
- Historical restoration with later edits, refreshed bindings and intact
  unrelated repository content.
- Template creation, discoverability in the app and directive/config agreement.
- Existing typed/script recovery and twelve-tool compatibility.

Measure Save-plus-checkpoint cost on representative font files and packages.
Keep Git work off Glyphs’ main thread wherever possible. Report measured
overhead without promising unmeasured speed.

Qualify actual editor saving/restoration and an installed chat-client workflow
using disposable Git repositories and fonts. Update canonical guidance and its
packaged mirror together.

Inspect current source, build and installation conventions before rollout.
Rebuild, install and relaunch only under applicable authorization. Record source,
built, installed and loaded identities. Do not publish or commit implementation
changes unless separately authorized.

Deliver a concise report of behavior, tests, performance, remaining limitations
and any incomplete native gates.

## Current implementation fit

These were the inspected integration points used for this implementation:

| Existing component | Milestone work |
| --- | --- |
| [Save coordination](src/sidecar/glyphs_mcp_sidecar/saving.py), [job records](src/sidecar/glyphs_mcp_sidecar/jobs.py) and [conversation lifecycle](src/sidecar/glyphs_mcp_sidecar/edit_workflow.py) | Attach baseline/checkpoint outcomes to existing durable identities; reconcile Git failure separately from a successful Save. Preserve no-op polling and active-work indexing. |
| [Saved-script recovery](src/sidecar/glyphs_mcp_sidecar/saved_script.py) and native bridge | Preserve current saved-version restoration. Qualify the additional historical-version load with actual Glyphs document coordination and fresh bindings. |
| [ReadOnlyGit](macos-installer/GlyphsMCPInstaller/Core/ReadOnlyGit.swift), [GlyphDiff](macos-installer/GlyphsMCPInstaller/Core/GlyphDiff.swift) and [desktop Git workspace](macos-installer/GlyphsMCPInstaller/Sources/DesktopGitWorkspace.swift) | Reuse bounded inspection and font comparisons. The current read-only browser is not an implementation of scoped checkpoint writes or historical restoration. |
| [Project settings](macos-installer/GlyphsMCPInstaller/Sources/DesktopProjectSettings.swift) and [project model](macos-installer/GlyphsMCPInstaller/Sources/DesktopProjects.swift) | Expose the opt-in setting and use one versioned project configuration shared with the server; do not turn AGENTS.md into executable policy. |
| [Template catalog](macos-installer/GlyphsMCPInstaller/Core/DesktopTemplateCatalog.swift), [template loader](macos-installer/GlyphsMCPInstaller/Core/TemplateStore.swift), [creation flow](macos-installer/GlyphsMCPInstaller/Sources/DesktopProjectWizard.swift) and [registry](templates/registry.json) | Add the selectable template through these paths. Remote entries currently require a pinned revision and archive checksum; qualify local/bundled delivery without inventing a published revision or silently publishing to satisfy the registry. |

Implementation must preserve action evidence after Keep even when the existing
job service releases bulk artifacts. That evidence is necessary to describe a
later Save containing multiple kept actions and manual changes. It must not
restore an expired selective-Undo or saved-version recovery offer.

Define and test the exact-byte contract at the Git boundary, including repository
attributes/filters, package deletions and concurrent writes. An unsupported
representation must fail explicitly instead of claiming that a normalized Git
blob matches the verified saved font. Choose the smallest tested implementation
within the existing lifecycle; do not introduce a second history/recovery store.
