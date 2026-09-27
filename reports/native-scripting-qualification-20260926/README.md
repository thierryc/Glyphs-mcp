# Native scripting qualification — September 26, 2026

The six focused fixes are implemented, synchronized, built and installed. Controlled native recovery and installed Codex text workflows pass on disposable fonts. The final candidate passes 2,231 Python regressions, 67 isolated native scripting checks, four retained typed native suites, and the complete 60-process benchmark matrix. This is local candidate qualification, not publication or an unconditional completion claim: the limitations and open interaction observation below remain explicit.

One native script capability (`script.native.v1`), twelve tools and the 4,096 eligible-surface limit remain. No alternative execution mode, layer snapshot system, backup subsystem or higher limit was added. An in-scope edit request authorizes Run; source review remains optional. Saving retains its separate authorization.

## Six fixes and integration corrections

| Finding | Implemented behavior / evidence |
|---|---|
| Keep left waiting tasks blocked | Completed script records reconcile in reads/reconnects. Waiting tasks reference the original `blockingWorkflowId` and its Keep/Save/Restore choices, without typed Undo. Restoration supplies its authoritative fresh binding. Failed/cancelled partial execution remains unresolved. Focused tests cover Keep, Save, Restore, reconnect, duplicate/stale actions and partial failures. |
| Capacity preceded eligibility | Bulk iteration is lazy; eligibility and deduplication precede counting. The 4,097th eligible surface fails. A 4,097-glyph font with one eligible background passes; 4,096 eligible surfaces pass. Explicit request limits remain. Skips retain an exact count and at most ten examples. |
| Content-only backgrounds omitted | Native image, attributes, user data and explicit metrics keys count as content. Missing/empty backgrounds remain skipped without creation. Native fixtures verify these content types; path filtering stays in the flip callback. |
| Compact reads erased details | Card evidence caches are bound to workflow, job and request fingerprint. Omission preserves matching evidence; explicit empty values replace it. Open details refresh once at completion. Source/output/errors remain text. Mock-host tests cover cache transitions and completion refresh; installed text reads retrieve exact source. |
| Result polling rehashed the font | One volatile five-second memo per active restoration offer; reads still refresh live document state. Save, baseline/path change, reconnect and completion invalidate it. Run/Restore perform authoritative checks. Ten reads, expiry, invalidation and overwritten-baseline rejection pass focused tests. |
| Preparation waited for the tick | A read exposes an already-ready script immediately; preparation/polling still cannot execute code or save. Typed automatic application remains unchanged. |

Actual installation exposed two additional defects in the same lifecycle: old applied typed records needed ordinary read reconciliation, and progress-only script revisions made Cancel tokens stale before dispatch. Both were corrected and covered by regressions. Cancellation now survives progress updates while completion and material state changes still invalidate it. Restored bindings also retain the font family for the conversation heading.

Three historical applied typed records were reconciled as interrupted/unverified after their native history had disappeared; they were not replayed or represented as restored. No original-font edit was performed.

## Installed editor and Codex evidence

Tests used Glyphs 4.1 (4107), macOS 26.7.1 arm64, and the installed MCP connection in this Codex conversation. Disposable real-font copies contain 423 glyphs and nine masters. The original Dactylotype package is open and clean after testing, with unchanged saved hash `sha256:38e15d52b86817f7e3273ae01d64fbde6c2656abff2c713a70c1b3ef66bc13be`.

| Test | Observed result |
|---|---|
| Fractional path editing, both formats | Regular `o`, node 0: `(816.875, -19.953)` → `(824.125, -23.453)`. Duplicate dispatch did not repeat the edit. Exact layer/path reads verify the targeted change. |
| Explicit spacing, both formats | H/n/o shifted by 12.5 units and advances increased by 20.75, giving 12.5 left and 8.25 right spacing. Target widths, outline controls and metric keys were checked; Restore matched the recorded baseline. This is explicit spacing, not the typed optical-spacing algorithm. |
| Kerning, both formats | Whole script with `targets:[]` set Regular A/V to −60.25 and T/o to −45.5. Exact stored pairs were read back; restoration recovered the baseline pairs. |
| Saving | Dirty Save and run returned one verified native Save receipt before execution. Clean runs produced no wrapper Save receipt. Save As to new `.glyphs` and `.glyphspackage` destinations passed; manual editor-save continuation passed. The isolated adapter tests count zero clean / one dirty calls; editor method-level Save calls were not independently instrumented. |
| Whole-font restoration | Reload replaced later manual width edits, cleared native Undo (also inspected in editor UI), returned a fresh document binding and left the font clean. Source hashes showed restoration did not save. |
| Earlier workflow blocker | Package spacing waited behind path editing, identified the earlier workflow, and prepared against the new binding after Restore. Keep-to-next behavior passed native and installed workflow observations. |
| Stale review | A manual edit after preparation invalidated Run before execution; fresh preparation then used authorized Save and run. |
| Partial failure | A callback that changed content then raised retained its partial changes and blocked following work until settled. A controlled Run→failure→Restore sequence passed. |
| Cancellation on final installed candidate | 23 of 66 callbacks completed; Cancel stopped remaining targets, preserved partial-outcome evidence, and Restore succeeded. No force-stop of a running callback is claimed. |
| Saved baseline overwritten | Manual editor Save changed the baseline. The old restoration offer became unavailable and supplied no Restore action. Keep settled the workflow. |
| Document closed | Closing a disposable modified document without saving made restoration unavailable. Reconciliation did not replay code; Keep settled the remaining workflow. |
| Actual sidecar reconnect | After one width edit `601.25 → 603.75`, the sidecar was stopped/started through its established controller. The original workflow became interrupted with Check result, retained the same job/output and still read 603.75. Check result recovered Applied; Restore returned a fresh binding and width 601.25. |
| Optional details / text actions | `include_review=true` returned exact source, parameters and output. Ordinary reads remained compact. Revision-bound text actions were used through the installed Codex connection; card caching/rendering was tested in the mock host, not visually in an installed card client in this pass. |

The editor work spanned installation iterations while correcting the discovered integration defects. The final identity was then used for Save As, cancellation, overwritten-baseline, closed-document and reconnect tests, plus the complete fresh-process benchmark and isolated native checks. Successful execution is never presented as wrapper verification of arbitrary intended effects; the targeted reads and native assertions are separate evidence.

Single installed Codex dispatch observations were 4.913 s for the path Run call and 5.615 s for the manual-save/kerning dispatch. These are client/tool observations (n=1 each), not a latency distribution or direct-loop timing. They exclude time spent reasoning and interacting manually. See [installed editor evidence](installed-editor-evidence.json).

## Performance

Every number below is **median (minimum–maximum)** across five runs. The final matrix is [raw evidence](final/benchmarks/) and [machine-readable summary](final/benchmark-summary.json). The earlier root-level benchmark run is preserved as historical evidence from the preceding candidate, not pooled into these numbers.

The direct baseline measures only the callback loop with Undo disabled and fractional precision enabled, excluding setup/cleanup. Native total includes target/syntax preparation, authorized Save through the standalone fixture writer, guarded dispatch, batching and completion polling. Save is a **subset** of dispatch/execution time; do not add those columns twice. Verification/restoration are reported separately. These are different workloads; their ratio describes wrapper overhead on these fixtures, not a universal slowdown or speedup against earlier scoped benchmarks.

| Backgrounds × contours | Direct callback loop, s | Native workflow, s | Workflow / loop |
|---|---:|---:|---:|
| 100 × 1 | 0.010 (0.010–0.012) | 0.316 (0.312–0.321) | 30.2× |
| 1,000 × 1 | 0.103 (0.101–0.104) | 0.576 (0.569–0.852) | 5.6× |
| 4,096 × 1 | 0.418 (0.411–0.435) | 1.866 (1.849–1.919) | 4.5× |
| 100 × 12 | 0.111 (0.110–0.165) | 0.601 (0.599–0.628) | 5.4× |
| 500 × 12 | 0.560 (0.542–0.573) | 1.109 (1.094–1.119) | 2.0× |

| Backgrounds × contours | Preparation, s | Save within dispatch, s | Dispatch through result, s | Verification, s | Restoration, s |
|---|---:|---:|---:|---:|---:|
| 100 × 1 | 0.066 (0.061–0.067) | 0.050 (0.048–0.067) | 0.251 (0.250–0.255) | 0.001 (0.000–0.001) | 0.007 (0.006–0.185) |
| 1,000 × 1 | 0.101 (0.098–0.122) | 0.053 (0.050–0.056) | 0.474 (0.469–0.730) | 0.000 (0.000–0.001) | 0.024 (0.021–0.037) |
| 4,096 × 1 | 0.273 (0.270–0.282) | 0.066 (0.062–0.123) | 1.591 (1.577–1.650) | 0.000 (0.000–0.000) | 0.080 (0.076–0.087) |
| 100 × 12 | 0.091 (0.072–0.121) | 0.125 (0.087–0.245) | 0.514 (0.507–0.533) | 0.000 (0.000–0.001) | 0.009 (0.009–0.010) |
| 500 × 12 | 0.088 (0.075–0.094) | 0.057 (0.051–0.064) | 1.022 (1.017–1.025) | 0.000 (0.000–0.000) | 0.022 (0.021–0.023) |

| Backgrounds × contours | Direct peak RSS, MiB | Native peak RSS, MiB | Longest scheduled chunk, ms |
|---|---:|---:|---:|
| 100 × 1 | 167.2 (166.4–169.6) | 169.2 (168.1–169.7) | 8.47 (7.93–8.82) |
| 1,000 × 1 | 187.7 (178.8–190.1) | 191.1 (189.6–193.5) | 10.05 (10.03–13.48) |
| 4,096 × 1 | 202.1 (174.4–212.4) | 206.3 (195.1–324.8) | 14.04 (13.00–15.00) |
| 100 × 12 | 170.4 (170.0–171.4) | 172.0 (171.3–173.6) | 11.21 (10.94–11.54) |
| 500 × 12 | 196.1 (195.8–198.6) | 198.5 (198.2–200.2) | 11.52 (11.23–16.25) |

The largest measured bulk scheduled chunk was 16.25 ms. The 4,096-surface native peak RSS range was 195.1–324.8 MiB, with a 206.3 MiB median. Retain the range; the high-water variation is not evidence for a tighter memory bound. The results support keeping the existing 4,096 limit, not increasing it.

### Real-font path, spacing and kerning

Five fresh native processes per file format, each running the three tasks sequentially, gave 30 task executions. Each task verified targets and unchanged controls, restored the saved version, checked clean state and fresh bindings, and preserved exact fractional geometry. Path/kerning started clean; spacing exercised one authorized dirty save.

| Format / task | Preparation, s | Save within execution, s | Execution + polling, s | Verification, s | Restoration, s |
|---|---:|---:|---:|---:|---:|
| .glyphs / path | 0.088 (0.084–0.091) | 0.000 (0.000–0.000) | 0.194 (0.184–0.197) | 0.073 (0.073–0.158) | 0.048 (0.047–0.101) |
| .glyphs / spacing | 0.027 (0.025–0.030) | 0.064 (0.058–0.128) | 0.159 (0.105–0.249) | 0.066 (0.064–0.073) | 0.051 (0.047–0.058) |
| .glyphs / kerning | 0.028 (0.027–0.028) | 0.000 (0.000–0.000) | 0.141 (0.115–0.149) | 0.115 (0.107–0.170) | 0.076 (0.055–0.077) |
| .glyphspackage / path | 0.165 (0.146–0.199) | 0.000 (0.000–0.000) | 0.433 (0.162–0.548) | 0.063 (0.062–0.066) | 0.124 (0.099–0.130) |
| .glyphspackage / spacing | 0.107 (0.089–0.113) | 0.130 (0.119–0.435) | 0.673 (0.614–0.983) | 0.062 (0.061–0.159) | 0.102 (0.097–0.110) |
| .glyphspackage / kerning | 0.090 (0.079–0.103) | 0.000 (0.000–0.000) | 0.250 (0.203–0.259) | 0.081 (0.078–0.085) | 0.106 (0.095–0.121) |

| Format / task | Cumulative peak RSS, MiB | Longest scheduled chunk, ms | Save calls in each of five runs |
|---|---:|---:|---|
| .glyphs / path | 230.3 (229.0–234.1) | 4.05 (3.78–4.37) | 0, 0, 0, 0, 0 |
| .glyphs / spacing | 262.1 (261.7–266.0) | 9.46 (8.47–10.79) | 1, 1, 1, 1, 1 |
| .glyphs / kerning | 295.2 (294.1–298.0) | 4.78 (4.56–6.54) | 0, 0, 0, 0, 0 |
| .glyphspackage / path | 229.7 (228.5–230.8) | 33.63 (29.02–38.58) | 0, 0, 0, 0, 0 |
| .glyphspackage / spacing | 261.2 (259.7–262.4) | 32.24 (26.27–39.14) | 1, 1, 1, 1, 1 |
| .glyphspackage / kerning | 293.5 (291.7–294.4) | 32.20 (26.38–33.86) | 0, 0, 0, 0, 0 |

Bulk RSS is isolated per fixture/mode and sampled before restoration. Real-task RSS is a cumulative process high-water mark across the three tasks, not isolated task memory. The longest scheduled chunk measures wrapper callbacks only; preparation, hashing, direct-loop work, synchronous Save/reload and full event-loop latency are not all covered by that number. No frame-rate or maximum responsiveness guarantee follows. CLI startup, HTTP/model latency and visual inspection time are excluded. Native benchmark saves use `GSFont.save` in a standalone GSDocument harness; actual NSDocument saving/restoration is qualified separately above. Some live editor checks overlapped benchmark execution; this was not an exclusively idle machine.

## Verification and identity

- Full Python suite: **2,229 passed, two skipped, two socket cases deselected**; those two socket cases passed separately with appropriate local socket access. Total distinct passed cases: **2,231**. [Full log](regressions.log), [socket log](socket-regressions.log).
- Final built scripting checks: **30 .glyphs + 30 .glyphspackage + seven focused native checks**, all passed. [File](native-glyphs.json), [package](native-glyphspackage.json), [focused](native-focused.json).
- Retained typed native suites: exact Undo/Redo in three masters, outline apply/discard/partial rollback/native Undo, spacing apply/discard, and kerning apply/discard all passed. The two legacy spacing/kerning harnesses first hit the production open-Undo-group guard because fixture construction stayed inside one CLI event. Their setup now finishes those fixture groups before dispatch; the production guard is unchanged. Both initial failures and corrected reruns are retained under `typed/`.
- Skill synchronization and package checks passed: **11 skills, twelve public tools, arm64 and x86_64 runtime payloads**. Canonical guidance and the packaged mirror match. Local routing files remain untracked and excluded. No installed plugin cache edits, commits or publication.
- Source package files match the built payload; build and installed hashes match. The builder's two generated panel release fields are validated separately. [File identity evidence](identity-files.json), [installation receipt](installation.json), [loaded status](runtime-status.json).

| Component | Built = installed = initialization-time loaded fingerprint |
|---|---|
| Bridge | `sha256:ff5f9e0e962bca7aaf2bbf73783417dc1c79e5caa87983024ce545db900bc24e` |
| Sidecar | `sha256:c5fdc08d1557a0021c7a4443a3bfb93c7ddca31b3a9dcbc4e2d835c89e311817` |

The established installer updated only MCP under the user's explicit installation/relaunch authorization, preserving copied installation mode, runtime, port/autostart settings and companions. Glyphs was relaunched, then the actual connection advertised `script.native.v1` and twelve tools. Curve Inspector remained `sha256:49263f6ab0d19d391251adca825cf2cba73c65531fb45f16a74cab3467bd85dc`; Reference Inspector remained `sha256:480a7fd1dfe54857673a21a7ee6066c42d7ca1e2e937dcef790ae3362fcca0e7`. These are file fingerprints at initialization, not an in-memory code attestation.

## Explicit limitations and follow-up

1. Failed/uncertain native Save outcomes are covered by fault-injected regression tests. No disk failure or ambiguous NSDocument completion was deliberately induced in the installed editor. That stricter live fault gate remains unperformed.
2. Automatic approval review rejected a live Save As probe using an existing disposable destination because it could overwrite a font file. The action was not executed or retried. Existing-destination rejection remains covered by automated tests; its live probe is incomplete.
3. Several longer manual test sequences acquired recorded Run/Keep actions that were not dispatched by the assistant in those sequences. Their origin could not be established; a user clarification remains unanswered. The evidence retains these transitions without attributing them to a user, another client or automatic execution. Controlled immediate Run→result→Restore and sidecar reconnect sequences passed. This unexplained interaction remains open and prevents an unconditional installed-client sign-off.
4. Native typed path Undo normalizes unnamed node metadata from `null` to an empty string. This separate follow-up from the prior real-task review remains deferred; this milestone makes no typed snapshot change or byte-exact metadata claim.
5. An installed Codex **text** workflow was exercised. Current card rendering/cache behavior passed the mock-host suite; no new installed Claude/Cursor visual card claim is made. The Codex connection's cached tool descriptions predate the runtime update, although current arguments and capability behavior worked. Refreshing another client's plugin cache was outside scope.

The implementation and controlled core editor gates are complete. The explicit live fault/overwrite probes and unattributed interaction observation above are not silently marked passed. No persistent crash recovery, protection from script filesystem effects, guaranteed recovery after external baseline changes, or new capacity guarantee is claimed.
