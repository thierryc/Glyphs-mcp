# Lean kerning collision workflow

Use this workflow when `get_status` advertises the seven-tool lean catalog.
Select one clean saved disposable font with `list_documents`. Read exact stored
pairs through `read_entities` using `kind="kerning"`, master, direction, left
and right keys, and the `value` field. A missing value differs from stored zero.

Choose explicit glyph-name pairs and masters. Call `start_job` with
`kind="kerning_collision"` and options `pairs`, `masters`, `targetGap` and
`denseStep`. Omit delta and glyphs. LTR is the supported collision direction.
Computation stays outside Glyphs and uses native intersections and native
effective-kerning resolution. Five coarse heights refine near the threshold;
the report preserves the coarse minimum and the refined minimum and density.

Use `get_job` to inspect evidence and unavailable pairs. Corrections create exact
pair exceptions, leaving shared class values and unmeasured peers unchanged.
Only a positive fractional loosening needed for the target gap is proposed.
This does not promise clearance between samples or optimal optical kerning.

After reviewing the result, `apply_job` displays the reversible native change.
Read back stored values and proof the chosen strings. `discard_job` restores
the exact prior presence and value. The designer may Save in Glyphs to accept;
do not save an applied design automatically.
