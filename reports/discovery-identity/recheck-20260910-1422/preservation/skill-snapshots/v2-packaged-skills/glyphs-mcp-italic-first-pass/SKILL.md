---
name: glyphs-mcp-italic-first-pass
description: Prepare a first-pass slant on a disposable or explicitly authorized font.
metadata:
  surface: glyphs-mcp-v2
---

# glyphs-mcp-italic-first-pass

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

Prepare kind="slant" with the requested angle and scope. Use a disposable copy
for exploration. Inspect all-master compatibility, unchanged widths, anchors,
components, topology and background material. Optional straight-stem
preservation is a separate explicit choice. Symbol drawing decisions remain
with the designer; do not silently exclude glyphs. This is a first pass, not
a finished italic or a compensated italic engine.
See [lean first pass](references/lean-v2.md).

[Documentation](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set-v2.mdx).
