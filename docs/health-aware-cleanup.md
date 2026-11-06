# Health-aware preview cleanup

`get_status.data.health.cleanupCandidates` exposes a bounded, cached view of
resource owners. Pressure advisories include the same evidence. This is a
sidecar extension (`cleanupCapabilities: ["health.cleanup.v1"]`); it does not
change the MCP tool catalog or automatically choose workflow recovery actions.

Each candidate identifies its job, optional workflow, document, status, reason,
suggested action, `automatic`, `blockedBy`, and inactivity deadline. It also
states `changesFont: false`, `preservesRecovery: true`, and
`estimatedMemoryBytes: null`: process footprint cannot establish per-task memory.
Only a `release_preview` action can be automatic. Other actions are guidance to
inspect the existing workflow; they are not action tokens or authorization.

`cleanupObservation` records bridge session, age, completeness and total selected
owners. Stale or cross-session evidence never advertises automatic permission.
`cleanupRecentActions` retains at most eight release/defer outcomes. There are at
most 20 candidates and four release attempts per maintenance pass. At most 128
compact job records are inspected per pass. Script bodies, parameters, reports
and completed history are excluded from these copies. Status and task readers
do not run maintenance, scan fonts, or dispatch native operations.

## Inactivity and pressure

Maintenance runs every 15 seconds while the sidecar is running. By default an
unapplied preview becomes eligible after ten minutes of inactivity during
observed memory pressure or native-dispatch overload. Normal load follows the
existing task inactivity policy (one day by default). A font-count warning alone
does not shorten this deadline. Missing health evidence never implies pressure.

Workflow intent timestamps, rather than polling or display refreshes, determine
inactivity. A queued or authorized Apply request is not an abandoned preview.
Already-cancelled preview reservations can be reconciled without another delay.
Invalid policy files disable automatic health cleanup until repaired.

Optional `jobs/health-cleanup-policy.json`:

```json
{
  "version": 1,
  "enabled": true,
  "pressurePreviewIdleSeconds": 600
}
```

The pressure timeout accepts integers from 30 to 86400 seconds, capped by the
normal task inactivity timeout. Disabling this policy leaves the pre-existing
task-history and inactivity policies in effect.

## Atomic native boundary

Background work holds the existing workflow and dispatch guards, checks fresh
job status and workflow revision, and defers while native execution is active
or native dispatch is delayed. Each release carries the exact job, document and
bridge session to the private `/v1/preview/release` route. A bridge advertising
`previewReleaseVersion: 1` is required; an older bridge reports a candidate with
`blockedBy: "bridge_update_required"` and receives no unsafe fallback request.

Under the bridge operation lock, release is permitted only for a prepared,
unapplied preview or its already-cancelled receipt. Execution, partial edits,
retained inverse states, script snapshots, save/restore attempts and uncertain
write evidence reject the action. It never calls the general-purpose discard
path, cancels remaining script callbacks, or performs Undo/Keep/Save/Restore.

Successful release expires the preview's execution intent and retains its
diagnostics. A lost response leaves local intent unchanged until the same
session-bound cancellation is reconciled idempotently. Applied and uncertain
work remains protected regardless of age or pressure.
