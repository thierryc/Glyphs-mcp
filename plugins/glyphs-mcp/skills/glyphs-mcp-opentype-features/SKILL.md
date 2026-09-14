---
name: glyphs-mcp-opentype-features
description: Review, write and debug OpenType feature source using native Glyphs 4 scripts, with compilation and exported behavior checks.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs 4 OpenType features

Start from the requested feature, font source and workspace. Use the focused
[native feature workflow](references/native-features.md) for review, source
changes or compiler diagnostics. Creating or reviewing a script needs no open
Glyphs document, MCP connection or document discovery.

Author scripts with normal file tools and execute through the existing native
Glyphs route within the user's task. The seven MCP tools provide neither feature
editing nor arbitrary Python execution. Native compilation, export and shaping
are separate evidence; job preview and discard do not apply to these scripts.

Reuse the target, workspace and relevant references already in context. For
needed live MCP reads, retain the connection's document ID through
[document targeting](../glyphs/references/document-targeting.md). An isolated
native runner needs its own explicit source path; it does not share that live
document or its unsaved changes.
