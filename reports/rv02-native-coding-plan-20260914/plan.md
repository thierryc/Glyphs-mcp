# RV02 — focused native-coding improvements

Status: proposed milestone; implementation and installation have not started.
Prepared 2026-09-14 against `build/milestone7/desktop`, HEAD `a833e599`.

## Outcome and scope

Make the native script workflow demonstrated in RV01 easier to complete correctly
on the first attempt. Address the obsolete OpenType route, native precision,
qualified Glyphs 4 API behavior and the incorrect glyph selector in the test
harness. Preserve the current seamless file-authoring/native-runner workflow.

Keep the seven MCP tools, five jobs, native operations and existing Undo/discard
mechanisms. This is primarily a skills and qualification milestone. It adds no
script execution tool, feature editor, topology engine, recovery system, watcher,
document model or private-version fallback. V1 and earlier reports stay unchanged.
Runtime changes are excluded from the core milestone; a better malformed-selector
error is a separately scoped optional follow-up.

Source evidence: [RV01 report](../rv01-realistic-20260914/report.md),
[judgment](../rv01-realistic-20260914/llm-judgment.md), task reports T01 and T04–T12,
and their preserved first-attempt and corrected artifacts. Native observations
apply to Glyphs 4.1 (4107); the implementation must record the host actually used
for qualification rather than assume every Glyphs 4 build behaves identically.

## 0. Freeze and establish the candidate

- Record the current source diff, configured skill trees and ownership records,
  packaged skill manifest, official corpus hashes, runtime identities and tool
  catalog. Preserve unrelated work; do not reset or stage it.
- Record RV01 as historical comparison evidence. Do not rewrite its failed first
  attempts, blocked OpenType route or unverified missing-glyph control.
- Use the same pinned Apache-2.0 Roboto Slab source and its three exact master IDs.
  Create fresh disposable copies for native trials and record their native
  post-load state, including import warnings and component-alignment decisions.
- Check any remaining RV01 UI cleanup when the Mac is available. Offline work
  does not depend on unlocking or opening a font.

Acceptance: baseline and candidate evidence are distinguishable, source hashes
are recorded, and all proposed edits have a narrow scope.

## 1. Repair OpenType routing and setup — high priority

Reintroduce `glyphs-mcp-opentype-features` into the current lean source and
`skills/manifest.json`, retaining that existing skill ID. Give it a compact
Glyphs 4 native-coding entry and one focused `references/native-features.md`.
Preserve its invocation policy; update display text and the prompt to describe
the actual native workflow and explicitly name `$glyphs-mcp-opentype-features`.

The reference will cover explicit font/artifact targeting, authored classes,
prefixes and features, automatic/disabled state, a bounded source diff, native
compilation diagnostics, export when authorized, and verification of the actual
binary behavior. Preserve existing feature order/source outside the requested
change. Do not advertise a complete multilingual or variable-feature audit from
the sampled tests. Keep script creation, native execution and public MCP calls
clearly identified. Existing job preview/discard guarantees do not cover these
scripts.

Add only a short intent route in `$glyphs`, development and scripting where
needed. Offline feature work needs no connection or document discovery; live
work retains the established target. Native runner processes do not inherit the
MCP bridge's live `document_id`. Use their explicit file/native context and never
substitute `Glyphs.font` for an independently targeted document without checking
that binding. Keep saved-source work distinct from dirty live-font work.

Use existing `AgentSkillBundleInstaller` behavior in
`macos-installer/GlyphsMCPInstaller/Core/ConfigPatchers.swift`:

- Matching installer-owned contents refresh with a verified backup.
- Matching current contents report `current` without a repeated installation.
- Modified or unowned contents report `preserved-conflict`, the exact path and
  the existing `Replace preserved skills (backup)` repair action.
- Explicit replacement backs up the old tree outside skill discovery, then
  replaces the same skill ID. Retire the obsolete instructions, not the skill ID.

The observed `~/.codex/skills/glyphs-mcp-opentype-features` has a legacy
`.glyphs-mcp-owner.json` but no entry in the current `.glyphs-mcp-skills.json`
hash ledger. Do not infer unchanged ownership from that marker. Use the existing
explicit replacement route during approved installation. No new migration or
ownership system is needed. Do not edit plugin caches or sweep other orphaned
skill families; report conflicting exposed copies separately.

Acceptance: OpenType intent selects a current native workflow; no executed path
requires retired typed-interface tools or `apiMajor == 2`. A fresh installation
includes the focused reference. Existing installations produce accurate
installed/current/conflict outcomes, with byte-exact replacement backups.

## 2. Add the native precision recipe — high priority

Add `skills/glyphs-mcp-development/references/native-precision.md`. Link it from
scripting and from development only where coordinate or path edits need it.
Keep the recipe in one place and reuse existing native operations.

The short recipe will show how to:

1. Resolve the intended glyphs and exact ordinary master IDs before any write.
   For an all-master request, validate all intended master layers first. Do not
   silently include backups, intermediate or alternate layers.
2. Explain that an integer grid can round native writes even when calculations
   produce fractional values. Preserve font grid settings.
3. Read each layer's `temporarilyDisableRounding` value, accounting for the
   observed callable getter, and use `setTemporarilyDisableRounding_` only around
   the bounded operation. Restore every previous flag in `finally`, including
   on exceptions and when the original flag was already true.
4. Verify exact requested coordinates after the write and restoration. For
   computed curve equivalence, declare numerical tolerances separately from
   exact coordinate, metadata and identity checks.
5. Record a failure or partial edit honestly. Flag restoration is not rollback.
   If the required native precision API is unavailable, stop that precision
   operation with an explicit explanation; do not silently round or change grid
   settings. Do not generalize an undocumented selector beyond tested hosts.

Native Undo remains the host's behavior. The recipe does not import private
bridge internals or reproduce its undo manager. Exact correspondence and useful
interpolation require task-specific evidence; additional nodes alone are not a
quality improvement.

Acceptance: RV01's +2.5 move and 102.5 midpoint succeed on the first candidate
attempt; precision-protected extrema and a corresponding split preserve the
verified curves. All intended masters are covered, previous flags are restored
on success and injected failure, and unrelated recorded data remain unchanged.

## 3. Add qualified Glyphs 4 API notes — medium priority

Add `skills/glyphs-mcp-development/references/glyphs4-api-notes.md`, linked from
the offline-documentation reference and native-feature reference. Label it as
project qualification evidence, with exact owners, tested host/build, route,
RV01 evidence links and the matching official source IDs. Keep installed notes
self-contained; repository evidence links are supplemental.

Cover four demonstrated issues:

- `GSInstance.generate`: lower camel case keywords such as `fontPath`,
  `autoHint`, `removeOverlap`, `useProductionNames` and `containers`. Describe the
  observed `None` result with a valid output file; check the actual new output,
  its identity and readability instead of treating the return value as proof.
- Native feature `automatic`/`disabled` flags: call an observed callable getter
  before interpreting its value. A bound method's truthiness is not the flag.
  This is a qualified native representation detail, not a fallback MCP workflow.
- `GSFont.compileFeatures`: inspect the success element and error in the
  observed result tuple; `(False, error)` is truthy as a Python tuple. Retain
  feature/glyph/line diagnostics and report unexpected result shapes explicitly.
- Separate source review, successful compilation, actual export and shaping
  evidence. Use feature-on/off examples and unaffected controls. A stale output
  file or successful process exit is not evidence of a successful new export.

Leave all pinned official corpus files, attribution and checksums intact. Use
focused links first; this milestone does not need another KDB search index or
retrieval mechanism. Preserve existing bounded offline search/get behavior.

Acceptance: the reviewed flags agree with native and source evidence, invalid
feature code is correctly identified, and an authorized disposable feature
addition compiles, exports and shapes as expected without the uppercase-keyword
or tuple-truthiness mistakes. The test feature remains a test artifact; do not
recommend shipping RV01's duplicate `ss20` design control.

## 4. Correct the agent/harness selector — small

Use `{"kind":"glyph","id":"o"}` in the follow-up harness and any newly
authored examples. The existing metadata reference already documents this
contract correctly, so avoid unnecessary rewrites. Keep archived RV01 artifacts
unchanged.

Repeat a valid read and a deliberately missing named glyph using `id`. Expect
`target_not_found` to identify the requested missing glyph. Keep the same valid
document ID, with no discovery or substitution. A stale document still produces
`document_not_found` and follows existing targeting guidance.

Optional later improvement: locally reject a missing, empty or non-string glyph
`id` with `invalid_request` and a concise example, analogous to existing layer
validation in `glyphs_adapter.py`. Do not accept `name` as a new alias or expand
the schema. This optional bridge change is not needed to close RV02; if pursued,
give it its own runtime fingerprint, contract tests and installed verification.

## 5. Qualification, installation and reporting

### Offline candidate checks

Use the existing lean development, skill routing, package and installer suites:
`test_simple_v2_development.py`, `test_simple_v2_skill_routing.py`,
`test_simple_v2_build.py`, relevant shared-package checks and the Swift managed
skill installation tests. Add meaningful cases for the new OpenType manifest
entry, legacy marker without ledger ownership, current/owned/modified installs,
conflict detection and verified backups. Avoid tests that merely enforce prose.

Validate frontmatter, reference links and invocation metadata. Exercise routing
for ordinary reads, offline feature coding, native feature debugging and generic
Python. Confirm that ordinary reads load no new coding references, known IDs are
reused, and missing private capabilities are explained accurately. Update only
relevant Starter routing if it actually lists these intents.

Generate mirrors with `scripts/sync_codex_plugin_skills.sh` and verify `--check`.
Build the candidate skill payload through existing packaging, preserving the
official corpus. Test it from a temporary installed copy with no repository or
v1 paths available. Pinpoint pre-existing unrelated suite failures separately.

### Targeted native qualification

Reuse RV01's independent native oracles and fresh Roboto Slab copies:

| Trial | Evidence required |
|---|---|
| T01 selector correction | Exact valid metadata; named missing glyph rejected without rediscovery; stale document remains distinct |
| T04–T06 precision | Fractional handle, exact midpoint, guarded removal; explicit three-master scope; failure restores flags |
| T07–T08 path precision | Native extrema and corresponding split; existing geometry/interpolation oracle; no unsupported generalization |
| T09 snippet iteration | Create/run/revise actual file through existing authoring and native runner; identify executed revision |
| T10–T12 OpenType | Correct source/flags; valid export and feature-on/off shaping; invalid compile diagnostics and corrected result |

Use exact checks for requested representable coordinates and unchanged data.
Retain RV01's predeclared 0.05-unit curve tolerance and stronger numerical
evidence where its oracle supports it. Check widths, anchors, components,
metadata, surviving object identities and native flags within the recorded
scope. Mark populated-hint behavior unverified unless a populated-hint fixture
is explicitly exercised. No test implicitly saves a user document.

Capture the first candidate attempt, mistakes and corrections. One complete
acceptance execution per affected scenario is sufficient for this targeted
follow-up. If making a timing improvement claim, separately run one warm-up and
five fresh-copy repetitions of the same defined workflow under recorded load;
do not substitute repeated scaffold commands or native callback timings for
complete agent sessions. Otherwise report descriptive timings with actual sample
counts and label the original RV01 comparison historical, not a matched trial.

### Install once and verify

After local qualification, use the existing skill installation path to deploy
the complete tested skill payload and perform the explicit backed-up replacement
of the obsolete OpenType folder. Preserve unrelated conflicts. Verify configured
skill hashes and resolved reference paths against the candidate; a report of a
preserved conflict is not successful routing qualification.

The core change needs no bridge/sidecar replacement or Glyphs relaunch. Verify
their running identities and seven-tool catalog remain unchanged. If the runtime
has changed independently, record it and avoid attributing that difference to
this skill milestone. Re-run a compact installed OpenType, precision and metadata
check through normal agent routes, then remove only owned test artifacts.

### Deliver and stop

Publish a separate RV02 report, structured assertions, timestamped action log,
artifact/skill fingerprints, installation and backup evidence, and native proofs.
Update the coverage index without rewriting RV01. Commit only RV02 changes after
reviewing the scoped diff; no release publication is part of this milestone.

Measure accuracy, first-attempt mistakes, calls, retries, discovery, reference
loads and installs. Use the RV01 tokenizer (`tiktoken 0.12.0`, `o200k_base`, literal
skill text and sorted compact JSON) for entry/reference/tool payload estimates.
Report actual usage separately if available. HTTP latency and directly measured
native time remain separate; this milestone makes no HTTP-tail optimization claim.

Assess skill routing, evidence clarity and workflow effort with observed examples.
Label an executing-agent judgment as self-assessment. A numerical score is not
the goal. Completion means the demonstrated mistakes are prevented, affected
tasks pass with honest limits, the installed instructions match the tested
payload, user data are preserved, and ordinary workflows gain no unnecessary
discovery, context loading, install attempts or runtime complexity.
