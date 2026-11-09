---
name: glyphs-mcp-small-caps
description: Derive editable Latin small and petite capitals from uppercase in Glyphs 4, with pilot approval, protected human corrections and native proof review.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs Small and Petite Caps

Create a designer-reviewed **first pass**, not finished typography. Support `.sc`
and `.pc` independently. Use [drawing and language decisions](references/design.md)
for construction, optical refinement, language behavior and proof acceptance.
Use the [dated research assessment](references/research.md) when choosing tools
or discussing learned models; models and RMX are optional.

## Establish the brief

Reuse the [$glyphs](../glyphs/SKILL.md) connection and exact intended document ID;
resolve missing context through its connection/targeting references. Inspect
uppercase sources, existing derived glyphs, ordinary masters, metrics, anchors,
components, manual feature code, languages and intended reading sizes. Dirty
fonts need no Save for reads or native scripts. Choose targets from glyph data,
never change sidebar filters to automate selection.

Use established target heights and weight relationships when present. Otherwise
ask for target heights using pilot proofs: petite caps commonly match x-height;
small caps usually exceed it. Do not prescribe a universal ratio, stem match or
width. Resolve special layers or unusual lettering as separate design decisions.

Default to an unsaved `duplicate_document` copy including current unsaved edits.
Creation/duplication follows the user's task authorization; never silently switch
fonts. Keep the original intact. No Save, export, install or restart is implied.

## Construct a pilot, then wait

Use **H O E N S R V**, or record replacements and missing evidence. Derive each
requested cap set across its requested ordinary masters. The self-contained
[helper contract](references/helper.md) defines inspect, construct and verify,
explicit mappings, parameters, fingerprints and task-local reports.

Use existing [native script jobs](../glyphs/references/python-scripts.md) for
coordinated construction on the duplicate, with `entrypoint="script"` and exact
identity/parameters. Check `script.native.v1`, `script.recovery.snapshot.v1` and
preparation version 3. The font-edit request authorizes this native route; do not
add a second Run approval. Write-only script requests remain non-executing.

The helper constructs detached candidates before attachment; existing destinations
are always preserved. It never writes hidden workflow metadata into the font.
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

Run helper verification against the last result fingerprints. Changed fingerprints
are review evidence, not permission to overwrite. Record approved parameters,
manual corrections, unresolved issues and next actions in a task-local report;
rebind exact document IDs and inspect again after reopening/restarting.

Check native drawing, color, spacing, accents, compatible endpoints and sampled
intermediate shapes. A matching hash or node count is not optical acceptance or
continuous interpolation proof. Use the existing spacing/master-compatibility
skills only as needed. Review OpenType source through the feature skill; preserve
manual code and verify both lowercase-only and all-cap conversion for each set.
Compilation and exported shaping are separate evidence; export only when authorized.

Report created/preserved/skipped/review-required glyphs and what was actually
verified. Designer acceptance, technical verification and unfinished drawings are
separate results. Record measured correction time against manual/simple-scaling
baselines when evaluating productivity; do not invent a speedup.
