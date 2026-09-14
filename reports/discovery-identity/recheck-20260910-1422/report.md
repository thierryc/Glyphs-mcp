**Report 01 recheck — 10 September 2026**

Progress is sufficient to continue to document discovery. The candidate again supplies correct release and independent runtime identities, and its connection-specific entry handles the actual legacy seven-tool installation. No candidate was installed or published. Report 02 will use the unchanged installed baselines, with explicitly version-matched skill controls.

The fresh build reproduces sidecar `2.0.0-beta.1+9000d1765aaf` and bridge `2.0.0-beta.1+15e6419bc81e`, each exactly matching its complete SHA-256 in the [manifest](build.json). Initialization reports `2.0.0-beta.1`; status retains product 2.0.0, beta 1, installer 43, seven tools, five jobs and bridge protocol 1. The native host is `com.GeorgSeifert.Glyphs4`, 4.1 (4107). These remain initialization-time file fingerprints, not continuous or in-memory attestation. All 30 snapshotted implementation files were unchanged during the recheck.

**387 Python tests passed, one Copilot CLI test skipped; 169 Swift tests passed.** Identity caching, unavailable evidence, managed skill updates/conflicts/backups, invocation/routing and relevant lean regressions were repeated. See [Python](python-tests.log) and [Swift](swift-tests.log) logs. Existing focused skills and editing/Undo/discard mechanisms were not changed by this test.

The configured global entry still requires unavailable typed-prototype tools. This preserved configuration failure does not count as a pass. The separate candidate entry control inspected only the actual `glyphs_mcp_server` connection's seven tools, called its advertised `get_status`, accepted its `0.1.0` legacy identity and found bridge/worker available. It required no `apiMajor == 2`, no font save, and no unavailable call. The [actual connector response](agent-status.json) records this control; automated routing cases pass in the regression log. V1 was not restarted for this connection recheck.

Times are milliseconds: **median (minimum–maximum); p95**, excluding the first attempt and warm-up.

| Measurement | Isolated installed-source baseline | Isolated candidate |
|---|---|---|
| Verified connection, n=5 | 25.911 (24.410–27.090); p95 27.090 | 25.451 (24.470–26.151); p95 26.151 |
| Status HTTP round trip, n=20 | 10.382 (8.997–13.886); p95 13.779 | 10.550 (9.109–14.112); p95 13.154 |
| Dispatch wait, n=30 | 2.704 (2.316–2.880); p95 2.833 | 2.692 (2.206–4.941); p95 2.914 |
| Native callback, n=30 | 0.022 (0.016–0.073); p95 0.056 | 0.024 (0.015–0.055); p95 0.049 |
| Bridge HTTP, n=28 | 3.736 (3.298–19.451); p95 4.166 | 3.716 (3.161–18.160); p95 5.981 |
| Sidecar assembly, n=28 | 0.138 (0.108–0.623); p95 0.332 | 0.145 (0.118–0.322); p95 0.193 |

First useful connection evidence was 137.398 ms for baseline and 124.385 ms for candidate. Each isolated run made 46 recorded calls: 8 initializations, 8 catalogs, 28 status calls and 2 document reads; all succeeded without retries. Native document listings stayed empty. The one-minute load was 12.66→13.49 and 14.49→15.09 respectively on 10 logical CPUs. Fixed baseline-first order and differing host load limit speed comparisons. No extra uninstrumented overhead run was added; the preceding report's bounded controls remain the only overhead estimate. Probe wrappers add clock reads and an in-memory append, with output flushed afterward.

The unchanged foreground Beta 1 endpoint returned a status median of **42.538 ms**, range **23.068–52.153 ms**, p95 **48.675 ms** across 20 requests. That is below the 50 ms proxy threshold in this sample, versus 57.539 ms in the previous follow-up and 71.470 ms in the original report. It does **not** establish a latency fix: installed code did not change and load varies. Native queue/callback samples passed 50/200 ms thresholds only in isolated, plugin-free Cocoa workers. Foreground native callback time remains unverified. Both isolated builds negotiated MCP 2025-11-25; the original client used 2025-06-18. No bridge protocol changed. There were no mutations, so application, cancellation, Undo/Redo, discard, post-mutation probes and typographic quality are inapplicable.

One preservation assertion failed and is retained: the v1 plugin skill cache went from **52 files to zero** between snapshots. The task performed no cache mutation, and the cause is unestablished. The other **894 files**, installed runtime code, global entry, receipt and application metadata were unchanged. The [raw preservation result](preservation/preservation.json) deliberately remains `filesUnchanged: false`; before/after inventories show the exact scope. For Report 02, use a preserved version-matched v1 skill copy and record this configuration issue. Do not silently reconstruct a cache.

| Agent judgment (1–5) | Candidate control | Reason |
|---|---|---|
| Discovery | 4 | Correct per-connection branch, but manual selection remains necessary with the global conflict. |
| Instruction accuracy | 4 | Legacy gate works; broad focused-family execution remains outside this check. |
| Evidence clarity | 5 | Release, host and both complete hashes agree with the fresh manifest. |
| Recovery guidance | 4 | Concrete paths and recovery actions; real installer replacement UI still unverified. |
| Workflow effort | 4 | Normal catalog/status sequence; no invented tool or save workaround. |

The configured global skill remains **1/5 for interface accuracy**. These are single-agent judgments with implementation familiarity, not blinded scores. Candidate identification is more effective; speed is essentially unchanged in the controlled comparison. Remaining priorities are disposable-profile installer click-through, foreground candidate qualification, then a bounded scheduling investigation if live tails persist. The cache disappearance requires checking setup state before v1, not changing the measured runtime. No architecture optimization is justified by these timings alone.

The [previous follow-up](../report.md) and original Beta 1 report retain their original measurements. Evidence: [specification](test-spec.md), [facts](facts.json), [calls](calls.jsonl), [isolated baseline](native-baseline/facts.json), [isolated candidate](native-candidate/facts.json), [live baseline](live-baseline/v2-facts.json).
