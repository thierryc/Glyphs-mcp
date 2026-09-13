# Lean start-node correspondence

Reuse the verified connection and intended `document_id`. Discover only for a
new target, a fresh current/frontmost-font question, or `document_not_found`.
A missing glyph is not a reason to rediscover or substitute another font.

Prepare from one clean saved font. Dirty preparation needs the designer's
explicit Save decision; never save automatically. For a fresh read, dirty
state is supported. Keep the document/job IDs and review the full report once.
Use `get_job(job_id=..., include_preview=false)` for subsequent status polls;
stop at ready/failed/cancelled, and inspect errors before retrying.

## One contour across three masters

Replace the illustrative IDs/names below with the exact known font/master IDs:

```json
{
  "document_id": "doc_known",
  "kind": "start_nodes",
  "glyphs": ["a"],
  "options": {
    "masters": ["LIGHT-ID", "REGULAR-ID", "BOLD-ID"],
    "path": 0,
    "referenceMaster": "LIGHT-ID"
  }
}
```

Pass this to `start_job`. Select 1–100 explicit glyphs and 2–32 masters.
Omitted `masters` selects the font's masters; omitted `referenceMaster` selects
the first selected master in font order. One `path` index applies to each glyph
and master. `path` is zero-based in `layer.paths` (0–255), excluding components:
in a path/component/path layer, path 1 is shape 2.

Optional `referenceNode` is zero-based in the reference path's entire node
collection, including off-curves (0–4095); it must identify an existing on-curve
landmark. Default is the reference contour's current native start, its last
node. V2 retains the reference layer's existing cyclic phase: choosing node 0
as a landmark does not make node 0 a new start in that reference. Other masters
rotate to the corresponding phase. The report gives `referenceNode`, matched
`landmarkNode`, `shift` and exact glyph/layer/path locations; a zero shift means
unchanged. Review these before `apply_job(job_id=..., include_preview=false)`.

## Evidence and recovery

Supported contours contain native lines and cubic segments. Cubic endpoints
need exactly two incoming off-curve controls, including at the cyclic boundary;
lines need none. Malformed segments, unverified node types, open paths,
ambiguous landmarks, mismatched topology/winding and unavailable targets are
rejected before an applicable patch. Use the returned location and reason to
inspect the contour in Glyphs. Structural repairs are manual; direction
normalization is a separate task followed by reinspection, never a silent step.

After application, reinspect explicit layers with `read_entities`, using widths
and `outlineHash` plus native contour/landmark inspection as needed. An outline
hash changes with node order; it alone does not prove geometric preservation
or good interpolation. Preserve node objects/types/smooth flags, geometry,
metadata, hints, anchors, components and advances. Native Undo/Redo are grouped
per glyph in Edit View; `discard_job` cancels or restores the whole job. Retain
the job ID across uncertain responses rather than creating another write.
Restored data does not guarantee a cleared dirty indicator.

A saved-source repeat is a no-op after the designer explicitly saves the
accepted alignment. A dirty unsaved repeat is refused; it is not a no-op claim.
Alignment establishes supported correspondence, not arbitrary compatibility
repair or interpolation quality. No older-private-build fallback workflow.
