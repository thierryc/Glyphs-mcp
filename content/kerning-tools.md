---
title: Kerning tools
description: Audit collisions and apply conservative “bumper” fixes as glyph–glyph exceptions.
---

These tools help you **audit** kerning with a geometry-based collision guard, and optionally **apply** conservative “bumper” fixes as **glyph–glyph exceptions**.

- `review_kerning_bumper` measures outline gaps and returns findings + suggestions (no mutation).
- `apply_kerning_bumper` applies the same suggestions as kerning exceptions (requires a confirmation gate).

The intent is typographer-first:
- Deterministic geometry measurements (objective).
- Human/LLM judgement for “best” kerning values (aesthetic).
- Safe defaults and explicit confirmation for mutation.

---

## When to use it

Use these tools after spacing and kerning groups have had a first pass. They are best for:

- detecting outline collisions or near-misses,
- generating a conservative list of pairs that need more space,
- applying approved glyph-glyph exception fixes,
- opening proof tabs for the worst offenders.

Do not treat the bumper tools as an optical kerning engine. They are a safety guardrail.

---

## What the tools change (and what they don’t)

### Changes (only when applied)
- Adds/updates **glyph–glyph kerning exceptions** for a master.

### Does not change
- Outlines (paths)
- Components
- Anchors
- Sidebearings / widths
- Kerning classes (group kerning)
- Any files on disk (no auto-save)

---

## Core idea (plain language)

For a given pair of glyphs in a master:
1) Place the right glyph after the left glyph using `leftWidth + kerningValue`.
2) Across the glyphs’ **vertical overlap range**, cast horizontal scanlines at multiple `y` values.
3) At each scanline, find:
   - the **rightmost** intersection of the left glyph (its right edge at that y),
   - the **leftmost** intersection of the right glyph (its left edge at that y).
4) Compute the **gap** between outlines at that y.
5) Keep the **minimum** gap across all scanlines (the “worst” place), and also report minima per vertical band.

If the minimum gap is below your configured `min_gap`, the tool proposes a **bumper**:
- the minimal **kerning loosening** (increase) needed to reach the gap constraint.

---

## Pair selection (what gets analyzed)

By default, the tools analyze a prioritized pair list:
1) Top‑N pairs from the bundled **Andre Fuchs “relevant pairs”** dataset (MIT snapshot, local/offline).
2) Plus representative pairs from your **existing explicit kerning** in the master (optional).

Controls:
- `relevant_limit`: how many “top pairs” are considered.
- `include_existing`: include representative pairs from existing kerning.
- `pair_limit`: hard cap on measured glyph pairs (performance guard).
- `glyph_names`: focus filter (keep only pairs where left or right is in the list).

---

## Scan strategy (BubbleKern-style)

The measurement uses a scan strategy similar in spirit to scan-height approaches:

### `scan_mode`
- `two_pass` (default): quick scan at a few normalized heights, then refine with a dense scan **only when near the threshold**.
- `heights_only`: only the quick scan heights (fastest; can miss tiny collisions).
- `dense_only`: dense scan for every pair (slowest; most thorough).

### `scan_heights`
Normalized heights within the overlap band, default:
`[0.05, 0.15, 0.35, 0.65, 0.75]`

### `dense_step`
Dense scan step in font units (e.g. `10.0` units).

### `bands`
Number of equal vertical bands used for `bandMinGaps` reporting.

---

## Bumper behavior (safety)

### `min_gap`
The minimum allowed outline gap in font units.

### `extra_gap` (apply tool only)
Adds extra cushion above `min_gap` when applying.

### `max_delta` (apply tool only)
Clamps how much the tool will loosen kerning per pair (in units), to prevent wild swings.

### “Only loosen”
The tools only propose/apply **loosening** (increasing kerning values). They never tighten.

---

## Limitations and caveats (important)

- This is a **collision guard**, not an “optical” kerning engine.
- Class–class kerning is represented by a **single representative glyph pair** for measurement; other members can still collide.
- Scanline intersection measurements depend on what `layer.intersectionsBetweenPoints` returns; very complex shapes or special layers may yield fewer usable samples.
- Fonts with unusual metrics conventions (very negative sidebearings, extreme overshoots) can yield legitimate collisions even with positive kerning.

---

## Related reference

- [Kerning workflow](./kerning-workflow.md)
- [Command set](./reference/command-set.mdx)
- [Safety model](./concepts/safety-model.mdx)

---

## Prompt templates (copy/paste)

### Review only
```text
In Glyphs, review kerning collisions in my current font/master.
Rules:
- Do not mutate anything.
- Summarize the worst problems first.

Call review_kerning_bumper:
{"font_index":0,"min_gap":5,"relevant_limit":2000,"include_existing":true,"scan_mode":"two_pass","dense_step":10,"bands":8,"result_limit":200}

Then:
- list the 20 worst collisions with recommendedException
- tell me which ones should be class kerning vs exceptions
```

### Dry run apply → confirm apply
```text
Fix collisions by adding glyph–glyph kerning exceptions only.
Rules:
- Never auto-save.
- Never mutate without a dry run first.
- Only loosen (never tighten).

1) Call apply_kerning_bumper (dry run):
{"font_index":0,"dry_run":true,"min_gap":5,"extra_gap":0,"max_delta":200,"relevant_limit":2000,"include_existing":true}

2) If I approve, call apply_kerning_bumper again with confirm=true using the same args.
3) After applying, open a proof tab:
Call review_kerning_bumper:
{"font_index":0,"min_gap":5,"open_tab":true,"result_limit":120,"rendering":"hybrid"}
```

---

## Inspirations

This implementation is designed as a clean-room, geometry-first tool, inspired by:
- BubbleKern scan-height ideas (conceptual scan strategy).
- mekkablue Glyphs scripts (audit mindset: GapFinder/KernCrasher/Auto Bumper concepts).
- FontForge’s auto-kerning ideas (minimum separation / collision avoidance).
- “Learning to Kern” (research literature; not used as code/data).
