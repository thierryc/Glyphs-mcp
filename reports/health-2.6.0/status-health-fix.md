# Status and health deadlock correction — 2026-11-05

The user reported a running listener, a blue empty connection icon, a status
request timeout, and unavailable Glyphs Health. A direct passive bridge request
still answered while the sidecar did not. A short native sample and a Python
thread dump identified task-history synchronization holding the job/service
locks while waiting for the workflow store; concurrent fast intake held the
store while waiting for jobs. Blocked requests exhausted the sidecar request
executor, so even cached status could no longer be served.

Changes:
- Order history and expiration locks consistently: workflow store before service
  and jobs. Add deterministic regressions for history change and cleanup during
  intake, preserving existing lifecycle and recovery checks.
- Serve both authenticated companion status and the public get_status cache
  without depending on execution-worker availability.
- Let background health publish fresh evidence when the job store is busy,
  explicitly retaining stale activity instead of blocking the collector.
- Share the ready/active/unavailable color policy across Setup and the title bar.
  A failed initial observation now displays Status unavailable rather than
  implying that process presence confirms readiness.

Qualification:
- 139 focused tests passed, including deadlock and status/health performance.
- Added test_health_status_performance.py: 100 public/companion requests with
  four concurrent readers while the sole execution worker is occupied; p95 must
  remain below 100 ms, and both routes must return the same session health.
- Added a locked-job-store health-publication performance check; health remains
  fresh while activity is explicitly stale.
- Existing blocked-native-scheduler test retains its 100-request, zero-native-
  callbacks gate. No font mutation or job reconciliation is used by these reads.
- Added scripts/benchmark_health_status.py for repeatable read-only measurements
  of the installed Glyphs bridge and companion endpoint. It records exact code
  identities, health evidence and per-endpoint latency, and exits unsuccessfully
  on unavailable/stale health, errors or a failed latency gate.
- Installed measurement: 100 requests per endpoint, four clients, zero errors;
  bridge p95 24.18 ms, companion p95 31.02 ms. Both reported the same bridge
  session and available health. See status-health-installed-performance.json.
- Repaired only the verified managed sidecar under installation/control locks
  after confirming zero active native operations and zero active durable jobs.
  The captured deadlock prevented its control reservation from responding.
  The previous sidecar was retained by InstallationTransaction. Glyphs remained
  open, with its bridge session and native recovery unchanged by this repair.
- Installed the rebuilt companion after verifying source, app and copied bundle
  hashes, retaining the previous app. Visually verified green checkmark circles
  in both Setup and the title bar, Ready, and available Glyphs Health. Caution
  accurately reflects an authoritative macOS memory-pressure warning separately
  from the connection state. No warning was synthesized or pressure injected.

The frozen serial release gate passed in 477 seconds on the corrected source:
3,458 Python tests passed (3 skipped), 327 native desktop tests passed,
documentation built, deterministic payloads matched, packaged arm64/x86_64
runtime checks passed, 14 managed skills/22 public tools were verified, and
unsigned candidate validation and the input-freeze check passed. The first run
passed its individual lanes but was rejected by its final input-freeze check
because qualification reports were edited while it ran; it is not counted as a
passed gate. The frozen rerun supersedes it. Logs:
build/health-status-fix-frozen-release-gate.log and
build/release-test-run.XZxBEB/. Final installed fingerprints match the verified
candidate and available health was reconfirmed through the public MCP tool.
Full feature release gates listed in qualification.md remain separate.
