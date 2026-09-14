---
title: Kerning workflow
description: A typographer-first kerning sequence for Glyphs MCP.
---

Use this workflow when you want an agent to help you proof kerning, generate worklists, audit collisions, and apply approved bumper fixes without replacing typographic judgement.

Kerning should stay human-led: spacing first, groups/classes first, exceptions only when there is proof.

## When to use it

- You want a structured kerning pass in Glyphs.
- You need a worklist proof tab for missing or suspicious pairs.
- You want a collision or near-miss guardrail.
- You want an agent to summarize kerning outliers before you edit.

## What changes

Nothing changes during `generate_kerning_tab` or `review_kerning_bumper`.

Only explicit mutating tools change kerning:

- `apply_kerning_bumper` can add or update glyph-glyph kerning exceptions.
- `set_kerning_pair` can set or remove a specific kerning pair.

Use dry runs and explicit approval before any mutation.

## What does not change

- Outlines
- Components
- Anchors
- Spacing and sidebearings
- Kerning groups/classes, unless you explicitly edit glyph properties
- Files on disk, unless you call `save_font`

## Recommended sequence

1. Pick the font and master with `list_open_fonts` and `get_font_masters`.
2. Run a spacing sanity pass first if sidebearings look inconsistent.
3. Audit kerning groups before adding exceptions.
4. Generate a proof tab with `generate_kerning_tab`.
5. Review collisions or near-misses with `review_kerning_bumper`.
6. Run `apply_kerning_bumper` with `dry_run=true`.
7. Apply only after approval with `confirm=true`.
8. Proof visually in Glyphs.
9. Save only when you decide to call `save_font`.

## Safe prompt template

```text
Use the glyphs-mcp-kerning skill.

Task: Review kerning for my current font and master.

Rules:
- Read current font and master first.
- Do not mutate during review.
- Prefer group/class kerning. Treat glyph-glyph exceptions as last-mile fixes.
- Run review_kerning_bumper before any apply step.
- Run apply_kerning_bumper with dry_run=true before mutation.
- Wait for me to reply exactly "apply" before using confirm=true.
- Never auto-save.

1. Call list_open_fonts and get_font_masters.
2. Call generate_kerning_tab for a review proof.
3. Call review_kerning_bumper and summarize the 20 worst findings.
4. If useful, dry-run apply_kerning_bumper and stop for approval.
```

## Related reference

- [Kerning tools](./kerning-tools.md)
- [Command set](./reference/command-set.mdx)
- [Safety model](./concepts/safety-model.mdx)
