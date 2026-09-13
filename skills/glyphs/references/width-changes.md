# Exact advance changes

Reuse the specific connection's `$glyphs` context and verify `width_delta` in
the retained `get_status.jobKinds`. A missing private capability requires updating the
bridge, sidecar and skills together; do not substitute an older-build workflow.

Reuse the intended `document_id`; discover only when it needs resolving. Inspect live
master/layer IDs and before widths using the layer-read reference. Reads work
on dirty fonts, but external width preparation requires a saved, clean source.
Never Save merely to satisfy this requirement without user authorization.

For “add 17 units to A and B”, call `start_job` with:

```json
{"document_id":"<retained ID>","kind":"width_delta","glyphs":["A","B"],"delta":17}
```

Use explicit glyph names. The delta is a finite non-zero number; negative and
fractional values are supported, booleans are rejected. This adds to each
existing advance; it does not set one absolute width across masters.
**All stored layers** of each named glyph are included, including backup and
special layers. There is no master filter and no width-specific `options`.
Omitting `glyphs` selects the full font; do not omit it for a scoped request.

Poll `get_job` with the returned `job_id` until ready or a terminal error.
Preparation rejects unknown-only and mixed valid/missing glyph requests with
the missing names. Correct the explicit names on the same document ID; a
missing glyph is not a reason to rediscover documents or accept a partial job.
Reconcile uncertain requests using the existing job ID before creating another.

Review `changeCount` and every returned `sample` before `apply_job`.
The sample is limited to 10 changes: compare its length with `changeCount`.
Ten of 90 is incomplete preview evidence, not a complete review. Report that
limit explicitly; do not claim to have inspected unreturned changes. If the
task requires every prepared entry reviewed, stop for that requirement rather
than presenting a partial preview as complete.

Apply the ready job once, poll to completion, then reread the explicit layers.
Check requested advances, unchanged outlines and unrelated metrics, including
metrics keys and component alignment where present. Do not disable native
alignment/keys to force an outcome. Report constraints or missing evidence.
Width arithmetic alone does not establish good spacing or typographic quality.

For native **Undo**, open an affected glyph in **Edit View**. Undo/Redo is
grouped per glyph across its changed layers; Font View has different history
context. Use `discard_job` for whole-job restoration or cancellation, then
verify the result. Reapplying the same job is not a new delta. A new accepted
width-delta job is additive; an explicitly authorized Save accepts the prior
change. Never retry an uncertain write as a new job, silently switch fonts or
save/export/close a document without authorization.
