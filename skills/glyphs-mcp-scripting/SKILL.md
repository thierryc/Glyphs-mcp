---
name: glyphs-mcp-scripting
description: Write focused native Glyphs Python scripts when the lean tools do not cover a request.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs 4 scripting

Create a workspace script for the requested one-off native operation. Reusable
plugins and ongoing coding sessions use [$glyphs-mcp-development](../glyphs-mcp-development/SKILL.md).
Writing and statically validating a script need no running Glyphs, MCP,
document discovery or Save. Unrelated Python needs no Glyphs skill.

Use the development skill's [offline documentation](../glyphs-mcp-development/references/development-docs.md)
for unfamiliar APIs and its existing `scaffold.py create script` and
`validate --target 4` commands. Separate pure logic from native access. State
targets, effects and verification; preserve fractional values, native flags,
metadata and object identity.
For coordinate edits, use the [native precision recipe](../glyphs-mcp-development/references/native-precision.md).
For feature work, use [OpenType guidance](../glyphs-mcp-opentype-features/SKILL.md).

Execution follows the user's authorised task. Use disposable copies for
experiments and the [native iteration reference](../glyphs-mcp-development/references/native-iteration.md)
for logs, proofs and cleanup. Static validation is not runtime success. Never
promise full-font recovery for arbitrary Python.

For needed MCP context, reuse the verified [$glyphs](../glyphs/SKILL.md) connection
and intended document ID already in context. Resolve missing bindings through the
[document targeting reference](../glyphs/references/document-targeting.md).
Do not reload the entry, repeat discovery or refetch known API excerpts merely
to switch to scripting. Rediscover after document_not_found, a target change or
bridge/Glyphs restart; never silently substitute another open font. Reads are fresh.
Dirty documents can be inspected without saving.

The seven public tools expose no arbitrary Python execution. Do not add a remote
endpoint or emulate missing private capabilities with scripts. Required missing
capabilities need the bridge, sidecar and skills updated together. A separately
authorised native task does not establish MCP support. Existing job Undo/discard
guarantees do not extend to arbitrary scripts.
