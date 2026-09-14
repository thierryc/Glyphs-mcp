# H5 — discover exact glyph layers

**Implemented, installed and functionally qualified** on private `2.0.0-beta.1`,
installer build 43, Glyphs 4.1 (4107). The interface still has **seven tools**.
H6 has not started. One callback exceeded the timing maximum; the focused follow-up
did not reproduce it. That result remains recorded below, not counted as a timing pass.

The agent can now ask “Show every stored layer of `a`, including intermediate,
alternate and backup layers,” obtain exact IDs, and read chosen layers without
guessing names or discovering documents again.

## What changed

`read_entities` now advertises **`layers.list.v1`**. One `layers` selector targets
one named glyph, with an integer page limit of 1–100, default 100:

```json
{"document_id":"doc_…","entities":[{"kind":"layers","glyph":"a","limit":100}],"fields":["id","name","associatedMasterId","isMasterLayer","isSpecialLayer","isBraceLayer","isBracketLayer"]}
```

The response's `values` contains `items`, `total`, `returned`, `complete` and
`nextCursor`. Each item contains only requested fields, for example:

```json
{"id":"H5_BACKUP","name":"Duplicate","associatedMasterId":"C7941642-FFB2-5D2E-B7FE-4A30A143BE40","isMasterLayer":false,"isSpecialLayer":false,"isBraceLayer":false,"isBracketLayer":false}
```

Use that ID directly in the existing measurement request:

```json
{"document_id":"doc_…","entities":[{"kind":"layer","glyph":"a","id":"H5_BACKUP"}],"fields":["id","width","bounds"]}
```

Native classification flags remain separate evidence. Brace means intermediate;
bracket means alternate. Other special layers can have neither flag. All-false
special flags on a non-master identify an extra/backup candidate, not its purpose.
Unknown optional evidence is null; it never becomes a fabricated false. Names,
flags and master associations do not establish compatibility or special-layer groups.
No derived classification engine was added.

The inventory follows native `countOfLayers()` / `objectInLayersAtIndex_` order.
The installed Python wrapper's integer indexing rescans preceding extra layers;
the implementation uses the underlying native accessor directly. It does not
sort, materialize the full collection or copy geometry. Nested backgrounds are
not separate entries in the stored glyph-layer collection. The skill states this
scope and distinguishes native order from UI/wrapper presentation.

Pages carry an opaque document/glyph-bound cursor. Count, existing generation/dirty
signals and the preceding layer ID/name provide bounded stale checks. An observed
edit or `stale_layer_cursor` requires discarding partial results and restarting.
These are **live pages, not an atomic snapshot**: silent same-count changes away
from the boundary or reverted edits can escape the guards; dirty-document redraws
can conservatively invalidate them. No cache, watcher or new document model was added.

Bridge, sidecar, entry skill, focused references and packaged mirrors were updated
together. An unavailable private capability requires an installation update;
there is no earlier-private fallback. Existing exact layer-ID reads, five job kinds,
interface/bridge protocol revision 1 and native Undo/discard hooks are unchanged.

## Accuracy and preservation

| Gate | Result |
|---|---|
| Lean regressions, including 83 H5 tests | **796/796 passed** |
| Isolated native source qualification | **164/164 passed** |
| Installed native/public MCP qualification | **302/302 distinct checks passed on the first run** |
| Focused latency follow-up correctness/preservation | **54/54 passed** |
| Deterministic packaging and seven-tool/capability regression | Passed in the lean suite |
| Managed installation | All **11** skills match the candidate; entry skill updated, ten current, no conflicts |
| Documentation site build | Passed; existing non-failing Node localStorage warning |

The reproducible [fixture](LayerDiscoveryTest.glyphs) contains three masters with
fixed IDs and fractional geometry; a seven-layer glyph with intermediate/alternate
layers, duplicate backup names and a deliberately incompatible backup; a second
glyph; a 105-layer glyph; and a populated background excluded from inventory.
The [generator and isolated gate](qualify_source.py) and [expected manifest](fixtures.json)
are retained. Open-source Roboto Slab uses the existing pinned source and license;
isolated checks cover `a`, `A`, `g`, `adieresis` and `one`, and live repetitions use `a`.

Each live inventory's IDs, names, associations, flags, order, counts and end marker
match an independent native oracle. Every returned ID is fed back through public
explicit layer reads, in batches of at most 100. Duplicate-name aliases are rejected.
Instrumentation confirms exactly the requested indices plus one preceding boundary
on continuations and one native count per page. A 10,000-layer double rejects
unbounded traversal. Empty collections and missing/corrupt native evidence have
double coverage; they were not artificially forced in the installed application.

Native controls cover add/delete and boundary rename, observed association changes,
dirty multi-page reads, explicit recovery, wrong glyph/cursor/field/limit inputs,
close/reopen with a new ID, rejection of an old cursor on another glyph or replacement
document, and continued targeting after foreground changes. H4 name discovery and
selected-node reads across all three masters still work. Untitled support is covered
by doubles; the native dirty-document test uses a saved disposable copy without saving it.

The independent [oracle](h5_oracle.py) traverses all test layers outside the measured
public callback. It verifies layer/master/glyph/shape/node object identities,
coordinates, widths, metrics keys, node and layer user data, layer attributes,
anchors, guides, component transforms/alignment, available hint references, backgrounds,
selection and dirty state. Both documents restored by Glyphs on launch and a separate
unrelated disposable font remain exactly unchanged through both native runs.
All baseline files remain unchanged; the protected user-copy file hash also matches
its prior H4 evidence. No user font was saved. These read checks do not claim new
hint-editing or Undo qualification.

## Timing and tokens

Each size used a first attempt, one warm-up and five measured fresh copies. All
trials had **four open documents**. IDs came only from public `list_documents`.
The table gives summed HTTP request costs, not total agent wall time: file opening,
independent oracles, report serialization and reasoning are outside request timers.
The original native qualification, including those activities and controls, took
**90.75 seconds**, 18:05:50–18:07:21 UTC on September 14, 2026.

| Five-repetition measurement | 7 layers | 105 layers | Roboto Slab `a`, 3 layers |
|---|---:|---:|---:|
| Inventory pages | 1 | 2 | 1 |
| Inventory HTTP sum median | 37.66 ms | 85.84 ms | 32.83 ms |
| Inventory HTTP sum range | 36.71–43.40 ms | 79.33–103.05 ms | 32.19–44.95 ms |
| Initial discovery median | 216.05 ms | 185.97 ms | 379.16 ms |
| Discovery + inventory HTTP sum median | 253.72 ms | 282.33 ms | 411.35 ms |
| Per-page HTTP p95 / maximum | 43.40 / 43.40 ms | 72.11 / 72.11 ms | 44.95 / 44.95 ms |
| Native callback median | 13.61 ms | 11.11 ms | 9.16 ms |
| Native callback p95 / maximum | 17.98 / 17.98 ms | 37.96 / 37.96 ms | 10.06 / 10.06 ms |
| Page samples | 5 | 10 | 5 |
| Complete inventory request + response tokens, median | 633 | 7,576 | 368 |

First inventory HTTP sums were 35.84 / 60.15 / 34.27 ms; warm-ups were
183.31 / 82.65 / 28.74 ms. [Analysis](analysis.json) retains every sample summary,
initial-discovery ranges and nearest-rank p95 values. At n=5, p95 is simply the
maximum, not a stable population-tail estimate. Exact-ID round-trip verification
calls are separately logged and excluded from inventory timing/token totals.

Across all **127 original callbacks**, native wall-time p95 was **35.30 ms**, but
maximum was **339.18 ms**, exceeding the 200 ms target once. It was the first
background-target inventory after showing another font, after the Roboto trials.
Only seven indices were visited. Queue waiting p95/max was **296.47/1,212.84 ms**.
This is callback instrumentation, not a continuous UI-responsiveness probe.

The [focused follow-up](latency-followup.json.gz) retained the first/warm-up/five
protocol on fresh copies, reading full metadata in foreground, immediately after
a foreground switch, and then IDs only in the background: **21 reads**, no accuracy
failures. Among all 29 follow-up callbacks the maximum was **48.46 ms**. The H5
layer projection itself had a **0.86 ms median, 1.91 ms maximum**. Five measured
post-switch full-metadata reads had native median/max **18.14/30.49 ms**, versus
HTTP median/max **139.48/461.56 ms**. Main-thread CPU time was recorded separately;
native wall time must not be interpreted as CPU consumption.

The original 339 ms callback remains unexplained: it did not have inner-stage/CPU
instrumentation, so the follow-up cannot retrospectively assign its cause. The
maximum target therefore did not pass for the complete original run. No intrinsic
layer-enumeration bottleneck was reproduced; the evidence does not justify caches,
watchers or thread changes. Retain this outlier with the separate latency investigation.

Original host load averages changed from 16.19/25.00/25.34 to 10.65/20.80/23.68;
follow-up load from 11.78/14.39/19.84 to 10.67/14.06/19.66. Concurrent host load was
uncontrolled. Native instrumentation adds bounded records, clock reads and index/
field wrappers; overhead was not independently subtracted. No historical speedup
over v1 or H4 is claimed. v1 was unchanged and not freshly timed.

Tokens use P06's method: tiktoken 0.12.0 / `o200k_base`, sorted compact JSON with
literal Unicode, one `{name,arguments}` request and one parsed response. They are
estimates, not billed usage. Shared status/catalog/discovery payloads are excluded
from the inventory-token row. A seven-layer full-metadata response costs **561**
tokens; the measured ID-only response costs **156**. The entry is **959 text tokens**
(31 more than H4); the focused reference is **728**, loaded only when needed.

The original run made **127 tool calls**: 1 status, 29 discoveries, 97 reads, plus
one initialization/catalog fetch. The follow-up added 1 status, 7 discoveries and
21 reads. No automatic request retries, edit jobs or repeated installation occurred.

## Installation, first-attempt findings and cleanup

Running sidecar **`2.0.0-beta.1+1dfd3ea6d279`** and bridge
**`2.0.0-beta.1+dd39b1c6edc6`** match the complete fingerprints in the
[candidate manifest](candidate-manifest.json), [receipt](install.json) and
[live status](runtime-final.json). Host identity is `com.GeorgSeifert.Glyphs4`,
4.1 (4107). The endpoint remains `http://127.0.0.1:9680/mcp/`.
One normal installation, one managed-skill refresh and one application launch
were used; no release publication or v1 installation took place.

Initial status correctly reported the H4 sidecar with an unavailable bridge because
Glyphs 4 was closed. A diagnostic print incorrectly assumed a bridge runtime ID;
the full response was preserved and the app state inspected. The first HTTP attempt
also required local-network sandbox access. Neither was a product failure or a
reason to reinstall. Native fixture prototyping initially used array-valued coordinates
and rules; the installed Glyphs 4 wrapper documents axis-ID dictionaries in memory.
The [first](native-probe-first.json) and [second](native-probe-second.json) probes
are retained alongside the corrected [native proof](native-probe.json). No installed
qualification correction or candidate rebuild was needed afterward.

[Source preservation](source-preservation.json) confirms **3,657 of 3,666 existing
files unchanged** against the earlier frozen worktree plus the intervening H4 commit;
the nine changed existing files are exactly H5 runtime/test/skill/command-reference
edits. The initial H5 hash capture was accidentally empty due to its absolute-path
build exclusion; it is not claimed as evidence. The older preserved baseline and H4
commit supply the comparison instead. Preexisting unrelated changes remain unstaged.
The new projection is a small stateless module; only existing read dispatch/capability
hooks changed. The bridge aggregate line budget grew by 120; global and per-module
budgets remain unchanged. H1–H4 reports remain intact.

Both native runs restored temporary instrumentation and closed their H5 disposable
fonts without saving. The verified-empty test macro was archived, Macro 1 reselected
and the original font window restored. No autosave or application preference changed.
Raw [native facts](native-facts.json.gz), [call log](calls.jsonl.gz),
[isolated checks](native-source.json.gz), [test output](lean-tests.txt),
[skill checksums](skills-install.json) and [cleanup](cleanup.json) are retained.

## Judgment and next fix

**Keep H5.** Exact IDs remove a real targeting gap without adding tools. Discovery,
instruction accuracy, evidence clarity, recovery guidance and workflow effort are
each **4/5**: explicit fields, honest coverage, current private capability checks,
and successful exact-ID reads support those judgments. Multiple pages and a quiet
interval still require agent care; unknown flags do not become certainty. The timing
outlier is disclosed separately from these judgments and from exact correctness.
No further H5 implementation change is justified by the bounded follow-up.

**Next, after feedback: H6 — discover stored kerning groups and pairs.** Example:
“Which kerning groups and stored pairs exist in this master?” Benefit: inspect
existing kerning without starting a correction job. H6 remains paused.
