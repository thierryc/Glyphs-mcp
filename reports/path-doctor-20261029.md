# Path Doctor qualification — 2026-10-29

Unreleased repository candidate; no top-level tool added and no release published.
Initial native qualification used isolated candidate modules on disposable fonts.
A subsequent explicitly authorized installation updated the bridge and sidecar,
and both were reloaded for the installed MCP acceptance described below.

## Implemented and checked

The diagnostic job uses the existing sliced native preparation registry and
returns a non-applicable diagnostic result. Dirty/pathless source support is
tested through the sidecar without a saved-source copy or worker invocation.
Stopped recovery remains available and is not settled by diagnosis.

The explicit outline operation preserves the authored seam position, path order,
real line/cubic segments, traversal, handles and every retained coordinate.
Incoming profiles move with their segment. Exact geometry/attribute/profile
state guards reject stale proposals. Native snapshots copy Pen points and
attributes and retain path/node identities for selective recovery and Undo/Redo.
Conflicting profiles and unsupported references are refused. The automatic zero
line is the only removed segment. Fill and connection flags are unchanged.

Original generic public fixtures cover line/cubic closure, correct loops,
intentional open returns, retracing, matching/conflicting profiles, interior
controls, inherited defaults, inactive open-start controls, fractional values,
locks, hints, unsupported attributes, master correspondence, multiple strokes,
fresh edits, deterministic diagnostics, idempotence and exact recovery.

Native generic tests on Glyphs 4.2 (4202) passed exact line/cubic normalization,
profile field/default preservation, numeric attribute precision, native
NSUndoManager Undo/Redo, and refusal for locked paths, hint references, conflicts,
open paths and stale coordinates. In-memory repair capability is limited to this
qualified host and native selector set. Other builds remain diagnostic-only.

Preparation explicitly requires a copied layer to be detached before changing
rounding flags or simulating an operation. The native isolation probe found
these copies already detached and their owner timestamps unchanged; a regression
now enforces that invariant for future hosts.

## Persistence and UI limits

Native Save serializes some coordinates at reduced precision on the qualified
host. Exact arbitrary live-coordinate Save/reopen did **not** pass. Separately
saved pristine/repaired copies passed differential geometry/profile comparisons:
normalization adds no error relative to the native persistence baseline. Copy
construction can regenerate instance IDs; native editing updates target glyph
change timestamps. These are separate from an in-memory seam edit. No owner's
font was saved to test persistence.

Native UI experiments used separate original, seam-only, fill-only and
smoothness variants. Selection and dragging worked in the tested original and
repaired variants. A blanket selection/drag refusal was not reproduced, so the
seam is not claimed as its cause. Corner flags retain independent editing
behavior; an intentional diagonal remains a line. Width-aware previews were
inspected at more than one scale, including counters, joins and closure. These
observations do not replace numerical profile verification or prove every native
editing interaction on every font/build.

## Privacy and delivery

Private live audits, disposable fonts, native measurements and detailed UI notes
stay local under the ignored `.codex-local/` tree. No private geometry, profiles,
font files or screenshots belong in tracked tests or release payloads. The
public fixtures are original generic examples.

The external OpenPlotFont converter was inspected read-only. Its native package
boundary independently closes paths while retaining explicit return endpoints.
A coordinated converter fix with segment/profile address mapping remains work
in its owning repository. No external repository was changed.

The coordinated local installation and reload were separately authorized.
Current source, build output and running identities were checked independently.
Published feeds, tags, release assets and version identities remain unchanged.
See the next-version preparation note for remaining release steps.

## Recorded automated checks

- Broad Python suite: 3,314 passed, 3 skipped, one failure in the existing
  feedback/branding test because the local MCP SDK `Implementation` response
  lacks `websiteUrl`. The test and branding implementation predate this task.
- Final focused Path Doctor/outline/preparation/recovery checks: 88 passed.
- Skill synchronization and lean-package checks: 13 managed skills, 22 tools.
- Native installer skill-catalog tests: 22 passed.
- Two assembled lean candidates produced identical manifests. Private evidence
  paths/font names were absent from the candidate payload.

The broad suite log is a build artifact, not proof that the installed runtime
contains this candidate. Native installer catalog test details remain in local build output.

## Installed acceptance

The local sidecar and Glyphs 4.2 (4202) bridge loaded the expected candidate
identities and advertised `path.diagnostics.v1` and
`outline.normalize-closed-seam.v1`. Live owner-font evidence was read-only.
All mutations used an original generic disposable with six cases in two masters:
line and cubic redundant closures, a correct closed loop, an intentional open
return with inactive start controls, conflicting profiles and a locked path.

Diagnostics completed on the dirty/pathless fixture while its stopped script
recovery remained available. A terminal diagnostic was rejected as
`job_not_applicable` when submitted for application. The separately saved generic
baseline used the ordinary typed outline preparation/application route. Four
qualified seams were repaired; four conflicting/locked seams were held.
The second diagnostic proposed no further repairs. Selective discard restored
the exact pre-repair diagnostic state hash. Reapplication through the conversation
workflow passed an independent native comparison of all 12 fixture layers: exact
coordinates, types, handles, every Pen-point field, explicit/inherited storage,
path attributes, metrics and all non-target paths. Reusing the old pre-repair
proposal after repair was rejected with a stale reference-path guard, before
application. The 141 focused tests passed
both in the full working tree and in a clean baseline export containing only
the proposed Path Doctor changes; unrelated pending UI/installer/branding work
was excluded from that export.

`scripts/fixtures/path-doctor-installed.py` reproduces the generic setup and
independent numeric capture/verification through existing native script jobs;
the actual repair uses advertised MCP tools. It contains no owner font data.
The earlier exhaustive private one-shot qualification kept Glyphs busy for many
minutes; it is not a responsiveness gate for the sliced installed diagnostic.
Native Save remains precision-limited, and full-font UI behavior is not inferred
from these small fixtures. Subsequent user feedback identified a View setting
as the cause of the reported invisible nodes.
