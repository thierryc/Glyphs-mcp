---
name: glyphs-mcp-scripting
description: Write focused native Glyphs Python scripts when the lean tools do not cover a request.
metadata:
  surface: glyphs-mcp-v2
---

# glyphs-mcp-scripting

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

Produce a workspace script for an unsupported operation. Read the pinned
GlyphsSDK and native documentation for unfamiliar APIs. State affected targets,
expected effects and verification. Use an authorized disposable copy for
experiments. Preserve fractional coordinates, native flags, metadata and
object identity. Run only when the user's request authorizes execution and
report exact readback. Do not add a remote execution endpoint to the bridge.

[Documentation](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set-v2.mdx).
