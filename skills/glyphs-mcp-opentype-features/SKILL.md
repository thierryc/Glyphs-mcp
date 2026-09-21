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

For updating Glyphs-managed automatic prefixes, classes and features, prefer
the advertised `native_action` named `update_features` and follow the
[closed native-action contract](../glyphs/references/native-actions.md). Its
native `updateFeatures()` call includes Glyphs' automatic update/compilation
behavior; inspect the generated source and diagnostics before acceptance.

For compiler-only evidence, use the advertised closed `feature_compile` job and
[feature-compilation workflow](../glyphs/references/feature-compilation.md).
For a generated binary or feature-on/off behavior, use the advertised
`font_export` job and [verified export workflow](../glyphs/references/font-export.md).
These remain inside the same nine-tool surface and do not expose arbitrary code.

Author scripts with normal file tools for genuinely unsupported feature-source
work and execute them through the existing native Glyphs route within the
user's task. The nine MCP tools provide no arbitrary Python execution.
Compilation, export and shaping remain separate evidence; MCP diagnostic and
artifact lifecycles differ from scripts. Never replace a missing advertised
`update_features` capability with an implicit script.

Reuse the target, workspace and relevant references already in context. For
needed live MCP reads, retain the connection's document ID through
[document targeting](../glyphs/references/document-targeting.md). An isolated
native runner needs its own explicit source path; it does not share that live
document or its unsaved changes.
