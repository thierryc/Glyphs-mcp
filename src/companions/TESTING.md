# Companion regression gates

Run the lifecycle and bundle tests before installing a companion change:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv-v2/bin/python -m pytest -q \
  src/glyphs-mcp/tests/test_simple_v2_companions.py \
  src/glyphs-mcp/tests/test_simple_v2_curve_lifecycle.py \
  src/glyphs-mcp/tests/test_simple_v2_reference_lifecycle.py \
  src/glyphs-mcp/tests/test_simple_v2_build.py
PYTHONDONTWRITEBYTECODE=1 .venv-v2/bin/python scripts/build_simple_v2.py
glyphs run --quiet --app '/Applications/Glyphs 4.app' --plugins '' \
  scripts/qualify_simple_v2_companions_native.py
```

The lifecycle tests execute the source callbacks with controlled main-loop and
worker queues. They cover restored activation without `willActivate`, delayed
controller/tab attachment, text-mode selection, reactivation, atomic publication,
stale workers, mouse/keyboard quiet periods, retained overlays, edited-occurrence
visibility, and graphics-state restoration. Repeated text may share the same
native layer object: reference labels and paths must use only the active-edit
callback, never inactive-layer or preview callbacks. Global `Glyphs.redraw()` fails these tests: completed overlays must
invalidate the active native `graphicView` without broadcasting a cache reset.
Bundle tests compare every shipped SDK copy and Reporter entry point with source.
The native gate loads the built entry points against the installed Glyphs SDK;
it checks selectors and native outline flags, but cannot prove editor rendering.

For editor acceptance, use exactly one disposable saved font with curved paths:

1. Enable both Reporters, save the disposable copy, and restart Glyphs. Open the
   copy and inspect it before touching the canvas or toggling either Reporter.
   The comb and reference status must appear on the edited glyph; reference
   loading must finish on its own. In a restored text-mode tab, the reference
   cache may prepare but no indication should draw until a glyph is edited.
2. Select one node, nudge it repeatedly, and drag it. Inspect completed updates
   without panning. Native outlines, nodes, guides, and both overlays must remain
   visible. Reference comparison waits for release and 150 ms of quiet; its last
   completed overlay remains available during the edit.
3. Undo each test edit. Both overlays must return to the saved shape, and the
   reference must report “No changes.” Switch layers and disable/re-enable each
   Reporter to check that cached geometry belongs to the displayed layer.
4. Repeat a glyph in the proof string and edit just one occurrence. The reference
   label and comparison paths must appear only on that edited occurrence, with
   no label on its repeated text occurrence or in the preview panel. Switch to
   text mode and confirm the reference indications disappear. Return to editing,
   hold Space to activate the temporary Hand tool, and confirm the indication is
   hidden until Space is released. The cached indication must return in both cases
   without toggling the Reporter.
5. Save the restored disposable copy and compare its font-data files with the
   pre-test backup. Only UI state may differ. Verify the original source hash.

Keep screenshots of startup, completed edits, and restoration with the test
record. A test that merely counts redraw requests does not verify this gate.
