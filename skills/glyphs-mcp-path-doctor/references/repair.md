# Qualified seam repair

Use `$glyphs-mcp-outlines-docs` and its [typed outline lifecycle](https://github.com/thierryc/Glyphs-mcp/blob/main/skills/glyphs-mcp-outlines-docs/references/path-editing.md).
The user must have requested the exact repair scope. Retain `compatibilityPolicy:
preserve`; prepare one exact layer target per independently diagnosed state hash
and include all corresponding master targets together. Native preparation checks
master correspondence. A geometry-only guard is insufficient.

```json
{"compatibilityPolicy":"preserve","targets":[
 {"glyph":"generic","layers":{"scope":"ids","ids":["MASTER"]},
  "referenceLayer":"MASTER","guards":[{"path":0,"hash":"FRESH_PATH_HASH"}],
  "operations":[{"op":"normalize_closed_seam","path":0,"stateHash":"FRESH_STATE_HASH"}]}]}
```

The two hashes use the same full native path state, including attributes,
profiles and explicit/inherited values. Use returned values, not placeholders.
Preparation/application revalidate state; fresh manual edits invalidate the
proposal. Never weaken a guard or replay an uncertain write.

Repair is currently qualified only for foreground ordinary-master layers.
Historical, special and background-layer repairs remain unsupported.

Qualification requires a closed path with node 0 a line and an exact duplicate
last on-curve endpoint, forming the automatic zero closing line. The incoming
line/cubic remains real. Node 0 retains the seam XY/start position and receives
the incoming endpoint's segment type and full Pen-point array. The last duplicate
maps to 0. All other node addresses remain fixed. Identical redundant t=1
controls can be reconciled; absent storage remains absent. Conflicting or
unsupported data, locks and hint references hold the repair for explicit review.
The intentional incoming diagonal must never be smoothed or removed.

Mutation preparation retains the existing saved-clean-baseline requirement.
Do not save an owner's font merely to satisfy it. Experiments use an explicitly
authorized disposable live duplicate; Save As needs authorization for its new
private local destination. `cleanup_paths` is not a qualified substitute.

After applying, independently compare all real segment coordinates/types/handles,
profile t/width/height/angle/placement/progression, explicit/inherited defaults,
path order, fill and smoothness. Check unrelated data and corresponding masters.
Run diagnosis again: a second repair should have nothing to change. Separately
inspect native selection/dragging, handles and width-aware appearance at multiple
scales, including joins, counters, overlaps and seams. Report untested behavior.

Typed jobs reuse selective `discard_job` and native glyph Undo/Redo; separately
authorized `accept_job` saves the whole font and ends wrapper recovery. Never
save, restore, reload or settle an owner's unrelated workflow during qualification.

Native qualification currently covers Glyphs 4.2 (4202). Other builds remain
diagnostic-only. Glyphs native Save can serialize coordinates at reduced precision;
exact repair in memory does not promise lossless Save/reopen. Explain that known
limit before a requested Save of precision-sensitive work. Do not save merely to
finish a diagnosis or an unsaved repair.
