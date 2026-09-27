# Bulk scripting milestone — September 25, 2026

Implemented in the v2 worktree. The twelve public MCP tools are unchanged. The
built candidate has been exercised in an isolated Glyphs 4.1 (4107) process;
the user's installed runtime has not been replaced or restarted.

## Behavior delivered

- `python_script` jobs support scoped callbacks and explicitly confirmed
  unrestricted callbacks or whole scripts. Source and JSON parameters stay in
  the reviewed request. Whole scripts support conventional Python main guards.
- Both modes require a saved, clean intended document. The existing chat Save,
  Save As, and manual-save choices remain separate from execution authorization.
- Exact foreground/background targets and exact-master bulk selectors resolve
  into a fixed manifest; duplicates collapse, overlapping surfaces reject, and
  missing or empty backgrounds are reported. No implicit current-selection or
  other-document substitution occurs.
- Scoped execution uses the existing private saved-source worker. It rejects
  outside-scope changes, preserves original grid settings and image-reference
  locations, and qualifies every live target before the first live application.
- Unrestricted preparation never executes Python. Only the revision-bound Run
  action dispatches it. Capture precedes module initialization, callbacks yield
  on the native main thread, and other MCP mutations cannot run concurrently.
- The existing native snapshot/Undo mechanism now covers complete supported
  layer contents. It preserves owning layer objects and unselected surfaces.
  Apply, native Undo/Redo, and whole-job restoration use recorded contents and
  never rerun Python. Native Undo remains per glyph.
- Cancellation stops external preparation or remaining native callbacks.
  Recovery results distinguish complete, partial and unavailable restoration.
  Lost responses reconcile by job identity. A confirmed lost native record can
  be acknowledged in chat with its outcome retained as unverified.
- Chat cards and text actions expose review, Run, Cancel, progress, and recovery.
  Exact source and bounded output render as text. No native confirmation dialog
  or external page was added. No-recovery results offer no wrapper restoration.

Limits remain 4,096 surfaces, 8 MiB per target state, and 64 MiB combined encoded
before/after recovery state. Source is limited to 128 KiB and parameters to
64 KiB. Internal prepared-patch transfer is chunked; bridge requests retain the
4 MiB limit. Scoped Python is trusted code, not a security sandbox. Filesystem
or network effects and external image bytes are outside recovery, and a Glyphs
crash does not preserve wrapper recovery.

The reusable [vertical flip callback](../../skills/glyphs-mcp-scripting/examples/vertical_flip.py)
uses combined native path bounds by default, with individual-path, baseline and
custom-Y pivots. It transforms every node, including controls, and preserves
components, anchors, foregrounds and other masters.

## Verification

The full regression run passed 2,190 tests with two existing skips. The two
loopback-port tests excluded from that sandboxed run passed separately with
local socket access. Subsequent targeted checks covered the final script,
worker, packaging and routing changes, including a new whole-script main-guard
test. Final targeted totals are recorded in verification.json.

Native suites verify saved-document worker/chat execution, complete content
addition/removal, metadata absence, fractional coordinates, hints referring to
restored nodes, components, guides, annotations, images, missing backgrounds,
unaltered surfaces, cancellation, module/runtime failure, later-edit conflicts,
deleted owners, no-recovery execution, exact-once confirmation, native Undo/Redo
and whole-job restoration. Grid-enabled curves and control points are included.
Private copies of both `.glyphs` and `.glyphspackage` retain original image
locations and reject out-of-scope grid changes.

Built-candidate qualification checks the modules actually imported by the
native process. `candidate-edges.json`, `candidate-workflow.json`, and the copied
manifest record its paths and code hashes. Source and built Python bytes match.
Canonical guidance and all 11 packaged skills synchronize, the package checker
passes, and the development SDK/scaffolder/native plugin workflow is retained.
Local routing instructions remain untracked and excluded from distribution.

## Measured performance

Times are seconds; lower is faster. Each row uses the same target count.

| Targets | Direct callback | Scoped preparation | Guarded bulk apply | Repeated bridge apply | Restore |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 0.05 | 0.69 | 1.24 | 1.19 | 0.58 |
| 1,000 | 0.48 | 6.45 | 11.77 | 11.90 | 5.88 |
| 4,096 | 1.97 | 28.24 | 55.74 | 62.59 | 28.36 |

| Targets | Peak process RSS (MiB) | Encoded recovery (MiB) | Longest scheduled chunk (ms) |
| ---: | ---: | ---: | ---: |
| 100 | 200.4 | 0.044 | 14.7 |
| 1,000 | 543.0 | 0.440 | 26.2 |
| 4,096 | 1286.3 | 1.801 | 119.2 |

Raw measurements and source hashes are in `benchmark-100.json`,
`benchmark-1000.json` and `benchmark-4096.json`. At 4,096 targets the combined
preparation/application time was 84.0 seconds, with 1.26 GiB peak process RSS.
Direct native execution remains much faster; the wrapper pays for complete
snapshots, target qualification, conflict checks and Undo/recovery. These runs
were not performed on an otherwise idle machine; native qualification briefly
overlapped the largest run.

These are single-run measurements on synthetic triangular backgrounds in fresh
isolated Glyphs processes. Preparation excludes CLI startup. Repeated edits
measure serialized bridge requests, excluding model/client/transport latency
and repeated external-worker startup. They are a lower-bound comparison for
repeated MCP edits, not a complete chat-to-editor latency measurement.
Scheduled chunk duration is a responsiveness proxy; interactive window frame
rates were not measured. Peak process RSS includes the font, native application,
Undo histories and all benchmark phases; it is not the encoded recovery budget.
The results do not establish a speedup over direct native Python. The benefit
is one bulk request with explicit scope validation and recoverable application.

## Handoff

Use [the shared script contract](../../skills/glyphs/references/python-scripts.md)
and the [scripting skill](../../skills/glyphs-mcp-scripting/SKILL.md) for requests.
The candidate is in `build/python-scripts-milestone`. The existing installation
is a copied bridge, not an established development-linked target, so no runtime
installation or editor relaunch was performed. Live installed-client testing in
Codex/Claude Code is pending a coordinated runtime update; current UI evidence
uses the standard MCP Apps host fixture and the real native workflow backend.
Changes are uncommitted and unstaged. Dirty/never-saved execution, general live
font serialization, and persistent crash recovery remain deferred.
