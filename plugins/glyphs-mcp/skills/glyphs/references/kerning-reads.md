# Exact stored kerning

Reuse the connection and `document_id` already verified through `$glyphs` for
fresh reads of the same font. Resolve the binding only if missing. Follow
[document targeting](document-targeting.md) for stale IDs and current/frontmost
intent. Reuse known exact master IDs scoped to this document. If unknown, use
the existing `masters` selector in [master reads](master-reads.md), not a guessed
name or ID.

Use 1–100 explicit selectors and exactly `fields:["value"]`. Each selector
requires `kind:"kerning"`, an exact native `master` ID, `direction`, `left` and
`right`. Direction is case-sensitive: `LTR`, `RTL` or `vertical`.

```json
{"document_id":"<retained document ID>","entities":[{"kind":"kerning","master":"<exact native master ID>","direction":"LTR","left":"A","right":"V"},{"kind":"kerning","master":"<exact native master ID>","direction":"LTR","left":"o","right":"V"},{"kind":"kerning","master":"<exact native master ID>","direction":"LTR","left":"X","right":"Y"},{"kind":"kerning","master":"<exact native master ID>","direction":"LTR","left":"@MMK_L_A","right":"@MMK_R_V"}],"fields":["value"]}
```

Resolve the placeholders before calling. Keys are glyph names or established
stored `@MMK_` group keys, not v1 native glyph IDs. Group keys must be supplied
or established by task evidence; do not infer them from glyph names. This read
does not enumerate group membership. The LTR example is not a group-key naming
rule for every direction. RTL/vertical reads can use verified glyph-name pairs.
An unknown group-key combination can be absent; an unknown glyph name is an
input error.

Successful `data` echoes each selector with `values.value`, in request order.
`null` means no stored entry for these exact keys, master and direction. `0` is
a stored zero. Preserve fractional values. Neither absence nor zero computes
effective kerning through class/exception precedence. Report 07's Regular test
fixture returns `[-90.125, 0, null, -70.25]` for the four examples; these values
are test expectations, not assumptions about another font.

Dirty and unsaved live fonts are readable without a Save, job or external source
script. Pure inspection stops after reporting the evidence. A clean saved
source is a job preparation/application requirement, not a read prerequisite.
Only prepare collision repair when requested; that separate workflow is LTR
only and has its own evidence and review requirements.

One bad selector rejects the entire request; do not report partial success.

| Result | Recovery |
| --- | --- |
| `document_not_found` | Discard the stale binding and rediscover the original intended font. Report absence or ambiguity; never silently substitute another font. |
| Kerning `invalid_request` | Correct the exact master ID, direction, glyph name, required keys or count. If masters changed, enumerate them using the same document ID. Do not rediscover documents for this input error. |
| `unsupported_read` | First check selector kind and exactly `fields:["value"]`. A proven private installation mismatch means the installation needs updating: update bridge, sidecar and skills together, reload and verify fresh status. Do not substitute an earlier private workflow. |
| `ok:true`, value `null` | Report exact stored absence, without converting it to zero or effective kerning. |
| `ok:true`, value `0` | Report stored zero, preserving its distinction from absence. |

Missing kerning glyph/master inputs return `invalid_request`, not the
`target_not_found` used by separate glyph/layer reads. Do not invent a new
kerning capability flag, raw-table tool, or fallback Python workflow.
