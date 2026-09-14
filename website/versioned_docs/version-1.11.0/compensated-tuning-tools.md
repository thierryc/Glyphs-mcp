---
title: Compensated tuning candidates
description: Preview and safely accept two-master compensated scaling through a candidate session.
---

# Compensated tuning candidates

Compensated tuning is a deterministic two-master scaling workflow. It compares
compatible outlines in a base and reference master, derives interpolation
factors from their geometric difference, and scales while approximately
preserving stem thickness. It is not a generic “make this master lighter”
command.

Glyphs MCP 1.8 exposes this workflow only through candidate sessions:

1. `preview_compensated_tuning_candidate`
2. `review_outline_candidate_session`
3. `accept_outline_candidate_session` with `dry_run=true`
4. explicit designer approval
5. `accept_outline_candidate_session` with `confirm=true`

The old measurement, direct review, and direct batch-apply commands are removed.
Their deterministic mathematics remains internal to the candidate adapter.

## Preconditions

- Use different base and reference masters with compatible path and node
  topology.
- Target explicit glyphs and masters. Components are blocked because this
  operation promotes node coordinates, smooth flags, and width only.
- Use finite scale and compensation values. `keep_stroke` matters only when a
  real two-master geometric delta exists.
- Never expect `base_master_id == ref_master_id` to create a weight change.
- The tool never saves the font.

## Important parameters

- `base_master_id` is the source master being tuned.
- `ref_master_id` supplies the compatible comparison geometry.
- `output_master_id` identifies the destination source layer.
- `sx` and `sy` are horizontal and vertical scale factors.
- `keep_stroke` controls compensation when factors are derived automatically.
- Explicit `q_x` and `q_y` override automatic compensation.
- `extrapolation` is `clamp`, `allow`, or `error` when a computed factor falls
  outside `[0, 1]`.

## Safe workflow

First resolve the font and master IDs with `list_open_fonts` and
`get_font_masters`. Preview a small explicit glyph set:

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
  "extrapolation": "clamp"
}
```

Inspect the golden-yellow difference-only Candidate Reporter. The normal Glyphs
outline remains visible; unchanged geometry receives no overlay drawing. If
manual edits are needed, call `materialize_outline_candidate_session`, edit the
native candidate layer, and review it again.

Next call `review_outline_candidate_session`. Confirm that topology is intact,
components are absent, the source is not stale, and only allowed fields differ.
The review returns a short-lived token bound to source and candidate
fingerprints.

Call `accept_outline_candidate_session` first with `dry_run=true` and the exact
token. Show the designer the target count, skipped/error reasons, largest
deltas, width changes, and rollback plan. Only after explicit approval, call it
again with `confirm=true`. Acceptance consumes the token, rechecks both
fingerprints on the main thread, promotes only allowed fields, verifies the
read-back, removes session layers on complete success, and never saves.

## Common mistakes

- Using one master as both base and reference leaves no second shape to
  interpolate against.
- `keep_stroke` is not an in-place thinning control.
- Explicit `q_x` or `q_y` supersede the corresponding automatic factor.
- Incompatible topology or components are safety failures, not candidates for
  automatic repair.
- A stale source or candidate requires a new review and token.

See the [safety model](./concepts/safety-model.mdx) and
[command set](./reference/command-set.mdx) for the common result envelope and
candidate lifecycle contracts.
