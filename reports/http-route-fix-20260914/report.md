# P07 follow-up — serve the configured MCP path directly

September 14, 2026. **Implemented, installed and verified.** The unchanged configured
endpoint `http://127.0.0.1:9680/mcp/` now returns the MCP response directly.
All 12 installed tool-call checks return one `200` response with redirect following
disabled; the equivalent baseline calls required `307 → 200` (24 HTTP exchanges
versus 12). No public tool, response schema, native editing behavior or skill was added.
The earlier [P07 latency report](../latency-investigation-20260911/report.md) remains intact.

## Implementation and tests

The only production change is `path="/mcp/"` on the existing FastMCP HTTP `run` call
in `build/milestone7/desktop/src/sidecar/glyphs_mcp_sidecar/server.py`.
Stateless HTTP, stdio, port, job lifetime and authenticated management routes remain
unchanged. The framework now redirects the alternate `/mcp` path to `/mcp/`;
that response was explicitly tested. No alias, middleware or fallback was added.

- **581 lean tests pass**, including four new route tests; the focused run passes
  22 tests. The existing old-session restart test now uses the configured path.
- The actual FastMCP ASGI transport, with a fixed service double, returns identical
  handshakes, all seven tool schemas, all seven tool outcomes and expected errors
  at the old and new canonical paths. Fractional read values are preserved.
- Initialization/cancellation notifications remain accepted. Request/session
  completion does not close process-owned jobs. These are transport/lifecycle
  regression tests, not newly executed native editing or cancellation benchmarks.
- Management authentication, remote-peer refusal, reserve/release, status,
  malformed requests and request-size limits pass. Installed management validation
  checks unauthenticated refusal without reserving or altering the live process.

[Full tests](tests-lean.txt), [focused tests](tests-focused.txt).

## Installed qualification

The live baseline and candidate each use the same pre-existing nine-glyph disposable
Font View control, discovered through the public catalog. Each has a first attempt,
one warm-up and five timed compact selection reads, plus identity, catalog,
document discovery and expected stale-document/missing-job errors. Parsed read
values and errors match exactly. The catalog and initialization JSON match exactly;
status changes only in the expected sidecar runtime ID and code hash.

A separate normal **FastMCP client** completes initialization, notification, catalog,
selection read and status requests with redirects disabled: four `200` responses
and the expected notification `202`, with no redirect. The configured Codex
connector also reports the candidate identity. [SDK trace](sdk-client.json),
[connector status](connector-status.json), [comparison audit](verification.json),
[baseline calls](baseline/calls.json), [candidate calls](candidate/calls.json).

The initial installer attempt was refused **before replacement**, because its
existing CLI guard requires Glyphs and native workers to be closed. This was an
incorrect initial assumption about sidecar-only installation, not a runtime failure.
The refusal is preserved in [install-first-refused.json](install-first-refused.json).
After confirming only the clean disposable control was open, Glyphs was quit
normally, the same candidate installed once successfully, and Glyphs relaunched.
The original exact path was reopened through its native recent-file entry.

Glyphs PID changed from 65954 to 16388, so public document IDs correctly changed.
All other returned document fields match. The control remains clean and its source
hash is unchanged. No font edit, Save, job submission, native helper installation
or autosave-setting change was performed. The native preference plist changed
across normal quit/relaunch; it is **not claimed byte-preserved**, and its individual
changes were not attributed. MCP configuration and LaunchAgent bytes are unchanged.
[UI before](ui-before.txt), [UI restored](ui-restored.txt), [installer receipt](installation.json).

## Release and preservation evidence

| Component | Installed identity |
|---|---|
| Product | 2.0.0-beta.1, installer 43; private candidate |
| Sidecar | `2.0.0-beta.1+82daa62ac227` |
| Full sidecar hash | `82daa62ac2277b49920d38c2207541841bc8294c6abf987ecddce5056c34be79` |
| Bridge, unchanged | `2.0.0-beta.1+bffc1729a4d7` |
| Host | Glyphs 4.1 (4107), `com.GeorgSeifert.Glyphs4` |

Two builds, including both bundled runtimes, produce identical manifests and full
payload fingerprints. Comparison to the P13 candidate shows only the sidecar
component changed. Every installed component matches its receipt. The P13 Curve
Inspector improvement remains installed at `49263f6ab0d19d391251adca825cf2cba73c65531fb45f16a74cab3467bd85dc`.
[Build proof](build.json), [manifest](candidate-manifest.json).

Configured global skills and plugin-cache skills, bridge, companions, protected
Dactylotype source and all 784 frozen v1 runtime/skill files retain their hashes.
No new crash report was found. The only lean source differences are the HTTP path,
updated restart test and new route regression tests. Unrelated work is excluded
from the scoped commit. No release was published.

## Timing and limits

| Compact selection HTTP read | n | Median ms | Range ms | p95/max ms |
|---|---:|---:|---:|---:|
| Baseline, redirect followed | 5 | 16.10 | 10.19–21.58 | 21.58 |
| Candidate, redirects disabled | 5 | 15.98 | 11.64–16.58 | 16.58 |

Nearest-rank p95 equals maximum with five samples. These timings exclude initial
discovery/initialization and do not represent complete task time. Those requests
remain in the logs. One-minute host load was 6.86 before versus 28.55 after; the
candidate uses a fresh host process. This is **not a matched-load speed comparison**.
The deterministic improvement is one fewer HTTP exchange per configured-path tool
call. No claim is made that the median, queue tails or occasional large HTTP stalls
are fixed. No model-token saving is claimed.

Native callback/queue timing, fresh-copy 12/100-pair P07 task trials, large-font
performance and native mutation/Undo controls were not rerun for this one-argument
route correction. Existing native regressions remain relevant but are not new
native evidence. The configured connector's first post-restart status call also
outlasted the orchestration tool's initial 30-second yield, then succeeded; its
HTTP stages were not captured and it is not included in the raw HTTP sample table.

**Decision:** retain this small route fix. Keep dirty-state restoration, fractional
native Undo behavior and larger HTTP/queue tails as separate investigations. No
cache, watcher, thread change or new Undo machinery was introduced.
