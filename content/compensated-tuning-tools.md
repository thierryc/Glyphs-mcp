---
title: Compensated tuning tools
description: Preview and apply two-master compensated scaling transforms with safety gates and backups.
---

These tools help you **preview** and optionally **apply** a compensated tuning transform to outlines across masters.

This is a **two-master compensated scaling** workflow:
- it compares a **base** master and a **different reference** master with compatible outlines,
- it computes interpolation factors from the geometric difference between those two masters, and
- it applies those factors while scaling (`sx`, `sy`) to preserve stroke thickness approximately.

This is **not** a generic "make this one master lighter/darker" tool.

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

3) **Two different masters are required for a meaningful result**
If `base_master_id == ref_master_id`, the current implementation has no geometric delta to interpolate from. In practice, that means the result is unchanged.

4) **This is a scaling workflow, not a standalone thinning workflow**
`keep_stroke` only matters when the tool is computing compensated interpolation from a real two-master setup. It is not a "lighten this master in place" knob.

5) **Safety gates**
`apply_compensated_tuning` refuses to mutate unless you use `dry_run=true` or `confirm=true`. It never auto-saves.

---

## When to use this tool

Use it when you want to:
- scale a master horizontally and/or vertically,
- use a second master to preserve stroke behavior while scaling,
- preview or apply the same compensated transform across many compatible glyphs.

Typical example:
- `base_master_id = Regular`
- `ref_master_id = Bold`
- `sx = 0.97` to condense slightly
- `sy = 1.00` to keep height unchanged
- `keep_stroke = 0.9` to preserve stroke thickness during that scaling

## When not to use this tool

Do **not** use it when you want to:
- make one master slightly lighter or darker **without** using another master,
- thin outlines in place with `base_master_id == ref_master_id`,
- change weight while leaving `sx = 1` and `sy = 1` and expecting `keep_stroke` to do the work,
- process component-based glyphs without decomposing them first.

If your font only has one usable master for a glyph, or if the reference master is structurally incompatible, this tool is the wrong tool for that task.

---

## Concepts (plain language)

### Base vs reference vs output

- `base_master_id`: the master you are tuning *toward* (often your “current” master).
- `ref_master_id`: the master you are tuning *from* (often the next heavier master on the weight axis).
- `output_master_id`: where the tuned outlines are written (defaults to `base_master_id`).

### `b`, `q_x`, `q_y`

- `b` is a **stem thickness ratio** (ref/base) used to compensate the interpolation.
- If you don’t provide `q_x` / `q_y` (and masters differ), the tool can estimate `b` automatically via `measure_stem_ratio`-style measurements.
- If you **do** provide `q_x` / `q_y`, those explicit values override the computed compensation. In that case, `keep_stroke` is no longer the control that determines `q`.
- `extrapolation` controls what happens when computed `q` falls outside `[0..1]`:
  - `"clamp"` (default): clamp and warn
  - `"allow"`: allow extrapolation
  - `"error"`: fail fast

### Why two masters are needed

The algorithm does not "invent" a lighter or heavier outline from one shape alone. It uses:
- the base-master point positions,
- the reference-master point positions,
- and the stem-thickness ratio between those two masters

to compute a compensated interpolation.

With a single master, there is no geometric difference to interpolate from, so the current implementation has nothing to work with.

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

Important:
- use **different** base and reference masters for a meaningful ratio,
- do not use `base_master_id == ref_master_id` unless you intentionally want a neutral baseline.

### Step 2) Preview on one glyph (no mutation)

Tool: `review_compensated_tuning`

```json
{
  "font_index": 0,
  "glyph_name": "A",
  "base_master_id": "REGULAR_MASTER_ID",
  "ref_master_id": "BOLD_MASTER_ID",
  "sx": 0.97,
  "sy": 1.0,
  "keep_stroke": 0.9,
  "extrapolation": "clamp",
  "round_units": true
}
```

The result is `set_glyph_paths`-compatible (`paths`, `width`) and includes a `gmcp` metadata block with:
- computed `qX` / `qY` and `warnings`
- `stem` info when `b` was measured automatically

Read the result like this:
- if `computed.qX` / `computed.qY` differ from `1`, the transform is doing real interpolation work,
- if you used the same master for base and reference, expect the result to be unchanged,
- if you supplied explicit `q_x` / `q_y`, those values are the real driver of the transform.

### Step 3) Dry-run apply across a set

Tool: `apply_compensated_tuning`

```json
{
  "font_index": 0,
  "glyph_names": ["A", "B", "C"],
  "base_master_id": "REGULAR_MASTER_ID",
  "ref_master_id": "BOLD_MASTER_ID",
  "output_master_id": "REGULAR_MASTER_ID",
  "sx": 0.97,
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
- `stem` if `b` was measured automatically

Before applying, confirm that:
- base and reference are different masters,
- the glyphs you selected are outline-compatible across those masters,
- the preview actually changed the geometry you care about.

### Step 4) Confirm apply (writes outlines)

Re-run `apply_compensated_tuning` with the same args, but `confirm=true` (and `dry_run=false`).

After applying, consider doing a visual proof pass in Glyphs and optionally calling `save_font` to persist.

---

## Common mistakes

- **Using the same master for both `base_master_id` and `ref_master_id`**
  This gives the algorithm no second shape to interpolate against. Expect no path change.

- **Expecting `keep_stroke` to lighten a master by itself**
  `keep_stroke` controls compensation within a scaling workflow. It is not a standalone weight-editing parameter.

- **Supplying `q_x` / `q_y` and then tuning `keep_stroke`**
  Once `q_x` / `q_y` are explicit, they override the computed compensation.

- **Using `measure_stem_ratio` with the same base and reference master and treating that as an active tuning setup**
  That is only a neutral baseline.

---

## Troubleshooting

- **“Glyph layers contain components”**: Decompose components; the tuning transform expects point-level outlines.
- **“Incompatible outlines between masters”**: Ensure the masters have matching node structure for that glyph (paths/nodes/types).
- **No visible path change**: Check whether you used the same base/ref master, whether your preview reported `qX = qY = 1`, or whether you supplied explicit `q_x` / `q_y` that keep the shape nearly unchanged.
- **Too many warnings about clamping**: Try `"extrapolation":"allow"` for exploration, or adjust `keep_stroke` / provide explicit `q_x` / `q_y`.

---

## Reference

- Full tool list: [Command set](./reference/command-set.mdx)
