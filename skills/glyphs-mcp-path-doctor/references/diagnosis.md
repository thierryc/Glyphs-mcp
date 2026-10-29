# Read-only diagnosis

```json
{"kind":"path_diagnostics","document_id":"EXACT_LIVE_ID",
 "options":{"glyphs":["generic"],"layers":"all_masters"}}
```

`glyphs` accepts `all` or 1–10,000 unique names. `layers` accepts `all_masters`
or 1–100 exact stored foreground layer IDs. Prefer bounded explicit scope for
a local question. The full-font option is a sliced live job. Follow `get_job`
until completed/failed/cancelled; retain the same job identity after a timeout.
Results are diagnostic and cannot be applied or accepted. No saved baseline or
external worker is required. The full report is a local job artifact; summarize
its evidence without copying private geometry into public material.

Each issue includes exact addresses, a stable ID, geometry/attribute/profile
state hash, evidence, severity, confidence, classification, a qualified repair
or held reasons. A `repair` is a proposal, not permission. IDs are scoped to the
bound document/report; raw node indices are not durable identities after edits.

Scope explicitly excludes historical/background layers and expanded components.
Component reference counts are reported. Unsupported paths make coverage
incomplete. A sliced scan is generation-guarded, not an atomic native snapshot.
Recompute after observed edits or a stale result. Never substitute saved files
for live evidence without identifying that different source and its limitations.

Findings:

- `redundant_closed_seam`: the specific automatic zero closing line. Its effect
  on a reported native editing failure remains unproven until reproduced.
- `closed_stroke_fill_unset`: inherited/unset fill may affect native appearance;
  inspect separately, do not silently write `fill=0`.
- `corner_connections`: valid independent-handle behavior, not a defect.
- `open_return`: valid open-stroke return/retracing, no seam repair.
- `inactive_open_start_profiles`: preserve stored controls with no incoming segment.
- Malformed segments or unsupported native attributes/references: explicit
  diagnostic evidence, no automatic repair.
