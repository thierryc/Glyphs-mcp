# H3 — compact document context

**Implemented, installed and qualified** on the private `2.0.0-beta.1` candidate,
installer build 43, Glyphs 4.1 (4107). H4 has not started.

An agent can now answer “Which glyphs and master have I selected?” in Font View
or Edit View using the existing `read_entities` tool. It can identify Glyphs’
current font through `list_documents.isCurrent`, while a retained document ID
continues targeting its original font after foreground changes.

## Delivered behavior

- New negotiated capability **`document.context.v1`**. One `{"kind":"context"}`
  selector, requesting only `view`, `master` and/or `selectedGlyphs`.
- Native selected-tab identity establishes `font`, `edit` or `unavailable`.
  The toolbar master returns its exact native ID and name, or null.
- Selected glyph names come from native `font.selection` in Font View and
  `font.selectedLayers` parents in Edit View. Native order is preserved. Glyphs
  itself collapses repeated occurrences of the same selected layer; the bridge
  does not add sorting, deduplication or text-occurrence counting.
- Default/maximum 100 names; optional integer `glyphLimit` 1–100 only with
  `selectedGlyphs`. Total, returned, limit, source and completeness are explicit.
  Missing count evidence returns null total, incomplete evidence and a reason.
  There is no traversal to manufacture a count and no pagination model.
- `isCurrent` is true/false from Glyphs’ native current font, or null when its
  evidence cannot be read. It is not inferred from list order or macOS window
  stacking. Retained IDs never silently retarget.
- Entry skill gains one routing row; focused context/selection/targeting references
  and packaged mirrors explain the request, bounds and update requirement.

For a known ID:

```json
{"document_id":"doc_…","entities":[{"kind":"context"}],"fields":["view","master","selectedGlyphs"]}
```

Example values:

```json
{"view":"font","master":{"id":"5EB56BC4-5A2B-5460-ABC1-E8EE0E3B95EC","name":"Regular"},"selectedGlyphs":{"source":"font.selection","total":2,"returned":2,"limit":100,"complete":true,"items":["control","h3test000"]}}
```

The seven tools, five job kinds and protocol/interface revision 1 remain unchanged.
Existing selection fields and optional node details retain their 64-default /
256-maximum contract. No editing, document lifecycle, Undo/discard or v1 code
was changed. Missing private capabilities require updating bridge, sidecar and
skills together; no older-private workflow was added.

## Validation and accuracy

| Evidence | Result |
|---|---|
| Lean Python suite, including 48 H3 tests | **649 distinct tests passed** across the suite and the socket-control rerun |
| Existing native selection regression on source | **133/133 checks passed** on isolated Glyphs 4 objects |
| Installed native context qualification | **102/102 distinct checks passed** after correcting two test setup errors |
| Deterministic lean packaging and capability/catalog regression | Passed in the lean suite |
| Installed skills | All **11** match the candidate; only the owned `glyphs` skill changed |
| Documentation site build | Passed; existing non-failing Node localStorage warning |

The installed checks cover all three masters, native empty/multiple selection,
Font/Edit View, repeated occurrences, an empty Edit View, mixed nodes/anchors/
components/guides, 256-node details, requested bounds, invalid fields/limits,
two disposable fonts alongside the protected document, foreground switches,
dirty state, close/reopen, stale-ID rejection and explicit recovery to a new ID.
Every context read was compared with an independent native oracle.

Exact before/after proofs cover native glyph/layer/shape/node/anchor/guide identity,
coordinates, widths, metrics keys, component references/transforms/alignment,
node names, selected objects and dirty state. The existing isolated selection
regression additionally verifies hints and node metadata. Both baseline fixtures
remain unchanged. The protected font’s file hash and native contents match
before installation and after qualification; no user font was saved.

Missing collection/view evidence and bounded traversal were exercised with
explicit doubles, including a 10,000-entry indexed selection whose iterator
raises. Native missing-evidence faults and native-address reuse were not forced
in Glyphs; existing document-ID doubles remain regression coverage for those
lifetime hazards. Native close/reopen and foreground behavior were actually run.

Raw evidence: [installed native facts](native-facts.json.gz),
[first attempt](native-first-attempt.json.gz), [second attempt](native-second-attempt.json.gz),
[isolated native selection regression](native-selection-regression.json.gz) and
[timestamped public calls](calls.jsonl). The gzip files preserve the exact raw JSON.

## Timing and tokens

First attempt, one warm-up and five timed repetitions used fresh copies for
both sizes, with **three open documents** each time. IDs came only from public
`list_documents`; setup/oracles did not supply IDs or complete MCP reads.

| Five-repetition measurement | 2 selected glyphs | 109 selected / 100 returned |
|---|---:|---:|
| Context HTTP median | 22.73 ms | 25.97 ms |
| HTTP range | 20.69–65.36 ms | 24.41–38.15 ms |
| HTTP p95 / maximum | 65.36 / 65.36 ms | 38.15 / 38.15 ms |
| Initial discovery median | 116.59 ms | 164.03 ms |
| Discovery + first read median | 157.43 ms | 188.44 ms |
| Native callback median | 4.38 ms | 6.40 ms |
| Native callback p95 / maximum | 8.28 / 8.28 ms | 10.20 / 10.20 ms |
| Dispatch wait median | 2.49 ms | 2.48 ms |
| Parsed response tokens | 92 | 582 |
| Request-token median | 50 | 50 |

First context reads were 21.66 / 51.73 ms; warm-ups were 18.71 / 28.93 ms. Initial
cost is disclosed, not omitted from the task. Full samples, initial ranges and
p95 values are in [analysis.json](analysis.json). With n=5, nearest-rank p95 is
just the maximum; this is not a stable population-tail estimate.

Across all 70 instrumented tool callbacks, native execution p95 was 34.72 ms and
maximum 126.81 ms, below the existing 50/200 ms execution targets. Dispatch waits
had p95 516.64 ms and maximum 634.20 ms. This is callback instrumentation, **not a
continuous UI responsiveness pass**. HTTP remains a separate round-trip measure.
The temporary wrapper adds two clock reads and one bounded sample append;
its overhead was not independently subtracted and it was removed at cleanup.
Host load averages rose from 9.82/13.43/13.11 to 26.89/34.41/24.32. Concurrent load
was not controlled, so no historical speedup or resolution of HTTP tails is claimed.

Token estimates use the same P06 method: tiktoken 0.12.0 / `o200k_base`, sorted
compact JSON, literal Unicode, one `{name,arguments}` request and one parsed
response body. They are not billed usage. The focused context reference is 684
text tokens; the current entry is 903. The older P06 53–56-token selection response
has less information and is not an equivalent task. Node details remain opt-in.

The harness made **70 tool calls**: 3 status, 20 discovery, 47 reads, plus three
initializations and three catalog fetches across initial execution and resumes.
There were no automatic request retries or edit jobs. Seven error responses are
intentional invalid/stale-ID controls. v1 was left unchanged and was not freshly
timed; this closes its historical current-context/Font View coverage gap without
claiming a measured v1 speed comparison.

## First-attempt findings and limits

All first-attempt evidence is retained. Initial unit development exposed a missing
capability-list addition and two outdated/text-format assertions; these were
corrected before packaging. Two broader-suite tests could not bind ephemeral
loopback sockets in the sandbox. The 20-test socket suite passed with required
local access, covering both failures; no product correction was needed.

Native execution first stopped after 78 successful assertions because the harness
nested a main-thread dispatch inside its own callback. This caused a 30-second
setup timeout, not an H3 callback failure or observed crash. The next run found
that the test’s inactive-layer width setter did not mark that document edited.
That dirty-state **precondition failed**. The corrected fixture explicitly calls
native `updateChangeCount_(NSChangeDone)` before testing its read. No production
Undo or dirty-state logic was changed. The 122 raw assertions therefore contain
121 passes and one failed setup assertion; all 102 distinct final checks pass.

Native controls were resumed on new copies with publicly discovered new IDs.
The successful timed repetitions were retained and not replaced. Total native
qualification spanned 16:48:37–16:53:40 UTC, including setup correction and restart
of the harness. Opening a Python file through the app’s general Open dialog was
unsupported; a dedicated native scripting macro was used instead. The inherited
3532 file-format application label also produced native version warnings on
some disposable opens. No global warning or autosave preference was changed.

## Installed identity and preservation

| Component | Running identity |
|---|---|
| Sidecar | `2.0.0-beta.1+f15183c8c77b` |
| Bridge | `2.0.0-beta.1+b889ff6290d5` |
| Host | `com.GeorgSeifert.Glyphs4`, 4.1 (4107) |

Both complete fingerprints match [candidate-manifest.json](candidate-manifest.json)
and [installation evidence](install.json). The existing installer replaced the
candidate while Glyphs was closed, then started the sidecar. Its normal managed
skill upgrade recorded no conflicts; [all eleven identities](skills-install.json)
match the tested payload. No public release was published.

[Source preservation](source-preservation.json) verifies 3,646 of 3,658 existing
source files unchanged; the twelve changed existing files are the H3 runtime,
test and documentation edits. New files are the stateless context projection,
focused reference, tests and qualification evidence. Preexisting desktop/installer
work remains in the worktree. The temporary test macro was archived, test windows
closed and the original font returned to view.

## Agent judgment and next fix

**Worth keeping.** This supplies the missing evidence through one existing read,
without node payloads, script execution, guessed font targeting or a new model.
Native ordering and explicit incompleteness make the answer verifiable. The
agent workflow is simpler; qualification itself had the recorded scripting and
setup friction. No 5/5 rating or broad latency improvement is claimed.

**Next, after feedback: H4 — bounded glyph-name discovery.** Example: “What glyphs
does this font contain?” The benefit is discovering valid targets without a
script or loading outlines. H4 remains paused.
