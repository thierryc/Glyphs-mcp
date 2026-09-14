# Lean v2: native slant and optional straight-stem preservation

Use `get_status` and `list_documents` to resolve one saved source. Work on an
explicitly authorized disposable or bootstrap copy. The current workflow edits
existing master layers; it does not create masters or set italic export metadata.

Prepare `start_job(kind="slant", glyphs=[...], options={"angle":12,
"pivotY":0, "preserveStraightStems":true, "masters":[...]})`. Omit `delta`.
Omitted glyphs/masters select all ordinary master layers. Positive angles follow
the Glyphs native slant convention. Angles must be nonzero and within ±30°;
the default is 12°. The correction is optional and defaults to false.

The external worker runs native slant on detached layers. With correction enabled,
it conservatively detects opposite straight segments and restores their measured
perpendicular separation. Curve-adjacent sides, ambiguous node reuse and unsafe
deltas are excluded. This preserves accepted straight-stem widths, not a complete
italic design. The real rectangular fixture compares native slant, Cursivy and
the native thickness-only option: each yields 97.814760 units from 100 at 12°;
the optional correction measures 100 within 1e-9 from output coordinates.
That comparison establishes only this fixture's objective.

Advance widths stay unchanged. Anchors follow native slant. Manual components
use affine composition, with conjugation when their base master is also selected
to avoid double slanting. A native matrix that cannot round-trip exactly rejects
the job before application. Automatic component layers are skipped; their local
data stays intact, but their displayed outlines can follow changed base glyphs.
Review skipped layers and component dependencies explicitly. The workflow does
not override alignment or infer arbitrary smart-component behavior.

Use `get_job` to review the report and compact coordinate patch, then `apply_job`
within the user's authorized scope. The bridge uses native setters with topology
and before/after read-back guards. Fractions, node objects, hints and metadata
remain intact. Use `read_entities` for target widths and outline hashes and review
the proof in Glyphs. Native Save accepts the result; `discard_job` restores the
whole job. Native Undo remains per glyph.

Keep custom Tunni, general compensated scaling, smoothness repair, and a full
balanced-italic engine outside this claim. A raw mechanical draft still needs
designer review for curves, spacing, joins, optical balance and interpolation.
