---
name: glyphs-mcp-release
description: Prepare and verify a local Glyphs MCP candidate while keeping publication separate.
metadata:
  surface: glyphs-mcp-v2
---

# glyphs-mcp-release

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

Inspect the current branch and preserve uncommitted work. Keep Glyphs 3 pinned
to 1.11.0. Build deterministic bridge, sidecar, runtime and companion artifacts;
verify source versions, installer build, managed skills and component hashes.
Run Python, installer, companion, documentation and disposable-font gates.
Report baseline and loaded timings separately; 200 ms is diagnostic.

Local preparation does not authorize committing, merging, tagging, pushing,
signing, notarizing, uploading assets or publication. Treat each public release
phase separately. Report the artifact paths, versions, checksums, installation
receipt and actual acceptance results. See the repository release procedure.

[Documentation](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set-v2.mdx).
