# Exact kerning edits

For an explicit value or pair map, use `kerning_edit` through the existing
conversation workflow. Require `kerning.edit.exact.v1` and `kerning_edit` in the
current status. A missing capability is an installation gap. Preparation uses
bounded native reads, with no external worker or full-font copy. Reuse the
known document and exact master IDs; never substitute the current font.

```json
{"document_id":"doc_…","kind":"kerning_edit","idempotency_key":"task-kerning-1","options":{"edits":[{"op":"set","master":"exact-master-id","direction":"LTR","left":{"kind":"glyph","name":"A"},"right":{"kind":"group","key":"@MMK_R_V"},"value":-72.5},{"op":"remove","master":"exact-master-id","direction":"LTR","left":{"kind":"glyph","name":"T"},"right":{"kind":"glyph","name":"o"}}]}}
```

Each batch contains 1–100 entries. `set` requires a finite numeric `value`,
including fractional values and zero. `remove` has no value field: deletion
can reveal inherited group kerning. Null is not an assignment or deletion
sentinel in this request. Duplicate/conflicting targets are rejected before
application. Split larger explicitly authorized maps into bounded batches;
finish and, when authorized, save between batches as required by prerequisites.
Never report an unfinished batch sequence as complete.

Each side explicitly identifies a glyph name or native group key. Read actual
group properties when unknown; never invent groups or change membership.
Use `rightKerningKey` / `leftKerningKey` for the first/second LTR side,
`leftKerningKey` / `rightKerningKey` for RTL, and `bottomKerningKey` /
`topKerningKey` for vertical. These correspond to L/R, R/L and T/B key prefixes.
“Left” and “right” fields mean native first/second table keys in that direction.
Groups require an existing member; orphan stored groups need investigation.
Different masters/directions can share a batch. No top-level `glyphs` or `delta`.

Both preparation and application require the intended saved, clean document.
Saving needs separate or existing authorization. A result-focused edit request
authorizes apply mode; explicit preview uses `mode:"preview"` and waits.
Preparation does not change values, save, run Python or perform collision
analysis. Changed document/target evidence invalidates the prepared action.

Verify exact stored entries after application, including unaffected controls.
**Undo these changes** restores only recorded values and presence, with conflict
checks. **Keep changes without saving** ends wrapper recovery, leaves unsaved
edits dirty and preserves native Undo/Redo. **Save font** follows the verified
whole-document save workflow. Native history belongs to a first-side glyph. For a first-side group,
guarded exact edits prefer a selected member in the target master whose
direction-specific group matches, otherwise the prepared representative.
Select that glyph to access its native history; unavailable history refuses the
edit. Native history is separate from whole-job selective recovery. Reconcile uncertain outcomes using the same
job/workflow instead of dispatching another edit.

An exact assignment is not optical kerning. Use [proofing](kerning-proofing.md)
to inspect candidates, and retain the collision algorithm only when requested.
