# Glyphs Curve Inspector

An independent Reporter for the currently visible layer. It copies at most 128
cubic segments on the Glyphs main thread, builds a bounded signed-curvature
comb and connected endpoint envelopes in one background worker with
latest-refresh-wins behavior, and draws only cached paths. Its sampling,
colors, alpha, scale and zoom-dependent line widths match the previous working
Glyphs MCP Curvature display. Unchanged UI notifications are coalesced. The
pure `curve_core` package is also bundled with the sidecar for external jobs.

Enabling the Reporter schedules an initial refresh on the next Cocoa main-loop
turn, so the overlay appears without a canvas interaction. Re-enabling also
redraws unchanged cached geometry. Disabling invalidates pending worker results.

Restored documents and tabs also wake the Reporter after controller attachment,
including a single selected layer in text mode. Same-layer edits retain the last
completed comb until the next result is ready. Publication invalidates only the
native canvas, and drawing restores Cocoa graphics state. See [regression gates](../TESTING.md).
