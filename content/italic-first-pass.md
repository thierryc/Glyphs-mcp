# Italic first pass

Glyphs MCP can generate guarded Raw, Cursivy, and Balanced first-pass italic
layers from a Roman master. These are starting points for optical drawing, not
finished italic designs.

## Modes

- `raw` applies a deterministic affine shear around the selected origin.
- `cursivy` uses Glyphs' callable Transformations filter when available. On
  hosts where that public Python entry point is unavailable, it reports and
  uses a conservative pure-Python straight-stem fallback.
- `balanced` interpolates Raw and Cursivy-compatible node coordinates and then
  compensates confidently detected straight vertical or diagonal stem pairs.

Balanced defaults to `curve_strength=0.75` and
`stem_compensation=1.0`. Both accept values from `0` through `1`.
`curve_strength=0` is exactly Raw, while `curve_strength=1` is exactly the
available Cursivy candidate before final stem compensation.

## Safety and diagnostics

`review_italic_first_pass` runs the complete transformation on detached layer
copies. It reports topology preservation, the effective backend and strengths,
origin pivot, anchor shifts, component placement, component-master conflicts,
candidate bounds and metrics, and detected/compensated/skipped stem pairs.

Balanced mode:

- Never changes path count, node order, node types, smooth flags, or curve
  handles during stem compensation.
- Moves only both endpoints of accepted straight sides.
- Preserves live components and adjusts only component x placement using
  `x += tan(angle) * y`.
- Shears copied anchors using
  `x′ = x + tan(angle) * (y - pivotY)`.
- Blocks an explicit component master that differs from the target master.

`stem_policy=copy_from_source` remains review-only. It reports source stem
availability but does not silently edit Font Info; use
`set_master_stem_metrics` for that separate confirmed mutation.

Run `apply_italic_first_pass` with `dry_run=true` before
`confirm=true`. The tool never saves the font.
