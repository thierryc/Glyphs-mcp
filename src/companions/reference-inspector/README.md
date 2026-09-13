# Changes Against Reference

An independent Glyphs 4 Reporter. Enable **View → Changes Against Reference**.
Choose **Edit → Comparison Reference** to compare against Last Saved, another
font file, a local Git branch/tag/commit, or a public GitHub repository revision.
Git references need a repository-relative `.glyphs` or `.glyphspackage` path.

When Comparison Reference opens, a native checkmark identifies the active font's
selected reference type. That command includes the filename and requested Git
revision, with the complete file path or repository, revision, and font path in
its hover tooltip. Long labels are shortened only in the menu; tooltips retain
the full values. The selected command still opens its chooser. Menu refresh
reads existing per-font preferences without polling, file access, or Git work.
With no font open, or an unsaved font, all reference commands are disabled and
stale checkmarks/details are cleared; their tooltips explain what is needed.

The active layer shows reference geometry in mint and current changes in cyan,
including outline changes, components, open paths, anchors, and width changes.
The label identifies the pinned reference and any width delta. Missing glyphs,
unmatched layers, unsaved fonts, or load failures get an explicit status.

During a mouse drag, the last completed overlay stays visible while Glyphs
continues drawing the editable outline normally. Geometry capture and comparison
wait until mouse buttons are released and interface updates have been quiet for
150 ms. Repeated keyboard edits use the same delay. One pending callback merges
updates; it stops when idle. Completed results replace the overlay together,
and obsolete results are discarded. Switching the active font, layer, or
reference clears the old overlay immediately. A refresh failure retains the
last usable overlay for that context and displays an error in its label.

Restored activation wakes after document, tab, or controller attachment, including
a single selected layer in text mode. Publication invalidates the native canvas
without a global redraw notification; drawing restores Cocoa graphics state so
native outlines and guides remain intact. See [regression gates](../TESTING.md).

Last Saved follows native Save. File and Git references stay pinned until
**Refresh Reference**. Switching glyphs preserves that snapshot. Reference
choices are stored per font path, separately from the font file.

Font loading and Git run in a separate `glyphs-cli` process with plugins disabled.
The host captures only the active layer (at most 8,192 path elements per closed
or open path collection). The Reporter paints cached Cocoa paths. No MCP server
is needed for manual use; an available bridge receives only a capability manifest.

Install the independent bundle produced by `scripts/build_simple_v2.py` and
restart Glyphs. The external reader requires `glyphs-cli`; it uses the current
Glyphs application explicitly. This initial display compares layer geometry and
width, not kerning tables, metadata, or a history of operations. Closed-contour
shading uses an even-odd overlay; mint/cyan segment strokes identify changes
when overlapping contours make the shading ambiguous.
