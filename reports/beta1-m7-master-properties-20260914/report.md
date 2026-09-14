# Gap 7 — native master properties

**Implemented, installed and qualified on September 14, 2026.** The current
private `2.0.0-beta.1` candidate reads explicitly requested master metrics,
italic angle and axis positions through `read_entities`. **942 lean regression
tests, 74 isolated native checks, 431 installed assertions and 50 delivery
checks passed.** This closes gap 7 only. Step 8 is paused for feedback.

The practical benefit: an agent can ask for a master's ascender and weight
position without writing a native script or guessing axis order. For example,
the synthetic master's stored ascender is returned as **812.375**, whereas the
Glyphs Python wrapper's `ascender` property returns **812**. The bridge uses the
qualified native default getter and preserves the fraction.

## Contract and implementation

Require negotiated `master.properties.v1`. The existing exact-master and
master-page selectors now support `ascender`, `capHeight`, `xHeight`, `descender`,
`italicAngle` and `axes`, alongside `id` and `name`. Unrequested fields are absent.
These are native master defaults, not layer-specific or export line metrics.
Reading `italicAngle` neither sets the angle nor slants outlines.

```json
{
  "document_id": "<retained connection-specific document ID>",
  "entities": [{"kind": "master", "id": "C7941642-FFB2-5D2E-B7FE-4A30A143BE40"}],
  "fields": ["id", "ascender", "italicAngle", "axes"]
}
```

The first synthetic master returns `ascender:812.375`, `italicAngle:0.0` and
three native-order axis items. The first is:

```json
{"index":0,"axisId":"a01","tag":"CSTM","name":"Custom","internalValue":0.125,"externalValue":0.625}
```

`axes` wraps the items with `total`, `returned` and `complete`. Internal and
external values are read independently from Glyphs; no mapping is inferred.
Native null positions remain null, with `complete:false` and exact `unavailable`
locations. Missing, unreadable or malformed required native evidence returns
`unsupported_read`; no invented zero or truncating fallback is used.

Limits are **32 axes per master and 256 master-axis items per request**, checked
before projection. The existing 100-target and 100-master page limits remain.
For nine masters with 32 axes, request eight masters, then follow the existing
cursor for the last master. An oversized request is rejected rather than clipped.
Pages remain fresh live reads, not an atomic snapshot.

The stateless `master_properties.py` helper reuses the existing master page and
native read hooks. The bridge, sidecar description, additive capability and
focused skill references are synchronized. The entry skill gained only a routing
row adjustment. Existing selection fields, jobs, targeting and Undo/discard code
are unchanged. Seven tools, five job kinds, interface revision 1 and bridge
protocol 1 are retained; all seven public input schemas match the baseline.
Older private builds need a coordinated installation update, not a fallback.

The helper extraction keeps every Python module below 500 lines. The bridge is
2,314 lines, a net increase of 79; its explicit budget was raised from 2,300 to
2,320. The module ceiling and total 6,000-line ceiling were retained; the current
protocol/bridge/sidecar total is 5,433. This is a small documented budget adjustment,
not a new editing, document or recovery architecture.

## Qualification and accuracy

| Gate | Result and evidence |
|---|---|
| Lean regression, packaging, routing and identity | **942 passed**; [final output](regressions-review-fix.txt). Deterministic package generation, size limits and skill mirrors are included. Documentation build also passed. |
| Isolated native source | **74 passed** in Glyphs 4.1 (4107); [checks](native-source.json.gz), [output](native-source-final.txt.gz). Fixed fixture generation reproduces byte-identical baselines. |
| Final installed public workflow | **431/431 assertions passed**, including 56 preservation assertions; [facts](native-facts.json.gz), [timestamped calls](calls.jsonl.gz). |
| Installation and configuration | **50/50 checks passed**; [verification](installed-verification.json.gz). Five component payloads and eleven source/package/mirror/installed skill trees agree. |

The native trials use a three-master/three-axis synthetic font, a nine-master/
32-axis bound fixture, and pinned open-source **Roboto Slab: 1,272 glyphs, three
masters, one axis**. [The manifest](fixtures.json) records exact expected values
and immutable source hashes; [Roboto provenance](../rv01-realistic-20260914/font-source/SOURCE.json)
is retained. All editor work uses fresh disposable copies. Native helpers prepare
fixtures and provide independent verification; they never fill in an MCP result.

Each fixture received its first attempt, one warm-up and five timed repetitions:
**21 complete final trials**. Checks cover duplicate master names, exact IDs,
fractional/negative metrics, zero/signed angles, custom and reordered axes,
differing internal/external positions, zero axes, native 33-axis rejection,
256-item acceptance and 288-item rejection, and mixed invalid selectors that
must not bypass the aggregate budget. A 100-slot scalar request is native-tested
using the same known master ID repeatedly; this is not a claim of testing 100
distinct native masters. Missing/unreadable/null API cases also have explicitly
separate small-double coverage.

Dirty changes are read fresh without saving. Background targeting, truly unsaved
copies, missing master IDs, invalid fields, closed/reopened document IDs,
pre-restart ID rejection, stale page rejection and recovery passed. Native object
identities and full available font evidence, selection, tabs, history/grouping
state and dirty state are compared before and after reads. This includes the
oracle's glyph/layer/path/node/component/anchor/hint/kerning metadata coverage;
it does not claim every possible third-party custom object was populated.

The two original saved fonts and unrelated disposable control were preserved.
Both original files have identical hashes, are open again and remain clean;
[final discovery](documents-final.json) confirms the original foreground font.
Temporary timing hooks were removed and all task fonts closed. The test loader
was cleared, Macro 1 reselected without executing it, and Scripting Window closed.
An accidentally pasted draft in the task-created Macro 4 was retained rather
than discarded; see the execution exceptions below. Autosave preferences were
not changed. No user font was saved or edited by the tests.

## Timing and context cost

The final run was **21:11:26–21:14:00 UTC**, about 154 seconds including native
setup, independent preservation proofs, controls and cleanup. Four documents
were open during every timed trial. An explicit fixture-settling phase took
2,001–2,007 ms per copy before discovery; it is setup time, not hidden in the
read measurements below. Opening and independent proof time are also excluded
from these HTTP task timings and included in full-run elapsed time.

All following times are milliseconds. Medians are computed per workflow; adding
medians does not necessarily give the median total. With five repetitions,
nearest-rank p95 equals the maximum; raw samples are retained in
[analysis](analysis.json.gz) and [facts](native-facts.json.gz).

| Five measured repetitions | Initial discovery median [range] | Known-target full read median [range; p95/max] | Discovery + full read median [range; p95/max] |
|---|---:|---:|---:|
| Three masters × three axes, one page | 31.65 [23.43–64.46] | 38.56 [29.75–53.83; 53.83] | 81.56 [53.18–96.21; 96.21] |
| Nine masters × 32 axes, two pages | 38.08 [28.97–49.57] | 67.17 [58.37–79.45; 79.45] | 109.68 [87.34–117.53; 117.53] |
| Roboto Slab, one page | 46.21 [32.72–61.11] | 48.70 [25.90–122.67; 122.67] | 81.41 [73.37–183.78; 183.78] |

First/warm-up full reads were respectively **75.14/61.19**, **94.21/63.06**
and **433.01/39.76 ms**. Roboto's first-attempt tail is retained, not excluded
from all-call statistics. A subsequent compact `id`/`italicAngle` read required
one call without discovery: **29.75 ms median**, 22.40–57.60 ms range,
p95 50.31 ms across 21 trials.

| Probe scope | n | Median | Range | p95 | Maximum |
|---|---:|---:|---:|---:|---:|
| Native read callback execution | 88 | 9.39 | 1.04–31.69 | **26.86** | **31.69** |
| Native execution, all callbacks | 114 | 11.82 | 0.28–42.14 | 28.85 | 42.14 |
| Queue waiting, read callbacks | 88 | 2.56 | 2.32–416.80 | 73.15 | 416.80 |
| Queue waiting, all callbacks | 114 | 2.62 | 2.32–603.93 | 226.55 | 603.93 |
| HTTP round trip, all calls | 114 | 36.86 | 19.53–657.35 | 271.09 | 657.35 |
| Native read callback, two-second post-change probe | 16 | 9.54 | 2.59–28.05 | 28.05 | 28.05 |

Native callbacks pass p95 <50 ms and maximum <200 ms. HTTP is not native
execution time; queue/transport tails remain separate. These bounded callback
samples are not an independent high-frequency UI heartbeat. Load averages were
45.41/32.59/26.80 initially and 33.49/34.29/28.59 finally on an Apple M1 Max
(10 CPUs, 32 GiB; [hardware](hardware.txt)). Background load was high and not controlled.
The detached alternating-order calibration used one warm-up plus 15 pairs:
median measured wrapper/clock overhead **0.224 ms**, without subtracting this
noisy estimate from reported times. See [calibration](probe-overhead.json).

Tokens use the established **tiktoken 0.12.0, o200k_base**, compact sorted JSON
with literal Unicode: `{name,arguments}` plus one parsed response body. Actual
billed usage and a reliable complete UI-action count were unavailable.

| Payload | Samples | Estimated token median [range] |
|---|---:|---:|
| Three-master full read | 5 | 660 [654–661] |
| Nine-master/32-axis complete inventory, two calls | 5 | 11,154 [11,139–11,164] |
| Roboto Slab full master read | 5 | 466 [464–472] |
| Compact exact ID/italic-angle read | 21 | 155 [148–158] |
| Document discovery, separately counted | 25 | 315 [298–320] |

The entry skill is 988 tokens; focused master guidance is 1,223, loaded only for
this task. The `read_entities` description grew from 1,149 to 1,277 tokens
(+128). Optional axes are useful but visibly expensive at the maximum: ask for
the required scalars when positions are irrelevant. The normal timed sequence
is discovery → full read → compact read, with 3 calls for small/Roboto or 4 for
the two-page bound fixture. Its measured costs (five repetitions) are:

| Complete discovery → full read → compact read sequence | HTTP median [range; p95/max], ms | Token median [range] |
|---|---:|---:|
| Small | 125.11 [96.78–146.51; 146.51] | 1,133 [1,115–1,136] |
| Bound | 146.51 [114.86–149.89; 149.89] | 11,627 [11,606–11,641] |
| Roboto Slab | 115.14 [105.81–217.81; 217.81] | 930 [924–948] |

These totals include discovery. The retained ID avoids a redundant discovery before
each compact read. Total final-harness calls: **1 status, 25 discovery, 88 reads**,
plus initialization and catalog retrieval. Twelve read errors were deliberate
negative controls; the final run needed no unexpected retry. Final connector
status/discovery and delivery checks ran outside the timed harness.

## Exceptions retained, not counted as passes

- Fixture development initially attempted to change master IDs before layer
  lookup, causing an isolated native range exception. Retaining the fixture's
  fixed master IDs corrected the setup. Format-3 axis IDs were also remapped by
  Glyphs on reload; the generator now uses the stable native IDs and unique axis
  names. Both failed source attempts are preserved.
- The first installed harness attempt stopped because the verification helper
  assumed a font metric collection was populated. The oracle now handles native
  null collections explicitly; this was not an MCP result repair.
- A later run caught a dirty-indicator transition while opening the synthetic
  32-axis fixture. Two independent **zero-MCP-call** controls also observed it
  before any oracle traversal. Final trials record this transition during setup,
  then require exact preservation during reads. The original failure remains
  in [the second run](native-facts-second.json.gz). This isolates it from the new
  MCP reads; it does not establish whether Glyphs core or another loaded plugin
  is responsible. No clean-state forcing or Undo workaround was added.
- The third run completed all 21 trials but stopped at an invalid unsaved-font
  setup assumption: clearing a document URL did not remove the font's source
  path. A real native font copy, discovered publicly with `path:null`, fixed the
  fixture. The interrupted run and unsaved probes remain separate artifacts.
- A Macro Panel paste inserted unrelated draft text and raised SyntaxError
  before execution. The draft remains in Macro 4. The subsequent run used a
  visibly verified loader in a separate task macro; cleanup used keyboard deletion
  after accessibility `setValue` did not persist. No user macro was run.
- Final code review found that a mixed invalid selector could bypass the
  aggregate axis preflight before eventual rejection. The correction counts
  every master selector before projection; dedicated unit and final native
  regressions passed. This justified **a second runtime installation** and the
  complete final rerun. The first candidate's identities/results are preserved
  under `candidate-first/`; no intermediate result is represented as final.
- The first sandboxed suite had two localhost-listener permission failures.
  The authorized rerun passed. Unrelated user-font alignment dialogs were left
  for the user to resolve; no automatic alignment choice was made.

## Running identity and delivery

The final host is **com.GeorgSeifert.Glyphs4, 4.1 (4107)**. Product/release remains
`2.0.0` / `2.0.0-beta.1`, installer build 43. The new capability is negotiated on
the configured endpoint. These are initialization-time file fingerprints, not
a continuous assertion that disk and loaded objects can never diverge.

- Sidecar: `2.0.0-beta.1+0d1590b10c67`, SHA-256
  `0d1590b10c67cd7eebbc4d3ea93f5f91eec51d9e80285f2d8b65d0c4398450a3`.
- Bridge: `2.0.0-beta.1+77bec730360c`, SHA-256
  `77bec730360ce043f184dcdc958fbad5519c7858fc06994bad292abf4ea01138`.

[Final status](runtime-final.json), [candidate manifest](candidate-manifest.json)
and [installed verification](installed-verification.json.gz) agree. The existing
skill installer updated two owned skills, found nine current, and reported zero
conflicts. No second skill installation was needed for the final bridge-only
correction. Runtime dependencies and Curve Inspector are unchanged; Reference
Inspector's payload fingerprint changes because it includes the shared additive
read-capability module, not because its editing code changed.

## Agent judgment and next step

| Area | Judgment | Evidence |
|---|---:|---|
| Discovery and targeting | 4/5 | Public master IDs, repeat reads without rediscovery, explicit stale-ID recovery; discovery/queue tails still exist. |
| Skill accuracy | 4/5 | Correct fractional native defaults, internal/external distinction, missing-capability update guidance and focused references. The full tool description is growing. |
| Evidence clarity | 4/5 | Requested fields, exact axis IDs and explicit completeness; native and HTTP costs remain separate. |
| Recovery guidance | 4/5 | Exact missing-ID, stale-page, unsupported-field and over-budget cases have actionable outcomes. |
| End-user workflow effort | 4/5 | One known-ID read supplies metrics; axes are optional. No native coding or new tool is required. |
| Qualification and delivery effort | 3/5 | Fixture/oracle corrections, one paste failure, user-dialog wait and a justified second installation caused substantial friction. Final correctness does not erase it. |

The historical v1 audit showed master metrics, italic angle and axis-related
values already available. This follow-up restores the corresponding useful read
outcome in lean v2, with explicit native axis identity and fractional evidence.
**V1 was neither modified nor freshly benchmarked**, so no comparative speed,
token superiority or new v1 failure is claimed. Familiarity from prior tests and
the fixed v2-first development process also limit comparative judgment.

No further gap-7 runtime fix is justified by these passing controls. Keep HTTP
tails and the host's opening dirty-state behavior separate. **Next, after user
feedback: step 8**, add requested production name, script and layer count.
Example: “Check these three glyphs before export,” without fetching outlines.
Steps 8–14 and P-series advancement have not started.

[Source preservation](source-preservation.json) compares the 5,388 pre-existing
source/report files: only the 16 intended existing files changed, none disappeared,
and all 5,372 others retained their hashes. The new step-7 helper, tests, evidence
and accepted gaps plan are recorded alongside those scoped edits. No release was
published and no v1 implementation or earlier report was rewritten.
