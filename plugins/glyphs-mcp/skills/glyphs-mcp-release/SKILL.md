---
name: glyphs-mcp-release
description: Prepare and verify a local Glyphs MCP candidate while keeping publication separate.
metadata:
  surface: glyphs-mcp-v2
---

# glyphs-mcp-release

Offline build/package work needs no MCP connection or font discovery. For
requested installation verification, obtain fresh status and compare component
identities with the candidate. Use [connection setup](../glyphs/references/connection-session.md)
only if this connection is unverified or changed. Discover a font only for a
font-specific native test; reuse its ID through [document targeting](../glyphs/references/document-targeting.md).

Inspect the current branch and preserve uncommitted work. Keep Glyphs 3 pinned
to 1.11.0. Build deterministic bridge, sidecar, runtime and companion artifacts;
verify source versions, installer build, managed skills and component hashes.
Run checks appropriate to the changed components. Native disposable-font gates
apply when native behavior changed or that qualification was requested.
Report baseline and loaded timings separately; 200 ms is diagnostic.

Local preparation does not authorize committing, merging, tagging, pushing,
signing, notarizing, uploading assets or publication. Treat each public release
phase separately. Report the artifact paths, versions, checksums, installation
receipt and actual acceptance results. See the repository release procedure.

[Documentation](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set-v2.mdx).
