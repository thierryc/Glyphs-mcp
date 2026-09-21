# Curvature display in Glyphs 4

Reuse the verified connection and intended document already in context. This
native companion uses **View → Show Curve Inspector**; it has no MCP toggle,
preparation job or Save requirement. Keep the nine-tool interface. If the
companion or its coverage notice is missing from the private installation,
explain that the installed candidate needs updating; do not invent an older
private workflow or a live-Python command.

## Inspect and return to work

1. Show the intended glyph and master in Edit View, then enable **Show Curve
   Inspector**. If the outline is offscreen, use native **Zoom to Active Layer**.
   Do not rediscover documents just to switch inspection skills.
2. Teal teeth indicate positive signed curvature; pink indicates negative.
   Sign depends on contour direction, not whether a curve is good or bad.
   Teeth and their connected tips help compare changes along a curve.
3. Read any notice near the lower-left of the canvas. Only direct cubic paths are
   inspected. Components are omitted without decomposition; component-only
   glyphs can therefore show a notice and no comb. Straight segments and empty
   layers have no teeth. **Complete coverage of direct cubics is not complete
   component or glyph coverage.**
4. At most **128 cubics** and **2,000 teeth** are displayed. Beyond the cubic
   bound the notice says more exist, without claiming an exact total. Extraction
   also stops after **8,192 nodes or 512 paths**, with an explicit partial notice.
   Uniform sampling starts at 51 samples/cubic and is reduced for dense layers.
   Tooth length is capped at **0.12em**; this is a rendering limit, not a measured
   radius. The notice states the cap when showing a limitation; it does not mean
   every tooth hit it. Absence of teeth is not proof that a component is straight.
5. Verify refresh after an authorised node edit, master/layer switch, pan or zoom.
   Check both the comb and the current notice: an old cache is not current
   evidence. Glyphs 4.1 (4107) also shows the comb in text mode; Font View should
   show neither the comb nor its notice. Return to Select for node editing.
6. Use native Undo/Redo for authorised edits; display activation itself must not
   edit the font or add Undo entries. Verify original geometry independently
   when restoration matters: the dirty indicator can remain set after exact
   restoration. On Glyphs 4.1 (4107), native Undo also failed to restore some
   fractional control points in realistic-font tests, including a control with
   Curve Inspector disabled. Use a disposable copy for exploratory edits and
   verify coordinates; do not treat Undo alone as proof of exact restoration.
   Disable **Show Curve Inspector** to remove the display.

Dirty documents need no Save for inspection. Never silently target another font;
rediscover only after a stale document ID, a restart or changed target intent.
Report any unavailable or partial evidence. Technical curvature display does
not establish good interpolation or typographic quality. Keep latency and Undo
dirty-state investigations separate; normal autosaving stays enabled. For a
crash, use the existing [connection troubleshooting reference](../../glyphs/references/connection-troubleshooting.md)
without claiming a cause from a passing retry.
