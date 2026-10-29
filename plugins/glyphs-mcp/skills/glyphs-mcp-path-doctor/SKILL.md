---
name: glyphs-mcp-path-doctor
description: Diagnose Glyphs path structure, explain stroke/profile findings, and propose or apply explicitly requested qualified closed-seam repairs while preserving authored geometry and profiles.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs Path Doctor

Reuse the [Glyphs connection and document binding](../glyphs/SKILL.md). For a
current-font request require fresh native `isCurrent` evidence; never infer it
from document order. Inspect live data, including unsaved edits, without Save.

Use `start_job(kind="path_diagnostics")` with `path.diagnostics.v1`, then poll
that job. Diagnostics never apply, save, close, reload or resolve another task.
Read [diagnosis](references/diagnosis.md) for request scope and report meanings.
No Path Doctor top-level tool exists.

Explain definite structural defects separately from appearance questions,
suspicion and valid drawing conventions. An intentional open return/retrace is
valid. Inactive open-start profiles are authored data to preserve. Corner flags
are not an instruction to smooth. Unset closed-stroke fill and a zero-length
closing seam are separate findings. Do not attribute native editing failures to
a seam without reproducing them on a disposable.

Inspection or a repair proposal does not authorize mutation. Apply only a repair
explicitly requested by the user and qualified by fresh evidence. Initial scope
is `normalize_closed_seam` within `outline_edit`, requiring the advertised
`outline.normalize-closed-seam.v1` capability. Follow
[repair and verification](references/repair.md). Missing capabilities mean the
installation needs a coordinated update, not a scripted bypass.

Preserve authored native coordinates, segment direction, intentional lines,
start position, stroke order, profiles and inherited defaults. Do not bundle
fill changes, smoothing, reversal or native cleanup with seam repair. Hold
conflicting profiles, locks, references and unsupported structures with the
report's actionable reasons. Use disposable copies for qualification, keeping
private font/profile evidence local and out of public tests and releases.
