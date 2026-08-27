---
name: glyphs-mcp-kerning
description: Review and safely apply Glyphs 4 directional pair or exact-sequence contextual kerning, with explicit coverage and exported visual proof.
surface: glyphs-mcp-v2
---

# Glyphs MCP v2 kerning

Use the deployed v2 kerning surface for ordinary directional pairs and Glyphs
4 contextual kerning. Contextual values are additional to ordinary kerning and
must be considered only after spacing, groups, and normal pair kerning are
finished. The tools do not measure optical clearance or shaping quality.

## Core rules

- Resolve the exact font with `get_server_info`, `list_open_fonts`, and
  `get_document_status`. Keep its stable `documentId` and current fingerprint.
- Use `list_kerning_pairs` with `entryKind="pair"` for ordinary values. Pair
  records identify `ltr`, `rtl`, or `vertical`; never collapse those domains.
- Use `list_kerning_pairs` with `entryKind="context"` for Glyphs 4 contexts.
  Exact-glyph records expose a sequence and one-based boundary. Raw class or
  manually authored contexts are visible but intentionally not editable.
- Use `review_kerning_coverage` to report which eligible pairs were measured,
  skipped, or remain untested. Use `mode="context_sequences"` for contexts.
- Propose only explicit, human-reviewed values. Do not invent a bumper,
  clearance threshold, collision result, or context from stored values alone.
- When the user has clearly authorized the edit, call
  `apply_kerning_updates` once with the complete typed batch, current
  fingerprint, and reason. Mixed pair/context updates are one transaction.
- Re-read affected entries and the document status after applying. Report the
  operation ID, observed changes, skipped items, and revert availability.
- Never save the font automatically.

## Route the work

1. Finish spacing and metrics inheritance through `glyphs-mcp-spacing`.
2. Finish ordinary pair and group kerning in every relevant direction and
   master. Use this route for `VA`, `To`, and other two-glyph relationships.
3. Use context kerning only for a longer exact sequence whose complete context
   changes one boundary, commonly punctuation, apostrophes, or spaces.
4. Route class-based, tokenized, or hand-authored GPOS code to
   `glyphs-mcp-opentype-features`; do not rewrite it through the exact-sequence
   context contract.

## Context workflow

1. Type and inspect the complete positive sequence in Edit View. In Glyphs 4,
   **Spacing -> Kerning -> Context Kerning** provides the native editing mode.
2. List stored contexts and inspect all relevant masters. Establish eligible,
   reviewed, skipped, and untested counts with `context_sequences` coverage.
3. Identify each boundary independently. For `L quoteright A`, boundary `1`
   means `L|’A`; boundary `2` means `L’|A`.
4. Present current and proposed values per master, plus negative controls such
   as `L’O`, `l’A`, and an unrelated apostrophe next to `A`. State:
   “Context values are additional to ordinary kerning. Geometry clearance was
   not measured by Glyphs MCP v2.”
5. After authorization, submit every approved boundary in one
   `apply_kerning_updates` batch. Use `null` to remove a context; numeric zero
   remains a stored value.
6. Re-list the exact context, verify ordinary LTR/RTL/vertical pairs are
   unchanged, and leave the font open and unsaved for visual proof.
7. Test the exported font with `kern` on and off, across required masters or
   variable-font positions, in Text Preview/CoreText and at least one external
   shaping environment. The positive sequence must change; negative controls
   must not.

Read [Advanced contextual kerning](references/context-kerning.md) before
planning or applying any contextual update.

## Deeper references

- [Glyphs MCP 2 foundation](https://github.com/thierryc/Glyphs-mcp/blob/main/content/contributor/glyphs-mcp-2-foundation.mdx)
- [Project briefing](https://github.com/thierryc/Glyphs-mcp/blob/main/CODEX.md)
