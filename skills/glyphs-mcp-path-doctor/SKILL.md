---
name: glyphs-mcp-path-doctor
description: Diagnose Glyphs paths and Pen-point distribution, preserve master correspondence, and perform explicitly requested qualified seam repairs or measured stroke-profile cleanup.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs Path Doctor

Reuse `$glyphs` for the [connection and document binding](https://github.com/thierryc/Glyphs-mcp/blob/main/skills/glyphs/SKILL.md). For a
current-font request require fresh native `isCurrent` evidence; never infer it
from document order. Inspect live data, including unsaved edits, without Save.

Use `start_job(kind="path_diagnostics")` with `path.diagnostics.v1`, then poll
that job. Diagnostics never apply, save, close, reload or resolve another task.
Read [diagnosis](references/diagnosis.md) for request scope and report meanings.
No Path Doctor top-level tool exists.

For crowded, misplaced or excessive Pen points, use the focused
[Pen-point cleanup](references/pen-points.md) mode. Establish exact-preservation
versus bounded-change intent, inspect profile correspondence independently of
outline compatibility, and qualify changes against native expanded strokes.
Even spacing and equal point counts alone are not quality criteria.

Explain definite structural defects separately from appearance questions,
suspicion and valid drawing conventions. An intentional open return/retrace is
valid. Inactive open-start profiles are authored data to preserve. Corner flags
are not an instruction to smooth. Unset closed-stroke fill and a zero-length
closing seam are separate findings. Do not attribute native editing failures to
a seam without reproducing them on a disposable.

Inspection or a repair proposal does not authorize mutation. Apply only a repair
explicitly requested by the user and qualified by fresh evidence. The typed repair
is `normalize_closed_seam` within `outline_edit`, requiring the advertised
`outline.normalize-closed-seam.v1` capability. Follow
[repair and verification](references/repair.md). Missing advertised typed
capabilities mean the installation needs a coordinated update, not a scripted
bypass. Custom interior Pen-point editing follows its focused reference and the
existing native-script recovery contract.

Preserve authored native coordinates, segment direction, intentional lines,
start position, stroke order, profiles and inherited defaults. Do not bundle
fill changes, smoothing, reversal or native cleanup with seam repair. Hold
conflicting profiles, locks, references and unsupported structures with the
report's actionable reasons. Use disposable copies for qualification, keeping
private font/profile evidence local and out of public tests and releases.
