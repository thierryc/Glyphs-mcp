# H6 — discover native kerning groups and stored pairs

**Implemented, installed and qualified** in Glyphs **4.1 (4107)** on the private
`2.0.0-beta.1`, installer build 43. Seven tools, five jobs and protocol revision 1
remain unchanged. No v1 implementation or native editing/Undo hook was changed.

The agent can now ask “Which kerning groups does A use?” or “Show the stored
pairs in this master” without guessing keys, saving the font, writing a script
or preparing a collision-repair job. This closes H6's agreed group/key and pair
discovery scope. It does not add an effective-kerning engine or reverse group
membership index.

## Requests and results

Request native group names and lookup keys only when needed:

```json
{"document_id":"doc_…","entities":[{"kind":"glyph","id":"A"}],"fields":["leftKerningGroup","rightKerningGroup","leftKerningKey","rightKerningKey"]}
```

`kerning.groups.v1` advertises all eight left/right/top/bottom group/key fields.
For fixture A, left/right groups are `leftA`/`rightA`, while keys are
`@MMK_R_leftA`/`@MMK_L_rightA`. Ungrouped keys return the glyph name. These native
lookup inputs differ from the raw glyph IDs used inside storage.

`kerning.pairs.v1` advertises one master/direction-scoped page:

```json
{"document_id":"doc_…","entities":[{"kind":"kerning_pairs","master":"C7941642-FFB2-5D2E-B7FE-4A30A143BE40","direction":"LTR","limit":100}],"fields":["left","right","value"]}
```

An item can be:

```json
{"left":{"key":"@MMK_L_rightA","glyph":null,"kind":"group"},"right":{"key":"@MMK_R_V","glyph":null,"kind":"group"},"value":-45.25}
```

Each requested side preserves its raw key and distinguishes group, resolved glyph
and unresolved ID. Only requested fields are projected. Zero remains stored zero;
absent pairs are omitted. Existing explicit-value reads continue to return null
for exact absence. LTR, RTL and vertical tables stay separate; no class precedence
or directional reinterpretation is inferred.

Optional `leftKey`/`rightKey` filters use exact raw keys. A left filter looks up
one group directly. A right filter performs one direct lookup per visited group.
Names must not be silently treated as raw IDs. Resolved names and group keys can
be fed into the existing exact-value read; unresolved IDs cannot.

Each response includes `items`, `total: null`, `returned`, `complete`,
`nextCursor`, `scanned`, and `scanLimit: 256`. The limit is 1–100, default 100.
Work units count outer-group visits (including their optional right-key lookup)
and sequential inner-entry visits. Empty groups and filter misses consume budget.
There are also constant-size scope/boundary checks. An empty incomplete page is
valid: follow its cursor. Total remains unavailable even on the terminal page;
no whole-table counting walk is performed.

The native `MGOrderedDictionary` accessors `count`, `keyAtIndex_` and
`objectForKey_` resume directly at the next indices. No table materialization,
sorting, retained iterator, font-wide glyph-ID map, watcher or cache was added.
Native `glyphForId_` resolves only requested output sides. The isolated prototype
read 100 entries at offsets 0, 500 and 1,000 in all three domains in 0.918–1.174 ms
(63 samples); these are detached native projection times, not HTTP measurements.

Cursors bind the document, master, direction and filters and check outer count,
existing generation/dirty signals and the last boundary. Edits or
`stale_kerning_cursor` require discarding partial evidence and restarting. Pages
are **live, not atomic**: silent same-count changes away from the boundary or
reverted edits can evade bounded guards. Dirty redraws may conservatively reject
a continuation. Missing private capabilities require a coordinated installation
update; no older-private fallback is shipped.

## Accuracy and preservation

| Gate | Result |
|---|---|
| Lean suite before installation | **870 passed** |
| Additional native-numeric regression cases | **5 passed**, bringing unique lean cases exercised to **875** |
| Final H6 and routing selection | **94 passed**, included in the above coverage |
| Isolated native source qualification | **155/155 passed** |
| Complete installed native/public run | **1,087/1,087 assertions passed** |
| Reproducible fixture regeneration | Exact byte match |
| Deterministic packaging, catalog, capability and size contracts | Passed in lean suite |
| Managed skills | All **11** payloads match; two updated, nine current, no conflict |
| Documentation build and whitespace | Passed; existing non-failing Node localStorage warning |

The synthetic fixture has three fixed master IDs, fractional outlines, three
named glyphs, all eight group/key properties, three pairs on small masters and
308 on the larger master in each direction. Native raw glyph IDs can change
when Glyphs reloads a source; every native run resolves them afresh. The generator,
fixture, source manifest and independent oracle are retained. Regeneration is
byte-identical after normalizing timestamps/app-version text.

Pinned open-source Roboto Slab contains 986, 1,094 and 1,299 LTR entries across
its three masters. The isolated gate checks all three masters and the empty
RTL/vertical domains. Live repetitions inspect the 986-entry master; synthetic
live controls cover every master/direction combination. All returned resolved
entries agree with existing exact-value reads. The oracle independently enumerates
native storage; it never fills in a missing public result.

Installed controls cover native empty groups and tables, a 206-entry inner group,
an unresolved ID, positive/negative fractions, zero, exact absence, group and
glyph keys, left/right/both/missing filters, page boundaries, no-match incomplete
pages, missing targets, invalid fields/limits/cursors/directions, dirty inspection,
foreground changes, value edits, added/deleted groups, group assignment changes,
closed IDs, reopened files with new IDs, foreign cursors and fresh recovery.
Doubles additionally exercise 600 empty/filter-missed groups, malformed native
evidence and silent non-boundary edits without claiming atomicity.

The independent proof covers native master/glyph/layer/shape/node identities,
geometry, available hint references, anchors, guides, components/alignment,
metadata, layer attributes/backgrounds, widths/metrics, selections, dirty state,
all group assignments and all kerning tables. Read operations leave them exact.
Deliberate storage mutations belong only to disposable control setup. Baselines,
the unrelated control and the two original open documents remain unchanged.
The original paths, clean states and foreground document are restored. No implicit
Save, autosave preference change, user-font edit or release publication occurred.

## Measured cost

The qualified run uses a fresh copy per trial: first, warm-up and five repetitions
for each workload, with **four open documents** throughout timing. IDs come from
public discovery; continuations retain the same ID. The original first attempt
is also retained separately, not overwritten by the successful rerun.

HTTP times below include the request/response round trip, not font opening,
independent oracle traversal, JSON report writing or agent reasoning. “Initial”
is one discovery plus all page reads; “known ID” includes every page, not just
the first one. Verification round trips are logged separately. No v1 speed
comparison is claimed: v1 was not rerun.

| Workload | Pairs / calls | Known-ID inventory median (range), ms | Initial median (range), ms |
|---|---:|---:|---:|
| Small synthetic | 3 / 1 | 42.8 (27.4–61.5) | 292.6 (74.9–339.4) |
| Larger synthetic | 308 / 4 | 154.8 (136.1–238.8) | 443.8 (354.3–575.5) |
| Roboto Slab | 986 / 10 | 372.6 (317.0–2,143.0) | 771.5 (644.4–2,769.4) |

Each row has n=5 full inventories; nearest-rank p95 equals the maximum at this
sample size. Discovery medians were 231.1, 292.0 and 441.3 ms, respectively.
The original first-attempt inventory/initial costs were 54.3/326.4,
280.6/572.0 and 493.1/792.8 ms. Warm-ups and every sample are in `analysis.json`
and `first-attempts.json`.

| Per-page measure | Small n=5 | Larger n=20 | Roboto Slab n=50 |
|---|---:|---:|---:|
| HTTP median, ms | 42.8 | 39.1 | 37.2 |
| HTTP p95 / maximum, ms | 61.5 / 61.5 | 62.6 / 137.9 | 209.1 / 927.1 |
| Native callback median, ms | 10.81 | 11.95 | 6.67 |
| Native callback p95 / maximum, ms | 19.09 / 19.09 | 18.94 / 24.39 | 16.92 / 29.43 |

Across all 360 observed native callbacks, p95 was **24.78 ms**, maximum
**64.35 ms**, meeting the existing <50/<200 ms targets in this run. Queue waiting
is separate: median 2.52 ms, p95 207.03 ms, maximum 955.33 ms. The native callback
includes target resolution and native reads; it is not merely an HTTP proxy.
The HTTP tails do not establish where every delay occurred. No new optimization
or causality claim follows from this measurement.

One/five/fifteen-minute host loads changed from 8.13/10.36/10.60 to
33.55/17.57/13.30. Load was not controlled, and qualification includes native
verification work outside measured callbacks. A separate alternating-order,
detached-host calibration (one warm-up + 15 pairs) measured a median **0.095 ms**
wrapper/clock overhead. That does not measure all live scheduling effects;
no overhead was subtracted. H6 adds no production timing instrumentation.

The complete successful harness took **171.7 seconds**, including fixture setup,
independent verification, incremental report writing and cleanup. It issued
**358 tool calls** (1 status, 29 discovery, 328 reads), plus initialize/catalog.
Thirteen tool errors were intentional rejection controls. Successful timing
repetitions required 75 page reads and 15 initial discoveries: retaining IDs
avoided 60 additional discovery calls versus discovery before every page.
The earlier stopped run adds 136 logged tool calls; it is not erased.

## Token costs and agent judgment

Estimates use **tiktoken 0.12.0 / o200k_base**, sorted compact JSON with literal
Unicode, one `{name,arguments}` plus one parsed response body. They are payload
estimates, not billed model usage. Actual model token usage is unavailable.

| Payload | Estimated tokens |
|---|---:|
| Eight native group/key fields for one glyph | 166–186 |
| Complete small three-pair read | 299–303 |
| Complete 308-pair traversal | 16,512–16,527 |
| Complete 986-pair traversal | 52,319–52,400 |
| One document discovery | 250–322; median 318 |
| Entry skill / focused discovery reference | 982 / 915 |

The large totals deliberately request both raw-key sides, resolution and values
for every pair. They are evidence costs, not a recommended default for an
ordinary known-pair question. Use the focused reference, requested fields and
exact filters; known pairs retain the compact exact-value route. The entry adds
only a routing row. Avoided discovery costs are estimated at roughly 19,080 tokens
for the 60 calls above using the observed median; that is a counterfactual estimate,
not measured usage savings. Initial discovery costs remain included in task totals.

**Agent/skill judgment: 4/5 for the resulting inspection workflow.** The agent
can obtain group assignments directly and verify discovered pairs through an
existing public read. Scope, directions, unknown IDs and incomplete evidence are
explicit. It needs no script, Save, install or UI action during ordinary discovery.
Large full-table questions still require multiple calls and careful raw-key/name
handling; live cursors can require restarting after edits. The skill provides
concrete guidance for these limitations.

**Implementation/qualification delivery: 3/5.** The first local test draft had
a syntax error and duplicate-key fixture helper errors. Isolated native testing
then caught PyObjC's `OC_PythonFloat` subclass: the original strict Python type
check rejected legitimate native values. That was corrected before installation,
and five regression cases were added. The installed runtime needed no correction.
The first live run stopped after 406 assertions because an unrelated background
status callback overlapped a measured read (13 native counts and 131 glyph lookups
were within their intended bounds). The harness now attributes H6 callbacks by
its temporary native counters and retains unrelated callbacks separately. The
first failure, all its timings and the clean rerun are preserved. One stale UI
index during app launch also required correction. No user intervention was needed.

One runtime installation, one ownership-checked skill installation and one
Glyphs quit/relaunch were used. The task macro was started twice for qualification,
then its verified-empty on-disk file was archived, the original macro selection
restored and Scripting Window closed. No redundant runtime installation followed
the harness correction.

## Installed identity and delivery

| Component | Running initialization-time fingerprint |
|---|---|
| Sidecar | `2.0.0-beta.1+8d20076967d8` |
| Bridge | `2.0.0-beta.1+f5331ad953dd` |
| Sidecar full | `sha256:8d20076967d8c1898f00ddfc2a3a38feb3f64e7d9d80f0f620e82954fa75bf39` |
| Bridge full | `sha256:f5331ad953dd8244a45b302a4a86416e2fd673a1afe22e987c3946aa2d17966e` |

Both match the candidate manifest before and after qualification. Runtime dependencies and Curve Inspector hashes are unchanged. Reference Inspector
has a new bundle fingerprint solely because it includes the shared protocol
`reads.py` capability constants; its companion implementation is unchanged.
The existing transaction installer carries those components alongside the updated
bridge/sidecar. Eleven configured skill
trees match the tested payload, with existing ownership backups and no conflicts.
The bridge adds one small stateless module; its 500-line adapter stays at 500.
The bridge aggregate budget rises from 2,130 to 2,300 lines; the global 6,000-line
budget and every editing hook remain unchanged. Source preservation is recorded
in `preservation.json`; unrelated work is retained.

See `test-spec.md`, `candidate-manifest.json`, `installed-verification.json`,
`api-evidence.json`, `analysis.json`, compressed native evidence/call logs and
retained test/build/install outputs for reproducible details. Historical reports
and v1 remain unchanged. MGOrderedDictionary behavior is qualified on this host,
not asserted for every Glyphs 4 build.

**No additional H6 fix is required by these results.** The high-priority steps
are closed within their agreed scope. Next, after feedback: add requested native
master metrics and axis values. Example: read each master's ascender, x-height
and axis position together, so the agent can compare masters without a script.
HTTP/queue tails and the existing native dirty-indicator limits remain separate.
