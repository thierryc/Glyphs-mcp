# Drawing, languages and acceptance

## Design constraints

For each cap set and master, record the intended reading sizes, nominal flat
alignment, baseline, overshoot policy, proportions and chosen optical weight
relationship to lowercase/full capitals. Identify approved controls, protected
manual corrections and the source of each decision. Explicit direction and
recorded approved heights take precedence; otherwise petite flat alignment uses
that master's x-height. Establish small-cap height independently. Preserve full
capitals and font-wide metrics.

An existing unapproved drawing is evidence to inspect, not permission to normalize
it. Weight matching is an optical relationship chosen for this design; no universal
scale, offset, stem ratio or clearance applies. Distinguish a correction to the
whole set from one to related shapes or to a specific region. Test affected controls
before extending a correction, and preserve the scope of recorded pilot approval.

## Height and weight compensation

1. **Establish the reference.** Inspect each master's x-height metric and lowercase
   `x`, checking other lowercase alignment controls when needed. If metric and
   drawing disagree materially, record the discrepancy and resolve the intended
   alignment before editing. Do not change font-wide metrics to accommodate caps.
2. **Measure the relevant geometry.** Separate nominal alignment, actual ink
   bounds, baseline and overshoot. Measure the base form independently of accents,
   tails and other extensions; full layer bounds are not a flat-height target.
   Identify flat controls and curved extrema explicitly. Control-point extrema
   alone do not establish the extrema of a curve; bounds alone do not identify
   which region establishes alignment.
3. **Construct at the intended height.** Use measured source alignment and target
   height to establish the intended initial vertical transform. Account for the
   expected expansion and baseline displacement of vertical offset compensation,
   then verify actual results on detached candidates. The helper uses the master's
   `capHeight`, not a measured source alignment, as its denominator; see its
   [transform assumptions](helper.md#transform-and-measurement-limits). It has no
   custom baseline/vertical-scale parameter or detached-preview stage. Qualify
   copies separately before construction. When its assumptions do not fit, use an
   explicitly scoped supported correction or native workflow with its own recovery,
   or a designer handoff. Do not change metrics or invent helper parameters.
4. **Correct residual height errors selectively.** For an otherwise approved
   drawing, adjust the affected terminal, serif or upper contour region with its
   associated handles. Preserve stroke thickness, curve quality, baseline and
   established proportions. Use whole-glyph vertical scaling only when overall
   proportions require it, followed by renewed weight review. Do not discard an
   approved weight relationship merely to repair an alignment error.
5. **Restore weight while retaining alignment.** Assess vertical stems, horizontal
   arms, crossbars, bowl crowns, diagonals and serifs separately. Satisfactory stems
   do not justify another uniform offset when only arms or serifs are weak. Where
   appropriate, increase horizontal thickness inward while retaining the outer
   alignment boundary; check counter clearance and apertures before applying it.
6. **Verify after every compensation pass.** Remeasure flat tops, overshoots,
   baseline, stroke relationships, apertures, spacing and dependent accents. Read
   back native coordinates, recording the measurement source, units, precision
   tolerance and why it fits the operation. Do not replace fractional evidence with
   rounded display values. Numerical tolerance is distinct from optical acceptance;
   no single tolerance establishes both.

Protect approved anchors and mark placement during corrections. Inspect dependent
composites after base edits; make any necessary anchor or mark adjustment explicit
in the proposed correction and resulting record. Newly transformed base anchors
and regenerated composite anchors also require review. Do not silently move marks
or decompose composites to hide clearance problems.

Show before/after proofs for corrections, preserving corresponding master topology
by default. After one unsuccessful automatic correction of the same issue, hand
off the exact glyph/master/region and evidence for designer adjustment. On resume,
reinspect geometry, anchors, components and correspondence before proceeding.

## Review by shape and use

Use H/O for flat/round alignment and stem relationships, E for horizontals and
counter spacing, N/V for diagonal weight and joins, S for curve transitions and
terminals, R for bowl/leg balance. Add controls to the compact pilot when the font
shows particular risks: C/G for apertures, B for stacked counters, further diagonal
forms, M/W for extreme breadth, or Q and accented forms for extensions. Record
replacements and missing evidence; additions do not authorize full-set expansion.
Review remaining risks, including U bowls, during approved expansion.
Serif length, brackets, taper and contrast often need local redrawing.
High contrast, heavy weights and irregular lettering need
particular care; neither offset nor RMX can decide the intended design.

Judge petite caps beside lowercase at text sizes and small caps both beside
uppercase and in mixed/all-small-cap words. Measure actual stems and counter
space, but assess optical color through reading proofs. Avoid matching every
stroke numerically. Review overshoot separately from flat target height. Existing
source proportions and approved control glyphs guide related shapes; they do not
authorize blind copying of corrections to unrelated letters.

Review spacing before kerning, including mixed full caps/derived caps. Uppercase
kerning groups and values are not authoritative for smaller forms. Check anchors,
mark size and clearance in stacked accents, top/bottom marks and narrow letters.
Use native components where appropriate; avoid decomposing accents just to scale
them uniformly. Font-wide changes to default marks are outside derivation scope.

Correspondence requires contour order, starts, directions, node types and semantic
locations, not equal counts alone. Check affected interpolation spans and relevant
interior locations in the actual designspace, including combinations of axes where
applicable. Record sample locations and inspect alignment, weight, counters, joins
and curves; increase sampling around observed problems. Do not prescribe a fixed
master or sample count. Structural compatibility, sampled geometric checks and
designer acceptance are separate results; finite samples do not prove continuous
interpolation quality. Special layers are excluded by the helper and must be
handled deliberately before production export. Do not clean away designed overlaps
or hint references without review. Newly derived glyph hinting is a later task.

## Language and feature proof

Use Glyphs' current naming conventions: `.sc`/`.smcp` for small capitals and
`.pc`/`.pcap` for petite capitals. The helper accepts only `.sc`/`.pc`, including
explicit destinations; broader naming context is not broader helper support.
Inspect existing conventions without renaming glyphs to fit the helper. Audit
other names through ordinary reads. Do not map typographic alternates to phonetic
small-cap Unicode characters.

Review automatic `smcp`/`c2sc` and `pcap`/`c2pc` source, including interaction with
`locl`, `ccmp` and ligature features. The lowercase-only features leave full caps
available; all-cap formatting combines both conversion routes. Preserve authored
manual code and language systems. Update automatic blocks only through supported
actions/routes; compile and shape separately when authorized.

- Turkish/Azeri dotted and dotless I need distinct derived mappings under the
  appropriate language systems. Test `i ı İ I` and a word such as `Diyarbakır`.
- Decide sharp-S presentation with the designer and preserve language intent;
  do not infer a universal SS-versus-capital-sharp-S policy from name casing.
- Check encoded `fi`, `fl` and legacy digraphs through their decomposition and
  conversion features rather than introducing unjustified new ligature forms.
- Catalan `l·l`/`L·L` needs a correctly placed middle dot, including feature order
  and the font's existing localized construction.
- For Spanish, inspect `¿Qué? ¡Sí!` in mixed and all-derived text. Pair inverted
  punctuation with its upright equivalent. Derived punctuation ordinarily belongs
  in `c2sc`/`c2pc`, rather than shrinking punctuation alongside lowercase-only text.
- Include AE/OE, accented bases and supported mark combinations from the actual
  font/language brief; do not expand the font's declared language coverage silently.

## Human review record

For each issue record glyph, exact master, region, observation, proof/measurement,
proposed correction, decision and actual follow-up state. Distinguish:

- Pilot accepted: the direction may be expanded.
- Manual adjustment needed: give a precise native editing task, then wait.
- Technically checked: state what geometry/compatibility/feature behavior passed.
- Designer accepted: record the human's actual acceptance and remaining issues.

Fingerprint changes after manual edits are expected evidence. Adopt them only
after fresh inspection and retain them in subsequent reports. Do not treat Keep,
timeout, successful script execution or absence of warnings as optical approval.
For productivity evaluation record actual designer minutes and correction counts
for manual, simple-scale and guided construction; report unmeasured baselines.

## Task-local completion record

Keep this record outside the font, in the helper's existing `review` payload or a
companion task report. These are reporting conventions, not new top-level helper
fields. Bind the exact document and record mode, glyph scope, cap set and master;
rebind and inspect after reopening or restarting. Record:

- Constraints: intended sizes, reference and target alignment, baseline/overshoot,
  chosen optical weight relationship, approved controls and decision provenance.
- Protected work: manual corrections, anchors, mark placements and accepted
  fingerprints, with fresh inspection evidence before adopting changed geometry.
- Review evidence: measurements and tolerance rationale, proof context, affected
  spans and sampled designspace locations, approval source and exact approved scope.
- Handoff: issues by glyph/master/region, proposed correction, actual follow-up,
  remaining coverage and next action. Preserve valid approval on continuation;
  request review only for a changed direction or scope not already approved.

For each cap set/master, track the following areas independently. Give each a
state of **pending**, **checked**, **accepted**, **unresolved** or **not applicable**,
and attach evidence or a reason. Use **accepted** only for actual designer approval;
**checked** describes the stated technical check, not optical acceptance.

| Area | Evidence to record |
| --- | --- |
| Drawing | Curves, proportions, terminals and protected corrections; remaining regions needing work. |
| Height | Reference/target, flat alignment, baseline and overshoot measured independently of extensions. |
| Weight | Chosen optical relationship and separate assessment of stems, arms, crowns, diagonals and serifs. |
| Spacing | Native spacing proofs, mixed full/derived caps and remaining adjustments before kerning. |
| Accents | Anchor positions, mark placement/clearance and dependent composites after base edits. |
| Interpolation | Structural correspondence, affected spans, sampled interior locations and unresolved problems. |
| Feature behavior | Source review, compilation and exported shaping as separate evidence; unperformed checks remain pending. |
| Designer approval | Who approved which direction/scope and when; open issues and outstanding decisions. |

For an audit without prior guards, report a fresh baseline and unavailable historical
comparison. If sources or names do not fit the helper, retain ordinary inspection
evidence. Do not fabricate approval or verification flags to complete the record.
Keep compilation and exported shaping distinct, and export only when authorized.
