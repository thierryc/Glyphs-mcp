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

1. Call `get_server_info`, require `data.apiMajor == 2`, and confirm all three
   Python modes. Use `get_runtime_status` when runtime health affects the task.
2. Search `search_knowledge` for unfamiliar Glyphs APIs and retrieve the exact
   cited/versioned entries with `get_knowledge` before writing code.
3. Resolve exact document and entity context with `list_documents` and
   `read_document`.

- `read_only`: bounded inspection with no document mutation. Treat any observed
  canonical or source change as failure.
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

Keep code minimal, deterministic, scoped, and bounded. Do not send removed
legacy arguments; use the contract in
`content/reference/command-set-v2.mdx`. Never call `exit()`, `quit()`, or
`sys.exit()`. Do not save, close, install, reload, restart, touch files, launch
processes, or use networking unless the user explicitly requested those open
world effects.

After an applied staged patch, re-read exact entities and use `list_history`,
`get_operation`, or `revert_change` as needed. For an explicit working-font
save, leave Python and call `save_document` with current fingerprints and user
confirmation. `execute_python` is never a working-source save path.
