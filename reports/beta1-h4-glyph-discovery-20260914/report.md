# H4 — bounded glyph discovery

**Implemented, installed and qualified** on the private `2.0.0-beta.1` candidate,
installer build 43, Glyphs 4.1 (4107). H5 has not started.

The agent can now answer “What glyphs does this font contain?” through the existing
`read_entities` tool. It reads native names in bounded pages, then uses the ordinary
explicit glyph selector to inspect chosen targets. Known names need no preliminary
inventory or repeated document discovery.

## Delivered behavior

- Negotiated **`glyphs.list.v1`** capability; bridge, sidecar and installed entry skill
  updated together. Missing capability requires updating this private installation.
- One `{"kind":"glyphs","limit":100}` selector with `fields:["name"]`. Integer
  limit 1–100, default 100; no other page fields or mixed selectors initially.
- Native collection order, `items`, `total`, `returned`, `complete` and opaque
  `nextCursor`. Empty fonts return a complete empty inventory with total zero.
- Each page accesses only its requested indices plus, on continuation, one preceding
  boundary glyph. Native count comes from `GSFont.count()` through the wrapper.
  No complete-font list, sorting, previous-page rescanning, inventory cache or watcher.
- A cursor binds document ID, count, existing generation/dirty signals and the last
  returned glyph's native ID/name. Changed evidence returns `stale_glyph_cursor`;
  close/reopen uses the existing `document_not_found`/new-ID behavior.
- One compact entry routing row and a focused discovery reference, mirrored into
  the plugin payload. No v1 code, editing job or Undo/discard change.

Request, using this connection's retained document ID:

```json
{"document_id":"doc_…","entities":[{"kind":"glyphs","limit":100}],"fields":["name"]}
```

Example `values` for a two-glyph font:

```json
{"items":[{"name":"A"},{"name":"V"}],"total":2,"returned":2,"complete":true,"nextCursor":null}
```

For a partial page, pass the returned cursor unchanged in the next selector.
An agent stopping early must report “N of total names read”. It must discard partial
results and restart after any observed edit or stale-cursor error.

**This is a live inventory, not an atomic snapshot.** Native probing found no usable
`GSDocument.changeCount()` on this host. Some scripted renames do not immediately
set a dirty flag or generation. Bounded guards cannot detect every silent same-count
edit away from the boundary, or an edit reverted between calls. Conversely, the
existing dirty-document update signal can invalidate on selection/redraw activity.
The skill states both limits, asks for a quiet read interval when needed and forbids
merging interrupted pages or claiming snapshot consistency. This limitation is
intentional in the accepted lean H4 plan; no new change-tracking system was added.

## Validation and accuracy

| Evidence | Result |
|---|---|
| Lean regression suite, including 64 H4 tests | **713/713 passed** |
| Isolated native source gate | **38/38 passed** |
| Installed public MCP/native qualification | **616/616 distinct checks passed on the first run** |
| Deterministic packaging, catalog/capability and skill mirror checks | Passed in the lean suite |
| Managed skill installation | All **11** payload identities match; `glyphs` updated, ten current, no conflicts |
| Documentation site build | Passed; existing non-failing Node localStorage warning |

Native cases include 0, 1, 100 and 101 glyphs, plus the pinned open-source **Roboto
Slab: 1,272 glyphs and three masters**. Synthetic fixtures retain three fixed master
IDs and fractional geometry. The generator, native expected names, source provenance
and hashes are retained in [qualify_source.py](qualify_source.py) and
[fixtures.json](fixtures.json). Only disposable copies were opened in the editor;
the original Roboto Slab source and all four synthetic baselines remain unchanged.

Installed checks compare every returned name, order, total, returned count and end
flag to an independent native oracle. Instrumented native collections confirm one
count read and exactly the page indices plus the preceding boundary, never iteration.
Missing native evidence, malformed cursors and a 10,000-entry collection whose
iterator raises have deterministic double coverage; native unavailability faults
were not artificially forced in Glyphs.

Native controls cover a dirty two-page inventory without saving; add/delete and
boundary rename rejection; an explicitly observed earlier rename; recovery by fresh
enumeration; invalid fields/limits/cursors; target close; reopening the same path
with a new ID; refusal to move an old cursor to that replacement. H3 Edit View and
optional selected-node context still work. The seven tools, five job kinds, interface
revision 1 and bridge protocol 1 remain intact.

Before/after native proofs compare glyph object identities, the existing P06 font
snapshot (layer/shape/node identity and geometry, anchors, components, widths and
metrics), selection, selected master and dirty state. Protected font contents and
file hash match across installation and qualification. No user font was saved.
The earlier H3 selection/hint qualification remains historical evidence, not a new
H4 hint-editing claim. No new Undo, mutation or restoration behavior is introduced.

Raw evidence: [native facts](native-facts.json.gz), [timestamped calls](calls.jsonl.gz),
[isolated source checks](native-source.json.gz), [native API probe](native-probe.json)
and [test output](lean-tests.txt). Gzip files preserve the exact raw evidence;
[evidence hashes](evidence-files.json) record their uncompressed checksums.

## Timing and token cost

Each size below used a first attempt, one warm-up and five measured fresh copies,
with **two open documents**. Each copy's ID came from public discovery. There were
no automatic retries. These are HTTP costs, not complete wall-clock agent sessions:
opening files, independent preservation oracles, evidence serialization and reasoning
are outside the request timer. The full installed run, including those controls,
took **90.66 seconds**, 17:40:00–17:41:31 UTC on September 14, 2026.

| Five-repetition result | 100 glyphs | 101 glyphs | Roboto Slab, 1,272 glyphs |
|---|---:|---:|---:|
| Pages per inventory | 1 | 2 | 13 |
| Inventory HTTP sum median | 36.88 ms | 71.81 ms | 452.73 ms |
| Inventory HTTP sum range | 27.95–82.76 ms | 65.96–115.11 ms | 383.63–559.24 ms |
| Discovery median | 290.83 ms | 282.73 ms | 324.39 ms |
| Discovery + inventory HTTP sum median | 327.29 ms | 378.98 ms | 796.28 ms |
| Per-page HTTP median | 36.88 ms | 36.13 ms | 32.82 ms |
| Per-page HTTP p95 / maximum | 82.76 / 82.76 ms | 83.12 / 83.12 ms | 49.74 / 138.76 ms |
| Per-page native callback median | 9.81 ms | 9.97 ms | 5.32 ms |
| Per-page native p95 / maximum | 18.64 / 18.64 ms | 18.01 / 18.01 ms | 12.61 / 13.86 ms |
| Page samples | 5 | 10 | 65 |
| Complete inventory request + response tokens, median | 794 | 1,274 | 13,892 |

First inventory HTTP sums were 40.41 / 161.81 / 908.14 ms; warm-ups were
48.91 / 52.83 / 535.30 ms. Initial discovery is disclosed above, not removed from
task cost. The complete [analysis](analysis.json) includes discovery and combined
ranges, p95 values and every first/warm-up sample. With five samples, nearest-rank
p95 equals the maximum and is not a reliable population-tail estimate.

Across all **175 callbacks**, native execution p95 was **21.35 ms**, maximum
**40.39 ms**, within the existing 50/200 ms callback targets. Queue waiting p95
was **364.37 ms**, maximum **1,099.84 ms**. This is temporary callback timing, not
a continuous UI-responsiveness probe or a resolution of the separate queue-tail
investigation. Instrumentation includes clock reads, bounded records and the
indexed-access wrapper; its overhead was not independently subtracted. Independent
full-font oracles ran outside these callback measurements.

Host load averages rose from 24.54/20.68/15.52 to 32.07/23.45/17.07. Concurrent
load was uncontrolled, and a documentation site build ran during qualification.
No speedup over H3 or v1 is claimed. v1 was unchanged and not freshly benchmarked.
H4 closes its historical glyph-inventory coverage gap with a bounded lean read.

Tokens use the established P06 method: tiktoken 0.12.0 / `o200k_base`, sorted
compact JSON with literal Unicode, one `{name,arguments}` request and one parsed
response body. These are estimates, not billed usage. Cursors and the existing
selector echo are included. The table excludes the separately shared status/catalog
and document-discovery payload. The 100-name response costs 743 tokens; Roboto
pages have a 900-token response median. Entry skill: **928 text tokens**, up 25
from H3; the focused reference is **640**, loaded only for unknown-name discovery.

The run used **175 tool calls**: 1 status, 31 document discoveries and 143 reads,
plus one initialization and one catalog request. Eleven errors were intentional
stale/invalid-input controls, all with the expected codes. No product or harness
correction was needed after the first installed run. One installation and one
Glyphs relaunch were used; the normal skill installer performed one managed refresh.

## Installed identity and preservation

| Component | Running identity |
|---|---|
| Sidecar | `2.0.0-beta.1+9ed7938a2e54` |
| Bridge | `2.0.0-beta.1+5331881901ff` |
| Host | `com.GeorgSeifert.Glyphs4`, 4.1 (4107) |

Both complete fingerprints agree with the [candidate manifest](candidate-manifest.json),
[installation receipt](install.json) and [running status](runtime-final.json).
The endpoint remains `http://127.0.0.1:9680/mcp/`. All eleven configured skills match
[their installed payload checksums](skills-install.json). No release was published.

[Source preservation](source-preservation.json) confirms **3,653 of 3,662 existing
files unchanged**; the nine changed existing files are precisely H4 source, test
budget, skill and command-reference edits. The new projection is 87 lines; the
adapter remains within its existing 500-line limit. The aggregate bridge budget
increased by 100 lines to accommodate this module; the global budget is unchanged.
Preexisting desktop, installer, legacy documentation and other work remain intact.
Original H1–H3 reports are unchanged. The test macro was archived, instrumentation
removed, disposable fonts closed and the clean protected font returned to view.

## Agent judgment and next fix

**Worth keeping; no further H4 fix is justified by this run.** Discovery, instruction
accuracy, evidence clarity and recovery are **4/5**: one existing tool provides
explicit names and coverage, and errors tell the agent when to restart. Workflow
effort is **4/5**: known IDs are reused, focused guidance adds little initial context,
and the installed protocol completed without retries or manual target correction.
These are reasoned ratings, not measured accuracy or a 5/5 goal. Pagination still
requires sequential requests and a quiet interval; the cursor cannot prove atomic
consistency against all silent native edits. The native result accuracy is separately
established by the exact checks above. No visual or typographic quality claim applies
to this read-only inventory.

**Next, after feedback: H5 — discover an explicit glyph's layers.** Example:
“Show every layer of `a`, including intermediate and backup layers.” Benefit:
the agent can obtain exact layer IDs instead of guessing them. H5 remains paused.
