# Glyphs Health

`get_status` returns cached health with `health.snapshot.v1`; automatic feedback
also accompanies relevant tool responses. `health.admission.v1` identifies server
protection. No additional tool or companion window is required.

Check once at connection. During work follow tool feedback, refreshing status
after a resource refusal or before substantial work after a pause longer than
five minutes. Do not poll status before every action. Capabilities remain
session-scoped while health observations age independently. Missing, stale or
partial signals are unavailable evidence; they never establish a healthy Mac.

Normal: continue within the requested scope. Caution: reuse open documents,
process batch inputs sequentially and avoid unnecessary new tabs or font copies.
Paused: defer new expensive work, respect `retryAfterSeconds`, and explain the
meaningful delay once. An open-font warning threshold alone never blocks work.
The server owns thresholds and recovery timing; do not reproduce them in scripts.

Queued edit workflows retain their identity and automatically resume when
admitted. Keep polling that workflow at its indicated retry interval; do not
submit another request or interpret Waiting as needing approval. A preview still
requires its original review. Expiry and restart retain their existing rules.

Direct tools return `resource_pressure` with `execution:not_started`; they do not
queue a hidden future operation. Retry the same request/key after the delay.
Lost or uncertain responses retain their original outcome checks. Completed
idempotent results and existing-document reuse are permitted under pressure.

Health handling does not authorize closing fonts, saving, discarding edits,
Keep, Undo, Restore, export, or restarting Glyphs. Use the original authorization
and lifecycle. Existing inspection, cancellation and recovery stay available,
subject to native responsiveness and ownership. Never release recovery to make
room automatically. A running script is not interrupted; its source should avoid
opening unnecessary documents because operation admission cannot sandbox Python.
