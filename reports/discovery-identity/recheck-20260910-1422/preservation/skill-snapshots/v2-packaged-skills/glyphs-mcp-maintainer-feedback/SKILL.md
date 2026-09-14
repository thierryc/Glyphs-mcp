---
name: glyphs-mcp-maintainer-feedback
description: Collect bounded reproduction evidence for a Glyphs MCP issue.
metadata:
  surface: glyphs-mcp-v2
---

# glyphs-mcp-maintainer-feedback

Call `get_status` first and verify the seven-tool Glyphs 4 catalog. Use
`list_documents` to resolve the intended font. Use `read_entities` for at most
100 explicit targets per request. Inspect source and dirty state before work.

Prepare supported work with `start_job`, inspect `get_job` until ready, and
review its report before `apply_job`. Application is a reversible live change;
native Save is acceptance. Use `discard_job` for whole-job restoration or
cancellation. Native Undo and Redo are grouped per glyph. Never save, export,
close, or overwrite a font unless the user's task authorizes it. Do not retry
an uncertain write as a new job; reconcile the existing job identity first.

The public tools are only `get_status`, `list_documents`, `read_entities`,
`start_job`, `get_job`, `apply_job`, and `discard_job`. There is no arbitrary
Python execution tool. Unsupported operations require a reviewed workspace
script or native Glyphs workflow; do not invent an MCP command.

Read status and collect the installed component versions, job identity,
reproduction steps, expected and observed results, and relevant bounded logs.
Use a disposable font and verify the original source remains unchanged. Exclude
authentication tokens and private font data from the report. Prepare the issue
locally; submit to GitHub only when explicitly authorized.

[Documentation](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set-v2.mdx).
