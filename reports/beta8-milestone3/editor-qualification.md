# Actual editor and installed-client qualification — September 27, 2026

Milestones 2 and 3 are qualified locally on Glyphs 4.1 (4107). No release or
commit is implied. The new save/continuation authorization was available;
Dactylotype was already clean. It was reopened after the authorized relaunches
and was never mutated or saved by these tests. All test fonts were disposable.

## Installation and recovery

The established copied installation was updated with `--only mcp`, preserving
both companions, port, auto-start setting and bundled runtime. The initial M3
candidate was installed first; a discovered inventory bottleneck then required
the small correction below and a second rebuild/install/relaunch.

Final source/build copies match (133 Python copies), installed and loaded bridge
hash `d9ad46e01f0f0a5baa93320dc6e9d887d8b4b5485f6a89950015d238d7273119`,
sidecar hash `7cb89a42377190ed25b6dc6518f28ddd0b579aa7711e0e994f2dc3335d6ac07c`.
See [byte verification](build-verification-live-inventory-fix.json),
[installation receipt](installation-live-inventory-fix.json) and
[loaded status](installed-loaded-live-inventory-fix.json). Twelve tools,
`script.native.v1` and the private typed preparation capability remain advertised.

The installed Codex connection exercised both [single-file](editor-glyphs.json)
and [package](editor-glyphspackage.json) fixtures:

- Fractional widths across two masters, metadata-only colors, background-node
  deltas, unchanged controls and foreground outline hashes.
- Actual Edit View native Undo/Redo and selective workflow Undo. Background
  node names remained null, with fractions and named control nodes preserved.
- Keep followed by the next task; duplicate Keep and duplicate script Run;
  authorized Save-and-continue and Save-result receipts from the native editor.
- Successful script execution, separately verified coordinates and optional
  full details. A deliberate partial failure retained Keep/Restore and no timer.
- Whole-font saved reload, fresh binding, restored geometry/widths and cleared
  Edit menu Undo/Redo. Single-file reload also removed a later manual width edit.

The earlier fixture generator described Bold width as 600.25; the actual editor
opened it as 600 under its nonzero grid. Tests used the observed live baseline
600 and verified the requested 0.375 delta exactly. This is recorded rather than
claiming the generator's anticipated value was observed.

## Editor-discovered inventory cost

The first 4,096-width preparation remained pending for 157.9 seconds and was
cancelled before any mutation. [Stack sampling](editor-preparation-sample.txt)
showed repeated `orderedDocuments`/window-server work. Glyphs' `AppFontProxy`
rebuilds its document inventory for length/index access; materializing it as a
generic Python sequence repeated those queries. The native benchmark harness
overrode `_fonts`, so it could not expose this editor-specific cost.

A [new regression test](../../src/glyphs-mcp/tests/test_simple_v2_live_font_inventory.py)
failed before the fix. The adapter now calls the proxy's existing `values()`
once per fresh check, preserving live closed/replaced-document detection and
plain collection support. No persistent document cache was added. Focused checks
pass (48); the full suite passes **2,322 tests, two skips**, with the same five
dependency warnings. Skill synchronization, package and whitespace checks pass.

The pre-correction attempt used four open documents; the corrected single-file
attempt used two. This is diagnostic evidence, not a controlled speed ratio.
Do not substitute it for the five-run standalone matrix or promise a universal
10 ms editor chunk. Corrected measured preparation chunks still reached 56.5 ms.

## Large edits and timing boundaries

The corrected [single-file check](editor-large-fixed.json) applied all 4,096
width edits and verified all 5,000 widths: 904 controls remained unchanged.
Native Undo/Redo remained functional. The actual card timed out to Keep during
the long verification (`responseOrigin=card_timeout`); it did not save. A second
edit disabled automatic Keep, exercised selective recovery, and an authorized
native verification script checked every glyph's final width, foreground and
background rounding flags, zero Undo grouping level and groups-by-event setting.

The 50 bounded Codex read calls took **210.1 seconds** including connector
round trips. This is verification cost, not edit execution time. The separate
[fresh local MCP client test](editor-large-glyphspackage.json) on the actual
editor package checked all widths before, after and after selective recovery:

| Stage | Seconds, one installed-editor run |
| --- | ---: |
| Preparation + application/polling | 19.016 |
| Selective recovery/polling | 2.463 |
| 50 bounded reads before | 2.326 |
| 50 bounded reads after application | 2.583 |
| 50 bounded reads after recovery | 3.374 |

The package run also completed actual verified saving and native checks of all
5,000 glyphs' rounding/Undo settings. These are qualification runs, not five-run
performance estimates; local transport, Codex latency and standalone-process
benchmarks remain separate methodologies. The original 100-run M3 matrix and
140-run M2 matrix retain their reported regressions and scope.

The successful card timeout and text Wait action were observed, but full visual
progress-bar, hidden/disconnected-card and local rejected-Wait tests remain the
milestone 5 gate. Earlier unrelated release gaps are not marked complete here.
