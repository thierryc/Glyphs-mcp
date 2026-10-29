# Path Doctor: smallest useful extension

Status: next-version implementation and qualification, no release publication.

Path Doctor is a workflow, not another editing service. It uses `start_job` /
`get_job` for `path_diagnostics` and the existing `outline_edit` operations for
`normalize_closed_seam`. No top-level MCP tool is added. Native preparation runs
in the existing sliced operation registry. Diagnostics return `resultKind:
diagnostic`, cannot be applied or accepted, need no Save, and inspect live data,
including unsaved changes. They may coexist with stopped recovery, without
settling it; active native writes remain protected.

## Evidence and repair

The diagnostic request names glyphs (`all` or explicit names) and foreground
master layers (`all_masters` or exact stored IDs). It never creates missing
layers or expands components. Reports identify each document/glyph/layer/path
and raw node address, give deterministic issue IDs, confidence, classification,
severity, evidence, qualified operations and held reasons. Reports describe
coverage and unsupported objects explicitly. Generation checks span slices;
this is not an atomic snapshot. A fresh diagnostic is required after observed
manual changes. Reports remain private local job artifacts.

Coincident coordinates on an open stroke are valid. Corner flags are a drawing
convention, not a smoothing request. Missing explicit fill on a closed stroke is
an appearance question, independent of a redundant seam. The workflow makes no
claim that a seam explains every native selection or handle failure.

The initial repair recognizes only a closed path whose first node is a line,
whose final on-curve exactly equals it, and whose automatic last-to-first line
has zero length. It validates the real incoming segment and all other segments.
It retains node 0 and its XY, transplants the last endpoint's incoming segment
type and complete Pen-point array, then removes the final duplicate. Thus a
cubic return retains its trailing handles and becomes the native closing cubic;
a line return becomes the native closing line. Every other node retains its
order, coordinates, attributes and identity. The removed last node maps to 0;
all other node addresses stay fixed. The incoming segment end maps to 0 and
only the automatic zero line disappears. No fitting, rounding, start rotation,
smoothing, direction reversal or fill change occurs.

Redundant node-0 profile storage must be absent or exactly one t=1 control
identical to the incoming endpoint, including sentinels and explicit storage.
Conflicts are held, rather than resolved by tolerance or effective-width guesses.
Locked paths, locked profiles, hint references and unsupported node/path metadata
are held. Unsupported quadratic/rotated seam patterns remain diagnostic only.
Repair currently targets foreground ordinary-master layers only. Historical,
special and background repairs remain unsupported. All ordinary-master correspondence is preserved by the existing simulation and
compatibility checks; seam normalization refuses `allow_incompatible`.

## Guards, precision and recovery

`pathHash` and outline state guards now include path/node native attributes,
profiles and user data. Profile values use exact binary floats, including
inherited DBL_MAX sentinels, plus explicit native storage evidence. Geometry
always uses `position`, never latent `positionPrecise`. Unknown native references
fail closed. This intentionally invalidates guards produced by older runtimes;
bridge, sidecar and skills must be updated together.

Preparation explicitly checks that native layer copies have no owning glyph
before simulation, avoiding any owner notification through a copied parent.
The existing outline snapshots retain native path/node objects and now also
independently copy their attribute dictionaries and Pen points. Exact native
selectors bypass wrapper attribute setters that can format numeric values.
Restoration verifies explicit storage and precision. The normal typed adapter
still owns native Undo/Redo, selective discard, before/after verification,
rounding protection and separately authorized Save. No recovery framework is
added. The known redundant zero line is valid input to this operation's explicit
qualification; general structural validation remains unchanged.

Mutation jobs retain the existing clean saved-baseline requirement. Diagnostics
support dirty/pathless fonts. Native qualification on a disposable can directly
test candidate functions without advertising unqualified runtime writes.

## Native cleanup and conversion boundary

`cleanup_paths` is a whole-target native command. It has no qualified guarantee
here for exact profile remapping or reference preservation and is not a Path
Doctor repair. Do not use it to fix all suspicious paths.

Read-only inspection of the external OpenPlotFont package writer found that
`path_nodes()` emits every command endpoint, while `write_package()` independently
sets `closed`. The correction belongs at that native serialization/conversion
boundary, after ordered OpenPlotFont commands have been interpreted. It needs
an explicit native segment/node map, including profile ownership and closure
endpoint reconciliation. Keep OpenPlotFont's ordered commands intact. An open
return or retracing must never be normalized by coordinate equality. Coordinate
that implementation and its tests in the owning repository separately; this
change makes no edits there.

## Qualification and delivery boundary

Generic public fixtures exercise exact numerical geometry/profile preservation,
refusal, deterministic diagnostics, idempotence, master correspondence and stale
state. Private native audits and disposable-font evidence stay ignored and local.
Native selection/dragging, multi-scale width-aware appearance, counters/joins,
Undo/Redo and disposable save/reopen are separate gates; passing pure tests or
render similarity cannot substitute for them. See the dated qualification report
for actually performed checks and remaining limits. Repair capability is limited to the qualified native host by
`path_doctor_qualification.py`. Native Save can reduce coordinate precision;
exact in-memory repair/recovery and differential native persistence are distinct
claims. Saving requires its own authorization and does not promise lossless
serialization of arbitrary live coordinates.

## Pen-point distribution mode

The skill also routes crowded/interior Pen-point requests to a focused reference
and a font-independent measurement/selection helper. This adds no MCP tool or
typed mutation operation. Authorized custom experiments use the existing native
script preparation, document guards and whole-font session recovery.

First establish profile correspondence: native outline compatibility does not
include all Pen-point ownership/count information. An already mismatched native
interpolation is not automatically a valid reference. Alignment trials preserve
authored masters within an explicit budget and report intermediate changes
separately. Only then does joint adaptive knot removal compare each cumulative
proposal against the same correspondence-correct reference. Its decision uses
the worst measured native stroke-boundary/profile error across masters and
required intermediate instances, protecting meaningful pressure transitions.

Close spacing is a candidate-ranking signal, not proof of redundancy. The
helper provides conservative sampled boundary bounds and deterministic greedy
selection; it neither edits a font nor proves a global minimum or aesthetic
quality. Native expansion, profile interpolation, overlaps, editing behavior and
perceptual review remain separate qualification requirements. Private trials
and their exact data remain ignored and local.

## Catalogue delivery before inclusion

Older apps ignore remotely advertised included skills and use their embedded
snapshot. Path Doctor is therefore downloadable from the online catalogue with
its canonical identity, immutable source and archive checksum until the app
includes it. Its package is self-contained and carries its redistribution
license; a distribution copy in the official skills repository avoids unrelated
repository symlinks rejected by the catalogue downloader. A later app prefers
its own included payload over that same curated
canonical entry; unrelated same-name sources still fail rather than replace an
included skill. Updating the catalogue does not install code or alter agent
skills without the user's installation choice.
