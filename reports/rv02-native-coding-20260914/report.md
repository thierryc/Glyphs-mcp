# RV02 — focused native-coding improvements

**Implemented, installed and qualified on Glyphs 4.1 (4107).** The obsolete
configured OpenType skill has been replaced with current native-coding guidance.
The precision and API examples now pass the affected Roboto Slab tasks without
RV01's coordinate-rounding, export-keyword or compiler-tuple mistakes.

The follow-up records **150 passed checks, zero failed and one unverified**:
populated-hint preservation, because the edited layers have zero hints.
[Assertions](assertions.json) separate these checks from
[workflow judgment](judgment.md). This is a targeted follow-up using existing
task actions and independent oracles, not a blinded new benchmark or five full
agent sessions per task. RV01 remains unchanged.

## What changed

- Added the existing `glyphs-mcp-opentype-features` ID to the lean managed
  payload, with a compact entry and focused native-feature reference.
  Its invocation policy remains enabled. Source, compilation, export and shaping
  are explicitly separate evidence.
- Added one native precision reference: exact ordinary master scope, temporary
  rounding protection, restoration of previous flags on success/failure and exact
  read-back. The existing native operations and Undo mechanisms are unchanged.
- Added project-qualified Glyphs 4 notes for lower camel case export arguments,
  callable feature flags, compiler result tuples and actual output verification.
  All 1,154 files of the pinned official corpus retain their hashes.
- Added small intent links to the entry, development, scripting and both Starter
  sources. The longer references load only for the corresponding work.
- Corrected the follow-up harness to use glyph selector `id`. No bridge error
  wording or schema was changed.

There is no new MCP tool, Python execution endpoint, feature editor, topology
engine or recovery framework. Scripts are authored with file tools and executed
by the existing Glyphs native CLI. They do not inherit MCP job discard guarantees
or a bridge document ID. Dirty live-font work remains distinct from loading a
saved source in an isolated runner.

## Installation and runtime

One invocation of a thin wrapper around the **existing AgentSkillBundleInstaller**
installed four changed skills and reported seven current. The wrapper made no
runtime installation call. It preflighted conflicts and allowed the reviewed
OpenType folder as the only conflicting replacement; unrelated legacy skills
would stop the wrapper before mutation.

The old OpenType folder had a legacy ownership marker but no current hash-ledger
entry. The existing explicit replacement path made a byte-exact backup outside
skill discovery, then installed the new tree. [Receipt](installation.json),
[installation log](installation.log) and [backup proof](backup-evidence.json).
All eleven configured skill identities match the tested payload.

The configured native-only skill receives the installer's existing generic
conflict/path/backup action; the older retired-tool heuristic is specific to
MCP-read guidance. No installer behavior was expanded just to produce a different
message. The new regression verifies this actual ownership and replacement path.

Running identities remain:

| Component | Runtime ID |
|---|---|
| Sidecar | `2.0.0-beta.1+82daa62ac227` |
| Bridge | `2.0.0-beta.1+8b74a8d27ae4` |
| Host | `com.GeorgSeifert.Glyphs4`, 4.1 (4107) |

Product Beta 1, installer build 43, protocol/interface 1, seven tools and five
jobs are unchanged. Full fingerprints are in [final status](runtime-final.json)
and the [tool catalog](catalog.json). No Glyphs relaunch or release publication
was needed. This task's preloaded catalog also exposes older repository and
plugin-cache variants; those separate locations were not silently edited.
Qualification uses the updated `~/.codex/skills` paths and current lean package.

## Qualification results

The baseline is the same pinned Apache-2.0 Roboto Slab source: **1,272 glyphs,
three masters**, source SHA-256
`98bd0e35d9267ad101270727f18bb58b17b629160ccdf3d8a60f9a99d526e845`.
Fresh disposable file copies were used for the native actions. The GUI copy
showed the same older-producer notice and twenty alignment issues as RV01;
existing Keep Position choices were retained. Each route is compared against its
own native post-load state; no general GUI/CLI import equivalence is claimed.

| Check | Result |
|---|---|
| Glyph selector and recovery | Three public metadata rows match the independent native oracle. `missing.rv02` is named in `target_not_found`. The next read reuses the same ID; closing the copy produces `document_not_found`. |
| T04: handle move | Exact +2.5 in all three masters on the first candidate attempt; other recorded data and objects retained. |
| T05/T06: midpoint and guarded removal | Exact midpoints, including Black's 102.5 coordinate. Removal recovers the original polygons. A perturbed last-master seed rejects before partial removal. |
| T07: native extrema | Six contours have full original-segment coverage. Maximum numerical control-polygon deviation bound is **1.422e-12 units**, below the predeclared 0.05 tolerance. |
| T08: corresponding cubic split | Exact intended topology; original objects retained. Native Light/Medium/Bold interpolation error is at most **5.085e-13 units** in the existing polynomial check. |
| Precision failure | An injected exception restores mixed original flags `[false, true, false]`; native data and objects remain exact. This proves this no-write failure control, not arbitrary-script rollback. |
| T09: snippet revision | Scaffolder and static validation pass. Actual revision 1 and changed revision 2 files execute on separate copies; twelve rows and added anchor names are exact. Invalid names, masters and oversized scope reject. |
| T10: OpenType review | All seventeen feature source/flag records, classes and prefixes match the independent source parse; sixteen features are automatic. |
| T11: export | The documented lower camel case invocation writes a readable 135,832-byte Regular TTF. Return is still `None`; actual output and eleven shaping cases pass. |
| T12: compiler diagnostics | Failure tuple rejects the missing glyph with feature and line information. The corrected tuple succeeds. |
| Installed smoke test | The installed precision and API code blocks pass exact coordinates, flag restoration, object/collateral preservation and invalid/corrected compilation. |

The feature-on/off test deliberately duplicates existing ss01 behavior in ss20;
it is a disposable control, not a recommendation to ship that feature. The
midpoint and extrema tests establish precision/preservation, not an aesthetic
improvement from adding more points.

Local checks: **118 Python tests passed, one optional Copilot CLI check skipped**.
After isolating the final documentation/catalog integration, the affected package
subset passed again (15 tests, same skip). Swift ran 123 distinct installer tests:
122 initially passed; the new test's overly specific diagnostic expectation was
corrected and its final reruns passed. The installer already supplied the required
path and repair action. No production installer change was needed.

The first Python integration run exposed the new skill missing from the public
skill inventory and a hard-coded skill count. The inventory is updated; that
count check now verifies uniqueness while the existing mirror test verifies all
manifest entries. First-run logs are retained.

Skill metadata/links validate, both Starter sources agree, packaged mirrors
match, and isolated offline search/get works from the candidate and installed
skill copies. The native precision/feature examples were exercised directly;
test doubles cover unavailable APIs and restoration attempts after one setter
fails. They do not substitute for native repair evidence.

## Costs and limitations

[Measurements](measurements.json) use RV01's `tiktoken 0.12.0 / o200k_base`,
literal text and sorted compact JSON. These are payload estimates, not billed
usage or total conversation tokens.

| Entry skill | Before | After |
|---|---:|---:|
| glyphs | 817 | 843 |
| development | 774 | 814 |
| scripting | 428 | 477 |
| OpenType | 425, obsolete | 240, current |

Optional precision: **580 tokens**. Native-feature workflow: **558**. Qualified
API notes: **691**. A fresh OpenType entry plus both relevant references is 1,489
tokens before task-specific documentation and tool responses. These references
buy missing correctness evidence; the old blocked 425-token skill is not an
equivalent successful-workflow cost. No overall token-saving claim is made.

Six instrumented public calls include one discovery and four heterogeneous
valid/missing/stale reads. Two additional connector status calls are recorded
separately. Payload totals for those six calls are 191 request and 1,329 response
tokens. One same-ID continuation follows the expected missing-glyph control;
there are no MCP retries or replacement-font substitutions.

Discovery was 24.09 ms and the first metadata read 29.70 ms: **53.79 ms combined**.
The four different read requests have median **22.07 ms**, range
**13.80–37.99 ms**, interpolated p95 **36.74 ms**, n=4. This is descriptive HTTP
latency, not a matched repeated-workflow benchmark or a responsiveness probe.
RV01 used different targets, response sizes and load, so this is not evidence of
a latency improvement. No main-queue p95 or maximum claim is made.

Direct isolated native outline actions took 1.06–5.07 ms; the deliberate rejection
took 0.65 ms. Native review was 0.31 ms, feature compilation tasks about 70.96 ms,
and export 548.45 ms; each phase has **n=1**. These exclude process startup, source
load and independent verification. Eight native CLI invocations include the
separate proof/installed checks; they are not eight complete coding sessions.
Host load changed substantially, and some qualification work overlapped.

The GUI path entry required retries and one clipboard timeout before a short
verified path worked. Those UI actions are separate from MCP timing. The action
log records the detour; it does not justify adding a script execution tool.

## Preservation and remaining scope

All protected source/user-file hashes, Dactylotype's recorded file hashes,
unrelated configured skills, runtime sources and frozen v1 sources are unchanged.
Recorded native widths, metrics, anchors, components, grid/rounding state and
surviving node metadata passed their scoped checks. Populated-hint preservation
remains unverified. Unrelated worktree modifications are preserved.

The GUI copy is closed without saving. The protected MCP Selection Inspection
document is restored without an Edited indicator; RV01's temporary script entry
is removed after Scripts refresh. This completes RV01's previously pending UI
cleanup. No new Glyphs crash report was found. Normal autosaving was not changed.

The optional malformed-selector error improvement remains deferred. Broader
private skill families, plugin caches, v1, HTTP tails and dirty-state/Undo changes
remain outside RV02. No additional runtime action is justified by these results.
