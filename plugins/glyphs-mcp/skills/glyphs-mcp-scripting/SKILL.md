---
name: glyphs-mcp-scripting
description: Write and run focused Glyphs Python scripts, using direct native execution and saved-version recovery.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs 4 scripting

Create a workspace script for the requested one-off native operation. Reusable
plugins and ongoing coding sessions use [$glyphs-mcp-development](../glyphs-mcp-development/SKILL.md).
Writing and statically validating a script need no running Glyphs, MCP,
document discovery or Save. Unrelated Python needs no Glyphs skill.

Before authoring a Glyphs script for metrics, geometry, components,
foreground/background, glyph information, reinterpolation or automatic feature
updates, check the retained `get_status.nativeActions`. Prefer the matching
[closed native action](../glyphs/references/native-actions.md) for an ordinary
single-command edit when advertised. For a custom or large composed operation,
offer direct native scripting under the [shared route and recovery
guide](../glyphs/references/python-scripts.md#choose-the-route). Original task
authorization permits execution without a separate code review or Run question.
If the required action is missing, report the capability gap; do not silently
use a script as a substitute for that missing capability. A deliberately chosen
bulk script is a separate supported route, not a repair for an installation gap.

Before scripting compilation or export, also check `jobKinds` and
`jobCapabilities`. Prefer `feature_compile` for native compiler diagnostics and
`font_export` for typed static/variable/web generation plus table or bounded
shaping verification. A missing advertised capability is an installation gap,
not permission to emulate it with arbitrary Python.

Use the development skill's [offline documentation](../glyphs-mcp-development/references/development-docs.md)
for unfamiliar APIs and its existing `scaffold.py create script` and
`validate --target 4` commands. Separate pure logic from native access. State
targets, effects and verification; preserve fractional values, native flags,
metadata and object identity.
For coordinate edits, use the [native precision recipe](../glyphs-mcp-development/references/native-precision.md).
For feature work, use [OpenType guidance](../glyphs-mcp-opentype-features/SKILL.md).

Execution follows the user's authorised task. Use disposable copies for
experiments and the [native iteration reference](../glyphs-mcp-development/references/native-iteration.md)
for logs, proofs and cleanup. Static validation is not runtime success. Never
promise recovery of arbitrary Python's external effects. Saved-file recovery
reloads the whole persisted font; external effects remain outside recovery.

For needed MCP context, reuse the verified [$glyphs](../glyphs/SKILL.md) connection
and intended document ID already in context. Resolve missing bindings through the
[document targeting reference](../glyphs/references/document-targeting.md).
Do not reload the entry, repeat discovery or refetch known API excerpts merely
to switch to scripting. Rediscover after document_not_found, a target change or
bridge/Glyphs restart; never silently substitute another open font. Reads are fresh.
Dirty documents can be inspected without saving.

For advertised `python_script` jobs, follow the shared [execution and recovery
contract](../glyphs/references/python-scripts.md). Choose the smallest useful form:

- `run(layer, params, context)` for independent selected-surface edits; send one
  manifest and loop over paths/nodes locally.
- `entrypoint="script"` for coordinated font-level changes; it receives `font`,
  `targets`, `params` and `Glyphs`. Use exact identifiers and expected values in
  `params`; `targets:[]` is valid when no layer target is meaningful.

**Direct native scripting** requires `script.native.v1`. Use `source`, `params`,
`entrypoint`, `targets` and optional `summary`; no execution/recovery mode or
count threshold. Clean saved fonts require no extra Save. Dirty fonts require
an authorized **Save and run**, and new fonts use Save As/manual saving.

Intent controls the workflow. Perform a requested task by generating, validating
and testing code as appropriate, running it, then verifying the result. Do not
require code review or a separate Run question for result-focused tasks. Writing
a script includes code review but does not authorize live execution. Reviewing
means review only. Write-and-run includes review and authorized execution.
Explicit previews wait. Source remains available through optional Script details.
Successful cards default to Keep without saving after 30 seconds, ending recovery.
Honor **“wait for my answer”** with `auto_keep=false` on new workflows or the
existing **Wait for my answer** action; retain that directive for later requests.
See the shared contract for countdown, visibility and text-only behavior.

**Restore saved version** reloads the whole unchanged baseline, clears Undo
history and replaces later unsaved edits. It never saves or replays code. Keep
or Save ends the restoration offer. Failure/cancellation leaves possible partial
edits for inspection; never auto-reload. Keep generated scripts free of save/close
calls and reconcile uncertain outcomes without replay. Use
[vertical_flip.py](examples/vertical_flip.py) for explicit vertical pivots.
