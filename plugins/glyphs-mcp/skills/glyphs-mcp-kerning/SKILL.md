---
name: glyphs-mcp-kerning
description: Inspect stored kerning, reason about exact pair or contextual proposals, and apply one verified generic Glyphs transaction.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP kerning

The tools expose stored mechanics. This skill owns optical judgment, grouping,
exceptions, proof strings, and contextual intent.

## Evidence

1. Call `get_server_info`, require `data.apiMajor == 2`, resolve one font with
   `list_documents`, and retain its fingerprint.
2. Search `search_knowledge` for current Glyphs kerning keys, directions,
   groups, exceptions, contextual storage, and OpenType behavior. Retrieve
   decisive entries with `get_knowledge`.
3. Use `read_document` with `entity="kerning"` plus exact master, direction,
   left/right, or context parent filters. Read glyph metadata separately when
   group resolution or proof selection needs it. Keep LTR, RTL, vertical, and
   context domains distinct; unresolved native keys remain evidence.
4. Use `execute_python(mode="read_only")` for effective pair resolution or
   Glyphs-native context details not represented by canonical reads. Bound the
   requested pairs and reject observed mutation.

## Decisions and writes

Choose reference strings across rounds, diagonals, straights, punctuation,
marks, and scripts. Separate class behavior from exceptions and report missing
coverage rather than inventing it. Contextual changes must identify the exact
sequence, boundary, master, and intended additive value.

Express approved storage changes as explicit generic mechanics:

- `set` an existing exact kerning scalar;
- `insert` a new exact pair/context mapping;
- `remove` an exact stored entry.

Add before constraints for current stored values and after constraints for the
requested values. Call `preview_change`, inspect the full semantic diff and
pair-domain preservation, then apply its exact `previewId` with `apply_change`.
Re-read stored results and proof the affected strings. Use
`execute_python(mode="staged_document")` only for an unsupported document edit,
and still apply its preview through `apply_change`. Never call `save_document`
automatically.

Use [the context-kerning reference](references/context-kerning.md) for advanced
sequence storage, additive semantics, manual feature-code routing, and proofing.
