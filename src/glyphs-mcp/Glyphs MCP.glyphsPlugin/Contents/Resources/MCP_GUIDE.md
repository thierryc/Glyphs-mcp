# Glyphs MCP Guide

Glyphs MCP is a local MCP server that runs inside Glyphs.

Endpoint: `http://127.0.0.1:9680/mcp/` over MCP Streamable HTTP (SSE).  
If your coding agent cannot connect, launch Glyphs fresh, start the MCP server first, then launch the coding agent.

## Mission

Execute Glyphs tools reliably and safely to inspect and edit fonts in the running app.

- Prefer deterministic tool usage over speculative code.
- Keep mutations minimal and verifiable.
- Use resources to improve correctness, not as the primary workflow.

## Execution Contract

Follow this flow for every task:

1. Read current context first.
2. Confirm target objects (font, master, glyph, layer, selection) from tool output.
3. Perform the smallest valid mutation.
4. Read back and verify the result.
5. Report exactly what changed, what was skipped, and any residual risk.

When mutating, do not skip preflight reads.

## Tool Selection Policy

Choose tools in this order:

1. Dedicated inspection/edit tools for direct operations.
2. `execute_code_with_context` for multi-step glyph workflows that depend on current font/glyph/layer context.
3. `execute_code` for broader scripts when context injection is unnecessary.

Use `docs_search` and `docs_get` when API details are uncertain.

## Native Curvature Review

Use `review_curve_quality` for explicit JSON measurements, then call
`set_curve_review_overlay(enabled=true, overlays=["curvature", "curve_events"])` and direct the user to **View > Show
Glyphs MCP Curvature**. The native Reporter draws the signed comb directly in
Glyphs at `0.65` alpha so the outline remains legible beneath it, and remains
available when the MCP server is stopped. It starts with 51 samples per cubic,
a `0.010` scale, and a `0.12em` normal clamp. Curvature magnitude follows the
path right normal, so correctly wound counter combs point into the white
counter; signed curvature still controls teal/pink colors. Call
`get_curve_review_overlay_state` to verify the last glyph/layer, stroke/event
caps, errors, and components omitted from the raw-path calculation. Adaptive
event markers identify extrema, inflections, cusps, and continuity warnings.

## Native Candidate Review

Use the typed `preview_*_candidate` tools as the default for Tunni, collinear
smoothing, italic-first-pass, and compensated-tuning work. Candidate sessions
are required for multi-master or multi-glyph batches. Preview automatically
enables **View > Show Glyphs MCP Candidate**. The normal Glyphs outline remains
the reference; only its symmetric difference from the candidate is added in
warm golden yellow. A stale source turns the difference coral red and adds a
`STALE` label. Curvature is intentionally separate under **View > Show Glyphs
MCP Curvature** so candidate decisions stay readable.

If the proposal needs no manual edit, call `review_outline_candidate_session`,
dry-run `accept_outline_candidate_session`, stop for approval, then confirm with
the exact issued token. If manual editing is wanted, materialize the session as
native layers, let the user edit them normally, and re-review before accepting.
Use `discard_outline_candidate_session` to delete owned candidate layers;
`set_outline_candidate_overlay(clear_session=true)` clears UI state only.
Never rely on conversational context as candidate ownership metadata and never
save automatically.

## Glyphs 3 Compatibility

Glyphs MCP supports Glyphs 3 and Glyphs 4 from `main`. When `get_server_info`
reports Glyphs `3.x`, treat
sidebearing reads/writes as best-effort and prefer dry runs before confirmed
spacing or metric mutations.

Load `glyphs://glyphs-mcp/glyphs3-compatibility` for the current Glyphs 3
limitations list. In particular, avoid escalating structured Glyphs 3 limitation
errors into larger retry scripts.

## Glyphs Show Links

Glyph/layer read tools may return `showUrl`, `showHttpUrl`, and `showMarkdown`
fields. Use `showMarkdown` in final answers when it helps the user jump directly
to the reported glyph or layer in Glyphs.

- `showUrl` uses `glyphsapp://show/`; `showMarkdown` uses the local
  `http://127.0.0.1:9680/glyphs-show/` bridge so LLM clients that block custom
  URL schemes can still render a clickable link.
- Links require a saved font path.
- If a font is unsaved, tools return `showUrlUnavailableReason` instead.
- These links open the containing glyph/layer only; they do not select nodes,
  anchors, components, or paths.
- For "style set", "stylistic set", or `ssXX` listing questions, call
  `list_style_sets` first. Use each style set's group-level `showMarkdown` in
  the final answer and list glyph names as plain text unless the user asks for
  per-glyph links.

## Balanced execute_code Policy

`execute_code` and `execute_code_with_context` can run arbitrary Python in Glyphs.

Use them early when they improve reliability for complex tasks, especially when:

- A task would otherwise require 3 or more dependent tool calls.
- Cross-master mapping or path surgery is easier to implement and validate in one script.
- A single scripted pass reduces partial-update risk.

Execution rules:

- Keep scripts focused and minimal.
- Validate object existence before mutating.
- Summarize outcomes with counts (changed, skipped, failed).
- Prefer one robust call over many chatty calls.
- Prefer `execute_code_with_context` for glyph-scoped mutations so the script gets `font`, `glyph`, and `layer`.
- Use `capture_output=false` for large loops.
- Use `max_output_chars` and `max_error_chars` to bound output.
- If you want manual control, request a Macro Panel snippet via `snippet_only=true` (returns code to paste; does not execute).
- Large glyph edits should use documented `layer.beginChanges()/endChanges()` blocks; avoid `glyph.beginUndo()/endUndo()` in MCP-driven scripts because live Glyphs 4 QA showed those undo groups can trigger Glyphs' undo recovery dialog.
- Glyphs undo is glyph-scoped, so master/global edits are not guaranteed undoable.
- Never call `exit()`, `quit()`, or `sys.exit()`.

## Mutation Safety Protocol

Before any mutation:

1. Identify exact targets from read tools.
2. Check preconditions (font open, glyph exists, master/layer exists, selection present).
3. Confirm operation scope (single glyph, selected glyphs, or all masters).

During mutation:

- Avoid destructive operations unless explicitly requested.
- Keep operations idempotent when practical.
- For batch operations, continue past per-item failures and collect failures for reporting.

After mutation:

1. Re-read the affected entities.
2. Verify expected structural and metric changes.
3. Report final state with explicit counts.

## Failure and Retry Playbook

If a call fails, use this retry order:

1. Argument or schema error: fix arguments and retry once.
2. Missing context or target: run context reads, then retry once.
3. Runtime traceback in `execute_code*`: reduce scope to a minimal reproducer, then retry once.

If retries still fail, stop and return:

- The failing step.
- Error summary.
- What was already changed (if anything).
- The most likely next action.

## Docs Usage Policy

Resources are helpers.

- First preference for docs: `docs_search` then `docs_get`.
- Docs index resource: `glyphs://glyphs-mcp/docs/index.json`.
- Documentation stays lean: use `docs_search` and `docs_get` instead of registering every page as a resource.

## Response Style

- Be concise and operational.
- Include exact tool names and concrete target identifiers.
- Distinguish clearly between facts from tool output and inferences.
- For edits, always include: target scope, actions executed, verification result, and unresolved risks.
