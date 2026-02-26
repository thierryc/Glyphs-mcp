---
title: Kerning workflow
description: A practical, typographer-first kerning checklist and “go-through” tutorial with copy/paste-ready prompts.
---

This page is a practical, typographer‑first kerning checklist and “go‑through” tutorial, aligned with Glyphs’ kerning workflow as described in the official **Kerning** tutorial on glyphsapp.com.

It assumes you’re using the **Glyphs MCP** server so an LLM can:
- generate proof tabs,
- audit kerning data,
- detect collisions/near‑misses geometrically, and
- apply conservative “bumper” fixes safely (confirm‑gated).

> Note: tool name prefixes vary by client. If your tools aren’t named `glyphs-app-mcp__*`, replace that prefix with whatever your MCP client shows.

---

## Kerning to‑do list (quick checklist)

### Setup + proofing
- [ ] Proof in **context** (use real words/strings, not isolated pairs) and at the **intended size**.
- [ ] In Glyphs: enable **View → Show Metrics** so kerning indicators are visible.
- [ ] Optional: set kerning increments (low/high) so manual kerning is consistent (see prompts below).

### Spacing first (kerning comes late)
- [ ] Run a spacing pass on key glyphs (or your current selection).
- [ ] If you see lots of kerning under ~10 units, revisit spacing instead of “micro‑kerning”.

### Kerning groups (classes) first
- [ ] Ensure core glyphs have consistent **left/right kerning groups**.
- [ ] Prefer **group kerning** (locks closed) and only create exceptions when you have proof.
- [ ] When checking group kerning in Glyphs, use **View → Show Group Members** to spot collisions in diacritics.

### Kern methodically
- [ ] Work through group combinations in a stable order:
  - [ ] lowercase→lowercase
  - [ ] uppercase→lowercase
  - [ ] uppercase→uppercase
  - [ ] punctuation around letters
  - [ ] punctuation around figures
  - [ ] punctuation→punctuation
- [ ] Keep an “unkerned reference” pair visible (e.g. `nn` or `HH`) to avoid overkern.
- [ ] Avoid aggressive overkern (rule of thumb: don’t kern beyond ~40% of glyph width).

### Exceptions + audits
- [ ] Add exceptions only where needed (group→glyph, glyph→group, glyph→glyph).
- [ ] Run collision/near‑miss audit (`review_kerning_bumper`) and apply safe loosening only when approved.
- [ ] Audit outliers (tightest/widest) and fix rhythm breakers.

### Clean up + final proof
- [ ] Clean redundant/ineffective pairs (Glyphs Kerning window has Clean up / Compress; optional).
- [ ] Re‑proof with multiple sample strings and re‑run audits.
- [ ] Save (`save_font`) only when you’re happy.

---

## Tutorial: a simple “go‑through” (LLM‑assisted)

### Step 0 — Pick the font/master you’re working on
```text
List open fonts and tell me which font_index to use.
Call glyphs-app-mcp__list_open_fonts.
```

```text
For font_index 0, list masters and tell me the master_id for the master I’m editing.
Call glyphs-app-mcp__get_font_masters with: {"font_index":0}
```

### Step 1 — Spacing sanity pass (before kerning)
```text
You are my spacing assistant.
Rules:
- Never auto-save.
- Never mutate without a dry run first.
- Keep changes conservative (use clamping).

Task: Review spacing for my current selection in the active font.

1) Call glyphs-app-mcp__review_spacing: {"font_index":0}
2) Summarize the top spacing outliers and skip reasons.
3) Call glyphs-app-mcp__apply_spacing (dry run):
{"font_index":0,"dry_run":true,"clamp":{"maxDeltaLSB":80,"maxDeltaRSB":80,"minLSB":-50,"minRSB":-50}}
4) Wait for my approval before applying with confirm=true.
```

### Step 2 — Audit kerning groups (classes)
Use this to find missing or inconsistent kerning group assignments quickly.

```text
Audit kerning groups for my font.

1) Call glyphs-app-mcp__get_font_glyphs: {"font_index":0}
2) Focus on Latin letters + punctuation and list:
   - glyphs with missing leftKerningGroup/rightKerningGroup
   - glyphs whose groups look suspicious (e.g. obvious outliers)
3) Propose a conservative “grouping to-do list” (do not apply changes yet).
```

If you want the LLM to apply group edits, keep it explicit and confirm each batch:
```text
Apply kerning group fixes as follows (ask before mutating):
1) Show me the exact list of update_glyph_properties calls you intend to make.
2) After I reply “apply”, execute them.
```

### Step 3 — Generate a kerning worklist proof tab (relevance-based)
```text
Open a kerning review proof tab for my current font/master.

Call glyphs-app-mcp__generate_kerning_tab:
{"font_index":0,"rendering":"hybrid","relevant_limit":2000,"missing_limit":800,"audit_limit":200,"per_line":12}

Then:
- Tell me which section is for what.
- Extract the first 30 missing pairs and tell me which 10 to kern first (class-first).
```

### Step 4 — Collision/near‑miss guardrail (geometry)
This is the “don’t let outlines touch” pass. It’s intentionally conservative and deterministic.

```text
Review kerning collisions/near-misses in my current font/master.
Rules:
- Do not mutate anything.
- Prioritize the worst collisions first.

Call glyphs-app-mcp__review_kerning_bumper:
{"font_index":0,"min_gap":5,"relevant_limit":2000,"include_existing":true,"scan_mode":"two_pass","dense_step":10,"bands":8,"result_limit":200}

Then:
- List the 20 worst collisions (lowest minGap) and the recommendedException.
- Explain which ones are likely “true collisions” vs diacritic edge cases.
```

Open a proof tab for the worst offenders:
```text
Open a proof tab for the worst collision pairs so I can inspect them by eye.

Call glyphs-app-mcp__review_kerning_bumper:
{"font_index":0,"min_gap":5,"open_tab":true,"result_limit":120,"rendering":"hybrid","per_line":12}
```

### Step 5 — Apply “bumper” fixes safely (dry-run → confirm)
This writes **glyph–glyph kerning exceptions only** (never class kerning).

```text
Fix collisions by adding glyph–glyph kerning exceptions only.
Rules:
- Never auto-save.
- Never mutate without a dry run first.
- Only loosen (never tighten).

1) Call glyphs-app-mcp__apply_kerning_bumper (dry run):
{"font_index":0,"dry_run":true,"min_gap":5,"extra_gap":0,"max_delta":200,"relevant_limit":2000,"include_existing":true}

2) Show me the first 50 proposed changes (old → new) and the biggest deltas.
3) If I say “apply”, call apply_kerning_bumper again with confirm=true using the same args.
4) After applying, call review_kerning_bumper with open_tab=true so I can re-proof.
```

### Step 6 — Audit outliers (rhythm breakers)
```text
Open a kerning audit tab showing only outliers (tightest + widest existing explicit kerning).

Call glyphs-app-mcp__generate_kerning_tab:
{"font_index":0,"missing_limit":0,"audit_limit":250,"rendering":"hybrid"}

Then explain what the worst outliers likely indicate (overkern, punctuation traps, bad groups, etc.).
```

### Step 7 — Save (only when you’re happy)
```text
If (and only if) I say “save”, call glyphs-app-mcp__save_font with {"font_index":0}.
```

---

## Optional: set kerning increments (keyboard workflow helper)

Glyphs supports separate “low/high” kerning increments. If you want the LLM to set them, use `execute_code`:

```text
Set kerning increments to low=10, high=50 for the current Glyphs app session.
Call glyphs-app-mcp__execute_code with:
{"code":"from GlyphsApp import Glyphs\\nGlyphs.defaults['GSKerningIncrementLow']=10\\nGlyphs.defaults['GSKerningIncrementHigh']=50\\nprint('Kerning increments set: low=10, high=50')"}
```
