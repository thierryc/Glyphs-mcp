# P13 follow-up — implemented coverage feedback and realistic-font qualification

September 13–14, 2026. **The focused skill and companion coverage notice are implemented,
installed and verified on Glyphs 4.** Final-build inspection passes **30/30 realistic
Dactylotype layer cases**, with exact whole-font preservation. **The broader native
editing/history benchmark is not an unconditional pass:** native Undo rounds some
fractional control points in `at` and `s`. The `at` failure reproduces with Curve
Inspector disabled. No Undo or autosave implementation was changed.

[Specification](test-spec.md), [structured facts](facts.json), [preservation audit](final-audit.json).
The original [P13 paired comparison](../report.md) and its measurements remain intact.

## Delivered change and identities

- The compact outlines skill links to one focused curvature reference. It names
  **View → Show Curve Inspector**, explains signs, components, sampling/clamping,
  native view/history checks, retained connection/document context and exact
  restoration limits. The invocation names `$glyphs-mcp-outlines-docs`; its implicit
  invocation policy is preserved. Entry skill remains unchanged.
- Native visible-layer extraction returns existing cubics plus compact coverage
  metadata. One extra valid cubic establishes “more exist”; no exact total is
  invented after a bound. Extraction stops at 128 cubics, 8,192 visited nodes or 512
  paths. Components are counted and explicitly omitted, without decomposition.
- The existing worker/cache carries that metadata. Metadata changes participate
  in refresh invalidation. Drawing shows a small, backed notice in the safe
  viewport, and clears it with the old layer/activation state. Existing comb
  geometry and the 2,000-tooth budget are unchanged. No tool, job, watcher, history
  manager, live-Python capability or full-font product traversal was added.

| Component | Final evidence |
|---|---|
| Product / host | 2.0.0-beta.1, installer 43 / Glyphs 4.1 (4107) |
| Curve companion bundle fingerprint | `sha256:49263f6ab0d19d391251adca825cf2cba73c65531fb45f16a74cab3467bd85dc` |
| Sidecar, unchanged | `2.0.0-beta.1+61c6975537ea` |
| Bridge, unchanged | `2.0.0-beta.1+bffc1729a4d7` |
| Interface | Same seven tools; interface 1, bridge protocol 1 |
| Loaded host | PID 65954; fresh launch after final installation, new notice behavior verified |

[Candidate manifest](candidate-manifest.json), [installer receipt](installation.json),
[skill installation/backups](skill-installation.txt), [native loaded path/build](v2/native-ready.json),
[final public status](final-status.json). Companion manifest version 0.1.0 remains a
component label; it does not expose a new live code hash. Installed bundle bytes,
a fresh process and observed revision behavior establish the tested revision.

Three distinct companion revisions were installed through the existing installer:
r1 exposed offscreen notice positioning; r2 used the already-qualified Glyphs 4
`safeViewPort`; r3 added contrast over dense outlines. These were changed revisions,
not retries of unchanged installation. Earlier failed visual evidence is preserved
under `candidate-r1` and `candidate-r2`. Managed skill updates used ownership checks
and backups; plugin caches were not edited.

## Realistic-font results

The input is the prior P09 frozen **Dactylotype** baseline: 423 glyphs, 9 masters.
Ten real glyphs were inspected in Thin Condensed, Regular Condensed and Black
Condensed, including **57 closed paths**. Other masters/glyphs remained present.
The source is retained locally outside the committed evidence archive.
[Provenance](realistic-source.json), [source checksum manifest/native inventory](isolated-native.json).

| Final installed candidate check | Result |
|---|---|
| 30 real layers: native cubic/component counts, correct current layer | **30/30 pass** |
| Mixed `n`, `A`, `AE` and component-only `aacute` | Exact omission count; no invented component comb |
| `space`, complete direct paths and master switching | Correct empty/absent notice; no stale warning |
| Full real font after 30 inspection cases | Exact stored-data, object, hint-reference and derived-bounds hashes; dirty=false |
| `o` native edit/history on final revision | Correct comb refresh; exact whole-font Undo/Redo restoration; dirty flag remains true |
| Text mode, Font View, return to Select and zoom | Current notice/comb retained where applicable; neither remains in Font View |
| Dirty document inspection | Correct current coverage, no Save |
| Synthetic exactly 128 / 129 cubics | Complete 128 versus explicit partial 128; no fabricated total |
| Synthetic closed wraparound | Two correctly ordered cubics; exact native edit/Undo/Redo on r2, final drawing rechecked |

The independent formula audit evaluates **85,905 tooth samples across 143 captured
states**, all within 1e-9 (maximum error 3.42e-13). This includes intermediate and
final candidates; duplicated final artifact aliases are excluded. It verifies
rendered mathematics against actual native nodes, not the restoration of changed
nodes. [Math evidence index](math-proof-index.json).

![Real mixed glyph with explicit component omissions](visuals/control-A-3.png)

![Readable partial-coverage notice at 129 cubics](visuals/control-overLimit-0.png)

[Component-only real glyph](visuals/control-aacute-0.png), [Font View](visuals/final-font-view.png),
[text mode](visuals/final-text-mode.png). Dense combs remain visually crowded. The
notice explains their scope; it does not establish typographic/interpolation quality.

### Failed realistic history assertions

The first `at` trial fails exact restoration. In Regular Condensed, a native Undo
leaves `[796,-22.625]` at `[796,-23]`, and `[332.875,-22.625]` at `[333,-23]`.
A fresh disabled-companion control reproduces the **same two node changes**.
The first `s` trial also fails exact restoration. Native objects, hint references
and derived bounds remain stable, and the comb accurately follows the resulting
nodes. These facts distinguish accurate display from correct native restoration.

The `at` warm-up and five timed repetitions were stopped, not counted as passes
or replaced by read-only trials. The separate `s` check is additional evidence,
not a substitute timing series. Seven `o` first/warm-up/timed workflows pass on
r1 and a final-revision `o` recheck also passes. These do not erase either failure.
[Disabled control](candidate-r1/v2/native-undo-finding.json),
[all exact differences](facts.json).

This points to native UI/history behavior independent of Curve Inspector being
enabled. It does **not** establish the internal Glyphs root cause or prove that
all other plugins are irrelevant. Investigate this fractional restoration issue
separately before promising exact exploratory-edit recovery; the skill now states
that limitation. No new Undo framework, rounding workaround or autosave pause was
introduced. No nonempty hints occur in these fixtures; no new hint-rich coverage
is claimed. Explicit drag panning was not remeasured in this follow-up.

## Time, tokens and workflow judgment

Five r1 `o` replays: median **17.021 s**, range 16.704–17.678 s, nearest-rank p95/max 17.678 s.
Adding each initial public discovery gives median **17.316 s**, range 16.984–18.054 s.
These are display/edit/history/verification replays including UI automation waits;
fixture opening/closing, identity setup, reasoning and report writing are excluded.
They are not complete agent-task time or a matched baseline speed comparison.
Each replay uses 15 logged UI actions. Final `o` recheck is 17.365 s, one sample.

The final ten-second real-font probe excludes heavy full-font proof snapshots and
retains 7.74 s after its last measured callback. Original callback identities restore
exactly. Load averages start 13.44/23.32/21.56 and finish 11.98/22.69/21.36.

| Measurement | n | Median ms | p95 / maximum ms |
|---|---:|---:|---:|
| Comb drawing | 7 | 1.97 | 5.32 / 5.32 |
| Notice drawing | 7 | 3.44 | 10.86 / 10.86 |
| Native extraction | 19 | 2.02 | 2.53 / 2.53 |
| Background comb worker | 3 | 1.86 | 2.30 / 2.30 |
| Main-queue timer lag | 793 | 1.24 | 2.46 / 177.24 |

The measured main-queue work meets p95 < 50 ms and maximum < 200 ms in this sample.
Probe overhead was not isolated with matched on/off controls; native counts are
small. The earlier 382.49 ms tail remains unexplained. [Native timing](v2/native-timing.json).

Across the qualification harness, 35 public calls include 16 discoveries.
`get_status`: n=19, median 121.41 ms, range 106.34–1680.08 ms.
`list_documents`: n=16, median 296.75 ms, range 21.97–1156.20 ms.
Nearest-rank p95 equals each maximum. These HTTP tails are separate from drawing
callbacks. Host load and UI/verification phases vary; no runtime optimization is
justified from this mixture. Final connector checks are recorded separately.

Using the same tiktoken 0.12.0 / o200k_base method, entry text stays 817 tokens; the
focused skill moves 588→599 and the on-demand reference costs 702. The reference
adds useful context rather than claiming a token saving. It is loaded once when
curvature work needs it. Screenshots, tool orchestration and reasoning are not
included in these text counts; actual billed usage is unavailable. [Token method](tokens.json).

Agent/skill judgment: discovery **4/5**, instruction accuracy **4/5**, evidence
clarity **4/5**, recovery guidance **4/5**, workflow effort **3/5**. Exact menu guidance,
current omission notices and explicit native recovery limitations support the
improvement over P13. UI toggles still require the same actions; there is no new
MCP control. Delivery friction remains: initial viewport/contrast revisions, an
Open-dialog clipboard timeout, and case-insensitive A/a artifact collisions.
All 30 native records survived in unique timestamped acknowledgements and now have
case-safe links. [Proof index and recovery explanation](realistic-proof-index.json).
The recorded replay is preserved and a corrected case-safe replay is provided.

V1 is **historical** here: original P13 passed 14 synthetic workflows with better
public coverage evidence and fewer UI actions. It has not been freshly tested on
these realistic fractional contours. Neither a v1 real-font advantage nor a
v2 speed improvement is established; v1 code/settings remain unchanged.

## Validation, cleanup and remaining actions

**577 lean regression tests pass**, including package, installer, routing,
companion lifecycle and native-read contracts. The added extraction and metadata
refresh tests cover exact/exceeded bounds, closed wraparound and stale worker
publication. Initial sandbox-only loopback failures were rerun successfully; the
final complete suite runs without that restriction. [Final tests](pytest-final.txt).
The new synthetic generator reproduces its tested baseline byte for byte. Node/
path scan-cap branches are tested with deterministic doubles, not new 8,192-node
live timing claims. Packaged skills and configured focused skill match.

All **16 disposable trial sources**, the retained realistic baseline, original
Dactylotype files, prior reports, sidecar/bridge and v1 preserve their checksums.
All test fonts close; the original nine-glyph control remains clean with a new
connection-specific ID after relaunch. Original reporters are restored, temporary
scripts are removed, active jobs/operations are zero, and normal autosaving remains
**8 seconds**. No new crash report occurred. This does not resolve the historical
crash cause. [Final audit](final-audit.json), [public documents](final-documents.json),
[helper cleanup](helper-cleanup.json), [native cleanup](v2/native-finish.json).

The P13 skill/coverage actions are delivered. Keep **fractional native Undo
restoration**, the existing dirty-indicator issue and HTTP/queue tails as separate
investigations. No release publication, v1 fix or additional milestone was started.
