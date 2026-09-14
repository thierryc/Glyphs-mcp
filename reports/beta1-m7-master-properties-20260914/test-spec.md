# M7 — master properties acceptance specification

Scope: only gap 7. Preserve seven tools, five jobs, current reads/editing hooks,
v1, user documents and historical reports. Follow the accepted gaps 7–14 plan.

Add requested `ascender`, `capHeight`, `xHeight`, `descender`, `italicAngle`,
`axes` to exact master and master-page reads. Advertise `master.properties.v1`
through the existing negotiated read capabilities. Existing id/name requests
must not read metrics or axes. No glyph traversal or implicit save.

Metric values come from native `default*` getters. Return unavailable evidence
as `unsupported_read` with the field named when a requested getter is missing,
unreadable or non-finite; do not fabricate zero or use truncating wrapper aliases.
Preserve the existing nullable id/name contract. Native axis count/index access
preflights at most 32 axes per master and 256 master-axis items across a request;
over-budget requests return `invalid_request` before value projection. Empty
pages have no axis projection. Axis values are complete native-order collections:
`items`, `total`, `returned`, `complete:true`; each item contains `axisId`, `tag`,
`name`, `index`, `internalValue`, `externalValue`. Native null numeric values
remain null with `complete:false` and explicit unavailable field locations.
Missing/unreadable getters or malformed identity/metadata reject the read with
`unsupported_read`; no partial success masquerades as complete evidence.

Exact requests retain strict ID lookup and the 100-target bound. Pages retain
the current cursor contract, count/boundary validation and 100-master limit.
Reads are fresh and live, not atomic across calls. No fallback for older private
builds. Update bridge/protocol, sidecar tool guidance and focused skill mirrors.

Tests: fractional and negative metrics, zero and signed angles, duplicate master
names, custom/reordered axes, differing internal/external coordinates, empty axes,
33-axis and over-256-item rejection, valid boundary requests, unsupported fields,
missing/native failure values, dirty/unsaved reads, missing/stale IDs, foreground
switch, stale page/recovery and native object/data/history preservation. Keep
small indexed-only doubles separate from actual native evidence.

Native qualification: isolated getters and source checks before installation;
fresh disposable synthetic three-master/large fixtures and pinned Roboto Slab;
first attempt, warm-up, five repetitions. Initial discovery versus known-ID cost;
native callback versus queue and HTTP latency; host load, probe overhead and
two-second follow-up samples. Native target p95 <50 ms/max <200 ms. Use the
existing o200k_base/compact sorted JSON token method, not claimed billing usage.

Install the qualified candidate through the existing authorized installer,
verify manifest versus loaded identities and managed skills. Preserve/reopen
clean original documents; never close dirty unrelated work without preservation.
Report results and pause before gap 8. No release publication.
