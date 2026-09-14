**Report 01 follow-up — lean v2 discovery, identity and skill setup**

The candidate fixes release identification and provides a usable connection-specific entry route. Its installer now reports preserved skill conflicts instead of silently skipping them. **It is built and qualified separately; installed Beta 1 and the original comparison remain unchanged. Report 02 remains paused.**

The final candidate comes from `build/milestone7/desktop`, retaining product **2.0.0 Beta 1, installer build 43**. It is not a new published release. The unsigned app is [here](../../build/discovery-identity-xcode/Build/Products/Debug/Glyphs%20MCP.app); its deterministic [payload manifest](candidate-manifest.json) identifies the qualified components. No candidate app or plugin was installed or opened in the foreground editor.

| Identity | Installed Beta 1 | Candidate |
|---|---|---|
| MCP initialization | `0.1.0` | `2.0.0-beta.1` |
| Product release in status | Absent | Version, release version, beta channel/number and build 43 |
| Sidecar / bridge versions | `0.1.0` / `0.1.0` | `2.0.0` / `2.0.0` |
| Tool interface | Inferred from catalog | `glyphs-mcp-sidecar`, revision `1` |
| Bridge / control protocol | `1` / `1` | `1` / `1` |
| Public tools / job kinds | 7 tools, jobs inferred | Same 7 tools, 5 declared job kinds |
| Sidecar runtime ID | Absent | `2.0.0-beta.1+9000d1765aaf` |
| Bridge runtime ID | Absent | `2.0.0-beta.1+15e6419bc81e` |
| Native application | Worker path only | `com.GeorgSeifert.Glyphs4`, 4.1, build 4107 |

Sidecar SHA-256: `sha256:9000d1765aaf37a931ab0b73945795e3f8650943b4aa7201398af21f79504443`. Bridge SHA-256: `sha256:15e6419bc81e8250b7aa275eaa9fc95fe3dc520b3e4a227deebfca060b1b196a`. Each exactly matches its own manifest value. These are **initialization-time file fingerprints**, not proof of all in-memory code or a continuous file monitor. The helper excludes generated caches and uses sorted relative paths, independent of installation paths and timestamps. Expected hashes stay in the external manifest/receipt; signing/stapling refreshes them through the existing release helper. Missing/unreadable evidence stays unavailable.

The actual jobs are `width_delta`, `spacing`, `kerning_collision`, `start_nodes`, and `slant`. Master compatibility remains outside this installed Beta 1 catalog. Editing, native Undo, Redo and discard implementations were left untouched; their relevant regression checks pass. This connection test makes no fresh native font-restoration claim.

The configured global entry’s original failure was preserved and rechecked: it remains incompatible. It requires `get_server_info` and `apiMajor == 2`. No unavailable call was sent and no font was saved to address that mismatch. The separately labelled candidate entry begins with the specific connection’s catalog, handles current and legacy lean responses, directs v1 to available v1 instructions, and rejects unknown interfaces. The [routing evaluation](routing-evaluation.json) records eight successful captured/synthetic instruction cases and the preserved configured-skill failure. It is a single-agent assessment, not a blinded model benchmark or a fresh simultaneous live v1 test. V1 was not restarted.

The installer returns `installed`, `current` and `preserved-conflict` entries with paths. Unchanged owned skills refresh automatically; exact current copies are identified without silently adopting unowned skills; modified or unowned conflicts stay intact. The completion state surfaces those conflicts and offers **Replace preserved skills (backup)** using the existing replacement path. A same-second backup-name collision found during testing was fixed in the existing backup helper; the replacement test verifies the preserved user contents. The candidate’s `$glyphs` invocation is explicit, its short description is complete, and its original invocation-policy settings are retained. Plugin caches were not edited. The focused families retain their current workflows and were not broadly migrated.

Recovery guidance now separates wrong skill, wrong server, stopped bridge, unavailable worker, occupied port and older loaded processes. It names the configured endpoint, **Edit → Glyphs MCP Server…**, and both Glyphs bundle identifiers. Desktop status compares each reported component fingerprint with its receipt independently and distinguishes a mismatch from unavailable legacy evidence. It does not restart anything automatically.

Measured times below are milliseconds, shown as **median (minimum–maximum)**. The final pair used fresh isolated native processes, empty document sets and the same private runtime. Baseline ran first, candidate second. The one-minute host load was 11.26 → 11.56 for baseline and 11.07 → 12.03 for candidate on 10 logical CPUs. These loads are recorded observations, not controlled CPU utilization.

| Measurement | Baseline | Candidate | p95 baseline / candidate |
|---|---|---|---|
| Verified connection, n=5 | 26.854 (26.045–27.175) | 25.235 (24.087–27.721) | 27.175 / 27.721 |
| MCP status HTTP round trip, n=20 | 10.734 (9.485–15.925) | 11.299 (9.409–16.811) | 15.491 / 15.516 |
| Bridge dispatch waiting, n=30 | 3.008 (2.282–3.327) | 3.165 (2.385–3.383) | 3.312 / 3.361 |
| Cocoa callback execution, n=30 | 0.022 (0.014–0.063) | 0.022 (0.017–0.051) | 0.055 / 0.051 |
| Bridge HTTP, n=28 | 4.120 (3.332–18.021) | 4.287 (3.450–17.860) | 4.427 / 5.211 |
| Sidecar assembly, n=28 | 0.141 (0.107–0.230) | 0.140 (0.103–0.331) | 0.193 / 0.261 |

First useful connection evidence took 135.7 ms for baseline and 131.9 ms for candidate. These first attempts are excluded from the five measured repetitions. The candidate’s median connection was about 1.62 ms faster in this final pair. The earlier verification-pilot pair favoured baseline by 0.93 ms; these bounded samples do not demonstrate a consistent speed improvement. The instrumentation reports actual Cocoa callback execution in the isolated host, including the Python bridge callback. It is not the duration of a native edit or rendering pass. Bridge HTTP includes queue waiting, serialization and transport; sidecar assembly is total service time minus bridge HTTP. Component medians must not be added as if they belonged to one request.

The final isolated queue and callback samples satisfy p95 below 50 ms and maximum below 200 ms. **Foreground editor responsiveness is still unverified for the candidate.** No mutation occurred, so post-mutation sampling, Undo/Redo, cancellation, geometry and typographic quality are inapplicable here.

The unchanged installed endpoint at `http://127.0.0.1:9680/mcp/` produced a fresh status-request p95 of **57.5 ms**, maximum **65.7 ms**, and median **45.4 ms** over 20 requests. Its verified-connection median was 38.0 ms. The request-latency threshold exceedance is reproducible; its native cause remains undetermined because that installed process was not instrumented or restarted. The isolated baseline also lacks the foreground editor’s other plugins and UI event traffic.

Uninstrumented controls had status medians of 10.144 ms (baseline) and 10.329 ms (candidate); the preceding instrumented pilot pair had 10.126 ms and 10.560 ms respectively. These separate bounded runs estimate total probe overhead plus run variation, not an exact overhead subtraction. The native waiting/callback wrapper adds three clock reads and an in-memory append; timing files are flushed after serving. The final verified pair is retained separately from pilot controls. All raw samples are available below. Both follow-up builds negotiated MCP `2025-11-25`; original Report 01 negotiated `2025-06-18` with the older client SDK. Bridge protocol remains `1` in both, and no transport implementation was upgraded. Cross-report timing differences therefore include client/environment differences.

There is no evidence here to justify a status cache, polling service or thread redesign. A separate optimization investigation should profile enqueue/start/end inside a disposable **foreground** Glyphs setup under matched plugin/UI load, then correlate it with public request timing. The isolated callback and assembly costs are too small to explain the live tail by themselves. UI scheduling or other process load is a hypothesis, not a finding.

Each final controlled implementation run made 8 MCP initializations, 8 catalog calls, 28 status calls and 2 document-preservation reads (46 recorded calls). There were zero MCP failures, retries, font mutations or manual UI actions in those runs. The first candidate harness attempt lost its sidecar timing file on SIGTERM; it is retained as incomplete evidence and excluded from timing conclusions. Graceful collection was corrected in the temporary harness. The execution notes also retain the sandbox socket restriction, the newly exposed backup collision and a corrected missing test import. A CLI invocation missing its required endpoint was corrected before live requests; it is not a server failure.

| Agent assessment, 1–5 | Original matched Beta 1 route | Candidate matching control | Observed reason |
|---|---|---|---|
| Discovery | 4 | 4 | Per-connection branches are clear, but the incompatible global entry remains installed and requires explicit selection/replacement. |
| Instruction accuracy | 4 | 4 | Version gates and `$glyphs` invocation are corrected; broad focused-family execution is outside this report. |
| Evidence clarity | 3 | 5 | Initialization, release, host and independent expected/runtime hashes agree without inferring product version from `0.1.0`. |
| Recovery guidance | 3 | 4 | Paths, ports, panel and separate process recovery are concrete; real installer click-through has not been exercised. |
| Workflow effort | 4 | 4 | Seven public tools and normal status workflow remain; resolving a preserved user conflict still needs one deliberate action. |

These scores are reasoned single-agent judgments, influenced by familiarity with the implementation and fixed baseline-first order. The configured global skill still scores **1/5 for interface accuracy** until the user chooses a matching skill or replaces the conflict. Smoothness improved most in interpreting evidence and explaining recovery; no typographic quality conclusion follows from connection discovery.

Validation completed: **387 Python tests passed, one Copilot CLI test skipped; 169 Swift tests passed; unsigned app build and structural verification passed; two full payload builds were identical; all 10 shipped skills were synchronized.** Tests cover managed upgrades, no-change repeats, unowned/user conflicts, backups, legacy/unavailable identities, signing-byte changes, cached fingerprints, receipt propagation, invocation metadata and routing instruction contracts. No candidate installer was run against the real home directory; real UI replacement remains unverified.

All **946 snapshotted installed-code/skill files**, receipt and application metadata remain unchanged. Native workers and the installed v2 endpoint had empty document listings before and after. The old report was not rewritten; its [file checksums](baseline-report-checksums.json) are recorded. Only the intended source files changed relative to the initial dirty worktree snapshot. Original v1-versus-v2 measurements and unrelated work remain preserved.

The candidate completes connection identification more effectively because it exposes the release and independent component fingerprints and provides honest skill conflict feedback. Speed is effectively similar in the isolated comparison; the live p95 issue remains open. Priorities after review are: exercise the explicit conflict-replacement UI in a disposable user profile, qualify the candidate in a disposable foreground Glyphs setup, and investigate the live scheduling tail before proposing a targeted optimization. Resume Report 02 only after this improvement review.

Evidence: [test specification](test-spec.md), [structured facts](facts.json), [timestamped calls](calls.jsonl), [verified baseline](native-baseline-verified/facts.json), [verified candidate](native-candidate-verified/facts.json), [native samples](native-candidate-verified/bridge-timings.json), [sidecar samples](native-candidate-verified/sidecar-timings.json), [live Beta 1 repeat](installed-baseline-repeat/v2-facts.json), [skill checksums](skill-checksums.json), [preservation](preservation/preservation.json), [validation logs](validation-logs/), and [original Report 01](/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2/reports/v1-v2/01-connection-routing/report.md).

Recheck the saved evidence with the [offline validator](validate_results.py); the latest [validation result](validation.json) records exact identity, timing, call-scope, link and preservation checks.
