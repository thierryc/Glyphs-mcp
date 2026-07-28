# Italic first pass

:::caution Experimental

Glyphs MCP can generate guarded Raw, Cursivy, and Balanced first-pass layers
from a Roman master. The result is a construction draft for the designer, not
a finished or authentic italic design.

:::

## Design goal

An italic commonly works as a companion to the Roman, providing contrast and
emphasis inside text. The Glyphs MCP workflow has the narrower goal of helping
the designer begin that companion efficiently: it establishes a controlled
slant, preserves reusable structure, and reports geometry that needs review.

It does not decide the italic's voice. Character construction, optical
correction, rhythm, spacing, kerning, alternates, interpolation, and proofing
remain design work. In particular, mechanically transformed `a`, `e`, `f`,
`g`, `k`, `v`, `w`, `x`, `y`, punctuation, brackets, quotes, and symbols
usually need deliberate redrawing.

## Modes

- `raw` applies a deterministic affine shear around the selected origin.
- `cursivy` uses Glyphs' callable Transformations filter when available. On
  hosts where that public Python entry point is unavailable, it reports and
  uses a conservative pure-Python straight-stem fallback.
- `balanced` interpolates Raw and Cursivy-compatible node coordinates and then
  compensates confidently detected straight vertical or diagonal stem pairs.

Balanced is the recommended experimental mode after passing the fixed
Broad-Latin promotion gate. Calls that omit `slant_mode` continue to use
Cursivy for backward compatibility.

Balanced defaults to `curve_strength=0.75` and
`stem_compensation=1.0`. Both accept values from `0` through `1`.
`curve_strength=0` is exactly Raw, while `curve_strength=1` is exactly the
available Cursivy candidate before final stem compensation.

## Broad-Latin evidence

The promotion benchmark covers 543 encoded glyphs in both pinned Inter and
Noto Sans sources:

| Family | Topology | Compensated pairs | Raw error | Cursivy error | Balanced error |
| --- | ---: | ---: | ---: | ---: | ---: |
| Inter v4.1 | 543/543 | 135 | 2.7812 | 1.8078 | &lt;0.00000000000004 |
| Noto Sans | 543/543 | 102 | 1.2912 | 0.8393 | &lt;0.00000000000002 |

Every generated mode preserved topology, review left all source layers
unchanged, anchor error was zero, and no unsafe compensation was applied.
Balanced exceeded the required 50% source-width improvement over both
alternatives in each family.

This is evidence for a safer mechanical first pass—not evidence that Balanced
resembles a designed italic. Mean Balanced-versus-official silhouette
differences were `7.237%` for Inter and `29.219%` for Noto Sans because the
official italics include deliberate redrawing, recomposition, and spacing.

[Read the complete Broad-Latin report](contributor/italic-balanced-broad-latin-benchmark.md).
Click either contact sheet for its full 144-DPI source.

[![Inter Broad-Latin italic audit](contributor/images/italic-balanced-inter-v4.1-broad-audit.png)](contributor/images/italic-balanced-inter-v4.1-broad-audit.png)

[![Noto Sans Broad-Latin italic audit](contributor/images/italic-balanced-noto-sans-cb097900-broad-audit.png)](contributor/images/italic-balanced-noto-sans-cb097900-broad-audit.png)

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

## Recommended workflow

1. Verify the source Roman and target italic masters and the target
   `italicAngle`.
2. Run `review_italic_first_pass` in Balanced mode and inspect blocked glyphs,
   components, anchors, topology, stems, bounds, and metrics.
3. Run `apply_italic_first_pass` with `dry_run=true`.
4. Apply only the approved scope with `confirm=true`.
5. Redraw and proof the result as an italic design.

The tool never saves the font.
