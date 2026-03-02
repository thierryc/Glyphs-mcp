# Glyphs MCP Guide

Glyphs MCP is a local MCP server that runs inside Glyphs 3.

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
- Use `capture_output=false` for large loops.
- Use `max_output_chars` and `max_error_chars` to bound output.
- If you want manual control, request a Macro Panel snippet via `snippet_only=true` (returns code to paste; does not execute).
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
- Per-page resource registration is optional and noisy; call `docs_enable_page_resources` only when explicitly needed.

## Response Style

- Be concise and operational.
- Include exact tool names and concrete target identifiers.
- Distinguish clearly between facts from tool output and inferences.
- For edits, always include: target scope, actions executed, verification result, and unresolved risks.
