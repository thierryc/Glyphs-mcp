---
name: glyphs-macro-iteration
description: Develop or debug a workspace Python script visibly in Glyphs 4 through the Scripting Window, verifying displayed source and capturing embedded console output. Use for interactive macro iteration, alongside glyphs-mcp-scripting.
metadata:
  surface: glyphs-mcp-v2
---

# Visible macro iteration

Use this optional companion when the user wants to see and iterate on script
code inside Glyphs. Ordinary one-off font operations remain with
[$glyphs-mcp-scripting](../glyphs-mcp-scripting/SKILL.md); ongoing script or
plugin development uses
[$glyphs-mcp-development](../glyphs-mcp-development/SKILL.md).
Reuse guidance already loaded. This skill adds no MCP tools and requires a
local Glyphs 4 UI automation surface for agent-driven interaction. Without that
surface, prepare the workspace revision and explain the manual steps; do not
claim native execution or console capture. Resolve the required scripting
guidance from its installed location if sibling links are unavailable.

The workspace file is authoritative. The goal is to make the intended revision
visible, run it under existing task authorization, capture attributable output,
and verify behavior before revising again. See
[qualified behavior and limits](references/qualification.md) when choosing the
loading/capture route or reporting host support.

## Prepare the intended revision

Follow the scripting skill for API documentation, static validation, pure logic,
precision, task scope and result checks. Writing or reviewing alone does not
authorize execution. Do not turn a coding session into an MCP server change.

Distinguish execution contexts before loading code. An MCP `run(layer, params,
context)` callback or font-level entrypoint is not automatically invoked by the
Scripting Window, and its injected arguments are not supplied there. For a
requested standalone macro, provide an explicit native entrypoint with exact
target checks. Do not silently convert an MCP job to manual execution or imply
that opening its source reproduces its execution environment.

Use tests proportional to the script: expected behavior and preservation checks
for meaningful transformations, pure tests for calculations, and read-only
preflight checks before native writes. Preflight validates prerequisites; it is
not evidence of test-driven development or successful execution. Experiments
that mutate fonts use disposable fixtures under the existing development
guidance. Repeated execution must start from a known state or deliberately test
repeat-run behavior.

## Load workspace source visibly

1. Identify the intended Glyphs 4 app by `com.GeorgSeifert.Glyphs4`; inspect the
   actual build, menu and UI state. Open **Window → Scripting Window** on the
   qualified build. Preserve existing macro source, settings and console history.
2. Reuse an owned link to the intended workspace `.py` when available. The
   qualified loading route is a uniquely named symbolic link in the app's
   Macros directory pointing to that file. Resolve the actual directory from
   native UI evidence; on the tested host it was
   `~/Library/Application Support/Glyphs 4/Macros/`. Creating a link is a
   scoped installation step under the user's loading/iteration authorization,
   not permission to overwrite existing files or change unrelated links.
   Verify the source and link destination; never replace a conflicting entry.
3. Select the linked script's sidebar row. Verify the resolved workspace path
   and displayed source before Run. **File → Open** rejected `.py` on the tested
   build; `Glyphs.showMacroWindow()` opens a window but does not load source.
4. After a workspace edit, inspect the displayed source again. Automatic refresh
   worked on the qualified build, but is not a universal guarantee. If stale,
   try selecting the owned script again or the observed **Reload Scripts**
   action, then verify. Stop before Run if the source still differs. Reconcile
   conflicting editor changes with the workspace file instead of overwriting
   either copy. Editor save-through-link behavior is unqualified.

Use current accessibility elements for UI actions. Refresh state after each
action; do not reuse stale indices or infer success from a click. Prefer named
controls to coordinate clicks, which caused an incidental setting change during
qualification. Do not execute unrelated macros encountered in the editor.

## Run, capture and iterate

- Confirm the correct script and revision immediately before the observed Run
  button. For font edits, resolve exact font/layer/surface targets and establish
  native recovery for this script first. A manual macro run has no automatic
  MCP pre-run snapshot, target binding, cancellation or workflow recovery.
  Do not run against targets owned by an unresolved MCP job.
- Capture the embedded console before execution. Use a distinct run/revision
  marker when useful for attributing output; do not impose logging boilerplate
  on every script. Run once within authorization, then inspect the embedded
  console's accessibility text and retain the new output or traceback.
- Preserve prior output. `Glyphs.clearLog()` and Clear Console erase evidence;
  clear only deliberately after retaining needed diagnostics. The floating
  console did not mirror embedded history in the qualified check.
- A changed marker proves the new revision ran, not that a font operation was
  correct. Verify the intended result and preservation requirements using the
  scripting/development guidance. Separate static validation, native execution
  and behavior verification in the report.
- Before retrying a failure or uncertain run, inspect its existing output and
  effects. Do not replay a potentially mutating script merely because output
  capture failed. Change a coherent workspace revision, confirm refreshed
  source, and repeat only the checks needed for that revision.

Keep a compact record in the task's existing workspace/report: source path and
revision, host build, displayed-source evidence, expected/observed output,
behavior checks, and unresolved limits. Report truncated output as incomplete.
Saving, exporting, closing fonts and restarting remain separately scoped.
When cleanup is requested, remove only owned test links after verifying their
destinations; preserve workspace source and unrelated macros. Report retained
links and artifacts at handoff. Do not infer safe unlink/trash behavior from the
untested editor context menu.
