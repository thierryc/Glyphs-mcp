---
title: First-pass slant
---

The `slant` job produces an experimental first-pass italic by applying native slant to selected master layers. It preserves advance widths and uses explicit coordinate patches. It does not build a complete optical italic.

```json
{
  "document_id": "<document ID>",
  "kind": "slant",
  "glyphs": ["H", "n", "o"],
  "options": {"angle": 12, "pivotY": 0, "preserveStraightStems": false}
}
```

Use a disposable copy and save its baseline first. `angle` is a nonzero number between −30 and +30 degrees; its default is 12. `pivotY` defaults to 0. `masters` selects master IDs, otherwise all masters are considered. Omit `delta`.

## Scope and preservation

Foreground nodes and anchors follow native slant. Widths, node identity, hints and fractional values remain protected. Manual components account for whether their base is also selected to avoid applying the shear twice.

Automatically aligned component layers are skipped without changing their local data, although their displayed outlines can inherit changes to a selected base. Lossy component-matrix round trips reject preparation. Special layers, arbitrary smart-component correction and a full balanced-italic construction are outside this job.

The optional `preserveStraightStems` pass conservatively restores perpendicular width for accepted opposite straight sides. It skips curve-adjacent segments and unsafe corrections. It is not a general curve or weight correction.

## Review and finish

Inspect `get_job` for coordinate changes, correction evidence and skipped-layer reasons. Apply only the reviewed proposal. Compare several masters and text samples, inspect curves with the [companions](workflows/visual-review.mdx), and try native Undo/Redo.

Use `discard_job` to restore current affected targets or, when persistence is
authorized, `accept_job` to verify the targets and save the whole document.
Further design work, alternate forms and font metadata belong to the designer's
native workflow.

Historical v1 optical-italic experiments and their sources remain in the [v1 italic guide](/docs/italic-first-pass); they are not promises of v2 functionality.
