# Glyphs Health

Glyphs Health supplies shared evidence to the companion and agents, with
admission protection at MCP operation boundaries. It works with the companion
closed. The companion layout and Markdown report changes are described in the
[2.7.0 candidate notes](../V2.7.0-RELEASE.md).

## Passive observation

There is one resource observer per bridge process. Public Darwin APIs collect
physical footprint and deliver memory-pressure notifications outside the main
thread. Pressure starts unknown; missing notifications never establish normal
pressure. No private sysctl, subprocess, full-font scan, copy or outline hash is
used. History retains at most 60 footprint samples. The companion shows Glyphs'
footprint as a share of installed RAM. The growth reading uses an observed
interval of 90 to 120 seconds and shows its actual duration. Both are context
for the separate macOS pressure and Glyphs responsiveness readings.
The companion uses green below 15% of installed RAM and orange for a heavy
footprint at 15% or more. Below 5% is labeled light and 5% to below 15% is
labeled moderate. Red indicates critical macOS pressure or severe Glyphs delay.

Native inventory inspects at most 128 open fonts within a 2 ms metadata budget;
counts of dirty documents and Edit tabs can therefore be partial. Font count
uses the native collection length. Interface/document events coalesce, and
successful document operations invalidate the inventory. Observations are
scheduled independently of status reads, with one pending callback maximum and
no catch-up queue. Main-thread observations run during activity or after an
invalidation; idle status reads schedule none.

The bridge initializes capability discovery on the main thread and serves its
cached status directly from the HTTP thread. The production sidecar serves
complete checking metadata immediately and discovers the bridge in the background,
then refreshes its own cache in the background. Both
`get_status` and `/internal/status` read that cache; neither reconciles jobs nor
advances workflows. Explicit job operations, workflow supervision and control
reservations keep their existing reconciliation.

Footprint sampling is 15 seconds idle and 5 seconds during native work. Optional
observations back off to 15/30 seconds under caution/pause. Sidecar refresh is
5 seconds during jobs and 30 seconds idle; mutations wake/coalesce refreshes.
Failures back off to 60 seconds. Evidence ages independently, using monotonic
time. Pressure is event-based and does not expire merely because it is unchanged.

## Additive contract

The tool catalog, interface revision and bridge protocol remain unchanged.
`healthCapabilities` negotiates `health.snapshot.v1` and `health.admission.v1`.
`get_status.data.health` contains version, session, revision, state, signals,
reasons, recommended actions and admission guidance. Signals describe
availability, age, completeness and source-specific observations. Overall
availability means the monitor exists; inspect individual signal coverage.

Relevant responses may add top-level `health` beside `ok`, `data` and `error`.
It contains a compact advisory and model-visible `text`; existing `data` shapes
are unchanged. Workflow results also include a separate text/context block.
Reading feedback does not change workflow revisions or action tokens.

States are normal, caution, paused and unknown. Reasons include
`font_budget_reached`, `memory_pressure_warning`, `memory_pressure_critical`,
`native_dispatch_slow`, `native_dispatch_delayed`, and `recovering`.
Delayed dispatch is distinct from execution time, HTTP latency and progress;
it does not diagnose a frozen Glyphs application.

## Admission and recovery

Settings → Glyphs Health can enable an installation-wide open-font warning
(1–128) without restarting. Font count is context when the preference is off.
The atomic `jobs/health-policy.json` uses version 1 and `fontWarningThreshold`.
An invalid policy retains the last valid threshold and exposes unavailable
policy evidence. Turning the preference off removes the override.

OS warning pressure or a pending native dispatch over 2 seconds yields caution.
Under elevated system pressure, routine edits can continue. Tool advisories
recommend running large document opens, imports, exports, comparisons or
whole-font snapshots one at a time, according to the requested work.
Critical pressure or a pending dispatch over 10 seconds pauses new expensive
work. Resume requires 30 seconds without the triggering condition and resolution
of native dispatch delay. Losing the pressure observer cannot clear a known
critical state. Count alone, footprint alone and missing evidence alone never
block work.

Protection defers document growth, new preparation/scripts, apply, export and
comparison. Existing-document reuse and completed idempotent receipts precede
the growth guard. The bridge rechecks before new native work starts, shared
across clients. Existing execution is not interrupted. Inspection, cancellation,
authorized save and existing recovery retain their normal ownership checks.

Edit workflows use their existing queue, identity, cancellation and expiry.
Health retry metadata does not renew execution intent. Preview requests do not
gain execution authorization while waiting. Health waits recheck no faster than
15 seconds. Direct tools return `resource_pressure` with
`details.execution="not_started"` and `retryAfterSeconds=15`; no hidden operation
runs later. Retry the same request/key. Unknown outcomes still require existing
reconciliation. Admission cannot constrain arbitrary Python after it starts.

Older components remain usable for existing operations but do not claim health
protection. Stale status or absent health is never displayed as verified health.
No cleanup, saving, recovery release, restart, notification or publication is
performed automatically.
