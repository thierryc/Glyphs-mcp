# Native slant and optional straight-stem preservation

Reuse the verified connection and intended `document_id`; do not rediscover
for a missing glyph. If the user now means a different/current font, resolve
that target explicitly. Check that preparation uses its current saved source.
Dirty reads need no Save, but this external editing job requires a clean source.
Use task-authorized disposable copies for exploration. The job edits existing
ordinary master layers; it does not create masters or set italic export metadata.
For the master's stored native `italicAngle`, use a requested
[master property read](../../glyphs/references/master-reads.md) with
`master.properties.v1`. A slant angle and stored master angle are different values;
neither operation silently changes the other.

## Mechanical request and review

Supply the actual document ID, exact master IDs and glyph names, for example:

```json
{"document_id":"KNOWN_DOCUMENT_ID","kind":"slant","glyphs":["n","o"],"options":{"angle":12,"pivotY":0,"preserveStraightStems":false,"masters":["LIGHT_ID","REGULAR_ID","BOLD_ID"]}}
```

Send this to `start_job`. Omit `delta`. Angles are nonzero and within ±30°;
default 12°. Positive angles follow Glyphs' native convention. `pivotY` defaults
to 0 and is bounded to ±10000. Omitted glyphs/masters select all ordinary master
layers; prefer explicit scope when the task identifies it.

Poll the same `job_id` using `get_job(include_preview=false)` until ready.
Read its report once before `apply_job`. Retain that review in context. For a
large report, inspect bounded relevant sections while accounting for every
target, options, suggested/unchanged/skipped counts and dependency warnings.
Do not call a partial excerpt a complete review. Poll application/discard with
`include_preview:false` too; do not resubmit an uncertain write as a new job.

The external worker slants detached native layers. Advance widths stay fixed;
anchors follow the slant. Manual components use affine composition, with
conjugation when their base master is also selected to avoid double slanting.
A native matrix that cannot round-trip exactly rejects preparation. Component
indexes in that error refer to `layer.components`, excluding paths. Automatic
component layers are skipped: local data is preserved, but displayed outlines
can follow changed bases. Review those dependents explicitly; no arbitrary
smart-component behavior is promised.

## Opt-in straight-stem correction

Set `preserveStraightStems:true` only when requested. The worker conservatively
detects opposite straight segments and restores measured perpendicular
separation. Curve-adjacent sides, ambiguous node reuse and unsafe deltas are
excluded. Review compensated counts and skipped reasons in each layer's
`correction` evidence. This is not a full balanced-italic engine or a promise
about curves, joins, spacing or optical quality.

## Verification and recovery

Read target widths/outline hashes through `read_entities` and inspect native
drawing, anchors, component dependents and bounds in the examined masters.
Separate applied/skipped counts from verification: unchanged hashes alone do
not establish good interpolation or compatibility. State unverified evidence.
Preserve existing objects, hints, metadata, alignment and unrelated material.

Native Undo/Redo is per glyph; `discard_job` restores the whole job or cancels
work. Check stored-data restoration and derived native bounds separately.
If dependent bounds disagree with restored geometry, view that exact dependent
layer in Glyphs and recheck. Report this native refresh limitation; stale bounds
alone do not prove object damage. Do not substitute a different layer or master.
Dirty-indicator restoration is not promised. When the task authorizes
persistence after review, `accept_job` verifies targets and saves the whole
document; there is no implicit Save or font replacement.

A clean font can still fail a later preparation/application with a saved/live
precision conflict: native Save may serialize rounded coordinates while live
objects retain more precision. Keep the exact target guard. Report the actual
target and conflict; identify serialization rounding only when supported by
saved/live evidence. Do not silently round, Save, close or reopen a font.

If the task authorizes closing/reopening that disposable source, first confirm
the rejected job made no changes, preserve its result, reopen that exact path,
obtain a fresh public document ID and prepare again. Otherwise explain that
the saved source and live target disagree and what authorized action is needed.
Repeating slant is additive; it is not expected to become a no-op. Dirty or
stale-source errors do not authorize replacing another open font. A required
missing private capability means the installation needs updating, not an
earlier-private fallback workflow.
