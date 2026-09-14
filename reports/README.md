# Lean v2 qualification records

Latest full native-coding qualification: **RV02, September 14, 2026**, committed in
`5666e289`. This is the private `2.0.0-beta.1` candidate, installer build 43,
tested in Glyphs 4.1 (4107). These records are evidence from specific runs;
they do not establish public-release readiness or the identity of a later process.

The subsequent [v1 → v2 feature and intent audit](v1-v2-feature-audit-20260914/report.md)
maps all 87 active v1 tools, distinguishes deliberate reductions from unresolved
workflow gaps, and identifies incompatible installed skills plus separate,
unintegrated master-compatibility work. It is a review, not a new native benchmark.

[The gap-fix implementation plan](beta1-gap-fixes-plan-20260914/plan.md) starts
with six high-priority steps. Each has a test gate and a short explanation of
the next fix; the plan itself does not claim implementation or qualification.

[H1 skill cleanup](beta1-h1-skills-20260914/report.md) is implemented and installed:
seven obsolete private instruction folders archived with exact backups, eleven
current managed skills verified, 130 installer and 46 Python tests passed. The
unchanged Starter wording assertion remains logged; the full desktop suite is
not claimed clean at the H1 gate; H2 resolves that assertion below. Runtime
identities were unchanged during H1.

[H2 setup/identity correction](beta1-h2-setup-20260914/report.md) aligns current
migration, release and skill guidance, installs the updated release skill, and
resolves the Starter assertion noted in H1. All **179 macOS** and **70 focused
Python** tests passed (one optional Python skip); the documentation build passed.
Desktop labels were corrected in source but the app was not reinstalled during
H2; runtime identities were unchanged at that gate.

[H3 compact context](beta1-h3-context-20260914/report.md) is implemented, installed
and qualified in Glyphs 4.1 (4107): native current-font evidence, toolbar master
and bounded selected glyph names through the seven-tool interface. All 649 lean
regressions, 133 isolated native selection checks and 102 distinct installed
native checks passed after two documented harness corrections. Median context
HTTP reads were 23/26 ms for small/bounded selections; queue tails remain separate.

[H4 bounded glyph discovery](beta1-h4-glyph-discovery-20260914/report.md) is installed
and qualified: native names in pages of up to 100, explicit coverage and stale-cursor
handling through `read_entities`. All **713 lean**, **38 isolated native** and
**616 installed native** checks passed, including a 1,272-glyph Roboto Slab inventory.
Native callback p95/max were 21.35/40.39 ms; document-discovery and queue tails remain
separate.

[H5 layer discovery](beta1-h5-layer-discovery-20260914/report.md) is implemented,
installed and functionally qualified: exact native layer IDs, associations and
requested classification flags in bounded pages. **796 lean**, **164 isolated native**
and **302 installed native** checks passed; 54 follow-up checks also passed.
One original callback exceeded the 200 ms maximum (339 ms); it did not recur in
21 focused reads. The original timing exception remains recorded.

[H6 kerning discovery](beta1-h6-kerning-discovery-20260914/report.md) is implemented,
installed and qualified: native group/key fields and bounded stored-pair pages in
LTR/RTL/vertical through the same seven tools. **875 unique lean cases**,
**155 isolated native checks** and **1,087 installed assertions** passed across
the recorded gates. One live harness-attribution failure was corrected and
preserved. Native callback p95/max were **24.78/64.35 ms**; HTTP/queue tails
remain separate. All eleven skills and both running component hashes match the
candidate. The next master-metrics/axis step is paused for feedback.

## Current result

[RV02 native-coding follow-up](rv02-native-coding-20260914/report.md) implemented,
installed and verified eleven managed skills, including current OpenType routing,
native precision guidance and qualified Glyphs 4 API notes. It records 150 passed
checks, zero failed and one unverified populated-hint case. The official offline
documentation corpus is unchanged. [Agent assessment](rv02-native-coding-20260914/judgment.md)
and [execution log](rv02-native-coding-20260914/action-log.md) distinguish measured
results from judgment and first-attempt friction.

Scripts are written with file tools and run through native Glyphs routes. The
MCP interface remains seven tools and five jobs; RV02 adds no script-execution
or feature-editing MCP tool and makes no latency improvement claim.

RV02 recorded runtime identities were sidecar `2.0.0-beta.1+82daa62ac227` and
bridge `2.0.0-beta.1+8b74a8d27ae4`. Full fingerprints, release metadata and host
identity are in [RV02 status evidence](rv02-native-coding-20260914/runtime-final.json).
The [installation receipt](rv02-native-coding-20260914/installation.json) and
[backup proof](rv02-native-coding-20260914/backup-evidence.json) document the skill
update; the runtime was unchanged during that update.

## Report index

| Record | Scope and later status |
|---|---|
| [H6](beta1-h6-kerning-discovery-20260914/report.md) | Stored kerning discovery; installed and qualified, next step paused. |
| [RV02](rv02-native-coding-20260914/report.md) | Latest focused native-coding implementation and installed qualification. |
| [RV02 plan](rv02-native-coding-plan-20260914/plan.md) | Accepted scope and acceptance criteria. |
| [RV01](rv01-realistic-20260914/report.md) | Twelve realistic Roboto Slab tasks. RV02 addresses its skill/API findings and completes its pending UI cleanup. |
| [Native grouping correction](dirty-grouping-20260914/report.md) | Minimal existing-hook change. Its pending installation/UI checks were subsequently completed in RV01 and confirmed in RV02. |
| [Dirty-indicator investigation](dirty-indicator-20260914/report.md) | Native data restoration versus document dirty-state behavior; historical observations retained. |
| [HTTP route correction](http-route-fix-20260914/report.md) | Serve the configured endpoint directly. This does not resolve all HTTP/queue tails. |
| [P13 improvement](p13-curvature-improvements-20260913/report.md) | Curvature display and realistic-font qualification. |
| [P13 paired baseline](p13-curvature-display-20260913/report.md) | MCP versus native companion/UI access, including historical v1 results. |
| [P12 final checks](p12-final-checks-20260913/report.md) | Completes the outstanding slant controls; retains derived-bounds and crash limitations. |
| [Crash guidance](crash-guidance-20260913/report.md) | Bounded recovery instructions, with permission required before temporarily pausing autosaving. |

## Remaining limits

- Populated-hint preservation is unverified in RV02; its edited layers had no hints.
- HTTP/queue latency tails and the earlier autosave crashes remain separate
  investigations. Successful bounded runs do not establish a crash root cause.
- Native Redo→Undo dirty-state behavior is accepted as Glyphs parity. Exact
  restoration does not imply every history path clears the document indicator.
- Selection Lens label/position polish and clearer malformed-selector wording
  remain deferred. Neither requires a new MCP tool.
- RV02 does not remeasure v1 or replace the earlier paired benchmark results.

## Evidence and maintenance

Preserve earlier reports and their measurements. Each `coverage-index.md` is a
historical snapshot from the original benchmark workspace; its relative links
may refer to that workspace. Use the direct links above for the committed records
in this checkout. Do not mistake a historical pending status for the latest result.

RV02's [evidence manifest](rv02-native-coding-20260914/evidence-manifest.json)
records the archive checksum and each member's checksum. Keep the archive,
manifests, native proofs and preserved user-font copies. The build directory also
contains evidence and source worktrees; cleanup must use inspected generated
outputs, never a blanket removal of `build/`.
