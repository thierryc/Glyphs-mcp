---
name: glyphs-mcp-spacing
description: Measure, reason about, preview, verify, and revert horizontal or vertical spacing in Glyphs through generic v2 reads and physical operations.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP v2 spacing

Typographic expertise belongs here. The tools expose evidence and mechanical
writes; they do not decide what should be preserved, choose reference glyphs,
reject categories, or solve an underdetermined spacing request.

## Evidence first

1. Call `get_server_info` and require `data.apiMajor == 2` plus the generic selector,
   projection, preview, and Python capabilities.
2. Resolve the exact `documentId` with `list_documents`.
3. When a factual claim or API detail matters, call `search_knowledge` first.
   Retrieve exact entries with `get_knowledge`. In particular, use
   `practice.spacing-physical-model` and
   `practice.negative-sidebearings` instead of treating a negative bearing as
   runtime-invalid.
4. Read exact layers with `read_document`. Prefer an `entity="layer"`
   selector constrained by exact IDs and `parent.glyphName`; metadata filters
   may be used for audits, but previewed mutations must resolve to exact layer
   identities. Request the relevant canonical fields plus `bounds`,
   `spacing.horizontal`, `spacing.vertical`, `geometry.counts`, `alignment`,
   `inheritance.metrics`, `ownership`, and provenance. Read the font `grid`
   projection separately when snapping matters.
5. Compare masters, special layers, styles, or other documents as evidence.
   Turn cross-document references into explicit numeric values before preview.

Treat projected `leadingBearing` and `trailingBearing` as observations; writes
still use the explicit physical operations below.

The alignment projection separates configured component modes from effective
native state:

- `configuredAutomaticComponentCount` counts raw modes other than `-1`;
- `modeCounts` reports raw `-1`, `0`, `1`, and `3` values;
- `effectiveLayerAlignment` comes from native `GSLayer.isAligned`;
- `hasAlignedWidth` remains a separate native observation.

Mode `0` is contextual configuration, not proof that alignment is active. A
mixed path/component layer can retain mode `0` while its complete foreground is
translated normally.

Partial observations are not proof. If bounds or metrics are unavailable, use
bounded `execute_python(mode="read_only")` inspection or stop rather than
inventing a value.

`inheritance.metrics` separates configured keys, stored measurements, and
values resolved by native `GSLayer.syncMetrics()` on a detached copy. Keys use
the layer's associated master/interpolation context; a layer key can override
the glyph key. When a retained key and numeric target disagree, choose to
preserve the resolved value, change or remove the key, or change its reference.
Tools expose and verify that choice, never make it.

## Physical model

Let the foreground bounds be `(x, y, w, h)`, horizontal advance be `a`,
vertical origin be `o`, vertical advance be `v`, and explicit geometry
translation be `(dx, dy)`.

Horizontal results are:

- `LSB = x + dx`
- `RSB = a - (x + dx + w)`

Vertical results are:

- `TSB = o - (y + dy + h)`
- `BSB = y + dy - o + v`

These equations do not determine a unique write until the agent states what
is preserved. Common explicit choices include:

- target LSB while preserving advance: `dx = targetLSB - x`, keep `a`;
- target RSB while preserving advance:
  `dx = a - x - w - targetRSB`, keep `a`;
- target both horizontal bearings: `dx = targetLSB - x` and
  `a = targetLSB + w + targetRSB`;
- target advance only: set `width`, use no translation;
- target both vertical bearings without moving geometry:
  `o = targetTSB + y + h` and `v = targetTSB + h + targetBSB`;
- target a vertical bearing while preserving origin or advance: solve the
  corresponding equation and state the chosen invariant.

Never let a tool infer preservation. Record the arithmetic and the selected
invariants in the explanation and preview.

## Declarative preview

Express the result with `preview_change` using only physical operations:

- `set` `width`, `vertOrigin`, or `vertWidth` for advances and origin;
- `translate` exact layers, shapes, nodes, or anchors by explicit x/y deltas;
- when intentionally changing metrics inheritance or component alignment,
  use explicit `set` operations for those authoritative canonical fields.

Use `quantizer="exact"` for an unsnapped value or `quantizer="grid"` for an
explicit mechanical grid choice. The normalized preview must show the applied
value or delta. Layer translation moves paths, components, images, and explicit
anchors through the same coordinate registry. Locks and configured alignment
modes are preserved metadata, not refusal policy. Detached native execution
and exact read-back decide whether Glyphs can reproduce the requested result;
structural invalidity, a missing coordinate payload, or a native rewrite of a
requested effect blocks the preview. Glyph category, script, mark status, or a
negative bearing never does.

Add before constraints for the physical values the arithmetic assumed and
after constraints for canonical fields and computed observations. Observation
operands use explicit paths such as `observation.bounds.x`,
`observation.spacing.horizontal.leadingBearing`, and
`observation.alignment.configuredAutomaticComponentCount`. References in
constraints must resolve exactly. Review the immutable preview for exact
targets, base-document and proposed fingerprints, normalized operations, semantic
diff, constraint values, provenance, completeness, warnings, and blockers.

After authorization, call `apply_change` with that `previewId`, its exact
`documentId`, live document fingerprint, and reason. Do not send the operations again:
apply must consume the stored patch and must not rerun planning. Re-read the
same layers and verify bearings, advance/origin, bounds, grid evidence,
geometry counts, and uniform translation. Use `revert_change` when the result
should be undone. Never auto-save.

The user may save in Glyphs before or during this workflow. A save-only event
does not invalidate the preview; only a changed live canonical document does.
Read the persistence reconciliation in apply/revert receipts: a saved final
state has no unsaved revert entry, while an intermediate save rebases history
to the exact residual diff. Never ask the user to postpone or disable Save.

## Python fallback

Generic reads and operations are preferred when they express the task. A
configured or effective alignment state is not by itself a reason to switch to
Python: first request the physical operation and let detached verification
decide. Python is permanent and available whenever generic mechanics do not
express the task:

- use `read_only` for bounded unsupported inspection;
- use `staged_document` for unsupported structural or algorithmic document
  edits, inspect its `previewId`, and apply it through `apply_change` without
  rerunning the code;
- use `live_open_world` only for unsupported UI, files, processes, or other
  external effects, and report which effects cannot be transactionally
  verified or reverted.

## Proofing and exceptions

Useful Latin proofs include `HHHOHH`, `HOHOHO`, `AVAYAW`, `JHJOJ`, `nnnon`,
`nonono`, repeated figures, and punctuation beside capitals, lowercase,
figures, and spaces. Adapt proof strings to the script, language, feature set,
and intended environment. Reference fonts are evidence, never ground truth.

Signed sidebearings are legal. Italic overhangs, swashes, marks, and shapes
such as J, j, f, or Q often require negative values. Inspect outline, direction,
neighbors, advance, and design intent; do not encode a category threshold as a
mutation blocker.
