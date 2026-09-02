---
name: glyphs-mcp-scripting
description: Use execute_python as the permanent Glyphs fallback when generic v2 tools cannot express a focused read, detached document edit, UI task, or external operation.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP scripting

Python is a permanent architectural capability. Prefer generic declarative
tools when they fit because they are simpler to inspect and revert; use Python
whenever the typed surface is insufficient.

## Select a mode

1. Call `get_server_info`, require `data.apiMajor == 2`, and inspect
   `data.registries.pythonExecution.detachedNamespace` before generating
   detached code. It is the machine-readable source for built-ins, imports,
   injected context, constructors, denials, and contract identity. Confirm all
   three Python modes. Use `get_runtime_status` when runtime health affects the
   task.
2. Search `search_knowledge` for unfamiliar Glyphs APIs and retrieve the exact
   cited/versioned entries with `get_knowledge` before writing code.
3. Resolve exact document and entity context with `list_documents` and
   `read_document`.

- `read_only`: bounded inspection on a detached document. The runtime
  proves that the live canonical fingerprint and dirty state did not change.
  Code that mutates only the detached clone is reported as evidence and does
  not affect the live font. An optional stale document fingerprint is not a
  write-safety blocker: execution rebases to the latest stable snapshot and
  returns `read_rebased_to_current_document` with the actual base fingerprint.
  Use `live_open_world` when the required API is inherently live-only.
- `staged_document`: execute once on a detached document. The result is an
  immutable `previewId` containing the exact code hash, scope, runtime,
  fingerprints, output, and semantic patch. Apply it through `apply_change`;
  never rerun the code for confirmation.
- `live_open_world`: last resort for unsupported Glyphs UI/global APIs, files,
  processes, networking, or other external effects. State the intended effects
  and recovery checkpoint. Confirm the exact `approvalId` once and report
  verified document effects separately from unverifiable external effects.

Use `open_document_view` for the supported named-glyph UI operation. Use
`repair_runtime` only when `get_runtime_status` reports a manager-owned
recoverable incident; re-read status and retry the original call once. Never
loop repairs. Escalate restart/manual recovery when reported.

## Code and safety contract

Detached Python exposes a near-standard reviewed Python 3.14 built-in set, not
a security sandbox. It intentionally omits external-effect, dynamic-code,
interactive, and process-control entry points, and imports only the roots
advertised by the runtime. Keep code minimal, deterministic, scoped, and
bounded. Preserve every fractional coordinate and verify exact geometry; do
not round coordinates, snap to a grid, set `font.grid`, change
`gridSubDivision`, or modify `font.disablesAutomaticAlignment`. The runtime
owns its temporary rounding suppression and restores those protected settings;
an attempted script change is reported as a failure. The global automatic
alignment setting therefore remains unchanged. Component-level alignment
changes remain explicit, reviewed opt-ins. For every direct or transitive
component effect, the runtime keeps its tool-owned zero grid active through
dependency settlement and restores the exact entry grid and subdivision before
read-back. Scripts must never implement this by editing grid settings; explicit
reviewed grid edits are isolated by the runtime after settlement. Do not send removed legacy arguments; use the contract in
`content/reference/command-set-v2.mdx`. Never call `exit()`, `quit()`, or
`sys.exit()`. Do not save, close, install, reload,
restart, touch files, launch processes, or use networking unless the user
explicitly requested those open-world effects.

Interpret detached failures precisely: `staged_symbol_unavailable` and
`staged_import_unavailable` mean the generated code exceeded the advertised
namespace; `staged_assertion_failed` means the script rejected its own
detached candidate and is not evidence of a clone or recalculation failure.
Unclassified failures retain their mode-specific Python error. Read the
returned contract fingerprint, line, code hash, live-state proof, dirty state,
and stage timings before revising code.

After an applied staged patch, re-read exact entities and use `list_history`,
`get_operation`, or `revert_change` as needed. For an explicit working-font
save, leave Python and call `save_document` with current fingerprints and user
confirmation. `execute_python` is never a working-source save path.

A user-initiated Glyphs Save is always allowed, including while a verified
document transaction is active. Do not treat a source-file fingerprint change
as live-document mutation. Continue from the receipt's persistence
reconciliation and its residual unsaved diff; only a changed live canonical
fingerprint stales an immutable preview.
