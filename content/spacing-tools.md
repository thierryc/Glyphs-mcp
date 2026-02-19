# Spacing Tools: `review_spacing` and `apply_spacing`

These tools help you **review** and optionally **apply** consistent sidebearings across a set of glyphs in a Glyphs font.

- `review_spacing` computes measurements and returns **suggested** metrics (no mutation).
- `apply_spacing` uses the same logic to **apply** those suggestions (with a required confirmation gate).

The intent is to make spacing more systematic and repeatable, while keeping you in control through:
1) clear per-glyph reporting, and  
2) conservative safety defaults (skip rules + clamping).

---

## What the tools change (and what they don’t)

### Changes
When applied, these tools adjust:
- **LSB** (left sidebearing)
- **RSB** (right sidebearing)
- optionally **width** (mainly for tabular figures / fixed-width targets)

### Does not change
- Outlines (paths)
- Kerning
- Components (except they may be included in measurement)
- Anchors

---

## Core idea (plain language)

For each glyph layer (glyph + master):
1) Choose a **vertical measurement band** (`yMin..yMax`) using a **reference glyph**.
2) At regular `y` steps (frequency), cast a horizontal “measurement line” through the glyph.
3) For each `y`, find the **first** intersection from the left and the **last** intersection from the right.
4) Convert those intersections into two numbers:
   - how much the glyph intrudes to the **left** of its “left edge” in that band,
   - how much it intrudes to the **right** of its “right edge” in that band.
5) Integrate (sum) these values across the band to get **left/right “area”** measurements.
6) Compare the measured areas to a **target area**, then compute suggested LSB/RSB changes.

This is designed to approximate how much “white space” a reader perceives around a glyph, not just the extreme sidebearings at one height.

---

## Reference glyphs and the measurement band

Many glyphs need different vertical measurement ranges:
- Lowercase letters typically want a band around the x-height region.
- Uppercase letters may want a taller band.
- Punctuation and symbols can require special handling.

These tools use a **reference glyph** to define the band:
- Find the reference layer’s bounds in the same master.
- Take `yMin..yMax` from those bounds.
- Extend it by `over` (as a percent of xHeight) above and below.

If a glyph doesn’t overlap enough with the band (coverage ratio), it is skipped to avoid nonsense measurements.

---

## Important safety skips (by default)

The tools skip glyphs/layers when they are likely to be unsafe or misleading to auto-space:

1) **Empty layers** (no paths and no components).
2) **Combining marks / nonspacing marks** (they should typically stay width 0).
3) **Auto-aligned component layers** (`layer.isAligned == true`) when `skipAutoAligned=true`.
4) **Metrics keys**:
   - If both left and right metrics keys are present and `respectMetricsKeys=true`, the glyph is skipped.
   - If only one side has a metrics key, the tool will keep that side unchanged and only suggest the other side.
5) **Insufficient vertical coverage** (the glyph doesn’t meaningfully overlap the band).

You’ll see the exact skip reason in each result entry.

---

## Parameters

You can pass parameters as:
- `defaults` (per-call), and/or
- font-level or master-level custom parameters (read automatically when present):
  - Canonical (recommended): `cx.ap.spacingArea`, `cx.ap.spacingDepth`, `cx.ap.spacingOver`, `cx.ap.spacingFreq`
  - Legacy aliases (read-only compatibility):
    - `gmcpSpacingArea`, `gmcpSpacingDepth`, `gmcpSpacingOver`, `gmcpSpacingFreq`
    - `paramArea`, `paramDepth`, `paramOver`, `paramFreq`

### Best way to set parameters (recommended)

Use **custom parameters inside the `.glyphs` file** for values that should be consistent for everyone using the font:
- good for: `cx.ap.spacingArea`, `cx.ap.spacingDepth`, `cx.ap.spacingOver`, `cx.ap.spacingFreq`
- benefits: travels with the font, persists across sessions, and can differ per master

Use a **JSON config file** for values you want to version-control and share as “spacing presets”:
- good for: `rules`, plus any `defaults` you want to keep in sync across a team
- benefits: diffable, reviewable, easy to keep multiple presets (e.g. “text”, “display”, “UI”)

In practice, a good split is:
- **In the font (custom parameters):** `cx.ap.spacingArea/Depth/Over/Freq` (recommended)
- **In a file:** `rules` + any per-project defaults like `referenceGlyph`, `italicMode`, `minCoverageRatio`, tabular settings

### Precedence (what wins)

For each numeric parameter (`area`, `depth`, `over`, `frequency`) the tools resolve values in this exact order:

1) Per-call `defaults` (if provided)
2) Master custom parameter (canonical `cx.ap.spacing*`)
3) Master custom parameter (legacy `gmcpSpacing*`)
4) Master custom parameter (legacy `param*`)
5) Font custom parameter (canonical `cx.ap.spacing*`)
6) Font custom parameter (legacy `gmcpSpacing*`)
7) Font custom parameter (legacy `param*`)
8) Internal default

### Setting spacing params in Glyphs (UI)

You can set the parameters in Glyphs’ UI:
- **Font-level:** `File → Font Info… → Font → Custom Parameters`
- **Per-master:** `File → Font Info… → Masters → (select a master) → Custom Parameters`

Add any of these keys (case-sensitive). Recommended canonical names:
- `cx.ap.spacingArea` (number)
- `cx.ap.spacingDepth` (number, percent of xHeight)
- `cx.ap.spacingOver` (number, percent of xHeight)
- `cx.ap.spacingFreq` (number, y sampling step in units)

Legacy aliases (still read, but not recommended for new work):
- `gmcpSpacingArea`, `gmcpSpacingDepth`, `gmcpSpacingOver`, `gmcpSpacingFreq`
- `paramArea`, `paramDepth`, `paramOver`, `paramFreq`

Font-level parameters act as defaults; master-level parameters override them.

### HT compatibility mode (legacy `param*` keys)

If you previously used **HTLetterspacer**, your masters (or font) may already contain:
- `paramArea`, `paramDepth`, `paramOver`, `paramFreq`

`review_spacing` / `apply_spacing` will automatically read these **as legacy keys** when the canonical `cx.ap.spacing*` keys are not present.

**Migration (recommended):** write canonical keys once (so future tools and collaborators see the branded keys in Font Info), then save:
```json
{
  "font_index": 0,
  "scope": "font",
  "params": { "area": 400, "depth": 15, "over": 0, "frequency": 5 }
}
```
Then call `save_font` to persist.

### Setting spacing params in Glyphs (Macro Panel script)

If you want to write them into the font programmatically, paste this into Glyphs’ **Macro Panel**:

```python
from GlyphsApp import Glyphs

font = Glyphs.font
if not font:
    raise RuntimeError("No active font")

# Font-wide defaults
font.customParameters["cx.ap.spacingArea"] = 400
font.customParameters["cx.ap.spacingDepth"] = 15
font.customParameters["cx.ap.spacingOver"] = 0
font.customParameters["cx.ap.spacingFreq"] = 5

# Optional: override per master
for master in font.masters:
    if master.name == "Display":
        master.customParameters["cx.ap.spacingArea"] = 440
```

### Setting parameters via MCP (`set_spacing_params`)

If you prefer not to use the UI or Macro Panel, use the MCP tool `set_spacing_params` (it does **not** auto-save).

Font-level defaults:
```json
{
  "font_index": 0,
  "scope": "font",
  "params": { "area": 400, "depth": 15, "over": 0, "frequency": 5 }
}
```

Override one master:
```json
{
  "font_index": 0,
  "scope": "master",
  "master_id": "MASTER_ID_HERE",
  "params": { "area": 440 }
}
```

Delete a value (unset):
```json
{
  "font_index": 0,
  "scope": "font",
  "params": { "over": null }
}
```

Preview changes without writing:
```json
{
  "font_index": 0,
  "scope": "font",
  "params": { "area": 420 },
  "dry_run": true
}
```

To persist after setting values, call `save_font`.

### Using a text file (JSON) for `defaults` + `rules`

There’s an example config file at:
- `content/spacing-config.example.json`

Recommended pattern:
1) Keep your preferred `defaults` + `rules` in a JSON file in your repo.
2) When calling `review_spacing` / `apply_spacing`, load that JSON in your client and pass:
   - `defaults: config.defaults`
   - `rules: config.rules`

The spacing tools do **not** currently read `rules` from the font automatically; passing them explicitly keeps the behavior transparent and reproducible.

### `defaults` fields

All values are optional; omitted fields fall back to internal defaults.

- `area` (number, default `400`)
  - Controls the “target white-space area” magnitude.
  - Larger values generally produce looser spacing.
- `depth` (number, percent of xHeight, default `15`)
  - Limits how far measurements are allowed to reach “into” openings.
  - Helps avoid letting deep counters dominate results.
- `over` (number, percent of xHeight, default `0`)
  - Extends the measurement band above/below the reference glyph’s bounds.
- `frequency` (number, default `5`)
  - Sampling step in font units along the y-axis.
  - Smaller values are slower but can be more stable.
- `referenceGlyph` (string, default `"x"`)
  - Fallback reference when no rule overrides it.
  - Special value `"*"` means “use the glyph itself as reference”.
- `factor` (number, default `1.0`)
  - Global multiplier applied to the target area (usually overridden by rules).
- `italicMode` (`"deslant"` or `"none"`, default `"deslant"`)
  - When `"deslant"`, measurements are corrected using master `italicAngle`.
- `includeComponents` (bool, default `true`)
  - Whether to include components in intersection measurement.
- `respectMetricsKeys` (bool, default `true`)
- `skipAutoAligned` (bool, default `true`)
- `minCoverageRatio` (number `0..1`, default `0.7`)
- `tabularMode` (bool, default `false`)
  - If true, and if a width target is available, the tool will keep width fixed by distributing width adjustments across LSB/RSB.
- `tabularWidth` (number or null, default `null`)
  - If set, becomes the fixed width target used by `tabularMode`.
- `includeSamples` (bool, default `false`)
  - If true, `review_spacing` includes per-y sample arrays (larger payload).

---

## Rules (per-glyph overrides)

The `rules` parameter is a list of objects. The best matching rule wins.

Each rule may include:
- `script` (string or `"*"`)
- `category` (string or `"*"`)
- `subCategory` (string or `"*"`)
- `nameRegex` (regex string, optional) or `nameFilter` (substring, optional)
- `referenceGlyph` (string; `"*"` uses the glyph itself)
- `factor` (number)

### Matching behavior
- A rule matches when all specified fields match.
- More specific rules win over wildcard rules.
- If two rules are equally specific, the **later** rule in the list wins (so you can append overrides).

---

## Tool reference

### `review_spacing`

Computes a per-glyph spacing report and suggestions.

**Inputs**
- `font_index` (int, default `0`)
- `glyph_names` (list of strings, optional)
  - If omitted, the tool uses the currently selected glyphs in Glyphs **only if** `font_index` is the active font.
- `master_id` (string, optional)
  - If omitted, evaluates all masters.
- `rules` (list, optional)
- `defaults` (object, optional)
- `debug` (object, optional)
  - Currently supports `includeSamples`.

**Output**
- `ok` boolean
- `summary` counts and effective defaults
- `results` list of per-layer entries:
  - `status`: `"ok" | "skipped" | "error"`
  - `reason` (when skipped/error)
  - `current` metrics
  - `reference` band info
  - `measured` areas/extremes
  - `target` values
  - `suggested` metrics
  - `delta` vs current
  - `warnings` list

### `apply_spacing`

Applies the suggestions computed by the same engine.

**Safety gates**
- If `confirm=false` and `dry_run=false`, the tool refuses to run.
- Use `dry_run=true` first to preview.

**Inputs**
Same as `review_spacing`, plus:
- `clamp` (object, optional)
  - `maxDeltaLSB` (default `150`)
  - `maxDeltaRSB` (default `150`)
  - `minLSB` (default `-200`)
  - `minRSB` (default `-200`)
- `confirm` (bool, default `false`)
- `dry_run` (bool, default `false`)

**Output**
- `ok` boolean
- `summary`
- `results` (the same analysis results)
- `applied` list (only when actually applied) with before/after metrics

### `set_spacing_guides`

Adds or clears **glyph-level guides** (`layer.guides`) that visualize the spacing model’s geometry:
- the **vertical measurement band** (`yMin..yMax`), and (by default)
- the key **x′ boundaries** used to compute negative space (zone edges, depth clamp, and average whitespace).

This is purely a visualization aid. It:
- writes guides into glyph layers (so they travel with the `.glyphs` file),
- does **not** change metrics,
- does **not** auto-save.

**Inputs**
- `font_index` (int, default `0`)
- `glyph_names` (list of strings, optional)
  - If omitted, uses selected glyphs in Glyphs (active font). If nothing is selected, it falls back to a small “diagnostic set”: `n`, `H`, `zero`, `o`, `O`, `period`, `comma`.
- `master_scope` (string, default `"current"`)
  - `"current"`: only the currently selected master
  - `"all"`: all masters
  - `"master"`: a specific master via `master_id`
- `master_id` (string, required when `master_scope="master"`)
- `mode` (`"add"` or `"clear"`, default `"add"`)
- `reference_glyph` (string, default `"x"`)
  - Special value `"*"` means “use the glyph itself”.
- `style` (`"band" | "model" | "full"`, default `"model"`)
  - `"band"`: only the vertical measurement band (two horizontal guides).
  - `"model"`: band + the most didactic x′ boundaries (zone, depth clamp, measured vs target averages).
  - `"full"`: `"model"` plus extra reference bounds and full extremes (more clutter).
- `dry_run` (bool, default `false`)

**Output**
- `ok` boolean
- `summary` counts
- `results` list with per-glyph/per-master actions, the computed band, and guide names

**Notes**
- To see them in the editor, enable `View → Show Guides`.
- By default, `mode="add"` clears previously created spacing guides for the target layers (so it’s idempotent).
- In italic masters with `italicMode="deslant"`, x′ boundary guides are drawn as **slanted lines** so they represent a *constant deslanted-x* across the band (i.e. they match the model’s coordinate space).

#### What the guides mean (didactic)

**Band (yMin/yMax)**
- `cx.ap.spacing.band:min` / `cx.ap.spacing.band:max`
  - The exact vertical region the model samples at `frequency` steps.

**Zone edges (what counts as “the edge”)**
- `cx.ap.spacing.zone:L` / `cx.ap.spacing.zone:R`
  - The model’s left/right “reference edges” inside the band (`lExtreme` / `rExtreme`), expressed in x′ space (deslanted if italic).

**Depth clamp (how far into openings we measure)**
- `cx.ap.spacing.depth:L` / `cx.ap.spacing.depth:R`
  - The clamp limits derived from `spacingDepth` (percent of x-height), starting from the zone edges.
  - If the glyph has deep counters, the clamp prevents extreme “inward” measurements from dominating.

**Average whitespace (measured vs target)**
- `cx.ap.spacing.avg.measured:L` / `cx.ap.spacing.avg.measured:R`
  - Where the **current** average whitespace sits on each side (area ÷ height).
- `cx.ap.spacing.avg.target:L` / `cx.ap.spacing.avg.target:R`
  - Where the model wants the average whitespace to sit, based on `spacingArea` (after scaling by UPM/x-height).

**Only in `style="full"`**
- `cx.ap.spacing.ref:min` / `cx.ap.spacing.ref:max`
  - The raw reference bounds **without** `spacingOver` (useful to understand what `over` is doing).
- `cx.ap.spacing.full:L` / `cx.ap.spacing.full:R`
  - The full extremes across the glyph’s own bounds (used for overshoot compensation in the engine).

---

## Recommended workflow

1) Select glyphs you want to space (or pass `glyph_names` explicitly).
2) Run `review_spacing`:
   - Check skip reasons.
   - Look at the largest `delta` outliers.
3) Tune `rules` and/or `defaults`:
   - pick better reference glyphs for punctuation and symbols
   - adjust `factor` per class
4) Run `apply_spacing(dry_run=true)` to confirm clamps and diffs.
5) Run `apply_spacing(confirm=true)` to apply.
6) Repeat: re-run `review_spacing` to confirm deltas are near zero.

---

## Practical examples

### Review selected glyphs (active font)
Call:
```json
{
  "font_index": 0
}
```

### Review specific glyphs across all masters
```json
{
  "font_index": 0,
  "glyph_names": ["H", "O", "n", "o", "period", "comma"],
  "defaults": {
    "referenceGlyph": "n",
    "frequency": 5,
    "area": 420
  }
}
```

### Apply with a conservative clamp (two-step)
Dry run:
```json
{
  "font_index": 0,
  "glyph_names": ["H", "O", "n", "o"],
  "dry_run": true,
  "clamp": { "maxDeltaLSB": 80, "maxDeltaRSB": 80 }
}
```

Apply:
```json
{
  "font_index": 0,
  "glyph_names": ["H", "O", "n", "o"],
  "confirm": true,
  "clamp": { "maxDeltaLSB": 80, "maxDeltaRSB": 80 }
}
```

---

## Limitations and notes

- Measurements rely on `layer.intersectionsBetweenPoints(...)`, which behaves like the Glyphs measurement tool; unusual outlines, open paths, or complex overlaps can produce sparse or noisy intersections.
- Auto-spacing does not replace human review. Use text strings and proofing after applying.
- If your font heavily uses metrics keys or auto-aligned component glyphs, many layers will be skipped by design.

---

## Prompt templates (copy/paste)

> Note: tool name prefixes vary by client. If your tools aren’t named `glyphs-app-mcp__*`, replace that prefix with whatever your MCP client shows.

### HTspacer-style spacing pass (review → dry-run → apply)

```text
You are a meticulous spacing assistant for a type designer working in Glyphs.
Rules:
- Never auto-save.
- Never mutate without a dry run first.
- Keep changes conservative (prefer clamping).
- If glyph_names isn't provided, use my current selection in the active font.

Task: Review and (optionally) apply spacing suggestions to improve rhythm and consistency.

1) Call glyphs-app-mcp__review_spacing:
{"font_index":0}

2) Summarize:
- Top 15 layers by |delta.lsb| + |delta.rsb| (and why they’re outliers)
- Skipped layers grouped by reason (metrics keys, low coverage, etc.)
- Any warnings that suggest a bad measurement band / reference glyph

3) Call glyphs-app-mcp__apply_spacing (dry run with a conservative clamp):
{"font_index":0,"dry_run":true,"clamp":{"maxDeltaLSB":80,"maxDeltaRSB":80,"minLSB":-50,"minRSB":-50}}

4) If I say “apply”, call apply_spacing again with confirm=true using the same clamp.
5) If I say “save”, call glyphs-app-mcp__save_font.
```

### Tabular figures spacing (fixed width)

```text
I want tabular figures to keep a fixed width by distributing width changes evenly across LSB/RSB.

First, select your figure glyphs in Glyphs (Font view), then:

1) Call glyphs-app-mcp__review_spacing:
{"font_index":0,"defaults":{"tabularMode":true,"tabularWidth":600,"referenceGlyph":"zero"}}

2) Call glyphs-app-mcp__apply_spacing (dry run):
{"font_index":0,"dry_run":true,"defaults":{"tabularMode":true,"tabularWidth":600,"referenceGlyph":"zero"},"clamp":{"maxDeltaLSB":60,"maxDeltaRSB":60,"minLSB":-50,"minRSB":-50}}

3) If I approve, call apply_spacing again with confirm=true using the same args.
```

### Visualize the spacing model with guides (expert)

Paste this into your LLM/client as a single prompt. It is designed to be safe, practical, and typography-oriented.

> **Role:** You are a meticulous spacing assistant for a type designer working in Glyphs.  
> **Rules:** Never auto-save. Use `dry_run` before mutating tools. Prefer a small diagnostic glyph set unless the user provides specific glyphs.

**Task:** Add spacing-model guides so I can visually confirm what the spacing engine is measuring (band, zone edges, depth clamp, and measured-vs-target averages) in the current master, then tell me what to look for.

1) Call `glyphs-app-mcp__set_spacing_guides` with:
```json
{
  "font_index": 0,
  "master_scope": "current",
  "mode": "add",
  "style": "model",
  "reference_glyph": "x"
}
```

2) Tell me exactly how to visualize them in Glyphs:
- Turn on `View → Show Guides`.
- Open the diagnostic glyphs (e.g. `n`, `H`, `zero`, `o`, `O`, `period`, `comma`) and verify:
  - The two horizontal guides match the intended measurement band for the current master.
  - The x′ guides are meaningful:
    - `zone:L/R` roughly bracket the “main body” of the glyph inside the band.
    - `depth:L/R` show how far into counters/openings the model is allowed to “look”.
    - `avg.measured:*` vs `avg.target:*` shows whether the glyph is currently too tight/loose on each side.
  - In italics (if any), confirm x′ guides are slanted (they should represent constant deslanted-x across the band).

3) If the band looks wrong, help me correct it:
- If it’s too tall/short: suggest adjusting `cx.ap.spacingOver`.
- If it’s using an unhelpful reference: suggest a better `reference_glyph` (e.g. `n` for lowercase, `H` for uppercase, `zero` for figures) and re-run `set_spacing_guides`.
- If the depth clamp looks wrong: suggest adjusting `cx.ap.spacingDepth` (percent of x-height).
- If target averages look too tight/loose globally: suggest adjusting `cx.ap.spacingArea`.

4) When I say “clear guides”, call:
```json
{
  "font_index": 0,
  "master_scope": "all",
  "mode": "clear"
}
```
