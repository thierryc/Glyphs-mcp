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
  - Canonical (recommended): `gmcpSpacingArea`, `gmcpSpacingDepth`, `gmcpSpacingOver`, `gmcpSpacingFreq`
  - Legacy aliases (read-only compatibility): `paramArea`, `paramDepth`, `paramOver`, `paramFreq`

### Best way to set parameters (recommended)

Use **custom parameters inside the `.glyphs` file** for values that should be consistent for everyone using the font:
- good for: `gmcpSpacingArea`, `gmcpSpacingDepth`, `gmcpSpacingOver`, `gmcpSpacingFreq`
- benefits: travels with the font, persists across sessions, and can differ per master

Use a **JSON config file** for values you want to version-control and share as “spacing presets”:
- good for: `rules`, plus any `defaults` you want to keep in sync across a team
- benefits: diffable, reviewable, easy to keep multiple presets (e.g. “text”, “display”, “UI”)

In practice, a good split is:
- **In the font (custom parameters):** `gmcpSpacingArea/Depth/Over/Freq` (recommended)
- **In a file:** `rules` + any per-project defaults like `referenceGlyph`, `italicMode`, `minCoverageRatio`, tabular settings

### Precedence (what wins)

For each numeric parameter (`area`, `depth`, `over`, `frequency`) the tools resolve values in this exact order:

1) Per-call `defaults` (if provided)
2) Master custom parameter (canonical `gmcpSpacing*`)
3) Master custom parameter (legacy `param*`)
4) Font custom parameter (canonical `gmcpSpacing*`)
5) Font custom parameter (legacy `param*`)
6) Internal default

### Setting `param*` in Glyphs (UI)

You can set the parameters in Glyphs’ UI:
- **Font-level:** `File → Font Info… → Font → Custom Parameters`
- **Per-master:** `File → Font Info… → Masters → (select a master) → Custom Parameters`

Add any of these keys (case-sensitive). Recommended canonical names:
- `gmcpSpacingArea` (number)
- `gmcpSpacingDepth` (number, percent of xHeight)
- `gmcpSpacingOver` (number, percent of xHeight)
- `gmcpSpacingFreq` (number, y sampling step in units)

Legacy aliases (still read, but not recommended for new work):
- `paramArea`, `paramDepth`, `paramOver`, `paramFreq`

Font-level parameters act as defaults; master-level parameters override them.

### Setting `param*` in Glyphs (Macro Panel script)

If you want to write them into the font programmatically, paste this into Glyphs’ **Macro Panel**:

```python
from GlyphsApp import Glyphs

font = Glyphs.font
if not font:
    raise RuntimeError("No active font")

# Font-wide defaults
font.customParameters["gmcpSpacingArea"] = 400
font.customParameters["gmcpSpacingDepth"] = 15
font.customParameters["gmcpSpacingOver"] = 0
font.customParameters["gmcpSpacingFreq"] = 5

# Optional: override per master
for master in font.masters:
    if master.name == "Display":
        master.customParameters["gmcpSpacingArea"] = 440
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
