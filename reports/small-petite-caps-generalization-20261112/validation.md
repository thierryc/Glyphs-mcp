# Small- and petite-cap documentation implementation

Completed 2026-11-12 against the [reviewed plan](plan.md). The canonical skill and
packaged copy now describe create, continue, refine and audit workflows, per-master
petite x-height defaults, selective compensation, protected manual corrections and
separate technical/design acceptance. The helper interface and executable files
are unchanged.

## Delivered scope

- Updated `SKILL.md`, `references/design.md`, `references/helper.md` and
  `agents/openai.yaml` under `skills/glyphs-mcp-small-caps/`.
- Synchronized their four packaged counterparts using
  `bash scripts/sync_codex_plugin_skills.sh`.
- Regenerated the two skill catalogs and agent instruction digest through that
  workflow. Exactly 11 existing files changed against the pre-task content
  baseline, all within the planned documentation/metadata scope.
- Kept the dated research reference, manifests, version fields, other packaged
  skills, installed skill directory and captured unrelated work unchanged.
- Added this implementation evidence and updated the plan's completion status.

The helper SHA-256 before and after, for both source and packaged copies, is:

```text
5c1b44bbe1f5ac7a48d0f144a623759994d767c4b5bacdd462eb9fc70a733f66
```

The already modified agent identity file retained every pre-task field except
`skillsDigest`, which was regenerated for the revised instructions.

## Validation results

All commands below completed with exit code 0:

```sh
python3 -B /Users/thierryc/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/glyphs-mcp-small-caps
python3 -B /Users/thierryc/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/glyphs-mcp/skills/glyphs-mcp-small-caps
bash scripts/sync_codex_plugin_skills.sh --check
python3 -B scripts/check_lean_package.py
```

| Check | Result |
| --- | --- |
| Canonical and packaged skill validators | Both reported `Skill is valid!`. |
| Synchronization | Verified 14 skill display titles and 14 synchronized skills. |
| Lean package | Passed: 14 skills, 22 public tools, arm64 and x86_64 runtime provenance. |
| Local Markdown links and heading fragments | All 10 per copy resolved, across the main skill and all references. |
| Scoped `git diff --check` | Passed for all 11 changed documentation/metadata files. |
| Baseline content hashes | Only the 11 planned existing files changed; helper, research, manifests, installed skill and captured unrelated files preserved. |
| Helper consistency review | Checked stages, suffixes, settings, transform, preservation, attachment, measurements and verification flags against implementation. |

## Scenario review

These are instruction-level acceptance results, not native font test results.
Section names refer to the revised canonical skill and its references; packaged
instructions are identical.

| Scenario | Result and instruction evidence |
| --- | --- |
| No height direction | Pass: main skill's Establish the brief supplies per-master x-height for petite flat alignment; helper requires the agent to pass explicit height. |
| Explicit override or recorded approved height | Pass: main skill and Design constraints preserve the approved height and record decision provenance. |
| Metric and drawing disagree | Pass: compensation step 1 requires resolution before editing and preserves font-wide metrics. |
| Round, pointed, accented or descending forms | Pass: the default preserves justified overshoot; compensation step 2 and helper measurement limits separate base geometry from extensions and full bounds. |
| Compensation changes height | Pass: steps 3, 4 and 6 require actual measurement and selective correction without discarding approved weight. |
| Weak arms/serifs with satisfactory stems | Pass: step 5 assesses regions separately, allows inward thickening and requires clearance/aperture checks. |
| Existing manually refined caps | Pass: Continue/Refine, protected anchors and fresh inspection preserve corrections; construct never regenerates destinations. |
| Existing glyph with incomplete masters | Pass: main skill and helper explicitly preserve it and require separately scoped completion. |
| Multiple masters/axes | Pass: Review by shape and use covers affected spans and interior axis combinations, records samples and increases sampling near problems. |
| Continue after pilot approval | Pass: workflow routing and completion record reuse valid approval within scope while requiring review of changed direction/scope. |
| Audit without guards, sources or compatible suffixes | Pass: audit stays read-only, establishes a fresh baseline and routes to ordinary reads without renaming or fabricating evidence. |
| Feature audit | Pass: source review, compilation, exported shaping and designer approval remain separate evidence with authorization boundaries. |
| Offset unavailable or correspondence changes | Pass: helper retains exact-build qualification, structural-check limits and UI/designer handoff; no additional adapter is claimed. |

The completion record covers drawing, height, weight, spacing, accents,
interpolation, feature behavior and designer approval independently. The revision
adds no font-specific names, measurements, master counts, node indexes or correction
recipes. Existing interface examples remain explicitly illustrative, and the
research assessment retains its original date.

No native qualification, live Glyphs test, font edit, compilation, export,
installation or runtime restart was performed. External research URLs were not
revalidated. These documentation checks establish instruction/package consistency,
not optical acceptance or live-runtime behavior. No files were staged or committed.
