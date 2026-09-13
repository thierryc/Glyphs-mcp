# P12 — remaining checks and source checkpoint

13 September 2026. **All four outstanding P12 checks have been executed with normal autosaving enabled.** Cubic native history, the independent request-size refusal, exact stored-data restoration and native responsiveness pass. The known dependent-bounds and dirty-flag findings remain explicit. The historical autosave-associated crash is not declared fixed.

The reviewed lean source, ten managed skills and packaged mirrors, offline KDB, supporting scripts/tests and existing P12 evidence are committed locally on `lit/v2-beta` as **2157efe23caf8ecd2d2b34c6e61dd9f5cecdde3c**. Unrelated desktop/UI/website changes remain in the working tree. No release was published or installed; v1 is unchanged.

## Source checkpoint validation

The working candidate passed **561 lean regressions**. Two loopback-socket tests initially encountered sandbox permission errors and passed when run with local socket permission. A separately exported Git tree passed 558 checks but exposed three routing assertions depending on two omitted current documents; including the command reference and skill roadmap resolved all 14 routing tests. The isolated staged build then produced the **exact installed bridge and sidecar hashes**. These were scope omissions in the proposed commit, not runtime changes or erased product failures.

Only version/build values were staged from the mixed Xcode project: **2.0.0 / installer43**. Other project-file edits remain untouched. The source commit contains a **39,734,836-byte compressed archive** preserving 1,739 existing P12 evidence/dependency files (1,006,233,420 uncompressed bytes); every archive member was read back and checked against its SHA-256 manifest. Original files remain on disk. This is a scoped runtime/skills checkpoint, not a claim that the complete desktop release migration is committed or ready.

## Native environment and method

The existing Glyphs4 **PID14685** was reused; no restart or pause was needed. Native autosaving delay was **8.0 seconds at start and finish**. Host **4.1 (4107)**, sidecar **2.0.0-beta.1+61c6975537ea**, bridge **2.0.0-beta.1+bffc1729a4d7**, seven tools and current capabilities were verified. Plugin inventory matches the preceding autosave comparison, with SpeedPunk, ShowTopsAndBottoms and SpaceBar absent.

The original clean nine-glyph control remained unchanged. Each trial used two fresh disposable copies of the reproducible P12 fixture. Public discovery supplied each target ID; the existing independent native oracle performed only setup, verification and explicitly separate native-history controls. Computed geometry tolerance remains **1e-9**; unchanged/restored data, native identities and hint references require exact equality. No primary timing repetition or v1 benchmark was rerun.

## Results

| Remaining check | Expected and observed |
|---|---|
| Unique-name request-size limit | **Pass:** 10,001 distinct names refused as `invalid_request`, “glyphs must contain 1-10,000 names”; zero data/object differences |
| Cubic native Edit-menu Undo/Redo/discard | **Pass:** `slant01`, all three masters; zero application, Undo, Redo or final discard differences |
| Dedicated component bounds | **Stored data passes; derived bounds differ.** Base glyph, component transforms, identities and metadata restore exactly. Eight bounds coordinates remain stale immediately after discard, then all return to the baseline after viewing affected masters |
| Normal-autosave native timing | **Pass in this bounded sample:** 90-layer application/discard exact; callback, native-chunk and main-queue budgets pass, including 2.324 seconds after mutation |

The earlier 101-duplicate-name case tested uniqueness only. The new independent check now verifies the actual general slant count bound without creating 10,001 glyphs or submitting an edit.

Cubic Undo and Redo were genuine **Edit-menu actions** observed under the label “Glyphs MCP: Slant suggestions for 3 master layers”; the external harness only verified them. Dirty state remains **false → true → true → true → true**, so dirty-flag restoration still fails separately from exact font-data restoration. [Cubic native proof](v2/ui-slant01.json).

The separate dependent-bounds experiment used the existing native undo manager as an independent control, not as a substitute for the genuine menu test. Immediately after discard, bounds x/width differ for `automatic` and `manual` in masters `C7941642-FFB2-5D2E-B7FE-4A30A143BE40` and `5EB56BC4-5A2B-5460-ABC1-E8EE0E3B95EC`. All stored-data/object comparisons pass. Viewing `automatic` in master0 clears two differences; viewing it in master1 clears the rest. The remaining four view checks also match exactly. This supports the already documented derived-bounds refresh limitation; it does not justify new caches, forced traversal or replacement Undo. [All locations and redraw checks](v2/component-bounds.json).

## Timing, cost and assessment

| Measurement | n | Median ms | p95 ms | Maximum ms |
|---|---:|---:|---:|---:|
| Native callbacks | 22 | 9.98 | 23.20 | 25.82 |
| Native edit chunks | 10 | 10.74 | 12.30 | 12.30 |
| Bridge dispatch wait | 22 | 3.11 | 4.36 | 9.36 |
| Main-queue lag | 332 | 1.46 | 5.49 | 23.67 |

The measured callback/chunk/queue p95 values are below **50 ms**, maxima below **200 ms**. This was one bounded profile under one-minute load **3.77**, not a new full five-repetition benchmark. Five warmed status requests with instrumentation off/on had medians **85.01/88.79 ms**, ranges **82.77–115.33 / 83.13–113.04 ms**. That small noisy comparison does not isolate probe overhead precisely.

The session made **81 public calls**: 21 status, five discovery, four starts, 30 polls, three apply, three discard and 15 reads, with zero public retries/transport exceptions. HTTP latency n81: median **44.29 ms**, range **6.27–237.75**, p95 **145.26 ms**. These are round trips, not native callback times. Connector preflight is separate from the harness count. [Facts](facts.json), [call log](v2/calls.jsonl).

Payload estimate: **136,432 tokens**, tiktoken0.12.0 / o200k_base, compact sorted literal-Unicode requests plus parsed responses and three external reports once. The deliberately oversized 10,001-name refusal contributes to this aggregate. It excludes native oracle/UI output, skill context, reasoning and report writing; actual billed usage is unavailable. No per-task speed/token improvement is inferred from these heterogeneous checks.

V1 is historical and unchanged: the earlier paired P12 report recorded 14/14 exact primary applications/restorations, small median 1,091.91 ms and batch 5,652.22 ms, n5 each. This follow-up does not change that comparison or silently resolve v1's recorded limitations.

Agent delivery now includes a reproducible committed source/evidence checkpoint and completion of the four missing cases. Skills and public errors correctly support explicit targeting, compact polling and exact restoration claims while distinguishing dirty state and derived measurements. The remaining source-level autosave diagnosis is a separate investigation; successful execution here does not warrant a higher general reliability rating or removal of the crash-recovery guidance.

## Cleanup and next step

All **1,737 earlier P12 files**, **952 source files**, **34 sidecar files**, **29 bridge files**, **1,732 frozen skill files**, **730 v1 runtime files**, **54 v1 skill files** and **451 protected Dactylotype files** retain their hashes. All **eight disposable source files** and the original control's disk hash are unchanged. New applied jobs were discarded, native hooks stopped and the exact temporary script removed. No user font was saved. [Native cleanup](v2/native-finish.json), [script removal](script-cleanup.json).

This closes the previously unexecuted P12 cases, with known issues retained rather than counted as full passes. The next benchmark is **P13: curvature display**, using the companion/native UI route. It remains a separate case. Ordinary autosaving remains enabled; any crash stops the affected trial. No crash fix, new Undo system or automatic autosave suppression is included.

The same PID14685 survived the final **131.518-second post-cleanup observation** with no new crash report. This is a successful bounded normal-autosave control; prior crashes and the quiet paused comparison remain separate evidence. Final status shows zero active jobs/native operations and the sole original control font is clean. [Observation](final-observation.json), [final status](final-status.json), [documents](final-documents.json).
