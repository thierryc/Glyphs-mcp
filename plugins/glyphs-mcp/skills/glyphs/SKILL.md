---
name: glyphs
description: Route Glyphs 4 font work to the lean MCP tools and independent companion plugins.
metadata:
  surface: glyphs-mcp-v2
---

# glyphs

For creating, revising or debugging a Glyphs 4 script/plugin, use
[$glyphs-mcp-development](../glyphs-mcp-development/SKILL.md). Offline coding
needs no connection, document discovery or Save. Generic Python with no Glyphs
app or font target needs no Glyphs skill.
OpenType source work uses [the native feature skill](../glyphs-mcp-opentype-features/SKILL.md).

## Continue from known context

Reuse the verified catalog, identity and capabilities of the **specific MCP
connection**, plus the intended font's `document_id`. A follow-up or switch to a
focused skill does not restart setup. If the connection is unverified or changed,
load [connection setup](references/connection-session.md); it distinguishes lean
v2, v1 and mismatches. Check a workflow's required `readCapabilities`/`jobKinds`
against that retained `get_status` response. Refresh it after a component update, known process
restart, changed endpoint, contradictory evidence or a request for current health.
Missing private capabilities mean the installation needs updating: update the
bridge, sidecar and skills together. Do not maintain fallback workflows.

Call `list_documents` only when the intended document has no valid retained ID,
after `document_not_found` or a known bridge/Glyphs restart, or to resolve an
explicit target change. Never silently substitute another open font. A missing
glyph is not a discovery trigger. “Current/frontmost font” may require fresh
intent resolution; see [document targeting](references/document-targeting.md).
Each `read_entities` call reads fresh contents. Dirty fonts need no Save for reads.

Load only the reference needed for the requested operation. Reuse instructions
and cited excerpts already in context; fetch only a missing or changed section.
A focused skill inherits this connection/document context without reloading this
entry. Resolve genuine context gaps; do not treat remembered font data as current.

| Requested work | Focused reference |
|---|---|
| Discover glyph names | [Glyph discovery](references/glyph-discovery.md), requiring `glyphs.list.v1` |
| Glyph metadata | [Metadata](references/metadata-reads.md) |
| Dimensions palette reference notes: read/fill freely, approve overwrites in conversation | [Dimensions](references/dimensions.md) |
| Native master IDs, metrics, axis positions or italic angle | [Masters](references/master-reads.md) |
| Discover a glyph's exact layer IDs and native types | [Layer discovery](references/layer-discovery.md), requiring `layers.list.v1` |
| Exact layers, fractional metrics and bounds | [Layers](references/layer-reads.md) |
| Current master or selected glyphs in Font/Edit View | [Context](references/context-reads.md), requiring `document.context.v1` |
| Active layer, selected-object counts or optional node details | [Selection](references/selection-reads.md), requiring `selection.context.v1` |
| Discover kerning groups or stored pairs | [Kerning discovery](references/kerning-discovery.md) |
| Exact stored kerning | [Kerning reads](references/kerning-reads.md) |
| Additive advance changes | [Widths](references/width-changes.md) |
| Glyphs-native metrics, outline/component/background, glyph-info or automatic-feature commands | [Closed native actions](references/native-actions.md), requiring `native.action.v1` and the action in `nativeActions` |
| Feature source discovery and saved/live compiler diagnostics | [Feature compilation](references/feature-compilation.md), requiring `features.read.v1` and a compile capability |
| Static, variable, WOFF/WOFF2 export and bounded shaping checks | [Font export](references/font-export.md), requiring `instances.read.v1` and export/verification capabilities |
| Color, icon/Unicode, production or LitSquare audit scope beyond these jobs | [Specialized scope](references/specialized-scope.md) |
| Connection failure | [Troubleshooting](references/connection-troubleshooting.md) |
| Glyphs crashed or unexpectedly exited | [Crash recovery](references/crash-recovery.md); ask before any temporary autosave pause |

Use the matching spacing, kerning, italic-first-pass, master-compatibility or
outlines skill only when its domain is needed. Curve Inspector and Reference
Inspector are independent companions. Use development or scripting for a
separately authorised native operation, release for packaging, and
maintainer-feedback for a reproducible defect. Ordinary reads need no coding
resources or job. Request only needed fields; the usual bound is 100 explicit
targets, with tighter detail limits specified in the focused references.

## Supported edits

For an advertised mutation job, prefer the shared [conversation workflow](references/edit-workflow.md)
when `workflowCapabilities` includes `edit.workflow.v1`. Use `start_edit_workflow`
with the same operation and scope and a retained idempotency key. An edit request
uses `apply`; an explicit preview uses `preview`. Ordinary complete results apply
automatically without saving. Warnings, skipped targets and overwrite approvals
require report review before application. Present the standard MCP App wherever
supported; every choice also works in ordinary conversation. “Save and continue”
authorizes one prerequisite whole-font save, then preparation and application;
the resulting edit remains unsaved. Reuse scoped authorization already given.

The existing `start_job`, `get_job`, `apply_job` lifecycle remains available for
explicit low-level job work. Diagnostic jobs finish without application; artifact jobs
publish through `accept_job` to a new directory. Reconcile an uncertain write
using that existing job ID; do not
submit a duplicate. `discard_job` cancels or restores the whole job. Application
is save-free. When the user's task authorizes persistence after review, call
`accept_job`; it revalidates affected targets, saves the entire document and
closes the rollback window. Use `save_document` only for a specifically
identified document with no active or applied MCP job. Inspect fresh source and
dirty state for preparation, and never save merely to satisfy `start_job`.
Never save, publish an export, close or overwrite a font unless the user's task
authorizes it. The twelve tools provide no arbitrary Python execution or plugin reload; do
not invent an MCP command. An advertised `native_action` is a closed typed job,
not a general script or remote-object interface.
