# MCP Apps-first conversation workflow

Accepted September 22, 2026. Preserve the saved-and-clean editing rules.

## Product decisions

1. Use one standard interactive MCP App wherever supported. Client-specific
   controls are permitted only when the standard is unavailable. Complete text
   conversation operation is available in every client, including UI clients.
2. Cover every advertised mutation job (including Dimensions); compilation and
   export retain their existing interfaces. Do not add another font editor.
3. Requested edits apply automatically after complete preparation without
   warnings or skipped/unavailable work. Preview requests wait for Apply.
   Reports requiring interpretation retain agent review, and existing operation
   approval requirements remain in force.
4. Save and continue authorizes one prerequisite save, including the whole live
   font, then resumes the retained request. It never authorizes saving the new
   result. Final Save font and guarded Discard remain explicit separate actions.
5. No new native/browser panel, live snapshots, reconciliation, automatic-saving
   preference, cloud relay, compiler/export cards or general queue.

## Interaction

The card identifies the font/path, operation and glyph/master scope. Clean fonts
start immediately. Dirty fonts offer Save and continue, Save As, I'll save in
Glyphs, and Cancel. New fonts require Save As or manual saving. Save As accepts
a folder and filename, shows the destination, and never overwrites. Manual Save
uses Check and continue. Preparing shows real progress, cancellation, and the
fact that editing requires preparing again. Preview offers Apply and Discard
proposal. Applied results say Applied in Glyphs / Not saved and offer Save font,
Save As, and Discard these changes. Outdated preparation offers preparation
again, with an explicit save when needed. Uncertain outcomes reconcile the
existing operation without blind retries. Terminal states show receipts or
recovery evidence. Resolve a previous applied job explicitly, retaining at most
one follow-up. Closing a card does not cancel authorized work.

Natural-language replies select the same actions; users never type tool names,
IDs or JSON. Reuse scoped authorization. State text stays useful without UI or
installed skills. UI failure immediately leaves text operation available.

## Implementation

Add a small sidecar coordinator over existing save/job services. Add
start_edit_workflow (existing request fields, apply/preview mode, idempotency
key), get_edit_workflow (authoritative state/revision/evidence/actions/text), and
respond_edit_workflow (ID, expected revision, action token, optional Save As
destination). Advertise edit.workflow.v1 and preserve the existing nine tools.

Validate scope/capabilities/worker before requesting a save. Bind exact document
identity; revalidate prerequisites before actions. Persist minimal metadata by
existing jobs. Deduplicate retries and simultaneous card/text actions; reject
stale controls. Mark interrupted work on restart and reconcile existing jobs,
never replay saves or mutations. Authorized continuation is independent of the
card or another model turn. Pending choices do not lock native font editing.

Serve ui://glyphs-mcp/edit-workflow-v1.html using standard MCP Apps messages,
tool calls, theme tokens, keyboard/focus support and accessible status updates.
Bundle assets; no external dependencies at runtime or direct UI-to-bridge HTTP.
Poll displayed active work only. Server revisions are authoritative. Every
response carries text plus structured data. Preserve the local Claude stdio
proxy's resources, metadata and results. Update shared skills and client packages
without importing the legacy UI/runtime.

## Qualification

Cursor documents MCP Apps at https://cursor.com/docs/mcp. Claude Desktop uses
the standard through a local connection. Verify actual local Codex capabilities
instead of inferring them from ChatGPT. CLI and unsupported surfaces use text;
record exact client versions and inline/text/unverified results separately.

Test clean/dirty/pathless and similarly named fonts; save/Save As/manual save and
failures; automatic application, preview, no change, warnings and partial scope;
prior-job resolution; stale preparation/cards/paths and closed documents;
duplicate/concurrent requests; transport loss, uncertainty and restart; guarded
discard and recovery; UI failures, missing capabilities, and text without skills.
One authorized Save and continue must complete routine preparation/application
without another user message, leaving results unsaved. All actions must work in
text and all existing validation, Undo, saving, build and installer checks pass.

## Delivery

Coordinator/text contract, shared card, transport/client qualification, then
packages and documentation. Ship text irrespective of rendering capability.
