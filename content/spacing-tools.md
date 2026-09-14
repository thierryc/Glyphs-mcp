---
title: Spacing
---

The `spacing` job prepares sampled spacing suggestions from a saved font using the external native worker. It changes existing foreground positions and widths through generic patches after you review and apply the result.

## Prepare a proposal

Use `start_job` with `kind="spacing"`, a document ID and an optional `glyphs` list. Omit `delta`. Omitted glyph names select all master layers; special layers are outside this workflow.

```json
{
  "document_id": "<document ID>",
  "kind": "spacing",
  "glyphs": ["H", "O", "n", "o"],
  "options": {"reference": "auto", "widthMode": "auto"}
}
```

| Option | Default and use |
| --- | --- |
| `reference` | `auto`: choose a class-aware reference. `*` means self-reference; a glyph name selects it explicitly. |
| `references` | Per-glyph reference overrides. Explicit references do not silently fall back. |
| `masters` | Selected master IDs; omitted or empty means all masters. |
| `widthMode` | `auto`, `preserve` or `proportional`. |
| `area` | 400; controls the sampled spacing area. |
| `depth` | 15 percent of x-height. |
| `sampleStep` | 5 font units. |

Automatic selection uses H for uppercase, x/n/o for lowercase and one/zero for decimal figures, with reported fallbacks. These are sampled suggestions, not a guarantee of optimal optical spacing.

## Review the evidence

Call `get_job` and inspect the report sample and full `report.json` path. Review references, fallback choices, before/after metrics, preservation reasons and unavailable targets before applying.

The workflow preserves tabular widths, zero-width marks, metrics keys and native component alignment. `preserve` keeps widths explicitly. `proportional` disables automatic equal-figure detection; named tabular glyphs and fixed-pitch widths remain protected. Alignment-dependent layers can be excluded rather than overridden.

## Tiny differences

The absolute tolerance is **0.001 font units**, inclusive. A translation of 0.0009 or 0.001 units is skipped; a translation of 0.0011 remains significant. Width is evaluated independently: a negligible shift can accompany a meaningful width patch. Reports describe the effective changes after this filtering.

This is a project comparison policy, not a universal minimum coordinate supported by Glyphs. A meaningful requested translation that a native setter cannot store exactly is reported as unavailable during preparation. Do not round it merely to make the test pass. Native apply, Undo/Redo and rollback remain exact.

## Apply and inspect

Use `apply_job`, wait for completion with `get_job`, then review varied text in Glyphs. Enable [Changes Against Reference](workflows/visual-review.mdx) to inspect the active layer's geometry and width. It does not evaluate spacing quality for you.

Use bounded `read_entities` for exact widths and outline hashes. Native displayed bearings can be rounded; coordinate or detached native measurements supply fractional evidence. To abandon the result use `discard_job`; to accept it use native Save.
