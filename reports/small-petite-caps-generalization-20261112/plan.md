# Small- and petite-cap skill generalization

Reviewed 2026-11-12. The review initially produced this plan only. Its
documentation-only implementation is now complete; see the
[implementation and validation results](validation.md). Executable code, fonts,
installation and runtime remain unchanged by this task. The sections below retain
the reviewed implementation plan and its original review-time evidence.

## Review decision

Proceed with the proposed documentation revision, with the clarifications below.
The x-height rule is this workflow's default, subject to designer intent; it is
not a claim that every typeface must follow a universal typographic convention.
Generalize design guidance across supported Latin work, while keeping the helper's
narrow construction eligibility explicit.

1. **Resolve default precedence.** An explicit designer direction or recorded,
   approved existing height takes precedence. With neither, petite flat alignment
   defaults to each master's x-height. An unapproved existing drawing is evidence,
   not permission to normalize it. Inspect and report discrepancies before editing.
   Small-cap height remains an independent decision. Preserve full-cap height and
   font-wide metrics.
2. **Separate measured design intent from the implemented transform.** The helper
   uses `(height - 2*offsetY) / master.capHeight`, followed by vertical translation
   by `offsetY` and the qualified offset operation. It has no measured-source-height,
   baseline, arbitrary vertical-scale or regional-compensation parameter. Describe
   the formula's alignment assumptions and mandatory readback; do not imply that
   inspection automatically changes its denominator. A discrepancy needs an
   explicitly scoped correction through an existing supported/native workflow,
   with its own recovery, or a designer handoff. Do not adjust global metrics to
   make the formula fit.
3. **Separate workflow modes from helper stages.** Create, continue, refine and
   audit are agent instructions. `run_caps` continues to accept only `inspect`,
   `construct` and `verify`. Existing destination glyphs are always preserved;
   construct cannot revise them or fill their missing master layers. Refinement
   must not be described as replaying construction.
4. **Make audit read-only.** Inspection and reporting need no duplicate, edit job
   or construction pilot. Use `verify` only with a suitable recorded identity and
   result guards; without prior evidence, establish a fresh baseline and identify
   unavailable comparisons. The helper requires source rows and `.sc`/`.pc`
   destinations even for inspection; audit other existing naming arrangements or
   sets without usable sources through ordinary reads, without renaming them.
5. **Define evidence honestly.** Helper bounds include the entire layer, and its
   `topOvershoot`/`bottomOvershoot` fields are arithmetic bounds comparisons. They
   do not isolate a base from accents/tails or distinguish optical overshoot from
   extensions. Its topology comparison does not certify semantic correspondence,
   and it does not sample interpolation or verify feature behavior. Keep those
   separate from helper success and fingerprint stability.

## Repository and installed-skill discrepancy

The canonical source is [the repository skill](../../skills/glyphs-mcp-small-caps/SKILL.md).
The packaged copy under `plugins/glyphs-mcp/skills/glyphs-mcp-small-caps/` currently
matches it. The supplied installed directory at
`/Users/thierryc/.codex/skills/glyphs-mcp-small-caps` is a real directory, not a
symlink in this session. Its main skill and helper reference contain additional
Core Offset Curve guidance and a font-specific case report absent from the source
and packaged skill. Do not copy that directory wholesale into the project.

The repository helper implements only the qualified `layer-filter-keep` adapter.
Retain its exact-build qualification and existing UI handoff in this revision.
Extract the generic lessons: inspect actual gains and baseline, preserve source
fingerprints, test detached candidates, and reject changed correspondence even
when a compatibility option is enabled. Omit the installed case's project name,
measurements, master totals, node indexes/counts and correction recipe.

Do not describe a Core class selector as a helper capability or port its code
example as part of this documentation revision. Adding a maintained alternative
API procedure would need separate evidence against the relevant build. Keep all
existing adapter-specific instructions in `references/helper.md`, apart from
general optical guidance in `references/design.md`.

## Planned file changes

| File | Change |
| --- | --- |
| `skills/glyphs-mcp-small-caps/SKILL.md` | Broaden description and opening to create, continue, refine and audit. Add compact mode routing and default precedence. Preserve targeting, recovery, pilot approval, manual-edit protection and the stopping rule. Link to detailed procedures. |
| `skills/glyphs-mcp-small-caps/references/design.md` | Add per-set/master constraints, the six-step measurement/compensation procedure, targeted weight correction, risk-based pilot additions, interpolation review and a task-local completion template. Clarify naming guidance versus helper naming restrictions. |
| `skills/glyphs-mcp-small-caps/references/helper.md` | Document unchanged stages, formula assumptions, automatic attachment, existing-destination preservation, `.sc`/`.pc` restriction and measurement/verification limits. Keep build-specific adapter qualification here. |
| `skills/glyphs-mcp-small-caps/agents/openai.yaml` | Broaden the description and default prompt to the four workflows; retain the stable skill identifier and display title. |
| `catalog-repository/registry.json` and `macos-installer/GlyphsMCPInstaller/Resources/SkillsCatalog/registry.json` | Regenerate the small-cap description from canonical metadata through the existing synchronizer. |
| `plugins/glyphs-mcp/skills/glyphs-mcp-small-caps/` | Synchronize the revised instructions and metadata from canonical source. Executable helper bytes remain unchanged. |
| `plugins/glyphs-mcp/glyphs-mcp-agent.json` | Regenerate the instruction-package digest through the existing workflow, preserving current version fields. |

Keep `references/research.md` unchanged unless wording directly contradicts the
new workflow scope. Do not refresh its research date or claim renewed external
verification. No new reference file is needed. No managed-skill manifest, runtime,
helper, test-code, installer-code or release-version change is planned. Generated
catalog and digest updates are packaging metadata for the instruction revision.

## Implementation sequence

### 1. Establish the source baseline

Record the current scoped diff and helper hashes in source and packaged copies.
Recheck the installed/source discrepancy without modifying the installed copy.
Preserve unrelated work, particularly the already modified agent identity file.
Confirm the installed example contributes lessons only, not a new adapter.

### 2. Revise the main entry and routing metadata

Use this essential rule, with the precedence clarification above:

> Unless the designer specifies otherwise, petite capitals must use the font's
> x-height as their nominal flat alignment height in each master. Round and pointed
> forms may retain optically justified overshoot. Small-cap height is established
> independently; existing full capitals retain their cap height.

Route the four modes as follows:

- **Create:** fresh inspection, unsaved duplicate by default for edits, compact
  pilot, explicit designer approval before expansion.
- **Continue:** rebind the exact intended document, reinspect geometry and
  dependencies, reconcile recovery and recorded approvals, protect corrections,
  then perform the next incomplete step. Do not restart construction or request
  the same valid approval again. Changed scope or design constraints require
  renewed review of the affected direction.
- **Refine:** identify the approved drawing and exact glyph/master/region;
  distinguish a set-wide adjustment, a related-shape adjustment and a local one.
  Use bounded corrections with before/after evidence and recovery. After one
  unsuccessful automatic correction of the same issue, hand off to the designer.
- **Audit:** inspect the requested existing sets and report evidence, discrepancies
  and unfinished work; do not mutate or construct. Keep acceptance separate from
  technical verification.

Retain the pilot `H O E N S R V`. Add only needed controls for observed risks:
apertures, stacked counters, diagonals, extreme widths/proportions, accents or
extensions. Record replacements and missing evidence. A larger diagnostic set
does not authorize expansion without approval.

### 3. Add the design procedure and completion record

Implement all six proposed steps in `references/design.md`:

1. Inspect each master's x-height metric and lowercase `x`, plus relevant
   lowercase controls. Record and resolve material metric/drawing disagreement
   before editing; never change global metrics to accommodate derived caps.
2. Distinguish nominal alignment, base ink geometry, baseline, overshoot and
   extensions. Measure the base independently from accents and tails.
3. Establish the intended transform from measured source alignment and target.
   Account for offset expansion and baseline displacement. Link to the helper's
   actual formula and limits. Qualify detached copies before construction; the
   helper has no preview stage that exposes candidates for a review pause and
   `construct` attaches them after its internal checks.
4. Correct residual height locally when the overall drawing is approved. Move
   the appropriate terminal/serif/upper region together with its handles while
   preserving weight, curve quality, baseline and proportions. Reserve whole-form
   vertical scaling for a proportion change, with renewed weight review.
5. Evaluate stems, arms, crossbars, crowns, diagonals and serifs separately. Where
   suitable, strengthen weak horizontals inward while preserving outer alignment;
   inspect counters and apertures before accepting the change. No universal
   offset, ratio, stem target or clearance is prescribed.
6. After every compensation pass, reread native coordinates and remeasure
   alignment, overshoot, baseline, weight relationships, spacing and accents.
   Record the precision source, units, tolerance and reason for that tolerance.
   Bounds or control-point extrema alone do not establish curved ink extrema.
   Numerical tolerance and optical acceptance remain separate evidence.

Protect approved anchors and mark placement. Inspect affected composites after
base changes; explicitly record necessary anchor/mark adjustments. For initial
construction, explain that transformed base anchors and regenerated composite
anchors still require review.

For interpolation, inspect affected spans and relevant interior locations in the
actual designspace, including combinations of axes where applicable. Record
sample locations and increase sampling around problems; no fixed master count,
uniform sample count or continuous-interpolation guarantee. Retain deliberate
handling of excluded special layers.

Add a task-local record template with document binding, mode, scope, cap set,
master, reference/target alignment, chosen optical weight relationship, protected
corrections, measurements/tolerances, sampled locations and next action. Track
drawing, height, weight, spacing, accents, interpolation, feature behavior and
designer approval independently as pending, checked, accepted, unresolved or
not applicable, with supporting evidence. Record approval provenance and scope.
Use the existing `review` payload or a companion task report; no new top-level
helper fields or hidden font metadata. Compilation and exported shaping remain
separate evidence and retain their authorization boundaries.

### 4. Tighten helper documentation and synchronize

Cross-check claims against `_request`, `_settings`, `_base_layer`, `measurements`
and `run_caps` in [derive_caps.py](../../skills/glyphs-mcp-small-caps/scripts/derive_caps.py).
Make `.sc`/`.pc` an explicit helper restriction even for manually supplied
destinations. Preserve other naming conventions as inspection/design context,
without implying constructor support or automatic renaming.

State that explicit `height` remains required for each constructed set/master;
the agent supplies the resolved x-height default, not an automatic helper default.
Keep ordinary-master, pure-composite, mapping, precision and source-eligibility
restrictions. Document that `changesVerified` is not optical acceptance, and
`interpolationVerified` and `featureBehaviorVerified` are not established by this
helper. Missing source/guard evidence remains explicitly unavailable.

Keep interface examples clearly illustrative; do not turn their numbers into
design defaults or add font-specific recipes. After reviewing canonical changes,
run `bash scripts/sync_codex_plugin_skills.sh`. It synchronizes all managed skills
and catalog metadata, so inspect its complete diff against the initial state;
preserve unrelated edits and resolve unexpected changes without blanket resets.
Do not update global skills, caches or installed runtime components.

### 5. Validate and review acceptance scenarios

Run from the repository root:

```sh
python3 -B /Users/thierryc/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/glyphs-mcp-small-caps
python3 -B /Users/thierryc/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/glyphs-mcp/skills/glyphs-mcp-small-caps
bash scripts/sync_codex_plugin_skills.sh --check
python3 -B scripts/check_lean_package.py
```

Check relative links and heading fragments throughout the main skill and all
references, in both source and package. The lean checker alone does not validate
all reference-file links or fragments. Check scoped whitespace, helper byte
identity and the final changed-file list. Review every new capability statement
against the unchanged implementation. No new executable tests are needed for
this prose revision; these checks do not establish native design correctness.

| Scenario | Required instruction outcome |
| --- | --- |
| No height direction | Per-master x-height supplies petite nominal flat alignment; no arbitrary ratio or separate mandatory height question. |
| Explicit override or recorded approved height | Preserve the chosen height and record its provenance; no silent normalization. |
| Metric and lowercase drawing disagree | Identify and resolve the intended reference before editing; global metrics remain untouched. |
| Round, pointed, accented or descending form | Separate base alignment and overshoot from extensions; do not fit full bounds to nominal height. |
| Compensation alters height | Recheck actual geometry and correct alignment selectively while retaining approved weight. |
| Stems satisfactory, arms/serifs weak | Diagnose and correct the deficient region; preserve outer boundary when suitable and check counter clearance. |
| Existing manual corrections | Fresh inspection and bounded revision protect them; construction never overwrites destinations. |
| Existing glyph has incomplete masters | Report the gap and use a separately scoped completion route; do not promise helper regeneration. |
| Multiple masters/axes | Cover affected spans and relevant interior locations, densifying around issues; distinguish sampled checks from continuous proof. |
| Continue after pilot approval | Reuse recorded approval within its scope, reconcile changed state and resume the outstanding work. |
| Audit without prior guards, sources or helper-compatible names | Read-only inspection; state missing historical comparison or helper applicability without changing names. |
| Feature audit | Distinguish source review, compilation, exported shaping and designer acceptance. |
| Unavailable offset adapter or changed correspondence | Follow the documented qualification/handoff boundary; no invented helper capability. |

Acceptance requires generic design instructions, unchanged executable/helper
interfaces, synchronized package metadata, passing documentation checks and
manual review of the scenario matrix. No font edits, runtime installation,
restart, export, staging or commit are part of implementing this plan.

## Review-time validation evidence

These results describe the current baseline, not the future revised skill:

- Skill quick validator: passed.
- Managed skill synchronization check: passed for 14 skills.
- Lean package check: passed (14 skills, 22 public tools, both runtime architectures).
- Main skill/reference local Markdown link check: all 5 local links resolved;
  external URLs were not tested.
- Source/helper review: completed; no live Glyphs calls or native qualification run.

Implementation and instruction-level scenario acceptance are now complete; see
[validation results](validation.md) for evidence separate from this baseline.
