---
title: Compensated tuning tools
description: Preview and apply compensated tuning transforms across masters with safety gates and backups.
---

These tools help you **preview** and optionally **apply** a compensated tuning transform to outlines across masters.

- `review_compensated_tuning` computes tuned outlines for **one** glyph (no mutation).
- `apply_compensated_tuning` applies the same transform across many glyphs (requires confirmation).
- `measure_stem_ratio` is an optional helper that estimates the stem ratio `b` used for compensation.

This workflow is meant for typographers and font engineers: it is deterministic, inspectable, and **safe by default** (dry-run and confirm gates, no auto-save).

---

## What the tools change (and what they don’t)

### Changes (only when applied)
- Replaces **paths** (outlines) in the target master layer.
- Updates **layer width** for the target master layer.
- Optionally adds a **backup layer** per glyph before applying.

### Does not change
- Kerning
- Components or anchors (and components are not supported for tuning)
- Any files on disk (no auto-save)

---

## Important constraints (read this first)

1) **No components**  
`review_compensated_tuning` and `apply_compensated_tuning` refuse glyph layers that contain components. Decompose first, tune, then rebuild components if needed.

2) **Compatible outlines across masters**  
The tool requires the base and reference master layers to have matching path/node structure (same path count, node count, node types).

3) **Safety gates**  
`apply_compensated_tuning` refuses to mutate unless you use `dry_run=true` or `confirm=true`. It never auto-saves.

---

## Concepts (plain language)

### Base vs reference vs output

- `base_master_id`: the master you are tuning *toward* (often your “current” master).
- `ref_master_id`: the master you are tuning *from* (often the next heavier master on the weight axis).
- `output_master_id`: where the tuned outlines are written (defaults to `base_master_id`).

### `b`, `q_x`, `q_y`

- `b` is a **stem thickness ratio** (ref/base) used to compensate the interpolation.
- If you don’t provide `q_x` / `q_y` (and masters differ), the tool can estimate `b` automatically via `measure_stem_ratio`-style measurements.
- `extrapolation` controls what happens when computed `q` falls outside `[0..1]`:
  - `"clamp"` (default): clamp and warn
  - `"allow"`: allow extrapolation
  - `"error"`: fail fast

---

## Recommended workflow (safe)

### Step 0) Identify masters

Use:
- `list_open_fonts` → pick `font_index`
- `get_font_masters` → get master IDs

### Step 1) (Optional) Measure `b`

If you want to inspect the measured ratio (or tune defaults), call:

```json
{
  "font_index": 0,
  "base_master_id": "BASE_MASTER_ID",
  "ref_master_id": "REF_MASTER_ID",
  "stem_source": "auto",
  "reference_glyphs": ["H", "n", "I", "o", "E"]
}
```

Tool: `measure_stem_ratio`  
Look at `ok`, `b`, and `warnings`.

### Step 2) Preview on one glyph (no mutation)

Tool: `review_compensated_tuning`

```json
{
  "font_index": 0,
  "glyph_name": "A",
  "base_master_id": "BASE_MASTER_ID",
  "ref_master_id": "REF_MASTER_ID",
  "sx": 1.0,
  "sy": 1.0,
  "keep_stroke": 0.9,
  "extrapolation": "clamp",
  "round_units": true
}
```

The result is `set_glyph_paths`-compatible (`paths`, `width`) and includes a `gmcp` metadata block with:
- computed `qX` / `qY` and `warnings`
- `stem` info when `b` was measured automatically

### Step 3) Dry-run apply across a set

Tool: `apply_compensated_tuning`

```json
{
  "font_index": 0,
  "glyph_names": ["A", "B", "C"],
  "base_master_id": "BASE_MASTER_ID",
  "ref_master_id": "REF_MASTER_ID",
  "output_master_id": "BASE_MASTER_ID",
  "sx": 1.0,
  "sy": 1.0,
  "keep_stroke": 0.9,
  "extrapolation": "clamp",
  "backup": true,
  "dry_run": true
}
```

Inspect:
- `dryRun`
- `summary.okCount / skippedCount / errorCount`
- `results[]` per glyph (and why something was skipped)

### Step 4) Confirm apply (writes outlines)

Re-run `apply_compensated_tuning` with the same args, but `confirm=true` (and `dry_run=false`).

After applying, consider doing a visual proof pass in Glyphs and optionally calling `save_font` to persist.

---

## Troubleshooting

- **“Glyph layers contain components”**: Decompose components; the tuning transform expects point-level outlines.
- **“Incompatible outlines between masters”**: Ensure the masters have matching node structure for that glyph (paths/nodes/types).
- **Too many warnings about clamping**: Try `"extrapolation":"allow"` for exploration, or adjust `keep_stroke` / provide explicit `q_x` / `q_y`.

---

## Reference

- Full tool list: [Command set](./reference/command-set.mdx)
