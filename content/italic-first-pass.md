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
- `balanced` is a reproducible pure-Python pipeline. It builds Raw, applies the
  conservative straight-stem correction at partial strength, interpolates
  between those compatible coordinates, and then applies the requested final
  compensation to confidently detected vertical or diagonal stem pairs. It
  never invokes the Glyphs Transformations filter.

Balanced is the recommended experimental deterministic option. Calls that omit
`slant_mode` continue to use Cursivy for backward compatibility.

Balanced defaults to `curve_strength=0.75` and
`stem_compensation=1.0`. Both accept values from `0` through `1`.
`curve_strength=0` is exactly Raw before final compensation, while
`curve_strength=1` uses the complete deterministic partial-correction
candidate. The controls are independent. At `stem_compensation=1`, accepted
stems converge to their Roman perpendicular width, so the final correction can
make the intermediate `curve_strength` difference visually subtle.

## Broad-Latin evidence

The benchmark covers 543 encoded glyphs in both pinned Inter and Noto Sans
sources plus the 391 values shared by pinned IBM Plex Sans Regular and Italic
UFOs:

| Family | Topology | Compensated pairs | Raw error | Partial error | Balanced error | Component-risk glyphs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Inter v4.1 | 543/543 | 135 | 2.7812 | 1.8078 | &lt;0.00000000000004 | 23 |
| Noto Sans | 543/543 | 102 | 1.2912 | 0.8393 | &lt;0.00000000000002 | 2 |
| IBM Plex Sans | 391/391 | 102 | 1.2607 | 0.8194 | &lt;0.00000000000002 | 0 |

Every generated mode preserved topology, review left all source layers
unchanged, anchor error was zero, and no unsafe compensation was applied.
Balanced exceeded the required 50% source-width improvement over both
deterministic alternatives in each family. Recursive component analysis found
23 Inter glyphs and 2 Noto Sans glyphs whose transforms do not commute with
the requested shear. Balanced blocked every one before application, so the
safety gates pass with zero unsafe component applications. In Inter, this
includes `d` and `q`, which are built from horizontally reflected components;
Plex draws those forms directly and does not show the reversal.

This is evidence for a safer mechanical first pass—not evidence that Balanced
resembles a designed italic. Mean Balanced-versus-official silhouette
differences were `7.237%` for Inter, `29.219%` for Noto Sans, and `19.798%`
for IBM Plex Sans because the official italics include deliberate redrawing,
recomposition, and spacing.

[Read the complete three-family report](contributor/italic-balanced-broad-latin-benchmark.md).
Click the combined story sheet for the full `4800 × 6424`, 144-DPI source.

[![Deterministic Balanced capacity and limits in Inter, Noto Sans, and IBM Plex Sans](contributor/images/italic-balanced-three-family-story.png)](contributor/images/italic-balanced-three-family-story.png)

The family-specific audit sheets remain available for closer inspection:

[![Inter Broad-Latin italic audit](contributor/images/italic-balanced-inter-v4.1-broad-audit.png)](contributor/images/italic-balanced-inter-v4.1-broad-audit.png)

[![Noto Sans Broad-Latin italic audit](contributor/images/italic-balanced-noto-sans-cb097900-broad-audit.png)](contributor/images/italic-balanced-noto-sans-cb097900-broad-audit.png)

[![IBM Plex Sans Broad-Latin italic audit](contributor/images/italic-balanced-ibm-plex-sans-71d012bc-broad-audit.png)](contributor/images/italic-balanced-ibm-plex-sans-71d012bc-broad-audit.png)

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
- Recursively inspects component chains and reports each matrix, determinant,
  shear commutator, and chain.
- Permits translation and commuting linear transforms, including uniform
  scale.
- Blocks reflection, rotation, non-uniform scale, cycles, unreadable
  transforms, and explicit component-master mismatches when safety cannot be
  established within `1e-6`.
- Applies a reviewed batch all-or-nothing. It never silently excludes glyphs;
  the designer can explicitly rerun with `skip_glyphs`.

Safety is based on actual outlines and component construction, not glyph names
or Unicode categories. Protected and design-sensitive forms still receive
manual-review warnings without being blocked merely because of their identity.

`stem_policy=copy_from_source` remains review-only. It reports source stem
availability but does not silently edit Font Info; use
`set_master_stem_metrics` for that separate confirmed mutation.

## Recommended workflow

1. Verify the source Roman and target italic masters and the target
   `italicAngle`.
2. For path-only or transform-safe constructions, compare Balanced with Raw
   and Cursivy; inspect blocked glyphs, components, anchors, topology, stems,
   bounds, and metrics.
3. Run `apply_italic_first_pass` with `dry_run=true`.
4. If the batch is blocked, decide whether to rebuild those components or
   explicitly rerun with `skip_glyphs`.
5. Apply only the approved scope with `confirm=true`.
6. Redraw, space, kern, and proof the result as an italic design.

The tool never saves the font.
