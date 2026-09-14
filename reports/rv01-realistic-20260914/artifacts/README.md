# Authored benchmark artifacts

These scripts target the pinned Roboto Slab fixture and explicitly supplied native font/master objects. They are **not general-purpose font repair tools or new MCP endpoints**.

- `outline_tasks.py`: bounded handle, straight-node, extrema and cubic-split operations. Native precision flags are restored in `finally`. The deletion guard intentionally requires the fixture’s 31-node seeded H contour and its exact midpoint; it rejects arbitrary curves and uncertain targets.
- `Realistic Master Audit.py`: scaffolded, statically validated, actually loaded revision 2. Call `audit(font, glyph_names, master_ids)` with an explicit native font, 1–20 glyphs and 1–32 exact master IDs. Returns complete compact rows without editing. The previous revision is retained.
- `feature_tasks.py`: read native feature flags correctly and create the isolated ss20 control only when absent. It does not implement an MCP feature workflow. ss20 duplicates existing ss01 here and is not a production change.

Execution was through the installed official Glyphs CLI with Glyphs 4 and plugins disabled for isolated tests. The benchmark runners record actual native results separately from independent oracles. `export_feature_corrected.py` contains the observed Glyphs 4 keyword forms. No custom history or automatic live-font targeting is provided.

To reproduce the evaluation, use a new output directory and fresh copies, retain the pinned source/license, verify current runtime identities, and adjust the harness’s explicit output paths. Do not run the historical runners in place: their outputs are evidence and must be preserved. Static validation does not establish native compatibility. Future fonts require new target/topology checks and a new qualification.
