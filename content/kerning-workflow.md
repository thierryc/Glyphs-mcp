---
title: Collision kerning
---

The `kerning_collision` job checks **explicit left-to-right glyph pairs** against a requested sampled clearance. It loosens collisions by creating or updating pair exceptions while leaving shared group values intact.

```json
{
  "document_id": "<document ID>",
  "kind": "kerning_collision",
  "options": {"pairs": [["A", "V"], ["T", "o"]], "targetGap": 5, "denseStep": 10}
}
```

Pass pairs in `options.pairs`; do not pass `glyphs` or `delta`. `options.masters` limits the master IDs, otherwise all masters are considered. The default target gap is 5 font units and dense step is 10.

## Review before applying

The worker resolves native groups and exceptions, performs a coarse scan and refines near the target. `get_job` reports native effective values, stored exceptions, class keys, sampling density, minima and unavailable pairs. Inspect the full report when the compact sample is insufficient.

The result only loosens a pair toward the sampled target. It does not generate an optimal optical-kerning system or guarantee clearance between sample heights. RTL and vertical kerning storage can be read, but this collision geometry workflow accepts LTR only.

## Verify the result

After `apply_job` completes, review the chosen pairs in Glyphs across the affected masters. Read the exact exception using `read_entities` with a `kind="kerning"` selector and `fields=["value"]`. An absent value is `null`; zero is a stored value and is not interchangeable with absence.

Native Undo/Redo retains exact values and exception presence. `discard_job` restores the job's current targets; native Save accepts the reviewed changes. See [Safety and recovery](concepts/safety-model.mdx).
