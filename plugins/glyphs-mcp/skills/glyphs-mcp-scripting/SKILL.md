---
name: glyphs-mcp-scripting
description: Use this skill to vibe-code, preview, run, or debug focused Python scripts inside the live Glyphs app through Glyphs MCP, including Macro Panel snippets and experiments that may later become reusable scripts or plug-ins. Ground unfamiliar GlyphsApp APIs in the bundled documentation and gate every mutation or external side effect.
---

# Glyphs MCP scripting

Turn a natural-language idea into the smallest verifiable Python script for the
running Glyphs app.

## Core rules

- Prefer an existing dedicated MCP tool or domain skill when it already covers
  the task. Keep outline-specific fallback code in `glyphs-mcp-outlines-docs`
  and guarded italic fallback code in `glyphs-mcp-italic-first-pass`.
- Read the live server, font, master, glyph, layer, and selection context needed
  for the request before writing code.
- Search with `docs_search`, then fetch only the relevant pages with `docs_get`
  before using an unfamiliar GlyphsApp API. Target Glyphs 3.5 and Glyphs 4
  unless the user requests one version.
- Use `execute_code_with_context` for glyph- or layer-scoped work. Use
  `execute_code` only when injected font, glyph, and layer context is not useful.
- Keep code focused, validate every target, make repeat runs safe when
  practical, and bound returned output with `max_output_chars` and
  `max_error_chars`.
- Never call `exit()`, `quit()`, or `sys.exit()`. Do not install or reload
  scripts or plug-ins, restart Glyphs, save a font, access files or the network,
  or launch subprocesses without separate explicit authorization.
- Never treat printed output as mutation proof. Re-read affected state with
  dedicated MCP tools and optionally inspect `get_document_change_overview`.

## Workflow

1. Form a compact brief from the request:
   - exact target and scope
   - expected behavior
   - permitted effects
   - observable success condition
2. Resolve missing live context with `get_server_info`, `list_open_fonts`,
   `get_selected_font_and_master`, and the smallest relevant selection or
   inspection tools. Ask only when a consequential target or scope remains
   ambiguous.
3. Search and fetch the focused API documentation needed for the script.
4. Write the smallest working vertical slice. Validate object existence before
   reading or changing it, and summarize outcomes as changed, skipped, and
   failed counts when processing a batch.
5. Classify the exact code before execution:
   - For clearly read-only code that the user asked to run, execute it and
     inspect the bounded result.
   - For any font mutation or external side effect, first call the matching
     execution tool with `snippet_only=true`. Show the exact code, targets, and
     expected changes, then stop for explicit approval.
6. Treat the submitted `code` argument as the reviewed executable. Label the
   returned Macro Panel snippet separately because it wraps that code for manual
   use. Bind approval to the exact execution tool, code, font/glyph context,
   remaining arguments, targets, and side-effect scope.
7. After approval, execute only that unchanged reviewed request. If any bound
   field changes, generate a new snippet and request approval again.
8. For larger layer edits, pair `layer.beginChanges()` and
   `layer.endChanges()` in `try/finally`. Avoid MCP-driven
   `glyph.beginUndo()`/`glyph.endUndo()` because live Glyphs 4 testing found
   that those groups can trigger the undo recovery dialog.
9. Re-read the affected state, compare it with the brief's success condition,
   and report what ran, what changed, what was skipped, errors, and whether the
   font remains unsaved.
10. On a traceback, reduce to a minimal reproducer and retry once. Stop after a
   repeated failure and report any state that may already have changed.

## Reusable artifacts

When the result should become a Script-menu command or a plug-in, route to
`glyphs-mcp-development`. Create the reusable `.py` file or plug-in bundle in
the workspace, retain `# MenuTitle` and `__doc__` for scripts, validate it
statically, and leave live installation or runtime testing as a separate
request.

## Deeper references

- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
- [Safety model](https://github.com/thierryc/Glyphs-mcp/blob/main/content/concepts/safety-model.mdx)
- [Development skill](https://github.com/thierryc/Glyphs-mcp/blob/main/skills/glyphs-mcp-development/SKILL.md)
