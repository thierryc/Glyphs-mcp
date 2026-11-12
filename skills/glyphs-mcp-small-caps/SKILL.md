---
name: glyphs-mcp-small-caps
description: Create, continue, refine and audit Latin small and petite capitals in Glyphs 4, with pilot approval, protected human corrections and native proof review.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs Small and Petite Caps

Create, continue, refine or audit cap sets in supported Latin fonts. Construction
produces a designer-reviewed **first pass**; it does not finish the typography.
The helper constructs `.sc` and `.pc` independently within its documented limits.
Use [drawing and language decisions](references/design.md) for measurement,
optical refinement, language behavior and proof acceptance.
Use the [dated research assessment](references/research.md) when choosing tools
or discussing learned models; models and RMX are optional.

## Choose the workflow

- **Create:** inspect fresh sources, construct a compact pilot and obtain explicit
  designer approval before expansion.
- **Continue:** inspect the exact document and current geometry, reconcile recovery
  and recorded approvals, then resume the next incomplete step. Preserve designer
  corrections. Reuse valid approval within its recorded scope; changed scope or
  design constraints need review of the affected direction.
- **Refine:** identify the existing drawing, exact glyph/master/region and optical
  purpose. Use bounded corrections with recovery and before/after evidence;
  construction never regenerates existing destinations.
- **Audit:** read and report existing cap sets without font mutation. No duplicate,
  edit job or construction pilot is required. Without prior fingerprints, establish
  a fresh baseline and state which historical comparisons are unavailable. Use
  ordinary reads when sources or naming do not fit the helper; do not rename caps.

These are workflow instructions, not helper API stages. The helper still accepts
only `inspect`, `construct` and `verify`. Follow the construction sections only
when creating missing glyphs; audits and local refinements do not imply expansion.

## Establish the brief

Reuse the [$glyphs](../glyphs/SKILL.md) connection and exact intended document ID;
resolve missing context through its connection/targeting references. Inspect
uppercase sources, existing derived glyphs, ordinary masters, metrics, anchors,
components, manual feature code, languages and intended reading sizes. Dirty
fonts need no Save for reads or native scripts. Choose targets from glyph data,
never change sidebar filters to automate selection.

Unless the designer specifies otherwise, petite capitals must use the font's
x-height as their nominal flat alignment height in each master. Round and pointed
forms may retain optically justified overshoot. Small-cap height is established
independently; existing full capitals retain their cap height.

Explicit direction or a recorded, approved existing height takes precedence over
this workflow default. Inspect unapproved existing drawings without normalizing
them. Resolve material metric/drawing discrepancies before editing; do not change
font-wide metrics to fit derived caps. Record constraints and the chosen optical
weight relationship per cap set and master. Establish an unspecified small-cap
height through pilot proofs. No universal scale, offset, stem ratio, clearance or
width applies. Resolve special layers or unusual lettering separately.

For edits, default to an unsaved `duplicate_document` copy including unsaved edits.
When continuing an established working copy, confirm its exact binding and recovery.
Creation/duplication follows the user's task authorization; never silently switch
fonts. Keep the original intact. No Save, export, install or restart is implied.

## Construct a pilot, then wait

Use **H O E N S R V**, or record replacements and missing evidence. Add diagnostic
glyphs for actual risks such as apertures, stacked counters, diagonals, extreme
proportions or accents; keep the pilot bounded. Derive each requested cap set
across its requested ordinary masters. The self-contained
[helper contract](references/helper.md) defines inspect, construct and verify,
explicit mappings, parameters, fingerprints and task-local reports.

Use existing [native script jobs](../glyphs/references/python-scripts.md) for
coordinated construction on the duplicate, with `entrypoint="script"` and exact
identity/parameters. Check `script.native.v1`, `script.recovery.snapshot.v1` and
preparation version 3. The font-edit request authorizes this native route; do not
add a second Run approval. Write-only script requests remain non-executing.

The helper constructs detached candidates, then attaches them after its internal
checks; it has no detached-preview stage for a review pause. Existing destinations,
including those with incomplete master coverage, are always preserved. It never
writes hidden workflow metadata into the font. Use the design reference's
[height and weight procedure](references/design.md#height-and-weight-compensation)
and check the helper's formula assumptions before construction.
Nonzero Offset Curve compensation needs a successful disposable qualification of
the exact host build/adapter. Inventory presence alone does not qualify execution.
If qualification fails, use the native UI handoff in the helper reference; do not
simulate the filter or claim scale-only drawings are compensated small caps.

Open native proofs with `open_edit_tab`. With `document.edit-tab.review.v1`,
stopped, known edits can retain recovery while a proof opens. Executing, prepared
or uncertain operations still block opening. Earlier runtimes require resolving
the existing lifecycle; do not Keep just to clear the block without explaining
that this ends recovery. Script recovery is a whole-font pre-run copy, includes
unsaved edits, discards later edits on restoration and lasts only this session.

Set `auto_keep=false` before any review wait. Present outlines and text at intended
sizes beside full caps/lowercase; request acceptance of height, proportions,
weight, overshoot and spacing. **Do not expand beyond the pilot without explicit
designer approval.** Silence, dismissal and timeout are not approval.

## Expand and refine

Expand approved settings to eligible bases, then construct accents with reviewed
base/mark mappings. Preserve existing destinations and human-edited pilot glyphs.
Use separate fresh inspections for expansion and after every manual correction;
never replay an old construct request against changed state.

Distinguish corrections affecting the whole set, related shapes and individual
regions. Preserve approved anchors and mark placement; inspect dependent composites
after base edits and explicitly record necessary adjustments.

For a bounded local correction, use supported outline edits where their clean
saved-baseline requirements fit, or a narrowly scoped native script with its own
recovery. Preserve corresponding master topology by default. Show before/after
proofs and specify the optical purpose. After one unsuccessful automatic correction
of the same issue, ask the designer to adjust it; do not loop speculative redraws.
Do not bypass stale-target errors or missing advertised capabilities with scripts.

Each handoff names the exact glyph/master/region, evidence, proposed adjustment,
and decision needed. Before manual editing reconcile the current workflow's Keep
or recovery choice. On resume reread geometry, anchors, components and master
correspondence; protect manual changes from regeneration.

## Verify and hand off

When suitable prior evidence exists, run helper verification with its identity and
last result fingerprints. Changed fingerprints are review evidence, not permission
to overwrite. Maintain the [task-local completion record](references/design.md#task-local-completion-record)
with approved constraints, manual corrections, evidence, unresolved issues and next
actions. Rebind exact document IDs and inspect again after reopening/restarting.

Check native drawing, color, spacing, accents, compatible endpoints and sampled
intermediate shapes across affected spans and relevant interior designspace
locations. Increase sampling around observed problems. A matching hash or node
count is not optical acceptance or continuous interpolation proof. Use the
existing spacing/master-compatibility
skills only as needed. Review OpenType source through the feature skill; preserve
manual code and verify both lowercase-only and all-cap conversion for each set.
Compilation and exported shaping are separate evidence; export only when authorized.

Report created/preserved/skipped/review-required glyphs and what was actually
verified. Designer acceptance, technical verification and unfinished drawings are
separate results. Record measured correction time against manual/simple-scaling
baselines when evaluating productivity; do not invent a speedup.
